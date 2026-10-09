"""The user guides describe the desktop app as it is."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

GUIDES = (Path("docs/user-guide/en.md"), Path("docs/user-guide/zh-CN.md"))
UI = Path("src/reverbscope/ui")


def _results_tab_rows(text: str) -> list[str]:
    """Rows of the table that follows "The Results page has ... tabs"."""
    start = re.search(r"^(The Results page has \w+ tabs|结果页有\S+个标签页)", text, re.M)
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
def test_the_guides_list_every_results_tab(guide: Path) -> None:
    """The guides said seven tabs, with the text report in the Overview; the
    page has eight, the report in its own tab."""
    tabs = (UI / "results.py").read_text(encoding="utf-8").count("self.tabs.addTab(")
    assert len(_results_tab_rows(guide.read_text(encoding="utf-8"))) == tabs


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


CHINESE_DOCS = sorted(
    (
        *Path("docs").glob("*.zh-CN.md"),
        *Path("docs/user-guide").glob("*zh-CN.md"),
        Path("README.zh-CN.md"),
        Path("SECURITY.zh-CN.md"),
    ),
    key=str,
)


def test_the_chinese_guides_use_the_words_of_the_chinese_interface() -> None:
    """The interface says 音频接口, 回采, 交流声 and 对比; the guides said 声卡,
    回送, 市电哼声 and 比较 for the same things."""
    from tests.unit.test_i18n_catalog import RETIRED_CHINESE_WORDS

    assert len(CHINESE_DOCS) >= 15
    found = {
        (path.as_posix(), match.group(0), better)
        for path in CHINESE_DOCS
        for pattern, better in RETIRED_CHINESE_WORDS.items()
        for match in re.finditer(pattern, path.read_text(encoding="utf-8"))
    }
    assert found == set(), sorted(found)
