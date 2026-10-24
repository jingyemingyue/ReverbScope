"""New Measurement: one page, two ways to play and record the sweep, no mode names.

The interface take and the DAW import used to be two pages, "Standalone Mode"
and "Universal DAW Mode". They are one flow now: a choice at the top, the
steps that differ, then one set of details, profile and a pinned action bar.
The import way in must stay usable with no audio device and no PortAudio.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QAbstractButton,
    QApplication,
    QComboBox,
    QGroupBox,
    QLabel,
    QWidget,
)

from reverbscope.audio import backend as backend_module
from reverbscope.audio.backend import DeviceInfo
from reverbscope.core.pipeline import synthetic_recording
from reverbscope.errors import AudioBackendUnavailableError
from reverbscope.io.wav import write_wav
from reverbscope.models.configuration import SweepSettings
from reverbscope.ui.main_window import MainWindow
from tests.conftest import make_rir
from tests.ui._metrics import wide_offscreen_latin

#: The two retired mode names, in both languages, as a user could read them.
MODE_NAMES = ("Universal DAW", "Standalone", "通用 DAW", "独立模式", "DAW 模式")


@pytest.fixture(scope="module")
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("REVERBSCOPE_HOME", str(tmp_path / "home"))


class _NoDevice:
    name = "test"

    def list_devices(self) -> list[DeviceInfo]:
        return []

    def check_sample_rate(self, *args: object, **kwargs: object) -> None:
        return None


def _texts(root: QWidget) -> list[str]:
    """Every string a user can read on ``root``: labels, buttons, boxes,
    combo rows, tooltips and accessible names."""
    out: list[str] = []
    for widget in [root, *root.findChildren(QWidget)]:
        out += [widget.toolTip(), widget.accessibleName(), widget.accessibleDescription()]
        if isinstance(widget, QLabel | QAbstractButton):
            out.append(widget.text())
        if isinstance(widget, QGroupBox):
            out.append(widget.title())
        if isinstance(widget, QComboBox):
            out += [widget.itemText(row) for row in range(widget.count())]
    return [text for text in out if text]


def _menu_texts(window: MainWindow) -> list[str]:
    out: list[str] = []
    for action in window.findChildren(QAction):
        out += [action.text(), action.toolTip(), action.statusTip()]
    return [text for text in out if text]


def test_one_page_offers_both_ways_and_shares_the_rest(app: QApplication) -> None:
    window = MainWindow()
    window.show()
    window.show_mode("standalone")
    page = window.measure
    assert window.stack.currentWidget() is page
    assert page.route() == "standalone"
    assert page.route_buttons["standalone"].isChecked()
    assert page.footer.currentWidget() is window.standalone.action_bar
    # One set of details for both ways in: what was typed stays on a switch.
    assert window.daw.room is window.standalone.room is page.details.room
    assert window.daw.profile is window.standalone.profile
    assert window.daw.placement is window.standalone.placement
    assert window.daw.third_octave is window.standalone.third_octave
    window.standalone.room.setText("Booth A")
    # The page's choice is the window's: it switches the strip too.
    page.route_buttons["universal_daw"].click()
    assert page.route() == "universal_daw"
    assert page.route_buttons["universal_daw"].isChecked()
    assert page.footer.currentWidget() is window.daw.action_bar
    assert window.strip.current_mode() == "universal_daw"
    assert window.daw.room.text() == "Booth A"
    # The strip's list is the same choice.
    window.strip.set_mode("standalone")
    assert page.route() == "standalone"
    # The test signal the two ways write follows: rate and duration.
    window.daw.sample_rate.setCurrentIndex(window.daw.sample_rate.findData(96000))
    assert window.standalone.sample_rate.currentData() == 96000
    window.standalone.duration.setValue(4.0)
    assert window.daw.duration.value() == 4.0
    # The levels do not: the interface keeps its own safe default.
    assert window.standalone.level.value() != window.daw.level.value()
    window.close()


@pytest.mark.parametrize("language", ["en", "zh_CN"])
def test_no_mode_name_is_left_in_the_window(app: QApplication, language: str) -> None:
    from reverbscope.i18n import activate

    activate(language)
    try:
        window = MainWindow()
        window.show()
        for route in ("standalone", "universal_daw"):
            window.show_mode(route)
            app.processEvents()
            texts = (
                _texts(window.measure)
                + _texts(window.strip)
                + _texts(window.home)
                + _menu_texts(window)
                + [window.statusBar().currentMessage(), window.workspace._title]
            )
            leaked = [text for text in texts if any(name in text for name in MODE_NAMES)]
            assert leaked == [], (route, leaked)
        menu = {a.shortcut().toString(): a.text() for a in window.findChildren(QAction)}
        assert menu["Ctrl+Shift+1"] and menu["Ctrl+Shift+2"]
        window.close()
    finally:
        activate("en")


def test_the_project_dialog_names_the_ways_not_modes(app: QApplication) -> None:
    from reverbscope.ui.project_view import NewPositionDialog

    dialog = NewPositionDialog("B", "universal_daw")
    rows = [dialog.mode.itemText(row) for row in range(dialog.mode.count())]
    assert rows == ["Audio interface", "DAW recording"]
    assert dialog.mode.currentData() == "universal_daw"
    dialog.close()


def test_no_device_offers_the_import_and_it_works(
    app: QApplication, tmp_path: Path, short_sweep: SweepSettings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No audio device: the interface steps say so and point at the import,
    which writes the signal, imports the take and analyses it."""
    monkeypatch.setattr(backend_module, "get_backend", lambda name=None: _NoDevice())
    window = MainWindow()
    window.show()
    window.show_mode("standalone")
    page = window.standalone
    reason = "No audio device found; you can still import a recording."
    assert page.readiness_reason() == reason
    assert not page.run_button.isEnabled()
    assert not page.import_button.isHidden()
    page.import_button.click()
    assert window.measure.route() == "universal_daw"
    assert window.strip.current_mode() == "universal_daw"
    _import_and_analyse(app, window, tmp_path, short_sweep)
    window.close()


def test_the_import_works_without_portaudio(
    app: QApplication, tmp_path: Path, short_sweep: SweepSettings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """sounddevice / PortAudio missing: the page still opens, and the DAW
    import analyses a take from start to end."""

    def unavailable(name: str | None = None) -> object:
        raise AudioBackendUnavailableError("the audio backend is not available")

    monkeypatch.setattr(backend_module, "get_backend", unavailable)
    window = MainWindow()
    window.show()
    window.show_mode("standalone")
    assert not window.standalone.run_button.isEnabled()
    assert not window.standalone.import_button.isHidden()
    window.show_mode("universal_daw")
    assert window.measure.route() == "universal_daw"
    _import_and_analyse(app, window, tmp_path, short_sweep)
    window.close()


def _import_and_analyse(
    app: QApplication, window: MainWindow, tmp_path: Path, short_sweep: SweepSettings
) -> None:
    daw = window.daw
    assert "Import the recording" in daw.readiness.text()
    daw.sample_rate.setCurrentIndex(daw.sample_rate.findData(short_sweep.sample_rate))
    daw.duration.setValue(short_sweep.duration_s)
    daw.generate_sweep_to(tmp_path / "sweep.wav")
    ir = make_rir(short_sweep.sample_rate, rt60_s=0.3, diffuse_level=0.01)
    recording = synthetic_recording(daw.current_sweep_settings(), ir, noise_rms=1e-5)
    path = write_wav(
        tmp_path / "take.wav", recording.samples, recording.sample_rate, subtype="FLOAT"
    )
    daw.set_recording(path)
    assert daw.readiness.text() == ""
    assert daw.steps.states[3] == "current"
    daw.start_analysis(blocking=True)
    app.processEvents()
    assert window.state.result is not None
    assert window.state.session.mode == "universal_daw"  # the stored id is unchanged
    assert window.stack.currentWidget() is window.views["overview"]


def test_the_choice_waits_while_a_take_runs(app: QApplication) -> None:
    """Switching the way in mid-take would hide its Stop: the cards wait."""
    window = MainWindow()
    window.show()
    window.show_mode("standalone")
    page = window.measure
    window.standalone.busy_changed.emit(True)
    assert not page.route_buttons["universal_daw"].isEnabled()
    assert "Measuring" in page.route_buttons["universal_daw"].toolTip()
    window.standalone.busy_changed.emit(False)
    assert page.route_buttons["universal_daw"].isEnabled()
    window.close()


def _pump(app: QApplication, seconds: float = 0.0) -> None:
    import time

    end = time.monotonic() + seconds
    app.processEvents()
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.01)


@pytest.mark.parametrize("language", ["en", "zh_CN"])
def test_the_narrow_page_stacks_the_cards_and_moves_the_reason(
    app: QApplication, language: str
) -> None:
    """960 x 640 with the inspector open: the two ways in stack instead of
    the second card being cut off, and the reason Run is off moves above
    the buttons when the pinned action bar (in the page's footer) narrows,
    without anything else asking it to."""
    from reverbscope.i18n import activate

    activate(language)
    try:
        window = MainWindow()
        window.resize(960, 640)
        window.show()
        window.show_mode("standalone")
        _pump(app, 0.1)
        page = window.measure
        standalone = window.standalone
        assert standalone.readiness_reason()
        # Only the bar is resized (as the footer does): the reason follows.
        standalone.action_bar.resize(900, standalone.action_bar.height())
        assert not standalone.reason_above_buttons()
        standalone.action_bar.resize(360, standalone.action_bar.height())
        assert standalone.reason_above_buttons()
        # Only the chooser is resized: the cards follow its width.
        page.chooser.resize(400, page.chooser.height())
        assert page.cards_stacked()
        page.chooser.resize(900, page.chooser.height())
        assert not page.cards_stacked()
        if wide_offscreen_latin() and language == "en":
            window.close()
            return  # the window cannot be 960 px wide there (tests/ui/_metrics.py)
        # The real window: inspector open at 960 px stacks the cards.
        window.set_inspector_open(True)
        _pump(app, 0.2)
        assert page.chooser.width() < 560
        assert page.cards_stacked()
        first, second = (page.route_buttons[r] for r in ("standalone", "universal_daw"))
        assert second.geometry().top() >= first.geometry().bottom()
        assert first.width() == second.width() == page.chooser.width()
        assert standalone.reason_above_buttons()
        # Room again: the cards go back side by side.
        window.set_inspector_open(False)
        _pump(app, 0.2)
        assert not page.cards_stacked()
        assert first.geometry().top() == second.geometry().top()
        window.close()
    finally:
        activate("en")
