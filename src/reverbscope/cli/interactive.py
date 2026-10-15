"""An interactive menu for a terminal: ``reverbscope`` with no command.

Numbered choices for the common tasks. Each asks for what its command
needs, prints the equivalent command line (to type or paste next time),
runs it in this process and returns to the menu. Ctrl+C at a question
returns to the menu; the end of input (Ctrl+D, Ctrl+Z) and ``q`` leave.
Only a terminal gets the menu: a pipe, a file or a script still gets the
home screen on stderr and the usage exit code, so nothing that scripts
ReverbScope changes. :data:`MENU_VARIABLE` switches it off on a terminal.

Nothing is played until the measurement item has printed what it will
do and the answer was ``y``.
"""

from __future__ import annotations

import logging
import os
import shlex
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TextIO

from reverbscope.cli.console import Console, shell_command
from reverbscope.i18n import _, pgettext
from reverbscope.io.session_store import SESSION_FILE
from reverbscope.io.wav import sidecar_path
from reverbscope.models.configuration import SUPPORTED_SAMPLE_RATES

#: Set (to anything) to keep the menu off a terminal.
MENU_VARIABLE = "REVERBSCOPE_NO_MENU"

log = logging.getLogger(__name__)

Asker = Callable[[str], str]
Runner = Callable[[list[str]], int]


class CancelledError(Exception):
    """The user left a question: an empty answer, or Ctrl+C."""


def parse_path(text: str) -> Path | None:
    """A path as typed, or as a terminal pastes a dragged file: surrounding
    quotes and backslash escapes removed, ``~`` expanded. ``None`` when empty."""
    text = text.strip()
    if not text:
        return None
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        text = text[1:-1]
    elif os.name != "nt" and ("\\" in text or '"' in text or "'" in text):
        # A POSIX terminal drops a dragged file as "my\ room/take.wav".
        try:
            parts = shlex.split(text)
        except ValueError:
            parts = []
        if len(parts) == 1:
            text = parts[0]
    return Path(text).expanduser()


class Session:
    """The questions of one menu visit, on one console."""

    def __init__(self, console: Console, ask: Asker, out: TextIO) -> None:
        self.console = console
        self._ask = ask
        self.out = out

    def say(self, lines: Sequence[str]) -> None:
        print("\n".join(lines), file=self.out)

    def ask(self, prompt: str, default: str = "") -> str:
        shown = f"{prompt} [{default}]: " if default else f"{prompt}: "
        answer = self._ask(self.console.fit(shown)).strip()
        return answer or default

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
            if folder and (path.is_dir() or (path.name == SESSION_FILE and path.is_file())):
                return path
            if not folder and path.exists():
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
        answer = self.ask(f"{prompt} [y/N]").strip().lower()
        return answer in ("y", "yes", pgettext("answer", "y"), pgettext("answer", "yes"))

    def ask_file_to_write(self, prompt: str, *, default: Path | None = None) -> Path:
        """A WAV path. An existing file or its sweep sidecar must be confirmed.

        No, Enter, or any other answer asks for a different path. Nothing is
        written here. A yes returns the path for the command that already
        knows how to replace a file.
        """
        while True:
            path = self.ask_path(prompt, default=default, exists=False)
            blocked = False
            for target in (path, sidecar_path(path)):
                if not (target.exists() or target.is_symlink()):
                    continue
                question = _("{name} already exists. Replace it?").format(name=str(target))
                if not self.ask_yes(question):
                    blocked = True
                    break
            if not blocked:
                return path

    def ask_session_folder(
        self,
        prompt: str,
        *,
        default: Path | None = None,
        allow_empty: bool = False,
    ) -> Path | None:
        """A session directory. Empty is allowed only when ``allow_empty`` is set.

        A saved session, or any other non-empty directory, has to be confirmed.
        An empty directory or a path that does not exist yet is used as given.
        No and Enter ask again. A stat error is not treated as "empty".
        """
        while True:
            if allow_empty:
                path = parse_path(self.ask(prompt, "" if default is None else str(default)))
                if path is None:
                    return None
            else:
                path = self.ask_path(prompt, default=default, exists=False)
            if self._confirm_output_dir(path):
                return path

    def _confirm_output_dir(self, path: Path) -> bool:
        if not path.exists() and not path.is_symlink():
            return True
        if not path.is_dir():
            return self.ask_yes(_("{name} already exists. Replace it?").format(name=str(path)))
        if (path / SESSION_FILE).is_file():
            return self.ask_yes(
                _("{path} already holds a saved session. Replace it?").format(path=str(path))
            )
        if not any(path.iterdir()):
            return True
        return self.ask_yes(
            _("{path} already has files in it. Use it anyway?").format(path=str(path))
        )


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


def _occupied(path: Path) -> bool:
    """True for a real file or directory and for a symlink, including a dangling one."""
    return path.exists() or path.is_symlink()


def new_session_folder(base: Path, now: datetime | None = None) -> Path:
    """``session-YYYYMMDD-HHMM`` under ``base``, or ``-2``, ``-3``, … if that name is taken.

    This only chooses a name. It does not create the directory, and two menus
    choosing at the same moment can still pick the same free name.
    """
    stamp = (datetime.now() if now is None else now).strftime("%Y%m%d-%H%M")
    plain = base / f"session-{stamp}"
    if not _occupied(plain):
        return plain
    number = 2
    while _occupied(base / f"session-{stamp}-{number}"):
        number += 1
    return base / f"session-{stamp}-{number}"


def _sweep(session: Session) -> list[str]:
    out = session.ask_file_to_write(_("Where to write the test signal"), default=Path("sweep.wav"))
    while True:
        rate = session.ask(_("Sample rate of your DAW project (Hz)"), "48000")
        if rate.isascii() and rate.isdigit() and int(rate) in SUPPORTED_SAMPLE_RATES:
            break
        session.say(
            session.console.status(
                "error",
                _("Choose one of {rates}.").format(
                    rates=", ".join(str(r) for r in SUPPORTED_SAMPLE_RATES)
                ),
            )
        )
    return ["sweep", "--out", str(out), "--sample-rate", rate]


def _analyze(session: Session) -> list[str]:
    recording = session.ask_path(_("The recording exported from your DAW (WAV, AIFF, CAF, FLAC)"))
    beside = recording.parent / "sweep.wav"
    sweep = session.ask_path(
        _("The test signal that was played"), default=beside if beside.is_file() else None
    )
    saved = session.ask_session_folder(
        _("Folder to save the session in (empty: show only)"), allow_empty=True
    )
    argv = ["analyze", "--recording", str(recording), "--sweep", str(sweep)]
    if saved is not None:
        argv += ["--out", str(saved)]
    return argv


def _measure(session: Session) -> list[str] | None:
    out = session.ask_session_folder(
        _("Folder for the new session"), default=new_session_folder(Path())
    )
    if out is None:
        raise CancelledError
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
        width = max(len(item.key) for item in items)
        session.say(
            [f"  {c.accent(item.key.rjust(width))}  {c.fit(item.title)}" for item in items]
            + [f"  {c.accent('q'.rjust(width))}  {_('Quit')}"]
        )
        try:
            choice = session.ask(pgettext("menu prompt", "Your choice")).lower()
        except (EOFError, KeyboardInterrupt):
            session.say([""])
            return 0
        if choice in ("q", "quit", "exit", "0"):
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
            log.exception("a menu question failed")
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
    "MENU_VARIABLE",
    "CancelledError",
    "MenuItem",
    "Session",
    "menu_items",
    "parse_path",
    "run_menu",
]
