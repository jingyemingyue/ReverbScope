from __future__ import annotations

import json

import numpy as np
import pytest

from reverbscope.core.decay import (
    MIN_BT_PRODUCT,
    analyze_band,
    analyze_decay,
    decay_lead_in_s,
    estimate_truncation,
    find_onset,
    fit_decay_metric,
    schroeder_curve,
    straightness_limits,
)
from reverbscope.core.filters import iec_band
from reverbscope.models.audio import FloatArray
from reverbscope.models.configuration import AnalysisSettings
from reverbscope.models.result import (
    EXCITATION_SOURCE_SETTINGS,
    BandDecay,
    DecayMetric,
    ExcitationBand,
    Validity,
)
from reverbscope.models.result_load import band_decay_from_dict
from tests.conftest import DECAY_CONSTANT, exponential_decay_ir, make_rir


def test_exact_exponential_decay_gives_exact_rt60(sample_rate: int) -> None:
    rt60 = 0.5
    n = int(1.2 * sample_rate)
    t = np.arange(n) / sample_rate
    # Deterministic alternating-sign exponential: the EDC is exactly exponential.
    ir = np.exp(-DECAY_CONSTANT * t / (2 * rt60)) * np.where(np.arange(n) % 2 == 0, 1.0, -1.0)
    band = analyze_band(ir, sample_rate, None, noise_margin_db=10.0)
    for metric in (band.edt, band.t20, band.t30):
        assert metric.validity is Validity.VALID
        assert metric.seconds == pytest.approx(rt60, rel=0.01)
        assert metric.nonlinearity_permille is not None and metric.nonlinearity_permille < 1.0
    assert band.rt60_estimate_s == pytest.approx(rt60, rel=0.01)
    assert band.rt60_basis == "T30"
    assert abs(band.curvature_percent or 0.0) < 2.0


@pytest.mark.parametrize("rt60", [0.25, 0.6, 1.2])
def test_noisy_exponential_decay_within_five_percent(sample_rate: int, rt60: float) -> None:
    ir = exponential_decay_ir(sample_rate, rt60, length_s=2.0 * rt60)
    band = analyze_band(ir, sample_rate, None, noise_margin_db=10.0)
    assert band.t20.validity is Validity.VALID
    assert band.t30.validity is Validity.VALID
    assert band.t20.seconds == pytest.approx(rt60, rel=0.05)
    assert band.t30.seconds == pytest.approx(rt60, rel=0.05)


def test_noise_floor_limits_available_range(sample_rate: int) -> None:
    rt60 = 0.5
    ir = exponential_decay_ir(sample_rate, rt60, length_s=1.5)
    rng = np.random.default_rng(7)
    # Noise floor about 30 dB below the start level.
    ir = ir + rng.normal(0.0, 10 ** (-30 / 20), ir.shape[0])
    band = analyze_band(ir, sample_rate, None, noise_margin_db=10.0)
    assert 24.0 < band.peak_to_noise_db < 36.0
    assert band.edt.validity is Validity.VALID
    assert band.t20.validity is Validity.INSUFFICIENT_RANGE
    assert band.t30.validity is Validity.INSUFFICIENT_RANGE
    assert band.t20.seconds is None and band.t30.seconds is None
    assert "Insufficient decay range" in (band.t20.reason or "")
    assert band.rt60_estimate_s is None


def test_truncation_point_near_noise_crossing(sample_rate: int) -> None:
    rt60 = 0.5
    ir = exponential_decay_ir(sample_rate, rt60, length_s=1.5)
    rng = np.random.default_rng(3)
    ir = ir + rng.normal(0.0, 10 ** (-40 / 20), ir.shape[0])
    trunc = estimate_truncation(ir**2, sample_rate)
    # Decay reaches -40 dB at rt60 * 40 / 60
    expected = rt60 * 40.0 / 60.0
    assert trunc.truncation_index / sample_rate == pytest.approx(expected, rel=0.25)
    assert trunc.late_slope_db_per_s is not None and trunc.late_slope_db_per_s < 0.0
    assert trunc.noise_floor_db == pytest.approx(-40.0 + 10 * np.log10(1.0), abs=3.0)


def test_schroeder_curve_is_monotonic_and_starts_at_zero(sample_rate: int) -> None:
    ir = exponential_decay_ir(sample_rate, 0.4, length_s=0.8)
    curve = schroeder_curve(ir, sample_rate)
    assert curve.edc_db[0] == pytest.approx(0.0)
    assert np.all(np.diff(curve.edc_db) <= 1e-9)


def test_fit_reports_insufficient_when_curve_short(sample_rate: int) -> None:
    ir = exponential_decay_ir(sample_rate, 2.0, length_s=0.3)
    curve = schroeder_curve(ir, sample_rate, compensate=False)
    metric = fit_decay_metric("T30", curve, (-5.0, -35.0), noise_margin_db=10.0)
    assert metric.validity is not Validity.VALID
    assert metric.seconds is None


def test_octave_band_decay_and_bt_flag(sample_rate: int) -> None:
    rt60 = 0.6
    ir = exponential_decay_ir(sample_rate, rt60, length_s=1.2)
    result = analyze_decay(ir, sample_rate, AnalysisSettings())
    labels = [b.band_label for b in result.bands]
    assert labels == ["63 Hz", "125 Hz", "250 Hz", "500 Hz", "1 kHz", "2 kHz", "4 kHz", "8 kHz"]
    # A9: nominal labels / centre values, IEC 61260-1 base-10 exact mid-band and edges.
    low = result.bands[0]
    assert low.center_hz == 63.0
    assert low.mid_band_hz == pytest.approx(63.0957, rel=1e-5)
    assert low.low_hz == pytest.approx(44.6684, rel=1e-5)
    assert low.high_hz == pytest.approx(89.1251, rel=1e-5)
    one_khz = next(b for b in result.bands if b.center_hz == 1000.0)
    assert one_khz.t30.validity is Validity.VALID
    assert one_khz.t30.seconds == pytest.approx(rt60, rel=0.1)
    assert one_khz.filter_bt_product is not None and one_khz.filter_bt_product > MIN_BT_PRODUCT
    assert one_khz.filter_warning is None


def test_short_decay_in_low_band_is_flagged_unreliable(sample_rate: int) -> None:
    band = iec_band(63.0, 1)
    # A 30 ms decay in the 63 Hz band gives B*T ~ 1.3 < 4.
    ir = exponential_decay_ir(sample_rate, 0.03, length_s=0.5)
    from reverbscope.core.filters import apply_bandpass, bandpass_sos

    filtered = apply_bandpass(ir, bandpass_sos(band, sample_rate))
    result = analyze_band(filtered, sample_rate, band, noise_margin_db=10.0)
    assert result.filter_bt_product is not None and result.filter_bt_product < MIN_BT_PRODUCT
    assert result.filter_warning is not None
    assert result.t20.validity in (Validity.UNRELIABLE, Validity.INSUFFICIENT_RANGE)
    assert result.rt60_estimate_s is None
    # B2: the curvature is only computed from VALID T20 and T30.
    assert result.curvature_percent is None


def test_bands_that_do_not_fit_are_skipped() -> None:
    sr = 44100
    ir = exponential_decay_ir(sr, 0.3, length_s=0.6)
    settings = AnalysisSettings(octave_bands_hz=(1000.0, 16000.0))
    result = analyze_decay(ir, sr, settings)
    assert [b.band_label for b in result.bands] == ["1 kHz"]


# --- B1 / A7: decay onset, time origin, EDT validity --------------------------


def _alternating_exponential(sample_rate: int, rt60: float, length_s: float) -> FloatArray:
    """Deterministic alternating-sign exponential: its EDC is exactly exponential."""
    n = int(length_s * sample_rate)
    t = np.arange(n) / sample_rate
    sign = np.where(np.arange(n) % 2 == 0, 1.0, -1.0)
    return np.asarray(np.exp(-DECAY_CONSTANT * t / (2 * rt60)) * sign, dtype=np.float64)


def _metrics(band: BandDecay) -> tuple[DecayMetric, DecayMetric, DecayMetric]:
    return band.edt, band.t20, band.t30


def _assert_same_metrics(a: BandDecay, b: BandDecay, rel: float = 0.02) -> None:
    for ma, mb in zip(_metrics(a), _metrics(b), strict=True):
        assert ma.validity is mb.validity, (a.band_label, ma, mb)
        if ma.seconds is None:
            assert mb.seconds is None
        else:
            assert mb.seconds == pytest.approx(ma.seconds, rel=rel), (a.band_label, ma, mb)


def test_silence_before_the_direct_sound_does_not_change_the_decay(sample_rate: int) -> None:
    """B1/A7: the old analysis started at the loudest 20 ms block, so a 5 ms
    pre-delay turned an EDT of 'fewer than 3 samples' into 1.03 s (valid)."""
    ir = make_rir(sample_rate, rt60_s=0.2, diffuse_level=0.01, length_s=1.0)  # DRR +11.6 dB
    settings = AnalysisSettings()
    reference_band = analyze_band(ir, sample_rate, None, noise_margin_db=10.0)
    reference_decay = analyze_decay(ir, sample_rate, settings, direct_index=0)
    for prefix in (240, 9600):
        x = np.concatenate([np.zeros(prefix), ir])
        band = analyze_band(x, sample_rate, None, noise_margin_db=10.0)
        _assert_same_metrics(reference_band, band)
        assert band.onset_time_s == pytest.approx(prefix / sample_rate)
        decay = analyze_decay(x, sample_rate, settings, direct_index=prefix)
        for ra, rb in zip(
            (reference_decay.broadband, *reference_decay.bands),
            (decay.broadband, *decay.bands),
            strict=True,
        ):
            _assert_same_metrics(ra, rb)
            assert rb.onset_time_s == pytest.approx(ra.onset_time_s)
    assert reference_band.edt.validity is not Validity.VALID
    assert reference_band.t30.validity is Validity.VALID
    assert reference_band.t30.seconds == pytest.approx(0.2, rel=0.05)


@pytest.mark.parametrize("rt60", [0.15, 0.3])
def test_exact_exponential_after_a_pre_delay_gives_exact_edt(sample_rate: int, rt60: float) -> None:
    """B1: with 5 ms of silence in front the old EDT was 8 % too long at 0.15 s."""
    pre = round(0.005 * sample_rate)
    x = np.concatenate([np.zeros(pre), _alternating_exponential(sample_rate, rt60, 2 * rt60 + 0.3)])
    for direct in (None, pre):
        band = analyze_band(x, sample_rate, None, noise_margin_db=10.0, direct_index=direct)
        assert band.edt.validity is Validity.VALID
        assert band.edt.seconds == pytest.approx(rt60, rel=0.01)
        assert band.t30.seconds == pytest.approx(rt60, rel=0.01)


@pytest.mark.parametrize("seed", [0, 1, 2])
@pytest.mark.parametrize("diffuse", [0.005, 0.01])
def test_strong_direct_sound_never_gives_a_valid_long_edt(
    sample_rate: int, seed: int, diffuse: float
) -> None:
    """B1: DRR +11.6 dB and more; EDT must not be VALID above 1.5 * T30."""
    ir = make_rir(
        sample_rate, rt60_s=0.2, diffuse_level=diffuse, length_s=1.0, seed=seed, start_delay_s=0.005
    )
    result = analyze_decay(ir, sample_rate, AnalysisSettings(), direct_index=240)
    assert result.broadband.edt.validity is not Validity.VALID
    assert "direct sound" in (result.broadband.edt.reason or "")
    for band in (result.broadband, *result.bands):
        if band.edt.validity is Validity.VALID:
            assert band.t30.seconds is not None and band.edt.seconds is not None
            assert band.edt.seconds <= 1.5 * band.t30.seconds


def test_reverberant_position_keeps_a_valid_edt(sample_rate: int) -> None:
    """The EDT rule only withholds EDT when the direct sound dominates."""
    ir = make_rir(sample_rate, rt60_s=0.5, diffuse_level=0.03, length_s=1.2)  # DRR about -2 dB
    result = analyze_decay(ir, sample_rate, AnalysisSettings(), direct_index=0)
    for band in (result.broadband, *result.bands):
        assert band.edt.validity is Validity.VALID, band.band_label
    assert result.broadband.edt.seconds == pytest.approx(0.5, rel=0.05)


def test_decay_times_share_the_direct_sound_origin(sample_rate: int) -> None:
    """B1: the curve started 20 ms after the direct sound (loudest block) and its
    time axis did not match truncation_time_s."""
    rt60, pre = 2.0, 240
    n = int(3 * rt60 * sample_rate)
    t = np.arange(n) / sample_rate
    rng = np.random.default_rng(0)
    reverberant_energy = 10 ** (20 / 10)  # DRR -20 dB
    sigma2 = reverberant_energy * DECAY_CONSTANT / (rt60 * sample_rate)
    ir = rng.normal(0.0, 1.0, n) * np.sqrt(sigma2) * np.exp(-DECAY_CONSTANT * t / (2 * rt60))
    ir[0] += 1.0
    x = np.concatenate([np.zeros(pre), ir]) + np.random.default_rng(9).normal(0.0, 1e-9, n + pre)
    result = analyze_decay(
        x, sample_rate, AnalysisSettings(octave_bands_hz=(1000.0,)), direct_index=pre
    )
    for band in (result.broadband, *result.bands):
        assert band.onset_time_s is not None and band.truncation_time_s is not None
        assert band.edc_time_s[0] == pytest.approx(band.onset_time_s)
        assert band.truncation_time_s == pytest.approx(band.edc_time_s[-1], abs=0.002)
    assert result.broadband.onset_time_s == pytest.approx(0.0, abs=1.0 / sample_rate)
    # The time-reversed band filter moves the band's onset slightly ahead.
    assert -0.01 < result.bands[0].onset_time_s < 0.0
    assert result.broadband.edt.seconds == pytest.approx(rt60, rel=0.02)
    assert result.time_origin.startswith("direct sound")


def test_onset_is_the_first_sample_within_20_db_of_the_maximum() -> None:
    power = np.array([0.0, 1e-4, 0.005, 0.02, 1.0, 0.5, 0.0])
    assert find_onset(power) == 3
    assert find_onset(power, search_start=4) == 4
    assert find_onset(np.zeros(4), search_start=2) == 2


def test_lead_in_covers_the_lowest_band() -> None:
    assert decay_lead_in_s(AnalysisSettings()) == pytest.approx(0.2)
    low = AnalysisSettings(octave_bands_hz=(16.0, 1000.0))
    assert decay_lead_in_s(low) == pytest.approx(5.0 / iec_band(16.0).bandwidth_hz)


# --- B2: non-straight decays ----------------------------------------------------


def _double_slope(sample_rate: int, seed: int = 0) -> FloatArray:
    n = 5 * sample_rate
    t = np.arange(n) / sample_rate
    envelope = np.exp(-DECAY_CONSTANT * t / 0.3) + 10 ** (-25 / 10) * np.exp(
        -DECAY_CONSTANT * t / 2.0
    )
    rng = np.random.default_rng(seed)
    x = rng.normal(0.0, 1.0, n) * np.sqrt(envelope)
    return np.asarray(x + np.random.default_rng(3).normal(0.0, 1e-6, n), dtype=np.float64)


def test_double_slope_decay_has_no_single_reverberation_time(sample_rate: int) -> None:
    """B2: 0.3 s + 2.0 s at -25 dB gave T30 = 1.50 s (valid), matching neither slope."""
    x = _double_slope(sample_rate)
    band = analyze_band(x, sample_rate, None, noise_margin_db=10.0)
    assert band.rt60_estimate_s is None and band.rt60_basis is None
    assert band.t20.validity is Validity.UNRELIABLE
    assert band.t30.validity is Validity.UNRELIABLE
    assert band.curvature_percent is not None and band.curvature_percent > 50.0
    assert any("not straight" in w for w in band.warnings)
    assert "not straight" in (band.t30.reason or "")

    bands = (250.0, 500.0, 1000.0, 2000.0, 4000.0, 8000.0)
    result = analyze_decay(x, sample_rate, AnalysisSettings(octave_bands_hz=bands))
    for b in (result.broadband, *result.bands):
        assert b.rt60_estimate_s is None, b.band_label
        assert any("not straight" in w for w in b.warnings), b.band_label
    assert any("not straight" in note for note in result.notes)


def test_single_slope_decays_are_not_flagged_as_curved(sample_rate: int) -> None:
    """B2 false positives (the thresholds were calibrated on a larger Monte Carlo)."""
    total = 0
    for rt60 in (0.3, 0.8, 1.6):
        for seed in (0, 1):
            ir = make_rir(
                sample_rate, rt60_s=rt60, diffuse_level=0.03, length_s=2.2 * rt60 + 0.3, seed=seed
            )
            noise = np.random.default_rng(seed + 10).normal(0.0, 10 ** (-85 / 20), ir.shape[0])
            result = analyze_decay(ir + noise, sample_rate, AnalysisSettings(), direct_index=0)
            for band in (result.broadband, *result.bands):
                if band.curvature_percent is None:
                    continue
                total += 1
                assert not band.warnings, (rt60, seed, band.band_label, band.warnings)
                assert band.rt60_estimate_s is not None
    assert total >= 50


def test_strong_early_reflection_makes_the_broadband_decay_curved(sample_rate: int) -> None:
    """A -6 dB reflection that carries more energy than the reverberant tail
    bends the broadband EDC: T20 and T30 disagree by more than 10 %."""
    ir = make_rir(sample_rate, rt60_s=0.4, reflections=[(0.018, 0.5)], diffuse_level=0.01)
    result = analyze_decay(
        ir, sample_rate, AnalysisSettings(octave_bands_hz=(1000.0,)), direct_index=0
    )
    broadband = result.broadband
    assert broadband.curvature_percent is not None and broadband.curvature_percent > 15.0
    assert broadband.rt60_estimate_s is None
    assert "early reflections" in broadband.warnings[0]


def test_straightness_limits_widen_for_narrow_bands_and_short_decays() -> None:
    assert straightness_limits(20000.0, 0.5) == (pytest.approx(10.0), pytest.approx(15.0))
    c_low, xi_low = straightness_limits(iec_band(63.0).bandwidth_hz, 0.4)
    assert c_low == pytest.approx(500.0 / np.sqrt(iec_band(63.0).bandwidth_hz * 0.4))
    assert xi_low == pytest.approx(2.0 * c_low)
    assert c_low > 50.0


# --- E1: implausible Lundeby estimates ------------------------------------------


def _decay_with_gated_floor(
    sample_rate: int, floor_db: float, period_s: float = 0.3, duty: float = 0.15
) -> FloatArray:
    """Squared response: RT 0.5 s noise decay plus an intermittent noise floor
    (short-block levels far above the floor's mean, like beating hum harmonics)."""
    n = 3 * sample_rate
    t = np.arange(n) / sample_rate
    rng = np.random.default_rng(4)
    decay = rng.normal(0.0, 1.0, n) ** 2 * np.exp(-DECAY_CONSTANT * t / 0.5)
    gate = ((t % period_s) < duty * period_s).astype(np.float64)
    floor = 10 ** (floor_db / 10) * (gate + 1e-3) * rng.normal(0.0, 1.0, n) ** 2
    return np.asarray(decay + floor, dtype=np.float64)


@pytest.mark.parametrize("rate", [48000, 192000])
def test_runaway_noise_truncation_falls_back_and_is_marked_unreliable(rate: int) -> None:
    """E1: the late slope was fitted to floor blocks (-3 dB/s), the truncation
    ran to the end of the response and T30 = 9.8 s was reported as valid."""
    power = _decay_with_gated_floor(rate, -40.0)
    trunc = estimate_truncation(power, rate)
    assert trunc.problem is not None and "late decay slope" in trunc.problem
    assert trunc.iterative_truncation_index is not None
    assert trunc.iterative_truncation_index / rate > 2.5
    assert trunc.truncation_index / rate < 0.6  # preliminary crosspoint
    assert trunc.late_slope_db_per_s is not None and trunc.late_slope_db_per_s < -80.0

    band = analyze_band(np.sqrt(power), rate, None, noise_margin_db=10.0)
    assert band.rt60_estimate_s is None
    assert band.t30.validity is Validity.UNRELIABLE
    assert band.t30.seconds == pytest.approx(0.5, rel=0.15)
    assert "noise truncation is not trustworthy" in band.warnings[0]
    assert band.truncation_time_s is not None and band.truncation_time_s < 0.6


def test_rejected_truncation_that_does_not_change_the_result_keeps_it_valid(
    sample_rate: int,
) -> None:
    power = _decay_with_gated_floor(sample_rate, -50.0)
    assert estimate_truncation(power, sample_rate).problem is not None
    band = analyze_band(np.sqrt(power), sample_rate, None, noise_margin_db=10.0)
    assert band.t30.validity is Validity.VALID
    assert band.t30.seconds == pytest.approx(0.5, rel=0.05)
    assert not band.warnings


@pytest.mark.parametrize("rate", [48000, 192000])
def test_preliminary_regression_stops_where_the_decay_reaches_the_floor(rate: int) -> None:
    """E1: a slowly modulated floor rose above noise + 10 dB after the decay; the
    preliminary regression ran over it (T30 = 10 s, valid)."""
    n = 3 * rate
    t = np.arange(n) / rate
    rng = np.random.default_rng(4)
    decay = rng.normal(0.0, 1.0, n) ** 2 * np.exp(-DECAY_CONSTANT * t / 0.5)
    modulation = (1 + 0.95 * np.sin(2 * np.pi * 1.0 * t)) ** 2
    power = decay + 1e-5 * modulation * rng.normal(0.0, 1.0, n) ** 2
    band = analyze_band(np.sqrt(power), rate, None, noise_margin_db=10.0)
    assert band.t30.validity is Validity.VALID
    assert band.t30.seconds == pytest.approx(0.5, rel=0.1)
    assert band.truncation_time_s is not None and band.truncation_time_s < 0.6


# --- A2/B3: bands outside the excitation ------------------------------------------


def test_bands_outside_the_excitation_are_withheld(sample_rate: int) -> None:
    ir = exponential_decay_ir(sample_rate, 0.5, length_s=1.2)
    excitation = ExcitationBand(low_hz=250.0, high_hz=5000.0, source=EXCITATION_SOURCE_SETTINGS)
    result = analyze_decay(ir, sample_rate, AnalysisSettings(), excitation_band=excitation)
    by_label = {b.band_label: b for b in result.bands}
    assert list(by_label) == [
        "63 Hz",
        "125 Hz",
        "250 Hz",
        "500 Hz",
        "1 kHz",
        "2 kHz",
        "4 kHz",
        "8 kHz",
    ]
    withheld = ["63 Hz", "125 Hz", "250 Hz", "4 kHz", "8 kHz"]
    for label in withheld:
        band = by_label[label]
        for metric in _metrics(band):
            assert metric.validity is Validity.OUTSIDE_EXCITATION
            assert metric.seconds is None
            assert "excitation range" in (metric.reason or "")
        assert band.c50.validity is Validity.OUTSIDE_EXCITATION
        assert band.c80.value is None and band.d50.value is None
        assert band.centre_time.validity is Validity.OUTSIDE_EXCITATION
        assert "excitation range" in (band.c50.reason or "")
        assert band.rt60_estimate_s is None and band.curvature_percent is None
        assert band.peak_to_noise_db is None and band.noise_floor_db is None
        assert band.truncation_time_s is None and band.onset_time_s is None
        assert band.filter_bt_product is None and band.edc_db.shape == (0,)
    for label in ("500 Hz", "1 kHz", "2 kHz"):
        assert by_label[label].t30.validity is Validity.VALID
        assert by_label[label].c50.validity is Validity.VALID
    assert any(", ".join(withheld) in note for note in result.notes)
    assert str(Validity.OUTSIDE_EXCITATION) == "outside_excitation_range"
    json.dumps(result.to_dict(), allow_nan=False)
    assert result.time_origin.startswith("start of the analysed signal")


# --- A5: marking a whole decay result unreliable ----------------------------------


def test_with_all_unreliable_marks_every_metric(sample_rate: int) -> None:
    ir = exponential_decay_ir(sample_rate, 0.25, length_s=0.5)
    rng = np.random.default_rng(7)
    ir = ir + rng.normal(0.0, 10 ** (-30 / 20), ir.shape[0])
    result = analyze_decay(ir, sample_rate, AnalysisSettings(octave_bands_hz=(63.0, 1000.0)))
    before = [m for b in (result.broadband, *result.bands) for m in _metrics(b)]
    assert any(m.validity is Validity.VALID for m in before)
    assert any(m.validity is Validity.INSUFFICIENT_RANGE for m in before)
    assert result.broadband.c50.validity is Validity.VALID
    marked = result.with_all_unreliable("the recording clips")
    after = [m for b in (marked.broadband, *marked.bands) for m in _metrics(b)]
    for old, new in zip(before, after, strict=True):
        assert new.validity is not Validity.VALID
        assert new.seconds == old.seconds
        if old.validity in (Validity.VALID, Validity.UNRELIABLE):
            assert new.validity is Validity.UNRELIABLE
            assert "the recording clips" in (new.reason or "")
            if old.reason:
                assert (new.reason or "").startswith(old.reason)
        else:
            assert new == old
    for band in (marked.broadband, *marked.bands):
        assert band.rt60_estimate_s is None and band.rt60_basis is None
        assert band.curvature_percent is None
    assert marked.broadband.c50.validity is Validity.UNRELIABLE
    assert marked.broadband.c50.value == result.broadband.c50.value
    assert "the recording clips" in (marked.broadband.c50.reason or "")
    assert marked.notes[-1].endswith("the recording clips")
    # Idempotent reason handling.
    again = marked.with_all_unreliable("the recording clips")
    assert again.broadband.t30.reason == marked.broadband.t30.reason


def _expected_clarity_db(split_s: float, rt60: float) -> float:
    """C_te of an infinite exponential whose power falls 60 dB in ``rt60``."""
    tau = rt60 / DECAY_CONSTANT
    return float(10.0 * np.log10(np.exp(split_s / tau) - 1.0))


def test_exact_exponential_has_iso_energy_ratios(sample_rate: int) -> None:
    """C50, C80, D50 and centre time of a pure exponential match the closed form."""
    rt60 = 0.5
    band = analyze_band(
        _alternating_exponential(sample_rate, rt60, 1.2),
        sample_rate,
        None,
        noise_margin_db=10.0,
    )
    tau = rt60 / DECAY_CONSTANT
    assert band.c50.validity is Validity.VALID
    assert band.c80.validity is Validity.VALID
    assert band.d50.validity is Validity.VALID
    assert band.centre_time.validity is Validity.VALID
    assert band.c50.value == pytest.approx(_expected_clarity_db(0.05, rt60), abs=0.4)
    assert band.c80.value == pytest.approx(_expected_clarity_db(0.08, rt60), abs=0.4)
    assert band.d50.value == pytest.approx(100.0 * (1.0 - np.exp(-0.05 / tau)), abs=1.0)
    assert band.centre_time.value == pytest.approx(tau, abs=0.002)
    assert band.c50.unit == "dB" and band.d50.unit == "%" and band.centre_time.unit == "s"


def test_energy_ratios_follow_the_direct_sound_not_the_file_start(sample_rate: int) -> None:
    rt60 = 0.5
    ir = _alternating_exponential(sample_rate, rt60, 1.2)
    pre = 1000
    plain = analyze_band(ir, sample_rate, None, noise_margin_db=10.0, direct_index=0)
    shifted = analyze_band(
        np.concatenate([np.zeros(pre), ir]),
        sample_rate,
        None,
        noise_margin_db=10.0,
        direct_index=pre,
    )
    assert shifted.c50.value == pytest.approx(plain.c50.value, abs=0.05)
    assert shifted.c80.value == pytest.approx(plain.c80.value, abs=0.05)
    assert shifted.d50.value == pytest.approx(plain.d50.value, abs=0.2)
    assert shifted.centre_time.value == pytest.approx(plain.centre_time.value, abs=0.001)


def test_energy_ratios_need_twenty_db_of_decay(sample_rate: int) -> None:
    ir = exponential_decay_ir(sample_rate, 0.4, length_s=1.0)
    rng = np.random.default_rng(1)
    ir = ir + rng.normal(0.0, 10 ** (-12 / 20), ir.shape[0])
    band = analyze_band(ir, sample_rate, None, noise_margin_db=10.0)
    assert band.peak_to_noise_db is not None and band.peak_to_noise_db < 20.0
    assert band.c50.validity is Validity.INSUFFICIENT_RANGE
    assert band.c80.value is None and band.d50.value is None and band.centre_time.value is None
    assert "early/late energy ratio" in (band.c50.reason or "")


def test_an_arrival_inside_50_ms_raises_c50(sample_rate: int) -> None:
    """A copy of the direct sound inside 50 ms raises C50; the same copy at 120 ms lowers it."""
    tail = 0.05 * _alternating_exponential(sample_rate, 0.6, 1.5)
    early = tail.copy()
    late = tail.copy()
    early[0] = 1.0
    late[0] = 1.0
    early[round(0.012 * sample_rate)] += 1.0
    late[round(0.120 * sample_rate)] += 1.0
    early_band = analyze_band(early, sample_rate, None, noise_margin_db=10.0, direct_index=0)
    late_band = analyze_band(late, sample_rate, None, noise_margin_db=10.0, direct_index=0)
    assert early_band.c50.validity is Validity.VALID
    assert late_band.c50.validity is Validity.VALID
    assert early_band.c50.value is not None and late_band.c50.value is not None
    assert early_band.c50.value > late_band.c50.value + 3.0


def test_energy_parameters_round_trip_and_older_files_omit_them(sample_rate: int) -> None:
    band = analyze_band(
        _alternating_exponential(sample_rate, 0.4, 1.0),
        sample_rate,
        None,
        noise_margin_db=10.0,
    )
    again = band_decay_from_dict(band.to_dict())
    assert again.c50.value == pytest.approx(band.c50.value)
    assert again.centre_time.value == pytest.approx(band.centre_time.value)
    payload = band.to_dict()
    for key in ("c50", "c80", "d50", "centre_time"):
        del payload[key]
    old = band_decay_from_dict(payload)
    assert old.c50.validity is Validity.NOT_COMPUTED
    assert old.c50.value is None
    assert old.centre_time.validity is Validity.NOT_COMPUTED
    assert old.edt.seconds == pytest.approx(band.edt.seconds)
