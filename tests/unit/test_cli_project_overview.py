"""``reverbscope project overview``: the takes, the positions, the average, the next steps."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

import pytest

from reverbscope.cli.main import main
from reverbscope.core.pipeline import Reference, analyze, synthetic_recording
from reverbscope.io.project_store import add_session, save_project
from reverbscope.io.session_store import save_measurement
from reverbscope.models.configuration import SweepSettings
from reverbscope.models.project import Project
from reverbscope.models.result import AnalysisResult
from reverbscope.models.session import MeasurementSession
from tests.conftest import make_rir


def _result(sweep: SweepSettings, rt60_s: float, seed: int, strong: bool = False) -> AnalysisResult:
    ir = make_rir(
        sweep.sample_rate,
        rt60_s=rt60_s,
        reflections=[(0.010, 0.5)] if strong else [],
        diffuse_level=0.02,
        seed=seed,
    )
    recording = synthetic_recording(sweep, ir, noise_rms=1e-5, seed=seed)
    return analyze(recording, Reference.from_settings(sweep))


@pytest.fixture
def booth(tmp_path: Path, short_sweep: SweepSettings) -> Path:
    project = tmp_path / "booth"
    save_project(project, Project(name="Booth"))
    takes = (
        ("a-1", "A", _result(short_sweep, 0.35, 1)),
        ("a-2", "A", _result(short_sweep, 0.35, 2)),
        ("b-1", "B", _result(short_sweep, 0.9, 3, strong=True)),
        ("a-3", "A", _result(short_sweep, 0.35, 4)),
    )
    for name, position, result in takes:
        session = MeasurementSession(
            room_name="Booth", measurement_position=position, recording_profile="vocal"
        )
        save_measurement(project / name, session, result, copy_recording=False)
        add_session(project, project / name, position=position)
    # A take whose result file is damaged is listed as not read, not hidden.
    (project / "a-3" / "result.json").write_text("{", encoding="utf-8")
    return project


def test_project_overview_prints_takes_positions_average_and_next_steps(
    booth: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["--color", "never", "project", "overview", str(booth)]) == 0
    # The console wraps long sentences: compare on one line.
    out = " ".join(capsys.readouterr().out.split())
    assert "ReverbScope project overview" in out
    assert "Booth" in out and "Vocals" in out
    assert "2 position(s), 3 session(s), 0 unlisted" in out
    # The takes table and the per-position lines.
    assert "a-1" in out and "a-2" in out and "b-1" in out
    assert "a-3" in out and "not read" in out
    assert "takes agree" in out  # A
    assert "against position A" in out  # B
    assert "warnings" in out and "fits" in out
    # The spatial average and its ISO class, and what to measure next.
    assert "Spatial average" in out and "survey" in out
    assert "differ by" in out and "% across the room" in out
    assert "second take at B" in out
    assert "A is the one position that fits the Vocals profile" in out
    assert "second source position" in out


def test_project_overview_json_and_profile_override(
    booth: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert (
        main(["--format", "json", "project", "overview", str(booth), "--profile", "generic"]) == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["profile"] == "generic" and payload["name"] == "Booth"
    assert [p["label"] for p in payload["positions"]] == ["A", "B"]
    assert len(payload["positions"][0]["sessions"]) == 2
    assert payload["positions"][1]["verdict"]["aspects"]
    assert payload["averaged"]["iso_3382_2_class"] == "survey"
    assert payload["skipped"] and payload["skipped"][0][0].endswith("a-3")
    assert payload["next_steps"]


def test_project_overview_lists_a_position_whose_folder_is_gone_instead_of_dropping_it(
    booth: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Deleting a session folder left the overview at "1 position(s)" with no
    word about the position that had been listed."""
    shutil.rmtree(booth / "b-1")
    assert main(["--color", "never", "project", "overview", str(booth)]) == 0
    out = " ".join(capsys.readouterr().out.split())
    assert "b-1: not read" in out and "position B: no session.json there" in out
    assert "1 position(s), 2 session(s), 0 unlisted" in out
    assert main(["--format", "json", "project", "overview", str(booth)]) == 0
    skipped = json.loads(capsys.readouterr().out)["skipped"]
    assert ["b-1", "position B: no session.json there"] in skipped
    assert main(["--lang", "zh_CN", "--color", "never", "project", "overview", str(booth)]) == 0
    assert "那里没有 session.json" in capsys.readouterr().out


def test_project_overview_refuses_a_folder_without_a_project(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["project", "overview", str(tmp_path)]) != 0
    assert "project.json" in capsys.readouterr().err


def test_project_average_table_is_unchanged_by_the_shared_renderer(
    booth: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # The average needs every listed take: the damaged one is removed first.
    shutil.rmtree(booth / "a-3")
    assert main(["--color", "never", "project", "average", str(booth)]) == 0
    out = capsys.readouterr().out
    assert "ISO 3382-2 class" in out
    assert "Band" in out and "EDT" in out and "T20" in out and "T30" in out and "RT60" in out
    assert re.search(r"\d\.\d\d s", out)
