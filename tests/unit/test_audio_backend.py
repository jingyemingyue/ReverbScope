"""Fake audio backend: progress, Stop, and a two-channel loopback capture."""

from __future__ import annotations

import threading

import numpy as np
import pytest

from reverbscope.audio.backend import CALLBACK_BLOCK, get_backend
from reverbscope.audio.fake import FakeBackend, make_rir
from reverbscope.core.sweep import measurement_signal
from reverbscope.errors import ConfigurationError, MeasurementCancelledError
from reverbscope.models.audio import AudioSignal
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
        loopback_input=2,
    )
    assert recording.n_channels == 2
    mic = recording.channel(0)
    loop = recording.channel(1)
    # The electrical return is much shorter than the room channel.
    assert float(np.max(np.abs(loop))) > 0.0
    assert float(np.sqrt(np.mean(mic**2))) != pytest.approx(float(np.sqrt(np.mean(loop**2))))


def test_only_the_declared_fake_loopback_input_carries_the_cable(
    short_sweep: SweepSettings,
) -> None:
    """Review findings: every fake input from 2 to 8 was the noiseless
    loopback (a Demo microphone on input 3 analysed a cable: RT60 0.07 s,
    "exact digital silence"), then only input 2 was, so a microphone on input
    2 still analysed the cable and a loopback on input 3 stopped working. The
    cable is on the input the caller declares, and on no other."""

    def take(channels: list[int], loopback_input: int | None) -> AudioSignal:
        return FakeBackend().play_and_record(
            measurement_signal(short_sweep),
            short_sweep.sample_rate,
            input_device=0,
            output_device=0,
            input_channels=channels,
            output_channel=1,
            level_dbfs=-12.0,
            loopback_input=loopback_input,
        )

    declared_on_3 = take([1, 2, 3, 8], 3)
    room = declared_on_3.channel(0)
    cable = declared_on_3.channel(2)
    assert not np.array_equal(room, cable)
    for column in (1, 3):
        np.testing.assert_array_equal(declared_on_3.channel(column), room)
    # Input 2 is a microphone like any other when nothing is wired to it, and
    # with no loopback declared there is no cable at all.
    mic_on_2 = take([2], None)
    np.testing.assert_array_equal(mic_on_2.channel(0), room)
    assert np.array_equal(take([1, 3], None).channel(1), room)
    # The declaration moves the cable with it.
    np.testing.assert_array_equal(take([2, 3], 2).channel(0), cable)
    np.testing.assert_array_equal(take([2, 3], 2).channel(1), room)


def test_the_fake_loopback_arrives_before_the_microphone(short_sweep: SweepSettings) -> None:
    """The default room had its direct sound at t = 0 while the loopback was
    delayed by the interface: every Demo take with a loopback reported
    "path delay -2.00 ms", which no electrical return can produce."""
    from reverbscope.core.pipeline import Reference, analyze
    from reverbscope.models.configuration import AnalysisSettings

    take = FakeBackend().play_and_record(
        measurement_signal(short_sweep),
        short_sweep.sample_rate,
        input_device=0,
        output_device=0,
        input_channels=[1, 2],
        output_channel=1,
        level_dbfs=-12.0,
        loopback_input=2,
    )
    result = analyze(
        take, Reference.from_settings(short_sweep), AnalysisSettings(loopback_channel=1)
    )
    loopback = result.impulse_response.loopback
    assert loopback is not None and loopback.compensation_applied
    assert loopback.path_delay_ms == pytest.approx(4.0, abs=0.1)
    assert loopback.distance_upper_bound_m is not None


def test_a_nan_level_is_refused_before_playback() -> None:
    from reverbscope.audio.backend import scale_to_level

    with pytest.raises(ConfigurationError):
        scale_to_level(np.ones(8), float("nan"))
    with pytest.raises(ConfigurationError):
        scale_to_level(np.array([0.0, np.nan]), -12.0)


@pytest.mark.parametrize(("inputs", "output"), [([9], 1), ([1], 3)])
def test_the_fake_device_has_the_channels_it_advertises(
    short_sweep: SweepSettings, inputs: list[int], output: int
) -> None:
    from reverbscope.errors import AudioDeviceError

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
    from reverbscope.audio.inventory import check_channels

    devices = FakeBackend().list_devices()
    with pytest.raises(ConfigurationError, match="1-based"):
        check_channels(
            devices, input_device=0, output_device=0, input_channels=[1], output_channel=0
        )
