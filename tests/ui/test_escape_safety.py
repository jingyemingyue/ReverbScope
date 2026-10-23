"""Esc priority while a take is sounding (C8, §11.5).

Offscreen only: these tests check key dispatch and the software cancel flag.
They do not measure how soon a physical output goes silent.
"""

from __future__ import annotations

import os
import threading
import time

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, Qt, QThread
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox, QMenu

from reverbscope.errors import MeasurementCancelledError
from reverbscope.ui.main_window import MainWindow
from reverbscope.ui.settings_dialog import SettingsDialog
from reverbscope.ui.workers import MeasureWorker

pytestmark = pytest.mark.gui


@pytest.fixture(scope="module")
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _settle(app: QApplication, *threads: object) -> None:
    for thread in threads:
        if thread is not None:
            thread.wait()  # type: ignore[attr-defined]
    for _ in range(10):
        app.processEvents()
        time.sleep(0.01)


@pytest.fixture
def held_take(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    """The fake interface plays until the test releases it, or Stop is pressed."""
    from reverbscope.audio.fake import FakeBackend

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


@pytest.fixture
def held_analysis(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    """Analysis waits until the test releases it."""
    from reverbscope.ui import workers

    gate = threading.Event()
    real = workers.analyze

    def held(*args, **kwargs):  # type: ignore[no-untyped-def]
        gate.wait(30)
        return real(*args, **kwargs)

    monkeypatch.setattr(workers, "analyze", held)
    yield gate
    gate.set()


@pytest.fixture
def stop_calls(monkeypatch: pytest.MonkeyPatch) -> list[MeasureWorker]:
    calls: list[MeasureWorker] = []
    real = MeasureWorker.request_stop

    def wrapped(self: MeasureWorker) -> None:
        calls.append(self)
        real(self)

    monkeypatch.setattr(MeasureWorker, "request_stop", wrapped)
    return calls


def _window(app: QApplication) -> MainWindow:
    window = MainWindow()
    window.show()
    window.show_mode("demo")
    app.processEvents()
    return window


def _start_take(app: QApplication, window: MainWindow) -> None:
    page = window.standalone
    page.duration.setValue(1.0)
    page.run_button.click()
    for _ in range(50):
        if page.is_take_running() and window.strip.stop_button.isEnabled():
            return
        app.processEvents()
        time.sleep(0.01)
    raise AssertionError("the take did not start sounding")


def _press_escape(widget: object) -> None:
    QTest.keyClick(widget, Qt.Key.Key_Escape)  # type: ignore[arg-type]


def _popup(window: MainWindow, app: QApplication) -> QMenu:
    menu = QMenu(window)
    menu.addAction("Leave this open")
    menu.popup(window.mapToGlobal(QPoint(8, 8)))
    app.processEvents()
    assert menu.isVisible()
    return menu


def test_escape_while_idle_leaves_the_page_and_closes_a_popup(
    app: QApplication, stop_calls: list[MeasureWorker]
) -> None:
    window = _window(app)
    page = window.stack.currentWidget()
    menu = _popup(window, app)
    _press_escape(menu)
    app.processEvents()
    assert not menu.isVisible()
    assert window.stack.currentWidget() is page
    assert window.state.result is None
    assert stop_calls == []
    assert not window.strip.stop_button.isEnabled()
    window.close()


def test_escape_while_measuring_stops_the_take(
    app: QApplication, held_take: threading.Event, stop_calls: list[MeasureWorker]
) -> None:
    window = _window(app)
    saves: list[str] = []
    window.save_take = lambda: saves.append("saved")  # type: ignore[method-assign]
    try:
        _start_take(app, window)
        stopped: list[int] = []
        succeeded: list[int] = []
        worker = window.standalone._measure_worker
        assert worker is not None
        worker.stopped.connect(lambda: stopped.append(1))
        worker.succeeded.connect(lambda: succeeded.append(1))
        _press_escape(window)
        _settle(app, worker)
        assert stop_calls == [worker]
        assert stopped == [1]
        assert succeeded == []
        assert window.state.result is None
        assert saves == []
        assert "Stopped" in window.standalone.status.text()
        assert not window.strip.stop_button.isEnabled()
    finally:
        held_take.set()
        window.close()


def test_escape_while_measuring_stops_when_focus_is_in_a_child(
    app: QApplication, held_take: threading.Event, stop_calls: list[MeasureWorker]
) -> None:
    window = _window(app)
    try:
        _start_take(app, window)
        child = window.standalone.room
        assert child.isEnabled()
        child.setFocus()
        app.processEvents()
        assert app.focusWidget() is child
        worker = window.standalone._measure_worker
        _press_escape(child)
        _settle(app, worker)
        assert worker is not None
        assert stop_calls == [worker]
        assert window.state.result is None
        assert not window.strip.stop_button.isEnabled()
    finally:
        held_take.set()
        window.close()


def test_escape_while_measuring_stops_instead_of_rejecting_a_dialog(
    app: QApplication, held_take: threading.Event, stop_calls: list[MeasureWorker]
) -> None:
    window = _window(app)
    try:
        _start_take(app, window)
        dialog = SettingsDialog(window)
        dialog.setWindowModality(Qt.WindowModality.ApplicationModal)
        rejected: list[int] = []
        dialog.rejected.connect(lambda: rejected.append(1))
        dialog.show()
        app.processEvents()
        assert dialog.isVisible()
        _press_escape(dialog)
        app.processEvents()
        worker = window.standalone._measure_worker
        assert worker is not None
        assert stop_calls == [worker]
        assert dialog.isVisible()
        assert rejected == []
        dialog.close()
        _settle(app, worker)
        assert window.state.result is None
    finally:
        held_take.set()
        window.close()


def test_escape_while_measuring_stops_instead_of_closing_a_popup(
    app: QApplication, held_take: threading.Event, stop_calls: list[MeasureWorker]
) -> None:
    window = _window(app)
    try:
        _start_take(app, window)
        menu = _popup(window, app)
        _press_escape(menu)
        app.processEvents()
        worker = window.standalone._measure_worker
        assert worker is not None
        assert stop_calls == [worker]
        assert menu.isVisible()
        menu.close()
        _settle(app, worker)
        assert window.state.result is None
    finally:
        held_take.set()
        window.close()


def test_escape_in_an_idle_dialog_cancels_it(
    app: QApplication, stop_calls: list[MeasureWorker]
) -> None:
    window = _window(app)
    dialog = SettingsDialog(window)
    rejected: list[int] = []
    dialog.rejected.connect(lambda: rejected.append(1))
    dialog.show()
    app.processEvents()
    _press_escape(dialog)
    app.processEvents()
    assert not dialog.isVisible()
    assert rejected == [1]
    assert stop_calls == []

    again = SettingsDialog(window)
    again.show()
    app.processEvents()
    box = again.findChild(QDialogButtonBox)
    assert box is not None
    cancel = box.button(QDialogButtonBox.StandardButton.Cancel)
    assert cancel is not None
    cancel.click()
    app.processEvents()
    assert again.result() == QDialog.DialogCode.Rejected
    assert not again.isVisible()
    assert stop_calls == []
    window.close()


def test_repeated_escape_while_measuring_stops_once(
    app: QApplication, held_take: threading.Event, stop_calls: list[MeasureWorker]
) -> None:
    window = _window(app)
    saves: list[str] = []
    window.save_take = lambda: saves.append("saved")  # type: ignore[method-assign]
    try:
        _start_take(app, window)
        worker = window.standalone._measure_worker
        assert worker is not None
        stopped: list[int] = []
        succeeded: list[int] = []
        worker.stopped.connect(lambda: stopped.append(1))
        worker.succeeded.connect(lambda: succeeded.append(1))
        for _ in range(3):
            _press_escape(window)
        _settle(app, worker)
        assert stop_calls == [worker]
        assert stopped == [1]
        assert succeeded == []
        assert window.state.result is None
        assert saves == []
    finally:
        held_take.set()
        window.close()


def test_escape_stops_a_take_started_after_a_stop(
    app: QApplication, held_take: threading.Event, stop_calls: list[MeasureWorker]
) -> None:
    window = _window(app)
    try:
        for _ in range(2):
            _start_take(app, window)
            worker = window.standalone._measure_worker
            assert worker is not None
            _press_escape(window)
            _settle(app, worker)
            assert not worker.isRunning()
            assert window.state.result is None
            assert window.standalone.run_button.isEnabled()
            assert not window.strip.stop_button.isEnabled()
        assert len(stop_calls) == 2
        assert stop_calls[0] is not stop_calls[1]
    finally:
        held_take.set()
        window.close()


def test_escape_during_analysis_does_not_stop_or_publish(
    app: QApplication,
    held_take: threading.Event,
    held_analysis: threading.Event,
    stop_calls: list[MeasureWorker],
) -> None:
    """Analysis is not a sounding take. Esc must not publish a result or claim
    that this keypress silenced an output."""
    window = _window(app)
    try:
        _start_take(app, window)
        held_take.set()
        page = window.standalone
        analysis = None
        for _ in range(100):
            app.processEvents()
            analysis = page._analysis_worker
            sounding = window.strip.stop_button.isEnabled()
            if analysis is not None and analysis.isRunning() and not sounding:
                break
            time.sleep(0.01)
        assert analysis is not None and analysis.isRunning()
        assert not page.stop_button.isEnabled()
        before = len(stop_calls)
        _press_escape(window)
        _press_escape(page.room)
        app.processEvents()
        assert len(stop_calls) == before
        assert analysis.isRunning()
        assert window.state.result is None
        assert window.strip.phase.text() == "Analyzing"
    finally:
        held_analysis.set()
        window.close()
