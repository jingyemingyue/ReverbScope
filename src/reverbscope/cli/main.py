"""``reverbscope`` command-line interface.

Subcommands, in the order of the workflow: ``demo``, ``gui``, ``sweep``,
``analyze``, ``devices``, ``measure``, ``analyze-ir``, ``show``, ``compare``,
``project``, ``export``, ``session``, ``config``, ``doctor``, ``schema``.

Reports go to stdout and diagnostics to stderr; all text is laid out by
:mod:`reverbscope.cli.render` through :mod:`reverbscope.cli.console`. A user error
is one ``× error:`` block with commands to try, never a traceback (``--verbose``
adds it). With ``--format json`` stdout carries the JSON document only.
"""

from __future__ import annotations

import argparse
import codecs
import contextlib
import errno
import json
import logging
import math
import os
import re
import shlex
import sys
import tempfile
import traceback
from collections.abc import Iterator, Sequence
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from reverbscope import __version__
from reverbscope.cli.console import (
    COLOR_MODES,
    Console,
    ProgressLine,
    Verbatim,
    cell_width,
    printable,
    shell_command,
    truncate,
)
from reverbscope.cli.render import (
    render_analysis,
    render_comparison,
    render_config,
    render_config_key,
    render_config_language,
    render_config_saved,
    render_demo,
    render_devices,
    render_environment,
    render_error,
    render_home,
    render_host_apis,
    render_inventory,
    render_measure_plan,
    render_saved_next_steps,
    render_status,
    render_sweep_written,
    render_terminal_edition_gui,
)
from reverbscope.errors import (
    AudioBackendUnavailableError,
    AudioDeviceError,
    ConfigurationError,
    InvalidAudioError,
    MeasurementCancelledError,
    ReverbScopeError,
    SessionError,
)
from reverbscope.health import assess, failure_guidance
from reverbscope.i18n import N_, _, activate, list_separator, localize, pgettext
from reverbscope.interpretation import available_profiles
from reverbscope.interpretation.profiles import band_text
from reverbscope.interpretation.verdicts import judge_comparison
from reverbscope.labels import accuracy_class_text
from reverbscope.logging_config import configure_logging
from reverbscope.models.configuration import (
    DEFAULT_SAMPLE_RATE,
    SUPPORTED_SAMPLE_RATES,
    AnalysisSettings,
    SweepSettings,
)

if TYPE_CHECKING:
    from reverbscope.audio.backend import ChannelPlan

log = logging.getLogger("reverbscope.cli")


#: argparse's own texts. The standard library looks them up in gettext's
#: "argparse" domain, which has no Chinese catalog; ReverbScope's catalog
#: translates the ones a user sees: the help layout and the parse errors.
ARGPARSE_MESSAGES = frozenset(
    {
        N_("usage: "),
        N_("positional arguments"),
        N_("options"),
        N_("%(heading)s:"),
        N_(" (default: %(default)s)"),
        N_("%(prog)s: error: %(message)s\n"),
        N_("argument %(argument_name)s: %(message)s"),
        N_("ambiguous option: %(option)s could match %(matches)s"),
        N_("expected one argument"),
        N_("expected at least one argument"),
        N_("expected at most one argument"),
        N_("invalid %(type)s value: %(value)r"),
        N_("invalid choice: %(value)r (choose from %(choices)s)"),
        N_("not allowed with argument %s"),
        N_("one of the arguments %s is required"),
        N_("the following arguments are required: %s"),
        N_("unrecognized arguments: %s"),
        N_("show this help message and exit"),
        N_("show program's version number and exit"),
        N_("can't open '%(filename)s': %(error)s"),
        N_("ignored explicit argument %r"),
        N_("unknown parser %(parser_name)r (choices: %(choices)s)"),
        N_("unexpected option string: %s"),
        # ngettext: "--band 20" (two values expected). Chinese has one form.
        N_("expected %s argument"),
        N_("expected %s arguments"),
    }
)


#: argparse messages with a list argparse joined with ", " (all of it, or the
#: named field); the list is re-joined with the language's separator.
_LIST_ARGUMENTS: dict[str, str | None] = {
    "the following arguments are required: %s": None,
    "invalid choice: %(value)r (choose from %(choices)s)": "choices",
    "unknown parser %(parser_name)r (choices: %(choices)s)": "choices",
    "ambiguous option: %(option)s could match %(matches)s": "matches",
}


class _ListTemplate(str):
    """A translated argparse template whose list argument, which argparse
    joins with ``", "`` before filling it in, reads as a list of the active
    language once filled in (``缺少必需的参数：项目、会话、--position``)."""

    field: str | None

    def __new__(cls, text: str, field: str | None) -> _ListTemplate:
        made = super().__new__(cls, text)
        made.field = field
        return made

    def __mod__(self, values: Any) -> str:
        separator = list_separator()
        if self.field is None and isinstance(values, str):
            values = values.replace(", ", separator)
        elif isinstance(values, dict) and isinstance(values.get(self.field), str):
            items = values[self.field].split(", ")
            if self.field == "choices":
                items = [_quoted_choice(item) for item in items]
            values = {**values, self.field: separator.join(items)}
        filled: str = str(self) % values
        return filled


def _quoted_choice(item: str) -> str:
    """One choice of an "invalid choice" error, quoted as the typed value is.

    Python releases disagree: 3.12.3 quotes the choices, 3.12.11 and 3.14
    do not, 3.13 quotes them again. One form keeps the message the same on
    every Python.
    """
    if len(item) >= 2 and item[0] == item[-1] and item[0] in "'\"":
        item = item[1:-1]
    return repr(item)


def _argparse_gettext(message: str) -> str:
    if message not in ARGPARSE_MESSAGES:
        return message
    if message in _LIST_ARGUMENTS:
        return _ListTemplate(_(message), _LIST_ARGUMENTS[message])
    return _(message)


def _argparse_ngettext(singular: str, plural: str, n: int) -> str:
    message = singular if n == 1 else plural
    return _(message) if message in ARGPARSE_MESSAGES else message


def _translate_argparse() -> None:
    """Route argparse's module-level ``_`` and ``ngettext`` through ReverbScope's catalog."""
    setattr(argparse, "_", _argparse_gettext)  # noqa: B010 - a module attribute, not ours
    setattr(argparse, "ngettext", _argparse_ngettext)  # noqa: B010


def _type_name(kind: object) -> str | None:
    """The word for a value argparse could not convert ("invalid int value")."""
    if kind is int:
        return pgettext("argument type", "int")
    if kind is float:
        return pgettext("argument type", "float")
    return None


#: The root help lists the commands in these groups, in the order of the
#: workflow: try it, measure, look at the results, then troubleshoot.
COMMAND_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (N_("Get started"), ("demo", "gui")),
    (N_("Measurement"), ("sweep", "analyze", "devices", "measure", "analyze-ir")),
    (N_("Results"), ("show", "compare", "project", "export", "session")),
    (N_("Settings"), ("config",)),
    (N_("Diagnostics"), ("doctor", "schema")),
)

#: A few commands to start from (every flag exists in the parser; a test runs them).
ROOT_EXAMPLES = (
    "reverbscope demo",
    "reverbscope sweep --out sweep.wav",
    "reverbscope analyze --recording take.wav --sweep sweep.wav --out session-1",
    "reverbscope compare session-1 session-2",
)

#: Where ``reverbscope demo`` writes unless told otherwise.
DEMO_FOLDER = "reverbscope-demo"

#: ``--color`` as given on the command line, for messages printed before the
#: arguments are parsed (argparse's own errors).
_COLOR_REQUEST: dict[str, str] = {"mode": "auto"}


class _HelpFormatter(argparse.RawDescriptionHelpFormatter):
    """argparse's layout, with help text wrapped by display width.

    argparse wraps with :mod:`textwrap`, which counts a Chinese character as
    one column, so a translated help line ran past the terminal's edge.
    Indented blocks (the command list, examples) stay as written; a plain
    description or epilog is wrapped by display width.
    """

    def _split_lines(self, text: str, width: int) -> list[str]:
        from reverbscope.cli.console import wrap

        return wrap(" ".join(text.split()), max(width, 11))

    def _fill_text(self, text: str, width: int, indent: str) -> str:
        """Wrap plain paragraphs; leave preformatted blocks (commands) whole.

        The formatter is raw so the grouped command list and the examples stay
        aligned, but a description or epilog that is one sentence must still
        fit a narrow terminal. An example line stays one line so it can be
        copied.
        """
        from reverbscope.cli.console import cell_width, wrap

        blocks: list[str] = []
        for block in text.split("\n\n"):
            rendered: list[str] = []
            lines = block.split("\n")
            preformatted = any(line.startswith((" ", "\t")) for line in lines)
            if preformatted:
                for line in lines:
                    if line.startswith((" ", "\t")) or cell_width(line) <= width:
                        rendered.append(indent + line)
                    else:
                        rendered.extend(indent + part for part in wrap(line, max(width, 11)))
            else:
                paragraph = " ".join(line.strip() for line in lines if line.strip())
                rendered.extend(indent + part for part in wrap(paragraph, max(width, 11)))
            blocks.append("\n".join(rendered))
        # A blank line between paragraphs, as they were written.
        return "\n\n".join(block for block in blocks if block)

    def add_argument(self, action: argparse.Action) -> None:
        """argparse sizes the option column with ``len()``; a translated
        placeholder ("--out 目录") is wider on screen than it is long."""
        super().add_argument(action)
        if action.help is argparse.SUPPRESS:
            return
        from reverbscope.cli.console import cell_width

        invocations = [self._format_action_invocation(action)]
        invocations += [
            self._format_action_invocation(a) for a in self._iter_indented_subactions(action)
        ]
        widest = max(cell_width(text) for text in invocations) + self._current_indent
        self._action_max_length = max(self._action_max_length, widest)

    def _format_action(self, action: argparse.Action) -> str:
        """argparse's layout, with the help column aligned by display width.

        argparse pads an option to the help column with ``%-*s``, which counts
        characters: a row with a Chinese placeholder started its help two
        columns further right for every Chinese character.
        """
        from reverbscope.cli.console import cell_width

        text = super()._format_action(action)
        header = self._format_action_invocation(action)
        extra = cell_width(header) - len(header)
        if extra <= 0 or not action.help:
            return text
        help_position = min(self._action_max_length + 2, self._max_help_position)
        action_width = help_position - self._current_indent - 2
        lead = " " * self._current_indent + header
        first, newline, rest = text.partition("\n")
        if len(header) > action_width or not first.startswith(lead):
            return text  # argparse already put the help on the next line
        after = first[len(lead) :]
        if cell_width(header) <= action_width:
            first = lead + after[extra:]
        else:  # too wide on screen for the column: the help goes below, as argparse does
            first = lead + "\n" + " " * help_position + after.lstrip(" ")
        return first + newline + rest

    def _format_usage(self, usage: Any, actions: Any, groups: Any, prefix: Any) -> str:
        # argparse measures the prefix with len(); "用法：" takes six columns, not three.
        from reverbscope.cli.console import cell_width

        shown = _("usage: ") if prefix is None else prefix
        extra = cell_width(shown) - len(shown)
        self._width -= extra
        try:
            return super()._format_usage(usage, actions, groups, prefix)
        finally:
            self._width += extra

    def _get_help_string(self, action: argparse.Action) -> str | None:
        """The help, plus the default when it tells the reader something.

        Nothing is added for flags, empty or computed defaults, positionals,
        or a help text that already names its default.
        """
        text = action.help or ""
        default = action.default
        if (
            not action.option_strings
            or default is None
            or isinstance(default, bool)  # a flag (1.0 == True: test the type, not the value)
            or default in ("", argparse.SUPPRESS)
            or isinstance(action, argparse._HelpAction | argparse._VersionAction)
            or "default" in text
            or "默认" in text
        ):
            return action.help
        shown = f"{default:g}" if isinstance(default, float) else str(default)
        return text + (_(" (default: %(default)s)") % {"default": shown}).replace("%", "%%")


class _Parser(argparse.ArgumentParser):
    """argparse with ReverbScope's error block instead of the usage dump.

    Exit code 2 and stderr as before; the message is argparse's (translated),
    followed by the command's ``--help`` to try.
    """

    def _get_value(self, action: argparse.Action, arg_string: str) -> Any:
        """argparse's conversion; the type is named in words ("整数"), not as int.

        A path that starts with ``~`` is in the home folder: cmd.exe and
        Windows PowerShell pass ``~`` to a program unexpanded (so does a POSIX
        shell when it is quoted), and ``--out ~/reverbscope-demo`` made a folder
        named ``~`` in the current one.
        """
        try:
            value = super()._get_value(action, arg_string)
        except argparse.ArgumentError:
            name = _type_name(action.type)
            if name is None:
                raise
            message = _("invalid %(type)s value: %(value)r") % {"type": name, "value": arg_string}
            raise argparse.ArgumentError(action, message) from None
        if isinstance(value, Path):
            with contextlib.suppress(RuntimeError):  # no home folder to expand to
                return value.expanduser()
        return value

    def error(self, message: str) -> Any:
        console = Console.for_stream(sys.stderr, _COLOR_REQUEST["mode"])  # type: ignore[arg-type]
        text = render_error(console, message, hints=[f"{self.prog} --help"])
        self.exit(2, text + "\n")


def _heading(text: str) -> str:
    """A help section heading in argparse's own style ("options:" / "选项：")."""
    return _("%(heading)s:") % {"heading": text}


def _examples_block(examples: Sequence[str]) -> str:
    return "\n".join([_heading(_("examples")), *(f"  {line}" for line in examples)])


def _command(
    sub: object, name: str, text: str, *, examples: Sequence[str] = ()
) -> argparse.ArgumentParser:
    """Subcommand with the same gettext string as help (parent list) and description."""
    parser = sub.add_parser(  # type: ignore[attr-defined]
        name,
        help=text,
        description=text,
        add_help=False,
        epilog=_examples_block(examples) if examples else None,
        formatter_class=_HelpFormatter,
    )
    parser.add_argument("-h", "--help", action="help", help=_("show this help message and exit"))
    return cast(argparse.ArgumentParser, parser)


def _settings_block(keys: Any) -> str:
    """``reverbscope config --help``: each setting and the values it takes."""
    from reverbscope.cli.console import is_terminal, terminal_width, wrap

    width = terminal_width(sys.stdout, is_terminal(sys.stdout), os.environ)
    name_width = max(len(key) for key in keys.KEYS) + 2
    lines = [_heading(_("settings"))]
    for key in keys.KEYS:
        prefix = f"  {key.ljust(name_width)}"
        lines += wrap(keys.choices(key), width, first=prefix, rest=" " * len(prefix))
    return "\n".join(lines)


def _commands_block(helps: dict[str, str]) -> str:
    """The root help's command list, grouped and aligned (display width aware)."""
    from reverbscope.cli.console import is_terminal, terminal_width, wrap

    # sys.stdout is None in a windowed bundle (reverbscope-gui); never touch it directly.
    width = terminal_width(sys.stdout, is_terminal(sys.stdout), os.environ)
    name_width = max(len(name) for name in helps) + 2
    lines = [_heading(_("commands"))]
    listed: set[str] = set()
    for group, names in COMMAND_GROUPS:
        present = [name for name in names if name in helps]
        if not present:
            continue
        lines.append(f"  {_(group)}")
        for name in present:
            listed.add(name)
            prefix = f"    {name.ljust(name_width)}"
            lines += wrap(helps[name], width, first=prefix, rest=" " * len(prefix))
    for name in helps:  # a command added without a group still shows
        if name not in listed:
            lines.append(f"    {name.ljust(name_width)}{helps[name]}")
    return "\n".join(lines)


def _add_sweep_arguments(parser: argparse.ArgumentParser, *, default_level: float) -> None:
    group = parser.add_argument_group(_("test signal"))
    group.add_argument(
        "--sample-rate",
        type=int,
        default=DEFAULT_SAMPLE_RATE,
        choices=SUPPORTED_SAMPLE_RATES,
        metavar=pgettext("metavar", "HZ"),
        help=_("sample rate (Hz): {rates}").format(
            rates=", ".join(str(rate) for rate in SUPPORTED_SAMPLE_RATES)
        ),
    )
    group.add_argument(
        "--duration",
        type=float,
        default=10.0,
        metavar=pgettext("metavar", "S"),
        help=_("sweep duration in seconds (default 10)"),
    )
    group.add_argument(
        "--start-hz",
        type=float,
        default=20.0,
        metavar=pgettext("metavar", "HZ"),
        help=_("sweep start frequency (default 20)"),
    )
    group.add_argument(
        "--end-hz",
        type=float,
        default=20000.0,
        metavar=pgettext("metavar", "HZ"),
        help=_("sweep end frequency (default 20000)"),
    )
    group.add_argument(
        "--level",
        type=float,
        default=default_level,
        metavar=pgettext("metavar", "DBFS"),
        help=_("peak level in dBFS (default {level:g})").format(level=default_level),
    )
    group.add_argument(
        "--fade-in",
        type=float,
        default=0.05,
        metavar=pgettext("metavar", "S"),
        help=_("fade-in in seconds (default 0.05)"),
    )
    group.add_argument(
        "--fade-out",
        type=float,
        default=0.01,
        metavar=pgettext("metavar", "S"),
        help=_("fade-out in seconds (default 0.01)"),
    )
    group.add_argument(
        "--pre-silence",
        type=float,
        default=1.0,
        metavar=pgettext("metavar", "S"),
        help=_("silence before the sweep (s)"),
    )
    group.add_argument(
        "--post-silence",
        type=float,
        default=3.0,
        metavar=pgettext("metavar", "S"),
        help=_("silence after the sweep (s)"),
    )


#: The settings fields the command line sets, as the options that set them.
_FIELD_OPTIONS = {
    "sample_rate": "--sample-rate",
    "duration_s": "--duration",
    "start_hz": "--start-hz",
    "end_hz": "--end-hz",
    "level_dbfs": "--level",
    "channel": "--channel",
    "fr_smoothing_fraction": "--smoothing",
    "placement_distance_m": "--speaker-distance",
    "placement_mic_height_m": "--mic-height",
    "placement_temperature_c": "--temperature",
    "loopback_channel": "--loopback-channel",
}
_FIELD_NAME = re.compile(
    r"(?<![\w-])(" + "|".join(sorted(_FIELD_OPTIONS, key=len, reverse=True)) + r")(?!\w)"
)


def _name_options(exc: ConfigurationError) -> ConfigurationError:
    """``exc`` with the settings fields it names given as their options.

    The settings check their own values and name their fields ("end_hz must
    be greater than start_hz"); on the command line the user typed --end-hz.
    """
    message = _FIELD_NAME.sub(lambda found: _FIELD_OPTIONS[found.group(1)], str(exc))
    return ConfigurationError(message)


def _sweep_settings(args: argparse.Namespace) -> SweepSettings:
    try:
        return SweepSettings(
            sample_rate=args.sample_rate,
            duration_s=args.duration,
            start_hz=args.start_hz,
            end_hz=args.end_hz,
            fade_in_s=args.fade_in,
            fade_out_s=args.fade_out,
            level_dbfs=args.level,
            pre_silence_s=args.pre_silence,
            post_silence_s=args.post_silence,
        )
    except ConfigurationError as exc:
        raise _name_options(exc) from None


@contextlib.contextmanager
def _option_at_fault(command: str) -> Iterator[None]:
    """Send a refused option to the command's help, not to the device commands.

    ``measure`` answers a ConfigurationError with ``devices --probe`` and
    ``doctor --probe`` (a device or channel that is not there is one), but a
    --duration of 0 or an input channel listed twice is the option's fault:
    the devices are fine. An error that already chose its hints keeps them.
    """
    try:
        yield
    except ConfigurationError as exc:
        if not getattr(exc, "cli_hints", None):
            exc.cli_hints = [f"reverbscope {command} --help"]  # type: ignore[attr-defined]
        raise


def _add_analysis_arguments(parser: argparse.ArgumentParser, *, channel: bool = True) -> None:
    analysis = parser.add_argument_group(_("analysis"))
    if channel:
        # Not for measure: there the analysed column follows --input-channel(s).
        analysis.add_argument(
            "--channel",
            type=int,
            default=None,
            metavar=pgettext("channel metavar", "N"),
            help=_("recording channel to analyse (0-based)"),
        )
    analysis.add_argument(
        "--smoothing",
        type=int,
        default=6,
        metavar=pgettext("fraction metavar", "N"),
        help=_("fractional-octave smoothing 1/N (0 = off)"),
    )
    analysis.add_argument(
        "--profile",
        default=None,
        choices=available_profiles(),
        help=_("recording profile that shapes the interpretation (default: user settings)"),
    )
    notes = parser.add_argument_group(_("session notes (stored in session.json)"))
    notes.add_argument(
        "--room", default="", metavar=pgettext("metavar", "TEXT"), help=_("room name (metadata)")
    )
    notes.add_argument(
        "--position",
        default="",
        metavar=pgettext("metavar", "TEXT"),
        help=_("measurement position (metadata)"),
    )
    notes.add_argument(
        "--mic",
        default="",
        metavar=pgettext("metavar", "TEXT"),
        help=_("microphone name (metadata)"),
    )
    notes.add_argument(
        "--notes",
        default="",
        metavar=pgettext("metavar", "TEXT"),
        help=_("free-text notes (metadata)"),
    )
    placement = parser.add_argument_group(_("placement (optional tape measurements)"))
    placement.add_argument(
        "--speaker-distance",
        type=float,
        default=None,
        metavar=pgettext("metavar", "M"),
        help=_(
            "straight line from the loudspeaker to the microphone capsule (m), measured "
            "with a tape. Without it no geometry can be derived from the reflections"
        ),
    )
    placement.add_argument(
        "--mic-height",
        type=float,
        default=None,
        metavar=pgettext("metavar", "M"),
        help=_(
            "microphone capsule above the first solid horizontal surface below it (m) -- "
            "the desk top at a desk, otherwise the floor. Needs --speaker-distance"
        ),
    )
    placement.add_argument(
        "--temperature",
        type=float,
        default=None,
        metavar=pgettext("metavar", "C"),
        help=_("air temperature (C); 20 C is assumed, and reported as assumed, without it"),
    )
    output = parser.add_argument_group(_("output"))
    output.add_argument("--no-curves", action="store_true", help=_("omit curves from result.json"))
    output.add_argument(
        "--json", action="store_true", help=_("deprecated: use reverbscope --format json")
    )


def _add_loopback_file_arguments(parser: argparse.ArgumentParser) -> None:
    group = parser.add_argument_group(_("loopback (optional)"))
    group.add_argument(
        "--loopback",
        type=Path,
        default=None,
        metavar=pgettext("metavar", "WAV"),
        help=_("separate loopback WAV from the same take (same sample rate)"),
    )
    group.add_argument(
        "--loopback-channel",
        type=int,
        default=None,
        metavar=pgettext("channel metavar", "N"),
        help=_(
            "0-based loopback channel: of --loopback when it is given, otherwise of the recording"
        ),
    )


def _analysis_settings(
    args: argparse.Namespace, *, loopback_channel: int | None = None
) -> AnalysisSettings:
    channel = getattr(args, "loopback_channel", None)
    try:
        return AnalysisSettings(
            channel=args.channel,
            fr_smoothing_fraction=args.smoothing,
            placement_distance_m=args.speaker_distance,
            placement_mic_height_m=args.mic_height,
            placement_temperature_c=args.temperature,
            loopback_channel=loopback_channel if loopback_channel is not None else channel,
        )
    except ConfigurationError as exc:
        raise _name_options(exc) from None


def _shorten_usage(parser: argparse.ArgumentParser) -> None:
    """``reverbscope measure --out DIR [options]`` instead of every option.

    Each leaf command's usage line names what it cannot run without; the
    options are listed, grouped, below it.
    """
    for action in parser._actions:
        if not isinstance(action, argparse._SubParsersAction):
            continue
        for sub in action.choices.values():
            if any(isinstance(a, argparse._SubParsersAction) for a in sub._actions):
                _shorten_usage(sub)
                continue
            parts = [sub.prog]
            optional = 0  # positionals that may be left out: "[KEY [VALUE]]"
            for item in sub._actions:
                if not item.option_strings:
                    if item.metavar is None and item.choices:
                        shown = "{" + ",".join(str(c) for c in item.choices) + "}"
                    else:
                        shown = str(item.metavar or item.dest)
                    if item.nargs == "?":
                        optional += 1
                        shown = "[" + shown
                    parts.append(shown)
                elif item.required:
                    metavar = item.metavar or item.dest.upper()
                    shown = " ".join(metavar) if isinstance(metavar, tuple) else metavar
                    parts.append(f"{item.option_strings[0]} {shown}")
            if optional:
                last = max(i for i, part in enumerate(parts) if part.startswith("["))
                parts[last] += "]" * optional
            parts.append(_("[options]"))
            sub.usage = " ".join(parts)


def _required(parser: argparse.ArgumentParser) -> Any:
    """The group for the options a command cannot run without (listed first)."""
    group = parser.add_argument_group(_("required"))
    # argparse lists its own groups (positionals, options) first; after the
    # positionals, what the command cannot run without comes next.
    parser._action_groups.remove(group)
    parser._action_groups.insert(1, group)
    return group


#: argparse's split of a usage line into the pieces it keeps together.
_USAGE_PART = re.compile(r"\(.*?\)+(?=\s|$)|\[.*?\]+(?=\s|$)|\S+")


def _root_usage(parser: argparse.ArgumentParser) -> str:
    """The root usage line, wrapped by display width.

    The command list is printed grouped, so argparse's own list is hidden and
    the command placeholder is added at the end. argparse wraps with
    ``len()``: a translated prefix ("用法：") and placeholders ("[--lang 语言]")
    are wider on screen, so the lines ran past the edge and the continuation
    lines did not line up under the first. This is argparse's wrapping rule,
    measured in columns.
    """
    from reverbscope.cli.console import cell_width

    one_line = _HelpFormatter(parser.prog, width=100_000)
    one_line.add_usage(None, parser._actions, parser._mutually_exclusive_groups, prefix="")
    text = one_line.format_help().strip()
    parts = [
        parser.prog,
        *_USAGE_PART.findall(text[len(parser.prog) :]),
        f"{pgettext('metavar', '<command>')} ...",
    ]
    width = parser._get_formatter()._width
    prefix = cell_width(_("usage: "))
    hang = " " * (prefix + cell_width(parser.prog) + 1)
    lines: list[list[str]] = [[]]
    used = prefix - 1
    for part in parts:
        if used + 1 + cell_width(part) > width and lines[-1]:
            lines.append([])
            used = len(hang) - 1
        lines[-1].append(part)
        used += cell_width(part) + 1
    return "\n".join((hang if number else "") + " ".join(line) for number, line in enumerate(lines))


def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(
        prog="reverbscope",
        description=_(
            "ReverbScope: an open-source, DAW-independent recording environment analyzer."
        ),
        add_help=False,
        formatter_class=_HelpFormatter,
    )
    parser.add_argument("-h", "--help", action="help", help=_("show this help message and exit"))
    parser.add_argument(
        "--version",
        action="version",
        version=f"reverbscope {__version__}",
        help=_("show program's version number and exit"),
    )
    parser.add_argument(
        "--lang",
        default=None,
        metavar=pgettext("metavar", "LANG"),
        help=_(
            "interface language for this command (en, zh_CN); reverbscope config language keeps one"
        ),
    )
    parser.add_argument(
        "--format",
        choices=["text", "json"],
        default=None,
        help=_("text report or JSON on stdout (diagnostics stay on stderr)"),
    )
    parser.add_argument(
        "--color",
        choices=COLOR_MODES,
        default="auto",
        metavar=pgettext("metavar", "WHEN"),
        help=_(
            "colour in the terminal: auto (default; off for pipes, files and NO_COLOR), always, never"
        ),
    )
    parser.add_argument(
        "--backend",
        default=None,
        metavar=pgettext("metavar", "NAME"),
        help=_("audio backend for Standalone Mode: portaudio (default) or fake"),
    )
    parser.add_argument(
        "--copy-recording",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=_("copy the raw recording into the session folder (default: user settings)"),
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help=_("debug logging, and tracebacks on errors")
    )
    sub = parser.add_subparsers(
        dest="command",
        required=False,
        metavar=pgettext("metavar", "<command>"),
        help=argparse.SUPPRESS,
    )

    # Registered in the order of the workflow; the root help groups them (COMMAND_GROUPS).
    p_demo = _command(
        sub,
        "demo",
        _("try ReverbScope with synthetic data: no audio hardware needed"),
        examples=("reverbscope demo", "reverbscope demo --out ~/reverbscope-demo"),
    )
    p_demo.add_argument(
        "--out",
        type=Path,
        default=Path(DEMO_FOLDER),
        metavar=pgettext("metavar", "DIR"),
        help=_("folder for the demo files, created or replaced (default {folder})").format(
            folder=DEMO_FOLDER
        ),
    )
    p_demo.add_argument(
        "--profile",
        default="vocal",
        choices=available_profiles(),
        # The value to type, as for every other default (not its title, 人声).
        help=_("recording profile used to interpret the demo (default: {profile})").format(
            profile="vocal"
        ),
    )

    p_gui = _command(
        sub,
        "gui",
        _("start the desktop GUI (needs PySide6; the desktop download includes it)"),
        examples=("reverbscope gui",),
    )
    p_gui.add_argument(
        "--smoke",
        action="store_true",
        help=_("construct the window offscreen and exit (bundle smoke; no loudspeaker)"),
    )

    p_sweep = _command(
        sub,
        "sweep",
        _("write the ESS test signal WAV (+ JSON sidecar)"),
        examples=(
            "reverbscope sweep --out sweep.wav",
            "reverbscope sweep --out sweep.wav --sample-rate 96000 --duration 15",
        ),
    )
    _required(p_sweep).add_argument(
        "--out",
        required=True,
        type=Path,
        metavar=pgettext("metavar", "WAV"),
        help=_("output WAV path"),
    )
    _add_sweep_arguments(p_sweep, default_level=-12.0)

    p_an = _command(
        sub,
        "analyze",
        _("analyse a recording made with the sweep"),
        examples=(
            "reverbscope analyze --recording take.wav --sweep sweep.wav",
            "reverbscope analyze --recording take.wav --sweep sweep.wav --out session-1",
            "reverbscope analyze --recording take.wav --sweep sweep.wav --loopback-channel 1",
        ),
    )
    required = _required(p_an)
    required.add_argument(
        "--recording",
        required=True,
        type=Path,
        metavar=pgettext("metavar", "WAV"),
        help=_("recorded WAV (any length, untrimmed)"),
    )
    required.add_argument(
        "--sweep",
        required=True,
        type=Path,
        metavar=pgettext("metavar", "FILE"),
        help=_("sweep WAV or its .reverbscope-sweep.json sidecar"),
    )
    p_an.add_argument(
        "--out",
        type=Path,
        default=None,
        metavar=pgettext("metavar", "DIR"),
        help=_("directory for session.json, result.json, IR WAV"),
    )
    _add_analysis_arguments(p_an)
    _add_loopback_file_arguments(p_an)

    p_dev = _command(
        sub,
        "devices",
        _("list audio devices (Standalone Mode)"),
        examples=("reverbscope devices", "reverbscope devices --probe"),
    )
    p_dev.add_argument(
        "--probe",
        action="store_true",
        help=_(
            "also check which sample rates each device accepts and mark the recommended "
            "entry of each physical device (nothing is played)"
        ),
    )
    p_dev.add_argument(
        "--host-apis", action="store_true", help=_("list the host APIs instead of devices")
    )
    p_dev.add_argument(
        "--json", action="store_true", help=_("deprecated: use reverbscope --format json")
    )

    p_me = _command(
        sub,
        "measure",
        _("Standalone Mode: play the sweep and record the microphone"),
        examples=(
            "reverbscope devices",
            "reverbscope measure --out session-1 --input-device 2 --output-device 2",
            "reverbscope measure --out session-2 --input-channels 1,2 --loopback-channel 2",
        ),
    )
    _required(p_me).add_argument(
        "--out",
        required=True,
        type=Path,
        metavar=pgettext("metavar", "DIR"),
        help=_("session directory (created)"),
    )
    iface = p_me.add_argument_group(_("audio interface"))
    iface.add_argument(
        "--input-device",
        type=int,
        default=None,
        metavar=pgettext("metavar", "N"),
        help=_("input device index (see 'devices')"),
    )
    iface.add_argument(
        "--output-device",
        type=int,
        default=None,
        metavar=pgettext("metavar", "N"),
        help=_("output device index"),
    )
    iface.add_argument(
        "--input-channel",
        type=int,
        default=1,
        metavar=pgettext("channel metavar", "N"),
        help=_("input channel, 1-based (default 1)"),
    )
    iface.add_argument(
        "--input-channels",
        type=_channel_list,
        default=None,
        metavar=pgettext("metavar", "LIST"),
        help=_("1-based input channels, comma-separated (e.g. 1,2); overrides --input-channel"),
    )
    iface.add_argument(
        "--output-channel",
        type=int,
        default=1,
        metavar=pgettext("channel metavar", "N"),
        help=_("output channel, 1-based (default 1)"),
    )
    iface.add_argument(
        "--loopback-channel",
        type=int,
        default=None,
        metavar=pgettext("channel metavar", "N"),
        dest="measure_loopback_channel",
        help=_("1-based loopback input channel (recorded with the microphone)"),
    )
    iface.add_argument(
        "--latency",
        choices=("low", "high"),
        default=None,
        help=_("PortAudio latency class of the stream (default: PortAudio's high latency)"),
    )
    iface.add_argument(
        "--wasapi-exclusive",
        action="store_true",
        help=_("Windows WASAPI: open the device in exclusive mode (no mixer, no conversion)"),
    )
    iface.add_argument(
        "--coreaudio-set-rate",
        action="store_true",
        help=_("macOS: let ReverbScope set the device's sample rate instead of converting"),
    )
    iface.add_argument(
        "--acknowledge-level",
        action="store_true",
        help=_("required for levels above -12 dBFS; confirms the monitor level was set low first"),
    )
    _add_sweep_arguments(p_me, default_level=-20.0)
    _add_analysis_arguments(p_me, channel=False)

    p_ir = _command(
        sub,
        "analyze-ir",
        _("analyse an impulse-response WAV from another tool"),
        examples=("reverbscope analyze-ir --ir room.wav --band 20 20000 --out session-ir",),
    )
    _required(p_ir).add_argument(
        "--ir",
        required=True,
        type=Path,
        metavar=pgettext("metavar", "WAV"),
        help=_("impulse-response WAV"),
    )
    p_ir.add_argument(
        "--band",
        nargs=2,
        type=float,
        metavar=(pgettext("metavar", "LO"), pgettext("metavar", "HI")),
        default=None,
        help=_(
            "declared excitation band in Hz (required for every decay and clarity metric, "
            "broadband included)"
        ),
    )
    p_ir.add_argument(
        "--out",
        type=Path,
        default=None,
        metavar=pgettext("metavar", "DIR"),
        help=_("session directory"),
    )
    _add_analysis_arguments(p_ir)

    p_show = _command(
        sub,
        "show",
        _("print a saved session or comparison.json report, or list sessions"),
        examples=("reverbscope show session-1", "reverbscope show --list ."),
    )
    p_show.add_argument(
        "path",
        type=Path,
        metavar=pgettext("metavar", "path"),
        help=_("session directory, session.json, comparison.json, or folder to list"),
    )
    p_show.add_argument(
        "--list",
        action="store_true",
        help=_("list session.json files under path instead of opening one session"),
    )
    p_show.add_argument(
        "--profile",
        default=None,
        choices=available_profiles(),
        help=_("override the recording profile stored in the session"),
    )
    p_show.add_argument(
        "--json", action="store_true", help=_("deprecated: use reverbscope --format json")
    )
    p_show.add_argument("--no-curves", action="store_true", help=_("omit curves from JSON output"))

    p_cmp = _command(
        sub,
        "compare",
        _("compare two saved sessions"),
        examples=(
            "reverbscope compare session-1 session-2",
            "reverbscope compare session-1 session-2 --same-input-gain --out comparison.json",
        ),
    )
    p_cmp.add_argument(
        "baseline",
        type=Path,
        metavar=pgettext("metavar", "baseline"),
        help=_("baseline session directory or session.json"),
    )
    p_cmp.add_argument(
        "candidate",
        type=Path,
        metavar=pgettext("metavar", "candidate"),
        help=_("candidate session directory or session.json"),
    )
    p_cmp.add_argument(
        "--out",
        type=Path,
        default=None,
        metavar=pgettext("metavar", "PATH"),
        help=_("write comparison.json here (file or directory)"),
    )
    p_cmp.add_argument(
        "--same-input-gain",
        action="store_true",
        help=_("declare that the input gain was unchanged (required for a VALID noise delta)"),
    )
    p_cmp.add_argument(
        "--profile",
        default=None,
        choices=available_profiles(),
        help=_("recording profile for comparison findings (default: the candidate session's)"),
    )
    p_cmp.add_argument(
        "--json", action="store_true", help=_("deprecated: use reverbscope --format json")
    )

    p_proj = _command(sub, "project", _("project folders (one room, several positions)"))
    proj_sub = p_proj.add_subparsers(dest="project_command", required=True)
    p_init = _command(
        proj_sub,
        "init",
        _("create a project.json"),
        examples=("reverbscope project init --out studio-a",),
    )
    _required(p_init).add_argument(
        "--out",
        required=True,
        type=Path,
        metavar=pgettext("metavar", "DIR"),
        help=_("project directory"),
    )
    p_init.add_argument(
        "--name", default="", metavar=pgettext("metavar", "TEXT"), help=_("room name")
    )
    p_init.add_argument(
        "--notes", default="", metavar=pgettext("metavar", "TEXT"), help=_("free-text notes")
    )
    p_init.add_argument(
        "--force",
        action="store_true",
        help=_("replace an existing project.json (its positions and notes are lost)"),
    )
    p_add = _command(
        proj_sub,
        "add",
        _("add a session to a position"),
        examples=("reverbscope project add studio-a session-1 --position A",),
    )
    p_add.add_argument(
        "project", type=Path, metavar=pgettext("metavar", "project"), help=_("project directory")
    )
    p_add.add_argument(
        "session", type=Path, metavar=pgettext("metavar", "session"), help=_("session directory")
    )
    _required(p_add).add_argument(
        "--position", required=True, metavar=pgettext("metavar", "LABEL"), help=_("position label")
    )
    p_avg = _command(
        proj_sub,
        "average",
        _("spatial average of VALID T values"),
        examples=("reverbscope project average studio-a",),
    )
    p_avg.add_argument(
        "project", type=Path, metavar=pgettext("metavar", "project"), help=_("project directory")
    )
    p_avg.add_argument(
        "--sources",
        type=int,
        default=1,
        metavar=pgettext("count metavar", "N"),
        help=_("number of source positions"),
    )
    p_avg.add_argument(
        "--json", action="store_true", help=_("deprecated: use reverbscope --format json")
    )
    p_show_proj = _command(proj_sub, "show", _("list positions and sessions"))
    p_show_proj.add_argument(
        "project", type=Path, metavar=pgettext("metavar", "project"), help=_("project directory")
    )
    # Without a metavar argparse names the missing action by its dest
    # ("the following arguments are required: project_command").
    proj_sub.metavar = "{" + ",".join(proj_sub.choices) + "}"

    p_ex = _command(
        sub,
        "export",
        _("export curves through an exporter"),
        examples=("reverbscope export session-1 --out session-1/csv",),
    )
    p_ex.add_argument(
        "session",
        type=Path,
        metavar=pgettext("metavar", "session"),
        help=_("session directory or session.json"),
    )
    p_ex.add_argument(
        "--format",
        dest="export_format",
        default="csv",
        metavar=pgettext("metavar", "NAME"),
        help=_("exporter name (default csv)"),
    )
    p_ex.add_argument(
        "--out",
        type=Path,
        default=None,
        metavar=pgettext("metavar", "DIR"),
        help=_("output directory"),
    )

    p_sess = _command(sub, "session", _("session folder tools"))
    sess_sub = p_sess.add_subparsers(dest="session_command", required=True)
    p_bundle = _command(
        sess_sub,
        "bundle",
        _("zip a session for a bug report"),
        examples=("reverbscope session bundle session-1 --no-audio",),
    )
    p_bundle.add_argument(
        "session",
        type=Path,
        metavar=pgettext("metavar", "session"),
        help=_("session directory or session.json"),
    )
    p_bundle.add_argument(
        "--no-audio",
        action="store_true",
        help=_("leave WAV files out of the zip"),
    )
    p_bundle.add_argument(
        "--out",
        type=Path,
        default=None,
        metavar=pgettext("metavar", "PATH"),
        help=_("zip file (.zip) or folder"),
    )
    sess_sub.metavar = "{" + ",".join(sess_sub.choices) + "}"

    from reverbscope.cli import config as settings_keys

    p_cfg = _command(
        sub,
        "config",
        _("show or change the settings (the same settings.json as the desktop app)"),
        examples=(
            "reverbscope config",
            "reverbscope config language zh_CN",
            "reverbscope config language auto",
            "reverbscope config profile vocal",
        ),
    )
    p_cfg.add_argument(
        "key",
        nargs="?",
        default=None,
        metavar=pgettext("metavar", "KEY"),
        help=_("the setting to show or change; without it every setting is listed"),
    )
    p_cfg.add_argument(
        "value",
        nargs="?",
        default=None,
        metavar=pgettext("metavar", "VALUE"),
        help=_("the new value; auto goes back to the default"),
    )
    p_cfg.epilog = "\n\n".join([_settings_block(settings_keys), str(p_cfg.epilog)])

    p_doc = _command(
        sub,
        "doctor",
        _("print an environment report for bug reports and debugging"),
        examples=("reverbscope doctor", "reverbscope doctor --probe"),
    )
    p_doc.add_argument(
        "--json", action="store_true", help=_("deprecated: use reverbscope --format json")
    )
    p_doc.add_argument(
        "--out",
        metavar=pgettext("metavar", "FILE"),
        help=_(
            "also write the report to this file (UTF-8), ready to attach to a bug or "
            "hardware report"
        ),
    )
    p_doc.add_argument(
        "--probe",
        action="store_true",
        help=_("also ask every device which sample rates it accepts (nothing is played)"),
    )

    p_schema = _command(
        sub, "schema", _("print a shipped JSON Schema"), examples=("reverbscope schema result",)
    )
    schemas = ["result", "session", "comparison", "project", "sidecar"]
    p_schema.add_argument(
        "name",
        choices=schemas,
        # As for project and session: without a metavar argparse's errors
        # name the argument by its dest ("argument name: invalid choice").
        metavar="{" + ",".join(schemas) + "}",
        help=_("which schema to print"),
    )
    _shorten_usage(parser)
    parser.usage = _root_usage(parser)
    helps = {action.dest: str(action.help) for action in sub._choices_actions}
    parser.description = "\n\n".join(
        [
            _("ReverbScope: an open-source, DAW-independent recording environment analyzer."),
            _commands_block(helps),
        ]
    )
    epilog = [
        _examples_block(ROOT_EXAMPLES),
        # The command on a line of its own: a wrapped sentence split it.
        _("Run a command with --help for its options, for example:")
        + "\n  reverbscope measure --help",
    ]
    # The width argparse lays this help out in: the command in the hint
    # goes on a line of its own, whole, where the line would not hold it.
    hint = _language_hint(parser._get_formatter()._width)
    if hint:
        epilog.append(hint)
    parser.epilog = "\n\n".join(epilog)
    return parser


def _language_hint(width: int) -> str | None:
    """The way to the other interface language, where stdout can write it."""
    from reverbscope.cli.config import language_hint_lines
    from reverbscope.cli.console import can_encode
    from reverbscope.i18n import current_locale

    hint = "\n".join(language_hint_lines(current_locale(), width))
    if hint and can_encode(hint, getattr(sys.stdout, "encoding", None)):
        return hint
    return None


def cmd_sweep(args: argparse.Namespace) -> int:
    from reverbscope.io.wav import write_sweep_file

    _warn_ignored_json(args, "sweep")
    settings = _sweep_settings(args)
    wav_path, sidecar = write_sweep_file(settings, args.out)
    print(render_sweep_written(_console(args), settings, wav_path, sidecar))
    return 0


#: The long options of the top-level parser (``build_parser``; a test keeps the
#: two in step). argparse takes any unambiguous prefix of them for the option
#: (``--lan zh_CN``), so the ones read before the parser exists must too.
_ROOT_LONG_OPTIONS = (
    "--help",
    "--version",
    "--lang",
    "--format",
    "--color",
    "--backend",
    "--copy-recording",
    "--no-copy-recording",
    "--verbose",
)


def _abbreviates(flag: str, names: tuple[str, ...]) -> bool:
    """Whether ``flag`` is an abbreviation argparse resolves to one of ``names``."""
    if len(flag) < 3 or not flag.startswith("--"):
        return False
    matches = [option for option in _ROOT_LONG_OPTIONS if option.startswith(flag)]
    return len(matches) == 1 and matches[0] in names


def _peek_option(argv: Sequence[str], names: tuple[str, ...]) -> str | None:
    """The value of a top-level option, read before the parser is built.

    ``--lang X``, ``--lang=X`` and what argparse accepts for them (``--lan X``,
    ``--la=X``): the language and the colour policy have to be known before
    the parser's own texts are made, and an option given by an abbreviation
    would otherwise be dropped without a word.
    """
    # The top-level options come before the command; after it, ``--l`` may be
    # the start of one of the command's own options.
    command = next((index for index, arg in enumerate(argv) if arg in COMMANDS), len(argv))
    for index, arg in enumerate(argv):
        flag, has_value, value = arg.partition("=")
        if flag not in names and not (index < command and _abbreviates(flag, names)):
            continue
        if has_value:
            return value
        if index + 1 < len(argv):
            return argv[index + 1]
    return None


def _console(args: argparse.Namespace, stream: Any = None) -> Console:
    """How to lay out text for ``stream`` (stdout by default) under ``--color``."""
    return Console.for_stream(stream or sys.stdout, getattr(args, "color", None) or "auto")


def _warn_ignored_json(args: argparse.Namespace, command: str) -> None:
    """Say so when ``--format json`` does not apply, instead of ignoring it."""
    if getattr(args, "format", None) != "json":
        return
    print(
        render_status(
            _console(args, sys.stderr),
            "warn",
            _("warning: --format json does not apply to {command}; printing text").format(
                command=command
            ),
        ),
        file=sys.stderr,
    )


def _use_json(args: argparse.Namespace) -> bool:
    if getattr(args, "format", None) == "json":
        return True
    if getattr(args, "json", False):
        if not getattr(args, "json_warned", False):
            args.json_warned = True
            print(
                render_status(
                    _console(args, sys.stderr),
                    "warn",
                    _(
                        "warning: --json is deprecated; use --format json "
                        "(--json will be removed in a future minor release)"
                    ),
                ),
                file=sys.stderr,
            )
        return True
    return False


def _resolve_profile(args: argparse.Namespace, stored: str | None = None) -> str:
    if getattr(args, "profile", None):
        name = str(args.profile)
    elif stored:
        name = stored
    else:
        from reverbscope.settings import load_settings

        name = load_settings().default_profile or "generic"
    if name not in available_profiles():
        return "generic"
    return name


def _refuse_file_out(path: Path | None, command: str, *, project: bool = False) -> None:
    """Refuse an --out that is an existing file before any work is done.

    Otherwise the whole analysis runs first and the save fails with the
    operating system's English "File exists".
    """
    if path is None or not path.exists() or path.is_dir():
        return
    message = (
        _("{path} is a file; --out needs a folder for the project")
        if project
        else _("{path} is a file; --out needs a folder for the session")
    )
    refusal = ConfigurationError(message.format(path=path))
    refusal.cli_hints = [f"reverbscope {command} --out {_('<new-folder>')}"]  # type: ignore[attr-defined]
    raise refusal


def _prove_out_usable(path: Path) -> None:
    """Fail before a take when --out cannot be created or written to.

    ``measure`` copies the take into --out only after it was played, recorded
    and analysed; a path below a file, a drive that is not mounted or a
    read-only folder would otherwise fail only then, with the sweep played
    through the loudspeakers and the take thrown away. A probe file in the
    nearest folder that exists proves that --out (and the folders above it)
    can be created there, and leaves nothing behind: a take that is stopped
    must not have made --out.
    """
    folder = path
    while not folder.exists() and folder.parent != folder:
        folder = folder.parent
    if not folder.is_dir():
        # The text the save's own mkdir would give, naming --out.
        raise NotADirectoryError(errno.ENOTDIR, os.strerror(errno.ENOTDIR), str(path))
    try:
        with tempfile.TemporaryFile(dir=folder):
            pass
    except OSError as exc:
        # Name the folder that refused, not the probe's random file name.
        raise OSError(exc.errno, exc.strerror, str(folder)) from None


def _run_analysis(
    recording_path: Path,
    reference_path: Path | None,
    args: argparse.Namespace,
    *,
    sweep_settings: SweepSettings | None = None,
    mode: str = "universal_daw",
    out_dir: Path | None = None,
    hardware: ChannelPlan | None = None,
    output_channel: int | None = None,
    device_warnings: tuple[str, ...] = (),
    inputs: Sequence[tuple[str, str]] = (),
    take: bool = False,
) -> int:
    """Analyse a recording and optionally save a session.

    ``hardware`` is the Standalone channel plan; the session then records the
    1-based interface channels. In Universal DAW Mode the DAW did the routing,
    so the session leaves them empty and the analysed WAV column stays in
    ``analysis_settings`` (0-based). ``take`` marks a sweep and a recording
    written for this session (``reverbscope measure``): both are copied into
    ``out_dir`` together with it.
    """
    from reverbscope.core.pipeline import Reference, analyze
    from reverbscope.interpretation import interpret
    from reverbscope.io.recent import remember_session
    from reverbscope.io.session_store import save_measurement
    from reverbscope.io.wav import load_reference, read_wav
    from reverbscope.models.session import MeasurementSession

    recording = read_wav(recording_path)
    if device_warnings:
        # Written to a WAV and read back, the take has lost what the device
        # reported while recording it.
        recording = replace(recording, device_warnings=device_warnings)
    if sweep_settings is not None:
        reference = Reference.from_settings(sweep_settings)
    else:
        assert reference_path is not None
        reference = load_reference(reference_path)
    settings = _analysis_settings(args)
    loopback_signal = None
    if getattr(args, "loopback", None) is not None:
        loopback_signal = read_wav(args.loopback)
    result = analyze(recording, reference, settings, loopback=loopback_signal)
    profile = _resolve_profile(args)
    findings = interpret(result, profile)

    if out_dir is not None:
        session = MeasurementSession(
            mode=mode,
            room_name=args.room,
            measurement_position=args.position,
            microphone_name=args.mic,
            notes=args.notes,
            sweep_settings=reference.settings or SweepSettings(sample_rate=recording.sample_rate),
            analysis_settings=settings,
            sweep_path=str(reference_path) if reference_path else None,
            recording_path=str(recording_path),
            input_channel=None if hardware is None else hardware.microphone_channel,
            output_channel=output_channel if hardware is not None else None,
            loopback_channel=None if hardware is None else hardware.loopback_channel,
            recording_profile=profile,
        )
        session_path = save_measurement(
            out_dir,
            session,
            result,
            include_curves=not args.no_curves,
            copy_recording=True if take else getattr(args, "copy_recording", None),
            copy_sweep=take,
        )
        remember_session(out_dir)
        log.info("session saved to %s", session_path)

    if _use_json(args):
        payload = result.to_dict(include_curves=not args.no_curves)
        payload["findings"] = [f.to_dict() for f in findings]
        payload["health"] = assess(result).to_dict()
        print(json.dumps(payload, indent=1))
    else:
        console = _console(args)
        print(render_analysis(console, result, findings, profile, inputs=inputs))
        if out_dir is not None:
            print()
            print(render_saved_next_steps(console, out_dir))
    return 0


def cmd_analyze(args: argparse.Namespace) -> int:
    _refuse_file_out(args.out, "analyze")
    inputs = [
        (_("Recording"), Verbatim(str(args.recording))),
        (_("Sweep"), Verbatim(str(args.sweep))),
    ]
    if getattr(args, "loopback", None) is not None:
        inputs.append((_("Loopback"), Verbatim(str(args.loopback))))
    return _run_analysis(args.recording, args.sweep, args, out_dir=args.out, inputs=inputs)


def cmd_devices(args: argparse.Namespace) -> int:
    from reverbscope.audio.backend import get_backend

    backend = get_backend(args.backend)
    # _use_json, not args.json: it warns that --json is going away.
    if getattr(args, "probe", False) or getattr(args, "host_apis", False) or _use_json(args):
        return _print_inventory(backend, args)
    print(render_devices(_console(args), backend.list_devices()))
    return 0


def _print_inventory(backend: Any, args: argparse.Namespace) -> int:
    from reverbscope.audio.inventory import build_inventory

    inventory = build_inventory(backend, probe_rates=bool(getattr(args, "probe", False)))
    if _use_json(args):
        print(json.dumps(inventory.to_dict(), indent=1))
        return 0
    if getattr(args, "host_apis", False):
        print(render_host_apis(_console(args), inventory))
    else:
        print(render_inventory(_console(args), inventory))
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    from reverbscope.diagnostics import environment_report

    as_json = _use_json(args)
    # The JSON is pasted into issues and read by tools: English, like the
    # diagnostics it stores, whatever the interface language.
    report = environment_report(
        backend_name=args.backend, probe_rates=args.probe, english_errors=as_json
    )
    if as_json:
        text = json.dumps(report, indent=1, default=str)
    else:
        text = render_environment(_console(args), report)
    print(text)
    out = getattr(args, "out", None)
    if out:
        # The same report, as a file a tester attaches to an issue: always
        # UTF-8, whatever the console's code page (a PowerShell redirect
        # would write UTF-16 or mojibake).
        path = Path(out)
        if path.is_dir():
            refusal = ConfigurationError(
                _("{path} is a folder; --out needs a file name for the report").format(path=out)
            )
            refusal.cli_hints = [f"reverbscope doctor --out {_('<file>')}"]  # type: ignore[attr-defined]
            raise refusal
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text + "\n", encoding="utf-8")
        except OSError as exc:
            raise ConfigurationError(
                _("cannot write the report to {path}: {error}").format(path=out, error=exc)
            ) from exc
        print(_("Report written to {path}").format(path=out), file=sys.stderr)
    return 0


def _stream_options(args: argparse.Namespace) -> Any:
    from reverbscope.audio.backend import StreamOptions

    return StreamOptions(
        latency=getattr(args, "latency", None),
        wasapi_exclusive=bool(getattr(args, "wasapi_exclusive", False)),
        coreaudio_change_device_rate=bool(getattr(args, "coreaudio_set_rate", False)),
    )


def cmd_measure(args: argparse.Namespace) -> int:
    from reverbscope.audio.backend import (
        SAFE_MAX_LEVEL_DBFS,
        SAFETY_MESSAGE,
        get_backend,
        plan_input_channels,
    )
    from reverbscope.core.sweep import measurement_signal
    from reverbscope.demo import DEMO_MODE, FAKE_BACKEND_NOTES
    from reverbscope.io.session_store import (
        IR_FILE,
        RECORDING_FILE,
        RESULT_FILE,
        SESSION_FILE,
        SWEEP_FILE,
        SWEEP_SIDECAR_NAME,
    )
    from reverbscope.io.wav import write_sweep_file, write_wav

    with _option_at_fault("measure"):
        settings = _sweep_settings(args)
    err = _console(args, sys.stderr)
    _refuse_file_out(Path(args.out), "measure")
    if Path(args.out).is_dir() and not (Path(args.out) / SESSION_FILE).is_file():
        # A session folder is measured again as a whole; any other folder may
        # hold the user's own sweep (reverbscope sweep --out folder/sweep.wav),
        # which the take's sweep.wav and sidecar would silently replace.
        names = (SWEEP_FILE, SWEEP_SIDECAR_NAME, RECORDING_FILE, IR_FILE, RESULT_FILE)
        clash = next((name for name in names if (Path(args.out) / name).exists()), None)
        if clash is not None:
            refusal = ConfigurationError(
                _(
                    "{path} already holds {name} and is not a ReverbScope session; "
                    "the take would replace that file"
                ).format(path=args.out, name=clash)
            )
            refusal.cli_hints = [f"reverbscope measure --out {_('<new-folder>')}"]  # type: ignore[attr-defined]
            raise refusal
    # The take reaches --out only after it was played and analysed: prove now,
    # while nothing has been played, that it can.
    _prove_out_usable(Path(args.out))
    if settings.total_samples < settings.sample_rate:
        # The analysis refuses a recording shorter than one second: say so
        # before the take, not after it was played and recorded for nothing.
        refusal = ConfigurationError(
            _(
                "the test signal lasts {seconds:.2f} s, but a recording must last at least "
                "1 s to be analysed; lengthen the silence after the sweep (--post-silence)"
            ).format(seconds=settings.total_samples / settings.sample_rate)
        )
        # The settings are at fault, not the devices.
        refusal.cli_hints = ["reverbscope measure --help"]  # type: ignore[attr-defined]
        raise refusal
    if settings.level_dbfs > SAFE_MAX_LEVEL_DBFS and not args.acknowledge_level:
        print(
            render_error(
                err,
                _(
                    "Level {level:g} dBFS is above {max_level:g} dBFS. "
                    "Set the monitor level low first and pass --acknowledge-level to confirm."
                ).format(level=settings.level_dbfs, max_level=SAFE_MAX_LEVEL_DBFS),
                detail=_("Nothing was played."),
            ),
            file=sys.stderr,
        )
        return 2
    as_json = _use_json(args)
    out = _console(args)
    # With --format json, stdout carries the JSON document only; the safety
    # note and the status lines go to stderr.
    status_stream = sys.stderr if as_json else sys.stdout
    backend = get_backend(args.backend)
    # The fake backend (--backend fake, settings or REVERBSCOPE_AUDIO_BACKEND)
    # simulates the room: the session is marked like reverbscope demo's.
    synthetic = backend.name == "fake"
    if synthetic:
        args.notes = "\n".join(part for part in (FAKE_BACKEND_NOTES, args.notes) if part)
    requested = list(args.input_channels or [int(args.input_channel)])
    # Hardware inputs are 1-based, recording columns 0-based; validate the
    # mapping before anything is played (#13).
    with _option_at_fault("measure"):
        plan = plan_input_channels(requested, getattr(args, "measure_loopback_channel", None))
    channels = list(plan.input_channels)
    args.loopback_channel = plan.analysis_loopback_channel
    args.channel = plan.analysis_channel
    with _option_at_fault("measure"):
        # --mic-height without --speaker-distance, a temperature out of range:
        # refused after the take, the sweep was played and recorded for nothing.
        _analysis_settings(args)
    options = _stream_options(args)
    # Device pre-flight, shared with the GUI: one host API for both
    # directions, channels that exist, the rate on the devices the stream will
    # open, and a warning for two devices on two clocks (docs/AUDIO_DEVICES.md).
    from reverbscope.audio.inventory import build_inventory, preflight

    inventory = build_inventory(backend, probe_rates=False)
    # With no device at all PortAudio's "system default" fails only when the
    # stream opens, after the plan and the sweep file.
    if not any(probe.device.is_input for probe in inventory.devices):
        raise AudioDeviceError(_("no audio input device found"))
    if not any(probe.device.is_output for probe in inventory.devices):
        raise AudioDeviceError(_("no audio output device found"))
    device_plan = preflight(
        backend,
        inventory,
        input_device=args.input_device,
        output_device=args.output_device,
        input_channels=channels,
        output_channel=int(args.output_channel),
        sample_rate=settings.sample_rate,
        options=options,
    )
    args.input_device, args.output_device = device_plan.input_device, device_plan.output_device
    if as_json:
        print(_(SAFETY_MESSAGE), file=sys.stderr)
        if device_plan.clock_warning:
            print(
                render_status(
                    err,
                    "warn",
                    _("Warning: {message}").format(message=localize(device_plan.clock_warning)),
                ),
                file=sys.stderr,
            )
    else:
        print(
            render_measure_plan(
                out,
                devices=[probe.device for probe in inventory.devices],
                input_device=device_plan.input_device,
                output_device=device_plan.output_device,
                input_channels=channels,
                loopback_channel=plan.loopback_channel,
                output_channel=int(args.output_channel),
                settings=settings,
                backend=backend.name,
                options=options,
                clock_warning=device_plan.clock_warning,
                safe_max_level=SAFE_MAX_LEVEL_DBFS,
            )
        )
        print()
        print("\n".join(out.status("warn", _(SAFETY_MESSAGE), indent=0)))
        print()
    out_dir: Path = args.out
    # The sweep and the take are written to a folder of their own and copied
    # into --out only with the session that describes them: a take that is
    # stopped or refused leaves --out as it was, the previous session's audio
    # included, instead of beside a session from another take.
    with tempfile.TemporaryDirectory(prefix="reverbscope-take-", ignore_cleanup_errors=True) as tmp:
        take_dir = Path(tmp)
        sweep_path, _sidecar = write_sweep_file(settings, take_dir / "sweep.wav")
        # Progress is drawn by the thread that waits for the stream, never by
        # the audio callback; a failing display cannot stop the take (the
        # backend catches it). JSON mode shows none.
        progress = (
            None
            if as_json
            else ProgressLine(
                err,
                sys.stderr,
                _("Playing the sweep and recording"),
                settings.total_samples / settings.sample_rate,
            )
        )

        def report(fraction: float) -> None:
            # The backends report progress only once the stream runs: until
            # then a failure (a device PortAudio cannot open) played nothing.
            args.playback_started = True
            if progress is not None:
                progress.update(fraction)

        completed = False
        try:
            recording = backend.play_and_record(
                measurement_signal(settings),
                settings.sample_rate,
                input_device=args.input_device,
                output_device=args.output_device,
                input_channels=channels,
                output_channel=args.output_channel,
                level_dbfs=settings.level_dbfs,
                progress=report,
                options=options,
                loopback_input=plan.loopback_channel,
            )
            completed = True
        finally:
            if progress is not None:
                progress.finish(completed)
        recording_path = write_wav(
            take_dir / "recording.wav", recording.samples, settings.sample_rate, subtype="FLOAT"
        )
        print(
            render_status(
                err if as_json else out,
                "ok",
                _("Recorded {seconds:.1f} s").format(seconds=recording.duration_s),
                keep=True,
            ),
            file=status_stream,
        )
        if not as_json:
            print()
        return _run_analysis(
            recording_path,
            sweep_path,
            args,
            sweep_settings=settings,
            mode=DEMO_MODE if synthetic else "standalone",
            out_dir=out_dir,
            hardware=plan,
            output_channel=int(args.output_channel),
            device_warnings=recording.device_warnings,
            inputs=[(_("Recording"), Verbatim(str(out_dir / RECORDING_FILE)))],
            take=True,
        )


def _channel_list(text: str) -> list[int]:
    """argparse type of ``--input-channels``: ``"1,2"`` -> ``[1, 2]``."""
    try:
        channels = [int(part) for part in text.split(",") if part.strip()]
    except ValueError:
        channels = []
    if not channels:
        raise argparse.ArgumentTypeError(
            _("{value} is not a comma-separated list of channel numbers (e.g. 1,2)").format(
                value=repr(text)
            )
        )
    return channels


def _is_comparison_path(path: Path) -> bool:
    """True when ``path`` is a comparison file or a folder that holds only
    ``comparison.json``. ``compare --out ab.json`` writes any name, so a JSON
    file other than ``session.json`` is recognised by its content."""
    if path.is_file():
        if path.name == "comparison.json":
            return True
        if path.suffix.lower() != ".json" or path.name == "session.json":
            return False
        from reverbscope.io.jsonutil import read_json_object

        try:
            data = read_json_object(path, kind="comparison")
        except ReverbScopeError:
            return False
        return "comparable" in data and "common_band" in data
    if path.is_dir():
        return (path / "comparison.json").is_file() and not (path / "session.json").is_file()
    return False


def _candidate_profile(candidate_session: object) -> str | None:
    """The profile ``compare`` interpreted with: the candidate session's.

    ``comparison.json`` does not store it. When the candidate session can no
    longer be read (it moved, or its path is relative to where compare ran),
    the settings' default profile applies, as for a session without one.
    """
    from reverbscope.io.session_store import load_session

    # compare stores the session folder; nothing else is opened for it.
    if (
        not isinstance(candidate_session, str)
        or not candidate_session
        or not Path(candidate_session).is_dir()
    ):
        return None
    try:
        return load_session(candidate_session).recording_profile or None
    except (ReverbScopeError, OSError):
        return None


def _saved_results(comparison: Any) -> tuple[Any, Any]:
    """The two results a saved comparison was made from, where they can still be read.

    ``comparison.json`` stores the folders of the two sessions and not their
    health, and ``compare`` judged with both results at hand. ``show`` reads
    them again so that one comparison has one verdict; a folder that moved or
    is damaged is not an error here: that side is ``None``.
    """
    from reverbscope.io.session_store import load_measurement

    results = []
    for folder in (comparison.baseline_session, comparison.candidate_session):
        result = None
        # compare stores the session folder; nothing else is opened for it.
        if isinstance(folder, str) and folder and Path(folder).is_dir():
            try:
                result = load_measurement(folder).result
            except (ReverbScopeError, OSError):
                result = None
        results.append(result)
    return results[0], results[1]


def _health_not_considered(verdict: Any, baseline: Any, candidate: Any) -> Any:
    """``verdict``, naming in its conditions each side whose result could not be read."""
    from dataclasses import replace

    missing = [
        side
        for side, result in (
            (pgettext("comparison side", "baseline"), baseline),
            (pgettext("comparison side", "candidate"), candidate),
        )
        if result is None
    ]
    if not missing:
        return verdict
    if len(missing) == 2:
        note = _(
            "The measurement health of the two takes was not considered: their sessions are "
            "no longer where the comparison was saved."
        )
    else:
        note = _(
            "The measurement health of the {side} take was not considered: its session is "
            "no longer where the comparison was saved."
        ).format(side=missing[0])
    return replace(verdict, conditions=(*verdict.conditions, note))


def cmd_show(args: argparse.Namespace) -> int:
    from reverbscope.interpretation import interpret, interpret_comparison
    from reverbscope.io.session_store import (
        list_sessions,
        load_comparison,
        load_measurement,
        load_session,
    )

    if args.list:
        _warn_ignored_json(args, "show --list")
        listings = list_sessions(args.path)
        if not listings:
            print(_("No session.json files under {root}").format(root=args.path))
            return 0
        console = _console(args)
        for item in listings:
            # Tab-separated for scripts: never wrapped, but "·" becomes "|"
            # where the stream's encoding has no "·". A tab or a control
            # character from a received session.json is shown as an escape.
            path = printable(str(item.path), single_line=True)
            print(f"{path}\t{console.fit(printable(item.label, single_line=True))}")
        return 0

    if _is_comparison_path(args.path):
        comparison = load_comparison(args.path)
        profile = _resolve_profile(args, _candidate_profile(comparison.candidate_session))
        findings = interpret_comparison(comparison, profile)
        # Judged as `compare` judged it, with both results at hand, so that a
        # comparison has one verdict: each side's measurement health counts.
        # The health is not stored in comparison.json; where a session cannot
        # be read any more, the verdict says that its health was not considered.
        baseline, candidate = _saved_results(comparison)
        verdict = _health_not_considered(
            judge_comparison(comparison, profile, baseline=baseline, candidate=candidate),
            baseline,
            candidate,
        )
        if _use_json(args):
            payload = comparison.to_dict()
            payload["findings"] = [f.to_dict() for f in findings]
            payload["verdict"] = verdict.to_dict()
            print(json.dumps(payload, indent=1))
        else:
            print(render_comparison(_console(args), comparison, findings, profile, verdict))
        return 0

    loaded = load_measurement(args.path)
    profile = _resolve_profile(args, loaded.session.recording_profile or "generic")
    findings = interpret(loaded.result, profile)
    if _use_json(args):
        payload = loaded.result.to_dict(include_curves=not args.no_curves)
        payload["findings"] = [f.to_dict() for f in findings]
        payload["health"] = assess(loaded.result).to_dict()
        # As session.json stores it: load_measurement resolves the sweep and
        # recording paths for a later save, or drops them when they lead out.
        payload["session"] = load_session(args.path).to_dict()
        print(json.dumps(payload, indent=1))
    else:
        print(
            render_analysis(
                _console(args),
                loaded.result,
                findings,
                profile,
                inputs=_session_inputs(loaded.session, loaded.directory),
            )
        )
    return 0


#: Display names of the stored session modes.
SESSION_MODES = {
    "standalone": N_("Standalone Mode"),
    "universal_daw": N_("Universal DAW Mode"),
    "analyze_ir": N_("impulse-response file"),
    "synthetic_demo": N_("Synthetic demo"),
}


def _session_inputs(session: Any, directory: Path) -> list[tuple[str, str]]:
    """The saved session's folder and the names the user gave it, as entered.

    The names a demo wrote itself are shown in the interface language, whichever
    it was made in.
    """
    from reverbscope.demo import localize_demo_name

    rows: list[tuple[str, str]] = [(_("Session"), Verbatim(str(directory)))]
    mode = SESSION_MODES.get(str(session.mode))
    if mode:
        rows.append((_("Mode"), _(mode)))
    for label, value in (
        (_("Room"), session.room_name),
        (_("Position"), session.measurement_position),
        (_("Microphone"), session.microphone_name),
    ):
        if value:
            # A session from someone else: a line break or escape sequence in
            # a name must not forge report lines or drive the terminal.
            shown = localize_demo_name(str(session.mode), str(value))
            rows.append((label, printable(shown, single_line=True)))
    return rows


def cmd_compare(args: argparse.Namespace) -> int:
    from dataclasses import replace

    from reverbscope.core.compare import compare
    from reverbscope.interpretation import interpret_comparison
    from reverbscope.io.session_store import load_measurement, save_comparison
    from reverbscope.models.comparison import CompareSettings

    baseline = load_measurement(args.baseline)
    candidate = load_measurement(args.candidate)
    settings = CompareSettings(same_input_gain=args.same_input_gain)
    comparison = replace(
        compare(baseline.result, candidate.result, settings=settings),
        baseline_session=str(baseline.directory),
        candidate_session=str(candidate.directory),
    )
    profile = _resolve_profile(args, candidate.session.recording_profile or "generic")
    findings = interpret_comparison(comparison, profile)
    # Judged with both results at hand: each side's measurement health counts.
    verdict = judge_comparison(
        comparison, profile, baseline=baseline.result, candidate=candidate.result
    )
    # --out without .json is a folder: name the file that was written in it.
    written = save_comparison(args.out, comparison) if args.out is not None else None
    if _use_json(args):
        payload = comparison.to_dict()
        payload["findings"] = [f.to_dict() for f in findings]
        payload["verdict"] = verdict.to_dict()
        print(json.dumps(payload, indent=1))
    else:
        console = _console(args)
        print(render_comparison(console, comparison, findings, profile, verdict))
        if written is not None:
            print()
            print(
                render_status(
                    console, "ok", _("Wrote comparison to {path}").format(path=written), keep=True
                )
            )
    return 0


def _stored_settings(args: argparse.Namespace) -> Any:
    """The settings to show; a damaged file is named and the defaults shown."""
    from reverbscope.settings import UserSettings, read_settings

    try:
        return read_settings()
    except SessionError as exc:
        print(
            render_status(
                _console(args, sys.stderr),
                "warn",
                _("warning: {error}; the defaults are shown").format(error=localize(str(exc))),
            ),
            file=sys.stderr,
        )
        return UserSettings()


def _show_config(args: argparse.Namespace, key: str | None) -> int:
    """``reverbscope config`` and ``reverbscope config KEY``: nothing is written."""
    from reverbscope.i18n import current_locale, language_choice
    from reverbscope.settings import settings_path

    settings = _stored_settings(args)
    if getattr(args, "format", None) == "json":
        print(json.dumps(settings.to_dict(), indent=1))
    elif key is None:
        path = settings_path()
        shown = render_config(
            _console(args), settings, path, language_choice(None), exists=path.exists()
        )
        print(shown)
    elif key == "language":
        choice = language_choice(getattr(args, "lang", None))
        print(render_config_language(_console(args), settings, choice, current_locale()))
    else:
        print(render_config_key(_console(args), key, settings))
    return 0


def cmd_config(args: argparse.Namespace) -> int:
    from reverbscope.cli import config
    from reverbscope.i18n import LanguageChoice, language_choice
    from reverbscope.settings import read_settings, save_settings

    try:
        key = None if args.key is None else config.canonical_key(args.key)
        value = None if args.value is None or key is None else config.parse_value(key, args.value)
    except config.SettingError as exc:
        changing = args.value is not None
        detail = _("Nothing was changed.") if changing else ""
        raise _UsageError(str(exc), detail=detail, hints=exc.hints) from None
    if key is None or args.value is None:
        return _show_config(args, key)
    try:
        # A damaged file is not replaced by the defaults and one new value.
        stored = read_settings()
    except SessionError as exc:
        refusal = SessionError(
            _("{error}; nothing was changed: correct or delete the file first").format(
                error=localize(str(exc))
            )
        )
        refusal.cli_hints = ["reverbscope config"]  # type: ignore[attr-defined]
        raise refusal from exc
    settings = config.changed(stored, key, value)
    saved = save_settings(settings)
    choice: LanguageChoice | None = None
    if key == "language":
        # The confirmation is written in the language just chosen; --lang
        # applied to this command only.
        activate(settings.language or None)
        choice = language_choice(None)
    if getattr(args, "format", None) == "json":
        print(json.dumps(settings.to_dict(), indent=1))
    else:
        print(render_config_saved(_console(args), key, settings, saved, choice=choice))
    return 0


def cmd_schema(args: argparse.Namespace) -> int:
    from reverbscope.schemas import schema_text

    sys.stdout.write(schema_text(args.name))
    return 0


def cmd_analyze_ir(args: argparse.Namespace) -> int:
    from reverbscope.core.pipeline import analyze_impulse_response
    from reverbscope.interpretation import interpret
    from reverbscope.io.recent import remember_session
    from reverbscope.io.session_store import save_measurement
    from reverbscope.io.wav import read_wav
    from reverbscope.models.session import MeasurementSession

    _refuse_file_out(args.out, "analyze-ir")
    band = (float(args.band[0]), float(args.band[1])) if args.band else None
    if band is not None and not (band[0] > 0.0 and band[1] > band[0] and math.isfinite(band[1])):
        # The analysis would name its own parameter: "excitation_band must be
        # a (low_hz, high_hz) pair".
        raise ConfigurationError(
            _("--band needs two frequencies in Hz, LO then HI, with HI above LO and LO above 0")
        )
    ir = read_wav(args.ir)
    settings = _analysis_settings(args)
    result = analyze_impulse_response(ir, settings, excitation_band=band)
    profile = _resolve_profile(args)
    findings = interpret(result, profile)
    if args.out is not None:
        session = MeasurementSession(
            mode="analyze_ir",
            room_name=args.room,
            measurement_position=args.position,
            microphone_name=args.mic,
            notes=args.notes,
            analysis_settings=settings,
            recording_path=str(args.ir),
            recording_profile=profile,
        )
        save_measurement(
            args.out,
            session,
            result,
            include_curves=not args.no_curves,
            copy_recording=getattr(args, "copy_recording", None),
        )
        remember_session(args.out)
    if _use_json(args):
        payload = result.to_dict(include_curves=not args.no_curves)
        payload["findings"] = [f.to_dict() for f in findings]
        payload["health"] = assess(result).to_dict()
        print(json.dumps(payload, indent=1))
    else:
        console = _console(args)
        print(
            render_analysis(
                console,
                result,
                findings,
                profile,
                inputs=[(_("Impulse response"), Verbatim(str(args.ir)))],
            )
        )
        if args.out is not None:
            print()
            print(render_saved_next_steps(console, args.out))
    return 0


def cmd_session(args: argparse.Namespace) -> int:
    from reverbscope.io.session_store import bundle_session

    if args.session_command == "bundle":
        _warn_ignored_json(args, "session bundle")
        path = bundle_session(args.session, args.out, include_audio=not args.no_audio)
        print(render_status(_console(args), "ok", _("Wrote {path}").format(path=path), keep=True))
        return 0
    raise ReverbScopeError(f"unknown session command {args.session_command}")


def cmd_export(args: argparse.Namespace) -> int:
    from reverbscope.io.exporters import get_exporter
    from reverbscope.io.session_store import load_measurement

    _warn_ignored_json(args, "export")
    loaded = load_measurement(args.session)
    out = args.out if args.out is not None else loaded.directory / "export"
    written = get_exporter(args.export_format).export(loaded.result, out)
    for path in written:
        print(path)
    return 0


#: How many left-out positions a project command names before it counts the rest.
MISSING_POSITIONS_SHOW_LIMIT = 10


def _warn_missing_positions(args: argparse.Namespace, project: Path) -> None:
    """Say which listed positions a project command could not read (stderr).

    ``project show`` and ``project average`` list the takes that still exist; a
    folder that was moved, renamed or deleted would otherwise drop out of the
    list, and out of the average, without a word.
    """
    from reverbscope.io.project_store import missing_project_sessions

    missing = missing_project_sessions(project)
    if not missing:
        return
    err = _console(args, sys.stderr)
    for label, stored in missing[:MISSING_POSITIONS_SHOW_LIMIT]:
        text = _("position {label}: {path} has no session.json; it is left out").format(
            label=printable(label, single_line=True), path=printable(stored, single_line=True)
        )
        print(render_status(err, "warn", text, keep=True), file=sys.stderr)
    if len(missing) > MISSING_POSITIONS_SHOW_LIMIT:
        more = _("... and {n} more positions left out").format(
            n=len(missing) - MISSING_POSITIONS_SHOW_LIMIT
        )
        print(render_status(err, "warn", more, keep=True), file=sys.stderr)


def cmd_project(args: argparse.Namespace) -> int:
    from reverbscope.core.averaging import AveragedMetric, average_decay
    from reverbscope.io.project_store import (
        PROJECT_FILE,
        add_session,
        is_project,
        list_project_sessions,
        load_project,
        save_project,
    )
    from reverbscope.io.session_store import load_measurement
    from reverbscope.models.project import Project

    command = args.project_command
    if command in ("init", "add", "show"):
        _warn_ignored_json(args, f"project {command}")
    if command == "init":
        _refuse_file_out(args.out, "project init", project=True)
        if (args.out / PROJECT_FILE).is_file() and not args.force:
            # A fresh project.json lists no positions: run again by mistake
            # (or to set a name), init would drop every position label.
            raise ReverbScopeError(
                _("{path} already contains a project.json; use --force to replace it").format(
                    path=args.out
                )
            )
        project = Project(name=args.name or args.out.name, notes=args.notes)
        path = save_project(args.out, project)
        print(render_status(_console(args), "ok", _("Wrote {path}").format(path=path), keep=True))
        return 0
    if command == "add":
        project = add_session(args.project, args.session, position=args.position)
        print(
            render_status(
                _console(args),
                "ok",
                _("{n} position(s) in {path}").format(n=len(project.positions), path=args.project),
            )
        )
        return 0
    if command == "show":
        if not is_project(args.project):
            raise ReverbScopeError(_("no project.json in {path}").format(path=args.project))
        project = load_project(args.project)
        # project.json may come from someone else (SECURITY.md).
        print(printable(project.name or str(args.project), single_line=True))
        for label, path in list_project_sessions(args.project):
            tag = printable(label, single_line=True) if label else _("(unlisted)")
            print(f"  {tag}\t{printable(str(path), single_line=True)}")
        _warn_missing_positions(args, args.project)
        return 0
    if command == "average":
        if not is_project(args.project):
            raise ReverbScopeError(_("no project.json in {path}").format(path=args.project))
        items = list_project_sessions(args.project)
        # Before the "no sessions" error, which would otherwise not say why.
        _warn_missing_positions(args, args.project)
        if not items:
            raise ReverbScopeError(_("no sessions in {path}").format(path=args.project))
        loaded = [load_measurement(path) for _label, path in items]
        # A position label is one microphone position; repeated takes there
        # add sessions, not positions (#15). Sessions not assigned to a
        # position are averaged but do not count as positions.
        labelled = [label for label, _path in items if label]
        n_mic = max(1, len(set(labelled)))
        sources = int(args.sources)
        if sources < 1:
            raise ConfigurationError(_("--sources must be at least 1"))
        averaged = average_decay(
            [item.result for item in loaded],
            n_source_positions=sources,
            n_microphone_positions=n_mic,
            n_combinations=max(1, min(len(labelled), sources * n_mic)),
            session_labels=[str(item.directory) for item in loaded],
        )
        if _use_json(args) or args.json:
            print(json.dumps(averaged.to_dict(), indent=1))
        else:
            console = _console(args)
            iso_class = _(
                "ISO 3382-2 class: {klass} ({sources} source × {mics} mic, {combos} combinations)"
            ).format(
                klass=accuracy_class_text(averaged.iso_3382_2_class),
                sources=averaged.n_source_positions,
                mics=averaged.n_microphone_positions,
                combos=averaged.n_combinations,
            )
            print("\n".join(console.paragraph(iso_class, indent=0)))
            dash = console.dash()

            # Each value averages only the sessions where it is VALID, so its
            # count can differ along a row: n is the row's largest count, and
            # a value from fewer sessions shows its own.
            partial = False

            def cell(metric: AveragedMetric, n: int) -> str:
                nonlocal partial
                if metric.seconds is None:
                    return dash
                if metric.count < n:
                    partial = True
                    return f"{metric.seconds:.2f} s ({metric.count})"
                return f"{metric.seconds:.2f} s"

            rows = []
            for band in averaged.bands:
                metrics = (band.edt, band.t20, band.t30, band.rt60)
                n = max(metric.count for metric in metrics)
                # A label read from a session file: one line, whatever it holds.
                label = printable(band_text(band.band_label), single_line=True)
                rows.append([label, *(cell(m, n) for m in metrics), str(n)])
            print()
            print(
                "\n".join(
                    console.table(
                        [_("Band"), "EDT", "T20", "T30", "RT60", "n"], rows, align="lrrrrr"
                    )
                )
            )
            if partial:
                note = _(
                    "n is the number of sessions averaged in the row; a value followed by "
                    "(k) averages only k of them, as the others have no VALID value."
                )
                print("\n".join(console.paragraph(note, style=("dim",))))
        return 0
    raise ReverbScopeError(_("unknown project command {command}").format(command=command))


def cmd_gui(args: argparse.Namespace) -> int:
    from reverbscope.edition import is_terminal_package

    if is_terminal_package():
        # Built without Qt: say which download has the GUI, not that PySide6 is missing.
        print(render_terminal_edition_gui(_console(args, sys.stderr)), file=sys.stderr)
        return 2
    from reverbscope.ui.app import GUI_UNAVAILABLE, pyside6_import_error, run_app

    # PySide6 is imported inside run_app, so check it first: without the gui
    # extra (or the Qt system libraries) the user gets a sentence, not a traceback.
    error = pyside6_import_error()
    if error is not None:
        print(
            render_error(
                _console(args, sys.stderr),
                _(GUI_UNAVAILABLE).format(error=error),
                hints=['pip install "PySide6_Essentials>=6.6,<6.12"'],
            ),
            file=sys.stderr,
        )
        return 2
    # --lang was activated for the command line; the GUI resolves its
    # language again and would otherwise drop it for settings or the system's.
    return int(run_app(smoke=bool(getattr(args, "smoke", False)), lang=getattr(args, "lang", None)))


def _is_demo_folder(path: Path) -> bool:
    """True for a folder ``reverbscope demo`` wrote (safe to write again)."""
    from reverbscope.demo import DEMO_MODE

    try:
        session = json.loads((path / "position-a" / "session.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return isinstance(session, dict) and session.get("mode") == DEMO_MODE


def cmd_demo(args: argparse.Namespace) -> int:
    from reverbscope.demo import run_demo
    from reverbscope.edition import is_terminal_package
    from reverbscope.interpretation import interpret
    from reverbscope.io.recent import remember_session

    if _use_json(args):
        raise _UsageError(
            _("the demo prints a walkthrough, not JSON"),
            hints=[
                shell_command(
                    [
                        "reverbscope",
                        "--format",
                        "json",
                        "show",
                        str(Path(args.out) / "position-a"),
                    ]
                )
            ],
        )
    out_dir: Path = args.out
    occupied = out_dir.exists() and (not out_dir.is_dir() or any(out_dir.iterdir()))
    if occupied and not _is_demo_folder(out_dir):
        raise _UsageError(
            _("{path} already exists and was not written by reverbscope demo").format(path=out_dir),
            detail=_("Nothing was changed. Choose an empty or new folder for the demo."),
            hints=[f"reverbscope demo --out {_('<new-folder>')}"],
        )
    profile = _resolve_profile(args)
    err = _console(args, sys.stderr)
    note = ""
    if err.interactive and sys.stderr is not None:
        # A transient line while the two positions are simulated and analysed.
        # Cleared with spaces, never an escape sequence: --color never and
        # NO_COLOR must not write ESC[2K. Cut to the terminal like the
        # progress line: a wrapped note leaves its first row behind, as "\r"
        # returns only to the start of the second.
        note = truncate(
            err.fit(_("Simulating and analysing two microphone positions …")),
            max(8, err.width - 1),
        )
        sys.stderr.write(note)
        sys.stderr.flush()
    try:
        run = run_demo(out_dir, profile=profile)
    finally:
        if note and sys.stderr is not None:
            sys.stderr.write("\r" + (" " * cell_width(note)) + "\r")
            sys.stderr.flush()
    for take in run.takes:
        remember_session(take.session_dir)
    findings = [interpret(take.result, profile) for take in run.takes]
    terminal = is_terminal_package()
    if terminal:
        gui_available = False
    else:
        from reverbscope.ui.app import pyside6_import_error

        gui_available = pyside6_import_error() is None
    print(
        render_demo(
            _console(args), run, findings, gui_available=gui_available, terminal_edition=terminal
        )
    )
    return 0


COMMANDS = {
    "demo": cmd_demo,
    "sweep": cmd_sweep,
    "analyze": cmd_analyze,
    "analyze-ir": cmd_analyze_ir,
    "show": cmd_show,
    "compare": cmd_compare,
    "schema": cmd_schema,
    "devices": cmd_devices,
    "doctor": cmd_doctor,
    "measure": cmd_measure,
    "gui": cmd_gui,
    "session": cmd_session,
    "export": cmd_export,
    "project": cmd_project,
    "config": cmd_config,
}


class _UsageError(Exception):
    """A request the command cannot carry out as given (exit code 2)."""

    def __init__(self, message: str, *, detail: str = "", hints: Sequence[str] = ()) -> None:
        super().__init__(message)
        self.detail = detail
        self.hints = tuple(hints)


#: Error handlers that write something for any character instead of raising.
_SAFE_ERRORS = frozenset(
    {"replace", "backslashreplace", "xmlcharrefreplace", "namereplace", "ignore"}
)


def _prepare_streams() -> None:
    """Make stdout and stderr safe to write any report to.

    Redirected output uses the locale code page (cp1252, cp936 on Windows)
    with strict errors, so a report with Δ, → or a Chinese room name raised
    UnicodeEncodeError after the work was done: a pipe or file gets UTF-8
    unless the user chose an encoding. A stream that stays on a narrow
    encoding (a terminal, or ``PYTHONIOENCODING=cp1252``) replaces what it
    cannot write instead of failing; the console layer already writes ASCII
    symbols to such a stream.

    A frozen bundle's interpreter ignores ``PYTHONIOENCODING`` (PyInstaller
    runs it isolated from ``PYTHON*`` variables), so a stream still on
    another encoding is switched to the one the variable asks for.
    """
    chosen = os.environ.get("PYTHONIOENCODING", "")
    wanted, _sep, wanted_errors = chosen.partition(":")
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        isatty = getattr(stream, "isatty", None)
        if reconfigure is None or isatty is None:
            continue
        try:
            if not chosen and not isatty():
                reconfigure(encoding="utf-8", errors="backslashreplace")
                continue
            current = getattr(stream, "encoding", None) or "utf-8"
            if wanted and codecs.lookup(wanted).name != codecs.lookup(current).name:
                reconfigure(encoding=wanted, errors=wanted_errors or stream.errors)
                current = wanted
            narrow = codecs.lookup(current).name != "utf-8"
            if narrow and getattr(stream, "errors", "strict") not in _SAFE_ERRORS:
                reconfigure(errors="replace")
        except (LookupError, OSError, ValueError):
            continue


def _error_hints(exc: BaseException, command: str | None) -> list[str]:
    """What to try after each kind of error (the most specific class first)."""
    chosen = getattr(exc, "cli_hints", None)
    if chosen:
        return list(chosen)
    here = f"reverbscope {command} --help" if command else "reverbscope --help"
    if isinstance(exc, AudioBackendUnavailableError):
        return ["reverbscope doctor"]
    if isinstance(exc, AudioDeviceError) or (
        command in ("measure", "devices") and isinstance(exc, ConfigurationError)
    ):
        return ["reverbscope devices --probe", "reverbscope doctor --probe"]
    if isinstance(exc, InvalidAudioError | ConfigurationError):
        return [here]
    if isinstance(exc, SessionError):
        return [f"reverbscope show --list {_('<folder>')}"]
    return []


def _os_error_text(exc: OSError) -> str:
    """``permission denied: …/folder`` from an OSError, in the interface language.

    Python gives ``strerror`` in English on Linux and macOS; the common
    reasons are translated here, any other stays as the system gives it.
    """
    reasons = {
        errno.EEXIST: _("already exists"),
        errno.EACCES: _("permission denied"),
        errno.EPERM: _("permission denied"),
        errno.ENOSPC: _("no space left on the disk"),
        errno.ENOTDIR: _("part of the path is a file, not a folder"),
        errno.EISDIR: _("is a folder, not a file"),
        errno.ENOENT: _("no such file or folder"),
        errno.EROFS: _("the disk is read-only"),
    }
    reason = reasons.get(exc.errno or 0) or exc.strerror or str(exc)
    if exc.filename is not None:
        return _("{reason}: {path}").format(reason=reason, path=exc.filename)
    return reason


def main(argv: Sequence[str] | None = None) -> int:
    _prepare_streams()
    argv_list = list(sys.argv[1:] if argv is None else argv)
    activate(_peek_option(argv_list, ("--lang",)))
    _translate_argparse()
    color = _peek_option(argv_list, ("--color",))
    _COLOR_REQUEST["mode"] = color if color in COLOR_MODES else "auto"
    parser = build_parser()
    args = parser.parse_args(argv)
    configure_logging(logging.DEBUG if args.verbose else logging.WARNING)
    err = _console(args, sys.stderr)
    if args.command is None:
        # Bare ``reverbscope``: a short home screen instead of argparse's error.
        # A command is still required, so the exit code stays the usage error's.
        from reverbscope.edition import is_terminal_package

        print(
            render_home(err, __version__, terminal_edition=is_terminal_package()), file=sys.stderr
        )
        return 2

    def nothing_played() -> str:
        # Before the stream starts nothing has reached the loudspeaker; say so.
        if args.command == "measure" and not getattr(args, "playback_started", False):
            return _("Nothing was played.")
        return ""

    def trace() -> None:
        if args.verbose and sys.stderr is not None:
            traceback.print_exc(file=sys.stderr)

    try:
        return COMMANDS[args.command](args)
    except MeasurementCancelledError as exc:
        print(
            render_status(err, "warn", _("stopped: {message}").format(message=localize(str(exc)))),
            file=sys.stderr,
        )
        return 130
    except _UsageError as exc:
        print(render_error(err, str(exc), detail=exc.detail, hints=exc.hints), file=sys.stderr)
        return 2
    except ReverbScopeError as exc:
        trace()
        # A cause the user can fix (the sweep played at the wrong speed) comes
        # with the steps to take, DAW by DAW, under the error.
        detail = "\n".join(part for part in (nothing_played(), *failure_guidance(exc)) if part)
        print(
            render_error(
                err, localize(str(exc)), detail=detail, hints=_error_hints(exc, args.command)
            ),
            file=sys.stderr,
        )
        return 1
    except KeyboardInterrupt:
        print(render_status(err, "warn", _("interrupted")), file=sys.stderr)
        return 130
    except BrokenPipeError:
        # The reader went away (``reverbscope show … | head``): nothing to say.
        # Point stdout at nothing so the interpreter's final flush is quiet.
        with contextlib.suppress(OSError, ValueError, AttributeError):
            os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        return 1
    except OSError as exc:
        # A folder that cannot be created, a file that cannot be written: the
        # user's to fix, not a bug.
        trace()
        print(
            render_error(
                err,
                _os_error_text(exc),
                detail=nothing_played(),
                hints=[f"reverbscope {args.command} --help"],
            ),
            file=sys.stderr,
        )
        return 1
    except MemoryError:
        # A long recording: the analysis holds roughly 140 bytes per sample. The
        # user's to fix (cut it, free memory), not a bug in ReverbScope.
        trace()
        print(
            render_error(
                err,
                _("not enough memory to finish this command"),
                detail=_(
                    "A long recording needs a lot of memory: about 2 GB for 5 minutes at "
                    "48 kHz, in proportion to its length. Cut it to the sweep plus a few "
                    "seconds of silence on each side (any audio editor or DAW does it), or "
                    "close other programs, and run the command again."
                ),
                hints=[f"reverbscope {args.command} --help"],
            ),
            file=sys.stderr,
        )
        return 1
    except Exception as exc:
        if args.verbose:
            raise
        print(
            render_error(
                err,
                _("unexpected {kind}: {message}").format(kind=type(exc).__name__, message=exc),
                detail=_(
                    "This is a bug in ReverbScope. Run the command again with --verbose for the "
                    "details and include them, with the environment report, in a bug report."
                ),
                hints=[
                    shlex.join(["reverbscope", "--verbose", *argv_list]),
                    "reverbscope doctor",
                ],
            ),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
