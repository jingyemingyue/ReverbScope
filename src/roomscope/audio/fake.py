"""Synthetic-room backend for tests and the GUI Demo mode.

``make_rir`` lives here so the package does not import ``tests``. The fake
backend convolves the playback with a configured room impulse response, honours
``progress`` and ``cancel``, and can emit a second channel that is an electrical
loopback of the playback.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

import numpy as np
from scipy.signal import fftconvolve

from roomscope.audio.backend import (
    CALLBACK_BLOCK,
    DeviceInfo,
    StreamOptions,
    prepare_playback,
    supported_sample_rate,
)
from roomscope.errors import AudioDeviceError, ConfigurationError, MeasurementCancelledError
from roomscope.i18n import _
from roomscope.models.audio import AudioSignal, FloatArray

DECAY_CONSTANT = 3.0 * np.log(10.0) * 2.0


def make_rir(
    sample_rate: int,
    *,
    rt60_s: float = 0.5,
    length_s: float | None = None,
    direct: float = 1.0,
    reflections: Sequence[tuple[float, float]] = (),
    diffuse_level: float = 0.02,
    seed: int = 0,
    start_delay_s: float = 0.0,
) -> FloatArray:
    """Synthetic room impulse response.

    ``direct`` impulse at ``start_delay_s``, discrete ``reflections`` as
    ``(delay_s, linear_gain)`` relative to the direct sound, and a Gaussian
    diffuse tail whose energy decays 60 dB in ``rt60_s``.
    """
    length = length_s if length_s is not None else max(1.0, 1.6 * rt60_s)
    n = int(length * sample_rate)
    t = np.arange(n) / sample_rate
    rng = np.random.default_rng(seed)
    d0 = round(start_delay_s * sample_rate)
    tail = np.zeros(n)
    if diffuse_level > 0.0:
        envelope = np.exp(-DECAY_CONSTANT * np.maximum(t - t[d0], 0.0) / (2.0 * rt60_s))
        envelope[:d0] = 0.0
        tail = rng.normal(0.0, 1.0, n) * envelope * diffuse_level
    ir = tail
    ir[d0] += direct
    for delay_s, gain in reflections:
        idx = d0 + round(delay_s * sample_rate)
        if idx < n:
            ir[idx] += direct * gain
    return np.asarray(ir, dtype=np.float64)


@dataclass
class FakeBackend:
    """In-process backend: no devices, no PortAudio, immediate Stop."""

    name: str = "fake"
    rir: FloatArray | None = None
    interface_ir: FloatArray | None = None
    loopback_delay_s: float = 0.002
    #: Loudspeaker-to-microphone delay of the default room (about 1.4 m). The
    #: microphone also goes through the interface, so it hears the sweep
    #: ``loopback_delay_s + acoustic_delay_s`` after it was played, never
    #: before the loopback does. An explicit ``rir`` keeps its own timing.
    acoustic_delay_s: float = 0.004
    noise_rms: float = 1e-5
    rt60_s: float = 0.4
    seed: int = 0
    #: Last output block after a cancel (tests assert it is silence).
    last_output_block: FloatArray = field(default_factory=lambda: np.zeros(0))
    cancelled: bool = False

    def list_devices(self) -> list[DeviceInfo]:
        return [
            DeviceInfo(
                index=0,
                name="RoomScope fake interface",
                host_api="fake",
                max_input_channels=8,
                max_output_channels=2,
                default_sample_rate=48000.0,
                is_default_input=True,
                is_default_output=True,
            )
        ]

    def check_sample_rate(
        self,
        device: int,
        sample_rate: int,
        *,
        kind: str,
        channels: int | None = None,
        options: StreamOptions | None = None,
    ) -> None:
        del channels, options
        if kind not in {"input", "output"}:
            raise ConfigurationError(_("kind must be 'input' or 'output'"))
        if device != 0:
            raise AudioDeviceError(_("fake backend has no device {device}").format(device=device))
        supported_sample_rate(sample_rate)

    def play_and_record(
        self,
        playback: FloatArray,
        sample_rate: int,
        *,
        input_device: int | None,
        output_device: int | None,
        input_channels: Sequence[int],
        output_channel: int,
        level_dbfs: float,
        extra_record_s: float = 0.0,
        progress: Callable[[float], None] | None = None,
        cancel: threading.Event | None = None,
        options: StreamOptions | None = None,
    ) -> AudioSignal:
        del options  # the synthetic backend has no host API
        if not input_channels:
            raise ConfigurationError(_("at least one input channel is required"))
        if any(ch < 1 for ch in input_channels) or output_channel < 1:
            raise ConfigurationError(_("channels are 1-based and must be >= 1"))
        if input_device not in (None, 0) or output_device not in (None, 0):
            raise AudioDeviceError(_("fake backend only has device 0"))
        # The channels it advertises, as a real device would check them.
        device = self.list_devices()[0]
        for channel in input_channels:
            if channel > device.max_input_channels:
                raise AudioDeviceError(
                    _(
                        "input channel {channel} does not exist on {device} "
                        "({count} input channel(s))"
                    ).format(channel=channel, device=device.name, count=device.max_input_channels)
                )
        if output_channel > device.max_output_channels:
            raise AudioDeviceError(
                _(
                    "output channel {channel} does not exist on {device} "
                    "({count} output channel(s))"
                ).format(
                    channel=output_channel, device=device.name, count=device.max_output_channels
                )
            )
        supported_sample_rate(sample_rate)
        signal = prepare_playback(playback, sample_rate, level_dbfs, extra_record_s)
        room = (
            self.rir
            if self.rir is not None
            else make_rir(
                sample_rate,
                rt60_s=self.rt60_s,
                seed=self.seed,
                start_delay_s=self.loopback_delay_s + self.acoustic_delay_s,
            )
        )
        mic = np.asarray(
            fftconvolve(signal, room, mode="full")[: signal.shape[0]], dtype=np.float64
        )
        if self.noise_rms > 0.0:
            rng = np.random.default_rng(self.seed + 1)
            mic = mic + rng.normal(0.0, self.noise_rms, mic.shape[0])
        delay = max(0, round(self.loopback_delay_s * sample_rate))
        loop = np.zeros_like(signal)
        delayed = (
            signal
            if self.interface_ir is None
            else np.asarray(
                fftconvolve(signal, self.interface_ir, mode="full")[: signal.shape[0]],
                dtype=np.float64,
            )
        )
        loop[delay:] = delayed[: delayed.shape[0] - delay] if delay else delayed

        n_ch = len(input_channels)
        recorded = np.zeros((signal.shape[0], n_ch), dtype=np.float64)
        for i, channel in enumerate(input_channels):
            recorded[:, i] = loop if channel >= 2 else mic

        n = signal.shape[0]
        for start in range(0, n, CALLBACK_BLOCK):
            if cancel is not None and cancel.is_set():
                self.last_output_block = np.zeros(min(CALLBACK_BLOCK, n - start), dtype=np.float64)
                self.cancelled = True
                raise MeasurementCancelledError(_("measurement stopped"))
            self.last_output_block = np.asarray(
                signal[start : start + CALLBACK_BLOCK], dtype=np.float64
            )
            if progress is not None:
                progress(min(1.0, (start + CALLBACK_BLOCK) / n))
        self.cancelled = False
        samples = recorded[:, 0] if n_ch == 1 else recorded
        return AudioSignal(
            samples=np.ascontiguousarray(samples),
            sample_rate=sample_rate,
            source="fake",
        )
