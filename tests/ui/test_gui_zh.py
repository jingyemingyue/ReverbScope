"""The GUI in Simplified Chinese: every page, the results and comparison of
real (synthetic) measurements, the settings dialog and the developer tools
show no English beyond the names in tests/zh_tokens.py, and the charts draw
their Chinese text with a CJK font (no empty boxes)."""

from __future__ import annotations

import warnings
from collections.abc import Iterator
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import (
    QAbstractButton,
    QApplication,
    QComboBox,
    QGroupBox,
    QLabel,
    QLineEdit,
    QTableWidget,
    QTabWidget,
    QWidget,
)

from reverbscope.i18n import activate
from tests.zh_tokens import english_words


@pytest.fixture(scope="module")
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.fixture
def zh(app: QApplication, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[None]:
    from reverbscope.ui.app import install_qt_translations

    monkeypatch.setenv("REVERBSCOPE_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("REVERBSCOPE_EDITION", "developer")
    # The synthetic backend: device names are the user's data, and a CI runner
    # (macOS lists "Apple Virtual Sound Device") must not decide the result.
    monkeypatch.setenv("REVERBSCOPE_AUDIO_BACKEND", "fake")
    activate("zh_CN")
    install_qt_translations(app)
    try:
        yield
    finally:
        activate("en")


def _texts(root: QWidget) -> list[str]:
    out: list[str] = []
    for widget in [root, *root.findChildren(QWidget)]:
        out += [widget.toolTip(), widget.windowTitle()]
        if isinstance(widget, QLabel):
            out.append(widget.text())
        if isinstance(widget, QAbstractButton):
            out.append(widget.text())
        if isinstance(widget, QGroupBox):
            out.append(widget.title())
        if isinstance(widget, QTabWidget):
            out += [widget.tabText(i) for i in range(widget.count())]
        if isinstance(widget, QComboBox):
            out += [widget.itemText(i) for i in range(widget.count())]
        if isinstance(widget, QLineEdit):
            out.append(widget.placeholderText())
        if isinstance(widget, QTableWidget):
            for column in range(widget.columnCount()):
                header = widget.horizontalHeaderItem(column)
                if header is not None:
                    out.append(header.text())
            for row in range(widget.rowCount()):
                for column in range(widget.columnCount()):
                    item = widget.item(row, column)
                    if item is not None:
                        out += [item.text(), item.toolTip()]
    return [text.replace("&", "") for text in out if text]


def _data_values() -> tuple[str, ...]:
    from reverbscope.audio.backend import get_backend
    from reverbscope.ui.settings_dialog import LANGUAGE_NAMES, RESTART_FOR_LANGUAGE

    devices = tuple(device.name for device in get_backend("fake").list_devices())
    # Language names are written in their own language on purpose.
    return (*devices, *RESTART_FOR_LANGUAGE.splitlines(), *LANGUAGE_NAMES.values())


def _check(texts: list[str], where: str) -> None:
    data = _data_values()
    found = {word: text for text in texts for word in english_words(text, data=data)}
    assert found == {}, f"{where}: English in the Chinese interface: {found}"


def _measurements(home: Path) -> list[tuple[Path, object]]:
    from reverbscope.core.pipeline import Reference, analyze, synthetic_recording
    from reverbscope.io.session_store import save_measurement
    from reverbscope.models.configuration import SweepSettings
    from reverbscope.models.session import MeasurementSession
    from tests.conftest import make_rir

    settings = SweepSettings(sample_rate=48000, duration_s=3.0)
    saved = []
    for name, rt60 in (("房间A", 0.35), ("房间B", 0.9)):
        ir = make_rir(48000, rt60_s=rt60, reflections=[(0.01, 0.5)], length_s=1.5, seed=3)
        recording = synthetic_recording(settings, ir, noise_rms=3e-4, gain=0.3, seed=3)
        result = analyze(recording, Reference.from_settings(settings))
        folder = home / name
        save_measurement(
            folder,
            MeasurementSession(room_name=name, measurement_position="1", mode="universal_daw"),
            result,
        )
        saved.append((folder, result))
    return saved


def test_every_page_is_chinese(zh: None, app: QApplication, tmp_path: Path) -> None:
    from reverbscope.interpretation import interpret
    from reverbscope.models.session import MeasurementSession
    from reverbscope.ui.main_window import MainWindow

    saved = _measurements(tmp_path)
    window = MainWindow()
    window.resize(1280, 860)
    window.show()

    def settle() -> None:
        for _ in range(5):
            app.processEvents()

    menus = [
        action.text()
        for menu in (a.menu() for a in window.menuBar().actions() if a.menu())
        for action in menu.actions()
    ]
    _check([text.replace("&", "") for text in menus], "menus")
    for page, show in (
        ("home", window.show_home),
        ("daw", lambda: window.show_mode("universal_daw")),
        ("standalone", lambda: window.show_mode("standalone")),
        ("demo", lambda: window.show_mode("demo")),
    ):
        show()
        settle()
        _check(_texts(window), page)

    _folder, result = saved[1]
    window.state.result = result
    window.state.findings = interpret(result, "vocal")
    window.state.session = MeasurementSession(room_name="房间B", measurement_position="1")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        window.show_results()
        for index in range(window.results.tabs.count()):
            window.results.tabs.setCurrentIndex(index)
            settle()
        window.show_compare()
        window.compare.set_paths(saved[0][0], saved[1][0])
        window.compare.run_compare()
        window.compare.tabs.setCurrentIndex(1)
        settle()
        window.grab()
    tofu = [w for w in caught if "missing from font" in str(w.message)]
    _check(_texts(window.results), "results")
    _check([window.results.text.toPlainText()], "full report")
    _check(_texts(window.compare), "compare")
    _check([window.compare.text.toPlainText()], "comparison report")
    tabs = (
        window.results.ir_tab,
        window.results.fr_tab,
        window.results.decay_tab,
        window.results.noise_tab,
        window.results.refl_tab,
        window.results.place_tab,
    )
    figures = [tab.figure for tab in tabs] + [
        window.compare.figure,
        window.daw.placement.figure,
        window.standalone.placement.figure,
    ]
    for figure in figures:
        chart_text = [t.get_text() for t in figure.findobj(lambda o: hasattr(o, "get_text"))]
        _check([text for text in chart_text if text], "charts")
    window.close()
    if any(name for name in _cjk_fonts()):
        assert tofu == [], [str(w.message) for w in tofu[:3]]
    _check_about_and_clocks(window)


def _check_about_and_clocks(window: QWidget) -> None:
    import re

    from reverbscope.ui.main_window import about_box
    from reverbscope.ui.pages import separate_clocks_box
    from reverbscope.ui.workers import unexpected_error_text

    about = about_box(window)
    plain = re.sub(r"<[^>]+>", " ", about.text())
    _check([plain, about.windowTitle(), *[button.text() for button in about.buttons()]], "about")
    about.close()
    clocks = separate_clocks_box(window, "播放和录音不在同一台设备上")
    labels = [
        clocks.windowTitle(),
        clocks.text(),
        clocks.informativeText(),
        *[button.text() for button in clocks.buttons()],
    ]
    _check(labels, "two clocks")
    from reverbscope.i18n import _

    default = clocks.defaultButton()
    assert default is not None and default.text() == _("Cancel")
    clocks.close()
    _check([unexpected_error_text()], "unexpected error")
    from PySide6.QtGui import QFontDatabase

    from reverbscope.ui.theme import CJK_FALLBACK_FONTS

    present = [name for name in CJK_FALLBACK_FONTS if name in set(QFontDatabase.families())]
    if present:
        families = window.results.text.font().families()
        assert any(name in families for name in present), families


def _cjk_fonts() -> list[str]:
    from reverbscope.ui.theme import font_families

    return font_families()[1:]


def test_settings_and_developer_tools_are_chinese(zh: None, app: QApplication) -> None:
    from reverbscope.ui.dev_tools import DeviceInspector, EnvironmentReport
    from reverbscope.ui.settings_dialog import SettingsDialog

    dialog = SettingsDialog()
    names = [dialog.language.itemText(i) for i in range(dialog.language.count())]
    assert names == ["跟随系统", "English", "简体中文"]
    assert [dialog.language.itemData(i) for i in range(dialog.language.count())] == [
        "",
        "en",
        "zh_CN",
    ]
    _check(_texts(dialog), "settings")
    for tool in (EnvironmentReport("fake"), DeviceInspector("fake")):
        _check(_texts(tool), type(tool).__name__)
        tool.close()
    dialog.close()


def test_choosing_a_language_does_not_switch_the_open_windows(zh: None, app: QApplication) -> None:
    from reverbscope.i18n import current_locale
    from reverbscope.settings import load_settings
    from reverbscope.ui.settings_dialog import SettingsDialog

    dialog = SettingsDialog()
    dialog.language.setCurrentIndex(dialog.language.findData("en"))
    dialog.accept()
    assert load_settings().language == "en"
    # Saved for the next start; this session stays Chinese, never half and half.
    assert current_locale() == "zh_CN"
    assert "重新启动" in dialog.language_hint.text()
