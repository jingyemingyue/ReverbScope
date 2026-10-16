"""The energy-time curve the workstation draws, and where reflection markers sit on it.

The curve is the reflection detector's own envelope
(:func:`reverbscope.core.reflections.reflection_envelope_db` with the
detector's 0.1 ms hold) referred to the detector's own 0 dB: the envelope
maximum within ±0.5 ms of the direct sound. A detected reflection therefore
lies exactly on the curve, at the level the result stores for it. See
docs/design/GUI_2_ARCHITECTURE.md §5.2.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from reverbscope.core.reflections import reflection_envelope_db
from reverbscope.display import DisplayDataError
from reverbscope.i18n import N_
from reverbscope.models.audio import FloatArray
from reverbscope.models.result import Reflection

#: The detector's peak hold (``detect_early_reflections``' default).
DETECTOR_HOLD_MS = 0.1


@dataclass(frozen=True)
class EtcCurve:
    """Time after the direct sound (ms) and level re the direct sound (dB)."""

    time_ms: FloatArray
    level_db: FloatArray
    sample_rate: int
    direct_index: int
    #: The envelope level that is 0 dB, in dB of the stored samples.
    reference_db: float


def etc_curve(samples: FloatArray, sample_rate: int, direct_index: int) -> EtcCurve:
    """The whole stored response as an energy-time curve."""
    ir = np.asarray(samples, dtype=np.float64)
    if ir.ndim != 1 or ir.shape[0] == 0:
        raise DisplayDataError(N_("no impulse response is stored with this measurement"))
    if not np.all(np.isfinite(ir)):
        raise DisplayDataError(N_("the stored impulse response holds invalid samples"))
    if sample_rate <= 0 or not 0 <= direct_index < ir.shape[0]:
        raise DisplayDataError(N_("the direct sound lies outside the stored impulse response"))
    env_db = reflection_envelope_db(ir, sample_rate, hold_ms=DETECTOR_HOLD_MS)
    half = max(1, round(0.5e-3 * sample_rate))
    lo = max(0, direct_index - half)
    hi = min(env_db.shape[0], direct_index + half + 1)
    reference = float(np.max(env_db[lo:hi]))
    time_ms = (np.arange(ir.shape[0], dtype=np.float64) - direct_index) * 1000.0 / sample_rate
    return EtcCurve(
        time_ms=time_ms,
        level_db=env_db - reference,
        sample_rate=sample_rate,
        direct_index=direct_index,
        reference_db=reference,
    )


def marker_index(curve: EtcCurve, delay_ms: float) -> int:
    """The curve sample at ``delay_ms`` after the direct sound.

    The detector reports a delay as a whole number of samples, so the
    rounding recovers that sample exactly.
    """
    index = curve.direct_index + round(delay_ms * curve.sample_rate / 1000.0)
    return int(min(max(index, 0), curve.level_db.shape[0] - 1))


def marker_points(curve: EtcCurve, reflections: tuple[Reflection, ...]) -> FloatArray:
    """``(n, 2)`` array of (time ms, level dB) on the curve, one row per reflection."""
    points = np.empty((len(reflections), 2), dtype=np.float64)
    for row, reflection in enumerate(reflections):
        index = marker_index(curve, reflection.delay_ms)
        points[row, 0] = curve.time_ms[index]
        points[row, 1] = curve.level_db[index]
    return points
