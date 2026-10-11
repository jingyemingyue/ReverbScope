"""scripts/render_readme_assets.py shows the README reader the app they download."""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

pytestmark = [pytest.mark.gui, pytest.mark.slow]

ROOT = Path(__file__).resolve().parents[2]


def _script() -> Any:
    path = ROOT / "scripts" / "render_readme_assets.py"
    spec = importlib.util.spec_from_file_location("render_readme_assets", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_gui_screenshots_are_the_user_edition_and_chinese_for_the_chinese_readme(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The screenshots must show the user edition (no Developer menu), the
    Chinese window for README.zh-CN.md, and in each language the names that
    language's demo run wrote. Every window shows the synthetic marker."""
    from reverbscope.demo import run_demo
    from reverbscope.i18n import activate, current_locale
    from reverbscope.ui import workbench

    QApplication.instance() or QApplication([])
    monkeypatch.setenv("REVERBSCOPE_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("REVERBSCOPE_AUDIO_BACKEND", "fake")
    # A source checkout is the developer edition; the script must not inherit it.
    monkeypatch.setenv("REVERBSCOPE_EDITION", "developer")
    script = _script()
    try:
        for lang in ("en", "zh_CN"):
            activate(lang)
            run_demo(script.demo_folder(tmp_path, lang) / "reverbscope-demo")
    finally:
        activate("en")
    grabbed: list[tuple[str, bool, str, int, bool]] = []
    names: list[str] = []
    homes: list[str] = []

    class Recorded(workbench.WorkbenchWindow):  # type: ignore[misc]
        def grab(self, *args: Any) -> Any:
            kind = self.panels[0].kind()
            selected = self.document.selected()
            assert selected is not None and selected.synthetic
            grabbed.append(
                (
                    current_locale(),
                    self.developer_menu is None,
                    kind,
                    len(self.document),
                    self.document.baseline() is not None,
                )
            )
            names.append(selected.name())
            homes.append(os.environ["REVERBSCOPE_HOME"])
            return super().grab(*args)

    monkeypatch.setattr(workbench, "WorkbenchWindow", Recorded)
    out = tmp_path / "images"
    out.mkdir()
    script.render_gui(tmp_path, out)
    assert sorted(path.name for path in out.iterdir()) == [
        "gui-compare.png",
        "gui-frequency-response.png",
        "gui-results.png",
        "gui-results.zh-CN.png",
    ]
    assert [(lang, user, count) for lang, user, _kind, count, _base in grabbed] == [
        ("en", True, 2),
        ("en", True, 2),
        ("en", True, 2),
        ("zh_CN", True, 2),
    ]
    # The comparison screenshot has a baseline; the others do not.
    assert [base for *_rest, base in grabbed] == [False, False, True, False]
    assert names[0].startswith("Synthetic demo room")
    assert names[-1].startswith("合成演示房间")
    # Each language's sessions stay out of the other's recent list.
    assert len(set(homes[:3])) == 1 and homes[0] != homes[-1]
    assert current_locale() == "en"


def test_the_chinese_readme_shows_the_chinese_window() -> None:
    readme = (ROOT / "README.zh-CN.md").read_text(encoding="utf-8")
    assert "(docs/images/gui-results.zh-CN.png)" in readme
    assert "截图为英文界面" not in readme
    assert (ROOT / "docs" / "images" / "gui-results.zh-CN.png").is_file()
