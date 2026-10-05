from __future__ import annotations

import json

import numpy as np
import pytest

from reverbscope.core.pipeline import Reference, analyze, synthetic_recording
from reverbscope.errors import ConfigurationError, InvalidAudioError, SessionError
from reverbscope.models.audio import AudioSignal
from reverbscope.models.configuration import AnalysisSettings, SweepSettings
from reverbscope.models.result import AnalysisResult
from reverbscope.models.session import MeasurementSession
from tests.conftest import make_rir


def test_sweep_settings_round_trip_and_resample() -> None:
    s = SweepSettings(sample_rate=48000, duration_s=3.0)
    assert SweepSettings.from_dict(s.to_dict()) == s
    r = s.with_sample_rate(96000)
    assert r.sample_rate == 96000 and r.duration_s == 3.0
    assert r.sweep_rate == pytest.approx(s.sweep_rate)
    extra = SweepSettings.from_dict({**s.to_dict(), "bogus": 1})
    assert extra == s


@pytest.mark.parametrize(
    "kwargs",
    [
        {"duration_s": 0.1},
        {"start_hz": 0.0},
        {"end_hz": 10.0},
        {"fade_in_s": 5.0, "fade_out_s": 6.0},
        {"level_dbfs": -100.0},
        {"pre_silence_s": -1.0},
    ],
)
def test_sweep_settings_validation(kwargs: dict[str, float]) -> None:
    with pytest.raises(ConfigurationError):
        SweepSettings(**kwargs)


def test_analysis_settings_validation_and_round_trip() -> None:
    a = AnalysisSettings(channel=1, octave_bands_hz=(125.0, 250.0))
    assert AnalysisSettings.from_dict(a.to_dict()) == a
    with pytest.raises(ConfigurationError):
        AnalysisSettings(octave_bands_hz=(250.0, 125.0))
    with pytest.raises(ConfigurationError):
        AnalysisSettings(reflections_threshold_db=3.0)
    extra = AnalysisSettings.from_dict({**a.to_dict(), "nope": 1})
    assert extra == a


def test_audio_signal_validation_and_channel_selection() -> None:
    with pytest.raises(InvalidAudioError):
        AudioSignal(np.zeros(0), 48000)
    with pytest.raises(InvalidAudioError):
        AudioSignal(np.array([np.nan, 1.0]), 48000)
    stereo = AudioSignal(np.stack([np.full(100, 0.1), np.full(100, 0.5)], axis=1), 48000)
    assert stereo.n_channels == 2
    mono, idx, warning = stereo.select_channel(None)
    assert idx == 1 and warning is not None and np.all(mono == 0.5)
    mono0, idx0, warning0 = stereo.select_channel(0)
    assert idx0 == 0 and warning0 is None and np.all(mono0 == 0.1)
    with pytest.raises(InvalidAudioError):
        stereo.channel(2)


def test_session_round_trip_and_schema_check() -> None:
    session = MeasurementSession(room_name="A", sweep_settings=SweepSettings(duration_s=2.0))
    data = json.loads(json.dumps(session.to_dict()))
    loaded = MeasurementSession.from_dict(data)
    assert loaded == session
    with pytest.raises(SessionError):
        MeasurementSession.from_dict({**data, "schema_version": 99})
    loaded_extra = MeasurementSession.from_dict({**data, "unknown": 1})
    assert loaded_extra.room_name == session.room_name


def test_analysis_result_is_json_serialisable(short_sweep: SweepSettings) -> None:
    ir = make_rir(short_sweep.sample_rate, rt60_s=0.3, reflections=[(0.018, 0.35)])
    rec = synthetic_recording(short_sweep, ir, noise_rms=1e-5)
    result = analyze(rec, Reference.from_settings(short_sweep))
    payload = result.to_dict(include_curves=True)
    text = json.dumps(payload)
    back = json.loads(text)
    assert back["schema_version"] == 1
    assert back["decay"]["broadband"]["rt60_estimate_s"] is not None
    assert "magnitude_db_raw" in back["frequency_response"]
    assert "samples" not in back["impulse_response"]
    slim = result.to_dict(include_curves=False)
    assert "magnitude_db_raw" not in slim["frequency_response"]

    loaded = AnalysisResult.from_dict(json.loads(text))
    assert loaded.sample_rate == result.sample_rate
    assert loaded.decay.broadband.rt60_estimate_s == result.decay.broadband.rt60_estimate_s
    assert loaded.impulse_response.direct_sound_index == result.impulse_response.direct_sound_index
    assert loaded.impulse_response.samples.size == 0
    slim_loaded = AnalysisResult.from_dict(slim)
    assert slim_loaded.frequency_response.frequencies_hz.size == 0
    assert slim_loaded.reflections.reflections == result.reflections.reflections

    extra = dict(slim)
    extra["future_field"] = {"ok": True}
    AnalysisResult.from_dict(extra)
    with pytest.raises(SessionError):
        AnalysisResult.from_dict({**slim, "schema_version": 99})


def test_session_recording_profile_defaults_when_absent() -> None:
    session = MeasurementSession(room_name="A", recording_profile="vocal")
    data = session.to_dict()
    assert data["recording_profile"] == "vocal"
    del data["recording_profile"]
    loaded = MeasurementSession.from_dict(data)
    assert loaded.recording_profile == "generic"
