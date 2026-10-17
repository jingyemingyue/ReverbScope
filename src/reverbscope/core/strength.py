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

import math
from dataclasses import dataclass

import numpy as np

from reverbscope.errors import InvalidAudioError
from reverbscope.i18n import _
from reverbscope.models.audio import FloatArray

#: Reference distance for G calibration (m), per ISO 3382-1.
G_REFERENCE_DISTANCE_M = 10.0


def _power_values(power: FloatArray) -> FloatArray:
    values = np.asarray(power, dtype=np.float64)
    if values.ndim != 1 or values.size == 0:
        raise InvalidAudioError(_("power must be a non-empty 1-D array"))
    if not np.all(np.isfinite(values)) or np.any(values < 0):
        raise InvalidAudioError(_("power must be finite and non-negative"))
    return values


def _sample_rate(sample_rate: int) -> int:
    if (
        isinstance(sample_rate, bool)
        or not isinstance(sample_rate, (int, np.integer))
        or sample_rate <= 0
    ):
        raise InvalidAudioError(_("sample_rate must be a positive integer"))
    return int(sample_rate)


def _log_energy(power: FloatArray, sample_rate: int) -> float | None:
    peak = float(np.max(power))
    if peak == 0:
        return None
    # Log integrals keep finite input powers from overflowing their sums.
    return math.log(peak) + math.log(float(np.sum(power / peak))) - math.log(sample_rate)


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
        p = _power_values(self.power).copy()
        _sample_rate(self.sample_rate)
        if not math.isfinite(self.distance_m) or self.distance_m <= 0.0:
            raise InvalidAudioError(_("distance_m must be finite and positive"))
        p.setflags(write=False)
        object.__setattr__(self, "power", p)


def compute_g(
    power: FloatArray,
    calibration: CalibrationReference,
    *,
    sample_rate: int | None = None,
) -> float | None:
    """Sound strength G (dB) relative to the calibration reference.

    Returns None when either energy is zero. ``sample_rate`` is the rate of
    ``power``; omitting it assumes the calibration rate. The ratio uses time
    integrals, including when the two rates differ.
    """
    p = _power_values(power)
    rate = _sample_rate(calibration.sample_rate if sample_rate is None else sample_rate)
    energy = _log_energy(p, rate)
    ref_energy = _log_energy(_power_values(calibration.power), calibration.sample_rate)
    if ref_energy is None or energy is None:
        return None
    # Distance correction if calibration was not at 10 m:
    # E_ref(10 m) = E_ref(d) * (d / 10 m)**2. Correct the denominator.
    distance_corr_db = 20.0 * (
        math.log10(calibration.distance_m) - math.log10(G_REFERENCE_DISTANCE_M)
    )
    g = 10.0 * (energy - ref_energy) / math.log(10.0) - distance_corr_db
    return float(g)


def compute_g_bands(
    band_powers: dict[float, FloatArray],
    calibration_bands: dict[float, CalibrationReference],
    *,
    sample_rate: int | None = None,
) -> dict[float, float | None]:
    """G per octave band (dB). Bands without a calibration return None."""
    result: dict[float, float | None] = {}
    for band_hz, power in band_powers.items():
        cal = calibration_bands.get(band_hz)
        if cal is None:
            result[band_hz] = None
        else:
            result[band_hz] = compute_g(power, cal, sample_rate=sample_rate)
    return result
