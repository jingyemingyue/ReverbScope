"""File ▸ Close Project and Help ▸ Getting started must not interrupt BUSY."""

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


def test_getting_started_is_blocked_while_a_take_runs(app: QApplication, held_take) -> None:
    window = MainWindow()
    window.show()
    window.show_mode("demo")
    app.processEvents()
    page = window.standalone
    page.duration.setValue(1.0)
    try:
        page.run_button.click()
        assert page.is_busy()
        assert not window.getting_started_action.isEnabled()
        before = window.stack.currentWidget()
        window.show_getting_started()
        app.processEvents()
        assert window.stack.currentWidget() is before
        assert window.stack.currentWidget() is not window.home
    finally:
        held_take.set()
        _settle(app, page._measure_worker)
        _settle(app, page._analysis_worker)
    window.close()


def test_environment_report_is_blocked_while_a_take_runs(
    app: QApplication, held_take, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A modal Report over a sounding take steals Esc from Stop."""
    import reverbscope.ui.dev_tools as dev_tools
    import reverbscope.ui.settings_dialog as settings_mod

    reports: list[object] = []
    settings: list[object] = []

    class _FakeReport:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            reports.append(self)

        def exec(self) -> int:
            return 0

    class _FakeSettings:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            settings.append(self)

        def exec(self) -> int:
            return 0

    monkeypatch.setattr(dev_tools, "EnvironmentReport", _FakeReport)
    monkeypatch.setattr(settings_mod, "SettingsDialog", _FakeSettings)

    window = MainWindow()
    window.show()
    window.show_mode("demo")
    app.processEvents()
    page = window.standalone
    page.duration.setValue(1.0)
    try:
        page.run_button.click()
        assert page.is_busy()
        assert not window.report_action.isEnabled()
        assert not window.navigator.report_button.isEnabled()
        assert not window.navigator.help_button.isEnabled()
        window.show_environment_report()
        window.show_settings()
        app.processEvents()
        assert reports == []
        assert settings == []
    finally:
        held_take.set()
        _settle(app, page._measure_worker)
        _settle(app, page._analysis_worker)
    assert window.report_action.isEnabled()
    assert window.navigator.report_button.isEnabled()
    window.close()


def test_compare_is_blocked_while_a_take_runs(app: QApplication, held_take) -> None:
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
        assert not window.compare_action.isEnabled()
        assert not window.view_actions["compare"].isEnabled()
        window.show_compare()
        window.show_view("compare")
        app.processEvents()
        assert window.stack.currentWidget() is before
    finally:
        held_take.set()
        _settle(app, page._measure_worker)
        _settle(app, page._analysis_worker)
    assert window.compare_action.isEnabled()
    assert window.view_actions["compare"].isEnabled()
    window.close()


def test_about_is_blocked_while_a_take_runs(
    app: QApplication, held_take, monkeypatch: pytest.MonkeyPatch
) -> None:
    from reverbscope.ui import main_window as mw

    opened: list[object] = []

    class _FakeBox:
        def exec(self) -> int:
            opened.append(self)
            return 0

    monkeypatch.setattr(mw, "about_box", lambda _parent=None: _FakeBox())

    window = MainWindow()
    window.show()
    window.show_mode("demo")
    app.processEvents()
    page = window.standalone
    page.duration.setValue(1.0)
    try:
        page.run_button.click()
        assert page.is_busy()
        assert not window.about_action.isEnabled()
        window._about()
        app.processEvents()
        assert opened == []
    finally:
        held_take.set()
        _settle(app, page._measure_worker)
        _settle(app, page._analysis_worker)
    window.close()


def test_navigator_rename_is_blocked_while_a_take_runs(
    app: QApplication, held_take, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rename dialog over a sounding take would steal Esc from Stop."""
    from PySide6.QtWidgets import QInputDialog

    asked: list[str] = []

    def boom(*_args: object, **_kwargs: object) -> tuple[str, bool]:
        asked.append("rename")
        return ("x", True)

    monkeypatch.setattr(QInputDialog, "getText", staticmethod(boom))
    window = MainWindow()
    window.show()
    window.show_mode("demo")
    app.processEvents()
    page = window.standalone
    page.duration.setValue(1.0)
    try:
        page.run_button.click()
        assert page.is_busy()
        window.navigator._rename("any-key")
        app.processEvents()
        assert asked == []
        assert window.save_take() is False
    finally:
        held_take.set()
        _settle(app, page._measure_worker)
        _settle(app, page._analysis_worker)
    window.close()


def test_device_inspector_is_blocked_while_a_take_runs(
    app: QApplication, held_take, monkeypatch: pytest.MonkeyPatch
) -> None:
    import reverbscope.ui.dev_tools as dev_tools

    opened: list[object] = []

    class _FakeInspector:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            opened.append(self)

        def exec(self) -> int:
            return 0

    monkeypatch.setattr(dev_tools, "DeviceInspector", _FakeInspector)
    window = MainWindow()
    window.show()
    window.show_mode("demo")
    app.processEvents()
    page = window.standalone
    page.duration.setValue(1.0)
    try:
        page.run_button.click()
        assert page.is_busy()
        if window.device_inspector_action is not None:
            assert not window.device_inspector_action.isEnabled()
        window.show_device_inspector()
        app.processEvents()
        assert opened == []
    finally:
        held_take.set()
        _settle(app, page._measure_worker)
        _settle(app, page._analysis_worker)
    window.close()


def test_close_project_is_disabled_while_measure_busy(
    app: QApplication, tmp_path: Path, held_analysis
) -> None:
    window = MainWindow()
    window.show()
    window.show_view("project")
    assert window.project.create_project(tmp_path / "room")
    assert window.model.wait_until_loaded()
    project_dir = window.model.project_path
    assert project_dir is not None

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
        assert page.is_busy()
        assert not window.close_project_action.isEnabled()
        window.close_project()
        app.processEvents()
        assert window.model.project_path == project_dir
        assert page._worker is not None and page._worker.isRunning()
    finally:
        held_analysis.set()
        _settle(app, page._worker)
    window.close()
