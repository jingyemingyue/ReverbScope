"""Reference given only as audio (no sweep sidecar): silences, band, inverse."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from scipy.signal import butter, fftconvolve, sosfiltfilt

from reverbscope.core.pipeline import Reference, analyze, synthetic_recording
from reverbscope.core.sweep import excitation_band_hz, generate_ess, measurement_signal
from reverbscope.io.wav import load_reference, write_sweep_file
from reverbscope.models.audio import AudioSignal
from reverbscope.models.configuration import SweepSettings
from reverbscope.models.result import EXCITATION_SOURCE_ESTIMATED, Validity
from tests.conftest import make_rir


def _wav_only_reference(settings: SweepSettings, directory: Path) -> Reference:
    wav, sidecar = write_sweep_file(settings, directory / "sweep.wav")
    sidecar.unlink()  # the user kept only the WAV
    reference = load_reference(wav)
    assert reference.settings is None
    return reference


def test_wav_reference_without_sidecar_matches_sidecar_analysis(
    short_sweep: SweepSettings, tmp_path: Path
) -> None:
    """A4/B4: the file's silences were counted as sweep, so an export of exactly
    the test-file length was rejected and sweep start / valid length were wrong."""
    sr = short_sweep.sample_rate
    reference = _wav_only_reference(short_sweep, tmp_path)
    sidecar = Reference.from_settings(short_sweep)
    file_length = short_sweep.total_samples

    loopback = AudioSignal(measurement_signal(short_sweep), sr)
    ir = make_rir(sr, rt60_s=0.4, diffuse_level=0.01)
    room = synthetic_recording(short_sweep, ir, noise_rms=1e-5).samples
    for recording in (loopback, AudioSignal(room[:file_length], sr)):
        result = analyze(recording, reference)
        imp = result.impulse_response
        assert imp.valid_length_s == pytest.approx(short_sweep.post_silence_s, abs=0.005)
        assert imp.sweep_start_in_recording_s == pytest.approx(short_sweep.pre_silence_s, abs=0.005)
        if recording is loopback:
            # C3: the pre-roll of a pure loopback is exact digital silence, so
            # there is no acoustic noise floor to report (it used to read
            # -6000 dBFS).
            assert result.noise.segment_source is None and result.noise.rms_dbfs is None
            assert any("digital silence" in n for n in result.noise.notes)
        else:
            assert result.noise.segment_source == "pre-sweep"
        assert any("near-silence" in w for w in result.warnings)
        band = imp.excitation_band
        assert band is not None and band.source == EXCITATION_SOURCE_ESTIMATED
        settings_band = excitation_band_hz(short_sweep)
        assert settings_band[0] < band.low_hz < 2.0 * settings_band[0]
        assert settings_band[1] / 2.0 < band.high_hz < settings_band[1]

    room_result = analyze(AudioSignal(room[:file_length], sr), reference)
    sidecar_result = analyze(AudioSignal(room[:file_length], sr), sidecar)
    rt_wav = room_result.decay.broadband.rt60_estimate_s
    rt_sidecar = sidecar_result.decay.broadband.rt60_estimate_s
    assert rt_wav is not None and rt_sidecar is not None
    assert rt_wav == pytest.approx(rt_sidecar, rel=0.1)

    longer = np.concatenate([room, np.random.default_rng(1).normal(0.0, 1e-5, sr // 2)])
    longer = longer[: file_length + sr // 2]
    result = analyze(AudioSignal(longer, sr), reference)
    assert result.impulse_response.valid_length_s == pytest.approx(
        short_sweep.post_silence_s + 0.5, abs=0.005
    )
    assert not any("of decay were recorded" in w for w in result.warnings)


def _room(sr: int) -> np.ndarray:
    return make_rir(sr, rt60_s=0.5, diffuse_level=0.01, length_s=1.0, start_delay_s=0.003)


def test_sweep_only_reference_gives_correct_t30() -> None:
    """A8: with a constant regularisation the spectral inverse left a slowly
    decaying tail and a noise-free 0.5 s room read T30 = 8.09 s (valid)."""
    settings = SweepSettings(duration_s=10.0, pre_silence_s=1.0, post_silence_s=3.0)
    sr = settings.sample_rate
    rec = np.asarray(fftconvolve(measurement_signal(settings), _room(sr)))
    result = analyze(AudioSignal(rec, sr), Reference.from_signal(generate_ess(settings), sr))
    t30 = result.decay.broadband.t30
    assert t30.validity is Validity.VALID
    assert t30.seconds == pytest.approx(0.5, rel=0.05)


def test_full_file_reference_with_subsonic_rumble_gives_correct_t30() -> None:
    """A8: -40 dBFS 3-12 Hz rumble was boosted by the inverse (T30 of 22-32 s)."""
    settings = SweepSettings(duration_s=5.0, pre_silence_s=1.0, post_silence_s=3.0)
    sr = settings.sample_rate
    signal = measurement_signal(settings)
    clean = np.concatenate([np.asarray(fftconvolve(signal, _room(sr))), np.zeros(sr)])
    rng = np.random.default_rng(3)
    sos = butter(2, [3.0 / (sr / 2), 12.0 / (sr / 2)], "bandpass", output="sos")
    rumble = sosfiltfilt(sos, rng.normal(0.0, 1.0, clean.shape[0]))
    rumble *= 10 ** (-40 / 20) * np.sqrt(0.5) / np.sqrt(np.mean(rumble**2))
    result = analyze(AudioSignal(clean + rumble, sr), Reference.from_signal(signal, sr))
    t30 = result.decay.broadband.t30
    assert t30.validity is Validity.VALID
    assert t30.seconds == pytest.approx(0.5, rel=0.05)
    assert result.decay.broadband.peak_to_noise_db > 80.0
