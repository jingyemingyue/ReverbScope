"""Strip Start must not race an open project's session loader."""

from __future__ import annotations

import os
import threading
from pathlib import Path

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from reverbscope.ui.main_window import MainWindow

pytestmark = pytest.mark.gui


@pytest.fixture(scope="module")
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.fixture
def held_loader(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    from reverbscope.ui import workspace as ws

    gate = threading.Event()
    real = ws.ProjectLoader.run

    def held(self: object) -> None:  # type: ignore[no-untyped-def]
        gate.wait(timeout=30)
        if self.isInterruptionRequested():  # type: ignore[attr-defined]
            return
        return real(self)

    monkeypatch.setattr(ws.ProjectLoader, "run", held)
    yield gate
    gate.set()


def test_strip_start_refuses_while_project_sessions_are_loading(
    app: QApplication, tmp_path: Path, held_loader, monkeypatch: pytest.MonkeyPatch
) -> None:
    started: list[str] = []
    window = MainWindow()
    window.show()
    window.show_view("project")
    monkeypatch.setattr(
        window.standalone,
        "start_measurement",
        lambda: started.append("take"),
    )
    assert window.project.create_project(tmp_path / "room")
    app.processEvents()
    try:
        assert window.model.loading
        assert not window.strip.start_button.isEnabled()
        window._strip_start("standalone")
        app.processEvents()
        assert started == []
        window.strip.set_position("Stay")
        window._measure_at("A")
        app.processEvents()
        assert window.strip.position.currentText() == "Stay"
        assert started == []
    finally:
        held_loader.set()
        assert window.model.wait_until_loaded()
    window.close()


def test_standalone_run_refuses_while_project_sessions_are_loading(
    app: QApplication, tmp_path: Path, held_loader
) -> None:
    window = MainWindow()
    window.show()
    window.show_view("project")
    assert window.project.create_project(tmp_path / "room")
    app.processEvents()
    try:
        assert window.model.loading
        assert not window.standalone.run_button.isEnabled()
        window.show_mode("demo")
        app.processEvents()
        # show_mode may re-enable Run via readiness; the hard gate still applies.
        window.standalone.start_measurement()
        app.processEvents()
        assert not window.standalone.is_busy()
        assert window.standalone._measure_worker is None
    finally:
        held_loader.set()
        assert window.model.wait_until_loaded()
    window.close()


def test_daw_analyze_refuses_while_project_sessions_are_loading(
    app: QApplication, tmp_path: Path, held_loader
) -> None:
    from reverbscope.core.pipeline import synthetic_recording
    from reverbscope.io.wav import write_wav
    from reverbscope.models.configuration import SweepSettings
    from tests.conftest import make_rir

    window = MainWindow()
    window.show()
    window.show_view("project")
    assert window.project.create_project(tmp_path / "room")
    app.processEvents()
    try:
        assert window.model.loading
        assert not window.daw.analyze_button.isEnabled()
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
        assert not page.is_busy()
        assert page._worker is None
    finally:
        held_loader.set()
        assert window.model.wait_until_loaded()
    window.close()
