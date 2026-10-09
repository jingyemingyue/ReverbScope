"""User settings stored under ``$REVERBSCOPE_HOME/settings.json``.

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

from reverbscope.errors import SessionError
from reverbscope.i18n import _
from reverbscope.io.jsonutil import make_folder, read_json_object, write_text_atomic
from reverbscope.io.recent import reverbscope_home
from reverbscope.models.loadutil import drop_unknown, read_schema_version

log = logging.getLogger("reverbscope.settings")

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
    #: Show the developer tools in an installed (user-edition) ReverbScope.
    developer_tools: bool = False
    #: How the command line frames its reports: "" (auto), "boxed" or "plain".
    cli_style: str = ""
    #: The first-measurement card on the Home page was dismissed.
    walkthrough_dismissed: bool = False

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
        if payload.get("cli_style") not in (None, "", "boxed", "plain"):
            payload["cli_style"] = ""
        return cls(**payload)


def settings_path() -> Path:
    return reverbscope_home() / SETTINGS_FILENAME


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


def read_settings() -> UserSettings:
    """The stored settings; an existing file that cannot be read is an error.

    :func:`load_settings` falls back to the defaults so that a damaged file
    never stops a measurement. A command that changes one setting must not
    write the defaults over the others instead (``reverbscope config``).
    """
    path = settings_path()
    if not path.exists():
        return UserSettings()
    return UserSettings.from_dict(read_json_object(path, kind="settings"))


def save_settings(settings: UserSettings) -> Path:
    """Write ``settings.json``. Never stores a level acknowledgement."""
    path = settings_path()
    make_folder(path.parent)
    payload = settings.to_dict()
    payload.pop("acknowledge_level", None)
    try:
        # A settings.json kept as a link (a dotfiles folder) stays a link.
        write_text_atomic(path, json.dumps(payload, indent=2) + "\n", follow_symlinks=True)
    except OSError as exc:
        raise SessionError(_("cannot write {path}: {error}").format(path=path, error=exc)) from exc
    return path
