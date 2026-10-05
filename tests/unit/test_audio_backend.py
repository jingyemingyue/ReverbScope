"""Fake audio backend: progress, Stop, and a two-channel loopback capture."""

from __future__ import annotations

import threading

import numpy as np
import pytest

from reverbscope.audio.backend import CALLBACK_BLOCK, get_backend
from reverbscope.audio.fake import FakeBackend, make_rir
from reverbscope.core.sweep import measurement_signal
from reverbscope.errors import ConfigurationError, MeasurementCancelledError
from reverbscope.models.configuration import SweepSettings


def test_get_backend_fake_and_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REVERBSCOPE_AUDIO_BACKEND", "fake")
    backend = get_backend()
    assert backend.name == "fake"
    monkeypatch.delenv("REVERBSCOPE_AUDIO_BACKEND")
    named = get_backend("fake")
    assert named.name == "fake"
    with pytest.raises(ConfigurationError, match="unknown"):
        get_backend("asio")


def test_fake_lists_a_device_and_rejects_bad_rate() -> None:
    backend = FakeBackend()
    devices = backend.list_devices()
    assert devices and devices[0].is_input and devices[0].is_output
    backend.check_sample_rate(0, 48000, kind="input")
    with pytest.raises(ConfigurationError):
        backend.check_sample_rate(0, 32000, kind="input")


def test_fake_play_and_record_progress(short_sweep: SweepSettings) -> None:
    backend = FakeBackend(rir=make_rir(short_sweep.sample_rate, rt60_s=0.3, diffuse_level=0.01))
    seen: list[float] = []
    recording = backend.play_and_record(
        measurement_signal(short_sweep),
        short_sweep.sample_rate,
        input_device=None,
        output_device=None,
        input_channels=[1],
        output_channel=1,
        level_dbfs=-20.0,
        progress=seen.append,
    )
    assert recording.n_channels == 1
    assert recording.n_samples > 0
    assert seen
    assert seen[-1] == pytest.approx(1.0)
    assert all(0.0 < p <= 1.0 for p in seen)


def test_fake_stop_silences_within_one_callback(short_sweep: SweepSettings) -> None:
    backend = FakeBackend()
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(MeasurementCancelledError):
        backend.play_and_record(
            measurement_signal(short_sweep),
            short_sweep.sample_rate,
            input_device=None,
            output_device=None,
            input_channels=[1],
            output_channel=1,
            level_dbfs=-20.0,
            cancel=cancel,
        )
    assert backend.cancelled is True
    assert backend.last_output_block.shape[0] <= CALLBACK_BLOCK
    assert np.max(np.abs(backend.last_output_block)) == 0.0


def test_fake_two_channel_loopback_capture(short_sweep: SweepSettings) -> None:
    backend = FakeBackend(
        rir=make_rir(short_sweep.sample_rate, rt60_s=0.3),
        loopback_delay_s=0.003,
    )
    recording = backend.play_and_record(
        measurement_signal(short_sweep),
        short_sweep.sample_rate,
        input_device=None,
        output_device=None,
        input_channels=[1, 2],
        output_channel=1,
        level_dbfs=-20.0,
    )
    assert recording.n_channels == 2
    mic = recording.channel(0)
    loop = recording.channel(1)
    # The electrical return is much shorter than the room channel.
    assert float(np.max(np.abs(loop))) > 0.0
    assert float(np.sqrt(np.mean(mic**2))) != pytest.approx(float(np.sqrt(np.mean(loop**2))))
