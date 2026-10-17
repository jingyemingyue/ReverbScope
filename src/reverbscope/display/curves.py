"""Curves as the workstation draws them: decimated, smoothed and aligned for display.

The stored curve is never changed. Each function returns new arrays, and
what it did is something the chart labels (display smoothing, level
alignment) or that does not change what is seen (the peak-preserving subset
keeps every extreme). See docs/design/GUI_2_ARCHITECTURE.md §5.1.
"""

from __future__ import annotations

import numpy as np

from reverbscope.display import DisplayDataError
from reverbscope.i18n import N_
from reverbscope.models.audio import FloatArray

#: Display smoothing offered by the frequency view (0 = none), in 1/N octave.
SMOOTHING_FRACTIONS = (0, 48, 24, 12, 6, 3, 1)

#: The band whose mean level aligns overlaid curves (Hz).
DEFAULT_ALIGN_BAND_HZ = (500.0, 2000.0)


def _as_pair(x: FloatArray, y: FloatArray) -> tuple[FloatArray, FloatArray]:
    xa = np.asarray(x, dtype=np.float64)
    ya = np.asarray(y, dtype=np.float64)
    if xa.ndim != 1 or ya.ndim != 1 or xa.shape != ya.shape:
        raise DisplayDataError(N_("the curve's axes do not have the same length"))
    return xa, ya


def peak_subset(
    x: FloatArray,
    y: FloatArray,
    max_points: int,
    *,
    log_x: bool = False,
    x_range: tuple[float, float] | None = None,
) -> tuple[FloatArray, FloatArray]:
    """At most about ``max_points`` stored points that keep every extreme.

    The visible part of the curve (``x_range``, else all of it) is cut into
    ``max_points // 2`` buckets of equal width (in ``log10(x)`` when
    ``log_x``), and the smallest and largest value of each bucket are kept,
    in their order along x. Every returned point is a stored point: a notch
    keeps its depth and a peak its height, which pyqtgraph's subsample and
    mean modes do not. Non-finite values are skipped. A curve that already
    fits is returned whole (as copies).
    """
    xa, ya = _as_pair(x, y)
    keep = np.isfinite(xa) & np.isfinite(ya)
    if log_x:
        keep &= xa > 0.0
    xs = xa[keep]
    ys = ya[keep]
    if x_range is not None and xs.size:
        lo, hi = x_range
        if hi < xs[0] or lo > xs[-1]:
            return xs[:0].copy(), ys[:0].copy()
        # Include the segment crossing the viewport even when neither end
        # lies inside it (a deep zoom between adjacent stored samples).
        first = max(0, int(np.searchsorted(xs, lo, side="left")) - 1)
        stop = min(xs.size, int(np.searchsorted(xs, hi, side="right")) + 1)
        xs, ys = xs[first:stop], ys[first:stop]
    if max_points < 4 or xs.shape[0] <= max_points:
        return xs.copy(), ys.copy()
    position = np.log10(xs) if log_x else xs
    n_buckets = (max_points - 2) // 2
    span = float(position[-1] - position[0])
    if span <= 0.0:
        return xs[:max_points].copy(), ys[:max_points].copy()
    bucket = np.minimum(
        ((position - position[0]) / span * n_buckets).astype(np.int64), n_buckets - 1
    )
    # x is sorted, so each bucket is one contiguous run of indices.
    starts = np.flatnonzero(np.r_[True, bucket[1:] != bucket[:-1]])
    stops = np.r_[starts[1:], bucket.shape[0]]
    picked: list[int] = []
    for start, stop in zip(starts.tolist(), stops.tolist(), strict=True):
        segment = ys[start:stop]
        lo_index = start + int(np.argmin(segment))
        hi_index = start + int(np.argmax(segment))
        if lo_index == hi_index:
            picked.append(lo_index)
        else:
            picked.extend(sorted((lo_index, hi_index)))
    index = np.unique(np.asarray([0, *picked, xs.size - 1], dtype=np.int64))
    return xs[index].copy(), ys[index].copy()


def _window_power_sums(power: FloatArray, lo: np.ndarray, hi: np.ndarray) -> FloatArray:
    """Sum half-open windows without subtracting near-equal global sums.

    Positive pairwise partial sums avoid losing a quiet window after a loud
    resonance. Batched segment-tree queries take O(N log N) work and O(N)
    space, without constructing one array per smoothing window.
    """
    left, right = lo.copy(), hi.copy()
    totals = np.zeros(left.shape, dtype=np.float64)
    level = power
    while np.any(left < right):
        take_left = (left < right) & (left % 2 == 1)
        totals[take_left] += level[left[take_left]]
        left[take_left] += 1
        take_right = (left < right) & (right % 2 == 1)
        right[take_right] -= 1
        totals[take_right] += level[right[take_right]]
        left //= 2
        right //= 2
        if np.any(left < right):
            if level.size % 2:
                level = np.r_[level, 0.0]
            level = level[::2] + level[1::2]
    return totals


def smooth_fractional_octave(f: FloatArray, db: FloatArray, fraction: int) -> FloatArray:
    """``db`` averaged in power over ±1/(2·fraction) octave around each point.

    Display smoothing only: the chart labels it, and the stored curve stays
    available. ``fraction == 0`` returns a copy. The average weighs every
    stored point in the window equally, as the analysis' own smoothing does
    on its log-spaced grid; points at or below 0 Hz are left as they are.
    """
    fa, da = _as_pair(f, db)
    if fraction < 0:
        raise DisplayDataError(N_("display smoothing must be 0 or a positive fraction"))
    out = da.copy()
    if fraction == 0 or fa.shape[0] < 3:
        return out
    valid = (fa > 0.0) & np.isfinite(fa) & np.isfinite(da)
    if not np.any(valid):
        return out
    fv = fa[valid]
    reference_db = float(np.max(da[valid]))
    power = 10.0 ** ((da[valid] - reference_db) / 10.0)
    half = 2.0 ** (1.0 / (2.0 * fraction))
    lo = np.searchsorted(fv, fv / half, side="left")
    hi = np.searchsorted(fv, fv * half, side="right")
    count = np.maximum(hi - lo, 1)
    mean = _window_power_sums(power, lo, hi) / count
    out[valid] = reference_db + 10.0 * np.log10(np.maximum(mean, np.finfo(float).tiny))
    return out


def level_offset(
    f: FloatArray, db: FloatArray, band_hz: tuple[float, float] = DEFAULT_ALIGN_BAND_HZ
) -> float | None:
    """The mean level (in power) of ``db`` inside ``band_hz``, or ``None``.

    Subtracting it aligns overlaid curves at that band; the chart shows the
    offset in the legend so an aligned curve is never read as measured.
    """
    fa, da = _as_pair(f, db)
    lo, hi = band_hz
    inside = (fa >= lo) & (fa <= hi) & np.isfinite(da)
    if not np.any(inside):
        return None
    return float(10.0 * np.log10(np.mean(10.0 ** (da[inside] / 10.0))))


def difference(
    f_a: FloatArray, a: FloatArray, f_b: FloatArray, b: FloatArray
) -> tuple[FloatArray, FloatArray]:
    """``b − a`` on ``a``'s frequencies over the range both curves cover.

    ``b`` is interpolated in ``log10(f)``. Raises :class:`DisplayDataError`
    when the two curves share no frequency range.
    """
    fa, da = _as_pair(f_a, a)
    fb, db = _as_pair(f_b, b)
    ok_a = (fa > 0.0) & np.isfinite(da)
    ok_b = (fb > 0.0) & np.isfinite(db)
    if not np.any(ok_a) or not np.any(ok_b):
        raise DisplayDataError(N_("one of the two curves has no frequency response"))
    fa, da = fa[ok_a], da[ok_a]
    fb, db = fb[ok_b], db[ok_b]
    lo = max(float(fa[0]), float(fb[0]))
    hi = min(float(fa[-1]), float(fb[-1]))
    common = (fa >= lo) & (fa <= hi)
    if lo >= hi or not np.any(common):
        raise DisplayDataError(N_("the two curves share no frequency range"))
    grid = fa[common]
    interpolated = np.interp(np.log10(grid), np.log10(fb), db)
    return grid.copy(), interpolated - da[common]
