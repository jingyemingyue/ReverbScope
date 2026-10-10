"""The interface state kept between runs: ``ui.ini`` in the ReverbScope home folder.

Window geometry, splitter sizes, the current view and, per project, the
current entry, the overlays and the baseline (docs/design/GUI_2_ARCHITECTURE.md
§8). Nothing here is needed to open a session or a project: a missing or
unreadable key falls back to the default, and a file that cannot be written
only loses the layout.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

from PySide6.QtCore import QByteArray, QSettings

from reverbscope.io.recent import reverbscope_home

log = logging.getLogger(__name__)

UI_FILE = "ui.ini"


def settings() -> QSettings:
    return QSettings(str(reverbscope_home() / UI_FILE), QSettings.Format.IniFormat)


def project_key(path: Path) -> str:
    """``project/<sha1>``: the folder's resolved path, hashed (paths make poor INI keys)."""
    digest = hashlib.sha1(str(path.resolve()).encode("utf-8"), usedforsecurity=False)
    return f"project/{digest.hexdigest()}"


def read_bytes(name: str) -> QByteArray | None:
    value = settings().value(name)
    return value if isinstance(value, QByteArray) and not value.isEmpty() else None


def read_text(name: str, default: str = "") -> str:
    value = settings().value(name, default)
    return value if isinstance(value, str) else default


def write(name: str, value: Any) -> None:
    store = settings()
    store.setValue(name, value)
    store.sync()
    if store.status() != QSettings.Status.NoError:
        log.info("could not write %s to %s", name, store.fileName())


def read_selection(project: Path) -> dict[str, Any] | None:
    """The selection saved for ``project``, or ``None``."""
    text = read_text(f"{project_key(project)}/selection")
    if not text:
        return None
    try:
        value = json.loads(text)
    except ValueError:
        return None
    if not isinstance(value, dict):
        return None
    overlay = value.get("overlay")
    return {
        "current": str(value.get("current") or ""),
        "overlay": [str(k) for k in overlay] if isinstance(overlay, list) else [],
        "baseline": str(value.get("baseline") or ""),
    }


def write_selection(project: Path, selection: dict[str, Any]) -> None:
    write(f"{project_key(project)}/selection", json.dumps(selection, ensure_ascii=False))
