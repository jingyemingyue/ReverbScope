"""The Project page: the overview of a room's positions, and the workflow
that measures the next position into the project."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from reverbscope.core.pipeline import Reference, analyze, synthetic_recording
from reverbscope.io.project_store import add_session, list_project_sessions, save_project
from reverbscope.io.session_store import save_measurement
from reverbscope.io.wav import write_wav
from reverbscope.models.configuration import SweepSettings
from reverbscope.models.project import Project
from reverbscope.models.result import AnalysisResult
from reverbscope.models.session import MeasurementSession
from reverbscope.ui.main_window import MainWindow, suggested_folder
from reverbscope.ui.project_view import suggest_label
from tests.conftest import make_rir

pytestmark = pytest.mark.gui


@pytest.fixture(scope="module")
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _result(sweep: SweepSettings, rt60_s: float, seed: int, strong: bool = False) -> AnalysisResult:
    ir = make_rir(
        sweep.sample_rate,
        rt60_s=rt60_s,
        reflections=[(0.010, 0.5)] if strong else [],
        diffuse_level=0.02,
        seed=seed,
    )
    return analyze(
        synthetic_recording(sweep, ir, noise_rms=1e-5, seed=seed), Reference.from_settings(sweep)
    )


def _booth(root: Path, sweep: SweepSettings) -> Path:
    project = root / "booth"
    save_project(project, Project(name="Booth"))
    for name, position, result in (
        ("a-1", "A", _result(sweep, 0.35, 1)),
        ("a-2", "A", _result(sweep, 0.35, 2)),
        ("b-1", "B", _result(sweep, 0.9, 3, strong=True)),
    ):
        session = MeasurementSession(
            room_name="Booth", measurement_position=position, recording_profile="vocal"
        )
        save_measurement(project / name, session, result, copy_recording=False)
        add_session(project, project / name, position=position)
    return project


def test_the_project_page_shows_positions_takes_average_and_next_steps(
    app: QApplication, tmp_path: Path, short_sweep: SweepSettings
) -> None:
    project = _booth(tmp_path, short_sweep)
    window = MainWindow()
    window.show()
    window.show_project(project)
    assert window.model.wait_until_loaded()
    page = window.project
    assert window.stack.currentWidget() is page
    assert page.path == project
    assert page.profile.currentData() == "vocal"  # the latest take's own profile
    assert page.table.rowCount() == 3
    assert page.position_rows.count() == 2
    fits = [page.table.item(r, 8).text() for r in range(3)]
    assert fits == ["fits", "fits", "warnings"]
    assert "survey" in page.iso_line.text()
    assert page.average_table.rowCount() > 0
    assert "% across the room" in page.spread.text()
    steps = page.next_steps.text()
    assert "second take at B" in steps and "A is the one position that fits" in steps
    assert "Booth" in page.header.subtitle.text()
    assert "ReverbScope project overview" in page.overview_text()
    # Compare with the first position: only a take of another position.
    page.table.selectRow(0)
    assert not page.compare_button.isEnabled()
    page.table.selectRow(2)
    assert page.compare_button.isEnabled()
    page.compare_button.click()
    assert window.stack.currentWidget() is window.compare
    baseline, candidate = window.model.baseline(), window.model.current()
    assert baseline is not None and baseline.directory is not None
    assert candidate is not None and candidate.directory is not None
    assert baseline.directory.name == "a-2"  # the latest good take of A
    assert candidate.directory.name == "b-1"
    # Another profile re-judges the same takes.
    window.show_project()
    assert window.model.wait_until_loaded()
    page.profile.setCurrentIndex(page.profile.findData("generic"))
    assert page.overview is not None and page.overview.profile == "generic"
    window.close()


def test_measuring_a_new_position_saves_the_take_into_the_project(
    app: QApplication, tmp_path: Path, short_sweep: SweepSettings
) -> None:
    project = _booth(tmp_path, short_sweep)
    window = MainWindow()
    window.show()
    window.show_project(project)
    assert window.model.wait_until_loaded()
    assert suggest_label(window.project.labels()) == "C"
    window.project.start_position("C", "universal_daw")
    assert window.stack.currentWidget() is window.daw
    assert window.model.project_path == project
    assert window.strip.position.currentText() == "C"
    assert window.daw.position.text() == "C" and window.daw.room.text() == "Booth"

    page = window.daw
    rate = short_sweep.sample_rate
    page.sample_rate.setCurrentIndex(page.sample_rate.findData(rate))
    page.duration.setValue(short_sweep.duration_s)
    page.generate_sweep_to(tmp_path / "sweep.wav")
    take = synthetic_recording(short_sweep, make_rir(rate, rt60_s=0.4), noise_rms=1e-5)
    page.set_recording(write_wav(tmp_path / "take.wav", take.samples, rate, subtype="FLOAT"))
    page.start_analysis(blocking=True)
    app.processEvents()
    assert window.stack.currentWidget() is window.views["overview"]
    take = window.model.current()
    assert take is not None and take.is_take and take.position == "C"
    assert suggested_folder(project, "C") == "C-1"
    assert window.save_to(project / suggested_folder(project, "C"))
    assert "listed in project Booth under position C" in window.statusBar().currentMessage()
    listed = {label: path.name for label, path in list_project_sessions(project)}
    assert listed["C"] == "C-1"
    assert suggested_folder(project, "C") == "C-2"
    # The saved take stays current, now under position C of the project.
    assert window.model.wait_until_loaded()
    saved = window.model.current()
    assert saved is not None and not saved.is_take and saved.position == "C"
    # Back to the project: the new position is there, judged with the others.
    window.show_project()
    assert window.model.wait_until_loaded()
    assert window.stack.currentWidget() is window.project
    assert window.project.labels() == ["A", "B", "C"]
    # The project stays open until it is closed; then a save belongs to no project.
    window.show_home()
    assert window.model.project_path == project
    window.close_project()
    assert window.model.project_path is None
    assert all(not entry.position for entry in window.model.entries())
    window.close()


def test_a_plain_folder_becomes_a_project_and_takes_are_added(
    app: QApplication, tmp_path: Path, short_sweep: SweepSettings, monkeypatch: pytest.MonkeyPatch
) -> None:
    from reverbscope.ui import project_view

    errors: list[str] = []
    monkeypatch.setattr(
        project_view.QMessageBox, "critical", lambda _parent, _title, text: errors.append(text)
    )
    window = MainWindow()
    window.show()
    window.show_view("project")
    page = window.project
    assert page.create_project(tmp_path / "room")
    assert window.model.wait_until_loaded()
    assert (tmp_path / "room" / "project.json").is_file()
    assert page.labels() == [] and page.empty.isHidden()
    assert "No position yet" in page.next_steps.text()
    assert "No session to average yet" in page.iso_line.text()
    session = MeasurementSession(room_name="Room", measurement_position="desk")
    save_measurement(
        tmp_path / "desk-take", session, _result(short_sweep, 0.5, 7), copy_recording=False
    )
    assert page.add_existing(tmp_path / "desk-take" / "session.json", "desk")
    assert window.model.wait_until_loaded()
    assert page.labels() == ["desk"]
    assert page.table.rowCount() == 1 and page.table.item(0, 0).text() == "desk"
    # A folder that is not a session is refused with a message, not a crash.
    assert not page.add_existing(tmp_path / "nowhere", "x")
    assert errors and "nowhere" in errors[0]
    window.close()


def test_suggested_labels_skip_the_ones_in_use() -> None:
    assert suggest_label([]) == "A"
    assert suggest_label(["A", "b"]) == "C"
    assert suggest_label([f"{c}" for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"]) == "A2"
