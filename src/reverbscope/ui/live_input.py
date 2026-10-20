"""Live input for the level meter and spectrum: a ring buffer and its sources.

The measurement backend (:mod:`reverbscope.audio.portaudio`) plays a sweep
and records it in one stream; it has no "just listen" call, and the
analysis path stays untouched. The live monitor therefore opens its own
*input-only* stream with the library the backend already uses
(python-sounddevice, through :func:`reverbscope.audio.devices.sounddevice_module`
and the same host-API options), on the device the Connection step chose.
It is a display: nothing it reads is stored or analysed.

As in the backend, the audio callback only copies samples into a ring
buffer and advances a counter; it never calls into Qt. The GUI reads the
buffer from a timer (single producer, single consumer, no lock in the
callback). The stream is closed before a take starts, so the monitor never
competes with the measurement for the device.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Protocol

import numpy as np

from reverbscope.audio.backend import CALLBACK_BLOCK, StreamOptions
from reverbscope.errors import ReverbScopeError
from reverbscope.i18n import _
from reverbscope.models.audio import FloatArray

log = logging.getLogger(__name__)

#: What went wrong when the input could not be opened; each has its own sentence.
ERROR_NO_DEVICE = "no_device"
ERROR_PERMISSION = "permission"
ERROR_BUSY = "busy"
ERROR_UNAVAILABLE = "unavailable"
ERROR_OTHER = "other"


class LiveInputError(ReverbScopeError):
    """The live input could not be opened or stopped working."""

    def __init__(self, kind: str, detail: str = "") -> None:
        self.kind = kind
        self.detail = detail
        super().__init__(f"{kind}: {detail}")

    def text(self) -> str:
        """What the panel shows: what happened and what to do, in the interface language."""
        if self.kind == ERROR_NO_DEVICE:
            return _("No input device is available. Choose one in the Connection step.")
        if self.kind == ERROR_PERMISSION:
            return _(
                "ReverbScope may not use the microphone. Allow microphone access for "
                "ReverbScope in the system settings, then resume."
            )
        if self.kind == ERROR_BUSY:
            return _(
                "The input device is busy: another program or an exclusive-mode stream is using it."
            )
        if self.kind == ERROR_UNAVAILABLE:
            return _("The audio backend is not available, so the input cannot be shown.")
        return _("The input could not be opened: {error}").format(error=self.detail)


def classify_error(exc: BaseException) -> str:
    """Sort a PortAudio / sounddevice error into one of the ``ERROR_*`` kinds."""
    from reverbscope.errors import AudioBackendUnavailableError

    if isinstance(exc, AudioBackendUnavailableError):
        return ERROR_UNAVAILABLE
    text = str(exc).lower()
    if any(
        key in text
        for key in (
            "permission",
            "not permitted",
            "access denied",
            "not authorized",
            "authorization",
        )
    ):
        return ERROR_PERMISSION
    if any(
        key in text
        for key in (
            "busy",
            "in use",
            "device unavailable",
            "-9985",
            "exclusive",
            "resource temporarily unavailable",
        )
    ):
        return ERROR_BUSY
    if any(
        key in text
        for key in (
            "no default input",
            "invalid device",
            "error querying device -1",
            "no such device",
            "-9996",
            "invalid number of channels",
            "-9998",
        )
    ):
        return ERROR_NO_DEVICE
    return ERROR_OTHER


class RingBuffer:
    """Single-producer, single-consumer sample buffer (frames x channels, float32).

    The producer (the audio callback) writes a block and then advances
    :attr:`written`; the consumer reads the newest frames. A Python int
    assignment is atomic under the GIL, and the buffer holds far more than one
    GUI frame, so the region read is never the one being written.
    """

    def __init__(self, capacity: int, channels: int) -> None:
        self.capacity = max(1, int(capacity))
        self.channels = max(1, int(channels))
        self._data = np.zeros((self.capacity, self.channels), dtype=np.float32)
        #: Frames written since the start (monotonic).
        self.written = 0

    def write(self, block: np.ndarray) -> None:
        frames = int(block.shape[0])
        if frames == 0:
            return
        if frames >= self.capacity:
            block = block[-self.capacity :]
            frames = self.capacity
        start = self.written % self.capacity
        first = min(frames, self.capacity - start)
        self._data[start : start + first] = block[:first]
        if first < frames:
            self._data[: frames - first] = block[first:]
        self.written += frames

    def latest(
        self,
        frames: int,
        *,
        upto: int | None = None,
        out: np.ndarray | None = None,
    ) -> FloatArray:
        """The newest ``frames`` frames up to ``upto`` (default: all written).

        Zeros pad the front when fewer frames have been written. Uses the same
        two-slice copy as :meth:`write` (no ``arange`` of indices). Pass an
        ``out`` array of shape ``(frames, channels)`` to reuse a buffer; the
        result is float32 like the ring.
        """
        end = self.written if upto is None else int(upto)
        frames = max(0, min(int(frames), self.capacity))
        if out is None or out.shape != (frames, self.channels) or out.dtype != np.float32:
            out = np.zeros((frames, self.channels), dtype=np.float32)
        available = min(frames, end)
        if available < frames:
            out[: frames - available] = 0.0
        if available <= 0:
            return out
        start = end - available
        dest = frames - available
        index = start % self.capacity
        first = min(available, self.capacity - index)
        out[dest : dest + first] = self._data[index : index + first]
        if first < available:
            out[dest + first : dest + available] = self._data[: available - first]
        return out


class InputSource(Protocol):
    """Something that fills a :class:`RingBuffer` with live input."""

    sample_rate: int
    channels: int
    #: Synthetic samples (Demo, tests, screenshots): the panel says so (C9).
    synthetic: bool

    def start(self, ring: RingBuffer) -> None: ...

    def stop(self) -> None: ...

    def failure(self) -> LiveInputError | None: ...


class SoundDeviceInput:
    """An input-only sounddevice stream on the device and channels the page chose."""

    synthetic = False

    def __init__(
        self,
        device: int | None,
        input_channels: list[int],
        sample_rate: int,
        options: StreamOptions | None = None,
    ) -> None:
        self.device = device
        #: 1-based hardware inputs, as on the interface's front panel.
        self.input_channels = [int(ch) for ch in input_channels] or [1]
        self.channels = len(self.input_channels)
        self.sample_rate = int(sample_rate)
        self.options = options
        self._stream: Any = None
        self._error: LiveInputError | None = None
        self.overflows = 0

    def start(self, ring: RingBuffer) -> None:
        from reverbscope.audio.devices import sounddevice_module
        from reverbscope.audio.portaudio import host_api_settings

        try:
            sd = sounddevice_module()
        except ReverbScopeError as exc:
            raise LiveInputError(ERROR_UNAVAILABLE, str(exc)) from exc
        columns = [ch - 1 for ch in self.input_channels]
        wanted = max(self.input_channels)

        def callback(indata: np.ndarray, frames: int, _time: object, status: object) -> None:
            # Copy and count only (as the measurement backend's callback).
            if status:
                self.overflows += 1
            ring.write(indata[:frames, columns])

        kwargs: dict[str, object] = {}
        if self.options is not None and not self.options.is_default:
            if self.options.latency is not None:
                kwargs["latency"] = self.options.latency
            extra = host_api_settings(sd, self.device, "input", self.options)
            if extra is not None:
                kwargs["extra_settings"] = extra
        try:
            stream = sd.InputStream(
                samplerate=self.sample_rate,
                device=self.device,
                channels=wanted,
                dtype="float32",
                blocksize=CALLBACK_BLOCK,
                callback=callback,
                **kwargs,
            )
            stream.start()
        except Exception as exc:
            raise LiveInputError(classify_error(exc), str(exc)) from exc
        self._stream = stream
        log.info(
            "live input: device=%s channels=%s rate=%s",
            self.device,
            self.input_channels,
            self.sample_rate,
        )

    def stop(self) -> None:
        stream, self._stream = self._stream, None
        if stream is None:
            return
        try:
            stream.abort()
        except Exception:
            log.debug("live input: abort failed", exc_info=True)
        try:
            stream.close()
        except Exception:
            log.debug("live input: close failed", exc_info=True)

    def failure(self) -> LiveInputError | None:
        stream = self._stream
        if self._error is None and stream is not None and not getattr(stream, "active", True):
            self._error = LiveInputError(ERROR_OTHER, _("the input stream stopped"))
        return self._error


#: The synthetic input: pink noise and a few tones, all in dBFS.
SYNTHETIC_NOISE_RMS_DBFS = -30.0
SYNTHETIC_TONES: tuple[tuple[float, float], ...] = (
    (100.0, -24.0),
    (1000.0, -18.0),
    (6300.0, -30.0),
)


class SyntheticInput:
    """Pink noise plus tones at a real-time pace, for Demo mode, tests and screenshots.

    ``threaded=False`` produces nothing on its own: a test calls :meth:`pump`
    to feed an exact number of frames, so the lifecycle and the readings are
    deterministic.
    """

    synthetic = True

    def __init__(
        self,
        sample_rate: int = 48000,
        channels: int = 1,
        *,
        noise_rms_dbfs: float = SYNTHETIC_NOISE_RMS_DBFS,
        tones: tuple[tuple[float, float], ...] = SYNTHETIC_TONES,
        threaded: bool = True,
        seed: int = 7,
        block: int = 512,
    ) -> None:
        from scipy.signal import lfilter_zi

        from reverbscope.display.live import pink_noise_filter

        self.sample_rate = int(sample_rate)
        self.channels = max(1, int(channels))
        self.noise_rms_dbfs = noise_rms_dbfs
        self.tones = tones
        self.threaded = threaded
        self.block = int(block)
        self._rng = np.random.default_rng(seed)
        self._b, self._a = pink_noise_filter()
        self._zi = np.asarray(lfilter_zi(self._b, self._a), dtype=np.float64) * 0.0
        self._phase = 0
        self._ring: RingBuffer | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self.running = False

    def start(self, ring: RingBuffer) -> None:
        self._ring = ring
        self._stop.clear()
        self.running = True
        if self.threaded:
            self._thread = threading.Thread(target=self._run, name="live-synthetic", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        thread, self._thread = self._thread, None
        if thread is not None:
            thread.join(timeout=1.0)
        self.running = False

    def failure(self) -> LiveInputError | None:
        return None

    def generate(self, frames: int) -> np.ndarray:
        from scipy.signal import lfilter

        white = self._rng.standard_normal(frames)
        pink, self._zi = lfilter(self._b, self._a, white, zi=self._zi)
        # The economy filter's gain is about -12.6 dB on white noise of unit
        # RMS; scale to the requested RMS measured over the block.
        rms = float(np.sqrt(np.mean(pink * pink))) or 1.0
        signal = np.asarray(pink, dtype=np.float64) * (10.0 ** (self.noise_rms_dbfs / 20.0) / rms)
        t = (self._phase + np.arange(frames)) / self.sample_rate
        for hz, dbfs in self.tones:
            if hz < 0.5 * self.sample_rate:
                signal = signal + 10.0 ** (dbfs / 20.0) * np.sin(2.0 * np.pi * hz * t)
        self._phase += frames
        out = np.repeat(signal[:, None], self.channels, axis=1)
        # A second channel (the loopback) sits 6 dB lower so the meters differ.
        if self.channels > 1:
            out[:, 1:] *= 0.5
        return np.asarray(out, dtype=np.float32)

    def pump(self, frames: int) -> None:
        """Write ``frames`` frames now (tests; also used by the thread)."""
        ring = self._ring
        if ring is None or not self.running:
            return
        remaining = int(frames)
        while remaining > 0:
            n = min(remaining, self.block)
            ring.write(self.generate(n))
            remaining -= n

    def _run(self) -> None:
        period = self.block / float(self.sample_rate)
        next_at = time.monotonic()
        while not self._stop.is_set():
            self.pump(self.block)
            next_at += period
            delay = next_at - time.monotonic()
            if delay > 0:
                self._stop.wait(delay)
            else:
                next_at = time.monotonic()
