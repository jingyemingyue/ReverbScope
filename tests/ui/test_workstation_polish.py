"""Workstation polish: no product demo, independent measurement state, layout.

Offscreen. A passing run here is not a Retina or macOS hardware check.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import numpy as np
import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QByteArray, QPoint
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QApplication

from reverbscope.core.pipeline import Reference, analyze, synthetic_recording
from reverbscope.models.configuration import SweepSettings
from reverbscope.models.result import AnalysisResult
from reverbscope.models.session import MeasurementSession
from tests.conftest import make_rir

pytestmark = pytest.mark.gui


@pytest.fixture(scope="module")
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.fixture(scope="module")
def result() -> AnalysisResult:
    sweep = SweepSettings(duration_s=2.0, pre_silence_s=1.0, post_silence_s=1.5, level_dbfs=-12.0)
    ir = make_rir(sweep.sample_rate, rt60_s=0.35, reflections=[(0.018, 0.35)])
    return analyze(synthetic_recording(sweep, ir, noise_rms=1e-5), Reference.from_settings(sweep))


def _texts(window: Any) -> list[str]:
    return [action.text().replace("&", "") for action in window.findChildren(QAction)]


def test_the_product_has_no_demo_entry(app: QApplication) -> None:
    from reverbscope.ui.main_window import MainWindow
    from reverbscope.ui.measure_strip import MODES
    from reverbscope.ui.project_view import NewPositionDialog

    window = MainWindow()
    joined = "\n".join(_texts(window))
    assert "Demo (no interface)" not in joined
    assert window.strip.mode.findData("demo") < 0
    assert [value for value, _text in MODES] == ["standalone", "universal_daw"]
    dialog = NewPositionDialog("A", "standalone", window)
    assert dialog.mode.findData("demo") < 0
    captions = [
        window.home.walkthrough.buttons[i].text()
        for i in range(len(window.home.walkthrough.buttons))
    ]
    assert all("demo" not in caption.lower() for caption in captions)
    window.close()
    dialog.deleteLater()


def test_selection_visibility_and_baseline_stay_independent(
    app: QApplication, result: AnalysisResult, tmp_path: Path
) -> None:
    from reverbscope.ui.views.frequency import FrequencyView
    from reverbscope.ui.workspace import WorkspaceModel

    model = WorkspaceModel()
    for index in range(3):
        model.add_session(
            tmp_path / f"take-{index}",
            MeasurementSession(),
            result,
            make_current=index == 0,
            visible=index == 0,
        )
    keys = [entry.key for entry in model.entries()]
    model.set_current(keys[1])
    assert model.current_key == keys[1]
    assert not model.is_visible(keys[1])
    assert model.is_visible(keys[0])
    view = FrequencyView(model)
    view.resize(900, 500)
    view.show()
    view.redraw()
    app.processEvents()
    assert [series.key for series in view.chart.series if series.key] == [keys[0]]
    model.set_baseline(keys[2])
    app.processEvents()
    assert model.current_key == keys[1]
    assert model.baseline_key == keys[2]
    assert not model.is_visible(keys[2])
    model.set_overlay(keys[1], True)
    app.processEvents()
    drawn = [series.key for series in view.chart.series if series.key in keys]
    assert drawn[-1] == keys[1]
    assert keys[0] in drawn and keys[2] not in drawn
    # The baseline legend is marked, and it is not the thick current curve.
    names = [series.name for series in view.chart.series if series.key == keys[2]]
    assert names == []
    model.set_overlay(keys[2], True)
    app.processEvents()
    baseline = next(series for series in view.chart.series if series.key == keys[2])
    current = next(series for series in view.chart.series if series.key == keys[1])
    assert "baseline" in baseline.name
    assert current.width > baseline.width
    view.close()


def test_hiding_the_inspector_and_resetting_the_layout(
    app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("REVERBSCOPE_HOME", str(tmp_path / "home"))
    from reverbscope.ui.main_window import MainWindow

    window = MainWindow()
    window.resize(960, 640)
    window.show()
    app.processEvents()
    assert window.strip.start_button.isVisible()
    assert window.strip.stop_button.isVisible()
    before = window.workspace.width()
    window.set_inspector_open(False)
    app.processEvents()
    assert not window.inspector.isVisible()
    assert window.workspace.width() >= before
    window.set_navigator_open(False)
    app.processEvents()
    assert not window.navigator.isVisible()
    assert window.workspace.width() > 400
    window.reset_layout()
    app.processEvents()
    assert window.navigator.isVisible() and window.inspector.isVisible()
    assert window.splitter.sizes()[1] >= 320
    window.close()


def test_a_broken_splitter_state_uses_the_default(
    app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("REVERBSCOPE_HOME", str(tmp_path / "home"))
    from reverbscope.ui import ui_state
    from reverbscope.ui.main_window import MainWindow

    ui_state.write("window/splitter", QByteArray(b"not-a-splitter-state"))
    window = MainWindow()
    window.resize(1280, 720)
    window.show()
    app.processEvents()
    assert window.splitter.sizes()[1] >= 320
    window.splitter.setSizes([800, 40, 200])
    window._ensure_chart_space()
    assert window.splitter.sizes()[1] >= 320
    window.close()


@pytest.mark.parametrize("language", ["en", "zh_CN"])
def test_narrow_strip_keeps_transport_and_rate_readable(app: QApplication, language: str) -> None:
    from reverbscope.i18n import activate
    from reverbscope.ui.main_window import MainWindow
    from reverbscope.ui.theme import apply_application_chrome

    activate(language)
    apply_application_chrome(app)
    window = MainWindow()
    window.resize(960, 640)
    window.show()
    strip = window.strip
    for _step in range(4):
        app.processEvents()
    # Qt's platform style and system fonts may calculate a minimum wider than
    # the requested 960 px (986 px on Windows); the strip's content must not
    # widen it further.
    baseline = window.minimumSizeHint().width()
    device = "MOTU UltraLite-mk5 — Core Audio — microphone inputs 1–18"
    strip.input_device.addItem(device, "test-device")
    strip.input_device.setCurrentIndex(strip.input_device.count() - 1)
    strip.advanced_button.setChecked(True)
    for _step in range(4):
        app.processEvents()
    # The requested window can remain narrow; the strip must not force it wider.
    assert window.minimumSizeHint().width() <= max(baseline, window.width())
    assert strip.mode.width() >= (
        strip.mode.fontMetrics().horizontalAdvance(strip.mode.currentText()) + 24
    )
    assert strip.sample_rate.width() >= (
        strip.sample_rate.fontMetrics().horizontalAdvance(strip.sample_rate.currentText()) + 24
    )
    assert device in strip.input_device.toolTip()
    assert strip.input_device.accessibleName()
    for widget in (strip.start_button, strip.stop_button, strip.phase):
        rect = widget.rect().translated(widget.mapTo(strip, QPoint()))
        assert strip.rect().contains(rect)
        assert not rect.intersects(strip.settings_bar.geometry())
    # Mirroring is still two-way after the settings have moved to another row.
    strip.input_channel.setValue(2)
    assert window.standalone.input_channel.value() == 2
    window.standalone.input_channel.setValue(1)
    assert strip.input_channel.value() == 1
    window.resize(1920, 1080)
    for _step in range(4):
        app.processEvents()
    assert strip.settings_bar.geometry().top() == strip.transport_bar.geometry().top()
    strip.set_mode("universal_daw")
    app.processEvents()
    assert not strip.input_device.isVisible()
    assert strip.start_button.isVisible()
    assert strip.start_button.shortcut().isEmpty()
    window.close()


def test_keyboard_view_choice_stays_visible_in_narrow_tab_bar(app: QApplication) -> None:
    from reverbscope.ui.main_window import MainWindow

    window = MainWindow()
    window.resize(960, 640)
    window.show()
    for view_id, group_id in (
        ("report", "report"),
        ("spectrogram", "spectral"),
        ("fr", "frequency"),
    ):
        # Use the QAction path taken by menu/shortcut navigation, not a tab click.
        window.view_actions[view_id].trigger()
        for _step in range(4):
            app.processEvents()
        workspace = window.workspace
        button = workspace.buttons[group_id]
        viewport = workspace.group_scroll.viewport()
        rect = button.rect().translated(button.mapTo(viewport, QPoint()))
        assert viewport.rect().contains(rect)
        assert button.isChecked()
    window.view_actions["project"].trigger()
    for _step in range(4):
        app.processEvents()
    button = window.workspace.project_button
    viewport = window.workspace.group_scroll.viewport()
    assert viewport.rect().contains(button.rect().translated(button.mapTo(viewport, QPoint())))
    assert button.isChecked()
    window.close()


@pytest.mark.parametrize("view_id", ["fr", "spectrogram", "waterfall"])
def test_small_window_scrolls_instead_of_clipping_plot_axes(
    app: QApplication, result: AnalysisResult, tmp_path: Path, view_id: str
) -> None:
    from reverbscope.i18n import activate
    from reverbscope.ui.main_window import MainWindow
    from reverbscope.ui.theme import apply_application_chrome

    activate("zh_CN")
    apply_application_chrome(app)
    window = MainWindow()
    for index in range(2):
        window.model.add_session(tmp_path / f"take-{index}", MeasurementSession(), result)
    window.model.set_baseline(window.model.entries()[0].key)
    window.resize(960, 640)
    window.strip.advanced_button.setChecked(True)
    window.show()
    window.show_view(view_id)
    view = window.views[view_id]
    for _step in range(4):
        app.processEvents()
    worker = getattr(view, "_worker", None)
    if worker is not None:
        assert worker.wait(10_000)
    for _step in range(4):
        app.processEvents()
    charts = [view.chart] + ([view.diff] if view_id == "fr" else [])
    for panel in charts:
        # A 140 px PlotWidget was previously assigned outside its smaller
        # panel: the axes existed in the scene but the parent cut them off.
        plot_rect = panel.plot.rect().translated(panel.plot.mapTo(panel, QPoint()))
        assert panel.rect().contains(plot_rect)
        # The scrollbars can reach every edge, even if controls make the
        # content wider than the viewport. The plot is not permanently cut.
        viewport = view.content_scroll.viewport()
        for x, y in ((0, 0), (panel.plot.width() - 1, panel.plot.height() - 1)):
            point = panel.plot.mapTo(view.content_scroll.widget(), QPoint(x, y))
            view.content_scroll.ensureVisible(point.x(), point.y(), 2, 2)
            app.processEvents()
            visible = panel.plot.mapTo(viewport, QPoint(x, y))
            assert viewport.rect().contains(visible)
    assert window.height() == 640
    window.close()


def test_frequency_csv_matches_the_drawn_curve(
    app: QApplication, result: AnalysisResult, tmp_path: Path
) -> None:
    from reverbscope.ui.views.frequency import FrequencyView
    from reverbscope.ui.workspace import WorkspaceModel

    model = WorkspaceModel()
    model.add_take(MeasurementSession(), result, [], "", "generic", unsaved=False, synthetic=True)
    view = FrequencyView(model)
    view.resize(800, 500)
    view.show()
    view.redraw()
    app.processEvents()
    path = view.chart.export_csv(tmp_path / "fr.csv")
    text = path.read_text(encoding="utf-8")
    assert "display smoothing" in text or "smoothing" in text or "stored" in text
    rows = [line.split(",") for line in text.splitlines() if line and not line.startswith("#")]
    assert rows[0] == ["curve", "x", "y"]
    xs = [float(row[1]) for row in rows[1:]]
    ys = [float(row[2]) for row in rows[1:]]
    stored = result.frequency_response
    assert xs[0] == pytest.approx(float(stored.frequencies_hz[0]), rel=1e-4)
    assert max(ys) == pytest.approx(float(np.nanmax(view.chart.series[0].y)), rel=1e-4)
    view.close()


def test_native_shortcut_is_text_and_the_strip_names_its_phase(app: QApplication) -> None:
    from reverbscope.ui.main_window import MainWindow
    from reverbscope.ui.widgets import native_shortcut

    shown = native_shortcut("Ctrl+1")
    assert isinstance(shown, str) and "1" in shown
    window = MainWindow()
    window.resize(1100, 700)
    window.show()
    app.processEvents()
    assert window.strip.phase.property("phase") == "idle"
    assert window.strip.phase.text() == "Ready"
    window.standalone.stop_button.setEnabled(True)
    window.standalone.busy_changed.emit(True)
    app.processEvents()
    assert window.strip.phase.property("phase") == "measure"
    assert window.strip.progress.isVisible()
    assert window.strip.stop_button.isEnabled()
    window.standalone.stop_button.setEnabled(False)
    window.standalone.busy_changed.emit(True)
    assert window.strip.phase.property("phase") == "analyze"
    window.standalone.busy_changed.emit(False)
    assert window.strip.phase.property("phase") == "idle"
    assert not window.strip.stop_button.isEnabled()
    window.close()


def test_themes_swap_the_same_tokens(app: QApplication, monkeypatch: pytest.MonkeyPatch) -> None:
    from reverbscope.ui.theme import color_scheme, stylesheet, tokens

    backgrounds = []
    for scheme in ("light", "dark"):
        monkeypatch.setenv("REVERBSCOPE_COLOR_SCHEME", scheme)
        assert color_scheme() == scheme
        sheet = stylesheet()
        assert tokens()["bg"] in sheet
        assert tokens()["surface"] in sheet
        backgrounds.append(tokens()["bg"])
    assert backgrounds[0] != backgrounds[1]


def test_a_display_alias_is_kept_without_rewriting_the_session(
    app: QApplication, result: AnalysisResult, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("REVERBSCOPE_HOME", str(tmp_path / "home"))
    from reverbscope.ui.workspace import WorkspaceModel, entry_label

    folder = tmp_path / "session"
    model = WorkspaceModel()
    entry = model.add_session(folder, MeasurementSession(room_name="Booth"), result)
    before = (folder / "session.json").read_bytes() if (folder / "session.json").is_file() else b""
    model.set_alias(entry.key, "Desk left")
    assert entry_label(model.entry(entry.key)).startswith("Desk")  # type: ignore[arg-type]
    again = WorkspaceModel()
    reopened = again.add_session(folder, MeasurementSession(room_name="Booth"), result)
    assert entry_label(reopened) == "Desk left"
    if before:
        assert (folder / "session.json").read_bytes() == before
