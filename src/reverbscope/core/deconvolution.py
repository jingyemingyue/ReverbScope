"""Deconvolution of the recorded sweep and location of the impulse response.

Because linear convolution is shift invariant, the recording is convolved with
the inverse filter as a whole; the linear impulse response then appears at
``sweep_start + len(reference) - 1 + acoustic_delay`` in the output. Nothing is
cut before deconvolution, so no manual trimming is required from the user.

Output sample ``i`` of the full convolution depends only on recording samples
``<= i``. The part of the impulse response ``tau`` samples after the direct
sound is therefore exact as long as the recording continues for ``tau``
samples after the end of the sweep and no further excitation (a second sweep
pass) has started by then. This is what ``valid_length`` measures.

Harmonic distortion of the k-th order appears ``L * ln(k)`` before the linear
response (Farina 2000). Those windows are excluded from the direct-sound
margin and evaluated separately (:func:`harmonic_distortion_levels`), against
a floor that holds no harmonic response nor the room's decay after one.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy import fft as sfft
from scipy.ndimage import maximum_filter1d
from scipy.signal import fftconvolve, find_peaks
from scipy.signal.windows import tukey

from reverbscope.core.sweep import normalisation_band_hz
from reverbscope.errors import AnalysisError, InvalidAudioError
from reverbscope.i18n import diag
from reverbscope.models.audio import FloatArray
from reverbscope.models.result import ExcitationBand, HarmonicDistortion

#: Highest harmonic order whose pre-response window is handled.
HARMONIC_MAX_ORDER = 5
#: Window around the k-th harmonic response: this much before its direct part
#: (band-limited pulse spread) ...
HARMONIC_WINDOW_BEFORE_S = 0.005
#: ... and this much after it (its own early reflections). Both are limited to
#: half the distance to the neighbouring harmonic (or linear) response.
HARMONIC_WINDOW_AFTER_S = 0.050
#: A harmonic level is reported only if it is this far above the floor (dB).
HARMONIC_DETECTION_MARGIN_DB = 6.0
#: Another sweep pass is a pulse at most this far below the main peak (dB) ...
PASS_LEVEL_DB = 20.0
#: ... at least this many reference lengths away from any other pass ...
PASS_MIN_SEPARATION = 0.95
#: ... that stands at least this far above the content just before it (dB),
#: within a window of ``PASS_PULSE_WINDOW_S`` (limited to 5 % of the reference
#: length and to half the second-harmonic offset). The last condition rejects
#: samples of a reverberant tail, which are never far above what precedes them.
PASS_PULSE_MARGIN_DB = 10.0
PASS_PULSE_WINDOW_S = 0.1
#: Passes within this many dB of the loudest complete pass count as equal; of
#: those, the one followed by the most recorded decay is analysed.
PASS_EQUAL_DB = 3.0
#: Content around other sweep passes that is excluded from the margin window.
_PASS_EXCLUDE_BEFORE_S = 0.005
_PASS_EXCLUDE_AFTER_S = 0.050
_TINY = 1e-300
#: An earlier local peak this close to the loudest sample (dB), with a quiet
#: gap between them, is a separate arrival. It may be the direct sound and a
#: louder reflection, so time zero is not trusted. Weaker pre-echoes are left
#: alone: there is no way to tell them from the direct sound, and moving the
#: marker would be a guess.
EARLIER_ARRIVAL_MAX_DB = 20.0
#: The gap between that peak and the loudest sample must be at least this quiet
#: (dB below both), so filter ringing and a noise floor are not arrivals.
EARLIER_ARRIVAL_GAP_DB = 12.0
#: And the peak must stand this far above the median of the look-back, so a
#: single noise spike is not an arrival.
EARLIER_ARRIVAL_ABOVE_BACKGROUND_DB = 12.0
#: How far before the loudest sample a rival arrival is sought (s). Early
#: reflections that can steal time zero sit inside this; a longer look-back
#: mostly sees the pre-roll.
EARLIER_ARRIVAL_LOOKBACK_S = 0.10

Window = tuple[int, int]


def deconvolve(recording: FloatArray, inverse: FloatArray) -> FloatArray:
    """Full linear convolution of the recording with the inverse filter."""
    if recording.ndim != 1 or inverse.ndim != 1:
        raise InvalidAudioError("deconvolve expects mono arrays")
    if recording.shape[0] < inverse.shape[0]:
        # diag(): on the loopback path this message is stored (LoopbackResult.reason).
        raise InvalidAudioError(
            diag(
                "recording is shorter than the reference sweep; the file does not contain "
                "the full sweep"
            )
        )
    return np.asarray(fftconvolve(recording, inverse, mode="full"), dtype=np.float64)


@dataclass(frozen=True)
class HarmonicWindow:
    """Samples ``[start, stop)`` of ``h_full`` holding the k-th harmonic response."""

    order: int
    offset_s: float
    start: int
    stop: int
    #: Samples of the window before / after the harmonic's direct part.
    before: int
    after: int


def harmonic_windows(
    peak: int,
    *,
    sweep_rate_s: float,
    sample_rate: int,
    max_order: int = HARMONIC_MAX_ORDER,
) -> tuple[HarmonicWindow, ...]:
    """Windows of the harmonic pre-responses (k = 2..max_order) of the pulse at ``peak``.

    The k-th response starts ``L * ln(k)`` before the linear one. Each window
    spans ``HARMONIC_WINDOW_BEFORE_S`` before and ``HARMONIC_WINDOW_AFTER_S``
    after that point, each limited to half the distance to the neighbouring
    response so that windows never overlap each other or the linear response.
    Indices may be negative (outside the signal); callers clip them.
    """
    offsets = [sweep_rate_s * math.log(k) for k in range(1, max_order + 2)]
    windows: list[HarmonicWindow] = []
    for k in range(2, max_order + 1):
        before_s = min(HARMONIC_WINDOW_BEFORE_S, 0.5 * (offsets[k] - offsets[k - 1]))
        after_s = min(HARMONIC_WINDOW_AFTER_S, 0.5 * (offsets[k - 1] - offsets[k - 2]))
        centre = peak - round(offsets[k - 1] * sample_rate)
        before = max(1, round(before_s * sample_rate))
        after = max(1, round(after_s * sample_rate))
        windows.append(
            HarmonicWindow(
                order=k,
                offset_s=float(offsets[k - 1]),
                start=centre - before,
                stop=centre + after + 1,
                before=before,
                after=after,
            )
        )
    return tuple(windows)


def _allowed_segments(
    length: int, start: int, stop: int, excluded: tuple[Window, ...]
) -> list[Window]:
    """Parts of ``[start, stop)`` (clipped to the signal) outside ``excluded``."""
    lo = max(0, start)
    hi = min(length, max(lo, stop))
    if hi <= lo:
        return []
    allowed = np.ones(hi - lo, dtype=bool)
    for start, stop in excluded:
        a, b = max(start, lo), min(stop, hi)
        if b > a:
            allowed[a - lo : b - lo] = False
    edges = np.flatnonzero(np.diff(np.concatenate([[0], allowed.astype(np.int8), [0]])))
    return [(lo + int(s), lo + int(e)) for s, e in zip(edges[0::2], edges[1::2], strict=True)]


def _allowed_pre_peak_segments(
    length: int, peak: int, near: int, far: int, excluded: tuple[Window, ...]
) -> list[Window]:
    """Parts of ``[peak - far, peak - near)`` (clipped to the signal) outside ``excluded``."""
    return _allowed_segments(length, peak - far, peak - near, excluded)


def pre_peak_margin_db(
    magnitude: FloatArray,
    peak: int,
    *,
    sample_rate: int,
    near_ms: float,
    far_s: float,
    excluded: tuple[Window, ...] = (),
) -> float | None:
    """dB between ``magnitude[peak]`` and the strongest allowed content before it.

    The window is ``[peak - far_s, peak - near_ms]`` minus ``excluded``.
    Returns ``None`` when nothing is left to compare with.
    """
    near = round(near_ms * sample_rate / 1000.0)
    far = round(far_s * sample_rate)
    segments = _allowed_pre_peak_segments(magnitude.shape[0], peak, near, far, excluded)
    if not segments:
        return None
    before = max(float(np.max(magnitude[a:b])) for a, b in segments)
    return float(20.0 * np.log10(max(float(magnitude[peak]), _TINY) / max(before, _TINY)))


def direct_arrival_warning(earlier_arrival_db: float | None) -> str | None:
    """Why time zero is not trusted, or ``None`` when no rival arrival was found.

    ``earlier_arrival_db`` is negative (the rival is below the loudest peak).
    """
    if earlier_arrival_db is None:
        return None
    return diag(
        "an earlier arrival is only {level_db:.1f} dB below the loudest peak and is separated "
        "from it, so the loudest peak may be a reflection rather than the direct sound; decay "
        "and energy metrics are not trusted",
        level_db=-earlier_arrival_db,
    )


def _distinct_earlier_arrival_db(
    magnitude: FloatArray,
    peak: int,
    *,
    sample_rate: int,
    near_ms: float,
    far_s: float,
    excluded: tuple[Window, ...],
) -> float | None:
    """Level (dB, negative) of the strongest distinct peak before ``peak``.

    ``None`` when nothing before the loudest sample is both within
    :data:`EARLIER_ARRIVAL_MAX_DB` and separated from it by a quiet gap. The
    loudest sample is not moved: a weak pre-echo and the true direct sound
    look the same, so a rival withholds trust instead of guessing time zero.
    """
    near = round(near_ms * sample_rate / 1000.0)
    far = round(min(far_s, EARLIER_ARRIVAL_LOOKBACK_S) * sample_rate)
    hi = peak - max(near, 1)
    lo = max(0, peak - far)
    if hi - lo < 3:
        return None
    segment = np.array(magnitude[lo:hi], dtype=np.float64, copy=True)
    for start, stop in excluded:
        a = max(0, start - lo)
        b = min(segment.shape[0], stop - lo)
        if b > a:
            segment[a:b] = 0.0
    background = float(np.median(segment))
    peak_value = float(magnitude[peak])
    if not np.isfinite(peak_value) or peak_value <= 0.0:
        return None
    level_floor = peak_value * 10.0 ** (-EARLIER_ARRIVAL_MAX_DB / 20.0)
    if background > 0.0:
        level_floor = max(
            level_floor,
            background * 10.0 ** (EARLIER_ARRIVAL_ABOVE_BACKGROUND_DB / 20.0),
        )
    padded = np.concatenate(([0.0], segment, [0.0]))
    distance = max(1, round(0.0003 * sample_rate))
    indices, _properties = find_peaks(padded, height=level_floor, distance=distance)
    gap_limit = 10.0 ** (-EARLIER_ARRIVAL_GAP_DB / 20.0)
    best: float | None = None
    for index in indices:
        candidate = int(index) - 1
        if candidate < 0 or candidate >= segment.shape[0]:
            continue
        cand_value = float(segment[candidate])
        if cand_value < level_floor:
            continue
        gap = magnitude[lo + candidate + 1 : hi]
        if gap.size == 0:
            continue
        loudest_between = float(np.max(gap))
        if loudest_between > cand_value * gap_limit or loudest_between > peak_value * gap_limit:
            continue
        relative = 20.0 * math.log10(cand_value / peak_value)
        if best is None or relative > best:
            best = float(relative)
    return best


def _pulse_window(reference_length: int, sample_rate: int, sweep_rate_s: float | None) -> int:
    window_s = min(PASS_PULSE_WINDOW_S, 0.05 * reference_length / sample_rate)
    if sweep_rate_s is not None:
        window_s = min(window_s, 0.5 * sweep_rate_s * math.log(2.0))
    return round(window_s * sample_rate)


def find_sweep_passes(
    magnitude: FloatArray,
    peak: int,
    *,
    reference_length: int,
    sample_rate: int,
    sweep_rate_s: float | None = None,
    excluded: tuple[Window, ...] = (),
) -> tuple[int, ...]:
    """Peak indices of all sweep passes in ``|h_full|`` (ascending, includes ``peak``).

    A further pass is a pulse no more than ``PASS_LEVEL_DB`` below the main
    peak, at least ``PASS_MIN_SEPARATION`` reference lengths from every other
    pass, outside ``excluded`` (the harmonic windows of the main pass) and at
    least ``PASS_PULSE_MARGIN_DB`` above the strongest content in the short
    window before it. Passes more than ``PASS_LEVEL_DB`` weaker are not found.

    A reference shorter than two samples means there was no sweep (an
    imported impulse response): there are no passes to find, and a
    one-sample separation would make every loud sample a "pass" (quadratic
    time on a long, loud file; #10).
    """
    if reference_length < 2:
        return (peak,)
    level = float(magnitude[peak])
    threshold = level * 10.0 ** (-PASS_LEVEL_DB / 20.0)
    separation = max(1, round(PASS_MIN_SEPARATION * reference_length))
    candidates = np.flatnonzero(magnitude >= threshold)
    candidates = candidates[np.abs(candidates - peak) >= separation]
    for start, stop in excluded:
        candidates = candidates[(candidates < start) | (candidates >= stop)]
    if candidates.size == 0:
        return (peak,)

    near = max(1, round(0.002 * sample_rate))
    window = _pulse_window(reference_length, sample_rate, sweep_rate_s)
    size = window - near
    if size >= 1:
        # Trailing maximum over [c - window, c - near): a centred filter of
        # ``size`` evaluated at c - window + size // 2.
        running = maximum_filter1d(magnitude, size=size, mode="constant", cval=0.0)
        index = candidates - window + size // 2
        prior = np.where(index >= 0, running[np.clip(index, 0, None)], np.inf)
        partial = np.flatnonzero(index < 0)
        for j in partial:
            c = int(candidates[j])
            segment = magnitude[max(0, c - window) : max(0, c - near)]
            prior[j] = float(np.max(segment)) if segment.size else 0.0
        ratio = 10.0 ** (PASS_PULSE_MARGIN_DB / 20.0)
        candidates = candidates[magnitude[candidates] >= prior * ratio]

    accepted = [peak]
    for c in candidates[np.argsort(-magnitude[candidates], kind="stable")]:
        if all(abs(int(c) - a) >= separation for a in accepted):
            accepted.append(int(c))
    return tuple(sorted(accepted))


@dataclass(frozen=True)
class LocatedImpulseResponse:
    samples: FloatArray
    direct_index: int
    pre_delay_samples: int
    #: Index of the direct sound in ``h_full``.
    peak_index: int
    peak_value: float
    valid_length_samples: int
    #: Start of the analysed sweep in the recording, clamped to >= 0.
    sweep_start_index_in_recording: int
    #: Same, unclamped: negative when the recording starts inside the sweep.
    sweep_start_raw_index: int
    pre_peak_margin_db: float | None
    truncated_by_max_length: bool
    #: ``h_full`` indices of all detected sweep passes (ascending).
    pass_peak_indices: tuple[int, ...] = ()
    #: Start of the first sweep pass in the recording (unclamped).
    first_sweep_start_raw_index: int = 0
    #: True when the IR ends early because the next sweep pass starts.
    truncated_by_next_pass: bool = False
    #: Harmonic windows of the analysed pass (empty without a sweep rate).
    harmonic_windows: tuple[HarmonicWindow, ...] = ()
    #: All windows excluded from the margin (harmonics, other passes).
    excluded_windows: tuple[Window, ...] = ()
    #: Strongest distinct peak before the loudest sample, in dB (negative).
    #: ``None`` when time zero does not have a rival arrival.
    earlier_arrival_db: float | None = None

    @property
    def sweep_passes(self) -> int:
        return max(1, len(self.pass_peak_indices))

    @property
    def first_sweep_start_index_in_recording(self) -> int:
        return max(0, self.first_sweep_start_raw_index)


def locate_impulse_response(
    h_full: FloatArray,
    *,
    recording_length: int,
    reference_length: int,
    sample_rate: int,
    pre_delay_ms: float,
    max_length_s: float,
    sweep_rate_s: float | None = None,
    start_tolerance_samples: int = 0,
    margin_near_ms: float = 2.0,
    margin_far_s: float = 0.5,
) -> LocatedImpulseResponse:
    """Find the direct sound in the deconvolved signal and cut the IR around it.

    The direct sound is the strongest sample of ``|h_full|``. A distinct earlier
    peak within :data:`EARLIER_ARRIVAL_MAX_DB`, separated by a quiet gap, is
    recorded on :attr:`LocatedImpulseResponse.earlier_arrival_db` and is not
    used as time zero: it may be the direct sound or a pre-echo, and guessing
    would move every later figure. Callers withhold decay and energy metrics.
    Other sweep passes are searched with :func:`find_sweep_passes`; when there
    are several, only passes whose sweep starts no more than
    ``start_tolerance_samples`` before the recording are considered. Of those
    within ``PASS_EQUAL_DB`` of the loudest, the one followed by the most
    recorded decay (up to ``max_length_s``) is analysed, the louder one on a
    tie; its IR ends where the next pass starts.

    The *pre-peak margin* compares the direct sound with the strongest content
    in ``[peak - margin_far_s, peak - margin_near_ms]``. When ``sweep_rate_s``
    (the sweep's ``L``) is known, the windows of the harmonic pre-responses
    (k = 2..5) are excluded, as are windows around other passes, so the margin
    reflects noise, pre-ringing and a possibly wrong reference - not the
    distortion level, which is reported separately. Without ``sweep_rate_s``
    harmonic responses of short sweeps can fall into the window and lower the
    margin. ``None`` means there was nothing to compare with.
    """
    if h_full.ndim != 1 or h_full.shape[0] == 0:
        raise AnalysisError(diag("deconvolved signal is empty"))
    magnitude = np.abs(h_full)
    strongest = int(np.argmax(magnitude))
    strongest_value = float(h_full[strongest])
    if not np.isfinite(strongest_value) or strongest_value == 0.0:
        raise AnalysisError(diag("deconvolved signal has no usable peak (silent recording?)"))

    def windows_for(index: int) -> tuple[HarmonicWindow, ...]:
        if sweep_rate_s is None:
            return ()
        return harmonic_windows(index, sweep_rate_s=sweep_rate_s, sample_rate=sample_rate)

    passes = find_sweep_passes(
        magnitude,
        strongest,
        reference_length=reference_length,
        sample_rate=sample_rate,
        sweep_rate_s=sweep_rate_s,
        excluded=tuple((w.start, w.stop) for w in windows_for(strongest)),
    )
    offset = reference_length - 1
    max_len = round(max_length_s * sample_rate)

    def decay_after(index: int) -> int:
        """Samples after ``index`` before the recording ends or the next pass starts."""
        later_starts = [p - offset for p in passes if p > index]
        return min([recording_length, *later_starts]) - 1 - index

    peak = strongest
    complete = [p for p in passes if p - offset >= -start_tolerance_samples]
    if len(passes) > 1 and complete:
        # Passes of about the same level differ only by noise, so the loudest
        # one is a random pick; the one with a recorded decay after it is the
        # one worth analysing (usually the last).
        loudest = max(float(magnitude[p]) for p in complete)
        floor = loudest * 10.0 ** (-PASS_EQUAL_DB / 20.0)
        peak = max(
            (p for p in complete if float(magnitude[p]) >= floor),
            key=lambda p: (min(decay_after(p), max_len), float(magnitude[p])),
        )
    peak_value = float(h_full[peak])

    later = [p for p in passes if p > peak]
    usable_end = recording_length
    truncated_by_next = False
    if later:
        next_start = later[0] - offset
        if next_start < recording_length:
            usable_end = next_start
            truncated_by_next = True
    valid_length = usable_end - 1 - peak
    if valid_length <= 0:
        if truncated_by_next:
            raise AnalysisError(
                diag(
                    "the next sweep pass starts right after this one; the room decay after the "
                    "sweep was not recorded. Leave silence after each sweep (the generated test "
                    "file contains it) or record a single pass"
                )
            )
        if peak >= recording_length:
            # The direct sound arrives when the sweep ends; past the last
            # recorded sample, the export stopped inside the sweep.
            raise InvalidAudioError(
                diag(
                    "the recording ends about {missing_s:.2f} s before the sweep does, so the "
                    "end of the sweep and the room decay after it were not recorded. Export "
                    "the whole take, with the silence after the sweep",
                    missing_s=(peak - recording_length + 1) / sample_rate,
                )
            )
        raise AnalysisError(
            diag(
                "the direct sound was found at the very end of the recording; "
                "the recording does not contain the room decay after the sweep"
            )
        )
    truncated = valid_length > max_len
    length_after_peak = min(valid_length, max_len)

    pre_delay = round(pre_delay_ms * sample_rate / 1000.0)
    start = max(0, peak - pre_delay)
    end = min(h_full.shape[0], peak + length_after_peak + 1)
    samples = np.array(h_full[start:end], dtype=np.float64)

    harmonics = windows_for(peak)
    excluded: list[Window] = [(w.start, w.stop) for w in harmonics]
    before = round(_PASS_EXCLUDE_BEFORE_S * sample_rate)
    after = round(_PASS_EXCLUDE_AFTER_S * sample_rate)
    excluded.extend((p - before, p + after + 1) for p in passes if p != peak)
    margin_db = pre_peak_margin_db(
        magnitude,
        peak,
        sample_rate=sample_rate,
        near_ms=margin_near_ms,
        far_s=margin_far_s,
        excluded=tuple(excluded),
    )
    earlier_arrival_db = _distinct_earlier_arrival_db(
        magnitude,
        peak,
        sample_rate=sample_rate,
        near_ms=margin_near_ms,
        far_s=margin_far_s,
        excluded=tuple(excluded),
    )

    sweep_start = peak - offset
    return LocatedImpulseResponse(
        samples=samples,
        direct_index=peak - start,
        pre_delay_samples=peak - start,
        peak_index=peak,
        peak_value=peak_value,
        valid_length_samples=valid_length,
        sweep_start_index_in_recording=max(0, sweep_start),
        sweep_start_raw_index=sweep_start,
        pre_peak_margin_db=margin_db,
        truncated_by_max_length=truncated,
        pass_peak_indices=passes,
        first_sweep_start_raw_index=passes[0] - offset,
        truncated_by_next_pass=truncated_by_next,
        harmonic_windows=harmonics,
        excluded_windows=tuple(excluded),
        earlier_arrival_db=earlier_arrival_db,
    )


def confidence_label(margin_db: float | None) -> str:
    """Map the pre-peak margin to high (>= 20 dB), medium (>= 10 dB) or low.

    ``None`` (nothing before the direct sound could be checked) maps to "low":
    the detection is unverified.
    """
    if margin_db is None or not math.isfinite(margin_db):
        return "low"
    if margin_db >= 20.0:
        return "high"
    if margin_db >= 10.0:
        return "medium"
    return "low"


def _band_energy(segment: FloatArray, sample_rate: int, band: tuple[float, float]) -> float:
    """In-band energy of a Tukey-tapered segment (independent of the FFT length)."""
    n = segment.shape[0]
    taper_n = max(1, min(round(0.001 * sample_rate), n // 4))
    windowed = segment * tukey(n, alpha=min(1.0, 2.0 * taper_n / n))
    nfft = int(sfft.next_fast_len(n, real=True))
    spectrum = sfft.rfft(windowed, nfft)
    freqs = np.fft.rfftfreq(nfft, 1.0 / sample_rate)
    select = (freqs >= band[0]) & (freqs <= band[1])
    return float(np.sum(np.abs(spectrum[select]) ** 2)) / nfft


def _linear_pre_peak(
    h_full: FloatArray,
    located: LocatedImpulseResponse,
    ideal_pulse: FloatArray,
    near: int,
    far: int,
) -> FloatArray:
    """What a distortion-free take holds ``far`` to ``near`` samples before the
    direct sound, without noise.

    The ideal pulse (the reference deconvolved by its own inverse) is not a
    Dirac: its endpoint artefacts reach far before its peak. Its part more
    than ``near`` samples before the peak, convolved with the measured
    response from ``near`` samples before the direct sound to the end of the
    located impulse response, gives those artefacts as this chain and room
    spread them, with no harmonic response and no harmonic's decay. Element
    ``i`` belongs to ``h_full[peak - far + i]``.
    """
    peak = located.peak_index
    out = np.zeros(max(0, far - near), dtype=np.float64)
    start = max(0, peak - near)
    response = h_full[start : peak + located.samples.shape[0] - located.direct_index]
    centre = int(np.argmax(np.abs(ideal_pulse)))
    first_offset = -min(centre, far + response.shape[0])
    kernel = ideal_pulse[centre + first_offset : max(0, centre - near)]
    if response.shape[0] == 0 or kernel.shape[0] == 0:
        return out
    spread = fftconvolve(response, kernel)
    # spread[m] belongs to h_full[start + first_offset + m].
    lo = peak - far - (start + first_offset)
    i0, i1 = max(0, -lo), min(out.shape[0], spread.shape[0] - lo)
    if i1 > i0:
        out[i0:i1] = spread[lo + i0 : lo + i1]
    return out


def _floor_chunks(segments: list[Window], n: int, max_chunks: int) -> list[Window]:
    """Window-sized chunks of the harmonic-free segments; a segment shorter than
    ``n`` (but at least ``n // 4``) contributes one chunk of its own length."""
    chunks: list[Window] = []
    for a, b in segments:
        if b - a >= n:
            chunks.extend((a + i * n, a + (i + 1) * n) for i in range((b - a) // n))
        elif b - a >= max(8, n // 4):
            chunks.append((a, b))
    if len(chunks) > max_chunks:
        picks = np.linspace(0, len(chunks) - 1, max_chunks).round().astype(int)
        chunks = [chunks[i] for i in picks]
    return chunks


def harmonic_distortion_levels(
    h_full: FloatArray,
    located: LocatedImpulseResponse,
    *,
    sample_rate: int,
    excitation_band: ExcitationBand,
    ideal_pulse: FloatArray,
    margin_near_ms: float = 2.0,
    margin_far_s: float = 0.5,
    max_floor_chunks: int = 20,
) -> tuple[HarmonicDistortion, ...]:
    """Energy of each harmonic response relative to the linear response (dB).

    For order k, the window of :func:`harmonic_windows` and a window of the
    same shape around the linear direct sound are compared over the part of
    the excitation band where both exist, ``[k*f_lo, f_hi]`` (inner part per
    :func:`~reverbscope.core.sweep.normalisation_band_hz`). Comparing spectra
    over a common band avoids the dependence of pulse peaks on bandwidth,
    sub-sample position and the constant phase offset of the harmonic pulses.

    The floor is the same measure (the strongest of up to
    ``max_floor_chunks`` window-sized chunks; shorter gaps count with their
    per-sample energy) for what a take without these harmonic responses
    holds there: the noise and the ideal pulse's own artefacts in the
    pre-peak window as this room spreads them (:func:`_linear_pre_peak`, from
    ``ideal_pulse``, the reference deconvolved by its own inverse). The
    pre-peak window of ``h_full`` itself also holds the room's decay after
    each harmonic response: with a sweep shorter than about 5 s, or in a very
    reverberant room, that floor followed the distortion level and no
    harmonic was ever 6 dB above it.

    The noise is stationary, so it is measured where no harmonic response
    lands, in two places, and the lower of the two is used. The
    ``margin_far_s`` before the earliest window holds none of the evaluated
    orders but does hold the higher ones, which strong distortion makes loud
    (the 6th and 7th of a 10 s sweep). The last ``margin_far_s`` of the valid
    record, at least ``margin_far_s`` after the direct sound, holds none but
    holds what is left of the room's decay and the products a digital
    clipper folded back. Either can only hold more than the noise. A record
    with too little after the direct sound to have that tail has only the
    first stretch.
    """
    peak = located.peak_index
    length = h_full.shape[0]
    near = round(margin_near_ms * sample_rate / 1000.0)
    far = round(margin_far_s * sample_rate)
    floor_segments = _allowed_pre_peak_segments(length, peak, near, far, located.excluded_windows)
    first = min((w.start for w in located.harmonic_windows), default=peak - near)
    pre_noise = _allowed_pre_peak_segments(length, first, 0, far, located.excluded_windows)
    # The end of the valid record, at least ``far`` after the direct sound.
    record_end = peak + located.valid_length_samples + 1
    tail_noise = _allowed_segments(
        length, max(record_end - far, peak + far), record_end, located.excluded_windows
    )
    linear_free = _linear_pre_peak(h_full, located, ideal_pulse, near, far)
    results: list[HarmonicDistortion] = []
    for w in located.harmonic_windows:
        low = w.order * excitation_band.low_hz
        if low >= excitation_band.high_hz:
            results.append(
                HarmonicDistortion(
                    order=w.order,
                    offset_s=w.offset_s,
                    level_db=None,
                    floor_db=None,
                    band_hz=None,
                    reason=diag("the harmonic lies above the excitation band"),
                )
            )
            continue
        band = normalisation_band_hz(low, excitation_band.high_hz)
        n = w.stop - w.start
        reason: str | None = None
        if w.start < 0 or peak + w.after + 1 > length:
            reason = diag("the harmonic window lies outside the deconvolved signal")
        elif band[1] - band[0] < 4.0 * sample_rate / n:
            reason = diag("the harmonic window is too short to resolve the common band")
        if reason is not None:
            results.append(
                HarmonicDistortion(
                    order=w.order,
                    offset_s=w.offset_s,
                    level_db=None,
                    floor_db=None,
                    band_hz=band,
                    reason=reason,
                )
            )
            continue
        linear = _band_energy(h_full[peak - w.before : peak + w.after + 1], sample_rate, band)
        harmonic = _band_energy(h_full[w.start : w.stop], sample_rate, band)
        # A tail shorter than the window is too short an estimate to lower the floor.
        noise_chunks = [
            _floor_chunks(pre_noise, n, max_floor_chunks),
            [(a, b) for a, b in _floor_chunks(tail_noise, n, max_floor_chunks) if b - a == n],
        ]
        if linear <= 0.0:
            reason = diag("the linear response has no energy in the common band")
        elif not any(noise_chunks):
            reason = diag("no harmonic-free content around the direct sound to compare with")
        if reason is not None:
            results.append(
                HarmonicDistortion(
                    order=w.order,
                    offset_s=w.offset_s,
                    level_db=None,
                    floor_db=None,
                    band_hz=band,
                    reason=reason,
                )
            )
            continue
        # Energy scaled to the window length, so short chunks count per sample.
        floor = min(
            max(_band_energy(h_full[a:b], sample_rate, band) * n / (b - a) for a, b in chunks)
            for chunks in noise_chunks
            if chunks
        )
        offset = peak - far
        for a, b in _floor_chunks(floor_segments, n, max_floor_chunks):
            segment = linear_free[a - offset : b - offset]
            floor = max(floor, _band_energy(segment, sample_rate, band) * n / (b - a))
        level_db = 10.0 * math.log10(max(harmonic, _TINY) / linear)
        floor_db = 10.0 * math.log10(max(floor, _TINY) / linear)
        detected = level_db >= floor_db + HARMONIC_DETECTION_MARGIN_DB
        results.append(
            HarmonicDistortion(
                order=w.order,
                offset_s=w.offset_s,
                level_db=float(level_db) if detected else None,
                floor_db=float(floor_db),
                band_hz=band,
                reason=None
                if detected
                else diag(
                    "not distinguishable from the floor (at most {level_db:.1f} dB, "
                    "floor {floor_db:.1f} dB)",
                    level_db=level_db,
                    floor_db=floor_db,
                ),
            )
        )
    return tuple(results)
