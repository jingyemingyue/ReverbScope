"""Pipeline-level checks of the recording itself: clipping, aliased distortion
and the choice of the quiet segment (repeated passes, digital silence)."""

from __future__ import annotations

import numpy as np
import pytest
from scipy.signal import fftconvolve

from roomscope.core.noise import NOISE_FLOOR_DBFS
from roomscope.core.pipeline import Reference, analyze, synthetic_recording
from roomscope.core.sweep import measurement_signal
from roomscope.interpretation import interpret
from roomscope.models.audio import AudioSignal
from roomscope.models.configuration import AnalysisSettings, SweepSettings
from tests.conftest import make_rir


def _room_recording(
    settings: SweepSettings,
    *,
    gain: float = 0.3,
    noise_rms: float = 3e-4,
    rt60_s: float = 0.4,
    seed: int = 0,
) -> np.ndarray:
    ir = make_rir(settings.sample_rate, rt60_s=rt60_s, diffuse_level=0.02, length_s=1.0, seed=seed)
    return synthetic_recording(settings, ir, noise_rms=noise_rms, gain=gain, seed=seed).samples


def _quantise(x: np.ndarray, bits: int = 24) -> np.ndarray:
    step = 2.0 ** -(bits - 1)
    return np.asarray(np.round(np.clip(x, -1.0, 1.0 - step) / step) * step)


def test_clipped_then_attenuated_recording_is_warned(short_sweep: SweepSettings) -> None:
    """C22: the recording clipped at the converter and was exported 0.5 dB
    below full scale; the absolute 0.999 threshold saw nothing."""
    sr = short_sweep.sample_rate
    samples = _room_recording(short_sweep, gain=1.0, noise_rms=1e-5)
    clipped = np.clip(samples * 4.0 / np.max(np.abs(samples)), -1.0, 1.0) * 10 ** (-0.5 / 20)
    result = analyze(AudioSignal(_quantise(clipped), sr), Reference.from_settings(short_sweep))
    assert result.clipping is not None and result.clipping.clipped
    assert result.clipping.peak_dbfs == pytest.approx(-0.5, abs=0.1)
    warning = next(w for w in result.warnings if "clipping" in w)
    assert "flat-topped" in warning and "below full scale" in warning
    assert any(f.message.startswith("The recording clips") for f in interpret(result))
    assert "clips" in (result.decay.broadband.t30.reason or "")


def test_unclipped_recording_normalised_to_full_scale_is_not_warned(
    short_sweep: SweepSettings,
) -> None:
    """A6: an unclipped recording normalised to 0 dBFS was reported as
    'probable clipping' (205 samples at or above 0.999)."""
    sr = short_sweep.sample_rate
    samples = _room_recording(short_sweep, gain=1.0, noise_rms=1e-5)
    normalised = samples / np.max(np.abs(samples))
    result = analyze(AudioSignal(_quantise(normalised), sr), Reference.from_settings(short_sweep))
    assert result.clipping is not None and not result.clipping.clipped
    assert result.clipping.peak_dbfs == pytest.approx(0.0, abs=0.01)
    assert not any("clipping" in w for w in result.warnings)


@pytest.mark.parametrize("rate", [96000, 192000])
def test_probe_reports_that_nothing_can_fold_back_at_high_rates(rate: int) -> None:
    """At 88.2 kHz and above, the harmonics of a 20 kHz sweep fold back above
    the swept range (or not at all), where the inverse filter rejects them."""
    settings = SweepSettings(
        sample_rate=rate, duration_s=1.5, pre_silence_s=1.0, post_silence_s=1.5
    )
    excitation = measurement_signal(settings)
    clipped = np.clip(excitation * 2.0, -settings.amplitude, settings.amplitude)
    ir = make_rir(rate, rt60_s=0.4, diffuse_level=0.02 * np.sqrt(48000 / rate), length_s=1.0)
    rng = np.random.default_rng(0)
    samples = np.asarray(fftconvolve(clipped, ir)) * 0.5
    result = analyze(
        AudioSignal(samples + rng.normal(0.0, 1e-5, samples.shape[0]), rate),
        Reference.from_settings(settings),
    )
    aliased = result.impulse_response.aliased_distortion
    assert aliased and not any(a.significant for a in aliased)
    assert all(a.level_db is None and a.reason for a in aliased)
    assert any("fold" in (a.reason or "") for a in aliased)


def test_pre_roll_of_digital_silence_is_not_a_noise_level() -> None:
    """C3: a DAW export that starts before the recorded region begins with
    digital zeros, which were reported as '-6000.0 dBFS RMS'."""
    settings = SweepSettings(duration_s=2.0, pre_silence_s=1.0, post_silence_s=4.5)
    sr = settings.sample_rate
    samples = _room_recording(settings, noise_rms=3e-4)
    samples[: round(0.95 * sr)] = 0.0
    result = analyze(AudioSignal(_quantise(samples), sr), Reference.from_settings(settings))
    noise = result.noise
    # 0.05 s are skipped at the start, so what is left of the pre-sweep
    # segment after the zeros is too short; the tail is used instead.
    assert noise.segment_source == "tail"
    assert noise.rms_dbfs is not None and noise.rms_dbfs > NOISE_FLOOR_DBFS
    assert any("digital zeros" in n or "digital silence" in n for n in noise.notes)
    assert all(level is None or level > NOISE_FLOOR_DBFS for _, level in noise.band_levels_dbfs)
    assert "-6000" not in str(result.to_dict(include_curves=False))
    assert not any("-6000" in f.message for f in interpret(result))


def _passes(settings: SweepSettings, gains: tuple[float, ...], noise_rms: float) -> np.ndarray:
    ir = make_rir(settings.sample_rate, rt60_s=0.4, diffuse_level=0.02, length_s=1.0)
    parts = [np.asarray(fftconvolve(measurement_signal(settings), ir)) * gain for gain in gains]
    recording = np.concatenate(parts)
    rng = np.random.default_rng(3)
    return recording + rng.normal(0.0, noise_rms, recording.shape[0])


@pytest.mark.parametrize("gains", [(0.1, 0.3), (0.25, 0.25, 0.25)])
def test_noise_of_a_multi_pass_recording_is_the_real_noise(
    short_sweep: SweepSettings, gains: tuple[float, ...]
) -> None:
    """E2: with a second (louder) take in the same file, the 'quiet segment'
    contained the first sweep and the noise floor was reported as -31.8 dBFS
    instead of -75 dBFS."""
    sr = short_sweep.sample_rate
    noise_rms = 10 ** (-75 / 20) / np.sqrt(2)
    result = analyze(
        AudioSignal(_passes(short_sweep, gains, noise_rms), sr),
        Reference.from_settings(short_sweep),
    )
    assert result.impulse_response.sweep_passes == len(gains)
    assert result.noise.rms_dbfs == pytest.approx(-75.0, abs=1.5)
    assert result.noise.segment_source in ("pre-sweep", "tail")


def test_looped_sweep_without_silence_has_no_quiet_segment() -> None:
    """E2: a looped sweep with no silence gave a 'background noise' level that
    was the sweep itself (-23.8 dBFS), with no warning."""
    settings = SweepSettings(duration_s=1.0, pre_silence_s=0.0, post_silence_s=0.6)
    sr = settings.sample_rate
    ir = make_rir(sr, rt60_s=0.3, diffuse_level=0.02, length_s=0.5)
    one = np.asarray(fftconvolve(measurement_signal(settings), ir)) * 0.3
    rng = np.random.default_rng(1)
    recording = np.concatenate([one, one, one])
    recording = recording + rng.normal(0.0, 1e-4, recording.shape[0])
    result = analyze(
        AudioSignal(recording, sr),
        Reference.from_settings(settings),
        AnalysisSettings(noise_min_segment_s=0.3),
    )
    assert result.impulse_response.sweep_passes == 3
    assert result.noise.segment_source is None and result.noise.rms_dbfs is None
    assert any("No quiet segment" in n for n in result.noise.notes)
    assert not any(f.topic == "noise" for f in interpret(result))


@pytest.mark.parametrize("weak_gain", [0.01, 0.003])
def test_weaker_earlier_pass_is_not_measured_as_background_noise(
    short_sweep: SweepSettings, weak_gain: float
) -> None:
    """E2: a pass more than 20 dB below the analysed one is not detected as a
    pass at all, so it stays inside the pre-sweep segment; the quietness check
    of the segment content is what keeps it out of the noise level."""
    sr = short_sweep.sample_rate
    ir = make_rir(sr, rt60_s=0.4, diffuse_level=0.02, length_s=1.0)
    one = np.asarray(fftconvolve(measurement_signal(short_sweep), ir))
    rng = np.random.default_rng(5)
    recording = np.concatenate([one * weak_gain, one * 0.3])
    recording = recording + rng.normal(0.0, 10 ** (-75 / 20) / np.sqrt(2), recording.shape[0])
    result = analyze(AudioSignal(recording, sr), Reference.from_settings(short_sweep))
    assert result.impulse_response.sweep_passes == 1  # the weak pass is not detected
    assert result.noise.segment_source == "pre-sweep"
    assert result.noise.rms_dbfs == pytest.approx(-75.0, abs=1.0)
    assert any("above its quietest blocks" in n for n in result.noise.notes)


def test_device_buffer_problems_reach_the_result_and_a_finding(
    short_sweep: SweepSettings,
) -> None:
    """A take whose device reported an input overflow is analysed, but the
    result and the findings say so (the log line alone reached no GUI user)."""
    sr = short_sweep.sample_rate
    samples = _room_recording(short_sweep)
    warning = (
        "the audio device reported 1 buffer problem(s) during the take (input overflow); "
        "the recording may contain dropouts"
    )
    take = AudioSignal(samples, sr, source="standalone", device_warnings=(warning,))
    result = analyze(take, Reference.from_settings(short_sweep))
    assert warning in result.warnings
    dropouts = [f for f in interpret(result) if f.message_id == "measurement.dropouts"]
    assert len(dropouts) == 1 and dropouts[0].evidence == {"warning": warning}
    clean = analyze(AudioSignal(samples, sr), Reference.from_settings(short_sweep))
    assert not any(f.message_id == "measurement.dropouts" for f in interpret(clean))


def test_the_test_signal_exported_instead_of_the_microphone_is_flagged(
    short_sweep: SweepSettings,
) -> None:
    """Review finding: the sweep track analysed as the recording gave a
    confident, room-like result (T30 of a few hundredths of a second) whose
    only hint was a note about digital silence."""
    sr = short_sweep.sample_rate
    sweep_only = measurement_signal(short_sweep)
    result = analyze(AudioSignal(sweep_only, sr), Reference.from_settings(short_sweep))
    ids = [f.message_id for f in interpret(result)]
    assert "measurement.digital_silence" in ids
    # A microphone take (room noise before the sweep) is not flagged.
    take = analyze(
        AudioSignal(_room_recording(short_sweep), sr), Reference.from_settings(short_sweep)
    )
    assert "measurement.digital_silence" not in [f.message_id for f in interpret(take)]
