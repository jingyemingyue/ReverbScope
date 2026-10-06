"""Deterministic diagnostic engine.

Reads a :class:`MeasurementSnapshot` and emits structured findings. It does not
call a model, does not open the network, and does not invent a metric the
measurement marked invalid.
"""

from __future__ import annotations

from reverbscope.experimental.guided.findings import (
    Confidence,
    EvidenceValue,
    FindingType,
    Priority,
    Severity,
    StructuredFinding,
    ValidityState,
    finding_id,
)
from reverbscope.experimental.guided.snapshot import MeasurementSnapshot
from reverbscope.experimental.guided.thresholds import (
    FR_CONFIDENT_RESOLUTION_HZ,
    HIGH_NOISE_RMS_DBFS,
    HOT_PEAK_DBFS,
    LOW_NULL_DEPTH_DB,
    LOW_PEAK_PROMINENCE_DB,
    LOW_SIGNAL_PEAK_DBFS,
    SLOW_LOW_RATIO,
    STRONG_REFLECTION_LEVEL_DB,
    STRONG_REFLECTION_WINDOW_MS,
    VERY_CLOSE_REFLECTION_MS,
    VERY_STRONG_REFLECTION_DB,
)

_INSUFFICIENT = "insufficient_decay_range"


def _ev(key: str, value: float | int | str | None, unit: str) -> EvidenceValue:
    return EvidenceValue(key=key, value=value, unit=unit)


def _warning_has(snapshot: MeasurementSnapshot, needle: str) -> bool:
    return any(needle in warning for warning in snapshot.warnings)


def diagnose(snapshot: MeasurementSnapshot) -> tuple[StructuredFinding, ...]:
    """Findings in a stable order. Priority is assigned here, not by a model."""
    found: list[StructuredFinding] = []
    found.extend(_integrity(snapshot))
    found.extend(_signal(snapshot))
    found.extend(_reflections(snapshot))
    found.extend(_decay(snapshot))
    found.extend(_spectrum(snapshot))
    found.extend(_noise(snapshot))
    return tuple(found)


def _integrity(snapshot: MeasurementSnapshot) -> list[StructuredFinding]:
    found: list[StructuredFinding] = []
    if snapshot.playback_kind == "sample_rate_mismatch":
        found.append(
            StructuredFinding(
                finding_id=finding_id(FindingType.SAMPLE_RATE_MISMATCH),
                type=FindingType.SAMPLE_RATE_MISMATCH,
                severity=Severity.CRITICAL,
                confidence=Confidence.HIGH,
                validity=ValidityState.VALID,
                validity_reason=None,
                priority=Priority.P0,
                evidence=(
                    _ev("generated_rate_hz", snapshot.generated_rate_hz, "Hz"),
                    _ev("played_rate_hz", snapshot.played_rate_hz, "Hz"),
                ),
                possible_cause_ids=("project_rate", "import_without_conversion"),
                recommendation_id="regenerate_sweep_at_project_rate",
            )
        )
    elif snapshot.playback_kind == "time_stretch":
        found.append(
            StructuredFinding(
                finding_id=finding_id(FindingType.TIME_STRETCH_DETECTED),
                type=FindingType.TIME_STRETCH_DETECTED,
                severity=Severity.CRITICAL,
                confidence=Confidence.HIGH,
                validity=ValidityState.VALID,
                validity_reason=None,
                priority=Priority.P0,
                evidence=(),
                possible_cause_ids=("warp", "flex_time", "follow_tempo", "elastic_audio"),
                recommendation_id="disable_time_stretch",
            )
        )
    if snapshot.direct_sound_confidence != "high":
        low = snapshot.direct_sound_confidence == "low"
        found.append(
            StructuredFinding(
                finding_id=finding_id(FindingType.LOW_DIRECT_SOUND_CONFIDENCE),
                type=FindingType.LOW_DIRECT_SOUND_CONFIDENCE,
                severity=Severity.CRITICAL if low else Severity.HIGH,
                confidence=Confidence.HIGH,
                validity=ValidityState.VALID,
                validity_reason=None,
                priority=Priority.P0 if low else Priority.P1,
                evidence=(_ev("direct_sound_confidence", snapshot.direct_sound_confidence, ""),),
                possible_cause_ids=("wrong_sweep", "distortion", "overlap"),
                recommendation_id="confirm_direct_sound",
            )
        )
    if snapshot.clipped or _warning_has(snapshot, "clipping"):
        found.append(
            StructuredFinding(
                finding_id=finding_id(FindingType.CLIPPING_DETECTED),
                type=FindingType.CLIPPING_DETECTED,
                severity=Severity.CRITICAL,
                confidence=Confidence.HIGH,
                validity=ValidityState.VALID,
                validity_reason=None,
                priority=Priority.P0,
                evidence=(_ev("peak_dbfs", snapshot.recording_peak_dbfs, "dBFS"),),
                possible_cause_ids=("input_gain", "playback_level"),
                recommendation_id="lower_gain",
            )
        )
    if _warning_has(snapshot, "buffer problem") or _warning_has(snapshot, "dropout"):
        found.append(
            StructuredFinding(
                finding_id=finding_id(FindingType.AUDIO_DROPOUT_DETECTED),
                type=FindingType.AUDIO_DROPOUT_DETECTED,
                severity=Severity.CRITICAL,
                confidence=Confidence.HIGH,
                validity=ValidityState.VALID,
                validity_reason=None,
                priority=Priority.P0,
                evidence=(),
                possible_cause_ids=("buffer_underrun", "cpu_load"),
                recommendation_id="increase_buffer",
            )
        )
    if _warning_has(snapshot, "clock") or _warning_has(snapshot, "two devices"):
        found.append(
            StructuredFinding(
                finding_id=finding_id(FindingType.DEVICE_TIMING_SUSPICIOUS),
                type=FindingType.DEVICE_TIMING_SUSPICIOUS,
                severity=Severity.HIGH,
                confidence=Confidence.MEDIUM,
                validity=ValidityState.VALID,
                validity_reason=None,
                priority=Priority.P1,
                evidence=(),
                possible_cause_ids=("separate_clocks",),
                recommendation_id="one_clock",
            )
        )
    t30_bad = snapshot.broadband_t30_validity == _INSUFFICIENT
    t20_bad = snapshot.broadband_t20_validity == _INSUFFICIENT
    if t30_bad or t20_bad:
        both = t30_bad and t20_bad
        found.append(
            StructuredFinding(
                finding_id=finding_id(FindingType.INSUFFICIENT_DECAY_RANGE),
                type=FindingType.INSUFFICIENT_DECAY_RANGE,
                severity=Severity.HIGH if both else Severity.MODERATE,
                confidence=Confidence.HIGH,
                validity=ValidityState.INVALID,
                validity_reason=snapshot.broadband_t30_reason or "insufficient_decay_range",
                priority=Priority.P0 if both else Priority.P2,
                evidence=(),
                possible_cause_ids=("noise_floor", "short_sweep", "low_level"),
                recommendation_id="more_decay_range",
            )
        )
    return found


def _signal(snapshot: MeasurementSnapshot) -> list[StructuredFinding]:
    found: list[StructuredFinding] = []
    if snapshot.digital_silence:
        found.append(
            StructuredFinding(
                finding_id=finding_id(FindingType.SIGNAL_TOO_LOW),
                type=FindingType.SIGNAL_TOO_LOW,
                severity=Severity.CRITICAL,
                confidence=Confidence.HIGH,
                validity=ValidityState.INVALID,
                validity_reason="digital_silence",
                priority=Priority.P0,
                evidence=(),
                possible_cause_ids=("exported_sweep_track", "gate", "noise_reduction"),
                recommendation_id="export_microphone",
            )
        )
        return found
    peak = snapshot.recording_peak_dbfs
    if peak is None or snapshot.clipped:
        return found
    if peak >= HOT_PEAK_DBFS.value:
        found.append(
            StructuredFinding(
                finding_id=finding_id(FindingType.INPUT_TOO_HOT),
                type=FindingType.INPUT_TOO_HOT,
                severity=Severity.HIGH,
                confidence=Confidence.MEDIUM,
                validity=ValidityState.VALID,
                validity_reason=None,
                priority=Priority.P1,
                evidence=(_ev("peak_dbfs", peak, "dBFS"),),
                possible_cause_ids=("input_gain", "playback_level"),
                recommendation_id="lower_gain_slightly",
            )
        )
    elif peak <= LOW_SIGNAL_PEAK_DBFS.value:
        found.append(
            StructuredFinding(
                finding_id=finding_id(FindingType.SIGNAL_TOO_LOW),
                type=FindingType.SIGNAL_TOO_LOW,
                severity=Severity.HIGH,
                confidence=Confidence.MEDIUM,
                validity=ValidityState.VALID,
                validity_reason=None,
                priority=Priority.P1,
                evidence=(_ev("peak_dbfs", peak, "dBFS"),),
                possible_cause_ids=("mic_gain", "playback_level", "wrong_channel"),
                recommendation_id="raise_gain",
            )
        )
    return found


def _reflections(snapshot: MeasurementSnapshot) -> list[StructuredFinding]:
    window = STRONG_REFLECTION_WINDOW_MS.value
    level = STRONG_REFLECTION_LEVEL_DB.value
    strong = [
        item
        for item in snapshot.reflections
        if item.delay_ms <= window and item.relative_level_db >= level
    ]
    if not strong:
        return []
    first = max(strong, key=lambda item: item.relative_level_db)
    very = (
        first.delay_ms <= VERY_CLOSE_REFLECTION_MS.value
        and first.relative_level_db >= VERY_STRONG_REFLECTION_DB.value
    )
    confidence = Confidence.LOW if snapshot.direct_sound_confidence != "high" else Confidence.HIGH
    return [
        StructuredFinding(
            finding_id=finding_id(FindingType.STRONG_EARLY_REFLECTION),
            type=FindingType.STRONG_EARLY_REFLECTION,
            severity=Severity.HIGH if very else Severity.MODERATE,
            confidence=confidence,
            validity=ValidityState.VALID,
            validity_reason=None,
            priority=Priority.P1 if very else Priority.P2,
            evidence=(
                _ev("delay_ms", first.delay_ms, "ms"),
                _ev("relative_level_db", first.relative_level_db, "dB"),
                _ev("count_in_window", len(strong), "1"),
            ),
            possible_cause_ids=("nearby_hard_surface",),
            recommendation_id="move_or_cover",
        )
    ]


def _decay(snapshot: MeasurementSnapshot) -> list[StructuredFinding]:
    pair = snapshot.low_mid_rt60()
    if pair is None:
        return []
    low_max, mid_mean = pair
    if mid_mean <= 0.0 or low_max <= SLOW_LOW_RATIO.value * mid_mean:
        return []
    return [
        StructuredFinding(
            finding_id=finding_id(FindingType.LOW_FREQUENCY_DECAY_LONG),
            type=FindingType.LOW_FREQUENCY_DECAY_LONG,
            severity=Severity.MODERATE,
            confidence=Confidence.MEDIUM,
            validity=ValidityState.VALID,
            validity_reason=None,
            priority=Priority.P1,
            evidence=(
                _ev("low_max_rt60_s", low_max, "s"),
                _ev("mid_mean_rt60_s", mid_mean, "s"),
            ),
            possible_cause_ids=("room_modes", "boundary"),
            recommendation_id="move_and_recheck_low",
        )
    ]


def _spectrum(snapshot: MeasurementSnapshot) -> list[StructuredFinding]:
    found: list[StructuredFinding] = []
    if snapshot.distinguishable_low_hz:
        hz = snapshot.distinguishable_low_hz[0]
        found.append(
            StructuredFinding(
                finding_id=finding_id(FindingType.LOW_FREQUENCY_PEAK),
                type=FindingType.LOW_FREQUENCY_PEAK,
                severity=Severity.MODERATE,
                confidence=Confidence.HIGH,
                validity=ValidityState.VALID,
                validity_reason=None,
                priority=Priority.P2,
                evidence=(_ev("frequency_hz", hz, "Hz"),),
                possible_cause_ids=("room_mode", "loudspeaker", "boundary"),
                recommendation_id="move_and_recheck_peak",
            )
        )
    elif (
        snapshot.low_peak_prominence_db is not None
        and snapshot.low_peak_prominence_db >= LOW_PEAK_PROMINENCE_DB.value
        and snapshot.low_peak_hz is not None
    ):
        found.append(
            StructuredFinding(
                finding_id=finding_id(FindingType.LOW_FREQUENCY_PEAK),
                type=FindingType.LOW_FREQUENCY_PEAK,
                severity=Severity.LOW,
                confidence=_fr_confidence(snapshot),
                validity=ValidityState.VALID,
                validity_reason=None,
                priority=Priority.P2,
                evidence=(
                    _ev("frequency_hz", snapshot.low_peak_hz, "Hz"),
                    _ev("prominence_db", snapshot.low_peak_prominence_db, "dB"),
                ),
                possible_cause_ids=("room_mode", "loudspeaker", "boundary"),
                recommendation_id="move_and_recheck_peak",
            )
        )
    if (
        snapshot.low_null_depth_db is not None
        and snapshot.low_null_depth_db >= LOW_NULL_DEPTH_DB.value
        and snapshot.low_null_hz is not None
    ):
        found.append(
            StructuredFinding(
                finding_id=finding_id(FindingType.LOW_FREQUENCY_NULL),
                type=FindingType.LOW_FREQUENCY_NULL,
                severity=Severity.LOW,
                confidence=_fr_confidence(snapshot),
                validity=ValidityState.VALID,
                validity_reason=None,
                priority=Priority.P2,
                evidence=(
                    _ev("frequency_hz", snapshot.low_null_hz, "Hz"),
                    _ev("depth_db", snapshot.low_null_depth_db, "dB"),
                ),
                possible_cause_ids=("boundary_interference", "loudspeaker", "microphone"),
                recommendation_id="move_and_recheck_null",
            )
        )
    return found


def _fr_confidence(snapshot: MeasurementSnapshot) -> Confidence:
    resolution = snapshot.fr_resolution_hz
    if resolution is None or resolution > FR_CONFIDENT_RESOLUTION_HZ.value:
        return Confidence.LOW
    return Confidence.MEDIUM


def _noise(snapshot: MeasurementSnapshot) -> list[StructuredFinding]:
    found: list[StructuredFinding] = []
    rms = snapshot.noise_rms_dbfs
    if rms is not None and rms > HIGH_NOISE_RMS_DBFS.value:
        found.append(
            StructuredFinding(
                finding_id=finding_id(FindingType.HIGH_NOISE_FLOOR),
                type=FindingType.HIGH_NOISE_FLOOR,
                severity=Severity.MODERATE,
                confidence=Confidence.MEDIUM,
                validity=ValidityState.VALID,
                validity_reason=None,
                priority=Priority.P1,
                evidence=(_ev("rms_dbfs", rms, "dBFS"),),
                possible_cause_ids=("room_noise", "preamp", "gain"),
                recommendation_id="quiet_the_take",
            )
        )
    if snapshot.hum_bases_hz:
        found.append(
            StructuredFinding(
                finding_id=finding_id(FindingType.MAINS_HUM_DETECTED),
                type=FindingType.MAINS_HUM_DETECTED,
                severity=Severity.MODERATE,
                confidence=Confidence.HIGH,
                validity=ValidityState.VALID,
                validity_reason=None,
                priority=Priority.P1,
                evidence=(_ev("base_hz", snapshot.hum_bases_hz[0], "Hz"),),
                possible_cause_ids=("ground", "cables", "dimmers", "supply"),
                recommendation_id="hunt_hum",
            )
        )
    return found
