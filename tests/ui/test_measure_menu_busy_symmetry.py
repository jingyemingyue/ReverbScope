"""Measure menu must not start a second take/analysis while another is busy."""

from __future__ import annotations

import os
import threading
from pathlib import Path

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QThread
from PySide6.QtWidgets import QApplication

from reverbscope.core.pipeline import synthetic_recording
from reverbscope.io.wav import write_wav
from reverbscope.models.configuration import SweepSettings
from reverbscope.ui.main_window import MainWindow
from tests.conftest import make_rir

pytestmark = pytest.mark.gui


@pytest.fixture(scope="module")
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.fixture
def held_analysis(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    from reverbscope.ui import workers

    gate = threading.Event()
    real = workers.analyze

    def held(*args: object, **kwargs: object) -> object:
        gate.wait(timeout=30)
        return real(*args, **kwargs)

    monkeypatch.setattr(workers, "analyze", held)
    yield gate
    gate.set()


@pytest.fixture
def held_take(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
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


def _settle(app: QApplication, worker: QThread | None, timeout_ms: int = 8000) -> None:
    if worker is None:
        return
    elapsed = 0
    while worker.isRunning() and elapsed < timeout_ms:
        app.processEvents()
        worker.wait(20)
        elapsed += 20
    app.processEvents()


def _start_held_daw_analysis(window: MainWindow, tmp_path: Path, app: QApplication) -> object:
    window.show_mode("universal_daw")
    page = window.daw
    settings = SweepSettings(sample_rate=48000, duration_s=0.5, level_dbfs=-20.0)
    page.sample_rate.setCurrentIndex(page.sample_rate.findData(settings.sample_rate))
    page.duration.setValue(settings.duration_s)
    page.generate_sweep_to(tmp_path / "sweep.wav")
    take = synthetic_recording(settings, make_rir(settings.sample_rate, rt60_s=0.3))
    page.set_recording(
        write_wav(tmp_path / "take.wav", take.samples, take.sample_rate, subtype="FLOAT")
    )
    page.start_analysis()
    app.processEvents()
    assert page.is_busy()
    return page


def test_daw_is_busy_matches_busy_flag_and_worker(
    app: QApplication, tmp_path: Path, held_analysis
) -> None:
    window = MainWindow()
    window.show()
    page = _start_held_daw_analysis(window, tmp_path, app)
    try:
        assert page.is_busy()
        assert page._busy_flag
        assert page._worker is not None and page._worker.isRunning()
    finally:
        held_analysis.set()
        _settle(app, page._worker)
    assert not page.is_busy()
    window.close()


def test_standalone_is_busy_matches_busy_flag_without_running_worker(
    app: QApplication,
) -> None:
    """``_busy_flag`` alone must count as busy (same contract as DAW Analyze)."""
    window = MainWindow()
    window.show()
    page = window.standalone
    assert not page.is_busy()
    page._busy_flag = True
    assert page.is_busy()
    page._busy_flag = False
    assert not page.is_busy()
    window.close()


def test_daw_analyze_blocks_measure_menu_from_starting_a_demo_take(
    app: QApplication, tmp_path: Path, held_analysis, monkeypatch: pytest.MonkeyPatch
) -> None:
    """While DAW Analyze runs, Measure ▸ Standalone must not switch away."""
    from reverbscope.ui import pages as pages_mod

    started: list[str] = []
    real_start = pages_mod.StandalonePage.start_measurement

    def spy(self: object, *args: object, **kwargs: object) -> None:
        started.append("standalone")
        return real_start(self, *args, **kwargs)

    monkeypatch.setattr(pages_mod.StandalonePage, "start_measurement", spy)

    window = MainWindow()
    window.show()
    page = _start_held_daw_analysis(window, tmp_path, app)
    try:
        for action in window.measure_mode_actions:
            assert not action.isEnabled(), action.text()
        window.show_mode("demo")
        app.processEvents()
        assert window.stack.currentWidget() is window.daw
        # Strip Start is the user path into a sounding take; keep it locked.
        assert not window.strip.start_button.isEnabled()
        window.strip.start_button.click()
        app.processEvents()
        assert started == []
        assert page._worker is not None and page._worker.isRunning()
    finally:
        held_analysis.set()
        _settle(app, page._worker)
    window.close()


def test_standalone_take_blocks_measure_menu_from_starting_daw_analyze(
    app: QApplication, held_take
) -> None:
    """While a Standalone take sounds, Measure ▸ DAW must not switch away."""
    window = MainWindow()
    window.show()
    window.show_mode("demo")
    app.processEvents()
    page = window.standalone
    page.duration.setValue(1.0)
    try:
        page.run_button.click()
        assert page.is_busy()
        for action in window.measure_mode_actions:
            assert not action.isEnabled(), action.text()
        window.show_mode("universal_daw")
        app.processEvents()
        assert window.stack.currentWidget() is window.standalone
        assert window.daw._worker is None or not window.daw._worker.isRunning()
    finally:
        held_take.set()
        _settle(app, page._measure_worker)
        _settle(app, page._analysis_worker)
    window.close()


def test_measure_at_does_not_reposition_while_busy(
    app: QApplication, tmp_path: Path, held_analysis
) -> None:
    window = MainWindow()
    window.show()
    page = _start_held_daw_analysis(window, tmp_path, app)
    window.strip.set_position("A")
    window.daw.position.setText("A")
    try:
        window._measure_at("B")
        app.processEvents()
        assert window.strip.position.currentText() == "A"
        assert window.daw.position.text() == "A"
    finally:
        held_analysis.set()
        _settle(app, page._worker)
    window.close()
