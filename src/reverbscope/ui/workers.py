"""Worker threads so that analysis and playback never block the UI."""

from __future__ import annotations

import logging
import threading
from collections.abc import Sequence

from PySide6.QtCore import QThread, Signal

from reverbscope.audio.backend import StreamOptions
from reverbscope.core.pipeline import Reference, analyze
from reverbscope.errors import MeasurementCancelledError, ReverbScopeError
from reverbscope.i18n import _, localize
from reverbscope.models.audio import AudioSignal, FloatArray
from reverbscope.models.configuration import AnalysisSettings

log = logging.getLogger(__name__)


def unexpected_error_text() -> str:
    """What the GUI says when a bug escapes.

    The traceback is for the log (the caller writes it). The dialog stays in
    the interface language, with no exception class name and no English sentence.
    """
    return _(
        "Something unexpected went wrong. This is a bug in ReverbScope. "
        "The details were written to the log; the environment report in the Help "
        "menu shows where that log is. Include both in a bug report."
    )


def gui_failure_text(exc: BaseException) -> str:
    """A dialog sentence for an exception that reached the GUI thread."""
    if isinstance(exc, ReverbScopeError):
        return localize(str(exc))
    return unexpected_error_text()


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
        except ReverbScopeError as exc:
            self.failed.emit(localize(str(exc)))
        except Exception:
            log.exception("analysis failed unexpectedly")
            self.failed.emit(unexpected_error_text())
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
        from reverbscope.audio.backend import get_backend

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
        except ReverbScopeError as exc:
            self.failed.emit(localize(str(exc)))
        except Exception:
            log.exception("measurement failed unexpectedly")
            self.failed.emit(unexpected_error_text())
        else:
            self.succeeded.emit(recording)
