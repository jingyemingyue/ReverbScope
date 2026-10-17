"""Independent physical and boundary checks for the new optional metrics."""

from __future__ import annotations

import cmath
import math

import numpy as np
import pytest

from reverbscope.core.iacc import compute_iacc
from reverbscope.core.sti import MODULATION_FREQUENCIES_HZ, STI_OCTAVE_BANDS_HZ, compute_sti
from reverbscope.core.strength import CalibrationReference, compute_g
from reverbscope.errors import InvalidAudioError


def test_strength_corrects_a_five_metre_reference_to_ten_metres() -> None:
    # Four units at 5 m equal one at 10 m in a free field.
    calibration = CalibrationReference(np.array([4.0]), 48000, distance_m=5)
    assert compute_g(np.array([1.0]), calibration) == pytest.approx(0.0)


def test_strength_uses_energy_integrals_for_different_sample_rates() -> None:
    calibration = CalibrationReference(np.ones(48000), 48000)
    assert compute_g(np.ones(24000), calibration, sample_rate=24000) == pytest.approx(0)


@pytest.mark.parametrize("distance", [math.nan, math.inf, -1.0])
def test_strength_refuses_nonphysical_calibration_distance(distance: float) -> None:
    with pytest.raises(InvalidAudioError):
        CalibrationReference(np.ones(10), 48000, distance_m=distance)


def test_strength_refuses_negative_power_and_withholds_silent_measurement() -> None:
    calibration = CalibrationReference(np.ones(10), 48000)
    with pytest.raises(InvalidAudioError):
        compute_g(np.array([-1.0, 2.0]), calibration)
    with pytest.raises(InvalidAudioError):
        CalibrationReference(np.array([-1.0, 2.0]), 48000)
    assert compute_g(np.zeros(10), calibration) is None


def test_strength_is_finite_for_large_finite_powers() -> None:
    calibration = CalibrationReference(np.full(10, 1e308), 48000)
    assert compute_g(np.full(10, 1e308), calibration) == pytest.approx(0)


def test_sti_requires_the_full_seven_band_spectrum() -> None:
    assert compute_sti({1000.0: np.array([1.0, 0.0])}, 48000) is None


def test_sti_matches_the_analytic_geometric_decay_and_redundancy_formula() -> None:
    rate = 1000
    n = 2000
    powers = {}
    mtis = []
    for band, tau in zip(STI_OCTAVE_BANDS_HZ, np.linspace(0.03, 0.2, 7), strict=True):
        q = math.exp(-1 / (rate * tau))
        powers[band] = q ** np.arange(n)
        indices = []
        for frequency in MODULATION_FREQUENCIES_HZ:
            z = q * cmath.exp(-2j * math.pi * frequency / rate)
            mtf = abs((1 - z**n) / (1 - z)) * (1 - q) / (1 - q**n)
            snr = min(15, max(-15, 10 * math.log10(mtf / (1 - mtf))))
            indices.append((snr + 15) / 30)
        mtis.append(sum(indices) / 14)
    alpha = [0.085, 0.127, 0.230, 0.233, 0.309, 0.224, 0.173]
    beta = [0.085, 0.078, 0.065, 0.011, 0.047, 0.095]
    expected = sum(a * m for a, m in zip(alpha, mtis, strict=True)) - sum(
        beta[k] * math.sqrt(mtis[k] * mtis[k + 1]) for k in range(6)
    )
    result = compute_sti(powers, rate)
    assert result is not None
    assert result.sti == pytest.approx(expected, abs=1e-10)


def test_sti_does_not_turn_invalid_or_silent_power_into_a_qualified_result() -> None:
    powers = {band: np.zeros(10) for band in STI_OCTAVE_BANDS_HZ}
    assert compute_sti(powers, 48000) is None
    powers[1000.0] = np.full(10, -1.0)
    with pytest.raises(InvalidAudioError):
        compute_sti(powers, 48000)


def test_sti_handles_finite_power_without_sum_overflow() -> None:
    powers = {band: np.full(100, 1e308) for band in STI_OCTAVE_BANDS_HZ}
    result = compute_sti(powers, 48000)
    assert result is not None
    assert math.isfinite(result.sti)


def test_iacc_uses_energy_normalization_without_subtracting_the_mean() -> None:
    result = compute_iacc(np.ones(200), np.ones(200), 1000)
    assert result.iacc_overall == pytest.approx(1)


def test_short_ir_keeps_the_entire_early_window_and_has_no_late_window() -> None:
    impulse = np.zeros(100)
    impulse[-1] = 1
    result = compute_iacc(impulse, impulse, 2000)
    assert result.iacc_early == pytest.approx(1)
    assert result.iacc_late is None


def test_iacc_does_not_search_beyond_one_millisecond() -> None:
    left, right = np.zeros(300), np.zeros(300)
    left[30], right[75] = 1, 1
    result = compute_iacc(left, right, 44600)
    assert result.delay_s is not None
    assert abs(result.delay_s) <= 0.001
    assert result.iacc_overall == pytest.approx(0)


@pytest.mark.parametrize("gain", [1e-200, 1.0, 1e200])
def test_iacc_is_invariant_to_independent_channel_gains(gain: float) -> None:
    signal = np.random.default_rng(7).standard_normal(400)
    result = compute_iacc(signal * gain, -signal / gain, 2000)
    assert result.iacc_overall == pytest.approx(1)


@pytest.mark.parametrize("split", [0.0, -1.0, math.nan, math.inf])
def test_iacc_refuses_invalid_early_late_split(split: float) -> None:
    with pytest.raises(InvalidAudioError):
        compute_iacc(np.ones(100), np.ones(100), 48000, early_split_s=split)
