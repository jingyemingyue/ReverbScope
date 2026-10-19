"""reverbscope.display.live: meter ballistics, dBFS and the live spectrum's display mapping."""

from __future__ import annotations

import math

import numpy as np
import pytest

from reverbscope.display.live import (
    CLIP_DBFS,
    METER_FLOOR_DBFS,
    PEAK_HOLD_S,
    RELEASE_DB_PER_S,
    SILENCE_DBFS,
    Ballistics,
    LiveSpectrum,
    MeterChannel,
    amplitude_spectrum_power,
    amplitude_to_dbfs,
    block_peak_dbfs,
    block_rms_dbfs,
    display_frequencies,
    log_resample,
    meter_fraction,
    note_name,
    periodic_hann,
    power_to_db,
)

RATE = 48000


def sine(hz: float, dbfs: float, frames: int, rate: int = RATE) -> np.ndarray:
    t = np.arange(frames) / rate
    return np.asarray(10.0 ** (dbfs / 20.0) * np.sin(2.0 * np.pi * hz * t))


# --- dBFS ------------------------------------------------------------------------


def test_dbfs_conversion() -> None:
    assert amplitude_to_dbfs(1.0) == pytest.approx(0.0)
    assert amplitude_to_dbfs(0.5) == pytest.approx(-6.0206, abs=1e-3)
    assert amplitude_to_dbfs(-0.25) == pytest.approx(-12.0412, abs=1e-3)
    assert amplitude_to_dbfs(0.0) == SILENCE_DBFS
    assert amplitude_to_dbfs(float("nan")) == SILENCE_DBFS
    assert power_to_db(np.array([1.0, 0.01, 0.0])).tolist() == pytest.approx(
        [0.0, -20.0, SILENCE_DBFS]
    )


def test_block_peak_and_rms_per_channel() -> None:
    left = sine(1000.0, -6.0, 4800)
    right = sine(1000.0, -20.0, 4800)
    block = np.stack([left, right], axis=1)
    peaks = block_peak_dbfs(block)
    rms = block_rms_dbfs(block)
    assert peaks == pytest.approx([-6.0, -20.0], abs=0.05)
    # A sine's RMS is 3.01 dB below its peak.
    assert rms == pytest.approx([-9.01, -23.01], abs=0.05)
    assert block_peak_dbfs(np.zeros((0, 2))) == [SILENCE_DBFS, SILENCE_DBFS]


def test_meter_fraction_spans_the_scale() -> None:
    assert meter_fraction(0.0) == 1.0
    assert meter_fraction(METER_FLOOR_DBFS) == 0.0
    assert meter_fraction(-30.0) == pytest.approx(0.5)
    assert meter_fraction(-200.0) == 0.0
    assert meter_fraction(6.0) == 1.0


# --- ballistics ------------------------------------------------------------------


def test_attack_is_instant_and_release_follows_the_rate() -> None:
    meter = Ballistics()
    assert meter.update(-6.0, 0.033) == -6.0
    # Silence afterwards: the bar falls RELEASE_DB_PER_S per second.
    meter.update(SILENCE_DBFS, 0.5)
    assert meter.level == pytest.approx(-6.0 - 0.5 * RELEASE_DB_PER_S)
    meter.update(SILENCE_DBFS, 0.5)
    assert meter.level == pytest.approx(-6.0 - RELEASE_DB_PER_S)
    # A louder block jumps straight up again.
    assert meter.update(-3.0, 0.01) == -3.0


def test_peak_hold_waits_then_falls_but_never_below_the_bar() -> None:
    meter = Ballistics()
    meter.update(-6.0, 0.0)
    for _ in range(round(PEAK_HOLD_S / 0.1) - 1):
        meter.update(-40.0, 0.1)
    assert meter.hold == pytest.approx(-6.0)  # still held just before PEAK_HOLD_S
    meter.update(-40.0, 0.1)
    meter.update(-40.0, 0.1)
    assert meter.hold < -6.0
    assert meter.hold >= meter.level
    for _ in range(100):
        meter.update(-40.0, 0.1)
    assert meter.hold == pytest.approx(-40.0)
    assert meter.level == pytest.approx(-40.0)


def test_clip_latches_until_reset() -> None:
    channel = MeterChannel()
    channel.update(-20.0, -26.0, 0.03)
    assert not channel.clipped
    channel.update(CLIP_DBFS, -3.0, 0.03)
    assert channel.clipped
    for _ in range(50):
        channel.update(-40.0, -46.0, 0.1)
    assert channel.clipped  # latched
    channel.reset_clip()
    assert not channel.clipped
    assert channel.peak.level == pytest.approx(-40.0)


# --- spectrum --------------------------------------------------------------------


def test_hann_window_is_periodic() -> None:
    window = periodic_hann(8)
    assert window[0] == 0.0
    assert window[4] == pytest.approx(1.0)
    assert np.sum(window) == pytest.approx(4.0)


def test_bin_centred_full_scale_sine_reads_zero_dbfs() -> None:
    size = 4096
    hz = 64 * RATE / size  # exactly on bin 64
    power = amplitude_spectrum_power(sine(hz, 0.0, size), periodic_hann(size))
    assert 10.0 * math.log10(power[64]) == pytest.approx(0.0, abs=0.01)


@pytest.mark.parametrize("fft_size", [2048, 4096, 8192, 16384])
def test_one_khz_at_minus_6_dbfs_reads_minus_6_db(fft_size: int) -> None:
    spectrum = LiveSpectrum(sample_rate=RATE, fft_size=fft_size, averaging_s=0.0, points=800)
    spectrum.update(sine(1000.0, -6.0, fft_size), 0.03)
    peak = int(np.argmax(spectrum.level_db))
    # Off-bin, the Hann window's scalloping loss is at most 1.42 dB.
    assert spectrum.level_db[peak] == pytest.approx(-6.0, abs=1.5)
    assert spectrum.frequencies[peak] == pytest.approx(1000.0, rel=0.03)
    assert spectrum.value_at(1000.0) == pytest.approx(-6.0, abs=2.0)


def test_display_frequencies_are_log_spaced_and_stop_below_nyquist() -> None:
    f = display_frequencies(48000, 500)
    assert f[0] == pytest.approx(20.0)
    assert f[-1] == pytest.approx(20000.0)
    ratios = f[1:] / f[:-1]
    assert np.allclose(ratios, ratios[0])
    low = display_frequencies(32000, 500)
    assert low[-1] < 16000.0


def test_peak_mapping_keeps_a_tone_however_few_points() -> None:
    size = 16384
    power = amplitude_spectrum_power(sine(7000.0, -10.0, size), periodic_hann(size))
    for points in (64, 200, 1500):
        f = display_frequencies(RATE, points)
        shown = power_to_db(log_resample(power, RATE, f, 0))
        assert shown.max() == pytest.approx(-10.0, abs=1.5)


def test_fractional_octave_smoothing_keeps_noise_level_and_lowers_tones() -> None:
    size = 16384
    rng = np.random.default_rng(1)
    noise = 0.01 * rng.standard_normal(size * 8)
    window = periodic_hann(size)
    # Average several frames so the raw noise spectrum is steady enough to compare.
    power = np.mean(
        [amplitude_spectrum_power(noise[i * size : (i + 1) * size], window) for i in range(8)],
        axis=0,
    )
    f = display_frequencies(RATE, 400)
    raw = power_to_db(log_resample(power, RATE, f, 0))
    third = power_to_db(log_resample(power, RATE, f, 3))
    band = (f > 1000) & (f < 10000)
    # White noise: the smoothed mean power equals the bin mean (raw takes cell maxima).
    mean_bin_db = 10.0 * math.log10(float(np.mean(power[100:-100])))
    assert np.median(third[band]) == pytest.approx(mean_bin_db, abs=1.0)
    assert np.std(third[band]) < np.std(raw[band])
    tone = amplitude_spectrum_power(sine(1000.0, -6.0, size), window)
    for fraction in (3, 6, 12):
        smoothed = power_to_db(log_resample(tone, RATE, f, fraction))
        assert smoothed.max() < -6.0
    assert (
        power_to_db(log_resample(tone, RATE, f, 12)).max()
        > power_to_db(log_resample(tone, RATE, f, 3)).max()
    )


def test_averaging_and_peak_hold_decay() -> None:
    spectrum = LiveSpectrum(sample_rate=RATE, fft_size=4096, averaging_s=0.3, points=300)
    loud = sine(1000.0, -6.0, 4096)
    spectrum.update(loud, 0.03)
    peak_index = int(np.argmax(spectrum.level_db))
    assert spectrum.level_db[peak_index] == pytest.approx(-6.0, abs=1.5)
    before = float(spectrum.level_db[peak_index])
    quiet = np.zeros(4096)
    spectrum.update(quiet, 0.03)
    # Exponential averaging of power: one frame of silence lowers the tone by
    # 10*log10(exp(-dt/tau)) only (0.43 dB for 30 ms against 0.3 s).
    expected = 10.0 * math.log10(math.exp(-0.03 / 0.3))
    assert spectrum.level_db[peak_index] == pytest.approx(before + expected, abs=0.01)
    # The peak trace holds, then falls at its decay rate, never below the curve.
    held = float(spectrum.peak_db[peak_index])
    spectrum.update(quiet, spectrum.peak_hold_s * 0.5)
    assert spectrum.peak_db[peak_index] == pytest.approx(held)
    for _ in range(40):
        spectrum.update(quiet, 0.1)
    assert spectrum.peak_db[peak_index] < held - 10.0
    assert np.all(spectrum.peak_db >= spectrum.level_db - 1e-9)


def test_no_averaging_follows_the_newest_frame() -> None:
    spectrum = LiveSpectrum(sample_rate=RATE, fft_size=2048, averaging_s=0.0, points=200)
    spectrum.update(sine(1000.0, -6.0, 2048), 0.03)
    spectrum.update(sine(1000.0, -26.0, 2048), 0.03)
    assert spectrum.level_db.max() == pytest.approx(-26.0, abs=1.5)


def test_note_names() -> None:
    assert note_name(440.0) == "A4"
    assert note_name(261.63) == "C4"
    assert note_name(1000.0) == "B5"
    assert note_name(10.0) == ""
