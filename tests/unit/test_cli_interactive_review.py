"""How the menu reads an answer.

``是的`` and ``确定`` are a yes; an answer that is neither a yes nor a no is
said to be taken as no, so that a yes in other words is not taken for a no
without a word; the warning before a take asks for a lower volume in plain
words.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.menus import drive

pytestmark = pytest.mark.usefixtures("_work_in_a_folder")


@pytest.fixture
def _work_in_a_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("REVERBSCOPE_HOME", str(tmp_path / "home"))


# --- Answers -----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("lang", "answer", "plays"),
    [
        ("en", "y", True),
        ("en", "YES", True),
        ("en", "ｙ", True),
        ("zh_CN", "是", True),
        ("zh_CN", "是的", True),
        ("zh_CN", "确定", True),
        ("en", "n", False),
        ("en", "", False),
        ("zh_CN", "否", False),
        ("zh_CN", "不要", False),
        ("en", "ok", False),
        ("zh_CN", "好", False),
        ("en", "yy", False),
    ],
)
def test_only_a_yes_plays_and_an_answer_that_is_neither_is_said_to_be_taken_as_no(
    lang: str, answer: str, plays: bool
) -> None:
    visit = drive(["4", "take", "", answer, "q"], lang=lang, prefix=["--backend", "fake"])
    assert bool(visit.runs) is plays
    understood = answer in ("y", "YES", "ｙ", "是", "是的", "确定", "n", "", "否", "不要")
    note = "没能理解为“是”" if lang == "zh_CN" else "Not understood as yes"
    assert (note in visit.text) is (not understood), visit.text


def test_the_warning_before_a_take_asks_for_a_lower_volume_in_plain_words() -> None:
    visit = drive(["4", "take", "", "n", "q"], lang="zh_CN", prefix=["--backend", "fake"])
    assert "请先调低监听音箱或音频接口的输出音量" in visit.text
    assert "开低" not in visit.text
