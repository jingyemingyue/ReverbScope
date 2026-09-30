"""PortAudio backend callback logic against a scripted ``sounddevice`` stand-in (#13).

The stand-in runs the stream callback on its own thread in fixed blocks, the
way PortAudio does, and follows sounddevice's rules: ``CallbackStop`` ends the
stream after the current block, ``CallbackAbort`` ends it at once, any other
exception aborts it (sounddevice only prints it) and the finished callback
fires in every case. No audio device is involved; this is not hardware
evidence (docs/HARDWARE_TESTS.md).
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

from roomscope.audio import portaudio
from roomscope.audio.backend import CALLBACK_BLOCK, plan_input_channels
from roomscope.audio.portaudio import PortAudioBackend
from roomscope.errors import AudioDeviceError, ConfigurationError, MeasurementCancelledError


class _CallbackStop(Exception):  # noqa: N818 - mirrors sounddevice.CallbackStop
    pass


class _CallbackAbort(Exception):  # noqa: N818 - mirrors sounddevice.CallbackAbort
    pass


@dataclass
class _Script:
    """What the stand-in device does, block by block."""

    block_sleep_s: float = 0.002
    #: Hand ``None`` as ``indata`` in this block, so the callback raises.
    fail_at_block: int | None = None
    #: The device stops on its own after this many blocks (unplugged).
    stop_after_blocks: int | None = None
    #: The device stalls after this many blocks: no callback, no finish.
    stall_after_blocks: int | None = None
    #: PortAudio status string per block index.
    status: dict[int, str] = field(default_factory=dict)
    #: Delay between the last callback and the finished callback (PortAudio
    #: drains the output buffers first).
    finish_delay_s: float = 0.0
    outputs: list[np.ndarray] = field(default_factory=list)
    stream_thread: list[int] = field(default_factory=list)
    aborted: list[bool] = field(default_factory=list)


def _input_block(start: int, frames: int, channels: int) -> np.ndarray:
    """Channel c carries ``(c + 1) * 1e-6 * frame_index`` so the mapping is visible."""
    index = np.arange(start, start + frames, dtype=np.float64)[:, None]
    scale = (np.arange(channels, dtype=np.float64)[None, :] + 1.0) * 1e-6
    return np.asarray(index * scale, dtype=np.float32)


def _fake_sounddevice(script: _Script) -> SimpleNamespace:
    class Stream:
        def __init__(
            self,
            *,
            samplerate: int,
            channels: tuple[int, int],
            dtype: str,
            device: object,
            blocksize: int,
            callback: Callable[..., None],
            finished_callback: Callable[[], None],
        ) -> None:
            del samplerate, dtype, device
            self.n_in, self.n_out = channels
            self.blocksize = blocksize
            self.callback = callback
            self.finished_callback = finished_callback
            self.closed = threading.Event()
            self.thread = threading.Thread(target=self._run, daemon=True)

        def _run(self) -> None:
            script.stream_thread.append(threading.get_ident())
            frame = 0
            block = 0
            try:
                while True:
                    if script.stall_after_blocks is not None and block >= script.stall_after_blocks:
                        self.closed.wait(timeout=30.0)
                        break
                    indata: Any = _input_block(frame, self.blocksize, self.n_in)
                    if script.fail_at_block == block:
                        indata = None
                    outdata = np.full((self.blocksize, self.n_out), 0.5, dtype=np.float32)
                    try:
                        self.callback(
                            indata, outdata, self.blocksize, None, script.status.get(block, "")
                        )
                    except _CallbackStop:
                        script.outputs.append(outdata.copy())
                        break
                    except _CallbackAbort:
                        script.outputs.append(outdata.copy())
                        script.aborted.append(True)
                        break
                    except Exception:
                        # sounddevice's cffi callback returns paAbort on error.
                        script.outputs.append(outdata.copy())
                        script.aborted.append(True)
                        break
                    script.outputs.append(outdata.copy())
                    frame += self.blocksize
                    block += 1
                    if script.stop_after_blocks is not None and block >= script.stop_after_blocks:
                        break
                    time.sleep(script.block_sleep_s)
            finally:
                time.sleep(script.finish_delay_s)
                self.finished_callback()

        def __enter__(self) -> Stream:
            self.thread.start()
            return self

        def __exit__(self, *_exc: object) -> None:
            self.closed.set()
            self.thread.join(timeout=10.0)

    return SimpleNamespace(Stream=Stream, CallbackStop=_CallbackStop, CallbackAbort=_CallbackAbort)


@pytest.fixture
def script(monkeypatch: pytest.MonkeyPatch) -> _Script:
    current = _Script()
    monkeypatch.setattr(portaudio, "sounddevice_module", lambda: _fake_sounddevice(current))
    return current


def _take(
    frames: int = 60 * CALLBACK_BLOCK,
    *,
    input_channels: tuple[int, ...] = (1,),
    progress: Callable[[float], None] | None = None,
    cancel: threading.Event | None = None,
):
    rng = np.random.default_rng(0)
    return PortAudioBackend().play_and_record(
        rng.normal(0.0, 0.1, frames),
        48000,
        input_device=None,
        output_device=None,
        input_channels=list(input_channels),
        output_channel=1,
        level_dbfs=-20.0,
        progress=progress,
        cancel=cancel,
    )


def test_progress_is_reported_from_the_waiting_thread(script: _Script) -> None:
    calls: list[tuple[int, float]] = []
    recording = _take(progress=lambda f: calls.append((threading.get_ident(), f)))
    assert calls, "no progress was reported"
    stream_thread = script.stream_thread[0]
    assert {ident for ident, _ in calls} == {threading.get_ident()}
    assert stream_thread not in {ident for ident, _ in calls}
    fractions = [f for _, f in calls]
    assert fractions == sorted(fractions)
    assert fractions[-1] == 1.0
    assert recording.n_samples == 60 * CALLBACK_BLOCK


def test_input_channels_are_mapped_by_their_1_based_number(script: _Script) -> None:
    recording = _take(input_channels=(3, 1))
    assert recording.n_channels == 2
    expected = _input_block(0, 60 * CALLBACK_BLOCK, 3).astype(np.float64)
    np.testing.assert_allclose(recording.channel(0), expected[:, 2])
    np.testing.assert_allclose(recording.channel(1), expected[:, 0])
    # No block kept the stand-in device's garbage (0.5) in the output.
    assert all(np.all(block[:, 0] != 0.5) for block in script.outputs)


def test_an_exception_in_the_callback_fails_the_take(script: _Script) -> None:
    script.fail_at_block = 5
    with pytest.raises(AudioDeviceError, match="audio callback") as info:
        _take()
    assert isinstance(info.value.__cause__, TypeError)
    assert script.aborted == [True]
    # The failing block was silenced before the error, not left with garbage.
    assert np.max(np.abs(script.outputs[-1])) == 0.0


def test_a_stream_that_ends_early_is_not_returned_as_a_recording(script: _Script) -> None:
    script.stop_after_blocks = 4
    with pytest.raises(AudioDeviceError, match="ended after"):
        _take()


def test_stop_silences_the_next_block_and_raises_cancelled(script: _Script) -> None:
    cancel = threading.Event()

    def progress(fraction: float) -> None:
        if fraction > 0.2:
            cancel.set()

    with pytest.raises(MeasurementCancelledError):
        _take(frames=400 * CALLBACK_BLOCK, progress=progress, cancel=cancel)
    assert len(script.outputs) < 400
    assert np.max(np.abs(script.outputs[-1])) == 0.0


def test_stop_on_a_stalled_device_does_not_wait_for_the_timeout(script: _Script) -> None:
    """A device that stops calling back must not make Stop wait for the whole
    sweep plus the timeout margin, nor turn into a device error."""
    script.stall_after_blocks = 3
    cancel = threading.Event()
    threading.Timer(0.1, cancel.set).start()
    started = time.monotonic()
    with pytest.raises(MeasurementCancelledError):
        _take(frames=48000 * 10, cancel=cancel)
    assert time.monotonic() - started < 3.0


def test_a_failing_final_progress_report_keeps_the_take(
    script: _Script, caplog: pytest.LogCaptureFixture
) -> None:
    def progress(fraction: float) -> None:
        if fraction >= 1.0:
            raise RuntimeError("window already closed")

    with caplog.at_level(logging.WARNING, logger="roomscope.audio.portaudio"):
        recording = _take(progress=progress)
    assert recording.n_samples == 60 * CALLBACK_BLOCK
    assert any("progress callback failed" in r.getMessage() for r in caplog.records)


def test_progress_at_100_percent_before_the_stream_finishes_keeps_the_take(
    script: _Script, caplog: pytest.LogCaptureFixture
) -> None:
    """CI #58 (macOS): the last block sets the position to 100 % before
    PortAudio calls the finished callback (it drains the output first). A poll
    in that gap reported 1.0 inside the stream loop, the failing progress
    callback escaped and the complete take was discarded."""
    from roomscope.audio.portaudio import PROGRESS_POLL_S

    script.finish_delay_s = 4 * PROGRESS_POLL_S
    calls: list[float] = []

    def progress(fraction: float) -> None:
        calls.append(fraction)
        if fraction >= 1.0:
            raise RuntimeError("window already closed")

    with caplog.at_level(logging.WARNING, logger="roomscope.audio.portaudio"):
        recording = _take(progress=progress)
    assert recording.n_samples == 60 * CALLBACK_BLOCK
    assert 1.0 in calls
    failures = [r for r in caplog.records if "progress callback failed" in r.getMessage()]
    assert len(failures) == 1  # logged once, not at every poll


def test_a_progress_callback_failing_mid_take_does_not_stop_it(script: _Script) -> None:
    def progress(fraction: float) -> None:
        raise RuntimeError("the display went away")

    assert _take(progress=progress).n_samples == 60 * CALLBACK_BLOCK


def test_buffer_problems_are_logged_and_kept_with_the_take(
    script: _Script, caplog: pytest.LogCaptureFixture
) -> None:
    script.status = {2: "input overflow", 7: "input overflow"}
    with caplog.at_level(logging.WARNING, logger="roomscope.audio.portaudio"):
        recording = _take()
    assert any("2 buffer problem(s)" in r.getMessage() for r in caplog.records)
    assert any("input overflow" in r.getMessage() for r in caplog.records)
    # Not only a log line: the analysis and the GUI see it (a finding).
    (warning,) = recording.device_warnings
    assert "2 buffer problem(s)" in warning and "input overflow" in warning


def test_a_clean_take_has_no_device_warnings(script: _Script) -> None:
    assert _take().device_warnings == ()


@pytest.mark.parametrize(
    ("channels", "loopback", "recorded", "mic", "analysis", "analysis_loopback"),
    [
        ([1], None, (1,), 1, 0, None),
        ([1], 2, (1, 2), 1, 0, 1),
        ([2, 1], 2, (2, 1), 1, 1, 0),
        ([3, 4], 4, (3, 4), 3, 0, 1),
    ],
)
def test_channel_plan_maps_1_based_inputs_to_0_based_columns(
    channels: list[int],
    loopback: int | None,
    recorded: tuple[int, ...],
    mic: int,
    analysis: int,
    analysis_loopback: int | None,
) -> None:
    plan = plan_input_channels(channels, loopback)
    assert plan.input_channels == recorded
    assert plan.microphone_channel == mic
    assert plan.loopback_channel == loopback
    assert plan.analysis_channel == analysis
    assert plan.analysis_loopback_channel == analysis_loopback


@pytest.mark.parametrize(
    ("channels", "loopback", "message"),
    [
        ([1], 1, "both the microphone and the loopback"),
        ([0], None, "1-based"),
        ([1, 1], None, "once"),
        ([1], 0, "1-based"),
        ([], None, "at least one"),
    ],
)
def test_channel_plan_refuses_bad_inputs(
    channels: list[int], loopback: int | None, message: str
) -> None:
    with pytest.raises(ConfigurationError, match=message):
        plan_input_channels(channels, loopback)


def test_cli_refuses_a_loopback_on_the_microphone_input_before_playing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from roomscope.cli.main import main

    out = tmp_path / "take"
    code = main(
        [
            "--backend",
            "fake",
            "measure",
            "--out",
            str(out),
            "--duration",
            "2",
            "--level",
            "-20",
            "--input-channel",
            "1",
            "--loopback-channel",
            "1",
        ]
    )
    captured = capsys.readouterr()
    assert code != 0
    assert "both the microphone and the loopback" in captured.err
    assert "Playing sweep" not in captured.out
    assert not (out / "recording.wav").exists()


def test_cli_session_stores_1_based_hardware_channels(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    import json

    from roomscope.cli.main import main

    out = tmp_path / "take"
    code = main(
        [
            "--backend",
            "fake",
            "measure",
            "--out",
            str(out),
            "--duration",
            "2",
            "--post-silence",
            "1.5",
            "--level",
            "-20",
            "--input-channels",
            "2,1",
            "--loopback-channel",
            "2",
            "--output-channel",
            "1",
        ]
    )
    assert code == 0, capsys.readouterr().err
    session = json.loads((out / "session.json").read_text(encoding="utf-8"))
    assert session["input_channel"] == 1
    assert session["loopback_channel"] == 2
    assert session["output_channel"] == 1
    assert session["analysis_settings"]["channel"] == 1
    assert session["analysis_settings"]["loopback_channel"] == 0


def test_cli_daw_mode_session_leaves_hardware_channels_empty(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    import json

    from scipy.signal import fftconvolve

    from roomscope.cli.main import main
    from roomscope.io.wav import read_wav, write_wav
    from tests.conftest import make_rir

    sweep = tmp_path / "sweep.wav"
    assert main(["sweep", "--out", str(sweep), "--duration", "2", "--post-silence", "1.5"]) == 0
    signal = read_wav(sweep)
    ir = make_rir(signal.sample_rate, rt60_s=0.3, diffuse_level=0.02)
    rec = fftconvolve(signal.samples, ir)[: signal.n_samples + ir.shape[0]]
    recording = write_wav(tmp_path / "recording.wav", rec, signal.sample_rate, subtype="FLOAT")
    out = tmp_path / "session"
    code = main(
        ["analyze", "--recording", str(recording), "--sweep", str(sweep), "--out", str(out)]
    )
    assert code == 0, capsys.readouterr().err
    session = json.loads((out / "session.json").read_text(encoding="utf-8"))
    assert session["input_channel"] is None
    assert session["loopback_channel"] is None
    # The analysed WAV column (0-based) is recorded by the analysis instead.
    result = json.loads((out / "result.json").read_text(encoding="utf-8"))
    assert result["analysis_settings"]["channel_analysed"] == 0
