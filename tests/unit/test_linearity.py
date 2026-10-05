"""Flat-top (clipping) detection and the aliased-distortion probe."""

from __future__ import annotations

import numpy as np
import pytest

from reverbscope.core.linearity import (
    CLIPPING_MIN_RUNS,
    detect_clipping,
    quantisation_step,
)
from reverbscope.core.sweep import generate_ess, measurement_signal
from reverbscope.models.configuration import SweepSettings


def _quantise(x: np.ndarray, bits: int = 24, dither: float = 0.0, seed: int = 0) -> np.ndarray:
    """``x`` on the grid of a PCM export of ``bits`` bits, optionally dithered."""
    step = 2.0 ** -(bits - 1)
    if dither:
        x = x + np.random.default_rng(seed).triangular(-dither, 0.0, dither, x.shape[0]) * step
    return np.asarray(np.round(np.clip(x, -1.0, 1.0 - step) / step) * step)


def _sine(sample_rate: int, frequency_hz: float, seconds: float, amplitude: float) -> np.ndarray:
    t = np.arange(int(seconds * sample_rate)) / sample_rate
    return amplitude * np.sin(2 * np.pi * frequency_hz * t)


def test_quantisation_step_is_recognised(sample_rate: int) -> None:
    x = _sine(sample_rate, 100.0, 0.2, 0.5)
    assert quantisation_step(_quantise(x, 16)) == pytest.approx(2.0**-15)
    assert quantisation_step(_quantise(x, 24)) == pytest.approx(2.0**-23)
    assert quantisation_step(x) is None


def test_unclipped_signals_are_not_flagged(sample_rate: int) -> None:
    """A6: an unclipped recording normalised to 0 dBFS produced a 'probable
    clipping' warning, because 205 samples were at or above 0.999."""
    settings = SweepSettings(sample_rate=sample_rate, duration_s=2.0)
    sweep = measurement_signal(settings)
    for signal in (
        sweep,  # an ESS at -12 dBFS
        sweep / np.max(np.abs(sweep)),  # the same, normalised to 0 dBFS
        _quantise(sweep / np.max(np.abs(sweep)), 24),
        _sine(sample_rate, 1000.0, 0.5, 1.0),  # a full-scale sine
        _quantise(_sine(sample_rate, 30.0, 0.5, 0.999), 24),  # flat quantised crests
    ):
        check = detect_clipping(signal)
        assert not check.clipped, check


@pytest.mark.parametrize("gain_db", [0.0, -0.5, -1.0, -6.02])
def test_clipped_sine_is_flagged_whatever_the_export_level(
    sample_rate: int, gain_db: float
) -> None:
    """C22: clipping was detected with an absolute threshold of 0.999, so a
    clipped file exported 0.1 dB below full scale was not flagged."""
    clipped = np.clip(_sine(sample_rate, 100.0, 1.0, 1.5), -1.0, 1.0) * 10 ** (gain_db / 20)
    check = detect_clipping(_quantise(clipped, 24))
    assert check.clipped
    assert check.peak_dbfs == pytest.approx(gain_db, abs=0.05)
    assert check.runs > CLIPPING_MIN_RUNS


def test_ceiling_below_full_scale_is_flagged(sample_rate: int) -> None:
    """C22: a file clipped at a 0.5 ceiling (12 dB of overdrive, then a
    fader) was reported as clean with a 'high' confidence."""
    check = detect_clipping(np.clip(_sine(sample_rate, 200.0, 1.0, 2.0), -0.5, 0.5))
    assert check.clipped and check.peak_dbfs == pytest.approx(-6.02, abs=0.05)


def test_dithered_export_of_a_clipped_signal_is_flagged(sample_rate: int) -> None:
    clipped = np.clip(_sine(sample_rate, 100.0, 1.0, 1.5), -1.0, 1.0) * 0.9
    check = detect_clipping(_quantise(clipped, 16, dither=1.0))
    assert check.clipped and check.quantisation_step == pytest.approx(2.0**-15)


def test_a_few_flat_samples_are_not_enough(sample_rate: int) -> None:
    signal = generate_ess(SweepSettings(sample_rate=sample_rate, duration_s=2.0))
    signal = signal / np.max(np.abs(signal))
    # Two clipped peaks: a single transient, not a clipped measurement.
    signal[1000:1010] = 1.0
    signal[5000:5010] = -1.0
    check = detect_clipping(signal)
    assert check.runs == 2 and not check.clipped


def test_quiet_signals_are_never_reported(sample_rate: int) -> None:
    """Below the level floor, the flat tops of a quantised low-frequency
    crest cannot be told from a clipped one."""
    clipped = np.clip(_sine(sample_rate, 100.0, 1.0, 1.5), -1.0, 1.0) * 10 ** (-30 / 20)
    assert not detect_clipping(_quantise(clipped, 16)).clipped


@pytest.mark.parametrize("duration_s", [2.0, 10.0, 30.0])
def test_long_sweeps_in_16_bit_are_not_flagged(sample_rate: int, duration_s: float) -> None:
    """A quantised low-frequency crest is flat too: at 16 bits, the 20-100 Hz
    part of an unclipped sweep has runs of a dozen samples at its maximum.
    They are told apart by the step at the end of the plateau."""
    settings = SweepSettings(sample_rate=sample_rate, duration_s=duration_s)
    sweep = measurement_signal(settings)
    for signal in (sweep, sweep / np.max(np.abs(sweep))):
        assert not detect_clipping(_quantise(signal, 16)).clipped
        assert not detect_clipping(_quantise(signal, 16, dither=1.0)).clipped
