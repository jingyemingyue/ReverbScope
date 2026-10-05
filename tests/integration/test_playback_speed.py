"""A DAW that plays the sweep at the wrong speed (sample-rate mismatch without
conversion, or time-stretching) is diagnosed instead of reported as an
unidentifiable direct sound."""

from __future__ import annotations

import numpy as np
import pytest
from scipy.signal import fftconvolve, resample_poly

from roomscope.core.pipeline import Reference, analyze
from roomscope.core.playback_speed import diagnose_playback_speed, measure_sweep_speed
from roomscope.core.sweep import measurement_signal
from roomscope.errors import InvalidAudioError
from roomscope.interpretation import interpret
from roomscope.models.audio import AudioSignal
from roomscope.models.configuration import SweepSettings
from roomscope.models.result import KIND_SAMPLE_RATE, KIND_TIME_STRETCH, Validity
from roomscope.models.result_load import analysis_result_from_dict
from tests.conftest import make_rir

SWEEP = SweepSettings(
    sample_rate=48000, duration_s=3.0, pre_silence_s=1.0, post_silence_s=2.0, level_dbfs=-12.0
)


def _played(signal: np.ndarray, sample_rate: int, *, rt60_s: float = 0.4) -> np.ndarray:
    """``signal`` sounding in a room, recorded at ``sample_rate``."""
    ir = make_rir(sample_rate, rt60_s=rt60_s, diffuse_level=0.02, length_s=1.0, seed=3)
    wet = fftconvolve(signal, ir)[: signal.shape[0] + sample_rate] * 0.3
    return wet + np.random.default_rng(3).normal(0.0, 3e-4, wet.shape[0])


@pytest.fixture(scope="module")
def sweep_signal() -> np.ndarray:
    return measurement_signal(SWEEP)


def test_sweep_played_as_generated_measures_unit_speed(sweep_signal: np.ndarray) -> None:
    recording = _played(sweep_signal, 48000, rt60_s=1.2)
    speed = measure_sweep_speed(recording, 48000, SWEEP)
    assert speed == pytest.approx(1.0, abs=0.005)
    assert diagnose_playback_speed(recording, 48000, SWEEP) is None


@pytest.mark.parametrize(
    ("played_at", "expected_ratio"),
    [(44100, 44100 / 48000), (96000, 2.0), (88200, 88200 / 48000)],
)
def test_file_played_without_conversion_names_the_rate(
    sweep_signal: np.ndarray, played_at: int, expected_ratio: float
) -> None:
    # The 48 kHz samples played unchanged at another rate.
    speed = diagnose_playback_speed(_played(sweep_signal, played_at), played_at, SWEEP)
    assert speed is not None
    assert speed.kind == KIND_SAMPLE_RATE
    assert speed.played_rate_hz == played_at
    assert speed.generated_rate_hz == 48000
    assert speed.speed_ratio == pytest.approx(expected_ratio, rel=0.01)


def test_project_rate_differs_from_export_rate(sweep_signal: np.ndarray) -> None:
    """A 44.1 kHz project played the 48 kHz file unconverted and the take was
    exported at 48 kHz: the recording's rate matches the sweep's, its speed
    does not."""
    slowed = np.asarray(resample_poly(sweep_signal, 160, 147), dtype=np.float64)
    speed = diagnose_playback_speed(_played(slowed, 48000), 48000, SWEEP)
    assert speed is not None and speed.kind == KIND_SAMPLE_RATE
    assert speed.played_rate_hz == 44100


@pytest.mark.parametrize("stretch", [0.97, 1.03])
def test_time_stretch_is_not_a_sample_rate(sweep_signal: np.ndarray, stretch: float) -> None:
    stretched = np.asarray(resample_poly(sweep_signal, round(stretch * 100), 100), dtype=np.float64)
    speed = diagnose_playback_speed(_played(stretched, 48000), 48000, SWEEP)
    assert speed is not None
    assert speed.kind == KIND_TIME_STRETCH
    assert speed.played_rate_hz is None
    assert speed.speed_ratio == pytest.approx(1.0 / stretch, rel=0.005)


def test_noise_without_a_sweep_gives_no_diagnosis() -> None:
    noise = np.random.default_rng(0).normal(0.0, 0.1, 48000 * 6)
    assert measure_sweep_speed(noise, 48000, SWEEP) is None
    assert diagnose_playback_speed(noise, 48000, SWEEP) is None


def test_pipeline_reports_sample_rate_mismatch(sweep_signal: np.ndarray) -> None:
    recording = AudioSignal(_played(sweep_signal, 44100), 44100)
    result = analyze(recording, Reference.from_settings(SWEEP))
    ir = result.impulse_response
    assert ir.direct_sound_confidence != "high"
    assert ir.playback_speed is not None
    assert ir.playback_speed.played_rate_hz == 44100
    assert any("without sample-rate conversion" in note for note in ir.notes)
    assert result.decay.broadband.t30.validity is not Validity.VALID
    assert "speed it was generated at" in (result.decay.broadband.t30.reason or "")

    findings = interpret(result)
    ids = [f.message_id for f in findings]
    assert "measurement.playback_sample_rate" in ids
    # The specific cause replaces the generic "direct sound not identified".
    assert "measurement.direct_sound" not in ids
    message = next(f for f in findings if f.message_id == "measurement.playback_sample_rate")
    assert "48000 Hz" in message.message and "44100 Hz" in message.message

    restored = analysis_result_from_dict(result.to_dict())
    assert restored.impulse_response.playback_speed == ir.playback_speed


def test_pipeline_reports_time_stretch(sweep_signal: np.ndarray) -> None:
    stretched = np.asarray(resample_poly(sweep_signal, 103, 100), dtype=np.float64)
    result = analyze(AudioSignal(_played(stretched, 48000), 48000), Reference.from_settings(SWEEP))
    speed = result.impulse_response.playback_speed
    assert speed is not None and speed.kind == KIND_TIME_STRETCH
    ids = [f.message_id for f in interpret(result)]
    assert "measurement.playback_time_stretch" in ids


def test_good_measurement_is_not_checked(sweep_signal: np.ndarray) -> None:
    result = analyze(
        AudioSignal(_played(sweep_signal, 48000), 48000), Reference.from_settings(SWEEP)
    )
    assert result.impulse_response.direct_sound_confidence == "high"
    assert result.impulse_response.playback_speed is None
    assert result.to_dict()["impulse_response"]["playback_speed"] is None


def test_too_short_recording_explains_a_faster_playback(sweep_signal: np.ndarray) -> None:
    """A 48 kHz sweep played at 96 kHz lasts half as long: the recording is
    shorter than the reference, and the error says why."""
    recording = AudioSignal(_played(sweep_signal, 96000)[: 96000 * 3], 96000)
    with pytest.raises(InvalidAudioError, match="played at 96000 Hz"):
        analyze(recording, Reference.from_settings(SWEEP))


def test_finding_is_translated(sweep_signal: np.ndarray) -> None:
    from roomscope.i18n import activate

    result = analyze(
        AudioSignal(_played(sweep_signal, 44100), 44100), Reference.from_settings(SWEEP)
    )
    activate("zh_CN")
    try:
        finding = next(
            f for f in interpret(result) if f.message_id == "measurement.playback_sample_rate"
        )
    finally:
        activate("en")
    assert "采样率" in finding.message
    assert finding.params["played_rate_hz"] == 44100


def test_sample_rate_mismatch_without_a_rate_is_not_called_a_stretch(
    sweep_signal: np.ndarray,
) -> None:
    """A stored ``sample_rate_mismatch`` without ``played_rate_hz`` (allowed by
    the schema) falls back to the generic finding instead of blaming
    time-stretching."""
    from dataclasses import replace

    from roomscope.models.result import PlaybackSpeed

    result = analyze(
        AudioSignal(_played(sweep_signal, 44100), 44100), Reference.from_settings(SWEEP)
    )
    speed = PlaybackSpeed(speed_ratio=0.919, kind=KIND_SAMPLE_RATE, generated_rate_hz=48000)
    edited = replace(
        result, impulse_response=replace(result.impulse_response, playback_speed=speed)
    )
    ids = [f.message_id for f in interpret(edited)]
    assert "measurement.playback_time_stretch" not in ids
    assert "measurement.playback_sample_rate" not in ids
    assert "measurement.direct_sound" in ids


def test_failing_diagnosis_keeps_the_original_error(
    sweep_signal: np.ndarray, monkeypatch: pytest.MonkeyPatch
) -> None:
    import roomscope.core.pipeline as pipeline

    def broken(*_args: object) -> None:
        raise ValueError("diagnosis failed")

    monkeypatch.setattr(pipeline, "diagnose_playback_speed", broken)
    recording = AudioSignal(_played(sweep_signal, 96000)[: 96000 * 3], 96000)
    with pytest.raises(InvalidAudioError) as info:
        analyze(recording, Reference.from_settings(SWEEP))
    assert "However" not in str(info.value)


@pytest.mark.parametrize(("duration_s", "rt60_s", "seed"), [(1.0, 2.5, 6), (3.0, 4.0, 2)])
def test_short_sweep_in_a_reverberant_room_is_not_called_stretched(
    duration_s: float, rt60_s: float, seed: int
) -> None:
    """Review finding: a correctly played 1 s sweep with RT60 2.5 s measured
    about 4 % off and was diagnosed as a time-stretch. These are the worst
    cases of the spread measured for the tolerance."""
    from roomscope.core.pipeline import synthetic_recording
    from tests.conftest import make_rir

    settings = SweepSettings(sample_rate=48000, duration_s=duration_s, post_silence_s=rt60_s)
    ir = make_rir(
        48000,
        rt60_s=rt60_s,
        diffuse_level=0.3 if duration_s > 2 else 0.1,
        length_s=rt60_s * 1.2,
        seed=seed,
    )
    recording = synthetic_recording(settings, ir, noise_rms=3e-4, gain=0.3, seed=seed).samples
    speed = measure_sweep_speed(recording, 48000, settings)
    assert speed is not None and abs(speed - 1.0) > 0.0125  # outside the old 1 % band
    assert diagnose_playback_speed(recording, 48000, settings) is None


def test_the_tolerance_keeps_a_sample_rate_mismatch_detectable() -> None:
    from roomscope.core.playback_speed import speed_tolerance

    assert speed_tolerance(10.0) == pytest.approx(0.0125)
    assert speed_tolerance(3.0) < 0.03  # the +/-3 % stretch tests above still fire
    assert speed_tolerance(1.0) < 1 - 44100 / 48000  # 44.1 vs 48 kHz is named from 1 s


@pytest.mark.parametrize("source", ["standalone", "fake"])
def test_self_played_take_is_never_blamed_on_a_daw(source: str) -> None:
    """RoomScope played the sweep itself, so no DAW can have stretched it.

    A correctly played 3 s sweep in a very reverberant, noisy room leaves a low
    direct-sound confidence, and the speed estimate on such a take is biased
    (about 9 % here). Imported from a file the take would be checked; played
    by Standalone Mode or the demo backend it must not be.
    """
    ir = make_rir(48000, rt60_s=4.0, diffuse_level=0.3, seed=0)
    sweep = measurement_signal(SWEEP)
    wet = fftconvolve(sweep, ir)[: sweep.size + 48000]
    take = wet / np.max(np.abs(wet)) * 0.5 + 0.1 * np.random.default_rng(0).standard_normal(
        wet.size
    )
    result = analyze(AudioSignal(take, 48000, source=source), Reference.from_settings(SWEEP))
    assert result.impulse_response.direct_sound_confidence == "low"
    assert result.impulse_response.playback_speed is None
    assert "speed it was generated at" not in (result.decay.broadband.t30.reason or "")
    ids = [f.message_id for f in interpret(result)]
    assert "measurement.playback_time_stretch" not in ids
    assert "measurement.playback_sample_rate" not in ids


def test_self_played_take_skips_the_check_even_when_stretched(sweep_signal: np.ndarray) -> None:
    """The check is skipped by the take's source, not by its content."""
    stretched = np.asarray(resample_poly(sweep_signal, 103, 100), dtype=np.float64)
    recording = AudioSignal(_played(stretched, 48000), 48000, source="standalone")
    assert (
        analyze(recording, Reference.from_settings(SWEEP)).impulse_response.playback_speed is None
    )


def test_a_wrong_speed_is_the_message_when_no_response_stands_out(
    sweep_signal: np.ndarray,
) -> None:
    """Played at twice the speed, the take seemed to start late; the speed
    is the cause, not a late start."""
    recording = AudioSignal(_played(sweep_signal, 96000)[: 96000 * 3], 96000)
    with pytest.raises(InvalidAudioError) as info:
        analyze(recording, Reference.from_settings(SWEEP))
    assert "after the sweep began" not in str(info.value)
    assert "runs at 200" in str(info.value)


def test_the_speed_explanation_is_shown_in_the_active_language(
    sweep_signal: np.ndarray,
) -> None:
    """The explanation was glued to the error as ". However, " and the
    English speed sentence, so a Chinese user read half the error in
    English."""
    from roomscope.i18n import activate, localize

    # Cut shorter than the reference: refused before the impulse response is
    # located, with the speed appended.
    recording = AudioSignal(_played(sweep_signal, 96000)[: 96000 * 2], 96000)
    activate("zh_CN")
    try:
        with pytest.raises(InvalidAudioError) as info:
            analyze(recording, Reference.from_settings(SWEEP))
        shown = localize(str(info.value))
    finally:
        activate("en")
    assert "However" not in shown and "the sweep" not in shown
    assert "不过，录音中扫频的速度是生成时的 200" in shown
    with pytest.raises(InvalidAudioError, match=r"full sweep\. However, the sweep in the"):
        analyze(recording, Reference.from_settings(SWEEP))
