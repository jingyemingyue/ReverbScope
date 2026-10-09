"""Ctrl+C and Ctrl+D at the menu and at its questions.

Ctrl+C at a question returns to the menu, at the menu it leaves with exit
code 130; the end of input leaves with 0 wherever it comes; none of them is a
traceback.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from tests.menus import CTRL_C, CTRL_D, drive


@pytest.fixture(autouse=True)
def _work_in_a_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


def test_ctrl_c_at_the_menu_leaves_with_130() -> None:
    visit = drive([CTRL_C])
    assert visit.code == 130 and visit.runs == []
    # The shell's prompt does not start in the middle of the menu's last line.
    assert visit.raw.endswith("\n\n")


def test_ctrl_c_at_a_question_returns_to_the_menu_and_the_next_one_leaves() -> None:
    visit = drive(["3", CTRL_C, CTRL_C])
    assert visit.code == 130 and visit.runs == []
    assert visit.text.count("Back to the menu.") == 1
    assert "Traceback" not in visit.raw


@pytest.mark.parametrize(
    "answers",
    [[], ["2"], ["2", "sweep.wav"], ["3"], ["5"], ["6", "x"], ["4"], ["4", ""], [CTRL_D]],
    ids=["menu", "sweep", "rate", "analyze", "show", "compare", "measure", "measure-folder", "d"],
)
def test_end_of_input_leaves_with_0_anywhere(answers: list[object]) -> None:
    visit = drive(answers)
    assert visit.code == 0 and visit.runs == []
    assert "Traceback" not in visit.raw


def test_a_question_that_fails_for_another_reason_is_not_a_traceback(
    capfd: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture
) -> None:
    """The menu's last resort says so in words; the traceback goes to the log
    file, not to the screen (``--verbose`` shows it)."""
    from reverbscope.logging_config import configure_logging

    configure_logging(logging.WARNING, log_file=False)
    visit = drive(["2", ValueError("boom"), "q"])
    assert visit.code == 0 and visit.runs == []
    assert "could not be completed (ValueError: boom)" in visit.text
    assert "Traceback" not in capfd.readouterr().err
