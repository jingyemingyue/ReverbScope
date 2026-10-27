"""Open Session / recent must not bypass the measure busy lock."""

from __future__ import annotations

import os
import threading
from pathlib import Path

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QThread
from PySide6.QtWidgets import QApplication

from reverbscope.core.pipeline import Reference, analyze, synthetic_recording
from reverbscope.io.session_store import save_measurement
from reverbscope.io.wav import write_wav
from reverbscope.models.configuration import SweepSettings
from reverbscope.models.session import MeasurementSession
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


def _saved_session(tmp_path: Path, short_sweep: SweepSettings) -> Path:
    rate = short_sweep.sample_rate
    result = analyze(
        synthetic_recording(short_sweep, make_rir(rate, rt60_s=0.8), noise_rms=1e-5),
        Reference.from_settings(short_sweep),
    )
    folder = tmp_path / "studio-x"
    save_measurement(folder, MeasurementSession(room_name="Studio X"), result, copy_recording=False)
    return folder


def test_open_session_path_refuses_while_daw_analysis_runs(
    app: QApplication, tmp_path: Path, short_sweep: SweepSettings, held_analysis
) -> None:
    folder = _saved_session(tmp_path, short_sweep)
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
    before_keys = {entry.key for entry in window.model.entries()}
    try:
        page.start_analysis()
        app.processEvents()
        assert page.is_busy()
        assert not window.navigator.recent.isEnabled()
        assert not window.open_session_path(folder)
        assert {entry.key for entry in window.model.entries()} == before_keys
        assert page._worker is not None and page._worker.isRunning()
    finally:
        held_analysis.set()
        _settle(app, page._worker)
    assert window.navigator.recent.isEnabled()
    assert window.open_session_path(folder)
    window.close()


def test_recent_and_open_are_blocked_while_a_take_sounds(
    app: QApplication, tmp_path: Path, short_sweep: SweepSettings, held_take
) -> None:
    folder = _saved_session(tmp_path, short_sweep)
    window = MainWindow()
    window.show()
    window.show_mode("demo")
    app.processEvents()
    page = window.standalone
    page.duration.setValue(1.0)
    before = window.stack.currentWidget()
    try:
        page.run_button.click()
        assert page.is_busy()
        assert not window.navigator.recent.isEnabled()
        assert not window.open_session_path(folder)
        window.navigator.open_recent_requested.emit(str(folder))
        app.processEvents()
        assert window.stack.currentWidget() is before
        assert window.model.entry(_folder_key(folder)) is None
    finally:
        held_take.set()
        _settle(app, page._measure_worker)
        _settle(app, page._analysis_worker)
    window.close()


def _folder_key(path: Path) -> str:
    from reverbscope.ui.workspace import folder_key

    return folder_key(path)
