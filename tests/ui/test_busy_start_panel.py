"""View ▸ Start panel must not open while a take is sounding."""

from __future__ import annotations

import os
import threading

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QThread
from PySide6.QtWidgets import QApplication

from reverbscope.ui.main_window import MainWindow

pytestmark = pytest.mark.gui


@pytest.fixture(scope="module")
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


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


def _settle(app: QApplication, worker: QThread | None, timeout_ms: int = 5000) -> None:
    if worker is None:
        return
    elapsed = 0
    while worker.isRunning() and elapsed < timeout_ms:
        app.processEvents()
        worker.wait(20)
        elapsed += 20
    app.processEvents()


def test_start_panel_stays_locked_while_a_take_plays(app: QApplication, held_take) -> None:
    window = MainWindow()
    window.show()
    window.show_mode("demo")
    app.processEvents()
    page = window.standalone
    page.duration.setValue(1.0)
    start = next(a for a in window.busy_actions if a.text().replace("&", "") == "Start panel")
    try:
        page.run_button.click()
        assert page.is_busy()
        assert not start.isEnabled()
        # The disabled action must not fire; a direct trigger is ignored by Qt
        # when the action is disabled.
        start.trigger()
        assert window.stack.currentWidget() is not window.home
        assert page.is_busy()
    finally:
        held_take.set()
        _settle(app, page._measure_worker)
        _settle(app, page._analysis_worker)
    assert start.isEnabled()
    window.close()
