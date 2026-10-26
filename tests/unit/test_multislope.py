"""Single- versus double-slope fit of the energy decay (core/multislope.py).

Synthetic decays with known decay times and amplitude ratios: Gaussian noise
with one or two exponential envelopes plus a stationary noise floor. The
tolerances are regression choices for these fixed seeds, not accuracy claims
for real rooms (see docs/validation/aachen-nikolauskapelle.md for measured
data).
"""

from __future__ import annotations

import json
import math

import numpy as np
import pytest

from reverbscope.core.decay import analyze_band, analyze_decay
from reverbscope.core.filters import apply_bandpass, bandpass_sos, iec_band
from reverbscope.core.multislope import (
    DELTA_BIC_MIN,
    MIN_DECAY_RANGE_DB,
    effective_points,
    fit_multi_slope,
    raw_energy_decay,
)
from reverbscope.models.configuration import AnalysisSettings
from reverbscope.models.result import (
    DECAY_60_DB_NEPER,
    AnalysisResult,
    BandDecay,
    DecaySlopeModel,
    MultiSlopeFit,
    Validity,
)
from reverbscope.models.result_load import band_decay_from_dict, multi_slope_from_dict

RATE = 48_000
LEAD = int(0.2 * RATE)


def decay(
    t1: float,
    t2: float | None = None,
    late_db: float | None = None,
    *,
    noise_db: float = -75.0,
    seed: int = 0,
    seconds: float | None = None,
) -> np.ndarray:
    """Noise with one or two exponential envelopes; ``late_db`` is the slow
    part's power at t = 0 relative to the fast part's (dB)."""
    rng = np.random.default_rng(seed)
    length = seconds if seconds is not None else 1.5 * (t2 or t1) + 0.2
    t = np.arange(int(length * RATE)) / RATE
    power = np.exp(-DECAY_60_DB_NEPER * t / t1)
    if t2 is not None and late_db is not None:
        power = power + 10.0 ** (late_db / 10.0) * np.exp(-DECAY_60_DB_NEPER * t / t2)
    h = rng.standard_normal(t.size) * np.sqrt(power)
    h += rng.standard_normal(t.size) * 10.0 ** (noise_db / 20.0)
    return np.concatenate([np.zeros(LEAD), h])


def band_fit(signal: np.ndarray, nominal_hz: float | None) -> BandDecay:
    """One band through the public per-band analysis, direct sound at LEAD."""
    band = iec_band(nominal_hz, 1) if nominal_hz is not None else None
    filtered = (
        apply_bandpass(signal, bandpass_sos(band, RATE), time_reversed=True)
        if band is not None
        else signal
    )
    return analyze_band(filtered, RATE, band, noise_margin_db=10.0, direct_index=LEAD)


def expected_ratio_db(t1: float, t2: float, late_db: float) -> float:
    """EDC amplitude ratio A2/A1 (dB) of two exponential power envelopes."""
    return late_db + 10.0 * math.log10(t2 / t1)


@pytest.mark.parametrize("nominal", [None, 250.0, 1000.0, 4000.0])
@pytest.mark.parametrize(("t1", "t2", "late_db"), [(0.4, 1.6, -25.0), (1.0, 3.0, -25.0)])
def test_double_slope_is_recovered(
    nominal: float | None, t1: float, t2: float, late_db: float
) -> None:
    result = band_fit(decay(t1, t2, late_db, seed=3), nominal)
    fit = result.multi_slope
    assert fit is not None
    assert fit.validity is Validity.VALID
    assert fit.selected_slopes == 2
    assert fit.delta_bic is not None and fit.delta_bic >= DELTA_BIC_MIN
    model = fit.selected
    assert model is not None
    assert model.decay_times_s[0] == pytest.approx(t1, rel=0.15)
    assert model.decay_times_s[1] == pytest.approx(t2, rel=0.10)
    ratio = model.amplitudes_db[1] - model.amplitudes_db[0]
    assert ratio == pytest.approx(expected_ratio_db(t1, t2, late_db), abs=3.0)
    # The turning point is where the two exponentials are equal, on the model.
    assert fit.knee_time_s is not None and fit.knee_level_db is not None
    assert fit.fit_start_s is not None and fit.fit_end_s is not None
    assert fit.fit_start_s < fit.knee_time_s < fit.fit_end_s
    a1, a2 = model.amplitudes
    knee = math.log(a1 / a2) / (DECAY_60_DB_NEPER * (1.0 / t1 - 1.0 / t2))
    assert fit.knee_time_s == pytest.approx(knee, rel=0.25)
    assert -45.0 < fit.knee_level_db < -10.0


#: 63 Hz at 0.3 s (B*T = 13) is covered by the rate test below.
SINGLE_CASES = [
    (nominal, t60)
    for nominal in (None, 63.0, 125.0, 250.0, 500.0, 1000.0, 4000.0)
    for t60 in (0.3, 0.8, 1.5, 3.0)
    if (nominal, t60) != (63.0, 0.3)
]


@pytest.mark.parametrize(("nominal", "t60"), SINGLE_CASES)
def test_single_slope_rooms_are_not_split(nominal: float | None, t60: float) -> None:
    result = band_fit(decay(t60, seed=1), nominal)
    fit = result.multi_slope
    assert fit is not None
    assert fit.selected_slopes == 1
    model = fit.selected
    assert model is not None
    assert model.slope_count == 1
    assert model.decay_times_s[0] == pytest.approx(t60, rel=0.15)
    assert fit.knee_time_s is None and fit.knee_level_db is None


def test_narrowest_band_rarely_splits_a_short_single_slope() -> None:
    """63 Hz octave, T = 0.3 s (B*T = 13): the EDC fluctuates by about 1.5 dB
    rms and a second slope occasionally fits the last decibels above the
    noise. Documented limit: at most 2 of 24 seeds (1 of 24 when written)."""
    split = sum(
        1
        for seed in range(24)
        if (fit := band_fit(decay(0.3, seed=seed), 63.0).multi_slope) is not None
        and fit.selected_slopes == 2
    )
    assert split <= 2


def test_single_slope_with_a_strong_direct_sound_is_not_split() -> None:
    signal = decay(1.0, seed=2)
    signal[LEAD] += 4.0 * math.sqrt(float(np.sum(signal**2)))
    fit = band_fit(signal, 1000.0).multi_slope
    assert fit is not None
    assert fit.selected_slopes == 1


def test_iso_metrics_are_unchanged_by_the_fit() -> None:
    """The fit is additive: EDT/T20/T30 are fitted exactly as before."""
    from reverbscope.core.decay import (
        _curve_from_truncation,
        _fit_all,
        estimate_truncation,
        find_onset,
    )

    signal = decay(0.5, 2.0, -20.0, seed=4)
    result = band_fit(signal, None)
    power = signal**2
    onset = find_onset(power, search_start=0)
    trunc = estimate_truncation(power[onset:], RATE, bandwidth_hz=RATE / 2.0)
    curve = _curve_from_truncation(
        power, RATE, onset, trunc, compensate=True, time_origin_index=LEAD
    )
    first = max(0, LEAD + round(0.0005 * RATE) + 1 - onset)
    edt, t20, t30 = _fit_all(curve, 10.0, first)
    assert result.t20.seconds == t20.seconds
    assert result.t30.seconds == t30.seconds
    assert result.edt.seconds == edt.seconds


def test_insufficient_range_has_no_numbers() -> None:
    signal = decay(0.8, noise_db=-25.0, seed=5)
    fit = band_fit(signal, 1000.0).multi_slope
    assert fit is not None
    assert fit.validity is Validity.INSUFFICIENT_RANGE
    assert fit.selected_slopes is None
    assert fit.models == ()
    assert fit.reason is not None and f"{MIN_DECAY_RANGE_DB:.0f} dB needed" in fit.reason


def test_direct_call_validates_short_and_silent_inputs() -> None:
    silent = np.zeros(RATE)
    fit = fit_multi_slope(
        silent,
        RATE,
        onset=0,
        time_origin_index=0,
        first_index=0,
        decay_range_db=float("nan"),
        bandwidth_hz=None,
    )
    assert fit.validity is Validity.INSUFFICIENT_RANGE
    short = np.exp(-np.arange(50) / 5.0)
    fit = fit_multi_slope(
        short**2,
        RATE,
        onset=0,
        time_origin_index=0,
        first_index=0,
        decay_range_db=60.0,
        bandwidth_hz=None,
    )
    assert fit.validity is Validity.INSUFFICIENT_RANGE
    assert fit.selected_slopes is None


def test_cut_short_response_is_unreliable() -> None:
    signal = decay(0.8, seed=6)
    signal[LEAD + int(0.6 * RATE) :] = 0.0
    signal[-1] = 1e-9
    result = band_fit(signal, None)
    fit = result.multi_slope
    assert fit is not None
    if fit.validity is not Validity.INSUFFICIENT_RANGE:
        assert fit.validity is Validity.UNRELIABLE
        assert fit.reason is not None and "cut short" in fit.reason


def test_narrow_band_short_decay_is_unreliable() -> None:
    # 63 Hz octave (B = 44 Hz) with T = 0.06 s: B*T1 < 4.
    fit = band_fit(decay(0.06, noise_db=-90.0, seed=7, seconds=0.6), 63.0).multi_slope
    assert fit is not None
    if fit.selected_slopes is not None:
        assert fit.validity is Validity.UNRELIABLE
        assert fit.reason is not None and "B*T1" in fit.reason


def test_trailing_digital_silence_is_not_integrated() -> None:
    power = np.concatenate([np.exp(-np.arange(1000) / 100.0), np.zeros(500)])
    times, edc, end = raw_energy_decay(power, 0, 0, 1000)
    assert times.shape[0] == 1000
    assert edc[0] == pytest.approx(1.0)
    assert end == pytest.approx(1.0)


def test_effective_points_of_correlated_residuals() -> None:
    rng = np.random.default_rng(0)
    white = rng.standard_normal(100)
    assert effective_points(white) > 50.0
    smooth = np.convolve(rng.standard_normal(140), np.ones(40) / 40.0, mode="valid")[:100]
    assert effective_points(smooth) < 20.0
    assert effective_points(np.zeros(100)) == 100.0


def test_model_evaluation_matches_the_published_form() -> None:
    model = DecaySlopeModel(
        slope_count=2,
        decay_times_s=(0.5, 2.0),
        amplitudes=(0.9, 0.1),
        noise_term=1e-6,
        bic=0.0,
        rms_residual_db=0.0,
    )
    t = np.array([0.0, 0.5, 1.0])
    end = 3.0
    expected = (
        0.9 * (np.exp(-13.8155 * t / 0.5) - np.exp(-13.8155 * end / 0.5))
        + 0.1 * (np.exp(-13.8155 * t / 2.0) - np.exp(-13.8155 * end / 2.0))
        + 1e-6 * (end - t)
    )
    np.testing.assert_allclose(model.evaluate(t, end), expected, rtol=1e-4)
    assert model.energy_shares_percent == pytest.approx((90.0, 10.0))
    assert model.amplitudes_db[1] == pytest.approx(-10.0)
    # One slope alone is a straight line of -60 dB per T.
    line = model.component_db(1, np.array([0.0, 2.0]))
    assert line[0] - line[1] == pytest.approx(60.0)


def test_round_trip_and_older_files() -> None:
    result = band_fit(decay(0.4, 1.6, -25.0, seed=3), None)
    data = json.loads(json.dumps(result.to_dict()))
    loaded = band_decay_from_dict(data)
    assert loaded.multi_slope is not None
    assert loaded.multi_slope.to_dict() == result.multi_slope.to_dict()  # type: ignore[union-attr]
    # A file written before the fit existed has no key: no fit, nothing invented.
    del data["multi_slope"]
    assert band_decay_from_dict(data).multi_slope is None
    assert multi_slope_from_dict(None) is None


def test_with_all_unreliable_marks_the_fit() -> None:
    result = band_fit(decay(0.4, 1.6, -25.0, seed=3), None)
    marked = result.with_all_unreliable("clipped")
    assert marked.multi_slope is not None
    assert marked.multi_slope.validity is Validity.UNRELIABLE
    assert marked.multi_slope.reason == "clipped"
    assert marked.multi_slope.selected_slopes == 2


def test_marked_unreliable_keeps_stronger_states() -> None:
    fit = MultiSlopeFit(validity=Validity.INSUFFICIENT_RANGE, selected_slopes=None)
    assert fit.marked_unreliable("x") is fit


def test_analyze_decay_reports_every_band_and_schema() -> None:
    from jsonschema import Draft202012Validator

    from reverbscope.core.pipeline import analyze_impulse_response
    from reverbscope.models.audio import AudioSignal
    from reverbscope.schemas import load_schema

    signal = decay(0.4, 1.6, -25.0, seed=8)
    signal[LEAD] = 4.0 * math.sqrt(float(np.sum(signal**2)))
    decay_result = analyze_decay(signal, RATE, AnalysisSettings(), direct_index=LEAD)
    assert decay_result.broadband.multi_slope is not None
    assert all(b.multi_slope is not None for b in decay_result.bands)
    result: AnalysisResult = analyze_impulse_response(
        AudioSignal(signal, RATE), AnalysisSettings(), excitation_band=(20.0, 20_000.0)
    )
    payload = json.loads(json.dumps(result.to_dict()))
    Draft202012Validator(load_schema("result")).validate(payload)
    assert any(
        band["multi_slope"] is not None and band["multi_slope"]["selected_slopes"] == 2
        for band in [payload["decay"]["broadband"], *payload["decay"]["bands"]]
    )
