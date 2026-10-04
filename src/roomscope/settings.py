"""User settings stored under ``$ROOMSCOPE_HOME/settings.json``.

Plain JSON written by this module so the CLI does not depend on Qt and no
configuration library is added (ARCHITECTURE_V1.md §5.10). Level
acknowledgements are never persisted.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any

from roomscope.errors import SessionError
from roomscope.i18n import _
from roomscope.io.jsonutil import read_json_object, write_text_atomic
from roomscope.io.recent import roomscope_home
from roomscope.models.loadutil import drop_unknown, read_schema_version

log = logging.getLogger("roomscope.settings")

SETTINGS_FILENAME = "settings.json"
SETTINGS_SCHEMA_VERSION = 1


@dataclass
class UserSettings:
    """Preferences that apply across sessions.

    ``language`` and ``audio_backend`` empty means "follow the environment /
    system default". ``copy_recording`` defaults to True (the GUI default).
    """

    schema_version: int = SETTINGS_SCHEMA_VERSION
    language: str = ""
    default_profile: str = "generic"
    audio_backend: str = ""
    output_dir: str = ""
    copy_recording: bool = True
    #: "" follows the system, or "light" / "dark".
    theme: str = ""
    #: Show the developer tools in an installed (user-edition) RoomScope.
    developer_tools: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> UserSettings:
        if not isinstance(data, dict):
            raise SessionError(_("settings data must be a JSON object"))
        version = read_schema_version(data, SETTINGS_SCHEMA_VERSION, "settings")
        payload = drop_unknown(data, {f.name for f in fields(cls)}, kind="settings")
        payload["schema_version"] = version
        defaults = cls()
        for item in fields(cls):
            if item.name == "schema_version" or item.name not in payload:
                continue
            expected = type(getattr(defaults, item.name))
            if not isinstance(payload[item.name], expected):
                # A hand-edited file: "false" must not read as True, and a
                # number for the language must not stop every command.
                log.info("ignoring settings field %s: not a %s", item.name, expected.__name__)
                del payload[item.name]
        if payload.get("theme") not in (None, "", "light", "dark"):
            payload["theme"] = ""
        return cls(**payload)


def settings_path() -> Path:
    return roomscope_home() / SETTINGS_FILENAME


def load_settings() -> UserSettings:
    """Read settings, or the defaults when the file is missing or unreadable."""
    path = settings_path()
    if not path.is_file():
        return UserSettings()
    try:
        payload = read_json_object(path, kind="settings")
    except SessionError as exc:
        log.info("ignoring unreadable settings file %s: %s", path, exc)
        return UserSettings()
    try:
        return UserSettings.from_dict(payload)
    except SessionError as exc:
        log.info("ignoring settings file %s: %s", path, exc)
        return UserSettings()


def save_settings(settings: UserSettings) -> Path:
    """Write ``settings.json``. Never stores a level acknowledgement."""
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = settings.to_dict()
    payload.pop("acknowledge_level", None)
    try:
        # A settings.json kept as a link (a dotfiles folder) stays a link.
        write_text_atomic(path, json.dumps(payload, indent=2) + "\n", follow_symlinks=True)
    except OSError as exc:
        raise SessionError(_("cannot write {path}: {error}").format(path=path, error=exc)) from exc
    return path
