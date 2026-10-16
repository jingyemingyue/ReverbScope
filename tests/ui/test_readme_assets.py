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
    """The screenshots showed the Developer menu, which the downloaded app does
    not have, and README.zh-CN.md showed the English window. The English
    window must also show the English demo's names, not those the Chinese
    demo run wrote last."""
    from reverbscope.demo import run_demo
    from reverbscope.i18n import activate, current_locale
    from reverbscope.ui import main_window

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
    grabbed: list[tuple[str, bool, str]] = []
    subtitles: list[str] = []
    homes: list[str] = []

    class Recorded(main_window.MainWindow):  # type: ignore[misc]
        def grab(self, *args: Any) -> Any:
            tab = self.workspace.views["overview"].title()
            grabbed.append((current_locale(), self.developer_menu is None, tab))
            subtitles.append(self.inspector.subtitle.text())
            homes.append(os.environ["REVERBSCOPE_HOME"])
            return super().grab(*args)

    monkeypatch.setattr(main_window, "MainWindow", Recorded)
    out = tmp_path / "images"
    out.mkdir()
    script.render_gui(tmp_path, out)
    assert sorted(path.name for path in out.iterdir()) == [
        "gui-compare.png",
        "gui-frequency-response.png",
        "gui-results.png",
        "gui-results.zh-CN.png",
    ]
    assert [(lang, user) for lang, user, _tab in grabbed] == [
        ("en", True),
        ("en", True),
        ("en", True),
        ("zh_CN", True),
    ]
    english_tab, chinese_tab = grabbed[0][2], grabbed[-1][2]
    assert english_tab != chinese_tab
    assert not any(char.isascii() and char.isalpha() for char in chinese_tab)
    assert subtitles[0].startswith("Synthetic demo room")
    assert subtitles[-1].startswith("合成演示房间")
    # Each language's sessions stay out of the other's recent list.
    assert len(set(homes[:3])) == 1 and homes[0] != homes[-1]
    assert current_locale() == "en"


def test_the_chinese_readme_shows_the_chinese_window() -> None:
    readme = (ROOT / "README.zh-CN.md").read_text(encoding="utf-8")
    assert "(docs/images/gui-results.zh-CN.png)" in readme
    assert "截图为英文界面" not in readme
    assert (ROOT / "docs" / "images" / "gui-results.zh-CN.png").is_file()
