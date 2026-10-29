"""Edge paths of :mod:`reverbscope.core.compare` helpers."""

from __future__ import annotations

import numpy as np

from reverbscope.core.compare import (
    _coarser_smoothing,
    _curve,
    _delta_from_values,
    _placement_length_delta,
    _side_reasons,
    _sweep_notes,
)
from reverbscope.core.pipeline import Reference, analyze, synthetic_recording
from reverbscope.models.configuration import SweepSettings
from reverbscope.models.result import (
    DecayMetric,
    FrequencyResponseResult,
    PlacementLength,
    Validity,
)
from tests.conftest import make_rir


def test_delta_from_values_marks_missing_numbers_not_comparable() -> None:
    delta = _delta_from_values("metric", None, 1.0, unit="s", time=True)
    assert delta.validity is Validity.NOT_COMPARABLE
    assert delta.reason is not None
    assert "no number" in delta.reason


def test_side_reasons_without_detailed_reason_still_name_validity() -> None:
    metric = DecayMetric(
        name="t20",
        seconds=None,
        validity=Validity.INSUFFICIENT_RANGE,
        evaluation_range_db=(-5.0, -25.0),
        reason=None,
    )
    reasons = _side_reasons(metric, metric)
    assert len(reasons) == 2
    assert all("insufficient range" in reason for reason in reasons)


def test_coarser_smoothing_prefers_the_positive_side() -> None:
    assert _coarser_smoothing(0, 12) == 12
    assert _coarser_smoothing(12, 0) == 12
    assert _coarser_smoothing(12, 6) == 6


def test_curve_falls_back_to_smoothed_or_returns_none() -> None:
    smoothed = FrequencyResponseResult(
        frequencies_hz=np.array([100.0, 200.0, 400.0]),
        magnitude_db_raw=np.array([]),
        magnitude_db_smoothed=np.array([-1.0, -2.0, -3.0]),
        smoothing_fraction=12,
        window_s=0.5,
    )
    curve = _curve(smoothed)
    assert curve is not None
    assert curve[0].shape[0] == 3

    empty = FrequencyResponseResult(
        frequencies_hz=np.array([0.0]),
        magnitude_db_raw=np.array([0.0]),
        magnitude_db_smoothed=None,
        smoothing_fraction=0,
        window_s=0.5,
    )
    assert _curve(empty) is None


def test_placement_length_delta_needs_both_sides_valid() -> None:
    left = PlacementLength(metres=1.2, validity=Validity.VALID)
    right = PlacementLength(metres=None, validity=Validity.NOT_COMPUTED, reason=None)
    delta = _placement_length_delta("placement.source_height_m", left, right)
    assert delta.validity is Validity.NOT_COMPARABLE
    assert delta.reason is not None


def test_sweep_notes_mention_differing_levels(short_sweep: SweepSettings) -> None:
    from dataclasses import replace

    quiet = replace(short_sweep, level_dbfs=-18.0)
    loud = replace(short_sweep, level_dbfs=-6.0)
    baseline = analyze(
        synthetic_recording(
            quiet, make_rir(quiet.sample_rate, rt60_s=0.3, diffuse_level=0.02), noise_rms=1e-5
        ),
        Reference.from_settings(quiet),
    )
    candidate = analyze(
        synthetic_recording(
            loud, make_rir(loud.sample_rate, rt60_s=0.3, diffuse_level=0.02), noise_rms=1e-5, seed=2
        ),
        Reference.from_settings(loud),
    )
    notes = _sweep_notes(baseline, candidate)
    assert any("sweep levels differ" in note for note in notes)
