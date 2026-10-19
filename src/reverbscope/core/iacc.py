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

import math
from dataclasses import dataclass

import numpy as np
from scipy.signal import correlate

from reverbscope.errors import InvalidAudioError
from reverbscope.i18n import _
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
    left_peak = float(np.max(np.abs(left[:n])))
    right_peak = float(np.max(np.abs(right[:n])))
    if left_peak == 0 or right_peak == 0:
        return None, None
    left_scaled = left[:n] / left_peak
    right_scaled = right[:n] / right_peak
    # IACF is an energy-normalized integral, not Pearson correlation.
    denom = math.sqrt(float(np.sum(left_scaled**2))) * math.sqrt(float(np.sum(right_scaled**2)))
    if denom <= 0.0:
        return None, None
    xcorr = correlate(left_scaled, right_scaled, mode="full") / denom
    # Lags: -(n-1) .. (n-1); we want |lag| <= max_delay.
    max_lag = math.floor(max_delay_s * sample_rate)
    lags = np.arange(-(n - 1), n)
    mask = np.abs(lags) <= max_lag
    if not np.any(mask):
        return None, None
    masked = np.abs(xcorr[mask])
    best_idx = int(np.argmax(masked))
    best_lag = int(lags[mask][best_idx])
    return float(np.clip(masked[best_idx], 0.0, 1.0)), float(best_lag) / sample_rate


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
    if (
        isinstance(sample_rate, bool)
        or not isinstance(sample_rate, (int, np.integer))
        or sample_rate <= 0
    ):
        raise InvalidAudioError(_("sample_rate must be a positive integer"))
    if not math.isfinite(early_split_s) or early_split_s <= 0:
        raise InvalidAudioError(_("early_split_s must be finite and positive"))
    left = np.asarray(left_ir, dtype=np.float64)
    right = np.asarray(right_ir, dtype=np.float64)
    if left.ndim != 1 or right.ndim != 1:
        raise InvalidAudioError(_("impulse responses must be one-dimensional"))
    if left.shape[0] == 0 or right.shape[0] == 0:
        raise InvalidAudioError(_("impulse responses must be non-empty"))
    if not (np.all(np.isfinite(left)) and np.all(np.isfinite(right))):
        raise InvalidAudioError(_("impulse responses contain NaN or inf"))

    n = min(left.shape[0], right.shape[0])
    left, right = left[:n], right[:n]
    split = n if early_split_s >= n / sample_rate else max(1, round(early_split_s * sample_rate))

    iacc_e, _delay_e = _normalized_xcorr_max(left[:split], right[:split], sample_rate)
    iacc_l, _delay_l = _normalized_xcorr_max(left[split:], right[split:], sample_rate)
    iacc_a, delay = _normalized_xcorr_max(left, right, sample_rate)
    return IACCResult(
        iacc_early=iacc_e,
        iacc_late=iacc_l,
        iacc_overall=iacc_a,
        delay_s=delay,
    )
