"""Common-slope analysis across positions (core/common_slope.py).

Synthetic rooms: Gaussian noise with exponential envelopes whose decay times
are the same at every position and whose amplitudes differ, plus a stationary
noise floor. The tolerances are regression choices for these fixed seeds, not
accuracy claims for real rooms (docs/validation/aachen-nikolauskapelle-common-slope.md
has the measured data).
"""

from __future__ import annotations

import csv
import io
import itertools
import json
import math

import numpy as np
import pytest
from jsonschema import Draft202012Validator

from reverbscope.core import common_slope as cs
from reverbscope.core.common_slope import (
    AMPLITUDES_EDC,
    ESTIMATOR_SAGE,
    ResponseInput,
    analyze_common_slopes,
    fit_common_slopes,
    kmeans_log,
    minimum_support,
    observe_response,
)
from reverbscope.errors import ConfigurationError
from reverbscope.io.common_slope_store import (
    BAND_COLUMNS,
    POSITION_COLUMNS,
    save_common_slope,
)
from reverbscope.models.configuration import AnalysisSettings
from reverbscope.models.result import (
    DECAY_60_DB_NEPER,
    EXCITATION_SOURCE_DECLARED,
    ExcitationBand,
    Validity,
)
from reverbscope.schemas import load_schema

RATE = 16_000
LEAD_S = 0.1
SETTINGS = AnalysisSettings(octave_bands_hz=(500.0, 1000.0, 2000.0))
EXCITATION = ExcitationBand(20.0, 7000.0, source=EXCITATION_SOURCE_DECLARED)


def response(
    decays: tuple[float, ...],
    levels_db: tuple[float, ...],
    *,
    seed: int,
    noise_db: float = -80.0,
    seconds: float = 4.0,
    name: str = "P",
) -> ResponseInput:
    """Noise with envelopes ``10^(level/10) exp(-13.8 t / T)`` and a noise floor."""
    rng = np.random.default_rng(seed)
    t = np.arange(int(seconds * RATE)) / RATE
    power = sum(
        10.0 ** (level / 10.0) * np.exp(-DECAY_60_DB_NEPER * t / decay)
        for decay, level in zip(decays, levels_db, strict=True)
    )
    h = rng.standard_normal(t.size) * np.sqrt(power)
    h += rng.standard_normal(t.size) * 10.0 ** (noise_db / 20.0)
    h[0] += 30.0 * math.sqrt(float(power[0]))
    lead = rng.standard_normal(int(LEAD_S * RATE)) * 10.0 ** (noise_db / 20.0)
    return ResponseInput(name, np.concatenate([lead, h]), RATE, lead.size, EXCITATION)


def room(
    decays: tuple[float, ...], positions: int, *, seed: int = 0, noise_db: float = -80.0
) -> list[ResponseInput]:
    rng = np.random.default_rng(1000 + seed)
    out = []
    for r in range(positions):
        if len(decays) == 1:
            levels: tuple[float, ...] = (0.0,)
        elif len(decays) == 2:
            levels = (rng.uniform(-3.0, 0.0), rng.uniform(-28.0, -12.0))
        else:
            levels = (0.0, rng.uniform(-22.0, -10.0), rng.uniform(-42.0, -28.0))
        seconds = 4.0 if max(decays) < 2.0 else 6.0
        out.append(
            response(
                decays,
                levels,
                seed=seed * 100 + r,
                noise_db=noise_db,
                seconds=seconds,
                name=f"P{r + 1}",
            )
        )
    return out


@pytest.fixture(scope="module")
def two_slope_result() -> cs.CommonSlopeResult:
    return analyze_common_slopes(room((0.4, 1.6), 8, seed=0), SETTINGS)


def test_shared_decay_times_are_recovered(two_slope_result: cs.CommonSlopeResult) -> None:
    for band in two_slope_result.bands:
        assert band.validity is Validity.VALID
        assert band.selected_slopes == 2, band.notes
        t1, t2 = band.decay_times_s
        assert t1 == pytest.approx(0.4, rel=0.06)
        assert t2 == pytest.approx(1.6, rel=0.06)
        assert len(band.positions) == 8
        assert band.supporting_positions[1] >= 2


def test_amplitudes_follow_each_positions_levels(two_slope_result: cs.CommonSlopeResult) -> None:
    """The late-to-early amplitude ratio of each position matches its synthetic
    levels: ``A_k`` is the slope's energy, ``level_k * T_k`` up to a common factor."""
    rng = np.random.default_rng(1000)
    expected = []
    for _r in range(8):
        early, late = rng.uniform(-3.0, 0.0), rng.uniform(-28.0, -12.0)
        expected.append(late - early + 10.0 * math.log10(1.6 / 0.4))
    band = two_slope_result.bands[1]  # 1 kHz
    for position, want in zip(band.positions, expected, strict=True):
        a1, a2 = position.amplitudes_db
        assert a1 is not None and a2 is not None
        assert a2 - a1 == pytest.approx(want, abs=1.5)
        # Each position's own fit is reported beside the common one.
        assert position.single_slopes in (1, 2)
        assert position.rms_residual_db < 1.0
        assert position.noise_db is not None and position.noise_db < -40.0


def test_linex_and_edc_amplitudes_agree() -> None:
    responses = room((0.4, 1.6), 5, seed=3)
    linex = analyze_common_slopes(responses, SETTINGS)
    edc = analyze_common_slopes(responses, SETTINGS, amplitude_method=AMPLITUDES_EDC)
    for a, b in zip(linex.bands, edc.bands, strict=True):
        assert a.decay_times_s == pytest.approx(b.decay_times_s)
        for pa, pb in zip(a.positions, b.positions, strict=True):
            for x, y in zip(pa.amplitudes_db, pb.amplitudes_db, strict=True):
                assert x is not None and y is not None
                assert x == pytest.approx(y, abs=1.5)


def test_one_slope_room_selects_one_slope() -> None:
    result = analyze_common_slopes(room((1.2,), 6, seed=1), SETTINGS)
    for band in result.bands:
        assert band.selected_slopes == 1, band.notes
        assert band.decay_times_s[0] == pytest.approx(1.2, rel=0.05)
        assert len(band.models) == 3
        # A spurious second slope is turned down by the criterion or a rule.
        assert band.delta_bic[0] < cs.DELTA_BIC_MIN or band.notes


@pytest.mark.parametrize("seed", [1, 2])
def test_spurious_third_slope_is_not_reported(seed: int) -> None:
    result = analyze_common_slopes(room((0.4, 1.6), 10, seed=seed), SETTINGS)
    assert [b.selected_slopes for b in result.bands] == [2, 2, 2]


def test_three_slope_room_selects_three_slopes() -> None:
    settings = AnalysisSettings(octave_bands_hz=(500.0,))
    result = analyze_common_slopes(room((0.3, 0.9, 2.5), 8, seed=0, noise_db=-95.0), settings)
    band = result.bands[0]
    assert band.selected_slopes == 3, band.notes
    for got, want in zip(band.decay_times_s, (0.3, 0.9, 2.5), strict=True):
        assert got == pytest.approx(want, rel=0.12)


def test_max_slopes_caps_the_order(two_slope_result: cs.CommonSlopeResult) -> None:
    result = analyze_common_slopes(room((0.4, 1.6), 4, seed=0), SETTINGS, max_slopes=1)
    assert all(b.selected_slopes == 1 for b in result.bands)
    assert all(len(b.models) == 1 for b in result.bands)


def test_single_position_reduces_to_its_own_fit() -> None:
    result = analyze_common_slopes(room((0.4, 1.6), 1, seed=4), SETTINGS)
    band = result.bands[1]
    assert band.selected_slopes == 2
    assert band.decay_times_s == pytest.approx((0.4, 1.6), rel=0.08)
    assert any("one position only" in note for note in band.notes)
    assert minimum_support(1) == 1
    assert minimum_support(10) == 2
    assert minimum_support(46) == 3


def test_positions_without_decay_range_are_left_out() -> None:
    good = room((1.0,), 3, seed=5)
    flat = response((1.0,), (0.0,), seed=99, noise_db=-12.0, name="noisy")
    result = analyze_common_slopes([*good, flat], SETTINGS)
    for band in result.bands:
        assert [p.position for p in band.positions] == ["P1", "P2", "P3"]
        assert [e.position for e in band.excluded] == ["noisy"]
        assert band.excluded[0].reason


def test_no_usable_position_is_insufficient() -> None:
    flat = response((1.0,), (0.0,), seed=7, noise_db=-10.0, name="noisy")
    band = analyze_common_slopes([flat], SETTINGS).bands[0]
    assert band.validity is Validity.INSUFFICIENT_RANGE
    assert band.selected_slopes is None
    assert band.reason
    empty = fit_common_slopes([], band_label="1 kHz", center_hz=1000.0, bandwidth_hz=707.0)
    assert empty.validity is Validity.INSUFFICIENT_RANGE


def test_band_outside_excitation_is_left_out() -> None:
    narrow = ExcitationBand(300.0, 1500.0, source=EXCITATION_SOURCE_DECLARED)
    responses = [
        ResponseInput(r.position, r.samples, r.sample_rate, r.direct_index, narrow)
        for r in room((1.0,), 2, seed=6)
    ]
    items = observe_response(responses[0], SETTINGS)
    # 500 Hz (354-707 Hz) and 1 kHz (707-1414 Hz) are inside 300-1500 Hz; 2 kHz is not.
    assert isinstance(items[0], cs.BandObservation)
    assert isinstance(items[1], cs.BandObservation)
    assert isinstance(items[2], cs.ExcludedPosition)
    result = analyze_common_slopes(responses, SETTINGS)
    assert result.bands[2].validity is Validity.INSUFFICIENT_RANGE


def test_bad_arguments_are_refused() -> None:
    responses = room((1.0,), 1, seed=8)
    with pytest.raises(ConfigurationError):
        analyze_common_slopes([], SETTINGS)
    with pytest.raises(ConfigurationError):
        analyze_common_slopes([*responses, *responses], SETTINGS)
    with pytest.raises(ConfigurationError):
        analyze_common_slopes(responses, SETTINGS, max_slopes=4)
    with pytest.raises(ConfigurationError):
        analyze_common_slopes(responses, SETTINGS, estimator="nope")
    with pytest.raises(ConfigurationError):
        analyze_common_slopes(responses, SETTINGS, amplitude_method="nope")


def test_kmeans_log_clusters() -> None:
    assert kmeans_log([0.5, 0.52, 0.48, 2.0, 2.1, 1.9], 2) == pytest.approx([0.5, 2.0], rel=0.03)
    assert kmeans_log([1.0, 1.0, 1.0], 3) == pytest.approx([1.0])
    with pytest.raises(ValueError):
        kmeans_log([], 2)


# --- envelope estimators --------------------------------------------------------------


def _envelope(
    decays: tuple[float, float], positions: int, *, seed: int, samples: int = 1500
) -> tuple[cs._Envelope, np.ndarray]:
    """Complex-Gaussian powers with the IS-NMF model of arXiv:2610.05549 eq. (1)."""
    rng = np.random.default_rng(seed)
    tau = np.linspace(0.0, 3.0, samples)
    rates = DECAY_60_DB_NEPER / np.asarray(decays)
    share = rng.uniform(0.05, 0.95, positions)
    power = np.stack([share, 1.0 - share, np.full(positions, 1e-4)], axis=1)
    v = power[:, :2] @ np.exp(-rates[:, None] * tau[None, :]) + power[:, 2:]
    y = v * rng.exponential(1.0, v.shape)
    env = cs._Envelope(
        tau=np.tile(tau, (positions, 1)),
        y=y,
        mask=np.ones_like(y),
        counts=np.full(positions, samples),
    )
    return env, power


def test_linex_amplitudes_recover_powers() -> None:
    env, power = _envelope((0.8, 1.4), 20, seed=0)
    rates = DECAY_60_DB_NEPER / np.array([0.8, 1.4])
    estimate = cs.linex_amplitudes(env, rates, np.full_like(power, 0.3))
    # Total early power is well determined; the split within 1-2 dB.
    assert np.median(np.abs(10 * np.log10(estimate[:, :2] / power[:, :2]))) < 1.5
    assert np.median(np.abs(10 * np.log10(estimate[:, 2] / power[:, 2]))) < 1.0


def test_sage_recovers_shared_decay_rates() -> None:
    """The setting of the paper's synthetic experiment (T = 0.8, 1.4 s), smaller;
    contribution-weighted SAGE (p = 1) reaches a lower loss than plain SAGE in
    the same number of iterations, as the paper reports."""
    env, power = _envelope((0.8, 1.4), 64, seed=1, samples=800)
    start = DECAY_60_DB_NEPER / np.array([0.6, 2.0])
    rates, estimate, losses = cs.sage(env, start, np.full_like(power, 0.5))
    decays = DECAY_60_DB_NEPER / rates
    assert decays == pytest.approx([0.8, 1.4], rel=0.06)
    weighted = cs.SAGE_WEIGHTED_ITERATIONS
    # p = 0 iterations do not increase the observed-data loss.
    plain = losses[weighted:]
    assert all(b <= a + 1e-6 * abs(a) for a, b in itertools.pairwise(plain))
    # The fit is at least as likely as the true parameters (sampling variance).
    truth = cs.is_loss(env, DECAY_60_DB_NEPER / np.array([0.8, 1.4]), power)
    assert losses[-1] <= truth
    _rates, _power, standard = cs.sage(
        env,
        start,
        np.full_like(power, 0.5),
        weighted_iterations=0,
        plain_iterations=weighted + cs.SAGE_PLAIN_ITERATIONS,
    )
    assert losses[-1] < standard[-1]
    assert estimate.shape == power.shape


def test_sage_estimator_on_responses() -> None:
    result = analyze_common_slopes(room((0.4, 1.6), 6, seed=2), SETTINGS, estimator=ESTIMATOR_SAGE)
    band = result.bands[1]
    assert band.selected_slopes == 2
    assert band.decay_times_s == pytest.approx((0.4, 1.6), rel=0.1)
    assert band.edc_decay_times_s == pytest.approx((0.4, 1.6), rel=0.08)
    assert any("SAGE" in note for note in band.notes)


# --- files ------------------------------------------------------------------------------


def test_result_validates_and_exports(
    two_slope_result: cs.CommonSlopeResult, tmp_path: object
) -> None:
    from pathlib import Path

    payload = two_slope_result.to_dict()
    Draft202012Validator(load_schema("common-slope")).validate(payload)
    written = save_common_slope(Path(str(tmp_path)) / "out", two_slope_result)
    assert [p.name for p in written] == [
        "common-slope.json",
        "common-slope-bands.csv",
        "common-slope-positions.csv",
    ]
    assert json.loads(written[0].read_text(encoding="utf-8")) == json.loads(json.dumps(payload))
    bands = list(csv.reader(io.StringIO(written[1].read_text(encoding="utf-8"))))
    assert tuple(bands[0]) == BAND_COLUMNS
    assert len(bands) == 1 + len(two_slope_result.bands)
    assert float(bands[1][BAND_COLUMNS.index("t2_s")]) == pytest.approx(1.6, rel=0.06)
    positions = list(csv.reader(io.StringIO(written[2].read_text(encoding="utf-8"))))
    assert tuple(positions[0]) == POSITION_COLUMNS
    assert len(positions) == 1 + 3 * 8 * 2


def test_insufficient_band_validates() -> None:
    flat = response((1.0,), (0.0,), seed=7, noise_db=-10.0, name="noisy")
    payload = analyze_common_slopes([flat], SETTINGS).to_dict()
    Draft202012Validator(load_schema("common-slope")).validate(payload)
