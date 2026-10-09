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
* **Colour sits on marks, bars and borders only**: never on a run of letters
  or digits (yellow, green and cyan text has a contrast of 1.7 to 3.5 on the
  usual light backgrounds, dim text 1.9 to 3.7), and nothing that carries
  information is dim. Status words, titles, headings, commands and menu
  numbers are bold in the colour of the terminal's text; labels, notes and
  descriptions are plain; dim is for decoration (rules, borders, the rest of
  a progress bar). A mark that is a letter (the ASCII ``[OK]``, ``x``, ``i``)
  is bold, not coloured.
* **Colour is never the only signal**: every status carries a symbol and a
  word (``✓`` / ``!`` / ``×`` / ``→``), with ASCII forms (``[OK]`` /
  ``[WARN]`` / ``[ERROR]`` / ``->``) where the stream cannot show the symbols;
  :meth:`Console.fit` turns the remaining typographic signs (``Δ``, ``→``,
  ``–``) into ASCII for such a stream as well. Where a table has room for a
  status column its cell is a badge (:meth:`Console.badge`), the mark and a
  word (``✓ good``).
* **Widths are display widths**: a CJK or full-width character takes two
  columns, a combining mark none (:func:`cell_width`); ``len()`` is never used
  to align text.
* Nothing here changes what is measured or stored; it only lays text out.
"""

from __future__ import annotations

import functools
import os
import re
import shlex
import shutil
import sys
import time
import unicodedata
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, is_dataclass, replace
from dataclasses import fields as dataclass_fields
from typing import Any, Literal, TextIO

from reverbscope.i18n import pgettext

ColorMode = Literal["auto", "always", "never"]
COLOR_MODES: tuple[ColorMode, ...] = ("auto", "always", "never")

#: How reports are framed: ``boxed`` draws a frame around a report's title,
#: rules through its section headings and borders around its tables;
#: ``plain`` is the ruled layout; ``auto`` boxes a terminal at least
#: :data:`MIN_BOXED_WIDTH` columns wide and never a pipe or a file.
StyleMode = Literal["auto", "boxed", "plain"]
STYLE_MODES: tuple[StyleMode, ...] = ("auto", "boxed", "plain")
#: The environment variable that chooses the style when the option is ``auto``.
STYLE_VARIABLE = "REVERBSCOPE_CLI_STYLE"
MIN_BOXED_WIDTH = 48

#: Frame glyphs: (top-left, top, top-right, side, bottom-left, bottom-right)
#: for a title panel, and the table set (corners, tees, cross).
_PANEL = {True: ("╭", "─", "╮", "│", "╰", "╯"), False: ("+", "-", "+", "|", "+", "+")}
_GRID = {
    True: {
        "tl": "┌",
        "tr": "┐",
        "bl": "└",
        "br": "┘",
        "t": "┬",
        "b": "┴",
        "l": "├",
        "r": "┤",
        "x": "┼",
        "h": "─",
        "v": "│",
    },
    False: {
        "tl": "+",
        "tr": "+",
        "bl": "+",
        "br": "+",
        "t": "+",
        "b": "+",
        "l": "+",
        "r": "+",
        "x": "+",
        "h": "-",
        "v": "|",
    },
}

#: Status kinds; each has a symbol, an ASCII fallback and a colour.
Status = Literal["ok", "warn", "error", "info", "skip", "unsure", "next"]
#: The colour of a card's border and of the mark in its title.
Tone = Literal["accent", "ok", "warn", "error", "muted"]

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
#: accent, and the three status colours, which only ever go on marks, bars and
#: borders (see the module docstring); dim is for decoration alone.
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

_TONE_STYLE: dict[str, tuple[str, ...]] = {
    "accent": ("cyan",),
    "ok": ("green",),
    "warn": ("yellow",),
    "error": ("red",),
    "muted": ("dim",),
}

#: One-column marks for a badge (``✓ good``) and for the title of a card
#: (``✗ Error``), which carry their word: Unicode, then ASCII. ``✗`` rather
#: than the ``×`` of a status line, because ``×`` is an ambiguous-width
#: character that a CJK terminal may draw two columns wide; ``✗`` is one
#: column everywhere.
_MARKS: dict[str, tuple[str, str]] = {
    "ok": ("✓", "+"),
    "warn": ("!", "!"),
    "error": ("✗", "x"),
    "info": ("i", "i"),
    "skip": ("–", "-"),
    "unsure": ("?", "?"),
    "next": ("→", ">"),
}

#: The narrowest a wrapping column of a bordered table gets before the table
#: is laid out another way.
_WRAP_FLOOR = 16

#: The progress bar: the part done, its head and the part to come, Unicode
#: then ASCII. The head says where the bar stands without colour.
_METER = {True: ("━", "╸", "─"), False: ("=", ">", "-")}

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

#: Kept wherever the encoding can write it (cp1252, GBK, the classic Windows
#: console), even when the other signs are not; dropped otherwise: 20 C.
_DEGREE = "°"

_ANSI = re.compile(r"\x1b\[[0-9;]*m")
#: The escape sequences :meth:`Console.style` writes, and only those.
_OWN_CODE = "|".join(sorted({*_SGR.values(), "0"}, key=len, reverse=True))
_OWN_STYLE = re.compile(rf"(\x1b\[(?:{_OWN_CODE})(?:;(?:{_OWN_CODE}))*m)")
#: A styled word at the start of a cell: the escape, the text, the reset.
_LEADING_STYLE = re.compile(r"(?:\x1b\[[0-9;]*m)+(?P<text>[^\x1b\s]+)\x1b\[0m")
#: Characters a terminal acts on instead of showing: C0 and C1 controls
#: (ESC starts a sequence that clears the screen or retitles the window) and
#: the bidirectional controls, which reorder what follows them.
_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f\u061c\u200e\u200f\u202a-\u202e\u2066-\u2069]")
_ESCAPES = {"\n": "\\n", "\r": "\\r", "\t": "\\t"}

#: Characters a line should not start with (closing punctuation, CJK and
#: Latin); a wrap lets them hang one step past the margin instead.
_NO_LINE_START = frozenset("，。、；：！？）」』”’》〉】〕,.;:!?)]}%")
#: Characters a line should not end with (opening brackets and quotes); a
#: wrap carries them down with what they open.
_NO_LINE_END = frozenset("（「『“‘《〈【〔([{")

#: Symbols and rules that must survive the stream's encoding for the
#: Unicode forms to be used.
_UNICODE_PROBE = "✓×–─━·…"

#: Every glyph of the Unicode frames: the corners, sides, tees and cross of a
#: card and of a table. An encoding that writes the symbols above but not
#: these (the JIS X 0213 family has ``×`` and ``─`` but no rounded corners)
#: gets the ASCII frames.
_FRAME_PROBE = "".join(sorted({*_PANEL[True], *_GRID[True].values()}))

#: Width used when the output is not a terminal (files and pipes get stable
#: text), and the bounds for a terminal's width.
PIPE_WIDTH = 100
MIN_WIDTH = 20
#: Wider terminals keep this width: longer lines are harder to read.
MAX_WIDTH = 100


def badge_word(kind: Status) -> str:
    """The word a badge shows next to its mark (``✓ good``); empty for ``next``.

    The words say how a result stands in an overview (``good``, ``check``,
    ``problem``), not how a measurement is judged: the health and verdict
    sections keep their own vocabulary.
    """
    return {
        "ok": pgettext("status", "good"),
        "warn": pgettext("status", "check"),
        "error": pgettext("status", "problem"),
        "info": pgettext("status", "note"),
        "skip": pgettext("status", "no data"),
        "unsure": pgettext("status", "unsure"),
    }.get(kind, "")


class Verbatim(str):
    """Text printed exactly as it is, on one line: never wrapped or split.

    For paths, URLs and commands, which must survive copy and paste; on a
    narrow terminal they run past the edge (the terminal folds them) rather
    than being cut into pieces.
    """


def printable(text: str, *, single_line: bool = False, own_styles: bool = True) -> str:
    """``text`` with the control characters in it shown as escapes (``\\x1b``).

    Text from files, such as the room name of a session from someone else or
    a warning stored in its result.json, must not reach the terminal as
    control sequences: they could clear the screen, retitle the window, or
    hide and forge lines of the report. ``single_line`` is for a name shown
    on one line: line breaks and tabs are shown as escapes too, and every
    escape sequence. Otherwise ReverbScope's own colour codes are kept
    (``own_styles``): a stream that gets no colour has none, so an escape
    code in its text is never one of ours.
    """
    keep = "" if single_line else "\n\t"

    def escape(match: re.Match[str]) -> str:
        char = match.group()
        if char in keep:
            return char
        if char in _ESCAPES:
            return _ESCAPES[char]
        code = ord(char)
        return f"\\x{code:02x}" if code < 0x100 else f"\\u{code:04x}"

    if not _CONTROL.search(text):
        return text
    if single_line or not own_styles:
        shown = _CONTROL.sub(escape, text)
    else:
        parts = _OWN_STYLE.split(text)
        shown = "".join(
            part if index % 2 else _CONTROL.sub(escape, part) for index, part in enumerate(parts)
        )
    return Verbatim(shown) if isinstance(text, Verbatim) else shown


def printable_fields[T](value: T) -> T:
    """``value`` with every text in it passed through :func:`printable` (one line).

    For a result or comparison read from a file: its warnings, notes, labels
    and reasons are laid out inside lines of ReverbScope's own, so a line break
    or an escape code in one of them forges a row of the report. Lists,
    tuples, dicts and dataclasses are followed; a record that needs no change
    is returned as it is, and the one that was read is never modified.
    """
    shown: T = _printable_fields(value)
    return shown


def _printable_fields(value: Any) -> Any:
    if type(value) is str:
        return printable(value, single_line=True)
    if type(value) in (list, tuple):
        items = [_printable_fields(item) for item in value]
        if all(new is old for new, old in zip(items, value, strict=True)):
            return value
        return type(value)(items)
    if type(value) is dict:
        pairs = {key: _printable_fields(item) for key, item in value.items()}
        if all(pairs[key] is old for key, old in value.items()):
            return value
        return pairs
    if is_dataclass(value) and not isinstance(value, type):
        changes = {}
        for field in dataclass_fields(value):
            if not field.init:
                continue
            old = getattr(value, field.name)
            new = _printable_fields(old)
            if new is not old:
                changes[field.name] = new
        return replace(value, **changes) if changes else value
    return value


#: Joins a number to its unit inside the layout (``2.4<NBSP>ms``): wrapping
#: never separates them, and :meth:`Console.fit` writes a plain space.
GLUE = "\u00a0"
_UNIT = re.compile(r"(\d) (dBFS|dB|kHz|Hz|ms|s|m|°C|%)(?![\w])")
#: A Chinese counter or unit that follows a number (``3 个``, ``20 摄氏度``).
_CJK_UNIT = "摄氏度|赫兹|倍频程|分贝|[个项次条遍处]"
_COUNTED = re.compile(rf"(\d) ({_CJK_UNIT})")
_CJK_UNIT_AT = re.compile(_CJK_UNIT)


def glue_units(text: str) -> str:
    """``110 Hz (+11.3 dB)`` and ``3 个`` with each number held to its unit
    (and dB to SPL)."""
    text = _UNIT.sub(lambda match: match.group(1) + GLUE + match.group(2), text)
    text = _COUNTED.sub(lambda match: match.group(1) + GLUE + match.group(2), text)
    return text.replace("dB SPL", "dB" + GLUE + "SPL")


#: What a POSIX shell passes through untouched in a word, besides letters and
#: digits of any script (so a Chinese name stays readable): everything else
#: is quoted, whether or not some shell would do anything with it.
_POSIX_PLAIN = frozenset("._-/:,=@%+")
#: Characters cmd.exe or PowerShell split at or expand outside quotes.
_WINDOWS_SPECIAL = frozenset(" \t\"'&|()<>^%;,{}@$`")
#: ``<take.wav>``: an instruction, not a path.
_PLACEHOLDER = re.compile(r"<[^<>\s]+>")


def _windows_cmdline_arg(text: str, *, quote: bool = False) -> str:
    """One argv element quoted the way ``cmd.exe`` parses it.

    Same rules as ``subprocess.list2cmdline`` for a single argument; ``quote``
    also quotes an argument that has no space (``room&booth``). Inlined
    because ``src/`` may not import ``subprocess`` (that module is for
    launching processes; this only prints a command the user can copy).
    """
    # A space, a tab, or an empty argument needs quotes. A quote is escaped
    # either way.
    needs_quotes = quote or (not text) or any(char in text for char in " \t")
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
    """One copy-paste command. On macOS and Linux an argument with anything
    but letters and digits of any script and ``. / - _ : , = @ % +`` in it is
    quoted (a space, a quote, ``( ) & ; $ |``, a caret, a character nobody can
    see); on Windows one that cmd or PowerShell would split or expand is.

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
        if windows:
            # "demo(1)&x/position-a" bare is two commands in cmd; a character
            # that cannot be seen is quoted too, for it would pass for nothing.
            needs_quotes = not text or any(
                char.isspace() or char in _WINDOWS_SPECIAL or not char.isprintable()
                for char in text
            )
        else:
            # "demo(1)&x/position-a" bare is a syntax error in bash. Anything
            # but a letter, a digit or . / - _ : , = @ % + gets quotes: a caret
            # (a pipe to the oldest shells), a control character, a zero-width
            # space or a right-to-left override (which would pass for nothing in
            # the line shown) as much as a bracket or a dollar.
            needs_quotes = not text or not all(
                char.isalnum() or char in _POSIX_PLAIN for char in text
            )
        if not needs_quotes or _PLACEHOLDER.fullmatch(text):
            parts.append(text)
        elif windows:
            parts.append(_windows_cmdline_arg(text, quote=True))
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


#: Full-width marks that end a run of Chinese text; a path in a Chinese
#: sentence (``找不到会话文件：录音/会话/take.wav``) starts after the last of
#: them and runs to the next one or a blank.
_CJK_STOPS = "，。、；：！？（）「」『』“”‘’《》〈〉【】〔〕"
_PATH_RUN = re.compile(rf"[^\s{_CJK_STOPS}]*[/\\][^\s{_CJK_STOPS}]*")
_DRIVE = re.compile(r"[A-Za-z]:[/\\]")
_EXTENSION = re.compile(r"\.\w{1,5}$")


def _is_wide_path(run: str) -> bool:
    """Whether ``run`` (non-blank text with a ``/`` or ``\\`` in it) is a path
    that has Chinese in it, which is never cut: a path of Latin letters is one
    word already. ``输入/输出`` is a pair of words, not a path, so a run needs a
    second separator, a start that only a path has (``/``, ``~``, ``C:\\``) or
    a file extension."""
    if not any(char_width(char) == 2 for char in run):
        return False
    separators = run.count("/") + run.count("\\")
    return (
        separators >= 2
        or run[0] in "/\\~"
        or _DRIVE.match(run) is not None
        or _EXTENSION.search(run) is not None
    )


def _tokens(text: str) -> Iterator[str]:
    """Spaces, Latin words, single wide characters and paths, in order. A number
    held to a Chinese unit (``3<glue>个``, ``20<glue>摄氏度``) is one token, and
    so is a path that has Chinese in it: it is not cut between characters."""
    start = 0
    for found in _PATH_RUN.finditer(text):
        if _is_wide_path(found.group()):
            yield from _word_tokens(text[start : found.start()])
            yield found.group()
            start = found.end()
    yield from _word_tokens(text[start:])


def _word_tokens(text: str) -> Iterator[str]:
    """Spaces, Latin words and single wide characters, in order."""
    buffer, kind = "", ""
    skip = 0
    for index, char in enumerate(text):
        if skip:
            skip -= 1
            continue
        if char.isspace() and char != GLUE:
            this = "space"
        elif char_width(char) == 2:
            if buffer.endswith(GLUE):
                unit = _CJK_UNIT_AT.match(text, index)
                piece = unit.group() if unit else char
                skip = len(piece) - 1
                yield buffer + piece
            else:
                if buffer:
                    yield buffer
                yield char
            buffer, kind = "", ""
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


def _is_word_char(text: str) -> bool:
    """One wide character that is part of a word (not punctuation): the first
    half of a two-character word such as 路径 can be kept with the second."""
    return (
        len(text) == 1
        and char_width(text) == 2
        and text not in _NO_LINE_START
        and text not in _NO_LINE_END
        and unicodedata.category(text).startswith("L")
    )


#: A note in full-width brackets this short (a default hint such as
#: ``（默认：10）``) is never broken across two lines when a line can hold it.
_HINT_WIDTH = 30


def _group(tokens: list[str], first: int, last: int) -> str:
    """``tokens[first:last]`` as one piece (a space between words is a blank)."""
    return "".join(
        " " if piece.isspace() and piece != GLUE else piece for piece in tokens[first:last]
    )


def _hold_hints(tokens: list[str], room: int) -> list[str]:
    """``tokens`` with each short full-width bracket group made one token."""
    held: list[str] = []
    index = 0
    while index < len(tokens):
        if tokens[index] == "（":
            end = index + 1
            while end < len(tokens) and tokens[end] not in ("（", "）"):
                end += 1
            if end < len(tokens) and tokens[end] == "）":
                # The marks that follow (，。) cannot start a line: they go
                # with the group, and the line must hold them too.
                stop = end + 1
                while stop < len(tokens) and tokens[stop] in _NO_LINE_START:
                    stop += 1
                group = _group(tokens, index, stop)
                if cell_width(_group(tokens, index, end + 1)) <= min(_HINT_WIDTH, room) and (
                    cell_width(group) <= room
                ):
                    held.append(group)
                    index = stop
                    continue
        held.append(tokens[index])
        index += 1
    return held


#: A number held to its unit (``110<glue>Hz``) inside one word.
_GLUED = re.compile(rf"[-+]?\d[\d.,]*{GLUE}[A-Za-z°%\u3400-\u9fff]+")


def _whole_number(piece: str, head: str) -> str:
    """``head``, the part of ``piece`` that fits a line, without the number
    whose unit (held to it by :data:`GLUE`) the cut would part from it: a word
    longer than the line is cut where it must be, but never inside ``110 Hz``."""
    cut = len(head)
    for glued in _GLUED.finditer(piece):
        if glued.start() < cut < glued.end():
            return head[: glued.start()] or head
    return head


def wrap(text: str, width: int, *, first: str = "", rest: str | None = None) -> list[str]:
    """Plain ``text`` filled to ``width`` columns.

    ``first`` starts the first line and ``rest`` every following one (a
    hanging indent). Chinese text breaks between characters, Latin text at
    spaces; a word longer than a line is split. Explicit newlines are kept.

    A number stays on the line of its unit (:func:`glue_units`): paragraphs,
    status lines and fields are wrapped here, not only the at-a-glance rows.
    Closing punctuation does not start a line: the character before it goes
    down with it (and the one before that, when it is a closing character
    too, or when both are the two halves of a Chinese word). A short note in
    full-width brackets, a default hint such as ``（默认：10）``, is not broken
    across two lines. The last line is never a lone character.
    """
    rest = first if rest is None else rest
    text = glue_units(text)
    lines: list[str] = []
    for paragraph in text.split("\n"):
        start = len(lines)
        prefix = first if not lines else rest
        # The line as pieces: a token with the space before it, if any.
        parts: list[str] = []
        space = False
        room_of_a_line = max(1, width - max(cell_width(first), cell_width(rest)))
        tokens = _hold_hints(list(_tokens(paragraph)), room_of_a_line)
        for index, token in enumerate(tokens):
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
                # before it moves down with it, and a closing character
                # before that, and the first half of a two-character word.
                carry = parts.pop()
                while len(parts) > 1 and carry[0] in _NO_LINE_START:
                    carry = parts.pop() + carry
                if len(parts) > 1 and _is_word_char(carry[:1]) and _is_word_char(parts[-1]):
                    carry = parts.pop() + carry
            elif parts and not joiner and _is_word_char(token) and len(parts) > 1:
                # The line is full and the next one would start with one
                # character and a closing mark (路 / 径：): keep the word whole.
                after = tokens[index + 1] if index + 1 < len(tokens) else ""
                if after[:1] in _NO_LINE_START and after and _is_word_char(parts[-1]):
                    carry = parts.pop()
            # An opening bracket does not end a line: it moves down with
            # what it opens (and with the space after it, if any).
            while len(parts) > 1 and parts[-1][-1] in _NO_LINE_END:
                carry = parts.pop() + (carry or joiner)
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
                head = _whole_number(piece, head)
                lines.append(prefix + head)
                prefix, piece = rest, piece[len(head) :]
            parts = [piece]
        # A last line of one character (the second half of a word, or a
        # word and its closing mark) takes the character before it along.
        if (
            len(lines) > start
            and 0 < cell_width("".join(parts).rstrip("".join(_NO_LINE_START))) <= 2
        ):
            before = lines[-1]
            if len(before) > len(rest) + 1 and _is_word_char(before[-1]):
                lines[-1] = before[:-1]
                parts = [before[-1], *parts]
        lines.append(prefix + "".join(parts))
    return [line.replace(GLUE, " ") for line in lines]


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


def can_encode(text: str, encoding: str | None) -> bool:
    """Whether ``encoding`` (UTF-8 when unknown) can write ``text``."""
    try:
        text.encode(encoding or "utf-8")
    except (LookupError, UnicodeEncodeError):
        return False
    return True


@functools.lru_cache(maxsize=32)
def frames_writable(encoding: str) -> bool:
    """Whether ``encoding`` can write every glyph of the Unicode frames."""
    return can_encode(_FRAME_PROBE, encoding)


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


def use_boxes(
    style: StyleMode, interactive: bool, width: int, environ: Mapping[str, str] | None = None
) -> bool:
    """Whether to frame reports (see :data:`StyleMode`).

    ``--style boxed`` / ``plain`` decide; ``auto`` follows
    :data:`STYLE_VARIABLE`, else frames a terminal at least
    :data:`MIN_BOXED_WIDTH` columns wide and never a pipe or a file, whose
    text stays the stable ruled layout.
    """
    env = os.environ if environ is None else environ
    if style == "auto":
        asked = env.get(STYLE_VARIABLE, "").strip().lower()
        if asked in ("boxed", "plain"):
            style = asked  # type: ignore[assignment]
    if style == "boxed":
        return True
    if style == "plain":
        return False
    return interactive and width >= MIN_BOXED_WIDTH


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
    #: The stream's encoding, for text that is shown only where it can be written.
    encoding: str = "utf-8"
    #: Frames around titles, tables, findings and errors, rules through
    #: section headings (:data:`StyleMode`). A command or a path is never framed.
    boxed: bool = False

    @classmethod
    def for_stream(
        cls,
        stream: TextIO,
        mode: ColorMode = "auto",
        environ: Mapping[str, str] | None = None,
        style: StyleMode = "auto",
    ) -> Console:
        env = os.environ if environ is None else environ
        interactive = _isatty(stream) and env.get("TERM") != "dumb"
        width = terminal_width(stream, interactive, env)
        return cls(
            color=use_color(stream, mode, env),
            unicode=_unicode_ok(stream, interactive, env),
            width=width,
            interactive=interactive,
            encoding=getattr(stream, "encoding", None) or "utf-8",
            boxed=use_boxes(style, interactive, width, env),
        )

    def inner(self) -> Console:
        """How the body of a card is laid out: four columns narrower, for the
        sides and their padding. Its text reads like the rest of the output
        (the same marks and separators); it does not draw frames itself."""
        return replace(self, width=max(1, self.width - 4))

    def can_write(self, text: str) -> bool:
        """Whether the stream's encoding holds every character of ``text``."""
        return can_encode(text, self.encoding)

    @property
    def unicode_frames(self) -> bool:
        """Whether frames are drawn with box glyphs (``╭─╮``): the stream shows
        Unicode and its encoding writes every glyph of them; otherwise the
        frames are ASCII (``+-+``), though the symbols may stay Unicode."""
        return self.unicode and frames_writable(self.encoding)

    def readable(self, text: str) -> str:
        """Text as this stream will show it, before its width is measured.

        Control characters are shown as escapes (:func:`printable`), our
        colour codes kept only where this stream gets colour; a
        :class:`Verbatim` value stays on its one line. :meth:`fit` still
        translates anything left. Doing it here keeps a narrow encoding
        (``Δ`` becomes ``delta``) from running past the width the line was
        wrapped to.
        """
        if not text:
            return text
        shown = printable(text, single_line=isinstance(text, Verbatim), own_styles=self.color)
        if not self.unicode:
            shown = self._ascii(str(shown))
        elif self.boxed and not self.unicode_frames:
            shown = str(shown).replace("|Δ|", "abs(delta)")  # not two more sides
        return Verbatim(shown) if isinstance(text, Verbatim) else shown

    def _ascii(self, text: str) -> str:
        """``text`` with the signs this stream cannot show in ASCII."""
        if self.boxed:
            # "|" is the side of an ASCII frame: a separator inside one is "/",
            # and |Δ| (the size of a change) is not drawn as two more sides.
            text = text.replace("·", "/").replace("|Δ|", "abs(delta)")
        text = text.translate(_ASCII_SIGNS)
        if _DEGREE in text and not self.can_write(_DEGREE):
            text = text.replace(_DEGREE, "")
        if (self.boxed or self.interactive) and not self.can_write(text.replace(GLUE, " ")):
            # What the encoding cannot write is replaced by one "?" however
            # wide the character is, and a frame's sides, a table's columns
            # would come out ragged: one "?" per column keeps them straight.
            # A pipe or a file keeps the stream's own "?" (its text has no
            # frames to keep straight). The glue between a number and its
            # unit is not text: fit() writes a space.
            text = "".join(
                char if char == GLUE or self.can_write(char) else "?" * max(1, char_width(char))
                for char in text
            )
        return text

    # Styles -----------------------------------------------------------------

    def style(self, text: str, *names: str) -> str:
        if not self.color or not names or not text:
            return text
        codes = ";".join(_SGR[name] for name in names)
        return f"\x1b[{codes}m{text}\x1b[0m"

    def bold(self, text: str) -> str:
        return self.style(text, "bold")

    def muted(self, text: str) -> str:
        """Secondary text (a note, a label, a description): not styled. Dim
        text is too faint on many colour schemes and these words carry
        information; only decoration is dimmed (:meth:`faint`)."""
        return text

    def faint(self, text: str) -> str:
        """Decoration (rules, borders, the rest of a progress bar), dimmed."""
        return self.style(text, "dim")

    def accent(self, text: str) -> str:
        return self.style(text, "cyan")

    def _marked(self, glyph: str, *names: str) -> str:
        """A mark in ``names``; one that is a letter (the ASCII ``[OK]``, ``x``,
        ``i``) is bold instead: coloured letters are hard to read."""
        if any(char.isalnum() for char in glyph):
            return self.style(glyph, "bold")
        return self.style(glyph, *names)

    def symbol(self, status: Status) -> str:
        glyph, ascii_form = _SYMBOLS[status]
        if status == "error" and self.boxed:
            # One glyph for a failure on a framed screen: the badge of a table
            # and the title of a card have ``✗`` (one column everywhere); the
            # ``×`` of the unframed lines may be drawn two columns wide by a CJK
            # terminal and does not sit well beside them.
            glyph = self.mark("error") if self.unicode and self.can_write("✗") else glyph
        return self._marked(glyph if self.unicode else ascii_form, *_STATUS_STYLE[status])

    def mark(self, status: Status) -> str:
        """The one-column mark of a badge, unstyled; its ASCII form where the
        stream cannot write the glyph."""
        glyph, ascii_form = _MARKS[status]
        return glyph if self.unicode and self.can_write(glyph) else ascii_form

    def badge(self, status: Status, word: str | None = None) -> str:
        """``✓ good``, ``! check``, ``✗ problem``: the mark, coloured, and the
        word (``word``, else the status's own), bold. Colour is only ever on
        the mark: a letter or a digit coloured yellow or green cannot be read
        on a light background."""
        mark = self._marked(self.mark(status), *_STATUS_STYLE[status])
        word = self.readable(badge_word(status) if word is None else word)
        return f"{mark} {self.bold(word)}" if word else mark

    def fit(self, text: str) -> str:
        """``text`` as this stream can write it: typographic signs become ASCII
        where the encoding cannot hold them (see :data:`_ASCII_SIGNS`)."""
        text = text.replace(GLUE, " ")
        return text if self.unicode else self._ascii(text)

    def arrow(self) -> str:
        return "→" if self.unicode else "->"

    def command(self, text: str) -> str:
        """A command to copy: bold, and never wrapped."""
        return self.bold(text)

    def rule_char(self) -> str:
        return "─" if self.unicode else "-"

    def meter(self, fraction: float, size: int) -> str:
        """A progress bar ``size`` columns wide: ``━━━━╸────`` (the part done
        in the accent colour, the rest dim), green when full; ``====>----``
        where the stream cannot write the glyphs. The head shows where the
        bar stands without colour."""
        done_glyph, head, rest = _METER[self.unicode]
        if self.unicode and not self.can_write(head):
            head = done_glyph
        size = max(1, size)
        if fraction >= 1.0:
            return self.style(done_glyph * size, "green")
        done = min(size - 1, max(0, int(size * fraction)))
        return self.accent(done_glyph * done + head) + self.faint(rest * (size - done - 1))

    def dash(self) -> str:
        """The mark for a value that is not there."""
        return "—" if self.unicode else "-"

    def sep(self) -> str:
        """Separator between short facts on one line."""
        if self.unicode:
            return " · "
        # "|" is the side of an ASCII frame.
        return " / " if self.boxed else " | "

    # Blocks -------------------------------------------------------------------

    def title(self, text: str) -> list[str]:
        """A command's heading: the title and a rule as wide as it, or, boxed,
        the title in a panel as wide as the terminal."""
        text = self.readable(text)
        if not self.boxed:
            # A title wider than the terminal wraps, its rule as wide as the longest line.
            heads = wrap(text, self.width) or [""]
            rule = self.rule_char() * max(cell_width(head) for head in heads)
            return [*(self.bold(head) for head in heads), self.faint(rule)]
        left, top, right, side, bottom_left, bottom_right = _PANEL[self.unicode_frames]
        inner = max(1, self.width - 4)
        lines = wrap(text, inner) or [""]
        out = [self.faint(left + top * (inner + 2) + right)]
        for line in lines:
            out.append(
                self.faint(side) + " " + pad(self.bold(line), inner) + " " + self.faint(side)
            )
        out.append(self.faint(bottom_left + top * (inner + 2) + bottom_right))
        return out

    def frame(
        self,
        title: str,
        lines: Sequence[str],
        tone: Tone = "accent",
        *,
        mark: Status | None = None,
    ) -> list[str] | None:
        """A card: ``lines`` (laid out by :meth:`inner`) in a rounded frame as
        wide as the console, with ``title`` in its top border. The border and
        ``mark`` (the status mark in front of the title, if any) are coloured
        by ``tone``, the title is bold. ``╭─ ! Notice · reverberation ──╮``

        ``None`` without frames, or when the title or a line is wider than the
        frame holds (a path is never cut): the caller lays the text out
        unframed. A command or a path to copy never goes inside: the caller
        prints it bare, after the card.
        """
        if not self.boxed:
            return None
        room = self.width - 4
        title = self.readable(title)
        lead = self.mark(mark) + " " if mark else ""
        fill = self.width - 5 - cell_width(lead) - cell_width(title)
        if room < 1 or fill < 1 or any(cell_width(line) > room for line in lines):
            return None
        left, top, right, side, bottom_left, bottom_right = _PANEL[self.unicode_frames]
        tone_style = _TONE_STYLE[tone]
        head = self._marked(lead.rstrip(), *tone_style) + " " if mark else ""
        edge = self.style(side, *tone_style)
        return [
            self.style(left + top, *tone_style)
            + " "
            + head
            + self.bold(title)
            + " "
            + self.style(top * fill + right, *tone_style),
            *(f"{edge} {pad(line, room)} {edge}" for line in lines),
            self.style(bottom_left + top * (self.width - 2) + bottom_right, *tone_style),
        ]

    def section(self, text: str, note: str = "") -> list[str]:
        """A blank line and a section heading, bold, with an optional note;
        boxed, the heading sits in a rule across the terminal. A heading wider
        than the terminal wraps, without the rule."""
        text = self.readable(text)
        note = self.readable(note) if note else ""
        rule = self.rule_char()
        if self.boxed and cell_width(text) + 5 <= self.width:
            lead = self.faint(rule * 2) + " " + self.bold(text) + " "
            tail = self.width - cell_width(text) - 4
            out = ["", lead + self.faint(rule * tail)]
            if note:
                out += self.paragraph(note)
            return out
        heads = [self.bold(line) for line in wrap(text, self.width)]
        if not note:
            return ["", *heads]
        if len(heads) == 1 and cell_width(text) + 2 + cell_width(note) <= self.width:
            return ["", heads[0] + "  " + note]
        return ["", *heads, *self.paragraph(note)]

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
                out += wrap(text, self.width, first=margin + "  ")
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
                out += wrap(label, self.width, first=margin)
                out += _styled_wrap(value, plain, styled, self.width, margin + "  ")
                continue
            head = margin + pad(label, label_width) + "  "
            if cell_width(label) > label_width:
                out += wrap(label, self.width, first=margin)
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

        if self.boxed and indent + sum(w + 3 for w in widths) + 1 <= self.width:
            return self._grid(headers, rows, widths, align, margin)
        rule = [self.faint(self.rule_char() * width) for width in widths]
        return [line([self.bold(h) for h in headers]), line(rule), *(line(row) for row in rows)]

    def framed_table(
        self,
        headers: Sequence[str],
        rows: Sequence[Sequence[str]],
        *,
        align: str = "",
        indent: int = 2,
        wrap_column: int | None = None,
        expand: bool = False,
        min_widths: Sequence[int] = (),
    ) -> list[str] | None:
        """Rows in a bordered grid, or ``None`` when no grid is drawn.

        A grid is drawn only with frames (:attr:`boxed`) and when it fits the
        console; the caller then lays the rows out another way. Cells may be
        styled. The text of ``wrap_column`` (the last column unless given)
        wraps inside its column when the grid would be wider than the console,
        down to :data:`_WRAP_FLOOR` columns, and ``expand`` widens that column
        so the grid's right border sits on the console's last column, under the
        title panel's. ``min_widths`` holds a column at least that wide, so
        that tables shown one under the other keep their first border in
        step. A cell that cannot wrap (a path, or an unbreakable word wider
        than the column) makes the grid give up rather than cut it.
        """
        if not self.boxed or not rows:
            return None
        headers = [self.readable(header) for header in headers]
        rows = [[self.readable(cell) for cell in row] for row in rows]
        widths = [cell_width(header) for header in headers]
        for row in rows:
            for index, cell in enumerate(row):
                widths[index] = max(widths[index], cell_width(cell))
        for index, least in enumerate(min_widths):
            widths[index] = max(widths[index], least)
        columns = len(widths)
        align = (align or "l" * columns).ljust(columns, "l")
        flex = columns - 1 if wrap_column is None else wrap_column
        spare = self.width - (indent + sum(widths) + 3 * columns + 1)
        if spare < 0:
            # The wrapping column narrows, down to a readable width.
            least = max(min(widths[flex], _WRAP_FLOOR), cell_width(headers[flex]))
            shrunk = max(0, min(-spare, widths[flex] - least))
            widths[flex] -= shrunk
            spare += shrunk
        if spare < 0:
            return None
        if expand:
            widths[flex] += spare

        def lines_of(cells: Sequence[str]) -> list[list[str]] | None:
            """One row of cells as display lines; ``None`` when one cannot wrap."""
            split: list[list[str]] = []
            for index, cell in enumerate(cells):
                if cell_width(cell) <= widths[index]:
                    split.append([cell])
                    continue
                if isinstance(cell, Verbatim):
                    return None
                wrapped = wrap(strip_ansi(cell), widths[index])
                if any(cell_width(line) > widths[index] for line in wrapped):
                    return None  # an unbreakable word inside the text
                # Wrapping works on bare text: a coloured mark in front of it
                # (the overview without its status column) keeps its colour.
                lead = _LEADING_STYLE.match(cell)
                if lead and wrapped[0].startswith(lead["text"]):
                    wrapped[0] = lead[0] + wrapped[0][len(lead["text"]) :]
                split.append(wrapped)
            height = max(len(lines) for lines in split)
            return [[lines[k] if k < len(lines) else "" for lines in split] for k in range(height)]

        body: list[list[str]] = []
        for row in rows:
            row_lines = lines_of(row)
            if row_lines is None:
                return None
            body += row_lines
        for index, width in enumerate(widths):
            if any(cell_width(row[index]) > width for row in rows):
                align = align[:index] + "l" + align[index + 1 :]  # wrapped text reads left
        return self._grid(headers, body, widths, align, " " * indent)

    def _grid(
        self,
        headers: Sequence[str],
        rows: Sequence[Sequence[str]],
        widths: Sequence[int],
        align: str,
        margin: str,
    ) -> list[str]:
        """The bordered form of :meth:`table`: one space of padding in every cell."""
        g = _GRID[self.unicode_frames]
        bar = self.faint(g["v"])

        def rule(left: str, middle: str, right: str) -> str:
            return margin + self.faint(left + middle.join(g["h"] * (w + 2) for w in widths) + right)

        def row_line(cells: Sequence[str]) -> str:
            parts = [
                " " + pad(cell, widths[i], "right" if align[i] == "r" else "left") + " "
                for i, cell in enumerate(cells)
            ]
            return margin + bar + bar.join(parts) + bar

        return [
            rule(g["tl"], g["t"], g["tr"]),
            row_line([self.bold(h) for h in headers]),
            rule(g["l"], g["x"], g["r"]),
            *(row_line(row) for row in rows),
            rule(g["bl"], g["b"], g["br"]),
        ]


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
        text = self.line(fraction, width)
        visible = cell_width(text)
        # Wipe what a longer earlier line left, but never past the last
        # column: a terminal that was made narrower would wrap the blanks.
        wipe = max(0, min(self._drawn, width) - visible)
        self.stream.write("\r" + text + " " * wipe)
        self.stream.flush()
        self._drawn = visible

    def line(self, fraction: float, width: int) -> str:
        """The line at ``fraction``, never wider than ``width`` columns:
        ``  label  ━━━━╸────  42%  00:04 / 00:09``. A narrow terminal loses
        the bar first, then the clock; the label is cut short, and gives way
        last, never the percentage."""
        c = self.console
        percent = f"{fraction * 100:3.0f}%"
        timing = f"{clock(fraction * self.total_s)} / {clock(self.total_s)}"
        ellipsis = "…" if c.unicode else "..."
        label = c.readable(self.label)
        pct, clk = cell_width(percent), cell_width(timing)
        # Every part is preceded by two spaces: "  label  bar  percent  timing".
        # One column too many and a terminal wraps the line, so each redraw
        # lands on a new row instead of over the last one. With a bar the
        # label keeps at most half of the line.
        shown = truncate(label, max(8, width // 2), ellipsis)
        size = min(32, width - cell_width(shown) - pct - clk - 8)
        if size >= 10:
            return f"  {shown}  {c.meter(fraction, size)}  {percent}  {timing}"
        # No bar: the label takes what the numbers leave.
        room = width - pct - clk - 6
        if room >= 8:
            return f"  {truncate(label, room, ellipsis)}  {percent}  {timing}"
        room = width - pct - 4
        if room >= 4:
            return f"  {truncate(label, room, ellipsis)}  {percent}"
        return f"  {percent}"

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
