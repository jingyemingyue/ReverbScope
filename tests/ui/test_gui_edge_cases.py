"""Slots and state that an offscreen audit found wanting: a settings file that
cannot be written, an interface that comes back under another index, Ctrl+2
from another page during an analysis, and the data-folder buttons with an
uncreatable home."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

from reverbscope.audio import backend as backend_module
from reverbscope.audio import inventory as inventory_module
from reverbscope.audio.backend import DeviceInfo
from reverbscope.ui import dev_tools
from reverbscope.ui.main_window import MainWindow
from reverbscope.ui.settings_dialog import SettingsDialog

pytestmark = pytest.mark.gui


@pytest.fixture(scope="module")
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _unwritable_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A home folder that cannot be created: its parent is a file."""
    blocker = tmp_path / "blocker"
    blocker.write_text("x", encoding="utf-8")
    home = blocker / "home"
    monkeypatch.setenv("REVERBSCOPE_HOME", str(home))
    return home


def test_ok_in_settings_with_an_unwritable_home_is_an_error_dialog_not_a_bug(
    app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _unwritable_home(tmp_path, monkeypatch)
    shown: list[tuple[str, str]] = []
    monkeypatch.setattr(
        QMessageBox,
        "critical",
        staticmethod(lambda _p, title, text, *a, **k: shown.append((title, text))),
    )
    dialog = SettingsDialog()
    dialog.theme.setCurrentIndex(dialog.theme.findData("dark"))
    dialog.accept()  # used to raise SessionError out of the slot
    assert shown and shown[0][0] == "Cannot save settings"
    assert "cannot create folder" in shown[0][1]
    assert dialog.result() != QDialog.DialogCode.Accepted.value
    dialog.close()


def _device(index: int, name: str, default: bool = False) -> DeviceInfo:
    return DeviceInfo(index, name, "Core Audio", 2, 2, 48000.0, default, default)


class _Interface:
    name = "test"

    def __init__(self) -> None:
        self.devices = [
            _device(0, "MacBook Pro Speakers", True),
            _device(1, "Scarlett 2i2"),
            _device(2, "Hypothetical Mic"),
        ]

    def list_devices(self) -> list[DeviceInfo]:
        return list(self.devices)

    def check_sample_rate(self, *_args: object, **_kwargs: object) -> None:
        return None


def test_the_chosen_interface_is_kept_when_it_comes_back_under_another_index(
    app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("REVERBSCOPE_HOME", str(tmp_path / "home"))
    interface = _Interface()
    monkeypatch.setattr(backend_module, "get_backend", lambda name=None: interface)
    real_build = inventory_module.build_inventory
    monkeypatch.setattr(
        inventory_module,
        "build_inventory",
        lambda backend, **kw: real_build(backend, probe_rates=False, platform="darwin"),
    )
    window = MainWindow()
    window.show()
    window.show_mode("standalone")
    page = window.standalone
    page.input_device.setCurrentIndex(page.input_device.findData(1))
    page.output_device.setCurrentIndex(page.output_device.findData(1))
    # Another device unplugged: the Scarlett keeps its index.
    interface.devices = [_device(0, "MacBook Pro Speakers", True), _device(1, "Scarlett 2i2")]
    page.refresh_devices()
    assert page.input_device.currentData() == 1 and page.output_device.currentData() == 1
    # Plugged in again, the Scarlett comes back under index 2: it is kept by name.
    interface.devices = [
        _device(0, "MacBook Pro Speakers", True),
        _device(1, "Hypothetical Mic"),
        _device(2, "Scarlett 2i2"),
    ]
    page.refresh_devices()
    assert page.input_device.currentData() == 2 and page.output_device.currentData() == 2
    # Its index taken by another device and its name gone: back to the defaults.
    interface.devices = [_device(0, "MacBook Pro Speakers", True), _device(2, "Hypothetical Mic")]
    page.refresh_devices()
    assert page.input_device.currentData() is None and page.output_device.currentData() is None
    window.close()


def test_switching_modes_from_another_page_leaves_a_busy_standalone_page_alone(
    app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("REVERBSCOPE_HOME", str(tmp_path / "home"))
    window = MainWindow()
    window.show()
    window.show_mode("demo")
    page = window.standalone
    assert page.demo_mode
    page.status.setText("Recorded. Analyzing...")
    monkeypatch.setattr(page, "is_busy", lambda: True)
    window.show_compare()
    window.show_mode("standalone")  # Ctrl+2 from Compare while the analysis runs
    assert window.stack.currentWidget() is page
    assert page.demo_mode
    assert page.status.text() == "Recorded. Analyzing..."
    window.close()


def test_open_data_folder_with_an_uncreatable_home_warns_instead_of_raising(
    app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = _unwritable_home(tmp_path, monkeypatch)
    opened: list[str] = []
    warned: list[tuple[str, str]] = []
    monkeypatch.setattr(
        QDesktopServices, "openUrl", staticmethod(lambda url: opened.append(url.toString()) or True)
    )
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        staticmethod(lambda _p, title, text, *a, **k: warned.append((title, text))),
    )
    window = MainWindow()
    window.show()
    window._open_data_folder()
    report = dev_tools.EnvironmentReport("fake", window)
    report._open_folder()
    assert opened == []
    assert [title for title, _text in warned] == ["Cannot open the data folder"] * 2
    assert all(str(home) in text for _title, text in warned)
    report.close()
    window.close()
    assert QUrl.fromLocalFile(str(home)).toString() not in opened


def test_a_worker_that_runs_out_of_memory_says_so_and_does_not_call_it_a_bug(
    app: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    from reverbscope.models.configuration import AnalysisSettings
    from reverbscope.ui import workers

    def boom(*_args: object, **_kwargs: object) -> object:
        raise MemoryError("Unable to allocate 5.15 GiB for an array")

    monkeypatch.setattr(workers, "analyze", boom)
    worker = workers.AnalysisWorker(object(), object(), AnalysisSettings())  # type: ignore[arg-type]
    shown: list[str] = []
    worker.failed.connect(shown.append)
    worker.run()  # on this thread: the slot runs at once
    assert shown == [workers.out_of_memory_text()]
    assert "not enough memory" in shown[0].lower() and "bug" not in shown[0]
    assert workers.gui_failure_text(MemoryError()) == workers.out_of_memory_text()
    assert workers.gui_failure_text(RuntimeError("x")) == workers.unexpected_error_text()
