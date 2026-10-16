"""Spectrogram and waterfall (cumulative spectral decay) of a stored impulse response.

Both transforms work on the stored impulse response only, never on the
recording, and return new arrays: the samples passed in are not changed and
no analysis number is recomputed. See docs/design/GUI_2_ARCHITECTURE.md §5.3.

Frequency grid
--------------
Both put their levels on a logarithmic grid anchored at 1 kHz,
``1000 · 2^(k/n)`` for integer ``k`` and ``n`` points per octave. The anchor
makes 1 kHz, 2 kHz, 500 Hz … exact grid points whatever the range, so a
cursor readout at an octave frequency is a computed value rather than an
interpolation of two neighbours, and two results with the same ``n`` share
their frequencies.

FFT bins are mapped onto the grid in power (never in dB, which would bias a
notch or a peak): where a grid cell (``f · 2^(±1/(2n))``) holds two or more
FFT bins their power is averaged, so a wide cell at high frequency reports
the mean energy of the band it stands for instead of one arbitrary bin;
where the cell is narrower than that, the power is interpolated linearly
between the two neighbouring bins. The FFT is zero-padded (four times the
window for the spectrogram, twice for the waterfall) so that the
interpolation runs on a smooth spectrum at low frequency.

Level scale
-----------
Power is ``|X|² · 4 / (Σw)²`` so that a full-scale sine reads 0 dB re full
scale² at its peak whatever the window; this absolute value is kept in
``reference_db`` for every normalisation, so a displayed level can always be
traced back to the stored samples.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt
from numpy.lib.stride_tricks import sliding_window_view

from reverbscope.display import DisplayDataError
from reverbscope.i18n import N_
from reverbscope.models.audio import FloatArray

#: Frames per batch of the spectrogram: one FFT call each, and the point at
#: which ``cancelled`` is polled (a 1 s range at the default hop is 4 batches).
_FRAMES_PER_BATCH = 128
_TINY_POWER = 1e-30
_NORMALIZATIONS = ("peak", "direct", "none")
_MAX_POINTS_PER_OCTAVE = 96

UNIT_PEAK = N_("dB re peak")
UNIT_DIRECT = N_("dB re direct sound")
UNIT_FULL_SCALE = N_("dB re full scale²")
UNIT_FIRST_SLICE = N_("dB re first slice peak")

Note = tuple[str, dict[str, object]]
IntArray = npt.NDArray[np.int64]


class TimeFrequencyParamError(DisplayDataError):
    """The spectrogram or waterfall parameters cannot be used."""


class TransformCancelledError(Exception):
    """``cancelled()`` returned true; the view asked for a newer transform."""


def _check_finite(**values: float) -> None:
    for name, value in values.items():
        if not math.isfinite(value):
            raise TimeFrequencyParamError(
                N_("The parameter {name} must be a finite number, not {value}."),
                name=name,
                value=value,
            )


def _check_freq_range(freq_range_hz: tuple[float, float | None]) -> None:
    fmin, fmax = freq_range_hz
    _check_finite(fmin_hz=fmin)
    if fmin <= 0.0:
        raise TimeFrequencyParamError(
            N_("The lower frequency must be above 0 Hz, not {fmin_hz:g} Hz."), fmin_hz=fmin
        )
    if fmax is not None:
        _check_finite(fmax_hz=fmax)
        if fmax <= fmin:
            raise TimeFrequencyParamError(
                N_(
                    "The upper frequency ({fmax_hz:g} Hz) must be above the lower "
                    "frequency ({fmin_hz:g} Hz)."
                ),
                fmin_hz=fmin,
                fmax_hz=fmax,
            )


def _check_points_per_octave(points_per_octave: int) -> None:
    if not 1 <= points_per_octave <= _MAX_POINTS_PER_OCTAVE:
        raise TimeFrequencyParamError(
            N_("Points per octave must be between 1 and {maximum}, not {value}."),
            maximum=_MAX_POINTS_PER_OCTAVE,
            value=points_per_octave,
        )


@dataclass(frozen=True)
class SpectrogramParams:
    """How a spectrogram is computed. Times are relative to the direct sound.

    ``time_range_ms[1] = None`` runs to the end of the impulse response but
    never past ``max_duration_ms``: a 10 s tail at a 2 ms hop is 5000 frames
    that the view cannot show apart and the worker would spend seconds on.
    ``floor_db`` is relative to the normalisation reference and only clips
    what is drawn.
    """

    window_ms: float = 20.0
    hop_ms: float = 2.0
    freq_range_hz: tuple[float, float | None] = (20.0, None)
    time_range_ms: tuple[float, float | None] = (-5.0, None)
    max_duration_ms: float = 1000.0
    points_per_octave: int = 48
    normalization: str = "peak"
    floor_db: float = -90.0

    def __post_init__(self) -> None:
        _check_finite(
            window_ms=self.window_ms,
            hop_ms=self.hop_ms,
            max_duration_ms=self.max_duration_ms,
            floor_db=self.floor_db,
            time_start_ms=self.time_range_ms[0],
        )
        if self.window_ms <= 0.0:
            raise TimeFrequencyParamError(
                N_("The window must be longer than 0 ms, not {window_ms:g} ms."),
                window_ms=self.window_ms,
            )
        if not 0.0 < self.hop_ms <= self.window_ms:
            raise TimeFrequencyParamError(
                N_(
                    "The hop must be longer than 0 ms and no longer than the window "
                    "({window_ms:g} ms), not {hop_ms:g} ms."
                ),
                window_ms=self.window_ms,
                hop_ms=self.hop_ms,
            )
        _check_freq_range(self.freq_range_hz)
        start, end = self.time_range_ms
        if end is not None:
            _check_finite(time_end_ms=end)
            if end <= start:
                raise TimeFrequencyParamError(
                    N_(
                        "The end of the time range ({end_ms:g} ms) must be after its "
                        "start ({start_ms:g} ms)."
                    ),
                    start_ms=start,
                    end_ms=end,
                )
        if self.max_duration_ms <= 0.0:
            raise TimeFrequencyParamError(
                N_("The longest time range must be above 0 ms, not {value:g} ms."),
                value=self.max_duration_ms,
            )
        _check_points_per_octave(self.points_per_octave)
        if self.normalization not in _NORMALIZATIONS:
            raise TimeFrequencyParamError(
                N_("Unknown normalisation {value!r}; use peak, direct or none."),
                value=self.normalization,
            )
        if self.floor_db >= 0.0:
            raise TimeFrequencyParamError(
                N_("The display floor must be below 0 dB, not {floor_db:g} dB."),
                floor_db=self.floor_db,
            )


@dataclass(frozen=True)
class WaterfallParams:
    """How a cumulative spectral decay is computed.

    Slice ``k`` starts ``start_ms + k · step_ms`` after the direct sound and
    lasts ``window_ms``. ``smoothing`` is 1/N octave power smoothing for
    display (0 = none); ``floor_db`` is relative to the peak of the first
    slice and only clips what is drawn.
    """

    window_ms: float = 300.0
    rise_ms: float = 0.5
    taper_percent: float = 25.0
    start_ms: float = 0.0
    step_ms: float = 10.0
    slices: int = 30
    freq_range_hz: tuple[float, float | None] = (20.0, None)
    points_per_octave: int = 48
    smoothing: int = 0
    floor_db: float = -60.0

    def __post_init__(self) -> None:
        _check_finite(
            window_ms=self.window_ms,
            rise_ms=self.rise_ms,
            taper_percent=self.taper_percent,
            start_ms=self.start_ms,
            step_ms=self.step_ms,
            floor_db=self.floor_db,
        )
        if self.window_ms <= 0.0:
            raise TimeFrequencyParamError(
                N_("The window must be longer than 0 ms, not {window_ms:g} ms."),
                window_ms=self.window_ms,
            )
        if not 0.0 <= self.taper_percent <= 100.0:
            raise TimeFrequencyParamError(
                N_("The taper must be between 0 % and 100 %, not {value:g} %."),
                value=self.taper_percent,
            )
        fall_ms = self.window_ms * self.taper_percent / 100.0
        if self.rise_ms < 0.0 or self.rise_ms + fall_ms > self.window_ms:
            raise TimeFrequencyParamError(
                N_(
                    "The rise ({rise_ms:g} ms) must be at least 0 ms and fit in the "
                    "window ({window_ms:g} ms) together with the taper ({fall_ms:g} ms)."
                ),
                rise_ms=self.rise_ms,
                window_ms=self.window_ms,
                fall_ms=fall_ms,
            )
        if self.step_ms <= 0.0:
            raise TimeFrequencyParamError(
                N_("The step between slices must be longer than 0 ms, not {step_ms:g} ms."),
                step_ms=self.step_ms,
            )
        if self.slices < 1:
            raise TimeFrequencyParamError(
                N_("There must be at least one slice, not {value}."), value=self.slices
            )
        _check_freq_range(self.freq_range_hz)
        _check_points_per_octave(self.points_per_octave)
        if not 0 <= self.smoothing <= _MAX_POINTS_PER_OCTAVE:
            raise TimeFrequencyParamError(
                N_(
                    "Smoothing must be 0 (none) or 1/N octave with N from 1 to {maximum}, not {value}."
                ),
                maximum=_MAX_POINTS_PER_OCTAVE,
                value=self.smoothing,
            )
        if self.floor_db >= 0.0:
            raise TimeFrequencyParamError(
                N_("The display floor must be below 0 dB, not {floor_db:g} dB."),
                floor_db=self.floor_db,
            )


@dataclass(frozen=True)
class TimeFrequencyResult:
    """Levels on a time × log-frequency grid, ready to draw.

    ``levels_db`` has shape ``(len(times_ms), len(freqs_hz))``. ``unit`` is
    an ``N_``-marked label; ``reference_db`` is the absolute level (dB re
    full scale²) that reads 0 dB; ``notes`` are ``(N_ template, params)``
    pairs that say what was done, listed under the chart.
    """

    kind: str
    times_ms: FloatArray
    freqs_hz: FloatArray
    levels_db: FloatArray
    unit: str
    reference_db: float
    params: SpectrogramParams | WaterfallParams
    notes: tuple[Note, ...]


# --------------------------------------------------------------------------
# shared helpers


def log_grid(fmin_hz: float, fmax_hz: float, points_per_octave: int) -> FloatArray:
    """``1000 · 2^(k/n)`` for every integer ``k`` with the value in ``[fmin, fmax]``.

    Each point is computed from its own ``k`` (not by repeated multiplication)
    so 1 kHz is exactly 1000.0 and octave points carry no accumulated error.
    """
    n = points_per_octave
    k_lo = math.ceil(n * math.log2(fmin_hz / 1000.0) - 1e-9)
    k_hi = math.floor(n * math.log2(fmax_hz / 1000.0) + 1e-9)
    k = np.arange(k_lo, k_hi + 1, dtype=np.float64)
    grid = 1000.0 * np.power(2.0, k / n)
    return np.asarray(grid[(grid >= fmin_hz * (1 - 1e-12)) & (grid <= fmax_hz * (1 + 1e-12))])


def _validate_input(samples: FloatArray, sample_rate: int, direct_index: int) -> FloatArray:
    if sample_rate <= 0:
        raise DisplayDataError(
            N_("The sample rate must be above 0 Hz, not {sample_rate} Hz."),
            sample_rate=sample_rate,
        )
    data = np.asarray(samples, dtype=np.float64)
    if data.ndim != 1:
        raise DisplayDataError(N_("The impulse response must have a single channel."))
    if data.size == 0:
        raise DisplayDataError(N_("The impulse response is empty."))
    if not np.all(np.isfinite(data)):
        raise DisplayDataError(N_("The impulse response contains values that are not finite."))
    if not 0 <= direct_index < data.size:
        raise DisplayDataError(
            N_("The direct sound index {index} is outside the impulse response (0 to {last})."),
            index=direct_index,
            last=data.size - 1,
        )
    return data


def _frequency_grid(
    freq_range_hz: tuple[float, float | None], points_per_octave: int, sample_rate: int
) -> FloatArray:
    nyquist = sample_rate / 2.0
    fmin, fmax = freq_range_hz
    if fmax is None:
        fmax = nyquist
    elif fmax > nyquist:
        raise DisplayDataError(
            N_(
                "The upper frequency {fmax_hz:g} Hz is above the Nyquist frequency {nyquist_hz:g} Hz."
            ),
            fmax_hz=fmax,
            nyquist_hz=nyquist,
        )
    if fmin >= fmax:
        raise TimeFrequencyParamError(
            N_(
                "The lower frequency ({fmin_hz:g} Hz) must be below the upper "
                "frequency ({fmax_hz:g} Hz)."
            ),
            fmin_hz=fmin,
            fmax_hz=fmax,
        )
    grid = log_grid(fmin, fmax, points_per_octave)
    if grid.size == 0:
        raise TimeFrequencyParamError(
            N_("No grid frequency lies between {fmin_hz:g} Hz and {fmax_hz:g} Hz."),
            fmin_hz=fmin,
            fmax_hz=fmax,
        )
    return grid


def _bin_to_grid_matrix(grid: FloatArray, nfft: int, sample_rate: int) -> FloatArray:
    """Weights ``M`` with ``grid_power = bin_power @ M.T`` (see the module docstring)."""
    n_bins = nfft // 2 + 1
    df = sample_rate / nfft
    ratio = float(np.sqrt(grid[1] / grid[0])) if grid.size > 1 else 2.0 ** (1.0 / 96.0)
    matrix = np.zeros((grid.size, n_bins), dtype=np.float64)
    for row, f in enumerate(grid):
        lo = math.ceil(f / ratio / df)
        hi = min(n_bins - 1, math.ceil(f * ratio / df) - 1)
        if hi - lo >= 1:
            matrix[row, lo : hi + 1] = 1.0 / (hi - lo + 1)
            continue
        x = f / df
        i0 = min(math.floor(x), n_bins - 2)
        frac = x - i0
        matrix[row, i0] = 1.0 - frac
        matrix[row, i0 + 1] = frac
    return matrix


def _power_db(power: FloatArray) -> FloatArray:
    return np.asarray(10.0 * np.log10(np.maximum(power, _TINY_POWER)), dtype=np.float64)


def _next_pow2(n: int) -> int:
    return 1 << max(0, (n - 1).bit_length())


def _poll(cancelled: Callable[[], bool] | None) -> None:
    if cancelled is not None and cancelled():
        raise TransformCancelledError


def _round(value: float, digits: int = 3) -> float:
    return round(float(value), digits)


def _grid_notes(grid: FloatArray, points_per_octave: int) -> list[Note]:
    return [
        (
            N_(
                "Frequencies {fmin_hz:g} Hz to {fmax_hz:g} Hz, {points_per_octave} points "
                "per octave anchored at 1 kHz."
            ),
            {
                "fmin_hz": _round(grid[0], 2),
                "fmax_hz": _round(grid[-1], 2),
                "points_per_octave": points_per_octave,
            },
        ),
        (
            N_(
                "FFT bins are mapped to the grid in power: averaged where a grid cell "
                "holds two or more bins, interpolated linearly between bins elsewhere."
            ),
            {},
        ),
    ]


def _clip_note(floor_db: float, clipped: int) -> Note:
    return (
        N_(
            "Levels below {floor_db:g} dB are drawn at {floor_db:g} dB ({clipped} values, display only)."
        ),
        {"floor_db": floor_db, "clipped": clipped},
    )


# --------------------------------------------------------------------------
# spectrogram


def spectrogram(
    samples: FloatArray,
    sample_rate: int,
    direct_index: int,
    params: SpectrogramParams = SpectrogramParams(),  # noqa: B008 - frozen, never mutated
    *,
    cancelled: Callable[[], bool] | None = None,
) -> TimeFrequencyResult:
    """Short-time power spectrum of the impulse response on the 1 kHz log grid.

    Frame centres lie on a hop grid anchored at the direct sound, so 0 ms is
    always a frame centre and the direct sound is never smeared across two
    frames. A frame that runs off either end of the response is zero-padded
    when at least half its window holds data; otherwise it is dropped (and
    counted in the notes) rather than drawn as an artificial fade.
    """
    data = _validate_input(samples, sample_rate, direct_index)
    _poll(cancelled)
    win = round(params.window_ms * sample_rate / 1000.0)
    if win < 4:
        raise TimeFrequencyParamError(
            N_("The window of {window_ms:g} ms is shorter than 4 samples at {sample_rate} Hz."),
            window_ms=params.window_ms,
            sample_rate=sample_rate,
        )
    hop = max(1, round(params.hop_ms * sample_rate / 1000.0))
    grid = _frequency_grid(params.freq_range_hz, params.points_per_octave, sample_rate)
    nfft = _next_pow2(4 * win)
    window = np.hanning(win + 2)[1:-1]  # no zero end points: every sample counts
    scale = 4.0 / float(np.sum(window)) ** 2
    weights = _bin_to_grid_matrix(grid, nfft, sample_rate)

    n = data.size
    end_of_ir_ms = (n - 1 - direct_index) * 1000.0 / sample_rate
    start_ms, end_ms = params.time_range_ms
    capped = False
    if end_ms is None:
        end_ms = end_of_ir_ms
        if end_ms > params.max_duration_ms:
            end_ms, capped = params.max_duration_ms, True
    j_lo = math.ceil(start_ms * sample_rate / 1000.0 / hop - 1e-9)
    j_hi = math.floor(end_ms * sample_rate / 1000.0 / hop + 1e-9)
    half = win // 2
    padded = np.concatenate([np.zeros(win), data, np.zeros(win)])
    frames_view = sliding_window_view(padded, win)

    j = np.arange(j_lo, j_hi + 1)
    first = direct_index + j * hop - half  # first sample of each frame in ``data``
    inside = np.clip(first + win, 0, n) - np.clip(first, 0, n)
    keep = inside * 2 >= win
    dropped = int(np.count_nonzero(~keep))
    j, first = j[keep], first[keep]
    if j.size == 0:
        raise DisplayDataError(
            N_(
                "The impulse response is too short for one spectrogram frame in the "
                "chosen time range (a frame needs {needed_ms:g} ms of data)."
            ),
            needed_ms=_round(win / 2 * 1000.0 / sample_rate),
        )

    def frame_power(starts: IntArray) -> FloatArray:
        block = frames_view[starts + win] * window
        spectrum = np.fft.rfft(block, nfft, axis=1)
        power = (spectrum.real**2 + spectrum.imag**2) * scale
        return np.asarray(power @ weights.T, dtype=np.float64)

    chunks: list[FloatArray] = []
    for begin in range(0, j.size, _FRAMES_PER_BATCH):
        _poll(cancelled)
        chunks.append(frame_power(first[begin : begin + _FRAMES_PER_BATCH]))
    _poll(cancelled)
    absolute_db = _power_db(np.concatenate(chunks, axis=0))

    if params.normalization == "peak":
        reference = float(np.max(absolute_db))
        unit = UNIT_PEAK
        norm_note: Note = (
            N_("Levels in dB re the largest value shown ({reference_db:.1f} dB re full scale²)."),
            {"reference_db": _round(reference, 2)},
        )
    elif params.normalization == "direct":
        direct_first = np.array([direct_index - half])
        reference = float(np.max(_power_db(frame_power(direct_first))))
        unit = UNIT_DIRECT
        norm_note = (
            N_(
                "Levels in dB re the frame that holds the direct sound "
                "({reference_db:.1f} dB re full scale²)."
            ),
            {"reference_db": _round(reference, 2)},
        )
    else:
        reference = 0.0
        unit = UNIT_FULL_SCALE
        norm_note = (N_("Levels in dB re full scale²: a full-scale sine reads 0 dB."), {})

    relative = absolute_db - reference
    clipped = int(np.count_nonzero(relative < params.floor_db))
    levels = np.maximum(relative, params.floor_db)
    times = j * hop * 1000.0 / sample_rate

    notes: list[Note] = [
        (
            N_(
                "Hann window of {window_ms:g} ms ({window_samples} samples), FFT length "
                "{nfft}, hop {hop_ms:g} ms."
            ),
            {
                "window_ms": _round(win * 1000.0 / sample_rate),
                "window_samples": win,
                "nfft": nfft,
                "hop_ms": _round(hop * 1000.0 / sample_rate),
            },
        ),
        *_grid_notes(grid, params.points_per_octave),
        (
            N_(
                "Frame centres {start_ms:g} ms to {end_ms:g} ms after the direct sound "
                "({frames} frames)."
            ),
            {"start_ms": _round(times[0]), "end_ms": _round(times[-1]), "frames": int(j.size)},
        ),
        norm_note,
    ]
    if capped:
        notes.append(
            (
                N_(
                    "The time range stops at {max_ms:g} ms; the impulse response runs to {end_ms:g} ms."
                ),
                {"max_ms": params.max_duration_ms, "end_ms": _round(end_of_ir_ms)},
            )
        )
    if dropped:
        notes.append(
            (
                N_(
                    "Frames dropped because less than half of their window lies inside "
                    "the impulse response: {dropped}."
                ),
                {"dropped": dropped},
            )
        )
    notes.append(_clip_note(params.floor_db, clipped))
    return TimeFrequencyResult(
        kind="spectrogram",
        times_ms=np.asarray(times, dtype=np.float64),
        freqs_hz=grid,
        levels_db=np.asarray(levels, dtype=np.float64),
        unit=unit,
        reference_db=reference,
        params=params,
        notes=tuple(notes),
    )


# --------------------------------------------------------------------------
# waterfall


def _slice_window(win: int, rise: int, fall: int) -> FloatArray:
    window = np.ones(win, dtype=np.float64)
    if rise > 0:
        window[:rise] = np.hanning(2 * rise + 2)[1 : rise + 1]
    if fall > 0:
        window[win - fall :] = np.hanning(2 * fall + 2)[fall + 1 : -1]
    return window


def _smooth_octave(power: FloatArray, points_per_octave: int, fraction: int) -> FloatArray:
    """Average power over ±1/(2·fraction) octave on the log grid (edges use what exists)."""
    half = round(points_per_octave / (2.0 * fraction))
    if half < 1:
        return power
    cumulative = np.concatenate([np.zeros((power.shape[0], 1)), np.cumsum(power, axis=1)], axis=1)
    idx = np.arange(power.shape[1])
    lo = np.clip(idx - half, 0, power.shape[1])
    hi = np.clip(idx + half + 1, 0, power.shape[1])
    return np.asarray((cumulative[:, hi] - cumulative[:, lo]) / (hi - lo), dtype=np.float64)


def cumulative_spectral_decay(
    samples: FloatArray,
    sample_rate: int,
    direct_index: int,
    params: WaterfallParams = WaterfallParams(),  # noqa: B008 - frozen, never mutated
    *,
    cancelled: Callable[[], bool] | None = None,
) -> TimeFrequencyResult:
    """One spectrum per slice of the decay, in dB re the peak of the first slice.

    Each slice keeps its full window length: samples past the end of the
    response are zero, so later slices fall as the energy that remains falls
    (that is what a waterfall shows). A slice that would start after the end
    holds no data at all and is dropped, so the plot does not end in a flat
    slab of floor.
    """
    data = _validate_input(samples, sample_rate, direct_index)
    _poll(cancelled)
    win = round(params.window_ms * sample_rate / 1000.0)
    if win < 4:
        raise TimeFrequencyParamError(
            N_("The window of {window_ms:g} ms is shorter than 4 samples at {sample_rate} Hz."),
            window_ms=params.window_ms,
            sample_rate=sample_rate,
        )
    grid = _frequency_grid(params.freq_range_hz, params.points_per_octave, sample_rate)
    rise = min(win, round(params.rise_ms * sample_rate / 1000.0))
    fall = min(win - rise, round(win * params.taper_percent / 100.0))
    window = _slice_window(win, rise, fall)
    nfft = _next_pow2(2 * win)
    scale = 4.0 / float(np.sum(window)) ** 2
    weights = _bin_to_grid_matrix(grid, nfft, sample_rate)

    n = data.size
    starts = np.array(
        [
            direct_index + round((params.start_ms + k * params.step_ms) * sample_rate / 1000.0)
            for k in range(params.slices)
        ]
    )
    keep = starts < n
    dropped = int(np.count_nonzero(~keep))
    starts = starts[keep]
    if starts.size == 0 or not keep[0]:
        raise DisplayDataError(
            N_(
                "The impulse response ends before the first waterfall slice starts "
                "({start_ms:g} ms after the direct sound)."
            ),
            start_ms=params.start_ms,
        )

    powers = np.empty((starts.size, grid.size), dtype=np.float64)
    for row, start in enumerate(starts):
        _poll(cancelled)
        segment = np.zeros(win, dtype=np.float64)
        lo, hi = max(0, int(start)), min(n, int(start) + win)
        segment[lo - start : hi - start] = data[lo:hi]
        spectrum = np.fft.rfft(segment * window, nfft)
        powers[row] = ((spectrum.real**2 + spectrum.imag**2) * scale) @ weights.T
    _poll(cancelled)
    if params.smoothing:
        powers = _smooth_octave(powers, params.points_per_octave, params.smoothing)

    absolute_db = _power_db(powers)
    reference = float(np.max(absolute_db[0]))
    relative = absolute_db - reference
    clipped = int(np.count_nonzero(relative < params.floor_db))
    levels = np.maximum(relative, params.floor_db)
    times = (starts - direct_index) * 1000.0 / sample_rate

    notes: list[Note] = [
        (
            N_(
                "Slice window of {window_ms:g} ms: half-Hann rise of {rise_ms:g} ms, flat, "
                "half-Hann fall over the last {taper_percent:g} %; FFT length {nfft}."
            ),
            {
                "window_ms": _round(win * 1000.0 / sample_rate),
                "rise_ms": _round(rise * 1000.0 / sample_rate),
                "taper_percent": params.taper_percent,
                "nfft": nfft,
            },
        ),
        (
            N_(
                "{slices} slices starting {start_ms:g} ms to {end_ms:g} ms after the "
                "direct sound, every {step_ms:g} ms; samples past the end of the impulse "
                "response count as zero."
            ),
            {
                "slices": int(starts.size),
                "start_ms": _round(times[0]),
                "end_ms": _round(times[-1]),
                "step_ms": params.step_ms,
            },
        ),
        *_grid_notes(grid, params.points_per_octave),
        (
            N_(
                "Levels in dB re the peak of the first slice ({reference_db:.1f} dB re full scale²)."
            ),
            {"reference_db": _round(reference, 2)},
        ),
    ]
    if params.smoothing:
        notes.append(
            (
                N_("Display smoothing: 1/{fraction} octave, averaged in power."),
                {"fraction": params.smoothing},
            )
        )
    if dropped:
        notes.append(
            (
                N_(
                    "Slices dropped because they start after the end of the impulse response: {dropped}."
                ),
                {"dropped": dropped},
            )
        )
    notes.append(_clip_note(params.floor_db, clipped))
    return TimeFrequencyResult(
        kind="waterfall",
        times_ms=np.asarray(times, dtype=np.float64),
        freqs_hz=grid,
        levels_db=np.asarray(levels, dtype=np.float64),
        unit=UNIT_FIRST_SLICE,
        reference_db=reference,
        params=params,
        notes=tuple(notes),
    )
