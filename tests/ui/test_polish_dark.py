"""The polished dark desktop: every feature in view, nothing clipped, sound safety.

Offscreen at 960 x 640 and 1280 x 800, in English and Simplified Chinese.
A passing run here is not a hardware or Retina check.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QAbstractButton, QApplication, QLabel, QWidget

from reverbscope.core.pipeline import Reference, analyze, synthetic_recording
from reverbscope.models.configuration import SweepSettings
from reverbscope.models.result import AnalysisResult
from reverbscope.models.session import MeasurementSession
from tests.conftest import make_rir

pytestmark = pytest.mark.gui

SIZES = ((960, 640), (1280, 800))
#: Analysis views that must be one click away as a visible tab.
TAB_VIEWS = ("overview", "fr", "etc", "decay", "noise", "spectrogram", "waterfall", "report")


@pytest.fixture(scope="module")
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.fixture(scope="module")
def result() -> AnalysisResult:
    sweep = SweepSettings(duration_s=2.0, pre_silence_s=1.0, post_silence_s=1.5, level_dbfs=-12.0)
    ir = make_rir(sweep.sample_rate, rt60_s=0.35, reflections=[(0.018, 0.35)])
    return analyze(synthetic_recording(sweep, ir, noise_rms=1e-5), Reference.from_settings(sweep))


@pytest.fixture(params=["en", "zh_CN"])
def lang(
    request: pytest.FixtureRequest,
    app: QApplication,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Iterator[str]:
    from reverbscope.i18n import activate
    from reverbscope.ui.theme import apply_application_chrome

    monkeypatch.setenv("REVERBSCOPE_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("REVERBSCOPE_AUDIO_BACKEND", "fake")
    monkeypatch.setenv("REVERBSCOPE_COLOR_SCHEME", "dark")
    activate(request.param)
    apply_application_chrome(app)
    try:
        yield request.param
    finally:
        activate("en")


def _settle(app: QApplication) -> None:
    for _step in range(6):
        app.processEvents()


def _window(app: QApplication, size: tuple[int, int]) -> Any:
    from reverbscope.ui.main_window import MainWindow

    window = MainWindow()
    window.resize(*size)
    window.show()
    _settle(app)
    return window


def _inside(child: QWidget, bar: QWidget) -> bool:
    rect = child.rect().translated(child.mapTo(bar, QPoint()))
    return bar.rect().contains(rect)


def _clipped(bar: QWidget) -> list[str]:
    """Visible labels and buttons of ``bar`` that stick out of it or are squeezed."""
    problems = []
    for widget in bar.findChildren(QWidget):
        if not isinstance(widget, (QLabel, QAbstractButton)) or not widget.isVisibleTo(bar):
            continue
        name = widget.text() or widget.accessibleName()
        if not _inside(widget, bar):
            problems.append(f"outside the bar: {name!r}")
        elif widget.width() < widget.minimumSizeHint().width():
            problems.append(f"squeezed: {name!r} {widget.width()} < {widget.minimumSizeHint()}")
    return problems


@pytest.mark.parametrize("size", SIZES)
def test_every_analysis_view_is_a_visible_tab_and_the_bars_do_not_clip(
    app: QApplication, lang: str, result: AnalysisResult, tmp_path: Path, size: tuple[int, int]
) -> None:
    from reverbscope.demo import DEMO_MODE

    window = _window(app, size)
    entry = window.model.add_session(tmp_path / "a", MeasurementSession(mode=DEMO_MODE), result)
    assert entry.synthetic
    window.model.set_current(entry.key)
    tabs = window.workspace.context.view
    for view_id in TAB_VIEWS:
        window.show_view(view_id)
        _settle(app)
        index = tabs.findData(view_id)
        assert index >= 0, view_id
        button = tabs.button(index)
        assert button.isVisible() and button.isChecked(), view_id
        assert _inside(button, window.workspace.context), view_id
        assert button.toolTip(), view_id
        for bar in (window.workspace.taskbar, window.workspace.context):
            assert _clipped(bar) == [], (view_id, size, lang)
    # The synthetic data is said in words on every view, also when compact.
    assert window.workspace.context.synthetic.isVisible()
    assert window.workspace.context.synthetic.text()
    # Clicking a tab opens its view.
    tabs.button(tabs.findData("decay")).click()
    _settle(app)
    assert window.current_view_id() == "decay"
    window.close()


@pytest.mark.parametrize("size", SIZES)
def test_the_measure_context_bar_does_not_clip(
    app: QApplication, lang: str, size: tuple[int, int]
) -> None:
    window = _window(app, size)
    for mode in ("standalone", "universal_daw"):
        window.show_mode(mode)
        _settle(app)
        assert window.workspace.context.measurement_controls.isVisible()
        for bar in (window.workspace.taskbar, window.workspace.context):
            assert _clipped(bar) == [], (mode, size, lang)
    window.close()


def test_the_room_view_is_reachable_but_not_promoted(app: QApplication, lang: str) -> None:
    window = _window(app, (1280, 800))
    assert window.workspace.context.view.findData("room") < 0
    assert "room" in window.view_actions  # View menu and its shortcut stay
    window.close()


def test_a_save_notice_is_shown_over_the_canvas(app: QApplication, lang: str) -> None:
    window = _window(app, (960, 640))
    window.show_view("fr")
    window.notify("Session saved to /tmp/x")
    _settle(app)
    notice = window.notice
    assert notice.isVisible() and notice.message() == "Session saved to /tmp/x"
    assert _inside(notice, window.workspace.body)
    assert window.statusBar().currentMessage() == "Session saved to /tmp/x"
    notice.close_button.click()
    assert not notice.isVisible()
    window.close()


def test_run_waits_for_a_hand_picked_interface_output(app: QApplication, lang: str) -> None:
    window = _window(app, (1280, 800))
    page = window.standalone
    assert page.output_block_reason("fake") == ""  # the fake backend plays nothing
    # A real backend with a preselected output: Run is off and says why.
    page._inventory_backend = "portaudio"
    page._explicit_output = None
    page._sync_run_button()
    assert not page.run_button.isEnabled()
    assert not page.run_reason.isHidden() and page.run_reason.text()
    assert page.run_button.toolTip() == page.run_reason.text()
    chosen = page._chosen_devices()
    if chosen is None or chosen[2] is None:
        # "System default" is never a choice the sweep may use.
        assert page.output_block_reason("portaudio")
    else:
        assert page.choose_output(chosen[2][0])
        assert page.run_button.isEnabled() and page.run_reason.isHidden()
    window.close()


def test_the_inspector_offers_the_baseline_in_view(
    app: QApplication, lang: str, result: AnalysisResult, tmp_path: Path
) -> None:
    window = _window(app, (1280, 800))
    entry = window.model.add_session(tmp_path / "a", MeasurementSession(), result)
    window.model.set_current(entry.key)
    window.set_inspector_open(True)
    _settle(app)
    button = window.inspector.baseline_button
    assert button.isVisible()
    button.click()
    assert window.model.baseline_key == entry.key
    window.close()


def test_the_report_names_the_command_line_for_what_the_desktop_does_not_do(
    app: QApplication, lang: str, result: AnalysisResult, tmp_path: Path
) -> None:
    window = _window(app, (1280, 800))
    entry = window.model.add_session(tmp_path / "take one", MeasurementSession(), result)
    window.model.set_current(entry.key)
    window.show_view("report")
    _settle(app)
    commands = window.views["report"].commands.toPlainText()
    assert f'reverbscope export "{tmp_path / "take one"}" --format csv' in commands
    assert "reverbscope session bundle" in commands
    assert "reverbscope analyze-ir --ir" in commands
    window.close()


def test_one_icon_family_draws_every_glyph(app: QApplication) -> None:
    from reverbscope.ui.components.icons import ICON_NAMES, icon, icon_pixmap

    for name in ICON_NAMES:
        image = icon_pixmap(name, "#ffffff").toImage()
        assert any(
            image.pixelColor(x, y).alpha() > 0
            for x in range(0, image.width(), 2)
            for y in range(0, image.height(), 2)
        ), name
        assert not icon(name).isNull()


def test_chart_tick_numbers_stay_readable_on_the_dark_canvas() -> None:
    from reverbscope.ui.theme import DARK_TOKENS, contrast_ratio

    assert contrast_ratio(DARK_TOKENS["muted"], DARK_TOKENS["canvas"]) >= 4.5
    assert contrast_ratio(DARK_TOKENS["text"], DARK_TOKENS["canvas"]) >= 7.0
    assert contrast_ratio(DARK_TOKENS["accent"], DARK_TOKENS["surface"]) >= 4.5
