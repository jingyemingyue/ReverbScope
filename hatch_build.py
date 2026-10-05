"""Hatch hook: compile gettext ``.po`` catalogs to ``.mo`` for the wheel.

The ``.mo`` files are written to a temporary directory, never into the source
tree, and are force-included next to their ``.po`` in the wheel
(``reverbscope/locale/<lang>/LC_MESSAGES/reverbscope.mo``). ``*.mo`` is
git-ignored and hatchling honours VCS ignores, so a ``.mo`` lying in the
source tree would not reach the wheel anyway. Each ``.mo`` records the SHA-256
of the ``.po`` it was compiled from; ``reverbscope.i18n`` uses it only while it
still matches. The sdist ships the ``.po`` only.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

from hatchling.builders.hooks.plugin.interface import BuildHookInterface

_SRC = Path(__file__).resolve().parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


def compiled_catalogs(out_dir: Path) -> dict[str, str]:
    """Compile the catalogs into ``out_dir``; return the wheel force-include map."""
    from reverbscope.i18n import compile_catalogs

    locale_dir = _SRC / "reverbscope" / "locale"
    include: dict[str, str] = {}
    for mo in compile_catalogs(locale_dir, out_dir):
        relative = mo.relative_to(out_dir).as_posix()
        include[str(mo)] = f"reverbscope/locale/{relative}"
    return include


class CustomBuildHook(BuildHookInterface):
    _out_dir: Path | None = None

    def initialize(self, _version: str, build_data: dict[str, object]) -> None:
        if self.target_name != "wheel":
            return
        self._out_dir = Path(tempfile.mkdtemp(prefix="reverbscope-mo-"))
        force_include = build_data.setdefault("force_include", {})
        assert isinstance(force_include, dict)
        force_include.update(compiled_catalogs(self._out_dir))

    def finalize(self, _version: str, _build_data: dict[str, object], _artifact: str) -> None:
        if self._out_dir is not None:
            shutil.rmtree(self._out_dir, ignore_errors=True)
            self._out_dir = None
