"""``roomscope menu``: the everyday tasks from a numbered menu.

For whoever would rather not remember commands. Bare ``roomscope`` opens the
menu when stdin and stdout are both terminals, ``--format json`` was not
given and ``ROOMSCOPE_NO_MENU`` is not set; a pipe, a file or a script gets
the short home screen as before.

Each item asks only for what it needs, with a default that Enter accepts,
then prints the command it stands for (so the user learns it) and runs that
command through the command line's own :func:`roomscope.cli.main.main` in
this process. The menu adds no second way of doing anything: a setting is
changed by ``roomscope config``, a take is played by ``roomscope measure``.

All text is laid out by :class:`~roomscope.cli.console.Console`, so the menu
looks like the rest of the command line. Answers come from a function
(``input`` by default) and text goes to a stream, so tests drive every item
with scripted answers.

At a question, Ctrl+C goes back to the menu; at the menu itself it leaves
(exit code 130). End of input (Ctrl+D, or Ctrl+Z then Enter on Windows)
leaves with exit code 0 wherever it comes.
"""

from __future__ import annotations

import argparse
import contextlib
import os
import re
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, TextIO, TypeVar

from roomscope.cli.console import (
    COLOR_MODES,
    ColorMode,
    Console,
    Verbatim,
    cell_width,
    is_terminal,
    pad,
    shell_command,
    truncate,
    wrap,
)
from roomscope.errors import RoomScopeError
from roomscope.i18n import _, list_join, localize, pgettext

if TYPE_CHECKING:
    from roomscope.audio.backend import DeviceInfo
    from roomscope.io.session_store import SessionListing

#: Set (to anything but an empty value) to keep bare ``roomscope`` on the home screen.
ENV_NO_MENU = "ROOMSCOPE_NO_MENU"

#: Reads one answer: the prompt is shown, the line typed is returned
#: (``input``). Raises EOFError at the end of input, KeyboardInterrupt on Ctrl+C.
Reader = Callable[[str], str]
#: Runs one command line (without the program name) and returns its exit code.
Dispatch = Callable[[list[str]], int]

#: Exit codes of the menu itself.
EXIT_OK = 0
EXIT_REFUSED = 2
EXIT_INTERRUPTED = 130

#: Answers that leave the menu, besides 0.
_QUIT_WORDS = frozenset({"q", "quit", "exit"})
#: Columns a prompt leaves free at the right edge for the answer being typed.
_ANSWER_ROOM = 10
#: Sessions listed for "view results" and "compare", newest first.
MAX_LISTED = 20
#: Interface languages in the order the language list shows them.
_LANGUAGE_ORDER = ("zh_CN", "en", "zh_TW", "ja", "ko", "es", "fr", "de")
#: The ``measure`` defaults the menu leaves to the command.
_MEASURE_LEVEL = -20.0
_SWEEP_SECONDS = 10.0

T = TypeVar("T")


class _BackToMenuError(Exception):
    """Ctrl+C at a question: back to the menu."""


class _LeaveMenuError(Exception):
    """Leave the menu with ``code``."""

    def __init__(self, code: int) -> None:
        super().__init__(code)
        self.code = code


class InvalidAnswerError(ValueError):
    """An answer the question cannot take; the reason is shown and it is asked again."""


# --- Starting ----------------------------------------------------------------------------


def wanted(
    args: argparse.Namespace,
    *,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
    environ: Mapping[str, str] | None = None,
) -> bool:
    """Whether bare ``roomscope`` opens the menu instead of the home screen."""
    env = os.environ if environ is None else environ
    return (
        getattr(args, "command", None) is None
        and getattr(args, "format", None) != "json"
        and not env.get(ENV_NO_MENU)
        and is_terminal(sys.stdin if stdin is None else stdin)
        and is_terminal(sys.stdout if stdout is None else stdout)
    )


def root_options(args: argparse.Namespace) -> list[str]:
    """The options before the command that every command run from the menu keeps."""
    options: list[str] = []
    if getattr(args, "lang", None):
        options += ["--lang", str(args.lang)]
    color = getattr(args, "color", None)
    if color and color != "auto":
        options += ["--color", str(color)]
    if getattr(args, "backend", None):
        options += ["--backend", str(args.backend)]
    copy = getattr(args, "copy_recording", None)
    if copy is not None:
        options.append("--copy-recording" if copy else "--no-copy-recording")
    if getattr(args, "verbose", False):
        options.append("--verbose")
    return options


def start(
    args: argparse.Namespace,
    *,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
    read: Reader | None = None,
    dispatch: Dispatch | None = None,
) -> int:
    """``roomscope menu`` and bare ``roomscope`` on a terminal.

    Refused (exit code 2) for JSON output and where nobody can type the
    answers: a pipe, a file, a script.
    """
    from roomscope.cli.main import _stream_console
    from roomscope.cli.render import render_error

    stdin = sys.stdin if stdin is None else stdin
    stdout = sys.stdout if stdout is None else stdout
    color = _color_mode(getattr(args, "color", None))
    refusal = ""
    if getattr(args, "format", None) == "json":
        refusal = _("the menu prints text, not JSON")
    elif not (is_terminal(stdin) and is_terminal(stdout)):
        refusal = _(
            "the menu needs a terminal to type the answers in; "
            "run the commands themselves instead (roomscope --help lists them)"
        )
    if refusal:
        if sys.stderr is not None:
            console = _stream_console(sys.stderr, color)
            print(render_error(console, refusal, hints=["roomscope --help"]), file=sys.stderr)
        return EXIT_REFUSED
    if read is None:
        _enable_line_editing()
        read = input
    return run_menu(read, stdout, root=root_options(args), dispatch=dispatch, color=color)


def run_menu(
    read: Reader,
    out: TextIO,
    *,
    root: Sequence[str] = (),
    dispatch: Dispatch | None = None,
    color: str = "auto",
    terminal_edition: bool | None = None,
) -> int:
    """Show the menu until the user leaves; the exit code (0, or 130 for Ctrl+C)."""
    if terminal_edition is None:
        from roomscope.edition import is_terminal_package

        terminal_edition = is_terminal_package()
    menu = Menu(
        read=read,
        out=out,
        dispatch=dispatch or _run_command,
        root=list(root),
        color=_color_mode(color),
        terminal_edition=terminal_edition,
    )
    return menu.loop()


def _color_mode(value: object) -> ColorMode:
    return next((mode for mode in COLOR_MODES if mode == value), "auto")


def _run_command(argv: list[str]) -> int:
    """One command through the command line's own entry point, in this process."""
    from roomscope.cli.main import main

    return main(argv)


def _enable_line_editing() -> None:
    """Arrow keys and history at the questions, where Python has readline."""
    with contextlib.suppress(ImportError):
        import readline  # noqa: F401 - loading it is enough: input() then edits lines


# --- Answers -----------------------------------------------------------------------------


_QUOTES = {'"': '"', "'": "'", "“": "”", "‘": "’", "「": "」"}


def clean_path(text: str, *, posix: bool | None = None) -> str:
    """A path as typed, pasted or dragged into the terminal, as a plain path.

    Spaces around it and one pair of surrounding quotes go (``"My Take.wav"``,
    ``'My Take.wav'``, “…”); PowerShell's ``& '…'`` goes too. On macOS and
    Linux a path that is not quoted loses the backslashes a drag and drop
    adds (``My\\ Take.wav``); on Windows a backslash is a separator and stays.
    ``~`` is left for :func:`as_path`.
    """
    posix = os.name != "nt" if posix is None else posix
    text = text.strip()
    if text.startswith("& ") and text[2:].lstrip()[:1] in _QUOTES:
        text = text[2:].lstrip()
    if len(text) >= 2 and _QUOTES.get(text[0]) == text[-1]:
        return text[1:-1]
    if posix and "\\" in text:
        text = re.sub(r"\\(.)", r"\1", text)
    return text


def as_path(text: str, *, posix: bool | None = None) -> Path:
    """:func:`clean_path`, with ``~`` expanded."""
    return Path(clean_path(text, posix=posix)).expanduser()


def _required_path(text: str) -> Path:
    if not clean_path(text):
        raise InvalidAnswerError(_("Type an answer, or press Ctrl+C to go back to the menu."))
    return as_path(text)


def existing_file(text: str) -> Path:
    """A file that exists (a recording, a sweep)."""
    path = _required_path(text)
    if path.is_dir():
        raise InvalidAnswerError(
            _("{path} is a folder; type the path of a file.").format(path=path)
        )
    if not path.is_file():
        raise InvalidAnswerError(
            _("{path} was not found; check the path and type it again.").format(path=path)
        )
    return path


def folder_to_write(text: str) -> Path:
    """A folder to create, or one that exists (not a file)."""
    path = _required_path(text)
    if path.exists() and not path.is_dir():
        raise InvalidAnswerError(_("{path} is a file; type a folder.").format(path=path))
    return path


def existing_folder(text: str) -> Path:
    path = _required_path(text)
    if not path.is_dir():
        raise InvalidAnswerError(_("{path} is not an existing folder.").format(path=path))
    return path


def _number(text: str, units: str = "") -> float:
    """``text`` as a number; a unit after it (``10 s``, ``-20 dBFS``) is allowed."""
    cleaned = text.strip().replace(",", ".")
    if units:
        cleaned = re.sub(rf"\s*(?:{units})$", "", cleaned, flags=re.IGNORECASE)
    return float(cleaned)


def number_between(low: int, high: int) -> Callable[[str], int]:
    """A whole number from ``low`` to ``high``."""

    def check(text: str) -> int:
        reason = _("Type a number from {low} to {high}.").format(low=low, high=high)
        if not text.strip().isdigit():
            raise InvalidAnswerError(reason)
        value = int(text.strip())
        if not low <= value <= high:
            raise InvalidAnswerError(reason)
        return value

    return check


def one_of(numbers: Sequence[int], reason: str) -> Callable[[str], int | None]:
    """One of ``numbers``; an empty answer is ``None`` (the system default)."""

    def check(text: str) -> int | None:
        if not text.strip():
            return None
        if text.strip().isdigit() and int(text.strip()) in numbers:
            return int(text.strip())
        raise InvalidAnswerError(reason)

    return check


def sample_rate(text: str) -> int:
    """A supported sample rate: ``48000``, ``48k``, ``44.1 kHz``."""
    from roomscope.models.configuration import SUPPORTED_SAMPLE_RATES

    reason = _("Type one of these sample rates: {rates}.").format(
        rates=list_join(str(rate) for rate in SUPPORTED_SAMPLE_RATES)
    )
    match = re.fullmatch(r"\s*([\d.,]+)\s*(k?)(?:hz)?\s*", text, flags=re.IGNORECASE)
    if match is None:
        raise InvalidAnswerError(reason)
    try:
        value = float(match.group(1).replace(",", "."))
    except ValueError:
        raise InvalidAnswerError(reason) from None
    rate = round(value * 1000) if match.group(2) else round(value)
    if rate not in SUPPORTED_SAMPLE_RATES:
        raise InvalidAnswerError(reason)
    return rate


def sweep_seconds(text: str) -> float:
    """The sweep's length: what ``SweepSettings`` accepts (0.5 to 120 s)."""
    low, high = 0.5, 120.0
    try:
        value = _number(text, units="s|sec|seconds?|秒")
    except ValueError:
        value = float("nan")
    if not low <= value <= high:  # NaN fails too
        raise InvalidAnswerError(
            _("Type a duration from {low:g} to {high:g} s.").format(low=low, high=high)
        )
    return value


def level_dbfs(text: str) -> float:
    """A sweep level the command accepts (-80 to 0 dBFS)."""
    low, high = -80.0, 0.0
    try:
        value = _number(text, units="dbfs|db")
    except ValueError:
        value = float("nan")
    if not low <= value <= high:
        raise InvalidAnswerError(
            _("Type a level from {low:g} to {high:g} dBFS.").format(low=low, high=high)
        )
    return value


def is_yes(text: str) -> bool:
    """``y`` or ``yes``, or a word for yes in the interface language."""
    words = {"y", "yes"}
    words.update(re.split(r"[\s,、，]+", pgettext("answers meaning yes", "y yes").casefold()))
    return text.strip().casefold() in words - {""}


# --- Sessions ------------------------------------------------------------------------------


def find_sessions(roots: Sequence[Path], *, limit: int = MAX_LISTED) -> list[SessionListing]:
    """Saved sessions in ``roots`` and up to two folders below, newest first.

    Hidden folders are skipped and a folder that cannot be read is left out;
    the search never goes deeper, so starting in a home folder stays quick.
    """
    from roomscope.io.session_store import SESSION_FILE, SessionListing, load_session

    found: dict[Path, SessionListing] = {}
    for root in roots:
        for pattern in (SESSION_FILE, f"*/{SESSION_FILE}", f"*/*/{SESSION_FILE}"):
            try:
                candidates = sorted(root.glob(pattern))
            except OSError:
                continue
            for candidate in candidates:
                parts = candidate.relative_to(root).parts[:-1]
                if any(part.startswith(".") for part in parts):
                    continue
                try:
                    key = candidate.parent.resolve()
                    if key not in found:
                        found[key] = SessionListing(candidate.parent, load_session(candidate))
                except (RoomScopeError, OSError):
                    continue
    listed = sorted(found.values(), key=lambda item: item.session.created_at, reverse=True)
    return listed[:limit]


def shown_path(path: Path) -> str:
    """``path`` relative to the current folder when it is inside it."""
    if not path.is_absolute():
        return str(path)
    with contextlib.suppress(ValueError, OSError):
        relative = path.resolve().relative_to(Path.cwd().resolve())
        return str(relative) if relative.parts else "."
    return str(path)


def path_arg(path: Path | str) -> str:
    """``path`` as a command-line argument: ``./-take.wav``, never an option."""
    text = str(path)
    return os.curdir + os.sep + text if text.startswith("-") else text


def new_session_folder(base: Path) -> Path:
    """The first ``session-N`` that does not exist yet in ``base``."""
    number = 1
    while (base / f"session-{number}").exists():
        number += 1
    return base / f"session-{number}"


def sweep_beside(recording: Path) -> Path | None:
    """``sweep.wav`` next to the recording, else in the current folder."""
    for candidate in (recording.parent / "sweep.wav", Path("sweep.wav")):
        if candidate.is_file():
            return candidate
    return None


# --- The menu ------------------------------------------------------------------------------


@dataclass(frozen=True)
class _Item:
    key: str
    label: str
    description: str
    action: Callable[[], None]


@dataclass
class Menu:
    """One menu session: what was typed and what the commands run with."""

    read: Reader
    out: TextIO
    dispatch: Dispatch
    #: Options before the command (``--lang en``, ``--backend fake``) kept for every command.
    root: list[str] = field(default_factory=list)
    color: ColorMode = "auto"
    terminal_edition: bool = False

    # Output --------------------------------------------------------------------------------

    def console(self) -> Console:
        # The style stored by ``roomscope config style`` applies here as well.
        from roomscope.cli.main import _stream_console

        return _stream_console(self.out, self.color)

    def write(self, lines: Sequence[str]) -> None:
        self.out.write(self.console().fit("\n".join(lines)) + "\n")
        self.out.flush()

    def write_text(self, text: str) -> None:
        """A block another renderer already laid out (the device list, an error)."""
        self.out.write(text + "\n")
        self.out.flush()

    def warn(self, text: str) -> None:
        self.write(self.console().status("warn", text))

    def heading(self, text: str) -> None:
        self.write(self.console().section(text))

    # Questions -----------------------------------------------------------------------------

    def _input(self, prompt: str) -> str:
        c = self.console()
        text = c.readable(prompt)
        trailing = text[len(text.rstrip()) :]
        margin = " " * (len(text) - len(text.lstrip(" ")))
        # A question longer than the screen is written in lines, so the answer is
        # typed on a line with room; only the last line is the prompt.
        lines = wrap(text.strip(), max(c.width - _ANSWER_ROOM, 20), first=margin)
        for line in lines[:-1]:
            self.out.write(c.fit(line) + "\n")
        try:
            return self.read(c.fit(lines[-1] + trailing))
        except KeyboardInterrupt:
            self.out.write("\n")
            raise _BackToMenuError from None
        except EOFError:
            self.out.write("\n")
            raise _LeaveMenuError(EXIT_OK) from None

    def ask(
        self,
        question: str,
        check: Callable[[str], T],
        *,
        default: str | None = None,
        shown: str | None = None,
    ) -> T:
        """Ask until ``check`` takes the answer; an empty answer takes ``default``."""
        if default is None and shown is None:
            prompt = _("{question}: ").format(question=question)
        else:
            prompt = _("{question} [{default}]: ").format(
                question=question, default=default if shown is None else shown
            )
        while True:
            text = self._input("  " + prompt).strip()
            if not text and default is not None:
                text = default
            try:
                return check(text)
            except InvalidAnswerError as reason:
                self.warn(str(reason))

    def confirm(self, question: str) -> bool:
        """Yes only for an explicit yes; Enter is no."""
        return is_yes(self._input("  " + _("{question} [y/N]: ").format(question=question)))

    def pause(self) -> None:
        with contextlib.suppress(_BackToMenuError):
            self._input(_("Press Enter to return to the menu") + " ")

    # Running commands ----------------------------------------------------------------------

    def command_line(self, argv: Sequence[str]) -> str:
        return shell_command(["roomscope", *self.root, *argv])

    def same_as(self, argv: Sequence[str]) -> None:
        """The command a step stands for, whole on one line to be copied."""
        same = _("Same as the command: {command}").format(command=self.command_line(argv))
        self.write(["", *self.console().status("next", Verbatim(same), indent=0), ""])

    def run(self, argv: list[str]) -> int:
        """Print the command, run it here, and say in words when it failed."""
        c = self.console()
        self.same_as(argv)
        try:
            code = self.dispatch([*self.root, *argv])
        except SystemExit as stop:  # argparse: --help, or arguments it refused
            code = stop.code if isinstance(stop.code, int) else (0 if stop.code is None else 1)
        except KeyboardInterrupt:
            code = EXIT_INTERRUPTED
        if code:
            reason = {
                2: _("it could not run as asked"),
                EXIT_INTERRUPTED: _("it was interrupted"),
            }.get(code, _("an error stopped it"))
            self.write(
                [
                    "",
                    *c.status(
                        "error",
                        _("The command did not succeed: {reason} (exit status {code}).").format(
                            reason=reason, code=code
                        ),
                        indent=0,
                    ),
                ]
            )
        return code

    def run_and_pause(self, argv: list[str]) -> None:
        self.run(argv)
        self.out.write("\n")
        self.pause()

    def show_error(self, exc: BaseException, *, detail: str = "") -> None:
        from roomscope.cli.render import render_error

        message = localize(str(exc)) if isinstance(exc, RoomScopeError) else str(exc)
        self.write_text(render_error(self.console(), message, detail=detail))

    # The screen ----------------------------------------------------------------------------

    def items(self) -> list[tuple[str, list[_Item]]]:
        measurement = [
            _Item(
                "1",
                pgettext("menu", "Try the demo"),
                _("synthetic data, no audio interface needed"),
                self.demo,
            ),
            _Item(
                "2",
                _("Write the test signal"),
                _("a sweep WAV to play and record in your DAW"),
                self.sweep,
            ),
            _Item(
                "3",
                _("Analyse a recording"),
                _("a WAV recorded while the sweep played"),
                self.analyze,
            ),
            _Item(
                "4",
                _("Measure with your interface"),
                _("RoomScope plays the sweep and records"),
                self.measure,
            ),
        ]
        results = [
            _Item("5", _("View results"), _("a saved session or comparison"), self.show),
            _Item(
                "6",
                _("Compare two positions"),
                _("what changed between two sessions"),
                self.compare,
            ),
        ]
        if not self.terminal_edition:
            results.append(
                _Item("7", _("Open the desktop app"), _("the results with charts"), self.gui)
            )
        other = [
            _Item(
                "8",
                _("Settings"),
                _("language, profile, backend, output folder"),
                self.settings,
            ),
            _Item("9", _("Environment report"), _("for bug reports"), self.doctor),
        ]
        return [
            (_("Measurement"), measurement),
            (_("Results"), results),
            (_("Settings and diagnostics"), other),
        ]

    def screen(self, groups: Sequence[tuple[str, Sequence[_Item]]]) -> list[str]:
        from roomscope.cli.config import language_hint_lines
        from roomscope.i18n import current_locale

        c = self.console()
        quit_row = ("0", _("Quit"), _("or type q"))
        rows = [(item.key, item.label, item.description) for _h, items in groups for item in items]
        width = max(
            cell_width(c.readable(f"{key}  {label}")) for key, label, _d in [*rows, quit_row]
        )

        def listed(entries: Sequence[tuple[str, str, str]]) -> list[str]:
            return c.commands(
                [(pad(f"{key}  {label}", width), text) for key, label, text in entries]
            )

        lines = c.title(_("RoomScope menu"))
        lines += c.paragraph(
            _(
                "Type a number and press Enter. Each step shows the command it runs, "
                "so you can type it yourself next time."
            ),
            indent=0,
        )
        for heading, items in groups:
            lines += c.section(heading)
            lines += listed([(item.key, item.label, item.description) for item in items])
        lines.append("")
        lines += listed([quit_row])
        # The way to the other language, written in that language, as on the home screen.
        hint = language_hint_lines(current_locale(), c.width)
        if hint and c.can_write("".join(hint)):
            lines.append("")
            lines += [c.muted(line) for line in hint]
        return [line.rstrip() for line in lines]

    def loop(self) -> int:
        try:
            while True:
                groups = self.items()
                actions = {item.key: item for _h, items in groups for item in items}
                self.write(["", *self.screen(groups), ""])
                item = self.choose(actions)
                if item is None:
                    return EXIT_OK
                try:
                    self.heading(item.label)
                    item.action()
                except _BackToMenuError:
                    continue
                except KeyboardInterrupt:  # while the menu itself was busy (listing sessions)
                    self.out.write("\n")
                    continue
                except (RoomScopeError, OSError) as exc:
                    self.show_error(exc)
                    self.pause()
        except _LeaveMenuError as leave:
            return leave.code

    def choose(self, actions: Mapping[str, _Item]) -> _Item | None:
        """The item typed at the menu; ``None`` to leave."""
        while True:
            try:
                answer = self.read(self.console().fit(_("Choose a number: ")))
            except KeyboardInterrupt:
                self.out.write("\n")
                raise _LeaveMenuError(EXIT_INTERRUPTED) from None
            except EOFError:
                self.out.write("\n")
                raise _LeaveMenuError(EXIT_OK) from None
            key = answer.strip().casefold()
            if not key:
                continue
            if key == "0" or key in _QUIT_WORDS:
                return None
            if key in actions:
                return actions[key]
            self.warn(
                _("There is no item {choice} in the menu; type one of the numbers shown.").format(
                    choice=answer.strip()
                )
            )

    def output_base(self) -> Path:
        """Where new sessions go: the output folder from the settings, else here."""
        from roomscope.settings import load_settings

        folder = load_settings().output_dir
        if folder and Path(folder).is_dir():
            return Path(folder)
        return Path()

    def ask_session_folder(self, question: str) -> Path:
        """A folder for a new session; replacing a saved one is confirmed first."""
        while True:
            folder = self.ask(
                question, folder_to_write, default=str(new_session_folder(self.output_base()))
            )
            if not (folder / "session.json").exists():
                return folder
            if self.confirm(_("{path} holds a saved session. Replace it?").format(path=folder)):
                return folder

    # Items -----------------------------------------------------------------------------------

    def demo(self) -> None:
        from roomscope.cli.main import DEMO_FOLDER, _is_demo_folder

        while True:
            folder = self.ask(_("Folder for the demo files"), _required_path, default=DEMO_FOLDER)
            occupied = folder.exists() and (not folder.is_dir() or any(folder.iterdir()))
            if not occupied:
                break
            if _is_demo_folder(folder):
                if self.confirm(_("{path} holds an earlier demo. Replace it?").format(path=folder)):
                    break
                continue
            self.warn(
                _(
                    "{path} already exists and was not written by roomscope demo; "
                    "choose another folder."
                ).format(path=folder)
            )
        argv = ["demo"] if str(folder) == DEMO_FOLDER else ["demo", "--out", path_arg(folder)]
        self.run_and_pause(argv)

    def sweep(self) -> None:
        from roomscope.models.configuration import DEFAULT_SAMPLE_RATE, SUPPORTED_SAMPLE_RATES

        while True:
            path = self.ask(_("File for the test signal"), _required_path, default="sweep.wav")
            if path.is_dir():
                self.warn(_("{path} is a folder; type the path of a file.").format(path=path))
                continue
            if path.suffix.lower() != ".wav":  # the test signal is always a WAV file
                path = path.with_name(path.name + ".wav")
            if not path.exists() or self.confirm(
                _("{path} already exists. Replace it?").format(path=path)
            ):
                break
        rate = self.ask(
            _("Sample rate in Hz ({rates})").format(
                rates=list_join(str(rate) for rate in SUPPORTED_SAMPLE_RATES)
            ),
            sample_rate,
            default=str(DEFAULT_SAMPLE_RATE),
        )
        seconds = self.ask(
            _("Length of the sweep in seconds"), sweep_seconds, default=f"{_SWEEP_SECONDS:g}"
        )
        argv = ["sweep", "--out", path_arg(path)]
        if rate != DEFAULT_SAMPLE_RATE:
            argv += ["--sample-rate", str(rate)]
        if seconds != _SWEEP_SECONDS:
            argv += ["--duration", f"{seconds:g}"]
        self.run_and_pause(argv)

    def analyze(self) -> None:
        recording = self.ask(
            _("Recording (a WAV file; you can drag it into this window)"), existing_file
        )
        found = sweep_beside(recording)
        sweep = self.ask(
            _("Test signal played for it"),
            existing_file,
            default=None if found is None else shown_path(found),
        )
        out = self.ask_session_folder(_("Folder for the results"))
        self.run_and_pause(
            [
                "analyze",
                "--recording",
                path_arg(recording),
                "--sweep",
                path_arg(sweep),
                "--out",
                path_arg(out),
            ]
        )

    def _devices(self) -> list[DeviceInfo]:
        from roomscope.audio.backend import get_backend
        from roomscope.cli.render import render_devices

        name = None
        if "--backend" in self.root:
            name = self.root[self.root.index("--backend") + 1]
        devices = get_backend(name).list_devices()
        self.write_text(render_devices(self.console(), devices) + "\n")
        return devices

    def measure(self) -> None:
        from roomscope.audio.backend import SAFE_MAX_LEVEL_DBFS, SAFETY_MESSAGE
        from roomscope.cli.render import rate_text
        from roomscope.models.configuration import DEFAULT_SAMPLE_RATE

        self.same_as(["devices"])
        try:
            devices = self._devices()
        except RoomScopeError as exc:
            self.show_error(exc, detail=_("Nothing was played."))
            self.pause()
            return
        inputs = [d.index for d in devices if d.max_input_channels > 0]
        outputs = [d.index for d in devices if d.max_output_channels > 0]
        input_device = self.ask(
            _("Input device (the microphone)"),
            one_of(
                inputs,
                _("Type one of these input devices: {devices}, or press Enter.").format(
                    devices=list_join(str(i) for i in inputs)
                ),
            ),
            default="",
            shown=_("system default"),
        )
        output_device = self.ask(
            _("Output device (the loudspeakers)"),
            one_of(
                outputs,
                _("Type one of these output devices: {devices}, or press Enter.").format(
                    devices=list_join(str(i) for i in outputs)
                ),
            ),
            default="",
            shown=_("system default"),
        )
        microphone = _device(devices, input_device, "is_default_input")
        speaker = _device(devices, output_device, "is_default_output")
        channels = microphone.max_input_channels if microphone is not None else 1
        channel = self.ask(
            _("Input channel of the microphone"), number_between(1, max(1, channels)), default="1"
        )
        acknowledged = False
        while True:
            level = self.ask(
                _("Level of the sweep in dBFS"), level_dbfs, default=f"{_MEASURE_LEVEL:g}"
            )
            if level <= SAFE_MAX_LEVEL_DBFS:
                break
            if self.confirm(
                _(
                    "{level:g} dBFS is above {max_level:g} dBFS. "
                    "Is the monitor level already turned down?"
                ).format(level=level, max_level=SAFE_MAX_LEVEL_DBFS)
            ):
                acknowledged = True
                break
        out = self.ask_session_folder(_("Folder for the session"))

        c = self.console()

        def device_text(device: DeviceInfo | None) -> str:
            return f"[{device.index}] {device.name}" if device else _("system default")

        lines = c.section(_("Measurement plan"))
        lines += c.fields(
            [
                (
                    _("Input"),
                    device_text(microphone)
                    + c.sep()
                    + _("input {channels}").format(channels=channel),
                ),
                (
                    _("Output"),
                    device_text(speaker) + c.sep() + _("output {channel}").format(channel=1),
                ),
                (_("Level"), f"{level:g} dBFS"),
                (
                    _("Sweep"),
                    f"{_SWEEP_SECONDS:g} s{c.sep()}{rate_text(DEFAULT_SAMPLE_RATE)}",
                ),
                (_("Save to"), Verbatim(str(out))),
            ]
        )
        lines.append("")
        lines += c.status("warn", _(SAFETY_MESSAGE), indent=0)
        self.write(lines)
        if not self.confirm(_("Type y to play the sweep now")):
            self.write(c.status("info", _("Nothing was played.")))
            self.out.write("\n")
            self.pause()
            return
        argv = ["measure", "--out", path_arg(out)]
        if input_device is not None:
            argv += ["--input-device", str(input_device)]
        if output_device is not None:
            argv += ["--output-device", str(output_device)]
        if channel != 1:
            argv += ["--input-channel", str(channel)]
        if level != _MEASURE_LEVEL:
            argv += ["--level", f"{level:g}"]
        if acknowledged:
            argv.append("--acknowledge-level")
        self.run_and_pause(argv)

    def sessions(self) -> list[SessionListing]:
        """Saved sessions here and in the output folder, listed as a table."""
        from roomscope.cli.render import created_text

        roots = [Path()]
        base = self.output_base()
        if base.is_absolute() and base.resolve() != Path.cwd().resolve():
            roots.append(base)
        listed = find_sessions(roots)
        c = self.console()
        if not listed:
            self.write(
                c.paragraph(
                    _("No saved sessions were found in this folder or in the output folder.")
                )
            )
            return listed
        headers = [_("No."), _("Session"), _("Position"), _("Created")]
        rows = [
            [
                str(number),
                Verbatim(shown_path(item.path)),
                item.session.measurement_position or item.session.room_name or c.dash(),
                created_text(item.session.created_at),
            ]
            for number, item in enumerate(listed, start=1)
        ]
        # A long position ("A: close to the desk and the side wall") is cut to
        # the room the other columns leave, so each session keeps one line. A
        # bordered table takes 3 cells a column and 1 more (the plain one 2 and
        # 3 a gap): the room is reckoned for the wider, so with either the
        # narrow columns keep their headers whole.
        widths = [max(cell_width(c.readable(row[i])) for row in [headers, *rows]) for i in range(4)]
        room = c.width - (3 * len(headers) + 1) - widths[0] - widths[1] - widths[3]
        if room >= 12:  # narrower, and the table becomes blocks that show it whole
            for row in rows:
                row[2] = truncate(row[2], room, "…" if c.unicode else "...")
        lines = c.table(headers, rows, align="rlll")
        if len(listed) == MAX_LISTED:
            lines += c.paragraph(
                _("The {count} newest are listed; type a path for an older one.").format(
                    count=MAX_LISTED
                ),
                style=("dim",),
            )
        self.write(["", *lines, ""])
        return listed

    def pick_session(
        self, question: str, listed: Sequence[SessionListing], *, other_than: Path | None = None
    ) -> Path:
        def check(text: str) -> Path:
            cleaned = clean_path(text)
            if cleaned.isdigit() and not Path(cleaned).exists():
                chosen = int(cleaned)
                if not 1 <= chosen <= len(listed):
                    raise InvalidAnswerError(
                        _("Type a number from {low} to {high}.").format(low=1, high=len(listed))
                        if listed
                        else _("Type the path of a session folder.")
                    )
                path = Path(shown_path(listed[chosen - 1].path))
            else:
                path = _required_path(text)
                if not path.exists():
                    raise InvalidAnswerError(
                        _("{path} was not found; check the path and type it again.").format(
                            path=path
                        )
                    )
            if other_than is not None and path.resolve() == other_than.resolve():
                raise InvalidAnswerError(_("That is the baseline; choose another session."))
            return path

        return self.ask(question, check)

    def show(self) -> None:
        listed = self.sessions()
        question = (
            _("Session number, or the path of a session or comparison")
            if listed
            else _("Path of a session folder or comparison.json")
        )
        target = self.pick_session(question, listed)
        self.run_and_pause(["show", path_arg(target)])

    def compare(self) -> None:
        listed = self.sessions()
        baseline = self.pick_session(_("Baseline (before): number or path"), listed)
        candidate = self.pick_session(
            _("Candidate (after): number or path"), listed, other_than=baseline
        )
        self.run_and_pause(["compare", path_arg(baseline), path_arg(candidate)])

    def gui(self) -> None:
        self.run_and_pause(["gui"])

    def doctor(self) -> None:
        self.run_and_pause(["doctor"])

    # Settings ------------------------------------------------------------------------------

    def settings(self) -> None:
        """The settings ``roomscope config`` changes, one list per setting."""
        from roomscope.cli import config
        from roomscope.i18n import language_choice
        from roomscope.settings import load_settings

        keys = ("language", "profile", "backend", "output-folder")
        changers: dict[str, Callable[[], list[str] | None]] = {
            "language": self.choose_language,
            "profile": self.choose_profile,
            "backend": self.choose_backend,
            "output-folder": self.choose_output_folder,
        }

        def title(key: str) -> str:
            # The menu writes new sessions there too: not "(desktop app)" only.
            return _("Output folder") if key == "output-folder" else config.title(key)

        while True:
            stored = load_settings()
            choice = language_choice(self._root_lang())
            rows = [
                (
                    str(number),
                    title(key),
                    (stored.output_dir or _("not set"))
                    if key == "output-folder"
                    else config.state(key, stored, choice),
                )
                for number, key in enumerate(keys, start=1)
            ]
            rows.append(("0", _("Back to the menu"), ""))
            self.write(self._choices(rows))
            number = self.ask(_("Choose a number"), number_between(0, len(keys)))
            if number == 0:
                return
            key = keys[number - 1]
            self.heading(title(key))
            argv = changers[key]()
            if argv is None:
                continue
            code = self.run(["config", key, *argv])
            if key == "language" and code == 0:
                self._forget_root_lang()

    def _choices(self, rows: Sequence[tuple[str, str, str]]) -> list[str]:
        c = self.console()
        width = max(cell_width(c.readable(f"{key}  {label}")) for key, label, _t in rows)
        lines = c.commands([(pad(f"{key}  {label}", width), text) for key, label, text in rows])
        return ["", *(line.rstrip() for line in lines)]

    def _root_lang(self) -> str | None:
        if "--lang" in self.root:
            return self.root[self.root.index("--lang") + 1]
        return None

    def _forget_root_lang(self) -> None:
        """The language just stored applies from now on, not the one given at the start."""
        from roomscope.i18n import activate

        if "--lang" in self.root:
            where = self.root.index("--lang")
            del self.root[where : where + 2]
        activate(None)

    def _pick(self, rows: Sequence[tuple[str, str]], values: Sequence[str]) -> str | None:
        """One of ``values`` from a numbered list; ``None`` for 0 (back)."""
        numbered = [(str(n), label, text) for n, (label, text) in enumerate(rows, start=1)]
        self.write(self._choices([*numbered, ("0", _("Back"), "")]))
        number = self.ask(_("Choose a number"), number_between(0, len(values)))
        return None if number == 0 else values[number - 1]

    def choose_language(self) -> list[str] | None:
        from roomscope.cli import config
        from roomscope.i18n import LANGUAGE_NAMES, available_locales
        from roomscope.settings import load_settings

        found = available_locales()
        langs = [lang for lang in _LANGUAGE_ORDER if lang in found]
        langs += [lang for lang in found if lang not in langs]
        stored = load_settings().language
        current = _("current setting")
        rows: list[tuple[str, str]] = []
        for lang in langs:
            native = LANGUAGE_NAMES.get(lang, lang)
            here = config.language_name(lang)
            text = "" if here == native else here
            if lang == stored:
                text = current if not text else text + self.console().sep() + current
            rows.append((native, text))
        rows.append((_("follow the system"), "" if stored else current))
        value = self._pick(rows, [*langs, config.AUTO])
        return None if value is None else [value]

    def choose_profile(self) -> list[str] | None:
        from roomscope.interpretation import available_profiles
        from roomscope.interpretation.profiles import profile_title
        from roomscope.settings import load_settings

        names = list(available_profiles())
        stored = load_settings().default_profile
        rows = [
            (
                profile_title(name),
                name + (self.console().sep() + _("current setting") if name == stored else ""),
            )
            for name in names
        ]
        value = self._pick(rows, names)
        return None if value is None else [value]

    def choose_backend(self) -> list[str] | None:
        from roomscope.cli import config
        from roomscope.settings import load_settings

        stored = load_settings().audio_backend
        sep, current = self.console().sep(), _("current setting")
        rows = [
            (
                "portaudio",
                _("the audio interfaces of this computer")
                + (sep + current if stored == "portaudio" else ""),
            ),
            (
                "fake",
                _("simulated interface, for the demo and tests")
                + (sep + current if stored == "fake" else ""),
            ),
            (
                config.AUTO,
                _("PortAudio (the default)") + ("" if stored else sep + current),
            ),
        ]
        value = self._pick(rows, ["portaudio", "fake", config.AUTO])
        return None if value is None else [value]

    def choose_output_folder(self) -> list[str] | None:
        from roomscope.cli import config
        from roomscope.settings import load_settings

        stored = load_settings().output_dir

        def check(text: str) -> str | None:
            if not text:
                return None
            if text.strip().casefold() == config.AUTO:
                return config.AUTO
            return path_arg(existing_folder(text))

        value = self.ask(
            _("Default output folder (auto clears it)"),
            check,
            default="",
            shown=stored or _("not set"),
        )
        if value is None:
            self.write(self.console().status("info", _("Nothing was changed.")))
            return None
        return [value]


def _device(devices: Sequence[DeviceInfo], index: int | None, default: str) -> DeviceInfo | None:
    if index is not None:
        return next((d for d in devices if d.index == index), None)
    return next((d for d in devices if getattr(d, default)), None)
