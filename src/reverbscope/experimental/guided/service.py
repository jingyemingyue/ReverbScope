"""One entry point for the guided loop: measure result in, guidance out."""

from __future__ import annotations

import os
import platform
from dataclasses import dataclass, replace
from typing import Any

from reverbscope.experimental.guided.compare import ComparisonGuidance, compare_guidance
from reverbscope.experimental.guided.config import GuidedSettings, load_guided_settings
from reverbscope.experimental.guided.context import assert_no_secret
from reverbscope.experimental.guided.engine import diagnose
from reverbscope.experimental.guided.explain import (
    ExplanationBundle,
    ExplanationProvider,
    explain_findings,
)
from reverbscope.experimental.guided.findings import StructuredFinding
from reverbscope.experimental.guided.knowledge import LocalModelLibrary
from reverbscope.experimental.guided.planner import RecommendationPlan, plan_recommendations
from reverbscope.experimental.guided.privacy import HttpTransport
from reverbscope.experimental.guided.report import render_json, render_text
from reverbscope.experimental.guided.snapshot import MeasurementSnapshot, snapshot_from_result
from reverbscope.i18n import current_locale
from reverbscope.models.result import AnalysisResult
from reverbscope.version import __version__


def language_from_settings(settings: GuidedSettings, override: str | None = None) -> str:
    from reverbscope.experimental.guided.catalog import normalize_language

    if override:
        return normalize_language(override)
    if settings.language:
        return normalize_language(settings.language)
    locale = current_locale()
    return "zh-CN" if locale.lower().startswith("zh") else "en"


@dataclass(frozen=True)
class GuidedReport:
    snapshot: MeasurementSnapshot
    findings: tuple[StructuredFinding, ...]
    plan: RecommendationPlan
    bundle: ExplanationBundle
    comparison: ComparisonGuidance | None
    language: str
    experimental: bool = True
    stable_feature: bool = False

    def text(self) -> str:
        return render_text(
            self.findings,
            self.plan,
            self.bundle,
            language=self.language,
            comparison=self.comparison,
        )

    def json(self, *, include_preview: bool = False) -> str:
        return render_json(
            self.findings,
            self.plan,
            self.bundle,
            language=self.language,
            comparison=self.comparison,
            include_preview=include_preview,
        )


def run_guided(
    result: AnalysisResult,
    *,
    settings: GuidedSettings | None = None,
    other: AnalysisResult | None = None,
    language: str | None = None,
    expertise: str | None = None,
    privacy: bool | None = None,
    api_key: str = "",
    library: LocalModelLibrary | None = None,
    local_complete: ExplanationProvider | None = None,
    transport: HttpTransport | None = None,
    consent_override: str | None = None,
) -> GuidedReport:
    """Diagnose, plan, and explain. Measurement numbers are not recomputed here."""
    chosen = settings if settings is not None else load_guided_settings()
    if expertise:
        chosen = replace(chosen, expertise=expertise)
    private = _privacy_enabled() if privacy is None else privacy
    snap = snapshot_from_result(result)
    findings = diagnose(snap)
    level = expertise or chosen.expertise
    plan = plan_recommendations(findings, level)
    comparison = None
    if other is not None:
        other_snap = snapshot_from_result(other)
        other_findings = diagnose(other_snap)
        comparison = compare_guidance(snap, other_snap, findings, other_findings)
    lang = language_from_settings(chosen, language)
    bands = tuple((band.center_hz, band.rt60_s, band.t30_validity) for band in snap.bands)
    bundle = explain_findings(
        plan.visible,
        chosen,
        language=lang,
        comparison=comparison,
        privacy=private,
        api_key=api_key,
        library=library,
        local_complete=local_complete,
        transport=transport,
        consent_override=consent_override,
        bands=bands,
    )
    return GuidedReport(snap, findings, plan, bundle, comparison, lang)


def _privacy_enabled() -> bool:
    return os.environ.get("REVERBSCOPE_PRIVACY_MODE", "").strip() in {"1", "true", "yes"}


def improvement_payload(
    settings: GuidedSettings,
    report: GuidedReport,
    *,
    secret: str = "",
) -> dict[str, Any] | None:
    """Opt-in summary. Empty unless the user turned a share flag on."""
    if settings.privacy_mode or _privacy_enabled():
        return None
    usage = settings.share_anonymous_usage
    hardware = settings.share_hardware_compatibility
    crashes = settings.share_anonymous_crashes
    if not (usage or hardware or crashes):
        return None
    payload: dict[str, Any] = {"schema": "reverbscope.improvement.v1"}
    if usage:
        payload["usage"] = {
            "version": __version__,
            "os_family": platform.system(),
            "architecture": platform.machine(),
            "locale": report.language,
            "finding_types": [item.type.value for item in report.findings],
            "validity": [item.validity.value for item in report.findings],
        }
    if hardware:
        payload["hardware"] = {
            "generic_model": settings.generic_device_model,
            "sample_rate_hz": report.snapshot.sample_rate_hz,
        }
    if crashes:
        payload["crash"] = {"included": False}
    assert_no_secret(payload, secret)
    return payload
