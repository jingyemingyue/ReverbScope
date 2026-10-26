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
from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox, QMenu, QWidget

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


def test_escape_stops_a_worker_that_has_not_started(
    app: QApplication,
    held_take: threading.Event,
    stop_calls: list[MeasureWorker],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Stop is on and the worker exists, but its thread has not started."""
    window = _window(app)
    real_start = MeasureWorker.start

    def hold_start(self: MeasureWorker, *args: object, **kwargs: object) -> None:
        del args, kwargs

    monkeypatch.setattr(MeasureWorker, "start", hold_start)
    try:
        page = window.standalone
        page.duration.setValue(1.0)
        page.run_button.click()
        app.processEvents()
        worker = page._measure_worker
        assert worker is not None and not worker.isRunning()
        assert window.strip.stop_button.isEnabled()
        for _ in range(3):
            _press_escape(window)
        assert stop_calls == [worker]
        assert worker._cancel.is_set()
        real_start(worker)
        _settle(app, worker)
        assert not worker.isRunning()
        assert window.state.result is None
        assert "Stopped" in page.status.text()
    finally:
        held_take.set()
        window.close()


def test_escape_before_the_worker_exists_cancels_before_playback(
    app: QApplication,
    held_take: threading.Event,
    stop_calls: list[MeasureWorker],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Stop is already on, and the worker object does not exist yet."""
    from reverbscope.audio.fake import FakeBackend

    window = _window(app)
    page = window.standalone
    played: list[int] = []
    current = FakeBackend.play_and_record

    def track(self: FakeBackend, *args: object, **kwargs: object) -> object:
        cancel = kwargs.get("cancel")
        if cancel is not None and getattr(cancel, "is_set", lambda: False)():
            raise MeasurementCancelledError("stopped")
        played.append(1)
        return current(self, *args, **kwargs)

    monkeypatch.setattr(FakeBackend, "play_and_record", track)
    real_set_busy = page._set_busy

    def busy_then_escape(busy: bool, text: str = "", *, tone: str = "") -> None:
        real_set_busy(busy, text, tone=tone)
        if busy and page._measure_worker is None and window.strip.stop_button.isEnabled():
            for _ in range(3):
                _press_escape(window)

    monkeypatch.setattr(page, "_set_busy", busy_then_escape)
    try:
        page.duration.setValue(1.0)
        page.run_button.click()
        worker = page._measure_worker
        assert worker is not None
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline and stop_calls != [worker]:
            app.processEvents()
            time.sleep(0.01)
        assert stop_calls == [worker]
        assert played == []
        _settle(app, worker)
        assert window.state.result is None
        assert "Stopped" in page.status.text()
    finally:
        held_take.set()
        window.close()


def test_escape_on_the_next_start_cancels_the_new_worker(
    app: QApplication,
    held_take: threading.Event,
    stop_calls: list[MeasureWorker],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The previous worker is still referenced when Stop comes on for the next take."""
    window = _window(app)
    try:
        _start_take(app, window)
        page = window.standalone
        previous = page._measure_worker
        assert previous is not None
        _press_escape(window)
        _settle(app, previous)
        assert not previous.isRunning()
        assert page._measure_worker is previous
        assert window.state.result is None
        assert not window.strip.stop_button.isEnabled()

        real_set_busy = page._set_busy

        def busy_then_escape(busy: bool, text: str = "", *, tone: str = "") -> None:
            real_set_busy(busy, text, tone=tone)
            if busy and page._measure_worker is previous and window.strip.stop_button.isEnabled():
                for _ in range(3):
                    _press_escape(window)

        monkeypatch.setattr(page, "_set_busy", busy_then_escape)
        marked = len(stop_calls)
        page.run_button.click()
        new = page._measure_worker
        assert new is not None and new is not previous
        assert new._cancel.is_set()
        assert stop_calls[marked:] == [new]
        _settle(app, new)
        assert window.state.result is None
        assert "Stopped" in page.status.text()
    finally:
        held_take.set()
        window.close()


def test_closing_the_window_drops_the_escape_filter(
    app: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    window = _window(app)
    stale: list[int] = []
    monkeypatch.setattr(window.standalone, "stop_measurement", lambda: stale.append(1))
    window.close()
    app.processEvents()
    window.strip.stop_button.setEnabled(True)
    probe = QWidget()
    probe.show()
    app.processEvents()
    _press_escape(probe)
    app.processEvents()
    assert stale == []
    probe.close()


def test_a_cancelled_close_keeps_one_escape_filter(
    app: QApplication,
    held_take: threading.Event,
    stop_calls: list[MeasureWorker],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window = _window(app)
    # Only the close is refused. Starting a take also asks _leave_take, and
    # that must keep its normal answer or the run button does nothing.
    allow_leave = window._leave_take
    monkeypatch.setattr(window, "_leave_take", lambda: False)
    window.close()
    app.processEvents()
    monkeypatch.setattr(window, "_leave_take", allow_leave)
    assert window.isVisible()
    try:
        _start_take(app, window)
        for _ in range(3):
            _press_escape(window)
        worker = window.standalone._measure_worker
        _settle(app, worker)
        assert worker is not None
        assert stop_calls == [worker]
        assert window.state.result is None
    finally:
        held_take.set()
        window.close()


def test_a_new_window_does_not_reuse_a_closed_windows_escape_filter(
    app: QApplication,
    held_take: threading.Event,
    stop_calls: list[MeasureWorker],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = _window(app)
    stale: list[int] = []
    monkeypatch.setattr(first.standalone, "stop_measurement", lambda: stale.append(1))
    first.close()
    app.processEvents()
    first.strip.stop_button.setEnabled(True)
    second = _window(app)
    try:
        _start_take(app, second)
        _press_escape(second)
        worker = second.standalone._measure_worker
        _settle(app, worker)
        assert stale == []
        assert worker is not None
        assert stop_calls == [worker]
        assert second.state.result is None
    finally:
        held_take.set()
        second.close()
        probe = QWidget()
        probe.show()
        _press_escape(probe)
        app.processEvents()
        assert stale == []
        probe.close()
