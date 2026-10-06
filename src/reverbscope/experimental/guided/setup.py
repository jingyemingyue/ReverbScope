"""Non-secret assistant choices. Keys stay in the credential vault."""

from __future__ import annotations

import os

from reverbscope.experimental.guided.catalog import normalize_language, ui_text
from reverbscope.experimental.guided.config import GuidedSettings
from reverbscope.experimental.guided.context import CloudContextBuilder
from reverbscope.experimental.guided.explain import CloudModelProvider, TestConnectionResult
from reverbscope.experimental.guided.privacy import (
    CredentialVault,
    HttpTransport,
    NetworkClient,
    NetworkPolicy,
    StoreChoice,
    StoreResult,
    process_vault,
)

PROVIDER_IDS: tuple[str, ...] = ("openai", "anthropic", "gemini", "openai_compatible")
ENGINE_IDS: tuple[str, ...] = ("builtin", "local", "cloud", "auto")

ASSISTANT_LABEL_KEYS: tuple[str, ...] = (
    "open_settings",
    "settings_title",
    "settings_hint",
    "engine",
    "engine_builtin",
    "engine_local",
    "engine_cloud",
    "engine_auto",
    "provider",
    "provider_openai",
    "provider_anthropic",
    "provider_gemini",
    "provider_openai_compatible",
    "model",
    "model_hint",
    "key",
    "key_hint",
    "replace",
    "remove",
    "test_connection",
    "reveal_confirm",
    "reveal",
    "hide",
    "base_url",
    "ack_endpoint",
    "cloud_enabled",
    "data_level",
    "level_minimal",
    "level_detailed",
    "length",
    "length_concise",
    "length_balanced",
    "length_detailed_choice",
    "expertise",
    "expertise_beginner",
    "expertise_intermediate",
    "expertise_expert",
    "consent_label",
    "consent_unset",
    "consent_once",
    "consent_always",
    "privacy",
    "offline",
    "lookup",
    "share_usage",
    "share_hardware",
    "share_crash",
    "preview",
    "save",
    "cancel",
    "key_empty",
    "key_not_stored",
    "key_stored_secure",
    "key_stored_session",
    "key_removed",
    "configured",
    "not_configured",
    "test_ok",
    "test_failed",
    "secure_unavailable",
    "secure_choice",
    "session_choice",
    "cancel_choice",
    "local_status",
    "packs_status",
    "key_missing",
    "store_title",
    "language_follow",
    "language_en",
    "language_zh",
    "language_label",
    "cost",
    "endpoint_warning",
)


def interface_language() -> str:
    from reverbscope.i18n import current_locale

    return normalize_language(current_locale())


def assistant_labels(language: str | None) -> dict[str, str]:
    return {key: ui_text(language, key) for key in ASSISTANT_LABEL_KEYS}


def resolve_api_key(provider_id: str, vault: CredentialVault | None = None) -> str:
    """Key for this process only. Never read from settings, never logged."""
    if not provider_id:
        return ""
    store = process_vault() if vault is None else vault
    found = store.get(provider_id)
    if found:
        return found
    return os.environ.get("REVERBSCOPE_API_KEY", "").strip()


def test_provider(
    settings: GuidedSettings,
    api_key: str,
    transport: HttpTransport | None = None,
) -> TestConnectionResult:
    """Explicit connection check. Privacy and offline still refuse the network."""
    if settings.privacy_mode or settings.offline:
        return TestConnectionResult(False, None, "privacy_or_offline")
    if not settings.provider_id or settings.provider_id not in PROVIDER_IDS:
        return TestConnectionResult(False, None, "provider not selected")
    policy = NetworkPolicy(allow_cloud_ai=True)
    client = NetworkClient(policy, transport)
    provider = CloudModelProvider(
        settings.provider_id,
        settings.model_id,
        api_key,
        client,
        base_url=settings.base_url,
        custom_acknowledged=settings.custom_endpoint_acknowledged,
    )
    return provider.test_connection()


def preview_without_measurement(settings: GuidedSettings, language: str) -> str:
    """Payload shape when no take is open. It contains no audio and no key."""
    return CloudContextBuilder().build((), settings, language=language).to_json()


def store_provider_key(
    provider_id: str,
    key: str,
    choice: StoreChoice,
    vault: CredentialVault | None = None,
) -> StoreResult:
    store = process_vault() if vault is None else vault
    return store.store(provider_id, key, choice)
