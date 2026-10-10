"""State and lifecycle of the desktop app's workers (bug hunt round 4).

What happens when a result arrives after the user moved on, when a profile
fails, when Analyze is asked twice, when Stop and Run follow each other at
once, and when a folder cannot be written.
"""

from __future__ import annotations

import os
import threading
from pathlib import Path

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMessageBox

from reverbscope.core.pipeline import synthetic_recording
from reverbscope.errors import AnalysisError
from reverbscope.io.wav import write_wav
from reverbscope.models.configuration import SweepSettings
from reverbscope.ui import daw_page, measure_flow, workers
from reverbscope.ui.main_window import MainWindow
from tests.conftest import make_rir

pytestmark = pytest.mark.gui


@pytest.fixture(scope="module")
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _settle(app: QApplication, *threads: object) -> None:
    """Wait for the workers, then deliver their queued signals."""
    import time

    for thread in threads:
        if thread is not None:
            thread.wait()  # type: ignore[attr-defined]
    for _ in range(10):
        app.processEvents()
        time.sleep(0.01)


@pytest.fixture
def held_analysis(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    """The GUI's analysis waits until the test releases it."""
    gate = threading.Event()
    real = workers.analyze

    def held(*args, **kwargs):  # type: ignore[no-untyped-def]
        gate.wait(30)
        return real(*args, **kwargs)

    monkeypatch.setattr(workers, "analyze", held)
    yield gate
    gate.set()


@pytest.fixture
def held_take(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    """The fake interface plays until the test releases it (or Stop is pressed)."""
    from PySide6.QtCore import QThread

    from reverbscope.audio.fake import FakeBackend
    from reverbscope.errors import MeasurementCancelledError

    release = threading.Event()
    real = FakeBackend.play_and_record
    takes: list[tuple[QThread, threading.Event | None]] = []

    def held(self, *args, cancel=None, **kwargs):  # type: ignore[no-untyped-def]
        takes.append((QThread.currentThread(), cancel))
        while not release.wait(0.01):
            if cancel is not None and cancel.is_set():
                raise MeasurementCancelledError("stopped")
        return real(self, *args, cancel=cancel, **kwargs)

    monkeypatch.setattr(FakeBackend, "play_and_record", held)
    yield release
    for thread, cancel in takes:
        if cancel is not None:
            cancel.set()
        else:
            release.set()
        thread.wait()


def _daw_ready(app: QApplication, tmp_path: Path, short_sweep: SweepSettings) -> MainWindow:
    """A window on the Universal DAW page with a sweep and a take ready to analyse."""
    window = MainWindow()
    window.show()
    window.show_mode("universal_daw")
    page = window.daw
    rate = short_sweep.sample_rate
    page.sample_rate.setCurrentIndex(page.sample_rate.findData(rate))
    page.duration.setValue(short_sweep.duration_s)
    page.generate_sweep_to(tmp_path / "sweep.wav")
    take = synthetic_recording(page.current_sweep_settings(), make_rir(rate, rt60_s=0.3))
    page.set_recording(
        write_wav(tmp_path / "take.wav", take.samples, take.sample_rate, subtype="FLOAT")
    )
    app.processEvents()
    return window


def test_a_visit_to_compare_does_not_discard_a_running_analysis(
    app: QApplication, tmp_path: Path, short_sweep: SweepSettings, held_analysis
) -> None:
    """Ctrl+Shift+C during an analysis hid the page, and the result that
    arrived meanwhile was thrown away as "late" although nothing had
    replaced it; the user had to run the analysis again."""
    window = _daw_ready(app, tmp_path, short_sweep)
    page = window.daw
    try:
        page.start_analysis()
        window.show_compare()
        assert window.stack.currentWidget() is window.compare
    finally:
        held_analysis.set()
        _settle(app, page._worker)
    assert window.state.result is not None
    assert window.stack.currentWidget() is window.results
    assert "discarded" not in page.status.text()
    assert page.analyze_button.isEnabled()
    window.close()


def test_a_profile_that_fails_does_not_leave_the_page_busy(
    app: QApplication, tmp_path: Path, short_sweep: SweepSettings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A recording profile (a third-party one from an entry point) that raised
    while interpreting the result left the progress bar running and Analyze
    disabled for good; the result itself was never shown."""

    def broken(result: object, profile: str) -> list[object]:
        raise RuntimeError("plugin bug")

    monkeypatch.setattr(measure_flow, "interpret", broken)
    window = _daw_ready(app, tmp_path, short_sweep)
    page = window.daw
    page.start_analysis(blocking=True)
    app.processEvents()
    assert page.analyze_button.isEnabled()
    assert not page.progress.isVisible()
    assert window.state.result is not None
    assert window.state.findings == []
    assert window.stack.currentWidget() is window.results
    assert page.status.text()
    window.close()


def test_a_failure_after_new_measurement_shows_no_dialog(
    app: QApplication, tmp_path: Path, short_sweep: SweepSettings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ctrl+N abandoned the analysis; its failure then opened a modal error
    box over whatever page the user had moved to."""
    gate = threading.Event()

    def failing(*args: object, **kwargs: object) -> object:
        gate.wait(30)
        raise AnalysisError("the reference sweep was not found in the recording")

    boxes: list[tuple[object, ...]] = []
    monkeypatch.setattr(workers, "analyze", failing)
    monkeypatch.setattr(daw_page, "error_box", lambda *args, **kwargs: boxes.append(args))
    window = _daw_ready(app, tmp_path, short_sweep)
    page = window.daw
    try:
        page.start_analysis()
        window.show_home()
    finally:
        gate.set()
        _settle(app, page._worker)
    assert boxes == []
    assert "failed" in page.status.text().lower()
    assert page.analyze_button.isEnabled()
    assert window.stack.currentWidget() is window.home
    window.close()


def test_a_second_analyze_during_an_analysis_is_ignored(
    app: QApplication, tmp_path: Path, short_sweep: SweepSettings, held_analysis
) -> None:
    """A second ``start_analysis`` while one ran replaced the only reference
    to the running QThread (Qt aborts the process when such a thread is
    destroyed); the button is disabled, but the call is reachable."""
    window = _daw_ready(app, tmp_path, short_sweep)
    page = window.daw
    try:
        page.start_analysis()
        first = page._worker
        assert first is not None and first.isRunning()
        page.start_analysis()
        assert page._worker is first
    finally:
        held_analysis.set()
        _settle(app, page._worker)
    assert window.state.result is not None
    window.close()


def test_closing_the_window_as_the_analysis_completes_is_quiet(
    app: QApplication, tmp_path: Path, short_sweep: SweepSettings, held_analysis
) -> None:
    """Close the window the instant the analysis is released: the result
    arrives on a closed window and must neither crash nor open a page."""
    window = _daw_ready(app, tmp_path, short_sweep)
    page = window.daw
    page.start_analysis()
    worker = page._worker
    held_analysis.set()
    window.close()  # waits for the worker
    assert worker is not None and not worker.isRunning()
    _settle(app)
    assert not window.isVisible()
    assert page.analyze_button.isEnabled()


def test_stop_then_run_again_at_once(app: QApplication, held_take) -> None:
    """Stop, Run, Stop, Run on the demo page: every Stop frees the page for
    the next take and no take is ever lost or doubled."""
    window = MainWindow()
    window.show()
    window.show_mode("demo")
    app.processEvents()
    page = window.standalone
    page.duration.setValue(1.0)
    seen = []
    for _ in range(3):
        page.run_button.click()
        worker = page._measure_worker
        assert worker is not None and worker.isRunning()
        assert worker not in seen
        seen.append(worker)
        assert page.stop_button.isEnabled() and not page.run_button.isEnabled()
        page.stop_button.click()
        _settle(app, worker)
        assert page.run_button.isEnabled() and not page.stop_button.isEnabled()
        assert "Stopped" in page.status.text()
    window.close()


def test_a_recent_session_deleted_meanwhile_is_reported_not_crashed(
    app: QApplication, tmp_path: Path, short_sweep: SweepSettings, monkeypatch: pytest.MonkeyPatch
) -> None:
    import shutil

    from reverbscope.core.pipeline import Reference, analyze
    from reverbscope.io.session_store import save_measurement
    from reverbscope.models.session import MeasurementSession

    rate = short_sweep.sample_rate
    result = analyze(
        synthetic_recording(short_sweep, make_rir(rate, rt60_s=0.4), noise_rms=1e-5),
        Reference.from_settings(short_sweep),
    )
    folder = tmp_path / "gone"
    save_measurement(folder, MeasurementSession(room_name="Gone"), result, copy_recording=False)
    shown: list[str] = []
    monkeypatch.setattr(
        QMessageBox, "critical", lambda parent, title, text, *a, **k: shown.append(text)
    )
    window = MainWindow()
    window.show()
    window.open_session_path(folder)
    assert window.stack.currentWidget() is window.results
    shutil.rmtree(folder)
    window.show_home()
    window.open_session_path(folder)
    assert shown and "gone" in shown[-1]
    assert window.stack.currentWidget() is window.home
    assert window.state.result is None
    window.close()


def test_saving_into_a_folder_that_cannot_be_created_is_a_dialog_not_a_bug(
    app: QApplication, tmp_path: Path, short_sweep: SweepSettings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A parent that is a file (on Windows also a reserved name such as CON)
    raised a bare OSError out of Save, which the app called a bug."""
    shown: list[str] = []
    monkeypatch.setattr(
        QMessageBox, "critical", lambda parent, title, text, *a, **k: shown.append(text)
    )
    window = _daw_ready(app, tmp_path, short_sweep)
    window.daw.start_analysis(blocking=True)
    app.processEvents()
    assert window.stack.currentWidget() is window.results
    blocker = tmp_path / "blocker"
    blocker.write_text("x", encoding="utf-8")
    window.results.save_to(blocker / "session")
    assert shown and "cannot create" in shown[-1]
    # A folder whose parents went missing meanwhile is made again.
    window.results.save_to(tmp_path / "deleted" / "again" / "session")
    assert (tmp_path / "deleted" / "again" / "session" / "session.json").is_file()
    window.close()


def test_a_test_signal_that_cannot_be_written_is_a_dialog_not_a_bug(
    app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    shown: list[str] = []
    monkeypatch.setattr(
        QMessageBox, "critical", lambda parent, title, text, *a, **k: shown.append(text)
    )
    window = MainWindow()
    window.show()
    window.show_mode("universal_daw")
    blocker = tmp_path / "blocker"
    blocker.write_text("x", encoding="utf-8")
    window.daw.generate_sweep_to(blocker / "sweep.wav")
    assert shown and "cannot write" in shown[-1]
    assert "No test signal" in window.daw.sweep_label.text()
    window.close()
