"""Shipped JSON Schemas validate writers and match ``roomscope schema``."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from jsonschema import Draft202012Validator

from roomscope.cli.main import main
from roomscope.core.pipeline import Reference, analyze, synthetic_recording
from roomscope.io.wav import write_sweep_file
from roomscope.models.comparison import ComparisonResult
from roomscope.models.project import Project
from roomscope.models.session import MeasurementSession
from roomscope.schemas import SCHEMA_FILES, load_schema, schema_text
from tests.conftest import make_rir


def _validate(name: str, payload: dict) -> None:
    Draft202012Validator(load_schema(name)).validate(payload)


def test_schema_cli_matches_shipped_files(capsys: pytest.CaptureFixture[str]) -> None:
    for name, filename in SCHEMA_FILES.items():
        assert main(["schema", name]) == 0
        printed = capsys.readouterr().out
        assert printed == schema_text(name)
        shipped = Path("src/roomscope/schemas") / filename
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
    sidecar = json.loads((tmp_path / "sweep.roomscope-sweep.json").read_text(encoding="utf-8"))
    _validate("sidecar", sidecar)


def test_comparison_and_project_to_dict_validate(short_sweep) -> None:
    from roomscope.core.compare import compare

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


def test_the_schema_requires_what_the_loader_requires() -> None:
    """A schema-valid result.json without these was refused by the loader."""
    from roomscope.schemas import load_schema

    schema = load_schema("result")
    required = schema["$defs"]["impulse_response"]["required"]
    for field in ("direct_sound_index", "pre_delay_samples", "peak_value", "valid_length_s"):
        assert field in required


@pytest.fixture(scope="module")
def full_result(short_sweep) -> dict:  # type: ignore[no-untyped-def]
    """A result with every optional record filled, as ``to_dict`` writes it."""
    from dataclasses import replace

    from roomscope.models.configuration import AnalysisSettings
    from roomscope.models.result import ResonanceCandidate

    ir = make_rir(short_sweep.sample_rate, rt60_s=0.3, reflections=[(0.004, 0.5), (0.018, 0.35)])
    rec = synthetic_recording(short_sweep, ir, noise_rms=1e-5)
    result = analyze(
        rec,
        Reference.from_settings(short_sweep),
        AnalysisSettings(placement_distance_m=1.0, placement_mic_height_m=1.2),
        loopback=rec,
    )
    candidate = ResonanceCandidate(
        frequency_hz=48.0,
        level_above_baseline_db=9.0,
        narrowband_decay_20db_s=0.4,
        filter_ringing_20db_s=0.1,
        decay_distinguishable=True,
    )
    result = replace(result, resonances=replace(result.resonances, candidates=(candidate,)))
    ir_result = result.impulse_response
    assert result.placement is not None and result.placement.candidates
    assert ir_result.loopback is not None and ir_result.harmonic_distortion
    assert ir_result.aliased_distortion and result.noise.hum
    return result.to_dict(include_curves=True)


def test_every_record_of_a_full_result_validates(full_result: dict) -> None:
    _validate("result", full_result)


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("noise", "hum"), [{}]),
        (("resonances", "candidates"), [{}]),
        (("impulse_response", "harmonic_distortion"), [{}]),
        (("impulse_response", "aliased_distortion"), [{}]),
        (("placement",), {"candidates": [{}]}),
        (("impulse_response", "loopback"), {"channel": "x"}),
        (("decay", "broadband"), {"edt": 5}),
        (("decay", "bands"), [{"t30": {"evaluation_range_db": [1]}}]),
        (("noise", "band_levels_dbfs"), [[1]]),
        (("decay", "broadband", "edc_db"), 5),
        (("sample_rate",), 0),
        (("impulse_response", "direct_sound_index"), 2**60),
    ],
    ids=lambda value: repr(value)[:40],
)
def test_the_schema_refuses_what_the_loader_refuses(
    full_result: dict, path: tuple[str, ...], value: object
) -> None:
    """Each of these passed the published schema and was refused on load."""
    import copy

    from roomscope.errors import SessionError
    from roomscope.models.result import AnalysisResult

    edited = copy.deepcopy(full_result)
    target = edited
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    assert not Draft202012Validator(load_schema("result")).is_valid(edited)
    with pytest.raises(SessionError):
        AnalysisResult.from_dict(edited)


def _comparison_with_every_record() -> dict:
    from roomscope.models.comparison import (
        FrequencyResponseDelta,
        MetricDelta,
        ReflectionMatch,
        ResonanceMatch,
    )
    from roomscope.models.result import Validity

    delta = MetricDelta("broadband.t30", 0.5, 0.55, Validity.VALID, delta=0.05, unit="s")
    return ComparisonResult(
        comparable=True,
        common_band=(20.0, 20000.0),
        decay=(delta,),
        frequency_response=FrequencyResponseDelta(
            np.array([100.0, 200.0]), np.array([0.5, -0.5]), (("125 Hz", 0.5),), 6, "dB"
        ),
        reflections=(
            ReflectionMatch("matched", 3.0, 3.1, -6.0, -7.0, 0.1, -1.0),
            ReflectionMatch("appeared", candidate_delay_ms=4.0, candidate_relative_db=-9.0),
            ReflectionMatch("disappeared", baseline_delay_ms=5.0, baseline_relative_db=-8.0),
        ),
        resonances=(ResonanceMatch("matched", 50.0, 51.0, True, False),),
    ).to_dict()


def test_every_record_of_a_full_comparison_validates() -> None:
    payload = _comparison_with_every_record()
    _validate("comparison", payload)
    assert len(ComparisonResult.from_dict(payload).reflections) == 3


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("decay", [{"name": "broadband.t30", "validity": "valid"}]),
        ("decay", [{"name": 5, "baseline": 1.0, "candidate": 1.1, "validity": "valid"}]),
        ("reflections", [{"status": "matched", "baseline_delay_ms": 3.0}]),
        ("reflections", [{"status": "appeared", "baseline_delay_ms": 3.0}]),
        ("reflections", [{"status": None}]),
        ("resonances", [{"status": 5}]),
        ("frequency_response", {"band_mad_db": [["1 kHz"]]}),
        ("comparable", "false"),
    ],
    ids=lambda value: repr(value)[:40],
)
def test_the_comparison_schema_refuses_what_the_loader_refuses(key: str, value: object) -> None:
    from roomscope.errors import SessionError

    edited = {**_comparison_with_every_record(), key: value}
    assert not Draft202012Validator(load_schema("comparison")).is_valid(edited)
    with pytest.raises(SessionError):
        ComparisonResult.from_dict(edited)
