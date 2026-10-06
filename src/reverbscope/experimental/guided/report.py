"""Text and JSON reports. Numbers are inserted here, not by a model."""

from __future__ import annotations

import json
from typing import Any

from reverbscope.experimental import TRACK
from reverbscope.experimental.guided.catalog import (
    evidence_label,
    resolve_copy,
    ui_text,
)
from reverbscope.experimental.guided.compare import Change, ComparisonGuidance
from reverbscope.experimental.guided.explain import FALLBACK_NOTICE, ExplanationBundle
from reverbscope.experimental.guided.findings import (
    EvidenceValue,
    FindingType,
    StructuredFinding,
)
from reverbscope.experimental.guided.planner import Expertise, RecommendationPlan


def _format_value(language: str, value: float | int | str | None, unit: str) -> str:
    if value is None:
        return "—"
    if isinstance(value, str):
        shown = _TOKEN.get(language, {}).get(value, value)
    elif isinstance(value, float):
        shown = f"{value:.1f}"
    else:
        shown = str(value)
    if not unit or unit == "1":
        return shown
    return f"{shown} {unit}"


_TOKEN = {
    "zh-CN": {"high": "高", "medium": "中", "low": "低", "valid": "有效", "invalid": "无效"},
}


def _evidence_lines(language: str, evidence: tuple[EvidenceValue, ...]) -> list[str]:
    lines = []
    for item in evidence:
        if item.value is None:
            continue
        label = evidence_label(language, item.key)
        lines.append(f"{label}: {_format_value(language, item.value, item.unit)}")
    return lines


def _source_label(language: str, bundle: ExplanationBundle) -> str:
    label = ui_text(language, bundle.source_label_key)
    if bundle.source == "cloud" and bundle.model:
        return f"{label} · {bundle.provider}/{bundle.model}"
    return label


def _notice(language: str, bundle: ExplanationBundle) -> str:
    if bundle.notice == "cloud_unavailable":
        if language == "zh-CN":
            return FALLBACK_NOTICE["zh-CN"]
        return FALLBACK_NOTICE["en"]
    if bundle.notice == "privacy_mode":
        return ui_text(language, "privacy_cloud")
    if bundle.notice == "consent_required":
        return ui_text(language, "consent")
    if bundle.notice == "key_missing":
        return ui_text(language, "key_missing")
    if bundle.notice == "local_unavailable":
        if language == "zh-CN":
            return "本地模型不可用。以下改为内置离线说明。"
        return "Local model unavailable. Showing the built-in offline explanation instead."
    return ""


def render_text(
    findings: tuple[StructuredFinding, ...],
    plan: RecommendationPlan,
    bundle: ExplanationBundle,
    *,
    language: str,
    comparison: ComparisonGuidance | None = None,
) -> str:
    known = {item.finding_id: item for item in findings}
    by_id = {block.finding_id: block for block in bundle.blocks}
    lines = [
        f"{ui_text(language, 'badge')}  ·  {ui_text(language, 'title')}",
        f"{ui_text(language, 'source')}: {_source_label(language, bundle)}",
    ]
    notice = _notice(language, bundle)
    if notice:
        lines.append(notice)
    if comparison is not None:
        lines.append("")
        lines.append(ui_text(language, "compare"))
        lines.append(ui_text(language, comparison.overall.value))
        lines.append(ui_text(language, "no_score"))
        for change in comparison.items:
            if change.change is Change.NOT_COMPARABLE:
                continue
            label = ui_text(language, change.change.value)
            if change.finding_type:
                topic = resolve_copy(_as_finding_type(change.finding_type), language).copy.title
            else:
                topic = (
                    ui_text(language, change.topic)
                    if change.topic
                    in {
                        "improved",
                        "worse",
                        "unchanged",
                        "mixed",
                    }
                    else change.topic
                )
            if change.topic == "new_issue":
                topic = f"{ui_text(language, 'new_issue')}: {topic}"
            lines.append(f"{topic}: {label}")
    lines.append("")
    visible = plan.visible
    if not visible:
        lines.append(ui_text(language, "none"))
        return "\n".join(lines).rstrip() + "\n"
    show_evidence = plan.expertise is not Expertise.BEGINNER
    for shown in visible:
        finding = known.get(shown.finding_id, shown)
        copy = resolve_copy(finding.type, language)
        if copy.notice:
            lines.append(copy.notice)
        lines.append(ui_text(language, "next") if finding is plan.next_best else copy.copy.title)
        lines.append(copy.copy.title)
        lines.append("")
        lines.append(ui_text(language, "what"))
        lines.append(copy.copy.what)
        lines.append("")
        lines.append(ui_text(language, "why"))
        lines.append(copy.copy.why)
        lines.append("")
        lines.append(ui_text(language, "impact"))
        lines.append(copy.copy.impact)
        lines.append("")
        lines.append(ui_text(language, "causes"))
        for cause in copy.copy.causes:
            lines.append(f"- {cause}")
        lines.append("")
        lines.append(ui_text(language, "action"))
        lines.append(copy.copy.action)
        lines.append("")
        lines.append(ui_text(language, "verify"))
        lines.append(copy.copy.verify)
        block = by_id.get(finding.finding_id)
        if block is not None and block.source != "template":
            lines.append("")
            lines.append(block.explanation)
        if show_evidence or finding.evidence:
            lines.append("")
            lines.append(ui_text(language, "evidence"))
            lines.extend(_evidence_lines(language, finding.evidence))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _as_finding_type(name: str) -> FindingType:
    try:
        return FindingType(name)
    except ValueError:
        return FindingType.STRONG_EARLY_REFLECTION


def render_json(
    findings: tuple[StructuredFinding, ...],
    plan: RecommendationPlan,
    bundle: ExplanationBundle,
    *,
    language: str,
    comparison: ComparisonGuidance | None = None,
    include_preview: bool = False,
) -> str:
    payload: dict[str, Any] = {
        "experimental": True,
        "track": TRACK,
        "stable_feature": False,
        "language": language,
        "source": bundle.source,
        "provider": bundle.provider,
        "model": bundle.model,
        "notice": _notice(language, bundle),
        "findings": [item.to_dict() for item in findings],
        "plan": plan.to_dict(),
        "explanation": bundle.to_dict(),
        "comparison": None if comparison is None else comparison.to_dict(),
    }
    if not include_preview:
        explanation = payload["explanation"]
        if isinstance(explanation, dict):
            explanation.pop("preview", None)
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
