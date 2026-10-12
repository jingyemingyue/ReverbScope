"""The error panel.

On a terminal that draws frames an error is a card titled ``✗ Error``
(``✗ 错误``): the message and its explanation inside a red frame, and the
commands to try under it, bare. A command is never framed or wrapped, so that
it can be copied; a text that a card cannot hold whole (a path is never cut) is
laid out as the line it always was. The usage errors argparse raises before
the options are parsed follow ``--style``, the ``style`` setting and
``REVERBSCOPE_CLI_STYLE`` too. Without frames (a pipe, a file, a terminal
narrower than ``use_boxes`` allows, ``--style plain``) an error is the line it
always was.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from reverbscope.cli.console import Console, cell_width, strip_ansi
from reverbscope.cli.main import main
from reverbscope.cli.render import render_error
from reverbscope.i18n import activate
from tests.frames import (
    BOTTOM,
    ESC,
    LANGS,
    TOP,
    VARIANTS,
    WIDTHS,
    Stream,
    boxed_console,
    check_card,
    find_cards,
    invoke,
)


@pytest.fixture
def language(request: pytest.FixtureRequest) -> Iterator[str]:
    lang: str = getattr(request, "param", "en")
    activate(lang)
    try:
        yield lang
    finally:
        activate("en")


@contextmanager
def _in(lang: str) -> Iterator[None]:
    activate(lang)
    try:
        yield
    finally:
        activate("en")


@pytest.fixture
def home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Path]:
    monkeypatch.setenv("REVERBSCOPE_HOME", str(tmp_path / "home"))
    for name in ("NO_COLOR", "FORCE_COLOR", "TERM", "COLUMNS", "REVERBSCOPE_CLI_STYLE"):
        monkeypatch.delenv(name, raising=False)
    try:
        yield tmp_path
    finally:
        activate("en")


# --- The error panel -----------------------------------------------------------------

MESSAGES = {
    "en": (
        "audio file not found: take.wav",
        "input channel 9 does not exist on ReverbScope fake interface (8 input channel(s)); "
        "pick one of the channels that the interface has",
    ),
    "zh_CN": (
        "找不到音频文件：take.wav",
        "输入通道 9 在 ReverbScope 假接口上不存在（共 8 个输入通道）；请选择接口上有的通道",
    ),
}
DETAILS = {"en": "Nothing was played.", "zh_CN": "没有播放任何声音。"}
TRY = {"en": "  Try:", "zh_CN": "  可以尝试："}
HINTS = ("reverbscope devices --probe", "reverbscope doctor --probe")


def _split_error(text: str) -> tuple[list[str], list[str]]:
    """The card of an error and the lines after it."""
    lines = text.splitlines()
    end = next(i for i, line in enumerate(lines) if BOTTOM.match(strip_ansi(line)))
    return lines[: end + 1], lines[end + 1 :]


@pytest.mark.parametrize("language", LANGS, indirect=True)
@pytest.mark.parametrize("variant", sorted(VARIANTS))
@pytest.mark.parametrize("width", WIDTHS)
def test_an_error_is_a_card_and_its_commands_stay_bare_after_it(
    language: str, variant: str, width: int
) -> None:
    console = boxed_console(width, variant)
    for message in MESSAGES[language]:
        text = render_error(console, message, detail=DETAILS[language], hints=HINTS)
        panel, rest = _split_error(text)
        (card,) = find_cards("\n".join(panel))
        check_card(card, width)
        mark = "x" if not console.unicode else "✗"
        word = "Error" if language == "en" else "错误"
        if variant == "cp1252" and language == "zh_CN":
            word = "????"  # one "?" per column
        assert card.title == f"{mark} {word}"
        said = "".join("".join(card.body).split())
        if variant != "cp1252" or language == "en":
            assert said == "".join((message + DETAILS[language]).split()), card.body
        # The commands: after the card, bare, at their own indent, on one line each.
        assert [strip_ansi(line) for line in rest] == [
            "",
            TRY[language] if variant != "cp1252" else rest[1],
            *(f"    {hint}" for hint in HINTS),
        ]
        assert not any(char in "".join(rest) for char in "│╭╰|+")
        if variant in ("colour", "ascii-colour"):
            # A red border; the mark in the title is red (the ASCII "x", a letter,
            # is bold instead) and the title bold.
            assert panel[0].startswith("\x1b[31m") and panel[-1].startswith("\x1b[31m")
            shown = f"\x1b[1m{mark}\x1b[0m" if mark.isalnum() else f"\x1b[31m{mark}\x1b[0m"
            assert f"{shown} \x1b[1m" in panel[0]
            assert all(line.startswith("\x1b[31m") for line in panel)
            assert all(line.endswith("\x1b[0m") for line in panel)
            # The text itself is not coloured: only the sides of a line carry escapes.
            for line in panel[1:-1]:
                inner = line[len("\x1b[31m│\x1b[0m ") : -len(" \x1b[31m│\x1b[0m")]
                assert ESC not in inner or not console.unicode, inner
        else:
            assert ESC not in text


def test_the_error_card_says_error_in_words_and_with_a_mark() -> None:
    text = render_error(boxed_console(60), "session file not found: x", hints=["reverbscope show"])
    assert text.splitlines()[0].startswith("╭─ ✗ Error ─")
    assert text.splitlines()[1].startswith("│ session file not found: x ")
    assert text.splitlines()[2].startswith("╰") and text.splitlines()[3] == ""
    with _in("zh_CN"):
        zh = render_error(boxed_console(60), "找不到会话文件：x")
    assert zh.splitlines()[0].startswith("╭─ ✗ 错误 ─")
    ascii_text = render_error(boxed_console(60, "ascii"), "session file not found: x")
    assert ascii_text.splitlines()[0].startswith("+- x Error -")
    assert "error:" not in text and "错误：" not in zh  # the title says it once


def test_without_frames_an_error_is_the_line_it_always_was() -> None:
    plain = Console(width=60)
    assert render_error(plain, "session file not found: x", hints=HINTS[:1]) == (
        "× error: session file not found: x\n\n  Try:\n    reverbscope devices --probe"
    )
    assert render_error(plain, "bad", detail="Nothing was played.") == (
        "× error: bad\n  Nothing was played."
    )
    ascii_text = render_error(Console(width=60, unicode=False), "bad", hints=["x --help"])
    assert ascii_text == "error: bad\n\n  Try:\n    x --help"
    with _in("zh_CN"):
        zh = render_error(plain, "找不到会话文件：x", hints=["reverbscope show --help"])
    assert zh == "× 错误：找不到会话文件：x\n\n  可以尝试：\n    reverbscope show --help"


def test_a_command_in_an_error_is_never_bordered_or_wrapped() -> None:
    command = "reverbscope --verbose analyze --recording /a/long/path/to/take.wav --sweep sweep.wav"
    text = render_error(
        boxed_console(48), "unexpected KeyError: 'x'", hints=[command, "reverbscope doctor"]
    )
    lines = text.splitlines()
    assert f"    {command}" in lines  # whole, on one line, past the width
    assert cell_width(command) > 48
    assert "    reverbscope doctor" in lines
    assert all(not line.startswith(("│", "╭", "╰")) for line in lines if "reverbscope" in line)


def test_an_error_naming_a_path_too_long_for_the_card_is_unframed_and_keeps_it_whole() -> None:
    path = "/a/very/long/path/that/does/not/fit/in/a/card/of/fifty/columns/take.wav"
    text = render_error(
        boxed_console(50), f"no such file or folder: {path}", hints=["reverbscope show"]
    )
    lines = text.splitlines()
    assert not any(TOP.match(line) for line in lines)
    assert any(line.endswith(path) for line in lines), "the path is on one line, whole"
    # The line that stands in for the card has the card's glyph.
    assert lines[0].startswith("✗ error: no such file or folder:")
    # A path that fits is inside the card.
    short = render_error(boxed_console(80), f"no such file or folder: {path}")
    assert path in short and find_cards(short)


def test_a_chinese_path_too_long_for_the_card_is_kept_whole_too() -> None:
    """The card cut ``不存在的文件夹/录音位置甲/会话/…`` between 会 and 话 at 48
    columns; a path of Latin letters was never cut."""
    path = "不存在的文件夹/录音位置甲/会话/再加一层很长很长的目录名称/还有一层"
    with _in("zh_CN"):
        for width in (48, 60, 100):
            text = render_error(
                boxed_console(width), f"找不到会话文件：{path}", hints=["reverbscope show --help"]
            )
            lines = text.splitlines()
            if width < 100:
                assert not any(TOP.match(line) for line in lines), text
                assert any(line.endswith(path) for line in lines), text
            else:
                assert find_cards(text), text  # it fits: inside the card


def test_the_detail_of_an_error_is_inside_the_card_under_the_message() -> None:
    guidance = "Set the project's sample rate to 48 kHz.\nTurn off time stretching."
    text = render_error(boxed_console(60), "the sweep was played too fast", detail=guidance)
    (card,) = find_cards(text)
    assert card.body[0].startswith("the sweep was played too fast")
    assert [line.strip() for line in card.body[1:]] == [
        "Set the project's sample rate to 48 kHz.",
        "Turn off time stretching.",
    ]


def test_the_command_line_shows_the_error_card_where_the_style_says_so(
    home: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    # A pipe or a file: the line, as always.
    code, out, err = invoke(["show", "no-such-session"], capsys)
    assert code == 1 and out == "" and err.startswith("× error: session file not found")
    # --style boxed asks for frames in a pipe too, and a failed run follows it.
    code, out, err = invoke(["--style", "boxed", "show", "no-such-session"], capsys)
    assert code == 1 and out == "" and err.startswith("╭─ ✗ Error ─")
    assert "session file not found: no-such-session" in err
    assert err.rstrip().endswith("reverbscope show --list <folder>")
    code, out, err = invoke(["--style", "plain", "show", "no-such-session"], capsys)
    assert err.startswith("× error:")
    # A terminal wide enough: the card, by default.
    # On Windows only Windows Terminal and alike show the symbols and the frames, and
    # colour needs a console handle that a pretend terminal does not have.
    monkeypatch.setenv("WT_SESSION", "1")
    monkeypatch.setattr("reverbscope.cli.console._enable_windows_vt", lambda _stream: True)
    tty = Stream(tty=True)
    monkeypatch.setattr("sys.stderr", tty)
    monkeypatch.setenv("COLUMNS", "70")
    assert main(["show", "no-such-session"]) == 1
    assert tty.getvalue().startswith("\x1b[31m╭─\x1b[0m")
    narrow = Stream(tty=True)
    monkeypatch.setattr("sys.stderr", narrow)
    monkeypatch.setenv("COLUMNS", "47")
    assert main(["show", "no-such-session"]) == 1
    assert strip_ansi(narrow.getvalue()).startswith("× error:")
    # The environment variable and the stored choice, as for the reports.
    plain = Stream(tty=True)
    monkeypatch.setattr("sys.stderr", plain)
    monkeypatch.setenv("COLUMNS", "70")
    monkeypatch.setenv("REVERBSCOPE_CLI_STYLE", "plain")
    assert main(["show", "no-such-session"]) == 1
    assert strip_ansi(plain.getvalue()).startswith("× error:")


def test_a_usage_error_follows_the_style_that_was_asked_for(
    home: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """argparse fails before the options are parsed: the style is read from the
    command line, the environment and the stored setting by hand."""
    code, _out, err = invoke(["show", "somewhere", "--bogus"], capsys)
    assert code == 2 and err.startswith("× error: unrecognized arguments: --bogus")
    code, _out, err = invoke(["--style", "boxed", "show", "somewhere", "--bogus"], capsys)
    assert code == 2 and err.startswith("╭─ ✗ Error ─") and "--bogus" in err
    code, _out, err = invoke(["--style=boxed", "show", "somewhere", "--bogus"], capsys)
    assert err.startswith("╭─ ✗ Error ─")
    code, _out, err = invoke(["--sty", "boxed", "show", "somewhere", "--bogus"], capsys)
    assert err.startswith("╭─ ✗ Error ─")
    code, _out, err = invoke(
        ["--lang", "zh_CN", "--style", "boxed", "show", "somewhere", "--bogus"], capsys
    )
    assert err.startswith("╭─ ✗ 错误 ─")
    # A terminal that would frame it, asked not to.
    monkeypatch.setenv("WT_SESSION", "1")  # Windows Terminal and alike show the symbols
    tty = Stream(tty=True)
    monkeypatch.setattr("sys.stderr", tty)
    monkeypatch.setenv("COLUMNS", "80")
    with pytest.raises(SystemExit):
        main(["--style", "plain", "show", "somewhere", "--bogus"])
    assert strip_ansi(tty.getvalue()).startswith("× error:")
    # The stored setting decides when the option is not given.
    assert main(["config", "style", "plain"]) == 0
    capsys.readouterr()
    again = Stream(tty=True)
    monkeypatch.setattr("sys.stderr", again)
    with pytest.raises(SystemExit):
        main(["show", "somewhere", "--bogus"])
    assert strip_ansi(again.getvalue()).startswith("× error:")
    assert main(["config", "style", "boxed"]) == 0
    capsys.readouterr()
    monkeypatch.undo()
    monkeypatch.setenv("REVERBSCOPE_HOME", str(home / "home"))
    code, _out, err = invoke(["show", "somewhere", "--bogus"], capsys)
    assert code == 2 and err.startswith("╭─ ✗ Error ─")
