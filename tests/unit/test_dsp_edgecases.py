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
    assert any("stops abruptly" in warning for warning in band.warnings)


def test_a_gate_onto_a_floor_is_not_a_valid_rt60(sample_rate: int) -> None:
    """Same cliff with a smooth floor instead of one residual sample. Exact
    zeros are trimmed and correctly refuse T30; a floor of 1e-6 does not."""
    ir = _gated(sample_rate, floor=1e-6)
    band = analyze_band(ir, sample_rate, None, noise_margin_db=10.0)
    assert band.rt60_estimate_s is None
    assert band.t30.validity is not Validity.VALID
    result = analyze_decay(ir, sample_rate, AnalysisSettings())
    assert all(band.rt60_estimate_s is None for band in result.bands)


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
