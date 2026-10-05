"""Command-line output without its frames, for tests that read its words.

Panels and bordered tables (``roomscope config style boxed``, the default)
put border glyphs between the words and wrap a long value inside its cell;
:func:`words` reads a screen the same way whatever style drew it.
"""

from __future__ import annotations

import re

#: The glyphs of panels, tables and section bars (Unicode forms; the ASCII
#: forms are ordinary characters).
FRAME_GLYPHS = "╭╮╰╯─│┌┬┐├┼┤└┴┘┏┳┓━┃┡╇┩▌"
_FRAME = re.compile(f"[{FRAME_GLYPHS}]")


def unframe(text: str) -> str:
    """``text`` with every border glyph turned into a space: the cells of a
    row stay side by side, separated by spaces."""
    return _FRAME.sub(" ", text)


def words(text: str) -> str:
    """The words of ``text``, one space apart, frames and line breaks gone."""
    return " ".join(unframe(text).split())


#: The first glyph of every line of a frame: Unicode, then ASCII.
_LEFT = (frozenset("╭│╰┏┃┡└┌├"), frozenset("+|"))


def frame_blocks(text: str, *, ascii: bool = False) -> list[list[str]]:
    """Every run of consecutive lines that belong to frames (panels, tables;
    cards stacked on each other make one run)."""
    from roomscope.cli.console import strip_ansi

    left = _LEFT[1 if ascii else 0]
    blocks: list[list[str]] = []
    run: list[str] = []
    for line in [*text.splitlines(), ""]:
        plain = strip_ansi(line)
        if plain[:1] in left:
            run.append(line)
            continue
        if run:
            blocks.append(run)
        run = []
    return blocks
