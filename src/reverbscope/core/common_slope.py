"""Common-slope analysis: decay times shared by several positions in one room.

Method (see docs/MEASUREMENT_METHODOLOGY.md §3d and ADR 0005)
--------------------------------------------------------------
The common-slope model (Götz, Schlecht & Pulkki 2023, IEEE/ACM TASLP 31,
3945-3957) describes the late decay at *every* source-receiver position of a
room with the same few decay times ``T_k`` ("common slopes"); only their
amplitudes ``A_{r,k}`` and the noise term change from position ``r`` to
position. :mod:`reverbscope.core.multislope` fits one or two slopes to one
response; this module fits ``K`` = 1, 2 or 3 slopes to a *set* of responses
at once, band by band.

1. **Observations.** Each response is analysed by the product's own decay
   analysis (:func:`reverbscope.core.decay.analyze_band`, octave or opt-in
   one-third-octave bands, time-reversed filters, the same onset, fit start
   and per-response single/double-slope fit). From it this module takes the
   untruncated Schroeder EDC over the same fit range as the per-response fit
   (from the -5 dB point after the direct sound to 95 % of the integration),
   resampled to 100 points, and the band's power envelope ``|analytic|^2 / 2``
   sampled every ``1 / B`` s (``B`` the bandwidth; adjacent samples of a band
   of width ``B`` are then roughly uncorrelated). A response whose band has
   less than 30 dB of decay range is left out of that band with its reason.
2. **Common decay times (EDC fit).** For ``K`` slopes the model of position
   ``r`` is the per-response model with shared ``T_k``::

       EDC_r(t) = sum_k A_rk (exp(-13.8155 t / T_k) - exp(-13.8155 L_r / T_k)) + N_r (L_r - t)

   Starting values are the k-means clusters (in log T) of the per-response
   decay times, the approach Götz et al. found the most general; the
   ``T_k`` are then refined jointly over all positions by least squares of
   the dB error, with the amplitudes and noise of each position projected
   out (non-negative least squares of the relative error, re-weighted once:
   variable projection, Golub & Pereyra 1973). Every position therefore
   contributes to every ``T_k``, including slopes that are weak at most
   positions.
3. **Number of slopes.** ``BIC_K = sum_r n_r ln(max(RSS_r / 100, 0.05^2)) +
   p_K ln(sum_r n_r)`` with ``p_K = K + R (K + 1)`` and ``n_r`` the effective
   number of independent EDC points of position ``r``
   (:func:`reverbscope.core.multislope.effective_points`, from the residuals
   of the richest model). ``K + 1`` slopes replace ``K`` only when the BIC
   falls by at least 10 *and* the richer model is plausible: adjacent decay
   times differ by at least 1.25x, and every slope is *supported*, that is
   the largest term of the model, above the noise term, over at least 10 dB
   of decay at two positions or more (one when only one response is
   analysed) and at no fewer than 5 % of them, and the extra slope at least
   halves the RMS dB error at one position or more. The BIC threshold, the
   1.25x ratio and the 10 dB spans are those of the per-response fit (ADR
   0004); the support and improvement rules are this module's (ADR 0005).
4. **Amplitudes (LINEX / maximum likelihood).** Bai & Schlecht (DAFx25,
   "Estimation of multi-slope amplitudes in late reverberation") compare
   amplitude estimators for fixed common decay times and find the maximum-
   likelihood LINEX regression on the log energy the most efficient, with
   the EDC fit close behind but slightly biased. The LINEX loss on
   ``log h^2`` is the negative log-likelihood of a Gaussian response, which
   for power samples is the Itakura-Saito loss ``sum(y / v + ln v)``. With
   the common ``T_k`` fixed, the reported amplitudes and noise of each
   position minimise that loss on the envelope samples (Fisher scoring on
   the log amplitudes). They are converted to the units of the EDC model
   (fraction of the onset energy; noise per second), so they can be read like
   the per-response amplitudes. The EDC-fit amplitudes are kept as an option
   (``amplitude_method="edc"``).
5. **Joint IS-NMF / SAGE estimator (opt-in, experimental).** Bai, Elvander &
   Schlecht (arXiv:2610.05549) estimate the common decay rates and spatial
   amplitudes together as a parameterised non-negative matrix factorisation
   with the Itakura-Saito loss, by space-alternating generalised EM (SAGE):
   closed-form amplitude updates and a convex scalar Newton problem per decay
   rate, optionally contribution-weighted (CW-SAGE, ``p = 1``). The paper
   works on STFT bins; here it runs on the same band envelope samples as step
   4, started from the EDC estimate with the number of slopes of step 3 (the
   paper prescribes ``K``), ``p = 1`` iterations followed by ``p = 0``
   refinement. It has been validated on synthetic data only, by its authors
   and in ``tests/unit/test_common_slope.py``; on the Aachen data it is
   reported next to the EDC estimate, not instead of it.
6. **Validity.** A band is ``INSUFFICIENT_RANGE`` when no position has a
   usable decay, ``UNRELIABLE`` when ``B * T_1 < 4`` (band filter ringing) or
   the decay-time refinement did not converge.

Nothing in the single-response analysis changes: this is a separate,
multi-file analysis (``reverbscope common-slope``, ``reverbscope project
common-slope``).
"""

from __future__ import annotations

import itertools
import math
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from typing import Any

import numpy as np
from scipy.optimize import least_squares, nnls
from scipy.signal import hilbert

from reverbscope.core.decay import (
    _prepare_signal,
    _search_start,
    analyze_band,
    decay_lead_in_s,
    third_octave_decay_bands,
    third_octave_lead_in_s,
)
from reverbscope.core.filters import Band, apply_bandpass, band_fits, bandpass_sos, iec_band
from reverbscope.core.multislope import (
    DELTA_BIC_MIN,
    FIT_POINTS,
    KNEE_ABOVE_NOISE_DB,
    LATE_VISIBLE_DB,
    MIN_BT_PRODUCT,
    RESIDUAL_FLOOR_DB,
    SLOPE_RATIO_MIN,
    effective_points,
    raw_energy_decay,
)
from reverbscope.errors import ConfigurationError
from reverbscope.i18n import _, diag
from reverbscope.models.audio import FloatArray
from reverbscope.models.configuration import AnalysisSettings
from reverbscope.models.result import DECAY_60_DB_NEPER, ExcitationBand, Validity

#: Schema version of ``common-slope.json``.
COMMON_SLOPE_SCHEMA_VERSION = 1
#: ``CommonSlopeResult.method``.
COMMON_SLOPE_METHOD = diag(
    "common-slope model (Götz et al. 2023): shared decay times from a joint EDC fit over all "
    "positions, number of slopes by BIC"
)
#: Largest number of common slopes considered.
MAX_COMMON_SLOPES = 3
#: Decay-time estimators.
ESTIMATOR_EDC = "edc"
ESTIMATOR_SAGE = "is-sage"
ESTIMATORS = (ESTIMATOR_EDC, ESTIMATOR_SAGE)
#: Amplitude methods.
AMPLITUDES_LINEX = "linex"
AMPLITUDES_EDC = "edc"
AMPLITUDE_METHODS = (AMPLITUDES_LINEX, AMPLITUDES_EDC)
#: Envelope samples per response used by the amplitude and SAGE estimators
#: (more are thinned evenly; the samples are already about 1 / B apart).
MAX_ENVELOPE_SAMPLES = 4000
#: Scoring iterations of the LINEX amplitude fit.
LINEX_ITERATIONS = 60
#: SAGE iterations: contribution-weighted (p = 1), then plain (p = 0).
SAGE_WEIGHTED_ITERATIONS = 150
SAGE_PLAIN_ITERATIONS = 100
#: One more common slope must at least halve the RMS error at one position or
#: more (set with the synthetic decays in tests/unit/test_common_slope.py: a
#: spurious extra slope gains at most 40 % anywhere, a real one 55 % or more).
MIN_POSITION_IMPROVEMENT = 0.5
#: Every slope of a richer model must be supported at this many positions (one
#: when only one response is analysed) and at this fraction of them.
MIN_SUPPORT_POSITIONS = 2
MIN_SUPPORT_FRACTION = 0.05
#: Least-squares evaluations of one decay-time refinement.
MAX_EVALUATIONS = 200
_MIN_DECAY_S = 0.005
_TINY = 1e-300
_LOG10_E = 10.0 / math.log(10.0)


@dataclass(frozen=True)
class BandObservation:
    """One position's decay in one band, as the common-slope fits use it."""

    position: str
    band_label: str
    center_hz: float
    bandwidth_hz: float
    #: EDC fit points (s after the direct sound) and the EDC there (dB re onset).
    times_s: FloatArray
    edc_db: FloatArray
    integration_end_s: float
    #: Power-envelope samples: times (s after the direct sound) and power
    #: (fraction of the onset energy per sample).
    envelope_times_s: FloatArray
    envelope_power: FloatArray
    sample_rate: int
    #: The per-response fit of the same band (selected slopes, decay times).
    single_slopes: int | None = None
    single_decay_times_s: tuple[float, ...] = ()
    single_rms_residual_db: float | None = None
    #: The one- and two-slope per-response decay times (k-means start values).
    candidate_decay_times_s: tuple[tuple[float, ...], ...] = ()


@dataclass(frozen=True)
class ExcludedPosition:
    position: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {"position": self.position, "reason": self.reason}


@dataclass(frozen=True)
class CommonSlopeModel:
    """The joint fit with ``slope_count`` common slopes."""

    slope_count: int
    decay_times_s: tuple[float, ...]
    bic: float
    #: RMS dB error over all positions' fitted EDC points.
    rms_residual_db: float
    converged: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "slope_count": self.slope_count,
            "decay_times_s": list(self.decay_times_s),
            "bic": self.bic,
            "rms_residual_db": self.rms_residual_db,
            "converged": self.converged,
        }


@dataclass(frozen=True)
class PositionAmplitudes:
    """Amplitudes of the common slopes at one position (selected model)."""

    position: str
    #: ``A_k`` (fraction of the onset energy), one per common slope; 0 allowed.
    amplitudes: tuple[float, ...]
    #: Noise term ``N`` (fraction of the onset energy per second).
    noise_term: float
    #: RMS dB error between the common model and this position's EDC.
    rms_residual_db: float
    integration_end_s: float
    #: The per-response fit of the same band, for comparison.
    single_slopes: int | None = None
    single_decay_times_s: tuple[float, ...] = ()
    single_rms_residual_db: float | None = None

    @property
    def amplitudes_db(self) -> tuple[float | None, ...]:
        return tuple(10.0 * math.log10(a) if a > 0.0 else None for a in self.amplitudes)

    @property
    def noise_db(self) -> float | None:
        return 10.0 * math.log10(self.noise_term) if self.noise_term > 0.0 else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "position": self.position,
            "amplitudes": list(self.amplitudes),
            "amplitudes_db": list(self.amplitudes_db),
            "noise_term": self.noise_term,
            "noise_db": self.noise_db,
            "rms_residual_db": self.rms_residual_db,
            "integration_end_s": self.integration_end_s,
            "single_slopes": self.single_slopes,
            "single_decay_times_s": list(self.single_decay_times_s),
            "single_rms_residual_db": self.single_rms_residual_db,
        }


@dataclass(frozen=True)
class CommonSlopeBand:
    """Common slopes of one band."""

    band_label: str
    center_hz: float
    fraction: str
    validity: Validity
    selected_slopes: int | None = None
    #: Common decay times of the selected model (estimator's), ascending.
    decay_times_s: tuple[float, ...] = ()
    #: The EDC-fit models, one slope first.
    models: tuple[CommonSlopeModel, ...] = ()
    #: ``BIC(K-1) - BIC(K)`` for K = 2.. (positive favours more slopes).
    delta_bic: tuple[float, ...] = ()
    #: Positions supporting each slope (largest term over 10 dB of decay).
    supporting_positions: tuple[int, ...] = ()
    positions: tuple[PositionAmplitudes, ...] = ()
    excluded: tuple[ExcludedPosition, ...] = ()
    #: EDC-fit decay times when the SAGE estimator moved them.
    edc_decay_times_s: tuple[float, ...] = ()
    runtime_s: float = 0.0
    reason: str | None = None
    notes: tuple[str, ...] = ()

    @property
    def selected(self) -> CommonSlopeModel | None:
        return next((m for m in self.models if m.slope_count == self.selected_slopes), None)

    def to_dict(self) -> dict[str, Any]:
        return {
            "band_label": self.band_label,
            "center_hz": self.center_hz,
            "fraction": self.fraction,
            "validity": str(self.validity),
            "selected_slopes": self.selected_slopes,
            "decay_times_s": list(self.decay_times_s),
            "edc_decay_times_s": list(self.edc_decay_times_s),
            "models": [m.to_dict() for m in self.models],
            "delta_bic": list(self.delta_bic),
            "supporting_positions": list(self.supporting_positions),
            "positions": [p.to_dict() for p in self.positions],
            "excluded": [e.to_dict() for e in self.excluded],
            "runtime_s": self.runtime_s,
            "reason": self.reason,
            "notes": list(self.notes),
        }


@dataclass(frozen=True)
class CommonSlopeResult:
    """Common-slope analysis of a set of responses (``common-slope.json``)."""

    positions: tuple[str, ...]
    bands: tuple[CommonSlopeBand, ...]
    estimator: str = ESTIMATOR_EDC
    amplitude_method: str = AMPLITUDES_LINEX
    max_slopes: int = MAX_COMMON_SLOPES
    method: str = COMMON_SLOPE_METHOD
    notes: tuple[str, ...] = ()
    reverbscope_version: str = ""
    schema_version: int = COMMON_SLOPE_SCHEMA_VERSION
    runtime_s: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "kind": "common-slope",
            "method": self.method,
            "estimator": self.estimator,
            "amplitude_method": self.amplitude_method,
            "max_slopes": self.max_slopes,
            "positions": list(self.positions),
            "bands": [b.to_dict() for b in self.bands],
            "notes": list(self.notes),
            "runtime_s": self.runtime_s,
            "reverbscope_version": self.reverbscope_version,
        }


# --------------------------------------------------------------------------
# Observations
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ResponseInput:
    """One response of the set: samples, rate, direct sound and band limits."""

    position: str
    samples: FloatArray
    sample_rate: int
    direct_index: int
    excitation_band: ExcitationBand | None


def analysis_bands(settings: AnalysisSettings, *, third_octave: bool) -> tuple[Band, ...]:
    if third_octave:
        return third_octave_decay_bands(settings)
    return tuple(iec_band(center, 1) for center in settings.octave_bands_hz)


def observe_response(
    response: ResponseInput, settings: AnalysisSettings, *, third_octave: bool = False
) -> list[BandObservation | ExcludedPosition | None]:
    """One entry per band of :func:`analysis_bands`.

    ``None`` for a band the response cannot have (above 0.9 x Nyquist),
    :class:`ExcludedPosition` for a band without a usable decay.
    """
    rate = int(response.sample_rate)
    lead = third_octave_lead_in_s(settings) if third_octave else decay_lead_in_s(settings)
    prepared = _prepare_signal(
        np.asarray(response.samples, dtype=np.float64),
        rate,
        lead,
        response.direct_index,
        response.excitation_band,
    )
    out: list[BandObservation | ExcludedPosition | None] = []
    for band in analysis_bands(settings, third_octave=third_octave):
        if not band_fits(band, rate):
            out.append(None)
            continue
        if response.excitation_band is not None and not response.excitation_band.contains(
            band.low_hz, band.high_hz
        ):
            out.append(
                ExcludedPosition(
                    response.position, diag("the band is outside the excitation range")
                )
            )
            continue
        filtered = apply_bandpass(prepared.signal, bandpass_sos(band, rate), time_reversed=True)
        decay = analyze_band(
            filtered,
            rate,
            band,
            noise_margin_db=settings.decay_noise_margin_db,
            direct_index=prepared.direct,
            time_origin_index=prepared.direct,
            onset_search_start=_search_start(prepared, band.bandwidth_hz, rate),
            direct_spread_s=prepared.spread_s,
        )
        out.append(_observation(response.position, band, filtered, decay, prepared.direct, rate))
    return out


def _observation(
    position: str,
    band: Band,
    filtered: FloatArray,
    decay: Any,
    origin: int,
    rate: int,
) -> BandObservation | ExcludedPosition:
    fit = decay.multi_slope
    if fit is None or fit.fit_start_s is None or fit.fit_end_s is None or not fit.models:
        reason = fit.reason if fit is not None and fit.reason else diag("no slope fit")
        return ExcludedPosition(position, reason)
    power = np.asarray(filtered, dtype=np.float64) ** 2
    onset = origin + round(float(decay.onset_time_s) * rate)
    times, edc, end = raw_energy_decay(power, onset, origin, rate)
    energy = float(np.sum(power[onset:]))
    t_fit = np.linspace(fit.fit_start_s, fit.fit_end_s, FIT_POINTS)
    edc_fit = np.interp(t_fit, times, edc)
    edc_db = _LOG10_E * np.log(np.maximum(edc_fit, _TINY))
    # Envelope: |analytic signal|^2 / 2 has the mean of h^2; samples 1 / B apart.
    first = origin + round(fit.fit_start_s * rate)
    last = origin + round(fit.fit_end_s * rate)
    stride = max(1, int(rate // band.bandwidth_hz))
    count = (last - first) // stride + 1
    if count > MAX_ENVELOPE_SAMPLES:
        stride = math.ceil((last - first) / (MAX_ENVELOPE_SAMPLES - 1))
    index = np.arange(first, last + 1, stride)
    pad = 2048
    lo, hi = max(0, first - pad), min(filtered.shape[0], last + pad)
    analytic = hilbert(np.asarray(filtered[lo:hi], dtype=np.float64))
    envelope = np.abs(analytic[index - lo]) ** 2 / 2.0 / max(energy, _TINY)
    selected = fit.selected
    candidates = tuple(m.decay_times_s for m in fit.models)
    return BandObservation(
        position=position,
        band_label=band.label,
        center_hz=float(band.label_hz),
        bandwidth_hz=float(band.bandwidth_hz),
        times_s=t_fit,
        edc_db=edc_db,
        integration_end_s=float(end),
        envelope_times_s=(index - origin) / float(rate),
        envelope_power=np.asarray(envelope, dtype=np.float64),
        sample_rate=rate,
        single_slopes=fit.selected_slopes,
        single_decay_times_s=selected.decay_times_s if selected is not None else (),
        single_rms_residual_db=selected.rms_residual_db if selected is not None else None,
        candidate_decay_times_s=candidates,
    )


# --------------------------------------------------------------------------
# Joint EDC fit (variable projection)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class _Stack:
    """All positions' EDC points of one band as ``R x P`` arrays."""

    t: FloatArray
    edc_db: FloatArray
    edc: FloatArray
    end: FloatArray

    @classmethod
    def of(cls, observations: Sequence[BandObservation]) -> _Stack:
        t = np.stack([o.times_s for o in observations])
        edc_db = np.stack([o.edc_db for o in observations])
        end = np.array([o.integration_end_s for o in observations])
        return cls(t=t, edc_db=edc_db, edc=10.0 ** (edc_db / 10.0), end=end)


def _basis(stack: _Stack, decays: FloatArray) -> FloatArray:
    """``R x P x (K + 1)``: the slope terms then the noise term (unit amplitudes)."""
    t = stack.t[:, :, None]
    end = stack.end[:, None, None]
    rate = DECAY_60_DB_NEPER / np.asarray(decays)[None, None, :]
    slopes = np.exp(-rate * t) - np.exp(-rate * end)
    noise = (stack.end[:, None] - stack.t)[:, :, None]
    return np.asarray(np.concatenate([slopes, noise], axis=2), dtype=np.float64)


def _project(stack: _Stack, basis: FloatArray) -> FloatArray:
    """Non-negative coefficients ``R x (K + 1)`` minimising the relative error.

    Weighted by the measured EDC, then once more by the model (so the weights
    approach those of the dB error).
    """
    weights = 1.0 / np.maximum(stack.edc, _TINY)
    coefficients = _weighted_nnls(basis, stack.edc, weights)
    model = np.einsum("rpk,rk->rp", basis, coefficients)
    weights = 1.0 / np.maximum(np.maximum(model, 1e-3 * stack.edc), _TINY)
    return _weighted_nnls(basis, stack.edc, weights)


def _weighted_nnls(basis: FloatArray, target: FloatArray, weights: FloatArray) -> FloatArray:
    a = basis * weights[:, :, None]
    b = target * weights
    gram = np.einsum("rpk,rpl->rkl", a, a)
    rhs = np.einsum("rpk,rp->rk", a, b)
    scale = np.sqrt(np.maximum(np.einsum("rkk->rk", gram), _TINY))
    try:
        with np.errstate(all="ignore"):
            normalised = gram / (scale[:, :, None] * scale[:, None, :])
            solution = np.linalg.solve(normalised, (rhs / scale)[:, :, None])[:, :, 0] / scale
    except np.linalg.LinAlgError:
        solution = np.full(rhs.shape, -1.0)
    out = np.empty_like(solution)
    for r in range(solution.shape[0]):
        if np.all(solution[r] >= 0.0) and np.all(np.isfinite(solution[r])):
            out[r] = solution[r]
        else:
            # A column that underflowed (a very fast slope) gets amplitude 0.
            norms = np.linalg.norm(a[r], axis=0)
            usable = norms > 1e-150
            out[r] = 0.0
            if np.any(usable):
                x, _residual = nnls(a[r][:, usable] / norms[usable], b[r], maxiter=50 * a.shape[2])
                out[r, usable] = x / norms[usable]
    return np.asarray(out, dtype=np.float64)


def _residuals_db(stack: _Stack, basis: FloatArray, coefficients: FloatArray) -> FloatArray:
    model = np.einsum("rpk,rk->rp", basis, coefficients)
    return np.asarray(_LOG10_E * np.log(np.maximum(model, _TINY)) - stack.edc_db)


@dataclass(frozen=True)
class _JointFit:
    decays: tuple[float, ...]
    coefficients: FloatArray  # R x (K + 1): amplitudes then noise
    residuals_db: FloatArray  # R x P
    converged: bool

    @property
    def rss(self) -> FloatArray:
        return np.asarray(np.sum(self.residuals_db**2, axis=1))


def _fit_decays(
    stack: _Stack, starts: Sequence[Sequence[float]], max_decay_s: float
) -> _JointFit | None:
    slopes = len(starts[0])
    lower = np.full(slopes, math.log(_MIN_DECAY_S))
    upper = np.full(slopes, math.log(max_decay_s))

    def residual(log_decays: FloatArray) -> FloatArray:
        decays = np.exp(np.clip(log_decays, lower, upper))
        basis = _basis(stack, decays)
        return _residuals_db(stack, basis, _project(stack, basis)).ravel()

    best: _JointFit | None = None
    best_cost = np.inf
    for start in starts:
        x0 = np.log(
            np.clip(
                np.sort(np.asarray(start, dtype=np.float64)),
                _MIN_DECAY_S * 1.01,
                max_decay_s * 0.99,
            )
        )
        try:
            solution = least_squares(
                residual,
                x0,
                bounds=(lower, upper),
                method="trf",
                max_nfev=MAX_EVALUATIONS,
                x_scale=1.0,
                diff_step=1e-4,
            )
        except (ValueError, FloatingPointError, np.linalg.LinAlgError):
            continue
        if not np.all(np.isfinite(solution.fun)):
            continue
        cost = float(np.sum(solution.fun**2))
        if cost < best_cost:
            best_cost = cost
            decays = np.exp(np.clip(solution.x, lower, upper))
            order = np.argsort(decays)
            decays = decays[order]
            basis = _basis(stack, decays)
            coefficients = _project(stack, basis)
            best = _JointFit(
                decays=tuple(float(d) for d in decays),
                coefficients=coefficients,
                residuals_db=_residuals_db(stack, basis, coefficients),
                converged=bool(solution.status > 0),
            )
    return best


def kmeans_log(values: Sequence[float], clusters: int, *, iterations: int = 100) -> list[float]:
    """1-D k-means of ``log(values)``; returns the cluster centres (seconds, ascending).

    Deterministic: the centres start at evenly spaced quantiles.
    """
    data = np.log(np.asarray([v for v in values if v > 0.0 and math.isfinite(v)], dtype=float))
    if data.size == 0:
        raise ValueError("no decay times to cluster")
    clusters = max(1, min(clusters, int(np.unique(data).size)))
    centres = np.quantile(data, (np.arange(clusters) + 0.5) / clusters)
    for _iteration in range(iterations):
        labels = np.argmin(np.abs(data[:, None] - centres[None, :]), axis=1)
        updated = np.array(
            [
                data[labels == k].mean() if np.any(labels == k) else centres[k]
                for k in range(clusters)
            ]
        )
        if np.allclose(updated, centres):
            break
        centres = updated
    return [float(np.exp(c)) for c in np.sort(centres)]


def _starts(
    observations: Sequence[BandObservation], slopes: int, previous: tuple[float, ...] | None
) -> list[list[float]]:
    """Start values: k-means (log T) of the per-response decay times -- of the
    selected models, and of all fitted models -- and the previous model with
    one more slope (faster or slower)."""
    selected = [t for o in observations for t in o.single_decay_times_s]
    pooled = [t for o in observations for model in o.candidate_decay_times_s for t in model]
    starts: list[list[float]] = []
    for values in (selected, pooled):
        if values:
            centres = kmeans_log(values, slopes)
            if len(centres) == slopes:
                starts.append(centres)
    if slopes == 1:
        one = [m[0] for o in observations for m in o.candidate_decay_times_s if len(m) == 1]
        if one:
            starts.append([float(np.median(one))])
    if slopes == 2:
        two = [t for o in observations for m in o.candidate_decay_times_s if len(m) == 2 for t in m]
        if two:
            centres = kmeans_log(two, 2)
            if len(centres) == 2:
                starts.append(centres)
    if previous is not None and len(previous) == slopes - 1:
        starts.append([0.5 * previous[0], *previous])
        starts.append([*previous, 2.0 * previous[-1]])
        if slopes == 2:
            starts.append([0.7 * previous[0], 1.6 * previous[0]])
    if not starts and pooled:
        median = float(np.median(pooled))
        starts.append([median * 2.0 ** (k - (slopes - 1) / 2.0) for k in range(slopes)])
    if not starts:
        starts.append([0.5 * 2.0**k for k in range(slopes)])
    unique: list[list[float]] = []
    for start in starts:
        if not any(np.allclose(start, other, rtol=1e-3) for other in unique):
            unique.append(start)
    return unique


def _bic(fit: _JointFit, effective: FloatArray) -> float:
    rows, slopes_plus = fit.coefficients.shape
    points = fit.residuals_db.shape[1]
    variance = np.maximum(fit.rss / points, RESIDUAL_FLOOR_DB**2)
    parameters = (slopes_plus - 1) + rows * slopes_plus
    total = float(np.sum(effective))
    return float(np.sum(effective * np.log(variance)) + parameters * math.log(max(total, 2.0)))


def slope_support(
    decays: Sequence[float],
    amplitudes: FloatArray,
    noise: FloatArray,
    stack_t: FloatArray,
    end: FloatArray,
) -> list[int]:
    """Positions at which each slope is the largest term, above the noise term,
    over at least :data:`~reverbscope.core.multislope.LATE_VISIBLE_DB` of decay."""
    counts = [0] * len(decays)
    rate = DECAY_60_DB_NEPER / np.asarray(decays)
    for r in range(amplitudes.shape[0]):
        grid = np.linspace(stack_t[r, 0], stack_t[r, -1], 400)
        terms = amplitudes[r][None, :] * np.exp(-rate[None, :] * grid[:, None])
        floor = noise[r] * (end[r] - grid)
        strongest = np.argmax(terms, axis=1)
        for k in range(len(decays)):
            if amplitudes[r, k] <= 0.0:
                continue
            mask = (strongest == k) & (terms[:, k] >= floor * 10.0 ** (KNEE_ABOVE_NOISE_DB / 10.0))
            if not np.any(mask):
                continue
            span = grid[mask]
            decay_db = 10.0 * np.log10(np.e) * rate[k] * (span.max() - span.min())
            if decay_db >= LATE_VISIBLE_DB:
                counts[k] += 1
    return counts


# --------------------------------------------------------------------------
# Envelope (power-sample) estimators: LINEX amplitudes and IS-NMF / SAGE
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class _Envelope:
    """All positions' envelope samples, padded to ``R x N`` with a mask."""

    tau: FloatArray
    y: FloatArray
    mask: FloatArray
    counts: FloatArray

    @classmethod
    def of(cls, observations: Sequence[BandObservation]) -> _Envelope:
        size = max(o.envelope_power.shape[0] for o in observations)
        rows = len(observations)
        tau = np.zeros((rows, size))
        y = np.zeros((rows, size))
        mask = np.zeros((rows, size))
        for r, o in enumerate(observations):
            n = o.envelope_power.shape[0]
            tau[r, :n] = o.envelope_times_s
            tau[r, n:] = o.envelope_times_s[-1] if n else 0.0
            y[r, :n] = np.maximum(o.envelope_power, 0.0)
            mask[r, :n] = 1.0
        return cls(tau=tau, y=y, mask=mask, counts=mask.sum(axis=1))


def is_loss(env: _Envelope, rates: FloatArray, power: FloatArray) -> float:
    """Itakura-Saito negative log-likelihood ``sum(y / v + ln v)`` (masked)."""
    v = _variance(env, rates, power)
    return float(np.sum(env.mask * (env.y / v + np.log(v))))


def _variance(env: _Envelope, rates: FloatArray, power: FloatArray) -> FloatArray:
    phi = np.exp(-rates[None, None, :] * env.tau[:, :, None])
    v = np.einsum("rnk,rk->rn", phi, power[:, :-1]) + power[:, -1:]
    return np.asarray(np.maximum(v, _TINY))


def linex_amplitudes(env: _Envelope, rates: FloatArray, start: FloatArray) -> FloatArray:
    """Maximum-likelihood (LINEX / Itakura-Saito) powers ``R x (K + 1)`` for
    fixed decay rates: Fisher scoring on the log powers, step-halved."""
    phi = np.concatenate(
        [np.exp(-rates[None, None, :] * env.tau[:, :, None]), np.ones((*env.tau.shape, 1))],
        axis=2,
    )
    floor = 1e-14 * np.maximum(np.max(env.y * env.mask, axis=1, keepdims=True), _TINY)
    log_p = np.log(np.maximum(start, floor))

    def loss(lp: FloatArray) -> FloatArray:
        v = np.maximum(np.einsum("rnk,rk->rn", phi, np.exp(lp)), _TINY)
        return np.asarray(np.sum(env.mask * (env.y / v + np.log(v)), axis=1))

    current = loss(log_p)
    for _iteration in range(LINEX_ITERATIONS):
        p = np.exp(log_p)
        v = np.maximum(np.einsum("rnk,rk->rn", phi, p), _TINY)
        d = phi * p[:, None, :]  # dv / dlog p
        gradient = np.einsum("rnk,rn->rk", d, env.mask * (1.0 / v - env.y / v**2))
        fisher = np.einsum("rnk,rnl,rn->rkl", d, d, env.mask / v**2)
        fisher += (
            1e-9
            * np.eye(fisher.shape[1])[None]
            * np.maximum(np.einsum("rkk->rk", fisher).max(axis=1), _TINY)[:, None, None]
        )
        try:
            step = -np.linalg.solve(fisher, gradient[:, :, None])[:, :, 0]
        except np.linalg.LinAlgError:
            break
        step = np.clip(step, -5.0, 5.0)
        scale = np.ones(p.shape[0])
        improved = np.zeros(p.shape[0], dtype=bool)
        for _halving in range(12):
            trial = np.maximum(log_p + scale[:, None] * step, np.log(floor))
            value = loss(trial)
            better = value <= current + 1e-12 * np.abs(current)
            update = better & ~improved
            log_p = np.where(update[:, None], trial, log_p)
            current = np.where(update, value, current)
            improved |= better
            if np.all(improved):
                break
            scale = np.where(improved, scale, scale * 0.5)
        if np.max(np.abs(step)) < 1e-7:
            break
    power = np.exp(log_p)
    power[power <= floor * 1.0001] = 0.0
    return np.asarray(power)


def sage(
    env: _Envelope,
    rates: FloatArray,
    power: FloatArray,
    *,
    weighted_iterations: int = SAGE_WEIGHTED_ITERATIONS,
    plain_iterations: int = SAGE_PLAIN_ITERATIONS,
    rate_bounds: tuple[float, float] = (0.05, DECAY_60_DB_NEPER / _MIN_DECAY_S),
) -> tuple[FloatArray, FloatArray, list[float]]:
    """IS-NMF of the envelope powers with shared decay rates by (CW-)SAGE.

    Bai, Elvander & Schlecht (arXiv:2610.05549), eqs. (7)-(14): for each
    component in turn, posterior powers ``y_hat = rho^2 y + v (1 - rho)``, a
    safeguarded Newton solve of the convex profiled surrogate for its decay
    rate (pooled over positions), closed-form amplitudes ``a = M / W``; the
    noise component (rate 0) gets ``a_0 = mean(y_hat_0)``. ``p = 1`` weights
    (``w = rho^p``) for ``weighted_iterations``, then ``p = 0``. Returns the
    rates, the ``R x (K + 1)`` powers and the observed-data IS loss per
    iteration.
    """
    rates = np.array(rates, dtype=np.float64)
    power = np.array(power, dtype=np.float64)
    slopes = rates.shape[0]
    mask = env.mask
    losses: list[float] = []
    total = weighted_iterations + plain_iterations
    for iteration in range(total):
        p_exp = 1.0 if iteration < weighted_iterations else 0.0
        for k in [*range(slopes), slopes]:
            v = _variance(env, rates, power)
            if k == slopes:
                vk = np.broadcast_to(power[:, -1:], v.shape)
            else:
                vk = power[:, k : k + 1] * np.exp(-rates[k] * env.tau)
            rho = np.clip(vk / v, 0.0, 1.0)
            y_hat = rho**2 * env.y + vk * (1.0 - rho)
            if k == slopes:
                power[:, -1] = np.sum(mask * y_hat, axis=1) / np.maximum(env.counts, 1.0)
                continue
            w = mask * (rho**p_exp if p_exp else 1.0)
            w_sum = np.sum(w, axis=1)
            b_sum = np.sum(w * env.tau, axis=1)
            usable = w_sum > 1e-9
            if not np.any(usable):
                continue
            with np.errstate(divide="ignore"):
                log_wy = np.where(w * y_hat > 0.0, np.log(np.maximum(w * y_hat, _TINY)), -np.inf)
            lam = float(rates[k])
            for _newton in range(20):
                exponent = log_wy + lam * env.tau
                peak = np.max(exponent, axis=1, keepdims=True)
                peak = np.where(np.isfinite(peak), peak, 0.0)
                weights = np.exp(exponent - peak)
                norm = np.maximum(np.sum(weights, axis=1), _TINY)
                mean_tau = np.sum(weights * env.tau, axis=1) / norm
                var_tau = np.sum(weights * env.tau**2, axis=1) / norm - mean_tau**2
                grad = float(np.sum((w_sum * mean_tau - b_sum)[usable]))
                hess = float(np.sum((w_sum * np.maximum(var_tau, 0.0))[usable]))
                if hess <= 0.0 or not math.isfinite(grad):
                    break
                step = grad / hess
                new = min(max(lam - step, rate_bounds[0]), rate_bounds[1])
                # Keep the step inside a factor of two (safeguard).
                new = min(max(new, 0.5 * lam), 2.0 * lam)
                if abs(new - lam) < 1e-10 * max(lam, 1.0):
                    lam = new
                    break
                lam = new
            rates[k] = lam
            exponent = log_wy + lam * env.tau
            peak = np.max(exponent, axis=1)
            peak = np.where(np.isfinite(peak), peak, 0.0)
            m_sum = np.exp(peak) * np.sum(np.exp(exponent - peak[:, None]), axis=1)
            power[:, k] = np.where(usable, m_sum / np.maximum(w_sum, _TINY), power[:, k])
        losses.append(is_loss(env, rates, power))
    order = np.argsort(-rates)  # fastest decay (largest rate) first = shortest T first
    rates = rates[order]
    power = np.concatenate([power[:, :-1][:, order], power[:, -1:]], axis=1)
    return rates, power, losses


def _power_to_edc(
    power: FloatArray, decays: Sequence[float], sample_rates: FloatArray
) -> FloatArray:
    """Envelope powers (per sample at t = 0) to EDC-model amplitudes and noise."""
    rate = DECAY_60_DB_NEPER / np.asarray(decays)[None, :]
    fs = sample_rates[:, None]
    amplitudes = power[:, :-1] / (-np.expm1(-rate / fs))
    noise = power[:, -1:] * fs
    return np.asarray(np.concatenate([amplitudes, noise], axis=1))


def _edc_to_power(
    coefficients: FloatArray, decays: Sequence[float], sample_rates: FloatArray
) -> FloatArray:
    rate = DECAY_60_DB_NEPER / np.asarray(decays)[None, :]
    fs = sample_rates[:, None]
    amplitudes = coefficients[:, :-1] * (-np.expm1(-rate / fs))
    noise = coefficients[:, -1:] / fs
    return np.asarray(np.concatenate([amplitudes, noise], axis=1))


# --------------------------------------------------------------------------
# One band
# --------------------------------------------------------------------------


def fit_common_slopes(
    observations: Sequence[BandObservation],
    *,
    band_label: str,
    center_hz: float,
    bandwidth_hz: float,
    fraction: str = "octave",
    excluded: Sequence[ExcludedPosition] = (),
    max_slopes: int = MAX_COMMON_SLOPES,
    estimator: str = ESTIMATOR_EDC,
    amplitude_method: str = AMPLITUDES_LINEX,
) -> CommonSlopeBand:
    """Common slopes of one band from the positions' observations."""
    started = time.perf_counter()
    if not 1 <= max_slopes <= MAX_COMMON_SLOPES:
        raise ConfigurationError(
            _("the number of common slopes must be between 1 and {maximum}").format(
                maximum=MAX_COMMON_SLOPES
            )
        )
    if estimator not in ESTIMATORS:
        raise ConfigurationError(_("unknown estimator {name}").format(name=estimator))
    if amplitude_method not in AMPLITUDE_METHODS:
        raise ConfigurationError(_("unknown amplitude method {name}").format(name=amplitude_method))
    base = CommonSlopeBand(
        band_label=band_label,
        center_hz=center_hz,
        fraction=fraction,
        validity=Validity.INSUFFICIENT_RANGE,
        excluded=tuple(excluded),
    )
    if not observations:
        return replace(
            base,
            reason=diag("no position has a usable decay in this band"),
            runtime_s=time.perf_counter() - started,
        )
    stack = _Stack.of(observations)
    max_decay = max(4.0 * float(np.max(stack.end)), 1.0)
    fits: list[_JointFit] = []
    previous: tuple[float, ...] | None = None
    for slopes in range(1, max_slopes + 1):
        fit = _fit_decays(stack, _starts(observations, slopes, previous), max_decay)
        if fit is None:
            break
        fits.append(fit)
        previous = fit.decays
    if not fits:
        return replace(
            base,
            validity=Validity.UNRELIABLE,
            reason=diag("the common-slope fit did not converge"),
            runtime_s=time.perf_counter() - started,
        )
    effective = np.array([effective_points(row) for row in fits[-1].residuals_db])
    bics = [_bic(fit, effective) for fit in fits]
    models = tuple(
        CommonSlopeModel(
            slope_count=len(fit.decays),
            decay_times_s=fit.decays,
            bic=bic,
            rms_residual_db=float(np.sqrt(np.mean(fit.residuals_db**2))),
            converged=fit.converged,
        )
        for fit, bic in zip(fits, bics, strict=True)
    )
    deltas = tuple(bics[i - 1] - bics[i] for i in range(1, len(bics)))
    notes: list[str] = []
    selected = 0
    # Each richer model is judged against the one before it.
    for index in range(1, len(fits)):
        if deltas[index - 1] < DELTA_BIC_MIN:
            break
        rejected = _implausible(fits[index], fits[index - 1], stack)
        if rejected is not None:
            notes.append(rejected)
            break
        selected = index
    chosen = fits[selected]
    decays = chosen.decays
    coefficients = chosen.coefficients
    edc_decays: tuple[float, ...] = ()
    rates_arr = DECAY_60_DB_NEPER / np.asarray(decays)
    sample_rates = np.array([float(o.sample_rate) for o in observations])
    env: _Envelope | None = None
    if estimator == ESTIMATOR_SAGE or amplitude_method == AMPLITUDES_LINEX:
        env = _Envelope.of(observations)
    if estimator == ESTIMATOR_SAGE and env is not None:
        start_power = _edc_to_power(coefficients, decays, sample_rates)
        start_power = linex_amplitudes(env, rates_arr, start_power)
        rates_sage, power, _losses = sage(env, rates_arr, start_power)
        edc_decays = decays
        decays = tuple(float(DECAY_60_DB_NEPER / r) for r in rates_sage)
        rates_arr = rates_sage
        coefficients = _power_to_edc(power, decays, sample_rates)
        notes.append(
            diag(
                "decay times from the IS-NMF / SAGE estimator (experimental, validated on "
                "synthetic data only); EDC-fit decay times kept for comparison"
            )
        )
    elif amplitude_method == AMPLITUDES_LINEX and env is not None:
        start_power = _edc_to_power(coefficients, decays, sample_rates)
        power = linex_amplitudes(env, rates_arr, start_power)
        coefficients = _power_to_edc(power, decays, sample_rates)
    basis = _basis(stack, np.asarray(decays))
    residuals = _residuals_db(stack, basis, coefficients)
    support = slope_support(decays, coefficients[:, :-1], coefficients[:, -1], stack.t, stack.end)
    positions = tuple(
        PositionAmplitudes(
            position=o.position,
            amplitudes=tuple(float(a) for a in coefficients[r, :-1]),
            noise_term=float(coefficients[r, -1]),
            rms_residual_db=float(np.sqrt(np.mean(residuals[r] ** 2))),
            integration_end_s=o.integration_end_s,
            single_slopes=o.single_slopes,
            single_decay_times_s=o.single_decay_times_s,
            single_rms_residual_db=o.single_rms_residual_db,
        )
        for r, o in enumerate(observations)
    )
    validity = Validity.VALID
    reason: str | None = None
    if not chosen.converged:
        validity = Validity.UNRELIABLE
        reason = diag("the common-slope fit did not converge")
    if bandwidth_hz * decays[0] < MIN_BT_PRODUCT:
        validity = Validity.UNRELIABLE
        text = diag(
            "B*T1 = {bt:.1f} < {minimum:g}: the band filter's own decay is comparable to the "
            "fast slope",
            bt=bandwidth_hz * decays[0],
            minimum=MIN_BT_PRODUCT,
        )
        reason = text if reason is None else f"{reason}; {text}"
    if len(observations) == 1:
        notes.append(diag("one position only: the common slopes are that position's own fit"))
    return replace(
        base,
        validity=validity,
        selected_slopes=len(decays),
        decay_times_s=tuple(decays),
        edc_decay_times_s=edc_decays,
        models=models,
        delta_bic=deltas,
        supporting_positions=tuple(support),
        positions=positions,
        reason=reason,
        notes=tuple(notes),
        runtime_s=time.perf_counter() - started,
    )


def _implausible(fit: _JointFit, fewer: _JointFit, stack: _Stack) -> str | None:
    decays = fit.decays
    points = fit.residuals_db.shape[1]
    before = np.sqrt(np.maximum(fewer.rss / points, _TINY))
    after = np.sqrt(np.maximum(fit.rss / points, _TINY))
    gain = float(np.max(1.0 - after / before))
    if gain < MIN_POSITION_IMPROVEMENT:
        return diag(
            "{n} common slopes not reported: the extra slope lowers the RMS error by at most "
            "{gain:.1f} % at any position (limit {limit:.0f} %)",
            n=len(decays),
            gain=100.0 * gain,
            limit=100.0 * MIN_POSITION_IMPROVEMENT,
        )
    for fast, slow in itertools.pairwise(decays):
        if slow < SLOPE_RATIO_MIN * fast:
            return diag(
                "{n} common slopes not reported: adjacent decay times differ by only "
                "{ratio:.2f}x (limit {minimum:g})",
                n=len(decays),
                ratio=slow / fast,
                minimum=SLOPE_RATIO_MIN,
            )
    support = slope_support(
        decays, fit.coefficients[:, :-1], fit.coefficients[:, -1], stack.t, stack.end
    )
    needed = minimum_support(fit.coefficients.shape[0])
    for k, count in enumerate(support):
        if count < needed:
            return diag(
                "{n} common slopes not reported: the slope of {decay:.2f} s is the strongest "
                "decay over {limit:g} dB at {count} position(s), {needed} needed",
                n=len(decays),
                decay=decays[k],
                limit=LATE_VISIBLE_DB,
                count=count,
                needed=needed,
            )
    return None


def minimum_support(positions: int) -> int:
    """Positions that must support every slope of a richer model.

    Two (one when there is only one response), and at least
    :data:`MIN_SUPPORT_FRACTION` of the positions: a slope seen at a single
    position cannot be told from an artefact of that one response (a drifting
    noise floor, a gate, a fault in that take).
    """
    return max(min(MIN_SUPPORT_POSITIONS, positions), math.ceil(MIN_SUPPORT_FRACTION * positions))


# --------------------------------------------------------------------------
# A set of responses
# --------------------------------------------------------------------------


@dataclass
class _BandCollector:
    band: Band
    observations: list[BandObservation] = field(default_factory=list)
    excluded: list[ExcludedPosition] = field(default_factory=list)
    present: bool = False


def analyze_common_slopes(
    responses: Sequence[ResponseInput],
    settings: AnalysisSettings | None = None,
    *,
    third_octave: bool = False,
    max_slopes: int = MAX_COMMON_SLOPES,
    estimator: str = ESTIMATOR_EDC,
    amplitude_method: str = AMPLITUDES_LINEX,
    progress: Callable[[int, int], None] | None = None,
) -> CommonSlopeResult:
    """Common-slope analysis of several responses of one room, band by band."""
    from reverbscope.version import __version__

    started = time.perf_counter()
    settings = settings or AnalysisSettings()
    if not responses:
        raise ConfigurationError(_("the common-slope analysis needs at least one response"))
    labels = [r.position for r in responses]
    if len(set(labels)) != len(labels):
        raise ConfigurationError(_("each response needs its own position label"))
    bands = analysis_bands(settings, third_octave=third_octave)
    collectors = [_BandCollector(band) for band in bands]
    for count, response in enumerate(responses, start=1):
        for collector, item in zip(
            collectors,
            observe_response(response, settings, third_octave=third_octave),
            strict=True,
        ):
            if item is None:
                continue
            collector.present = True
            if isinstance(item, ExcludedPosition):
                collector.excluded.append(item)
            else:
                collector.observations.append(item)
        if progress is not None:
            progress(count, len(responses))
    fraction = "third" if third_octave else "octave"
    out = [
        fit_common_slopes(
            c.observations,
            band_label=c.band.label,
            center_hz=float(c.band.label_hz),
            bandwidth_hz=float(c.band.bandwidth_hz),
            fraction=fraction,
            excluded=c.excluded,
            max_slopes=max_slopes,
            estimator=estimator,
            amplitude_method=amplitude_method,
        )
        for c in collectors
        if c.present
    ]
    rates = {r.sample_rate for r in responses}
    notes: list[str] = []
    if len(rates) > 1:
        notes.append(diag("the responses have different sample rates"))
    return CommonSlopeResult(
        positions=tuple(labels),
        bands=tuple(out),
        estimator=estimator,
        amplitude_method=amplitude_method,
        max_slopes=max_slopes,
        notes=tuple(notes),
        reverbscope_version=__version__,
        runtime_s=time.perf_counter() - started,
    )
