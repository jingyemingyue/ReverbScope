"""Regressions for DSP defects found by adversarial inputs.

Each case below published a VALID reverberation time, raised, or ran in
quadratic time on the code before the fix. A clean exponential and a
synthetic room are included so the new gates cannot be satisfied by
rejecting everything.
"""

from __future__ import annotations

import numpy as np
import pytest

from reverbscope.core.decay import analyze_band, analyze_decay, estimate_truncation
from reverbscope.models.configuration import AnalysisSettings
from reverbscope.models.result import Validity
from tests.conftest import DECAY_CONSTANT, exponential_decay_ir, make_rir


def _gated(sample_rate: int, *, floor: float, residue: float = 0.0) -> np.ndarray:
    """RT 2 s cut off at 1 s. The record is longer than the decay."""
    n = 2 * sample_rate
    t = np.arange(n) / sample_rate
    ir = np.random.default_rng(0).normal(0.0, 1.0, n) * np.exp(-DECAY_CONSTANT * t / 4.0)
    ir[t >= 1.0] = 0.0
    if floor:
        ir = ir + floor * np.random.default_rng(9).normal(0.0, 1.0, n)
    if residue:
        ir[-1] = residue
    return ir


def test_a_residual_sample_after_a_gate_is_not_a_valid_rt60(sample_rate: int) -> None:
    """One sample of 1e-12 after exact silence made the last 10 % a floor of
    about -280 dB. The late slope then had no intervals, the rejected Lundeby
    estimate was the same index as the preliminary one, and T30 of the cliff
    (1.76 s, true RT 2 s, gate at 1 s) was published as VALID."""
    ir = _gated(sample_rate, floor=0.0, residue=1e-12)
    band = analyze_band(ir, sample_rate, None, noise_margin_db=10.0)
    assert band.rt60_estimate_s is None
    assert band.t30.validity is not Validity.VALID
    assert band.t20.validity is not Validity.VALID
    assert band.t30.validity is Validity.INSUFFICIENT_RANGE
    assert any("cut off" in warning for warning in band.warnings)


def test_a_gate_onto_a_floor_is_not_a_valid_rt60(sample_rate: int) -> None:
    """Same cliff with a smooth floor instead of one residual sample. Exact
    zeros are trimmed and correctly refuse T30; a floor of 1e-6 does not."""
    ir = _gated(sample_rate, floor=1e-6)
    band = analyze_band(ir, sample_rate, None, noise_margin_db=10.0)
    assert band.rt60_estimate_s is None
    assert band.t30.validity is not Validity.VALID
    result = analyze_decay(ir, sample_rate, AnalysisSettings())
    # No band has 45 dB of decay above the cut, so no T30 anywhere. A narrow
    # band's filter smears the gate into a few more dB of apparent decay; its
    # T20, fitted over the real decay above the gate, is the true 2 s and not
    # the cliff's, so it may stand.
    assert all(band.t30.validity is not Validity.VALID for band in result.bands)
    for band in result.bands:
        if band.rt60_estimate_s is not None:
            assert band.rt60_basis == "T20"
            assert band.rt60_estimate_s == pytest.approx(2.0, rel=0.1)


def test_an_empty_response_is_too_short_rather_than_an_exception() -> None:
    trunc = estimate_truncation(np.zeros(0), 48000)
    assert trunc.problem == "the response is too short for a noise-floor estimate"
    band = analyze_band(np.zeros(0), 48000, None, noise_margin_db=10.0)
    assert band.rt60_estimate_s is None


def test_a_curved_t20_is_not_the_rt60_when_t30_has_no_range(sample_rate: int) -> None:
    """Double slope, 0.3 s then 2 s at -25 dB, with a floor near -38 dB.
    T30 has no range, so the curvature check never ran and the bent T20
    (xi about 30 permille, limit 15) was the published RT60."""
    n = 5 * sample_rate
    t = np.arange(n) / sample_rate
    envelope = np.exp(-DECAY_CONSTANT * t / 0.3) + 10 ** (-25 / 10) * np.exp(
        -DECAY_CONSTANT * t / 2.0
    )
    signal = np.random.default_rng(0).normal(0.0, 1.0, n) * np.sqrt(envelope)
    signal += 10 ** (-38 / 20) * np.random.default_rng(1).normal(0.0, 1.0, n)
    band = analyze_band(signal, sample_rate, None, noise_margin_db=10.0)
    assert band.t30.validity is Validity.INSUFFICIENT_RANGE
    assert band.t20.validity is not Validity.VALID
    assert band.rt60_estimate_s is None
    assert any("not straight" in warning for warning in band.warnings)


def test_a_late_noise_burst_is_not_a_valid_edt(sample_rate: int) -> None:
    """Energy burst on [1.5 s, 1.6 s) of an RT 0.5 s decay. The -10 dB point
    lands on the burst, so EDT was VALID at about 73 s with xi about 780
    permille; T20 and T30 were already rejected for curvature."""
    ir = exponential_decay_ir(sample_rate, 0.5, 2.0, seed=3)
    start, stop = int(1.5 * sample_rate), int(1.6 * sample_rate)
    ir = ir.copy()
    ir[start:stop] += np.random.default_rng(0).normal(0.0, 0.5, stop - start)
    band = analyze_band(ir, sample_rate, None, noise_margin_db=10.0)
    assert band.edt.validity is not Validity.VALID
    assert not (
        band.edt.validity is Validity.VALID
        and band.edt.seconds is not None
        and band.edt.seconds > 5.0
    )
    assert band.rt60_estimate_s is None


def test_a_mid_decay_burst_is_not_a_short_rt60(sample_rate: int) -> None:
    """Burst on [0.8 s, 0.82 s) of an RT 0.5 s decay. T30 of a wide band fitted
    the cliff (about 0.03 s) and stayed VALID because B*T was so small that
    the straightness limit opened up past the fit's own xi."""
    ir = exponential_decay_ir(sample_rate, 0.5, 2.0, seed=3)
    start, stop = int(0.8 * sample_rate), int(0.82 * sample_rate)
    ir = ir.copy()
    ir[start:stop] += np.random.default_rng(0).normal(0.0, 1.0, stop - start)
    result = analyze_decay(ir, sample_rate, AnalysisSettings(), direct_index=0)
    for band in (result.broadband, *result.bands):
        for metric in (band.t20, band.t30):
            assert not (
                metric.validity is Validity.VALID
                and metric.seconds is not None
                and metric.seconds < 0.1
            )
        assert band.rt60_estimate_s is None or band.rt60_estimate_s > 0.1


def test_clean_exponential_and_room_stay_valid(sample_rate: int) -> None:
    for ir, rt60 in (
        (exponential_decay_ir(sample_rate, 0.8, 2.5, seed=1), 0.8),
        (make_rir(sample_rate, rt60_s=0.8, length_s=2.0, seed=1), 0.8),
        (exponential_decay_ir(sample_rate, 0.05, 0.5, seed=2), 0.05),
    ):
        band = analyze_band(ir, sample_rate, None, noise_margin_db=10.0)
        assert band.rt60_estimate_s == pytest.approx(rt60, rel=0.05)
        assert band.t30.validity is Validity.VALID
        assert band.edt.validity is Validity.VALID


def test_a_decay_cut_far_below_its_range_keeps_its_rt60(sample_rate: int) -> None:
    """A synthetic or imported response that ends while its decay is still 70 dB
    down (and 45 dB above the floor) is a cut, not a reverberation problem: the
    floor is set at the cut, T30 is fitted on the decay above it, and a warning
    names the cut. (Rejecting the whole band here withheld the RT60 of every
    low band of the demo's second position.)"""
    decay = exponential_decay_ir(sample_rate, 0.8, 1.0, seed=5)
    floor = 1e-6 * np.random.default_rng(6).normal(0.0, 1.0, int(1.5 * sample_rate))
    ir = np.concatenate([decay, floor])
    band = analyze_band(ir, sample_rate, None, noise_margin_db=10.0)
    assert band.t30.validity is Validity.VALID
    assert band.rt60_estimate_s == pytest.approx(0.8, rel=0.05)
    assert band.peak_to_noise_db == pytest.approx(75.0, abs=6.0)
    assert sum("cut off" in warning for warning in band.warnings) == 1


def test_a_fast_decay_over_a_deep_floor_is_not_read_as_cut(sample_rate: int) -> None:
    """RT 0.05 s falls 24 dB per 20 ms block, which is its slope and not a fall
    off its line; with a white floor 80 dB down every metric stays valid."""
    ir = exponential_decay_ir(sample_rate, 0.05, 0.5, seed=2)
    ir = ir + 1e-4 * np.random.default_rng(7).normal(0.0, 1.0, ir.shape[0])
    band = analyze_band(ir, sample_rate, None, noise_margin_db=10.0)
    assert band.t30.validity is Validity.VALID
    assert band.rt60_estimate_s == pytest.approx(0.05, rel=0.1)
    assert not any("cut off" in warning for warning in band.warnings)


def test_a_strong_early_reflection_keeps_a_valid_edt(sample_rate: int) -> None:
    """The first 10 dB of a room with a desk reflection are not straight (xi of
    about 45 permille against a limit of 15), and that is what EDT measures:
    shorter than T30, and valid. Only an EDT far longer than the late decay is
    checked for straightness (test_a_late_noise_burst_is_not_a_valid_edt)."""
    ir = make_rir(sample_rate, rt60_s=0.7, reflections=[(0.0024, 0.7)], seed=3)
    band = analyze_band(ir, sample_rate, None, noise_margin_db=10.0)
    assert band.edt.validity is Validity.VALID
    assert band.t30.validity is Validity.VALID
    assert band.edt.seconds is not None and band.t30.seconds is not None
    assert band.edt.seconds < band.t30.seconds


def _direct_sound_then_decay(sample_rate: int, step_db: float) -> np.ndarray:
    """A single-sample direct sound followed by an exactly exponential tail
    (RT 0.5 s) whose energy sits ``step_db`` below the direct sound's."""
    n = int(1.5 * sample_rate)
    t = np.arange(n) / sample_rate
    tail = np.exp(-DECAY_CONSTANT * t / 1.0) * np.where(np.arange(n) % 2 == 0, 1.0, -1.0)
    fraction = 10.0 ** (-step_db / 10.0)
    tail *= np.sqrt(fraction / (1.0 - fraction) / float(np.sum(tail**2)))
    tail[0] = 1.0
    tail[1] = 0.0
    return tail + 10.0 ** (-90.0 / 20.0) * np.random.default_rng(0).normal(0.0, 1.0, n)


def test_t20_and_t30_are_not_fitted_across_the_direct_sound(sample_rate: int) -> None:
    """With the direct sound 22 dB above the room, the Schroeder curve has
    already fallen 22 dB when the fit may start, so a T20 fit would cover 3 dB
    of room decay and a T30 fit 13 dB: they described the direct sound's step
    and were published as VALID (up to 27 % off). EDT already had this rule."""
    band = analyze_band(
        _direct_sound_then_decay(sample_rate, 22.0),
        sample_rate,
        None,
        noise_margin_db=10.0,
        direct_index=0,
    )
    for metric in (band.t20, band.t30):
        assert metric.validity is Validity.UNRELIABLE
        assert "direct sound covers" in (metric.reason or "")
    assert band.rt60_estimate_s is None
    # A direct sound 8 dB above the room leaves most of both ranges to the room.
    band = analyze_band(
        _direct_sound_then_decay(sample_rate, 8.0),
        sample_rate,
        None,
        noise_margin_db=10.0,
        direct_index=0,
    )
    assert band.t20.validity is Validity.VALID
    assert band.t30.validity is Validity.VALID
    assert band.rt60_estimate_s == pytest.approx(0.5, rel=0.1)
