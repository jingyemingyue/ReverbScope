"""End-to-end round trips: generate sweep -> synthetic room -> analyse."""

from __future__ import annotations

import numpy as np
import pytest
from scipy.signal import fftconvolve

from reverbscope.core.pipeline import Reference, analyze, synthetic_recording
from reverbscope.core.sweep import measurement_signal, reference_pulse
from reverbscope.models.audio import AudioSignal
from reverbscope.models.configuration import (
    SUPPORTED_SAMPLE_RATES,
    AnalysisSettings,
    SweepSettings,
)
from reverbscope.models.result import Validity
from tests.conftest import alias_free_distortion, fr_median_db, make_rir


def test_round_trip_recovers_rt60_reflection_and_noise(short_sweep: SweepSettings) -> None:
    sr = short_sweep.sample_rate
    rt60 = 0.45
    ir = make_rir(sr, rt60_s=rt60, reflections=[(0.018, 10 ** (-9 / 20))], diffuse_level=0.01)
    rec = synthetic_recording(short_sweep, ir, noise_rms=3e-5)
    result = analyze(rec, Reference.from_settings(short_sweep))

    # The direct sound (gain 1) peaks like the loopback pulse; levels are read
    # from the frequency response, whose in-band loopback level is 0 dB.
    loopback_peak = float(np.max(reference_pulse(short_sweep)))
    assert result.impulse_response.peak_value == pytest.approx(loopback_peak, rel=0.02)
    assert result.impulse_response.direct_sound_confidence == "high"
    broadband = result.decay.broadband
    assert broadband.t30.validity is Validity.VALID
    assert broadband.rt60_estimate_s == pytest.approx(rt60, rel=0.1)
    mid = [b for b in result.decay.bands if b.center_hz in (500.0, 1000.0, 2000.0)]
    for band in mid:
        assert band.rt60_estimate_s == pytest.approx(rt60, rel=0.15)
    strong = [r for r in result.reflections.reflections if r.relative_db > -12.0]
    assert len(strong) == 1
    assert strong[0].delay_ms == pytest.approx(18.0, abs=0.2)
    # D5: the "18 ms at about -9 dB" claim was never asserted end to end.
    assert strong[0].relative_db == pytest.approx(-9.0, abs=1.0)
    assert result.reflections.analysed_window_ms == pytest.approx((0.8, 80.0))
    assert not result.reflections.window_truncated
    assert result.noise.segment_source == "pre-sweep"
    assert result.noise.rms_dbfs == pytest.approx(20 * np.log10(3e-5 * np.sqrt(2)), abs=0.5)
    assert not any(h.detected for h in result.noise.hum)


@pytest.mark.parametrize("recording_rate", [44100, 96000])
def test_recording_at_other_sample_rate_regenerates_reference(
    short_sweep: SweepSettings, recording_rate: int
) -> None:
    played = short_sweep.with_sample_rate(recording_rate)  # what the DAW effectively played
    ir = make_rir(recording_rate, rt60_s=0.4, diffuse_level=0.01)
    rec = synthetic_recording(played, ir, noise_rms=3e-5)
    result = analyze(rec, Reference.from_settings(short_sweep))
    assert result.sample_rate == recording_rate
    assert any("regenerated" in w for w in result.warnings)
    assert result.decay.broadband.rt60_estimate_s == pytest.approx(0.4, rel=0.1)


def test_stereo_recording_channel_selection(short_sweep: SweepSettings) -> None:
    sr = short_sweep.sample_rate
    ir = make_rir(sr, rt60_s=0.3, diffuse_level=0.01)
    mono = synthetic_recording(short_sweep, ir, noise_rms=1e-5).samples
    stereo = AudioSignal(np.stack([mono * 0.01, mono], axis=1), sr)
    auto = analyze(stereo, Reference.from_settings(short_sweep))
    assert auto.analysis_settings["channel_analysed"] == 1
    assert any("channels" in w for w in auto.warnings)
    explicit = analyze(stereo, Reference.from_settings(short_sweep), AnalysisSettings(channel=0))
    assert explicit.analysis_settings["channel_analysed"] == 0
    loopback_peak = float(np.max(reference_pulse(short_sweep)))
    assert explicit.impulse_response.peak_value == pytest.approx(0.01 * loopback_peak, rel=0.05)


def test_reference_from_signal_without_sweep_definition(short_sweep: SweepSettings) -> None:
    sr = short_sweep.sample_rate
    ir = make_rir(sr, rt60_s=0.4, diffuse_level=0.01)
    rec = synthetic_recording(short_sweep, ir, noise_rms=3e-5)
    reference = Reference.from_signal(measurement_signal(short_sweep), sr)
    result = analyze(rec, reference)
    assert any("spectral division" in w for w in result.warnings)
    # Same level as with the analytic inverse: the in-band responses agree.
    analytic = analyze(rec, Reference.from_settings(short_sweep))
    assert fr_median_db(result) == pytest.approx(fr_median_db(analytic), abs=0.1)
    assert result.impulse_response.sweep_start_in_recording_s == pytest.approx(
        short_sweep.pre_silence_s, abs=0.005
    )
    assert result.decay.broadband.rt60_estimate_s == pytest.approx(0.4, rel=0.1)


def test_reference_signal_at_other_rate_is_resampled(short_sweep: SweepSettings) -> None:
    sr = short_sweep.sample_rate
    ir = make_rir(sr, rt60_s=0.4, diffuse_level=0.01)
    rec = synthetic_recording(short_sweep, ir, noise_rms=3e-5)
    other = short_sweep.with_sample_rate(96000)
    reference = Reference.from_signal(measurement_signal(other), 96000)
    result = analyze(rec, reference)
    assert any("resampled" in w for w in result.warnings)
    assert result.decay.broadband.rt60_estimate_s == pytest.approx(0.4, rel=0.15)


def test_noisy_measurement_reports_insufficient_range(short_sweep: SweepSettings) -> None:
    sr = short_sweep.sample_rate
    ir = make_rir(sr, rt60_s=0.5, diffuse_level=0.01)
    rec = synthetic_recording(short_sweep, ir, noise_rms=0.02)
    result = analyze(rec, Reference.from_settings(short_sweep))
    broadband = result.decay.broadband
    assert broadband.t30.validity is Validity.INSUFFICIENT_RANGE
    assert broadband.t30.seconds is None
    assert "Insufficient decay range" in (broadband.t30.reason or "")


def test_loudspeaker_distortion_is_separated_from_linear_response(
    short_sweep: SweepSettings,
) -> None:
    """A12: the distortion was applied in the digital domain at the sample
    rate, so it aliased; a loudspeaker distorts in the analogue domain, where
    the harmonics above the Nyquist frequency are simply lost."""
    sr = short_sweep.sample_rate
    ir = make_rir(sr, rt60_s=0.4, diffuse_level=0.01)
    excitation = measurement_signal(short_sweep)
    distorted = alias_free_distortion(excitation, short_sweep.amplitude, h2=0.0125, h3=0.0008)
    rec = AudioSignal(fftconvolve(distorted, ir)[: excitation.shape[0] + ir.shape[0]], sr)
    result = analyze(rec, Reference.from_settings(short_sweep))
    margin = result.impulse_response.pre_peak_margin_db
    assert margin is not None and margin > 15.0
    loopback_peak = float(np.max(reference_pulse(short_sweep)))
    assert result.impulse_response.peak_value == pytest.approx(loopback_peak, rel=0.1)
    levels = {h.order: h.level_db for h in result.impulse_response.harmonic_distortion}
    assert levels[2] is not None and levels[2] == pytest.approx(20 * np.log10(0.0125), abs=1.0)
    assert levels[3] is None  # 0.0008 stays below the detection margin
    # Nothing folded back, so the decay is measured as usual.
    assert not any(a.significant for a in result.impulse_response.aliased_distortion)
    assert result.decay.broadband.rt60_estimate_s == pytest.approx(0.4, rel=0.1)


def test_digital_clipping_before_the_room_is_detected(short_sweep: SweepSettings) -> None:
    """A6: a playback bus clipped 6 dB over full scale folds the harmonics above
    the Nyquist frequency back onto falling trajectories. They deconvolve
    *after* the direct sound and gave a valid broadband T30 of 8.7 s with no
    warning; the recording itself does not clip, so the flat-top check cannot
    see it either."""
    sr = short_sweep.sample_rate
    ir = make_rir(sr, rt60_s=0.4, diffuse_level=0.02, length_s=1.0)
    excitation = measurement_signal(short_sweep)
    clipped = np.clip(excitation * 2.0, -short_sweep.amplitude, short_sweep.amplitude)
    rng = np.random.default_rng(0)
    samples = np.asarray(fftconvolve(clipped, ir)) * 0.5
    samples = samples + rng.normal(0.0, 1e-5, samples.shape[0])
    result = analyze(AudioSignal(samples, sr), Reference.from_settings(short_sweep))

    assert result.clipping is not None and not result.clipping.clipped
    aliased = {a.order: a for a in result.impulse_response.aliased_distortion}
    assert aliased[3].significant
    # A symmetric clip 6 dB over full scale has H3 about -13 dB re the fundamental.
    assert aliased[3].level_db == pytest.approx(-12.9, abs=2.0)
    assert any("folded back" in w for w in result.warnings)
    metrics = [
        m
        for band in (result.decay.broadband, *result.decay.bands)
        for m in (band.edt, band.t20, band.t30)
    ]
    assert not any(m.validity is Validity.VALID for m in metrics)
    assert all(band.rt60_estimate_s is None for band in result.decay.bands)


@pytest.mark.parametrize("rate", SUPPORTED_SAMPLE_RATES)
def test_round_trip_recovers_the_decay_at_every_supported_sample_rate(rate: int) -> None:
    """A12: only 44.1 and 96 kHz were covered by a round trip, and the band
    filters were tested at 48 kHz only."""
    settings = SweepSettings(
        sample_rate=rate, duration_s=1.5, pre_silence_s=1.0, post_silence_s=1.5
    )
    rt60 = 0.4
    ir = make_rir(rate, rt60_s=rt60, diffuse_level=0.02, length_s=1.0)
    result = analyze(
        synthetic_recording(settings, ir, noise_rms=1e-5), Reference.from_settings(settings)
    )
    assert result.sample_rate == rate
    assert result.impulse_response.direct_sound_confidence == "high"
    assert result.decay.broadband.rt60_estimate_s == pytest.approx(rt60, rel=0.15)
    bands = {band.band_label: band for band in result.decay.bands}
    # Including the lowest band at the highest rate (B*T and the filter design
    # are hardest there).
    for label in ("63 Hz", "1 kHz", "8 kHz"):
        band = bands[label]
        assert band.t30.validity is Validity.VALID, (rate, label, band.t30.reason)
        assert band.rt60_estimate_s == pytest.approx(rt60, rel=0.25), (rate, label)
    assert result.noise.rms_dbfs == pytest.approx(20 * np.log10(1e-5 * np.sqrt(2)), abs=1.0)
