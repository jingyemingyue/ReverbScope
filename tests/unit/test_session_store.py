from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from reverbscope.core.compare import compare
from reverbscope.core.pipeline import Reference, analyze, synthetic_recording
from reverbscope.errors import SessionError
from reverbscope.io.session_store import (
    COMPARISON_FILE,
    IR_FILE,
    RESULT_FILE,
    SESSION_FILE,
    list_sessions,
    load_comparison,
    load_measurement,
    load_session,
    save_comparison,
    save_measurement,
)
from reverbscope.io.wav import read_wav
from reverbscope.models.configuration import SweepSettings
from reverbscope.models.session import MeasurementSession
from tests.conftest import make_rir


def test_save_and_load_measurement(tmp_path: Path, short_sweep: SweepSettings) -> None:
    ir = make_rir(short_sweep.sample_rate, rt60_s=0.3)
    rec = synthetic_recording(short_sweep, ir, noise_rms=1e-5)
    result = analyze(rec, Reference.from_settings(short_sweep))
    session = MeasurementSession(
        room_name="Booth", sweep_settings=short_sweep, recording_path=str(tmp_path / "rec.wav")
    )
    out = tmp_path / "session"
    session_path = save_measurement(out, session, result, include_curves=False)
    assert session_path == out / SESSION_FILE
    assert (out / RESULT_FILE).is_file() and (out / IR_FILE).is_file()

    loaded = load_session(out)
    assert loaded.room_name == "Booth"
    assert loaded.impulse_response_path == IR_FILE
    assert loaded.result_path == RESULT_FILE
    assert loaded.recording_path == str(tmp_path / "rec.wav")
    assert loaded.analysis_summary["broadband_rt60_estimate_s"] is not None
    assert loaded.analysis_summary["bands"]["1 kHz"]["t30_s"] is not None

    stored_ir = read_wav(out / IR_FILE)
    assert np.allclose(stored_ir.samples, result.impulse_response.samples, atol=1e-6)
    payload = json.loads((out / RESULT_FILE).read_text())
    assert payload["schema_version"] == 1
    assert "edc_db" not in payload["decay"]["broadband"]

    measurement = load_measurement(out)
    assert measurement.session.room_name == "Booth"
    assert np.allclose(
        measurement.result.impulse_response.samples,
        result.impulse_response.samples,
        atol=1e-6,
    )
    assert measurement.result.decay.broadband.rt60_estimate_s == (
        result.decay.broadband.rt60_estimate_s
    )
    from_file = load_measurement(out / SESSION_FILE)
    assert from_file.directory == measurement.directory


def test_load_measurement_requires_ir_when_result_has_no_samples(
    tmp_path: Path, short_sweep: SweepSettings
) -> None:
    ir = make_rir(short_sweep.sample_rate, rt60_s=0.3)
    rec = synthetic_recording(short_sweep, ir, noise_rms=1e-5)
    result = analyze(rec, Reference.from_settings(short_sweep))
    out = tmp_path / "session"
    save_measurement(out, MeasurementSession(room_name="Booth"), result, include_curves=False)
    (out / IR_FILE).unlink()
    with pytest.raises(SessionError, match=r"impulse_response\.wav"):
        load_measurement(out)


def test_load_measurement_requires_result_json(tmp_path: Path, short_sweep: SweepSettings) -> None:
    ir = make_rir(short_sweep.sample_rate, rt60_s=0.3)
    rec = synthetic_recording(short_sweep, ir, noise_rms=1e-5)
    result = analyze(rec, Reference.from_settings(short_sweep))
    out = tmp_path / "session"
    save_measurement(out, MeasurementSession(room_name="Booth"), result, include_curves=False)
    (out / RESULT_FILE).unlink()
    with pytest.raises(SessionError, match=r"result\.json"):
        load_measurement(out)


def test_list_sessions_skips_broken_and_orders_newest(
    tmp_path: Path, short_sweep: SweepSettings
) -> None:
    ir = make_rir(short_sweep.sample_rate, rt60_s=0.3)
    rec = synthetic_recording(short_sweep, ir, noise_rms=1e-5)
    result = analyze(rec, Reference.from_settings(short_sweep))
    first = tmp_path / "older"
    second = tmp_path / "nested" / "newer"
    save_measurement(
        first,
        MeasurementSession(room_name="Older", created_at="2020-01-01T00:00:00+00:00"),
        result,
        include_curves=False,
    )
    save_measurement(
        second,
        MeasurementSession(room_name="Newer", created_at="2024-01-01T00:00:00+00:00"),
        result,
        include_curves=False,
    )
    broken = tmp_path / "broken"
    broken.mkdir()
    (broken / SESSION_FILE).write_text("not json", encoding="utf-8")
    hidden = tmp_path / ".hidden" / "secret"
    save_measurement(hidden, MeasurementSession(room_name="Hidden"), result, include_curves=False)

    listings = list_sessions(tmp_path)
    names = [item.session.room_name for item in listings]
    assert names == ["Newer", "Older"]
    assert "Newer" in listings[0].label
    assert "RT60" in listings[0].label


def test_save_and_load_comparison_does_not_store_findings(
    tmp_path: Path, short_sweep: SweepSettings
) -> None:
    ir = make_rir(short_sweep.sample_rate, rt60_s=0.3)
    rec = synthetic_recording(short_sweep, ir, noise_rms=1e-5)
    result = analyze(rec, Reference.from_settings(short_sweep))
    comparison = compare(result, result)
    written = save_comparison(tmp_path / "out", comparison)
    assert written == tmp_path / "out" / COMPARISON_FILE
    payload = json.loads(written.read_text(encoding="utf-8"))
    assert "findings" not in payload
    loaded = load_comparison(tmp_path / "out")
    assert loaded.comparable is comparison.comparable
    assert loaded.schema_version == comparison.schema_version
    again = load_comparison(written)
    assert again.common_band == comparison.common_band
