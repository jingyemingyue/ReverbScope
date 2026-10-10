"""The room view, the scan import dialog, ui.ini and thread shutdown.

GUI_2_ARCHITECTURE.md §6.4, §7 and §8: three layers kept apart, the
reflection selected in one place is the one shown in the other, the room
file stays beside the measurements, scans are read off the GUI thread, and
closing the window waits for every worker.
"""

from __future__ import annotations

import os
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

import numpy as np
import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from reverbscope.core.pipeline import Reference, analyze, synthetic_recording
from reverbscope.io.session_store import save_measurement
from reverbscope.models.configuration import SweepSettings
from reverbscope.models.result import AnalysisResult, PlacementLength, PlacementResult, Validity
from reverbscope.models.session import MeasurementSession
from tests.conftest import make_rir

pytestmark = pytest.mark.gui


@pytest.fixture(scope="module")
def app() -> Any:
    return QApplication.instance() or QApplication([])


@pytest.fixture(scope="module")
def result() -> AnalysisResult:
    sweep = SweepSettings(duration_s=2.0, pre_silence_s=1.0, post_silence_s=1.5, level_dbfs=-12.0)
    ir = make_rir(sweep.sample_rate, rt60_s=0.35, reflections=[(0.006, 0.5), (0.011, 0.35)])
    return analyze(synthetic_recording(sweep, ir, noise_rms=1e-5), Reference.from_settings(sweep))


def _pump(app: Any, seconds: float = 0.2) -> None:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.01)


def _view(app: Any, result: AnalysisResult, folder: Path) -> Any:
    from reverbscope.ui.room.view import RoomView
    from reverbscope.ui.workspace import WorkspaceModel

    save_measurement(
        folder, MeasurementSession(measurement_position="A"), result, copy_recording=False
    )
    model = WorkspaceModel()
    model.add_session(folder, MeasurementSession(measurement_position="A"), result, position="A")
    view = RoomView(model)
    view.resize(1100, 700)
    view.show()
    _pump(app)
    return view


def test_the_example_room_is_saved_beside_the_session_and_read_back(
    app: Any, result: AnalysisResult, tmp_path: Path
) -> None:
    from reverbscope.geometry.room import load_geometry

    folder = tmp_path / "a-1"
    view = _view(app, result, folder)
    session_before = (folder / "session.json").read_bytes()
    assert view.directory == folder
    view.use_example()
    _pump(app, 0.7)  # the save is debounced
    stored = load_geometry(folder)
    assert stored is not None and stored.room is not None and stored.microphone("A") is not None
    # The session itself is untouched: geometry lives in its own file.
    assert (folder / "session.json").read_bytes() == session_before
    assert (folder / "room-geometry.json").is_file()
    view.load(None)
    assert view.room_geometry.room is None
    view.load(folder)
    assert view.room_geometry.room == stored.room
    view.shutdown()
    view.close()


def test_a_selected_reflection_draws_its_ellipsoid_and_highlights_matching_faces(
    app: Any, result: AnalysisResult, tmp_path: Path
) -> None:
    view = _view(app, result, tmp_path / "a-1")
    view.use_example()
    _pump(app)
    scene = view.canvas.scene
    assert scene.box is not None and scene.predicted, "a box predicts first-order paths"
    assert scene.ellipsoid is None
    assert result.reflections.reflections
    view.model.select_reflection(view.model.current_key, 0)
    _pump(app)
    scene = view.canvas.scene
    assert scene.ellipsoid is not None
    source, mic, semi_major = scene.ellipsoid
    assert semi_major > 0.5 * float(np.linalg.norm(np.subtract(mic.as_tuple(), source.as_tuple())))
    # Layers switch independently; the drawing still renders offscreen.
    from reverbscope.ui.room.canvas import LAYER_ASSUMED, LAYER_MEASURED

    view.layer_boxes[LAYER_MEASURED].setChecked(False)
    assert view.canvas.scene.layers[LAYER_MEASURED] is False
    assert view.canvas.scene.layers[LAYER_ASSUMED] is True
    image = view.canvas.grab().toImage()
    assert image.width() > 100 and image.height() > 100
    # The inspector receives the consistency checks with the one-microphone note.
    checks, note = view.checks()
    assert checks and "wall" in note.lower()
    view.shutdown()
    view.close()


def test_a_valid_placement_draws_the_ring_of_loudspeaker_positions() -> None:
    from reverbscope.geometry.room import Point
    from reverbscope.ui.room.view import placement_ring

    placement = PlacementResult(
        tier=2,
        candidates=(),
        source_height_m=PlacementLength(1.2, Validity.VALID),
        ceiling_height_m=PlacementLength(None, Validity.INSUFFICIENT_RANGE),
        horizontal_separation_m=PlacementLength(1.5, Validity.VALID),
        speed_of_sound_m_s=343.0,
        temperature_c=20.0,
        temperature_assumed=False,
        distance_m=1.8,
        mic_height_m=0.4,
    )
    mic = Point(2.0, 1.0, 0.4)
    centre, radius = placement_ring(placement, mic) or (None, None)
    assert centre == Point(2.0, 1.0, 1.2) and radius == 1.5
    assert placement_ring(placement, None) is None
    unknown = replace(
        placement, source_height_m=PlacementLength(None, Validity.INSUFFICIENT_RANGE)
    )
    assert placement_ring(unknown, mic) is None


def test_the_orbit_camera_projects_and_unprojects_the_plan_to_scale() -> None:
    from reverbscope.ui.room.camera import OrbitCamera

    camera = OrbitCamera(width=800, height=600)
    camera.fit(np.zeros(3), np.array([5.0, 4.0, 2.5]))
    screen, visible = camera.project(np.array([[2.5, 2.0, 1.25]]))
    assert visible.all()
    assert abs(screen[0, 0] - 400) < 1 and abs(screen[0, 1] - 300) < 1  # the target is centred
    camera.plan = True
    points = np.array([[1.0, 1.0, 0.0], [3.0, 2.0, 0.0]])
    screen, _visible = camera.project(points)
    for (sx, sy), (x, y, _z) in zip(screen, points, strict=True):
        ux, uy = camera.unproject_plan(float(sx), float(sy))
        assert abs(ux - x) < 1e-6 and abs(uy - y) < 1e-6
    before = camera.metres_per_pixel()
    under = camera.unproject_plan(250.0, 200.0)
    camera.zoom_at(250.0, 200.0, 0.5)  # closer, about the cursor
    assert camera.metres_per_pixel() == pytest.approx(before / 2.0)
    assert camera.unproject_plan(250.0, 200.0) == pytest.approx(under)


def _ascii_ply(path: Path) -> Path:
    vertices = [(0, 0, 0), (2, 0, 0), (2, 3, 0), (0, 3, 0)]
    lines = [
        "ply",
        "format ascii 1.0",
        f"element vertex {len(vertices)}",
        "property float x",
        "property float y",
        "property float z",
        "element face 1",
        "property list uchar int vertex_indices",
        "end_header",
        *[" ".join(str(v) for v in vertex) for vertex in vertices],
        "4 0 1 2 3",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="ascii")
    return path


def test_a_scan_is_read_in_the_background_and_placed(app: Any, tmp_path: Path) -> None:
    from reverbscope.ui.room.scan_import import ScanImportDialog

    dialog = ScanImportDialog(str(tmp_path))
    dialog.read(_ascii_ply(tmp_path / "room.ply"))
    deadline = time.monotonic() + 20
    while dialog.mesh is None and time.monotonic() < deadline:
        _pump(app, 0.05)
    assert dialog.mesh is not None and dialog.ok_button.isEnabled()
    assert "4 vertices" in dialog.status.text()
    dialog.units.setCurrentIndex(dialog.units.findData("cm"))
    placed = dialog.placement()
    assert placed is not None
    reference, vertices = placed
    assert reference.file == "room.ply" and reference.units == "cm" and len(reference.sha256) == 64
    assert float(np.max(vertices)) == pytest.approx(0.03)  # 3 cm, lowest corner on the floor
    # A file that is not a scan says why; nothing is accepted.
    bad = tmp_path / "bad.ply"
    bad.write_text("not a scan", encoding="ascii")
    dialog.read(bad)
    deadline = time.monotonic() + 20
    while "Cannot import" not in dialog.status.text() and time.monotonic() < deadline:
        _pump(app, 0.05)
    assert "Cannot import" in dialog.status.text() and not dialog.ok_button.isEnabled()
    dialog.reject()  # waits for the worker


def test_ui_state_keeps_the_selection_per_project_and_survives_a_bad_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from reverbscope.ui import ui_state

    monkeypatch.setenv("REVERBSCOPE_HOME", str(tmp_path / "home"))
    project = tmp_path / "booth"
    project.mkdir()
    assert ui_state.read_selection(project) is None
    chosen = {"current": str(project / "a-1"), "overlay": [str(project / "b-1")], "baseline": ""}
    ui_state.write_selection(project, chosen)
    assert ui_state.read_selection(project) == chosen
    assert ui_state.read_selection(tmp_path / "other") is None
    ui_state.write(f"{ui_state.project_key(project)}/selection", "{not json")
    assert ui_state.read_selection(project) is None


def test_closing_the_window_waits_for_the_spectrogram_and_the_project_load(
    app: Any, result: AnalysisResult, tmp_path: Path
) -> None:
    """A QThread destroyed while it runs aborts the process."""
    from reverbscope.ui.main_window import MainWindow

    folder = tmp_path / "a-1"
    save_measurement(folder, MeasurementSession(), result, copy_recording=False)
    window = MainWindow()
    window.show()
    assert window.open_session_path(folder)
    window.show_view("spectrogram")
    window.show_view("waterfall")
    window.close()  # while the workers may still run
    from PySide6.QtCore import QThread

    running = [thread for thread in window.findChildren(QThread) if thread.isRunning()]
    assert running == []
    assert not window.model.loading
