"""The workbench in Simplified Chinese: menus, toolbar, the measurement
list, the inspector tabs, the measurement dialogs, the report and the
charts show no English beyond the names in tests/zh_tokens.py, and the
charts draw their Chinese text with a CJK font (no empty boxes)."""

from __future__ import annotations

import warnings
from collections.abc import Iterator
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QModelIndex, Qt
from PySide6.QtWidgets import (
    QAbstractButton,
    QAbstractItemView,
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
        if isinstance(widget, QAbstractItemView) and not isinstance(widget, QTableWidget):
            out += _model_texts(widget)
    return [text.replace("&", "") for text in out if text]


def _model_texts(view: QAbstractItemView) -> list[str]:
    """Every display text and tooltip of a model/view widget (the list, the tables)."""
    model = view.model()
    if model is None:
        return []
    out: list[str] = []

    def walk(parent: QModelIndex) -> None:
        for row in range(model.rowCount(parent)):
            for column in range(model.columnCount(parent)):
                index = model.index(row, column, parent)
                for role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.ToolTipRole):
                    value = model.data(index, role)
                    if isinstance(value, str):
                        out.append(value)
            child = model.index(row, 0, parent)
            if model.rowCount(child) > 0:
                walk(child)

    for column in range(model.columnCount(QModelIndex())):
        header = model.headerData(column, Qt.Orientation.Horizontal, Qt.ItemDataRole.DisplayRole)
        if isinstance(header, str):
            out.append(header)
    walk(QModelIndex())
    return out


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
            MeasurementSession(
                room_name=name,
                measurement_position="1",
                mode="universal_daw",
                recording_profile="vocal",
            ),
            result,
        )
        saved.append((folder, result))
    return saved


def _settle(app: QApplication) -> None:
    for _ in range(5):
        app.processEvents()


def test_the_workbench_is_chinese(zh: None, app: QApplication, tmp_path: Path) -> None:
    from reverbscope.ui.workbench import WorkbenchWindow

    saved = _measurements(tmp_path)
    window = WorkbenchWindow()
    window.resize(1280, 860)
    window.show()
    _settle(app)
    menus = [
        action.text()
        for menu in (a.menu() for a in window.menuBar().actions() if a.menu())
        for action in menu.actions()
    ]
    _check([text.replace("&", "") for text in menus], "menus")
    _check([a.text().replace("&", "") for a in window.toolbar.actions()], "toolbar")
    _check(_texts(window), "empty workbench")

    first = window.controller.open_session(saved[0][0])
    second = window.controller.open_session(saved[1][0])
    assert first is not None and second is not None
    window.document.set_baseline(first.id)
    window.set_inspector_visible(True)
    _settle(app)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        for key in ("frequency", "decay", "noise", "impulse", "reflections", "placement"):
            window.panels[0].set_kind(key)
            _settle(app)
            chart_text = [
                t.get_text()
                for t in window.panels[0].figure.findobj(lambda o: hasattr(o, "get_text"))
            ]
            _check([text for text in chart_text if text], f"chart {key}")
        window.panels[0].set_kind("frequency")
        window.panels[0].difference_button.setChecked(True)
        _settle(app)
        for name in ("quality", "diagnostics", "properties", "tables", "comparison", "report"):
            window.inspector.show_tab(name)
            _settle(app)
            _check(_texts(window.inspector), f"inspector {name}")
        window.grab()
    tofu = [w for w in caught if "missing from font" in str(w.message)]
    _check(_texts(window), "workbench")
    _check([window.inspector.report_text()], "full report")
    _check([window.windowTitle()], "title")
    if any(name for name in _cjk_fonts()):
        assert tofu == [], [str(w.message) for w in tofu[:3]]
    _check_dialogs(window)
    window.close()


def _check_dialogs(window: QWidget) -> None:
    import re

    from reverbscope.ui.measure_dialog import DawAnalysisDialog, StandaloneMeasureDialog
    from reverbscope.ui.measure_flow import separate_clocks_box
    from reverbscope.ui.workbench import about_box
    from reverbscope.ui.workers import out_of_memory_text, unexpected_error_text

    standalone = StandaloneMeasureDialog(window, profile="vocal", backend="fake")
    _check(_texts(standalone), "measure dialog")
    standalone.close()
    daw = DawAnalysisDialog(window, profile="vocal")
    _check(_texts(daw), "DAW dialog")
    daw.close()
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


def _cjk_fonts() -> list[str]:
    from reverbscope.ui.theme import font_families

    return font_families()[1:]


def test_a_synthetic_session_made_in_english_is_titled_in_chinese(
    zh: None, app: QApplication, tmp_path: Path
) -> None:
    """The names the demo wrote are shown in the interface language; a name a
    user typed is not touched, and the synthetic marker stays."""
    from reverbscope.demo import DEMO_MODE
    from reverbscope.io.session_store import save_measurement
    from reverbscope.models.session import MeasurementSession
    from reverbscope.ui.workbench import WorkbenchWindow

    [(_folder, result)] = _measurements(tmp_path)[:1]
    session = MeasurementSession(
        mode=DEMO_MODE,
        room_name="Synthetic demo room",
        measurement_position="A: close to the desk and the side wall",
        microphone_name="simulated omni",
    )
    saved = tmp_path / "demo-a"
    save_measurement(saved, session, result)
    window = WorkbenchWindow()
    window.show()
    measurement = window.controller.open_session(saved)
    _settle(app)
    assert measurement is not None
    name = measurement.name()
    assert "合成演示房间" in name and "A：靠近桌面和侧墙" in name, name
    assert "Synthetic" not in name and "desk" not in name, name
    listed = _model_texts(window.tree)
    assert any("合成数据" in text for text in listed), listed
    _check(listed, "measurement list")
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
    # The fake backend is a test facility, not a choice offered to the user.
    assert "fake" not in [dialog.backend.itemData(i) for i in range(dialog.backend.count())]
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
