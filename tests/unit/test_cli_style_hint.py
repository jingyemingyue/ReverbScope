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
    # Frames asked for in a pipe are in a file: nobody looks at them crooked.
    forced = capture((), monkeypatch, columns=80, lang="zh_CN", style="boxed", tty=False)
    assert COMMAND not in forced


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


def test_the_menu_says_it_once_and_does_not_repeat_the_list_after_a_wrong_choice() -> None:
    """The hint sat above the prompt every time the list was drawn, and the whole
    list was drawn again after each answer that was not on it."""
    import io

    from reverbscope.cli.console import Console
    from reverbscope.cli.interactive import run_menu

    activate("zh_CN")
    try:
        answers = iter(["x", "99", "8", "q"])  # two wrong choices, settings, quit
        out = io.StringIO()
        ran: list[list[str]] = []
        console = Console(width=60, boxed=True, interactive=True)
        code = run_menu(
            console,
            ask=lambda _prompt: next(answers),
            run=lambda argv: ran.append(argv) or 0,
            out=out,
        )
    finally:
        activate("en")
    text = out.getvalue()
    assert code == 0 and ran == [["config"]]
    # Listed at the start and again after the command ran: twice, not four times.
    assert text.count("试试演示（合成房间") == 2, text
    # The hint belongs to the first list only.
    assert text.count(COMMAND) == 1
    assert text.index(COMMAND) < text.index("请输入列表中的编号，或 q。")
    assert text.count("请输入列表中的编号，或 q。") == 2
