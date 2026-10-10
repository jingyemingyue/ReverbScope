"""Display curves: the subset keeps every extreme, smoothing and alignment are display only."""

from __future__ import annotations

import json

import numpy as np
import pytest

from reverbscope.display import DisplayDataError
from reverbscope.display.curves import (
    difference,
    level_offset,
    peak_subset,
    smooth_fractional_octave,
)
from reverbscope.display.etc import etc_curve, marker_index, marker_points
from reverbscope.models.result import AnalysisResult


def _log_curve(n: int = 131_072) -> tuple[np.ndarray, np.ndarray]:
    f = np.geomspace(10.0, 24_000.0, n)
    rng = np.random.default_rng(3)
    db = rng.normal(0.0, 1.0, n)
    db[n // 3] = -48.0  # a deep notch
    db[2 * n // 3] = 21.0  # a sharp peak
    return f, db


def test_peak_subset_keeps_only_stored_points_and_every_extreme() -> None:
    f, db = _log_curve()
    x, y = peak_subset(f, db, 2000, log_x=True)
    assert x.shape[0] <= 2000
    assert np.all(np.diff(x) > 0)
    stored = dict(zip(f.tolist(), db.tolist(), strict=True))
    assert all(stored[float(a)] == float(b) for a, b in zip(x, y, strict=True))
    assert y.min() == pytest.approx(-48.0)
    assert y.max() == pytest.approx(21.0)


def test_peak_subset_returns_short_curves_whole_and_as_copies() -> None:
    f = np.array([100.0, 200.0, 400.0])
    db = np.array([1.0, 2.0, 3.0])
    x, y = peak_subset(f, db, 2000, log_x=True)
    assert np.array_equal(x, f) and np.array_equal(y, db)
    x[0] = 0.0
    assert f[0] == 100.0


def test_peak_subset_honours_the_visible_range_with_one_point_beyond() -> None:
    f, db = _log_curve(10_000)
    x, _y = peak_subset(f, db, 400, log_x=True, x_range=(1000.0, 2000.0))
    assert x[0] < 1000.0 <= x[1]
    assert x[-2] <= 2000.0 < x[-1]


def test_peak_subset_skips_non_finite_and_non_positive_frequencies() -> None:
    f = np.array([0.0, 10.0, 20.0, 40.0])
    db = np.array([5.0, np.nan, 1.0, 2.0])
    x, y = peak_subset(f, db, 100, log_x=True)
    assert x.tolist() == [20.0, 40.0]
    assert y.tolist() == [1.0, 2.0]


def test_peak_subset_rejects_mismatched_axes() -> None:
    with pytest.raises(DisplayDataError):
        peak_subset(np.arange(3.0), np.arange(4.0), 10)


def test_smoothing_is_a_power_average_and_leaves_flat_curves_flat() -> None:
    f = np.geomspace(20.0, 20_000.0, 2000)
    flat = np.full(f.shape, -6.0)
    assert np.allclose(smooth_fractional_octave(f, flat, 3), -6.0)
    spiky = flat.copy()
    spiky[1000] = 30.0
    smoothed = smooth_fractional_octave(f, spiky, 3)
    assert smoothed[1000] < 30.0
    assert smoothed[1000] > -6.0
    # Power average: the spike raises its neighbourhood more than a dB average would.
    assert smoothed[1010] > -6.0


def test_smoothing_zero_is_a_copy_and_negative_is_refused() -> None:
    f = np.geomspace(20.0, 20_000.0, 50)
    db = np.linspace(-10.0, 10.0, 50)
    out = smooth_fractional_octave(f, db, 0)
    assert np.array_equal(out, db) and out is not db
    with pytest.raises(DisplayDataError):
        smooth_fractional_octave(f, db, -1)


def test_level_offset_is_the_band_mean_in_power() -> None:
    f = np.geomspace(20.0, 20_000.0, 1000)
    db = np.where((f >= 500.0) & (f <= 2000.0), 3.0, -40.0)
    assert level_offset(f, db) == pytest.approx(3.0)
    assert level_offset(f, db, (30_000.0, 40_000.0)) is None


def test_difference_interpolates_in_log_frequency_over_the_common_range() -> None:
    fa = np.geomspace(20.0, 10_000.0, 300)
    fb = np.geomspace(100.0, 20_000.0, 500)
    grid, delta = difference(fa, np.zeros_like(fa), fb, 2.0 * np.log10(fb))
    assert grid[0] >= 100.0 and grid[-1] <= 10_000.0
    assert np.allclose(delta, 2.0 * np.log10(grid), atol=1e-6)


def test_difference_without_a_common_range_is_refused() -> None:
    fa = np.geomspace(20.0, 100.0, 10)
    fb = np.geomspace(1000.0, 2000.0, 10)
    with pytest.raises(DisplayDataError) as caught:
        difference(fa, np.zeros(10), fb, np.zeros(10))
    assert caught.value.text()


def test_reflection_markers_lie_on_the_etc_at_the_stored_level(
    analysed_result: AnalysisResult,
) -> None:
    ir = analysed_result.impulse_response
    reflections = analysed_result.reflections.reflections
    assert reflections, "the fixture room has an 18 ms reflection"
    curve = etc_curve(ir.samples, ir.sample_rate, ir.direct_sound_index)
    points = marker_points(curve, reflections)
    for (t_ms, level), reflection in zip(points, reflections, strict=True):
        assert t_ms == pytest.approx(reflection.delay_ms, abs=1e-9)
        assert level == pytest.approx(reflection.relative_db, abs=1e-9)
    assert curve.level_db[marker_index(curve, 0.0)] <= 0.0 + 1e-12


def test_etc_refuses_what_it_cannot_draw() -> None:
    with pytest.raises(DisplayDataError):
        etc_curve(np.zeros(0), 48_000, 0)
    with pytest.raises(DisplayDataError):
        etc_curve(np.array([0.0, np.nan]), 48_000, 0)
    with pytest.raises(DisplayDataError):
        etc_curve(np.zeros(10), 48_000, 10)


def test_display_functions_never_change_the_result(analysed_result: AnalysisResult) -> None:
    before = json.dumps(analysed_result.to_dict(), sort_keys=True, default=str)
    fr = analysed_result.frequency_response
    peak_subset(fr.frequencies_hz, fr.magnitude_db_raw, 500, log_x=True)
    smooth_fractional_octave(fr.frequencies_hz, fr.magnitude_db_raw, 6)
    level_offset(fr.frequencies_hz, fr.magnitude_db_raw)
    ir = analysed_result.impulse_response
    etc_curve(ir.samples, ir.sample_rate, ir.direct_sound_index)
    assert json.dumps(analysed_result.to_dict(), sort_keys=True, default=str) == before
