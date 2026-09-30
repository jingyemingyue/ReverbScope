"""Developer tools on or off, and which download this is (docs/EDITIONS.md).

One code base, two defaults:

* **developer** — a source checkout or a ``pip`` install: debugging tools are
  on (the GUI's Developer menu with the audio-device inspector and the
  environment report, advanced stream options in Standalone Mode). Developers
  extend RoomScope through its entry points (``roomscope.exporters``) and the
  Python API.
* **user** — the desktop bundles and installers: the same measurement, with
  the everyday settings only (language, theme, default profile, backend).

``ROOMSCOPE_EDITION=developer|user`` overrides the default, and a user can
switch the developer tools on in Settings.

Separately, a release bundle is one of two downloads (:func:`package`): the
**Desktop Edition** (GUI and command line) or the **Terminal Edition**
(command line only, built without Qt). ``packaging/roomscope.spec`` writes
which one into ``build_info.json``.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ENV_EDITION = "ROOMSCOPE_EDITION"
DEVELOPER = "developer"
USER = "user"


def edition() -> str:
    """``developer`` or ``user`` for this process."""
    forced = os.environ.get(ENV_EDITION, "").strip().lower()
    if forced in {DEVELOPER, USER}:
        return forced
    try:
        from roomscope.settings import load_settings

        if load_settings().developer_tools:
            return DEVELOPER
    except Exception:
        pass
    return USER if getattr(sys, "frozen", False) else DEVELOPER


def is_developer() -> bool:
    return edition() == DEVELOPER


#: The two downloads (``build_info.json`` ``"package"``).
DESKTOP_PACKAGE = "desktop"
TERMINAL_PACKAGE = "terminal"
#: Where both editions are downloaded.
RELEASES_URL = "https://github.com/jingyemingyue/RoomScope/releases"


def package(build_info: Path | None = None) -> str | None:
    """``desktop`` or ``terminal`` for a release bundle; ``None`` for a source or pip install."""
    path = build_info or Path(__file__).resolve().parent / "build_info.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    found = data.get("package") if isinstance(data, dict) else None
    return found if found in (DESKTOP_PACKAGE, TERMINAL_PACKAGE) else None


def is_terminal_package() -> bool:
    """True in the Terminal Edition, which has no GUI."""
    return package() == TERMINAL_PACKAGE
