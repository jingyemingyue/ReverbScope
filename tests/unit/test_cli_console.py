"""The command line's presentation layer (reverbscope.cli.console / render).

Checked by meaning, not by escape codes: display widths, wrapping, tables
that fall back to blocks, the colour policy (NO_COLOR, --color, pipes), the
ASCII fallback, the progress line on a terminal and in a file, JSON on stdout,
exit codes, and the Chinese command line.
"""

from __future__ import annotations

import io
import json
import re
from collections.abc import Iterator
from pathlib import Path

import numpy as np
import pytest
from scipy.signal import fftconvolve

from reverbscope.audio.backend import DeviceInfo
from reverbscope.cli.console import (
    Console,
    ProgressLine,
    cell_width,
    pad,
    truncate,
    use_color,
    wrap,
)
from reverbscope.cli.main import main
from reverbscope.cli.render import render_devices, validity_cell
from reverbscope.i18n import activate
from reverbscope.models.result import Validity
from tests.conftest import make_rir
from tests.zh_tokens import english_words

ESC = "\x1b["
CLOSING = "，。、；：！？）」』”’》"


class _Stream(io.StringIO):
    def __init__(self, *, tty: bool, encoding: str = "utf-8") -> None:
        super().__init__()
        self._tty = tty
        self._encoding = encoding

    def isatty(self) -> bool:
        return self._tty

    @property
    def encoding(self) -> str:  # type: ignore[override]
        return self._encoding


@pytest.fixture
def home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Path]:
    monkeypatch.setenv("REVERBSCOPE_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("NO_COLOR", raising=False)
    try:
        yield tmp_path
    finally:
        activate("en")


# --- Widths and wrapping -----------------------------------------------------------


def test_display_width_counts_cjk_as_two_and_marks_as_zero() -> None:
    assert cell_width("采样率") == 6
    assert cell_width("48 kHz") == 6
    assert cell_width("ＡＢ") == 4  # full-width Latin
    assert cell_width("é") == 1  # e + combining acute
    assert cell_width("\x1b[1m采样\x1b[0m") == 4  # escape sequences take no room
    assert pad("采样率", 8) == "采样率  "
    assert pad("12", 5, "right") == "   12"
    assert cell_width(truncate("MacBook Pro 麦克风 很长的名字", 12)) <= 12


def test_wrap_breaks_chinese_between_characters_and_never_starts_with_punctuation() -> None:
    text = "T30 衰减范围不足，可用范围 18.4 dB，要求范围 35 dB；因此不报告可靠的 T30。" * 3
    for width in (20, 27, 33, 40):
        lines = wrap(text, width, first="  ", rest="    ")
        assert all(cell_width(line) <= width for line in lines), (width, lines)
        assert not any(line.strip()[:1] in CLOSING for line in lines), (width, lines)
        assert "".join(line.strip() for line in lines).replace(" ", "") == text.replace(" ", "")


def test_wrap_never_splits_a_path_or_url() -> None:
    path = "C:\\Users\\runneradmin\\AppData\\Local\\Temp\\pytest-of-runneradmin\\session"
    url = "https://github.com/jingyemingyue/ReverbScope/actions/runs/36321028824"
    for token in (path, url, "/Users/me/Music/ReverbScope/2026-09-27/a-long-session-folder"):
        lines = wrap(f"Saved session to {token}", 30)
        assert token in lines, lines


def test_wrap_splits_a_word_longer_than_the_line() -> None:
    lines = wrap("a-very-long-file-name-without-any-spaces.wav", 12, first="", rest="")
    assert all(cell_width(line) <= 12 for line in lines)
    assert "".join(lines) == "a-very-long-file-name-without-any-spaces.wav"


# --- Colour policy and fallbacks ------------------------------------------------------


@pytest.mark.parametrize(
    ("tty", "mode", "env", "expected"),
    [
        (True, "auto", {}, True),
        (False, "auto", {}, False),  # pipe or file
        (True, "auto", {"NO_COLOR": "1"}, False),
        (True, "auto", {"TERM": "dumb"}, False),
        (True, "never", {}, False),
        (False, "always", {}, True),
        (True, "always", {"NO_COLOR": "1"}, True),  # an explicit flag wins
    ],
)
def test_colour_policy(
    tty: bool, mode: str, env: dict[str, str], expected: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The policy only; on Windows the console call would refuse an in-memory
    # stream (a real console is asked in _enable_windows_vt).
    monkeypatch.setattr("reverbscope.cli.console._enable_windows_vt", lambda _stream: True)
    assert use_color(_Stream(tty=tty), mode, env) is expected  # type: ignore[arg-type]


def test_a_pipe_gets_no_escape_sequences_and_a_fixed_width() -> None:
    console = Console.for_stream(_Stream(tty=False), "auto", {})
    assert not console.color and not console.interactive
    assert console.width == 100
    assert ESC not in "\n".join(console.status("ok", "done") + console.title("ReverbScope"))


def test_symbols_fall_back_to_ascii_words_where_unicode_cannot_be_written() -> None:
    console = Console.for_stream(_Stream(tty=False, encoding="ascii"), "auto", {})
    assert not console.unicode
    text = "\n".join(
        console.status("ok", "a")
        + console.status("warn", "b")
        + console.status("error", "c")
        + console.table(["#", "x"], [["1", "y"]])
    )
    assert "[OK]" in text and "[WARN]" in text and "[ERROR]" in text
    text.encode("ascii")


@pytest.mark.parametrize("unicode", [True, False])
def test_validity_is_never_colour_alone(unicode: bool) -> None:
    console = Console(color=True, unicode=unicode)
    for validity in Validity:
        cell = re.sub(r"\x1b\[[0-9;]*m", "", validity_cell(console, validity))
        symbol, word = cell.split(" ", 1)
        assert symbol and word, validity


# --- Tables ---------------------------------------------------------------------------------


def _devices() -> list[DeviceInfo]:
    return [
        DeviceInfo(0, "MacBook Pro 麦克风", "Core Audio", 1, 0, 48000.0, True, False),
        DeviceInfo(1, "MOTU M4", "Core Audio", 4, 4, 48000.0, False, True),
        DeviceInfo(
            2,
            "An extremely long aggregate device name that no table column can hold",
            "Core Audio",
            16,
            16,
            96000.0,
            False,
            False,
        ),
    ]


def test_device_table_aligns_chinese_names() -> None:
    lines = render_devices(Console(width=110), _devices()[:2]).splitlines()
    rows = [line for line in lines if re.match(r"^  [0-9] ", line)]
    assert len(rows) == 2
    # The host API column starts at the same display column on every row.
    starts = {cell_width(row[: row.index("Core Audio")]) for row in rows}
    assert len(starts) == 1, rows


def test_a_device_name_is_never_cut() -> None:
    """A name wider than the table allows turns the table into blocks; the
    name is what identifies the hardware, so it is shown whole."""
    text = render_devices(Console(width=110), _devices())
    assert all(cell_width(line) <= 110 for line in text.splitlines())
    assert "An extremely long aggregate device name that no table column can hold" in text


def test_a_narrow_terminal_gets_blocks_instead_of_a_wide_table() -> None:
    text = render_devices(Console(width=40), _devices())
    lines = text.splitlines()
    assert all(cell_width(line) <= 40 for line in lines), text
    assert "MOTU M4" in text and "96 kHz" in text
    assert not any("───   ───" in line for line in lines)  # no ruled table header


# --- Progress --------------------------------------------------------------------------------


def test_progress_in_a_file_is_one_line_without_carriage_returns() -> None:
    stream = _Stream(tty=False)
    progress = ProgressLine(Console(), stream, "Recording", 9.0)
    for step in range(101):
        progress.update(step / 100)
    progress.finish()
    assert stream.getvalue().count("\n") == 1
    assert "\r" not in stream.getvalue() and ESC not in stream.getvalue()


def test_progress_on_a_terminal_redraws_one_line() -> None:
    stream = _Stream(tty=True)
    clock = iter(float(n) for n in range(1000))
    progress = ProgressLine(
        Console(interactive=True, width=80), stream, "Recording", 9.0, now=lambda: next(clock)
    )
    for step in range(11):
        progress.update(step / 10)
    progress.finish()
    text = stream.getvalue()
    assert text.count("\n") == 1 and text.endswith("\n")
    assert text.count("\r") >= 10
    assert "100%" in text and "00:09 / 00:09" in text


def test_progress_without_a_stream_is_silent() -> None:
    progress = ProgressLine(Console(interactive=True), None, "Recording", 9.0)
    for step in range(11):
        progress.update(step / 10)
    progress.finish()


def test_progress_is_throttled() -> None:
    stream = _Stream(tty=True)
    progress = ProgressLine(Console(interactive=True), stream, "Recording", 9.0, now=lambda: 5.0)
    for step in range(100):
        progress.update(step / 100)
    assert stream.getvalue().count("\r") == 1  # same instant: drawn once


# --- The command line ------------------------------------------------------------------------


def _take(root: Path, name: str = "take") -> tuple[Path, Path]:
    from reverbscope.io.wav import read_wav, write_wav

    sweep = root / "sweep.wav"
    if not sweep.exists():
        assert main(["sweep", "--out", str(sweep), "--duration", "2", "--post-silence", "2"]) == 0
    signal = read_wav(sweep)
    ir = make_rir(signal.sample_rate, rt60_s=0.5, reflections=[(0.011, 0.8)])
    rec = fftconvolve(signal.samples, ir)[: signal.n_samples + ir.shape[0]]
    rec = rec + np.random.default_rng(3).normal(0.0, 3e-5, rec.shape[0])
    return write_wav(root / f"{name}.wav", rec, signal.sample_rate, subtype="FLOAT"), sweep


def test_piped_reports_carry_no_escape_codes(
    home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    recording, sweep = _take(home)
    commands = [
        ["analyze", "--recording", str(recording), "--sweep", str(sweep), "--out", str(home / "s")],
        ["show", str(home / "s")],
        ["compare", str(home / "s"), str(home / "s")],
        ["--backend", "fake", "doctor", "--probe"],
        ["--backend", "fake", "devices"],
        ["--backend", "fake", "devices", "--host-apis"],
    ]
    for argv in commands:
        capsys.readouterr()
        assert main(argv) == 0, argv
        captured = capsys.readouterr()
        for text in (captured.out, captured.err):
            assert ESC not in text and "\r" not in text, argv


def test_color_always_styles_a_pipe(home: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--color", "always", "--backend", "fake", "devices"]) == 0
    assert ESC in capsys.readouterr().out


def test_json_stdout_is_json_for_every_command_that_offers_it(
    home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    recording, sweep = _take(home)
    runs = [
        ["--format", "json", "analyze", "--recording", str(recording), "--sweep", str(sweep),
         "--out", str(home / "s")],
        ["--format", "json", "show", str(home / "s")],
        ["--format", "json", "compare", str(home / "s"), str(home / "s")],
        ["--format", "json", "--backend", "fake", "doctor"],
        ["--format", "json", "--backend", "fake", "devices"],
        # Standalone: the safety note and status lines must not reach stdout.
        ["--format", "json", "--backend", "fake", "measure", "--out", str(home / "m"),
         "--duration", "1", "--post-silence", "1"],
    ]  # fmt: skip
    for argv in runs:
        capsys.readouterr()
        assert main(argv) == 0, argv
        captured = capsys.readouterr()
        json.loads(captured.out)
        assert ESC not in captured.out and ESC not in captured.err
    assert "low level" in captured.err  # the measure safety note, on stderr


def test_measure_status_is_on_stdout_and_progress_on_stderr(
    home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    argv = ["--backend", "fake", "measure", "--out", str(home / "m")]
    assert main([*argv, "--duration", "1", "--post-silence", "1"]) == 0
    captured = capsys.readouterr()
    assert "Checks" in captured.out and "Input and output use one host API" in captured.out
    assert "ReverbScope analysis" in captured.out
    assert captured.err.strip().splitlines() == ["Playing the sweep and recording …"]


@pytest.mark.parametrize(
    ("argv", "code", "stream", "text"),
    [
        (["--version"], 0, "out", "reverbscope"),
        (["--help"], 0, "out", "commands:"),
        (["analyze"], 2, "err", "required"),
        (["analyze", "--recording", "nope.wav", "--sweep", "nope.wav"], 1, "err", "error:"),
        (
            ["--backend", "fake", "measure", "--out", "m", "--input-channel", "12"],
            1,
            "err",
            "Nothing was played.",
        ),
        (["--backend", "fake", "measure", "--out", "m", "--level", "-6"], 2, "err", "acknowledge"),
    ],
)
def test_exit_codes_and_streams(
    home: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    argv: list[str],
    code: int,
    stream: str,
    text: str,
) -> None:
    monkeypatch.chdir(home)
    try:
        result = main(argv)
    except SystemExit as exc:  # argparse: --help, --version, usage errors
        result = int(exc.code or 0)
    assert result == code
    captured = capsys.readouterr()
    assert text in getattr(captured, stream)
    if code:
        assert captured.out == ""  # nothing but the error, and on stderr


def test_a_refused_measurement_says_nothing_was_played_only_before_playback(
    home: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from reverbscope.audio.fake import FakeBackend
    from reverbscope.errors import AudioDeviceError

    def broken(*_args: object, **_kwargs: object) -> None:
        raise AudioDeviceError("the stream stopped")

    monkeypatch.setattr(FakeBackend, "play_and_record", broken)
    assert main(["--backend", "fake", "measure", "--out", str(home / "m")]) == 1
    err = capsys.readouterr().err
    assert "the stream stopped" in err and "Nothing was played" not in err


def test_the_chinese_command_line_shows_no_english_prose(
    home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    devices = ("ReverbScope fake interface",)
    runs = [
        ["--lang", "zh_CN", "--backend", "fake", "devices"],
        ["--lang", "zh_CN", "--backend", "fake", "devices", "--probe"],
        ["--lang", "zh_CN", "--backend", "fake", "devices", "--host-apis"],
        ["--lang", "zh_CN", "sweep", "--out", str(home / "z.wav"), "--duration", "2"],
        ["--lang", "zh_CN", "--backend", "fake", "measure", "--out", str(home / "zm"),
         "--duration", "1", "--post-silence", "1"],
    ]  # fmt: skip
    for argv in runs:
        capsys.readouterr()
        assert main(argv) == 0, argv
        captured = capsys.readouterr()
        text = "\n".join(
            line
            for line in (captured.out + captured.err).splitlines()
            if str(home) not in line and "reverbscope analyze" not in line
        )
        # "fake" is the synthetic backend's name: data, like a device name.
        assert english_words(text, data=devices) == [], (argv, text)


# --- Help ------------------------------------------------------------------------------


def _help_screens() -> dict[str, str]:
    import argparse

    from reverbscope.cli.main import _translate_argparse, build_parser

    _translate_argparse()
    screens: dict[str, str] = {}

    def walk(parser: argparse.ArgumentParser, path: str) -> None:
        screens[path] = parser.format_help()
        for action in parser._actions:
            if isinstance(action, argparse._SubParsersAction):
                for name, sub in action.choices.items():
                    walk(sub, f"{path} {name}")

    walk(build_parser(), "reverbscope")
    return screens


def test_a_next_step_quotes_a_path_that_contains_a_space() -> None:
    import shlex

    from reverbscope.cli.console import shell_command
    from reverbscope.cli.render import render_saved_next_steps

    session = "My Room/take 1"
    text = render_saved_next_steps(Console(width=100, unicode=True), session)
    line = next(line.strip() for line in text.splitlines() if "reverbscope compare" in line)
    assert line == shell_command(["reverbscope", "compare", session, "<other-session>"])
    assert shlex.split(line)[2:] == [session, "<other-session>"]


def test_a_windows_path_uses_slashes_so_any_shell_can_replay_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A backslash is a separator on Windows and an escape everywhere else.

    Next-step lines are replayed with a POSIX split (see the demo
    walkthrough). Printing the path with slashes keeps that split, cmd and
    PowerShell on the same string, without quoting a path that has no space.
    """
    import shlex

    from reverbscope.cli import console as console_module

    monkeypatch.setattr(console_module.os, "name", "nt")
    show = console_module.shell_command(["reverbscope", "show", r"reverbscope-demo\position-a"])
    assert show == "reverbscope show reverbscope-demo/position-a"
    assert shlex.split(show) == ["reverbscope", "show", "reverbscope-demo/position-a"]
    compare = console_module.shell_command(["reverbscope", "compare", r"My Room\take 1", "<other>"])
    assert compare == 'reverbscope compare "My Room/take 1" <other>'
    assert shlex.split(compare)[2:] == ["My Room/take 1", "<other>"]
    # The placeholder is an instruction, not a path, so it stays bare.
    assert "<other>" in compare and "'<other>'" not in compare and '"<other>"' not in compare


def test_a_posix_shell_quotes_a_backslash(monkeypatch: pytest.MonkeyPatch) -> None:
    from reverbscope.cli import console as console_module

    monkeypatch.setattr(console_module.os, "name", "posix")
    shown = console_module.shell_command(["reverbscope", "show", r"odd\name"])
    assert shown == "reverbscope show 'odd\\name'"


def test_every_help_example_is_a_valid_command(home: Path) -> None:
    import shlex

    from reverbscope.cli.main import build_parser

    examples = [
        line.strip()
        for text in _help_screens().values()
        for line in text.splitlines()
        if line.startswith("  reverbscope ")
    ]
    assert len(examples) >= 10
    for example in examples:
        build_parser().parse_args(shlex.split(example)[1:])  # exits on an unknown flag


@pytest.mark.parametrize("lang", ["en", "zh_CN"])
@pytest.mark.parametrize("columns", [80, 60])
def test_help_fits_the_terminal_in_both_languages(
    home: Path, monkeypatch: pytest.MonkeyPatch, lang: str, columns: int
) -> None:
    monkeypatch.setenv("COLUMNS", str(columns))
    activate(lang)
    for path, text in _help_screens().items():
        for line in text.splitlines():
            if "{acoustic_guitar," in line:
                continue  # argparse cannot break one option's choice list
            if line.startswith("  reverbscope "):
                continue  # an example stays one line so it can be copied
            stripped = line.lstrip()
            if stripped.startswith(("usage:", "用法")):
                continue  # the synopsis stays one line; argparse will not wrap it
            assert cell_width(line) <= columns, (path, columns, line)


def test_a_long_session_path_is_printed_whole(
    home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A Windows temp path is longer than the report width; it must stay one
    piece so it can be copied (it was split across lines once)."""
    deep = home / ("a-very-long-folder-name-" * 5) / "session"
    recording, sweep = _take(home)
    capsys.readouterr()
    assert (
        main(["analyze", "--recording", str(recording), "--sweep", str(sweep), "--out", str(deep)])
        == 0
    )
    analysed = capsys.readouterr().out
    assert main(["show", str(deep)]) == 0
    shown = capsys.readouterr().out
    assert len(str(deep)) > 100
    assert str(deep) in shown
    assert f"Saved session to {deep}" in analysed


def test_the_windowed_bundle_has_no_stdout_and_still_runs(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """reverbscope-gui (PyInstaller, windowed) runs with sys.stdout and
    sys.stderr set to None; building the parser once touched sys.stdout and
    the unhandled error left a modal dialog open (Release #24, Windows)."""
    import sys

    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)
    from reverbscope.cli.main import build_parser

    build_parser()
    assert main(["--backend", "fake", "devices"]) == 0
    assert main(["--backend", "fake", "doctor"]) == 0
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
