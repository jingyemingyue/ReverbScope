"""Flow control of a measurement: the worker threads, the state generation
a run belongs to, and what happens to a result that arrives late.

The pages (``daw_page``, ``standalone_page``) own the widgets; these
controllers own the threads. A page starts a run under the generation it
claimed from the shared :class:`~reverbscope.ui.state.MeasurementState`,
and a result that comes back under another generation (New Measurement,
Open Session or another page's take meanwhile) is dropped, never shown.
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
from reverbscope.ui.state import MeasurementState
from reverbscope.ui.workers import AnalysisWorker, MeasureWorker, unexpected_error_text

log = logging.getLogger(__name__)


def late_result_text() -> str:
    """Shown on a mode page whose take or analysis ended after the user moved on.

    Not after any page switch: a visit to Compare or Settings keeps the result,
    which then opens Results. Only a reset (New Measurement, Open Session) or a
    measurement another page started meanwhile makes the result late.
    """
    return _(
        "The result was discarded: a new measurement or another session replaced it "
        "before it was ready."
    )


def safe_findings(result: AnalysisResult, profile: str) -> tuple[list[Finding], str]:
    """The findings for ``result``, or none and the reason why.

    A recording profile that fails (a third-party one from an entry point)
    must not stop the result from being shown: the page stayed busy for good
    and the measurement was never seen.
    """
    try:
        return interpret(result, profile), ""
    except ReverbScopeError as exc:
        return [], localize(str(exc))
    except Exception:
        log.exception("recording profile %r failed to interpret the result", profile)
        return [], unexpected_error_text()


def accept_result(state: MeasurementState, result: AnalysisResult) -> None:
    """Put ``result`` and its findings into the shared state (the page checked
    first that the run is not stale)."""
    findings, problem = safe_findings(result, state.profile)
    state.result = result
    state.findings = findings
    state.findings_problem = problem


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
    """One analysis thread at a time for a page, bound to a state generation.

    :attr:`succeeded` fires with the result; the page checks :meth:`stale`
    and calls :func:`accept_result`, so a test can drive the page's slot
    directly. :attr:`failed` carries the message in the interface language.
    """

    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, state: MeasurementState, page: QWidget) -> None:
        super().__init__(page)
        self._state = state
        self._page = page
        self.worker: AnalysisWorker | None = None
        self.generation = -1

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
        generation: int,
        loopback: AudioSignal | None = None,
        blocking: bool = False,
    ) -> None:
        """Analyse ``recording`` under ``generation`` (the one the page claimed)."""
        if self.is_running():
            # A second worker would drop the only reference to the running
            # one, and Qt aborts the process when a QThread is destroyed
            # while it runs.
            return
        self.generation = generation
        self.worker = AnalysisWorker(recording, reference, settings, loopback=loopback)
        self.worker.succeeded.connect(self._on_success)
        self.worker.failed.connect(self._on_failure)
        if blocking:
            self.worker.run()
        else:
            self.worker.start()

    def stale(self) -> bool:
        """The result that arrives now belongs to a session that is gone.

        The shared state was reset (New Measurement, Open Session) or taken by
        a measurement another page started since this one began, or the
        window is closed. A visit to Compare or Settings meanwhile is not
        that: the result is kept and opens Results.
        """
        return self.generation != self._state.generation or not self._page.window().isVisible()

    def _on_success(self, result: AnalysisResult) -> None:
        self.succeeded.emit(result)

    def _on_failure(self, message: str) -> None:
        self.failed.emit(message)


class TakeRun(QObject):
    """One take (play and record) at a time, with Stop."""

    recorded = Signal(object)
    failed = Signal(str)
    stopped = Signal()
    progress = Signal(float)

    def __init__(self, page: QWidget) -> None:
        super().__init__(page)
        self.worker: MeasureWorker | None = None

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
        self.worker.succeeded.connect(self.recorded.emit)
        self.worker.failed.connect(self.failed.emit)
        self.worker.progress.connect(self.progress.emit)
        self.worker.stopped.connect(self.stopped.emit)
        self.worker.start()
