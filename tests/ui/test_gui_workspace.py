"""The workspace frame: navigation that keeps the context, the details pane,
the run status line with Stop, the results overview and its analysis
groups, the placement view, export, and the project and compare pages."""

from __future__ import annotations

import os
import threading
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QFileDialog

from reverbscope.core.pipeline import Reference, analyze, synthetic_recording
from reverbscope.io.project_store import add_session, save_project
from reverbscope.io.session_store import save_measurement
from reverbscope.io.wav import write_wav
from reverbscope.models.configuration import SweepSettings
from reverbscope.models.project import Project
from reverbscope.models.result import AnalysisResult
from reverbscope.models.session import MeasurementSession
from reverbscope.ui import export as export_module
from reverbscope.ui.main_window import MainWindow
from reverbscope.ui.widgets import FindingCard
from reverbscope.ui.workspace import NAV_HOME, NAV_RESULTS
from tests.conftest import make_rir

pytestmark = pytest.mark.gui


@pytest.fixture(scope="module")
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _settle(app: QApplication, *workers: object) -> None:
    import time

    for worker in workers:
        if worker is not None:
            worker.wait()  # type: ignore[attr-defined]
    for _ in range(10):
        app.processEvents()
        time.sleep(0.01)


def _result(short_sweep: SweepSettings, rt60_s: float = 0.35, seed: int = 1) -> AnalysisResult:
    rate = short_sweep.sample_rate
    take = synthetic_recording(
        short_sweep,
        make_rir(rate, rt60_s=rt60_s, reflections=[(0.018, 0.35)], seed=seed),
        noise_rms=1e-5,
    )
    return analyze(take, Reference.from_settings(short_sweep))


def _analysed(app: QApplication, tmp_path: Path, short_sweep: SweepSettings) -> MainWindow:
    """A window on the Results page after a Universal DAW analysis."""
    window = MainWindow()
    window.show()
    window.show_mode("universal_daw")
    page = window.daw
    rate = short_sweep.sample_rate
    page.sample_rate.setCurrentIndex(page.sample_rate.findData(rate))
    page.duration.setValue(short_sweep.duration_s)
    page.generate_sweep_to(tmp_path / "sweep.wav")
    take = synthetic_recording(
        page.current_sweep_settings(),
        make_rir(rate, rt60_s=0.35, reflections=[(0.018, 0.35)]),
        noise_rms=1e-5,
    )
    page.set_recording(write_wav(tmp_path / "take.wav", take.samples, rate, subtype="FLOAT"))
    page.room.setText("Booth A")
    page.start_analysis(blocking=True)
    app.processEvents()
    assert window.stack.currentWidget() is window.results
    return window


# --- navigation keeps the context ----------------------------------------------------


def test_navigation_keeps_the_result_and_new_measurement_resets_it(
    app: QApplication, tmp_path: Path, short_sweep: SweepSettings
) -> None:
    window = _analysed(app, tmp_path, short_sweep)
    result = window.state.result
    # Home from the navigation: a look at the start page, nothing dropped.
    window.nav.page_requested.emit(NAV_HOME)
    assert window.stack.currentWidget() is window.home
    assert window.state.result is result
    assert window.daw.recording_label.text().startswith("take.wav")
    window.nav.page_requested.emit(NAV_RESULTS)
    assert window.stack.currentWidget() is window.results
    assert window.state.result is result
    # The context bar names the session; the status line names the page.
    assert "Booth A" in window.context_bar.title.text()
    assert window.statusBar().currentMessage().endswith("Results")
    # New Measurement is the explicit fresh start.
    window.show_home()
    assert window.state.result is None
    assert window.daw.recording_label.text() == "No recording selected."
    assert not window.nav._pages[NAV_RESULTS].isSelected()
    window.close()


def test_the_mode_pages_keep_their_step_and_the_context_bar_names_it(
    app: QApplication, tmp_path: Path
) -> None:
    window = MainWindow()
    window.show()
    window.show_mode("universal_daw")
    window.daw.show_step(2)
    assert "3" in window.context_bar.subtitle.text()
    window.show_compare()
    window.show_mode("universal_daw")
    assert window.daw.steps.current() == 2, "a visit to Compare does not reset the step"
    assert window.daw.action_area.next_button.isEnabled()
    window.daw.action_area.next_button.click()
    assert window.daw.steps.current() == 3
    assert not window.daw.action_area.next_button.isEnabled()
    window.close()


# --- the run status line and Stop ----------------------------------------------------


@pytest.fixture
def held_take(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    from PySide6.QtCore import QThread

    from reverbscope.audio.fake import FakeBackend
    from reverbscope.errors import MeasurementCancelledError

    release = threading.Event()
    real = FakeBackend.play_and_record
    takes: list[tuple[QThread, threading.Event | None]] = []

    def held(self, *args, cancel=None, **kwargs):  # type: ignore[no-untyped-def]
        takes.append((QThread.currentThread(), cancel))
        while not release.wait(0.01):
            if cancel is not None and cancel.is_set():
                raise MeasurementCancelledError("stopped")
        return real(self, *args, cancel=cancel, **kwargs)

    monkeypatch.setattr(FakeBackend, "play_and_record", held)
    yield release
    for thread, cancel in takes:
        if cancel is not None:
            cancel.set()
        else:
            release.set()
        thread.wait()


def test_stop_in_the_status_line_ends_a_take_from_any_page(
    app: QApplication, held_take: threading.Event
) -> None:
    window = MainWindow()
    window.show()
    window.show_mode("demo")
    app.processEvents()
    page = window.standalone
    page.duration.setValue(1.0)
    page.run_button.click()
    worker = page._measure_worker
    assert worker is not None and worker.isRunning()
    assert window.run_status.is_running()
    assert window.run_status.stop_button.isVisible()
    assert window.run_status.progress.isVisible()
    # The take is still on the Standalone page; its Stop stays reachable from
    # the status line whatever page is shown.
    window.run_status.stop_button.click()
    _settle(app, worker)
    assert not window.run_status.is_running()
    assert "Stopped" in page.status.text()
    assert page.run_button.isEnabled()
    window.close()


# --- results: overview, groups, details, export ----------------------------------------


def test_the_overview_answers_the_three_questions_and_links_the_charts(
    app: QApplication, tmp_path: Path, short_sweep: SweepSettings
) -> None:
    window = _analysed(app, tmp_path, short_sweep)
    overview = window.results.overview
    assert overview.trust_banner.text().startswith("Yes")
    assert overview.findings_title.text()
    # A finding card opens its chart and shows its evidence in the details pane.
    cards = [
        overview.findings.itemAt(i).widget()
        for i in range(overview.findings.count())
        if isinstance(overview.findings.itemAt(i).widget(), FindingCard)
    ]
    assert cards
    cards[0].activated.emit()
    assert window.results.detail.heading.text()
    assert window.results.analysis.current_group() in window.results.groups
    # A tile opens its group too.
    overview.rt60.activated.emit()
    assert window.results.analysis.current_group() == "decay"
    # The decay table selects a band for the details pane.
    window.results.table.selectRow(0)
    assert window.results.detail.heading.text() == "Broadband"
    assert any("T30" in key for key, _v in _detail_rows(window))
    window.close()


def _detail_rows(window: MainWindow) -> list[tuple[str, str]]:
    from PySide6.QtWidgets import QLabel

    rows = window.results.detail.rows
    out: list[tuple[str, str]] = []
    for i in range(rows.layout().count()):
        row = rows.layout().itemAt(i).widget()
        labels = row.findChildren(QLabel)
        out.append((labels[0].text(), labels[1].text()))
    return out


def test_an_invalid_measurement_is_said_to_have_failed_first(
    app: QApplication, tmp_path: Path, short_sweep: SweepSettings
) -> None:
    rate = short_sweep.sample_rate
    take = synthetic_recording(short_sweep, make_rir(rate, rt60_s=0.3), noise_rms=1e-5)
    clipped = np.clip(take.samples * 4.0, -0.3, 0.3)
    window = MainWindow()
    window.show()
    window.show_mode("universal_daw")
    page = window.daw
    page.sample_rate.setCurrentIndex(page.sample_rate.findData(rate))
    page.duration.setValue(short_sweep.duration_s)
    page.generate_sweep_to(tmp_path / "sweep.wav")
    page.set_recording(write_wav(tmp_path / "clipped.wav", clipped, rate, subtype="FLOAT"))
    page.start_analysis(blocking=True)
    app.processEvents()
    overview = window.results.overview
    assert overview.trust_banner.text().startswith("No")
    assert overview.trust_banner.property("banner") == "bad"
    # What next: the check's own fix comes first.
    steps = [
        overview.next_steps.itemAt(i).layout().itemAt(0).widget().text()
        for i in range(overview.next_steps.count())
        if overview.next_steps.itemAt(i).layout() is not None
    ]
    assert steps and "Level" in steps[0]
    window.close()


def test_many_findings_show_the_most_important_first_with_show_all(
    app: QApplication, short_sweep: SweepSettings
) -> None:
    from reverbscope.interpretation.interpreter import Finding, Severity
    from reverbscope.ui.results_overview import Overview

    result = _result(short_sweep)
    findings = [
        Finding("noise", Severity.INFO, "info one"),
        Finding("reverberation", Severity.NOTICE, "notice one"),
        Finding("early_reflections", Severity.WARNING, "warning one"),
        Finding("clarity", Severity.INFO, "info two"),
        Finding("low_frequency", Severity.NOTICE, "notice two"),
    ]
    overview = Overview()
    overview.show_result(result, findings, "generic")
    cards = [
        overview.findings.itemAt(i).widget()
        for i in range(overview.findings.count())
        if isinstance(overview.findings.itemAt(i).widget(), FindingCard)
    ]
    assert [card.message.text() for card in cards] == ["warning one", "notice one", "notice two"]
    assert overview.show_all_button.isVisibleTo(overview)
    overview.show_all_button.click()
    cards = [
        overview.findings.itemAt(i).widget()
        for i in range(overview.findings.count())
        if isinstance(overview.findings.itemAt(i).widget(), FindingCard)
    ]
    assert len(cards) == 5
    overview.close()


def test_charts_draw_when_their_group_is_shown(
    app: QApplication, tmp_path: Path, short_sweep: SweepSettings
) -> None:
    window = _analysed(app, tmp_path, short_sweep)
    noise = window.results.groups["noise"]
    assert noise._dirty and not noise.figure.get_axes()
    window.results.show_group("noise")
    assert not noise._dirty and noise.figure.get_axes()
    # A second result marks every group dirty again; the shown one redraws.
    window.results.state.result = _result(short_sweep, 0.5, 2)
    window.results.refresh()
    window.results.show_group("noise")
    assert not noise._dirty
    assert window.results.groups["decay"]._dirty
    window.close()


def test_export_writes_csv_and_png_and_reports_a_failure(
    app: QApplication, tmp_path: Path, short_sweep: SweepSettings, monkeypatch: pytest.MonkeyPatch
) -> None:
    window = _analysed(app, tmp_path, short_sweep)
    out = tmp_path / "csv"
    out.mkdir()
    monkeypatch.setattr(
        QFileDialog, "getExistingDirectory", staticmethod(lambda *_a, **_k: str(out))
    )
    window.results.export_csv()
    assert (out / "decay_metrics.csv").is_file()
    assert "decay_metrics.csv" in window.results.status.text()
    png = tmp_path / "chart.png"
    monkeypatch.setattr(export_module, "ask_save_path", lambda *_a, **_k: png)
    window.results.export_png()
    assert png.is_file() and png.stat().st_size > 1000
    assert str(png) in window.results.status.text()
    # A folder that cannot be written is a dialog with the reason, not a
    # success message.
    shown: list[str] = []
    monkeypatch.setattr(export_module, "error_box", lambda _p, _t, text: shown.append(text))
    blocker = tmp_path / "blocker"
    blocker.write_text("x", encoding="utf-8")
    monkeypatch.setattr(
        QFileDialog,
        "getExistingDirectory",
        staticmethod(lambda *_a, **_k: str(blocker / "inside")),
    )
    window.results.export_csv()
    assert shown and "failed" in window.results.status.text()
    window.close()


# --- placement ---------------------------------------------------------------------


def test_a_missing_tape_measure_names_the_field_and_leads_back_to_it(
    app: QApplication, tmp_path: Path, short_sweep: SweepSettings
) -> None:
    window = _analysed(app, tmp_path, short_sweep)
    window.results.show_group("placement")
    view = window.results.analysis.placement
    assert "Loudspeaker distance" in view.missing.text()
    assert view.settings_button.isVisible()
    # Tier 0: the three lengths are listed as not determined, never as 0 m.
    assert view.table.rowCount() == 3
    assert all("not determined" in view.table.item(r, 1).text() for r in range(3))
    assert view.candidates.rowCount() >= 1
    assert "Nothing has been entered" in view.scene_hint.text()
    view.settings_button.click()
    assert window.stack.currentWidget() is window.daw
    assert window.daw.steps.current() == 3
    assert window.daw.placement.isVisibleTo(window.daw)
    assert window.state.result is not None, "going back keeps the result"
    window.close()


def test_the_placement_views_switch_and_a_candidate_selects_its_details(
    app: QApplication, tmp_path: Path, short_sweep: SweepSettings
) -> None:
    import math

    from reverbscope.core.placement import DEFAULT_TEMPERATURE_C, speed_of_sound_m_s

    source_height, mic_height, horizontal, ceiling = 1.20, 0.40, 1.44, 3.20
    speed = speed_of_sound_m_s(DEFAULT_TEMPERATURE_C)
    distance = math.hypot(source_height - mic_height, horizontal)

    def plane(near: float, far: float) -> tuple[float, float]:
        path = math.hypot(near + far, horizontal)
        return (path - distance) / speed, 0.7 * distance / path

    window = MainWindow()
    window.show()
    window.show_mode("universal_daw")
    page = window.daw
    rate = short_sweep.sample_rate
    page.sample_rate.setCurrentIndex(page.sample_rate.findData(rate))
    page.duration.setValue(short_sweep.duration_s)
    page.generate_sweep_to(tmp_path / "sweep.wav")
    page.placement.distance.setValue(distance)
    page.placement.mic_height.setValue(mic_height)
    ir = make_rir(
        rate,
        rt60_s=0.35,
        reflections=[
            plane(source_height, mic_height),
            plane(ceiling - source_height, ceiling - mic_height),
        ],
        diffuse_level=0.004,
        length_s=0.6,
    )
    take = synthetic_recording(page.current_sweep_settings(), ir, noise_rms=1e-4)
    page.set_recording(write_wav(tmp_path / "take.wav", take.samples, rate, subtype="FLOAT"))
    page.start_analysis(blocking=True)
    app.processEvents()
    window.results.show_group("placement")
    view = window.results.analysis.placement
    assert view.missing.isHidden()
    assert "measured" in view.scene_hint.text()
    assert view.table.rowCount() == 3
    view.show_view("timeline")
    assert view.figure.get_axes()
    view.candidates.selectRow(0)
    assert window.results.detail.heading.text().startswith("Reflection at")
    rows = dict(_detail_rows(window))
    assert "Plane reflection?" in rows
    view.show_view("3d")
    assert view.reset_button.isVisible()
    assert "ring" in view.scene_hint.text()
    view.reset_button.click()
    view.show_view("side")
    assert not view.reset_button.isVisible()
    window.close()


def test_the_results_tile_never_shows_a_missing_number_as_zero(short_sweep: SweepSettings) -> None:
    from reverbscope.ui.results_overview import Overview

    result = _result(short_sweep)
    blank = replace(result, noise=replace(result.noise, rms_dbfs=None))
    overview = Overview()
    overview.show_result(blank, [], "generic")
    assert overview.noise.value.text() == "-"
    assert overview.noise.chip.text() == "not computed"
    overview.close()


# --- the details pane and narrow windows ----------------------------------------------


def test_the_details_pane_folds_in_a_narrow_window_and_comes_back(app: QApplication) -> None:
    window = MainWindow()
    window.resize(1440, 900)
    window.show()
    app.processEvents()
    assert window.details.isVisible()
    window.resize(960, 640)
    app.processEvents()
    assert not window.details.isVisible()
    # The main actions stay on screen at the minimum size.
    window.show_mode("universal_daw")
    app.processEvents()
    assert window.daw.analyze_button.isVisible()
    assert window.daw.action_area.isVisible()
    window.resize(1440, 900)
    app.processEvents()
    assert window.details.isVisible()
    window.details_action.trigger()
    assert not window.details.isVisible()
    window.resize(1280, 800)
    app.processEvents()
    assert not window.details.isVisible(), "hidden by hand stays hidden"
    window.close()


# --- compare -----------------------------------------------------------------------


def test_compare_draws_both_takes_on_one_scale_and_each_view(
    app: QApplication, tmp_path: Path, short_sweep: SweepSettings
) -> None:
    for name, rt60 in (("base", 0.3), ("cand", 0.8)):
        save_measurement(
            tmp_path / name,
            MeasurementSession(room_name=name),
            _result(short_sweep, rt60),
            copy_recording=False,
        )
    window = MainWindow()
    window.show()
    window.show_compare()
    page = window.compare
    page.set_paths(tmp_path / "base", tmp_path / "cand")
    page.run_compare()
    assert "base" in window.context_bar.subtitle.text()
    page.tabs.setCurrentIndex(1)
    app.processEvents()
    axes = page.figure.get_axes()
    assert len(axes) == 2 and len(axes[0].get_lines()) == 2
    limits = axes[0].get_ylim()
    page._set_curve_view("candidate")
    assert len(page.figure.get_axes()[0].get_lines()) == 1
    page._set_curve_view("difference")
    assert len(page.figure.get_axes()) == 1
    page._set_curve_view("both")
    assert page.figure.get_axes()[0].get_ylim() == limits
    page.tabs.setCurrentIndex(2)
    app.processEvents()
    assert len(page.decay_figure.get_axes()[0].get_lines()) == 2
    # An aspect card feeds the details pane; the metrics table too.
    cards = [
        page.verdict_rows.itemAt(i).widget()
        for i in range(page.verdict_rows.count())
        if isinstance(page.verdict_rows.itemAt(i).widget(), FindingCard)
    ]
    cards[0].activated.emit()
    assert page.detail.heading.text() == cards[0].topic.text()
    page.table.selectRow(0)
    assert page.detail.heading.text().startswith("Broadband")
    window.close()


# --- project -----------------------------------------------------------------------


def test_a_position_can_be_selected_measured_again_opened_and_listed_in_the_navigation(
    app: QApplication, tmp_path: Path, short_sweep: SweepSettings
) -> None:
    project = tmp_path / "booth"
    save_project(project, Project(name="Booth"))
    for name, position, rt60 in (("a-1", "A", 0.35), ("b-1", "B", 0.9)):
        session = MeasurementSession(room_name="Booth", measurement_position=position)
        save_measurement(project / name, session, _result(short_sweep, rt60), copy_recording=False)
        add_session(project, project / name, position=position)
    window = MainWindow()
    window.show()
    window.show_project(project)
    page = window.project
    assert window.nav._pages["project"].text(0) == "Booth"
    assert window.nav._pages["project"].childCount() == 2
    page.select_position("B")
    assert page.current_position() == "B"
    assert page.detail.heading.text().endswith("B")
    assert page.remeasure_button.isEnabled()
    selected = {index.row() for index in page.table.selectedIndexes()}
    assert selected == {1}
    asked: list[tuple[str, str]] = []
    page.measure_requested.connect(lambda label, mode: asked.append((label, mode)))
    page.start_position(page.current_position(), "universal_daw")
    assert asked == [("B", "universal_daw")]
    assert window.state.project_position == "B"
    window.show_project()
    page.table.selectRow(0)
    page.open_take_button.click()
    assert window.stack.currentWidget() is window.results
    assert window.state.session.measurement_position == "A"
    # The navigation opens a position of the project directly.
    window.nav.position_requested.emit("A")
    assert window.stack.currentWidget() is window.project
    assert page.current_position() == "A"
    window.close()


def test_navigation_highlights_the_results_page_when_a_session_opens(
    app: QApplication, tmp_path: Path, short_sweep: SweepSettings
) -> None:
    """The Results entry is enabled and selected in one go: the highlight
    follows the page that is shown, not the one before it."""
    session = MeasurementSession(room_name="Booth", measurement_position="A")
    save_measurement(tmp_path / "take", session, _result(short_sweep), copy_recording=False)
    window = MainWindow()
    window.show()
    app.processEvents()
    assert window.nav.tree.currentItem() is window.nav._pages[NAV_HOME]
    window.open_session_path(tmp_path / "take")
    app.processEvents()
    assert window.nav.tree.currentItem() is window.nav._pages[NAV_RESULTS]
    assert not window.nav._pages[NAV_RESULTS].isDisabled()
    window.close()
