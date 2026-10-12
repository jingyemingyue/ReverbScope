"""What the tests of the framed terminal output share.

A card is a titled frame as wide as the console (a finding, an error); these
helpers find the cards in a text and check that every line of one keeps its
sides and corners on one display column, whatever the language, the colour or
the encoding the stream is drawn in.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass

import pytest

from reverbscope.cli.console import Console, cell_width, strip_ansi
from reverbscope.cli.main import main

ESC = "\x1b["
WIDTHS = (48, 60, 80, 100)
LANGS = ("en", "zh_CN")

#: The ways a stream is drawn: Unicode frames, the same in colour, ASCII frames
#: (a stream that cannot write the box glyphs) and the two legacy Windows code
#: pages, one of which cannot write Chinese at all.
VARIANTS = {
    "unicode": {"unicode": True, "color": False, "encoding": "utf-8"},
    "colour": {"unicode": True, "color": True, "encoding": "utf-8"},
    "ascii": {"unicode": False, "color": False, "encoding": "utf-8"},
    "ascii-colour": {"unicode": False, "color": True, "encoding": "utf-8"},
    "gbk": {"unicode": False, "color": False, "encoding": "gbk"},
    "cp1252": {"unicode": False, "color": False, "encoding": "cp1252"},
}


def boxed_console(width: int, variant: str = "unicode", **kwargs: object) -> Console:
    """A console that draws frames, ``width`` columns wide, in one of the :data:`VARIANTS`."""
    options: dict[str, object] = {**VARIANTS[variant], "boxed": True, "width": width, **kwargs}
    return Console(**options)  # type: ignore[arg-type]


class Stream(io.StringIO):
    """A text stream that is, or is not, a terminal."""

    def __init__(self, *, tty: bool, encoding: str = "utf-8") -> None:
        super().__init__()
        self._tty = tty
        self._encoding = encoding

    def isatty(self) -> bool:
        return self._tty

    @property
    def encoding(self) -> str:  # type: ignore[override]
        return self._encoding


TOP = re.compile(r"^[╭+][─-] (?P<title>.+?) [─-]+[╮+]$")
BOTTOM = re.compile(r"^(╰─+╯|\+-+\+)$")
SIDE = re.compile(r"^[│|] (?P<text>.*) [│|]$")


@dataclass
class Card:
    title: str
    body: list[str]
    lines: list[str]


def find_cards(text: str) -> list[Card]:
    """The cards of ``text``, without colour: a titled top border, side lines, a bottom border."""
    found: list[Card] = []
    open_card: Card | None = None
    for raw in text.splitlines():
        line = strip_ansi(raw)
        if open_card is None:
            top = TOP.match(line)
            if top:
                open_card = Card(top["title"], [], [line])
            continue
        open_card.lines.append(line)
        side = SIDE.match(line)
        if side:
            open_card.body.append(side["text"])
        elif BOTTOM.match(line):
            found.append(open_card)
            open_card = None
        else:
            raise AssertionError(f"a card is broken off by {line!r}")
    assert open_card is None, "a card has no bottom border"
    return found


def check_card(card: Card, width: int) -> None:
    """Every line of a card is as wide as the console, with its corners and sides in line."""
    assert {cell_width(line) for line in card.lines} == {width}, "\n".join(card.lines)
    top, bottom = card.lines[0], card.lines[-1]
    ascii_frame = top[0] == "+"
    assert (top[0], top[-1]) == (("+", "+") if ascii_frame else ("╭", "╮"))
    assert (bottom[0], bottom[-1]) == (("+", "+") if ascii_frame else ("╰", "╯"))
    side = "|" if ascii_frame else "│"
    for line in card.lines[1:-1]:
        assert line[0] == side and line[-1] == side, line


_FRAME = re.compile(r"[─━│┃┌┐└┘├┤┬┴┼┏┓┗┛┣┫┳┻╋╭╮╰╯]")


def unframe(text: str) -> str:
    """``text`` without its frames: the sides, corners and rules of the cards,
    tables and headings are blanks, so the words can be read as they are."""
    return "\n".join(_FRAME.sub(" ", strip_ansi(line)).rstrip() for line in text.splitlines())


def invoke(argv: list[str], capsys: pytest.CaptureFixture[str]) -> tuple[int, str, str]:
    """Run the command line in this process: the exit code, stdout and stderr."""
    capsys.readouterr()
    try:
        code = main(argv)
    except SystemExit as exc:
        code = int(exc.code or 0)
    captured = capsys.readouterr()
    return code, captured.out, captured.err
