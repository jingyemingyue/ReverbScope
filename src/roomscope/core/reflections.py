"""Early reflection detection on the broadband impulse response.

Method
------
1. The analytic (Hilbert) envelope of the IR is taken and a short peak-hold
   (maximum filter, ``hold_ms``) merges the ringing of one arrival into one
   peak without lowering impulsive arrivals the way averaging would.
2. The envelope is expressed in dB relative to the direct sound.
3. A local trend (moving average of the dB envelope over ``trend_ms``) models
   the diffuse energy around each instant; the *excess* of a peak over that
   trend is used as its prominence.
4. Peaks between ``min_delay_ms`` and ``max_delay_ms`` after the direct sound
   that are above ``threshold_db`` (relative to the direct sound) and have an
   excess of at least ``prominence_db`` are reported. Neighbours outside the
   inclusive delay window are kept when detecting a peak at either boundary.
   When the impulse response ends before ``max_delay_ms``, the window that was actually
   analysed is reported (``analysed_window_ms``, ``window_truncated``): a
   shorter search must not look like "no reflections found".

The result is a list of *candidate* reflections (delay, level relative to the
direct sound). In a dense diffuse tail, statistical envelope peaks can still
appear as candidates; the notes say so.
"""

from __future__ import annotations

import numpy as np
from scipy.ndimage import maximum_filter1d, uniform_filter1d
from scipy.signal import find_peaks

from roomscope.core.impulse import envelope
from roomscope.i18n import diag
from roomscope.models.audio import FloatArray
from roomscope.models.result import Reflection, ReflectionsResult

MAX_REPORTED_REFLECTIONS = 20
_EPS = 1e-300


def reflection_envelope_db(
    ir: FloatArray,
    sample_rate: int,
    *,
    hold_ms: float = 0.1,
) -> FloatArray:
    """Peak-held analytic envelope in dB (relative units)."""
    env = envelope(ir, sample_rate, 0.0)
    hold = max(1, round(hold_ms * sample_rate / 1000.0))
    held = maximum_filter1d(env, size=hold, mode="nearest")
    return np.asarray(20.0 * np.log10(np.maximum(held, _EPS)), dtype=np.float64)


def detect_early_reflections(
    ir: FloatArray,
    sample_rate: int,
    direct_index: int,
    *,
    min_delay_ms: float,
    max_delay_ms: float,
    threshold_db: float,
    prominence_db: float,
    direct_sound_confidence: str,
    hold_ms: float = 0.1,
    trend_ms: float = 6.0,
) -> ReflectionsResult:
    env_db = reflection_envelope_db(ir, sample_rate, hold_ms=hold_ms)
    half = max(1, round(0.5e-3 * sample_rate))
    lo = max(0, direct_index - half)
    hi = min(env_db.shape[0], direct_index + half + 1)
    reference = float(np.max(env_db[lo:hi]))
    rel_db = env_db - reference

    start = direct_index + round(min_delay_ms * sample_rate / 1000.0)
    stop = min(rel_db.shape[0], direct_index + round(max_delay_ms * sample_rate / 1000.0) + 1)
    analysed_max_ms = max(0.0, (stop - 1 - direct_index) * 1000.0 / sample_rate)
    truncated = analysed_max_ms < max_delay_ms - 1e-9
    analysed_window = (min_delay_ms, analysed_max_ms)
    notes: list[str] = []
    if truncated:
        notes.append(
            diag(
                "the impulse response ends {analysed_ms:.1f} ms after the direct sound, so only "
                "that part of the {min_ms:.0f}-{max_ms:.0f} ms window could be searched",
                analysed_ms=analysed_max_ms,
                min_ms=min_delay_ms,
                max_ms=max_delay_ms,
            )
        )
    if stop - start < 3:
        notes.append(
            diag("impulse response is too short after the direct sound for reflection analysis")
        )
        return ReflectionsResult(
            direct_sound_time_s=direct_index / sample_rate,
            direct_sound_confidence=direct_sound_confidence,
            window_ms=(min_delay_ms, max_delay_ms),
            threshold_db=threshold_db,
            reflections=(),
            notes=tuple(notes),
            analysed_window_ms=analysed_window,
            window_truncated=truncated,
        )

    trend_len = max(3, round(trend_ms * sample_rate / 1000.0))
    trend = uniform_filter1d(rel_db, size=trend_len, mode="nearest")
    excess = rel_db - trend
    # A peak needs both neighbours; cropping exactly to the delay window
    # silently removes arrivals on its boundaries. Keep enough context for
    # the peak-hold plateau, but exclude out-of-window peaks by height BEFORE
    # the distance rule, so they cannot suppress an in-window arrival.
    context = max(1, int(np.ceil(hold_ms * sample_rate / 1000.0)))
    region_start = max(0, start - context)
    region_stop = min(rel_db.shape[0], stop + context)
    region = rel_db[region_start:region_stop]
    height = np.full(region.shape, np.inf)
    height[start - region_start : stop - region_start] = threshold_db
    min_distance = max(1, round(0.3e-3 * sample_rate))
    peaks, _ = find_peaks(region, height=height, distance=min_distance)
    found = [
        Reflection(
            delay_ms=float((region_start + p - direct_index) * 1000.0 / sample_rate),
            relative_db=float(region[p]),
        )
        for p in peaks
        if excess[region_start + p] >= prominence_db
    ]
    if len(found) > MAX_REPORTED_REFLECTIONS:
        found.sort(key=lambda r: r.relative_db, reverse=True)
        found = found[:MAX_REPORTED_REFLECTIONS]
        notes.append(
            diag(
                "only the {count} strongest reflections are listed",
                count=MAX_REPORTED_REFLECTIONS,
            )
        )
    found.sort(key=lambda r: r.delay_ms)
    notes.append(
        diag(
            "candidates are envelope peaks standing above the local diffuse level; in a dense "
            "early tail some candidates may be statistical rather than discrete reflections"
        )
    )
    if direct_sound_confidence == "low":
        notes.append(
            diag(
                "direct-sound detection confidence is low; reflection delays are relative to "
                "the strongest peak, which may not be the direct sound"
            )
        )
    return ReflectionsResult(
        direct_sound_time_s=direct_index / sample_rate,
        direct_sound_confidence=direct_sound_confidence,
        window_ms=(min_delay_ms, max_delay_ms),
        threshold_db=threshold_db,
        reflections=tuple(found),
        notes=tuple(notes),
        analysed_window_ms=analysed_window,
        window_truncated=truncated,
    )
