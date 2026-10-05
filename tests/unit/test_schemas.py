"""Shipped JSON Schemas validate writers and match ``reverbscope schema``."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from reverbscope.cli.main import main
from reverbscope.core.pipeline import Reference, analyze, synthetic_recording
from reverbscope.io.wav import write_sweep_file
from reverbscope.models.comparison import ComparisonResult
from reverbscope.models.project import Project
from reverbscope.models.session import MeasurementSession
from reverbscope.schemas import SCHEMA_FILES, load_schema, schema_text
from tests.conftest import make_rir


def _validate(name: str, payload: dict) -> None:
    Draft202012Validator(load_schema(name)).validate(payload)


def test_schema_cli_matches_shipped_files(capsys: pytest.CaptureFixture[str]) -> None:
    for name, filename in SCHEMA_FILES.items():
        assert main(["schema", name]) == 0
        printed = capsys.readouterr().out
        assert printed == schema_text(name)
        shipped = Path("src/reverbscope/schemas") / filename
        assert shipped.read_text(encoding="utf-8") == printed


def test_result_and_session_to_dict_validate(short_sweep, tmp_path: Path) -> None:
    ir = make_rir(short_sweep.sample_rate, rt60_s=0.3, reflections=[(0.018, 0.35)])
    rec = synthetic_recording(short_sweep, ir, noise_rms=1e-5)
    result = analyze(rec, Reference.from_settings(short_sweep))
    _validate("result", result.to_dict(include_curves=True))
    _validate("result", result.to_dict(include_curves=False))

    session = MeasurementSession(room_name="Booth", sweep_settings=short_sweep)
    _validate("session", session.to_dict())

    write_sweep_file(short_sweep, tmp_path / "sweep.wav")
    sidecar = json.loads((tmp_path / "sweep.reverbscope-sweep.json").read_text(encoding="utf-8"))
    _validate("sidecar", sidecar)


def test_comparison_and_project_to_dict_validate(short_sweep) -> None:
    from reverbscope.core.compare import compare

    ir_a = make_rir(short_sweep.sample_rate, rt60_s=0.35, reflections=[(0.018, 0.35)])
    ir_b = make_rir(short_sweep.sample_rate, rt60_s=0.55, reflections=[(0.018, 0.22)], seed=3)
    a = analyze(
        synthetic_recording(short_sweep, ir_a, noise_rms=1e-5), Reference.from_settings(short_sweep)
    )
    b = analyze(
        synthetic_recording(short_sweep, ir_b, noise_rms=1e-5), Reference.from_settings(short_sweep)
    )
    comparison = compare(a, b)
    _validate("comparison", comparison.to_dict())
    loaded = ComparisonResult.from_dict({**comparison.to_dict(), "future_field": True})
    assert loaded.comparable == comparison.comparable
    _validate("project", Project(name="Room", notes="").to_dict())
