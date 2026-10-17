"""Interaural Cross-Correlation (IACC) per ISO 3382-1, Annex B.

IACC quantifies the similarity of the sound at the two ears, related to
perceived spaciousness and envelopment. Computed as the maximum of the
normalized cross-correlation between left and right impulse responses:

    IACF(τ) = ∫ p_L(t)·p_R(t+τ) dt / sqrt(∫ p_L²(t)dt · ∫ p_R²(t)dt)

    IACC = max |IACF(τ)| for |τ| ≤ 1 ms

Three variants: IACC_E (early, 0–80 ms), IACC_L (late, 80 ms–end), IACC_A
(overall, 0–end). Requires a binaural or stereo impulse response.

Reference: ISO 3382-1:2009, Annex B (informative). Clause numbers not
verified against the standard text.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.signal import correlate

from reverbscope.errors import InvalidAudioError
from reverbscope.models.audio import FloatArray

#: Maximum interaural delay for IACC search (s).
IACC_MAX_DELAY_S = 0.001
#: Early/late split (s).
IACC_EARLY_SPLIT_S = 0.080


@dataclass(frozen=True)
class IACCResult:
    """Interaural cross-correlation coefficients."""

    #: Early (0–80 ms).
    iacc_early: float | None
    #: Late (80 ms–end).
    iacc_late: float | None
    #: Overall (0–end, "A" for average).
    iacc_overall: float | None
    #: Interaural delay (s) at which the overall maximum was found.
    delay_s: float | None


def _normalized_xcorr_max(
    left: FloatArray,
    right: FloatArray,
    sample_rate: int,
    max_delay_s: float = IACC_MAX_DELAY_S,
) -> tuple[float | None, float | None]:
    """Max |normalized cross-correlation| and its delay (s)."""
    n = min(left.shape[0], right.shape[0])
    if n < 2:
        return None, None
    l = np.asarray(left[:n], dtype=np.float64)
    r = np.asarray(right[:n], dtype=np.float64)
    # Normalized cross-correlation.
    l = l - np.mean(l)
    r = r - np.mean(r)
    denom = float(np.sqrt(np.sum(l * l) * np.sum(r * r)))
    if denom <= 0.0:
        return None, None
    xcorr = correlate(l, r, mode="full") / denom
    # Lags: -(n-1) .. (n-1); we want |lag| <= max_delay.
    max_lag = int(round(max_delay_s * sample_rate))
    lags = np.arange(-(n - 1), n)
    mask = np.abs(lags) <= max_lag
    if not np.any(mask):
        return None, None
    masked = np.abs(xcorr[mask])
    best_idx = int(np.argmax(masked))
    best_lag = int(lags[mask][best_idx])
    return float(masked[best_idx]), float(best_lag) / sample_rate


def compute_iacc(
    left_ir: FloatArray,
    right_ir: FloatArray,
    sample_rate: int,
    *,
    early_split_s: float = IACC_EARLY_SPLIT_S,
) -> IACCResult:
    """IACC_E, IACC_L, IACC_A from a binaural/stereo impulse response.

    Both channels must be the same length (truncated to the shorter).
    Returns None fields when the computation is not possible.
    """
    if sample_rate <= 0:
        raise InvalidAudioError("sample_rate must be positive")
    l = np.asarray(left_ir, dtype=np.float64)
    r = np.asarray(right_ir, dtype=np.float64)
    if l.ndim != 1 or r.ndim != 1:
        raise InvalidAudioError("impulse responses must be one-dimensional")
    if l.shape[0] == 0 or r.shape[0] == 0:
        raise InvalidAudioError("impulse responses must be non-empty")
    if not (np.all(np.isfinite(l)) and np.all(np.isfinite(r))):
        raise InvalidAudioError("impulse responses contain NaN or inf")

    n = min(l.shape[0], r.shape[0])
    l, r = l[:n], r[:n]
    split = int(round(early_split_s * sample_rate))
    split = max(1, min(split, n - 1))

    iacc_e, _ = _normalized_xcorr_max(l[:split], r[:split], sample_rate)
    iacc_l, _ = _normalized_xcorr_max(l[split:], r[split:], sample_rate)
    iacc_a, delay = _normalized_xcorr_max(l, r, sample_rate)
    return IACCResult(
        iacc_early=iacc_e,
        iacc_late=iacc_l,
        iacc_overall=iacc_a,
        delay_s=delay,
    )
