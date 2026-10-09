"""Slots and state that an offscreen audit found wanting: a settings file that
cannot be written, the theme switch on the Project page, the walkthrough card
within a run, an interface that comes back under another index, the Project
page's profile after a saved take, Ctrl+2 from another page during an analysis,
and the data-folder buttons with an uncreatable home."""

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
from reverbscope.audio.fake import make_rir
from reverbscope.core.pipeline import Reference, analyze, synthetic_recording
from reverbscope.io.project_store import add_session, save_project
from reverbscope.io.session_store import save_measurement
from reverbscope.models.configuration import SweepSettings
from reverbscope.models.project import Project
from reverbscope.models.result import AnalysisResult
from reverbscope.models.session import MeasurementSession
from reverbscope.settings import UserSettings, save_settings
from reverbscope.ui import dev_tools
from reverbscope.ui.main_window import MainWindow
from reverbscope.ui.settings_dialog import SettingsDialog
from reverbscope.ui.theme import DARK_TOKENS, LIGHT_TOKENS, apply_application_chrome
from reverbscope.ui.widgets import FindingCard

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


def _result(short_sweep: SweepSettings, rt60_s: float, seed: int) -> AnalysisResult:
    rate = short_sweep.sample_rate
    take = synthetic_recording(
        short_sweep, make_rir(rate, rt60_s=rt60_s, seed=seed), noise_rms=1e-5
    )
    return analyze(take, Reference.from_settings(short_sweep))


def _project_with_takes(
    folder: Path, short_sweep: SweepSettings, takes: list[tuple[str, str, str, float]]
) -> Path:
    """``takes``: (folder name, position, profile, RT60) in creation order."""
    save_project(folder, Project(name="Booth"))
    for n, (name, position, profile, rt60) in enumerate(takes):
        session = MeasurementSession(
            created_at=f"2026-01-0{n + 1}T10:00:00+00:00",
            room_name="Booth",
            measurement_position=position,
            recording_profile=profile,
        )
        save_measurement(
            folder / name, session, _result(short_sweep, rt60, n), copy_recording=False
        )
        add_session(folder, folder / name, position=position)
    return folder


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


def test_the_project_page_follows_the_theme_switch(
    app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, short_sweep: SweepSettings
) -> None:
    monkeypatch.setenv("REVERBSCOPE_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("REVERBSCOPE_COLOR_SCHEME", raising=False)
    save_settings(UserSettings(theme="light"))
    apply_application_chrome(app)
    project = _project_with_takes(
        tmp_path / "booth", short_sweep, [("a-1", "A", "vocal", 0.35), ("b-1", "B", "vocal", 0.9)]
    )
    window = MainWindow()
    window.show()
    window.show_project(project)
    page = window.project

    def card_styles() -> list[str]:
        return [
            page.position_rows.itemAt(i).widget().styleSheet()
            for i in range(page.position_rows.count())
            if isinstance(page.position_rows.itemAt(i).widget(), FindingCard)
        ]

    light = {LIGHT_TOKENS[k] for k in LIGHT_TOKENS if k.endswith("_soft")}
    dark = {DARK_TOKENS[k] for k in DARK_TOKENS if k.endswith("_soft")}
    before = card_styles()
    assert before and any(colour in before[0] for colour in light)
    save_settings(UserSettings(theme="dark"))
    window.restyle()
    after = card_styles()
    assert after and any(colour in after[0] for colour in dark)
    assert not any(colour in after[0] for colour in light)
    window.close()
    save_settings(UserSettings(theme="light"))
    apply_application_chrome(app)


def test_a_dismissed_walkthrough_stays_hidden_for_the_run_without_a_settings_file(
    app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _unwritable_home(tmp_path, monkeypatch)
    window = MainWindow()
    window.show()
    window.show_home()
    assert window.home.walkthrough.isVisibleTo(window.home)
    window.home.dismiss_walkthrough()  # the settings file cannot record it
    assert not window.home.walkthrough.isVisibleTo(window.home)
    window.show_home()  # used to read the (unwritten) settings and show it again
    assert not window.home.walkthrough.isVisibleTo(window.home)
    window.show_getting_started()
    assert window.home.walkthrough.isVisibleTo(window.home)
    window.close()


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


def test_the_project_page_follows_the_newest_take_until_the_user_chooses_a_profile(
    app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, short_sweep: SweepSettings
) -> None:
    monkeypatch.setenv("REVERBSCOPE_HOME", str(tmp_path / "home"))
    project = _project_with_takes(tmp_path / "booth", short_sweep, [("a-1", "A", "vocal", 0.35)])
    window = MainWindow()
    window.show()
    window.show_project(project)
    page = window.project
    assert page.profile.currentData() == "vocal"
    # A take with another profile is saved into the project (the Results page's
    # Project button then shows the page again without a path).
    session = MeasurementSession(
        created_at="2026-02-01T10:00:00+00:00",
        room_name="Booth",
        measurement_position="B",
        recording_profile="drums",
    )
    save_measurement(project / "b-1", session, _result(short_sweep, 0.9, 2), copy_recording=False)
    add_session(project, project / "b-1", position="B")
    window.show_project()
    assert page.profile.currentData() == "drums"
    # The user's own choice is kept across the same reload.
    page.profile.setCurrentIndex(page.profile.findData("generic"))
    window.show_project()
    assert page.profile.currentData() == "generic"
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


def _step_buttons_overlap_or_leave_the_card(window: MainWindow) -> list[str]:
    from PySide6.QtWidgets import QPushButton

    card = window.home.walkthrough
    buttons = [b for b in card.findChildren(QPushButton) if b.isVisible()]
    rects = {b: b.rect().translated(b.mapTo(card, b.rect().topLeft())) for b in buttons}
    problems = []
    for index, first in enumerate(buttons):
        for second in buttons[index + 1 :]:
            if rects[first].intersects(rects[second]):
                problems.append(f"{first.text()!r} overlaps {second.text()!r}")
    for button, rect in rects.items():
        if rect.bottom() > card.height() or rect.right() > card.width():
            problems.append(f"{button.text()!r} extends beyond the card")
    return problems


@pytest.mark.parametrize("size", [(960, 640), (1180, 800), (1366, 700)])
def test_a_short_window_scrolls_home_and_does_not_squeeze_the_first_measurement_card(
    app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, size: tuple[int, int]
) -> None:
    """At 960x640 (the window's own minimum) and on 1366x768 laptops the card's
    three step buttons overlapped and its last row was cut off, because the
    Home page had no scroll area to give the card the height it needs."""
    monkeypatch.setenv("REVERBSCOPE_HOME", str(tmp_path / "home"))
    apply_application_chrome(app)
    window = MainWindow()
    window.resize(*size)
    window.show()
    window.show_home()
    for _ in range(10):
        app.processEvents()
    card = window.home.walkthrough
    assert card.isVisible()
    assert _step_buttons_overlap_or_leave_the_card(window) == []
    # The card keeps the height its content needs; the page scrolls instead.
    assert card.height() >= card.minimumSizeHint().height()
    scroll = window.home.scroll
    body = scroll.widget()
    assert body.height() >= body.minimumSizeHint().height()
    if body.height() > scroll.viewport().height():
        # Everything below the fold can be reached.
        assert scroll.verticalScrollBar().maximum() >= body.height() - scroll.viewport().height()
    window.close()
