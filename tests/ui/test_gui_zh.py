"""The GUI in Simplified Chinese: every page, the results and comparison of
real (synthetic) measurements, the settings dialog and the developer tools
show no English beyond the names in tests/zh_tokens.py, and the charts draw
their Chinese text with a CJK font (no empty boxes)."""

from __future__ import annotations

import re
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


def _internal(widget: QWidget) -> bool:
    """pyqtgraph's own menus and settings panel: switched off, never shown."""
    from reverbscope.ui.pg import INTERNAL_PROPERTY

    while widget is not None:
        if widget.property(INTERNAL_PROPERTY):
            return True
        widget = widget.parentWidget()
    return False


def _texts(root: QWidget) -> list[str]:
    out: list[str] = []
    for widget in [root, *root.findChildren(QWidget)]:
        if _internal(widget):
            continue
        out += [widget.toolTip(), widget.windowTitle()]
        if isinstance(widget, QLabel):
            # Rich text (the inspector's coloured chips): the markup is not read.
            out.append(re.sub(r"<[^>]+>", " ", widget.text()))
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

    # Both measurements in the list, the first as the baseline, a reflection
    # selected and the example room entered: every view and the inspector
    # have something to say.
    assert window.open_session_path(saved[0][0])
    assert window.open_session_path(saved[1][0])
    first, second = (entry.key for entry in window.model.entries())
    window.model.set_baseline(first)
    window.model.set_current(second)
    window.model.select_reflection(second, 0)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        for view_id in window.views:
            window.show_view(view_id)
            settle()
        window.views["room"].use_example()
        settle()
        window.compare.tabs.setCurrentIndex(1)
        settle()
        window.grab()
    tofu = [w for w in caught if "missing from font" in str(w.message)]
    for view_id, view in window.views.items():
        _check(_texts(view), view_id)
    _check(_texts(window.navigator), "navigator")
    _check(_texts(window.inspector), "inspector")
    _check(_texts(window.strip), "measure strip")
    _check([window.views["report"].text.toPlainText()], "full report")
    _check([window.compare.text.toPlainText()], "comparison report")
    from reverbscope.ui.plotkit import ChartPanel

    charts = window.findChildren(ChartPanel)
    assert len(charts) >= 8
    for chart in charts:
        axes = [chart.plot_item.getAxis(name).labelText for name in ("bottom", "left")]
        legend = [series.name for series in chart.series] + [
            series.processing for series in chart.series
        ]
        _check([chart.title.text(), chart.readout.text(), *axes, *legend], "charts")
    # The two placement pictures beside the tape-measure inputs stay matplotlib.
    for figure in (window.daw.placement.figure, window.standalone.placement.figure):
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
    from reverbscope.ui.workers import out_of_memory_text, unexpected_error_text

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
    _check([out_of_memory_text()], "out of memory")
    from PySide6.QtGui import QFontDatabase

    from reverbscope.ui.theme import CJK_FALLBACK_FONTS

    present = [name for name in CJK_FALLBACK_FONTS if name in set(QFontDatabase.families())]
    if present:
        families = window.views["report"].text.font().families()
        assert any(name in families for name in present), families


def _cjk_fonts() -> list[str]:
    from reverbscope.ui.theme import font_families

    return font_families()[1:]


def test_a_demo_made_in_english_is_listed_and_titled_in_chinese(
    zh: None, app: QApplication, tmp_path: Path
) -> None:
    """The recent list and the results title printed "房间 Synthetic demo room"
    for a demo made before the language was changed: the names the demo wrote
    are shown in the interface language, a name a user typed is not touched."""
    from reverbscope.demo import DEMO_MODE
    from reverbscope.io.recent import remember_session
    from reverbscope.io.session_store import save_measurement
    from reverbscope.models.session import MeasurementSession
    from reverbscope.ui.main_window import MainWindow
    from reverbscope.ui.workspace import entry_label

    [(_folder, result)] = _measurements(tmp_path)[:1]
    session = MeasurementSession(
        mode=DEMO_MODE,
        room_name="Synthetic demo room",
        measurement_position="A: close to the desk and the side wall",
        microphone_name="simulated omni",
    )
    saved = tmp_path / "demo-a"
    save_measurement(saved, session, result)
    remember_session(saved)
    window = MainWindow()
    window.home.refresh_recent()
    listed = window.home.recent.item(0).text()
    assert "合成演示房间" in listed and "A：靠近桌面和侧墙" in listed, listed
    assert "Synthetic" not in listed and "desk" not in listed, listed
    assert window.open_session_path(saved)
    title = window.inspector.subtitle.text()
    assert "合成演示房间" in title and "模拟全指向话筒" in title, title
    assert "Synthetic" not in title and "omni" not in title, title
    # The navigator and the chart legends name it the same way.
    current = window.model.current()
    assert current is not None and "Synthetic" not in entry_label(current)
    session.room_name = "Booth A"
    save_measurement(saved, session, result)
    assert window.open_session_path(saved)
    assert "Booth A" in window.inspector.subtitle.text()
    window.close()


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
