"""Background-noise analysis of a quiet segment of the recording.

All levels are digital levels in dBFS (AES17 convention: a full-scale sine
wave reads 0 dBFS RMS). Without an SPL calibration ReverbScope never converts
them to dB SPL.

Choosing the quiet segment
--------------------------
:func:`quiet_segment_candidates` returns the *positions* that may hold
background noise, in order of preference: the recording before the **first**
sweep pass, then the recording well after the **last** pass. Position alone
does not make a segment quiet, so :func:`select_quiet_part` checks the
content of each candidate before it is measured:

* runs of exact digital zeros (a DAW export that starts before the recorded
  region, or a gap between regions) are dropped; the longest remaining
  contiguous piece is used. Zeros are not background noise, and averaging
  them in pulls the level down. What is left may be shorter than
  ``min_segment_s`` but is still measured down to
  :data:`MEASURABLE_SEGMENT_S`, with a note;
* the piece is split into short blocks; blocks more than
  :data:`QUIET_EXCESS_DB` above the quietest blocks (another sweep pass, a
  chair, a door) are cut away and the longest quiet run is kept;
* a "quiet" part that is less than :data:`QUIET_MIN_BELOW_SWEEP_DB` below the
  level of the sweep itself is not background noise (typically a looped sweep
  with no silence) and is rejected.

If nothing usable remains, the next candidate is tried and otherwise every
level is reported as ``None`` with a note. Levels below
:data:`NOISE_FLOOR_DBFS` are also reported as ``None``: they are digital
silence or numerical residue, not a measured acoustic noise floor.

Mains hum
---------
Hum is searched for at the two mains frequencies. The 50 Hz and 60 Hz series
share every multiple of :data:`MAINS_SHARED_MULTIPLE_HZ` (300 Hz, their least
common multiple), so a buzz on one grid always produces peaks that also fit
the other base. Only harmonics that belong to *one* base count towards
detection, and when both bases still qualify only the better-explained one is
reported as detected. The fundamental is not required: full-wave rectifier
buzz starts at twice the mains frequency.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

import numpy as np
from scipy.signal import welch

from reverbscope.core.filters import band_fits, band_level_samples, bandpass_sos, iec_band
from reverbscope.i18n import diag
from reverbscope.models.audio import FloatArray
from reverbscope.models.result import HumCandidate, NoiseResult

_EPS = 1e-300
_SQRT2 = float(np.sqrt(2.0))
MAINS_BASE_FREQUENCIES_HZ = (50.0, 60.0)
#: Harmonics at multiples of this frequency belong to both mains series
#: (lcm(50, 60) = 300 Hz) and cannot tell the two bases apart.
MAINS_SHARED_MULTIPLE_HZ = 300.0
HUM_MAX_HARMONIC_HZ = 1000.0
HUM_MAX_HARMONICS = 12
HUM_DETECTION_PROMINENCE_DB = 10.0
#: Number of harmonics *unique to one base* needed to report hum.
HUM_MIN_HARMONICS_FOR_DETECTION = 2

#: Levels below this are not a measured acoustic noise floor: 24-bit
#: quantisation noise of a full-scale signal is already near -140 dBFS, so
#: anything quieter is digital silence, a muted region or numerical residue
#: of a synthetic file.
NOISE_FLOOR_DBFS = -140.0
#: Runs of exactly zero samples at least this long are treated as digital
#: silence and dropped from the quiet segment.
ZERO_RUN_S = 0.01
#: Block length used to check that the segment is quiet.
QUIET_BLOCK_S = 0.1
#: Blocks more than this above the quietest blocks are not background noise.
QUIET_EXCESS_DB = 10.0
#: Percentile of the block levels taken as "the quietest blocks".
QUIET_REFERENCE_PERCENTILE = 10.0
#: A quiet segment must be at least this far below the level of the sweep.
QUIET_MIN_BELOW_SWEEP_DB = 6.0
#: Shortest part that is still measured. ``min_segment_s`` decides which
#: positions are considered, but once digital silence and noisy blocks have
#: been cut away, a shorter remainder of real background noise is still a
#: better answer than none; a note says that it is shorter than configured.
MEASURABLE_SEGMENT_S = 0.2


def rms_dbfs(x: FloatArray) -> float:
    """RMS level in dBFS with the AES17 sine reference."""
    rms = float(np.sqrt(np.mean(np.asarray(x, dtype=np.float64) ** 2)))
    return float(20.0 * np.log10(max(rms * _SQRT2, _EPS)))


def peak_dbfs(x: FloatArray) -> float:
    return float(20.0 * np.log10(max(float(np.max(np.abs(x))), _EPS)))


def _measurable(level_dbfs: float) -> float | None:
    """``level_dbfs`` or ``None`` when it is below :data:`NOISE_FLOOR_DBFS`."""
    return level_dbfs if level_dbfs > NOISE_FLOOR_DBFS else None


PRE_SWEEP_SOURCE = "pre-sweep"
TAIL_SOURCE = "tail"


def _by_source(source: str, *, pre_sweep: str, tail: str, other: str) -> str:
    """The note written for ``source``: each variant is a complete sentence."""
    if source == PRE_SWEEP_SOURCE:
        return pre_sweep
    if source == TAIL_SOURCE:
        return tail
    return other


@dataclass(frozen=True)
class QuietSegment:
    """Part of the recording ``[start, end)`` that may hold background noise."""

    start: int
    end: int
    source: str
    note: str | None = None


def quiet_segment_candidates(
    *,
    recording_length: int,
    sample_rate: int,
    first_sweep_start_index: int,
    last_sweep_end_index: int,
    min_segment_s: float,
    guard_s: float = 0.1,
    skip_head_s: float = 0.05,
    expected_decay_s: float = 3.0,
) -> tuple[QuietSegment, ...]:
    """Positions that may hold background noise, best first.

    ``first_sweep_start_index`` is the start of the *first* sweep pass and
    ``last_sweep_end_index`` the end of the *last* one, so that neither an
    earlier nor a later pass can be measured as background noise. The content
    of a candidate still has to be checked with :func:`select_quiet_part`.
    """
    min_len = round(min_segment_s * sample_rate)
    head = round(skip_head_s * sample_rate)
    guard = round(guard_s * sample_rate)
    candidates: list[QuietSegment] = []
    pre_end = first_sweep_start_index - guard
    if pre_end - head >= min_len:
        candidates.append(QuietSegment(start=head, end=pre_end, source=PRE_SWEEP_SOURCE))
    tail_start = last_sweep_end_index + round(expected_decay_s * sample_rate)
    if recording_length - tail_start >= min_len:
        candidates.append(
            QuietSegment(
                start=tail_start,
                end=recording_length,
                source=TAIL_SOURCE,
                note=diag(
                    "quiet segment taken from the end of the recording; it may contain late "
                    "reverberation, so the noise floor may be overestimated"
                ),
            )
        )
    return tuple(candidates)


def _nonzero_pieces(x: FloatArray, min_run: int) -> list[tuple[int, int]]:
    """Pieces of ``x`` separated by runs of at least ``min_run`` exact zeros."""
    nonzero = x != 0.0
    if not np.any(nonzero):
        return []
    edges = np.flatnonzero(np.diff(np.concatenate([[0], nonzero.view(np.int8), [0]])))
    starts, stops = edges[0::2], edges[1::2]
    pieces: list[tuple[int, int]] = []
    for start, stop in zip(starts, stops, strict=True):
        if pieces and start - pieces[-1][1] < min_run:
            pieces[-1] = (pieces[-1][0], int(stop))
        else:
            pieces.append((int(start), int(stop)))
    return pieces


def _block_levels(x: FloatArray, block: int) -> FloatArray:
    """RMS level (dBFS) of each whole block of ``block`` samples."""
    count = x.shape[0] // block
    blocks = x[: count * block].reshape(count, block)
    mean_square = np.mean(blocks**2, axis=1)
    return np.asarray(10.0 * np.log10(np.maximum(2.0 * mean_square, _EPS)), dtype=np.float64)


def _longest_run(mask: np.ndarray) -> tuple[int, int]:
    """``[start, stop)`` of the longest run of ``True`` (``(0, 0)`` if none)."""
    if not np.any(mask):
        return 0, 0
    edges = np.flatnonzero(np.diff(np.concatenate([[0], mask.view(np.int8), [0]])))
    starts, stops = edges[0::2], edges[1::2]
    best = int(np.argmax(stops - starts))
    return int(starts[best]), int(stops[best])


@dataclass(frozen=True)
class QuietSelection:
    """Outcome of checking one candidate segment.

    ``segment`` is the part that may be measured (possibly shorter than the
    candidate) or ``None`` when the candidate is unusable; ``notes`` says what
    was excluded or why it was rejected.
    """

    segment: QuietSegment | None
    notes: tuple[str, ...] = ()


def select_quiet_part(
    recording: FloatArray,
    sample_rate: int,
    candidate: QuietSegment,
    *,
    min_segment_s: float,
    sweep_level_dbfs: float | None = None,
) -> QuietSelection:
    """Check that ``candidate`` really holds background noise.

    Drops digital silence and blocks that are much louder than the quietest
    ones, and rejects a segment that is not clearly below the sweep level.
    """
    x = np.asarray(recording[candidate.start : candidate.end], dtype=np.float64)
    min_len = max(1, round(min(min_segment_s, MEASURABLE_SEGMENT_S) * sample_rate))
    source = candidate.source
    pieces = _nonzero_pieces(x, max(1, round(ZERO_RUN_S * sample_rate)))
    if not pieces:
        return QuietSelection(
            None,
            (
                _by_source(
                    source,
                    pre_sweep=diag(
                        "the pre-sweep segment is digital silence (exact zeros); the acoustic "
                        "noise floor cannot be measured there"
                    ),
                    tail=diag(
                        "the tail segment is digital silence (exact zeros); the acoustic noise "
                        "floor cannot be measured there"
                    ),
                    other=diag(
                        "the {source} segment is digital silence (exact zeros); the acoustic "
                        "noise floor cannot be measured there",
                        source=source,
                    ),
                ),
            ),
        )
    notes: list[str] = []
    start, stop = max(pieces, key=lambda p: p[1] - p[0])
    dropped = (x.shape[0] - (stop - start)) / sample_rate
    if dropped > ZERO_RUN_S:
        notes.append(
            _by_source(
                source,
                pre_sweep=diag(
                    "{dropped:.2f} s of exact digital zeros (an export that starts before the "
                    "recorded region, or a gap between regions) were excluded from the "
                    "pre-sweep segment",
                    dropped=dropped,
                ),
                tail=diag(
                    "{dropped:.2f} s of exact digital zeros (an export that starts before the "
                    "recorded region, or a gap between regions) were excluded from the tail "
                    "segment",
                    dropped=dropped,
                ),
                other=diag(
                    "{dropped:.2f} s of exact digital zeros (an export that starts before the "
                    "recorded region, or a gap between regions) were excluded from the "
                    "{source} segment",
                    dropped=dropped,
                    source=source,
                ),
            )
        )
    if stop - start < min_len:
        remaining = {"remaining": (stop - start) / sample_rate, "needed": min_len / sample_rate}
        notes.append(
            _by_source(
                source,
                pre_sweep=diag(
                    "only {remaining:.2f} s of the pre-sweep segment are not digital silence, "
                    "less than the {needed:.2f} s a level needs",
                    **remaining,
                ),
                tail=diag(
                    "only {remaining:.2f} s of the tail segment are not digital silence, less "
                    "than the {needed:.2f} s a level needs",
                    **remaining,
                ),
                other=diag(
                    "only {remaining:.2f} s of the {source} segment are not digital silence, "
                    "less than the {needed:.2f} s a level needs",
                    source=source,
                    **remaining,
                ),
            )
        )
        return QuietSelection(None, tuple(notes))

    piece = x[start:stop]
    block = max(1, round(QUIET_BLOCK_S * sample_rate))
    if piece.shape[0] >= 3 * block:
        levels = _block_levels(piece, block)
        reference = float(np.percentile(levels, QUIET_REFERENCE_PERCENTILE))
        quiet = levels <= reference + QUIET_EXCESS_DB
        first, last = _longest_run(quiet)
        excluded = (levels.shape[0] - (last - first)) * block / sample_rate
        if (last - first) * block < min_len:
            quiet_part = {"quiet": (last - first) * block / sample_rate, "excess": QUIET_EXCESS_DB}
            notes.append(
                _by_source(
                    source,
                    pre_sweep=diag(
                        "the pre-sweep segment is not quiet: only {quiet:.2f} s of it stay "
                        "within {excess:.0f} dB of its quietest blocks (another sweep pass or a "
                        "noise event?)",
                        **quiet_part,
                    ),
                    tail=diag(
                        "the tail segment is not quiet: only {quiet:.2f} s of it stay within "
                        "{excess:.0f} dB of its quietest blocks (another sweep pass or a noise "
                        "event?)",
                        **quiet_part,
                    ),
                    other=diag(
                        "the {source} segment is not quiet: only {quiet:.2f} s of it stay "
                        "within {excess:.0f} dB of its quietest blocks (another sweep pass or a "
                        "noise event?)",
                        source=source,
                        **quiet_part,
                    ),
                )
            )
            return QuietSelection(None, tuple(notes))
        if excluded > QUIET_BLOCK_S:
            loud_part = {"excluded": excluded, "excess": QUIET_EXCESS_DB}
            notes.append(
                _by_source(
                    source,
                    pre_sweep=diag(
                        "{excluded:.2f} s of the pre-sweep segment were more than {excess:.0f} dB "
                        "above its quietest blocks (another sweep pass or a noise event?) and "
                        "were excluded",
                        **loud_part,
                    ),
                    tail=diag(
                        "{excluded:.2f} s of the tail segment were more than {excess:.0f} dB "
                        "above its quietest blocks (another sweep pass or a noise event?) and "
                        "were excluded",
                        **loud_part,
                    ),
                    other=diag(
                        "{excluded:.2f} s of the {source} segment were more than {excess:.0f} dB "
                        "above its quietest blocks (another sweep pass or a noise event?) and "
                        "were excluded",
                        source=source,
                        **loud_part,
                    ),
                )
            )
        start, stop = start + first * block, start + last * block

    if stop - start < round(min_segment_s * sample_rate):
        usable = {"usable": (stop - start) / sample_rate, "configured": min_segment_s}
        notes.append(
            _by_source(
                source,
                pre_sweep=diag(
                    "only {usable:.2f} s of the pre-sweep segment are usable instead of the "
                    "{configured:.2f} s configured; the levels come from that shorter part",
                    **usable,
                ),
                tail=diag(
                    "only {usable:.2f} s of the tail segment are usable instead of the "
                    "{configured:.2f} s configured; the levels come from that shorter part",
                    **usable,
                ),
                other=diag(
                    "only {usable:.2f} s of the {source} segment are usable instead of the "
                    "{configured:.2f} s configured; the levels come from that shorter part",
                    source=source,
                    **usable,
                ),
            )
        )
    level = rms_dbfs(x[start:stop])
    if sweep_level_dbfs is not None and level > sweep_level_dbfs - QUIET_MIN_BELOW_SWEEP_DB:
        margin = {"below": sweep_level_dbfs - level, "sweep": sweep_level_dbfs}
        notes.append(
            _by_source(
                source,
                pre_sweep=diag(
                    "the pre-sweep segment is only {below:.1f} dB below the level of the sweep "
                    "({sweep:.1f} dBFS RMS): it is not background noise (a sweep pass without "
                    "silence before it?)",
                    **margin,
                ),
                tail=diag(
                    "the tail segment is only {below:.1f} dB below the level of the sweep "
                    "({sweep:.1f} dBFS RMS): it is not background noise (a sweep pass without "
                    "silence before it?)",
                    **margin,
                ),
                other=diag(
                    "the {source} segment is only {below:.1f} dB below the level of the sweep "
                    "({sweep:.1f} dBFS RMS): it is not background noise (a sweep pass without "
                    "silence before it?)",
                    source=source,
                    **margin,
                ),
            )
        )
        return QuietSelection(None, tuple(notes))
    return QuietSelection(
        replace(candidate, start=candidate.start + start, end=candidate.start + stop),
        tuple(notes),
    )


def _is_shared_harmonic(frequency_hz: float) -> bool:
    """True for a frequency that is a multiple of both mains fundamentals."""
    ratio = frequency_hz / MAINS_SHARED_MULTIPLE_HZ
    return abs(ratio - round(ratio)) < 1e-6


def _hum_candidate(
    freqs: FloatArray, psd_db: FloatArray, base_hz: float, nyquist: float
) -> HumCandidate:
    """Harmonics of ``base_hz`` that stand out of the PSD, and whether that is hum.

    Every harmonic that exceeds its neighbourhood by
    :data:`HUM_DETECTION_PROMINENCE_DB` is listed, but only harmonics that are
    not shared with the other mains base (:func:`_is_shared_harmonic`) count
    towards ``detected``; the fundamental is not required.
    """
    resolution = float(freqs[1] - freqs[0]) if freqs.shape[0] > 1 else float("inf")
    harmonics: list[tuple[float, float]] = []
    k = 1
    while k <= HUM_MAX_HARMONICS:
        f_k = k * base_hz
        if f_k > min(HUM_MAX_HARMONIC_HZ, nyquist * 0.9):
            break
        peak_half_width = max(2.0, 1.5 * resolution)
        lo = np.searchsorted(freqs, f_k - peak_half_width)
        hi = np.searchsorted(freqs, f_k + peak_half_width, side="right")
        neighbourhood = max(10.0, 0.15 * f_k)
        n_lo = np.searchsorted(freqs, f_k - neighbourhood)
        n_hi = np.searchsorted(freqs, f_k + neighbourhood, side="right")
        exclude_lo = np.searchsorted(freqs, f_k - peak_half_width - resolution)
        exclude_hi = np.searchsorted(freqs, f_k + peak_half_width + resolution, side="right")
        if hi <= lo or n_hi - n_lo < 6:
            k += 1
            continue
        peak_level = float(np.max(psd_db[lo:hi]))
        surround = np.concatenate([psd_db[n_lo:exclude_lo], psd_db[exclude_hi:n_hi]])
        if surround.shape[0] < 3:
            k += 1
            continue
        prominence = peak_level - float(np.median(surround))
        if prominence >= HUM_DETECTION_PROMINENCE_DB:
            harmonics.append((float(f_k), float(prominence)))
        k += 1
    distinct = tuple(f for f, _ in harmonics if not _is_shared_harmonic(f))
    strongest = max((p for _, p in harmonics), default=None)
    return HumCandidate(
        base_hz=base_hz,
        harmonics=tuple(harmonics),
        strongest_prominence_db=strongest,
        detected=len(distinct) >= HUM_MIN_HARMONICS_FOR_DETECTION,
        distinct_harmonics_hz=distinct,
    )


def _distinct_strength(candidate: HumCandidate) -> tuple[int, float]:
    prominence = dict(candidate.harmonics)
    return (
        len(candidate.distinct_harmonics_hz),
        sum(prominence[f] for f in candidate.distinct_harmonics_hz),
    )


def hum_candidates(
    freqs: FloatArray, psd_db: FloatArray, nyquist: float
) -> tuple[HumCandidate, ...]:
    """Hum candidates for both mains bases, with at most one reported as detected.

    A single mains supply is either 50 Hz or 60 Hz, so when both bases qualify
    only the one explaining more (and stronger) harmonics of its own keeps
    ``detected``; the other one says so in its note.
    """
    candidates = [
        _hum_candidate(freqs, psd_db, base, nyquist) for base in MAINS_BASE_FREQUENCIES_HZ
    ]
    detected = [c for c in candidates if c.detected]
    if len(detected) < 2:
        return tuple(candidates)
    best = max(detected, key=_distinct_strength)
    return tuple(
        c
        if c is best
        else replace(
            c,
            detected=False,
            note=diag(
                "harmonics of {base:.0f} Hz were found as well, but {best:.0f} Hz explains more "
                "of them; a single mains supply has one fundamental",
                base=c.base_hz,
                best=best.base_hz,
            ),
        )
        for c in candidates
    )


def _band_levels(
    x: FloatArray, sample_rate: int, octave_bands_hz: tuple[float, ...]
) -> tuple[list[tuple[float, float | None]], list[str]]:
    """Octave-band levels (dBFS) of ``x``; ``None`` where they cannot be measured."""
    levels: list[tuple[float, float | None]] = []
    too_short: list[str] = []
    for center in octave_bands_hz:
        band = iec_band(center, 1)
        if not band_fits(band, sample_rate):
            continue
        filtered = band_level_samples(x, bandpass_sos(band, sample_rate), sample_rate)
        if filtered is None:
            levels.append((center, None))
            too_short.append(band.label)
            continue
        levels.append((center, _measurable(rms_dbfs(filtered))))
    notes: list[str] = []
    if too_short:
        notes.append(
            diag(
                "the quiet segment is too short for the {bands} band filter(s); no level is "
                "reported for them",
                bands=", ".join(too_short),
            )
        )
    return levels, notes


def _unmeasured(source: str | None, notes: tuple[str, ...]) -> NoiseResult:
    return NoiseResult(
        segment_source=source,
        segment_start_s=None,
        segment_duration_s=None,
        rms_dbfs=None,
        peak_dbfs=None,
        band_levels_dbfs=(),
        psd_frequencies_hz=None,
        psd_db=None,
        hum=(),
        notes=notes,
    )


def analyze_noise(
    recording: FloatArray,
    sample_rate: int,
    segment: QuietSegment | None,
    *,
    octave_bands_hz: tuple[float, ...],
    min_segment_s: float = 0.5,
    sweep_level_dbfs: float | None = None,
    fallbacks: tuple[QuietSegment, ...] = (),
) -> NoiseResult:
    """Background-noise levels of the first candidate segment that is quiet.

    ``segment`` and then ``fallbacks`` are checked with
    :func:`select_quiet_part`; the first usable one is measured. Levels are
    dBFS (AES17), the PSD is referenced so that it integrates to the reported
    RMS level (:data:`~reverbscope.models.result.PSD_REFERENCE`), and octave-band
    levels come from a single filter pass with the start transient discarded.
    """
    notes: list[str] = []
    verified: QuietSegment | None = None
    for candidate in (segment, *fallbacks):
        if candidate is None:
            continue
        selection = select_quiet_part(
            recording,
            sample_rate,
            candidate,
            min_segment_s=min_segment_s,
            sweep_level_dbfs=sweep_level_dbfs,
        )
        notes.extend(selection.notes)
        if selection.segment is not None:
            verified = selection.segment
            break
    if verified is None:
        notes.append(
            diag(
                "No quiet segment found: add at least 1 s of silence before the sweep "
                "(the generated test signal already contains it) or record a longer tail."
            )
        )
        return _unmeasured(None, tuple(notes))

    x = np.asarray(recording[verified.start : verified.end], dtype=np.float64)
    if verified.note:
        notes.append(verified.note)
    level = rms_dbfs(x)
    if level <= NOISE_FLOOR_DBFS:
        notes.append(
            diag(
                "the quiet segment is below {floor:g} dBFS ({level:.0f} dBFS): that is below the "
                "quantisation noise of a 24-bit file, so it is digital silence or numerical "
                "residue, not a measured noise floor",
                floor=NOISE_FLOOR_DBFS,
                level=level,
            )
        )
        return _unmeasured(verified.source, tuple(notes))

    band_levels, band_notes = _band_levels(x, sample_rate, octave_bands_hz)
    notes.extend(band_notes)

    # 2 Hz resolution with several averaged segments (Welch) keeps random
    # spectral peaks small enough for the hum detector. The density is scaled
    # to the AES17 full-scale sine so that its integral is the RMS level.
    nperseg = int(min(x.shape[0], sample_rate // 2))
    freqs, psd = welch(x, fs=sample_rate, window="hann", nperseg=nperseg, scaling="density")
    freqs = np.asarray(freqs, dtype=np.float64)
    psd_db = np.asarray(10.0 * np.log10(np.maximum(2.0 * psd, _EPS)), dtype=np.float64)

    hum: tuple[HumCandidate, ...] = ()
    resolution = sample_rate / nperseg
    if resolution <= 5.0:
        hum = hum_candidates(freqs, psd_db, sample_rate / 2.0)
    else:
        notes.append(
            diag(
                "quiet segment is too short ({duration:.2f} s) for mains-hum detection",
                duration=x.shape[0] / sample_rate,
            )
        )

    return NoiseResult(
        segment_source=verified.source,
        segment_start_s=verified.start / sample_rate,
        segment_duration_s=x.shape[0] / sample_rate,
        rms_dbfs=level,
        # The segment is above the level floor, so its peak is a measurement
        # too (and front ends may print it next to the RMS level).
        peak_dbfs=peak_dbfs(x),
        band_levels_dbfs=tuple(band_levels),
        psd_frequencies_hz=freqs,
        psd_db=psd_db,
        hum=hum,
        notes=tuple(notes),
    )


def sweep_level_dbfs(
    recording: FloatArray, sample_rate: int, start: int, length: int
) -> float | None:
    """RMS level (dBFS) of the recording while the sweep was playing.

    Used to reject a "quiet" segment that is as loud as the sweep itself.
    ``None`` when the sweep region is not inside the recording.
    """
    lo, hi = max(0, start), min(recording.shape[0], start + length)
    if hi - lo < max(1, round(0.1 * sample_rate)):
        return None
    level = rms_dbfs(recording[lo:hi])
    return level if math.isfinite(level) else None
