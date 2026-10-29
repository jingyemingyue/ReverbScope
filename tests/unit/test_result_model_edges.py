"""Edge paths of :mod:`reverbscope.models.result` helpers."""

from __future__ import annotations

import numpy as np

from reverbscope.models.result import (
    DecayMetric,
    FrequencyResponseResult,
    Validity,
    _array_to_list,
    _join_reasons,
    _not_computed_energy,
)


def test_array_to_list_and_join_reasons() -> None:
    assert _array_to_list(None) is None
    assert _array_to_list(np.array([1.23456])) == [1.2346]
    assert _join_reasons(None, "first") == "first"
    assert _join_reasons("first", "first") == "first"
    assert _join_reasons("first", "second") == "first; second"


def test_marked_unreliable_leaves_stronger_statuses_alone() -> None:
    metric = DecayMetric(
        name="t20",
        seconds=None,
        validity=Validity.NOT_COMPUTED,
        evaluation_range_db=(-5.0, -25.0),
    )
    assert metric.marked_unreliable("noise") is metric
    valid = DecayMetric(
        name="t20",
        seconds=0.5,
        validity=Validity.VALID,
        evaluation_range_db=(-5.0, -25.0),
    )
    marked = valid.marked_unreliable("clipping")
    assert marked.validity is Validity.UNRELIABLE
    assert marked.seconds == 0.5
    assert marked.reason == "clipping"


def test_not_computed_energy_and_fr_dict_without_points() -> None:
    energy = _not_computed_energy("legacy.c50", "dB")
    assert energy.validity is Validity.NOT_COMPUTED and energy.value is None
    fr = FrequencyResponseResult(
        frequencies_hz=np.zeros(0),
        magnitude_db_raw=np.zeros(0),
        magnitude_db_smoothed=None,
        smoothing_fraction=0,
        window_s=0.5,
        stored_points=12,
    )
    payload = fr.to_dict(include_curves=False)
    assert payload["points"] == 12
