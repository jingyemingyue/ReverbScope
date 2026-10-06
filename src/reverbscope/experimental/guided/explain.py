"""Explanation providers. Guided mode never requires one of them to work.

Order of trust:

1. The diagnostic engine's finding.
2. The validator.
3. A provider sentence, or the built-in template if the provider fails.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, replace
from typing import Protocol

from reverbscope.experimental.guided.catalog import resolve_copy
from reverbscope.experimental.guided.compare import ComparisonGuidance
from reverbscope.experimental.guided.config import Consent, EngineChoice, GuidedSettings
from reverbscope.experimental.guided.context import (
    CloudContextBuilder,
    CloudPayload,
    validate_block,
)
from reverbscope.experimental.guided.findings import StructuredFinding
from reverbscope.experimental.guided.knowledge import LocalModelLibrary
from reverbscope.experimental.guided.privacy import (
    HttpTransport,
    NetworkClient,
    NetworkDeniedError,
    NetworkError,
    NetworkPolicy,
    Purpose,
)
from reverbscope.experimental.guided.prompt import SYSTEM_PROMPT

log = logging.getLogger("reverbscope.experimental.guided.explain")

FALLBACK_NOTICE = {
    "en": "Cloud explanation unavailable. Showing the built-in offline explanation instead.",
    "zh-CN": "云端说明不可用。以下改为内置离线说明。",
}


@dataclass(frozen=True)
class TokenUsage:
    input_tokens: int | None = None
    output_tokens: int | None = None

    def to_dict(self) -> dict[str, int | None]:
        return {"input_tokens": self.input_tokens, "output_tokens": self.output_tokens}


@dataclass(frozen=True)
class ExplanationBlock:
    finding_id: str
    explanation: str
    source: str
    accepted: bool = True
    rejected_reason: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "finding_id": self.finding_id,
            "explanation": self.explanation,
            "source": self.source,
            "accepted": self.accepted,
            "rejected_reason": self.rejected_reason,
        }


@dataclass
class ExplanationBundle:
    blocks: tuple[ExplanationBlock, ...]
    source: str
    source_label_key: str
    provider: str
    model: str
    notice: str = ""
    usage: TokenUsage | None = None
    preview: CloudPayload | None = None
    sent: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "source": self.source,
            "provider": self.provider,
            "model": self.model,
            "notice": self.notice,
            "sent": self.sent,
            "usage": None if self.usage is None else self.usage.to_dict(),
            "blocks": [block.to_dict() for block in self.blocks],
            "preview": None if self.preview is None else self.preview.body,
        }


@dataclass(frozen=True)
class ProviderCapabilities:
    text: bool = True
    structured_output: bool = False
    json_schema: bool = False
    multilingual: bool = True
    streaming: bool = False
    vision: bool = False


@dataclass(frozen=True)
class TestConnectionResult:
    ok: bool
    status: int | None
    message: str
    model: str = ""


class ExplanationProvider(Protocol):
    source: str

    def explain(
        self,
        findings: tuple[StructuredFinding, ...],
        *,
        language: str,
        comparison: ComparisonGuidance | None,
    ) -> tuple[ExplanationBlock, ...]: ...


class TemplateExplanationProvider:
    source = "template"

    def explain(
        self,
        findings: tuple[StructuredFinding, ...],
        *,
        language: str,
        comparison: ComparisonGuidance | None,
    ) -> tuple[ExplanationBlock, ...]:
        del comparison
        blocks: list[ExplanationBlock] = []
        for item in findings:
            copy = resolve_copy(item.type, language)
            text = " ".join((copy.copy.what, copy.copy.why, copy.copy.action, copy.copy.verify))
            blocks.append(ExplanationBlock(item.finding_id, text, self.source))
        return tuple(blocks)


class LocalModelExplanationProvider:
    """Optional on-device model. Unavailable models fall back to the template.

    No backend is bundled. A test or a future runtime can pass ``complete``,
    which must already speak the prompt contract. The default does nothing.
    """

    source = "local"

    def __init__(
        self,
        library: LocalModelLibrary | None = None,
        complete: ExplanationProvider | None = None,
    ) -> None:
        self.library = library if library is not None else LocalModelLibrary()
        self.complete = complete

    def available(self) -> bool:
        return self.library.available() and self.complete is not None

    def explain(
        self,
        findings: tuple[StructuredFinding, ...],
        *,
        language: str,
        comparison: ComparisonGuidance | None,
    ) -> tuple[ExplanationBlock, ...]:
        if not self.available() or self.complete is None:
            raise RuntimeError("local model is not installed")
        return self.complete.explain(findings, language=language, comparison=comparison)


@dataclass(frozen=True)
class ProviderSpec:
    provider_id: str
    default_base: str
    capabilities: ProviderCapabilities = field(default_factory=ProviderCapabilities)


PROVIDERS: dict[str, ProviderSpec] = {
    "openai": ProviderSpec("openai", "https://api.openai.com/v1"),
    "anthropic": ProviderSpec("anthropic", "https://api.anthropic.com"),
    "gemini": ProviderSpec("gemini", "https://generativelanguage.googleapis.com"),
    "openai_compatible": ProviderSpec("openai_compatible", ""),
}


def custom_endpoint_warning() -> str:
    return (
        "A custom endpoint may receive the data you choose to send. "
        "ReverbScope cannot guarantee the privacy practices of third-party servers."
    )


class CloudModelProvider:
    """Direct from this device to the provider the user chose.

    ReverbScope does not receive the key and does not proxy the request.
    """

    source = "cloud"

    def __init__(
        self,
        provider_id: str,
        model: str,
        api_key: str,
        client: NetworkClient,
        *,
        base_url: str = "",
        custom_acknowledged: bool = False,
    ) -> None:
        if provider_id not in PROVIDERS:
            raise ValueError(f"unknown provider {provider_id}")
        spec = PROVIDERS[provider_id]
        self.provider_id = provider_id
        self.model = model
        self.api_key = api_key
        self.client = client
        self.base_url = (base_url or spec.default_base).rstrip("/")
        self.custom = bool(base_url) and base_url.rstrip("/") != spec.default_base.rstrip("/")
        if provider_id == "openai_compatible":
            self.custom = True
        self.custom_acknowledged = custom_acknowledged

    def capabilities(self) -> ProviderCapabilities:
        return PROVIDERS[self.provider_id].capabilities

    def _guard_custom(self) -> None:
        if self.custom and not self.custom_acknowledged:
            raise PermissionError(custom_endpoint_warning())

    def test_connection(self) -> TestConnectionResult:
        """Smallest request that checks reachability. No measurement is sent."""
        self._guard_custom()
        if not self.model:
            return TestConnectionResult(False, None, "model not selected")
        if not self.api_key:
            return TestConnectionResult(False, None, "key not configured")
        url, headers, body = self._request_parts(
            "Reply with the single word OK.", include_measurement=False
        )
        try:
            response = self.client.request_json(Purpose.CLOUD_AI, "POST", url, headers, body, 20.0)
        except NetworkDeniedError as exc:
            return TestConnectionResult(False, None, exc.reason)
        except NetworkError as exc:
            return TestConnectionResult(False, exc.status, str(exc))
        return TestConnectionResult(True, response.status, "ok", self.model)

    def explain_raw(self, payload: CloudPayload) -> tuple[str, TokenUsage | None]:
        self._guard_custom()
        if not self.model:
            raise RuntimeError("model not selected")
        url, headers, body = self._request_parts(
            json.dumps(payload.body, ensure_ascii=False), include_measurement=True
        )
        response = self.client.request_json(Purpose.CLOUD_AI, "POST", url, headers, body, 60.0)
        text = _extract_text(response.body)
        return text, _extract_usage(response.body)

    def list_models_request(self) -> tuple[str, dict[str, str]]:
        """URL and headers for a model list. The caller decides whether to send it."""
        self._guard_custom()
        if self.provider_id in {"openai", "openai_compatible"}:
            return self.base_url + "/models", {"Authorization": f"Bearer {self.api_key}"}
        if self.provider_id == "anthropic":
            return self.base_url + "/v1/models", {
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
            }
        return (
            self.base_url + "/v1beta/models",
            {"x-goog-api-key": self.api_key},
        )

    def _request_parts(
        self, user_text: str, *, include_measurement: bool
    ) -> tuple[str, dict[str, str], dict[str, object]]:
        if include_measurement and any(
            token in user_text for token in ('"samples"', '"waveform"', '"audio"')
        ):
            raise PermissionError("measurement audio cannot be sent")
        if self.provider_id == "anthropic":
            return (
                self.base_url + "/v1/messages",
                {
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                {
                    "model": self.model,
                    "max_tokens": 800,
                    "system": SYSTEM_PROMPT,
                    "messages": [{"role": "user", "content": user_text}],
                },
            )
        if self.provider_id == "gemini":
            url = f"{self.base_url}/v1beta/models/{self.model}:generateContent"
            return (
                url,
                {"x-goog-api-key": self.api_key, "content-type": "application/json"},
                {
                    "contents": [{"parts": [{"text": SYSTEM_PROMPT + "\n" + user_text}]}],
                    "generationConfig": {"maxOutputTokens": 800, "temperature": 0},
                },
            )
        return (
            self.base_url + "/chat/completions",
            {
                "Authorization": f"Bearer {self.api_key}",
                "content-type": "application/json",
            },
            {
                "model": self.model,
                "temperature": 0,
                "max_tokens": 800,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_text},
                ],
            },
        )


def _extract_text(body: dict[str, object]) -> str:
    choices = body.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0]
        if isinstance(first, dict):
            message = first.get("message")
            if isinstance(message, dict) and isinstance(message.get("content"), str):
                return str(message["content"])
    content = body.get("content")
    if isinstance(content, list) and content:
        first = content[0]
        if isinstance(first, dict) and isinstance(first.get("text"), str):
            return str(first["text"])
    candidates = body.get("candidates")
    if isinstance(candidates, list) and candidates:
        first = candidates[0]
        if isinstance(first, dict):
            content_obj = first.get("content")
            if isinstance(content_obj, dict):
                parts = content_obj.get("parts")
                if isinstance(parts, list) and parts and isinstance(parts[0], dict):
                    text = parts[0].get("text")
                    if isinstance(text, str):
                        return text
    if isinstance(body.get("text"), str):
        return str(body["text"])
    return ""


def _extract_usage(body: dict[str, object]) -> TokenUsage | None:
    raw = body.get("usage")
    if not isinstance(raw, dict):
        raw = body.get("usageMetadata")
    if not isinstance(raw, dict):
        return None
    prompt = raw.get("prompt_tokens", raw.get("input_tokens", raw.get("promptTokenCount")))
    completion = raw.get(
        "completion_tokens", raw.get("output_tokens", raw.get("candidatesTokenCount"))
    )

    def _int(value: object) -> int | None:
        return value if isinstance(value, int) else None

    if _int(prompt) is None and _int(completion) is None:
        return None
    return TokenUsage(_int(prompt), _int(completion))


def select_engine(
    settings: GuidedSettings,
    *,
    privacy: bool,
    local_ready: bool,
) -> str:
    """Transparent. A better model is never a reason to leave the device."""
    forced_private = privacy or settings.privacy_mode or settings.offline
    choice = settings.explanation_engine
    if forced_private:
        if choice in {EngineChoice.LOCAL.value, EngineChoice.AUTO.value} and local_ready:
            return "local"
        return "template"
    if choice == EngineChoice.BUILTIN.value:
        return "template"
    if choice == EngineChoice.LOCAL.value:
        return "local" if local_ready else "template"
    cloud_ready = (
        settings.cloud_explanation_enabled
        and settings.cloud_consent in {Consent.ONCE.value, Consent.ALWAYS.value}
        and bool(settings.provider_id)
        and bool(settings.model_id)
    )
    if choice == EngineChoice.CLOUD.value:
        return "cloud" if cloud_ready else "template"
    if local_ready:
        return "local"
    if cloud_ready:
        return "cloud"
    return "template"


def _policy_from(settings: GuidedSettings, *, privacy: bool) -> NetworkPolicy:
    private = privacy or settings.privacy_mode
    return NetworkPolicy(
        privacy_mode=private,
        offline=settings.offline or private,
        allow_knowledge_lookup=settings.allow_knowledge_lookup and not private,
        allow_model_download=settings.allow_model_download and not private,
        allow_pack_download=settings.allow_pack_download and not private,
        allow_cloud_ai=settings.cloud_explanation_enabled and not private and not settings.offline,
        allow_update_check=settings.allow_update_check and not private,
        allow_telemetry=settings.allow_telemetry and settings.share_anonymous_usage and not private,
        allow_crash_report=(
            settings.allow_crash_report and settings.share_anonymous_crashes and not private
        ),
    )


def _parse_blocks(raw: str) -> dict[str, str]:
    try:
        loaded = json.loads(raw)
    except ValueError:
        return {}
    if not isinstance(loaded, dict):
        return {}
    blocks = loaded.get("blocks")
    if not isinstance(blocks, list):
        return {}
    found: dict[str, str] = {}
    for item in blocks:
        if not isinstance(item, dict):
            continue
        finding_id = item.get("finding_id")
        explanation = item.get("explanation")
        if isinstance(finding_id, str) and isinstance(explanation, str):
            found[finding_id] = explanation
    return found


def explain_findings(
    findings: tuple[StructuredFinding, ...],
    settings: GuidedSettings,
    *,
    language: str,
    comparison: ComparisonGuidance | None = None,
    privacy: bool = False,
    api_key: str = "",
    library: LocalModelLibrary | None = None,
    local_complete: ExplanationProvider | None = None,
    transport: HttpTransport | None = None,
    consent_override: str | None = None,
    bands: tuple[tuple[float, float | None, str], ...] = (),
) -> ExplanationBundle:
    """Pick a provider, validate anything it returns, and fall back offline."""
    if consent_override:
        settings = replace(settings, cloud_consent=consent_override)
    local = LocalModelExplanationProvider(library, local_complete)
    engine = select_engine(settings, privacy=privacy, local_ready=local.available())
    template = TemplateExplanationProvider()
    offline_blocks = template.explain(findings, language=language, comparison=comparison)
    builder = CloudContextBuilder()
    preview = builder.build(
        findings, settings, language=language, comparison=comparison, bands=bands
    )
    if not findings:
        return ExplanationBundle((), "template", "builtin", "", "", preview=preview)
    notice = ""
    if (
        (privacy or settings.privacy_mode)
        and engine == "template"
        and settings.explanation_engine == EngineChoice.CLOUD.value
    ):
        notice = "privacy_mode"
    if engine == "local":
        try:
            blocks = local.explain(findings, language=language, comparison=comparison)
        except Exception:
            log.info("local explanation failed; using template")
            return ExplanationBundle(
                offline_blocks,
                "template",
                "builtin",
                "",
                "",
                notice="local_unavailable",
                preview=preview,
            )
        checked = _validate_all(findings, blocks, comparison, language)
        model_id = "" if library is None or library.manifest is None else library.manifest.model_id
        return ExplanationBundle(checked, "local", "local", "local", model_id, preview=preview)
    if engine != "cloud":
        if (
            settings.explanation_engine == EngineChoice.LOCAL.value
            and not local.available()
            and not notice
        ):
            notice = "local_unavailable"
        if (
            settings.explanation_engine == EngineChoice.CLOUD.value
            and not notice
            and settings.cloud_consent == Consent.UNSET.value
        ):
            notice = "consent_required"
        return ExplanationBundle(
            offline_blocks, "template", "builtin", "", "", notice=notice, preview=preview
        )
    policy = _policy_from(settings, privacy=privacy)
    client = NetworkClient(policy, transport)
    provider = CloudModelProvider(
        settings.provider_id or "openai",
        settings.model_id,
        api_key,
        client,
        base_url=settings.base_url,
        custom_acknowledged=settings.custom_endpoint_acknowledged,
    )
    if not api_key.strip():
        log.info("cloud explanation skipped because no key is configured")
        return ExplanationBundle(
            offline_blocks,
            "template",
            "builtin",
            provider.provider_id,
            provider.model,
            notice="key_missing",
            preview=preview,
            sent=False,
        )
    try:
        raw, usage = provider.explain_raw(preview)
        parsed = _parse_blocks(raw)
        if not parsed:
            raise RuntimeError("malformed provider response")
        raw_blocks = [
            ExplanationBlock(item.finding_id, parsed.get(item.finding_id, ""), "cloud")
            for item in findings
            if item.finding_id in parsed
        ]
        if len(raw_blocks) != len(findings):
            raise RuntimeError("provider omitted a finding")
        checked = _validate_all(findings, tuple(raw_blocks), comparison, language)
        return ExplanationBundle(
            checked,
            "cloud",
            "cloud",
            provider.provider_id,
            provider.model,
            usage=usage,
            preview=preview,
            sent=True,
        )
    except (NetworkError, NetworkDeniedError, RuntimeError, PermissionError, ValueError) as exc:
        log.info("cloud explanation fell back status_class=%s", type(exc).__name__)
        return ExplanationBundle(
            offline_blocks,
            "template",
            "builtin",
            provider.provider_id,
            provider.model,
            notice="cloud_unavailable",
            preview=preview,
            sent=False,
        )


def _validate_all(
    findings: tuple[StructuredFinding, ...],
    blocks: tuple[ExplanationBlock, ...],
    comparison: ComparisonGuidance | None,
    language: str,
) -> tuple[ExplanationBlock, ...]:
    by_id = {item.finding_id: item for item in findings}
    template = {
        block.finding_id: block
        for block in TemplateExplanationProvider().explain(
            findings, language=language, comparison=comparison
        )
    }
    checked: list[ExplanationBlock] = []
    for block in blocks:
        finding = by_id.get(block.finding_id)
        if finding is None or not block.explanation:
            replacement = template[block.finding_id]
            checked.append(
                ExplanationBlock(
                    block.finding_id,
                    replacement.explanation,
                    "template",
                    accepted=False,
                    rejected_reason="missing",
                )
            )
            continue
        result = validate_block(block.explanation, finding, comparison=comparison)
        if result.accepted:
            checked.append(block)
            continue
        replacement = template[block.finding_id]
        checked.append(
            ExplanationBlock(
                block.finding_id,
                replacement.explanation,
                "template",
                accepted=False,
                rejected_reason=result.reason,
            )
        )
    return tuple(checked)
