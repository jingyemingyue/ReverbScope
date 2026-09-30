"""Worker threads so that analysis and playback never block the UI."""

from __future__ import annotations

import threading
from collections.abc import Sequence

from PySide6.QtCore import QThread, Signal

from roomscope.audio.backend import StreamOptions
from roomscope.core.pipeline import Reference, analyze
from roomscope.errors import MeasurementCancelledError, RoomScopeError
from roomscope.i18n import localize
from roomscope.models.audio import AudioSignal, FloatArray
from roomscope.models.configuration import AnalysisSettings


class AnalysisWorker(QThread):
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        recording: AudioSignal,
        reference: Reference,
        settings: AnalysisSettings,
        *,
        loopback: AudioSignal | None = None,
    ) -> None:
        super().__init__()
        self._recording = recording
        self._reference = reference
        self._settings = settings
        self._loopback = loopback

    def run(self) -> None:
        try:
            result = analyze(
                self._recording, self._reference, self._settings, loopback=self._loopback
            )
        except RoomScopeError as exc:
            self.failed.emit(localize(str(exc)))
        except Exception as exc:
            self.failed.emit(f"unexpected error: {exc!r}")
        else:
            self.succeeded.emit(result)


class MeasureWorker(QThread):
    succeeded = Signal(object)
    failed = Signal(str)
    progress = Signal(float)
    stopped = Signal()

    def __init__(
        self,
        signal: FloatArray,
        sample_rate: int,
        *,
        input_device: int | None,
        output_device: int | None,
        input_channels: Sequence[int],
        output_channel: int,
        level_dbfs: float,
        backend: str | None = None,
        options: StreamOptions | None = None,
    ) -> None:
        super().__init__()
        self._options = options
        self._signal = signal
        self._sample_rate = sample_rate
        self._input_device = input_device
        self._output_device = output_device
        self._input_channels = list(input_channels)
        self._output_channel = output_channel
        self._level_dbfs = level_dbfs
        self._backend = backend
        self._cancel = threading.Event()

    def request_stop(self) -> None:
        self._cancel.set()

    def run(self) -> None:
        from roomscope.audio.backend import get_backend

        try:
            recording = get_backend(self._backend).play_and_record(
                self._signal,
                self._sample_rate,
                input_device=self._input_device,
                output_device=self._output_device,
                input_channels=self._input_channels,
                output_channel=self._output_channel,
                level_dbfs=self._level_dbfs,
                progress=self.progress.emit,
                cancel=self._cancel,
                options=self._options,
            )
        except MeasurementCancelledError:
            self.stopped.emit()
        except RoomScopeError as exc:
            self.failed.emit(localize(str(exc)))
        except Exception as exc:
            self.failed.emit(f"unexpected error: {exc!r}")
        else:
            self.succeeded.emit(recording)
