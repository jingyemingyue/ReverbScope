"""Flow control of a measurement: the worker threads and what happens to a
result that arrives late.

:class:`~reverbscope.ui.measurement_controller.MeasurementController` owns
the threads through these two runners. A run is started under a *job* the
controller numbers; a result that comes back for a job that is no longer
the current one (the user stopped it, or the window closed) is dropped,
never shown.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import QMessageBox, QWidget

from reverbscope.audio.backend import StreamOptions
from reverbscope.core.pipeline import Reference
from reverbscope.errors import ReverbScopeError
from reverbscope.i18n import _, localize
from reverbscope.interpretation import Finding, interpret
from reverbscope.models.audio import AudioSignal, FloatArray
from reverbscope.models.configuration import AnalysisSettings
from reverbscope.models.result import AnalysisResult
from reverbscope.ui.workers import AnalysisWorker, MeasureWorker, unexpected_error_text

log = logging.getLogger(__name__)


def late_result_text() -> str:
    """Shown in the status line when a take or analysis ended after it was
    stopped or the window was closed: nothing is added to the workbench."""
    return _("The result was discarded: the measurement was stopped before it was ready.")


def safe_findings(result: AnalysisResult, profile: str) -> tuple[list[Finding], str]:
    """The findings for ``result``, or none and the reason why.

    A recording profile that fails (a third-party one from an entry point)
    must not stop the result from being shown.
    """
    try:
        return interpret(result, profile), ""
    except ReverbScopeError as exc:
        return [], localize(str(exc))
    except Exception:
        log.exception("recording profile %r failed to interpret the result", profile)
        return [], unexpected_error_text()


def separate_clocks_box(parent: QWidget, warning: str) -> QMessageBox:
    """Two devices, two clocks. The safe button is the default: do not measure."""
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Warning)
    box.setWindowTitle(_("Two devices, two clocks"))
    box.setText(localize(warning))
    box.setInformativeText(_("Measure anyway?"))
    box.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    box.addButton(_("Measure anyway"), QMessageBox.ButtonRole.AcceptRole)
    cancel = box.addButton(_("Cancel"), QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(cancel)
    box.setEscapeButton(cancel)
    return box


def ask_separate_clocks(parent: QWidget, warning: str) -> bool:
    box = separate_clocks_box(parent, warning)
    box.exec()
    clicked = box.clickedButton()
    # By role, not by label: some desktops insert "&" accelerators into it.
    return clicked is not None and box.buttonRole(clicked) == QMessageBox.ButtonRole.AcceptRole


class AnalysisRun(QObject):
    """One analysis thread at a time, bound to a job number.

    :attr:`succeeded` fires with the result and the job it belongs to; the
    controller decides whether that job is still current. :attr:`failed`
    carries the message in the interface language and the job.
    """

    succeeded = Signal(object, int)
    failed = Signal(str, int)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.worker: AnalysisWorker | None = None
        self.job = -1

    def is_running(self) -> bool:
        return self.worker is not None and self.worker.isRunning()

    def wait(self) -> None:
        """Let a running analysis finish: a QThread destroyed while it runs aborts."""
        if self.worker is not None:
            self.worker.wait()

    def start(
        self,
        recording: AudioSignal,
        reference: Reference,
        settings: AnalysisSettings,
        *,
        job: int,
        loopback: AudioSignal | None = None,
        blocking: bool = False,
    ) -> None:
        """Analyse ``recording`` for ``job``."""
        if self.is_running():
            # A second worker would drop the only reference to the running
            # one, and Qt aborts the process when a QThread is destroyed
            # while it runs.
            return
        self.job = job
        self.worker = AnalysisWorker(recording, reference, settings, loopback=loopback)
        self.worker.succeeded.connect(self._on_success)
        self.worker.failed.connect(self._on_failure)
        if blocking:
            self.worker.run()
        else:
            self.worker.start()

    def _on_success(self, result: AnalysisResult) -> None:
        self.succeeded.emit(result, self.job)

    def _on_failure(self, message: str) -> None:
        self.failed.emit(message, self.job)


class TakeRun(QObject):
    """One take (play and record) at a time, with Stop."""

    recorded = Signal(object, int)
    failed = Signal(str, int)
    stopped = Signal(int)
    progress = Signal(float)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.worker: MeasureWorker | None = None
        self.job = -1

    def is_running(self) -> bool:
        return self.worker is not None and self.worker.isRunning()

    def request_stop(self) -> None:
        if self.worker is not None:
            self.worker.request_stop()

    def wait(self) -> None:
        if self.worker is not None:
            self.worker.wait()

    def start(
        self,
        signal: FloatArray,
        sample_rate: int,
        *,
        job: int,
        input_device: int | None,
        output_device: int | None,
        input_channels: Sequence[int],
        output_channel: int,
        level_dbfs: float,
        backend: str | None,
        options: StreamOptions,
        loopback_channel: int | None,
    ) -> None:
        if self.is_running():
            return
        self.job = job
        self.worker = MeasureWorker(
            signal,
            sample_rate,
            input_device=input_device,
            output_device=output_device,
            input_channels=list(input_channels),
            output_channel=output_channel,
            level_dbfs=level_dbfs,
            backend=backend,
            options=options,
            loopback_channel=loopback_channel,
        )
        self.worker.succeeded.connect(self._on_recorded)
        self.worker.failed.connect(self._on_failure)
        self.worker.progress.connect(self.progress.emit)
        self.worker.stopped.connect(self._on_stopped)
        self.worker.start()

    def _on_recorded(self, recording: AudioSignal) -> None:
        self.recorded.emit(recording, self.job)

    def _on_failure(self, message: str) -> None:
        self.failed.emit(message, self.job)

    def _on_stopped(self) -> None:
        self.stopped.emit(self.job)
