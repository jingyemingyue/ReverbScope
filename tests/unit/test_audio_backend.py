"""Fake audio backend: progress, Stop, and a two-channel loopback capture."""

from __future__ import annotations

import threading

import numpy as np
import pytest

from roomscope.audio.backend import CALLBACK_BLOCK, get_backend
from roomscope.audio.fake import FakeBackend, make_rir
from roomscope.core.sweep import measurement_signal
from roomscope.errors import ConfigurationError, MeasurementCancelledError
from roomscope.models.configuration import SweepSettings


def test_get_backend_fake_and_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ROOMSCOPE_AUDIO_BACKEND", "fake")
    backend = get_backend()
    assert backend.name == "fake"
    monkeypatch.delenv("ROOMSCOPE_AUDIO_BACKEND")
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


def test_the_fake_loopback_arrives_before_the_microphone(short_sweep: SweepSettings) -> None:
    """The default room had its direct sound at t = 0 while the loopback was
    delayed by the interface: every Demo take with a loopback reported
    "path delay -2.00 ms", which no electrical return can produce."""
    from roomscope.core.pipeline import Reference, analyze
    from roomscope.models.configuration import AnalysisSettings

    take = FakeBackend().play_and_record(
        measurement_signal(short_sweep),
        short_sweep.sample_rate,
        input_device=0,
        output_device=0,
        input_channels=[1, 2],
        output_channel=1,
        level_dbfs=-12.0,
    )
    result = analyze(
        take, Reference.from_settings(short_sweep), AnalysisSettings(loopback_channel=1)
    )
    loopback = result.impulse_response.loopback
    assert loopback is not None and loopback.compensation_applied
    assert loopback.path_delay_ms == pytest.approx(4.0, abs=0.1)
    assert loopback.distance_upper_bound_m is not None


def test_a_nan_level_is_refused_before_playback() -> None:
    from roomscope.audio.backend import scale_to_level

    with pytest.raises(ConfigurationError):
        scale_to_level(np.ones(8), float("nan"))
    with pytest.raises(ConfigurationError):
        scale_to_level(np.array([0.0, np.nan]), -12.0)


@pytest.mark.parametrize(("inputs", "output"), [([9], 1), ([1], 3)])
def test_the_fake_device_has_the_channels_it_advertises(
    short_sweep: SweepSettings, inputs: list[int], output: int
) -> None:
    from roomscope.errors import AudioDeviceError

    with pytest.raises(AudioDeviceError, match="does not exist"):
        FakeBackend().play_and_record(
            measurement_signal(short_sweep),
            short_sweep.sample_rate,
            input_device=0,
            output_device=0,
            input_channels=inputs,
            output_channel=output,
            level_dbfs=-20.0,
        )


def test_preflight_refuses_channel_zero_before_anything_is_played() -> None:
    from roomscope.audio.inventory import check_channels

    devices = FakeBackend().list_devices()
    with pytest.raises(ConfigurationError, match="1-based"):
        check_channels(
            devices, input_device=0, output_device=0, input_channels=[1], output_channel=0
        )
