"""The user guides describe the desktop app as it is."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

GUIDES = (Path("docs/user-guide/en.md"), Path("docs/user-guide/zh-CN.md"))
UI = Path("src/reverbscope/ui")


def _chart_rows(text: str) -> list[str]:
    """Rows of the table that follows "The workbench charts" / "工作台图表"."""
    start = re.search(r"^#*\s*\**(The workbench charts|工作台图表)", text, re.M)
    assert start is not None
    rows: list[str] = []
    for line in text[start.end() :].splitlines()[1:]:
        if not line.startswith("|"):
            if rows:
                break
            continue
        rows.append(line)
    return rows[2:]  # header and separator


@pytest.mark.parametrize("guide", GUIDES, ids=lambda path: path.name)
def test_the_guides_list_every_chart_kind(guide: Path) -> None:
    """The guides list every chart kind a workbench panel offers, one row each,
    and no longer describe pages, result tabs, a demo entry or a home page."""
    from reverbscope.ui.plot_data import PLOT_KINDS

    text = guide.read_text(encoding="utf-8")
    assert len(_chart_rows(text)) == len(PLOT_KINDS)
    for stale in ("Results page", "Demo (no interface)", "Home page", "演示（无需音频接口）"):
        assert stale not in text, stale


def test_the_guides_do_not_promise_untranslated_diagnostics_or_file_drops() -> None:
    """Diagnostics are shown translated, and no widget accepts a dropped file."""
    english, chinese = (path.read_text(encoding="utf-8") for path in GUIDES)
    daw_chinese = Path("docs/user-guide/daw-setup.zh-CN.md").read_text(encoding="utf-8")
    assert "always English" not in english
    assert "始终为英文" not in chinese and "核心诊断保持英文" not in daw_chinese
    accepts_drops = any("dropEvent" in path.read_text(encoding="utf-8") for path in UI.glob("*.py"))
    if not accepts_drops:
        assert "drop the files" not in english
        assert "拖进界面" not in chinese
