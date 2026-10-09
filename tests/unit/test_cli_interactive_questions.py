"""A question longer than the screen is written in lines.

Only the last line is the prompt, and a default is never cut in two by the
lines: ``Where to write the test signal [/home/me/My`` / ``Sessions/take]: ``
read as two questions.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from reverbscope.cli import interactive
from reverbscope.cli.console import cell_width
from tests.menus import CTRL_C, drive


@pytest.fixture(autouse=True)
def _work_in_a_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


@pytest.mark.parametrize("lang", ["en", "zh_CN"])
@pytest.mark.parametrize("width", [80, 60, 40])
def test_a_default_is_never_cut_in_two_by_a_long_question(
    tmp_path: Path, lang: str, width: int
) -> None:
    """``测试信号 … （默认：/home/我的 录音/`` / ``sweep.wav）：`` read as two questions:
    the question is written in lines and the hint stays whole on the last."""
    folder = tmp_path / "My Takes 录音"
    folder.mkdir()
    take = folder / "take.wav"
    sweep = folder / "sweep.wav"
    take.write_bytes(b"RIFF")
    sweep.write_bytes(b"RIFF")
    visit = drive(["3", str(take), "", "", "q"], width=width, lang=lang)
    assert visit.code == 0
    hint = f"[{sweep}]: " if lang == "en" else f"（默认：{sweep}）："
    prompt = next(prompt for prompt in visit.prompts if str(sweep) in prompt)
    assert prompt.rstrip().endswith(hint.rstrip()), prompt
    for line in [*visit.lines, *visit.prompts]:
        assert line.count("[") == line.count("]"), line
        assert line.count("（") == line.count("）"), line
        assert not line.rstrip().endswith(("默认：", " [", "（")), line


def test_a_question_that_fits_is_one_prompt_and_says_nothing_else() -> None:
    visit = drive(["2", CTRL_C, "q"], width=80)
    assert visit.prompts[1] == "Where to write the test signal [sweep.wav]: "
    assert not any(cell_width(line) > 80 for line in visit.lines)


@pytest.mark.parametrize("lang", ["en", "zh_CN"])
def test_a_question_ends_in_one_colon_not_two(tmp_path: Path, lang: str) -> None:
    """The label of a question is not followed by a colon of its own: the
    prompt adds one ("Baseline (before): number or path:" had two)."""
    for name in ("a", "b", "room"):
        (tmp_path / name).mkdir()
    (tmp_path / "rec.wav").write_bytes(b"RIFF")
    answers = [
        "2", "", "", "3", str(tmp_path / "rec.wav"), "", "", "5", "x", "", "6", "a", "b", "",
        "7", "room", "4", "", "", "", "q",
    ]  # fmt: skip
    visit = drive(answers, lang=lang, prefix=["--backend", "fake"])
    questions = [prompt.rstrip() for prompt in visit.prompts]
    assert len(questions) > 12
    for prompt in questions:
        assert prompt.endswith((":", "：")), prompt
        label = re.sub(r"[:：]$", "", prompt)
        assert not label.endswith((":", "：")), prompt


def test_the_menu_writes_only_through_the_console() -> None:
    """The look comes from Console; the menu writes no escape sequence of its own."""
    source = Path(interactive.__file__).read_text(encoding="utf-8")
    assert "\\x1b" not in source and "\\033" not in source and "\x1b" not in source
