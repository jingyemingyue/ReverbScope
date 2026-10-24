"""The workstation's chart views and its model, without the main window.

These carry the risk assertions of the matplotlib plots they replace (dash
patterns, legend reasons, the no-curves message, chrome that follows the
scheme) and the GUI 2.0 additions: overlays in list colours, the baseline,
the cursor readout's speed, and display processing that leaves the result
untouched.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

import numpy as np
import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from reverbscope.core.pipeline import Reference, analyze, synthetic_recording
from reverbscope.i18n import _
from reverbscope.models.configuration import SweepSettings
from reverbscope.models.result import AnalysisResult
from reverbscope.models.session import MeasurementSession
from tests.conftest import make_rir

pytestmark = pytest.mark.gui


@pytest.fixture(scope="module")
def app() -> Any:
    application = QApplication.instance() or QApplication([])
    from reverbscope.ui.theme import apply_application_chrome

    apply_application_chrome(application)  # type: ignore[arg-type]
    return application


@pytest.fixture(scope="module")
def result() -> AnalysisResult:
    sweep = SweepSettings(duration_s=2.0, pre_silence_s=1.0, post_silence_s=1.5, level_dbfs=-12.0)
    ir = make_rir(sweep.sample_rate, rt60_s=0.35, reflections=[(0.018, 0.35)])
    return analyze(synthetic_recording(sweep, ir, noise_rms=1e-5), Reference.from_settings(sweep))


def _model(*results: AnalysisResult, folder: Path | None = None) -> Any:
    from reverbscope.ui.workspace import WorkspaceModel

    model = WorkspaceModel()
    for index, item in enumerate(results):
        if folder is None:
            model.add_take(
                MeasurementSession(), item, [], "", "generic", unsaved=False, synthetic=True
            )
        else:
            model.add_session(folder / f"take-{index}", MeasurementSession(), item)
    return model


def _shown(view: Any, app: Any) -> Any:
    view.resize(1100, 700)
    view.show()
    view.redraw()
    app.processEvents()
    return view


def test_exact_ranges_survive_processing_and_frame_restores_defaults(
    app: Any, result: AnalysisResult
) -> None:
    from reverbscope.ui.views.frequency import FrequencyView

    model = _model(result, result)
    model.set_baseline(model.entries()[0].key)
    view = _shown(FrequencyView(model), app)
    chart = view.chart
    chart.set_axis_ranges((80.0, 300.0), (-20.0, 15.0))
    view.smoothing.setCurrentIndex(view.smoothing.findData(6))
    app.processEvents()
    assert chart.visible_x_range() == pytest.approx((80.0, 300.0))
    assert chart.view_box.viewRange()[1] == pytest.approx((-20.0, 15.0))
    assert view.diff.visible_x_range() == pytest.approx((80.0, 300.0))
    # Mouse zoom/pan uses the same retention path as exact limits.
    chart.reset_view()
    chart.view_box.setXRange(np.log10(100), np.log10(500), padding=0)
    chart.view_box.sigRangeChangedManually.emit([True, False])
    view.show_raw.setChecked(True)
    app.processEvents()
    assert chart.visible_x_range() == pytest.approx((100.0, 500.0))
    chart.reset_button.click()
    assert chart.visible_x_range() == pytest.approx(view._x_default)
    view.diff.set_axis_ranges((120.0, 800.0), (-3.0, 3.0))
    view.align.setChecked(True)
    app.processEvents()
    assert chart.visible_x_range() == pytest.approx((120.0, 800.0))
    assert view.diff.view_box.viewRange()[1] == pytest.approx((-3.0, 3.0))
    view.diff.reset_button.click()
    assert chart.visible_x_range() == pytest.approx(view._x_default)
    view.resize(760, 480)
    chart.set_axis_ranges((80.0, 300.0), (-100.0, 20.0))
    for _step in range(3):
        app.processEvents()
    assert view.diff.visible_x_range() == pytest.approx((80.0, 300.0))
    assert view.diff.plot_item.getAxis("left").width() == chart.plot_item.getAxis("left").width()
    view.close()


def test_frequency_axis_limits_use_hz_and_reject_invalid_ranges(app: Any) -> None:
    from reverbscope.ui.axis_ranges import AxisRangesDialog
    from reverbscope.ui.plotkit import X_TIME_MS, ChartPanel

    chart = ChartPanel(X_TIME_MS, y_frequency=True)
    chart.set_axis_ranges((-5.0, 200.0), (100.0, 8000.0))
    assert chart.view_box.viewRange()[0] == pytest.approx((-5.0, 200.0))
    assert chart.view_box.viewRange()[1] == pytest.approx(np.log10([100.0, 8000.0]))
    before = chart.view_box.viewRange()
    for x, y in (
        ((10.0, -10.0), (100.0, 8000.0)),
        ((-5.0, 200.0), (0.0, 8000.0)),
        ((-5.0, float("nan")), (100.0, 8000.0)),
    ):
        with pytest.raises(ValueError):
            chart.set_axis_ranges(x, y)
        assert chart.view_box.viewRange() == before
    dialog = AxisRangesDialog(
        "Time (ms)", "Frequency (Hz)", (-5, 200), (100, 8000), y_frequency=True
    )
    dialog.fields[0][0].setValue(300)
    assert not dialog.apply_button.isEnabled()
    dialog.accept()
    assert dialog.result() == 0
    dialog.fields[0][0].setValue(-5)
    assert dialog.apply_button.isEnabled()
    assert dialog.ranges() == ((-5, 200), (100, 8000))
    dialog.reject()
    chart.dispose()


def test_redrawing_a_chart_clears_the_previous_cursor_readout(app: Any) -> None:
    from reverbscope.ui.plotkit import ChartPanel

    chart = ChartPanel()
    chart.add_curve("Old take", [1, 2, 3], [4, 5, 6], color="#177e89")
    chart.show_cursor(2, 0)
    assert "Old take" in chart._readout_full
    chart.clear()
    assert chart.readout.text() == ""
    assert chart.readout.toolTip() == ""
    assert not chart.cursor_line.isVisible()
    chart.dispose()


def test_all_bands_mode_draws_broadband_solid_and_each_band_with_its_own_dashes(
    app: Any, result: AnalysisResult
) -> None:
    """The user guide: octave bands use changing dash patterns so colour is
    not the only cue; Broadband is the only solid line."""
    from reverbscope.ui.views.decay import ALL_BANDS, DecayView

    view = DecayView(_model(result))
    _shown(view, app)
    view.band.setCurrentIndex(view.band.findData(ALL_BANDS))
    view.redraw()
    series = view.chart.series
    assert len(series) == 1 + len(result.decay.bands) >= 9
    assert series[0].dash is None and series[0].style == Qt.PenStyle.SolidLine
    patterns = [s.dash for s in series[1:]]
    assert all(patterns), "a band is drawn solid like Broadband"
    assert len(set(patterns)) == len(patterns)
    view.close()


def test_decay_legend_gives_the_reason_a_band_has_no_rt60(app: Any) -> None:
    """Every band without an RT60 was labelled "insufficient range", also the
    ones outside the sweep (the table said n/a)."""
    from reverbscope.ui.views.decay import ALL_BANDS, DecayView

    sweep = SweepSettings(duration_s=2.0, post_silence_s=1.5, start_hz=300.0)
    high_start = analyze(
        synthetic_recording(sweep, make_rir(48000, rt60_s=0.4), noise_rms=1e-5),
        Reference.from_settings(sweep),
    )
    view = DecayView(_model(high_start))
    _shown(view, app)
    view.band.setCurrentIndex(view.band.findData(ALL_BANDS))
    view.redraw()
    # A band with a curve but no RT60 says why in its legend name; a band
    # with no curve at all (outside the sweep) says why under the chart.
    for series in view.chart.series[1:]:
        assert "RT60" in series.name or "(" in series.name
    assert "63 Hz (outside the excitation range)" in view.notes.text()
    view.close()


def test_frequency_response_draws_the_stored_curve_dotted_and_the_display_curve_solid(
    app: Any, result: AnalysisResult
) -> None:
    from reverbscope.ui.views.frequency import FrequencyView

    view = FrequencyView(_model(result))
    view.show_raw.setChecked(True)
    _shown(view, app)
    styles = {s.style for s in view.chart.series}
    assert Qt.PenStyle.DotLine in styles
    assert Qt.PenStyle.SolidLine in styles
    # Every curve says how it was processed (labelled display processing).
    assert all(s.processing for s in view.chart.series if s.legend)
    view.close()


def test_a_session_saved_without_curves_says_so_on_the_fr_and_decay_charts(
    app: Any, result: AnalysisResult, tmp_path: Path
) -> None:
    """A session saved with --no-curves drew empty axes with every band in
    the legend, as if the measurement had failed."""
    from reverbscope.io.session_store import load_measurement, save_measurement
    from reverbscope.ui.views.decay import DecayView
    from reverbscope.ui.views.frequency import FrequencyView

    folder = tmp_path / "no-curves"
    save_measurement(
        folder, MeasurementSession(), result, include_curves=False, copy_recording=False
    )
    loaded = load_measurement(folder).result
    model = _model(loaded)
    for view_type, text in (
        (FrequencyView, "No frequency response stored with this session"),
        (DecayView, "No decay curves stored with this session"),
    ):
        view = _shown(view_type(model), app)
        assert view.chart.message.isVisible()
        assert view.chart.message.text() == text
        assert view.chart.series == []
        view.close()


def test_chart_chrome_follows_the_colour_scheme(
    app: Any, result: AnalysisResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    from reverbscope.ui.theme import color_scheme, tokens
    from reverbscope.ui.views.decay import DecayView

    view = _shown(DecayView(_model(result)), app)
    backgrounds = []
    for scheme in ("dark", "light"):
        monkeypatch.setenv("REVERBSCOPE_COLOR_SCHEME", scheme)
        assert color_scheme() == scheme
        view.restyle()
        background = view.chart.plot.backgroundBrush().color().name()
        assert background == tokens()["surface"].lower()
        backgrounds.append(background)
    assert backgrounds[0] != backgrounds[1]
    view.close()


def test_overlays_are_drawn_in_list_colours_with_the_current_on_top(
    app: Any, result: AnalysisResult, tmp_path: Path
) -> None:
    from reverbscope.ui.views.frequency import FrequencyView

    model = _model(result, result, result, folder=tmp_path)
    keys = [entry.key for entry in model.entries()]
    # Opening shows each measurement. Hide the third; selection does not draw it back.
    model.set_overlay(keys[2], False)
    model.set_current(keys[0])
    assert model.current_key == keys[0]
    assert model.is_visible(keys[0]) and model.is_visible(keys[1])
    assert not model.is_visible(keys[2])
    view = _shown(FrequencyView(model), app)
    drawn = [s for s in view.chart.series if s.key in keys]
    assert [s.key for s in drawn] == [keys[1], keys[0]]
    assert [s.color for s in drawn] == [model.entry(k).color for k in (keys[1], keys[0])]
    assert drawn[-1].readout and not drawn[0].readout
    assert drawn[-1].width > drawn[0].width
    # Unticking removes the curve and does not clear the selection.
    model.set_overlay(keys[1], False)
    app.processEvents()
    assert [s.key for s in view.chart.series if s.key in keys] == [keys[0]]
    model.set_overlay(keys[0], False)
    app.processEvents()
    assert model.current_key == keys[0]
    assert [s.key for s in view.chart.series if s.key in keys] == []
    # The baseline does not select the measurement or turn it back on.
    model.set_baseline(keys[1])
    app.processEvents()
    assert model.current_key == keys[0]
    assert not model.is_visible(keys[1])
    assert model.baseline_key == keys[1]
    view.close()


def test_display_processing_leaves_the_result_unchanged(app: Any, result: AnalysisResult) -> None:
    from reverbscope.ui.views.frequency import FrequencyView

    before = result.to_dict()
    view = FrequencyView(_model(result))
    _shown(view, app)
    for index in range(view.smoothing.count()):
        view.smoothing.setCurrentIndex(index)
        view.redraw()
    assert result.to_dict() == before
    view.close()


def test_cursor_readout_with_six_long_curves_is_quick(app: Any) -> None:
    """GUI_2_ARCHITECTURE.md §7: the readout keeps up with the mouse with six
    131072-point curves (the stored frequency response of a 48 kHz take)."""
    from reverbscope.ui.plotkit import X_FREQUENCY, ChartPanel

    chart = ChartPanel(X_FREQUENCY, x_label="Hz", y_label="dB", y_unit="dB")
    chart.resize(1000, 500)
    chart.show()
    f = np.linspace(1.0, 24_000.0, 131_072)
    for index in range(6):
        chart.add_curve(
            f"take {index}",
            f,
            np.sin(f / 500.0 + index) * 10.0,
            color="#3366cc",
            readout=index == 5,
        )
    app.processEvents()
    times = []
    for x in np.linspace(np.log10(30.0), np.log10(20_000.0), 40):
        start = time.perf_counter()
        chart.show_cursor(float(x), 0.0)
        times.append(time.perf_counter() - start)
    assert "Hz" in chart.readout.text() and "dB" in chart.readout.text()
    # The target is about 50 ms; the bound leaves room for a slow CI runner.
    assert float(np.median(times)) < 0.05, times
    chart.close()


@pytest.mark.parametrize("width", [480, 1000])
@pytest.mark.parametrize("name", ["take 5", "测量记录 / " * 60])
def test_cursor_units_survive_toolbar_and_long_names(app: Any, width: int, name: str) -> None:
    from reverbscope.ui.plotkit import X_FREQUENCY, ChartPanel

    chart = ChartPanel(X_FREQUENCY, x_label="Hz", y_label="dB", y_unit="dB")
    chart.resize(width, 400)
    chart.show()
    app.processEvents()
    # Qt's platform style may impose a minimum wider than the requested size
    # (494 px on Windows). The name must not widen that actual viewport.
    initial_width = chart.width()
    chart.add_curve(name, [1000, 20000], [1.0, 8.0], color="#3366cc")
    app.processEvents()
    chart.show_cursor(float(np.log10(20000)), 0.0)
    shown = chart.readout.text()
    assert shown.startswith("20 kHz") and shown.endswith("8.0 dB"), shown
    assert chart.width() == initial_width
    assert chart.readout.geometry().top() > chart.reset_button.geometry().bottom()
    assert chart.readout.fontMetrics().horizontalAdvance(shown) <= chart.readout.width()
    full = chart.readout_text(float(np.log10(20000)), 0.0)
    assert chart.readout.toolTip() == (full if shown != full else "")
    # Resize after a cursor update must preserve the same units too.
    chart.resize(600, 400)
    app.processEvents()
    assert chart.readout.text().endswith("8.0 dB")
    chart.close()


def test_baseline_and_comparison_are_cached_per_pair(
    app: Any, result: AnalysisResult, tmp_path: Path
) -> None:
    from reverbscope.ui.comparison import current_comparison

    model = _model(result, result, folder=tmp_path)
    first, second = (entry.key for entry in model.entries())
    assert current_comparison(model, same_gain=False) is None
    model.set_baseline(first)
    model.set_current(second)
    compared = current_comparison(model, same_gain=False)
    assert compared is not None
    assert current_comparison(model, same_gain=False) is compared
    assert current_comparison(model, same_gain=True) is not compared
    model.set_current(first)
    # The baseline against itself is not a comparison.
    assert current_comparison(model, same_gain=False) is None


def test_waterfall_csv_holds_the_slices_without_the_perspective_shift(
    app: Any, result: AnalysisResult, tmp_path: Path
) -> None:
    from reverbscope.ui.views.timefreq import WaterfallView

    view = WaterfallView(_model(result))
    view.perspective.setChecked(True)
    _shown(view, app)
    deadline = time.monotonic() + 30
    while view.result is None and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    assert view.result is not None
    path = view.chart.export_csv(tmp_path / "waterfall.csv")
    rows = [line.split(",") for line in path.read_text(encoding="utf-8").splitlines()]
    last = _("{time:.1f} ms").format(time=float(view.result.times_ms[-1]))
    xs = [float(row[1]) for row in rows if row[0] == last]
    ys = [float(row[2]) for row in rows if row[0] == last]
    finite = np.isfinite(view.result.levels_db[-1])
    assert xs[0] == pytest.approx(float(view.result.freqs_hz[finite][0]), rel=1e-5)
    assert max(ys) == pytest.approx(float(np.nanmax(view.result.levels_db[-1])), abs=1e-3)
    view.shutdown()
    view.close()


def test_the_strip_shows_the_device_the_page_picked_after_a_refill(app: Any) -> None:
    from PySide6.QtWidgets import QComboBox

    from reverbscope.ui.measure_strip import _mirror_combo

    page, strip = QComboBox(), QComboBox()
    page.addItems(["a", "b"])
    _mirror_combo(strip, page)
    page.blockSignals(True)
    page.clear()
    page.addItems(["x", "y", "z"])
    page.setCurrentIndex(2)  # the host API's default device
    page.blockSignals(False)
    app.processEvents()
    assert strip.currentText() == "z"
    strip.setCurrentIndex(0)
    assert page.currentText() == "x"


def test_decay_view_overlays_a_two_slope_fit_and_only_then(
    app: Any, result: AnalysisResult
) -> None:
    """The double-slope fit of the current band is drawn on its curve, with
    each slope alone and the turning point; a single-slope band draws only
    its curve and says so in the note."""
    from reverbscope.core.pipeline import analyze_impulse_response
    from reverbscope.models.audio import AudioSignal
    from reverbscope.models.configuration import AnalysisSettings
    from reverbscope.ui.views.decay import BROADBAND, DecayView
    from tests.unit.test_multislope import LEAD, RATE, decay

    signal = decay(0.4, 1.6, -25.0, seed=3)
    signal[LEAD] = 4.0 * float(np.sqrt(np.sum(signal**2)))
    coupled = analyze_impulse_response(
        AudioSignal(signal, RATE), AnalysisSettings(), excitation_band=(20.0, 20_000.0)
    )
    fit = coupled.decay.broadband.multi_slope
    assert fit is not None and fit.selected_slopes == 2
    view = _shown(DecayView(_model(coupled)), app)
    view.band.setCurrentIndex(view.band.findData(BROADBAND))
    view.redraw()
    names = [s.name for s in view.chart.series]
    assert _("Two-slope fit") in names
    assert _("Fast slope T1") in names and _("Slow slope T2") in names
    assert all(s.processing for s in view.chart.series if s.legend)
    assert "Two-slope fit: T1 = " in view.notes.text()
    view.close()

    single = _shown(DecayView(_model(result)), app)
    single.band.setCurrentIndex(single.band.findData(BROADBAND))
    single.redraw()
    assert [s.name for s in single.chart.series if "slope" in s.name.lower()] == []
    single.close()
