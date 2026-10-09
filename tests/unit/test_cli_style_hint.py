"""A Chinese interface says how to leave the frames out.

A terminal that draws ambiguous-width glyphs (the box glyphs) two columns wide, as
a CJK font or locale setting can make it, bends every frame; the only way out,
``reverbscope config style plain``, was written in ``config --help`` and in the
user guide, never where the crooked frame is.
"""

from __future__ import annotations

import pytest

from reverbscope.cli.config import style_hint_lines
from reverbscope.cli.interactive import menu_items
from reverbscope.i18n import activate
from tests.terminals import capture, menu_screen

COMMAND = "reverbscope config style plain"


def test_the_home_screen_of_a_chinese_interface_says_it(monkeypatch: pytest.MonkeyPatch) -> None:
    last = capture((), monkeypatch, columns=80, lang="zh_CN").splitlines()
    assert last[-2] == f"边框歪了？{COMMAND}"
    assert last[-1] == "English interface: reverbscope config language en"
    assert COMMAND not in capture((), monkeypatch, columns=80, lang="en")
    # Not once the style is plain, and a pipe has no frames to leave out.
    assert COMMAND not in capture((), monkeypatch, columns=80, lang="zh_CN", style="plain")
    piped = capture((), monkeypatch, columns=80, lang="zh_CN", style="auto", tty=False)
    assert COMMAND not in piped


def test_the_menu_of_a_chinese_interface_says_it_too() -> None:
    assert COMMAND not in menu_screen("en", boxed=True)
    assert COMMAND not in menu_screen("zh_CN", boxed=False)
    menu = menu_screen("zh_CN", boxed=True)
    assert f"\n边框歪了？{COMMAND}\n" in menu
    # The numbering and the items of the menu are what they were.
    for item in menu_items():
        assert f"  {item.key.rjust(2)}  {item.title}\n" in menu, item.key


def test_the_hint_keeps_its_command_whole_on_a_narrow_terminal() -> None:
    activate("zh_CN")
    assert style_hint_lines("zh_CN", 80, boxed=True) == [f"边框歪了？{COMMAND}"]
    assert style_hint_lines("zh_CN", 30, boxed=True) == ["边框歪了？", f"  {COMMAND}"]
    assert style_hint_lines("zh_CN", 80, boxed=False) == []
    assert style_hint_lines("en", 80, boxed=True) == []
