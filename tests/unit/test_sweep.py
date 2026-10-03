from __future__ import annotations

import numpy as np
import pytest
from scipy.signal import fftconvolve, hilbert

from reverbscope.core.sweep import (
    active_region,
    design_spectral_inverse,
    estimate_reference_band_hz,
    excitation_band_hz,
    frequency_at_sweep_time,
    generate_ess,
    harmonic_pre_response_offsets_s,
    instantaneous_frequency,
    inverse_filter,
    inverse_filter_spectral,
    measurement_signal,
    normalisation_band_hz,
    reference_pulse,
    sweep_time_axis,
)
from reverbscope.errors import ConfigurationError
from reverbscope.models.configuration import SUPPORTED_SAMPLE_RATES, SweepSettings


def test_sweep_length_and_level(short_sweep: SweepSettings) -> None:
    x = generate_ess(short_sweep)
    assert x.shape[0] == short_sweep.sweep_samples == int(2.0 * short_sweep.sample_rate)
    assert np.max(np.abs(x)) == pytest.approx(short_sweep.amplitude, rel=1e-3)
    assert short_sweep.amplitude == pytest.approx(10 ** (-12 / 20))


def test_sweep_fades_start_and_end_at_zero(short_sweep: SweepSettings) -> None:
    x = generate_ess(short_sweep)
    assert x[0] == 0.0
    assert abs(x[-1]) < 1e-3 * short_sweep.amplitude


def test_instantaneous_frequency_follows_exponential_law(short_sweep: SweepSettings) -> None:
    x = generate_ess(short_sweep, apply_level=False)
    sr = short_sweep.sample_rate
    phase = np.unwrap(np.angle(hilbert(x)))
    measured = np.diff(phase) * sr / (2 * np.pi)
    t = sweep_time_axis(short_sweep)[:-1]
    expected = instantaneous_frequency(short_sweep, t)
    # Compare in the middle of the sweep (away from fades and Hilbert edge effects)
    lo, hi = int(0.2 * len(t)), int(0.8 * len(t))
    assert np.allclose(measured[lo:hi], expected[lo:hi], rtol=0.02)
    assert expected[0] == pytest.approx(short_sweep.start_hz)
    assert instantaneous_frequency(short_sweep, np.array([short_sweep.duration_s]))[
        0
    ] == pytest.approx(short_sweep.end_hz, rel=1e-6)


def test_measurement_signal_has_silences(short_sweep: SweepSettings) -> None:
    sig = measurement_signal(short_sweep)
    sr = short_sweep.sample_rate
    assert sig.shape[0] == short_sweep.total_samples
    assert np.all(sig[: int(1.0 * sr)] == 0.0)
    assert np.all(sig[-int(1.5 * sr) :] == 0.0)


def _inband_magnitude_db(
    pulse: np.ndarray, sample_rate: int, band: tuple[float, float]
) -> np.ndarray:
    nfft = 1 << pulse.shape[0].bit_length()
    spectrum = np.abs(np.fft.rfft(pulse, nfft))
    freqs = np.fft.rfftfreq(nfft, 1.0 / sample_rate)
    lo, hi = normalisation_band_hz(*band)
    return np.asarray(20 * np.log10(spectrum[(freqs >= lo) & (freqs <= hi)]))


def test_inverse_filter_gives_unit_inband_gain(short_sweep: SweepSettings) -> None:
    # The inverse is normalised so that the in-band magnitude of sweep * inverse
    # is 1 (0 dB). The pulse peak is then *not* 1: a band-limited pulse peaks at
    # about 2 * bandwidth / fs times its in-band magnitude (~0.82 here).
    pulse = reference_pulse(short_sweep)
    sr = short_sweep.sample_rate
    inband = _inband_magnitude_db(pulse, sr, excitation_band_hz(short_sweep))
    assert float(np.median(inband)) == pytest.approx(0.0, abs=1e-6)
    assert np.max(np.abs(inband)) < 0.2
    k = int(np.argmax(np.abs(pulse)))
    band_width = excitation_band_hz(short_sweep)[1] - excitation_band_hz(short_sweep)[0]
    assert pulse[k] == pytest.approx(2.0 * band_width / sr, rel=0.05)
    # The linear response sits at the end of the sweep (index M - 1 of the full convolution).
    assert k == short_sweep.sweep_samples - 1
    rel = np.abs(pulse) / np.abs(pulse[k])
    w = int(2e-3 * sr)
    outside = np.concatenate([rel[: k - w], rel[k + w + 1 :]])
    assert 20 * np.log10(outside.max()) < -35.0


def test_spectral_inverse_matches_analytic_behaviour(short_sweep: SweepSettings) -> None:
    sr = short_sweep.sample_rate
    ref = generate_ess(short_sweep)
    design = design_spectral_inverse(ref, sr)
    inv = design.inverse
    assert inv.shape[0] == ref.shape[0]
    pulse = fftconvolve(ref, inv)
    inband = _inband_magnitude_db(pulse, sr, (design.band_low_hz, design.band_high_hz))
    assert float(np.median(inband)) == pytest.approx(0.0, abs=1e-6)
    assert np.max(np.abs(inband)) < 0.2
    k = int(np.argmax(np.abs(pulse)))
    assert k == short_sweep.sweep_samples - 1
    rel = np.abs(pulse) / np.abs(pulse[k])
    w = int(2e-3 * sr)
    outside = np.concatenate([rel[: k - w], rel[k + w + 1 :]])
    assert 20 * np.log10(outside.max()) < -35.0
    assert np.array_equal(inverse_filter_spectral(ref, sr), inv)


def test_spectral_inverse_does_not_boost_out_of_band_or_ring() -> None:
    """A8: a constant regularisation boosted the inverse 13-15 dB above its
    in-band gain near 2 Hz and just above f2 and left a slowly decaying
    deterministic tail (about -70 dB at 0.5-1 s after the pulse)."""
    settings = SweepSettings(duration_s=10.0)
    sr = settings.sample_rate
    ref = generate_ess(settings)
    inv = design_spectral_inverse(ref, sr).inverse
    nfft = 1 << (2 * ref.shape[0]).bit_length()
    gain = np.abs(np.fft.rfft(inv, nfft))
    freqs = np.fft.rfftfreq(nfft, 1.0 / sr)

    def level(f: float) -> float:
        return float(20 * np.log10(gain[int(np.argmin(np.abs(freqs - f)))]))

    in_band_max = float(20 * np.log10(np.max(gain[(freqs > 100.0) & (freqs < 15000.0)])))
    for f in (2.0, 5.0, 10.0, 20500.0, 22000.0, 23500.0):
        assert level(f) < in_band_max - 20.0, f
    pulse = fftconvolve(ref, inv)
    k = int(np.argmax(np.abs(pulse)))
    rel_db = 20 * np.log10(np.abs(pulse) / np.abs(pulse[k]) + 1e-300)
    assert rel_db[k + int(0.5 * sr) : k + int(1.0 * sr)].max() < -100.0


def test_excitation_band_from_settings() -> None:
    settings = SweepSettings(duration_s=0.5, start_hz=20.0, end_hz=20000.0)
    rate = settings.sweep_rate
    low, high = excitation_band_hz(settings)
    assert low == pytest.approx(20.0 * np.exp(settings.fade_in_s / rate))
    assert high == pytest.approx(20000.0 * np.exp(-settings.fade_out_s / rate))
    # With a 0.5 s sweep the 50 ms fade-in covers a whole octave.
    assert low == pytest.approx(39.9, abs=0.1)
    no_fades = SweepSettings(start_hz=250.0, end_hz=5000.0, fade_in_s=0.0, fade_out_s=0.0)
    assert excitation_band_hz(no_fades) == pytest.approx((250.0, 5000.0))
    assert frequency_at_sweep_time(no_fades, no_fades.duration_s) == pytest.approx(5000.0)


def test_normalisation_band() -> None:
    assert normalisation_band_hz(20.0, 20000.0) == pytest.approx((40.0, 10000.0))
    lo, hi = normalisation_band_hz(500.0, 2000.0)  # two octaves: central half in log f
    assert lo == pytest.approx(500.0 * np.sqrt(2.0))
    assert hi == pytest.approx(2000.0 / np.sqrt(2.0))
    with pytest.raises(ConfigurationError):
        normalisation_band_hz(100.0, 100.0)


@pytest.mark.parametrize(
    ("settings", "tolerance_octaves"),
    [
        (SweepSettings(duration_s=10.0), 1.0 / 12.0),
        (SweepSettings(duration_s=2.0, start_hz=250.0, end_hz=5000.0), 1.0 / 12.0),
        (SweepSettings(duration_s=2.0, start_hz=500.0, end_hz=2000.0), 1.0 / 12.0),
        # 0.5 s sweep: the 50 ms fade spans an octave; the -3 dB point lies inside it.
        (SweepSettings(duration_s=0.5), 1.0 / 3.0),
    ],
)
def test_estimated_reference_band_matches_sweep_definition(
    settings: SweepSettings, tolerance_octaves: float
) -> None:
    low, high = estimate_reference_band_hz(generate_ess(settings), settings.sample_rate)
    exp_low, exp_high = excitation_band_hz(settings)
    assert abs(np.log2(low / exp_low)) < tolerance_octaves
    assert abs(np.log2(high / exp_high)) < 1.0 / 12.0
    design = design_spectral_inverse(generate_ess(settings), settings.sample_rate)
    ratio = 2.0 ** (1.0 / 3.0)
    assert design.band_low_hz == pytest.approx(design.reference_low_hz * ratio)
    assert design.band_high_hz == pytest.approx(design.reference_high_hz / ratio)


def test_spectral_inverse_rejects_too_narrow_reference() -> None:
    sr = 48000
    tone = np.sin(2 * np.pi * 1000.0 * np.arange(sr) / sr)
    with pytest.raises(ConfigurationError, match="too narrow"):
        design_spectral_inverse(tone, sr)


def test_active_region_trims_file_silences(short_sweep: SweepSettings) -> None:
    sr = short_sweep.sample_rate
    signal = measurement_signal(short_sweep)
    start, stop = active_region(signal)
    pre = round(short_sweep.pre_silence_s * sr)
    assert pre <= start < pre + round(0.005 * sr)
    sweep_end = pre + short_sweep.sweep_samples
    assert sweep_end - round(0.001 * sr) < stop <= sweep_end
    with pytest.raises(ConfigurationError):
        active_region(np.zeros(100))


def test_inverse_filter_is_time_reversed_with_6db_per_octave_envelope(
    short_sweep: SweepSettings,
) -> None:
    inv = inverse_filter(short_sweep)
    unit = generate_ess(short_sweep, apply_level=False)[::-1]
    # envelope ratio between t and t + L*ln2 (one octave) must be 1/2
    rate = short_sweep.sweep_rate
    sr = short_sweep.sample_rate
    i0 = int(0.1 * sr)
    i1 = i0 + round(rate * np.log(2) * sr)
    env = np.abs(hilbert(inv / np.max(np.abs(unit))))
    ratio = np.median(env[i1 - 50 : i1 + 50]) / np.median(env[i0 - 50 : i0 + 50])
    assert ratio == pytest.approx(0.5, rel=0.1)


def test_harmonic_pre_response_offsets(short_sweep: SweepSettings) -> None:
    offsets = harmonic_pre_response_offsets_s(short_sweep, max_order=3)
    rate = short_sweep.sweep_rate
    assert offsets == pytest.approx([rate * np.log(2), rate * np.log(3)])


@pytest.mark.parametrize("sr", SUPPORTED_SAMPLE_RATES)
def test_all_supported_sample_rates_generate(sr: int) -> None:
    settings = SweepSettings(sample_rate=sr, duration_s=1.0)
    x = generate_ess(settings)
    assert x.shape[0] == sr
    assert np.all(np.isfinite(x))


def test_unsupported_sample_rate_rejected() -> None:
    with pytest.raises(ConfigurationError):
        SweepSettings(sample_rate=32000)


def test_end_frequency_above_nyquist_rejected() -> None:
    with pytest.raises(ConfigurationError):
        SweepSettings(sample_rate=44100, end_hz=23000.0)


def test_level_above_full_scale_rejected() -> None:
    with pytest.raises(ConfigurationError):
        SweepSettings(level_dbfs=1.0)


def test_spectral_inverse_rejects_silence() -> None:
    with pytest.raises(ConfigurationError):
        inverse_filter_spectral(np.zeros(1000), 48000)
    with pytest.raises(ConfigurationError):
        design_spectral_inverse(np.ones(8), 48000)
