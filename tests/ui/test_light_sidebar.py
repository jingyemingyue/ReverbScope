"""The light sidebar GUI (docs/design/light-sidebar): one icon family, the
output-safety rules of SPEC §8.4 (OUT-1…5), the level acknowledgement
(SAFE), the busy lock (BUSY) and unclipped button text at the two
acceptance sizes, in English and Chinese."""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QAbstractButton, QApplication, QScrollArea

from reverbscope.audio import backend as backend_module
from reverbscope.audio import inventory as inventory_module
from reverbscope.audio.backend import DeviceInfo
from reverbscope.ui import icons
from reverbscope.ui.main_window import MainWindow

pytestmark = pytest.mark.gui

SRC = Path(__file__).resolve().parents[2] / "src" / "reverbscope" / "ui"


@pytest.fixture(scope="module")
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


class _Interface:
    """A Mac with its speakers (the system default) and an interface."""

    name = "test"

    def list_devices(self) -> list[DeviceInfo]:
        return [
            DeviceInfo(0, "MacBook Pro Speakers", "Core Audio", 0, 2, 48000.0, False, True),
            DeviceInfo(1, "MacBook Pro Microphone", "Core Audio", 1, 0, 48000.0, True, False),
            DeviceInfo(2, "Studio Interface 2x2", "Core Audio", 2, 2, 48000.0, False, False),
        ]

    def check_sample_rate(self, *_args: object, **_kwargs: object) -> None:
        return None


@pytest.fixture
def interface(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("REVERBSCOPE_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("REVERBSCOPE_AUDIO_BACKEND", raising=False)
    real_build = inventory_module.build_inventory
    monkeypatch.setattr(backend_module, "get_backend", lambda name=None: _Interface())
    monkeypatch.setattr(
        inventory_module,
        "build_inventory",
        lambda backend, **kw: real_build(backend, probe_rates=False, platform="darwin"),
    )


def test_every_icon_the_gui_names_is_in_the_lucide_set(app: QApplication) -> None:
    named = set()
    for path in SRC.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        named.update(re.findall(r'icons\.(?:icon|pixmap)\(\s*"([a-z-]+)"', text))
        named.update(re.findall(r'_(?:row_button|tool_button|icon_switch)\(\s*"([a-z-]+)"', text))
    assert named, "the scan found no icon names"
    assert named <= set(icons.LUCIDE), named - set(icons.LUCIDE)
    for name in icons.LUCIDE:
        image = icons.pixmap(name, "#177e89", 16, 2.0)
        assert not image.isNull() and image.width() == 32
        assert not image.toImage().allGray() or name == "x", name


def test_the_lucide_notice_ships_with_the_desktop_bundle() -> None:
    import importlib.util

    script = Path(__file__).resolve().parents[2] / "scripts" / "build_license_bundle.py"
    spec = importlib.util.spec_from_file_location("build_license_bundle", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    notice = module.KNOWN_NOTICES["lucide"]
    assert "ISC License" in notice and "Cole Bemis" in notice
    assert "lucide" in module.GUI_NOTICES


def test_no_output_is_preselected_and_start_says_why(app: QApplication, interface: None) -> None:
    """OUT-2 / OUT-4: the system default output is not offered or chosen,
    Start (page, strip) is off with the reason beside it, and nothing starts."""
    window = MainWindow()
    window.show()
    window.show_mode("standalone")
    page = window.standalone
    page.host_api.setCurrentIndex(page.host_api.findData("Core Audio"))
    texts = [page.output_device.itemText(i) for i in range(page.output_device.count())]
    assert not any(text == "System default" for text in texts)
    assert page.output_device.currentData() is None
    assert not page.run_button.isEnabled()
    assert not window.strip.start_button.isEnabled()
    reason = page.readiness_reason()
    assert "output" in reason
    assert page.readiness.text() == reason
    assert window.strip.status.text() == reason
    assert page.steps.states[0] == "current" and page.steps.states[2] == "locked"
    page.start_measurement()  # Ctrl+Return or a stale click: nothing plays
    assert page._measure_worker is None
    page.output_device.setCurrentIndex(page.output_device.findData(2))
    assert page.run_button.isEnabled() and window.strip.start_button.isEnabled()
    assert page.steps.states == ("done", "done", "current")
    window.close()


def test_any_level_change_asks_for_the_acknowledgement_again(
    app: QApplication, interface: None
) -> None:
    """SAFE: above −12 dBFS Start waits for the box, the reason quotes the box
    word for word, and any level change, New Measurement and Stop clear it."""
    window = MainWindow()
    window.show()
    window.show_mode("standalone")
    page = window.standalone
    page.output_device.setCurrentIndex(page.output_device.findData(2))
    assert page.safe_band.isHidden()
    page.level.setValue(-6.0)
    assert not page.safe_band.isHidden()
    assert not page.run_button.isEnabled()
    assert page.acknowledge.text() in page.readiness.text()
    page.acknowledge.setChecked(True)
    assert page.run_button.isEnabled()
    page.level.setValue(-7.0)  # still above the line: asked again
    assert not page.acknowledge.isChecked() and not page.run_button.isEnabled()
    page.acknowledge.setChecked(True)
    window.show_home()
    assert not page.acknowledge.isChecked()
    page.level.setValue(-20.0)
    assert page.safe_band.isHidden() and not page.acknowledge.isEnabled()
    window.close()


def test_a_running_take_locks_what_would_interrupt_it(app: QApplication) -> None:
    """BUSY: New, Open, Open Project, Save and Settings are off while a take
    runs, in the menus and the sidebar, and say why; browsing stays."""
    window = MainWindow()
    window.show()
    window.standalone.busy_changed.emit(True)
    for action in window.busy_actions:
        assert not action.isEnabled()
        assert action.toolTip()
    for button in (window.navigator.new_button, window.navigator.settings_button):
        assert not button.isEnabled()
    assert window.navigator.tree.isEnabled()
    assert all(action.isEnabled() for action in window.view_actions.values())
    window.standalone.busy_changed.emit(False)
    assert all(action.isEnabled() for action in window.busy_actions)
    assert window.navigator.new_button.isEnabled()
    window.close()


def test_sidebar_rows_reach_their_actions(
    app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("REVERBSCOPE_HOME", str(tmp_path / "home"))
    window = MainWindow()
    called: list[str] = []
    monkeypatch.setattr(window, "show_settings", lambda: called.append("settings"))
    monkeypatch.setattr(window, "show_environment_report", lambda: called.append("report"))
    window.navigator.settings_requested.disconnect()
    window.navigator.report_requested.disconnect()
    window.navigator.settings_requested.connect(window.show_settings)
    window.navigator.report_requested.connect(window.show_environment_report)
    window.navigator.settings_button.click()
    window.navigator.report_button.click()
    assert called == ["settings", "report"]
    window.show_view("overview")
    window.navigator.new_button.click()
    assert window.stack.currentWidget() is window.home
    assert window.workspace.save_button.accessibleName()
    assert window.workspace.inspector_button.accessibleName()
    window.close()


def _clipped_buttons(window: MainWindow) -> list[str]:
    clipped = []
    for button in window.findChildren(QAbstractButton):
        if not button.isVisible() or not button.text():
            continue
        scroll = button.parentWidget()
        while scroll is not None and not isinstance(scroll, QScrollArea):
            scroll = scroll.parentWidget()
        if scroll is window.workspace.group_scroll:
            continue  # the view groups scroll and have the overflow menu
        if button.width() + 1 < button.sizeHint().width():
            clipped.append(f"{button.text()!r} {button.width()} < {button.sizeHint().width()}")
    return clipped


@pytest.mark.parametrize("language", ["en", "zh_CN"])
@pytest.mark.parametrize("size", [(960, 640), (1280, 800)])
def test_no_button_text_is_clipped_at_the_acceptance_sizes(
    app: QApplication, interface: None, language: str, size: tuple[int, int]
) -> None:
    from reverbscope.i18n import activate
    from reverbscope.ui.theme import apply_application_chrome

    activate(language)
    try:
        apply_application_chrome(app)
        window = MainWindow()
        window.resize(*size)
        window.show()
        for show in (
            window.show_home,
            lambda: window.show_mode("standalone"),
            lambda: window.show_mode("universal_daw"),
        ):
            show()
            for _ in range(4):
                app.processEvents()
            assert _clipped_buttons(window) == []
        window.close()
    finally:
        activate("en")
