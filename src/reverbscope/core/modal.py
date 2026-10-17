"""Modal decay estimation via time-reversed linear prediction (M8).

Karjalainen, Antsalo, Mäkivirta, Peltonen & Välimäki, "Estimation of modal
decay parameters from noisy response measurements," JAES 50(11), 867–878,
2002.

Method: time-reverse the measured response with exponential weighting, then
apply all-pole linear-prediction modeling. The poles give per-mode
frequencies and decay times. This is robust for low-frequency/modal decay
parameters where octave-band Schroeder analysis is unreliable, and cheap:
O(N·p) linear least squares instead of nonlinear optimization.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from reverbscope.errors import InvalidAudioError
from reverbscope.models.audio import FloatArray

#: Default LP order (number of poles). Each mode needs 2 poles (complex pair).
DEFAULT_LP_ORDER = 24
#: Default exponential weighting factor (per sample) for the time-reversed signal.
#: Emphasizes the late decay (early after reversal).
DEFAULT_WEIGHT_BETA = 0.9995


@dataclass(frozen=True)
class ModalDecay:
    """One estimated mode: frequency and decay time."""

    frequency_hz: float
    #: Time for 60 dB decay (s), from the pole radius.
    t60_s: float
    #: Pole magnitude (stability indicator, < 1).
    pole_radius: float


def _levinson_durbin(autocorr: FloatArray, order: int) -> FloatArray:
    """LP coefficients via Levinson-Durbin recursion.

    Returns ``a[1..order]`` such that x[n] ≈ -sum(a[k] * x[n-k]).
    """
    # autocorr[0..order]
    a = np.zeros(order + 1, dtype=np.float64)
    e = float(autocorr[0])
    if e <= 0.0:
        return np.zeros(order, dtype=np.float64)
    a[0] = 1.0
    for i in range(1, order + 1):
        acc = 0.0
        for j in range(1, i):
            acc += a[j] * float(autocorr[i - j])
        k = (float(autocorr[i]) - acc) / e
        # Clamp reflection coefficient for stability.
        k = max(-0.999999, min(0.999999, k))
        a[i] = k
        for j in range(1, i):
            a[j] = a[j] - k * a[i - j]
        e *= 1.0 - k * k
        if e <= 0.0:
            break
    # Return a[1..order] (a[0] is 1.0).
    return a[1:]


def estimate_modal_decays(
    impulse_response: FloatArray,
    sample_rate: int,
    *,
    lp_order: int = DEFAULT_LP_ORDER,
    weight_beta: float = DEFAULT_WEIGHT_BETA,
    min_freq_hz: float = 20.0,
    max_freq_hz: float | None = None,
) -> tuple[ModalDecay, ...]:
    """Estimate modal decay parameters (M8, Karjalainen et al. 2002).

    Time-reverses the impulse response, applies exponential weighting, fits
    an all-pole LP model, and converts stable poles to (frequency, T60).

    Only poles with frequency in ``[min_freq_hz, max_freq_hz]`` (default Nyquist)
    and radius < 1 (stable) are returned, sorted by frequency.
    """
    if sample_rate <= 0:
        raise InvalidAudioError("sample_rate must be positive")
    x = np.asarray(impulse_response, dtype=np.float64)
    if x.ndim != 1 or x.shape[0] < lp_order + 2:
        raise InvalidAudioError("impulse response too short for LP order")
    if not np.all(np.isfinite(x)):
        raise InvalidAudioError("impulse response contains NaN or inf")

    # 1. Time-reverse.
    x_rev = x[::-1].copy()
    # 2. Exponential weighting: emphasizes the (original) late decay.
    n = x_rev.shape[0]
    weights = weight_beta ** np.arange(n, dtype=np.float64)
    x_w = x_rev * weights
    # 3. Remove DC.
    x_w = x_w - np.mean(x_w)
    # 4. Autocorrelation.
    autocorr = np.correlate(x_w, x_w, mode="full")[n - 1 : n + lp_order]
    if autocorr[0] <= 0.0:
        return ()
    # 5. LP coefficients via Levinson-Durbin.
    a = _levinson_durbin(autocorr, lp_order)
    # 6. Roots of the prediction polynomial: 1 + a[1]z^-1 + ... + a[p]z^-p = 0
    #    Multiply by z^p: z^p + a[1]z^{p-1} + ... + a[p] = 0.
    poly = np.concatenate([[1.0], a])
    roots = np.roots(poly)
    # 7. Convert to (frequency, T60).
    if max_freq_hz is None:
        max_freq_hz = sample_rate / 2.0
    modes: list[ModalDecay] = []
    for r in roots:
        radius = abs(r)
        if radius >= 1.0 or radius <= 0.0:
            continue  # Unstable or degenerate.
        angle = math.atan2(r.imag, r.real)
        freq = abs(angle) * sample_rate / (2.0 * math.pi)
        if freq < min_freq_hz or freq > max_freq_hz:
            continue
        # Decay: amplitude ~ radius^n. T60: radius^(T60*fs) = 1e-3.
        # T60 = ln(1e-3) / (fs * ln(radius)) = -6.9078 / (fs * ln(radius)).
        t60 = -6.907755278982136 / (sample_rate * math.log(radius))
        if t60 <= 0.0 or not math.isfinite(t60):
            continue
        modes.append(ModalDecay(frequency_hz=freq, t60_s=t60, pole_radius=radius))
    # Deduplicate complex pairs (keep positive frequency) and sort.
    # np.roots returns both; we take abs(angle) so pairs coincide.
    seen: set[tuple[int, int]] = set()
    unique: list[ModalDecay] = []
    for m in sorted(modes, key=lambda m: m.frequency_hz):
        key = (round(m.frequency_hz * 10), round(m.t60_s * 1000))
        if key not in seen:
            seen.add(key)
            unique.append(m)
    return tuple(unique)
