"""Settings objects.

Settings are immutable dataclasses with validation in ``__post_init__`` so that
an invalid configuration fails early with a :class:`ConfigurationError` instead
of producing a misleading measurement.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, fields
from typing import Any

from reverbscope.errors import ConfigurationError
from reverbscope.i18n import _
from reverbscope.models.calibration import CalibrationRecord
from reverbscope.models.loadutil import settings_payload

SUPPORTED_SAMPLE_RATES: tuple[int, ...] = (44100, 48000, 88200, 96000, 176400, 192000)
DEFAULT_SAMPLE_RATE = 48000

#: Default octave-band centre frequencies (Hz) for decay analysis. ISO 3382-2
#: uses 125 Hz to 4 kHz for ordinary rooms; 63 Hz and 8 kHz are added because
#: recording rooms are usually small and low-frequency problems matter most.
DEFAULT_OCTAVE_BANDS_HZ: tuple[float, ...] = (
    63.0,
    125.0,
    250.0,
    500.0,
    1000.0,
    2000.0,
    4000.0,
    8000.0,
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ConfigurationError(message)


@dataclass(frozen=True)
class SweepSettings:
    """Parameters of the exponential sine sweep (ESS) test signal.

    Units: seconds, hertz, dBFS (peak amplitude relative to digital full scale).
    """

    sample_rate: int = DEFAULT_SAMPLE_RATE
    duration_s: float = 10.0
    start_hz: float = 20.0
    end_hz: float = 20000.0
    fade_in_s: float = 0.05
    fade_out_s: float = 0.01
    #: Peak level of the sweep in dBFS. Deliberately conservative: the user is
    #: told to start with the monitor level low (see docs/MEASUREMENT_METHODOLOGY.md).
    level_dbfs: float = -12.0
    #: Silence before the sweep. Used by the noise analysis as the quiet segment.
    pre_silence_s: float = 1.0
    #: Silence after the sweep so that the room decay is captured.
    post_silence_s: float = 3.0

    def __post_init__(self) -> None:
        _require(
            isinstance(self.sample_rate, int) and self.sample_rate > 0,
            _("sample_rate must be a positive integer"),
        )
        _require(
            self.sample_rate in SUPPORTED_SAMPLE_RATES,
            _("sample_rate {rate} is not supported; use one of {supported}").format(
                rate=self.sample_rate, supported=SUPPORTED_SAMPLE_RATES
            ),
        )
        _require(
            math.isfinite(self.duration_s) and self.duration_s >= 0.5,
            _("duration_s must be >= 0.5 s"),
        )
        _require(self.duration_s <= 120.0, _("duration_s must be <= 120 s"))
        _require(self.start_hz > 0.0, _("start_hz must be > 0"))
        _require(self.end_hz > self.start_hz, _("end_hz must be greater than start_hz"))
        _require(
            self.end_hz <= self.sample_rate / 2.0, _("end_hz must not exceed the Nyquist frequency")
        )
        _require(self.fade_in_s >= 0.0 and self.fade_out_s >= 0.0, _("fades must be >= 0"))
        _require(
            self.fade_in_s + self.fade_out_s < self.duration_s,
            _("fades must be shorter than the sweep"),
        )
        _require(
            math.isfinite(self.level_dbfs) and self.level_dbfs <= 0.0,
            _("level_dbfs must be <= 0 dBFS"),
        )
        _require(
            self.level_dbfs >= -80.0, _("level_dbfs below -80 dBFS is not a usable test signal")
        )
        _require(
            self.pre_silence_s >= 0.0 and self.post_silence_s >= 0.0, _("silences must be >= 0")
        )

    @property
    def amplitude(self) -> float:
        """Linear peak amplitude corresponding to :attr:`level_dbfs`."""
        return float(10.0 ** (self.level_dbfs / 20.0))

    @property
    def sweep_samples(self) -> int:
        return round(self.duration_s * self.sample_rate)

    @property
    def total_samples(self) -> int:
        return (
            round(self.pre_silence_s * self.sample_rate)
            + self.sweep_samples
            + round(self.post_silence_s * self.sample_rate)
        )

    @property
    def sweep_rate(self) -> float:
        """``L = T / ln(f2/f1)`` in seconds (Farina 2000)."""
        return self.duration_s / math.log(self.end_hz / self.start_hz)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SweepSettings:
        payload = settings_payload(data, {f.name for f in fields(cls)}, kind="sweep settings")
        return cls(**payload)

    def with_sample_rate(self, sample_rate: int) -> SweepSettings:
        """Return the same sweep definition at another sample rate."""
        return SweepSettings(**{**asdict(self), "sample_rate": sample_rate})


@dataclass(frozen=True)
class AnalysisSettings:
    """Parameters of the analysis pipeline. All thresholds are documented in
    docs/MEASUREMENT_METHODOLOGY.md."""

    #: Recording channel to analyse. ``None`` selects the channel with the
    #: highest RMS level (and records a warning).
    channel: int | None = None
    #: Time kept before the detected direct sound (ms).
    ir_pre_delay_ms: float = 5.0
    #: Maximum impulse response length analysed (s).
    ir_max_length_s: float = 6.0
    octave_bands_hz: tuple[float, ...] = DEFAULT_OCTAVE_BANDS_HZ
    #: Frequency-response window length (s) starting at the IR start. ``None``
    #: uses the whole valid impulse response.
    fr_window_s: float | None = None
    #: Fractional-octave smoothing denominator (6 -> 1/6 octave). 0 disables.
    fr_smoothing_fraction: int = 6
    #: Minimum quiet-segment length for the noise analysis (s).
    noise_min_segment_s: float = 0.5
    #: Early reflection search window after the direct sound (ms).
    reflections_min_delay_ms: float = 0.8
    reflections_max_delay_ms: float = 80.0
    #: Reflections below this level relative to the direct sound are ignored (dB).
    reflections_threshold_db: float = -20.0
    #: Minimum peak prominence in the envelope (dB).
    reflections_prominence_db: float = 6.0
    #: Upper frequency for the potential-resonance search (Hz).
    resonance_max_hz: float = 300.0
    resonance_min_prominence_db: float = 6.0
    #: Required margin between the evaluation range and the noise floor (dB).
    #: ISO 3382-1 requires the decay range to be at least 10 dB above noise.
    decay_noise_margin_db: float = 10.0
    #: Straight line from the loudspeaker's acoustic centre to the microphone
    #: capsule (m), measured with a tape. Without it no geometry is reported.
    placement_distance_m: float | None = None
    #: Microphone capsule above the first solid horizontal surface below it
    #: (m) -- the desk top at a desk, otherwise the floor. Needs
    #: ``placement_distance_m``; on its own it buys nothing.
    placement_mic_height_m: float | None = None
    #: Air temperature (C). ``None`` assumes 20 C and records that it did.
    placement_temperature_c: float | None = None
    #: 0-based channel of a loopback recording, or ``None`` when unused.
    loopback_channel: int | None = None
    #: Reserved. Stored and ignored by the analysis in 1.0.
    calibration: CalibrationRecord | None = None

    def __post_init__(self) -> None:
        _require(self.channel is None or self.channel >= 0, _("channel must be >= 0 or None"))
        _require(self.ir_pre_delay_ms >= 0.0, _("ir_pre_delay_ms must be >= 0"))
        _require(self.ir_max_length_s > 0.1, _("ir_max_length_s must be > 0.1 s"))
        _require(len(self.octave_bands_hz) > 0, _("at least one octave band is required"))
        _require(all(f > 0 for f in self.octave_bands_hz), _("octave band frequencies must be > 0"))
        _require(
            list(self.octave_bands_hz) == sorted(self.octave_bands_hz),
            _("octave_bands_hz must be ascending"),
        )
        _require(self.fr_window_s is None or self.fr_window_s > 0.0, _("fr_window_s must be > 0"))
        _require(self.fr_smoothing_fraction >= 0, _("fr_smoothing_fraction must be >= 0"))
        _require(self.noise_min_segment_s > 0.0, _("noise_min_segment_s must be > 0"))
        _require(
            0.0 <= self.reflections_min_delay_ms < self.reflections_max_delay_ms,
            _("reflection delay window is invalid"),
        )
        _require(
            self.reflections_threshold_db < 0.0, _("reflections_threshold_db must be negative")
        )
        _require(self.reflections_prominence_db > 0.0, _("reflections_prominence_db must be > 0"))
        _require(self.resonance_max_hz > 20.0, _("resonance_max_hz must be > 20 Hz"))
        _require(
            self.resonance_min_prominence_db > 0.0, _("resonance_min_prominence_db must be > 0")
        )
        _require(self.decay_noise_margin_db >= 0.0, _("decay_noise_margin_db must be >= 0"))
        _require(
            self.placement_distance_m is None or 0.20 <= self.placement_distance_m <= 15.0,
            _("placement_distance_m must be between 0.20 m and 15 m"),
        )
        _require(
            self.placement_mic_height_m is None or 0.02 <= self.placement_mic_height_m <= 5.0,
            _("placement_mic_height_m must be between 0.02 m and 5 m"),
        )
        _require(
            self.placement_temperature_c is None or -20.0 <= self.placement_temperature_c <= 50.0,
            _("placement_temperature_c must be between -20 C and 50 C"),
        )
        _require(
            self.placement_mic_height_m is None or self.placement_distance_m is not None,
            _(
                "placement_mic_height_m needs placement_distance_m: a height on its own "
                "cannot be turned into geometry"
            ),
        )
        _require(
            self.loopback_channel is None or self.loopback_channel >= 0,
            _("loopback_channel must be >= 0 or None"),
        )

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["octave_bands_hz"] = list(self.octave_bands_hz)
        if self.calibration is not None:
            data["calibration"] = self.calibration.to_dict()
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AnalysisSettings:
        payload = settings_payload(data, {f.name for f in fields(cls)}, kind="analysis settings")
        if "octave_bands_hz" in payload:
            payload["octave_bands_hz"] = tuple(float(f) for f in payload["octave_bands_hz"])
        if payload.get("calibration") is not None:
            payload["calibration"] = CalibrationRecord.from_dict(payload["calibration"])
        return cls(**payload)
