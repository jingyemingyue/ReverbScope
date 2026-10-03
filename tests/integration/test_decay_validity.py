"""Pipeline-level decay validity: pre-delay independence, direct-sound
dominance, unverified or clipped recordings, unexcited bands, hum floors."""

from __future__ import annotations

import numpy as np
import pytest
from scipy.signal import fftconvolve, resample_poly

from reverbscope.core.filters import iec_band
from reverbscope.core.pipeline import Reference, analyze, synthetic_recording
from reverbscope.core.sweep import excitation_band_hz, measurement_signal
from reverbscope.interpretation import interpret
from reverbscope.models.audio import AudioSignal
from reverbscope.models.configuration import DEFAULT_OCTAVE_BANDS_HZ, AnalysisSettings, SweepSettings
from reverbscope.models.result import AnalysisResult, BandDecay, DecayMetric, Validity
from tests.conftest import make_rir


def _bands(result: AnalysisResult) -> tuple[BandDecay, ...]:
    return (result.decay.broadband, *result.decay.bands)


def _all_metrics(result: AnalysisResult) -> list[DecayMetric]:
    return [m for b in _bands(result) for m in (b.edt, b.t20, b.t30)]


@pytest.mark.parametrize("diffuse", [0.01, 0.03])
def test_decay_metrics_do_not_depend_on_the_display_pre_delay(
    short_sweep: SweepSettings, diffuse: float
) -> None:
    """A7/B1: band EDT changed by up to 4x and T30 by about 10 % between
    ir_pre_delay_ms = 5 and 200 (the band filters ran on the cut IR)."""
    sr = short_sweep.sample_rate
    ir = make_rir(sr, rt60_s=0.5, diffuse_level=diffuse, length_s=1.0, start_delay_s=0.003)
    rec = synthetic_recording(short_sweep, ir, noise_rms=1e-5)
    results = [
        analyze(rec, Reference.from_settings(short_sweep), AnalysisSettings(ir_pre_delay_ms=pd))
        for pd in (5.0, 50.0, 200.0)
    ]
    reference = _bands(results[0])
    for other in results[1:]:
        for a, b in zip(reference, _bands(other), strict=True):
            for ma, mb in zip((a.edt, a.t20, a.t30), (b.edt, b.t20, b.t30), strict=True):
                assert ma.validity is mb.validity, (a.band_label, ma.name)
                if ma.seconds is not None:
                    assert mb.seconds == pytest.approx(ma.seconds, rel=0.02)
            assert b.edc_time_s[0] == pytest.approx(a.edc_time_s[0])
    if diffuse == 0.03:  # reverberant position (DRR about -2 dB): EDT is kept everywhere
        assert all(b.edt.validity is Validity.VALID for b in reference)
        assert reference[0].edt.seconds == pytest.approx(0.5, rel=0.05)
        # Band EDTs rest on only 10 dB of a band-limited noise decay; loose check.
        for band in reference[1:]:
            assert band.edt.seconds == pytest.approx(0.5, rel=0.6), band.band_label
    else:  # DRR +7.6 dB: the direct sound dominates the first 10 dB
        assert all(b.edt.validity is Validity.UNRELIABLE for b in reference)
    for band in reference:
        assert band.t30.validity is Validity.VALID, band.band_label
        assert band.t30.seconds == pytest.approx(0.5, rel=0.15), band.band_label


def test_strong_direct_sound_gives_no_valid_edt_above_1_5_t30(short_sweep: SweepSettings) -> None:
    """B1: DRR +11.6 dB gave broadband EDT = 0.43 s (valid) with T30 = 0.20 s."""
    sr = short_sweep.sample_rate
    ir = make_rir(sr, rt60_s=0.2, diffuse_level=0.01, length_s=1.0)
    result = analyze(
        synthetic_recording(short_sweep, ir, noise_rms=3e-5), Reference.from_settings(short_sweep)
    )
    assert result.decay.broadband.edt.validity is not Validity.VALID
    assert result.decay.broadband.t30.seconds == pytest.approx(0.2, rel=0.05)
    for band in _bands(result):
        if band.edt.validity is Validity.VALID:
            assert band.edt.seconds is not None and band.t30.seconds is not None
            assert band.edt.seconds <= 1.5 * band.t30.seconds, band.band_label


def _assert_nothing_valid(result: AnalysisResult) -> None:
    assert not any(m.validity is Validity.VALID for m in _all_metrics(result))
    assert all(b.rt60_estimate_s is None for b in _bands(result))
    assert any("all decay metrics are marked unreliable" in w for w in result.warnings)
    assert not any(f.topic == "reverberation" for f in interpret(result))


def _room(sr: int) -> np.ndarray:
    return make_rir(sr, rt60_s=0.5, diffuse_level=0.01, length_s=1.0)


def test_recording_of_an_impulse_has_no_valid_decay_metric(short_sweep: SweepSettings) -> None:
    """A5: a clap-like recording without the sweep gave EDT = 9.8 s (valid) and
    the finding 'estimated RT60 9.93 s'."""
    sr = short_sweep.sample_rate
    rng = np.random.default_rng(0)
    y = rng.normal(0.0, 1e-5, 6 * sr)
    ir = _room(sr)
    y[3 * sr : 3 * sr + ir.shape[0]] += 0.3 * ir
    result = analyze(AudioSignal(y, sr), Reference.from_settings(short_sweep))
    assert result.impulse_response.direct_sound_confidence == "low"
    _assert_nothing_valid(result)
    reason = result.decay.broadband.t30.reason or result.decay.broadband.edt.reason or ""
    assert "confidence is low" in reason


def test_recording_of_another_sweep_has_no_valid_decay_metric(short_sweep: SweepSettings) -> None:
    """A5: a recording of a different sweep kept 8 of 8 band T30 values valid."""
    sr = short_sweep.sample_rate
    other = SweepSettings(
        sample_rate=sr, duration_s=3.0, start_hz=40.0, end_hz=16000.0, post_silence_s=1.5
    )
    rec = synthetic_recording(other, _room(sr), noise_rms=1e-5)
    result = analyze(rec, Reference.from_settings(short_sweep))
    assert result.impulse_response.direct_sound_confidence == "low"
    _assert_nothing_valid(result)


def test_playback_rate_mismatch_has_no_valid_decay_metric(short_sweep: SweepSettings) -> None:
    """A5: a 48 kHz file played at 44.1 kHz kept band T30 values of 2.8-20 s valid."""
    sr = short_sweep.sample_rate
    played = resample_poly(measurement_signal(short_sweep), 160, 147)
    rng = np.random.default_rng(1)
    rec = np.asarray(fftconvolve(played, _room(sr)))
    rec = rec + rng.normal(0.0, 1e-5, rec.shape[0])
    result = analyze(AudioSignal(rec, sr), Reference.from_settings(short_sweep))
    assert result.impulse_response.direct_sound_confidence == "low"
    _assert_nothing_valid(result)


def test_clipped_recording_has_no_valid_decay_metric(short_sweep: SweepSettings) -> None:
    """A5: a recording clipped 6 dB over full scale gave T30 = 4.6 s (valid)."""
    sr = short_sweep.sample_rate
    rec = synthetic_recording(short_sweep, _room(sr), noise_rms=1e-5).samples
    clipped = np.clip(rec * 2.0 / np.max(np.abs(rec)), -1.0, 1.0)
    result = analyze(AudioSignal(clipped, sr), Reference.from_settings(short_sweep))
    assert result.impulse_response.direct_sound_confidence == "high"
    _assert_nothing_valid(result)
    assert "clips" in (result.decay.broadband.t30.reason or "")


def test_narrow_sweep_withholds_unexcited_bands() -> None:
    """A2/B3: a 250 Hz-5 kHz sweep reported 63 Hz T30 = 0.54 s (valid) for a
    room whose 63 Hz mode decays in 2 s, and 8 kHz values from leakage."""
    settings = SweepSettings(
        duration_s=2.0, start_hz=250.0, end_hz=5000.0, pre_silence_s=1.0, post_silence_s=2.0
    )
    sr = settings.sample_rate
    ir = make_rir(sr, rt60_s=0.5, diffuse_level=0.01, length_s=2.0)
    t = np.arange(ir.shape[0]) / sr
    ir = ir + 0.05 * np.sin(2 * np.pi * 63.0 * t) * np.exp(-6.9078 * t / 2.0)
    result = analyze(
        synthetic_recording(settings, ir, noise_rms=1e-5), Reference.from_settings(settings)
    )
    by_label = {b.band_label: b for b in result.decay.bands}
    for label in ("63 Hz", "125 Hz", "8 kHz"):
        band = by_label[label]
        assert all(
            m.validity is Validity.OUTSIDE_EXCITATION for m in (band.edt, band.t20, band.t30)
        )
        assert band.rt60_estimate_s is None and band.peak_to_noise_db is None
    for band in result.decay.bands:
        excitation = result.excitation_band
        assert excitation is not None
        if not excitation.contains(band.low_hz or 0.0, band.high_hz or 0.0):
            assert band.t30.validity is Validity.OUTSIDE_EXCITATION
    assert by_label["1 kHz"].t30.validity is Validity.VALID
    warning = next(w for w in result.warnings if "excitation range" in w)
    for label in ("63 Hz", "125 Hz", "8 kHz"):
        assert label in warning


def test_default_sweep_excites_every_default_band(short_sweep: SweepSettings) -> None:
    """A2/B3: the withholding rule must not touch the default configuration."""
    for settings in (SweepSettings(), short_sweep, SweepSettings(duration_s=0.5)):
        low, high = excitation_band_hz(settings)
        for center in DEFAULT_OCTAVE_BANDS_HZ:
            band = iec_band(center)
            assert low <= band.low_hz and band.high_hz <= high, (settings.duration_s, center)
    sr = short_sweep.sample_rate
    ir = make_rir(sr, rt60_s=0.5, diffuse_level=0.03, length_s=1.2)
    result = analyze(
        synthetic_recording(short_sweep, ir, noise_rms=1e-5), Reference.from_settings(short_sweep)
    )
    assert len(result.decay.bands) == len(DEFAULT_OCTAVE_BANDS_HZ)
    for band in result.decay.bands:
        assert band.t30.validity is Validity.VALID, band.band_label
    assert not any("excitation range" in w for w in result.warnings)


@pytest.mark.parametrize("rate", [48000, 192000])
def test_mains_hum_floor_gives_no_runaway_band_values(rate: int) -> None:
    """E1: with five 50 Hz harmonics at -60 dBFS the 63 Hz band reported
    T30 = 13.5 s (valid, 27 x the true value) at 192 kHz."""
    settings = SweepSettings(
        sample_rate=rate, duration_s=3.0, pre_silence_s=1.0, post_silence_s=2.0
    )
    ir = make_rir(
        rate, rt60_s=0.5, length_s=1.5, diffuse_level=0.02 * np.sqrt(48000 / rate), seed=2
    )
    rec = np.asarray(fftconvolve(measurement_signal(settings), ir)) * 0.5
    t = np.arange(rec.shape[0]) / rate
    rng = np.random.default_rng(102)
    rec = rec + rng.normal(0.0, 10 ** (-85 / 20), rec.shape[0])
    phases = rng.uniform(0.0, 2 * np.pi, 6)
    for k in range(1, 6):
        rec = rec + 10 ** (-60 / 20) * np.sin(2 * np.pi * 50.0 * k * t + phases[k])
    result = analyze(AudioSignal(rec, rate), Reference.from_settings(settings))
    # Low bands scatter statistically (B*T of about 20 at 63 Hz); a factor of
    # 1.5 still separates that from a runaway truncation.
    for band in _bands(result):
        for metric in (band.t20, band.t30):
            if metric.validity is Validity.VALID:
                assert metric.seconds is not None
                assert 0.5 / 1.5 < metric.seconds < 0.5 * 1.5, (band.band_label, metric)
        if band.rt60_estimate_s is not None:
            assert band.rt60_estimate_s == pytest.approx(0.5, rel=0.25), band.band_label
