"""Potential low-frequency resonance detection.

v0.1 deliberately reports *candidates* only:

* a candidate is a peak of the finely smoothed (1/24-octave) magnitude
  response that stands ``min_prominence_db`` above the 1-octave smoothed
  baseline, inside the searched range (below ``max_hz``, above
  :data:`MIN_FREQUENCY_HZ`, inside the excitation band and coarse enough for
  the frequency resolution of the response);
* for each candidate the decay of a 1/3-octave band around it is measured as
  the time for the band envelope to fall 20 dB, and compared with **two**
  references measured exactly the same way: the analysis filter's own ringing
  (a band-pass of a Dirac pulse, filtered time-reversed like the measurement)
  and the *surroundings*, the median of the neighbouring 1/3-octave bands.
  ``decay_distinguishable`` requires both: at least
  :data:`DISTINGUISHABLE_RATIO` times the filter ringing (otherwise the
  measurement only shows the filter) and at least
  :data:`SURROUNDINGS_RATIO` times the neighbouring bands (otherwise the whole
  low end decays like this and the peak is not a separate resonance).

The surroundings are measured *after* notching the candidate's own 1/3 octave
out of the impulse response. A strong, long resonance is 40 dB or more above
the tail of the neighbouring bands at later times, so without the notch it
leaks through the filter skirts and the neighbours simply repeat the
candidate's own decay (measured: every neighbour of a 62 Hz mode with
RT 1.5 s in a room with RT 0.3 s read 0.50 s, the mode's own decay).

Calibration of :data:`SURROUNDINGS_RATIO` (2.0): for mode-free synthetic rooms
(exponential Gaussian tails, RT 0.25-1.0 s, seven frequencies from 63 Hz to
250 Hz, 12 seeds each) the ratio has a median of 1.0 and a 99th percentile of
2.1, with a maximum of 2.9; for added modes whose RT is twice the room's or
more it is 2.0 to 7.9. The measure has a large statistical spread at low
frequencies (B*T of a 1/3-octave band is only a few), so a candidate remains a
candidate: one position cannot establish a room mode.

Identifying an actual room mode requires knowledge of the room geometry and
several measurement positions and is out of scope.
"""

from __future__ import annotations

import numpy as np
from scipy.signal import butter, find_peaks, sosfilt

from roomscope.core.filters import (
    OCTAVE_RATIO,
    apply_bandpass,
    band_fits,
    bandpass_sos,
    fractional_octave_band,
    fractional_octave_smooth,
)
from roomscope.core.impulse import envelope_db
from roomscope.i18n import diag
from roomscope.models.audio import FloatArray
from roomscope.models.result import (
    ExcitationBand,
    FrequencyResponseResult,
    ResonanceCandidate,
    ResonanceResult,
)

MAX_CANDIDATES = 8
MIN_FREQUENCY_HZ = 20.0
#: The narrow-band decay must be at least this many times the analysis
#: filter's own ringing.
DISTINGUISHABLE_RATIO = 2.0
#: ... and at least this many times the decay of the neighbouring bands.
SURROUNDINGS_RATIO = 2.0
#: Neighbouring band centres used as the surroundings reference (octaves).
SURROUNDING_OFFSETS_OCTAVES = (-1.0, -2.0 / 3.0, 2.0 / 3.0, 1.0)
#: At least this many neighbouring bands must be measurable.
MIN_SURROUNDING_BANDS = 2
#: Length of the impulse response used for the decay measurements (s).
DECAY_ANALYSIS_S = 3.0
#: Poles per skirt of the notch that removes the candidate's own band before
#: the surroundings are measured.
NOTCH_ORDER = 3
_FINE_FRACTION = 24
_BASELINE_FRACTION = 1
#: Relative width of the 1/24-octave smoothing window; a peak narrower than
#: the frequency resolution of the response cannot be seen.
_FINE_RELATIVE_WIDTH = 2.0 ** (1.0 / (2.0 * _FINE_FRACTION)) - 2.0 ** (
    -1.0 / (2.0 * _FINE_FRACTION)
)


def _decay_20db_s(signal: FloatArray, sample_rate: int, smoothing_s: float) -> float | None:
    env = envelope_db(signal, sample_rate, smoothing_s * 1000.0)
    peak = int(np.argmax(env))
    below = np.nonzero(env[peak:] <= env[peak] - 20.0)[0]
    if below.shape[0] == 0:
        return None
    return float(below[0]) / sample_rate


def band_decay_20db_s(ir: FloatArray, sample_rate: int, center_hz: float) -> float | None:
    """20 dB decay of ``ir`` in the 1/3-octave band around ``center_hz`` (s).

    The band is filtered time-reversed (as everywhere in RoomScope, so that
    the filter's own decay does not lengthen the measured one) and the decay
    is read from the Hilbert envelope smoothed over two periods.
    """
    band = fractional_octave_band(center_hz, 3)
    if not band_fits(band, sample_rate):
        return None
    sos = bandpass_sos(band, sample_rate, order=2)
    return _decay_20db_s(apply_bandpass(ir, sos, time_reversed=True), sample_rate, 2.0 / center_hz)


def filter_ringing_20db_s(sample_rate: int, center_hz: float) -> float | None:
    """The 1/3-octave analysis filter's own 20 dB ringing at ``center_hz`` (s).

    Measured on a Dirac pulse with the *same* time-reversed filtering and the
    same envelope smoothing as :func:`band_decay_20db_s`; forward filtering
    gives a ringing about 1.7 times longer and would not be comparable.
    """
    n = max(int(2.0 * sample_rate), 16)
    impulse = np.zeros(2 * n, dtype=np.float64)
    impulse[n] = 1.0
    return band_decay_20db_s(impulse, sample_rate, center_hz)


def notch_band(ir: FloatArray, sample_rate: int, center_hz: float) -> FloatArray:
    """``ir`` with the 1/3-octave band around ``center_hz`` filtered out.

    Applied time-reversed like the band-pass filters. Without it, the ringing
    of a strong resonance leaks through the skirts of the neighbouring band
    filters and the surroundings reference repeats the candidate's own decay.
    """
    band = fractional_octave_band(center_hz, 3)
    nyquist = sample_rate / 2.0
    if not band_fits(band, sample_rate):
        return np.asarray(ir, dtype=np.float64)
    sos = butter(
        NOTCH_ORDER,
        [band.low_hz / nyquist, band.high_hz / nyquist],
        btype="bandstop",
        output="sos",
    )
    return np.asarray(sosfilt(sos, ir[::-1])[::-1], dtype=np.float64)


def _surroundings_decay_20db_s(
    ir: FloatArray,
    sample_rate: int,
    center_hz: float,
    *,
    excitation_band: ExcitationBand | None,
) -> float | None:
    """Median 20 dB decay of the neighbouring 1/3-octave bands (s)."""
    without_candidate = notch_band(ir, sample_rate, center_hz)
    decays: list[float] = []
    for offset in SURROUNDING_OFFSETS_OCTAVES:
        neighbour = center_hz * OCTAVE_RATIO**offset
        band = fractional_octave_band(neighbour, 3)
        if excitation_band is not None and not excitation_band.contains(band.low_hz, band.high_hz):
            continue
        decay = band_decay_20db_s(without_candidate, sample_rate, neighbour)
        if decay is not None and decay > 0.0:
            decays.append(decay)
    if len(decays) < MIN_SURROUNDING_BANDS:
        return None
    return float(np.median(decays))


def _search_range(
    response: FrequencyResponseResult,
    *,
    max_hz: float,
    excitation_band: ExcitationBand | None,
) -> tuple[float, float, list[str]]:
    """``(low, high, notes)`` of the range that may be searched.

    A candidate needs a 1/3-octave band inside the excitation band, and a peak
    narrower than the response's true resolution cannot be seen.
    """
    notes: list[str] = []
    low, high = MIN_FREQUENCY_HZ, max_hz
    edge = OCTAVE_RATIO ** (1.0 / 6.0)
    if excitation_band is not None:
        band_low, band_high = excitation_band.low_hz * edge, excitation_band.high_hz / edge
        if band_low > low or band_high < high:
            low, high = max(low, band_low), min(high, band_high)
            # A band that misses the range leaves nothing to limit it to
            # (not "495-300 Hz"); the "no search was made" note says so.
            if low < high:
                notes.append(
                    diag(
                        "the search is limited to {low:.0f}-{high:.0f} Hz, the part of the "
                        "range whose 1/3-octave band lies inside the excited {band_low:.0f}-"
                        "{band_high:.0f} Hz",
                        low=low,
                        high=high,
                        band_low=excitation_band.low_hz,
                        band_high=excitation_band.high_hz,
                    )
                )
    resolvable = response.resolution_hz / _FINE_RELATIVE_WIDTH
    if resolvable > low:
        low = resolvable
        notes.append(
            diag(
                "the analysed response is {length_s:.2f} s long, so its resolution is "
                "{resolution_hz:.1f} Hz and peaks below {low:.0f} Hz cannot be separated",
                length_s=1.0 / response.resolution_hz,
                resolution_hz=response.resolution_hz,
                low=low,
            )
        )
    return low, high, notes


def detect_potential_resonances(
    ir: FloatArray,
    sample_rate: int,
    response: FrequencyResponseResult,
    *,
    max_hz: float,
    min_prominence_db: float,
    direct_index: int = 0,
    excitation_band: ExcitationBand | None = None,
) -> ResonanceResult:
    """Peaks in the low-frequency response whose narrow-band decay stands out.

    ``ir`` should start before the direct sound (``direct_index``) so that the
    time-reversed band filters keep the whole band response of the direct
    sound; ``response`` should be ungated, because a gate shorter than the
    decay hides exactly the resonances that are searched for.
    """
    freqs = response.frequencies_hz
    raw = response.magnitude_db_raw
    notes = [
        diag(
            "Candidates only: a peak in the low-frequency response with a long narrow-band "
            "decay may be a room resonance, but room-mode identification is not attempted in "
            "v0.1."
        ),
    ]
    low_hz, high_hz, range_notes = _search_range(
        response, max_hz=max_hz, excitation_band=excitation_band
    )
    notes.extend(range_notes)

    def nothing_found(*, searched: bool = True) -> ResonanceResult:
        return ResonanceResult(
            max_frequency_hz=max_hz,
            candidates=(),
            notes=tuple(notes),
            # No range at all when no search was made: an empty or inverted
            # one would read as a low end that was searched and is clean.
            searched_range_hz=(low_hz, high_hz) if searched else None,
        )

    if high_hz <= low_hz:
        notes.append(
            diag("no part of the resonance range was excited and resolved; no search was made")
        )
        return nothing_found(searched=False)
    # The baseline and the fine curve are smoothed over the excited part only,
    # so that the roll-off outside it cannot create a peak at the band edge.
    mask = (freqs >= low_hz / OCTAVE_RATIO) & (freqs <= high_hz * OCTAVE_RATIO)
    if excitation_band is not None:
        mask &= (freqs >= excitation_band.low_hz) & (freqs <= excitation_band.high_hz)
    if int(np.count_nonzero(mask)) < 8:
        notes.append(diag("frequency resolution is too coarse for the resonance search"))
        return nothing_found(searched=False)

    f = freqs[mask]
    fine = fractional_octave_smooth(f, raw[mask], _FINE_FRACTION)
    baseline = fractional_octave_smooth(f, raw[mask], _BASELINE_FRACTION)
    excess = fine - baseline
    searched = (f >= low_hz) & (f <= high_hz)
    peaks, props = find_peaks(excess, height=min_prominence_db, prominence=min_prominence_db / 2.0)
    keep = searched[peaks]
    peaks, heights = peaks[keep], np.asarray(props["peak_heights"])[keep]
    if peaks.shape[0] == 0:
        return nothing_found()
    order = np.argsort(heights)[::-1][:MAX_CANDIDATES]

    stop = min(ir.shape[0], direct_index + round(DECAY_ANALYSIS_S * sample_rate))
    analysed = np.asarray(ir[:stop], dtype=np.float64)
    candidates: list[ResonanceCandidate] = []
    for idx in sorted(peaks[order]):
        f0 = float(f[idx])
        decay = band_decay_20db_s(analysed, sample_rate, f0)
        ringing = filter_ringing_20db_s(sample_rate, f0)
        surroundings = _surroundings_decay_20db_s(
            analysed, sample_rate, f0, excitation_band=excitation_band
        )
        distinguishable = (
            decay is not None
            and ringing is not None
            and ringing > 0.0
            and decay / ringing >= DISTINGUISHABLE_RATIO
            and surroundings is not None
            and surroundings > 0.0
            and decay / surroundings >= SURROUNDINGS_RATIO
        )
        candidates.append(
            ResonanceCandidate(
                frequency_hz=f0,
                level_above_baseline_db=float(excess[idx]),
                narrowband_decay_20db_s=decay,
                filter_ringing_20db_s=ringing,
                surroundings_decay_20db_s=surroundings,
                decay_distinguishable=distinguishable,
            )
        )
    if any(c.surroundings_decay_20db_s is None for c in candidates):
        notes.append(
            diag(
                "some candidates have too few measurable neighbouring bands for the "
                "surroundings comparison; their decay is not called distinguishable"
            )
        )
    return ResonanceResult(
        max_frequency_hz=max_hz,
        candidates=tuple(candidates),
        notes=tuple(notes),
        searched_range_hz=(low_hz, high_hz),
    )
