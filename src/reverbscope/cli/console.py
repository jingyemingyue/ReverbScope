"""Terminal presentation for the command line.

One place decides how the CLI looks: styles, status symbols, display widths,
wrapping, field lists, tables and the progress line. Commands build their
text through a :class:`Console`; no other module writes escape sequences.

Rules the rest of the CLI relies on:

* **Colour** follows ``--color`` (``auto`` / ``always`` / ``never``), then the
  ``NO_COLOR`` convention (https://no-color.org), then ``FORCE_COLOR``, then
  ``TERM=dumb``, and in ``auto`` mode appears only on a terminal. A pipe or a
  file never receives an escape sequence or a carriage return unless colour
  was asked for.
* **Colour is never the only signal**: every status carries a symbol and a
  word (``✓`` / ``!`` / ``×`` / ``→``), with ASCII forms (``[OK]`` /
  ``[WARN]`` / ``[ERROR]`` / ``->``) where the stream cannot show the symbols;
  :meth:`Console.fit` turns the remaining typographic signs (``Δ``, ``→``,
  ``–``) into ASCII for such a stream as well.
* **Widths are display widths**: a CJK or full-width character takes two
  columns, a combining mark none (:func:`cell_width`); ``len()`` is never used
  to align text.
* Nothing here changes what is measured or stored; it only lays text out.
"""

from __future__ import annotations

import os
import re
import shlex
import shutil
import sys
import time
import unicodedata
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Literal, TextIO

ColorMode = Literal["auto", "always", "never"]
COLOR_MODES: tuple[ColorMode, ...] = ("auto", "always", "never")

#: Status kinds; each has a symbol, an ASCII fallback and a colour.
Status = Literal["ok", "warn", "error", "info", "skip", "unsure", "next"]

_SYMBOLS: dict[str, tuple[str, str]] = {
    "next": ("→", "->"),
    "ok": ("✓", "[OK]"),
    "warn": ("!", "[WARN]"),
    "error": ("×", "[ERROR]"),
    "info": ("i", "[INFO]"),
    "skip": ("–", "[--]"),
    "unsure": ("?", "[?]"),
}

#: SGR parameters. Kept to a restrained palette: bold for structure, one
#: accent, and the three status colours.
_SGR = {
    "bold": "1",
    "dim": "2",
    "red": "31",
    "green": "32",
    "yellow": "33",
    "blue": "34",
    "cyan": "36",
}

_STATUS_STYLE: dict[str, tuple[str, ...]] = {
    "ok": ("green",),
    "warn": ("yellow", "bold"),
    "error": ("red", "bold"),
    "info": ("cyan",),
    "skip": ("dim",),
    "unsure": ("yellow",),
    "next": ("cyan",),
}

#: ASCII stand-ins for the typographic signs the reports use, for a stream
#: whose encoding cannot write them (a cp1252 pipe, a Latin-1 terminal).
_ASCII_SIGNS = str.maketrans(
    {
        "–": "-",
        "—": "-",
        "─": "-",
        "━": "#",
        "→": "->",
        "←": "<-",
        "Δ": "delta",
        "±": "+/-",
        "·": "|",
        "…": "...",
        "×": "x",
        "✓": "[OK]",
        "≤": "<=",
        "≥": ">=",
        "“": '"',
        "”": '"',
        "‘": "'",
        "’": "'",
    }
)

_ANSI = re.compile(r"\x1b\[[0-9;]*m")

#: Characters a line should not start with (closing punctuation, CJK and
#: Latin); a wrap lets them hang one step past the margin instead.
_NO_LINE_START = frozenset("，。、；：！？）」』”’》〉】〕,.;:!?)]}%")

#: Symbols and rules that must survive the stream's encoding for the
#: Unicode forms to be used.
_UNICODE_PROBE = "✓×–─━·…"

#: Width used when the output is not a terminal (files and pipes get stable
#: text), and the bounds for a terminal's width.
PIPE_WIDTH = 100
MIN_WIDTH = 20
#: Wider terminals keep this width: longer lines are harder to read.
MAX_WIDTH = 100


class Verbatim(str):
    """Text printed exactly as it is, on one line: never wrapped or split.

    For paths, URLs and commands, which must survive copy and paste; on a
    narrow terminal they run past the edge (the terminal folds them) rather
    than being cut into pieces.
    """


#: Joins a number to its unit inside the layout (``2.4<NBSP>ms``): wrapping
#: never separates them, and :meth:`Console.fit` writes a plain space.
GLUE = "\u00a0"
_UNIT = re.compile(r"(\d) (dBFS|dB|kHz|Hz|ms|s|m|%)(?![\w])")


def glue_units(text: str) -> str:
    """``110 Hz (+11.3 dB)`` with each number held to its unit."""
    return _UNIT.sub(lambda match: match.group(1) + GLUE + match.group(2), text)


def _windows_cmdline_arg(text: str) -> str:
    """One argv element quoted the way ``cmd.exe`` parses it.

    Same rules as ``subprocess.list2cmdline`` for a single argument. Inlined
    because ``src/`` may not import ``subprocess`` (that module is for
    launching processes; this only prints a command the user can copy).
    """
    # A space, a tab, or an empty argument needs quotes. A quote is escaped
    # either way.
    needs_quotes = (not text) or any(char in text for char in " \t")
    out: list[str] = ['"'] if needs_quotes else []
    backslashes: list[str] = []
    for char in text:
        if char == "\\":
            backslashes.append(char)
            continue
        if char == '"':
            out.append("\\" * (len(backslashes) * 2))
            backslashes = []
            out.append('\\"')
            continue
        if backslashes:
            out.extend(backslashes)
            backslashes = []
        out.append(char)
    if backslashes:
        out.extend(backslashes)
    if needs_quotes:
        # Trailing backslashes sit before the closing quote, so they are escaped.
        out.extend(backslashes)
        out.append('"')
    return "".join(out)


def shell_command(argv: Iterable[str]) -> str:
    """One copy-paste command. An argument with a space or a quote is quoted.

    Placeholders such as ``<take.wav>`` stay bare: they are instructions, not
    a path, and quoting them would hide that. On Windows a backslash is
    rewritten to a slash before quoting. cmd, PowerShell and Git Bash all
    open that form, and a POSIX-style split (the demo replays its own next
    steps that way) no longer eats the separator. A POSIX shell still quotes
    a backslash, because there it is an escape.
    """
    windows = os.name == "nt"
    parts: list[str] = []
    for part in argv:
        text = str(part).replace("\\", "/") if windows else str(part)
        needs_quotes = any(char.isspace() for char in text) or '"' in text or "'" in text
        if not windows and "\\" in text:
            needs_quotes = True
        if not needs_quotes:
            parts.append(text)
        elif windows:
            parts.append(_windows_cmdline_arg(text))
        else:
            parts.append(shlex.quote(text))
    return " ".join(parts)


def _unbreakable(token: str) -> bool:
    """A path or URL: never split inside, even when longer than a line."""
    return "/" in token or "\\" in token or "://" in token


# --- Display width ---------------------------------------------------------


def char_width(char: str) -> int:
    """Columns a terminal gives ``char``: 0, 1 or 2.

    East Asian wide and full-width characters take two; combining marks and
    format characters none. Ambiguous-width characters (``×``, ``─``) count as
    one, as terminals render them by default.
    """
    if unicodedata.combining(char) or unicodedata.category(char) in ("Mn", "Me", "Cf"):
        return 0
    return 2 if unicodedata.east_asian_width(char) in ("W", "F") else 1


def strip_ansi(text: str) -> str:
    return _ANSI.sub("", text)


def cell_width(text: str) -> int:
    """Display width of ``text`` (escape sequences ignored)."""
    return sum(char_width(char) for char in strip_ansi(text))


def pad(text: str, width: int, align: Literal["left", "right"] = "left") -> str:
    """``text`` padded with spaces to ``width`` display columns."""
    fill = " " * max(0, width - cell_width(text))
    return fill + text if align == "right" else text + fill


def truncate(text: str, width: int, ellipsis: str = "…") -> str:
    """Plain ``text`` cut to ``width`` columns, ending in ``ellipsis`` when cut."""
    if cell_width(text) <= width:
        return text
    room = max(0, width - cell_width(ellipsis))
    out, used = [], 0
    for char in text:
        step = char_width(char)
        if used + step > room:
            break
        out.append(char)
        used += step
    return "".join(out) + ellipsis


def _tokens(text: str) -> Iterator[str]:
    """Spaces, Latin words and single wide characters, in order."""
    buffer, kind = "", ""
    for char in text:
        if char.isspace() and char != GLUE:
            this = "space"
        elif char_width(char) == 2:
            if buffer:
                yield buffer
            buffer, kind = "", ""
            yield char
            continue
        else:
            this = "word"
        if this != kind and buffer:
            yield buffer
            buffer = ""
        buffer += char
        kind = this
    if buffer:
        yield buffer


def wrap(text: str, width: int, *, first: str = "", rest: str | None = None) -> list[str]:
    """Plain ``text`` filled to ``width`` columns.

    ``first`` starts the first line and ``rest`` every following one (a
    hanging indent). Chinese text breaks between characters, Latin text at
    spaces; a word longer than a line is split. Explicit newlines are kept.
    """
    rest = first if rest is None else rest
    lines: list[str] = []
    for paragraph in text.split("\n"):
        prefix = first if not lines else rest
        # The line as pieces: a token with the space before it, if any.
        parts: list[str] = []
        space = False
        for token in _tokens(paragraph):
            if token.isspace():
                space = bool(parts)
                continue
            joiner = " " if space and parts else ""
            space = False
            room = width - cell_width(prefix)
            if parts and cell_width("".join(parts) + joiner + token) <= room:
                parts.append(joiner + token)
                continue
            carry = ""
            if parts and not joiner and token[0] in _NO_LINE_START:
                if len(parts) == 1:
                    parts.append(token)  # nothing to carry: let it hang
                    continue
                # Closing punctuation does not start a line: the character
                # before it moves down with it.
                carry = parts.pop()
            if parts:
                lines.append(prefix + "".join(parts))
                prefix = rest
            piece = carry.lstrip() + token
            # A single token wider than the line is split where it must be.
            room = max(1, width - cell_width(prefix))
            while cell_width(piece) > room and len(piece) > 1 and not _unbreakable(piece):
                head = truncate(piece, room, ellipsis="")
                if not head:
                    break
                lines.append(prefix + head)
                prefix, piece = rest, piece[len(head) :]
            parts = [piece]
        lines.append(prefix + "".join(parts))
    return lines


# --- Environment -----------------------------------------------------------


if sys.platform == "win32":

    def _windows_vt(stream: TextIO) -> bool:
        try:
            import ctypes
            import msvcrt

            handle = msvcrt.get_osfhandle(stream.fileno())
            kernel32 = ctypes.windll.kernel32
            mode = ctypes.c_uint32()
            if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
                return False
            enable_vt = 0x0004  # ENABLE_VIRTUAL_TERMINAL_PROCESSING
            if mode.value & enable_vt:
                return True
            return bool(kernel32.SetConsoleMode(handle, mode.value | enable_vt))
        except Exception:  # an old console, or not a console at all
            return False


def _enable_windows_vt(stream: TextIO) -> bool:
    """Turn on escape-sequence processing for a Windows console; False if refused.

    Windows Terminal has it on; the classic console host (cmd, PowerShell
    5) has it off until a program asks. Elsewhere there is nothing to do.
    """
    if sys.platform == "win32":
        return _windows_vt(stream)
    return True


def is_terminal(stream: TextIO | None) -> bool:
    """True for a terminal; False for a pipe, a file, a closed stream or none.

    A windowed desktop bundle (``reverbscope-gui``) runs with ``sys.stdout``
    and ``sys.stderr`` set to ``None``.
    """
    try:
        return bool(stream.isatty())  # type: ignore[union-attr]
    except (AttributeError, ValueError, OSError):
        return False


_isatty = is_terminal


def _unicode_ok(stream: TextIO, interactive: bool, environ: Mapping[str, str]) -> bool:
    # An in-memory text stream (io.StringIO) has no encoding and holds any character.
    encoding = getattr(stream, "encoding", None) or "utf-8"
    try:
        _UNICODE_PROBE.encode(encoding)
    except (LookupError, UnicodeEncodeError):
        return False
    if sys.platform == "win32" and interactive:
        # The classic console host's fonts lack these symbols; Windows
        # Terminal, VS Code and ConEmu show them.
        return any(environ.get(key) for key in ("WT_SESSION", "TERM_PROGRAM", "ConEmuANSI"))
    return True


def use_color(
    stream: TextIO, mode: ColorMode = "auto", environ: Mapping[str, str] | None = None
) -> bool:
    """Whether to write colour to ``stream`` (see the module docstring)."""
    env = os.environ if environ is None else environ
    if mode == "never":
        return False
    if mode == "always":
        _enable_windows_vt(stream)  # best effort; the user asked for colour
        return True
    if env.get("NO_COLOR"):
        return False
    if env.get("FORCE_COLOR", "0") not in ("", "0"):
        _enable_windows_vt(stream)  # best effort, as for --color always
        return True
    if env.get("TERM") == "dumb":
        return False
    if not _isatty(stream):
        return False
    return _enable_windows_vt(stream)


def terminal_width(stream: TextIO, interactive: bool, environ: Mapping[str, str]) -> int:
    """Columns to lay text out in: the terminal's (bounded), else a fixed width."""
    columns = environ.get("COLUMNS", "")
    if columns.isdigit() and int(columns) > 0:
        width = int(columns)
    elif interactive:
        try:
            width = os.get_terminal_size(stream.fileno()).columns
        except (AttributeError, ValueError, OSError):
            width = shutil.get_terminal_size((PIPE_WIDTH, 24)).columns
    else:
        width = PIPE_WIDTH
    return max(MIN_WIDTH, min(MAX_WIDTH, width))


# --- Console -----------------------------------------------------------------


@dataclass(frozen=True)
class Console:
    """How text for one stream is laid out and styled."""

    color: bool = False
    unicode: bool = True
    width: int = PIPE_WIDTH
    #: A terminal (dynamic progress may redraw a line); False for pipes/files.
    interactive: bool = False

    @classmethod
    def for_stream(
        cls,
        stream: TextIO,
        mode: ColorMode = "auto",
        environ: Mapping[str, str] | None = None,
    ) -> Console:
        env = os.environ if environ is None else environ
        interactive = _isatty(stream) and env.get("TERM") != "dumb"
        return cls(
            color=use_color(stream, mode, env),
            unicode=_unicode_ok(stream, interactive, env),
            width=terminal_width(stream, interactive, env),
            interactive=interactive,
        )

    def readable(self, text: str) -> str:
        """Text as this stream will show it, before its width is measured.

        :meth:`fit` still translates anything left. Doing it here keeps a
        narrow encoding (``Δ`` becomes ``delta``) from running past the width
        the line was wrapped to.
        """
        if self.unicode or not text:
            return text
        shown = str(text).translate(_ASCII_SIGNS)
        return Verbatim(shown) if isinstance(text, Verbatim) else shown

    # Styles -----------------------------------------------------------------

    def style(self, text: str, *names: str) -> str:
        if not self.color or not names or not text:
            return text
        codes = ";".join(_SGR[name] for name in names)
        return f"\x1b[{codes}m{text}\x1b[0m"

    def bold(self, text: str) -> str:
        return self.style(text, "bold")

    def muted(self, text: str) -> str:
        return self.style(text, "dim")

    def accent(self, text: str) -> str:
        return self.style(text, "cyan")

    def symbol(self, status: Status) -> str:
        glyph, ascii_form = _SYMBOLS[status]
        return self.style(glyph if self.unicode else ascii_form, *_STATUS_STYLE[status])

    def fit(self, text: str) -> str:
        """``text`` as this stream can write it: typographic signs become ASCII
        where the encoding cannot hold them (see :data:`_ASCII_SIGNS`)."""
        text = text.replace(GLUE, " ")
        return text if self.unicode else text.translate(_ASCII_SIGNS)

    def arrow(self) -> str:
        return "→" if self.unicode else "->"

    def command(self, text: str) -> str:
        """A command to copy: accented, and never wrapped."""
        return self.style(text, "cyan")

    def rule_char(self) -> str:
        return "─" if self.unicode else "-"

    def dash(self) -> str:
        """The mark for a value that is not there."""
        return "—" if self.unicode else "-"

    def sep(self) -> str:
        """Separator between short facts on one line."""
        return " · " if self.unicode else " | "

    # Blocks -------------------------------------------------------------------

    def title(self, text: str) -> list[str]:
        """A command's heading: the title and a rule as wide as it."""
        text = self.readable(text)
        return [self.bold(text), self.muted(self.rule_char() * cell_width(text))]

    def section(self, text: str, note: str = "") -> list[str]:
        """A blank line and a section heading, with an optional muted note."""
        text = self.readable(text)
        note = self.readable(note) if note else ""
        head = self.style(text, "bold", "cyan")
        if not note:
            return ["", head]
        if cell_width(text) + 2 + cell_width(note) <= self.width:
            return ["", head + "  " + self.muted(note)]
        return ["", head, *self.paragraph(note, style=("dim",))]

    def paragraph(self, text: str, indent: int = 2, *, style: tuple[str, ...] = ()) -> list[str]:
        """Plain ``text`` wrapped at ``indent``; ``style`` is applied per line."""
        text = self.readable(text)
        margin = " " * indent
        lines = wrap(text, self.width, first=margin, rest=margin)
        return [margin + self.style(line[indent:], *style) for line in lines]

    def status(
        self,
        kind: Status,
        text: str,
        indent: int = 2,
        *,
        detail: str = "",
        style: tuple[str, ...] = (),
    ) -> list[str]:
        """``✓ text`` wrapped under itself; ``detail`` follows on its own lines.

        ``text`` is plain; ``style`` is applied after wrapping, so an escape
        sequence is never split. :class:`Verbatim` text stays on one line.
        """
        text = self.readable(text)
        if detail:
            detail = self.readable(detail)
        glyph = self.symbol(kind)
        margin = " " * indent
        hang = margin + " " * (cell_width(glyph) + 1)
        lines = (
            [hang + text]
            if isinstance(text, Verbatim)
            else wrap(text, self.width, first=hang, rest=hang)
        )
        out = [hang + self.style(line[len(hang) :], *style) for line in lines]
        out[0] = margin + glyph + " " + out[0][len(hang) :]
        if detail:
            out += self.paragraph(detail, indent=cell_width(hang))
        return out

    def steps(self, items: Sequence[tuple[str, str]], indent: int = 2) -> list[str]:
        """Numbered steps: ``1. what`` wrapped, then the command to run on its own line.

        A step without a command is text only. Commands are kept whole.
        """
        margin = " " * indent
        out: list[str] = []
        for number, (text, command) in enumerate(items, start=1):
            text = self.readable(text)
            command = self.readable(command) if command else command
            head = f"{number}. "
            hang = margin + " " * len(head)
            out += [
                margin + head + line[len(hang) :] if index == 0 else line
                for index, line in enumerate(wrap(text, self.width, first=hang, rest=hang))
            ]
            if command:
                out.append(hang + self.command(command))
        return out

    def commands(self, items: Sequence[tuple[str, str]], indent: int = 2) -> list[str]:
        """``command   what it does`` rows; the description wraps under itself,
        or goes below the command on a narrow terminal."""
        if not items:
            return []
        items = [(self.readable(command), self.readable(text)) for command, text in items]
        margin = " " * indent
        column = indent + max(cell_width(command) for command, _text in items) + 3
        stacked = self.width - column < 28
        out: list[str] = []
        for command, text in items:
            if stacked:
                out.append(margin + self.command(command))
                out += [self.muted(line) for line in wrap(text, self.width, first=margin + "  ")]
                continue
            lines = wrap(text, self.width, first=" " * column)
            first = margin + pad(self.command(command), column - indent) + lines[0][column:]
            out += [first, *lines[1:]]
        return out

    def fields(
        self,
        pairs: Iterable[tuple[str, str]],
        indent: int = 2,
        *,
        max_label: int = 28,
        min_label: int = 0,
    ) -> list[str]:
        """``label  value`` rows with the values aligned and wrapped under themselves.

        On a narrow terminal each value goes on its own line under its label.
        """
        items = [(self.readable(label), self.readable(value)) for label, value in pairs]
        if not items:
            return []
        label_width = min(max_label, max(min_label, *(cell_width(label) for label, _v in items)))
        margin = " " * indent
        value_column = indent + label_width + 2
        stacked = self.width - value_column < 24
        out: list[str] = []
        for label, value in items:
            plain = strip_ansi(value)
            styled = value != plain
            if stacked:
                out.append(margin + self.muted(label))
                out += _styled_wrap(value, plain, styled, self.width, margin + "  ")
                continue
            head = margin + pad(self.muted(label), label_width) + "  "
            if cell_width(label) > label_width:
                out.append(margin + self.muted(label))
                head = " " * value_column
            body = _styled_wrap(value, plain, styled, self.width, " " * value_column)
            out.append(head + body[0][value_column:])
            out += body[1:]
        return out

    def fits(
        self,
        headers: Sequence[str],
        rows: Sequence[Sequence[str]],
        *,
        indent: int = 2,
        gap: int = 3,
    ) -> bool:
        """Whether :meth:`table` would lay these rows out as a table (not blocks)."""
        widths = [cell_width(header) for header in headers]
        for row in rows:
            for index, cell in enumerate(row):
                widths[index] = max(widths[index], cell_width(cell))
        return indent + sum(widths) + gap * (len(headers) - 1) <= self.width

    def table(
        self,
        headers: Sequence[str],
        rows: Sequence[Sequence[str]],
        *,
        align: str = "",
        indent: int = 2,
        gap: int = 3,
        title_columns: int = 1,
    ) -> list[str]:
        """A table with a ruled header; ``align`` has one ``l``/``r`` per column.

        Cells may be styled. When the table does not fit the width, every row
        becomes a small block (its first ``title_columns`` cells as the title,
        then ``header value`` pairs), so nothing runs off the right edge.
        """
        columns = len(headers)
        headers = [self.readable(header) for header in headers]
        rows = [[self.readable(cell) for cell in row] for row in rows]
        align = (align or "l" * columns).ljust(columns, "l")
        widths = [cell_width(header) for header in headers]
        for row in rows:
            for index, cell in enumerate(row):
                widths[index] = max(widths[index], cell_width(cell))
        margin = " " * indent
        if gap > 2 and not self.fits(headers, rows, indent=indent, gap=gap):
            gap = 2  # a little tighter before giving up the table
        if not self.fits(headers, rows, indent=indent, gap=gap):
            out: list[str] = []
            titles = [""] * title_columns
            for number, row in enumerate(rows):
                if number:
                    out.append("")
                # A grouped table leaves a repeated title cell empty; a block
                # needs it back.
                titles = [
                    strip_ansi(cell) or titles[i] for i, cell in enumerate(row[:title_columns])
                ]
                heading = " ".join(cell for cell in titles if cell)
                out += [
                    self.bold(line) for line in wrap(heading, self.width, first=margin, rest=margin)
                ]
                out += self.fields(
                    [
                        (strip_ansi(headers[i]), row[i])
                        for i in range(title_columns, columns)
                        if strip_ansi(row[i]).strip()
                    ],
                    indent=indent + 2,
                )
            return out

        def line(cells: Sequence[str]) -> str:
            parts = [
                pad(cell, widths[i], "right" if align[i] == "r" else "left")
                for i, cell in enumerate(cells)
            ]
            return (margin + (" " * gap).join(parts)).rstrip()

        rule = [self.muted(self.rule_char() * width) for width in widths]
        return [line([self.muted(h) for h in headers]), line(rule), *(line(row) for row in rows)]


def _styled_wrap(value: str, plain: str, styled: bool, width: int, prefix: str) -> list[str]:
    """Wrap a value after ``prefix``; a styled value is kept whole when it fits.

    A :class:`Verbatim` value (a path, a URL) is never wrapped.
    """
    if isinstance(value, Verbatim):
        return [prefix + value]
    if styled and cell_width(prefix) + cell_width(plain) <= width:
        return [prefix + value]
    return wrap(plain, width, first=prefix, rest=prefix)


# --- Progress -----------------------------------------------------------------


def clock(seconds: float) -> str:
    whole = max(0, int(seconds))
    return f"{whole // 60:02d}:{whole % 60:02d}"


class ProgressLine:
    """One redrawn line on a terminal; a single start line anywhere else.

    Called from the thread that waits for the audio stream (never from the
    audio callback). Redraws at most every ``interval`` seconds, re-reads the
    terminal width each time (a resize cannot break it), and writes nothing
    but ``label`` and one closing line when the stream is not a terminal.
    """

    def __init__(
        self,
        console: Console,
        stream: TextIO | None,
        label: str,
        total_s: float,
        *,
        interval: float = 0.1,
        now: Callable[[], float] = time.monotonic,
    ) -> None:
        self.console = console
        self.stream = stream
        self.label = label
        self.total_s = max(0.0, total_s)
        self.interval = interval
        self._now = now
        self._last = -1.0
        self._drawn = 0
        self._started = False

    def start(self) -> None:
        if self._started:
            return
        self._started = True
        if self.stream is None:  # a windowed bundle has no stderr
            self.console = Console()
            return
        if not self.console.interactive:
            self.stream.write(
                self.label + " …\n" if self.console.unicode else self.label + " ...\n"
            )
            self.stream.flush()

    def update(self, fraction: float) -> None:
        self.start()
        if not self.console.interactive or self.stream is None:
            return
        moment = self._now()
        if fraction < 1.0 and self._last >= 0 and moment - self._last < self.interval:
            return
        self._last = moment
        self._draw(min(1.0, max(0.0, fraction)))

    def _draw(self, fraction: float) -> None:
        if self.stream is None:
            return
        width = shutil.get_terminal_size((self.console.width, 24)).columns
        width = max(MIN_WIDTH, min(MAX_WIDTH, width)) - 1
        percent = f"{fraction * 100:3.0f}%"
        timing = f"{clock(fraction * self.total_s)} / {clock(self.total_s)}"
        label = truncate(self.label, max(8, width // 2))
        room = width - cell_width(label) - len(percent) - len(timing) - 6
        bar = ""
        if room >= 10:
            size = min(32, room)
            filled = round(size * fraction)
            full, empty = ("━", "─") if self.console.unicode else ("#", "-")
            bar = self.console.accent(full * filled) + self.console.muted(empty * (size - filled))
        text = f"  {label}  {bar}  {percent}  {self.console.muted(timing)}".replace("    ", "  ")
        visible = cell_width(text)
        self.stream.write("\r" + text + " " * max(0, self._drawn - visible))
        self.stream.flush()
        self._drawn = visible

    def finish(self, completed: bool = True) -> None:
        """End the line (terminal) so later output starts on its own row.

        ``completed`` draws the bar full first; a take that stopped early
        keeps the last position it reached.
        """
        if self.console.interactive and self._drawn and self.stream is not None:
            if completed:
                self._draw(1.0)
            self.stream.write("\n")
            self.stream.flush()
            self._drawn = 0
