"""The user guides describe the desktop app as it is."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

GUIDES = (Path("docs/user-guide/en.md"), Path("docs/user-guide/zh-CN.md"))
UI = Path("src/reverbscope/ui")


def _results_group_rows(text: str) -> list[str]:
    """Rows of the table that follows "The Results page is built around the chart"."""
    start = re.search(
        r"^(The Results page is built around the chart|结果页以图表为中心)", text, re.M
    )
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
def test_the_guides_list_every_chart_group(guide: Path) -> None:
    """The Results page has no tabs: the guides list the chart groups the
    Charts list offers, one row each."""
    from reverbscope.ui.results_presenter import GROUPS

    assert len(_results_group_rows(guide.read_text(encoding="utf-8"))) == len(GROUPS)
    assert (
        "tabs"
        not in guide.read_text(encoding="utf-8")
        .split("## Placement")[0]
        .split("The Results page is built around the chart")[-1]
    )


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
