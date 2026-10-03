"""PortAudio backend: callback stream with progress and immediate Stop.

The real-time callback only copies samples and advances a frame counter. It
never calls back into the front end: progress is reported from the waiting
thread, which polls the counter (a print to stderr or a Qt signal emitted from
the audio thread can block it long enough to drop samples). An exception in
the callback aborts the stream, is kept, and is re-raised from the waiting
thread, so a failed take is never returned as a recording. PortAudio's
under/overflow flags are counted and logged.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable, Sequence
from typing import Any

import numpy as np

from reverbscope.audio.backend import CALLBACK_BLOCK, DeviceInfo, StreamOptions, prepare_playback
from reverbscope.audio.devices import check_sample_rate, list_devices, sounddevice_module
from reverbscope.errors import AudioDeviceError, ConfigurationError, MeasurementCancelledError
from reverbscope.i18n import _, diag
from reverbscope.models.audio import AudioSignal, FloatArray

log = logging.getLogger(__name__)

#: How often the waiting thread reports progress (s).
PROGRESS_POLL_S = 0.05
#: Extra time allowed beyond the signal duration before the take times out (s).
TIMEOUT_MARGIN_S = 5.0
#: After Stop, how long to wait for the stream's next callback before giving
#: up on a stalled device (s).
CANCEL_GRACE_S = 0.5


def device_host_api(sd: Any, device: int | None, kind: str) -> str | None:
    """PortAudio host API name of ``device`` (or of the default ``kind`` device)."""
    try:
        if device is None:
            device = int(sd.default.device[0 if kind == "input" else 1])
            if device < 0:
                return None
        info = sd.query_devices(device)
        return str(sd.query_hostapis(int(info["hostapi"]))["name"])
    except Exception:
        return None


def host_api_settings(sd: Any, device: int | None, kind: str, options: StreamOptions) -> Any:
    """The sounddevice extra-settings object for ``options`` on this device's host API.

    ``WasapiSettings(exclusive)`` and
    ``CoreAudioSettings(change_device_parameters, fail_if_conversion_required)``
    are python-sounddevice's wrappers of PortAudio's ``paWinWasapiExclusive`` and
    ``paMacCoreChangeDeviceParameters`` /
    ``paMacCoreFailIfConversionRequired`` flags (pa_win_wasapi.h, pa_mac_core.h;
    docs/AUDIO_DEVICES.md).
    """
    api = device_host_api(sd, device, kind)
    if api == "Windows WASAPI" and options.wasapi_exclusive:
        return sd.WasapiSettings(exclusive=True)
    if api == "Core Audio" and options.coreaudio_change_device_rate:
        # Set the device's nominal rate, and fail rather than convert when the
        # device cannot run at it (paMacCoreChangeDeviceParameters |
        # paMacCoreFailIfConversionRequired).
        return sd.CoreAudioSettings(change_device_parameters=True, fail_if_conversion_required=True)
    return None


class PortAudioBackend:
    """sounddevice / PortAudio implementation of :class:`AudioBackend`."""

    name = "portaudio"

    def list_devices(self) -> list[DeviceInfo]:
        return list_devices()

    def check_sample_rate(
        self,
        device: int,
        sample_rate: int,
        *,
        kind: str,
        channels: int | None = None,
        options: StreamOptions | None = None,
    ) -> None:
        # Ask with the stream's host-API settings: WASAPI exclusive mode accepts
        # rates the shared-mode engine refuses (docs/AUDIO_DEVICES.md).
        extra = None
        if options is not None and not options.is_default:
            extra = host_api_settings(sounddevice_module(), device, kind, options)
        check_sample_rate(device, sample_rate, kind=kind, channels=channels, extra_settings=extra)

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
        if not input_channels:
            raise ConfigurationError(_("at least one input channel is required"))
        if any(ch < 1 for ch in input_channels) or output_channel < 1:
            raise ConfigurationError(_("channels are 1-based and must be >= 1"))
        sd = sounddevice_module()
        signal = prepare_playback(playback, sample_rate, level_dbfs, extra_record_s)
        n_in = max(input_channels)
        n_out = output_channel
        frames_total = int(signal.shape[0])
        recorded = np.zeros((frames_total, len(input_channels)), dtype=np.float64)
        # Written by the audio thread only; read by this thread (a Python int
        # assignment is atomic under the GIL).
        position = [0]
        finished = threading.Event()
        callback_error: list[BaseException] = []
        xruns: list[str] = []

        def callback(
            indata: np.ndarray,
            outdata: np.ndarray,
            frames: int,
            _time: object,
            status: object,
        ) -> None:
            # Silence first: Stop must zero the output in this callback period.
            outdata.fill(0)
            if cancel is not None and cancel.is_set():
                raise sd.CallbackStop
            try:
                if status:
                    xruns.append(str(status))
                play_idx = position[0]
                remaining = frames_total - play_idx
                if remaining <= 0:
                    raise sd.CallbackStop
                n = min(frames, remaining)
                outdata[:n, output_channel - 1] = signal[play_idx : play_idx + n]
                for i, channel in enumerate(input_channels):
                    recorded[play_idx : play_idx + n, i] = np.asarray(
                        indata[:n, channel - 1], dtype=np.float64
                    )
                position[0] = play_idx + n
            except (sd.CallbackStop, sd.CallbackAbort):
                raise
            except BaseException as exc:
                # Keep the error for the waiting thread and abort the stream;
                # an exception escaping the callback would only be printed.
                outdata.fill(0)
                callback_error.append(exc)
                raise sd.CallbackAbort from exc
            if position[0] >= frames_total:
                raise sd.CallbackStop

        def on_finished() -> None:
            finished.set()

        progress_failed: list[bool] = []

        def report(fraction: float) -> None:
            # A front end that cannot show progress (a window already closed)
            # must neither stop nor discard the take. The last block reaches
            # 100 % before PortAudio calls the finished callback (it drains
            # the output first), so 1.0 can be reported inside the loop too.
            if progress is None or progress_failed:
                return
            try:
                progress(min(1.0, fraction))
            except Exception:
                progress_failed.append(True)
                log.warning("the progress callback failed; the take goes on", exc_info=True)

        # Only an explicit option changes what is passed to PortAudio, so the
        # default take is opened exactly as before.
        stream_kwargs: dict[str, object] = {}
        if options is not None and not options.is_default:
            if options.latency is not None:
                stream_kwargs["latency"] = options.latency
            extra = (
                host_api_settings(sd, input_device, "input", options),
                host_api_settings(sd, output_device, "output", options),
            )
            if any(setting is not None for setting in extra):
                stream_kwargs["extra_settings"] = extra
        try:
            with sd.Stream(
                samplerate=sample_rate,
                channels=(n_in, n_out),
                dtype="float32",
                device=(input_device, output_device),
                blocksize=CALLBACK_BLOCK,
                callback=callback,
                finished_callback=on_finished,
                **stream_kwargs,
            ):
                deadline = time.monotonic() + frames_total / max(sample_rate, 1) + TIMEOUT_MARGIN_S
                cancelled_at: float | None = None
                while not finished.wait(timeout=PROGRESS_POLL_S):
                    report(position[0] / frames_total)
                    now = time.monotonic()
                    if cancel is not None and cancel.is_set():
                        # The next callback stops the stream; if the device
                        # has stalled and no callback comes, stop waiting.
                        cancelled_at = now if cancelled_at is None else cancelled_at
                        if now - cancelled_at > CANCEL_GRACE_S:
                            raise MeasurementCancelledError(_("measurement stopped"))
                    if now > deadline:
                        raise AudioDeviceError(_("playback/recording timed out"))
        except MeasurementCancelledError:
            raise
        except AudioDeviceError:
            if cancel is not None and cancel.is_set():
                raise MeasurementCancelledError(_("measurement stopped")) from None
            raise
        except Exception as exc:
            if cancel is not None and cancel.is_set():
                raise MeasurementCancelledError(_("measurement stopped")) from exc
            raise AudioDeviceError(
                _("playback/recording failed: {error}").format(error=exc)
            ) from exc
        if callback_error:
            raise AudioDeviceError(
                _("playback/recording failed in the audio callback: {error}").format(
                    error=repr(callback_error[0])
                )
            ) from callback_error[0]
        if cancel is not None and cancel.is_set():
            raise MeasurementCancelledError(_("measurement stopped"))
        if position[0] < frames_total:
            raise AudioDeviceError(
                _("the audio stream ended after {done} of {total} frames").format(
                    done=position[0], total=frames_total
                )
            )
        device_warnings: tuple[str, ...] = ()
        if xruns:
            # PortAudio's status flags: an input overflow drops recorded
            # samples, an output underflow inserts a gap in the sweep. Either
            # breaks the sweep's timing that deconvolution relies on.
            device_warnings = (
                diag(
                    "the audio device reported {count} buffer problem(s) during the take "
                    "({flags}); the recording may contain dropouts",
                    count=len(xruns),
                    flags="; ".join(sorted(set(xruns))),
                ),
            )
            log.warning("%s; measure again if the result looks wrong", device_warnings[0])
        report(1.0)
        samples = recorded[:, 0] if len(input_channels) == 1 else recorded
        return AudioSignal(
            samples=np.ascontiguousarray(samples),
            sample_rate=sample_rate,
            source="standalone",
            device_warnings=device_warnings,
        )
