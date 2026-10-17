"""Speech Transmission Index (STI) per IEC 60268-16.

STI quantifies speech intelligibility from the room impulse response via the
Modulation Transfer Function (MTF). For each octave band (125 Hz – 8 kHz) and
each of 14 modulation frequencies (0.63 – 12.5 Hz):

    m(fm) = |∫ h²(t)·e^(-j2π·fm·t) dt| / ∫ h²(t) dt

The MTF is converted to an effective SNR, clipped, averaged per band (MTI),
then combined with band weights to the final STI in [0, 1].

Reference: IEC 60268-16:2020, "Sound system equipment – Part 16: Objective
rating of speech intelligibility by speech transmission index".
Clause numbers not verified against the standard text; the algorithm follows
the standard's published method as restated in the literature.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from reverbscope.errors import InvalidAudioError
from reverbscope.models.audio import FloatArray

#: Modulation frequencies (Hz) per IEC 60268-16.
MODULATION_FREQUENCIES_HZ: tuple[float, ...] = (
    0.63, 0.80, 1.00, 1.25, 1.60, 2.00, 2.50,
    3.15, 4.00, 5.00, 6.30, 8.00, 10.0, 12.5,
)
#: Octave bands (Hz) for STI.
STI_OCTAVE_BANDS_HZ: tuple[float, ...] = (
    125.0, 250.0, 500.0, 1000.0, 2000.0, 4000.0, 8000.0,
)
#: Band weights (alpha) per IEC 60268-16, Table 3 (male weighting).
STI_BAND_WEIGHTS: tuple[float, ...] = (
    0.13, 0.14, 0.11, 0.12, 0.19, 0.17, 0.14,
)
#: Effective SNR clipping range (dB).
SNR_CLIP_DB = 15.0


@dataclass(frozen=True)
class BandSTI:
    """STI contribution of one octave band."""

    band_hz: float
    #: Modulation Transfer Index (mean of 14 transmission indices).
    mti: float
    #: Per-modulation-frequency transmission indices.
    transmission_indices: tuple[float, ...]


@dataclass(frozen=True)
class STIResult:
    """Speech Transmission Index and per-band details."""

    #: Final STI in [0, 1].
    sti: float
    bands: tuple[BandSTI, ...]
    #: Qualification per IEC 60268-16 Table B.1.
    qualification: str


def _mtf(
    power: FloatArray,
    sample_rate: int,
    modulation_hz: float,
) -> float:
    """Modulation Transfer Function at one modulation frequency.

    m(fm) = |∫ h²(t)·e^(-j2π·fm·t) dt| / ∫ h²(t) dt
    """
    n = power.shape[0]
    t = np.arange(n, dtype=np.float64) / sample_rate
    # Complex exponential at the modulation frequency.
    kernel = np.exp(-2j * np.pi * modulation_hz * t)
    numerator = abs(np.sum(power * kernel))
    denominator = float(np.sum(power))
    if denominator <= 0.0:
        return 0.0
    return float(np.clip(numerator / denominator, 0.0, 1.0))


def _transmission_index(m: float) -> float:
    """Convert MTF to Transmission Index via effective SNR."""
    # Avoid division by zero at m=1.
    m_clipped = float(np.clip(m, 1e-9, 1.0 - 1e-9))
    snr_eff = 10.0 * np.log10(m_clipped / (1.0 - m_clipped))
    snr_eff = float(np.clip(snr_eff, -SNR_CLIP_DB, SNR_CLIP_DB))
    ti = (snr_eff + SNR_CLIP_DB) / (2.0 * SNR_CLIP_DB)
    return float(np.clip(ti, 0.0, 1.0))


def _qualify(sti: float) -> str:
    """Qualification scale per IEC 60268-16, Annex B."""
    if sti >= 0.75:
        return "Excellent"
    if sti >= 0.60:
        return "Good"
    if sti >= 0.45:
        return "Fair"
    if sti >= 0.30:
        return "Poor"
    return "Bad"


def compute_sti(
    band_powers: dict[float, FloatArray],
    sample_rate: int,
) -> STIResult | None:
    """Compute STI from per-octave-band squared impulse responses.

    ``band_powers`` maps octave band centre frequency (Hz) to the squared
    (band-filtered) impulse response. Bands missing from STI_OCTAVE_BANDS_HZ
    are ignored; if none of the 7 bands are present, returns None.

    Returns the STI in [0, 1] with per-band MTI details.
    """
    if sample_rate <= 0:
        raise InvalidAudioError("sample_rate must be positive")
    bands: list[BandSTI] = []
    total_weight = 0.0
    weighted_sum = 0.0
    for band_hz, weight in zip(STI_OCTAVE_BANDS_HZ, STI_BAND_WEIGHTS):
        power = band_powers.get(band_hz)
        if power is None:
            continue
        power = np.asarray(power, dtype=np.float64)
        if power.ndim != 1 or power.shape[0] == 0:
            continue
        if not np.all(np.isfinite(power)):
            continue
        # 14 modulation frequencies → 14 transmission indices.
        tis = tuple(
            _transmission_index(_mtf(power, sample_rate, fm))
            for fm in MODULATION_FREQUENCIES_HZ
        )
        mti = float(np.mean(tis))
        bands.append(
            BandSTI(band_hz=band_hz, mti=mti, transmission_indices=tis)
        )
        weighted_sum += weight * mti
        total_weight += weight
    if not bands:
        return None
    # Renormalize weights if some bands are missing.
    sti = weighted_sum / total_weight if total_weight > 0.0 else 0.0
    sti = float(np.clip(sti, 0.0, 1.0))
    return STIResult(
        sti=sti,
        bands=tuple(bands),
        qualification=_qualify(sti),
    )
