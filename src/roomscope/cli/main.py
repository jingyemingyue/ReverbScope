"""``roomscope`` command-line interface.

Subcommands: ``sweep``, ``analyze``, ``show``, ``devices``, ``measure``, ``gui``,
``compare``, ``schema``, ``analyze-ir``, ``session``, ``export``, ``project``.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from roomscope import __version__
from roomscope.cli.console import COLOR_MODES, Console, ProgressLine
from roomscope.cli.render import (
    render_analysis,
    render_comparison,
    render_devices,
    render_environment,
    render_error,
    render_host_apis,
    render_inventory,
    render_measure_plan,
    render_status,
    render_sweep_written,
)
from roomscope.errors import ConfigurationError, MeasurementCancelledError, RoomScopeError
from roomscope.i18n import N_, _, activate, localize
from roomscope.interpretation import available_profiles
from roomscope.interpretation.profiles import band_text
from roomscope.labels import accuracy_class_text
from roomscope.logging_config import configure_logging
from roomscope.models.configuration import (
    DEFAULT_SAMPLE_RATE,
    SUPPORTED_SAMPLE_RATES,
    AnalysisSettings,
    SweepSettings,
)

if TYPE_CHECKING:
    from roomscope.audio.backend import ChannelPlan

log = logging.getLogger("roomscope.cli")


#: argparse's own texts. The standard library looks them up in gettext's
#: "argparse" domain, which has no Chinese catalog; RoomScope's catalog
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
    }
)


def _argparse_gettext(message: str) -> str:
    return _(message) if message in ARGPARSE_MESSAGES else message


def _translate_argparse() -> None:
    """Route argparse's module-level ``_`` through RoomScope's catalog."""
    setattr(argparse, "_", _argparse_gettext)  # noqa: B010 - a module attribute, not ours


#: The root help lists the commands in these groups, in this order.
COMMAND_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (N_("Measurement"), ("sweep", "measure", "analyze", "analyze-ir")),
    (N_("Results"), ("show", "compare", "export", "session")),
    (N_("Project"), ("project",)),
    (N_("Diagnostics"), ("devices", "doctor", "schema")),
    (N_("Desktop"), ("gui",)),
)

#: A few commands to start from (every flag exists in the parser; a test runs them).
ROOT_EXAMPLES = (
    "roomscope sweep --out sweep.wav",
    "roomscope analyze --recording take.wav --sweep sweep.wav --out session-1",
    "roomscope doctor --probe",
)


class _HelpFormatter(argparse.RawDescriptionHelpFormatter):
    """argparse's layout, with help text wrapped by display width.

    argparse wraps with :mod:`textwrap`, which counts a Chinese character as
    one column, so a translated help line ran past the terminal's edge.
    Descriptions and epilogs stay as written (they are laid out already).
    """

    def _split_lines(self, text: str, width: int) -> list[str]:
        from roomscope.cli.console import wrap

        return wrap(" ".join(text.split()), max(width, 11))


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


def _commands_block(helps: dict[str, str]) -> str:
    """The root help's command list, grouped and aligned (display width aware)."""
    from roomscope.cli.console import terminal_width, wrap

    width = terminal_width(sys.stdout, sys.stdout.isatty(), os.environ)
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
    parser.add_argument(
        "--sample-rate",
        type=int,
        default=DEFAULT_SAMPLE_RATE,
        choices=SUPPORTED_SAMPLE_RATES,
        help=_("sample rate (Hz)"),
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=10.0,
        help=_("sweep duration in seconds (default 10)"),
    )
    parser.add_argument(
        "--start-hz", type=float, default=20.0, help=_("sweep start frequency (default 20)")
    )
    parser.add_argument(
        "--end-hz",
        type=float,
        default=20000.0,
        help=_("sweep end frequency (default 20000)"),
    )
    parser.add_argument(
        "--fade-in", type=float, default=0.05, help=_("fade-in in seconds (default 0.05)")
    )
    parser.add_argument(
        "--fade-out", type=float, default=0.01, help=_("fade-out in seconds (default 0.01)")
    )
    parser.add_argument(
        "--level",
        type=float,
        default=default_level,
        help=_("peak level in dBFS (default {level:g})").format(level=default_level),
    )
    parser.add_argument(
        "--pre-silence", type=float, default=1.0, help=_("silence before the sweep (s)")
    )
    parser.add_argument(
        "--post-silence", type=float, default=3.0, help=_("silence after the sweep (s)")
    )


def _sweep_settings(args: argparse.Namespace) -> SweepSettings:
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


def _add_analysis_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--channel", type=int, default=None, help=_("recording channel to analyse (0-based)")
    )
    parser.add_argument(
        "--smoothing",
        type=int,
        default=6,
        help=_("fractional-octave smoothing 1/N (0 = off)"),
    )
    parser.add_argument("--room", default="", help=_("room name (metadata)"))
    parser.add_argument("--position", default="", help=_("measurement position (metadata)"))
    parser.add_argument("--mic", default="", help=_("microphone name (metadata)"))
    parser.add_argument("--notes", default="", help=_("free-text notes (metadata)"))
    parser.add_argument("--no-curves", action="store_true", help=_("omit curves from result.json"))
    parser.add_argument(
        "--json", action="store_true", help=_("print the result as JSON instead of a report")
    )
    parser.add_argument(
        "--speaker-distance",
        type=float,
        default=None,
        metavar="M",
        help=_(
            "straight line from the loudspeaker to the microphone capsule (m), measured "
            "with a tape. Without it no geometry can be derived from the reflections"
        ),
    )
    parser.add_argument(
        "--mic-height",
        type=float,
        default=None,
        metavar="M",
        help=_(
            "microphone capsule above the first solid horizontal surface below it (m) -- "
            "the desk top at a desk, otherwise the floor. Needs --speaker-distance"
        ),
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=None,
        metavar="C",
        help=_("air temperature (C); 20 C is assumed, and reported as assumed, without it"),
    )
    parser.add_argument(
        "--profile",
        default=None,
        choices=available_profiles(),
        help=_("recording profile that shapes the interpretation (default: user settings)"),
    )


def _add_loopback_file_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--loopback",
        type=Path,
        default=None,
        help=_("separate loopback WAV from the same take (same sample rate)"),
    )
    parser.add_argument(
        "--loopback-channel",
        type=int,
        default=None,
        help=_(
            "0-based loopback channel of the recording (or of --loopback if it is multi-channel)"
        ),
    )


def _analysis_settings(
    args: argparse.Namespace, *, loopback_channel: int | None = None
) -> AnalysisSettings:
    channel = getattr(args, "loopback_channel", None)
    return AnalysisSettings(
        channel=args.channel,
        fr_smoothing_fraction=args.smoothing,
        placement_distance_m=args.speaker_distance,
        placement_mic_height_m=args.mic_height,
        placement_temperature_c=args.temperature,
        loopback_channel=loopback_channel if loopback_channel is not None else channel,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="roomscope",
        description=_("RoomScope: an open-source, DAW-independent recording environment analyzer."),
        add_help=False,
        formatter_class=_HelpFormatter,
    )
    parser.add_argument("-h", "--help", action="help", help=_("show this help message and exit"))
    parser.add_argument(
        "--version",
        action="version",
        version=f"roomscope {__version__}",
        help=_("show program's version number and exit"),
    )
    parser.add_argument("-v", "--verbose", action="store_true", help=_("debug logging"))
    parser.add_argument(
        "--backend",
        default=None,
        help=_("audio backend for Standalone Mode: portaudio (default) or fake"),
    )
    parser.add_argument(
        "--lang",
        default=None,
        help=_("UI language (en, zh_CN). Overrides settings and ROOMSCOPE_LANG"),
    )
    parser.add_argument(
        "--format",
        choices=["text", "json"],
        default=None,
        help=_("text report or JSON on stdout (diagnostics stay on stderr)"),
    )
    parser.add_argument(
        "--copy-recording",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=_("copy the raw recording into the session folder (default: user settings)"),
    )
    parser.add_argument(
        "--color",
        choices=COLOR_MODES,
        default="auto",
        help=_(
            "colour in the terminal: auto (default; off for pipes, files and NO_COLOR), always, never"
        ),
    )
    sub = parser.add_subparsers(
        dest="command", required=True, metavar="<command>", help=argparse.SUPPRESS
    )

    p_sweep = _command(
        sub,
        "sweep",
        _("write the ESS test signal WAV (+ JSON sidecar)"),
        examples=(
            "roomscope sweep --out sweep.wav",
            "roomscope sweep --out sweep.wav --sample-rate 96000 --duration 15",
        ),
    )
    p_sweep.add_argument("--out", required=True, type=Path, help=_("output WAV path"))
    _add_sweep_arguments(p_sweep, default_level=-12.0)

    p_an = _command(
        sub,
        "analyze",
        _("analyse a recording made with the sweep"),
        examples=(
            "roomscope analyze --recording take.wav --sweep sweep.wav",
            "roomscope analyze --recording take.wav --sweep sweep.wav --out session-1",
        ),
    )
    p_an.add_argument(
        "--recording", required=True, type=Path, help=_("recorded WAV (any length, untrimmed)")
    )
    p_an.add_argument(
        "--sweep",
        required=True,
        type=Path,
        help=_("sweep WAV or its .roomscope-sweep.json sidecar"),
    )
    p_an.add_argument(
        "--out",
        type=Path,
        default=None,
        help=_("directory for session.json, result.json, IR WAV"),
    )
    _add_analysis_arguments(p_an)
    _add_loopback_file_arguments(p_an)

    p_dev = _command(sub, "devices", _("list audio devices (Standalone Mode)"))
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
    p_dev.add_argument("--json", action="store_true", help=_("print the inventory as JSON"))

    p_doc = _command(
        sub,
        "doctor",
        _("print an environment report for bug reports and debugging"),
        examples=("roomscope doctor", "roomscope doctor --probe"),
    )
    p_doc.add_argument("--json", action="store_true", help=_("print the report as JSON"))
    p_doc.add_argument(
        "--probe",
        action="store_true",
        help=_("also ask every device which sample rates it accepts (nothing is played)"),
    )

    p_me = _command(
        sub,
        "measure",
        _("Standalone Mode: play the sweep and record the microphone"),
        examples=(
            "roomscope devices",
            "roomscope measure --out session-1 --input-device 2 --output-device 2",
        ),
    )
    p_me.add_argument("--out", required=True, type=Path, help=_("session directory (created)"))
    p_me.add_argument(
        "--input-device", type=int, default=None, help=_("input device index (see 'devices')")
    )
    p_me.add_argument("--output-device", type=int, default=None, help=_("output device index"))
    p_me.add_argument(
        "--input-channel", type=int, default=1, help=_("input channel, 1-based (default 1)")
    )
    p_me.add_argument(
        "--input-channels",
        default=None,
        help=_("1-based input channels, comma-separated (e.g. 1,2); overrides --input-channel"),
    )
    p_me.add_argument(
        "--output-channel", type=int, default=1, help=_("output channel, 1-based (default 1)")
    )
    p_me.add_argument(
        "--loopback-channel",
        type=int,
        default=None,
        dest="measure_loopback_channel",
        help=_("1-based loopback input channel (recorded with the microphone)"),
    )
    p_me.add_argument(
        "--latency",
        choices=("low", "high"),
        default=None,
        help=_("PortAudio latency class of the stream (default: PortAudio's high latency)"),
    )
    p_me.add_argument(
        "--wasapi-exclusive",
        action="store_true",
        help=_("Windows WASAPI: open the device in exclusive mode (no mixer, no conversion)"),
    )
    p_me.add_argument(
        "--coreaudio-set-rate",
        action="store_true",
        help=_("macOS: let RoomScope set the device's sample rate instead of converting"),
    )
    p_me.add_argument(
        "--acknowledge-level",
        action="store_true",
        help=_("required for levels above -12 dBFS; confirms the monitor level was set low first"),
    )
    _add_sweep_arguments(p_me, default_level=-20.0)
    _add_analysis_arguments(p_me)

    p_show = _command(
        sub, "show", _("print a saved session or comparison.json report, or list sessions")
    )
    p_show.add_argument(
        "path",
        type=Path,
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
        "--json", action="store_true", help=_("print the result as JSON instead of a report")
    )
    p_show.add_argument("--no-curves", action="store_true", help=_("omit curves from JSON output"))

    p_cmp = _command(
        sub,
        "compare",
        _("compare two saved sessions"),
        examples=(
            "roomscope compare session-1 session-2",
            "roomscope compare session-1 session-2 --out comparison.json",
        ),
    )
    p_cmp.add_argument("baseline", type=Path, help=_("baseline session directory or session.json"))
    p_cmp.add_argument(
        "candidate", type=Path, help=_("candidate session directory or session.json")
    )
    p_cmp.add_argument(
        "--out",
        type=Path,
        default=None,
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
        "--json", action="store_true", help=_("print comparison.json instead of a report")
    )

    p_schema = _command(sub, "schema", _("print a shipped JSON Schema"))
    p_schema.add_argument(
        "name",
        choices=["result", "session", "comparison", "project", "sidecar"],
        help=_("which schema to print"),
    )

    p_ir = _command(sub, "analyze-ir", _("analyse an impulse-response WAV from another tool"))
    p_ir.add_argument("--ir", required=True, type=Path, help=_("impulse-response WAV"))
    p_ir.add_argument(
        "--band",
        nargs=2,
        type=float,
        metavar=("LO", "HI"),
        default=None,
        help=_("declared excitation band in Hz (required for band metrics)"),
    )
    p_ir.add_argument("--out", type=Path, default=None, help=_("session directory"))
    _add_analysis_arguments(p_ir)

    p_gui = _command(sub, "gui", _("start the desktop GUI (needs the 'gui' extra)"))
    p_gui.add_argument(
        "--smoke",
        action="store_true",
        help=_("construct the window offscreen and exit (bundle smoke; no loudspeaker)"),
    )

    p_sess = _command(sub, "session", _("session folder tools"))
    sess_sub = p_sess.add_subparsers(dest="session_command", required=True)
    p_bundle = _command(sess_sub, "bundle", _("zip a session for a bug report"))
    p_bundle.add_argument("session", type=Path, help=_("session directory or session.json"))
    p_bundle.add_argument(
        "--no-audio",
        action="store_true",
        help=_("leave WAV files out of the zip"),
    )
    p_bundle.add_argument("--out", type=Path, default=None, help=_("zip path (file or directory)"))

    p_ex = _command(sub, "export", _("export curves through an exporter"))
    p_ex.add_argument("session", type=Path, help=_("session directory or session.json"))
    p_ex.add_argument(
        "--format",
        dest="export_format",
        default="csv",
        help=_("exporter name (default csv)"),
    )
    p_ex.add_argument("--out", type=Path, default=None, help=_("output directory"))

    p_proj = _command(sub, "project", _("project folders (one room, several positions)"))
    proj_sub = p_proj.add_subparsers(dest="project_command", required=True)
    p_init = _command(proj_sub, "init", _("create a project.json"))
    p_init.add_argument("--out", required=True, type=Path, help=_("project directory"))
    p_init.add_argument("--name", default="", help=_("room name"))
    p_init.add_argument("--notes", default="", help=_("free-text notes"))
    p_add = _command(proj_sub, "add", _("add a session to a position"))
    p_add.add_argument("project", type=Path, help=_("project directory"))
    p_add.add_argument("session", type=Path, help=_("session directory"))
    p_add.add_argument("--position", required=True, help=_("position label"))
    p_avg = _command(proj_sub, "average", _("spatial average of VALID T values"))
    p_avg.add_argument("project", type=Path, help=_("project directory"))
    p_avg.add_argument("--sources", type=int, default=1, help=_("number of source positions"))
    p_avg.add_argument("--json", action="store_true", help=_("print JSON instead of a table"))
    p_show_proj = _command(proj_sub, "show", _("list positions and sessions"))
    p_show_proj.add_argument("project", type=Path, help=_("project directory"))
    # The command list is printed grouped (below), so argparse's own list is
    # hidden; put the command placeholder back into the usage line.
    usage = parser.format_usage().strip()
    prefix = _("usage: ")
    if usage.startswith(prefix):
        usage = usage[len(prefix) :]
    parser.usage = usage + " <command> ..."
    helps = {action.dest: str(action.help) for action in sub._choices_actions}
    parser.description = "\n\n".join(
        [
            _("RoomScope: an open-source, DAW-independent recording environment analyzer."),
            _commands_block(helps),
        ]
    )
    parser.epilog = "\n\n".join(
        [
            _examples_block(ROOT_EXAMPLES),
            _("Run a command with --help for its options, for example: roomscope measure --help"),
        ]
    )
    return parser


def cmd_sweep(args: argparse.Namespace) -> int:
    from roomscope.io.wav import write_sweep_file

    settings = _sweep_settings(args)
    wav_path, sidecar = write_sweep_file(settings, args.out)
    print(render_sweep_written(_console(args), settings, wav_path, sidecar))
    return 0


def _peek_option(argv: Sequence[str], names: tuple[str, ...]) -> str | None:
    for index, arg in enumerate(argv):
        for name in names:
            if arg == name and index + 1 < len(argv):
                return argv[index + 1]
            prefix = name + "="
            if arg.startswith(prefix):
                return arg[len(prefix) :]
    return None


def _console(args: argparse.Namespace, stream: Any = None) -> Console:
    """How to lay out text for ``stream`` (stdout by default) under ``--color``."""
    return Console.for_stream(stream or sys.stdout, getattr(args, "color", None) or "auto")


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
        from roomscope.settings import load_settings

        name = load_settings().default_profile or "generic"
    if name not in available_profiles():
        return "generic"
    return name


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
) -> int:
    """Analyse a recording and optionally save a session.

    ``hardware`` is the Standalone channel plan; the session then records the
    1-based interface channels. In Universal DAW Mode the DAW did the routing,
    so the session leaves them empty and the analysed WAV column stays in
    ``analysis_settings`` (0-based).
    """
    from roomscope.core.pipeline import Reference, analyze
    from roomscope.interpretation import interpret
    from roomscope.io.recent import remember_session
    from roomscope.io.session_store import save_measurement
    from roomscope.io.wav import load_reference, read_wav
    from roomscope.models.session import MeasurementSession

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
            copy_recording=getattr(args, "copy_recording", None),
        )
        remember_session(out_dir)
        log.info("session saved to %s", session_path)

    if _use_json(args):
        payload = result.to_dict(include_curves=not args.no_curves)
        payload["findings"] = [f.to_dict() for f in findings]
        print(json.dumps(payload, indent=1))
    else:
        console = _console(args)
        print(render_analysis(console, result, findings, profile, inputs=inputs))
        if out_dir is not None:
            print()
            print(render_status(console, "ok", _("Saved session to {path}").format(path=out_dir)))
    return 0


def cmd_analyze(args: argparse.Namespace) -> int:
    inputs = [(_("Recording"), str(args.recording)), (_("Sweep"), str(args.sweep))]
    if getattr(args, "loopback", None) is not None:
        inputs.append((_("Loopback"), str(args.loopback)))
    return _run_analysis(args.recording, args.sweep, args, out_dir=args.out, inputs=inputs)


def cmd_devices(args: argparse.Namespace) -> int:
    from roomscope.audio.backend import get_backend

    backend = get_backend(args.backend)
    if (
        getattr(args, "probe", False)
        or getattr(args, "host_apis", False)
        or getattr(args, "json", False)
        or getattr(args, "format", None) == "json"
    ):
        return _print_inventory(backend, args)
    print(render_devices(_console(args), backend.list_devices()))
    return 0


def _print_inventory(backend: Any, args: argparse.Namespace) -> int:
    from roomscope.audio.inventory import build_inventory

    inventory = build_inventory(backend, probe_rates=bool(getattr(args, "probe", False)))
    if getattr(args, "json", False) or getattr(args, "format", None) == "json":
        print(json.dumps(inventory.to_dict(), indent=1))
        return 0
    if getattr(args, "host_apis", False):
        print(render_host_apis(_console(args), inventory))
    else:
        print(render_inventory(_console(args), inventory))
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    from roomscope.diagnostics import environment_report

    report = environment_report(backend_name=args.backend, probe_rates=args.probe)
    if getattr(args, "json", False) or getattr(args, "format", None) == "json":
        print(json.dumps(report, indent=1, default=str))
    else:
        print(render_environment(_console(args), report))
    return 0


def _stream_options(args: argparse.Namespace) -> Any:
    from roomscope.audio.backend import StreamOptions

    return StreamOptions(
        latency=getattr(args, "latency", None),
        wasapi_exclusive=bool(getattr(args, "wasapi_exclusive", False)),
        coreaudio_change_device_rate=bool(getattr(args, "coreaudio_set_rate", False)),
    )


def cmd_measure(args: argparse.Namespace) -> int:
    from roomscope.audio.backend import (
        SAFE_MAX_LEVEL_DBFS,
        SAFETY_MESSAGE,
        get_backend,
        plan_input_channels,
    )
    from roomscope.core.sweep import measurement_signal
    from roomscope.io.wav import write_sweep_file, write_wav

    settings = _sweep_settings(args)
    err = _console(args, sys.stderr)
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
    if args.input_channels:
        requested = [
            int(part.strip()) for part in str(args.input_channels).split(",") if part.strip()
        ]
    else:
        requested = [int(args.input_channel)]
    # Hardware inputs are 1-based, recording columns 0-based; validate the
    # mapping before anything is played (#13).
    plan = plan_input_channels(requested, getattr(args, "measure_loopback_channel", None))
    channels = list(plan.input_channels)
    options = _stream_options(args)
    # Device pre-flight, shared with the GUI: one host API for both
    # directions, channels that exist, the rate on the devices the stream will
    # open, and a warning for two devices on two clocks (docs/AUDIO_DEVICES.md).
    from roomscope.audio.inventory import build_inventory, preflight

    inventory = build_inventory(backend, probe_rates=False)
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
    args.loopback_channel = plan.analysis_loopback_channel
    args.channel = plan.analysis_channel
    out_dir: Path = args.out
    out_dir.mkdir(parents=True, exist_ok=True)
    sweep_path, _sidecar = write_sweep_file(settings, out_dir / "sweep.wav")
    # Progress is drawn by the thread that waits for the stream, never by the
    # audio callback; a failing display cannot stop the take (the backend
    # catches it). JSON mode shows none.
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
    args.playback_started = True
    try:
        recording = backend.play_and_record(
            measurement_signal(settings),
            settings.sample_rate,
            input_device=args.input_device,
            output_device=args.output_device,
            input_channels=channels,
            output_channel=args.output_channel,
            level_dbfs=settings.level_dbfs,
            progress=None if progress is None else progress.update,
            options=options,
        )
    finally:
        if progress is not None:
            progress.finish()
    recording_path = write_wav(
        out_dir / "recording.wav", recording.samples, settings.sample_rate, subtype="FLOAT"
    )
    print(
        render_status(
            err if as_json else out,
            "ok",
            _("Recorded {seconds:.1f} s to {path}").format(
                seconds=recording.duration_s, path=recording_path
            ),
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
        mode="standalone",
        out_dir=out_dir,
        hardware=plan,
        output_channel=int(args.output_channel),
        device_warnings=recording.device_warnings,
        inputs=[(_("Recording"), str(recording_path))],
    )


def _is_comparison_path(path: Path) -> bool:
    """True when ``path`` is ``comparison.json`` or a folder that holds only that file."""
    if path.is_file():
        return path.name == "comparison.json"
    if path.is_dir():
        return (path / "comparison.json").is_file() and not (path / "session.json").is_file()
    return False


def cmd_show(args: argparse.Namespace) -> int:
    from roomscope.interpretation import interpret, interpret_comparison
    from roomscope.io.session_store import list_sessions, load_comparison, load_measurement

    if args.list:
        listings = list_sessions(args.path)
        if not listings:
            print(_("No session.json files under {root}").format(root=args.path))
            return 0
        for item in listings:
            print(f"{item.path}\t{item.label}")
        return 0

    if _is_comparison_path(args.path):
        comparison = load_comparison(args.path)
        profile = _resolve_profile(args, "generic")
        findings = interpret_comparison(comparison, profile)
        if _use_json(args):
            payload = comparison.to_dict()
            payload["findings"] = [f.to_dict() for f in findings]
            print(json.dumps(payload, indent=1))
        else:
            print(render_comparison(_console(args), comparison, findings, profile))
        return 0

    loaded = load_measurement(args.path)
    profile = _resolve_profile(args, loaded.session.recording_profile or "generic")
    findings = interpret(loaded.result, profile)
    if _use_json(args):
        payload = loaded.result.to_dict(include_curves=not args.no_curves)
        payload["findings"] = [f.to_dict() for f in findings]
        payload["session"] = loaded.session.to_dict()
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
}


def _session_inputs(session: Any, directory: Path) -> list[tuple[str, str]]:
    """The saved session's folder and the names the user gave it, as entered."""
    rows = [(_("Session"), str(directory))]
    mode = SESSION_MODES.get(str(session.mode))
    if mode:
        rows.append((_("Mode"), _(mode)))
    for label, value in (
        (_("Room"), session.room_name),
        (_("Position"), session.measurement_position),
        (_("Microphone"), session.microphone_name),
    ):
        if value:
            rows.append((label, str(value)))
    return rows


def cmd_compare(args: argparse.Namespace) -> int:
    from dataclasses import replace

    from roomscope.core.compare import compare
    from roomscope.interpretation import interpret_comparison
    from roomscope.io.session_store import load_measurement, save_comparison
    from roomscope.models.comparison import CompareSettings

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
    if args.out is not None:
        save_comparison(args.out, comparison)
    if _use_json(args):
        payload = comparison.to_dict()
        payload["findings"] = [f.to_dict() for f in findings]
        print(json.dumps(payload, indent=1))
    else:
        console = _console(args)
        print(render_comparison(console, comparison, findings, profile))
        if args.out is not None:
            print()
            print(
                render_status(console, "ok", _("Wrote comparison to {path}").format(path=args.out))
            )
    return 0


def cmd_schema(args: argparse.Namespace) -> int:
    from roomscope.schemas import schema_text

    sys.stdout.write(schema_text(args.name))
    return 0


def cmd_analyze_ir(args: argparse.Namespace) -> int:
    from roomscope.core.pipeline import analyze_impulse_response
    from roomscope.interpretation import interpret
    from roomscope.io.recent import remember_session
    from roomscope.io.session_store import save_measurement
    from roomscope.io.wav import read_wav
    from roomscope.models.session import MeasurementSession

    ir = read_wav(args.ir)
    settings = _analysis_settings(args)
    band = (float(args.band[0]), float(args.band[1])) if args.band else None
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
        print(json.dumps(payload, indent=1))
    else:
        console = _console(args)
        print(
            render_analysis(
                console, result, findings, profile, inputs=[(_("Impulse response"), str(args.ir))]
            )
        )
        if args.out is not None:
            print()
            print(render_status(console, "ok", _("Saved session to {path}").format(path=args.out)))
    return 0


def cmd_session(args: argparse.Namespace) -> int:
    from roomscope.io.session_store import bundle_session

    if args.session_command == "bundle":
        path = bundle_session(args.session, args.out, include_audio=not args.no_audio)
        print(render_status(_console(args), "ok", _("Wrote {path}").format(path=path)))
        return 0
    raise RoomScopeError(f"unknown session command {args.session_command}")


def cmd_export(args: argparse.Namespace) -> int:
    from roomscope.io.exporters import get_exporter
    from roomscope.io.session_store import load_measurement

    loaded = load_measurement(args.session)
    out = args.out if args.out is not None else loaded.directory / "export"
    written = get_exporter(args.export_format).export(loaded.result, out)
    for path in written:
        print(path)
    return 0


def cmd_project(args: argparse.Namespace) -> int:
    from roomscope.core.averaging import average_decay
    from roomscope.io.project_store import (
        add_session,
        is_project,
        list_project_sessions,
        load_project,
        save_project,
    )
    from roomscope.io.session_store import load_measurement
    from roomscope.models.project import Project

    command = args.project_command
    if command == "init":
        project = Project(name=args.name or args.out.name, notes=args.notes)
        path = save_project(args.out, project)
        print(render_status(_console(args), "ok", _("Wrote {path}").format(path=path)))
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
            raise RoomScopeError(f"no project.json in {args.project}")
        project = load_project(args.project)
        print(f"{project.name or args.project}")
        for label, path in list_project_sessions(args.project):
            tag = label or _("(unlisted)")
            print(f"  {tag}\t{path}")
        return 0
    if command == "average":
        if not is_project(args.project):
            raise RoomScopeError(f"no project.json in {args.project}")
        items = list_project_sessions(args.project)
        if not items:
            raise RoomScopeError(f"no sessions in {args.project}")
        loaded = [load_measurement(path) for _label, path in items]
        # A position label is one microphone position; repeated takes there
        # add sessions, not positions (#15). Sessions not assigned to a
        # position are averaged but do not count as positions.
        labelled = [label for label, _path in items if label]
        n_mic = max(1, len(set(labelled)))
        sources = int(args.sources)
        if sources < 1:
            raise ConfigurationError("--sources must be at least 1")
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
            print(
                _(
                    "ISO 3382-2 class: {klass} ({sources} source × {mics} mic, "
                    "{combos} combinations)"
                ).format(
                    klass=accuracy_class_text(averaged.iso_3382_2_class),
                    sources=averaged.n_source_positions,
                    mics=averaged.n_microphone_positions,
                    combos=averaged.n_combinations,
                )
            )
            console = _console(args)
            dash = console.dash()

            def seconds(value: float | None) -> str:
                return f"{value:.2f} s" if value is not None else dash

            rows = [
                [
                    band_text(band.band_label),
                    seconds(band.edt.seconds),
                    seconds(band.t20.seconds),
                    seconds(band.t30.seconds),
                    seconds(band.rt60_estimate_s),
                    str(band.t20.count),
                ]
                for band in averaged.bands
            ]
            print()
            print(
                "\n".join(
                    console.table(
                        [_("Band"), "EDT", "T20", "T30", "RT60", "n"], rows, align="lrrrrr"
                    )
                )
            )
        return 0
    raise RoomScopeError(_("unknown project command {command}").format(command=command))


def cmd_gui(args: argparse.Namespace) -> int:
    try:
        from roomscope.ui.app import run_app
    except ImportError as exc:
        print(
            _("The GUI needs PySide6 Essentials: pip install 'roomscope[gui]' ({error})").format(
                error=exc
            ),
            file=sys.stderr,
        )
        return 2
    return int(run_app(smoke=bool(getattr(args, "smoke", False))))


COMMANDS = {
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
}


def _utf8_when_redirected() -> None:
    """Write UTF-8 to a pipe or file unless the user chose an encoding.

    Redirected output uses the locale code page (cp1252, cp936 on Windows)
    with strict errors, so a report with Δ, → or a Chinese room name raised
    UnicodeEncodeError after the work was done. A console is left alone.
    """
    if os.environ.get("PYTHONIOENCODING"):
        return
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        isatty = getattr(stream, "isatty", None)
        if reconfigure is None or isatty is None:
            continue
        try:
            if not isatty():
                reconfigure(encoding="utf-8", errors="backslashreplace")
        except (OSError, ValueError):
            continue


def main(argv: Sequence[str] | None = None) -> int:
    _utf8_when_redirected()
    argv_list = list(sys.argv[1:] if argv is None else argv)
    activate(_peek_option(argv_list, ("--lang",)))
    _translate_argparse()
    parser = build_parser()
    args = parser.parse_args(argv)
    configure_logging(logging.DEBUG if args.verbose else logging.WARNING)
    err = _console(args, sys.stderr)
    try:
        return COMMANDS[args.command](args)
    except MeasurementCancelledError as exc:
        print(
            render_status(err, "warn", _("stopped: {message}").format(message=localize(str(exc)))),
            file=sys.stderr,
        )
        return 130
    except RoomScopeError as exc:
        # Before the stream starts nothing has reached the loudspeaker; say so.
        detail = (
            _("Nothing was played.")
            if args.command == "measure" and not getattr(args, "playback_started", False)
            else ""
        )
        print(render_error(err, localize(str(exc)), detail=detail), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print(render_status(err, "warn", _("interrupted")), file=sys.stderr)
        return 130


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
