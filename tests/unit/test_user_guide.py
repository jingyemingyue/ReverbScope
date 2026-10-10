"""The user guides describe the desktop app as it is."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

GUIDES = (Path("docs/user-guide/en.md"), Path("docs/user-guide/zh-CN.md"))
UI = Path("src/reverbscope/ui")


def _workspace_view_rows(text: str) -> list[str]:
    """First cells of the table that follows "The workstation has ... views"."""
    start = re.search(r"^(The workstation has \w+ views|工作台有\S+个视图)", text, re.M)
    assert start is not None
    rows: list[str] = []
    for line in text[start.end() :].splitlines()[1:]:
        if not line.startswith("|"):
            if rows:
                break
            continue
        rows.append(line.split("|")[1].strip())
    return rows[2:]  # header and separator


def _workspace_views() -> list[str]:
    """The view classes ``default_views`` builds, in order (read from the source)."""
    source = (UI / "analysis_workspace.py").read_text(encoding="utf-8")
    body = source.split("def default_views(", 1)[1].split("\n\n\n", 1)[0]
    listed = body.split("return [", 1)[1]
    return re.findall(r"^\s+(\w+)\(", listed, re.M)


@pytest.mark.parametrize("guide", GUIDES, ids=lambda path: path.name)
def test_the_guides_list_every_workspace_view(guide: Path) -> None:
    """The guides described the 0.5 Results page and its eight tabs; the
    workstation has a view bar, and the guide's table has a row per view."""
    views = _workspace_views()
    assert "OverviewView" in views and "RoomView" in views
    assert len(_workspace_view_rows(guide.read_text(encoding="utf-8"))) == len(views)


def test_the_english_guide_names_the_views_as_the_view_bar_does() -> None:
    rows = _workspace_view_rows(GUIDES[0].read_text(encoding="utf-8"))
    titles = re.findall(
        r'def title\(self\) -> str:\n\s+return _\("([^"]+)"\)',
        "".join(
            path.read_text(encoding="utf-8")
            for path in (*UI.glob("*.py"), *UI.glob("views/*.py"), *UI.glob("room/*.py"))
        ),
    )
    assert set(rows) <= set(titles), set(rows) - set(titles)
    assert "Results page" not in GUIDES[0].read_text(encoding="utf-8")
    assert "结果页" not in GUIDES[1].read_text(encoding="utf-8")


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
