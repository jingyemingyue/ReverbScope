"""Finding model and the ``interpret`` entry point."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from reverbscope.i18n import _, current_locale
from reverbscope.models.comparison import ComparisonResult
from reverbscope.models.result import AnalysisResult


class Severity(StrEnum):
    INFO = "info"
    NOTICE = "notice"
    WARNING = "warning"


@dataclass(frozen=True)
class Finding:
    topic: str
    severity: Severity
    message: str
    #: The measured values the message is based on (units in the keys).
    evidence: dict[str, Any] = field(default_factory=dict)
    #: Stable dotted identifier so translations survive threshold changes.
    message_id: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    locale: str = "en"

    def to_dict(self) -> dict[str, Any]:
        return {
            "topic": self.topic,
            "severity": str(self.severity),
            "message": self.message,
            "evidence": self.evidence,
            "message_id": self.message_id,
            "params": self.params,
            "locale": self.locale,
        }


def finding(
    topic: str,
    severity: Severity,
    message_id: str,
    template: str,
    *,
    evidence: dict[str, Any] | None = None,
    display: dict[str, str] | None = None,
    **params: Any,
) -> Finding:
    """Build a :class:`Finding` whose sentence is rendered through ``_()``.

    ``params`` are stored in the finding as given (stable English values such
    as ``"longer"``); ``display`` overrides them for the rendered sentence only,
    so a translated word can be inserted without changing the stored value.
    """
    values = {**params, **(display or {})}
    message = _(template).format(**values) if values else _(template)
    return Finding(
        topic=topic,
        severity=severity,
        message=message,
        evidence=evidence or {},
        message_id=message_id,
        params=params,
        locale=current_locale(),
    )


def interpret(result: AnalysisResult, profile_name: str = "generic") -> list[Finding]:
    """Produce findings for ``result`` using the named recording profile."""
    from reverbscope.interpretation.profiles import get_profile

    return get_profile(profile_name).interpret(result)


def interpret_comparison(
    comparison: ComparisonResult, profile_name: str = "generic"
) -> list[Finding]:
    """Produce findings for a comparison using the named recording profile."""
    from reverbscope.interpretation.profiles import get_profile

    return get_profile(profile_name).interpret_comparison(comparison)
