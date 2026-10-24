"""The measurement-tool polish: plain axes, band ticks, readouts, tables, status bar.

Display only. Every check here reads what is drawn or copied; none of it
changes a stored number (the analysis result is compared before and after).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QTableWidget

from reverbscope.core.pipeline import Reference, analyze, synthetic_recording
from reverbscope.models.configuration import SweepSettings
from reverbscope.models.result import AnalysisResult, Validity
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


def _model(*results: AnalysisResult) -> Any:
    from reverbscope.ui.workspace import WorkspaceModel

    model = WorkspaceModel()
    for item in results:
        model.add_take(MeasurementSession(), item, [], "", "generic", unsaved=False, synthetic=True)
    return model


def test_frequencies_are_written_as_the_guidelines_say() -> None:
    from reverbscope.ui.plotkit import format_frequency, format_sample_rate, format_y

    assert format_frequency(112.4) == "112 Hz"
    assert format_frequency(1234.0) == "1.2 kHz"
    assert format_frequency(1000.0) == "1 kHz"
    assert format_frequency(19726.0) == "19.7 kHz"
    assert format_sample_rate(48000) == "48 kHz"
    assert format_sample_rate(44100) == "44.1 kHz"
    assert format_y(-3.44, "dB") == "\u22123.4 dB"
    assert format_y(0.512, "s") == "0.51 s"


def test_axes_never_rescale_seconds_and_use_a_real_minus(app: Any) -> None:
    """pyqtgraph drew 0.4–0.8 s as "400–800" with "(x0.001)" in the title."""
    from reverbscope.ui.plotkit import X_TIME_S, ChartPanel

    chart = ChartPanel(X_TIME_S, x_label="Time (s)", y_label="Level (dB)")
    chart.add_curve("take", [0.0, 0.5, 1.0], [0.42, 0.61, 0.83], color="#177e89")
    app.processEvents()
    left = chart.plot_item.getAxis("left")
    assert left.autoSIPrefix is False
    assert chart.plot_item.getAxis("bottom").autoSIPrefix is False
    assert left.tickStrings([0.4, 0.6, 0.8], 1.0, 0.2) == ["0.4", "0.6", "0.8"]
    assert left.tickStrings([-10.0, 0.0], 1.0, 10.0) == ["\u221210", "0"]
    chart.dispose()


def test_band_charts_tick_on_the_band_centres_with_iec_names(
    app: Any, result: AnalysisResult
) -> None:
    from reverbscope.ui.plotkit import LogFrequencyAxis, nominal_band_label
    from reverbscope.ui.views.decay import DecayView

    assert nominal_band_label(31.62) == "31.5"
    assert nominal_band_label(1000.0) == "1k"
    assert nominal_band_label(3162.0) == "3.15k"
    view = DecayView(_model(result))
    view.resize(1100, 700)
    view.show()
    view.redraw()
    app.processEvents()
    axis = view.bands_chart.plot_item.getAxis("bottom")
    assert isinstance(axis, LogFrequencyAxis)
    lo, hi = view.bands_chart.view_box.viewRange()[0]
    ticks = axis.tickValues(lo, hi, 800)
    labels = axis.tickStrings(ticks[0][1], 1.0, 1.0)
    assert labels[:3] == ["63", "125", "250"] and "1k" in labels and "8k" in labels
    assert "100" not in labels and "200" not in labels
    view.close()


def test_one_third_octave_ticks_keep_octave_labels_when_crowded(app: Any) -> None:
    from reverbscope.ui.plotkit import NOMINAL_BANDS, X_FREQUENCY, ChartPanel

    chart = ChartPanel(X_FREQUENCY)
    centres = [hz for hz, _name in NOMINAL_BANDS if 50.0 <= hz <= 10000.0]
    chart.set_band_ticks(centres)
    axis = chart.plot_item.getAxis("bottom")
    major, minor = axis.tickValues(1.6, 4.1, 300)
    names = axis.tickStrings(major[1], 1.0, 1.0)
    assert names == ["63", "125", "250", "500", "1k", "2k", "4k", "8k"]
    assert len(minor[1]) == len(centres) - len(names)
    chart.set_band_ticks(None)
    assert axis.tickStrings(axis.tickValues(2.0, 3.0, 400)[0][1], 1.0, 1.0)[0] == "100"
    chart.dispose()


def test_the_readout_lists_every_visible_curve_with_the_current_one_last(app: Any) -> None:
    import numpy as np

    from reverbscope.ui.plotkit import X_FREQUENCY, ChartPanel

    chart = ChartPanel(X_FREQUENCY, y_unit="dB")
    chart.add_curve("A-1", [100, 1000], [-2.0, -2.0], color="#177e89")
    chart.add_curve("B-1", [100, 1000], [-5.0, -5.0], color="#d9731f", readout=True)
    hidden = chart.add_curve("C-1", [100, 1000], [9.0, 9.0], color="#6b5bd2")
    chart.set_series_visible(hidden, False)
    text = chart.readout_text(float(np.log10(112.0)), 0.0)
    assert text == "112 Hz  ·  A-1 \u22122.0 dB  ·  B-1 \u22125.0 dB", text
    chart.dispose()


def test_numbers_in_tables_are_right_aligned_and_copy_as_tsv(app: Any) -> None:
    from reverbscope.ui.datatable import data_item, number_in, setup_data_table, table_tsv

    assert number_in("(0.69 s)") == pytest.approx(0.69)
    assert number_in("\u221287.1 dBFS") == pytest.approx(-87.1)
    assert number_in("C80 +1.2 dB") == pytest.approx(1.2)
    assert number_in("1 kHz") == pytest.approx(1000.0)
    assert number_in("n/a") is None
    table = QTableWidget(0, 3)
    table.setHorizontalHeaderLabels(["Band", "T30", "C80"])
    setup_data_table(table, (1, 2))
    rows = [("125 Hz", "0.82 s", "+1.0 dB"), ("1 kHz", "n/a", "+3.5 dB"), ("500 Hz", "0.43 s", "")]
    table.setSortingEnabled(False)
    table.setRowCount(len(rows))
    for r, row in enumerate(rows):
        for c, text in enumerate(row):
            table.setItem(r, c, data_item(text, numeric=c > 0, row=r))
    table.setSortingEnabled(True)
    assert table.horizontalHeader().sortIndicatorSection() == -1  # own order first
    cell = table.item(0, 1)
    assert cell.textAlignment() & Qt.AlignmentFlag.AlignRight
    assert table.horizontalHeaderItem(1).textAlignment() & Qt.AlignmentFlag.AlignRight
    assert not table.item(0, 0).textAlignment() & Qt.AlignmentFlag.AlignRight
    assert not cell.flags() & Qt.ItemFlag.ItemIsEditable
    assert table.verticalHeader().defaultSectionSize() == 28
    # Sorted by T30: numbers low to high, the word after them.
    table.sortItems(1, Qt.SortOrder.AscendingOrder)
    assert [table.item(r, 0).text() for r in range(3)] == ["500 Hz", "125 Hz", "1 kHz"]
    # By band: kilohertz above hertz.
    table.sortItems(0, Qt.SortOrder.AscendingOrder)
    assert [table.item(r, 0).text() for r in range(3)] == ["125 Hz", "500 Hz", "1 kHz"]
    assert table_tsv(table).splitlines() == [
        "Band\tT30\tC80",
        "125 Hz\t0.82 s\t+1.0 dB",
        "500 Hz\t0.43 s\t",
        "1 kHz\tn/a\t+3.5 dB",
    ]
    table.selectRow(1)
    assert table_tsv(table, selected_only=True).splitlines()[1:] == ["500 Hz\t0.43 s\t"]
    from reverbscope.ui.datatable import copy_table

    copy_table(table)
    assert QApplication.clipboard().text().startswith("Band\tT30\tC80\n")


def test_overview_tables_keep_band_order_and_align_numbers(
    app: Any, result: AnalysisResult
) -> None:
    from reverbscope.ui.views.overview import OverviewView

    before = result.to_dict(include_curves=False)
    view = OverviewView(_model(result))
    view.resize(1100, 700)
    view.show()
    view.redraw()
    app.processEvents()
    table = view.table
    assert not table.isSortingEnabled()  # bands stay low to high
    assert table.item(1, 0).text().endswith("Hz")
    assert table.item(1, 3).textAlignment() & Qt.AlignmentFlag.AlignRight
    assert result.to_dict(include_curves=False) == before
    view.close()


def test_a_valid_figure_carries_no_badge_and_an_untrusted_one_does(
    app: Any, result: AnalysisResult
) -> None:
    """GUIDELINES §13.3: "valid" is the normal case and is not marked."""
    from PySide6.QtWidgets import QLabel

    from reverbscope.labels import validity_word
    from reverbscope.ui.inspector import Inspector, _validity_chip

    assert _validity_chip(Validity.VALID) == ("", "neutral")
    word, tone = _validity_chip(Validity.UNRELIABLE)
    assert word == validity_word(Validity.UNRELIABLE) and tone == "warn"
    model = _model(result)
    inspector = Inspector(model)
    inspector.resize(320, 900)
    inspector.show()
    model.set_current(model.entries()[0].key)
    app.processEvents()
    texts = [w.text() for w in inspector.figures.findChildren(QLabel)]
    valid = validity_word(Validity.VALID)
    assert result.decay.broadband.t30.validity is Validity.VALID
    assert not any(f"· {valid}" in text for text in texts), texts
    inspector.close()


def test_status_bar_shows_the_current_measurement_format(
    app: Any, result: AnalysisResult, tmp_path: Path
) -> None:
    from reverbscope.ui.main_window import MainWindow, measurement_info_text

    model = _model(result)
    text = measurement_info_text(model.entries()[0])
    assert text.startswith("48 kHz") and "dBFS" in text and "synthetic demo" in text
    assert measurement_info_text(None) == ""
    window = MainWindow()
    window.resize(1280, 800)
    window.show()
    app.processEvents()
    assert window.measurement_info.text() == ""
    window.close()
