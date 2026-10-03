from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from roomscope.core.compare import compare
from roomscope.core.pipeline import Reference, analyze, synthetic_recording
from roomscope.errors import SessionError
from roomscope.io.session_store import (
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
from roomscope.io.wav import read_wav
from roomscope.models.configuration import SweepSettings
from roomscope.models.session import MeasurementSession
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


@pytest.fixture
def analysed(short_sweep: SweepSettings):  # type: ignore[no-untyped-def]
    ir = make_rir(short_sweep.sample_rate, rt60_s=0.3)
    rec = synthetic_recording(short_sweep, ir, noise_rms=1e-5)
    return rec, analyze(rec, Reference.from_settings(short_sweep))


def test_saving_one_session_twice_keeps_the_recording(
    tmp_path: Path, short_sweep: SweepSettings, analysed, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The GUI saves state.session again (a second folder, or an opened
    session elsewhere). save_measurement rewrote the caller's paths relative
    to the first folder, so the second save looked for recording.wav in the
    working directory and stored a path that does not exist."""
    from roomscope.io.wav import write_wav

    recording, result = analysed
    take = write_wav(tmp_path / "in" / "take.wav", recording.samples, 48000, subtype="FLOAT")
    monkeypatch.chdir(tmp_path)  # neither session folder
    session = MeasurementSession(sweep_settings=short_sweep, recording_path=str(take))
    save_measurement(tmp_path / "A", session, result, copy_recording=True)
    save_measurement(tmp_path / "B", session, result, copy_recording=True)
    assert session.recording_path == str(take)
    loaded = load_measurement(tmp_path / "A")
    save_measurement(tmp_path / "C", loaded.session, loaded.result, copy_recording=True)
    for name in ("A", "B", "C"):
        stored = json.loads((tmp_path / name / SESSION_FILE).read_text(encoding="utf-8"))
        assert stored["recording_path"] == "recording.wav", name
        assert (tmp_path / name / "recording.wav").read_bytes() == take.read_bytes(), name


def test_list_sessions_skips_refused_and_mistyped_sessions(tmp_path: Path, analysed) -> None:
    _recording, result = analysed
    good = tmp_path / "good"
    save_measurement(good, MeasurementSession(room_name="Good"), result, include_curves=False)
    for name, change in (
        ("rate", {"sweep_settings": {"sample_rate": 12345}}),  # ConfigurationError
        ("created", {"created_at": None}),  # would break the sort
        ("summary", {"analysis_summary": []}),  # would break the label
    ):
        folder = tmp_path / name
        save_measurement(folder, MeasurementSession(), result, include_curves=False)
        data = json.loads((folder / SESSION_FILE).read_text(encoding="utf-8"))
        data.update(change)
        (folder / SESSION_FILE).write_text(json.dumps(data), encoding="utf-8")
    listings = list_sessions(tmp_path)
    assert [item.session.room_name for item in listings] == ["Good"]
    assert listings[0].label


def test_bundle_the_folder_you_are_in(
    tmp_path: Path, analysed, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``roomscope session bundle .`` failed: Path('.') has no name."""
    from roomscope.io.session_store import bundle_session

    _recording, result = analysed
    folder = tmp_path / "booth"
    save_measurement(folder, MeasurementSession(), result, include_curves=False)
    monkeypatch.chdir(folder)
    assert bundle_session(".") == tmp_path / "booth.zip"
    (tmp_path / "out").mkdir()
    assert bundle_session(SESSION_FILE, tmp_path / "out") == tmp_path / "out" / "booth.zip"


def test_a_failed_write_keeps_the_previous_session(
    tmp_path: Path, analysed, monkeypatch: pytest.MonkeyPatch
) -> None:
    """write_text truncated session.json and result.json first, so a full
    disk half-way through destroyed the session being replaced."""
    import os

    from roomscope.io import jsonutil

    _recording, result = analysed
    folder = tmp_path / "s"
    save_measurement(folder, MeasurementSession(room_name="First"), result, include_curves=False)
    before = {name: (folder / name).read_bytes() for name in (SESSION_FILE, RESULT_FILE)}

    def disk_full(_fd: int) -> None:
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(jsonutil.os, "fsync", disk_full)
    with pytest.raises(SessionError, match="No space left"):
        save_measurement(
            folder, MeasurementSession(room_name="Second"), result, include_curves=False
        )
    monkeypatch.setattr(jsonutil.os, "fsync", os.fsync)
    assert {name: (folder / name).read_bytes() for name in before} == before
    assert load_measurement(folder).session.room_name == "First"
    assert not list(folder.glob(".*.tmp"))
