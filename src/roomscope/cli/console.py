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
* **Frames** (panels and bordered tables) are on for the command line and
  off for the desktop app's report panes and :mod:`roomscope.cli.report`
  (:attr:`Console.frames`). ``ROOMSCOPE_CLI_STYLE=plain`` turns them off for
  a terminal that draws the ambiguous-width box glyphs two columns wide
  (some CJK fonts and locales); below :data:`FRAME_MIN_WIDTH` columns they
  are off anyway. Every line of a frame has the same display width, and a
  line that holds a command to copy never carries a border.
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
from dataclasses import dataclass, replace
from typing import Literal, TextIO

from roomscope.i18n import pgettext

ColorMode = Literal["auto", "always", "never"]
COLOR_MODES: tuple[ColorMode, ...] = ("auto", "always", "never")

#: ``boxed`` draws panels and bordered tables; ``plain`` lays the same text
#: out without them (the layout the desktop app's report panes use).
CliStyle = Literal["boxed", "plain"]
CLI_STYLES: tuple[CliStyle, ...] = ("boxed", "plain")
#: Chooses the style for one shell, before the stored setting.
ENV_STYLE = "ROOMSCOPE_CLI_STYLE"
#: Narrower than this, frames are off: a border takes four columns of a line
#: that is already short.
FRAME_MIN_WIDTH = 40

#: Status kinds; each has a symbol, an ASCII fallback and a colour.
Status = Literal["ok", "warn", "error", "info", "skip", "unsure", "next"]
#: The colour of a panel's border.
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

#: SGR parameters. Kept to a restrained palette: bold for structure, colour
#: only on marks, bars and borders (a letter or a digit is never coloured:
#: yellow, green and cyan text is unreadable on a light background, dim text
#: on a dark or a light one), and dim for decoration alone.
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

#: One-column marks for a badge (``✓ good``) and a panel title (``✗ Error``).
#: ``✗`` rather than ``×`` for an error: ``×`` is ambiguous-width, ``✗`` is
#: one column everywhere. ASCII forms for a stream that cannot write them.
_MARKS: dict[str, tuple[str, str]] = {
    "ok": ("✓", "+"),
    "warn": ("!", "!"),
    "error": ("✗", "x"),
    "info": ("i", "i"),
    "skip": ("–", "-"),
    "unsure": ("?", "?"),
    "next": ("→", ">"),
}

#: Frame glyphs, Unicode then ASCII. A panel: its corners (top left, top
#: right, bottom left, bottom right), its rule and its side.
_PANEL = (tuple("╭╮╰╯─│"), tuple("++++-|"))
#: A table: the junctions of its top, middle and bottom rules (left, inner,
#: right), its rule and its side.
_GRID = (tuple("┌┬┐├┼┤└┴┘─│"), tuple("+++++++++-|"))
#: A table's heavier header: its top junctions, rule and side, then the
#: junctions of the rule under it (heavy above, light below).
_HEAD = (tuple("┏┳┓━┃┡╇┩"), tuple("+++=|+++"))
#: The section bar, Unicode then ASCII.
_BAR = ("▌", "> ")
#: The progress bar: the part done, its head and the part to come; Unicode,
#: then ASCII (also the plain style's, whose terminal may draw ``━`` wide).
_METER = (("━", "╸", "─"), ("=", ">", "-"))
#: What a stream must be able to write for the Unicode frames.
_FRAME_PROBE = "╭╮╰╯─│┌┬┐├┼┤└┴┘┏┳┓━┃┡╇┩▌╸✗"

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
        "✗": "x",
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

#: Characters a line should not start with (closing punctuation, CJK and
#: Latin); a wrap lets them hang one step past the margin instead.
_NO_LINE_START = frozenset("，。、；：！？）」』”’》〉】〕,.;:!?)]}%")
#: Characters a line should not end with (opening brackets and quotes); a
#: wrap carries them down with what they open.
_NO_LINE_END = frozenset("（「『“‘《〈【〔([{")

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
_UNIT = re.compile(r"(\d) (dBFS|dB|kHz|Hz|ms|s|m|°C|%)(?![\w])")


def glue_units(text: str) -> str:
    """``110 Hz (+11.3 dB)`` with each number held to its unit."""
    return _UNIT.sub(lambda match: match.group(1) + GLUE + match.group(2), text)


def _windows_cmdline_arg(text: str) -> str:
    """One argv element quoted the way ``cmd.exe`` parses it.

    Same rules as ``subprocess.list2cmdline`` for a single argument. Inlined
    because ``src/`` may not import ``subprocess`` (that module is for
    launching processes; this only prints a command the user can copy).
    """
    # A space, a tab, an empty argument or a character cmd.exe reads as an
    # operator (``&``, ``(``) needs quotes. A quote is escaped either way.
    needs_quotes = (not text) or any(char in text for char in " \t&|<>()^;")
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


#: A whole argument that is an instruction for the reader (``<take.wav>``),
#: not a value: printed bare, as the help does.
_PLACEHOLDER = re.compile(r"<[\w.-]+>")
#: What a POSIX shell passes through untouched (letters and digits of any
#: script, so a Chinese name stays readable): anything else gets quotes.
_SHELL_SAFE = re.compile(r"[\w@%+=:,./-]+")


def _needs_quotes(text: str, windows: bool) -> bool:
    if _PLACEHOLDER.fullmatch(text):
        return False
    if windows:
        return any(char.isspace() or char in "\"'&|<>()^;" for char in text)
    # ``~`` and ``#`` are special only at the start, ``=`` only to zsh.
    return not _SHELL_SAFE.fullmatch(text) or text[0] in "~#="


def shell_command(argv: Iterable[str]) -> str:
    """One copy-paste command. An argument a shell would read as more than a
    word (a space, a quote, ``( ) & ; $ * ? | < > #``, a leading ``~``) is quoted.

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
        if not _needs_quotes(text, windows):
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


def wrap(
    text: str, width: int, *, first: str = "", rest: str | None = None, hang: int = 0
) -> list[str]:
    """Plain ``text`` filled to ``width`` columns.

    ``first`` starts the first line and ``rest`` every following one (a
    hanging indent). Chinese text breaks between characters, Latin text at
    spaces; a word longer than a line is split. Explicit newlines are kept.

    A number is never parted from its unit (``2.4 ms``, see
    :func:`glue_units`). Closing punctuation does not start a line: the
    character before it goes down with it (and the one before that, when it
    is a closing character too, or when both are the two halves of a Chinese
    word). With ``hang`` columns to spare (a prompt, which has room at the
    right edge for the answer) closing punctuation stays on the line instead.
    The last line is never a lone character.
    """
    rest = first if rest is None else rest
    lines: list[str] = []
    for paragraph in text.split("\n"):
        paragraph = glue_units(paragraph)
        start = len(lines)
        prefix = first if not lines else rest
        # The line as pieces: a token with the space before it, if any.
        parts: list[str] = []
        space = False
        tokens = list(_tokens(paragraph))
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
                if len(parts) == 1 or cell_width("".join(parts) + token) <= room + hang:
                    parts.append(token)  # nothing to carry (or room to spare): let it hang
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

    A windowed desktop bundle (``roomscope-gui``) runs with ``sys.stdout``
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


def cli_style(setting: str = "", environ: Mapping[str, str] | None = None) -> CliStyle:
    """The style in effect: ``ROOMSCOPE_CLI_STYLE``, then ``setting`` (the
    user's stored choice, if any), then ``boxed``. A value neither of them
    knows is passed over."""
    env = os.environ if environ is None else environ
    for value in (env.get(ENV_STYLE, ""), setting):
        word = value.strip().lower()
        if word in CLI_STYLES:
            return word
    return "boxed"


@functools.lru_cache(maxsize=16)
def _frames_writable(encoding: str) -> bool:
    return can_encode(_FRAME_PROBE, encoding)


def status_word(kind: Status) -> str:
    """The word a badge shows next to its mark (``✓ good``); empty for ``next``."""
    return {
        "ok": pgettext("status", "good"),
        "warn": pgettext("status", "check"),
        "error": pgettext("status", "problem"),
        "info": pgettext("status", "note"),
        "skip": pgettext("status", "no data"),
        "unsure": pgettext("status", "unsure"),
    }.get(kind, "")


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
    #: Panels and bordered tables. The command line turns them on
    #: (:meth:`for_stream`); off, the same text is laid out without them, as
    #: in the desktop app's report panes. :attr:`boxed` says whether they are
    #: drawn.
    frames: bool = False

    @classmethod
    def for_stream(
        cls,
        stream: TextIO,
        mode: ColorMode = "auto",
        environ: Mapping[str, str] | None = None,
        *,
        style: str = "",
    ) -> Console:
        """The console for ``stream``. ``style`` is the user's stored choice,
        if any (``boxed`` or ``plain``); ``ROOMSCOPE_CLI_STYLE`` decides first."""
        env = os.environ if environ is None else environ
        interactive = _isatty(stream) and env.get("TERM") != "dumb"
        width = terminal_width(stream, interactive, env)
        return cls(
            color=use_color(stream, mode, env),
            unicode=_unicode_ok(stream, interactive, env),
            width=width,
            interactive=interactive,
            encoding=getattr(stream, "encoding", None) or "utf-8",
            frames=cli_style(style, env) == "boxed" and width >= FRAME_MIN_WIDTH,
        )

    @property
    def boxed(self) -> bool:
        """Whether frames are drawn: asked for, with room for them."""
        return self.frames and self.width >= FRAME_MIN_WIDTH

    def inner(self) -> Console:
        """How a panel's body is laid out: four columns narrower (the sides
        and their padding). Its text reads like the rest of the output (the
        same marks and separators); it is not meant to draw frames itself."""
        return replace(self, width=self.width - 4)

    def _glyphs(self) -> int:
        """0 for the Unicode frame glyphs, 1 for their ASCII forms."""
        return 0 if self.unicode and _frames_writable(self.encoding) else 1

    def can_write(self, text: str) -> bool:
        """Whether the stream's encoding holds every character of ``text``."""
        return can_encode(text, self.encoding)

    def readable(self, text: str) -> str:
        """Text as this stream will show it, before its width is measured.

        :meth:`fit` still translates anything left. Doing it here keeps a
        narrow encoding (``Δ`` becomes ``delta``) from running past the width
        the line was wrapped to.
        """
        if self.unicode or not text:
            return text
        shown = self._ascii(str(text))
        return Verbatim(shown) if isinstance(text, Verbatim) else shown

    def _ascii(self, text: str) -> str:
        """``text`` with the signs this stream cannot show in ASCII."""
        if self.frames:
            # "|" is the side of an ASCII frame: a separator inside one is "/".
            text = text.replace("·", "/")
        text = text.translate(_ASCII_SIGNS)
        if _DEGREE in text and not self.can_write(_DEGREE):
            text = text.replace(_DEGREE, "")
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
        text is too faint on many colour schemes, and these words carry
        information; only decoration is dimmed (:meth:`faint`)."""
        return text

    def faint(self, text: str) -> str:
        """Decoration (rules, borders, the rest of a progress bar), dimmed."""
        return self.style(text, "dim")

    def accent(self, text: str) -> str:
        return self.style(text, "cyan")

    def symbol(self, status: Status) -> str:
        glyph, ascii_form = _SYMBOLS[status]
        if status == "error" and self.frames:
            glyph = _MARKS["error"][0]  # one column wide, like the frames
        return self.style(glyph if self.unicode else ascii_form, *_STATUS_STYLE[status])

    def mark(self, status: Status) -> str:
        """The one-column mark of a badge or a panel title, unstyled."""
        glyph, ascii_form = _MARKS[status]
        return glyph if self.unicode else ascii_form

    def badge(self, status: Status) -> str:
        """``✓ good``, ``! check``, ``✗ problem``: the mark, coloured, and the
        word, bold in the colour of the text."""
        mark = self.style(self.mark(status), *_STATUS_STYLE[status])
        word = self.readable(status_word(status))
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
        """A progress bar ``size`` columns wide: ``━━━━╸────`` (accent, then
        muted), green when full; ``====>----`` where the stream cannot write
        it or the style is plain. The head shows where the bar stands without
        colour."""
        glyphs = _METER[0 if self.frames and self._glyphs() == 0 else 1]
        done_glyph, head, rest = glyphs
        if fraction >= 1.0:
            return self.style(done_glyph * size, "green")
        done = min(size - 1, max(0, int(size * fraction)))
        return self.style(done_glyph * done + head, "cyan") + self.faint(rest * (size - done - 1))

    def dash(self) -> str:
        """The mark for a value that is not there."""
        return "—" if self.unicode else "-"

    def sep(self) -> str:
        """Separator between short facts on one line."""
        if self.unicode:
            return " · "
        return " / " if self.frames else " | "

    # Blocks -------------------------------------------------------------------

    def title(
        self,
        text: str,
        facts: Iterable[tuple[str, str]] = (),
        *,
        body: Callable[[Console, int], list[str]] | None = None,
        tone: Tone = "accent",
    ) -> list[str]:
        """A command's heading, with the facts it ran on.

        With frames: a panel with ``text`` in its top border, holding
        ``facts`` as aligned fields, then the lines ``body(console, indent)``
        lays out for it. A fact that is a path too long for the panel is
        never cut: it follows the panel, bare (a path to copy), under the
        same labels. Without frames (or when a line of the body is too wide
        for the panel): the title, a rule as wide as it and, when there is
        more, a blank line, the facts and the body at an indent of 2.
        """
        text = self.readable(text)
        facts = list(facts)
        if self.boxed:
            inner = self.inner()
            label = max((cell_width(self.readable(name)) for name, _value in facts), default=0)
            held: list[tuple[str, str]] = []
            spilled: list[tuple[str, str]] = []
            for name, value in facts:
                room = inner.width - min(label, 28) - 2
                too_long = isinstance(value, Verbatim) and cell_width(self.readable(value)) > room
                (spilled if too_long else held).append((name, value))
            content = inner.fields(held, indent=0, min_label=label)
            if body is not None:
                content += body(inner, 0)
            framed = (
                self.frame(text, content, tone)
                if content
                else self.frame("", [inner.bold(text)], tone)
            )
            if framed is not None:
                return framed + self.fields(spilled, min_label=label)
        lines = [self.bold(text), self.faint(self.rule_char() * cell_width(text))]
        if facts or body is not None:
            lines.append("")
            lines += self.fields(facts)
            if body is not None:
                lines += body(self, 2)
        return lines

    def frame(self, title: str, lines: Sequence[str], tone: Tone = "accent") -> list[str] | None:
        """``lines`` (laid out by :meth:`inner`) in a rounded frame with
        ``title`` in its top border, the border coloured by ``tone``.

        ``None`` without frames, or when the title or a line is wider than
        the frame holds (a path is never cut): the caller lays the text out
        unframed.
        """
        if not self.boxed:
            return None
        room = self.width - 4
        if any(cell_width(line) > room for line in lines):
            return None
        top_left, top_right, bottom_left, bottom_right, rule, side = _PANEL[self._glyphs()]
        tone_style = _TONE_STYLE[tone]
        title = self.readable(title)
        if cell_width(title) > self.width - 6:
            return None  # a title is never cut either
        if title:
            fill = self.width - 5 - cell_width(title)
            top = (
                self.style(top_left + rule, *tone_style)
                + " "
                + self.bold(title)
                + " "
                + self.style(rule * fill + top_right, *tone_style)
            )
        else:
            top = self.style(top_left + rule * (self.width - 2) + top_right, *tone_style)
        edge = self.style(side, *tone_style)
        body = [f"{edge} {pad(line, room)} {edge}" for line in lines]
        bottom = self.style(bottom_left + rule * (self.width - 2) + bottom_right, *tone_style)
        return [top, *body, bottom]

    def panel(self, title: str, lines: Sequence[str], tone: Tone = "accent") -> list[str]:
        """:meth:`frame`, or without frames the title in bold and ``lines``
        at an indent of 2."""
        framed = self.frame(title, lines, tone)
        if framed is not None:
            return framed
        head = [self.bold(self.readable(title))] if title else []
        return head + [("  " + line) if line else line for line in lines]

    def section(self, text: str, note: str = "") -> list[str]:
        """A blank line and a section heading, with an optional muted note.

        With frames the heading starts with a coloured bar (``▌``, ASCII
        ``> ``).
        """
        text = self.readable(text)
        note = self.readable(note) if note else ""
        if self.boxed:
            bar = _BAR[self._glyphs()]
            head = self.style(bar, "cyan") + self.bold(text)
            text = bar + text
        else:
            head = self.bold(text)
        if not note:
            return ["", head]
        if cell_width(text) + 2 + cell_width(note) <= self.width:
            return ["", head + "  " + note]
        return ["", head, *self.paragraph(note)]

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
                out.append(margin + label)
                out += _styled_wrap(value, plain, styled, self.width, margin + "  ")
                continue
            head = margin + pad(label, label_width) + "  "
            if cell_width(label) > label_width:
                out.append(margin + label)
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
        """Whether :meth:`table` would lay these rows out as a table (not
        blocks); with frames, as a bordered table."""
        if self.boxed:
            return self.framed_table(headers, rows) is not None
        return self._fits_unframed(_column_widths(headers, rows), indent, gap)

    def _fits_unframed(self, widths: Sequence[int], indent: int, gap: int) -> bool:
        return indent + sum(widths) + gap * (len(widths) - 1) <= self.width

    def framed_table(
        self,
        headers: Sequence[str],
        rows: Sequence[Sequence[str]],
        *,
        align: str = "",
        wrap_column: int | None = None,
        expand: bool = False,
    ) -> list[str] | None:
        """Rows in a bordered grid under a heavier header row; no header row
        when ``headers`` is empty.

        Cells may be styled. The text of ``wrap_column`` wraps inside its
        column when the grid would be wider than the console; ``expand``
        widens that column (else the last) to the full width. ``None``
        without frames, or when the grid does not fit even so (a path is
        never cut): the caller lays the rows out another way.
        """
        if not self.boxed or not rows:
            return None
        headers = [self.readable(header) for header in headers]
        rows = [[self.readable(cell) for cell in row] for row in rows]
        cell_widths = _column_widths([], rows)
        widths = _column_widths(headers, rows)
        columns = len(widths)
        align = (align or "l" * columns).ljust(columns, "l")
        flex = columns - 1 if wrap_column is None else wrap_column
        spare = self.width - (sum(widths) + 3 * columns + 1)
        shrunk = 0
        if spare < 0 and wrap_column is not None:
            # The wrapping column narrows first, down to a readable width.
            least = min(widths[flex], _WRAP_FLOOR)
            if headers:
                least = max(least, cell_width(headers[flex]))
            shrunk = max(0, min(-spare, widths[flex] - least))
            widths[flex] -= shrunk
            spare += shrunk
        if spare < 0 and headers:
            # Then a header wider than its cells goes on two lines, the one
            # that saves most first.
            def narrow(index: int) -> int:
                header = headers[index]
                return max(
                    cell_widths[index],
                    max((cell_width(token) for token in _tokens(header)), default=0),
                    -(-cell_width(header) // 2),
                )

            savings = sorted(
                ((widths[i] - narrow(i), i) for i in range(columns) if i != wrap_column),
                reverse=True,
            )
            for saving, index in savings:
                if spare >= 0 or saving <= 0:
                    break
                widths[index] -= saving
                spare += saving
        if spare < 0:
            return None
        widths[flex] += spare if expand else min(spare, shrunk)

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
                    return None  # a path inside the text
                split.append(wrapped)
            height = max(len(lines) for lines in split)
            return [[lines[k] if k < len(lines) else "" for lines in split] for k in range(height)]

        head = lines_of(headers) if headers else []
        body: list[list[str]] = []
        for row in rows:
            row_lines = lines_of(row)
            if head is None or row_lines is None:
                return None
            body += row_lines
        for index, width in enumerate(widths):
            if any(cell_width(row[index]) > width for row in rows):
                align = align[:index] + "l" + align[index + 1 :]  # wrapped text reads left

        glyphs = self._glyphs()
        (top_left, top_mid, top_right, _ml, _mm, _mr, low_left, low_mid, low_right, rule, side) = (
            _GRID[glyphs]
        )
        h_left, h_mid, h_right, h_rule, h_side, s_left, s_mid, s_right = _HEAD[glyphs]

        def border(left: str, mid: str, right: str, fill: str) -> str:
            return self.faint(left + mid.join(fill * (width + 2) for width in widths) + right)

        def line(cells: Sequence[str], edge: str) -> str:
            styled = self.faint(edge)
            parts = [
                " " + pad(cell, widths[i], "right" if align[i] == "r" else "left") + " "
                for i, cell in enumerate(cells)
            ]
            return styled + styled.join(parts) + styled

        out: list[str] = []
        if head:
            out.append(border(h_left, h_mid, h_right, h_rule))
            out += [line([self.bold(cell) for cell in cells], h_side) for cells in head]
            out.append(border(s_left, s_mid, s_right, h_rule))
        else:
            out.append(border(top_left, top_mid, top_right, rule))
        out += [line(cells, side) for cells in body]
        out.append(border(low_left, low_mid, low_right, rule))
        return out

    def grid(self, pairs: Iterable[tuple[str, str]]) -> list[str]:
        """``label  value`` rows: with frames a bordered grid without a
        header (the value wraps in its column), else :meth:`fields`."""
        items = list(pairs)
        if not items:
            return []
        framed = self.framed_table(
            [], [[self.readable(label), value] for label, value in items], wrap_column=1
        )
        return framed if framed is not None else self.fields(items)

    def table(
        self,
        headers: Sequence[str],
        rows: Sequence[Sequence[str]],
        *,
        align: str = "",
        indent: int = 2,
        gap: int = 3,
        title_columns: int = 1,
        wrap_column: int | None = None,
        expand: bool = False,
    ) -> list[str]:
        """A table with a ruled header; ``align`` has one ``l``/``r`` per column.

        Cells may be styled. With frames it is drawn in a bordered grid (see
        :meth:`framed_table`, which ``wrap_column`` and ``expand`` are for).
        When the table does not fit the width, every row becomes a small
        block (its first ``title_columns`` cells as the title, then ``header
        value`` pairs), so nothing runs off the right edge.
        """
        framed = self.framed_table(
            headers, rows, align=align, wrap_column=wrap_column, expand=expand
        )
        if framed is not None:
            return framed
        columns = len(headers)
        headers = [self.readable(header) for header in headers]
        rows = [[self.readable(cell) for cell in row] for row in rows]
        align = (align or "l" * columns).ljust(columns, "l")
        widths = _column_widths(headers, rows)
        margin = " " * indent
        if gap > 2 and not self._fits_unframed(widths, indent, gap):
            gap = 2  # a little tighter before giving up the table
        if not self._fits_unframed(widths, indent, gap):
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

        rule = [self.faint(self.rule_char() * width) for width in widths]
        return [line([self.bold(h) for h in headers]), line(rule), *(line(row) for row in rows)]


#: The narrowest a wrapping column of a bordered table gets before the table
#: is laid out another way.
_WRAP_FLOOR = 16


def _column_widths(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> list[int]:
    """Each column's display width: its widest cell, header included."""
    widths = [cell_width(header) for header in headers] or [0] * max(len(row) for row in rows)
    for row in rows:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], cell_width(cell))
    return widths


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
    but ``label`` and one closing line when the stream is not a terminal. The
    line is a coloured bar with the percentage and the elapsed and total
    time, never wider than the terminal's last column (:meth:`line`).
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
        text = self.line(fraction, max(MIN_WIDTH, min(MAX_WIDTH, width)) - 1)
        visible = cell_width(text)
        self.stream.write("\r" + text + " " * max(0, self._drawn - visible))
        self.stream.flush()
        self._drawn = visible

    def line(self, fraction: float, width: int) -> str:
        """The line at ``fraction``, never wider than ``width`` columns:
        ``  label  ━━━━╸────  42%  00:04 / 00:09``. A narrow terminal loses
        the bar first, then the clock, and the label is cut short, never the
        numbers."""
        c = self.console
        percent = f"{fraction * 100:3.0f}%"
        timing = f"{clock(fraction * self.total_s)} / {clock(self.total_s)}"
        ellipsis = "…" if c.unicode else "..."
        label = truncate(c.readable(self.label), max(8, width // 2), ellipsis)
        pct, clk = cell_width(percent), cell_width(timing)
        size = min(32, width - cell_width(label) - pct - clk - 8)
        if size >= 10:
            return f"  {label}  {c.meter(fraction, size)}  {c.bold(percent)}  {timing}"
        room = width - pct - clk - 6
        if room >= 6:
            label = truncate(label, room, ellipsis)
            return f"  {label}  {c.bold(percent)}  {timing}"
        room = width - pct - 4
        if room >= 4:
            return f"  {truncate(label, room, ellipsis)}  {c.bold(percent)}"
        return f"  {c.bold(percent)}"

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
