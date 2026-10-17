"""Sound strength G per ISO 3382-1.

G = 10·log10( ∫ p²(t) dt / ∫ p_ref²(t) dt )

where p_ref is the impulse response measured at 10 m from the source in free
field (or an equivalent calibrated reference). G quantifies how much the room
amplifies the sound relative to the free-field 10 m reference, in dB.

G requires a calibrated source: the user measures the reference once (free
field, 10 m, same source settings) and stores it. All subsequent G values are
relative to that calibration. Without a calibration, G is not computed.

Reference: ISO 3382-1:2009, Clause 5.4. Clause numbers not verified against
the standard text.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from reverbscope.errors import InvalidAudioError
from reverbscope.models.audio import FloatArray

#: Reference distance for G calibration (m), per ISO 3382-1.
G_REFERENCE_DISTANCE_M = 10.0


@dataclass(frozen=True)
class CalibrationReference:
    """Calibrated free-field reference for G computation.

    Measured once at :data:`G_REFERENCE_DISTANCE_M` from the source in free
    field (or anechoic), with the same source level and settings as the room
    measurements that will use it.
    """

    #: Squared impulse response of the reference measurement.
    power: FloatArray
    sample_rate: int
    #: Distance actually used (m); 10.0 for the standard reference.
    distance_m: float = G_REFERENCE_DISTANCE_M
    #: Free-text note (e.g. "Genelec 8030C, -12 dBFS, 2026-10-18").
    note: str = ""

    def __post_init__(self) -> None:
        p = np.asarray(self.power, dtype=np.float64)
        if p.ndim != 1 or p.shape[0] == 0:
            raise InvalidAudioError("calibration power must be a non-empty 1-D array")
        if not np.all(np.isfinite(p)):
            raise InvalidAudioError("calibration power contains NaN or inf")
        if self.sample_rate <= 0:
            raise InvalidAudioError("sample_rate must be positive")
        if self.distance_m <= 0.0:
            raise InvalidAudioError("distance_m must be positive")


def compute_g(
    power: FloatArray,
    calibration: CalibrationReference,
) -> float | None:
    """Sound strength G (dB) relative to the calibration reference.

    Returns None when the calibration energy is not positive.
    """
    p = np.asarray(power, dtype=np.float64)
    if p.ndim != 1 or p.shape[0] == 0:
        raise InvalidAudioError("power must be a non-empty 1-D array")
    if not np.all(np.isfinite(p)):
        raise InvalidAudioError("power contains NaN or inf")
    ref = np.asarray(calibration.power, dtype=np.float64)
    energy = float(np.sum(p))
    ref_energy = float(np.sum(ref))
    if ref_energy <= 0.0 or energy < 0.0:
        return None
    # Distance correction if calibration was not at 10 m:
    # energy scales as 1/d², so G += 20·log10(d_ref / 10).
    distance_corr_db = 20.0 * np.log10(calibration.distance_m / G_REFERENCE_DISTANCE_M)
    g = 10.0 * np.log10(max(energy, 1e-300) / ref_energy) + distance_corr_db
    return float(g)


def compute_g_bands(
    band_powers: dict[float, FloatArray],
    calibration_bands: dict[float, CalibrationReference],
) -> dict[float, float | None]:
    """G per octave band (dB). Bands without a calibration return None."""
    result: dict[float, float | None] = {}
    for band_hz, power in band_powers.items():
        cal = calibration_bands.get(band_hz)
        if cal is None:
            result[band_hz] = None
        else:
            result[band_hz] = compute_g(power, cal)
    return result
