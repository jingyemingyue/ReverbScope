"""Recently opened or saved session directories.

Paths are stored under ``$ROOMSCOPE_HOME/recent_sessions.json``
(``~/.roomscope`` by default). Missing directories are dropped on read.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from roomscope.errors import SessionError
from roomscope.io.jsonutil import read_json_object, write_text_atomic

log = logging.getLogger(__name__)

RECENT_LIMIT = 12
RECENT_FILENAME = "recent_sessions.json"


def roomscope_home() -> Path:
    override = os.environ.get("ROOMSCOPE_HOME")
    if override:
        return Path(override)
    return Path.home() / ".roomscope"


def recent_store_path() -> Path:
    return roomscope_home() / RECENT_FILENAME


def remember_session(directory: str | Path) -> None:
    """Put ``directory`` at the front of the recent list."""
    path = Path(directory).resolve()
    if path.is_file() and path.name == "session.json":
        path = path.parent
    entries = [str(path)]
    for existing in _read_paths():
        if existing != path:
            entries.append(str(existing))
    store = recent_store_path()
    try:
        store.parent.mkdir(parents=True, exist_ok=True)
        write_text_atomic(
            store,
            json.dumps({"sessions": entries[:RECENT_LIMIT]}, indent=2),
            follow_symlinks=True,
        )
    except OSError as exc:
        # The list is a convenience: the session itself was saved already.
        log.warning("cannot update the recent-sessions list %s: %s", store, exc)


def recent_session_paths(*, limit: int = RECENT_LIMIT) -> list[Path]:
    """Existing session directories, newest first."""
    found: list[Path] = []
    for path in _read_paths():
        if _looks_like_session(path):
            found.append(path)
        if len(found) >= limit:
            break
    return found


def _read_paths() -> list[Path]:
    store = recent_store_path()
    if not store.is_file():
        return []
    try:
        payload = read_json_object(store, kind="recent sessions")
    except SessionError:
        return []
    raw = payload.get("sessions")
    if not isinstance(raw, list):
        return []
    return [Path(item) for item in raw if isinstance(item, str)]


def _looks_like_session(path: Path) -> bool:
    if path.is_dir():
        return (path / "session.json").is_file()
    return path.is_file() and path.name == "session.json"
