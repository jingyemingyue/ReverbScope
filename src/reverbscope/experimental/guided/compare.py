"""Deterministic A/B guidance. A model may explain this. It may not decide it."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from reverbscope.experimental.guided.findings import FindingType, StructuredFinding
from reverbscope.experimental.guided.snapshot import MeasurementSnapshot
from reverbscope.experimental.guided.thresholds import (
    DECAY_RATIO_DEADBAND,
    NOISE_DEADBAND_DB,
    REFLECTION_LEVEL_DEADBAND_DB,
)


class Change(StrEnum):
    IMPROVED = "improved"
    SLIGHTLY_IMPROVED = "slightly_improved"
    WORSE = "worse"
    SLIGHTLY_WORSE = "slightly_worse"
    UNCHANGED = "unchanged"
    MIXED = "mixed"
    NOT_COMPARABLE = "not_comparable"


@dataclass(frozen=True)
class ItemChange:
    topic: str
    change: Change
    #: Evidence the renderer may print. No invented number.
    evidence: tuple[tuple[str, float | str | None, str], ...] = ()
    finding_type: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "topic": self.topic,
            "change": self.change.value,
            "finding_type": self.finding_type,
            "evidence": [
                {"key": key, "value": value, "unit": unit} for key, value, unit in self.evidence
            ],
        }


@dataclass(frozen=True)
class ComparisonGuidance:
    overall: Change
    items: tuple[ItemChange, ...]
    new_issues: tuple[str, ...]
    resolved_issues: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "overall": self.overall.value,
            "items": [item.to_dict() for item in self.items],
            "new_issues": list(self.new_issues),
            "resolved_issues": list(self.resolved_issues),
            "room_score": None,
        }


def _signed(delta: float, deadband: float, *, better_when_lower: bool) -> Change:
    if abs(delta) < deadband:
        return Change.UNCHANGED
    improved = delta < 0.0 if better_when_lower else delta > 0.0
    slight = abs(delta) < deadband * 2.0
    if improved:
        return Change.SLIGHTLY_IMPROVED if slight else Change.IMPROVED
    return Change.SLIGHTLY_WORSE if slight else Change.WORSE


def _strongest(snapshot: MeasurementSnapshot) -> tuple[float, float] | None:
    if not snapshot.reflections:
        return None
    best = max(snapshot.reflections, key=lambda item: item.relative_level_db)
    return best.delay_ms, best.relative_level_db


def _ratio(snapshot: MeasurementSnapshot) -> float | None:
    pair = snapshot.low_mid_rt60()
    if pair is None or pair[1] <= 0.0:
        return None
    return pair[0] / pair[1]


def _types(findings: tuple[StructuredFinding, ...]) -> set[str]:
    return {item.type.value for item in findings}


def compare_guidance(
    baseline: MeasurementSnapshot,
    candidate: MeasurementSnapshot,
    baseline_findings: tuple[StructuredFinding, ...],
    candidate_findings: tuple[StructuredFinding, ...],
) -> ComparisonGuidance:
    """Say what changed. Never reduce the pair to one room score."""
    items: list[ItemChange] = []
    base_ref = _strongest(baseline)
    cand_ref = _strongest(candidate)
    if base_ref is None or cand_ref is None:
        items.append(ItemChange("early_reflection", Change.NOT_COMPARABLE))
    else:
        change = _signed(
            cand_ref[1] - base_ref[1],
            REFLECTION_LEVEL_DEADBAND_DB.value,
            better_when_lower=True,
        )
        items.append(
            ItemChange(
                "early_reflection",
                change,
                evidence=(
                    ("baseline_relative_level_db", base_ref[1], "dB"),
                    ("candidate_relative_level_db", cand_ref[1], "dB"),
                ),
                finding_type=FindingType.STRONG_EARLY_REFLECTION.value,
            )
        )
    base_ratio = _ratio(baseline)
    cand_ratio = _ratio(candidate)
    if base_ratio is None or cand_ratio is None:
        items.append(ItemChange("low_frequency_decay", Change.NOT_COMPARABLE))
    else:
        items.append(
            ItemChange(
                "low_frequency_decay",
                _signed(
                    cand_ratio - base_ratio,
                    DECAY_RATIO_DEADBAND.value,
                    better_when_lower=True,
                ),
                evidence=(
                    ("baseline_low_mid_ratio", base_ratio, "1"),
                    ("candidate_low_mid_ratio", cand_ratio, "1"),
                ),
                finding_type=FindingType.LOW_FREQUENCY_DECAY_LONG.value,
            )
        )
    if baseline.noise_rms_dbfs is None or candidate.noise_rms_dbfs is None:
        items.append(ItemChange("noise", Change.NOT_COMPARABLE))
    else:
        items.append(
            ItemChange(
                "noise",
                _signed(
                    candidate.noise_rms_dbfs - baseline.noise_rms_dbfs,
                    NOISE_DEADBAND_DB.value,
                    better_when_lower=True,
                ),
                evidence=(
                    ("baseline_rms_dbfs", baseline.noise_rms_dbfs, "dBFS"),
                    ("candidate_rms_dbfs", candidate.noise_rms_dbfs, "dBFS"),
                ),
                finding_type=FindingType.HIGH_NOISE_FLOOR.value,
            )
        )
    before = _types(baseline_findings)
    after = _types(candidate_findings)
    new_issues = tuple(sorted(after - before))
    resolved = tuple(sorted(before - after))
    for kind in new_issues:
        hz = None
        for item in candidate_findings:
            if item.type.value == kind:
                raw = item.evidence_map().get("frequency_hz")
                if isinstance(raw, int | float):
                    hz = float(raw)
        evidence: tuple[tuple[str, float | str | None, str], ...] = ()
        if hz is not None:
            evidence = (("frequency_hz", hz, "Hz"),)
        items.append(ItemChange("new_issue", Change.WORSE, evidence, kind))
    for kind in resolved:
        items.append(ItemChange("resolved", Change.IMPROVED, finding_type=kind))

    meaningful = [
        item.change
        for item in items
        if item.change not in (Change.UNCHANGED, Change.NOT_COMPARABLE, Change.MIXED)
    ]
    improved = {
        Change.IMPROVED,
        Change.SLIGHTLY_IMPROVED,
    }
    worse = {Change.WORSE, Change.SLIGHTLY_WORSE}
    has_better = any(item in improved for item in meaningful)
    has_worse = any(item in worse for item in meaningful)
    if has_better and has_worse:
        overall = Change.MIXED
    elif has_worse:
        overall = Change.WORSE
    elif has_better:
        overall = Change.IMPROVED
    elif any(item.change is Change.UNCHANGED for item in items):
        overall = Change.UNCHANGED
    else:
        overall = Change.NOT_COMPARABLE
    return ComparisonGuidance(
        overall=overall,
        items=tuple(items),
        new_issues=new_issues,
        resolved_issues=resolved,
    )
