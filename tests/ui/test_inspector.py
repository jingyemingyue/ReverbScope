"""The inspector panel: measurement quality, diagnostics, properties, tables,
comparison and the text report of the selected measurement."""

from __future__ import annotations

import os
from dataclasses import replace

import numpy as np
import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QTableWidget, QTableWidgetItem

from reverbscope.cli.render import REPORT_CONSOLE, render_analysis
from reverbscope.core.compare import compare
from reverbscope.core.pipeline import Reference, analyze, synthetic_recording
from reverbscope.demo import DEMO_MODE
from reverbscope.health import HealthStatus, status_word
from reverbscope.interpretation import interpret, judge_comparison
from reverbscope.models.configuration import SweepSettings
from reverbscope.models.result import AnalysisResult
from reverbscope.models.session import MeasurementSession
from reverbscope.ui.document import Measurement
from reverbscope.ui.inspector import InspectorPanel, property_rows, quality_chip_text
from reverbscope.ui.results_presenter import check_group, finding_group, ranked_findings
from reverbscope.ui.widgets import KeyValueList
from tests.conftest import make_rir

pytestmark = pytest.mark.gui


@pytest.fixture(scope="module")
def app() -> QApplication:
    existing = QApplication.instance()
    return existing if isinstance(existing, QApplication) else QApplication([])


def _result(short_sweep: SweepSettings, rt60_s: float = 0.35, seed: int = 1) -> AnalysisResult:
    rate = short_sweep.sample_rate
    take = synthetic_recording(
        short_sweep,
        make_rir(rate, rt60_s=rt60_s, reflections=[(0.018, 0.35)], seed=seed),
        noise_rms=1e-5,
    )
    return analyze(take, Reference.from_settings(short_sweep))


def _clipped_result(short_sweep: SweepSettings) -> AnalysisResult:
    """A take that clipped: the Level check is invalid and bears on the decay."""
    rate = short_sweep.sample_rate
    take = synthetic_recording(short_sweep, make_rir(rate, rt60_s=0.3), noise_rms=1e-5)
    clipped = np.clip(take.samples * 4.0, -0.3, 0.3)
    return analyze(replace(take, samples=clipped), Reference.from_settings(short_sweep))


@pytest.fixture(scope="module")
def results(short_sweep: SweepSettings) -> tuple[AnalysisResult, AnalysisResult]:
    return _result(short_sweep), _result(short_sweep, rt60_s=0.6, seed=2)


@pytest.fixture(scope="module")
def clipped(short_sweep: SweepSettings) -> AnalysisResult:
    return _clipped_result(short_sweep)


def _measurement(
    result: AnalysisResult,
    *,
    room: str = "Booth A",
    position: str = "A",
    mode: str = "universal_daw",
    profile: str = "vocal",
) -> Measurement:
    session = MeasurementSession(
        mode=mode,
        room_name=room,
        measurement_position=position,
        microphone_name="omni",
        recording_profile=profile,
    )
    return Measurement(
        session=session, result=result, findings=interpret(result, profile), profile=profile
    )


def _panel(app: QApplication, measurement: Measurement | None) -> InspectorPanel:
    panel = InspectorPanel()
    panel.resize(900, 420)
    panel.show()
    panel.set_measurement(measurement)
    app.processEvents()
    return panel


def _rows(widget: KeyValueList) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    layout = widget.layout()
    assert layout is not None
    for i in range(layout.count()):
        entry = layout.itemAt(i)
        assert entry is not None
        row = entry.widget()
        assert row is not None
        labels = row.findChildren(QLabel)
        out.append((labels[0].text(), labels[1].text()))
    return out


def _text(item: QTableWidgetItem | None) -> str:
    assert item is not None
    return item.text()


def _header(table: QTableWidget, column: int) -> str:
    return _text(table.horizontalHeaderItem(column))


def _double_click(app: QApplication, view: object, row: int) -> None:
    """A double-click on ``row`` as a user makes it: the first click lands,
    the second pair of presses is the double-click."""
    from PySide6.QtWidgets import QAbstractItemView

    assert isinstance(view, QAbstractItemView)
    index = view.model().index(row, 1)
    view.scrollTo(index)
    pos = view.visualRect(index).center()
    QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, pos=pos)
    QTest.mouseDClick(view.viewport(), Qt.MouseButton.LeftButton, pos=pos)
    app.processEvents()


def _emitted(panel: InspectorPanel) -> list[tuple[str, object]]:
    seen: list[tuple[str, object]] = []
    panel.locate_requested.connect(lambda kind, index: seen.append((kind, index)))
    return seen


# --- the measurement ---------------------------------------------------------------


def test_set_measurement_fills_the_tabs(
    app: QApplication, results: tuple[AnalysisResult, AnalysisResult]
) -> None:
    measurement = _measurement(results[0])
    panel = _panel(app, measurement)
    assert measurement.health is not None
    assert panel.tabs.isVisible() and not panel.hint.isVisible()
    assert [panel.tabs.tabText(i) for i in range(panel.tabs.count())] == [
        "Measurement quality",
        "Diagnostics",
        "Properties",
        "Tables",
        "Comparison",
        "Report",
    ]
    # The header: the name, the overall status, the markers.
    assert panel.name.text() == "Booth A / A"
    word = status_word(measurement.health.overall)
    assert panel.status_chip.text().endswith(word)
    assert quality_chip_text(measurement) == (word, "good")
    assert quality_chip_text(None) == ("", "neutral")
    assert panel.unsaved_chip.isVisible(), "a measurement not on disk says so"
    assert not panel.synthetic_chip.isVisible()
    # Measurement quality: the sentence and one row per check.
    assert "10 of 10 checks good" in panel.health_summary.text()
    assert panel.checks_model.rowCount() == len(measurement.health.checks)
    assert panel.checks_model.columnCount() == 4
    first = panel.checks_model.index(0, 0)
    assert panel.checks_model.data(first) == word
    assert (
        panel.checks_model.data(panel.checks_model.index(0, 1))
        == measurement.health.checks[0].title
    )
    # Properties: what the session says, in functional rows.
    rows = dict(property_rows(measurement))
    assert rows["Room"] == "Booth A"
    assert rows["Position"] == "A"
    assert rows["Mode"] == "Universal DAW Mode"
    assert rows["Recording profile"] == "Vocals"
    assert rows["Sample rate"] == "48000 Hz"
    assert rows["Saved path"] == "not saved"
    assert dict(_rows(panel.properties)) == rows
    panel.close()


def test_a_synthetic_measurement_is_marked_as_such(
    app: QApplication, results: tuple[AnalysisResult, AnalysisResult]
) -> None:
    measurement = _measurement(results[0], mode=DEMO_MODE)
    panel = _panel(app, measurement)
    assert measurement.synthetic
    assert panel.synthetic_chip.isVisible()
    assert panel.synthetic_chip.text() == "synthetic data"
    assert dict(property_rows(measurement))["Mode"] == "synthetic data"
    panel.close()


def test_no_measurement_hides_the_tabs(
    app: QApplication, results: tuple[AnalysisResult, AnalysisResult]
) -> None:
    panel = _panel(app, _measurement(results[0]))
    seen = _emitted(panel)
    panel.set_measurement(None)
    app.processEvents()
    assert not panel.tabs.isVisible()
    assert not panel.header.isVisible()
    assert panel.hint.isVisible()
    assert panel.hint.text() == "No measurement selected."
    assert panel.diagnostics_model.rowCount() == 0
    assert panel.checks_model.rowCount() == 0
    assert panel.report.toPlainText() == ""
    assert seen == []
    panel.close()


# --- diagnostics -------------------------------------------------------------------


def test_diagnostics_rank_the_findings_and_locate_their_chart(
    app: QApplication, results: tuple[AnalysisResult, AnalysisResult]
) -> None:
    measurement = _measurement(results[0])
    panel = _panel(app, measurement)
    model = panel.diagnostics_model
    assert measurement.findings, "the synthetic room gives the vocal profile something to say"
    assert model.rowCount() == len(measurement.findings)
    ranked = [finding for _index, finding in ranked_findings(measurement.findings)]
    assert [model.finding_at(r) for r in range(model.rowCount())] == ranked
    assert model.data(model.index(0, 2)) == ranked[0].message
    assert model.data(model.index(0, 2), Qt.ItemDataRole.ToolTipRole) == ranked[0].message_id
    assert panel.findings_hint.isHidden()
    seen = _emitted(panel)
    panel.tabs.setCurrentWidget(panel.diagnostics_tab)
    app.processEvents()
    _double_click(app, panel.diagnostics_view, 0)
    group = finding_group(ranked[0])
    assert group is not None
    if ranked[0].topic == "early_reflections":
        # The impulse group holds two charts; a reflection finding wants the timeline.
        group = "reflections"
    assert seen == [(group, None)]
    # The selection shows the evidence, and the button asks for the chart again.
    rows = _rows(panel.finding_detail.rows)
    assert rows[0] == ("Severity", "notice")
    assert panel.finding_detail.message.text() == ranked[0].message
    assert panel.finding_detail.button.isEnabled()
    panel.finding_detail.button.click()
    assert seen[1:] == [(group, None)]
    # Return on the selected row does the same.
    panel.diagnostics_view.setFocus()
    app.processEvents()
    QTest.keyClick(panel.diagnostics_view, Qt.Key.Key_Return)
    app.processEvents()
    assert seen[2:] == [(group, None)]
    panel.close()


def test_a_failed_profile_is_said_in_a_plain_hint(
    app: QApplication, results: tuple[AnalysisResult, AnalysisResult]
) -> None:
    measurement = _measurement(results[0])
    measurement.findings = []
    measurement.findings_problem = "profile broke"
    panel = _panel(app, measurement)
    assert panel.diagnostics_model.rowCount() == 0
    assert not panel.findings_hint.isHidden()
    assert panel.findings_hint.text() == "profile broke"
    panel.close()


# --- measurement quality -------------------------------------------------------------


def test_an_invalid_check_comes_first_and_locates_its_chart(
    app: QApplication, clipped: AnalysisResult
) -> None:
    measurement = _measurement(clipped)
    panel = _panel(app, measurement)
    assert measurement.health is not None
    assert measurement.health.overall is HealthStatus.INVALID
    assert panel.status_chip.text().endswith("invalid")
    assert quality_chip_text(measurement) == ("invalid", "bad")
    model = panel.checks_model
    first = model.check_at(0)
    assert first is not None and first.status is HealthStatus.INVALID
    assert model.data(model.index(0, 1)) == "Level"
    assert first.fix[0] in str(model.data(model.index(0, 2), Qt.ItemDataRole.ToolTipRole))
    seen = _emitted(panel)
    panel.checks_view.selectRow(0)
    app.processEvents()
    rows = _rows(panel.check_detail.rows)
    assert rows[0] == ("Status", "invalid")
    assert ("What to do", first.fix[0]) in rows
    assert panel.check_detail.button.isEnabled()
    panel.check_detail.button.click()
    assert seen == [(check_group(first), None)]
    panel.close()


# --- tables ------------------------------------------------------------------------


def test_tables_switch_with_the_combo_and_a_row_locates_its_chart(
    app: QApplication, results: tuple[AnalysisResult, AnalysisResult]
) -> None:
    measurement = _measurement(results[0])
    panel = _panel(app, measurement)
    seen = _emitted(panel)
    assert panel.table_key() == "decay"
    bands = 1 + len(measurement.result.decay.bands)
    assert panel.table.rowCount() == bands
    assert _header(panel.table, 1) == "EDT"
    panel.table.selectRow(1)
    assert seen[-1:] == [("decay", 1)]
    assert any(key == "T30" for key, _value in _rows(panel.table_detail.rows))
    # Energy rows point at the same band.
    panel.table_kind.setCurrentIndex(panel.table_kind.findData("energy"))
    assert _header(panel.table, 1) == "C50"
    assert panel.table.rowCount() == bands
    panel.table.selectRow(2)
    assert seen[-1:] == [("decay", 2)]
    assert any(key == "C50" for key, _value in _rows(panel.table_detail.rows))
    # Noise bands locate the noise chart as a whole.
    panel.set_table_key("noise")
    assert panel.table.rowCount() == len(measurement.result.noise.band_levels_dbfs)
    panel.table.selectRow(0)
    assert seen[-1:] == [("noise", None)]
    # A reflection row locates the reflections chart.
    panel.set_table_key("reflections")
    assert panel.table.rowCount() == len(measurement.result.reflections.reflections) == 1
    panel.table.selectRow(0)
    assert seen[-1:] == [("reflections", 0)]
    rows = _rows(panel.table_detail.rows)
    assert rows[0][0] == "Delay" and rows[0][1].endswith("ms")
    # A placement candidate locates the placement chart.
    panel.set_table_key("candidates")
    assert panel.table.rowCount() == 1
    panel.table.selectRow(0)
    assert seen[-1:] == [("placement", 0)]
    assert any(key == "Excess path" for key, _value in _rows(panel.table_detail.rows))
    # No resonance was found: an empty table, with the note saying what was searched.
    panel.set_table_key("resonances")
    assert panel.table.rowCount() == 0
    assert panel.table_note.text()
    panel.close()


def test_show_item_selects_the_row_without_asking_the_chart_back(
    app: QApplication, results: tuple[AnalysisResult, AnalysisResult]
) -> None:
    measurement = _measurement(results[0])
    panel = _panel(app, measurement)
    seen = _emitted(panel)
    panel.show_item("band", 2)
    app.processEvents()
    assert panel.tabs.currentWidget() is panel.tables_tab
    assert panel.table_key() == "decay"
    assert {index.row() for index in panel.table.selectedIndexes()} == {2}
    assert seen == []
    assert _rows(panel.table_detail.rows), "the row's detail is shown all the same"
    panel.show_item("reflection", 0)
    assert panel.table_key() == "reflections"
    assert {index.row() for index in panel.table.selectedIndexes()} == {0}
    assert seen == []
    # A table row chosen by hand asks for the chart again.
    panel.table.clearSelection()
    panel.table.selectRow(0)
    assert seen == [("reflections", 0)]
    panel.close()


# --- comparison --------------------------------------------------------------------


def test_the_comparison_tab_waits_for_a_baseline_and_a_candidate(
    app: QApplication, results: tuple[AnalysisResult, AnalysisResult]
) -> None:
    baseline = _measurement(results[0], position="A")
    candidate = _measurement(results[1], position="B")
    panel = _panel(app, candidate)
    index = panel.tabs.indexOf(panel.comparison_tab)
    assert not panel.comparison_enabled()
    comparison = compare(baseline.result, candidate.result)
    verdict = judge_comparison(
        comparison, candidate.profile, baseline=baseline.result, candidate=candidate.result
    )
    panel.set_comparison(baseline, candidate, comparison, verdict)
    app.processEvents()
    assert panel.comparison_enabled()
    assert panel.verdict_headline.text() == verdict.headline()
    assert "Booth A / A" in panel.comparison_pair.text()
    assert "Booth A / B" in panel.comparison_pair.text()
    assert panel.aspects.rowCount() == len(verdict.aspects)
    assert _text(panel.aspects.item(0, 1)) == verdict.aspects[0].title
    assert panel.deltas.rowCount() == len(comparison.decay) + len(comparison.noise) + len(
        comparison.placement
    ) + len(comparison.loopback)
    assert _header(panel.deltas, 5) == "Validity"
    assert panel.reflections.rowCount() == len(comparison.reflections)
    assert not panel.same_gain.isChecked()
    settings: list[bool] = []
    panel.comparison_settings_changed.connect(settings.append)
    panel.same_gain.setChecked(True)
    assert settings == [True]
    # Without a baseline the tab greys out again, and the view leaves it.
    panel.tabs.setCurrentIndex(index)
    panel.set_comparison(None, candidate, None, None)
    assert not panel.comparison_enabled()
    assert panel.tabs.currentIndex() != index
    assert panel.verdict_headline.text() == ""
    panel.close()


# --- report ------------------------------------------------------------------------


def test_the_report_is_the_command_line_report(
    app: QApplication, results: tuple[AnalysisResult, AnalysisResult]
) -> None:
    measurement = _measurement(results[0])
    panel = _panel(app, measurement)
    expected = render_analysis(
        REPORT_CONSOLE, measurement.result, measurement.findings, measurement.profile
    )
    assert panel.report.toPlainText() == expected
    assert panel.report.isReadOnly()
    panel.copy_button.click()
    assert panel.report_note.text() == "Report copied to the clipboard."
    assert QGuiApplication.clipboard().text() == expected
    panel.close()
