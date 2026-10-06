"""Structured findings. Facts come from the diagnostic engine, never from a model."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class FindingType(StrEnum):
    STRONG_EARLY_REFLECTION = "strong_early_reflection"
    LOW_FREQUENCY_DECAY_LONG = "low_frequency_decay_long"
    LOW_FREQUENCY_PEAK = "low_frequency_peak"
    LOW_FREQUENCY_NULL = "low_frequency_null"
    HIGH_NOISE_FLOOR = "high_noise_floor"
    MAINS_HUM_DETECTED = "mains_hum_detected"
    INSUFFICIENT_DECAY_RANGE = "insufficient_decay_range"
    LOW_DIRECT_SOUND_CONFIDENCE = "low_direct_sound_confidence"
    INPUT_TOO_HOT = "input_too_hot"
    SIGNAL_TOO_LOW = "signal_too_low"
    CLIPPING_DETECTED = "clipping_detected"
    SAMPLE_RATE_MISMATCH = "sample_rate_mismatch"
    TIME_STRETCH_DETECTED = "time_stretch_detected"
    DEVICE_TIMING_SUSPICIOUS = "device_timing_suspicious"
    AUDIO_DROPOUT_DETECTED = "audio_dropout_detected"


class Severity(StrEnum):
    INFO = "info"
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"


class Confidence(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Priority(StrEnum):
    """What to do first. Not a room score."""

    P0 = "P0"  # measurement invalid for the decision the user is about to make
    P1 = "P1"  # major issue
    P2 = "P2"  # secondary issue
    P3 = "P3"  # minor optimization


class ValidityState(StrEnum):
    VALID = "valid"
    INVALID = "invalid"
    NOT_APPLICABLE = "not_applicable"


@dataclass(frozen=True)
class EvidenceValue:
    """One number the engine measured. A model is not allowed to replace it."""

    key: str
    value: float | int | str | None
    unit: str

    def to_dict(self) -> dict[str, Any]:
        return {"key": self.key, "value": self.value, "unit": self.unit}


@dataclass(frozen=True)
class StructuredFinding:
    finding_id: str
    type: FindingType
    severity: Severity
    confidence: Confidence
    validity: ValidityState
    validity_reason: str | None
    priority: Priority
    evidence: tuple[EvidenceValue, ...]
    #: Cause ids the catalog may mention as possibilities. Never a verified surface.
    possible_cause_ids: tuple[str, ...]
    recommendation_id: str

    def evidence_map(self) -> dict[str, float | int | str | None]:
        return {item.key: item.value for item in self.evidence}

    def to_dict(self) -> dict[str, Any]:
        return {
            "finding_id": self.finding_id,
            "type": self.type.value,
            "severity": self.severity.value,
            "confidence": self.confidence.value,
            "validity": self.validity.value,
            "validity_reason": self.validity_reason,
            "priority": self.priority.value,
            "evidence": [item.to_dict() for item in self.evidence],
            "possible_cause_ids": list(self.possible_cause_ids),
            "recommendation_id": self.recommendation_id,
        }


def finding_id(kind: FindingType, index: int = 0) -> str:
    return f"{kind.value}:{index}"
