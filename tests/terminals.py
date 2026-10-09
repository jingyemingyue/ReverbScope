"""The terminals the colour and narrow-screen tests run the command line on.

``capture`` runs ``main`` on a stream that is, or is not, a terminal, in a
given encoding and width, and returns what was written as the terminal would
show it; ``problems`` lists what is wrong with such a screen: a traceback, a
line wider than the terminal, a frame that is not straight, a number parted
from its unit at the end of a line, colour on a word.
"""

from __future__ import annotations

import contextlib
import io
import re
import sys
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path

import pytest

from reverbscope.cli.console import Console, cell_width, strip_ansi
from reverbscope.cli.interactive import run_menu
from reverbscope.cli.main import main
from reverbscope.demo import DemoRun, run_demo
from reverbscope.i18n import activate

ENCODINGS = ("utf-8", "cp1252", "cp936")


@dataclass(frozen=True)
class Workspace:
    """A demo (two sessions and their comparison) and a project made of them."""

    root: Path
    demo: Path
    room: Path
    run: DemoRun

    @property
    def a(self) -> str:
        return str(self.demo / "position-a")

    @property
    def b(self) -> str:
        return str(self.demo / "position-b")


def build_workspace(root: Path) -> Workspace:
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("REVERBSCOPE_HOME", str(root / "home"))
        demo = root / "demo"
        run = run_demo(demo)
        room = root / "room"
        for argv in (
            ["project", "init", "--out", str(room), "--name", "Studio"],
            ["project", "add", str(room), str(demo / "position-a"), "--position", "A"],
            ["project", "add", str(room), str(demo / "position-b"), "--position", "B"],
        ):
            assert main(argv) == 0
    return Workspace(root, demo, room, run)


def screens(space: Workspace) -> list[tuple[str, ...]]:
    """The screens of the commands that print a report: about twenty."""
    a, b = space.a, space.b
    return [
        ("show", a),
        ("show", b),
        ("show", str(space.demo / "comparison.json")),
        ("show", "--list", str(space.demo)),
        ("compare", a, b),
        ("compare", a, b, "--same-input-gain"),
        ("project", "overview", str(space.room)),
        ("project", "show", str(space.room)),
        ("project", "average", str(space.room)),
        ("--backend", "fake", "devices"),
        ("--backend", "fake", "devices", "--probe"),
        ("--backend", "fake", "doctor"),
        ("config",),
        ("config", "style"),
        ("config", "language"),
        ("profiles",),
        ("profiles", "vocal"),
        ("sweep", "--out", "sweep.wav", "--duration", "2"),
        ("show", str(space.root / "missing")),
        ("compare", a),
        (),
    ]


def layouts(space: Workspace) -> list[tuple[str, ...]]:
    """One screen of each layout in :func:`screens`: the same renderers
    behind two screens are tried once."""
    skipped = {
        ("show", space.b),
        ("compare", space.a, space.b, "--same-input-gain"),
        ("project", "show", str(space.room)),
        ("--backend", "fake", "devices"),
        ("config", "language"),
        ("profiles",),
        ("show", "--list", str(space.demo)),
    }
    return [argv for argv in screens(space) if argv not in skipped]


class Terminal(io.TextIOWrapper):
    """A text stream in a given encoding that is, or is not, a terminal."""

    def __init__(self, *, tty: bool, encoding: str, errors: str = "strict") -> None:
        self.raw = io.BytesIO()
        super().__init__(self.raw, encoding=encoding, errors=errors, write_through=True)
        self._tty = tty

    def isatty(self) -> bool:
        return self._tty

    def fileno(self) -> int:
        raise OSError("not a file")

    def shown(self) -> str:
        """What a reader sees: the bytes decoded, a character the stream could not write a "?"."""
        return self.raw.getvalue().decode(self.encoding, "replace")


def capture(
    argv: tuple[str, ...] | list[str],
    patch: pytest.MonkeyPatch,
    *,
    columns: int,
    lang: str = "en",
    color: str = "never",
    style: str = "boxed",
    encoding: str = "utf-8",
    tty: bool = True,
) -> str:
    """The text ``reverbscope`` writes for ``argv`` on such a terminal (stdout, then stderr)."""
    for name in ("NO_COLOR", "FORCE_COLOR", "REVERBSCOPE_CLI_STYLE"):
        patch.delenv(name, raising=False)
    patch.setenv("COLUMNS", str(columns))
    patch.setenv("PYTHONIOENCODING", encoding)
    patch.setenv("TERM", "xterm-256color")
    patch.setenv("REVERBSCOPE_NO_MENU", "1")  # the home screen, even if the tests run in a terminal
    out = Terminal(tty=tty, encoding=encoding)
    err = Terminal(tty=tty, encoding=encoding, errors="backslashreplace")
    patch.setattr(sys, "stdout", out)
    patch.setattr(sys, "stderr", err)
    with contextlib.suppress(SystemExit):
        main(["--lang", lang, "--color", color, "--style", style, *argv])
    return out.shown() + err.shown()


def menu_screen(lang: str, *, boxed: bool, width: int = 80, color: bool = False) -> str:
    """What the menu writes before its first answer (``q``): the title, the list, the hint."""
    activate(lang)
    out = io.StringIO()
    console = Console(width=width, boxed=boxed, color=color, interactive=True)
    run_menu(console, ask=lambda _prompt: "q", run=lambda _argv: 0, out=out)
    return out.getvalue()


# --- What is wrong with a screen ---------------------------------------------------------------

_SGR = re.compile(r"\x1b\[([0-9;]*)m")
#: Foreground colours and dim: unreadable on some palettes, so never on a word.
_FAINT_OR_COLOURED = {"2", "30", "31", "32", "33", "34", "35", "36", "37", "90", "91", "92", "93"}


def coloured_words(text: str) -> list[str]:
    """Every run of letters or digits that is dim or coloured."""
    found: list[str] = []
    active: set[str] = set()
    run = ""
    position = 0

    def flush() -> None:
        nonlocal run
        if run:
            found.append(run)
        run = ""

    for match in _SGR.finditer(text):
        for char in text[position : match.start()]:
            if char.isalnum() and active & _FAINT_OR_COLOURED:
                run += char
            else:
                flush()
        flush()
        codes = {code for code in match.group(1).split(";") if code}
        active = set() if not codes or codes == {"0"} else active | codes
        position = match.end()
    for char in text[position:]:
        if char.isalnum() and active & _FAINT_OR_COLOURED:
            run += char
        else:
            flush()
    flush()
    return found


#: The units a number is never parted from, in Latin and in Chinese.
_UNITS = r"(?:dBFS|dB|kHz|Hz|ms|s|m|°C|%|摄氏度|赫兹|倍频程|分贝|[个项次条遍处])"
_FRAMES = re.compile(r"[─━│┃┌┐└┘├┤┬┴┼┏┓┗┛┣┫┳┻╋╭╮╰╯|+]")
_FRAME_START = frozenset("╭│╰┌├└┬┴┼")
_ASCII_FRAME_LINE = re.compile(r"^\s*[+|][-+=| ]")
#: A command to copy is never wrapped; a path or a URL is never cut.
_COMMAND = re.compile(r"^\s*(\d+\. )?reverbscope ")
_PATH = re.compile(r"\S*(?:[/\\]|\w\.[A-Za-z]{2,5}(?!\w))\S*")


def _has_path(line: str) -> bool:
    return any(len(word) >= 12 for word in _PATH.findall(line))


def problems(text: str, columns: int, *, color: str = "never") -> list[str]:
    """What is wrong with ``text`` as a screen ``columns`` wide; empty when nothing."""
    found: list[str] = []
    if (
        "Traceback" in text
        or re.search(r"unexpected \w*(Error|Exception)", text)
        or "意外错误" in text
    ):
        found.append("an unexpected error")
    if color == "never" and "\x1b" in text:
        found.append("an escape sequence without colour")
    if color == "always" and (words := coloured_words(text)):
        found.append(f"colour on {words[:8]}")
    lines = [strip_ansi(line) for line in text.split("\n")]
    for line in lines:
        if cell_width(line) > columns and not (_COMMAND.match(line) or _has_path(line)):
            found.append(f"{cell_width(line)} > {columns} columns: {line!r}")
    group: list[str] = []

    def end_group() -> None:
        nonlocal group
        if len({cell_width(line) for line in group}) > 1:
            shown = "; ".join(f"{cell_width(line)}: {line}" for line in group[:6])
            found.append(f"frame not straight: {shown}")
        group = []

    for line in lines:
        start = line.lstrip()
        if start and (start[0] in _FRAME_START or _ASCII_FRAME_LINE.match(line)):
            group.append(line)
        else:
            end_group()
    end_group()
    flat = [" ".join(_FRAMES.sub(" ", line).split()) for line in lines]
    for above, below in pairwise(flat):
        if re.search(r"\d$", above) and re.match(rf"{_UNITS}(?![A-Za-z])", below):
            found.append(f"a number parted from its unit: {above!r} / {below!r}")
    return found
