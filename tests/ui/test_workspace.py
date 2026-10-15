"""The workstation shell: navigation rail, interactive graphs, split measure pages."""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from matplotlib.backend_bases import MouseEvent
from PySide6.QtWidgets import QApplication

from reverbscope.core.pipeline import Reference, analyze, synthetic_recording
from reverbscope.interpretation import interpret
from reverbscope.models.configuration import SweepSettings
from reverbscope.ui.main_window import MainWindow
from reverbscope.ui.plotview import (
    PlotView,
    clamped_limits,
    format_value,
    split_axis_label,
    zoomed_limits,
)
from tests.conftest import make_rir

pytestmark = pytest.mark.gui


@pytest.fixture(scope="module")
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.fixture
def view(app: QApplication) -> PlotView:
    """A graph with two traces, drawn and shown, as the Results page makes them."""
    widget = PlotView()
    widget.resize(800, 520)
    widget.show()
    ax = widget.figure.add_subplot(1, 1, 1)
    x = np.logspace(np.log10(20.0), np.log10(20000.0), 400)
    ax.semilogx(x, -3.0 * np.log10(x), label="smoothed")
    ax.semilogx(x, np.full_like(x, 2.0), label="flat")
    ax.set_xlabel("Frequency (Hz)")
    ax.set_ylabel("Magnitude (dB, relative)")
    widget.redraw()
    for _ in range(5):
        app.processEvents()
    widget.canvas.draw()
    return widget


def _point(view: PlotView, fx: float, fy: float) -> tuple[float, float]:
    """Pixel position of a fraction of the axes' width and height."""
    box = view.data_axes()[0].bbox
    return box.x0 + box.width * fx, box.y0 + box.height * fy


def _send(view: PlotView, kind: str, x: float, y: float, **kwargs: object) -> None:
    MouseEvent(kind, view.canvas, x, y, **kwargs)._process()  # type: ignore[arg-type]


def test_axis_labels_give_their_unit_in_both_languages() -> None:
    assert split_axis_label("Frequency (Hz)") == ("Frequency", "Hz")
    assert split_axis_label("Magnitude (dB, relative)") == ("Magnitude", "dB")
    assert split_axis_label("频率（Hz）") == ("频率", "Hz")
    assert split_axis_label("幅度（相对）") == ("幅度", "")
    assert split_axis_label("Amplitude (relative)") == ("Amplitude", "")
    assert split_axis_label("PSD (dB re FS^2/Hz)") == ("PSD", "dB re FS^2/Hz")
    assert split_axis_label("Plain") == ("Plain", "")


def test_readout_numbers_carry_their_unit() -> None:
    assert format_value(987.64, "Hz") == "987.6 Hz"
    assert format_value(2500.0, "Hz") == "2.500 kHz"
    assert format_value(-20.04, "dB") == "-20.0 dB"
    assert format_value(0.2134, "s") == "0.213 s"
    assert format_value(float("nan"), "dB") == "-"


def test_zooming_keeps_the_point_under_the_pointer_and_works_in_log_space() -> None:
    low, high = zoomed_limits((20.0, 20000.0), 1000.0, 0.5, "log")
    assert low < 1000.0 < high
    # Half the span in log space about 1 kHz: the anchor stays at the same fraction.
    import math

    before = (math.log10(1000.0) - math.log10(20.0)) / 3.0
    after = (math.log10(1000.0) - math.log10(low)) / (math.log10(high) - math.log10(low))
    assert after == pytest.approx(before)
    assert zoomed_limits((0.0, 10.0), 5.0, 0.5, "linear") == (2.5, 7.5)
    # A log axis cannot be zoomed about a non-positive anchor: unchanged.
    assert zoomed_limits((20.0, 20000.0), -1.0, 0.5, "log") == (20.0, 20000.0)


def test_a_view_cannot_leave_the_home_range() -> None:
    assert clamped_limits((-5.0, 5.0), (0.0, 10.0), "linear") == (0.0, 10.0)
    assert clamped_limits((8.0, 14.0), (0.0, 10.0), "linear") == (4.0, 10.0)
    assert clamped_limits((2.0, 4.0), (0.0, 10.0), "linear") == (2.0, 4.0)
    # A reversed axis stays reversed.
    assert clamped_limits((6.0, 2.0), (0.0, 10.0), "linear") == (6.0, 2.0)
    wide = clamped_limits((10.0, 50000.0), (20.0, 20000.0), "log")
    assert wide[0] >= 20.0 - 1e-9 and wide[1] <= 20000.0 + 1e-9


def test_the_crosshair_reads_every_trace_at_the_pointer(view: PlotView) -> None:
    x, y = _point(view, 0.5, 0.5)
    _send(view, "motion_notify_event", x, y)
    assert view.position.text().startswith("Frequency")
    assert "Hz" in view.position.text()
    text = view.values.text()
    assert "smoothed" in text and "flat" in text
    assert "2.0 dB" in text
    # The crosshair is drawn on the canvas: leaving the axes removes it again.
    _send(view, "motion_notify_event", 1.0, 1.0)
    assert view.position.text() == ""
    assert view.hint.isVisibleTo(view)


def test_the_wheel_zooms_about_the_pointer_and_fit_returns(view: PlotView) -> None:
    ax = view.data_axes()[0]
    home = tuple(ax.get_xlim())
    x, y = _point(view, 0.5, 0.5)
    _send(view, "scroll_event", x, y, step=3)
    zoomed = tuple(ax.get_xlim())
    assert zoomed[1] / zoomed[0] < home[1] / home[0]
    assert home[0] <= zoomed[0] and zoomed[1] <= home[1]
    # Zooming out past where the graph was drawn is not possible.
    _send(view, "scroll_event", x, y, step=-40)
    assert tuple(ax.get_xlim()) == pytest.approx(home)
    _send(view, "scroll_event", x, y, step=3)
    view.reset_view()
    assert tuple(ax.get_xlim()) == pytest.approx(home)


def test_a_drag_pans_a_zoomed_graph_and_a_double_click_fits(view: PlotView) -> None:
    ax = view.data_axes()[0]
    home = tuple(ax.get_xlim())
    x, y = _point(view, 0.5, 0.5)
    _send(view, "scroll_event", x, y, step=4)
    before = tuple(ax.get_xlim())
    _send(view, "button_press_event", x, y, button=1)
    _send(view, "motion_notify_event", x - 120, y, button=1)
    _send(view, "button_release_event", x - 120, y, button=1)
    after = tuple(ax.get_xlim())
    # Dragging left moves the window to higher frequencies, at the same width.
    assert after[0] > before[0]
    assert after[1] / after[0] == pytest.approx(before[1] / before[0], rel=1e-6)
    _send(view, "button_press_event", x, y, button=1, dblclick=True)
    assert tuple(ax.get_xlim()) == pytest.approx(home)


def test_zoom_mode_draws_a_box_and_zooms_into_it(view: PlotView) -> None:
    ax = view.data_axes()[0]
    home = tuple(ax.get_xlim())
    view.zoom_button.click()
    assert view.mode == "zoom"
    x0, y0 = _point(view, 0.3, 0.3)
    x1, y1 = _point(view, 0.6, 0.7)
    _send(view, "button_press_event", x0, y0, button=1)
    _send(view, "motion_notify_event", x1, y1, button=1)
    _send(view, "button_release_event", x1, y1, button=1)
    low, high = ax.get_xlim()
    assert low > home[0] and high < home[1]
    # A click without a drag is not a zoom.
    view.reset_view()
    _send(view, "button_press_event", x0, y0, button=1)
    _send(view, "button_release_event", x0 + 1, y0, button=1)
    assert tuple(ax.get_xlim()) == pytest.approx(home)
    view.pan_button.click()
    assert view.mode == "pan"


def test_copy_image_puts_the_graph_on_the_clipboard(app: QApplication, view: PlotView) -> None:
    app.clipboard().clear()
    view.copy_image()
    assert not app.clipboard().image().isNull()


def test_save_image_writes_a_png(
    view: PlotView, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from reverbscope.ui import plotview

    target = tmp_path / "graph.png"
    monkeypatch.setattr(plotview, "ask_save_path", lambda *_a, **_k: target)
    view.save_image()
    assert target.read_bytes().startswith(b"\x89PNG")
    monkeypatch.setattr(plotview, "ask_save_path", lambda *_a, **_k: None)
    view.save_image()  # cancelled: nothing happens


def test_a_placeholder_or_3d_figure_has_no_crosshair(app: QApplication) -> None:
    widget = PlotView()
    widget.resize(600, 400)
    widget.show()
    widget.figure.add_subplot(111, projection="3d")
    widget.redraw()
    widget.canvas.draw()
    assert widget.data_axes() == []
    _send(widget, "motion_notify_event", 300.0, 200.0)  # must not raise
    widget.close()


# --- the shell ---------------------------------------------------------------------------


def _window_with_result(short_sweep: SweepSettings) -> MainWindow:
    result = analyze(
        synthetic_recording(short_sweep, make_rir(48000, rt60_s=0.3), noise_rms=1e-5),
        Reference.from_settings(short_sweep),
    )
    window = MainWindow()
    window.state.result = result
    window.state.findings = interpret(result, "generic")
    window.show()
    window.show_results()
    return window


def test_the_rail_follows_the_page_and_opens_pages(
    app: QApplication, short_sweep: SweepSettings
) -> None:
    window = MainWindow()
    window.show()
    rail = window.rail
    assert rail.button("home").isChecked()
    # Nothing to show yet: the Results button is off.
    assert not rail.button("results").isEnabled()
    rail.button("measure").click()
    assert window.stack.currentWidget() is window.standalone
    assert rail.button("measure").isChecked()
    window.show_mode("universal_daw")
    assert rail.button("measure").isChecked()
    window.show_compare()
    assert rail.button("compare").isChecked()
    rail.button("home").click()
    assert window.stack.currentWidget() is window.home
    assert rail.button("home").isChecked()
    window.close()

    window = _window_with_result(short_sweep)
    assert window.rail.button("results").isEnabled()
    window.show_compare()
    window.rail.button("results").click()
    assert window.stack.currentWidget() is window.results
    assert window.rail.button("results").isChecked()
    window.close()


def test_the_rail_measure_button_returns_to_the_mode_used_last(app: QApplication) -> None:
    window = MainWindow()
    window.show()
    window.show_mode("universal_daw")
    window.rail.button("home").click()
    window.rail.button("measure").click()
    assert window.stack.currentWidget() is window.daw
    window.close()


def test_the_status_bar_names_the_session_on_screen(
    app: QApplication, short_sweep: SweepSettings
) -> None:
    window = _window_with_result(short_sweep)
    window.state.session.room_name = "Booth A"
    window.show_results()
    assert "Booth A" in window._status_info.text()
    assert "48000 Hz" in window._status_info.text()
    window.close()


def test_the_mode_switch_changes_the_mode_and_shows_the_current_one(app: QApplication) -> None:
    window = MainWindow()
    window.show()
    window.show_mode("universal_daw")
    assert window.daw.mode_switch._buttons["universal_daw"].isChecked()
    window.daw.mode_switch._buttons["demo"].click()
    assert window.stack.currentWidget() is window.standalone
    assert window.standalone.demo_mode
    assert window.standalone.mode_switch._buttons["demo"].isChecked()
    window.standalone.mode_switch._buttons["standalone"].click()
    assert not window.standalone.demo_mode
    assert window.standalone.mode_switch._buttons["standalone"].isChecked()
    window.close()


def test_the_test_signal_preview_follows_the_settings(app: QApplication) -> None:
    window = MainWindow()
    window.show()
    window.show_mode("universal_daw")
    page = window.daw
    ax = page.preview.figure.axes[0]
    assert "10 s" in ax.get_title()
    page.duration.setValue(20.0)
    ax = page.preview.figure.axes[0]
    assert "20 s" in ax.get_title()
    t, f = ax.lines[0].get_data()
    assert f[0] == pytest.approx(20.0) and f[-1] == pytest.approx(20000.0)
    assert t[0] == pytest.approx(1.0) and t[-1] == pytest.approx(21.0)
    window.close()


def test_the_results_workspace_has_graphs_and_an_inspector(
    app: QApplication, short_sweep: SweepSettings
) -> None:
    window = _window_with_result(short_sweep)
    results = window.results
    titles = [results.tabs.tabText(i) for i in range(results.tabs.count())]
    assert "RT60 by Band" in titles
    assert titles[-1] == "Placement"
    # The key figures stay on screen beside the graph, whatever tab is open.
    assert results.figures.rt60.value.text().endswith(" s")
    assert results.figures.health_chip.text()
    results.tabs.setCurrentWidget(results.bands_tab)
    ax = results.bands_tab.figure.axes[0]
    assert "octave band" in ax.get_title()
    labels = [line.get_label() for line in ax.get_lines()]
    assert "T30" in labels
    # View menu: hide the inspector, fit the graph.
    window.inspector_action.setChecked(False)
    assert results.inspector.isHidden()
    window.inspector_action.setChecked(True)
    assert not results.inspector.isHidden()
    results.bands_tab.zoom(ax, 250.0, 0.4, 0.3, "xy")
    results.fit_graph()
    assert tuple(ax.get_xlim()) == pytest.approx(results.bands_tab._ensure_home()[id(ax)][0])
    window.close()


def test_a_healthy_measurement_shows_no_health_card_on_the_overview(
    app: QApplication, short_sweep: SweepSettings
) -> None:
    window = _window_with_result(short_sweep)
    overview = window.results.overview
    assert overview.health_chip.text() == "GOOD"
    assert overview.health_card.isHidden()
    window.close()


def test_drawing_the_graph_again_does_not_pile_up_crosshairs(view: PlotView) -> None:
    ax = view.data_axes()[0]
    for _ in range(3):
        x, y = _point(view, 0.5, 0.5)
        _send(view, "motion_notify_event", x, y)
        view.redraw()
        view.canvas.draw()
    x, y = _point(view, 0.5, 0.5)
    _send(view, "motion_notify_event", x, y)
    helpers = [line for line in ax.get_lines() if str(line.get_label()).startswith("_")]
    # One vertical and one horizontal crosshair line, and one marker per trace.
    assert len([line for line in helpers if line.get_label() == "_crosshair"]) == 2
    assert len([line for line in helpers if line.get_label() == "_marker"]) == 2
