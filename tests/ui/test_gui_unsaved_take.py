"""A live take is the only copy of its recording until it is saved.

New Measurement, Open Session, a click on a recent session and closing the
window dropped it without a word. They now ask: Save Session..., Discard or
Cancel. A demo take, a DAW recording (its file is on disk) and a saved
session never ask.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

from reverbscope.core.pipeline import Reference, analyze, synthetic_recording
from reverbscope.i18n import _, activate
from reverbscope.io.session_store import save_measurement
from reverbscope.models.configuration import SweepSettings
from reverbscope.models.session import MeasurementSession
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

    take = window.model.current()
    assert take is not None and take.unsaved
    window.show_home()  # New Measurement
    # Open Session adds the session beside the take: nothing is dropped, so
    # nothing is asked, and the take stays in the list.
    window.open_session_path(other)
    assert window.model.entry(take.key) is take and take.unsaved
    window.close()  # closing the window
    assert asked == [True, True]
    assert window.state.result is not None and window.state.unsaved_take is True
    assert window.stack.currentWidget() is window.views["overview"]
    assert window.isVisible()
    # Discard at last, so the window may close. (monkeypatch.undo() would also
    # undo the fixture that keeps the real ~/.reverbscope out of the test.)
    monkeypatch.setattr(window, "_ask_about_unsaved_take", lambda: True)
    window._discard_take()
    window.close()
    assert not window.isVisible()


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
    window.save_to(tmp_path / "saved")  # Save Session...
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


def test_getting_started_asks_before_showing_start_with_an_unsaved_take(
    app: QApplication, home: Path, short_sweep: SweepSettings, monkeypatch: pytest.MonkeyPatch
) -> None:
    window = MainWindow()
    window.show()
    _finish_take(window, short_sweep)
    assert window.state.unsaved_take is True
    asked: list[bool] = []
    monkeypatch.setattr(
        window, "_ask_about_unsaved_take", lambda: asked.append(True) or False, raising=True
    )
    before = window.stack.currentWidget()
    window.show_getting_started()
    assert asked == [True]
    assert window.stack.currentWidget() is before
    assert window.stack.currentWidget() is not window.home
    window.show_start_panel()
    assert asked == [True, True]
    assert window.stack.currentWidget() is not window.home
    window.state.unsaved_take = False
    window.close()


def test_close_while_a_real_standalone_sweep_sounds_prompts(
    app: QApplication, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Closing while a non-synthetic sweep still sounds must ask first."""
    import threading

    from reverbscope.audio.fake import FakeBackend
    from reverbscope.errors import MeasurementCancelledError

    release = threading.Event()
    real = FakeBackend.play_and_record

    def held(self, *args, cancel=None, **kwargs):  # type: ignore[no-untyped-def]
        while not release.wait(0.01):
            if cancel is not None and cancel.is_set():
                raise MeasurementCancelledError("stopped")
        return real(self, *args, cancel=cancel, **kwargs)

    monkeypatch.setattr(FakeBackend, "play_and_record", held)
    window = MainWindow()
    window.show()
    # Demo starts without level-ack; then treat the sounding take as live so
    # _pending_memory_recording must fire (sweep stage: recording still None).
    window.show_mode("demo")
    app.processEvents()
    page = window.standalone
    page.duration.setValue(1.0)
    page.run_button.click()
    app.processEvents()
    assert page.is_busy()
    page.demo_mode = False
    page._take_synthetic = False
    assert window.state.recording is None
    asked: list[bool] = []
    monkeypatch.setattr(
        window, "_ask_about_unsaved_take", lambda: asked.append(True) or False, raising=True
    )
    window.close()
    assert asked == [True]
    assert window.isVisible()
    release.set()
    worker = page._measure_worker
    if worker is not None:
        elapsed = 0
        while worker.isRunning() and elapsed < 5000:
            app.processEvents()
            worker.wait(20)
            elapsed += 20
    page._take_synthetic = True
    page.demo_mode = True
    monkeypatch.setattr(window.standalone, "is_busy", lambda: False)
    window.close()


def test_close_while_standalone_post_record_analysis_prompts(
    app: QApplication, home: Path, short_sweep: SweepSettings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Closing during post-record analysis must ask: the recording is only in memory."""
    window = MainWindow()
    window.show()
    recording, _result = _take(short_sweep)
    window.standalone.demo_mode = False
    window.standalone._take_synthetic = False
    window.state.recording = recording
    window.state.recording_path = None
    window.state.result = None
    monkeypatch.setattr(window.standalone, "is_busy", lambda: True)
    asked: list[bool] = []
    monkeypatch.setattr(
        window, "_ask_about_unsaved_take", lambda: asked.append(True) or False, raising=True
    )
    window.close()
    assert asked == [True]
    assert window.isVisible()

    # Discard path: generation bump so a late result cannot revive the take.
    def discard_ok() -> bool:
        window._discard_take()
        return True

    monkeypatch.setattr(window, "_ask_about_unsaved_take", discard_ok)
    gen = window.state.generation
    assert window._leave_take() is True
    assert window.state.generation == gen + 1
    window.state.unsaved_take = False
    window.standalone._take_synthetic = True
    monkeypatch.setattr(window.standalone, "is_busy", lambda: False)
    window.close()


def test_pending_analysis_dialog_omits_save_without_a_result(
    app: QApplication, home: Path, short_sweep: SweepSettings, monkeypatch: pytest.MonkeyPatch
) -> None:
    window = MainWindow()
    window.show()
    recording, _result = _take(short_sweep)
    window.standalone.demo_mode = False
    window.standalone._take_synthetic = False
    window.state.recording = recording
    window.state.recording_path = None
    window.state.result = None
    monkeypatch.setattr(window.standalone, "is_busy", lambda: True)
    seen: list[str] = []

    from PySide6.QtWidgets import QMessageBox as RealBox

    class SpyBox(RealBox):
        def exec(self) -> int:
            labels = [btn.text() for btn in self.buttons()]
            seen.extend([self.windowTitle(), self.text(), *labels])
            self.reject()
            return int(RealBox.DialogCode.Rejected)

    monkeypatch.setattr("reverbscope.ui.main_window.QMessageBox", SpyBox)
    assert window._ask_about_unsaved_take() is False
    assert _("Save Session...") not in seen
    assert _("Discard") in seen and _("Cancel") in seen
    window.standalone._take_synthetic = True
    monkeypatch.setattr(window.standalone, "is_busy", lambda: False)
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
