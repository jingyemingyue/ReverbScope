"""Additional edge paths for :mod:`reverbscope.core.noise` helpers."""

from __future__ import annotations

import numpy as np

from reverbscope.core.noise import (
    PRE_SWEEP_SOURCE,
    TAIL_SOURCE,
    _band_levels,
    _by_source,
    _longest_run,
    _nonzero_pieces,
)


def test_by_source_selects_pre_sweep_tail_or_other() -> None:
    assert _by_source(PRE_SWEEP_SOURCE, pre_sweep="pre", tail="tail", other="other") == "pre"
    assert _by_source(TAIL_SOURCE, pre_sweep="pre", tail="tail", other="other") == "tail"
    assert _by_source("custom", pre_sweep="pre", tail="tail", other="other") == "other"


def test_nonzero_pieces_merge_across_short_zero_gaps() -> None:
    samples = np.array([1.0, 1.0, 0.0, 1.0, 1.0, 0.0, 0.0, 0.0, 1.0])
    assert _nonzero_pieces(samples, min_run=2) == [(0, 5), (8, 9)]
    assert _nonzero_pieces(np.zeros(8), min_run=2) == []


def test_longest_run_returns_empty_bounds_when_mask_is_false() -> None:
    assert _longest_run(np.zeros(5, dtype=bool)) == (0, 0)


def test_band_levels_skip_unfittable_bands_and_mark_short_filters() -> None:
    levels, notes = _band_levels(
        np.random.default_rng(0).normal(0.0, 0.01, 8_000),
        8_000,
        (125.0, 4_000.0),
    )
    assert len(levels) == 1 and levels[0][0] == 125.0
    assert levels[0][1] is not None
    assert notes == []

    short_levels, short_notes = _band_levels(np.zeros(100), 48_000, (63.0, 125.0))
    assert short_levels == [(63.0, None), (125.0, None)]
    assert short_notes and "too short" in short_notes[0]
