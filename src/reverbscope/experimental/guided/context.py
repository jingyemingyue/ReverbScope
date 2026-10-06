"""What a cloud model is allowed to see, and what a reply is allowed to change.

Business code must not build a prompt and post it. It goes through
:class:`CloudContextBuilder`.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from reverbscope.experimental.guided.compare import ComparisonGuidance
from reverbscope.experimental.guided.config import DataLevel, GuidedSettings, LengthChoice
from reverbscope.experimental.guided.findings import StructuredFinding, ValidityState
from reverbscope.experimental.guided.prompt import SYSTEM_PROMPT

FORBIDDEN_PAYLOAD_KEYS = frozenset(
    {
        "samples",
        "audio",
        "wav",
        "waveform",
        "impulse",
        "impulse_response",
        "recording",
        "notes",
        "room_name",
        "path",
        "file_path",
        "username",
        "serial",
        "serial_number",
        "location",
        "device_id",
        "authorization",
        "api_key",
        "token",
    }
)

_NUMBER = re.compile(r"(?<![\w.])(-?\d+(?:\.\d+)?)(?![\w.])")

EXACT_CAUSE_PHRASES = (
    "caused by the desk",
    "caused by the table",
    "this is the desk",
    "the desk is the cause",
    "it is the ceiling",
    "桌面造成",
    "是桌面造成",
    "就是桌面",
    "一定是墙壁",
    "确定是墙",
)

DANGEROUS_PHRASES = (
    "disable the ground",
    "remove the safety ground",
    "lift the safety ground",
    "cut a hole in the wall",
    "拆除承重",
    "断开地线",
    "拆掉安全地线",
)

UNKNOWN_METRICS = ("STI", "IACC", "clarity index", "strength index G")

_LENGTH_LIMIT = {
    LengthChoice.CONCISE.value: 1,
    LengthChoice.BALANCED.value: 5,
    LengthChoice.DETAILED.value: 12,
}


@dataclass(frozen=True)
class CloudPayload:
    body: dict[str, Any]

    def to_json(self) -> str:
        return json.dumps(self.body, ensure_ascii=False, indent=2, sort_keys=True)


class CloudContextBuilder:
    def build(
        self,
        findings: tuple[StructuredFinding, ...],
        settings: GuidedSettings,
        *,
        language: str,
        comparison: ComparisonGuidance | None = None,
        bands: tuple[tuple[float, float | None, str], ...] = (),
    ) -> CloudPayload:
        limit = _LENGTH_LIMIT.get(settings.length, 5)
        chosen = findings[:limit]
        items = [self._finding(item) for item in chosen]
        body: dict[str, Any] = {
            "schema": "reverbscope.guided.cloud_context.v1",
            "language": language,
            "expertise": settings.expertise,
            "length": settings.length,
            "data_level": settings.data_level,
            "findings": items,
            "comparison_overall": None if comparison is None else comparison.overall.value,
            "instructions": SYSTEM_PROMPT,
        }
        if settings.data_level == DataLevel.DETAILED.value:
            body["band_summaries"] = [
                {"center_hz": center, "rt60_s": rt60, "t30_validity": validity}
                for center, rt60, validity in bands
                if validity == "valid" and rt60 is not None
            ]
            model = settings.generic_device_model.strip()
            if model and not _looks_secret(model):
                body["generic_device_model"] = model
        if comparison is not None and settings.data_level == DataLevel.DETAILED.value:
            body["comparison_items"] = [item.to_dict() for item in comparison.items]
        return CloudPayload(_strip(body))

    def _finding(self, item: StructuredFinding) -> dict[str, Any]:
        evidence: dict[str, Any] = {}
        if item.validity is not ValidityState.INVALID:
            for value in item.evidence:
                if isinstance(value.value, int | float | str) or value.value is None:
                    evidence[value.key] = value.value
        return {
            "finding_id": item.finding_id,
            "type": item.type.value,
            "severity": item.severity.value,
            "confidence": item.confidence.value,
            "validity": item.validity.value,
            "validity_reason": item.validity_reason,
            "priority": item.priority.value,
            "evidence": evidence,
            "possible_cause_ids": list(item.possible_cause_ids),
        }


def _looks_secret(value: str) -> bool:
    lowered = value.lower()
    return any(part in lowered for part in ("sk-", "bearer", "api_key", "/", "\\", "serial"))


def _strip(value: Any) -> Any:
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, item in value.items():
            if key.lower() in FORBIDDEN_PAYLOAD_KEYS:
                continue
            cleaned[key] = _strip(item)
        return cleaned
    if isinstance(value, list):
        return [_strip(item) for item in value]
    return value


@dataclass(frozen=True)
class ValidationResult:
    accepted: bool
    reason: str = ""


def validate_block(
    text: str,
    finding: StructuredFinding,
    *,
    comparison: ComparisonGuidance | None = None,
) -> ValidationResult:
    """Reject a model sentence that invents a fact the engine did not supply."""
    lowered = text.lower()
    if any(phrase in text or phrase in lowered for phrase in EXACT_CAUSE_PHRASES):
        return ValidationResult(False, "unsupported_cause")
    if any(phrase in text or phrase in lowered for phrase in DANGEROUS_PHRASES):
        return ValidationResult(False, "dangerous_advice")
    if any(metric.lower() in lowered for metric in UNKNOWN_METRICS):
        return ValidationResult(False, "unknown_metric")
    stated = _stated_confidence(lowered)
    if stated is not None and stated != finding.confidence.value:
        return ValidationResult(False, "confidence_changed")
    if finding.validity is ValidityState.INVALID:
        if _NUMBER.search(text):
            return ValidationResult(False, "invalid_metric_number")
        if "valid" in lowered and finding.type.value == "insufficient_decay_range":
            return ValidationResult(False, "validity_changed")
    else:
        allowed = _allowed_numbers(finding)
        for match in _NUMBER.finditer(text):
            number = float(match.group(1))
            if not _number_allowed(number, allowed):
                return ValidationResult(False, "invented_number")
    if comparison is not None and _contradicts_comparison(lowered, comparison):
        return ValidationResult(False, "comparison_overruled")
    return ValidationResult(True)


def _stated_confidence(text: str) -> str | None:
    match = re.search(r"confidence\s*(?:is|:)\s*(high|medium|low)", text)
    if match is None:
        return None
    return match.group(1)


def _allowed_numbers(finding: StructuredFinding) -> set[float]:
    allowed: set[float] = set()
    for item in finding.evidence:
        if isinstance(item.value, bool) or not isinstance(item.value, int | float):
            continue
        number = float(item.value)
        allowed.add(number)
        allowed.add(round(number, 1))
        allowed.add(round(number, 2))
    return allowed


def _number_allowed(number: float, allowed: set[float]) -> bool:
    return any(abs(number - item) <= max(0.05, abs(item) * 0.02) for item in allowed)


def _contradicts_comparison(text: str, comparison: ComparisonGuidance) -> bool:
    better = ("better overall", "b is better", "improved overall")
    worse = ("worse overall", "b is worse")
    overall = comparison.overall.value
    if overall in {"worse", "slightly_worse"} and any(phrase in text for phrase in better):
        return True
    return overall in {"improved", "slightly_improved"} and any(phrase in text for phrase in worse)


def sanitize_public_query(text: str) -> str:
    """A knowledge lookup may name a topic. It may not carry a measurement."""
    cleaned = _NUMBER.sub(" ", text)
    cleaned = re.sub(r"[A-Za-z]:\\[^\s]+", " ", cleaned)
    cleaned = re.sub(r"/[\w./-]+", " ", cleaned)
    return " ".join(cleaned.split())


def session_explanation_record(provider_type: str, provider: str, model: str) -> dict[str, str]:
    """Safe to store in a session. The key is not a field."""
    return {
        "explanation_provider_type": provider_type,
        "provider": provider,
        "model": model,
    }


def sanitize_issue_report(payload: dict[str, Any]) -> dict[str, Any]:
    """Bug-report environment. Provider name may stay. Secrets may not."""
    blocked = FORBIDDEN_PAYLOAD_KEYS | {
        "headers",
        "authorization",
        "prompt",
        "request_body",
        "response_body",
    }
    cleaned: dict[str, Any] = {}
    for key, value in payload.items():
        if key.lower() in blocked:
            continue
        if isinstance(value, str):
            cleaned[key] = _redact_text(value)
        elif isinstance(value, dict):
            nested = sanitize_issue_report(value)
            cleaned[key] = nested
        else:
            cleaned[key] = value
    return cleaned


def _redact_text(text: str) -> str:
    from reverbscope.experimental.guided.privacy import REDACTOR

    return REDACTOR.redact(text)


def attachment_payload(*, explicit_upload: bool, kind: str) -> dict[str, str]:
    """Audio, logs, and sessions are never part of a normal explanation."""
    if not explicit_upload:
        raise PermissionError("audio, logs, and full sessions need a separate explicit upload")
    return {"attachment": kind, "explicit_upload": "true"}


def assert_no_secret(payload: object, secret: str) -> None:
    if not secret:
        return
    blob = json.dumps(payload, default=str)
    if secret in blob:
        raise AssertionError("secret appeared in a payload that must not contain it")
    if not secret:
        return
    blob = json.dumps(payload, default=str)
    if secret in blob:
        raise AssertionError("secret appeared in a payload that must not contain it")
