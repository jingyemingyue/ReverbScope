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
    if x_range is not None:
        lo, hi = x_range
        # One stored point beyond each edge, so the curve reaches the border.
        inside = np.flatnonzero(keep & (xa >= lo) & (xa <= hi))
        if inside.size:
            first = max(int(inside[0]) - 1, 0)
            last = min(int(inside[-1]) + 1, xa.shape[0] - 1)
            window = np.zeros_like(keep)
            window[first : last + 1] = True
            keep &= window
        else:
            keep &= (xa >= lo) & (xa <= hi)
    xs = xa[keep]
    ys = ya[keep]
    if max_points < 4 or xs.shape[0] <= max_points:
        return xs.copy(), ys.copy()
    position = np.log10(xs) if log_x else xs
    n_buckets = max_points // 2
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
    index = np.asarray(picked, dtype=np.int64)
    return xs[index].copy(), ys[index].copy()


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
    valid = (fa > 0.0) & np.isfinite(da)
    if not np.any(valid):
        return out
    fv = fa[valid]
    power = 10.0 ** (da[valid] / 10.0)
    cumulative = np.r_[0.0, np.cumsum(power)]
    half = 2.0 ** (1.0 / (2.0 * fraction))
    lo = np.searchsorted(fv, fv / half, side="left")
    hi = np.searchsorted(fv, fv * half, side="right")
    count = np.maximum(hi - lo, 1)
    mean = (cumulative[hi] - cumulative[lo]) / count
    out[valid] = 10.0 * np.log10(np.maximum(mean, 1e-30))
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
