"""Folders written while the 3D room view existed still open.

Releases up to 0.5.0b5 could save ``room-geometry.json`` (the entered room
box and device positions, plus an optional scan reference) next to a session
or a project, and users may have copied a PLY or OBJ scan beside it. The room
view, its geometry module and the scan reader were removed; those files are
now ignored. They are never read, rewritten or deleted.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from reverbscope.cli.main import main as cli_main
from reverbscope.core.pipeline import Reference, analyze, synthetic_recording
from reverbscope.io.project_store import add_session, list_project_sessions, save_project
from reverbscope.io.session_store import list_sessions, load_measurement, save_measurement
from reverbscope.models.configuration import SweepSettings
from reverbscope.models.project import Project
from reverbscope.models.session import MeasurementSession
from tests.conftest import make_rir

#: What the removed room view wrote (schema_version 1), scan reference included.
LEGACY_GEOMETRY = {
    "schema_version": 1,
    "room": {"length_m": 5.0, "width_m": 4.0, "height_m": 2.7},
    "source": {"x": 1.2, "y": 2.0, "z": 1.2},
    "microphones": {"A": {"x": 3.5, "y": 2.0, "z": 1.5}},
    "scan": {
        "file": "room.ply",
        "units": "cm",
        "up_axis": "y",
        "yaw_deg": 15.0,
        "offset": {"x": 0.1, "y": 0.2, "z": 0.0},
        "sha256": "0" * 64,
    },
    "notes": "entered by hand",
}
LEGACY_FILES = ("room-geometry.json", "room.ply")


def _leave_legacy_files(folder: Path) -> dict[str, bytes]:
    (folder / "room-geometry.json").write_text(json.dumps(LEGACY_GEOMETRY), encoding="utf-8")
    (folder / "room.ply").write_bytes(b"ply\nformat ascii 1.0\nelement vertex 0\nend_header\n")
    return {name: (folder / name).read_bytes() for name in LEGACY_FILES}


def _session(root: Path, sweep: SweepSettings, name: str = "take") -> Path:
    ir = make_rir(sweep.sample_rate, rt60_s=0.3)
    result = analyze(synthetic_recording(sweep, ir, noise_rms=1e-5), Reference.from_settings(sweep))
    folder = root / name
    save_measurement(
        folder,
        MeasurementSession(room_name="Booth", measurement_position="A"),
        result,
        copy_recording=False,
    )
    return folder


def test_a_session_with_a_room_geometry_file_still_loads(
    tmp_path: Path, short_sweep: SweepSettings
) -> None:
    folder = _session(tmp_path, short_sweep)
    before = _leave_legacy_files(folder)
    loaded = load_measurement(folder)
    assert loaded.session.room_name == "Booth"
    assert loaded.result.decay.broadband is not None
    assert [listing.path for listing in list_sessions(tmp_path)] == [folder]
    # Ignored, not removed or rewritten.
    assert {name: (folder / name).read_bytes() for name in LEGACY_FILES} == before


def test_a_project_with_a_room_geometry_file_still_lists_its_sessions(
    tmp_path: Path, short_sweep: SweepSettings
) -> None:
    project = tmp_path / "booth"
    save_project(project, Project(name="Booth"))
    before = _leave_legacy_files(project)
    take = _session(project, short_sweep, "a-1")
    add_session(project, take, position="A")
    assert [(position, path.resolve()) for position, path in list_project_sessions(project)] == [
        ("A", take.resolve())
    ]
    assert {name: (project / name).read_bytes() for name in LEGACY_FILES} == before


def test_the_cli_reads_a_session_with_a_room_geometry_file(
    tmp_path: Path, short_sweep: SweepSettings, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = _session(tmp_path, short_sweep)
    _leave_legacy_files(folder)
    assert cli_main(["show", str(folder)]) == 0
    assert "Booth" in capsys.readouterr().out


def test_the_room_geometry_module_is_gone() -> None:
    import importlib.util

    assert importlib.util.find_spec("reverbscope.geometry") is None
