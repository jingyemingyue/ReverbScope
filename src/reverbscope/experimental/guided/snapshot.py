"""Privacy-safe view of a measurement. No waveform, path, note, or device id."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from reverbscope.models.result import (
    KIND_SAMPLE_RATE,
    KIND_TIME_STRETCH,
    AnalysisResult,
    Validity,
)


@dataclass(frozen=True)
class ReflectionView:
    delay_ms: float
    relative_level_db: float


@dataclass(frozen=True)
class BandView:
    center_hz: float
    rt60_s: float | None
    t30_validity: str
    t30_reason: str | None


@dataclass(frozen=True)
class MeasurementSnapshot:
    """Numbers the diagnostic engine is allowed to read."""

    sample_rate_hz: int = 48000
    direct_sound_confidence: str = "high"
    reflections: tuple[ReflectionView, ...] = ()
    broadband_t20_validity: str = "valid"
    broadband_t30_validity: str = "valid"
    broadband_t30_reason: str | None = None
    broadband_rt60_s: float | None = None
    bands: tuple[BandView, ...] = ()
    noise_rms_dbfs: float | None = None
    hum_bases_hz: tuple[float, ...] = ()
    clipped: bool = False
    recording_peak_dbfs: float | None = None
    playback_kind: str | None = None
    generated_rate_hz: int | None = None
    played_rate_hz: int | None = None
    warnings: tuple[str, ...] = ()
    low_peak_hz: float | None = None
    low_peak_prominence_db: float | None = None
    low_null_hz: float | None = None
    low_null_depth_db: float | None = None
    fr_resolution_hz: float | None = None
    distinguishable_low_hz: tuple[float, ...] = ()
    digital_silence: bool = False

    def low_mid_rt60(self) -> tuple[float, float] | None:
        """(max low RT60, mean mid RT60) using only bands that already have an estimate."""
        from reverbscope.experimental.guided.thresholds import (
            LOW_BAND_MAX_HZ,
            MID_BAND_MAX_HZ,
            MID_BAND_MIN_HZ,
        )

        low = [
            band.rt60_s
            for band in self.bands
            if band.rt60_s is not None and band.center_hz <= LOW_BAND_MAX_HZ.value
        ]
        mid = [
            band.rt60_s
            for band in self.bands
            if band.rt60_s is not None
            and MID_BAND_MIN_HZ.value <= band.center_hz <= MID_BAND_MAX_HZ.value
        ]
        if not low or not mid:
            return None
        return max(low), sum(mid) / len(mid)


def _validity_name(value: Validity) -> str:
    return str(value)


def _low_curve_features(
    frequencies_hz: np.ndarray,
    magnitude_db: np.ndarray,
) -> tuple[float | None, float | None, float | None, float | None]:
    """Peak and null against the low-band median, not against an ideal curve.

    A broad tilt (the whole low band quieter than the mids) is not a null.
    """
    low = (frequencies_hz >= 60.0) & (frequencies_hz <= 200.0)
    if int(np.count_nonzero(low)) < 5:
        return None, None, None, None
    low_f = frequencies_hz[low]
    low_mag = magnitude_db[low]
    median = float(np.median(low_mag))
    peak_i = int(np.argmax(low_mag))
    null_i = int(np.argmin(low_mag))
    peak = float(low_mag[peak_i] - median)
    dip = float(median - low_mag[null_i])
    return float(low_f[peak_i]), peak, float(low_f[null_i]), dip


def snapshot_from_result(result: AnalysisResult) -> MeasurementSnapshot:
    """Copy validated scalars off an analysis result. The waveform is not copied."""
    reflections = tuple(
        ReflectionView(delay_ms=item.delay_ms, relative_level_db=item.relative_db)
        for item in result.reflections.reflections
    )
    bands = tuple(
        BandView(
            center_hz=float(band.center_hz),
            rt60_s=band.rt60_estimate_s,
            t30_validity=_validity_name(band.t30.validity),
            t30_reason=band.t30.reason,
        )
        for band in result.decay.bands
        if band.center_hz is not None
    )
    hum = tuple(float(item.base_hz) for item in result.noise.hum if item.detected)
    clipped = bool(result.clipping.clipped) if result.clipping is not None else False
    peak = result.clipping.peak_dbfs if result.clipping is not None else None
    speed = result.impulse_response.playback_speed
    kind = None
    generated = None
    played = None
    if speed is not None:
        if speed.kind == KIND_SAMPLE_RATE:
            kind = "sample_rate_mismatch"
        elif speed.kind == KIND_TIME_STRETCH:
            kind = "time_stretch"
        else:
            kind = speed.kind
        generated = speed.generated_rate_hz
        played = speed.played_rate_hz
    magnitude = result.frequency_response.magnitude_db_smoothed
    if magnitude is None:
        magnitude = result.frequency_response.magnitude_db_raw
    peak_hz, peak_db, null_hz, null_db = _low_curve_features(
        result.frequency_response.frequencies_hz, magnitude
    )
    low_resonances = tuple(
        float(item.frequency_hz)
        for item in result.resonances.candidates
        if item.decay_distinguishable and item.frequency_hz <= 250.0
    )
    silence = any("digital silence" in note for note in result.noise.notes)
    broadband = result.decay.broadband
    resolution = result.frequency_response.resolution_hz
    fr_resolution = None if resolution == float("inf") else float(resolution)
    return MeasurementSnapshot(
        sample_rate_hz=result.sample_rate,
        direct_sound_confidence=result.impulse_response.direct_sound_confidence,
        reflections=reflections,
        broadband_t20_validity=_validity_name(broadband.t20.validity),
        broadband_t30_validity=_validity_name(broadband.t30.validity),
        broadband_t30_reason=broadband.t30.reason,
        broadband_rt60_s=broadband.rt60_estimate_s,
        bands=bands,
        noise_rms_dbfs=result.noise.rms_dbfs,
        hum_bases_hz=hum,
        clipped=clipped,
        recording_peak_dbfs=peak,
        playback_kind=kind,
        generated_rate_hz=generated,
        played_rate_hz=played,
        warnings=tuple(result.warnings),
        low_peak_hz=peak_hz,
        low_peak_prominence_db=peak_db,
        low_null_hz=null_hz,
        low_null_depth_db=null_db,
        fr_resolution_hz=fr_resolution,
        distinguishable_low_hz=low_resonances,
        digital_silence=silence,
    )
