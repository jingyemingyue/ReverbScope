"""The menu on a real pseudo-terminal.

The scripted tests replace ``input()``; here the program runs as a person
runs it: ``input()`` reads the terminal's line, Ctrl+C is the signal the
terminal sends, and Qt really is asked to open a window. Linux and macOS only.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

# Windows has no pseudo-terminal (and tests.ptyrun cannot even be imported there).
pytest.importorskip("termios")

from tests.ptyrun import CTRL_C, CTRL_D, Terminal

PROMPT = {"en": "Your choice: ", "zh_CN": "你的选择："}
Start = Callable[..., Terminal]


@pytest.fixture
def terminal(tmp_path: Path) -> Iterator[Start]:
    """Start the program with an empty settings folder; always clean it up."""
    started: list[Terminal] = []
    environment = {
        key: value
        for key, value in os.environ.items()
        if key not in {"DISPLAY", "WAYLAND_DISPLAY", "QT_QPA_PLATFORM", "NO_COLOR", "FORCE_COLOR"}
        and not key.startswith("REVERBSCOPE_")
    }
    environment.update(
        REVERBSCOPE_HOME=str(tmp_path / "home"), TERM="xterm-256color", LANG="C.UTF-8"
    )
    (tmp_path / "work").mkdir()

    def start(*args: str, **extra: str) -> Terminal:
        env = {**environment, **extra}
        session = Terminal.python(*args, env=env, cwd=str(tmp_path / "work"))
        started.append(session)
        return session

    try:
        yield start
    finally:
        for session in started:
            session.close()


def test_ctrl_c_at_the_menu_leaves_with_130_and_no_traceback(terminal: Start) -> None:
    session = terminal("--lang", "en")
    session.expect(PROMPT["en"])
    session.send(CTRL_C)
    assert session.finish() == 130
    assert "Traceback" not in session.output


def test_ctrl_c_at_a_question_returns_to_the_menu(terminal: Start) -> None:
    session = terminal("--lang", "en")
    seen = session.expect(PROMPT["en"])
    session.type("3")
    seen = session.expect("exported from your DAW", after=seen)
    session.send(CTRL_C)
    seen = session.expect("Back to the menu.", after=seen)
    seen = session.expect(PROMPT["en"], after=seen)  # the menu again
    session.type("q")
    assert session.finish() == 0
    assert "Traceback" not in session.output


def test_the_end_of_input_leaves_with_0_at_the_menu_and_at_a_question(terminal: Start) -> None:
    session = terminal("--lang", "en")
    session.expect(PROMPT["en"])
    session.send(CTRL_D)
    assert session.finish() == 0
    session = terminal("--lang", "en")
    seen = session.expect(PROMPT["en"])
    session.type("5")
    session.expect("comparison.json", after=seen)
    session.send(CTRL_D)
    assert session.finish() == 0
    assert "Traceback" not in session.output


@pytest.mark.parametrize(
    ("lang", "word"), [("en", "ｑ"), ("en", "ＱＵＩＴ"), ("zh_CN", "退出"), ("zh_CN", "ｑ")]
)
def test_a_quit_word_typed_on_a_chinese_keyboard_leaves(
    terminal: Start, lang: str, word: str
) -> None:
    session = terminal("--lang", lang)
    session.expect(PROMPT[lang])
    session.type(word)
    assert session.finish() == 0
    assert "Traceback" not in session.output


def test_the_desktop_app_without_a_screen_does_not_abort_the_menu(terminal: Start) -> None:
    pytest.importorskip("PySide6.QtWidgets")
    if not sys.platform.startswith("linux"):
        pytest.skip("Qt aborts for lack of a display on Linux")
    session = terminal("--lang", "en")
    seen = session.expect(PROMPT["en"])
    session.type("10")
    seen = session.expect("needs a graphical display", after=seen)
    seen = session.expect("The command ended with exit code 2.", after=seen)
    seen = session.expect(PROMPT["en"], after=seen)  # the menu is still there
    session.type("q")
    assert session.finish() == 0
    assert "qt.qpa" not in session.output and "Traceback" not in session.output


def test_a_full_width_digit_chooses_an_item_and_the_command_line_is_shown(terminal: Start) -> None:
    session = terminal("--lang", "en")
    seen = session.expect(PROMPT["en"])
    session.type("９")
    seen = session.expect("reverbscope --lang en doctor", after=seen)
    seen = session.expect("Environment report", after=seen)
    seen = session.expect(PROMPT["en"], after=seen)
    session.type("q")
    assert session.finish() == 0


@pytest.mark.parametrize("key", [CTRL_C, CTRL_D], ids=["ctrl-c", "ctrl-d"])
def test_a_key_at_the_question_that_plays_plays_nothing(
    terminal: Start, tmp_path: Path, key: str
) -> None:
    """Enter, Ctrl+C and Ctrl+D at "Play and record now?" start no take, on the
    interface that would answer at once (``--backend fake``)."""
    session = terminal("--lang", "en", "--backend", "fake")
    seen = session.expect(PROMPT["en"])
    session.type("4")
    seen = session.expect("Folder for the new session", after=seen)
    session.type("")
    seen = session.expect("Level of the sweep in dBFS", after=seen)
    session.type("")
    seen = session.expect("Play and record now?", after=seen)
    session.send(key)
    if key == CTRL_C:
        seen = session.expect("Back to the menu.", after=seen)
        session.expect(PROMPT["en"], after=seen)
        session.type("q")
    assert session.finish() == 0
    assert "Recorded" not in session.output and "Traceback" not in session.output
    assert not list((tmp_path / "work").glob("session-*"))
