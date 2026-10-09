"""An interactive menu for a terminal: ``reverbscope`` with no command.

Numbered choices for the common tasks. Each asks for what its command
needs, prints the equivalent command line (to type or paste next time),
runs it in this process and returns to the menu. Ctrl+C at a question
returns to the menu, at the menu it leaves with exit code 130; the end of
input (Ctrl+D, Ctrl+Z) and ``q`` leave with 0. Only a terminal gets the
menu: a pipe, a file or a script still gets the home screen on stderr and
the usage exit code, so nothing that scripts ReverbScope changes.
:data:`MENU_VARIABLE` switches it off on a terminal.

An answer is read as a person types it on a Chinese keyboard: ``９`` is 9,
``ｑ`` is q and ``退出`` is quit. An answer is never an exception: a number
that is not one, a path the file system refuses, a key nobody expected, is
refused in words and asked again.

Nothing is played until the measurement item has printed what it will
do and the answer was ``y``.
"""

from __future__ import annotations

import logging
import os
import re
import shlex
import unicodedata
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TextIO

from reverbscope.cli.config import style_hint_lines
from reverbscope.cli.console import Console, cell_width, shell_command, wrap
from reverbscope.i18n import _, current_locale, list_join, pgettext
from reverbscope.io.session_store import SESSION_FILE
from reverbscope.models.configuration import SUPPORTED_SAMPLE_RATES

#: Set (to anything) to keep the menu off a terminal.
MENU_VARIABLE = "REVERBSCOPE_NO_MENU"
#: The exit code of Ctrl+C at the menu: 128 + SIGINT, as a shell reports it.
EXIT_INTERRUPTED = 130
#: Columns a prompt leaves free at the right edge for the answer being typed.
ANSWER_ROOM = 10

log = logging.getLogger(__name__)

Asker = Callable[[str], str]
Runner = Callable[[list[str]], int]


class CancelledError(Exception):
    """The user left a question: an empty answer, or Ctrl+C."""


def fold(text: str) -> str:
    """``text`` as ASCII where a Chinese input method typed a full-width digit,
    letter or sign (``９``, ``ｙ``, ``．``), without the blanks around it.

    For answers that are numbers or words, never for a path: NFKC would
    rename a file.
    """
    return unicodedata.normalize("NFKC", text).strip()


#: More digits than any answer needs: a longer string is not a number here.
_MAX_DIGITS = 18


def whole_number(text: str) -> int | None:
    """``text`` as a whole number, or ``None`` for anything else.

    ``①`` and ``²`` are digits to ``str.isdigit`` but not to ``int``, and a
    string of thousands of digits is more than ``int`` takes (both raised
    ``ValueError``): the first is read as the digit it is, the second is not a
    number.
    """
    digits = fold(text)
    if not digits.isdecimal() or len(digits) > _MAX_DIGITS:
        return None
    try:
        return int(digits)
    except ValueError:
        return None


def quit_words() -> frozenset[str]:
    """What leaves the menu: ``q``, ``quit``, ``exit``, 0, and the interface
    language's own words (``退出``)."""
    words = pgettext("answers meaning quit", "q quit exit").split()
    return frozenset(word.casefold() for word in (*words, "0"))


#: How ``shlex.quote`` and several terminals write an apostrophe inside quotes.
_APOSTROPHE = "'\"'\"'"
#: Quotes that wrap a pasted path, with the mark that closes each.
_QUOTES = {'"': '"', "'": "'", "\u201c": "\u201d", "\u2018": "\u2019", "\u300c": "\u300d"}


def clean_path(text: str, *, posix: bool | None = None) -> str:
    """A path as typed, pasted or dragged into the terminal, as a plain path.

    Spaces around it and one pair of surrounding quotes go (``"My Take.wav"``,
    ``'My Take.wav'``, “…”); PowerShell's ``& '…'`` goes too. On macOS and
    Linux a path that is not quoted loses the backslashes a drag and drop adds
    (``My\\ Take.wav``), and a name the terminal quoted as a shell would
    (``'it'\\''s a take.wav'``, which GNOME Terminal and KDE write) is read as
    a shell reads it; on Windows a backslash separates folders and stays.
    ``~`` is left for :func:`parse_path`.
    """
    posix = os.name != "nt" if posix is None else posix
    text = text.strip()
    if text.startswith("& ") and text[2:].lstrip()[:1] in _QUOTES:
        text = text[2:].lstrip()
    if posix and text[:1] in ("'", '"') and ("\\" in text or _APOSTROPHE in text):
        try:
            words = shlex.split(text)
        except ValueError:
            words = []
        if len(words) == 1:
            return words[0]
    if len(text) >= 2 and _QUOTES.get(text[0]) == text[-1]:
        return text[1:-1]
    if posix and "\\" in text:
        text = re.sub(r"\\(.)", r"\1", text)
    return text


def parse_path(text: str, *, posix: bool | None = None) -> Path | None:
    """:func:`clean_path`, with ``~`` expanded; ``None`` for an empty answer."""
    clean = clean_path(text, posix=posix).strip()
    if not clean:
        return None
    path = Path(clean)
    try:
        return path.expanduser()
    except RuntimeError:  # "~name" of nobody: the text stays as typed
        return path


def _is_dir(path: Path) -> bool:
    try:
        return path.is_dir()
    except (OSError, ValueError):  # a name too long for the file system, a NUL byte
        return False


def _is_file(path: Path) -> bool:
    try:
        return path.is_file()
    except (OSError, ValueError):
        return False


def _exists(path: Path) -> bool:
    try:
        return path.exists()
    except (OSError, ValueError):
        return False


class Session:
    """The questions of one menu visit, on one console."""

    def __init__(self, console: Console, ask: Asker, out: TextIO) -> None:
        self.console = console
        self._ask = ask
        self.out = out

    def say(self, lines: Sequence[str]) -> None:
        print("\n".join(lines), file=self.out)

    def _read(self, shown: str) -> str:
        c = self.console
        text = c.readable(shown)
        if cell_width(text) + ANSWER_ROOM <= c.width:
            return self._ask(c.fit(shown)).strip()
        # A question longer than the screen ran past its edge, so that the
        # answer was typed after the terminal had wrapped the line, in the
        # middle of the text: it is written in lines that leave room at the
        # right, and only the last line is the prompt.
        trailing = text[len(text.rstrip()) :]
        lines = wrap(text.strip(), max(c.width - ANSWER_ROOM, 10))
        self.say([c.fit(line) for line in lines[:-1]])
        return self._ask(c.fit(lines[-1] + trailing)).strip()

    def ask(self, prompt: str, default: str = "") -> str:
        """A question and its answer; an empty answer takes ``default``.

        The question, its default and its colon are written the way the
        interface language writes them (``测试信号写到哪里（默认：sweep.wav）：``).
        """
        if default:
            shown = _("{question} [{default}]: ").format(question=prompt, default=default)
        else:
            shown = _("{question}: ").format(question=prompt)
        return self._read(shown) or default

    def ask_path(
        self,
        prompt: str,
        *,
        default: Path | None = None,
        exists: bool = True,
        folder: bool = False,
    ) -> Path:
        """A path, asked again while it does not exist (when it must)."""
        while True:
            answer = self.ask(prompt, str(default) if default is not None else "")
            path = parse_path(answer)
            if path is None:
                raise CancelledError
            if not exists:
                return path
            if folder and (_is_dir(path) or (path.name == SESSION_FILE and _is_file(path))):
                return path
            if not folder and _exists(path):
                return path
            self.say(
                self.console.status(
                    "error",
                    (
                        _("{path} is not a folder; try again, or leave empty to go back.")
                        if folder
                        else _("{path} does not exist; try again, or leave empty to go back.")
                    ).format(path=path),
                )
            )

    def ask_yes(self, prompt: str) -> bool:
        """Yes only for an explicit yes; Enter, anything else, is no."""
        answer = fold(self._read(_("{question} [y/N]: ").format(question=prompt))).casefold()
        yes = ("y", "yes", pgettext("answer", "y"), pgettext("answer", "yes"))
        return answer in {word.casefold() for word in yes}


@dataclass(frozen=True)
class MenuItem:
    key: str
    title: str
    #: The command's arguments after ``reverbscope``, or ``None`` to do nothing.
    build: Callable[[Session], list[str] | None]


def _plain(*argv: str) -> Callable[[Session], list[str] | None]:
    """An item that asks nothing."""

    def build(_session: Session) -> list[str]:
        return list(argv)

    return build


def _sweep(session: Session) -> list[str]:
    out = session.ask_path(
        _("Where to write the test signal"), default=Path("sweep.wav"), exists=False
    )
    while True:
        rate = whole_number(session.ask(_("Sample rate of your DAW project (Hz)"), "48000"))
        if rate in SUPPORTED_SAMPLE_RATES:
            break
        session.say(
            session.console.status(
                "error",
                _("Choose one of {rates}.").format(
                    rates=list_join(str(r) for r in SUPPORTED_SAMPLE_RATES)
                ),
            )
        )
    return ["sweep", "--out", str(out), "--sample-rate", str(rate)]


def _analyze(session: Session) -> list[str]:
    recording = session.ask_path(_("The recording exported from your DAW (WAV, AIFF, CAF, FLAC)"))
    beside = recording.parent / "sweep.wav"
    sweep = session.ask_path(
        _("The test signal that was played"), default=beside if beside.is_file() else None
    )
    out = session.ask(_("Folder to save the session in (empty: show only)"))
    argv = ["analyze", "--recording", str(recording), "--sweep", str(sweep)]
    saved = parse_path(out)
    if saved is not None:
        argv += ["--out", str(saved)]
    return argv


def _measure(session: Session) -> list[str] | None:
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    out = session.ask_path(
        _("Folder for the new session"), default=Path(f"session-{stamp}"), exists=False
    )
    session.say(
        session.console.paragraph(
            _(
                "ReverbScope will play a sweep through the default output device at -12 dBFS "
                "and record the default input. Set a moderate monitor level first; nothing has "
                "been played yet."
            )
        )
    )
    if not session.ask_yes(_("Play and record now?")):
        session.say(session.console.status("info", _("Nothing was played.")))
        return None
    return ["measure", "--out", str(out)]


def _show(session: Session) -> list[str]:
    path = session.ask_path(_("A session folder, result.json or comparison.json"))
    return ["show", str(path)]


def _compare(session: Session) -> list[str]:
    baseline = session.ask_path(_("The baseline session (folder)"), folder=True)
    candidate = session.ask_path(_("The candidate session (folder)"), folder=True)
    argv = ["compare", str(baseline), str(candidate)]
    if session.ask_yes(_("Was the input gain the same for both takes?")):
        argv.append("--same-input-gain")
    return argv


def _overview(session: Session) -> list[str]:
    project = session.ask_path(_("The project folder"), folder=True)
    return ["project", "overview", str(project)]


def menu_items(*, terminal_edition: bool = False) -> list[MenuItem]:
    items = [
        MenuItem("1", _("Try the demo (synthetic room, no audio interface)"), _plain("demo")),
        MenuItem("2", _("Write the test signal to play from your DAW"), _sweep),
        MenuItem("3", _("Analyse a recording of the test signal"), _analyze),
        MenuItem("4", _("Measure through the audio interface (plays a sweep)"), _measure),
        MenuItem("5", _("Show a saved session or comparison"), _show),
        MenuItem("6", _("Compare two sessions"), _compare),
        MenuItem("7", _("Project overview (several positions)"), _overview),
        MenuItem("8", _("Settings"), _plain("config")),
        MenuItem("9", _("Environment report for bug reports"), _plain("doctor")),
    ]
    if not terminal_edition:
        items.append(MenuItem("10", _("Open the desktop app"), _plain("gui")))
    return items


def _choice_lines(c: Console, rows: Sequence[tuple[str, str]]) -> list[str]:
    """``  1  title`` rows, the number bold; a title longer than the line wraps
    under itself."""
    width = max(len(key) for key, _title in rows)
    hang = " " * (width + 4)
    out: list[str] = []
    for key, title in rows:
        lines = wrap(c.readable(title), c.width, first=hang, rest=hang)
        out.append("  " + c.bold(key.rjust(width)) + "  " + lines[0][len(hang) :])
        out += lines[1:]
    return out


def run_menu(
    console: Console,
    *,
    ask: Asker,
    run: Runner,
    out: TextIO,
    terminal_edition: bool = False,
    prefix: Sequence[str] = (),
) -> int:
    """The menu until the user leaves; ``prefix`` (``--lang``, ``--color``,
    ``--style``) goes before every command run and shown."""
    c = console
    session = Session(c, ask, out)
    items = menu_items(terminal_edition=terminal_edition)
    by_key = {item.key: item for item in items}
    # The frames are drawn with glyphs that some CJK terminals draw too wide:
    # a reader of such an interface is told how to leave them out.
    crooked = style_hint_lines(current_locale(), c.width, boxed=c.boxed)
    if not c.can_write("".join(crooked)):
        crooked = []
    session.say(c.title("ReverbScope"))
    session.say(
        c.paragraph(
            _(
                "Choose a number. Every choice shows the command it runs, so the next time "
                "you can type it directly. q leaves; Ctrl+C at a question comes back here."
            ),
            indent=0,
        )
    )
    while True:
        session.say([""])
        session.say(
            _choice_lines(c, [(item.key, item.title) for item in items] + [("q", _("Quit"))])
            + (["", *crooked] if crooked else [])
        )
        try:
            choice = fold(session.ask(pgettext("menu prompt", "Your choice"))).casefold()
        except EOFError:
            session.say([""])
            return 0
        except KeyboardInterrupt:
            session.say([""])
            return EXIT_INTERRUPTED
        if choice in quit_words():
            return 0
        item = by_key.get(choice)
        if item is None:
            session.say(c.status("error", _("Choose a number from the list, or q.")))
            continue
        try:
            argv = item.build(session)
        except (CancelledError, KeyboardInterrupt):
            session.say(["", *c.status("info", _("Back to the menu."))])
            continue
        except EOFError:
            session.say([""])
            return 0
        except Exception as exc:  # the menu must survive its own questions
            # The log file keeps the traceback; the screen gets the sentence.
            log.info("a menu question failed", exc_info=True)
            session.say(
                c.status(
                    "error",
                    _("The question could not be completed ({error}). Back to the menu.").format(
                        error=f"{type(exc).__name__}: {exc}"
                    ),
                )
            )
            continue
        if argv is None:
            continue
        full = [*prefix, *argv]
        session.say(c.status("next", _("The same from the command line:")))
        session.say(["    " + c.command(shell_command(["reverbscope", *full])), ""])
        try:
            code = run(full)
        except KeyboardInterrupt:
            code = 130
        except SystemExit as exc:
            # argparse refused the arguments (a path that starts with "-"): the
            # usage error is on stderr already; the menu goes on.
            code = exc.code if isinstance(exc.code, int) else 1
        if code:
            session.say(
                c.status("warn", _("The command ended with exit code {code}.").format(code=code))
            )


__all__ = [
    "EXIT_INTERRUPTED",
    "MENU_VARIABLE",
    "CancelledError",
    "MenuItem",
    "Session",
    "clean_path",
    "fold",
    "menu_items",
    "parse_path",
    "quit_words",
    "run_menu",
    "whole_number",
]
