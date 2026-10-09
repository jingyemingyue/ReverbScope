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

import argparse
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
from reverbscope.cli.console import COLOR_MODES, Console, cell_width, shell_command, wrap
from reverbscope.cli.render import SAFETY_NOTE_SHOWN, render_error, render_safety_note
from reverbscope.errors import ReverbScopeError
from reverbscope.i18n import _, clause_join, current_locale, list_join, localize, pgettext
from reverbscope.io.project_store import is_project
from reverbscope.io.session_store import SESSION_FILE
from reverbscope.io.wav import has_audio_extension
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


def path_arg(path: Path) -> str:
    """``path`` as one argument of a command. A name that starts with ``-`` would
    be read as an option (``reverbscope show -take.wav``), so it gets ``./``."""
    text = str(path)
    return os.curdir + os.sep + text if text.startswith("-") else text


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


#: The marks a prompt ends with when it has no default to show.
_CLOSING = frozenset(":\uff1a?\uff1f")


def _split_question(template: str, question: str, **fields: str) -> tuple[str, str]:
    """``template`` (``{question} [{default}]: ``) as the question and what
    follows it, so that the layout can keep the second part whole."""
    marker = "\x00"
    head, _marker, tail = template.format(question=marker, **fields).partition(marker)
    return head + question, tail


class Session:
    """The questions of one menu visit, on one console."""

    def __init__(
        self, console: Console, ask: Asker, out: TextIO, *, backend: str | None = None
    ) -> None:
        self.console = console
        self._ask = ask
        self.out = out
        #: The audio backend given before the command (``--backend fake``), else
        #: the settings' and the environment's.
        self.backend = backend

    def say(self, lines: Sequence[str]) -> None:
        print("\n".join(lines), file=self.out)

    def _read(self, question: str, tail: str = "") -> str:
        """``question`` followed by ``tail`` (the default hint and the colon),
        and the answer.

        A question longer than the screen ran past its edge, so that the
        answer was typed after the terminal had wrapped the line, in the
        middle of the text. It is written in lines that leave room at the
        right, and only the last line is the prompt. The tail stays whole: it
        follows the last line of the question when it fits there, else it is a
        line of its own, so that a default (``[My Sessions/take 1]``,
        ``（默认：48000）``) is never cut in two.
        """
        c = self.console
        text, hint = c.readable(question), c.readable(tail)
        if cell_width(text + hint) + ANSWER_ROOM <= c.width:
            return self._ask(c.fit(question + tail)).strip()
        end = hint or text
        trailing = end[len(end.rstrip()) :]
        room = max(c.width - ANSWER_ROOM, 10)
        lines = wrap(text.strip(), room)
        core = hint.strip()
        if core:
            joiner = " " if hint[:1].isspace() else ""
            # A colon alone cannot start a line; a hint is one piece or none.
            if all(char in _CLOSING for char in core) or (
                cell_width(lines[-1] + joiner + core) <= room
            ):
                lines[-1] += joiner + core
            else:
                lines.append(core)
        self.say([c.fit(line) for line in lines[:-1]])
        return self._ask(c.fit(lines[-1] + trailing)).strip()

    def ask(self, prompt: str, default: str = "") -> str:
        """A question and its answer; an empty answer takes ``default``.

        The question, its default and its colon are written the way the
        interface language writes them (``测试信号写到哪里（默认：sweep.wav）：``).
        """
        template = _("{question} [{default}]: ") if default else _("{question}: ")
        return self._read(*_split_question(template, prompt, default=default)) or default

    def ask_path(
        self,
        prompt: str,
        *,
        default: Path | None = None,
        exists: bool = True,
        folder: bool = False,
        file: bool = False,
    ) -> Path:
        """A path, asked again while it does not exist (when it must).

        ``folder`` asks for a folder (or a ``session.json``), ``file`` for a
        file that exists: a folder is refused in words, not accepted and
        reported as a missing file one step later.
        """
        shown = str(default) if default is not None else ""
        while True:
            answer = self.ask(prompt, shown)
            # The default is taken as it was offered: a path that was typed or
            # dragged is cleaned (quotes, the backslashes of a drag and drop),
            # one the menu offered is not text that anyone typed (``bs\dir``).
            path = default if default is not None and answer == shown else parse_path(answer)
            if path is None:
                raise CancelledError
            if not exists:
                return path
            if folder and (_is_dir(path) or (path.name == SESSION_FILE and _is_file(path))):
                return path
            if file and _is_file(path):
                return path
            if not folder and not file and _exists(path):
                return path
            if folder:
                text = _("{path} is not a folder; try again, or leave empty to go back.")
            elif file and _is_dir(path):
                text = _("{path} is a folder, not a file; try again, or leave empty to go back.")
            else:
                text = _("{path} does not exist; try again, or leave empty to go back.")
            self.say(self.console.status("error", text.format(path=path)))

    def ask_file_to_write(self, prompt: str, *, default: Path) -> Path:
        """A file to create: ``.wav`` is added to a name without an audio
        extension (libsndfile refuses it), a folder is refused in words and
        a file that exists is replaced only after a yes."""
        while True:
            path = self.ask_path(prompt, default=default, exists=False)
            if _is_dir(path):
                example = path / default.name
                self.say(
                    self.console.status(
                        "error",
                        _("{path} is a folder; type a file name, for example {example}.").format(
                            path=path, example=example
                        ),
                    )
                )
                continue
            if not has_audio_extension(path):
                path = path.with_name(path.name + ".wav")
            if not _exists(path) or self.ask_yes(
                _("{path} already exists. Replace it?").format(path=path)
            ):
                return path

    def confirm_session_folder(self, folder: Path) -> bool:
        """Whether a take or an analysis may be saved in ``folder``: it holds no
        session yet, or the user said yes to replacing the one in it."""
        if not _is_file(folder / SESSION_FILE):
            return True
        return self.ask_yes(
            _("{path} already holds a saved session. Replace it?").format(path=folder)
        )

    def ask_session_folder(self, prompt: str, *, default: Path) -> Path:
        """A folder for a new session, asked again while it holds a saved one
        that the user does not want replaced."""
        while True:
            folder = self.ask_path(prompt, default=default, exists=False)
            if self.confirm_session_folder(folder):
                return folder

    def ask_yes(self, prompt: str) -> bool:
        """Yes only for an explicit yes; Enter, anything else, is no."""
        answer = fold(self._read(*_split_question(_("{question} [y/N]: "), prompt))).casefold()
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
    out = session.ask_file_to_write(_("Where to write the test signal"), default=Path("sweep.wav"))
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
    return ["sweep", "--out", path_arg(out), "--sample-rate", str(rate)]


def _analyze(session: Session) -> list[str]:
    recording = session.ask_path(
        _("The recording exported from your DAW (WAV, AIFF, CAF, FLAC)"), file=True
    )
    beside = recording.parent / "sweep.wav"
    sweep = session.ask_path(
        _("The test signal that was played"),
        default=beside if beside.is_file() else None,
        file=True,
    )
    while True:
        saved = parse_path(session.ask(_("Folder to save the session in (empty: show only)")))
        if saved is None or session.confirm_session_folder(saved):
            break
    argv = ["analyze", "--recording", path_arg(recording), "--sweep", path_arg(sweep)]
    if saved is not None:
        argv += ["--out", path_arg(saved)]
    return argv


#: The levels a take can be played at (``reverbscope measure --level``).
MIN_LEVEL_DBFS = -80.0
MAX_LEVEL_DBFS = 0.0
_LEVEL = re.compile(r"[+-]?\d{1,3}(?:\.\d{1,3})?")


def level_dbfs(text: str) -> float | None:
    """``text`` as a level from -80 to 0 dBFS, or ``None``. The minus of a
    Chinese keyboard (``－``) and the typographic one (``−``) are minus signs."""
    folded = fold(text).replace("\u2212", "-")
    if not _LEVEL.fullmatch(folded):
        return None
    value = float(folded)
    return value if MIN_LEVEL_DBFS <= value <= MAX_LEVEL_DBFS else None


def output_base() -> Path:
    """Where new sessions start: the output folder of the settings (the desktop
    app's Save dialog opens there too), else the current folder."""
    from reverbscope.settings import load_settings

    try:
        configured = load_settings().output_dir
        folder = Path(configured).expanduser() if configured else None
    except (OSError, RuntimeError, ValueError):
        folder = None
    return folder if folder is not None and _is_dir(folder) else Path()


def new_session_folder(base: Path, now: datetime | None = None) -> Path:
    """``session-<date>-<time>`` in ``base``, or ``-2``, ``-3`` after it when
    that folder exists: a take lasts longer than the minute the name is made
    of, and the second one replaced the first in the same folder."""
    stamp = (now or datetime.now()).strftime("%Y%m%d-%H%M")
    folder = base / f"session-{stamp}"
    number = 2
    while _exists(folder):
        folder = base / f"session-{stamp}-{number}"
        number += 1
    return folder


def audio_problems(backend: str | None) -> list[str]:
    """Why no take can be made here, one sentence for each reason; empty when
    there is an input and an output device to make it with."""
    from reverbscope.audio.backend import get_backend

    try:
        devices = get_backend(backend).list_devices()
    except (ReverbScopeError, OSError) as exc:
        return [localize(str(exc))]
    problems = []
    if not any(device.is_input for device in devices):
        problems.append(_("no audio input device found"))
    if not any(device.is_output for device in devices):
        problems.append(_("no audio output device found"))
    return problems


def _measure(session: Session) -> list[str] | None:
    from reverbscope.audio.backend import DEFAULT_STANDALONE_LEVEL_DBFS, SAFE_MAX_LEVEL_DBFS

    # With nothing to record with or to play on, the questions would be asked
    # and a take refused after them: say so first.
    problems = audio_problems(session.backend)
    if problems:
        session.say(
            [
                render_error(
                    session.console,
                    clause_join(problems),
                    detail=_("Nothing was played."),
                    hints=["reverbscope doctor", "reverbscope demo"],
                )
            ]
        )
        return None
    out = session.ask_session_folder(
        _("Folder for the new session"), default=new_session_folder(output_base())
    )
    acknowledged = False
    while True:
        level = level_dbfs(
            session.ask(_("Level of the sweep in dBFS"), f"{DEFAULT_STANDALONE_LEVEL_DBFS:g}")
        )
        if level is None:
            session.say(
                session.console.status(
                    "error",
                    _("Type a level from {low:g} to {high:g} dBFS.").format(
                        low=MIN_LEVEL_DBFS, high=MAX_LEVEL_DBFS
                    ),
                )
            )
        elif level <= SAFE_MAX_LEVEL_DBFS:
            break
        elif session.ask_yes(
            _(
                "{level:g} dBFS is above {max_level:g} dBFS. "
                "Is the monitor level already turned down?"
            ).format(level=level, max_level=SAFE_MAX_LEVEL_DBFS)
        ):
            acknowledged = True
            break
    session.say(
        session.console.paragraph(
            _(
                "ReverbScope will play a sweep through the default output device at "
                "{level:g} dBFS and record the default input. Nothing has been played yet."
            ).format(level=level)
        )
    )
    session.say(["", render_safety_note(session.console), ""])
    if not session.ask_yes(_("Play and record now?")):
        session.say(session.console.status("info", _("Nothing was played.")))
        return None
    argv = ["measure", "--out", path_arg(out)]
    if level != DEFAULT_STANDALONE_LEVEL_DBFS:
        argv += ["--level", f"{level:g}"]
    if acknowledged:
        argv.append("--acknowledge-level")
    return argv


def _show(session: Session) -> list[str]:
    path = session.ask_path(_("A session folder, result.json or comparison.json"))
    return ["show", path_arg(path)]


def _compare(session: Session) -> list[str]:
    baseline = session.ask_path(_("The baseline session (folder)"), folder=True)
    candidate = session.ask_path(_("The candidate session (folder)"), folder=True)
    argv = ["compare", path_arg(baseline), path_arg(candidate)]
    if session.ask_yes(_("Was the input gain the same for both takes?")):
        argv.append("--same-input-gain")
    return argv


def _overview(session: Session) -> list[str]:
    while True:
        project = session.ask_path(_("The project folder"), folder=True)
        if is_project(project):
            return ["project", "overview", path_arg(project)]
        # The menu has no item that makes a project: the command is named.
        session.say(
            session.console.status(
                "error",
                _(
                    "{path} has no project.json; make a project first with "
                    "reverbscope project init --out <folder>, or try another folder."
                ).format(path=project),
            )
        )


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


def option_value(options: Sequence[str], name: str) -> str | None:
    """The value after ``name`` in ``options`` (``--backend fake``), else ``None``."""
    for index, option in enumerate(options[:-1]):
        if option == name:
            return options[index + 1]
    return None


def root_options(args: argparse.Namespace, *, lang: str, color: str = "auto") -> list[str]:
    """The options given before the command (``reverbscope --backend fake``),
    which go before every command the menu runs and shows.

    Without them the menu would measure on the real interface after the user
    asked for the simulated one, copy the recording after ``--no-copy-recording``
    and forget the colour, the style and the language that were asked for.
    """
    options = ["--lang", lang]
    if color in COLOR_MODES and color != "auto":
        options += ["--color", color]
    style = getattr(args, "style", "auto")
    if style != "auto":
        options += ["--style", str(style)]
    if getattr(args, "backend", None):
        options += ["--backend", str(args.backend)]
    copy = getattr(args, "copy_recording", None)
    if copy is not None:
        options.append("--copy-recording" if copy else "--no-copy-recording")
    if getattr(args, "verbose", False):
        options.append("--verbose")
    return options


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
    session = Session(c, ask, out, backend=option_value(prefix, "--backend"))
    items = menu_items(terminal_edition=terminal_edition)
    by_key = {item.key: item for item in items}
    # The frames are drawn with glyphs that some CJK terminals draw too wide:
    # a reader of such an interface is told how to leave them out, once, under
    # the first list (the list comes back after every command, the hint would
    # be the same line each time).
    crooked = style_hint_lines(current_locale(), c.width, boxed=c.boxed and c.interactive)
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
    listed = False
    while True:
        # The list is shown again after a command or a cancelled question; after
        # a choice that was not on it, it is still on the screen, a line above.
        if not listed:
            session.say([""])
            session.say(
                _choice_lines(c, [(item.key, item.title) for item in items] + [("q", _("Quit"))])
                + (["", *crooked] if crooked else [])
            )
            crooked = []
            listed = True
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
        listed = False
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
        # The take is played after the note about the monitors was shown and a
        # "y" typed (see _measure): the command need not show it a second time.
        shown = SAFETY_NOTE_SHOWN.set(argv[:1] == ["measure"])
        try:
            code = run(full)
        except KeyboardInterrupt:
            code = EXIT_INTERRUPTED
        except SystemExit as exc:
            # argparse refused the arguments (a path that starts with "-"): the
            # usage error is on stderr already; the menu goes on.
            code = exc.code if isinstance(exc.code, int) else 1
        finally:
            SAFETY_NOTE_SHOWN.reset(shown)
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
    "audio_problems",
    "clean_path",
    "fold",
    "level_dbfs",
    "menu_items",
    "option_value",
    "output_base",
    "parse_path",
    "path_arg",
    "quit_words",
    "root_options",
    "run_menu",
    "whole_number",
]
