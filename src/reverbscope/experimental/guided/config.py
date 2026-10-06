"""Guided settings. Credentials are never fields of this object."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, fields
from enum import StrEnum
from pathlib import Path
from typing import Any

from reverbscope.io.recent import reverbscope_home

log = logging.getLogger("reverbscope.experimental.guided")

SETTINGS_NAME = "guided_settings.json"
_SECRET_FIELDS = frozenset(
    {
        "api_key",
        "apikey",
        "token",
        "authorization",
        "secret",
        "password",
        "credential",
        "credentials",
    }
)


class EngineChoice(StrEnum):
    BUILTIN = "builtin"
    LOCAL = "local"
    CLOUD = "cloud"
    AUTO = "auto"


class DataLevel(StrEnum):
    MINIMAL = "minimal"
    DETAILED = "detailed"


class LengthChoice(StrEnum):
    CONCISE = "concise"
    BALANCED = "balanced"
    DETAILED = "detailed"


class Consent(StrEnum):
    UNSET = "unset"
    ONCE = "once"
    ALWAYS = "always"


@dataclass
class GuidedSettings:
    """Non-secret preferences. An API key must not be added here."""

    schema_version: int = 1
    explanation_engine: str = EngineChoice.BUILTIN.value
    privacy_mode: bool = False
    offline: bool = False
    language: str = ""
    expertise: str = "beginner"
    length: str = LengthChoice.BALANCED.value
    provider_id: str = ""
    model_id: str = ""
    base_url: str = ""
    custom_endpoint_acknowledged: bool = False
    cloud_explanation_enabled: bool = False
    cloud_consent: str = Consent.UNSET.value
    data_level: str = DataLevel.MINIMAL.value
    allow_knowledge_lookup: bool = False
    allow_model_download: bool = False
    allow_pack_download: bool = False
    allow_update_check: bool = False
    allow_telemetry: bool = False
    allow_crash_report: bool = False
    share_anonymous_usage: bool = False
    share_hardware_compatibility: bool = False
    share_anonymous_crashes: bool = False
    generic_device_model: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        for name in _SECRET_FIELDS:
            payload.pop(name, None)
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GuidedSettings:
        known = {item.name for item in fields(cls)}
        leaked = _SECRET_FIELDS.intersection(data)
        if leaked:
            log.warning(
                "guided settings contained credential fields %s; they were ignored",
                ",".join(sorted(leaked)),
            )
        payload = {key: value for key, value in data.items() if key in known}
        return cls(**payload)


def settings_path() -> Path:
    return reverbscope_home() / SETTINGS_NAME


def load_guided_settings() -> GuidedSettings:
    path = settings_path()
    if not path.is_file():
        return GuidedSettings()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        log.info("ignoring unreadable guided settings")
        return GuidedSettings()
    if not isinstance(raw, dict):
        return GuidedSettings()
    try:
        return GuidedSettings.from_dict(raw)
    except TypeError:
        log.info("ignoring guided settings that do not match the schema")
        return GuidedSettings()


def save_guided_settings(settings: GuidedSettings) -> Path:
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(settings.to_dict(), indent=2) + "\n", encoding="utf-8")
    return path


def export_settings(settings: GuidedSettings) -> dict[str, Any]:
    """Settings a user may copy to another machine. Credentials are absent."""
    payload = settings.to_dict()
    for name in list(payload):
        if name in _SECRET_FIELDS or "key" in name or "token" in name:
            payload.pop(name, None)
    payload["credentials_included"] = False
    return payload


CREDENTIALS_NOT_INCLUDED = (
    "AI provider credentials were not included. Enter your key on this device if needed."
)
