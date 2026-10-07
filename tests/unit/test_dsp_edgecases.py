"""Regressions for DSP defects found by adversarial inputs.

Each case below published a VALID reverberation time, raised, or ran in
quadratic time on the code before the fix. A clean exponential and a
synthetic room are included so the new gates cannot be satisfied by
rejecting everything.
"""

from __future__ import annotations

import time

import numpy as np
import pytest
from scipy.signal import sosfilt

from reverbscope.core.decay import analyze_band, analyze_decay, estimate_truncation
from reverbscope.core.deconvolution import find_sweep_passes
from reverbscope.core.filters import bandpass_sos, iec_band, settling_samples
from reverbscope.core.sweep import generate_ess
from reverbscope.errors import ConfigurationError
from reverbscope.models.configuration import AnalysisSettings, SweepSettings
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


def _full_settling(sos: np.ndarray, sample_rate: int) -> int:
    n = max(16, round(4.0 * sample_rate))
    impulse = np.zeros(n)
    impulse[0] = 1.0
    energy = np.cumsum(np.asarray(sosfilt(sos, impulse)) ** 2)
    total = float(energy[-1])
    return int(np.searchsorted(energy, 0.999 * total)) + 1


def test_settling_matches_a_full_length_impulse(sample_rate: int) -> None:
    """The early stop must not move the index a 4 s impulse would give."""
    for nominal in (63.0, 250.0, 1000.0, 4000.0, 8000.0):
        band = iec_band(nominal)
        if band.high_hz >= 0.9 * sample_rate / 2.0:
            continue
        sos = bandpass_sos(band, sample_rate)
        assert settling_samples(sos, sample_rate) == _full_settling(sos, sample_rate)


def test_settling_of_a_wide_band_does_not_filter_four_seconds() -> None:
    """At 192 kHz the 8 kHz octave settles in about 100 samples. Filtering the
    whole 4 s impulse spent hundreds of milliseconds in denormals."""
    sos = bandpass_sos(iec_band(8000.0), 192000)
    started = time.perf_counter()
    index = settling_samples(sos, 192000)
    assert time.perf_counter() - started < 0.05
    assert index < 1000


def _brute_passes(magnitude: np.ndarray, peak: int, reference_length: int) -> tuple[int, ...]:
    level = float(magnitude[peak])
    threshold = level * 10.0 ** (-20.0 / 20.0)
    separation = max(1, round(0.95 * reference_length))
    candidates = np.flatnonzero(magnitude >= threshold)
    candidates = candidates[np.abs(candidates - peak) >= separation]
    accepted = [peak]
    for candidate in candidates[np.argsort(-magnitude[candidates], kind="stable")]:
        if all(abs(int(candidate) - earlier) >= separation for earlier in accepted):
            accepted.append(int(candidate))
    return tuple(sorted(accepted))


def test_sweep_passes_match_the_quadratic_search() -> None:
    magnitude = np.abs(np.random.default_rng(0).normal(0.0, 0.05, 4000))
    clicks = np.random.default_rng(1).choice(4000, size=40, replace=False)
    magnitude[clicks] = np.random.default_rng(2).uniform(0.2, 1.0, size=40)
    peak = int(np.argmax(magnitude))
    found = find_sweep_passes(magnitude, peak, reference_length=2, sample_rate=48000)
    assert found == _brute_passes(magnitude, peak, 2)


def test_sweep_passes_of_a_short_reference_stay_fast() -> None:
    """A reference of two samples and a candidate every three samples made the
    acceptance loop quadratic (about a second at a few thousand candidates)."""
    n = 40000
    magnitude = np.zeros(n)
    positions = np.arange(0, n, 3)
    magnitude[positions] = np.random.default_rng(1).uniform(0.3, 1.0, size=positions.size)
    peak = int(np.argmax(magnitude))
    started = time.perf_counter()
    found = find_sweep_passes(magnitude, peak, reference_length=2, sample_rate=8000)
    assert time.perf_counter() - started < 1.0
    assert len(found) > 1000


def test_a_very_narrow_sweep_keeps_its_amplitude() -> None:
    """``exp(t/L) - 1`` cancelled to zero when the end frequency was one ulp
    above the start, so the sweep peaked a trillion times below its level."""
    settings = SweepSettings(
        sample_rate=48000,
        duration_s=0.5,
        start_hz=1000.0,
        end_hz=1000.0 * (1.0 + 1e-15),
        fade_in_s=0.0,
        fade_out_s=0.0,
        pre_silence_s=0.0,
        post_silence_s=0.0,
    )
    sweep = generate_ess(settings)
    assert float(np.max(np.abs(sweep))) == pytest.approx(settings.amplitude, rel=1e-6)


def test_an_underflowing_sweep_rate_is_rejected() -> None:
    """A start of 1e-320 makes ``ln(f2/f1)`` infinite, the rate 0, and the
    inverse filter's envelope a ZeroDivisionError. The sweep itself was all NaN."""
    settings = SweepSettings(
        sample_rate=48000,
        duration_s=0.5,
        start_hz=1e-320,
        end_hz=1000.0,
        fade_in_s=0.0,
        fade_out_s=0.0,
        pre_silence_s=0.0,
        post_silence_s=0.0,
    )
    with pytest.raises(ConfigurationError, match="sweep rate is not positive"):
        generate_ess(settings)
