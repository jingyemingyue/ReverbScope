"""Untrusted session, sidecar and WAV files raise ReverbScopeError only."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from reverbscope.core.pipeline import Reference, analyze, synthetic_recording
from reverbscope.errors import InvalidAudioError, ReverbScopeError, SessionError
from reverbscope.io.jsonutil import MAX_JSON_BYTES, MAX_JSON_DEPTH, read_json_object
from reverbscope.io.project_store import load_project
from reverbscope.io.session_store import load_comparison, load_measurement, load_session
from reverbscope.io.wav import read_sweep_sidecar, read_wav
from reverbscope.models.audio import AudioSignal
from reverbscope.models.configuration import SweepSettings
from tests.conftest import make_rir


def test_malformed_session_json_is_reverbscope_error(tmp_path: Path) -> None:
    path = tmp_path / "session.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(SessionError):
        load_session(path)


def test_oversized_session_json_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "session.json"
    path.write_bytes(b"{" + b" " * (MAX_JSON_BYTES + 1) + b"}")
    with pytest.raises(SessionError, match="refused"):
        load_session(path)


def test_session_json_array_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "session.json"
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(SessionError, match="not a JSON object"):
        load_session(path)


def test_truncated_wav_is_invalid_audio(tmp_path: Path) -> None:
    path = tmp_path / "broken.wav"
    path.write_bytes(b"RIFF\x00\x00\x00\x00WAVE")
    with pytest.raises(InvalidAudioError):
        read_wav(path)


def test_nan_audio_is_invalid() -> None:
    with pytest.raises(InvalidAudioError, match="NaN"):
        AudioSignal(samples=np.array([0.0, np.nan]), sample_rate=48000)


def test_sidecar_must_be_an_object(tmp_path: Path) -> None:
    path = tmp_path / "sweep.reverbscope-sweep.json"
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(ReverbScopeError):
        read_sweep_sidecar(path)


def test_missing_result_json_is_session_error(tmp_path: Path) -> None:
    session = tmp_path / "session.json"
    session.write_text(json.dumps({"schema_version": 1, "room_name": "X"}), encoding="utf-8")
    with pytest.raises(SessionError):
        load_measurement(tmp_path)


def test_deeply_nested_json_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "session.json"
    depth = MAX_JSON_DEPTH + 8
    path.write_text("{" * depth + "}" * depth, encoding="utf-8")
    with pytest.raises(SessionError, match="deeper"):
        read_json_object(path, kind="session")


def test_deeply_nested_project_is_session_error(tmp_path: Path) -> None:
    path = tmp_path / "project.json"
    depth = MAX_JSON_DEPTH + 2
    path.write_text("{" * depth + "}" * depth, encoding="utf-8")
    with pytest.raises(SessionError, match="deeper"):
        load_project(tmp_path)


def test_infinite_audio_is_invalid() -> None:
    with pytest.raises(InvalidAudioError, match="infinite"):
        AudioSignal(samples=np.array([0.0, np.inf]), sample_rate=48000)


def test_garbage_wav_is_invalid_audio(tmp_path: Path) -> None:
    path = tmp_path / "garbage.wav"
    path.write_bytes(b"this is not a RIFF wave file at all")
    with pytest.raises(InvalidAudioError):
        read_wav(path)


def test_oversized_sidecar_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "sweep.reverbscope-sweep.json"
    path.write_bytes(b"{" + b" " * 1_000_001 + b"}")
    with pytest.raises(ReverbScopeError):
        read_sweep_sidecar(path)


def test_malformed_project_json_is_session_error(tmp_path: Path) -> None:
    (tmp_path / "project.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(SessionError):
        load_project(tmp_path)


def test_malformed_result_json_is_session_error(tmp_path: Path) -> None:
    (tmp_path / "session.json").write_text(
        json.dumps({"schema_version": 1, "room_name": "X"}), encoding="utf-8"
    )
    (tmp_path / "result.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(SessionError):
        load_measurement(tmp_path)


def test_malformed_comparison_json_is_session_error(tmp_path: Path) -> None:
    path = tmp_path / "comparison.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(SessionError):
        load_comparison(path)


def test_comparison_json_array_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "comparison.json"
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(SessionError, match="not a JSON object"):
        load_comparison(path)


def test_oversized_comparison_json_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "comparison.json"
    path.write_bytes(b"{" + b" " * (MAX_JSON_BYTES + 1) + b"}")
    with pytest.raises(SessionError, match="refused"):
        load_comparison(path)


def test_deeply_nested_comparison_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "comparison.json"
    depth = MAX_JSON_DEPTH + 4
    path.write_text("{" * depth + "}" * depth, encoding="utf-8")
    with pytest.raises(SessionError, match="deeper"):
        load_comparison(path)


def test_loopback_that_is_a_microphone_does_not_raise(
    short_sweep: SweepSettings,
) -> None:
    ir = make_rir(short_sweep.sample_rate, rt60_s=0.4, reflections=[(0.018, 0.35)])
    rec = synthetic_recording(short_sweep, ir, noise_rms=1e-5)
    result = analyze(rec, Reference.from_settings(short_sweep), loopback=rec)
    assert result.impulse_response.loopback is not None
    assert result.impulse_response.loopback.compensation_applied is False
    assert result.impulse_response.loopback.reason is not None


def test_src_does_not_use_pickle_eval_or_shell() -> None:
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "check_src_safety", Path("scripts") / "check_src_safety.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.check(Path("src")) == []


# ------------------------------------------------------------------ #11


@pytest.fixture(scope="module")
def saved_session(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A real session folder written by ``save_measurement``."""
    from reverbscope.io.session_store import save_measurement
    from reverbscope.models.session import MeasurementSession

    sweep = SweepSettings(sample_rate=48000, duration_s=2.0, post_silence_s=1.5)
    result = analyze(
        synthetic_recording(sweep, make_rir(48000, rt60_s=0.3), noise_rms=1e-5),
        Reference.from_settings(sweep),
    )
    folder = tmp_path_factory.mktemp("session")
    save_measurement(folder, MeasurementSession(sweep_settings=sweep), result, copy_recording=False)
    return folder


def _copy_with_members(saved: Path, tmp_path: Path, **members: str) -> Path:
    import shutil

    folder = tmp_path / "received"
    shutil.copytree(saved, folder)
    session_file = folder / "session.json"
    data = json.loads(session_file.read_text(encoding="utf-8"))
    data.update(members)
    session_file.write_text(json.dumps(data), encoding="utf-8")
    return folder


def test_saved_session_members_are_relative_and_load(saved_session: Path) -> None:
    data = json.loads((saved_session / "session.json").read_text(encoding="utf-8"))
    assert data["result_path"] == "result.json"
    assert data["impulse_response_path"] == "impulse_response.wav"
    assert load_measurement(saved_session).result.impulse_response.samples.size > 0


@pytest.mark.parametrize(
    "member", ["result_path", "impulse_response_path"], ids=["result", "impulse_response"]
)
@pytest.mark.parametrize(
    "stored",
    ["../../../../../../etc/passwd", "../outside.json", "sub/../../outside.json"],
    ids=["etc-passwd", "parent", "sub-parent"],
)
def test_session_member_outside_the_folder_is_refused(
    saved_session: Path, tmp_path: Path, member: str, stored: str
) -> None:
    (tmp_path / "outside.json").write_text("{}", encoding="utf-8")
    folder = _copy_with_members(saved_session, tmp_path, **{member: stored})
    with pytest.raises(SessionError, match="outside the session folder"):
        load_measurement(folder)


@pytest.mark.parametrize("member", ["result_path", "impulse_response_path"])
def test_absolute_session_member_is_refused(
    saved_session: Path, tmp_path: Path, member: str
) -> None:
    target = tmp_path / "elsewhere.json"
    target.write_text("{}", encoding="utf-8")
    folder = _copy_with_members(saved_session, tmp_path, **{member: str(target.resolve())})
    with pytest.raises(SessionError, match="absolute path"):
        load_measurement(folder)


def test_symlinked_member_leading_outside_is_refused(saved_session: Path, tmp_path: Path) -> None:
    import os

    folder = _copy_with_members(saved_session, tmp_path, result_path="link.json")
    outside = tmp_path / "secret.json"
    outside.write_text("{}", encoding="utf-8")
    try:
        os.symlink(outside, folder / "link.json")
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are not available here")
    with pytest.raises(SessionError, match="outside the session folder"):
        load_measurement(folder)


def test_member_in_a_subfolder_still_loads(saved_session: Path, tmp_path: Path) -> None:
    folder = _copy_with_members(saved_session, tmp_path, result_path="data/result.json")
    (folder / "data").mkdir()
    (folder / "result.json").rename(folder / "data" / "result.json")
    assert load_measurement(folder).result.sample_rate == 48000


@pytest.mark.parametrize(
    ("payload", "match"),
    [
        ({"decay": [{"validity": "valid"}]}, "metric delta"),
        ({"decay": ["not an object"]}, "metric delta must be a JSON object"),
        ({"reflections": [{"baseline_delay_ms": 3.0}]}, "reflection match"),
        ({"resonances": [{"baseline_hz": 50.0}]}, "resonance match"),
        ({"frequency_response": {"band_mad_db": [["1 kHz"]]}}, "frequency-response delta"),
        ({"common_band": [20.0]}, "invalid comparison file"),
    ],
    ids=["delta-missing-name", "delta-not-object", "reflection", "resonance", "fr", "band"],
)
def test_incomplete_comparison_records_are_session_errors(
    tmp_path: Path, payload: dict, match: str
) -> None:
    path = tmp_path / "comparison.json"
    path.write_text(json.dumps({"comparable": True, **payload}), encoding="utf-8")
    with pytest.raises(SessionError, match=match):
        load_comparison(path)


def test_invalid_compare_settings_and_calibration_are_session_errors() -> None:
    from reverbscope.models.calibration import CalibrationRecord
    from reverbscope.models.comparison import CompareSettings

    with pytest.raises(SessionError, match="compare settings"):
        CompareSettings.from_dict({"min_common_band_octaves": -1.0})
    with pytest.raises(SessionError, match="calibration"):
        CalibrationRecord.from_dict({"reference_dbfs": -20.0})
    with pytest.raises(SessionError, match="calibration must be a JSON object"):
        CalibrationRecord.from_dict([])  # type: ignore[arg-type]
    record = CalibrationRecord.from_dict({"reference_dbfs": -20.0, "reference_db_spl": 94.0})
    assert record.reference_db_spl == 94.0
