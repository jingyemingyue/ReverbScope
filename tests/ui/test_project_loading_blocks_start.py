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
