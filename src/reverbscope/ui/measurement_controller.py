"""The measurement controller: runs a take or an analysis as a numbered job
and puts the finished measurement into the workspace document.

A job has its own identity: the measurement it produces is added as a new
entry, whatever the user selected meanwhile, and a result that arrives
after Stop or after the window closed is dropped. Only one job runs at a
time; the status bar shows its real progress (the take) or a busy bar
(the analysis, which has no percentage).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QWidget

from reverbscope.core.sweep import measurement_signal
from reverbscope.i18n import _
from reverbscope.models.audio import AudioSignal
from reverbscope.models.result import AnalysisResult
from reverbscope.ui.document import Measurement, WorkspaceDocument
from reverbscope.ui.measure_dialog import AnalysisRequest, TakeRequest
from reverbscope.ui.measure_flow import AnalysisRun, TakeRun, late_result_text, safe_findings
from reverbscope.ui.workers import unexpected_error_text

log = logging.getLogger(__name__)


@dataclass
class Job:
    """What runs now: a take (then its analysis) or an analysis of an import."""

    number: int
    take: TakeRequest | None = None
    analysis: AnalysisRequest | None = None
    recording: AudioSignal | None = None
    #: The project open when the job started: the measurement is filed under
    #: it, whatever project is open when the result arrives.
    project: Path | None = None

    @property
    def kind(self) -> str:
        return "take" if self.take is not None else "analysis"


class MeasurementController(QObject):
    """Owns the worker threads and the job they serve."""

    #: ``(busy, text, fraction or None, stoppable)`` for the status bar.
    status_changed = Signal(bool, str, object, bool)
    #: A measurement was added to the document (its id).
    measurement_ready = Signal(str)
    #: A take or analysis failed, with the message in the interface language.
    failed = Signal(str)
    #: The take was stopped before it ended; nothing was added.
    stopped = Signal()

    def __init__(self, document: WorkspaceDocument, parent: QWidget) -> None:
        super().__init__(parent)
        self.document = document
        self._parent = parent
        self._take = TakeRun(self)
        self._take.recorded.connect(self._on_recorded)
        self._take.failed.connect(self._on_failure)
        self._take.progress.connect(self._on_progress)
        self._take.stopped.connect(self._on_stopped)
        self._analysis = AnalysisRun(self)
        self._analysis.succeeded.connect(self._on_success)
        self._analysis.failed.connect(self._on_failure)
        self._job: Job | None = None
        self._next_job = 1

    # --- state --------------------------------------------------------------------

    @property
    def job(self) -> Job | None:
        """The job running now, or ``None``."""
        return self._job if self.is_busy() else None

    def is_busy(self) -> bool:
        return self._take.is_running() or self._analysis.is_running()

    def take_running(self) -> bool:
        return self._take.is_running()

    @property
    def take_worker(self) -> object:
        return self._take.worker

    @property
    def analysis_worker(self) -> object:
        return self._analysis.worker

    def shutdown(self) -> None:
        """Stop a take (silencing the output) and let both workers finish."""
        self._job = None
        self._take.request_stop()
        self._take.wait()
        self._analysis.wait()

    def stop(self) -> None:
        """Stop the take that plays. The analysis cannot be stopped; a result
        that arrives after Stop was pressed during it is still added."""
        self._take.request_stop()

    # --- starting -------------------------------------------------------------------

    def start_take(self, request: TakeRequest) -> bool:
        if self.is_busy():
            return False
        job = Job(self._next_job, take=request, project=self.document.project)
        self._next_job += 1
        self._job = job
        self.status_changed.emit(True, _("Playing the sweep and recording..."), 0.0, True)
        self._take.start(
            measurement_signal(request.settings),
            request.settings.sample_rate,
            job=job.number,
            input_device=request.input_device,
            output_device=request.output_device,
            input_channels=list(request.input_channels),
            output_channel=request.output_channel,
            level_dbfs=request.settings.level_dbfs,
            backend=request.backend,
            options=request.options,
            loopback_channel=request.loopback_channel,
        )
        return True

    def start_analysis(self, request: AnalysisRequest, *, blocking: bool = False) -> bool:
        if self.is_busy():
            return False
        job = Job(self._next_job, analysis=request, project=self.document.project)
        self._next_job += 1
        self._job = job
        self.status_changed.emit(True, _("Analyzing..."), None, False)
        self._analysis.start(
            request.recording,
            request.reference,
            request.analysis_settings,
            job=job.number,
            blocking=blocking,
        )
        return True

    # --- the take -----------------------------------------------------------------

    def _stale(self, job_number: int) -> bool:
        """The job is no longer the current one, or the window is gone."""
        return (
            self._job is None
            or self._job.number != job_number
            or not self._parent.window().isVisible()
        )

    def _on_progress(self, fraction: float) -> None:
        self.status_changed.emit(True, _("Playing the sweep and recording..."), fraction, True)

    def _on_stopped(self, job_number: int) -> None:
        if self._job is not None and self._job.number == job_number:
            self._job = None
        self.status_changed.emit(False, _("Stopped."), None, False)
        self.stopped.emit()

    def _on_recorded(self, recording: AudioSignal, job_number: int) -> None:
        if self._stale(job_number):
            self.status_changed.emit(False, late_result_text(), None, False)
            return
        job = self._job
        assert job is not None and job.take is not None
        job.recording = recording
        # The take is over; Stop cannot cancel the analysis, and its progress
        # has no percentage: a busy bar, never a number.
        self.status_changed.emit(True, _("Recorded. Analyzing..."), None, False)
        self._analysis.start(
            recording,
            job.take.reference,
            job.take.analysis_settings,
            job=job.number,
        )

    def _on_success(self, result: AnalysisResult, job_number: int) -> None:
        if self._stale(job_number):
            self.status_changed.emit(False, late_result_text(), None, False)
            return
        job = self._job
        assert job is not None
        self._job = None
        try:
            measurement = self._measurement_for(job, result)
        except Exception:
            # The worker is done: the window must not stay busy without a job.
            log.exception("The measurement could not be built from the result")
            message = unexpected_error_text()
            self.status_changed.emit(
                False, _("Analysis failed: {message}").format(message=message), None, False
            )
            self.failed.emit(message)
            return
        self.status_changed.emit(False, _("Done."), None, False)
        self.document.add(measurement)
        self.measurement_ready.emit(measurement.id)

    def _measurement_for(self, job: Job, result: AnalysisResult) -> Measurement:
        if job.take is not None:
            request = job.take
            findings, problem = safe_findings(result, request.profile)
            # A take on a real interface exists only in memory until the session
            # is saved; synthetic data (the fake backend) is nothing to lose.
            return Measurement(
                session=request.session,
                result=result,
                findings=findings,
                findings_problem=problem,
                profile=request.profile,
                recording=job.recording,
                reference=request.reference,
                unsaved_take=not request.synthetic,
                project=job.project,
            )
        assert job.analysis is not None
        request_a = job.analysis
        findings, problem = safe_findings(result, request_a.profile)
        return Measurement(
            session=request_a.session,
            result=result,
            findings=findings,
            findings_problem=problem,
            profile=request_a.profile,
            recording_path=request_a.recording_path,
            reference=request_a.reference,
            project=job.project,
        )

    def _on_failure(self, message: str, job_number: int) -> None:
        stale = self._stale(job_number)
        if self._job is not None and self._job.number == job_number:
            kind = self._job.kind
            self._job = None
        else:
            kind = "analysis"
        text = (
            _("Measurement failed: {message}").format(message=message)
            if kind == "take"
            else _("Analysis failed: {message}").format(message=message)
        )
        self.status_changed.emit(False, text, None, False)
        if not stale:
            self.failed.emit(message)
