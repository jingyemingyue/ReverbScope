"""A question longer than the screen is written in lines.

Only the last line is the prompt, and a default is never cut in two by the
lines: ``Where to write the test signal [/home/me/My`` / ``Sessions/take]: ``
read as two questions.
"""

from __future__ import annotations

from pathlib import Path

import pytest

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
