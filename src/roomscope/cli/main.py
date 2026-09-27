"""``roomscope`` command-line interface.

Subcommands: ``demo``, ``sweep``, ``analyze``, ``measure``, ``devices``, ``show``,
``compare``, ``gui``, ``analyze-ir``, ``project``, ``session``, ``export``, ``schema``.

Reports go to stdout, diagnostics and progress to stderr. Colour is used only
on an interactive terminal (see :mod:`roomscope.cli.style`).
"""

from __future__ import annotations

import argparse
import contextlib
import json
import logging
import shutil
import sys
import textwrap
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, cast

from roomscope import __version__
from roomscope.cli.report import (
    comparison_summary_lines,
    format_comparison_report,
    format_report,
    summary_lines,
)
from roomscope.cli.style import ProgressLine, Style, color_supported, terminal_width
from roomscope.errors import ConfigurationError, MeasurementCancelledError, RoomScopeError
from roomscope.i18n import _, activate
from roomscope.interpretation import available_profiles
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


DOCS_URL = "https://github.com/jingyemingyue/RoomScope"


class _HelpFormatter(argparse.RawDescriptionHelpFormatter):
    """Keeps hand-formatted descriptions/epilogs and shows each option's default.

    A default is appended only when it tells the reader something (not ``None``,
    ``False`` or an empty string) and the help text does not already name it.
    """

    def __init__(self, prog: str) -> None:
        width = min(100, max(60, shutil.get_terminal_size(fallback=(88, 24)).columns))
        super().__init__(prog, max_help_position=30, width=width)

    def _get_help_string(self, action: argparse.Action) -> str | None:
        text = action.help or ""
        default = action.default
        if (
            default is None
            or default is False
            or default == ""
            or default is argparse.SUPPRESS
            or isinstance(action, argparse._HelpAction | argparse._VersionAction)
            or not action.option_strings
            or "default" in text.lower()
            or "默认" in text
        ):
            return action.help
        return text + " " + _("(default: %(default)s)")

    def _split_lines(self, text: str, width: int) -> list[str]:
        # Like argparse, but never break "roomscope-demo" or "--speaker-distance".
        return textwrap.wrap(
            " ".join(text.split()), width, break_on_hyphens=False, break_long_words=False
        )


def _command(sub: object, name: str, text: str) -> argparse.ArgumentParser:
    """Subcommand with the same gettext string as help (parent list) and description."""
    parser = sub.add_parser(  # type: ignore[attr-defined]
        name,
        help=text,
        description=text,
        add_help=False,
        formatter_class=_HelpFormatter,
    )
    parser.add_argument("-h", "--help", action="help", help=_("show this help message and exit"))
    return cast(argparse.ArgumentParser, parser)


def _main_epilog() -> str:
    return "\n".join(
        [
            _("Quick start:"),
            "  roomscope demo",
            "      " + _("try RoomScope without audio hardware (synthetic data)"),
            "  roomscope sweep --out sweep.wav",
            "      " + _("1. write the test signal; play it and record the mic in your DAW"),
            "  roomscope analyze --recording take.wav --sweep sweep.wav --out pos-a/",
            "      " + _("2. analyse the exported recording"),
            "  roomscope compare pos-a/ pos-b/",
            "      " + _("3. compare two microphone positions"),
            "",
            _("Run 'roomscope <command> --help' for the options of one command."),
            _("Documentation: {url}").format(url=DOCS_URL),
        ]
    )


def _add_sweep_arguments(parser: argparse.ArgumentParser, *, default_level: float) -> None:
    group = parser.add_argument_group(_("test signal"))
    group.add_argument(
        "--sample-rate",
        type=int,
        default=DEFAULT_SAMPLE_RATE,
        choices=SUPPORTED_SAMPLE_RATES,
        help=_("sample rate (Hz)"),
    )
    group.add_argument(
        "--duration",
        type=float,
        metavar="S",
        default=10.0,
        help=_("sweep duration in seconds (default 10)"),
    )
    group.add_argument(
        "--start-hz",
        type=float,
        metavar="HZ",
        default=20.0,
        help=_("sweep start frequency (default 20)"),
    )
    group.add_argument(
        "--end-hz",
        type=float,
        metavar="HZ",
        default=20000.0,
        help=_("sweep end frequency (default 20000)"),
    )
    group.add_argument(
        "--fade-in",
        type=float,
        metavar="S",
        default=0.05,
        help=_("fade-in in seconds (default 0.05)"),
    )
    group.add_argument(
        "--fade-out",
        type=float,
        metavar="S",
        default=0.01,
        help=_("fade-out in seconds (default 0.01)"),
    )
    group.add_argument(
        "--level",
        type=float,
        metavar="DBFS",
        default=default_level,
        help=_("peak level in dBFS (default {level:g})").format(level=default_level),
    )
    group.add_argument(
        "--pre-silence",
        type=float,
        metavar="S",
        default=1.0,
        help=_("silence before the sweep (s)"),
    )
    group.add_argument(
        "--post-silence",
        type=float,
        metavar="S",
        default=3.0,
        help=_("silence after the sweep (s)"),
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
    analysis = parser.add_argument_group(_("analysis"))
    analysis.add_argument(
        "--channel",
        type=int,
        default=None,
        metavar="N",
        help=_("recording channel to analyse (0-based)"),
    )
    analysis.add_argument(
        "--smoothing",
        type=int,
        default=6,
        metavar="N",
        help=_("fractional-octave smoothing 1/N (0 = off)"),
    )
    analysis.add_argument(
        "--profile",
        default=None,
        choices=available_profiles(),
        help=_("recording profile that shapes the interpretation (default: user settings)"),
    )
    notes = parser.add_argument_group(_("session notes (stored in session.json)"))
    notes.add_argument("--room", default="", metavar="TEXT", help=_("room name (metadata)"))
    notes.add_argument(
        "--position", default="", metavar="TEXT", help=_("measurement position (metadata)")
    )
    notes.add_argument("--mic", default="", metavar="TEXT", help=_("microphone name (metadata)"))
    notes.add_argument("--notes", default="", metavar="TEXT", help=_("free-text notes (metadata)"))
    placement = parser.add_argument_group(_("placement (optional tape measurements)"))
    placement.add_argument(
        "--speaker-distance",
        type=float,
        default=None,
        metavar="M",
        help=_(
            "straight line from the loudspeaker to the microphone capsule (m), measured "
            "with a tape. Without it no geometry can be derived from the reflections"
        ),
    )
    placement.add_argument(
        "--mic-height",
        type=float,
        default=None,
        metavar="M",
        help=_(
            "microphone capsule above the first solid horizontal surface below it (m) -- "
            "the desk top at a desk, otherwise the floor. Needs --speaker-distance"
        ),
    )
    placement.add_argument(
        "--temperature",
        type=float,
        default=None,
        metavar="C",
        help=_("air temperature (C); 20 C is assumed, and reported as assumed, without it"),
    )
    output = parser.add_argument_group(_("output"))
    output.add_argument("--no-curves", action="store_true", help=_("omit curves from result.json"))
    output.add_argument("--json", action="store_true", help=_("deprecated: use --format json"))


def _add_loopback_file_arguments(parser: argparse.ArgumentParser) -> None:
    group = parser.add_argument_group(_("loopback (optional)"))
    group.add_argument(
        "--loopback",
        type=Path,
        default=None,
        metavar="WAV",
        help=_("separate loopback WAV from the same take (same sample rate)"),
    )
    group.add_argument(
        "--loopback-channel",
        type=int,
        default=None,
        metavar="N",
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
        description=_("RoomScope: an open-source, DAW-independent recording environment analyzer.")
        + "\n"
        + textwrap.fill(
            _(
                "Measure reverberation (RT60), early reflections, frequency response, noise "
                "floor and low-frequency resonances, and compare microphone positions. "
                "WAV in, WAV out."
            ),
            width=78,
        ),
        epilog=_main_epilog(),
        formatter_class=_HelpFormatter,
        add_help=False,
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
        choices=["portaudio", "fake"],
        help=_("audio backend for Standalone Mode: portaudio (default) or fake"),
    )
    parser.add_argument(
        "--lang",
        default=None,
        metavar="{en,zh_CN}",
        help=_("UI language (en, zh_CN). Overrides settings and ROOMSCOPE_LANG"),
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help=_(
            "plain text only (colour is also off when NO_COLOR is set or output is not a terminal)"
        ),
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
    sub = parser.add_subparsers(dest="command", metavar="<command>", title=_("commands"))

    p_demo = _command(
        sub,
        "demo",
        _("try RoomScope without audio hardware: simulate, analyse and compare two positions"),
    )
    p_demo.add_argument(
        "--out",
        type=Path,
        default=Path("roomscope-demo"),
        metavar="DIR",
        help=_("folder for the demo files (created)"),
    )
    p_demo.add_argument(
        "--profile",
        default="vocal",
        choices=available_profiles(),
        help=_("recording profile used to interpret the demo"),
    )

    p_sweep = _command(sub, "sweep", _("write the ESS test signal WAV (+ JSON sidecar)"))
    p_sweep.add_argument(
        "--out", required=True, type=Path, metavar="WAV", help=_("output WAV path")
    )
    _add_sweep_arguments(p_sweep, default_level=-12.0)

    p_an = _command(sub, "analyze", _("analyse a recording made with the sweep"))
    p_an.add_argument(
        "--recording",
        required=True,
        type=Path,
        metavar="WAV",
        help=_("recorded WAV (any length, untrimmed)"),
    )
    p_an.add_argument(
        "--sweep",
        required=True,
        type=Path,
        metavar="WAV",
        help=_("sweep WAV or its .roomscope-sweep.json sidecar"),
    )
    p_an.add_argument(
        "--out",
        type=Path,
        default=None,
        metavar="DIR",
        help=_("directory for session.json, result.json, IR WAV"),
    )
    _add_analysis_arguments(p_an)
    _add_loopback_file_arguments(p_an)

    p_me = _command(sub, "measure", _("Standalone Mode: play the sweep and record the microphone"))
    p_me.add_argument(
        "--out", required=True, type=Path, metavar="DIR", help=_("session directory (created)")
    )
    iface = p_me.add_argument_group(_("audio interface"))
    iface.add_argument(
        "--input-device",
        type=int,
        default=None,
        metavar="IDX",
        help=_("input device index (see 'devices')"),
    )
    iface.add_argument(
        "--output-device", type=int, default=None, metavar="IDX", help=_("output device index")
    )
    iface.add_argument(
        "--input-channel",
        type=int,
        default=1,
        metavar="N",
        help=_("input channel, 1-based (default 1)"),
    )
    iface.add_argument(
        "--input-channels",
        default=None,
        metavar="LIST",
        help=_("1-based input channels, comma-separated (e.g. 1,2); overrides --input-channel"),
    )
    iface.add_argument(
        "--output-channel",
        type=int,
        default=1,
        metavar="N",
        help=_("output channel, 1-based (default 1)"),
    )
    iface.add_argument(
        "--loopback-channel",
        type=int,
        default=None,
        metavar="N",
        dest="measure_loopback_channel",
        help=_("1-based loopback input channel (recorded with the microphone)"),
    )
    iface.add_argument(
        "--acknowledge-level",
        action="store_true",
        help=_("required for levels above -12 dBFS; confirms the monitor level was set low first"),
    )
    _add_sweep_arguments(p_me, default_level=-20.0)
    _add_analysis_arguments(p_me)

    _command(sub, "devices", _("list audio devices (Standalone Mode)"))

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
    p_show.add_argument("--json", action="store_true", help=_("deprecated: use --format json"))
    p_show.add_argument("--no-curves", action="store_true", help=_("omit curves from JSON output"))

    p_cmp = _command(sub, "compare", _("compare two saved sessions"))
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
    p_cmp.add_argument("--json", action="store_true", help=_("deprecated: use --format json"))

    p_gui = _command(sub, "gui", _("start the desktop GUI (needs the 'gui' extra)"))
    p_gui.add_argument(
        "--smoke",
        action="store_true",
        help=_("construct the window offscreen and exit (bundle smoke; no loudspeaker)"),
    )

    p_ir = _command(sub, "analyze-ir", _("analyse an impulse-response WAV from another tool"))
    p_ir.add_argument(
        "--ir", required=True, type=Path, metavar="WAV", help=_("impulse-response WAV")
    )
    p_ir.add_argument(
        "--band",
        nargs=2,
        type=float,
        metavar=("LO", "HI"),
        default=None,
        help=_("declared excitation band in Hz (required for band metrics)"),
    )
    p_ir.add_argument("--out", type=Path, default=None, metavar="DIR", help=_("session directory"))
    _add_analysis_arguments(p_ir)

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
    p_avg.add_argument("--json", action="store_true", help=_("deprecated: use --format json"))
    p_show_proj = _command(proj_sub, "show", _("list positions and sessions"))
    p_show_proj.add_argument("project", type=Path, help=_("project directory"))

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

    p_schema = _command(sub, "schema", _("print a shipped JSON Schema"))
    p_schema.add_argument(
        "name",
        choices=["result", "session", "comparison", "project", "sidecar"],
        help=_("which schema to print"),
    )
    return parser


def cmd_sweep(args: argparse.Namespace) -> int:
    from roomscope.io.wav import write_sweep_file

    settings = _sweep_settings(args)
    wav_path, sidecar = write_sweep_file(settings, args.out)
    print(
        _(
            "Wrote {wav} ({seconds:.1f} s at {rate} Hz, "
            "sweep {start:g}-{end:g} Hz, {duration:g} s, {level:g} dBFS)"
        ).format(
            wav=wav_path,
            seconds=settings.total_samples / settings.sample_rate,
            rate=settings.sample_rate,
            start=settings.start_hz,
            end=settings.end_hz,
            duration=settings.duration_s,
            level=settings.level_dbfs,
        )
    )
    print(_("Wrote {sidecar} (keep it next to the WAV)").format(sidecar=sidecar))
    style = _style(args)
    print()
    print(style.heading(_("Next steps")))
    print(
        _("  1. Import {wav} into your DAW and play it through your monitors.").format(
            wav=wav_path.name
        )
    )
    print(_("  2. Record the measurement microphone on another track (same sample rate)."))
    print(_("  3. Export that track as WAV (no trimming needed) and run:"))
    print(
        "     "
        + style.command(f"roomscope analyze --recording <file> --sweep {wav_path} --out <folder>")
    )
    print(style.dim(_("Start with the monitor level low and raise it between takes if needed.")))
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


def _use_json(args: argparse.Namespace) -> bool:
    if getattr(args, "format", None) == "json":
        return True
    if getattr(args, "json", False):
        print(
            _(
                "warning: --json is deprecated; use --format json "
                "(--json will be removed in a future minor release)"
            ),
            file=sys.stderr,
        )
        return True
    return False


def _style(args: argparse.Namespace, stream: object = None) -> Style:
    """Colour for ``stream`` (stdout by default) unless ``--no-color`` was given."""
    target = sys.stdout if stream is None else stream
    requested = False if getattr(args, "no_color", False) else None
    return Style(color=color_supported(target, requested=requested))  # type: ignore[arg-type]


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
        print(format_report(result, findings, profile, style=_style(args)))
        if out_dir is not None:
            print("\n" + _("Saved session to {path}").format(path=out_dir))
    return 0


def cmd_analyze(args: argparse.Namespace) -> int:
    return _run_analysis(args.recording, args.sweep, args, out_dir=args.out)


def cmd_devices(args: argparse.Namespace) -> int:
    from roomscope.audio.backend import get_backend

    devices = get_backend(args.backend).list_devices()
    style = _style(args)
    if not devices:
        print(_("No audio devices found."))
        return 0
    print(
        style.heading(
            f"{_('idx'):>3}  {_('in'):>3} {_('out'):>3}  {_('rate'):>7}  {_('name')}  [{_('host API')}]"
        )
    )
    for d in devices:
        flags = ("*in" if d.is_default_input else "") + ("*out" if d.is_default_output else "")
        print(
            f"{d.index:>3}  {d.max_input_channels:>3} {d.max_output_channels:>3}  {d.default_sample_rate:7.0f}  "
            f"{d.name}  [{d.host_api}] {style.accent(flags)}".rstrip()
        )
    print()
    print(
        style.dim(
            _(
                "* = system default. Pass the idx to measure: "
                "roomscope measure --input-device <idx> --output-device <idx> --out <folder>"
            )
        )
    )
    return 0


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
    if settings.level_dbfs > SAFE_MAX_LEVEL_DBFS and not args.acknowledge_level:
        print(
            _(
                "Level {level:g} dBFS is above {max_level:g} dBFS. "
                "Set the monitor level low first and pass --acknowledge-level to confirm."
            ).format(level=settings.level_dbfs, max_level=SAFE_MAX_LEVEL_DBFS),
            file=sys.stderr,
        )
        return 2
    backend = get_backend(args.backend)
    print(_(SAFETY_MESSAGE))
    if args.input_device is not None:
        backend.check_sample_rate(args.input_device, settings.sample_rate, kind="input")
    if args.output_device is not None:
        backend.check_sample_rate(args.output_device, settings.sample_rate, kind="output")
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
    args.loopback_channel = plan.analysis_loopback_channel
    args.channel = plan.analysis_channel
    out_dir: Path = args.out
    out_dir.mkdir(parents=True, exist_ok=True)
    sweep_path, _sidecar = write_sweep_file(settings, out_dir / "sweep.wav")
    print(
        _(
            "Playing sweep on output channel {output}, recording input "
            "channel(s) {channels} via {backend} ..."
        ).format(
            output=args.output_channel,
            channels=",".join(str(c) for c in channels),
            backend=backend.name,
        )
    )
    progress = ProgressLine(_("recording"))
    try:
        recording = backend.play_and_record(
            measurement_signal(settings),
            settings.sample_rate,
            input_device=args.input_device,
            output_device=args.output_device,
            input_channels=channels,
            output_channel=args.output_channel,
            level_dbfs=settings.level_dbfs,
            progress=progress,
        )
    finally:
        progress.finish()
    recording_path = write_wav(
        out_dir / "recording.wav", recording.samples, settings.sample_rate, subtype="FLOAT"
    )
    print(
        _("Recorded {seconds:.1f} s to {path}").format(
            seconds=recording.duration_s, path=recording_path
        )
    )
    return _run_analysis(
        recording_path,
        sweep_path,
        args,
        sweep_settings=settings,
        mode="standalone",
        out_dir=out_dir,
        hardware=plan,
        output_channel=int(args.output_channel),
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
            print(format_comparison_report(comparison, findings, profile, style=_style(args)))
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
        print(format_report(loaded.result, findings, profile, style=_style(args)))
        print("\n" + _("Session: {path}").format(path=loaded.directory))
    return 0


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
        print(format_comparison_report(comparison, findings, profile, style=_style(args)))
        if args.out is not None:
            print("\n" + _("Wrote comparison to {path}").format(path=args.out))
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
        print(format_report(result, findings, profile, style=_style(args)))
        if args.out is not None:
            print("\n" + _("Saved session to {path}").format(path=args.out))
    return 0


def cmd_session(args: argparse.Namespace) -> int:
    from roomscope.io.session_store import bundle_session

    if args.session_command == "bundle":
        path = bundle_session(args.session, args.out, include_audio=not args.no_audio)
        print(_("Wrote {path}").format(path=path))
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
        print(_("Wrote {path}").format(path=path))
        return 0
    if command == "add":
        project = add_session(args.project, args.session, position=args.position)
        print(_("{n} position(s) in {path}").format(n=len(project.positions), path=args.project))
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
                    klass=averaged.iso_3382_2_class,
                    sources=averaged.n_source_positions,
                    mics=averaged.n_microphone_positions,
                    combos=averaged.n_combinations,
                )
            )
            print(
                f"{_('band'):>10}  {_('EDT'):>8}  {_('T20'):>8}  {_('T30'):>8}  {_('RT60'):>8}  n"
            )
            for band in averaged.bands:
                edt = f"{band.edt.seconds:.2f}" if band.edt.seconds is not None else "-"
                t20 = f"{band.t20.seconds:.2f}" if band.t20.seconds is not None else "-"
                t30 = f"{band.t30.seconds:.2f}" if band.t30.seconds is not None else "-"
                rt = f"{band.rt60_estimate_s:.2f}" if band.rt60_estimate_s is not None else "-"
                print(
                    f"{band.band_label:>10}  {edt:>8}  {t20:>8}  {t30:>8}  {rt:>8}  {band.t20.count}"
                )
        return 0
    raise RoomScopeError(f"unknown project command {command}")


def cmd_gui(args: argparse.Namespace) -> int:
    # ``roomscope.ui.app`` imports Qt lazily, so check for it before starting (a
    # CLI-only install must get this hint, not a traceback).
    try:
        import PySide6.QtWidgets  # noqa: F401

        from roomscope.ui.app import run_app
    except ImportError as exc:
        print(
            _(
                "The desktop app needs the 'gui' extra (PySide6 Essentials). "
                'Install it with: pip install "PySide6_Essentials>=6.6" ({error})'
            ).format(error=exc),
            file=sys.stderr,
        )
        return 2
    return int(run_app(smoke=bool(getattr(args, "smoke", False))))


#: Findings per position the demo prints (warnings and notices; the rest is in ``show``).
DEMO_FINDINGS_SHOWN = 2


def _demo_description(key: str, fallback: str) -> str:
    """Translated description of a demo position (session.json keeps the English)."""
    return {
        "position-a": _("close to the desk and the side wall"),
        "position-b": _("moved 1 m back from the desk"),
    }.get(key, fallback)


def cmd_demo(args: argparse.Namespace) -> int:
    from roomscope.demo import run_demo
    from roomscope.interpretation import interpret, interpret_comparison
    from roomscope.io.recent import remember_session

    style = _style(args)
    width = terminal_width()
    out_dir: Path = args.out
    profile = _resolve_profile(args)
    print(style.heading(_("RoomScope demo")))
    print("=" * width)
    banner = _(
        "SYNTHETIC DATA: a simulated room. No audio hardware is used and nothing is "
        "played; the numbers below describe the simulation, not a real room."
    )
    for line in textwrap.wrap(banner, width=width):
        print(style.caution(line))
    print(_("Simulating and analysing two microphone positions ..."), file=sys.stderr)
    run = run_demo(out_dir, profile=profile)
    for take in run.takes:
        remember_session(take.session_dir)

    settings = run.settings
    print()
    print(style.heading(_("1. Test signal")))
    print(
        "  "
        + _("{path}  ({rate} Hz, {start:g}-{end:g} Hz, {duration:g} s sweep)").format(
            path=run.sweep_path,
            rate=settings.sample_rate,
            start=settings.start_hz,
            end=settings.end_hz,
            duration=settings.duration_s,
        )
    )
    print()
    print(style.heading(_("2. Simulated recordings (what your DAW would export)")))
    for take in run.takes:
        print(
            "  "
            + _("{path}  position {label}: {description}").format(
                path=take.recording_path,
                label=take.position.label,
                description=_demo_description(take.position.key, take.position.description),
            )
        )
    print()
    print(style.heading(_("3. Analysis ({profile} profile)").format(profile=profile)))
    for take in run.takes:
        print()
        print(
            style.accent(
                _("Position {label}: {description}").format(
                    label=take.position.label,
                    description=_demo_description(take.position.key, take.position.description),
                )
            )
        )
        print("\n".join(summary_lines(take.result, style)[1:]))
        shown = [f for f in interpret(take.result, profile) if str(f.severity) != "info"]
        for finding in shown[:DEMO_FINDINGS_SHOWN]:
            print(
                textwrap.fill(
                    f"{finding.topic}: {finding.message}",
                    width=width,
                    initial_indent=f"  {style.severity(str(finding.severity))} ",
                    subsequent_indent="      ",
                )
            )
        if len(shown) > DEMO_FINDINGS_SHOWN:
            print(
                style.dim(
                    _("  (+{n} more in the full report: roomscope show {path})").format(
                        n=len(shown) - DEMO_FINDINGS_SHOWN, path=take.session_dir
                    )
                )
            )
    print()
    first, second = run.takes[0].position.label, run.takes[1].position.label
    print(style.heading(_("4. Comparison {a} -> {b}").format(a=first, b=second)))
    print("\n".join(comparison_summary_lines(run.comparison, style)[1:]))
    for finding in interpret_comparison(run.comparison, profile):
        print(
            textwrap.fill(
                f"{finding.topic}: {finding.message}",
                width=width,
                initial_indent=f"  {style.severity(str(finding.severity))} ",
                subsequent_indent="      ",
            )
        )
    a_dir, b_dir = run.takes[0].session_dir, run.takes[1].session_dir
    print()
    print(style.heading(_("Next steps")))
    steps = (
        (f"roomscope show {a_dir}", _("full report for position A")),
        (f"roomscope compare {a_dir} {b_dir} --same-input-gain", _("full comparison")),
        ("roomscope gui", _("open the sessions in the desktop app (needs the 'gui' extra)")),
        ("roomscope sweep --out sweep.wav", _("start a real measurement with your DAW")),
    )
    for command, meaning in steps:
        print(f"  {style.command(command)}")
        print(f"      {style.dim(meaning)}")
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
    "measure": cmd_measure,
    "gui": cmd_gui,
    "session": cmd_session,
    "export": cmd_export,
    "project": cmd_project,
}


def _tolerate_narrow_encodings() -> None:
    """Reports use a few non-ASCII signs (—, →, Δ). A pipe on a legacy code page
    (cp1252 on Windows) cannot encode them; replace them instead of crashing."""
    for stream in (sys.stdout, sys.stderr):
        encoding = (getattr(stream, "encoding", None) or "").lower().replace("-", "")
        reconfigure = getattr(stream, "reconfigure", None)
        if encoding and encoding != "utf8" and callable(reconfigure):
            with contextlib.suppress(ValueError, OSError):
                reconfigure(errors="replace")


def main(argv: Sequence[str] | None = None) -> int:
    _tolerate_narrow_encodings()
    argv_list = list(sys.argv[1:] if argv is None else argv)
    activate(_peek_option(argv_list, ("--lang",)))
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        # Bare ``roomscope``: show the overview (commands and quick start).
        parser.print_help()
        return 0
    configure_logging(logging.DEBUG if args.verbose else logging.WARNING)
    try:
        return COMMANDS[args.command](args)
    except MeasurementCancelledError as exc:
        print(_("stopped: {message}").format(message=exc), file=sys.stderr)
        return 130
    except RoomScopeError as exc:
        print(_("error: {message}").format(message=exc), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print(_("interrupted"), file=sys.stderr)
        return 130


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
