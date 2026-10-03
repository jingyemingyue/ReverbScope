from __future__ import annotations

import numpy as np
import pytest

from roomscope.core.filters import (
    apply_bandpass,
    band_fits,
    band_level_samples,
    bandpass_sos,
    exact_mid_band_hz,
    fractional_octave_band,
    fractional_octave_smooth,
    iec_band,
    nearest_band_index,
    settling_samples,
)
from roomscope.errors import ConfigurationError


def test_octave_band_edges() -> None:
    # Base-10 ratio G = 10^(3/10) (IEC 61260-1:2014): edges f * G^(+-1/(2b)).
    # (The previous values 707.107 / 1414.214 were base-2, which the standard
    # no longer specifies.)
    band = fractional_octave_band(1000.0, 1)
    assert band.low_hz == pytest.approx(1000.0 * 10 ** (-0.15), rel=1e-9)
    assert band.low_hz == pytest.approx(707.946, rel=1e-5)
    assert band.high_hz == pytest.approx(1412.538, rel=1e-5)
    assert band.bandwidth_hz == pytest.approx(704.592, rel=1e-5)
    assert band.label == "1 kHz"
    third = fractional_octave_band(1000.0, 3)
    assert third.low_hz == pytest.approx(891.251, rel=1e-5)
    assert third.high_hz == pytest.approx(1122.018, rel=1e-5)
    assert fractional_octave_band(63.0).label == "63 Hz"
    # An arbitrary centre is kept as it is (resonance candidates).
    assert fractional_octave_band(241.0, 3).center_hz == 241.0


def test_iec_bands_use_exact_base10_mid_band_frequencies() -> None:
    """A9: exact mid-band frequencies f_m = 1000 * G^(x/b) with nominal labels."""
    g = 10**0.3
    band = iec_band(63.0)
    assert band.center_hz == pytest.approx(1000.0 * g**-4, rel=1e-12)
    assert band.center_hz == pytest.approx(63.0957, rel=1e-5)
    assert band.low_hz == pytest.approx(44.6684, rel=1e-5)
    assert band.high_hz == pytest.approx(89.1251, rel=1e-5)
    assert band.label == "63 Hz" and band.label_hz == 63.0 and band.nominal_hz == 63.0
    assert iec_band(1000.0).center_hz == 1000.0
    assert iec_band(125.0).center_hz == pytest.approx(125.893, rel=1e-5)
    assert iec_band(8000.0).center_hz == pytest.approx(7943.28, rel=1e-5)
    assert iec_band(16000.0).label == "16 kHz"
    third = iec_band(160.0, 3)
    assert third.center_hz == pytest.approx(158.489, rel=1e-5)
    assert third.high_hz / third.low_hz == pytest.approx(g ** (1 / 3), rel=1e-12)
    # Even bandwidth designators: f_m = 1000 * G^((2x+1)/(2b)); none sits at 1 kHz.
    assert exact_mid_band_hz(0, 6) == pytest.approx(1000.0 * g ** (1 / 12), rel=1e-12)
    assert iec_band(1060.0, 6).center_hz == pytest.approx(1059.254, rel=1e-5)
    assert nearest_band_index(1000.0, 1) == 0 and nearest_band_index(63.0, 1) == -4
    # Not a nominal frequency of the octave series: centred on the value itself.
    odd = iec_band(100.0)
    assert odd.center_hz == 100.0 and odd.label == "100 Hz"
    with pytest.raises(ConfigurationError):
        iec_band(0.0)


def test_band_fits_below_nyquist() -> None:
    assert band_fits(fractional_octave_band(8000.0), 44100)
    assert not band_fits(fractional_octave_band(16000.0), 44100)
    with pytest.raises(ConfigurationError):
        bandpass_sos(fractional_octave_band(16000.0), 44100)


def test_bandpass_passes_centre_and_rejects_far_frequencies(sample_rate: int) -> None:
    band = fractional_octave_band(1000.0)
    sos = bandpass_sos(band, sample_rate)
    t = np.arange(sample_rate) / sample_rate
    inband = np.sin(2 * np.pi * 1000.0 * t)
    out = apply_bandpass(inband, sos, time_reversed=False)
    assert np.sqrt(np.mean(out[sample_rate // 4 :] ** 2)) == pytest.approx(np.sqrt(0.5), rel=0.02)
    far = np.sin(2 * np.pi * 4000.0 * t)
    out_far = apply_bandpass(far, sos, time_reversed=False)
    attenuation_db = 20 * np.log10(
        np.sqrt(np.mean(out_far[sample_rate // 4 :] ** 2)) / np.sqrt(0.5)
    )
    assert attenuation_db < -30.0


def test_band_edges_are_3_db_down_for_a_single_pass(sample_rate: int) -> None:
    """A10: level filtering used sosfiltfilt, so |H|^2 put the nominal band
    edges at -6.02 dB and narrowed the noise bandwidth."""
    band = fractional_octave_band(1000.0)
    sos = bandpass_sos(band, sample_rate)
    t = np.arange(sample_rate) / sample_rate
    for edge in (band.low_hz, band.high_hz):
        settled = band_level_samples(np.sin(2 * np.pi * edge * t), sos, sample_rate)
        assert settled is not None
        level_db = 20 * np.log10(np.sqrt(np.mean(settled**2)) / np.sqrt(0.5))
        assert level_db == pytest.approx(-3.01, abs=0.1)


def test_level_filtering_discards_the_start_transient(sample_rate: int) -> None:
    band = fractional_octave_band(63.0)
    sos = bandpass_sos(band, sample_rate)
    settled = settling_samples(sos, sample_rate)
    # The 63 Hz filter needs several times 1/B to settle, the 4 kHz one much less.
    assert 0.05 * sample_rate < settled < 0.5 * sample_rate
    assert (
        settling_samples(bandpass_sos(fractional_octave_band(4000.0), sample_rate), sample_rate)
        < settled
    )
    rng = np.random.default_rng(0)
    noise = rng.normal(0.0, 1.0, sample_rate)
    out = band_level_samples(noise, sos, sample_rate)
    assert out is not None and out.shape[0] == sample_rate - settled
    assert (
        band_level_samples(noise[: settled + 8], sos, sample_rate, min_settled_samples=16) is None
    )


def test_time_reversed_filtering_is_anti_causal(sample_rate: int) -> None:
    """Output sample i depends only on input samples >= i, so content kept (or
    cut) before an event never changes the band signal from that event on."""
    sos = bandpass_sos(iec_band(63.0), sample_rate)
    rng = np.random.default_rng(0)
    x = rng.normal(0.0, 1.0, sample_rate)
    y = x.copy()
    y[: sample_rate // 2] = 0.0
    fx = apply_bandpass(x, sos, time_reversed=True)
    fy = apply_bandpass(y, sos, time_reversed=True)
    np.testing.assert_allclose(fx[sample_rate // 2 :], fy[sample_rate // 2 :], rtol=0, atol=1e-12)


def test_time_reversed_filtering_keeps_energy_and_order(sample_rate: int) -> None:
    sos = bandpass_sos(fractional_octave_band(500.0), sample_rate)
    impulse = np.zeros(sample_rate)
    mid = sample_rate // 2
    impulse[mid] = 1.0
    forward = apply_bandpass(impulse, sos, time_reversed=False)
    reverse = apply_bandpass(impulse, sos, time_reversed=True)
    assert np.sum(forward**2) == pytest.approx(np.sum(reverse**2), rel=1e-6)
    # Forward filtering rings after the impulse, reverse filtering rings before it.
    assert np.sum(forward[:mid] ** 2) < 1e-12
    assert np.sum(reverse[mid + 1 :] ** 2) < 1e-12


def test_fractional_octave_smooth_preserves_constant_and_reduces_spike() -> None:
    freqs = np.linspace(1.0, 20000.0, 20000)
    flat = np.full_like(freqs, 3.0)
    assert np.allclose(fractional_octave_smooth(freqs, flat, 3), 3.0)
    spiked = flat.copy()
    spiked[10000] = 23.0
    smoothed = fractional_octave_smooth(freqs, spiked, 3)
    assert smoothed[10000] < 23.0
    assert smoothed[10000] > 3.0
    assert np.array_equal(fractional_octave_smooth(freqs, spiked, 0), spiked)


def test_fractional_octave_smooth_shape_mismatch() -> None:
    with pytest.raises(ConfigurationError):
        fractional_octave_smooth(np.arange(10.0), np.arange(9.0), 3)


def test_smoothing_keeps_levels_far_below_the_running_total() -> None:
    """A difference of forward running sums lost everything 150 dB below them:
    above the sweep band every default analysis stored -3000 dB."""
    from roomscope.core.filters import fractional_octave_smooth

    freqs = np.arange(1.0, 24001.0)
    magnitude = np.where(freqs < 20000.0, 0.0, -150.0 - freqs / 1000.0)
    smoothed = fractional_octave_smooth(freqs, magnitude, 6)
    half = 2.0 ** (1.0 / 12.0)
    for f in (500.0, 19000.0, 21000.0, 23000.0, 24000.0):
        window = (freqs >= f / half) & (freqs <= f * half)
        direct = 10.0 * np.log10(np.mean(10.0 ** (magnitude[window] / 10.0)))
        assert smoothed[int(f) - 1] == pytest.approx(direct, abs=1e-6), f
