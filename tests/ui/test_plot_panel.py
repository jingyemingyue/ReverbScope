"""The chart panel of the workbench: overlays in the measurements' colours,
the selected one on top, hidden ones gone, difference mode, linked zoom
between panels on the same axis, lazy drawing, picking and CSV export."""

from __future__ import annotations

import csv
import os
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from matplotlib.axes import Axes
from matplotlib.backend_bases import MouseEvent
from PySide6.QtWidgets import QApplication, QWidget

from reverbscope.core.compare import compare
from reverbscope.core.pipeline import Reference, analyze, synthetic_recording
from reverbscope.models.comparison import ComparisonResult
from reverbscope.models.configuration import SweepSettings
from reverbscope.models.result import AnalysisResult, ResonanceCandidate
from reverbscope.models.session import MeasurementSession
from reverbscope.ui import plot_panel as plot_panel_module
from reverbscope.ui.document import Measurement, WorkspaceDocument
from reverbscope.ui.plot_data import (
    AXIS_FREQUENCY,
    AXIS_TIME_S,
    PLOT_KINDS,
    decay_curves,
    frequency_curves,
    noise_curve,
    plot_kind,
)
from reverbscope.ui.plot_panel import SCOPE_SELECTED, PlotPanel, ZoomLink
from tests.conftest import make_rir

pytestmark = pytest.mark.gui


@pytest.fixture(scope="module")
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _result(short_sweep: SweepSettings, rt60_s: float = 0.35, seed: int = 1) -> AnalysisResult:
    rate = short_sweep.sample_rate
    take = synthetic_recording(
        short_sweep,
        make_rir(rate, rt60_s=rt60_s, reflections=[(0.018, 0.35)], seed=seed),
        noise_rms=1e-5,
    )
    return analyze(take, Reference.from_settings(short_sweep))


@pytest.fixture(scope="module")
def results(short_sweep: SweepSettings) -> tuple[AnalysisResult, AnalysisResult]:
    return _result(short_sweep), _result(short_sweep, rt60_s=0.6, seed=2)


def _measurement(result: AnalysisResult, room: str, position: str) -> Measurement:
    session = MeasurementSession(room_name=room, measurement_position=position)
    return Measurement(session=session, result=result)


def _document(results: tuple[AnalysisResult, AnalysisResult]) -> tuple[WorkspaceDocument, str, str]:
    document = WorkspaceDocument()
    first = document.add(_measurement(results[0], "Booth A", "Mic 1"))
    second = document.add(_measurement(results[1], "Booth A", "Mic 2"))
    return document, first, second


def _shown(app: QApplication, panel: QWidget) -> None:
    panel.resize(800, 500)
    panel.show()
    app.processEvents()


def _curve_lines(ax: Axes) -> list:  # type: ignore[type-arg]
    """The data curves of an axes (markers and helper lines left out)."""
    return [
        line
        for line in ax.get_lines()
        if not str(line.get_label()).startswith("_")
        and line.get_linestyle() not in ("None", "")
        and len(line.get_xdata()) > 2
    ]


def _pixel(ax: Axes, x: float, y: float) -> tuple[float, float]:
    px, py = ax.transData.transform((x, y))
    return float(px), float(py)


# --- adapters -------------------------------------------------------------------------


def test_adapters_carry_the_measurement_colour_and_style(
    results: tuple[AnalysisResult, AnalysisResult],
) -> None:
    document, first, _second = _document(results)
    measurement = document.get(first)
    assert measurement is not None
    curves = frequency_curves(measurement, raw=True)
    assert [c.secondary for c in curves] == [False, True]
    assert all(c.colour == measurement.colour for c in curves)
    assert curves[0].style == measurement.style
    assert curves[0].label == "Booth A / Mic 1"
    decay = decay_curves(measurement, bands=True)
    assert decay[0].item == ("band", 0)
    assert len(decay) == 1 + len(results[0].decay.bands)
    assert decay[1].item == ("band", 1)
    assert decay_curves(measurement, bands=False)[0].x.size == decay[0].x.size
    noise = noise_curve(measurement)
    assert noise is not None and noise.x.min() > 0
    assert {k.key for k in PLOT_KINDS} == {
        "frequency",
        "decay",
        "noise",
        "impulse",
        "reflections",
        "placement",
    }
    assert plot_kind("frequency").axis == AXIS_FREQUENCY
    assert plot_kind("decay").axis == AXIS_TIME_S
    assert not plot_kind("impulse").multi
    with pytest.raises(KeyError):
        plot_kind("phase")


# --- overlays -------------------------------------------------------------------------


def test_overlay_draws_both_measurements_with_the_selected_one_on_top(
    app: QApplication, results: tuple[AnalysisResult, AnalysisResult]
) -> None:
    document, first, second = _document(results)
    panel = PlotPanel(document, ZoomLink())
    _shown(app, panel)
    ax = panel.figure.axes[0]
    lines = _curve_lines(ax)
    assert len(lines) == 2
    m1, m2 = document.get(first), document.get(second)
    assert m1 is not None and m2 is not None
    assert lines[0].get_color() == m1.colour
    assert lines[1].get_color() == m2.colour  # selected: drawn last
    assert lines[1].get_linewidth() > lines[0].get_linewidth()
    assert lines[1].get_alpha() == 1.0 and lines[0].get_alpha() == pytest.approx(0.6)
    labels = [text.get_text() for text in ax.get_legend().get_texts()]
    assert labels == ["Booth A / Mic 1", "Booth A / Mic 2"]
    assert "relative" in ax.get_ylabel() and "dB" in ax.get_ylabel()
    assert "2 measurements" in ax.get_title()
    # Selecting the other one puts it on top; nothing is hidden.
    document.set_selected(first)
    lines = _curve_lines(panel.figure.axes[0])
    assert len(lines) == 2 and lines[-1].get_color() == m1.colour
    # The baseline is named in the legend.
    document.set_baseline(second)
    labels = [text.get_text() for text in panel.figure.axes[0].get_legend().get_texts()]
    assert "Booth A / Mic 2 (baseline)" in labels
    panel.close()


def test_hiding_a_measurement_removes_its_line_and_scope_narrows(
    app: QApplication, results: tuple[AnalysisResult, AnalysisResult]
) -> None:
    document, first, second = _document(results)
    panel = PlotPanel(document, ZoomLink(), kind="decay")
    _shown(app, panel)
    assert len(_curve_lines(panel.figure.axes[0])) == 2
    document.set_visible(first, False)
    lines = _curve_lines(panel.figure.axes[0])
    m2 = document.get(second)
    assert m2 is not None
    assert len(lines) == 1 and lines[0].get_color() == m2.colour
    assert document.selected_id() == second  # hiding changes no selection
    document.set_visible(first, True)
    assert len(_curve_lines(panel.figure.axes[0])) == 2
    # Nothing visible at all: the empty state, not an empty axes.
    document.set_visible(first, False)
    document.set_visible(second, False)
    texts = [t.get_text() for t in panel.figure.axes[0].texts]
    assert texts == ["No visible measurement"]
    # "Selected only" shows the selected measurement whatever the checkboxes say.
    panel.set_scope(SCOPE_SELECTED)
    assert len(_curve_lines(panel.figure.axes[0])) == 1
    panel.close()


def test_switching_kind_keeps_the_document_untouched(
    app: QApplication, results: tuple[AnalysisResult, AnalysisResult]
) -> None:
    document, first, _second = _document(results)
    document.set_baseline(first)
    panel = PlotPanel(document, ZoomLink())
    _shown(app, panel)
    seen: list[str] = []
    panel.kind_changed.connect(seen.append)
    before = (
        document.selected_id(),
        document.baseline_id(),
        [m.id for m in document.visible()],
    )
    for key in ("decay", "noise", "impulse", "reflections", "placement", "frequency"):
        panel.kind_combo.setCurrentIndex(panel.kind_combo.findData(key))
        assert panel.kind() == key
        assert panel.figure.axes, key
    assert seen == ["decay", "noise", "impulse", "reflections", "placement", "frequency"]
    assert (
        document.selected_id(),
        document.baseline_id(),
        [m.id for m in document.visible()],
    ) == before
    # Kind-specific controls show only where they apply.
    panel.set_kind("decay")
    assert panel.bands_check.isVisible() and not panel.raw_check.isVisible()
    panel.set_kind("impulse")
    assert not panel.scope_combo.isVisible() and not panel.difference_button.isVisible()
    assert "selected measurement only" in panel.figure.get_suptitle()
    assert len(panel.figure.axes) == 2
    panel.close()


def test_single_measurement_kinds_say_when_nothing_is_selected(
    app: QApplication, results: tuple[AnalysisResult, AnalysisResult]
) -> None:
    document, _first, _second = _document(results)
    document.set_selected(None)
    panel = PlotPanel(document, ZoomLink(), kind="reflections")
    _shown(app, panel)
    texts = [t.get_text() for t in panel.figure.axes[0].texts]
    assert texts == ["No measurement selected"]
    empty = WorkspaceDocument()
    other = PlotPanel(empty, ZoomLink())
    _shown(app, other)
    assert [t.get_text() for t in other.figure.axes[0].texts] == ["No measurement loaded"]
    panel.close()
    other.close()


# --- difference mode --------------------------------------------------------------------


def test_difference_mode_draws_the_delta_axes_from_the_provider(
    app: QApplication, results: tuple[AnalysisResult, AnalysisResult]
) -> None:
    document, first, second = _document(results)
    panel = PlotPanel(document, ZoomLink())
    _shown(app, panel)
    assert not panel.difference_button.isEnabled()  # no baseline yet
    document.set_baseline(first)  # selected is the second: a candidate exists
    assert panel.difference_button.isEnabled()
    calls: list[tuple[str, str]] = []

    def provider(baseline: Measurement, candidate: Measurement) -> ComparisonResult | None:
        calls.append((baseline.id, candidate.id))
        return compare(baseline.result, candidate.result)

    panel.set_comparison_provider(provider)
    assert calls == []  # only asked in difference mode
    panel.difference_button.setChecked(True)
    assert calls == [(first, second)]
    axes = panel.figure.axes
    assert len(axes) == 2
    labels = [text.get_text() for text in axes[0].get_legend().get_texts()]
    assert labels == ["Booth A / Mic 1 (baseline)", "Booth A / Mic 2 (candidate)"]
    assert axes[1].get_ylabel() == "Δ dB"
    delta = _curve_lines(axes[1])
    assert len(delta) == 1 and len(delta[0].get_xdata()) > 10
    # Without a difference curve the lower axes says so.
    panel.set_comparison_provider(lambda _b, _c: None)
    assert [t.get_text() for t in panel.figure.axes[1].texts] == ["No difference curve"]
    # Decay: both broadband curves, labelled.
    panel.set_kind("decay")
    ax = panel.figure.axes[0]
    labels = [text.get_text() for text in ax.get_legend().get_texts()]
    assert len(labels) == 2
    assert labels[0].endswith("(baseline)") and labels[1].endswith("(candidate)")
    assert "baseline and candidate" in ax.get_title()
    # Baseline gone: the toggle is disabled and the overlay is back.
    document.set_baseline(None)
    assert not panel.difference_button.isEnabled()
    assert len(_curve_lines(panel.figure.axes[0])) == 2
    panel.close()


# --- zoom and links ---------------------------------------------------------------------


def test_wheel_zoom_links_panels_of_the_same_axis_only(
    app: QApplication, results: tuple[AnalysisResult, AnalysisResult]
) -> None:
    document, _first, _second = _document(results)
    link = ZoomLink()
    a = PlotPanel(document, link, kind="frequency")
    b = PlotPanel(document, link, kind="frequency")
    c = PlotPanel(document, link, kind="decay")
    for panel in (a, b, c):
        _shown(app, panel)
        panel.canvas.draw()
    ax = a.figure.axes[0]
    before_a = ax.get_xlim()
    before_c = c.figure.axes[0].get_xlim()
    px, py = _pixel(ax, 1000.0, float(np.mean(ax.get_ylim())))
    MouseEvent("scroll_event", a.canvas, px, py, step=1)._process()
    after = ax.get_xlim()
    assert after[0] > before_a[0] and after[1] < before_a[1]
    assert after[0] < 1000.0 < after[1]
    assert ax.get_xscale() == "log"
    assert b.figure.axes[0].get_xlim() == pytest.approx(after)
    assert c.figure.axes[0].get_xlim() == before_c  # another axis: not linked
    # Shift zooms y and does not propagate.
    before_y = ax.get_ylim()
    MouseEvent("scroll_event", a.canvas, px, py, step=1, modifiers=frozenset({"shift"}))._process()
    assert ax.get_ylim() != before_y
    assert b.figure.axes[0].get_ylim() != ax.get_ylim() or before_y == ax.get_ylim()
    # A redraw keeps the zoom; reset returns to the data limits and propagates.
    a.refresh()
    assert a.figure.axes[0].get_xlim() == pytest.approx(after)
    a.reset_zoom()
    assert a.figure.axes[0].get_xlim() == pytest.approx(before_a)
    assert b.figure.axes[0].get_xlim() == pytest.approx(before_a)
    # A disabled link stops propagation.
    link.enabled = False
    MouseEvent("scroll_event", a.canvas, px, py, step=1)._process()
    assert b.figure.axes[0].get_xlim() == pytest.approx(before_a)
    link.enabled = True
    # A panel that changes to another axis stops following.
    b.set_kind("decay")
    b.set_xlim_from_link(AXIS_FREQUENCY, (100.0, 200.0))
    assert b.figure.axes[0].get_xlim() != (100.0, 200.0)
    for panel in (a, b, c):
        panel.close()


def test_drag_pans_and_double_click_resets(
    app: QApplication, results: tuple[AnalysisResult, AnalysisResult]
) -> None:
    document, _first, _second = _document(results)
    panel = PlotPanel(document, ZoomLink(), kind="decay")
    _shown(app, panel)
    panel.canvas.draw()
    ax = panel.figure.axes[0]
    before = ax.get_xlim()
    y = float(np.mean(ax.get_ylim()))
    x0, y0 = _pixel(ax, 0.2, y)
    x1, _ = _pixel(ax, 0.4, y)
    MouseEvent("button_press_event", panel.canvas, x0, y0, button=1)._process()
    MouseEvent("motion_notify_event", panel.canvas, x1, y0, button=1)._process()
    MouseEvent("button_release_event", panel.canvas, x1, y0, button=1)._process()
    after = ax.get_xlim()
    assert after[0] == pytest.approx(before[0] - 0.2, abs=0.01)
    assert "s," in panel.readout.text() and panel.readout.text().endswith("dB")
    MouseEvent("button_press_event", panel.canvas, x0, y0, button=1, dblclick=True)._process()
    assert ax.get_xlim() == pytest.approx(before)
    panel.close()


def test_readout_formats_the_units_of_the_kind(
    app: QApplication, results: tuple[AnalysisResult, AnalysisResult]
) -> None:
    document, _first, _second = _document(results)
    panel = PlotPanel(document, ZoomLink())
    _shown(app, panel)
    panel.canvas.draw()
    ax = panel.figure.axes[0]
    px, py = _pixel(ax, 1234.0, -12.3)
    MouseEvent("motion_notify_event", panel.canvas, px, py)._process()
    assert panel.readout.text() == "1234 Hz, -12.3 dB"
    panel.set_kind("reflections")
    panel.canvas.draw()
    ax = panel.figure.axes[0]
    px, py = _pixel(ax, 5.2, -9.6)
    MouseEvent("motion_notify_event", panel.canvas, px, py)._process()
    assert panel.readout.text() == "5.2 ms, -9.6 dB"
    MouseEvent("motion_notify_event", panel.canvas, 1.0, 1.0)._process()
    assert panel.readout.text() == ""
    panel.close()


# --- lazy drawing -------------------------------------------------------------------


def test_hidden_panel_does_not_draw_until_shown(
    app: QApplication,
    results: tuple[AnalysisResult, AnalysisResult],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = WorkspaceDocument()
    panel = PlotPanel(document, ZoomLink())
    draws: list[int] = []
    monkeypatch.setattr(panel.canvas, "draw_idle", lambda: draws.append(1))
    document.add(_measurement(results[0], "Booth A", "Mic 1"))
    document.add(_measurement(results[1], "Booth A", "Mic 2"))
    panel.set_kind("decay")
    app.processEvents()
    assert draws == [] and panel.is_dirty() and not panel.figure.axes
    _shown(app, panel)
    assert len(draws) >= 1 and not panel.is_dirty()
    assert len(_curve_lines(panel.figure.axes[0])) == 2
    # Shown and clean: a document change draws once more; hidden again, it waits.
    count = len(draws)
    document.set_visible(document.measurements[0].id, False)
    assert len(draws) == count + 1
    panel.hide()
    app.processEvents()
    count = len(draws)
    document.set_visible(document.measurements[0].id, True)
    assert len(draws) == count and panel.is_dirty()
    panel.close()


# --- picking --------------------------------------------------------------------------


def test_clicking_a_marker_emits_item_selected(
    app: QApplication, results: tuple[AnalysisResult, AnalysisResult]
) -> None:
    candidate = ResonanceCandidate(
        frequency_hz=80.0,
        level_above_baseline_db=6.0,
        narrowband_decay_20db_s=0.3,
        filter_ringing_20db_s=0.05,
        decay_distinguishable=True,
    )
    with_resonance = replace(
        results[0], resonances=replace(results[0].resonances, candidates=(candidate,))
    )
    document = WorkspaceDocument()
    document.add(_measurement(with_resonance, "Booth A", "Mic 1"))
    document.add(_measurement(results[1], "Booth A", "Mic 2"), select=False)
    panel = PlotPanel(document, ZoomLink())
    _shown(app, panel)
    panel.canvas.draw()
    picked: list[tuple[str, int]] = []
    panel.item_selected.connect(lambda name, index: picked.append((name, index)))
    items = panel.pick_items()
    assert [item for _artist, item in items] == [("resonance", 0)]
    artist = items[0][0]
    px, py = _pixel(
        panel.figure.axes[0], float(artist.get_xdata()[0]), float(artist.get_ydata()[0])
    )
    MouseEvent("button_press_event", panel.canvas, px + 3.0, py - 2.0, button=1)._process()
    assert picked == [("resonance", 0)]
    assert panel.highlight() == {"resonance": 0}
    # Far from the marker nothing is picked.
    MouseEvent("button_press_event", panel.canvas, px + 60.0, py + 40.0, button=1)._process()
    assert picked == [("resonance", 0)]
    # Reflection markers of the selected measurement, on the reflections chart.
    panel.set_kind("reflections")
    panel.canvas.draw()
    items = panel.pick_items()
    assert [item for _artist, item in items] == [("reflection", 0)]
    artist = items[0][0]
    px, py = _pixel(
        panel.figure.axes[0], float(artist.get_xdata()[0]), float(artist.get_ydata()[0])
    )
    MouseEvent("button_press_event", panel.canvas, px, py, button=1)._process()
    assert picked[-1] == ("reflection", 0)
    # Decay bands: the broadband curve is band 0; a highlight dims the others.
    panel.set_kind("decay")
    panel.bands_check.setChecked(True)
    panel.canvas.draw()
    items = {item: artist for artist, item in panel.pick_items()}
    assert ("band", 0) in items and ("band", 1) in items
    panel.set_highlight("band", 1)
    lines = _curve_lines(panel.figure.axes[0])
    emphasised = [line for line in lines if line.get_linewidth() > 3.0]
    assert len(emphasised) == 1
    # Selecting another measurement clears the highlight.
    document.set_selected(document.measurements[1].id)
    assert panel.highlight() == {}
    panel.close()


# --- export -----------------------------------------------------------------------------


def test_export_csv_writes_the_curves_shown(
    app: QApplication,
    results: tuple[AnalysisResult, AnalysisResult],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document, _first, _second = _document(results)
    panel = PlotPanel(document, ZoomLink(), kind="decay")
    _shown(app, panel)
    target = tmp_path / "curves.csv"
    monkeypatch.setattr(plot_panel_module, "ask_save_path", lambda *_a, **_k: target)
    messages: list[str] = []
    panel.status_message.connect(messages.append)
    message = panel.export_csv()
    assert message == f"Wrote {target}" and messages == [message]
    with target.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.reader(handle))
    header = rows[0]
    assert len(header) == 4
    assert header[0].startswith("Booth A / Mic 1") and "Time (s)" in header[0]
    assert "dB" in header[1] and header[2].startswith("Booth A / Mic 2")
    assert len(rows) - 1 == max(
        results[0].decay.broadband.edc_time_s.size, results[1].decay.broadband.edc_time_s.size
    )
    assert float(rows[1][1]) == pytest.approx(float(results[0].decay.broadband.edc_db[0]), abs=0.01)
    # Cancelled: nothing written, nothing reported.
    monkeypatch.setattr(plot_panel_module, "ask_save_path", lambda *_a, **_k: None)
    assert panel.export_csv() == ""
    # PNG goes through the shared exporter.
    png = tmp_path / "chart.png"
    monkeypatch.setattr(
        plot_panel_module,
        "export_figure_png",
        lambda _parent, figure, _stem: str(figure.savefig(png)),
    )
    panel.export_png()
    assert png.is_file()
    panel.close()
