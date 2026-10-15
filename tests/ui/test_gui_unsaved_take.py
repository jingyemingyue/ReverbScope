"""A live take is the only copy of its recording until it is saved.

New Measurement, Open Session, a click on a recent session and closing the
window dropped it without a word. They now ask: Save Session..., Discard or
Cancel. A demo take, a DAW recording (its file is on disk) and a saved
session never ask.
"""

from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

from reverbscope.core.pipeline import Reference, analyze, synthetic_recording
from reverbscope.errors import SessionError
from reverbscope.i18n import _, activate
from reverbscope.io.session_store import load_measurement, save_measurement
from reverbscope.io.wav import read_wav, write_wav
from reverbscope.models.audio import AudioSignal
from reverbscope.models.configuration import SweepSettings
from reverbscope.models.session import MeasurementSession
from reverbscope.ui import pages
from reverbscope.ui.main_window import MainWindow
from tests.conftest import make_rir

pytestmark = pytest.mark.gui


@pytest.fixture(scope="module")
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "home"
    monkeypatch.setenv("REVERBSCOPE_HOME", str(path))
    return path


def _take(short_sweep: SweepSettings):  # type: ignore[no-untyped-def]
    recording = synthetic_recording(short_sweep, make_rir(short_sweep.sample_rate, rt60_s=0.3))
    return recording, analyze(recording, Reference.from_settings(short_sweep))


def _finish_take(window: MainWindow, short_sweep: SweepSettings, *, demo: bool = False) -> None:
    """What the Standalone page does when a take's analysis comes back."""
    recording, result = _take(short_sweep)
    page = window.standalone
    page.demo_mode = demo
    window.state.recording = recording
    window.state.recording_path = None
    page._stale = lambda: False  # type: ignore[method-assign]
    page._on_success(result)
    window.show_results()


def test_a_finished_live_take_is_unsaved_but_a_demo_and_a_daw_file_are_not(
    app: QApplication, home: Path, short_sweep: SweepSettings, tmp_path: Path
) -> None:
    window = MainWindow()
    window.show()
    _finish_take(window, short_sweep)
    assert window.state.unsaved_take is True and window.state.result is not None
    window.state.reset()
    assert window.state.unsaved_take is False
    _finish_take(window, short_sweep, demo=True)
    assert window.state.unsaved_take is False
    window.state.reset()
    # A recording that is a file on disk (Universal DAW Mode) is not "only in memory".
    window.state.recording_path = tmp_path / "take.wav"
    recording, result = _take(short_sweep)
    window.state.recording = recording
    window.standalone.demo_mode = False
    window.standalone._stale = lambda: False  # type: ignore[method-assign]
    window.standalone._on_success(result)
    assert window.state.unsaved_take is False
    window.close()


def test_cancel_keeps_the_take_on_every_way_out(
    app: QApplication,
    home: Path,
    short_sweep: SweepSettings,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window = MainWindow()
    window.show()
    _finish_take(window, short_sweep)
    asked: list[bool] = []
    monkeypatch.setattr(
        window, "_ask_about_unsaved_take", lambda: asked.append(True) or False, raising=True
    )
    other = tmp_path / "other"
    recording, result = _take(short_sweep)
    save_measurement(other, MeasurementSession(), result, recording=recording)

    window.show_home()  # New Measurement
    window.open_session_path(other)  # Open Session / a recent-session click
    window.close()  # closing the window
    assert asked == [True, True, True]
    assert window.state.result is not None and window.state.unsaved_take is True
    assert window.stack.currentWidget() is window.results
    assert window.isVisible()
    monkeypatch.undo()
    window.state.unsaved_take = False
    window.close()


def test_discard_lets_the_take_go(
    app: QApplication, home: Path, short_sweep: SweepSettings, monkeypatch: pytest.MonkeyPatch
) -> None:
    window = MainWindow()
    window.show()
    _finish_take(window, short_sweep)
    monkeypatch.setattr(window, "_ask_about_unsaved_take", lambda: True)
    window.show_home()
    assert window.state.result is None and window.state.unsaved_take is False
    assert window.stack.currentWidget() is window.home
    window.close()


def test_a_saved_take_and_a_demo_take_never_ask(
    app: QApplication, home: Path, short_sweep: SweepSettings, tmp_path: Path, monkeypatch
) -> None:
    window = MainWindow()
    window.show()
    monkeypatch.setattr(
        window, "_ask_about_unsaved_take", lambda: pytest.fail("asked about a take that is safe")
    )
    _finish_take(window, short_sweep, demo=True)
    window.show_home()
    _finish_take(window, short_sweep)
    window.results.save_to(tmp_path / "saved")  # Save Session...
    assert window.state.unsaved_take is False
    assert (tmp_path / "saved" / "recording.wav").is_file()
    window.show_home()
    window.close()


def _title_shown(title: str, expected: str) -> None:
    """macOS message boxes carry no window title (Qt drops it, as the platform
    guidelines require); everywhere else the dialog is named."""
    assert title == ("" if sys.platform == "darwin" else expected)


def _click_when_asked(button_text: str, seen: list[str] | None = None) -> list[str]:
    """Press a button of the dialog that opens while the event loop runs.

    Returns the list of problems (checked by the test afterwards). A dialog this
    cannot answer is rejected after five seconds, so a failure never hangs the
    suite on a modal dialog.
    """
    problems: list[str] = []
    tries = {"left": 300}

    def boxes() -> list[QMessageBox]:
        return [
            w
            for w in QApplication.topLevelWidgets()
            if isinstance(w, QMessageBox) and w.isVisible()
        ]

    def press() -> None:
        found = boxes()
        if not found:
            tries["left"] -= 1
            if tries["left"] > 0:
                QTimer.singleShot(10, press)
            else:
                problems.append("no dialog appeared")
            return
        box = found[0]
        if seen is not None:
            seen.extend([box.windowTitle(), box.text(), *[b.text() for b in box.buttons()]])
        for button in box.buttons():
            if button.text() == button_text:
                button.click()
                return
        problems.append(f"no {button_text!r} button in {[b.text() for b in box.buttons()]}")
        box.reject()

    def watchdog() -> None:
        for box in boxes():
            problems.append("a dialog was still open after 5 s")
            box.reject()

    QTimer.singleShot(0, press)
    QTimer.singleShot(5000, watchdog)
    return problems


def test_the_real_dialog_cancel_discard_and_save(
    app: QApplication,
    home: Path,
    short_sweep: SweepSettings,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window = MainWindow()
    window.show()
    _finish_take(window, short_sweep)
    seen: list[str] = []

    problems = _click_when_asked("Cancel", seen)
    window.show_home()
    assert problems == []
    assert window.state.result is not None, "Cancel must keep the take"
    _title_shown(seen[0], "Unsaved measurement")
    assert "exists only in memory" in seen[1]
    # Qt orders the buttons by role and platform, so compare them as a set.
    assert sorted(seen[2:]) == sorted(["Save Session...", "Discard", "Cancel"])

    # Save Session... whose folder chooser is cancelled keeps the take too.
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", staticmethod(lambda *a, **k: ""))
    problems = _click_when_asked("Save Session...")
    window.show_home()
    assert problems == []
    assert window.state.result is not None and window.state.unsaved_take is True

    # ... and one that is carried out lets it go, with the session on disk.
    target = tmp_path / "kept"
    target.mkdir()
    monkeypatch.setattr(
        QFileDialog, "getExistingDirectory", staticmethod(lambda *a, **k: str(target))
    )
    problems = _click_when_asked("Save Session...")
    window.show_home()
    assert problems == []
    assert (target / "session.json").is_file() and (target / "recording.wav").is_file()
    assert window.state.result is None and window.stack.currentWidget() is window.home

    _finish_take(window, short_sweep)
    problems = _click_when_asked("Discard")
    window.show_home()
    assert problems == []
    assert window.state.result is None and window.state.unsaved_take is False
    window.close()


def test_the_dialog_is_in_chinese_in_the_chinese_interface(
    app: QApplication, home: Path, short_sweep: SweepSettings
) -> None:
    from tests.zh_tokens import english_words

    activate("zh_CN")
    try:
        window = MainWindow()
        window.show()
        _finish_take(window, short_sweep)
        seen: list[str] = []
        problems = _click_when_asked("取消", seen)
        window.show_home()
        assert problems == []
        assert window.state.result is not None
        _title_shown(seen[0], "尚未保存的测量")
        assert _("Unsaved measurement") == "尚未保存的测量"
        assert sorted(seen[2:]) == sorted(["保存会话…", "放弃", "取消"])
        assert english_words(" ".join(seen)) == []
        window.state.unsaved_take = False
        window.close()
    finally:
        activate("en")


def _install_live_take(window: MainWindow, short_sweep: SweepSettings) -> AudioSignal:
    """A finished standalone take, through the real success path.

    The page's generation matches the window, so the stale check stays the
    real one (patching it would hide a later take).
    """
    recording, result = _take(short_sweep)
    page = window.standalone
    page.demo_mode = False
    window.state.recording = recording
    window.state.recording_path = None
    page._generation = window.state.generation
    page._on_success(result)
    window.state.session.room_name = "Old Room"
    window.show_results()
    assert window.state.unsaved_take is True
    return recording


def _kept(window: MainWindow) -> dict[str, object]:
    """Identity and scalars of the take. NumPy-bearing objects are not compared."""
    state = window.state
    return {
        "result": id(state.result),
        "recording": id(state.recording),
        "recording_path": state.recording_path,
        "reference": id(state.reference),
        "generation": state.generation,
        "unsaved": state.unsaved_take,
        "profile": state.profile,
        "analysis": state.analysis_settings,
        "session": state.session.to_dict(),
        "sweep": state.sweep_settings,
    }


def _prepare_daw(window: MainWindow, tmp_path: Path, short_sweep: SweepSettings) -> Path:
    """Select a sweep and a recording on the DAW page without touching the live take."""
    window.show_mode("universal_daw")
    page = window.daw
    page.sample_rate.setCurrentIndex(page.sample_rate.findData(short_sweep.sample_rate))
    page.duration.setValue(short_sweep.duration_s)
    page.generate_sweep_to(tmp_path / "sweep.wav")
    take = synthetic_recording(
        page.current_sweep_settings(), make_rir(short_sweep.sample_rate, rt60_s=0.3)
    )
    path = write_wav(tmp_path / "take.wav", take.samples, take.sample_rate, subtype="FLOAT")
    page.set_recording(path)
    return path


def _prepare_standalone(window: MainWindow, app: QApplication) -> None:
    """Demo mode: the fake backend, so a started take does not open a real device."""
    window.show_mode("demo")
    app.processEvents()
    window.standalone.duration.setValue(1.0)


def _forbid_new_workers(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("must not start")

    monkeypatch.setattr(pages, "AnalysisWorker", forbidden)
    monkeypatch.setattr(pages, "MeasureWorker", forbidden)


class _Question:
    """Answer the unsaved-take dialog that opens while ``exec`` runs.

    ``close`` and ``escape`` use the dialog itself. A button name is clicked.
    The token drops a timer that outlives the test, so it cannot click a later dialog.
    """

    def __init__(self, action: str, seen: list[str] | None = None) -> None:
        self.action = action
        self.seen = seen
        self.problems: list[str] = []
        self.tries = 100
        self.token = object()
        self.escape_button = ""
        self.default_button = ""
        QTimer.singleShot(0, self._press)
        QTimer.singleShot(5000, self._watchdog)

    def _alive(self) -> bool:
        return self.token is not None

    def _boxes(self) -> list[QMessageBox]:
        return [
            widget
            for widget in QApplication.topLevelWidgets()
            if isinstance(widget, QMessageBox) and widget.isVisible()
        ]

    def _press(self) -> None:
        if not self._alive():
            return
        found = self._boxes()
        if not found:
            self.tries -= 1
            if self.tries > 0:
                QTimer.singleShot(10, self._press)
            else:
                self.problems.append("no dialog appeared")
            return
        box = found[0]
        if self.seen is not None:
            self.seen.extend([box.windowTitle(), box.text(), *[b.text() for b in box.buttons()]])
        escape = box.escapeButton()
        default = box.defaultButton()
        self.escape_button = escape.text() if escape is not None else ""
        self.default_button = default.text() if default is not None else ""
        if self.action == "close":
            box.close()
            return
        if self.action == "escape":
            QTest.keyClick(box, Qt.Key.Key_Escape)
            return
        for button in box.buttons():
            if button.text() == self.action:
                button.click()
                return
        self.problems.append(f"no {self.action!r} button in {[b.text() for b in box.buttons()]}")
        box.reject()

    def _watchdog(self) -> None:
        if not self._alive():
            return
        for box in self._boxes():
            self.problems.append("a dialog was still open after 5 s")
            box.reject()

    def stop(self) -> None:
        self.token = None

    def wait_until_seen(self, app: QApplication) -> None:
        """If the start returned without a dialog, let the timer record that."""
        for _attempt in range(self.tries):
            if self.problems or self.escape_button or self.default_button:
                return
            app.processEvents()
            time.sleep(0.01)
        if not self.problems:
            self.problems.append("no dialog appeared")


def _close_quietly(window: MainWindow) -> None:
    window.state.unsaved_take = False
    window.standalone.shutdown_workers()
    window.daw.shutdown_workers()
    window.close()


def _start(window: MainWindow, entry: str, *, blocking: bool = False) -> None:
    if entry == "daw":
        window.daw.start_analysis(blocking=blocking)
    else:
        window.standalone.start_measurement()


@pytest.mark.parametrize("entry", ["daw", "standalone"])
@pytest.mark.parametrize("action", ["Cancel", "close", "escape"])
def test_entry_refuses_to_replace_an_unsaved_take(
    app: QApplication,
    home: Path,
    short_sweep: SweepSettings,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    entry: str,
    action: str,
) -> None:
    """Cancel, the window close button and Esc must not start a worker or touch the take."""
    window = MainWindow()
    window.show()
    _install_live_take(window, short_sweep)
    if entry == "daw":
        _prepare_daw(window, tmp_path, short_sweep)
    else:
        _prepare_standalone(window, app)
    before = _kept(window)
    question = _Question(action)
    _forbid_new_workers(monkeypatch)
    try:
        _start(window, entry)
        question.wait_until_seen(app)
        assert question.problems == []
        if action == "escape":
            assert question.escape_button == "Cancel"
            assert question.default_button == "Save Session..."
        assert _kept(window) == before
        assert window.daw._worker is None
        assert window.standalone._measure_worker is None
    finally:
        question.stop()
        _close_quietly(window)


@pytest.mark.parametrize("entry", ["daw", "standalone"])
def test_entry_cancelled_save_keeps_the_unsaved_take(
    app: QApplication,
    home: Path,
    short_sweep: SweepSettings,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    entry: str,
) -> None:
    window = MainWindow()
    window.show()
    _install_live_take(window, short_sweep)
    if entry == "daw":
        _prepare_daw(window, tmp_path, short_sweep)
    else:
        _prepare_standalone(window, app)
    before = _kept(window)
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", staticmethod(lambda *a, **k: ""))
    question = _Question("Save Session...")
    _forbid_new_workers(monkeypatch)
    try:
        _start(window, entry)
        question.wait_until_seen(app)
        assert question.problems == []
        assert _kept(window) == before
        assert window.daw._worker is None
        assert window.standalone._measure_worker is None
    finally:
        question.stop()
        _close_quietly(window)


@pytest.mark.parametrize("entry", ["daw", "standalone"])
def test_entry_failed_save_keeps_the_unsaved_take(
    app: QApplication,
    home: Path,
    short_sweep: SweepSettings,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    entry: str,
) -> None:
    window = MainWindow()
    window.show()
    _install_live_take(window, short_sweep)
    if entry == "daw":
        _prepare_daw(window, tmp_path, short_sweep)
    else:
        _prepare_standalone(window, app)
    before = _kept(window)
    target = tmp_path / "unsaved"
    target.mkdir()

    def broken(*_args: object, **_kwargs: object) -> None:
        raise SessionError("disk full")

    monkeypatch.setattr("reverbscope.ui.results.save_measurement", broken)
    monkeypatch.setattr(QMessageBox, "critical", lambda *a, **k: None)
    monkeypatch.setattr(
        QFileDialog, "getExistingDirectory", staticmethod(lambda *a, **k: str(target))
    )
    question = _Question("Save Session...")
    _forbid_new_workers(monkeypatch)
    try:
        _start(window, entry)
        question.wait_until_seen(app)
        assert question.problems == []
        assert _kept(window) == before
        assert not (target / "session.json").exists()
        assert window.daw._worker is None
    finally:
        question.stop()
        _close_quietly(window)


def test_entry_saved_take_is_what_daw_analysis_replaces(
    app: QApplication,
    home: Path,
    short_sweep: SweepSettings,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Save writes the live take, then the DAW analysis may replace it. Save does not claim."""
    window = MainWindow()
    window.show()
    old = _install_live_take(window, short_sweep)
    _prepare_daw(window, tmp_path, short_sweep)
    generation = window.state.generation
    target = tmp_path / "kept"
    target.mkdir()
    monkeypatch.setattr(
        QFileDialog, "getExistingDirectory", staticmethod(lambda *a, **k: str(target))
    )
    question = _Question("Save Session...")
    try:
        window.daw.start_analysis(blocking=True)
        app.processEvents()
        assert question.problems == []
        loaded = load_measurement(target)
        assert loaded.session.room_name == "Old Room"
        saved = read_wav(target / "recording.wav")
        assert np.allclose(saved.samples, old.samples)
        # One claim, from the analysis that was allowed to start. Not from Save.
        assert window.state.generation == generation + 1
        assert window.state.unsaved_take is False
        assert window.state.recording_path == tmp_path / "take.wav"
    finally:
        question.stop()
        _close_quietly(window)


def test_entry_saved_take_lets_standalone_start_without_claiming(
    app: QApplication,
    home: Path,
    short_sweep: SweepSettings,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """After Save, Run may start. It must not claim or clear anything before the take exists."""
    from reverbscope.audio.fake import FakeBackend
    from reverbscope.errors import MeasurementCancelledError

    release = threading.Event()
    real = FakeBackend.play_and_record

    def held(self, *args, cancel=None, **kwargs):  # type: ignore[no-untyped-def]
        while not release.wait(0.01):
            if cancel is not None and cancel.is_set():
                raise MeasurementCancelledError("stopped")
        if cancel is not None and cancel.is_set():
            raise MeasurementCancelledError("stopped")
        return real(self, *args, cancel=cancel, **kwargs)

    monkeypatch.setattr(FakeBackend, "play_and_record", held)
    window = MainWindow()
    window.show()
    old = _install_live_take(window, short_sweep)
    _prepare_standalone(window, app)
    generation = window.state.generation
    result_id = id(window.state.result)
    target = tmp_path / "kept"
    target.mkdir()
    monkeypatch.setattr(
        QFileDialog, "getExistingDirectory", staticmethod(lambda *a, **k: str(target))
    )
    question = _Question("Save Session...")
    try:
        window.standalone.start_measurement()
        assert question.problems == []
        assert (target / "session.json").is_file()
        saved = read_wav(target / "recording.wav")
        assert np.allclose(saved.samples, old.samples)
        assert window.state.generation == generation
        assert id(window.state.result) == result_id
        # Save already put the take on disk, so the flag is clear. Run did not claim.
        assert window.state.unsaved_take is False
        worker = window.standalone._measure_worker
        assert worker is not None and worker.isRunning()
        window.standalone.stop_measurement()
        worker.wait()
    finally:
        release.set()
        question.stop()
        _close_quietly(window)


def test_entry_discard_lets_daw_take_the_file_and_clears_unsaved(
    app: QApplication,
    home: Path,
    short_sweep: SweepSettings,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window = MainWindow()
    window.show()
    old = _install_live_take(window, short_sweep)
    recording_path = _prepare_daw(window, tmp_path, short_sweep)
    generation = window.state.generation
    question = _Question("Discard")
    try:
        window.daw.start_analysis(blocking=True)
        app.processEvents()
        assert question.problems == []
        assert window.state.recording is window.daw._recording
        assert window.state.recording is not old
        assert window.state.recording_path == recording_path
        assert window.state.unsaved_take is False
        assert window.state.generation == generation + 1
        monkeypatch.setattr(
            window,
            "_ask_about_unsaved_take",
            lambda: pytest.fail("the file on disk was still treated as only in memory"),
        )
        window.show_home()
        assert window.stack.currentWidget() is window.home
    finally:
        question.stop()
        _close_quietly(window)


def test_entry_preflight_refusal_keeps_the_unsaved_take(
    app: QApplication,
    home: Path,
    short_sweep: SweepSettings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Discard allows the run, but a refused preflight must not drop the live take."""
    window = MainWindow()
    window.show()
    _install_live_take(window, short_sweep)
    before = _kept(window)
    monkeypatch.setattr(window.standalone, "_preflight", lambda *_a, **_k: None)
    question = _Question("Discard")
    _forbid_new_workers(monkeypatch)
    try:
        window.standalone.start_measurement()
        question.wait_until_seen(app)
        assert question.problems == []
        assert _kept(window) == before
        assert window.standalone._measure_worker is None
    finally:
        question.stop()
        _close_quietly(window)


def test_entry_standalone_stop_keeps_the_unsaved_take(
    app: QApplication,
    home: Path,
    short_sweep: SweepSettings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Run does not clear the unsaved flag. Stop leaves the old take protected."""
    from reverbscope.audio.fake import FakeBackend
    from reverbscope.errors import MeasurementCancelledError

    release = threading.Event()
    real = FakeBackend.play_and_record

    def held(self, *args, cancel=None, **kwargs):  # type: ignore[no-untyped-def]
        while not release.wait(0.01):
            if cancel is not None and cancel.is_set():
                raise MeasurementCancelledError("stopped")
        if cancel is not None and cancel.is_set():
            raise MeasurementCancelledError("stopped")
        return real(self, *args, cancel=cancel, **kwargs)

    monkeypatch.setattr(FakeBackend, "play_and_record", held)
    window = MainWindow()
    window.show()
    _install_live_take(window, short_sweep)
    _prepare_standalone(window, app)
    before = _kept(window)
    started = _Question("Discard")
    again: _Question | None = None
    try:
        window.standalone.start_measurement()
        assert started.problems == []
        worker = window.standalone._measure_worker
        assert worker is not None and worker.isRunning()
        assert _kept(window) == before
        window.standalone.stop_measurement()
        worker.wait()
        app.processEvents()
        assert _kept(window) == before
        started.stop()
        again = _Question("Cancel")
        _forbid_new_workers(monkeypatch)
        window.standalone.start_measurement()
        again.wait_until_seen(app)
        assert again.problems == []
        assert window.standalone._measure_worker is worker
        assert _kept(window) == before
    finally:
        release.set()
        started.stop()
        if again is not None:
            again.stop()
        _close_quietly(window)


@pytest.mark.parametrize("kind", ["saved", "demo"])
def test_entry_saved_take_is_not_asked(
    app: QApplication,
    home: Path,
    short_sweep: SweepSettings,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    kind: str,
) -> None:
    window = MainWindow()
    window.show()
    if kind == "demo":
        _finish_take(window, short_sweep, demo=True)
        assert window.state.unsaved_take is False
    else:
        _install_live_take(window, short_sweep)
        window.results.save_to(tmp_path / "saved")
        assert window.state.unsaved_take is False
    monkeypatch.setattr(
        window,
        "_ask_about_unsaved_take",
        lambda: pytest.fail("asked about a take that is already safe"),
    )
    _prepare_daw(window, tmp_path / kind, short_sweep)
    window.daw.start_analysis(blocking=True)
    app.processEvents()
    assert window.state.result is not None
    assert window.daw._worker is not None
    _close_quietly(window)


@pytest.mark.parametrize("entry", ["daw", "standalone"])
def test_entry_question_is_chinese(
    app: QApplication,
    home: Path,
    short_sweep: SweepSettings,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    entry: str,
) -> None:
    from tests.zh_tokens import english_words

    activate("zh_CN")
    try:
        window = MainWindow()
        window.show()
        _install_live_take(window, short_sweep)
        if entry == "daw":
            _prepare_daw(window, tmp_path, short_sweep)
        else:
            _prepare_standalone(window, app)
        before = _kept(window)
        seen: list[str] = []
        question = _Question("取消", seen)
        _forbid_new_workers(monkeypatch)
        try:
            _start(window, entry)
            question.wait_until_seen(app)
            assert question.problems == []
            assert question.escape_button == "取消"
            assert "只存在于内存中" in seen[1]
            assert english_words(" ".join(seen)) == []
            assert _kept(window) == before
        finally:
            question.stop()
            _close_quietly(window)
    finally:
        activate("en")
