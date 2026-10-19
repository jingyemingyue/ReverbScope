"""Bayesian / multi-exponential decay-model fitting (M7).

Xiang, "Evaluation of reverberation times using a nonlinear regression
approach," JASA 98, 2112–2121, 1995;
Xiang & Goggans, JASA 110, 1415–1424, 2001;
Xiang, Goggans, Jasa & Robinson, "Bayesian characterization of multiple-slope
sound energy decays in coupled-volume systems," JASA 129, 741–752, 2011.

Fits multi-exponential + noise parametric models directly to the measured
decay curve, bypassing Schroeder integration + linear regression. Uses BIC
for model-order selection (how many slopes?). This experimental estimator
does not compute a Bayesian posterior or parameter uncertainty; robustness
on measured multi-slope decays has not been established.

Full MCMC (Xiang et al. 2011) is reserved for difficult cases; this module
implements the NLS + BIC core which captures most of the benefit at O(N·p²)
cost.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from reverbscope.errors import InvalidAudioError
from reverbscope.i18n import _
from reverbscope.models.audio import FloatArray

#: Maximum number of exponential slopes to try (1, 2, or 3).
MAX_SLOPES = 3
#: BIC penalty weight (standard BIC: k * ln(n)).
_BIC_PENALTY = 1.0


@dataclass(frozen=True)
class DecaySlope:
    """One exponential component: amplitude and decay time."""

    amplitude: float  # Linear power at t=0
    tau_s: float  # Power time constant (s); T60 = tau * ln(1e6).

    @property
    def t60_s(self) -> float:
        return self.tau_s * math.log(1e6)


@dataclass(frozen=True)
class BayesianDecayFit:
    """Multi-exponential + noise fit with model-order selection."""

    slopes: tuple[DecaySlope, ...]
    noise_power: float
    #: Number of slopes selected by BIC (1..MAX_SLOPES).
    n_slopes: int
    #: BIC values for 1..MAX_SLOPES (lower = better).
    bic_values: tuple[float, ...]
    #: RMS residual in dB (fit quality).
    residual_db: float


def _multi_exp_model(t: FloatArray, amps: FloatArray, taus: FloatArray, noise: float) -> FloatArray:
    """p(t) = sum(A_i * exp(-t/tau_i)) + N."""
    result = np.full_like(t, noise, dtype=np.float64)
    for a, tau in zip(amps, taus, strict=True):
        result += a * np.exp(-t / max(float(tau), 1e-9))
    return result


def _fit_n_slopes_gn(
    t: FloatArray,
    p: FloatArray,
    n_slopes: int,
    *,
    max_iter: int = 100,
    tol: float = 1e-7,
) -> tuple[FloatArray, FloatArray, float, float] | None:
    """Fit n_slopes exponentials + noise via Gauss-Newton.

    Returns (amps, taus, noise, rss) or None on failure.
    rss = residual sum of squares.
    """
    n = len(t)
    # Initialize: distribute amplitude, spread taus log-uniformly.
    p_max = float(np.max(p))
    p_tail = float(np.mean(p[int(0.9 * n) :]))
    noise_init = max(p_tail, 1e-300)
    total_amp = max(p_max - noise_init, 1e-300)
    amps = np.full(n_slopes, total_amp / n_slopes, dtype=np.float64)
    # Taus: from fast (0.05s) to slow (2s), log-spaced.
    taus = np.logspace(np.log10(0.05), np.log10(2.0), n_slopes, dtype=np.float64)
    noise = noise_init

    # Pack params: [amps..., taus..., noise]
    def pack(a: FloatArray, t_: FloatArray, n_: float) -> FloatArray:
        return np.concatenate([a, t_, [n_]])

    def unpack(params: FloatArray) -> tuple[FloatArray, FloatArray, float]:
        return params[:n_slopes], params[n_slopes : 2 * n_slopes], float(params[2 * n_slopes])

    params = pack(amps, taus, noise)
    n_params = 2 * n_slopes + 1

    for _iteration in range(max_iter):
        a_c, tau_c, n_c = unpack(params)
        tau_c = np.maximum(tau_c, 1e-9)
        # Model and residual.
        pred = _multi_exp_model(t, a_c, tau_c, n_c)
        residual = pred - p
        # Jacobian.
        j = np.zeros((n, n_params), dtype=np.float64)
        for i in range(n_slopes):
            exp_term = np.exp(-t / tau_c[i])
            j[:, i] = exp_term  # d/dA_i
            j[:, n_slopes + i] = a_c[i] * t * exp_term / (tau_c[i] ** 2)  # d/dtau_i
        j[:, 2 * n_slopes] = 1.0  # d/dN
        # Gauss-Newton step.
        jt_j = j.T @ j
        jt_r = j.T @ residual
        try:
            # Add damping for stability (Levenberg-Marquardt lite).
            damping = 1e-8 * np.trace(jt_j) / n_params
            delta = np.linalg.solve(jt_j + damping * np.eye(n_params), -jt_r)
        except np.linalg.LinAlgError:
            return None
        params_new = params + delta
        # Project to feasible: amps > 0, taus in [1ms, 100s], noise >= 0.
        for i in range(n_slopes):
            params_new[i] = max(params_new[i], 1e-300)
            params_new[n_slopes + i] = float(np.clip(params_new[n_slopes + i], 1e-3, 100.0))
        params_new[2 * n_slopes] = max(params_new[2 * n_slopes], 0.0)
        # Check convergence.
        rel_change = float(np.max(np.abs(delta) / (np.abs(params) + 1e-300)))
        params = params_new
        if rel_change < tol:
            break

    a_f, tau_f, n_f = unpack(params)
    # Sort by tau (fast to slow) for consistency.
    order = np.argsort(tau_f)
    a_f = a_f[order]
    tau_f = tau_f[order]
    pred = _multi_exp_model(t, a_f, tau_f, n_f)
    rss = float(np.sum((pred - p) ** 2))
    if not np.isfinite(rss):
        return None
    return (a_f, tau_f, n_f, rss)


def fit_bayesian_decay(
    power: FloatArray,
    sample_rate: int,
    *,
    max_slopes: int = MAX_SLOPES,
) -> BayesianDecayFit | None:
    """Fit 1..max_slopes exponentials + noise, select order by BIC (M7).

    Returns the best fit, or None if all fits fail. The BIC balances fit
    quality against model complexity, giving an objective answer to "how many
    slopes?" (Xiang et al. 2011).
    """
    if (
        isinstance(sample_rate, bool)
        or not isinstance(sample_rate, (int, np.integer))
        or sample_rate <= 0
    ):
        raise InvalidAudioError(_("sample_rate must be a positive integer"))
    if (
        isinstance(max_slopes, bool)
        or not isinstance(max_slopes, int)
        or not 1 <= max_slopes <= MAX_SLOPES
    ):
        raise ValueError(_("max_slopes must be an integer from 1 to 3"))
    p = np.asarray(power, dtype=np.float64)
    if p.ndim != 1 or p.shape[0] < 32:
        raise InvalidAudioError(_("power must be a 1-D array with >= 32 samples"))
    if not np.all(np.isfinite(p)):
        raise InvalidAudioError(_("power contains NaN or inf"))
    if np.any(p < 0):
        raise InvalidAudioError(_("power must be non-negative"))
    scale = float(np.max(p))
    if scale == 0.0:
        return None

    n = p.shape[0]
    t = np.arange(n, dtype=np.float64) / sample_rate
    # Decimate for speed.
    step = max(1, n // 2000)
    t_fit = t[::step]
    p_fit = p[::step] / scale
    n_fit = len(t_fit)

    results: dict[int, tuple[FloatArray, FloatArray, float, float]] = {}
    bic_values: list[float] = []
    for k in range(1, max_slopes + 1):
        fit = _fit_n_slopes_gn(t_fit, p_fit, k)
        if fit is None:
            bic_values.append(float("inf"))
            continue
        amps, taus, noise, rss = fit
        # BIC = n*ln(rss/n) + k*ln(n). k = 2*n_slopes + 1 params.
        n_params = 2 * k + 1
        variance_floor = np.finfo(np.float64).eps ** 2 * float(np.mean(p_fit**2))
        bic = n_fit * math.log(
            max(rss / n_fit, variance_floor, 1e-300)
        ) + _BIC_PENALTY * n_params * math.log(n_fit)
        bic_values.append(bic)
        results[k] = (amps, taus, noise, rss)

    if not results:
        return None
    # Select minimum BIC.
    best_idx = int(np.argmin(bic_values))
    k_best = best_idx + 1
    amps_best, taus_best, noise_best, _rss_best = results[k_best]
    # Residual in dB (RMS of 10*log10(pred/p)).
    pred_best = _multi_exp_model(t_fit, amps_best, taus_best, noise_best)
    with np.errstate(divide="ignore", invalid="ignore"):
        log_ratio = 10.0 * np.log10(np.maximum(pred_best, 1e-300) / np.maximum(p_fit, 1e-300))
    residual_db = float(np.sqrt(np.mean(log_ratio[np.isfinite(log_ratio)] ** 2)))

    slopes = tuple(
        DecaySlope(amplitude=float(a) * scale, tau_s=float(tau))
        for a, tau in zip(amps_best, taus_best, strict=True)
    )
    return BayesianDecayFit(
        slopes=slopes,
        noise_power=float(noise_best) * scale,
        n_slopes=k_best,
        bic_values=tuple(bic_values),
        residual_db=residual_db,
    )
