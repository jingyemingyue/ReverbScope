"""Worker lifecycle and failure handling of the workbench: a failing profile,
an analysis that fails or runs out of memory, a second job during a job, a
result that completes as the window closes, and folders that cannot be
written."""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMessageBox

from reverbscope.core.pipeline import Reference, synthetic_recording
from reverbscope.errors import AnalysisError
from reverbscope.models.configuration import AnalysisSettings, SweepSettings
from reverbscope.models.session import MeasurementSession
from reverbscope.ui import measure_flow, workbench, workers
from reverbscope.ui.measure_dialog import AnalysisRequest
from reverbscope.ui.workbench import WorkbenchWindow
from tests.conftest import make_rir

pytestmark = pytest.mark.gui


@pytest.fixture(scope="module")
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _settle(app: QApplication, *threads: object, rounds: int = 10) -> None:
    for thread in threads:
        if thread is not None:
            thread.wait()  # type: ignore[attr-defined]
    for _ in range(rounds):
        app.processEvents()
        time.sleep(0.01)


@pytest.fixture
def held_analysis(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    """The analysis waits until the test releases it."""
    gate = threading.Event()
    real = workers.analyze

    def held(*args, **kwargs):  # type: ignore[no-untyped-def]
        gate.wait(30)
        return real(*args, **kwargs)

    monkeypatch.setattr(workers, "analyze", held)
    yield gate
    gate.set()


def _request(short_sweep: SweepSettings, *, profile: str = "generic") -> AnalysisRequest:
    recording = synthetic_recording(short_sweep, make_rir(short_sweep.sample_rate, rt60_s=0.3))
    return AnalysisRequest(
        recording=recording,
        recording_path=None,
        reference=Reference.from_settings(short_sweep),
        sweep_path=None,
        settings=short_sweep,
        analysis_settings=AnalysisSettings(),
        profile=profile,
        session=MeasurementSession(room_name="Booth", measurement_position="A"),
    )


def test_a_profile_that_fails_still_adds_the_measurement(
    app: QApplication, short_sweep: SweepSettings, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(result: object, profile: str) -> list[object]:
        raise AnalysisError("profile exploded")

    monkeypatch.setattr(measure_flow, "interpret", broken)
    window = WorkbenchWindow()
    window.show()
    assert window.measurements.start_analysis(_request(short_sweep), blocking=True)
    _settle(app)
    measurement = window.document.selected()
    assert measurement is not None
    assert measurement.findings == [] and "profile exploded" in measurement.findings_problem
    assert not window.measurements.is_busy()
    assert window.measure_action.isEnabled()
    window.close()


def test_an_analysis_that_fails_is_a_dialog_not_a_bug(
    app: QApplication, short_sweep: SweepSettings, monkeypatch: pytest.MonkeyPatch
) -> None:
    def failing(*args: object, **kwargs: object) -> object:
        raise AnalysisError("no sweep found")

    monkeypatch.setattr(workers, "analyze", failing)
    shown: list[str] = []
    monkeypatch.setattr(workbench, "error_box", lambda parent, title, text: shown.append(text))
    window = WorkbenchWindow()
    window.show()
    assert window.measurements.start_analysis(_request(short_sweep), blocking=True)
    _settle(app)
    assert shown and "no sweep found" in shown[0]
    assert len(window.document) == 0
    assert not window.measurements.is_busy()
    assert "no sweep found" in window.run_status.activity.text()
    window.close()


def test_a_worker_that_runs_out_of_memory_says_so_and_does_not_call_it_a_bug(
    app: QApplication, short_sweep: SweepSettings, monkeypatch: pytest.MonkeyPatch
) -> None:
    def hungry(*args: object, **kwargs: object) -> object:
        raise MemoryError

    monkeypatch.setattr(workers, "analyze", hungry)
    shown: list[str] = []
    monkeypatch.setattr(workbench, "error_box", lambda parent, title, text: shown.append(text))
    window = WorkbenchWindow()
    window.show()
    assert window.measurements.start_analysis(_request(short_sweep), blocking=True)
    _settle(app)
    assert shown == [workers.out_of_memory_text()]
    assert "bug" not in shown[0].lower()
    window.close()


def test_a_second_analysis_during_an_analysis_is_refused(
    app: QApplication, held_analysis: threading.Event, short_sweep: SweepSettings
) -> None:
    window = WorkbenchWindow()
    window.show()
    assert window.measurements.start_analysis(_request(short_sweep))
    assert not window.measurements.start_analysis(_request(short_sweep))
    assert window.measurements.is_busy()
    assert not window.import_action.isEnabled()
    held_analysis.set()
    _settle(app, window.measurements.analysis_worker, rounds=20)
    assert len(window.document) == 1
    assert window.import_action.isEnabled()
    window.close()


def test_closing_the_window_as_the_analysis_completes_is_quiet(
    app: QApplication,
    held_analysis: threading.Event,
    short_sweep: SweepSettings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    shown: list[str] = []
    monkeypatch.setattr(workbench, "error_box", lambda parent, title, text: shown.append(text))
    window = WorkbenchWindow()
    window.show()
    assert window.measurements.start_analysis(_request(short_sweep))
    held_analysis.set()
    # close() waits for the thread; the late result is dropped, no dialog.
    window.close()
    _settle(app, window.measurements.analysis_worker)
    assert shown == []
    assert len(window.document) == 0


def test_open_data_folder_with_an_uncreatable_home_warns_instead_of_raising(
    app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    blocker = tmp_path / "file"
    blocker.write_text("not a folder")
    monkeypatch.setenv("REVERBSCOPE_HOME", str(blocker / "home"))
    warned: list[str] = []
    monkeypatch.setattr(
        QMessageBox, "warning", lambda parent, title, text, *a: warned.append(text) or 0
    )
    window = WorkbenchWindow()
    window._open_data_folder()
    assert warned and "cannot create folder" in warned[0]
    window.close()


def test_ok_in_settings_with_an_unwritable_home_is_an_error_dialog_not_a_bug(
    app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from reverbscope.ui.settings_dialog import SettingsDialog

    blocker = tmp_path / "file"
    blocker.write_text("not a folder")
    monkeypatch.setenv("REVERBSCOPE_HOME", str(blocker / "home"))
    shown: list[str] = []
    monkeypatch.setattr(
        QMessageBox, "critical", lambda parent, title, text, *a: shown.append(text) or 0
    )
    dialog = SettingsDialog()
    dialog.accept()
    assert shown, "the failure to write settings.json is reported"
    assert dialog.result() == 0, "the dialog stays open with its choices"
    dialog.close()
