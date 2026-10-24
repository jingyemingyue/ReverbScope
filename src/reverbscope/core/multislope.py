"""Single- versus double-slope fit of an energy decay curve.

Method (see docs/MEASUREMENT_METHODOLOGY.md §5b for the references)
---------------------------------------------------------------------
A room with coupled volumes (a chapel opening onto a nave, a stage house, a
reverberant side aisle) decays with more than one rate: the Schroeder curve
bends from a fast early slope into a slower late one. ISO 3382-2 Annex B
measures the bend (curvature ``C`` and non-linearity ``xi``) and
:mod:`reverbscope.core.decay` uses them only to *flag* that a single
reverberation time does not describe the decay. This module *fits* the bend.

1. **Energy decay curve.** The squared band response from the onset (the
   same onset as the ISO fits) to the end of the record is integrated
   backwards (Schroeder 1965) *without* Lundeby truncation or late-decay
   compensation, and normalised to 1 (0 dB) at the onset. Trailing digital
   silence (exact zeros) is removed first. The noise term of the model below
   describes what truncation would otherwise remove.
2. **Model** (Xiang 1995; the form used by DecayFitNet, Gotz et al. 2022)::

       EDC(t) = sum_i A_i (exp(-13.8155 t / T_i) - exp(-13.8155 L / T_i)) + N (L - t)

   ``t`` in s after the direct sound, ``L`` the end of the integration,
   ``T_i`` the 60 dB decay time of slope ``i``, ``A_i`` its amplitude and
   ``N`` the noise power (as a fraction of the onset EDC per second).
3. **Fit range.** From the end of the direct sound (the same first sample as
   the ISO fits) to ``1 - TAIL_DISCARD_FRACTION`` (95 %) of the integration
   (the last samples of a backward integral hold too few samples to have a
   stable logarithm; DecayFitNet's preprocessing discards the end of the EDC
   for the same reason, clause not verified). The EDC is resampled onto
   :data:`FIT_POINTS` (100) points evenly spaced in time.
4. **Fit.** Bounded nonlinear least squares (``scipy.optimize.least_squares``,
   trust-region reflective) of ``10 log10(model) - EDC_dB`` over the
   parameters ``log T_i``, ``log A_i`` and ``log N``. One slope starts from
   the band's T30 (else T20, else EDT, else the first 20 dB of the curve);
   two slopes from several pairs around the ISO values, the Lundeby late
   slope and the one-slope fit. The best of the starts is kept.
5. **Model selection.** ``BIC = K ln(max(RSS / K, sigma^2)) + p ln K``
   (Schwarz 1978) with ``K`` the fitted points, ``p`` = 3 (one slope) or 5
   (two slopes) and ``sigma`` = :data:`RESIDUAL_FLOOR_DB` (a floor on the
   residual so two near-perfect fits are not told apart by rounding). BIC
   is the large-sample approximation of the Bayesian evidence that Xiang,
   Goggans et al. (2011) use to choose the number of slopes. Two slopes are
   chosen only when ``BIC(1) - BIC(2) >= DELTA_BIC_MIN`` (10, "very strong"
   on the Kass & Raftery 1995 scale) *and* the two-slope model is plausible:

   * the slopes differ: ``T2 >= SLOPE_RATIO_MIN * T1`` (1.25);
   * the turning point (where the two exponentials are equal) lies inside the
     fit range, at least :data:`KNEE_MIN_DROP_DB` (3 dB) below the level at
     the fit start, so the fast slope is a decay and not a step of the
     direct sound;
   * the curve at the turning point is at least
     :data:`KNEE_ABOVE_NOISE_DB` (10 dB) above the noise term there, so the
     late slope is seen above the noise;
   * the single-slope model misses the curve somewhere by at least
     :data:`SINGLE_MISS_MIN_DB` (1 dB): a straight decay that a second
     slope only fits more closely is not split.

   A two-slope fit that wins on BIC but fails a rule is reported as one slope
   with a note naming the rule. These thresholds are ReverbScope's choice,
   set with the synthetic decays in ``tests/unit/test_multislope.py`` and
   checked on the open Aachen data set (docs/validation/).
6. **Validity.** No model is fitted (``INSUFFICIENT_RANGE``) when the band's
   decay range is less than :data:`MIN_DECAY_RANGE_DB` (30 dB). The numbers
   are ``UNRELIABLE`` when the fit did not converge, when ``B * T1`` is less
   than the time-reversed filtering limit of the ISO fits (4), or when the
   response is cut short (a gate: the model's noise term does not describe a
   cliff). The ISO metrics (EDT, T20, T30, RT60, C, xi) are not changed by
   this fit.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import least_squares

from reverbscope.i18n import diag
from reverbscope.models.audio import FloatArray
from reverbscope.models.result import (
    DECAY_60_DB_NEPER,
    DecaySlopeModel,
    MultiSlopeFit,
    SlopeUncertainty,
    Validity,
)

#: No model below this decay range (dB, loudest block to noise floor).
MIN_DECAY_RANGE_DB = 30.0
#: The last 5 % of the backward integral are not fitted.
TAIL_DISCARD_FRACTION = 0.05
#: The fit starts at the first sample at or below this EDC level (dB), as T20/T30 do.
FIT_START_DB = -5.0
#: Points the EDC is resampled onto for the fit (evenly spaced in time).
FIT_POINTS = 100
#: Residual floor (dB) in the BIC; see the module docstring.
RESIDUAL_FLOOR_DB = 0.05
#: Lower bound of the effective number of independent points in the BIC.
MIN_EFFECTIVE_POINTS = 10.0
#: Two slopes need at least this BIC advantage (Kass & Raftery: > 10 is very strong).
DELTA_BIC_MIN = 10.0
#: The slow slope must be at least this many times the fast one.
SLOPE_RATIO_MIN = 1.25
#: The turning point must be this far below the level at the fit start (dB):
#: a fast part shorter than the EDT range (10 dB) is the early decay that EDT
#: already describes (early reflections near the source), not a second slope.
KNEE_MIN_DROP_DB = 10.0
#: After the turning point the slow slope must decay this much (dB) above the
#: noise term.
LATE_VISIBLE_DB = 10.0
#: The EDC at the turning point must be this far above the noise term (dB).
KNEE_ABOVE_NOISE_DB = 10.0
#: Two slopes only when the one-slope model misses the curve by this much (dB).
SINGLE_MISS_MIN_DB = 1.0
#: ``B * T1`` below this: the band filter's own decay is comparable to the
#: fast slope (the ISO fits' limit, Jacobsen & Rindel 1987).
MIN_BT_PRODUCT = 4.0
#: Decay data rate of Xiang & Sü Gül (2025): ``f_d = DATA_RATE_FACTOR / T1``
#: (about 110 / T1). Their Eqs. (5)-(6) keep the single-exponential spectrum
#: up to where it has fallen to 1/20 of its 0 Hz value,
#: ``f_max = 20 * 13.8155 / (2 pi T)`` (about 44 / T), and sample at
#: ``2.5 f_max``. The equations are images on the publisher page; this
#: reading reproduces the paper's own choices (2.18 s -> 50 Hz,
#: 11.5 s -> 10 Hz). See ADR 0006.
DATA_RATE_FACTOR = 2.5 * 20.0 * DECAY_60_DB_NEPER / (2.0 * np.pi)
#: Two-sided standard-normal quantiles of the 68.27 % and 95 % intervals.
Z68 = 1.0
Z95 = 1.959963984540054
#: A log-parameter standard deviation above this (a factor of e^5 = 148 at
#: one sigma) means the parameter is not identified: no uncertainty is given.
_MAX_LOG_SD = 5.0
#: ``J^T J`` worse conditioned than this: no uncertainty is given.
_MAX_CONDITION = 1e14
#: Iteration limit of one least-squares start.
MAX_EVALUATIONS = 200
#: Bounds of the decay times (s) and amplitudes (fraction of the onset EDC).
_MIN_DECAY_S = 0.005
_MIN_AMPLITUDE = 1e-12
_MAX_AMPLITUDE = 10.0
_MIN_NOISE = 1e-30
_TINY = 1e-300
_LOG10_E = 10.0 / np.log(10.0)


@dataclass(frozen=True)
class _Fit:
    decay_times_s: tuple[float, ...]
    amplitudes: tuple[float, ...]
    noise_term: float
    rss_db2: float
    max_miss_db: float
    converged: bool
    residuals_db: FloatArray
    #: Log parameters (``log T_i``, ``log A_i``, ``log N``) in fit order, the
    #: Jacobian of the dB residuals with respect to them at the solution
    #: (columns of parameters at a bound are zero) and the ascending order of
    #: the decay times. Used only by :func:`slope_uncertainty`.
    log_params: FloatArray
    jacobian_db: FloatArray
    order: tuple[int, ...]


def raw_energy_decay(
    power: FloatArray, onset: int, time_origin_index: int, sample_rate: int
) -> tuple[FloatArray, FloatArray, float]:
    """Untruncated EDC (linear, 1 at the onset), its times and ``L``.

    ``power`` is the squared band response; trailing exact zeros are removed.
    Times are in seconds after ``time_origin_index``; ``L`` is the time just
    after the last sample.
    """
    segment = np.asarray(power[onset:], dtype=np.float64)
    nonzero = np.flatnonzero(segment)
    end = int(nonzero[-1]) + 1 if nonzero.size else 1
    segment = segment[:end] if segment.size else np.zeros(1, dtype=np.float64)
    edc = np.cumsum(segment[::-1])[::-1]
    start = float(edc[0]) if edc.size and edc[0] > 0.0 else 1.0
    edc = edc / start
    times = (np.arange(edc.shape[0], dtype=np.float64) + onset - time_origin_index) / sample_rate
    integration_end = float(times[-1] + 1.0 / sample_rate)
    return times, edc, integration_end


def _model(params: FloatArray, slopes: int, t: FloatArray, end: float) -> FloatArray:
    decays = np.exp(params[:slopes])
    amplitudes = np.exp(params[slopes : 2 * slopes])
    noise = np.exp(params[2 * slopes])
    total = noise * (end - t)
    for decay, amplitude in zip(decays, amplitudes, strict=True):
        total = total + amplitude * (
            np.exp(-DECAY_60_DB_NEPER * t / decay) - np.exp(-DECAY_60_DB_NEPER * end / decay)
        )
    return np.asarray(total, dtype=np.float64)


def _fit(
    slopes: int,
    starts: list[tuple[tuple[float, ...], tuple[float, ...], float]],
    t: FloatArray,
    edc_db: FloatArray,
    end: float,
    max_decay_s: float,
) -> _Fit | None:
    lower = np.array(
        [np.log(_MIN_DECAY_S)] * slopes + [np.log(_MIN_AMPLITUDE)] * slopes + [np.log(_MIN_NOISE)]
    )
    upper = np.array(
        [np.log(max_decay_s)] * slopes + [np.log(_MAX_AMPLITUDE)] * slopes + [np.log(1.0)]
    )

    # Levenberg-Marquardt (MINPACK) on log parameters: several times faster
    # than a bounded trust-region solver here. The bounds are kept by clipping
    # inside the model (a clipped parameter has no gradient), and the solution
    # is clipped the same way.
    def residual(raw: FloatArray) -> FloatArray:
        params = np.clip(raw, lower, upper)
        value = _model(params, slopes, t, end)
        return np.asarray(_LOG10_E * np.log(np.maximum(value, _TINY)) - edc_db, dtype=np.float64)

    def jacobian(raw: FloatArray) -> FloatArray:
        # d(10 log10 m)/d(log p) = (10 / ln 10) * (dm / d log p) / m.
        params = np.clip(raw, lower, upper)
        value = np.maximum(_model(params, slopes, t, end), _TINY)
        columns = np.empty((t.shape[0], 2 * slopes + 1), dtype=np.float64)
        for i in range(slopes):
            decay = np.exp(params[i])
            amplitude = np.exp(params[slopes + i])
            rate_t = DECAY_60_DB_NEPER * t / decay
            rate_end = DECAY_60_DB_NEPER * end / decay
            decay_t, decay_end = np.exp(-rate_t), np.exp(-rate_end)
            columns[:, i] = amplitude * (decay_t * rate_t - decay_end * rate_end)
            columns[:, slopes + i] = amplitude * (decay_t - decay_end)
        columns[:, 2 * slopes] = np.exp(params[2 * slopes]) * (end - t)
        columns[:, (raw < lower) | (raw > upper)] = 0.0
        return np.asarray(_LOG10_E * columns / value[:, None], dtype=np.float64)

    best: _Fit | None = None
    best_cost = np.inf
    for decays, amplitudes, noise in starts:
        x0 = np.log(
            np.array(
                [
                    *(min(max(d, _MIN_DECAY_S * 1.01), max_decay_s * 0.99) for d in decays),
                    *(min(max(a, _MIN_AMPLITUDE * 10), _MAX_AMPLITUDE * 0.99) for a in amplitudes),
                    min(max(noise, _MIN_NOISE * 10), 0.99),
                ]
            )
        )
        try:
            solution = least_squares(
                residual, x0, jac=jacobian, method="lm", max_nfev=MAX_EVALUATIONS
            )
        except (ValueError, FloatingPointError):
            continue
        if not np.all(np.isfinite(solution.fun)):
            continue
        cost = float(np.sum(solution.fun**2))
        if cost < best_cost:
            best_cost = cost
            params = np.clip(solution.x, lower, upper)
            order = np.argsort(params[:slopes])
            best = _Fit(
                decay_times_s=tuple(float(np.exp(params[i])) for i in order),
                amplitudes=tuple(float(np.exp(params[slopes + i])) for i in order),
                noise_term=float(np.exp(params[2 * slopes])),
                rss_db2=cost,
                max_miss_db=float(np.max(np.abs(solution.fun))),
                converged=bool(solution.status > 0),
                residuals_db=np.asarray(solution.fun, dtype=np.float64),
                log_params=np.asarray(params, dtype=np.float64),
                jacobian_db=jacobian(solution.x),
                order=tuple(int(i) for i in order),
            )
    return best


def effective_points(residuals_db: FloatArray) -> float:
    """``K / tau``: the number of independent points among correlated residuals.

    ``tau = 1 + 2 * sum(rho_k)`` is the integrated autocorrelation time of the
    residuals, summed over the initial positive lags (Geyer 1992's initial
    positive sequence, applied to single lags). An EDC is a running integral:
    its deviations from any smooth model are correlated over many points, so
    ``K`` resampled points carry far fewer independent observations.
    """
    r = np.asarray(residuals_db, dtype=np.float64)
    points = r.shape[0]
    centred = r - float(np.mean(r))
    variance = float(np.dot(centred, centred))
    if points < 4 or variance <= 0.0:
        return float(points)
    tau = 1.0
    for lag in range(1, points // 2):
        rho = float(np.dot(centred[:-lag], centred[lag:])) / variance
        if rho <= 0.0:
            break
        tau += 2.0 * rho
    return float(min(points, max(MIN_EFFECTIVE_POINTS, points / tau)))


def slope_uncertainty(
    fit: _Fit, t: FloatArray, end: float, bandwidth_hz: float
) -> SlopeUncertainty | None:
    """Standard deviations and intervals of ``fit``'s parameters (ADR 0006).

    ``t`` are the fitted times, ``end`` the end of the integration ``L`` and
    ``bandwidth_hz`` the band's bandwidth (half the sample rate for the
    unfiltered response). Two terms, in the log parameters, are added:

    **Analysis term** (Xiang & Sü Gül 2025). The likelihood of their
    Eq. (10) with uniform priors (Eq. 12) is ``Q(theta)^(-K/2)``, ``Q`` the
    sum of squared residuals over ``K`` decay data values. Its Laplace
    approximation at the least-squares solution is Gaussian with covariance
    ``(Q / K) (J^T J)^-1``. ``Q / K`` and ``J^T J / K`` do not depend on how
    finely a smooth EDC is sampled, so the width is set by ``K``; the paper
    counts the data at the adequate decay data rate ``f_d = 110 / T1``
    (Eq. 6), where their posterior spread matched repeated measurements. The
    covariance on the fit grid is rescaled to ``K_d = f_d * duration + 1``.
    It carries how well the model fits this curve (a misfit widens it).

    **Stochastic-decay term.** The EDC of a reverberant (random) response
    fluctuates around its expected curve, and the fluctuations are
    correlated over the whole tail, because ``EDC(t)`` integrates all later
    energy. For band-limited Gaussian noise with envelope ``e(t)`` (the
    derivative of the fitted model), ``Var EDC(t) = (1/B) int_t^L e^2`` and
    ``Cov(EDC(t_i), EDC(t_j)) = Var EDC(max(t_i, t_j))`` (the shared tail).
    In dB, ``Sigma_ij = (10/ln 10)^2 Var EDC(max) / (EDC_i EDC_j)``. The fit
    is ordinary least squares in dB, so its covariance is the sandwich
    ``(J^T J)^-1 J^T Sigma J (J^T J)^-1``. This term is what makes the
    intervals cover the generating decay times of synthetic responses
    (tests/unit/test_decay_uncertainty.py); the analysis term alone covers
    far less (residuals of an EDC are strongly correlated).

    Returns ``None`` when a decay time or amplitude sits at its bound, when
    ``J^T J`` is singular or when the standard deviation of a log decay time
    or log amplitude exceeds 5 (not identified). A noise term at its lower
    bound, one so small that ``J^T J`` is singular with it, or one whose own
    deviation exceeds 5 (no measurable floor) is held fixed and gets no
    uncertainty.
    """
    jac = fit.jacobian_db
    residuals = fit.residuals_db
    points, parameters = jac.shape
    slopes = len(fit.decay_times_s)
    if points <= parameters or not np.all(np.isfinite(jac)) or bandwidth_hz <= 0.0:
        return None
    free = ~np.all(jac == 0.0, axis=0)
    if not np.all(free[: 2 * slopes]):
        return None
    noise_index = 2 * slopes
    fastest = min(fit.decay_times_s)
    rate = DATA_RATE_FACTOR / fastest
    duration = float(t[-1] - t[0])
    variance = float(np.dot(residuals, residuals)) / points

    # Covariance of the dB curve of a random EDC (stochastic-decay term).
    rates = np.array([DECAY_60_DB_NEPER / d for d in fit.decay_times_s])
    amplitudes = np.array(fit.amplitudes)
    envelope = amplitudes * rates  # e(t) = sum_i a_i exp(-k_i t) + N
    noise = fit.noise_term
    tail_power = noise * noise * (end - t)
    edc = noise * (end - t)
    for i in range(slopes):
        decay_i = np.exp(-rates[i] * t) - np.exp(-rates[i] * end)
        edc = edc + amplitudes[i] * decay_i
        tail_power = tail_power + 2.0 * noise * envelope[i] * decay_i / rates[i]
        for j in range(slopes):
            both = rates[i] + rates[j]
            tail_power = tail_power + envelope[i] * envelope[j] * (
                (np.exp(-both * t) - np.exp(-both * end)) / both
            )
    edc = np.maximum(edc, _TINY)
    tail_variance = np.maximum(tail_power, 0.0) / bandwidth_hz
    later = np.maximum.outer(np.arange(points), np.arange(points))
    sigma = _LOG10_E**2 * tail_variance[later] / np.outer(edc, edc)

    # A noise term that is too small to matter (singular J^T J with it) or
    # not determined by the curve (huge deviation) is held fixed, like one at
    # its bound, and the rest is computed without it.
    while True:
        sub = jac[:, free]
        inverse = _stable_inverse(sub)
        if inverse is None:
            if free[noise_index]:
                free[noise_index] = False
                continue
            return None
        # Analysis term at the paper's data rate.
        data_points = max(float(sub.shape[1] + 2), rate * duration + 1.0)
        analysis = variance * inverse * (points / data_points)
        # Stochastic-decay term: least-squares sandwich.
        stochastic = inverse @ (sub.T @ sigma @ sub) @ inverse
        covariance = np.zeros((parameters, parameters))
        covariance[np.ix_(free, free)] = analysis + stochastic
        analysis_full = np.zeros((parameters, parameters))
        analysis_full[np.ix_(free, free)] = analysis
        sd = np.sqrt(np.maximum(np.diagonal(covariance), 0.0))
        sd_analysis = np.sqrt(np.maximum(np.diagonal(analysis_full), 0.0))
        if not (np.all(np.isfinite(sd)) and np.all(np.isfinite(sd_analysis))):
            return None
        if free[noise_index] and sd[noise_index] > _MAX_LOG_SD:
            free[noise_index] = False
            continue
        break

    order = fit.order
    decays = fit.decay_times_s
    if float(np.max(sd[:noise_index])) > _MAX_LOG_SD:
        # A decay time or amplitude not identified (a degenerate forced
        # fit): no interval rather than one spanning orders of magnitude.
        return None
    log_sd_t = [float(sd[i]) for i in order]
    log_sd_a = [float(sd[slopes + i]) for i in order]

    def interval(value: float, log_sd: float, z: float) -> tuple[float, float]:
        return (float(value * np.exp(-z * log_sd)), float(value * np.exp(z * log_sd)))

    knee_sd: float | None = None
    if slopes == 2:
        (t1, t2), (a1, a2) = decays, fit.amplitudes
        rate_difference = DECAY_60_DB_NEPER * (1.0 / t1 - 1.0 / t2)
        if rate_difference > 0.0 and a1 > 0.0 and a2 > 0.0:
            knee = float(np.log(a1 / a2)) / rate_difference
            # d knee / d(log T1, log T2, log A1, log A2), sorted order.
            sorted_gradient = (
                knee * DECAY_60_DB_NEPER / (t1 * rate_difference),
                -knee * DECAY_60_DB_NEPER / (t2 * rate_difference),
                1.0 / rate_difference,
                -1.0 / rate_difference,
            )
            gradient = np.zeros(parameters)
            for position, index in enumerate(order):
                gradient[index] = sorted_gradient[position]
                gradient[slopes + index] = sorted_gradient[2 + position]
            knee_sd = float(np.sqrt(max(float(gradient @ covariance @ gradient), 0.0)))
    return SlopeUncertainty(
        decay_times_sd_s=tuple(d * s for d, s in zip(decays, log_sd_t, strict=True)),
        decay_times_ci68_s=tuple(
            interval(d, s, Z68) for d, s in zip(decays, log_sd_t, strict=True)
        ),
        decay_times_ci95_s=tuple(
            interval(d, s, Z95) for d, s in zip(decays, log_sd_t, strict=True)
        ),
        amplitudes_sd_db=tuple(float(_LOG10_E * s) for s in log_sd_a),
        noise_sd_db=float(_LOG10_E * sd[noise_index]) if free[noise_index] else None,
        knee_time_sd_s=knee_sd,
        decay_times_analysis_sd_s=tuple(
            float(d * sd_analysis[i]) for d, i in zip(decays, order, strict=True)
        ),
        data_points=float(data_points),
        data_rate_hz=float(rate),
        grid_adequate=bool(points >= data_points),
    )


def _stable_inverse(jac: FloatArray) -> FloatArray | None:
    """``(J^T J)^-1``, or ``None`` when it is (numerically) singular."""
    information = jac.T @ jac
    try:
        if not np.isfinite(information).all() or np.linalg.cond(information) > _MAX_CONDITION:
            return None
        return np.asarray(np.linalg.inv(information), dtype=np.float64)
    except np.linalg.LinAlgError:
        return None


def _bic(fit: _Fit, points: int, parameters: int, effective: float) -> float:
    """BIC with ``effective`` independent points (see :func:`effective_points`)."""
    variance = max(fit.rss_db2 / points, RESIDUAL_FLOOR_DB**2)
    return float(effective * np.log(variance) + parameters * np.log(effective))


def _knee(fit: _Fit) -> float | None:
    """Time at which the two exponentials are equal (``None`` if never)."""
    (t1, t2), (a1, a2) = fit.decay_times_s, fit.amplitudes
    rate = DECAY_60_DB_NEPER * (1.0 / t1 - 1.0 / t2)
    if rate <= 0.0 or a1 <= 0.0 or a2 <= 0.0:
        return None
    return float(np.log(a1 / a2) / rate)


def _to_model(
    fit: _Fit, bic: float, t: FloatArray, end: float, bandwidth_hz: float
) -> DecaySlopeModel:
    return DecaySlopeModel(
        slope_count=len(fit.decay_times_s),
        decay_times_s=fit.decay_times_s,
        amplitudes=fit.amplitudes,
        noise_term=fit.noise_term,
        bic=bic,
        rms_residual_db=float(np.sqrt(fit.rss_db2 / FIT_POINTS)),
        uncertainty=slope_uncertainty(fit, t, end, bandwidth_hz),
    )


def _initial_decay(edc_db: FloatArray, t: FloatArray, *candidates: float | None) -> float:
    for value in candidates:
        if value is not None and np.isfinite(value) and value > 0.0:
            return float(value)
    below = np.flatnonzero(edc_db <= edc_db[0] - 20.0)
    if below.size and t[below[0]] > t[0]:
        return float(60.0 * (t[below[0]] - t[0]) / 20.0)
    return 1.0


def fit_multi_slope(
    power: FloatArray,
    sample_rate: int,
    *,
    onset: int,
    time_origin_index: int,
    first_index: int,
    decay_range_db: float,
    bandwidth_hz: float | None,
    reference_decays_s: tuple[float | None, float | None, float | None] = (None, None, None),
    late_decay_s: float | None = None,
    cut_short: bool = False,
) -> MultiSlopeFit:
    """Fit one and two slopes to the band's EDC and choose between them.

    ``power`` is the squared band response, ``onset`` and ``first_index``
    (relative to the onset) are the integration start and the first sample
    after the direct sound as used by the ISO fits, ``decay_range_db`` the
    band's peak-to-noise range, ``reference_decays_s`` the band's (T30, T20,
    EDT) seconds and ``late_decay_s`` the 60 dB time of the Lundeby late
    slope, all only as starting values.
    """
    if not np.isfinite(decay_range_db) or decay_range_db < MIN_DECAY_RANGE_DB:
        return MultiSlopeFit(
            validity=Validity.INSUFFICIENT_RANGE,
            selected_slopes=None,
            reason=diag(
                "Insufficient decay range for a slope fit: {available:.1f} dB available, "
                "{needed:.0f} dB needed",
                available=decay_range_db if np.isfinite(decay_range_db) else 0.0,
                needed=MIN_DECAY_RANGE_DB,
            ),
        )
    times, edc, end = raw_energy_decay(power, onset, time_origin_index, sample_rate)
    first = min(max(0, first_index), times.shape[0] - 1)
    # Start where the ISO T20/T30 ranges start (-5 dB), after the direct sound:
    # the first 5 dB are the direct sound and the earliest reflections.
    below = np.flatnonzero(edc[first:] <= 10.0 ** (FIT_START_DB / 10.0))
    if below.size:
        first += int(below[0])
    last = int(np.floor((1.0 - TAIL_DISCARD_FRACTION) * times.shape[0])) - 1
    if last - first < FIT_POINTS:
        return MultiSlopeFit(
            validity=Validity.INSUFFICIENT_RANGE,
            selected_slopes=None,
            integration_end_s=end,
            reason=diag("the decay curve is too short for a slope fit"),
        )
    t_fit = np.linspace(times[first], times[last], FIT_POINTS)
    edc_fit = np.interp(t_fit, times[first : last + 1], edc[first : last + 1])
    edc_db = _LOG10_E * np.log(np.maximum(edc_fit, _TINY))
    max_decay = max(4.0 * end, 1.0)
    # Bandwidth of the random decay process (uncertainty only).
    noise_bandwidth = bandwidth_hz if bandwidth_hz is not None else sample_rate / 2.0

    t30, t20, edt = reference_decays_s
    base = _initial_decay(edc_db, t_fit, t30, t20, edt)
    # Noise: the slope of the linear EDC over its last fifth.
    tail = max(2, FIT_POINTS // 5)
    noise0 = (edc_fit[-tail] - edc_fit[-1]) / max(t_fit[-1] - t_fit[-tail], 1e-9)
    noise0 = float(max(noise0, _MIN_NOISE * 10))
    one = _fit(
        1,
        [((base,), (1.0,), noise0)],
        t_fit,
        edc_db,
        end,
        max_decay,
    )
    if one is None:
        return MultiSlopeFit(
            validity=Validity.UNRELIABLE,
            selected_slopes=None,
            integration_end_s=end,
            reason=diag("the slope fit did not converge"),
        )
    early = _initial_decay(edc_db, t_fit, edt, t20, base)
    late = _initial_decay(edc_db, t_fit, late_decay_s, None, None)
    pairs: set[tuple[float, float]] = {
        (0.6 * one.decay_times_s[0], 1.6 * one.decay_times_s[0]),
        (early, max(late, 1.5 * early)),
        (0.5 * base, 2.0 * base),
        (0.8 * base, 3.0 * base),
        (0.9 * base, 1.4 * base),
    }
    starts: list[tuple[tuple[float, ...], tuple[float, ...], float]] = []
    for fast, slow in sorted(pairs):
        for share in (0.1, 0.01):
            starts.append(((fast, slow), (1.0, share), one.noise_term))
    two = _fit(2, starts, t_fit, edc_db, end, max_decay)

    # Both models are scored on the same effective number of points, from
    # the residuals of the richer model (its residuals are closest to the
    # EDC's own fluctuation; those of a misfit one-slope model are not noise).
    effective = effective_points(two.residuals_db if two is not None else one.residuals_db)
    bic_one = _bic(one, FIT_POINTS, 3, effective)
    models = [_to_model(one, bic_one, t_fit, end, noise_bandwidth)]
    notes: list[str] = []
    delta: float | None = None
    selected = 1
    knee_time: float | None = None
    knee_level: float | None = None
    chosen = one
    if two is not None:
        bic_two = _bic(two, FIT_POINTS, 5, effective)
        models.append(_to_model(two, bic_two, t_fit, end, noise_bandwidth))
        delta = bic_one - bic_two
        if delta >= DELTA_BIC_MIN:
            rejected = _implausible_double(two, one, t_fit, end)
            if rejected is None:
                selected = 2
                chosen = two
                knee_time = _knee(two)
                if knee_time is not None:
                    level = _model_db(two, np.array([knee_time]), end, include_noise=True)
                    knee_level = float(level[0])
            else:
                notes.append(rejected)

    validity = Validity.VALID
    reason: str | None = None
    if not chosen.converged:
        validity = Validity.UNRELIABLE
        reason = diag("the slope fit did not converge")
    if bandwidth_hz is not None and bandwidth_hz * chosen.decay_times_s[0] < MIN_BT_PRODUCT:
        validity = Validity.UNRELIABLE
        reason = _join(
            reason,
            diag(
                "B*T1 = {bt:.1f} < {minimum:g}: the band filter's own decay is comparable to "
                "the fast slope",
                bt=bandwidth_hz * chosen.decay_times_s[0],
                minimum=MIN_BT_PRODUCT,
            ),
        )
    if cut_short:
        validity = Validity.UNRELIABLE
        reason = _join(
            reason,
            diag("the response is cut short: the noise term of the slope model does not apply"),
        )
    return MultiSlopeFit(
        validity=validity,
        selected_slopes=selected,
        models=tuple(models),
        delta_bic=delta,
        fit_start_s=float(t_fit[0]),
        fit_end_s=float(t_fit[-1]),
        integration_end_s=end,
        knee_time_s=knee_time,
        knee_level_db=knee_level,
        reason=reason,
        notes=tuple(notes),
    )


def _join(existing: str | None, reason: str) -> str:
    return reason if not existing else f"{existing}; {reason}"


def _model_db(fit: _Fit, t: FloatArray, end: float, *, include_noise: bool) -> FloatArray:
    total = np.zeros_like(t) + (fit.noise_term * (end - t) if include_noise else 0.0)
    for decay, amplitude in zip(fit.decay_times_s, fit.amplitudes, strict=True):
        total = total + amplitude * (
            np.exp(-DECAY_60_DB_NEPER * t / decay) - np.exp(-DECAY_60_DB_NEPER * end / decay)
        )
    return np.asarray(_LOG10_E * np.log(np.maximum(total, _TINY)), dtype=np.float64)


def _implausible_double(two: _Fit, one: _Fit, t: FloatArray, end: float) -> str | None:
    """Why a two-slope fit that won on BIC is not reported (``None``: it is)."""
    t1, t2 = two.decay_times_s
    if t2 < SLOPE_RATIO_MIN * t1:
        return diag(
            "two slopes not reported: T2/T1 = {ratio:.2f} < {minimum:g}, the slopes are not "
            "distinct",
            ratio=t2 / t1,
            minimum=SLOPE_RATIO_MIN,
        )
    if one.max_miss_db < SINGLE_MISS_MIN_DB:
        return diag(
            "two slopes not reported: one slope fits the curve within {miss:.2f} dB "
            "(limit {limit:g} dB)",
            miss=one.max_miss_db,
            limit=SINGLE_MISS_MIN_DB,
        )
    knee = _knee(two)
    if knee is None or knee <= t[0] or knee >= t[-1]:
        return diag("two slopes not reported: the slopes do not cross inside the fitted range")
    start_db = float(_model_db(two, t[:1], end, include_noise=True)[0])
    knee_db = float(_model_db(two, np.array([knee]), end, include_noise=True)[0])
    if start_db - knee_db < KNEE_MIN_DROP_DB:
        return diag(
            "two slopes not reported: the turning point is only {drop:.1f} dB below the fit "
            "start (limit {limit:g} dB): the fast part is the early decay, not a second slope",
            drop=start_db - knee_db,
            limit=KNEE_MIN_DROP_DB,
        )
    noise_db = 10.0 * np.log10(max(two.noise_term * (end - knee), _TINY))
    if knee_db - noise_db < KNEE_ABOVE_NOISE_DB:
        return diag(
            "two slopes not reported: the turning point is only {margin:.1f} dB above the "
            "noise (limit {limit:g} dB)",
            margin=knee_db - noise_db,
            limit=KNEE_ABOVE_NOISE_DB,
        )
    # The slow slope has to be seen decaying above the noise term, not only
    # bridging the turning point and the floor (a drifting floor fits that).
    after = np.linspace(knee, t[-1], 200)
    slow = np.log10(two.amplitudes[1]) - np.log10(np.e) * DECAY_60_DB_NEPER * after / t2
    floor = np.log10(np.maximum(two.noise_term * (end - after), _TINY))
    above = np.flatnonzero(slow < floor)
    cross = after[above[0]] if above.size else after[-1]
    visible_db = 10.0 * np.log10(np.e) * DECAY_60_DB_NEPER * (cross - knee) / t2
    if visible_db < LATE_VISIBLE_DB:
        return diag(
            "two slopes not reported: the slow slope decays only {visible:.1f} dB above the "
            "noise after the turning point (limit {limit:g} dB)",
            visible=visible_db,
            limit=LATE_VISIBLE_DB,
        )
    return None
