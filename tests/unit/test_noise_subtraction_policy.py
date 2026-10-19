"""Noise subtraction is opt-in until a tail estimate can distinguish signal."""

from __future__ import annotations

import math

import numpy as np
import pytest

from reverbscope.core.decay import (
    DECAY_METHOD,
    TruncationEstimate,
    _curve_from_truncation,
    analyze_band,
    schroeder_curve,
)
from reverbscope.models.result import Validity


@pytest.mark.parametrize("cut_db", [45.0, 50.0, 55.0])
def test_default_curve_preserves_a_noiseless_exponential(cut_db: float) -> None:
    sample_rate = 8000
    t60 = 0.8
    time = np.arange(2 * sample_rate) / sample_rate
    signal = np.exp(-math.log(1000) * time / t60)
    signal[time >= t60 * cut_db / 60] = 0.0

    default = schroeder_curve(signal, sample_rate)
    unsubtracted = schroeder_curve(signal, sample_rate, subtract_noise=False)
    np.testing.assert_array_equal(default.edc_db, unsubtracted.edc_db)
    fit = (default.edc_db <= -5.0) & (default.edc_db >= -35.0)
    slope = np.polyfit(default.time_s[fit], default.edc_db[fit], 1)[0]
    assert -60.0 / slope == pytest.approx(t60, rel=0.01)


def test_default_band_analysis_preserves_valid_noiseless_t30() -> None:
    sample_rate = 8000
    time = np.arange(2 * sample_rate) / sample_rate
    signal = np.exp(-math.log(1000) * time / 0.8)
    signal[time >= 0.8 * 50.0 / 60] = 0.0

    band = analyze_band(signal, sample_rate, None, noise_margin_db=10.0)
    assert band.t30.validity is Validity.VALID
    assert band.t30.seconds == pytest.approx(0.8, rel=0.01)
    assert "noise-power subtraction" not in DECAY_METHOD


def test_public_opt_in_reaches_the_noise_subtraction_path() -> None:
    sample_rate = 8000
    time = np.arange(2 * sample_rate) / sample_rate
    signal = np.exp(-math.log(1000) * time / 0.8)
    signal[time >= 0.8 * 50.0 / 60] = 0.0
    raw = schroeder_curve(signal, sample_rate, subtract_noise=False)
    opted_in = schroeder_curve(signal, sample_rate, subtract_noise=True)
    assert opted_in.truncation.problem is None
    assert opted_in.truncation.peak_db - opted_in.truncation.noise_floor_db > 40.0
    assert np.max(np.abs(raw.edc_db - opted_in.edc_db)) > 1.0


@pytest.mark.parametrize("dynamic_range_db", [39.999999, 40.0, 40.000001, 60.0])
@pytest.mark.parametrize("problem", [None, "Lundeby estimate rejected"])
def test_explicit_subtraction_keeps_the_guard_and_known_energy_sum(
    dynamic_range_db: float, problem: str | None
) -> None:
    noise = 10.0 ** (-dynamic_range_db / 10.0)
    power = np.array([1.0, 0.1, noise / 2, 3 * noise, noise / 10])
    original = power.copy()
    truncation = TruncationEstimate(
        start_index=0,
        truncation_index=len(power),
        noise_floor_db=-dynamic_range_db,
        peak_db=0.0,
        late_slope_db_per_s=None,
        converged=problem is None,
        iterations=2,
        problem=problem,
    )
    kwargs = {"compensate": False, "time_origin_index": 0}
    default = _curve_from_truncation(power, 1000, 0, truncation, **kwargs)
    raw = _curve_from_truncation(power, 1000, 0, truncation, subtract_noise=False, **kwargs)
    np.testing.assert_array_equal(default.edc_db, raw.edc_db)

    opted_in = _curve_from_truncation(power, 1000, 0, truncation, subtract_noise=True, **kwargs)
    eligible = dynamic_range_db > 40.0 and problem is None
    corrected = [max(float(p) - noise, 1e-300) if eligible else float(p) for p in power]
    energy = np.array([math.fsum(corrected[k:]) for k in range(len(power))])
    expected = 10.0 * np.log10(np.maximum(energy / energy[0], 1e-300))
    np.testing.assert_allclose(opted_in.edc_db, expected, atol=1e-12)
    assert np.isfinite(opted_in.edc_db).all()
    assert (np.diff(opted_in.edc_db) <= 0.0).all()
    np.testing.assert_array_equal(power, original)


@pytest.mark.parametrize("floor_db", [float("nan"), float("inf"), -float("inf")])
def test_explicit_subtraction_rejects_a_nonfinite_floor(floor_db: float) -> None:
    power = np.array([1.0, 0.5, 0.1])
    truncation = TruncationEstimate(0, 3, floor_db, 0.0, None, True, 2)
    raw = _curve_from_truncation(
        power,
        1000,
        0,
        truncation,
        compensate=False,
        time_origin_index=0,
        subtract_noise=False,
    )
    opted_in = _curve_from_truncation(
        power,
        1000,
        0,
        truncation,
        compensate=False,
        time_origin_index=0,
        subtract_noise=True,
    )
    np.testing.assert_array_equal(opted_in.edc_db, raw.edc_db)


@pytest.mark.parametrize("name", ["schroeder_curve", "_curve_from_truncation"])
def test_noise_subtraction_signatures_remain_opt_in(name: str) -> None:
    import inspect

    from reverbscope.core import decay

    assert inspect.signature(getattr(decay, name)).parameters["subtract_noise"].default is False


def test_public_ir_analysis_matches_explicitly_unsubtracted_builder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from functools import partial

    from reverbscope.core import decay
    from reverbscope.core.pipeline import analyze_impulse_response
    from reverbscope.models.audio import AudioSignal

    rate = 8000
    time = np.arange(2 * rate) / rate
    signal = np.exp(-math.log(1000) * time / 0.8)
    signal[time >= 0.8 * 50 / 60] = 0
    audio = AudioSignal(signal, rate)
    default = analyze_impulse_response(audio).decay.to_dict()
    monkeypatch.setattr(
        decay, "_curve_from_truncation", partial(decay._curve_from_truncation, subtract_noise=False)
    )
    assert analyze_impulse_response(audio).decay.to_dict() == default
