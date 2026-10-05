"""Audio-backend protocol, device record and backend selection.

``core`` never imports this module. Front ends call :func:`get_backend` so
Standalone Mode can run against PortAudio or the synthetic ``fake`` backend.
"""

from __future__ import annotations

import os
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Protocol

import numpy as np

from reverbscope.errors import ConfigurationError
from reverbscope.i18n import N_, _
from reverbscope.models.audio import AudioSignal, FloatArray
from reverbscope.models.configuration import SUPPORTED_SAMPLE_RATES

#: Shown before every Standalone measurement; front ends translate it with ``_()``.
SAFETY_MESSAGE = N_(
    "Start with your monitor/interface output at a low level. ReverbScope will play a "
    "sine sweep at a conservative digital level; raise the level gradually between "
    "measurements only if the recording is too quiet."
)
#: Levels above this need an explicit acknowledgement in the front end.
SAFE_MAX_LEVEL_DBFS = -12.0
DEFAULT_STANDALONE_LEVEL_DBFS = -20.0
#: Block size used by the fake backend and as the PortAudio callback period
#: that Stop must silence within.
CALLBACK_BLOCK = 256
ENV_BACKEND = "REVERBSCOPE_AUDIO_BACKEND"


@dataclass(frozen=True)
class DeviceInfo:
    index: int
    name: str
    host_api: str
    max_input_channels: int
    max_output_channels: int
    default_sample_rate: float
    is_default_input: bool
    is_default_output: bool
    #: PortAudio's host API index (``None`` for backends without host APIs).
    host_api_index: int | None = None
    #: PortAudio's default latencies (s) for interactive / robust streams.
    default_low_input_latency_s: float | None = None
    default_high_input_latency_s: float | None = None
    default_low_output_latency_s: float | None = None
    default_high_output_latency_s: float | None = None

    @property
    def is_input(self) -> bool:
        return self.max_input_channels > 0

    @property
    def is_output(self) -> bool:
        return self.max_output_channels > 0


@dataclass(frozen=True)
class StreamOptions:
    """Host-API options for a Standalone take (docs/AUDIO_DEVICES.md).

    The defaults leave PortAudio's choices alone. ``latency`` is ``"low"`` or
    ``"high"`` (PortAudio's default low / high latency of the device; high is
    sounddevice's default and "typically more robust"). ``wasapi_exclusive``
    opens a Windows WASAPI device in exclusive mode: no audio engine, no
    mixing or conversion, the requested rate or a refusal.
    ``coreaudio_change_device_rate`` lets PortAudio set a macOS device's
    nominal rate and refuse to convert instead. Options that do not match the
    selected device's host API are ignored. WASAPI's auto-convert flag is
    deliberately not offered: it inserts the engine's sample-rate converter,
    which a measurement path must not contain (docs/AUDIO_DEVICES.md).
    """

    latency: str | None = None
    wasapi_exclusive: bool = False
    coreaudio_change_device_rate: bool = False

    def __post_init__(self) -> None:
        if self.latency not in (None, "low", "high"):
            raise ConfigurationError(_("latency must be 'low' or 'high'"))

    @property
    def is_default(self) -> bool:
        return self == StreamOptions()


class AudioBackend(Protocol):
    """Play a sweep and record one or more input channels."""

    name: str

    def list_devices(self) -> list[DeviceInfo]: ...

    def check_sample_rate(
        self,
        device: int,
        sample_rate: int,
        *,
        kind: str,
        channels: int | None = None,
        options: StreamOptions | None = None,
    ) -> None: ...

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
    ) -> AudioSignal: ...


@dataclass(frozen=True)
class ChannelPlan:
    """How Standalone Mode's hardware inputs map onto the analysed recording.

    Two conventions meet here and must not be mixed: hardware channels of the
    interface are **1-based** (what the user reads on the front panel and what
    ``MeasurementSession.input_channel`` / ``loopback_channel`` store), columns
    of the recorded signal are **0-based** (``AnalysisSettings.channel`` /
    ``loopback_channel``).
    """

    #: 1-based hardware input channels to record, in recording-column order.
    input_channels: tuple[int, ...]
    #: 1-based hardware channel of the microphone that is analysed.
    microphone_channel: int
    #: 1-based hardware channel of the electrical loopback, or ``None``.
    loopback_channel: int | None
    #: 0-based recording column of the microphone (``AnalysisSettings.channel``).
    analysis_channel: int
    #: 0-based recording column of the loopback (``AnalysisSettings.loopback_channel``).
    analysis_loopback_channel: int | None


def plan_input_channels(
    channels: Sequence[int], loopback_channel: int | None = None
) -> ChannelPlan:
    """Validate the requested inputs *before* anything is played.

    ``channels`` are the 1-based hardware inputs to record (the first one that
    is not the loopback is the analysed microphone); ``loopback_channel`` is
    the 1-based input that carries the electrical return, recorded as an extra
    column when it is not already listed.
    """
    requested = [int(ch) for ch in channels]
    if not requested:
        raise ConfigurationError(_("at least one input channel is required"))
    if any(ch < 1 for ch in requested):
        raise ConfigurationError(_("input channels are 1-based and must be >= 1"))
    if len(set(requested)) != len(requested):
        raise ConfigurationError(_("each input channel may be listed once"))
    if loopback_channel is not None:
        loopback_channel = int(loopback_channel)
        if loopback_channel < 1:
            raise ConfigurationError(_("the loopback channel is 1-based and must be >= 1"))
        if loopback_channel not in requested:
            requested.append(loopback_channel)
    microphones = [ch for ch in requested if ch != loopback_channel]
    if not microphones:
        raise ConfigurationError(
            _(
                "input {channel} cannot be both the microphone and the loopback; "
                "record the loopback on a different input"
            ).format(channel=loopback_channel)
        )
    microphone = microphones[0]
    return ChannelPlan(
        input_channels=tuple(requested),
        microphone_channel=microphone,
        loopback_channel=loopback_channel,
        analysis_channel=requested.index(microphone),
        analysis_loopback_channel=(
            None if loopback_channel is None else requested.index(loopback_channel)
        ),
    )


def scale_to_level(signal: FloatArray, level_dbfs: float) -> FloatArray:
    """Return ``signal`` peak-normalised to ``level_dbfs``."""
    if level_dbfs > 0.0:
        raise ConfigurationError(_("playback level must be <= 0 dBFS"))
    peak = float(np.max(np.abs(signal)))
    if peak <= 0.0:
        raise ConfigurationError(_("signal is silent"))
    scale = float(10.0 ** (level_dbfs / 20.0) / peak)
    return np.asarray(np.asarray(signal, dtype=np.float64) * scale, dtype=np.float64)


def prepare_playback(
    signal: FloatArray, sample_rate: int, level_dbfs: float, extra_record_s: float
) -> FloatArray:
    """Peak-normalise and optionally pad trailing silence."""
    playback = scale_to_level(signal, level_dbfs)
    if extra_record_s > 0.0:
        playback = np.concatenate(
            [playback, np.zeros(int(extra_record_s * sample_rate), dtype=np.float64)]
        )
    return np.asarray(playback, dtype=np.float64)


def get_backend(name: str | None = None) -> AudioBackend:
    """Return the named backend, settings, ``REVERBSCOPE_AUDIO_BACKEND``, or PortAudio."""
    chosen = name or os.environ.get(ENV_BACKEND)
    if not chosen:
        try:
            from reverbscope.settings import load_settings

            chosen = load_settings().audio_backend
        except Exception:
            chosen = ""
    chosen = (chosen or "portaudio").strip().lower()
    if chosen == "fake":
        from reverbscope.audio.fake import FakeBackend

        return FakeBackend()
    if chosen in {"portaudio", "sounddevice"}:
        from reverbscope.audio.portaudio import PortAudioBackend

        return PortAudioBackend()
    raise ConfigurationError(
        _("unknown audio backend {name}; available: portaudio, fake").format(name=repr(chosen))
    )


def supported_sample_rate(sample_rate: int) -> None:
    if sample_rate not in SUPPORTED_SAMPLE_RATES:
        raise ConfigurationError(
            _("sample rate {rate} Hz is not in {supported}").format(
                rate=sample_rate, supported=SUPPORTED_SAMPLE_RATES
            )
        )
