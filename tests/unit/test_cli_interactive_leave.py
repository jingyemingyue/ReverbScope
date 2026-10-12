"""Leaving the menu, and the desktop app item.

Ctrl+C while the list is being drawn (a long paste, a slow link) ended with a
traceback where the menu promises 130, and the desktop app item started Qt in
the menu's process without a word: a Qt that cannot start (a missing system
library) ends the program, the menu with it.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from reverbscope.cli.console import Console
from reverbscope.cli.interactive import run_menu
from tests.menus import drive

pytestmark = pytest.mark.usefixtures("_work_in_a_folder")


@pytest.fixture
def _work_in_a_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("REVERBSCOPE_HOME", str(tmp_path / "home"))


# --- The desktop app, and Ctrl+C ---------------------------------------------------------------


def test_the_menu_says_that_a_desktop_app_that_cannot_start_ends_the_program(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.delenv("QT_QPA_PLATFORM", raising=False)
    visit = drive(["10", "q"])
    assert "If Qt cannot start it, the whole program ends, and this menu with it." in visit.text
    zh = drive(["10", "q"], lang="zh_CN")
    assert "整个程序会结束，菜单也随之退出" in zh.text
    # Without a screen the command says so itself and the menu goes on: no note.
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.delenv("QT_QPA_PLATFORM", raising=False)
    monkeypatch.setattr("sys.platform", "linux")
    assert "If Qt cannot start it" not in drive(["10", "q"]).text


class _Interrupts(io.StringIO):
    """A stream on which Ctrl+C arrives while the menu is writing."""

    def __init__(self, after: int) -> None:
        super().__init__()
        self.writes = 0
        self.after = after

    def write(self, text: str) -> int:
        self.writes += 1
        if self.writes == self.after:
            raise KeyboardInterrupt
        return super().write(text)


@pytest.mark.parametrize("after", [1, 2, 3, 6, 12, 25])
def test_ctrl_c_while_the_menu_is_drawn_leaves_with_130_and_no_traceback(after: int) -> None:
    out = _Interrupts(after)
    code = run_menu(
        Console(width=80),
        ask=lambda _prompt: "abc",
        run=lambda _argv: 0,
        out=out,
    )
    assert code == 130
    assert "Traceback" not in out.getvalue()
