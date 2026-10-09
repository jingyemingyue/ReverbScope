"""The command line's presentation layer (reverbscope.cli.console / render).

Checked by meaning, not by escape codes: display widths, wrapping, tables
that fall back to blocks, the colour policy (NO_COLOR, --color, pipes), the
ASCII fallback, the progress line on a terminal and in a file, JSON on stdout,
exit codes, and the Chinese command line.
"""

from __future__ import annotations

import io
import itertools
import json
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from scipy.signal import fftconvolve

from reverbscope.audio.backend import DeviceInfo
from reverbscope.cli.console import (
    Console,
    ProgressLine,
    Status,
    Verbatim,
    badge_word,
    cell_width,
    pad,
    strip_ansi,
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


OPENING = "（「『“‘《〈【〔([{"


def test_wrap_never_ends_a_line_with_an_opening_bracket() -> None:
    """ "…voiceover 或 auto（" then "generic）": the bracket went with the line
    before what it opens."""
    texts = (
        "acoustic_guitar、choir、drums、generic、room_mic、vocal、voiceover 或 auto（generic）",
        "列出音频设备，并标出每个物理设备的推荐条目（不会播放任何声音）" * 2,
        "《设置》「语言」【中文】“引号”‘单引号’〈书名〉〔注〕『双引号』" * 3,
    )
    for text in texts:
        for width in range(12, 70):
            lines = wrap(text, width, first="  ", rest="  ")
            assert not any(line.rstrip()[-1:] in OPENING for line in lines), (width, lines)
            assert "".join("".join(line.split()) for line in lines) == "".join(text.split())
    assert wrap(texts[0], 60, first="  ", rest="  ")[-1] == "  voiceover 或 auto（generic）"
    # The space after an opening bracket goes down with it.
    assert wrap("see ( the thing ) here", 8) == ["see", "( the", "thing )", "here"]


def test_wrap_never_splits_a_path_or_url() -> None:
    path = "C:\\Users\\runneradmin\\AppData\\Local\\Temp\\pytest-of-runneradmin\\session"
    url = "https://github.com/jingyemingyue/ReverbScope/actions/runs/36321028824"
    for token in (path, url, "/Users/me/Music/ReverbScope/2026-09-27/a-long-session-folder"):
        lines = wrap(f"Saved session to {token}", 30)
        assert token in lines, lines


def test_wrap_never_splits_a_path_that_has_chinese_in_it() -> None:
    """The path glued to ``找不到会话文件：`` was cut between characters (会|话),
    though a path of Latin letters never is."""
    folder = "不存在的文件夹/录音位置甲/会话/再加一层很长很长的目录名称/还有一层"
    windows = "C:\\用户\\录音\\会话\\session.json"
    for token in (folder, windows, "~/录音/会话.json", "录音/会话.json"):
        for width in (20, 30, 44):
            lines = wrap(f"找不到会话文件：{token}，请检查", width)
            # (whole on one line, with the comma that follows it)
            assert any(token in line for line in lines), (width, lines)
    # A pair of words with a slash is text, not a path: it wraps as before.
    lines = wrap("播放/录制在音频回调中失败，请检查设备并重新测量", 12)
    assert all(cell_width(line) <= 12 for line in lines), lines


def test_wrap_splits_a_word_longer_than_the_line() -> None:
    lines = wrap("a-very-long-file-name-without-any-spaces.wav", 12, first="", rest="")
    assert all(cell_width(line) <= 12 for line in lines)
    assert "".join(lines) == "a-very-long-file-name-without-any-spaces.wav"


def test_wrapping_never_separates_a_number_from_its_unit() -> None:
    """Only the at-a-glance rows held numbers to their units: paragraphs,
    status lines and fields broke "至少有 20" / "dB 时", "-12" / "dBFS"."""
    texts = [
        "只有衰减范围至少有 20 dB 时才给出比值，而且它不是房间评分。",
        "Background noise is -69.2 dBFS RMS (uncalibrated digital level, not dB SPL).",
        "Potential mains hum at multiples of 50 Hz: 50 Hz (+57 dB), 100 Hz (+48 dB)",
    ]
    unit = re.compile(r"^\s*(dBFS|dB|kHz|Hz|s|SPL)\b")
    for width in range(20, 90):
        console = Console(width=width)
        blocks = [
            *(console.paragraph(text) for text in texts),
            *(console.status("warn", text) for text in texts),
            console.fields([("Sweep", "20 Hz – 20 kHz · 10 s · -12 dBFS")]),
        ]
        for lines in blocks:
            assert "\u00a0" not in "".join(lines)  # no-break spaces are written back
            for above, below in itertools.pairwise(lines):
                assert not (above.rstrip()[-1:].isdigit() and unit.match(below)), (above, below)
                assert not (above.endswith(" dB") and below.lstrip().startswith("SPL"))


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


@pytest.mark.parametrize(
    ("encoding", "shown"),
    [("cp1252", "20 °C"), ("gbk", "20 °C"), ("latin-1", "20 °C"), ("ascii", "20 C")],
)
def test_the_degree_sign_is_dropped_only_where_the_encoding_lacks_it(
    encoding: str, shown: str
) -> None:
    """cp1252 and GBK (a Chinese Windows code page) cannot write ✓, so the
    other signs become ASCII there, but they hold the degree sign."""
    console = Console.for_stream(_Stream(tty=False, encoding=encoding), "auto", {})
    assert not console.unicode
    line = "343.2 m/s at 20 °C – assumed"
    for text in (console.fit(line), console.readable(line), *console.paragraph(line)):
        assert shown in text and "–" not in text, text
        text.encode(encoding)


def test_the_classic_windows_console_keeps_the_degree_sign(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Its fonts lack ✓ (so the ASCII signs are used) but have °."""
    monkeypatch.setattr("sys.platform", "win32")
    monkeypatch.setattr("reverbscope.cli.console._enable_windows_vt", lambda stream: False)
    console = Console.for_stream(_Stream(tty=True, encoding="utf-8"), "auto", {})
    assert not console.unicode
    assert console.fit("20 °C – 5 °C") == "20 °C - 5 °C"


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


@pytest.mark.parametrize("lang", ["en", "zh_CN"])
def test_progress_never_reaches_the_last_column(monkeypatch: pytest.MonkeyPatch, lang: str) -> None:
    """The line counted six separating spaces but wrote eight: 81 columns on
    an 80-column terminal, which wraps, so every redraw started a new row."""
    from reverbscope.i18n import _

    activate(lang)
    try:
        label = _("Playing the sweep and recording")
        for columns in range(20, 121):
            monkeypatch.setenv("COLUMNS", str(columns))
            stream = _Stream(tty=True)
            console = Console(interactive=True, width=columns)
            progress = ProgressLine(console, stream, label, 7.0, interval=0.0)
            for step in range(11):
                progress.update(step / 10)
            progress.finish()
            frames = stream.getvalue().rstrip("\n").split("\r")[1:]
            assert frames, columns
            widest = max(cell_width(frame) for frame in frames)
            assert widest <= min(columns, 100) - 1, (columns, frames)
    finally:
        activate("en")


# --- The command line ------------------------------------------------------------------------


@pytest.mark.parametrize("lang", ["en", "zh_CN"])
def test_the_demo_note_fits_a_narrow_terminal(
    home: Path, monkeypatch: pytest.MonkeyPatch, lang: str
) -> None:
    """The demo's transient note was written whole: on a terminal narrower
    than it, it wrapped, "\r" returned to the second row only, and the first
    row stayed above the report."""
    import reverbscope.demo
    from reverbscope.errors import ReverbScopeError

    def stop(*_args: object, **_kwargs: object) -> None:
        raise ReverbScopeError("stopped here")

    monkeypatch.setattr(reverbscope.demo, "run_demo", stop)
    for columns in (20, 24, 40):
        stderr = _Stream(tty=True)
        monkeypatch.setattr("sys.stderr", stderr)
        monkeypatch.setenv("COLUMNS", str(columns))
        monkeypatch.setenv("TERM", "xterm")
        main(["--lang", lang, "--color", "never", "demo", "--out", str(home / "d")])
        note, clear = stderr.getvalue().split("\r")[:2]
        assert note and cell_width(note) <= columns - 1, (columns, note)
        assert clear == " " * cell_width(note)


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

    def broken(*_args: object, progress: Any = None, **_kwargs: object) -> None:
        progress(0.25)  # the stream ran for a while
        raise AudioDeviceError("the stream stopped")

    monkeypatch.setattr(FakeBackend, "play_and_record", broken)
    assert main(["--backend", "fake", "measure", "--out", str(home / "m")]) == 1
    err = capsys.readouterr().err
    assert "the stream stopped" in err and "Nothing was played" not in err


def test_a_stream_that_never_opened_played_nothing(
    home: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """playback_started was set before the stream was opened, so PortAudio's
    "Error querying device -1" lost the line "Nothing was played."."""
    from reverbscope.audio.fake import FakeBackend
    from reverbscope.errors import AudioDeviceError

    def unopened(*_args: object, **_kwargs: object) -> None:
        raise AudioDeviceError("playback/recording failed: Error querying device -1")

    monkeypatch.setattr(FakeBackend, "play_and_record", unopened)
    assert main(["--backend", "fake", "measure", "--out", str(home / "m")]) == 1
    err = capsys.readouterr().err
    assert "device -1" in err and "Nothing was played." in err


@pytest.mark.parametrize("missing", ["input", "output", "both"])
def test_measure_refuses_a_machine_without_audio_devices_before_the_plan(
    home: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, missing: str
) -> None:
    """With no device the plan ticked "one host API" and "the selected
    channels exist", wrote sweep.wav, and only the stream failed."""
    from dataclasses import replace

    from reverbscope.audio.fake import FakeBackend

    listed = FakeBackend().list_devices()
    if missing == "both":
        devices = []
    elif missing == "input":
        devices = [replace(d, max_input_channels=0, is_default_input=False) for d in listed]
    else:
        devices = [replace(d, max_output_channels=0, is_default_output=False) for d in listed]
    monkeypatch.setattr(FakeBackend, "list_devices", lambda _self: devices)
    out = home / "m"
    assert main(["--backend", "fake", "measure", "--out", str(out)]) == 1
    captured = capsys.readouterr()
    word = "output" if missing == "output" else "input"
    assert f"no audio {word} device found" in captured.err
    assert "Nothing was played." in captured.err
    assert "Checks" not in captured.out and not out.exists()


def test_the_plan_ticks_no_check_it_could_not_make() -> None:
    from reverbscope.audio.backend import StreamOptions
    from reverbscope.cli.render import render_measure_plan
    from reverbscope.models.configuration import SweepSettings

    def plan(devices: list[DeviceInfo]) -> str:
        return render_measure_plan(
            Console(),
            devices=devices,
            input_device=None,
            output_device=None,
            input_channels=[1],
            loopback_channel=None,
            output_channel=1,
            settings=SweepSettings(),
            backend="portaudio",
            options=StreamOptions(),
            clock_warning=None,
            safe_max_level=-12.0,
        )

    unchecked = plan([])
    assert "one host API" not in unchecked and "channels exist" not in unchecked
    assert "not checked" in unchecked
    interface = DeviceInfo(
        index=0,
        name="Interface",
        host_api="Core Audio",
        max_input_channels=2,
        max_output_channels=2,
        default_sample_rate=48000.0,
        is_default_input=True,
        is_default_output=True,
    )
    checked = plan([interface])
    assert "one host API" in checked and "channels exist" in checked
    assert "not checked" not in checked


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


@pytest.mark.parametrize("folder", ["take(1)", "room&booth", "mix;v2", "$tmp", "a|b", "x*"])
def test_a_next_step_quotes_shell_metacharacters(
    monkeypatch: pytest.MonkeyPatch, folder: str
) -> None:
    """A folder such as demo(1)&x was printed bare: the command to copy was a
    syntax error in bash, and & split it in two in bash and cmd."""
    import shlex

    from reverbscope.cli import console as console_module

    monkeypatch.setattr(console_module.os, "name", "posix")
    shown = console_module.shell_command(["reverbscope", "show", f"{folder}/position-a", "<other>"])
    assert shlex.split(shown) == ["reverbscope", "show", f"{folder}/position-a", "<other>"]
    assert shown.startswith("reverbscope show '") and shown.endswith(" <other>")
    monkeypatch.setattr(console_module.os, "name", "nt")
    shown = console_module.shell_command(["reverbscope", "show", f"{folder}/position-a", "<other>"])
    # cmd and PowerShell hand * to the program as it is.
    quote = "" if folder == "x*" else '"'
    assert shown == f"reverbscope show {quote}{folder}/position-a{quote} <other>"


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
        if example.endswith(" --help"):
            # "reverbscope measure --help": the command must exist; --help would exit.
            example = example.removesuffix(" --help")
            with pytest.raises(SystemExit) as exc:
                build_parser().parse_args(shlex.split(example)[1:])
            assert exc.value.code == 2  # measure without --out, not "invalid choice"
            continue
        build_parser().parse_args(shlex.split(example)[1:])  # exits on an unknown flag


@pytest.mark.parametrize("lang", ["en", "zh_CN"])
def test_help_paragraphs_keep_their_blank_line(home: Path, lang: str) -> None:
    """The description, the command list, the examples and the closing
    sentence ran together: the blank lines between them were dropped."""
    activate(lang)
    root = _help_screens()["reverbscope"]
    heading = "commands:" if lang == "en" else "命令："
    examples = "examples:" if lang == "en" else "示例："
    assert f"\n\n{heading}\n" in root
    assert f"\n\n{examples}\n" in root
    tail = root.split(examples, 1)[1]
    assert "\n\n" in tail.strip(), tail


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


def test_control_characters_from_files_are_shown_as_escapes() -> None:
    """A room name or stored warning from someone else's session reached the
    terminal raw: ESC sequences cleared the screen or retitled the window,
    and a line break forged a report line."""
    from reverbscope.cli.console import Verbatim, printable

    crafted = "Booth\x1b[2J\x1b]0;pwned\x07‮"
    assert printable(crafted) == "Booth\\x1b[2J\\x1b]0;pwned\\x07\\u202e"
    assert printable("A\nRT60 0.30 s\tVALID") == "A\nRT60 0.30 s\tVALID"
    assert printable("A\nRT60\t0.30 s", single_line=True) == "A\\nRT60\\t0.30 s"
    assert printable("录音棚 · 2 m") == "录音棚 · 2 m"
    console = Console(color=True)
    styled = console.style("ok", "green", "bold") + " \x1b[8mhidden\x1b[0m"
    shown = console.readable(styled)
    assert shown.startswith("\x1b[32;1mok\x1b[0m ") and "\\x1b[8mhidden" in shown
    path = console.readable(Verbatim("sessions/a\nb"))
    assert isinstance(path, Verbatim) and path == "sessions/a\\nb"


def test_a_console_without_colour_shows_every_escape_code_as_text() -> None:
    """With colour off ReverbScope writes no escape code at all, so one in a
    stored text is never its own: it was kept, and reached the stream."""
    from reverbscope.cli.console import Verbatim, printable

    plain = Console(color=False)
    assert plain.readable("a\x1b[32mb\x1b[0m") == "a\\x1b[32mb\\x1b[0m"
    assert printable("a\x1b[32mb", own_styles=False) == "a\\x1b[32mb"
    assert printable("a\x1b[32mb") == "a\x1b[32mb"
    assert plain.readable(Verbatim("x\x1b[0m")) == "x\\x1b[0m"


def test_the_text_of_a_loaded_record_is_made_printable_in_place_of_its_layout() -> None:
    """Every text field of a result read from a file is shown on one line,
    whatever field it is, and a record that needs no change is the same object."""
    from dataclasses import dataclass, field

    from reverbscope.cli.console import printable_fields

    @dataclass(frozen=True)
    class Inner:
        note: str | None = None
        level: float = 1.0

    @dataclass(frozen=True)
    class Record:
        label: str = "ok"
        notes: tuple[str, ...] = ()
        inner: Inner = field(default_factory=Inner)
        by_name: dict[str, list[str]] = field(default_factory=dict)

    clean = Record(notes=("a", "b"), by_name={"k": ["v"]})
    assert printable_fields(clean) is clean
    crafted = Record(
        label="x\ny",
        notes=("a", "b\x1b[32m"),
        inner=Inner(note="n\tn", level=2.5),
        by_name={"k": ["v\r"]},
    )
    shown = printable_fields(crafted)
    assert shown == Record(
        label="x\\ny",
        notes=("a", "b\\x1b[32m"),
        inner=Inner(note="n\\tn", level=2.5),
        by_name={"k": ["v\\r"]},
    )
    assert crafted.label == "x\ny"  # the loaded record itself is not touched
    assert printable_fields(7) == 7 and printable_fields(None) is None


# --- The boxed style -----------------------------------------------------------------


def _frame_widths(lines: list[str]) -> set[int]:
    return {cell_width(line) for line in lines}


def test_boxed_title_sections_and_tables_keep_one_width_with_chinese_cells() -> None:
    c = Console(boxed=True, unicode=True, width=50, color=False)
    title = c.title("ReverbScope 分析")
    assert title[0].startswith("╭") and title[-1].startswith("╰")
    assert _frame_widths(title) == {50}
    section = c.section("测量健康", "10 项检查中 10 项良好")
    assert section[0] == "" and section[1].startswith("── 测量健康 ──")
    assert cell_width(section[1]) == 50
    assert section[2].strip() == "10 项检查中 10 项良好"
    table = c.table(["频段", "EDT", "T20"], [["宽带", "0.59 s", "0.53 s"], ["63 Hz", "—", "0.5 s"]])
    assert table[0].strip().startswith("┌") and table[-1].strip().startswith("└")
    assert len(_frame_widths(table)) == 1
    assert "│ 宽带  │" in table[3]


def test_boxed_frames_fall_back_to_ascii_and_to_the_ruled_table_when_too_wide() -> None:
    a = Console(boxed=True, unicode=False, width=40, color=False)
    assert a.title("ReverbScope analysis")[0] == "+" + "-" * 38 + "+"
    assert (
        a.table(["Band", "EDT"], [["Broadband", "0.59 s"]])[0].strip() == "+-----------+--------+"
    )
    # A table that fits only without borders keeps the ruled layout.
    tight = Console(boxed=True, unicode=True, width=30, color=False)
    lines = tight.table(["Band", "EDT", "T20"], [["Broadband", "0.59 s", "0.53 s"]])
    assert not any("┌" in line for line in lines)
    assert lines[2].startswith("  Broadband")
    # Status lines, steps and commands are never framed.
    assert Console(boxed=True, width=50).status("ok", "fine") == ["  ✓ fine"]
    assert (
        Console(boxed=True, width=50)
        .commands([("reverbscope demo", "try")])[0]
        .startswith("  reverbscope demo")
    )


def test_the_style_policy_boxes_only_a_wide_terminal_unless_asked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from reverbscope.cli.console import use_boxes

    env: dict[str, str] = {}
    assert use_boxes("auto", True, 80, env) is True
    assert use_boxes("auto", True, 40, env) is False
    assert use_boxes("auto", False, 100, env) is False  # a pipe stays plain
    assert use_boxes("boxed", False, 100, env) is True
    assert use_boxes("plain", True, 100, env) is False
    assert use_boxes("auto", False, 100, {"REVERBSCOPE_CLI_STYLE": "boxed"}) is True
    assert use_boxes("auto", True, 100, {"REVERBSCOPE_CLI_STYLE": "plain"}) is False
    assert use_boxes("boxed", True, 100, {"REVERBSCOPE_CLI_STYLE": "plain"}) is True
    pipe = Console.for_stream(_Stream(tty=False), environ=env)
    assert pipe.boxed is False
    tty = Console.for_stream(_Stream(tty=True), environ={"COLUMNS": "100"})
    assert tty.boxed is True


def test_style_boxed_frames_a_report_and_leaves_json_alone(
    home: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["--color", "never", "--style", "boxed", "demo", "--out", str(tmp_path / "d")]) == 0
    assert "╭" in capsys.readouterr().out
    assert (
        main(["--color", "never", "--style", "boxed", "show", str(tmp_path / "d" / "position-a")])
        == 0
    )
    out = capsys.readouterr().out
    assert "╭" in out and "┌" in out and "──" in out
    assert (
        main(["--style", "boxed", "--format", "json", "show", str(tmp_path / "d" / "position-a")])
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["decay"]
    assert main(["--style", "plain", "show", str(tmp_path / "d" / "position-a")]) == 0
    assert "╭" not in capsys.readouterr().out


# --- The status badge and the bordered table that wraps one column ---------------------


@pytest.mark.parametrize(
    ("lang", "kind", "shown"),
    [
        ("zh_CN", "ok", "✓ 良好"),
        ("zh_CN", "warn", "! 注意"),
        ("zh_CN", "error", "✗ 问题"),
        ("zh_CN", "info", "i 说明"),
        ("zh_CN", "skip", "– 无数据"),
        ("zh_CN", "unsure", "? 不确定"),
        ("en", "ok", "✓ good"),
        ("en", "warn", "! check"),
        ("en", "error", "✗ problem"),
        ("en", "info", "i note"),
        ("en", "skip", "– no data"),
        ("en", "unsure", "? unsure"),
    ],
)
def test_a_badge_is_the_mark_and_a_word(lang: str, kind: Status, shown: str) -> None:
    """The owner's words: ✓ 良好, ! 注意, ✗ 问题, i 说明; the ASCII forms keep the word."""
    activate(lang)
    try:
        assert Console().badge(kind) == shown
        ascii_badge = Console(unicode=False).badge(kind)
        assert ascii_badge.split(" ", 1)[1] == shown.split(" ", 1)[1]
        assert ascii_badge.isascii() or lang == "zh_CN"
    finally:
        activate("en")


def test_a_badge_has_a_one_column_mark_and_colour_only_on_it() -> None:
    kinds: tuple[Status, ...] = ("ok", "warn", "error", "info", "skip", "unsure")
    for kind in kinds:
        for unicode in (True, False):
            plain = Console(unicode=unicode).badge(kind)
            assert cell_width(plain.split(" ", 1)[0]) == 1, plain
            styled = Console(unicode=unicode, color=True).badge(kind)
            assert strip_ansi(styled) == plain
            mark, word = styled.split(" ", 1)
            assert strip_ansi(mark) == plain.split(" ", 1)[0]
            # The word is bold, never green, yellow or red: those are unreadable
            # on a light background.
            assert word.startswith("\x1b[1m") and not re.search(r"\x1b\[3\dm", word), repr(word)
    assert Console().badge("ok", "已对比") == "✓ 已对比"
    assert Console(unicode=False).badge("error") == "x " + badge_word("error")
    assert Console().badge("next") == "→"  # a step has no word


def test_framed_table_wraps_the_chosen_column_and_expands_it() -> None:
    c = Console(boxed=True, width=40)
    rows = [
        ["a", "✓ good", "a long result that needs two lines or three to fit"],
        ["b", "! check", "short"],
    ]
    table = c.framed_table(["Topic", "Status", "Result"], rows, wrap_column=2, expand=True)
    assert table is not None
    assert {cell_width(line) for line in table} == {40}
    assert sum(line.startswith("  │ a ") for line in table) == 1
    assert sum(line.startswith("  │       │") for line in table) >= 1
    # Without expand the grid is as wide as it needs to be.
    fitted = c.framed_table(["Topic", "Status", "Result"], [["a", "✓ good", "ok"]], wrap_column=2)
    assert fitted is not None and len({cell_width(line) for line in fitted}) == 1
    assert cell_width(fitted[0]) < 40
    # A first column held at a width keeps two tables in step.
    held = c.framed_table(["Topic", "Status"], [["a", "b"]], min_widths=(12,))
    assert held is not None and held[1].startswith("  │ Topic        │")


def test_framed_table_gives_up_instead_of_cutting_a_cell() -> None:
    boxed = Console(boxed=True, width=40)
    assert Console(width=100).framed_table(["a"], [["b"]]) is None  # no frames, no grid
    assert boxed.framed_table(["a", "b"], []) is None
    # A path never wraps.
    path = Verbatim("/a/very/long/path/that/cannot/be/split/into/pieces")
    assert boxed.framed_table(["Folder", "Path"], [["x", path]], wrap_column=1) is None
    # An unbreakable word wider than the column.
    word = "a/very/long/word/wider/than/the/column/of/this/narrow/terminal"
    assert boxed.framed_table(["Folder", "Path"], [["x", word]], wrap_column=1) is None
    # Columns that need more than the console has, whatever wraps.
    tight = Console(boxed=True, width=20)
    assert tight.framed_table(["a", "b", "c"], [["aaaaaaa", "bbbbbbb", "ccccc"]]) is None


def test_framed_table_measures_chinese_cells_in_columns() -> None:
    c = Console(boxed=True, width=44)
    rows = [["混响", "✓ 良好", "RT60 0.70 s，EDT 0.45 s，C50 +9.8 dB，D50 91 %"]]
    table = c.framed_table(["项目", "状态", "结果"], rows, wrap_column=2, expand=True)
    assert table is not None
    assert {cell_width(line) for line in table} == {44}
    assert len(table) > 5  # the Chinese text wrapped between characters


def test_an_ascii_frame_has_no_pipe_inside_a_cell() -> None:
    c = Console(boxed=True, unicode=False, width=60)
    assert c.sep() == " / " and Console(unicode=False).sep() == " | "
    assert c.readable("mean |Δ| 8 dB · x") == "mean abs(delta) 8 dB / x"
    # Without frames the text is as it was.
    assert Console(unicode=False).readable("mean |Δ| 8 dB") == "mean |delta| 8 dB"


def test_a_stream_that_cannot_write_chinese_gets_one_question_mark_per_column() -> None:
    """cp1252 replaces a character with one "?", which left the side of a frame
    short by a column for every Chinese character in the line."""
    framed = Console(boxed=True, unicode=False, encoding="cp1252", width=60)
    assert framed.readable("混响 x") == "???? x"
    assert cell_width(framed.readable("混响 x")) == cell_width("混响 x")
    # GBK writes Chinese: nothing is replaced, and the glue between a number and
    # its unit (a no-break space, which GBK cannot write) is left for fit() to
    # turn into a space, not made a "?".
    gbk = Console(boxed=True, unicode=False, encoding="gbk")
    assert gbk.readable("混响 x") == "混响 x"
    assert gbk.readable("RT60 0.70\u00a0s") == "RT60 0.70\u00a0s"
    assert gbk.fit(gbk.readable("RT60 0.70\u00a0s")) == "RT60 0.70 s"
    # Without frames the text is as it was.
    assert Console(unicode=False, encoding="cp1252").readable("混响 x") == "混响 x"
