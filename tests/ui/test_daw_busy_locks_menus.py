"""DAW Analyze must lock the same busy_actions as a Standalone take."""

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


def _settle(app: QApplication, worker: QThread | None, timeout_ms: int = 8000) -> None:
    if worker is None:
        return
    elapsed = 0
    while worker.isRunning() and elapsed < timeout_ms:
        app.processEvents()
        worker.wait(20)
        elapsed += 20
    app.processEvents()


def test_daw_analyze_locks_new_open_and_start_panel(
    app: QApplication, tmp_path: Path, held_analysis
) -> None:
    window = MainWindow()
    window.show()
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
    try:
        page.start_analysis()
        app.processEvents()
        assert page._busy_flag
        for action in window.busy_actions:
            assert not action.isEnabled(), action.text()
    finally:
        held_analysis.set()
        _settle(app, page._worker)
    assert all(action.isEnabled() for action in window.busy_actions)
    window.close()
