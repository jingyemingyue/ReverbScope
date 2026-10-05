"""Validity-aware comparison of two analysis results."""

from __future__ import annotations

from dataclasses import replace

import pytest

from roomscope.core.compare import compare
from roomscope.core.pipeline import Reference, analyze, synthetic_recording
from roomscope.interpretation import interpret_comparison
from roomscope.models.comparison import CompareSettings
from roomscope.models.configuration import SweepSettings
from roomscope.models.result import Validity
from tests.conftest import make_rir


def _result(
    sweep: SweepSettings, *, rt60_s: float, reflections: list[tuple[float, float]], seed: int = 0
):
    ir = make_rir(
        sweep.sample_rate, rt60_s=rt60_s, reflections=reflections, diffuse_level=0.02, seed=seed
    )
    return analyze(
        synthetic_recording(sweep, ir, noise_rms=1e-5, seed=seed), Reference.from_settings(sweep)
    )


def test_compare_two_synthetic_positions(short_sweep: SweepSettings) -> None:
    baseline = _result(short_sweep, rt60_s=0.35, reflections=[(0.018, 0.35)])
    candidate = _result(short_sweep, rt60_s=0.55, reflections=[(0.0185, 0.20)], seed=4)
    comparison = compare(baseline, candidate)
    assert comparison.comparable
    assert comparison.common_band is not None
    assert all(item.validity is not None for item in comparison.decay)
    rt = next(item for item in comparison.decay if item.name == "broadband.rt60_estimate")
    assert rt.validity is Validity.VALID
    assert rt.delta_s is not None and rt.delta_s > 0.0
    assert rt.delta_percent is not None
    c50 = next(item for item in comparison.decay if item.name == "broadband.c50")
    assert c50.validity is Validity.VALID
    assert c50.unit == "dB" and c50.delta is not None
    matched = [m for m in comparison.reflections if m.status == "matched"]
    assert matched
    assert matched[0].level_delta_db is not None
    noise = next(item for item in comparison.noise if item.name == "noise.rms_dbfs")
    assert noise.validity is Validity.UNRELIABLE
    assert noise.reason == "gain not declared equal"
    same = compare(baseline, candidate, settings=CompareSettings(same_input_gain=True))
    noise_ok = next(item for item in same.noise if item.name == "noise.rms_dbfs")
    assert noise_ok.validity is Validity.VALID
    findings = interpret_comparison(comparison)
    assert findings
    assert all(f.message for f in findings)
    joined = " ".join(f.message.lower() for f in findings)
    assert "not enough to call the change significant" in joined
    assert "the change is significant" not in joined


def test_compare_not_comparable_when_band_too_narrow(short_sweep: SweepSettings) -> None:
    baseline = _result(short_sweep, rt60_s=0.35, reflections=[(0.018, 0.35)])
    narrow = replace(
        baseline,
        impulse_response=replace(
            baseline.impulse_response,
            excitation_band=replace(baseline.impulse_response.excitation_band, high_hz=30.0)
            if baseline.impulse_response.excitation_band is not None
            else None,
        ),
    )
    comparison = compare(narrow, baseline)
    assert comparison.comparable is False
    assert comparison.decay == ()
    findings = interpret_comparison(comparison)
    assert findings[0].message_id == "comparison.not_comparable"


def test_decay_delta_not_comparable_unless_both_valid(short_sweep: SweepSettings) -> None:
    baseline = _result(short_sweep, rt60_s=0.35, reflections=[(0.018, 0.35)])
    broken = replace(
        baseline,
        decay=replace(
            baseline.decay,
            broadband=replace(
                baseline.decay.broadband,
                t30=replace(
                    baseline.decay.broadband.t30,
                    validity=Validity.INSUFFICIENT_RANGE,
                    seconds=None,
                    reason="synthetic",
                ),
            ),
        ),
    )
    other = _result(short_sweep, rt60_s=0.4, reflections=[(0.018, 0.3)], seed=2)
    comparison = compare(broken, other)
    t30 = next(item for item in comparison.decay if item.name == "broadband.t30")
    assert t30.validity is Validity.NOT_COMPARABLE
    assert t30.delta_s is None
    assert "synthetic" in (t30.reason or "")


def test_placement_refused_unless_both_tier_two(short_sweep: SweepSettings) -> None:
    baseline = _result(short_sweep, rt60_s=0.35, reflections=[(0.018, 0.35)])
    comparison = compare(baseline, baseline)
    place = next(item for item in comparison.placement if item.name == "placement.source_height_m")
    assert place.validity is Validity.NOT_COMPARABLE


# --------------------------------------------------------------- #9 follow-up


def _room(sweep: SweepSettings, *, seed: int, noise_seed: int | None = None, fir=None):
    """The same synthetic room shape; ``seed`` changes the diffuse realisation."""
    import numpy as np
    from scipy.signal import fftconvolve

    ir = make_rir(
        sweep.sample_rate, rt60_s=0.4, reflections=[(0.018, 0.35)], diffuse_level=0.02, seed=seed
    )
    if fir is not None:
        ir = np.asarray(fftconvolve(ir, fir), dtype=np.float64)
    rec = synthetic_recording(
        sweep, ir, noise_rms=1e-5, seed=seed if noise_seed is None else noise_seed
    )
    return analyze(rec, Reference.from_settings(sweep))


def _mad(comparison) -> dict[str, float]:
    assert comparison.frequency_response is not None
    return dict(comparison.frequency_response.band_mad_db)


def test_frequency_response_self_comparison_is_exactly_zero(short_sweep: SweepSettings) -> None:
    import numpy as np

    result = _room(short_sweep, seed=0)
    delta = compare(result, result).frequency_response
    assert delta is not None
    assert np.max(np.abs(delta.difference_db)) == 0.0
    assert all(value == 0.0 for _label, value in delta.band_mad_db)
    assert delta.smoothing_fraction == result.frequency_response.smoothing_fraction


def test_frequency_response_ignores_measurement_noise(short_sweep: SweepSettings) -> None:
    """Same room, different measurement-noise realisation: no audible change."""
    baseline = _room(short_sweep, seed=0)
    repeat = _room(short_sweep, seed=0, noise_seed=5)
    assert max(_mad(compare(baseline, repeat)).values()) < 0.05


def test_frequency_response_delta_is_not_comb_sampling_noise(short_sweep: SweepSettings) -> None:
    """#9: two rooms that differ only in the random diffuse tail.

    Their smoothed high-frequency responses agree to well within a dB. The
    earlier interpolate-then-smooth order point-sampled the comb ripple and
    reported about 2.5-3.3 dB MAD in the 4, 8 and 16 kHz octaves for this pair.
    """
    baseline = _room(short_sweep, seed=0)
    other = _room(short_sweep, seed=7)
    mad = _mad(compare(baseline, other))
    assert mad["4 kHz"] < 1.2
    assert mad["8 kHz"] < 1.0
    assert mad["16 kHz"] < 0.6


def test_frequency_response_recovers_a_known_6_db_shelf(short_sweep: SweepSettings) -> None:
    import numpy as np
    from scipy.signal import firwin2

    sr = short_sweep.sample_rate
    # Linear-phase shelf: 0 dB below 1 kHz, +6.02 dB (x2) above 3 kHz.
    shelf = firwin2(511, [0.0, 1000.0, 3000.0, sr / 2.0], [1.0, 1.0, 2.0, 2.0], fs=sr)
    baseline = _room(short_sweep, seed=0)
    boosted = _room(short_sweep, seed=0, fir=shelf)
    delta = compare(baseline, boosted).frequency_response
    assert delta is not None
    mad = dict(delta.band_mad_db)
    for label in ("63 Hz", "125 Hz", "250 Hz", "500 Hz"):
        assert mad[label] < 0.1, (label, mad[label])
    for label in ("4 kHz", "8 kHz", "16 kHz"):
        assert abs(mad[label] - 6.02) < 0.3, (label, mad[label])
    for frequency in (5000.0, 10000.0):
        index = int(np.argmin(np.abs(delta.frequencies_hz - frequency)))
        assert delta.difference_db[index] == pytest.approx(6.02, abs=0.3)


def test_unsmoothed_results_are_compared_at_the_grid_resolution(
    short_sweep: SweepSettings,
) -> None:
    baseline = _room(short_sweep, seed=0)
    raw_a = replace(
        baseline,
        frequency_response=replace(baseline.frequency_response, smoothing_fraction=0),
    )
    raw_b = replace(raw_a)
    delta = compare(raw_a, raw_b, settings=CompareSettings(log_grid_points_per_octave=12))
    assert delta.frequency_response is not None
    assert delta.frequency_response.smoothing_fraction == 12


def test_decay_bands_missing_on_either_side_are_reported(short_sweep: SweepSettings) -> None:
    result = _room(short_sweep, seed=0)
    bands = result.decay.bands
    assert len(bands) >= 3
    first, last = bands[0].band_label, bands[-1].band_label
    baseline = replace(result, decay=replace(result.decay, bands=bands[1:]))
    candidate = replace(result, decay=replace(result.decay, bands=bands[:-1]))
    by_name = {item.name: item for item in compare(baseline, candidate).decay}
    missing_in_candidate = by_name[f"band.{last}"]
    assert missing_in_candidate.validity is Validity.NOT_COMPARABLE
    assert missing_in_candidate.reason == "band missing from the candidate"
    missing_in_baseline = by_name[f"band.{first}"]
    assert missing_in_baseline.validity is Validity.NOT_COMPARABLE
    assert missing_in_baseline.reason == "band missing from the baseline"
    assert missing_in_baseline.baseline is None
    # And the same pair the other way round reports the mirror image.
    mirrored = {item.name: item for item in compare(candidate, baseline).decay}
    assert mirrored[f"band.{first}"].reason == "band missing from the candidate"
    assert mirrored[f"band.{last}"].reason == "band missing from the baseline"


def test_resonances_are_matched_within_a_sixth_of_an_octave(short_sweep: SweepSettings) -> None:
    from roomscope.models.result import ResonanceCandidate

    def candidate(frequency: float, distinguishable: bool) -> ResonanceCandidate:
        return ResonanceCandidate(
            frequency_hz=frequency,
            level_above_baseline_db=6.0,
            narrowband_decay_20db_s=0.5,
            filter_ringing_20db_s=0.1,
            decay_distinguishable=distinguishable,
            surroundings_decay_20db_s=0.2,
        )

    result = _room(short_sweep, seed=0)
    baseline = replace(
        result,
        resonances=replace(
            result.resonances, candidates=(candidate(50.0, True), candidate(100.0, True))
        ),
    )
    # 53 Hz is 0.08 octave from 50 Hz (matched); 150 Hz is 0.58 octave from
    # 100 Hz (not matched), so 100 Hz disappears and 150 Hz appears.
    other = replace(
        result,
        resonances=replace(
            result.resonances, candidates=(candidate(53.0, False), candidate(150.0, True))
        ),
    )
    matches = compare(baseline, other).resonances
    by_status = {(m.status, m.baseline_hz, m.candidate_hz) for m in matches}
    assert ("matched", 50.0, 53.0) in by_status
    assert ("disappeared", 100.0, None) in by_status
    assert ("appeared", None, 150.0) in by_status
    matched = next(m for m in matches if m.status == "matched")
    assert matched.baseline_decay_distinguishable is True
    assert matched.candidate_decay_distinguishable is False


def test_loopback_path_delay_is_compared_only_when_both_were_compensated(
    short_sweep: SweepSettings,
) -> None:
    from roomscope.models.result import LoopbackResult

    result = _room(short_sweep, seed=0)

    def with_loopback(delay_ms: float | None, applied: bool):
        loopback = LoopbackResult(channel=1, compensation_applied=applied, path_delay_ms=delay_ms)
        return replace(result, impulse_response=replace(result.impulse_response, loopback=loopback))

    valid = compare(with_loopback(6.0, True), with_loopback(7.5, True)).loopback
    assert len(valid) == 1
    assert valid[0].validity is Validity.VALID
    assert valid[0].delta == pytest.approx(1.5)
    refused = compare(with_loopback(6.0, True), with_loopback(7.5, False)).loopback
    assert refused[0].validity is Validity.NOT_COMPARABLE
    assert refused[0].delta is None
    absent = compare(result, with_loopback(7.5, True)).loopback
    assert absent[0].validity is Validity.NOT_COMPARABLE


def test_percent_change_only_for_ratio_scale_units() -> None:
    """In percent of a level in dB the sign followed the baseline's: C50 going
    from -2 to -1 dB read -50 %."""
    from roomscope.core.compare import _delta_from_values

    assert _delta_from_values("broadband.c50", -2.0, -1.0, unit="dB").delta_percent is None
    assert _delta_from_values("noise.rms_dbfs", -75.0, -70.0, unit="dBFS").delta_percent is None
    assert _delta_from_values("broadband.d50", 90.0, 95.0, unit="%").delta_percent is None
    assert _delta_from_values("broadband.t30", 0.5, 0.55, unit="s").delta_percent == (
        pytest.approx(10.0)
    )


def test_no_percent_change_of_a_negative_baseline() -> None:
    """A loopback path delay going from -0.50 to -0.25 ms read -50 %."""
    from roomscope.core.compare import _delta_from_values

    delta = _delta_from_values("loopback.path_delay_ms", -0.5, -0.25, unit="ms")
    assert delta.delta_percent is None
    assert delta.delta == pytest.approx(0.25)


def test_a_stored_percent_of_a_level_is_dropped_on_load() -> None:
    """Comparisons saved by 0.5.0b1 stored a percent for every unit, and
    ``roomscope show`` printed "C50 (dB) ... +3.4 %"."""
    import io

    from roomscope.cli.console import Console
    from roomscope.cli.render import render_comparison
    from roomscope.models.comparison import ComparisonResult

    payload = ComparisonResult(comparable=True, common_band=(20.0, 20000.0)).to_dict()
    common = {"validity": "valid", "reason": None}
    payload["decay"] = [
        {"name": "broadband.c50", "baseline": 9.814, "candidate": 10.146, "delta": 0.332}
        | {"delta_percent": 3.38, "unit": "dB"}
        | common,
        {"name": "broadband.t30", "baseline": 0.5, "candidate": 0.55, "delta": 0.05}
        | {"delta_s": 0.05, "delta_percent": 10.0, "unit": "s"}
        | common,
    ]
    payload["loopback"] = [
        {"name": "loopback.path_delay_ms", "baseline": -0.5, "candidate": -0.25}
        | {"delta": 0.25, "delta_percent": -50.0, "unit": "ms"}
        | common,
    ]
    loaded = ComparisonResult.from_dict(payload)
    assert [d.delta_percent for d in loaded.decay] == [None, 10.0]
    assert loaded.loopback[0].delta_percent is None
    text = render_comparison(Console.for_stream(io.StringIO(), "never"), loaded)
    assert "+3.4 %" not in text


def test_an_undeclared_imported_band_is_not_compared(short_sweep: SweepSettings) -> None:
    """The 20 Hz-20 kHz placeholder of an imported IR without --band was used
    as a measured band (octave differences of 60 dB where nothing was excited)."""
    from roomscope.core.pipeline import analyze_impulse_response
    from roomscope.models.audio import AudioSignal

    swept = _result(short_sweep, rt60_s=0.4, reflections=[])
    imported = analyze_impulse_response(AudioSignal(make_rir(48000, rt60_s=0.4), 48000))
    comparison = compare(swept, imported)
    assert not comparison.comparable
    assert "no excitation band" in comparison.notes[0]


def test_a_refused_pair_names_its_reason_first(short_sweep: SweepSettings) -> None:
    """The finding quoted notes[0], which was a sweep-difference or the ISO note."""
    low = replace(short_sweep, start_hz=20.0, end_hz=1000.0)
    high = replace(short_sweep, start_hz=700.0, end_hz=20000.0, sample_rate=96000)
    comparison = compare(
        _result(low, rt60_s=0.4, reflections=[]), _result(high, rt60_s=0.4, reflections=[])
    )
    assert not comparison.comparable
    assert "narrower than the required" in comparison.notes[0]
    finding = interpret_comparison(comparison)[0]
    assert "narrower than the required" in finding.message


def test_every_refusal_starts_with_a_known_prefix(short_sweep: SweepSettings) -> None:
    """``show`` finds the reason of a refused comparison saved by 0.5.0b1 (where
    it was not the first note) by these prefixes; a reworded refusal must
    update them."""
    from roomscope.models.comparison import REFUSAL_NOTE_PREFIXES

    base = _result(short_sweep, rt60_s=0.4, reflections=[])
    band = base.impulse_response.excitation_band
    assert band is not None

    def banded(low_hz: float | None, high_hz: float = 20000.0):
        new_band = None if low_hz is None else replace(band, low_hz=low_hz, high_hz=high_hz)
        return replace(
            base, impulse_response=replace(base.impulse_response, excitation_band=new_band)
        )

    for baseline, candidate in (
        (banded(None), base),
        (banded(20.0, 100.0), banded(200.0)),
        (banded(100.0, 150.0), base),
    ):
        comparison = compare(baseline, candidate)
        assert not comparison.comparable
        refusals = [n for n in comparison.notes if n.startswith(REFUSAL_NOTE_PREFIXES)]
        assert refusals == [comparison.notes[0]]
