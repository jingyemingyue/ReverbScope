"""Reverberation analysis: decay onset, Schroeder integration, noise truncation,
EDT/T20/T30 and their validity.

Method (see docs/MEASUREMENT_METHODOLOGY.md for the references)
------------------------------------------------------------------
1. **Analysis segment and band filtering.** The caller passes a signal that
   contains the impulse response and the index of the (broadband) direct
   sound. Octave bands are IEC 61260-1 base-10 bands (``filters.iec_band``)
   filtered with time-reversed Butterworth band-passes (Jacobsen & Rindel
   1987). A time-reversed filter is anti-causal: the band signal at any time
   depends only on the input from that time on, and the filter's ringing
   appears *before* each input event (about ``4/B`` at -40 dB for bandwidth
   ``B``). The signal is therefore given a lead-in of :func:`decay_lead_in_s`
   (at least ``DECAY_LEAD_IN_MIN_S`` = 0.2 s and ``DECAY_LEAD_IN_BANDWIDTHS/B``
   of the lowest band) before the direct sound, zero-padded where the signal
   has less. The result does not depend on how much signal before the direct
   sound the caller kept (for example the display pre-delay
   ``ir_pre_delay_ms``).
2. **Onset** (start of the Schroeder integration), found separately for the
   broadband response and for each band: the first sample at which the
   squared response rises to within ``ONSET_LEVEL_DB`` (20 dB) of its
   maximum, before the direct sound. This follows the start-point rule of
   ISO 3382-1:2009, Annex A (clause not verified against the standard text;
   wording as restated by Christensen, Koutsouris & Rindel, ISRA 2013). When
   the direct sound is known, the search starts ``2 ms + 4/B`` before it
   (``B`` = the band's bandwidth, or the excitation bandwidth for the
   broadband response), so that noise, other sweep passes or harmonic
   pre-responses further ahead cannot start the decay. Without a known
   direct sound the search starts at the beginning of the signal. The EDC is
   normalised at the onset, so a band's 0 dB includes all of its
   direct-sound energy.
3. **Noise truncation** (Lundeby et al. 1995, steps as summarised by
   Karjalainen et al. 2002) on the squared response from the onset. Trailing
   digital silence (exact zeros, e.g. an imported response padded with zeros)
   is removed first: it is not a noise floor, and "the last 10 %" below is the
   last 10 % before it. 20 ms block averages, preliminary regression from the
   loudest block to the first block at noise + 10 dB (noise from the last
   10 %), then iterated block length / noise / late-slope estimates until the
   crosspoint moves by less than ``LUNDEBY_CONVERGENCE_DB`` (1 dB) of decay at
   the late slope (at least 1 ms). The iterative estimate is rejected, and the
   preliminary crosspoint, slope and noise level are used instead, when the
   iteration does not converge within 6 passes, when the late slope is less
   than ``LUNDEBY_MIN_SLOPE_RATIO`` (0.5) times the
   preliminary slope, or when the crosspoint lies more than
   ``10 dB / |preliminary slope|`` plus two blocks after the first block at
   noise + 5 dB (a stationary tonal floor such as mains hum drags the late
   slope towards zero and the crosspoint to the end of the response). The
   metrics are then also computed with the rejected estimate; if any VALID
   metric changes by more than ``TRUNCATION_SENSITIVITY`` (5 %) or loses or
   gains its number, the band's metrics are marked unreliable. (Marking every
   rejected estimate unreliable would flag most bands of clean measurements
   with more than about 100 dB of range, where the late slope is fitted to a
   few blocks and oscillates without affecting the metrics.) The energy of
   the decay after the truncation point is estimated from the slope and added
   back (late-decay compensation).
4. **Schroeder curve** ``EDC(t) = sum_{tau >= t} h^2(tau)`` from the onset to
   the truncation point (Schroeder 1965), normalised to 0 dB at the onset.
   All times (curve, onset, truncation) are measured from the direct sound
   (from the start of the signal when no direct sound is given; see
   ``DecayResult.time_origin``). Without a direct sound, the energy
   parameters of item 7 are the exception.
5. **Fits.** EDT, T20 and T30 are least-squares line fits over 0..-10 dB,
   -5..-25 dB and -5..-35 dB, extrapolated to 60 dB (ISO 3382-1). A fit
   never starts before the end of the direct sound (the direct sound plus
   the excitation pulse spread ``4/B_exc + 0.5 ms``): before it, a
   time-reversed band response contains only the band filter's pre-ringing
   of the direct sound, not room decay. This reproduces what an ideal,
   non-smearing band filter would give, where the direct sound is a step of
   the EDC at time 0; for the broadband curve it changes nothing. The degree
   of non-linearity ``xi = 1000 * (1 - r^2)`` and the curvature
   ``C = 100 * (T30 / T20 - 1)`` are defined in ISO 3382-2:2008, Annex B.
6. **Validity** (a metric is only VALID when none of these applies):

   * *insufficient decay range*: the range from the loudest block to the
     noise floor is less than ``|lower limit| + noise_margin_db`` (ISO 3382:
     the evaluation range must end at least 10 dB above the noise);
   * fewer than 3 samples in the range, or a non-negative slope;
   * EDT only: the EDC drops by more than ``EDT_MAX_DIRECT_STEP_DB`` (5 dB)
     across the direct sound, i.e. the direct sound carries more than about
     70 % of the (band) energy. Less than half of the 0..-10 dB range is then
     room decay and EDT describes the direct sound rather than the room (with
     a step of 10 dB or more there is no room decay in the range at all);
   * B*T < ``MIN_BT_PRODUCT`` (4) for time-reversed filtering (Jacobsen &
     Rindel 1987; value confirmed only through citing works);
   * the metrics depend on a rejected Lundeby estimate (item 3);
   * *non-straight decay*: ISO 3382-2 Annex B introduces the curvature C and
     the non-linearity xi to warn when a decay is not straight and a single
     reverberation time does not describe it (for example a double slope);
     such results should be marked as less reliable. When ``|C|`` exceeds its
     limit (10 % for wide bands, growing as ``1/sqrt(B * T30)`` for narrow
     bands and short decays, see :func:`straightness_limits`), T20 and T30
     are both marked unreliable and no RT60 is estimated; when the xi of one
     fit exceeds its limit (15 permille, growing the same way), that metric
     is marked unreliable. A band warning says why. The numerical guidance of
     Annex B was not verified; the limits are RoomScope's choice, calibrated
     as documented next to the constants;
   * the band is not fully inside the excitation range
     (``Validity.OUTSIDE_EXCITATION``, no numbers at all);
   * the caller marks everything unreliable
     (:meth:`~roomscope.models.result.DecayResult.with_all_unreliable`), e.g.
     for a low direct-sound confidence or a clipped recording.

7. **Early/late energy** (ISO 3382-1 clarity, definition and centre time; the
   clause numbers were not read from the standard text). From the same onset,
   truncation and late-decay compensation as the Schroeder curve:
   ``C50`` and ``C80`` are ``10 log10(E_early / E_late)`` at 50 ms and 80 ms
   after the direct sound, ``D50`` is ``100 * E_early / (E_early + E_late)``
   at 50 ms (percent), and centre time ``Ts`` is the energy-weighted mean
   time. Energy before the direct-sound sample is counted at time zero (it is
   the rise, or a band filter's pre-ringing of the direct sound). Without a
   known direct sound they are timed from each curve's onset (item 2), not
   from ``DecayResult.time_origin``, so leading silence does not move them;
   ``Ts`` is then not on the result's time axis. A parameter
   is reported only when the decay range is at least
   ``ENERGY_MIN_DECAY_RANGE_DB`` (20 dB, the same floor as EDT) and the
   truncation point is after the early window. Sound strength ``G`` is not
   computed: it needs a calibrated source. These are ratios, not a room score,
   and ``average_decay`` does not average them.

   The estimated RT60 is the VALID T30, else the VALID T20, else none.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from roomscope.core.filters import (
    Band,
    apply_bandpass,
    band_fits,
    bandpass_sos,
    iec_band,
)
from roomscope.i18n import diag
from roomscope.models.audio import FloatArray
from roomscope.models.configuration import AnalysisSettings
from roomscope.models.result import (
    DECAY_TIME_ORIGIN,
    EXCITATION_SOURCE_DECLARED,
    EXCITATION_SOURCE_ESTIMATED,
    EXCITATION_SOURCE_SETTINGS,
    EXCITATION_SOURCE_UNKNOWN,
    BandDecay,
    DecayMetric,
    DecayResult,
    EnergyMetric,
    ExcitationBand,
    Validity,
)

#: ``DecayResult.time_origin`` when no direct sound was given. C50, C80, D50
#: and ``Ts`` are then timed from each curve's onset instead.
TIME_ORIGIN_SIGNAL_START = "start of the analysed signal (no direct sound given)"
_EPS = 1e-300
_EDT_RANGE = (0.0, -10.0)
_T20_RANGE = (-5.0, -25.0)
_T30_RANGE = (-5.0, -35.0)
#: Minimum bandwidth-time product for time-reversed filtering (Jacobsen & Rindel 1987).
MIN_BT_PRODUCT = 4.0
#: The decay starts where the squared response first rises to within this
#: many dB of its maximum (ISO 3382-1 start-point rule, clause not verified).
ONSET_LEVEL_DB = 20.0
#: The onset search starts this long ...
ONSET_SEARCH_MARGIN_S = 0.002
#: ... plus this many inverse bandwidths before the direct sound.
ONSET_SEARCH_BANDWIDTHS = 4.0
#: The direct sound lasts this long plus ``ONSET_SEARCH_BANDWIDTHS`` inverse
#: excitation bandwidths after its peak (band-limited pulse spread).
DIRECT_SOUND_MARGIN_S = 0.0005
#: Lead-in before the direct sound for band filtering: at least this long ...
DECAY_LEAD_IN_MIN_S = 0.2
#: ... and at least this many inverse bandwidths of the lowest band.
DECAY_LEAD_IN_BANDWIDTHS = 5.0
#: EDT is unreliable when the EDC drops by more than this (dB) across the
#: direct sound (less than half of the EDT range is then room decay).
EDT_MAX_DIRECT_STEP_DB = 5.0
#: Lundeby iteration: converged when the crosspoint moves by less than this
#: much decay (dB at the late slope), or by less than 1 ms.
LUNDEBY_CONVERGENCE_DB = 1.0
LUNDEBY_MAX_ITERATIONS = 6
#: Lundeby estimate rejected when |late slope| < this ratio * |preliminary slope| ...
LUNDEBY_MIN_SLOPE_RATIO = 0.5
#: ... or when the crosspoint lies more than this decay (dB, at the
#: preliminary slope) plus two blocks after the first block at noise + 5 dB.
LUNDEBY_CROSSPOINT_ALLOWANCE_DB = 10.0
_NOISE_REACHED_DB = 5.0
#: With a rejected Lundeby estimate, metrics that change by more than this
#: fraction between the preliminary and the rejected truncation are unreliable.
TRUNCATION_SENSITIVITY = 0.05
#: Early/late ratios need the tail, so they are withheld below the same decay
#: range EDT already requires. Not Hak et al.'s per-parameter INR table [17],
#: which was not re-read; 20 dB is the floor already used for EDT.
ENERGY_MIN_DECAY_RANGE_DB = 20.0
C50_SPLIT_S = 0.050
C80_SPLIT_S = 0.080
#: Truncation-sensitivity gates, not a claim that a change is audible. The
#: numbers are the just-noticeable differences commonly quoted for C80 (1 dB),
#: D50 (5 percentage points) and centre time (10 ms). The clauses were not
#: read from ISO 3382-1; a single pair of sessions is never called significant.
ENERGY_C_SENSITIVITY_DB = 1.0
ENERGY_D50_SENSITIVITY_PERCENT = 5.0
ENERGY_TS_SENSITIVITY_S = 0.010
#: Non-straight decay (ISO 3382-2:2008 Annex B measures). T20 and T30 are
#: both marked unreliable when |C| exceeds
#: ``max(MAX_CURVATURE_PERCENT, CURVATURE_SPREAD_PERCENT / sqrt(B * T30))``;
#: a single metric is marked unreliable when its own xi exceeds
#: ``max(MAX_NONLINEARITY_PERMILLE, NONLINEARITY_SPREAD_PERMILLE / sqrt(B * T30))``.
#:
#: Calibration (RoomScope's choice; the numerical guidance of Annex B was not
#: verified against the standard text):
#:
#: * the 10 % floor for C is the value the Annex is commonly cited with. In
#:   simulations of single-slope rooms with strong early reflections, curves
#:   with |C| > 10 % had a median T30 error of -10 % or worse;
#: * the xi floor is 15 permille rather than the commonly cited 10: in the
#:   same simulations the median T30 error stayed below 10 % up to about
#:   15 permille and exceeded it above (T20: above about 20 permille);
#: * the 1/sqrt(B*T) terms follow the statistics of band-limited noise
#:   decays, whose relative scatter falls with the number of degrees of
#:   freedom B*T. The constants were set with a Monte Carlo of single-slope
#:   decays (Gaussian noise with exponential envelopes, RT 0.15-2.5 s,
#:   direct-to-reverberant ratios from none to +21 dB, noise 60 and 85 dB
#:   below the start, default octave bands, 48 and 96 kHz, plus full
#:   sweep/deconvolution runs): below 1 % of the single-slope results are
#:   flagged overall (at most about 2 % in any band), while a double slope of
#:   0.3 s and 2.0 s with the slow part 25 dB down is flagged in every run for
#:   the broadband curve and the 250 Hz-8 kHz bands, but only in 60-90 % of
#:   the runs at 63 and 125 Hz, where a single decay already scatters that
#:   much (B*T of about 20). Low-band values need that caution anyway.
MAX_CURVATURE_PERCENT = 10.0
MAX_NONLINEARITY_PERMILLE = 15.0
CURVATURE_SPREAD_PERCENT = 500.0
NONLINEARITY_SPREAD_PERMILLE = 1000.0

DECAY_METHOD = (
    "ISO 3382-1 onset (-20 dB) per band; Schroeder backward integration with Lundeby "
    "noise truncation (plausibility-checked) and late-decay compensation; EDT/T20/T30 by "
    "least-squares fit per ISO 3382-1, fits starting after the direct sound; straightness "
    "check with xi and C (ISO 3382-2 Annex B); C50, C80, D50 and centre time from the "
    "same truncated energy; time-reversed Butterworth IEC 61260-1 base-10 octave-band "
    "filtering"
)


def _to_db(power: FloatArray) -> FloatArray:
    return np.asarray(10.0 * np.log10(np.maximum(power, _EPS)), dtype=np.float64)


def _local_average(power: FloatArray, block: int) -> tuple[FloatArray, FloatArray]:
    """Average ``power`` in consecutive blocks; return (block_centre_index, mean)."""
    block = max(1, block)
    n_blocks = power.shape[0] // block
    if n_blocks == 0:
        return np.array([power.shape[0] / 2.0]), np.array([float(np.mean(power))])
    trimmed = power[: n_blocks * block].reshape(n_blocks, block)
    means = trimmed.mean(axis=1)
    centres = (np.arange(n_blocks) + 0.5) * block
    return centres, means


def _linear_fit(x: FloatArray, y: FloatArray) -> tuple[float, float, float]:
    """Least-squares line ``y = slope * x + intercept``; returns (slope, intercept, r2)."""
    if x.shape[0] < 2:
        return float("nan"), float("nan"), float("nan")
    slope, intercept = np.polyfit(x, y, 1)
    predicted = slope * x + intercept
    ss_res = float(np.sum((y - predicted) ** 2))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0.0 else 1.0
    return float(slope), float(intercept), float(r2)


def _level_db(power: FloatArray) -> float:
    return float(_to_db(np.array([np.mean(power)]))[0])


@dataclass(frozen=True)
class TruncationEstimate:
    """Result of the Lundeby noise-floor / crosspoint iteration.

    Indices refer to the power array passed to :func:`estimate_truncation`.
    When the iterative estimate was rejected (``problem`` is set),
    ``truncation_index``, ``late_slope_db_per_s`` and ``noise_floor_db`` hold
    the preliminary values and the ``iterative_*`` fields the rejected ones.
    """

    #: Start of the loudest 20 ms block (the preliminary regression starts there).
    start_index: int
    truncation_index: int
    noise_floor_db: float
    peak_db: float
    late_slope_db_per_s: float | None
    converged: bool
    iterations: int
    #: Why the iterative estimate was rejected, or why there is none.
    problem: str | None = None
    iterative_truncation_index: int | None = None
    iterative_slope_db_per_s: float | None = None
    iterative_noise_floor_db: float | None = None

    def rejected_estimate(self) -> TruncationEstimate | None:
        """The rejected iterative estimate, if there is one."""
        if (
            self.problem is None
            or self.iterative_truncation_index is None
            or self.iterative_noise_floor_db is None
        ):
            return None
        return TruncationEstimate(
            start_index=self.start_index,
            truncation_index=self.iterative_truncation_index,
            noise_floor_db=self.iterative_noise_floor_db,
            peak_db=self.peak_db,
            late_slope_db_per_s=self.iterative_slope_db_per_s,
            converged=self.converged,
            iterations=self.iterations,
        )


def estimate_truncation(
    power: FloatArray,
    sample_rate: int,
    *,
    max_iterations: int = LUNDEBY_MAX_ITERATIONS,
    intervals_per_10db: float = 5.0,
) -> TruncationEstimate:
    """Lundeby et al. (1995) iterative estimate of the noise floor and the
    point where the decay meets it, with plausibility checks.

    ``power`` is the squared response starting at the decay onset. Levels are
    in dB relative to 1 (same scale for peak and noise so that their
    difference is the usable dynamic range). See the module docstring for the
    conditions under which the preliminary estimate replaces the iterative one.
    """
    # Digital silence after the response (an imported IR padded or gated with
    # zeros) is not a noise floor: read as one it is -3000 dB, the iteration
    # never converges and the real floor before it is integrated as decay.
    nonzero = np.flatnonzero(power > 0.0)
    if nonzero.shape[0] > 0:
        power = power[: int(nonzero[-1]) + 1]
    n = power.shape[0]
    if n < 16:
        return TruncationEstimate(
            0,
            n,
            _level_db(power),
            float(_to_db(np.array([np.max(power)]))[0]),
            None,
            False,
            0,
            problem=diag("the response is too short for a noise-floor estimate"),
        )

    # 1. First local averages (about 20 ms blocks).
    block = max(1, round(0.02 * sample_rate))
    centres, means = _local_average(power, block)
    level_db = _to_db(means)
    start_block = int(np.argmax(level_db))
    peak_db = float(level_db[start_block])
    start_index = int(min(n - 1, max(0, centres[start_block] - block / 2.0)))
    start_t = start_index / sample_rate

    # 2. Noise from the last 10 %.
    noise_db = _level_db(power[int(0.9 * n) :])

    # 3. Preliminary slope from the peak down to noise + 10 dB: the blocks
    #    before the first one at or below that level (a fluctuating floor may
    #    rise above it again later; that is not part of the decay).
    reached = np.flatnonzero(level_db[start_block:] <= noise_db + 10.0)
    usable = np.arange(reached[0] if reached.shape[0] else level_db.shape[0] - start_block)
    if usable.shape[0] < 2:
        return TruncationEstimate(
            start_index,
            n,
            noise_db,
            peak_db,
            None,
            False,
            0,
            problem=diag("no decay above the noise floor was found"),
        )
    stop_block = start_block + int(usable[-1]) + 1
    t = centres[start_block:stop_block] / sample_rate
    slope, intercept, _ = _linear_fit(t, level_db[start_block:stop_block])
    if not np.isfinite(slope) or slope >= 0.0:
        return TruncationEstimate(
            start_index,
            n,
            noise_db,
            peak_db,
            None,
            False,
            0,
            problem=diag("the response does not decay"),
        )
    cross_t = (noise_db - intercept) / slope
    preliminary = (cross_t, slope, noise_db)

    converged = False
    iterations = 0
    late_slope = slope
    times = centres / sample_rate
    while iterations < max_iterations:
        iterations += 1
        # 5./6. New block length: `intervals_per_10db` intervals per 10 dB of decay.
        seconds_per_10db = 10.0 / abs(late_slope)
        block = round(seconds_per_10db / intervals_per_10db * sample_rate)
        block = int(np.clip(block, max(1, int(0.001 * sample_rate)), int(0.05 * sample_rate)))
        centres, means = _local_average(power, block)
        level_db = _to_db(means)
        times = centres / sample_rate

        # 7. Noise from a segment starting 5-10 dB (here 7.5 dB) of decay after
        #    the crosspoint, at least the last 10 % of the response.
        noise_start_t = cross_t + 7.5 / abs(late_slope)
        noise_start = int(noise_start_t * sample_rate)
        noise_start = min(noise_start, int(0.9 * n))
        noise_start = max(noise_start, 0)
        noise_db = _level_db(power[noise_start:])

        # 8. Late slope over 10-20 dB starting 5-10 dB above the noise.
        lower = noise_db + 7.5
        upper = lower + 15.0
        mask = (level_db <= upper) & (level_db >= lower) & (times >= start_t)
        if int(np.count_nonzero(mask)) < 3:
            break
        new_slope, new_intercept, _ = _linear_fit(times[mask], level_db[mask])
        if not np.isfinite(new_slope) or new_slope >= 0.0:
            break
        new_cross_t = (noise_db - new_intercept) / new_slope
        late_slope = new_slope
        tolerance = max(0.001, LUNDEBY_CONVERGENCE_DB / abs(new_slope))
        moved = abs(new_cross_t - cross_t)
        cross_t = new_cross_t
        if moved < tolerance:
            converged = True
            break

    problem: str | None = None
    if not converged:
        problem = diag(
            "the Lundeby noise-floor iteration did not converge in {iterations} iteration(s)",
            iterations=iterations,
        )
    elif abs(late_slope) < LUNDEBY_MIN_SLOPE_RATIO * abs(preliminary[1]):
        problem = diag(
            "the late decay slope ({late:.1f} dB/s) is less than {ratio:g} times the early "
            "slope ({early:.1f} dB/s)",
            late=late_slope,
            ratio=LUNDEBY_MIN_SLOPE_RATIO,
            early=preliminary[1],
        )
    else:
        reached = np.nonzero((level_db <= noise_db + _NOISE_REACHED_DB) & (times >= start_t))[0]
        if reached.shape[0] > 0:
            first_reached_t = float(times[reached[0]])
            allowance = LUNDEBY_CROSSPOINT_ALLOWANCE_DB / abs(preliminary[1])
            allowance += 2.0 * block / sample_rate
            if cross_t > first_reached_t + allowance:
                problem = diag(
                    "the noise crosspoint ({crosspoint:.2f} s after the onset) lies far beyond "
                    "the first point where the decay reaches the noise floor ({reached:.2f} s)",
                    crosspoint=cross_t,
                    reached=first_reached_t,
                )

    def index_of(t_s: float) -> int:
        return int(np.clip(round(t_s * sample_rate), start_index + 1, n))

    if problem is None:
        return TruncationEstimate(
            start_index=start_index,
            truncation_index=index_of(cross_t),
            noise_floor_db=noise_db,
            peak_db=peak_db,
            late_slope_db_per_s=late_slope,
            converged=converged,
            iterations=iterations,
        )
    return TruncationEstimate(
        start_index=start_index,
        truncation_index=index_of(preliminary[0]),
        noise_floor_db=preliminary[2],
        peak_db=peak_db,
        late_slope_db_per_s=preliminary[1],
        converged=converged,
        iterations=iterations,
        problem=problem,
        iterative_truncation_index=index_of(cross_t),
        iterative_slope_db_per_s=late_slope,
        iterative_noise_floor_db=noise_db,
    )


def find_onset(
    power: FloatArray, *, search_start: int = 0, level_db: float = ONSET_LEVEL_DB
) -> int:
    """First index ``>= search_start`` where ``power`` rises to within
    ``level_db`` of its maximum (the maximum is taken from ``search_start`` on)."""
    search_start = int(np.clip(search_start, 0, max(0, power.shape[0] - 1)))
    tail = power[search_start:]
    if tail.shape[0] == 0:
        return search_start
    peak = float(np.max(tail))
    if peak <= 0.0:
        return search_start
    above = np.flatnonzero(tail >= peak * 10.0 ** (-level_db / 10.0))
    return search_start + int(above[0])


def pulse_spread_s(bandwidth_hz: float | None) -> float:
    """Time a band-limited pulse of ``bandwidth_hz`` spreads on each side of its
    peak at a significant level (``ONSET_SEARCH_BANDWIDTHS / B``; 0 if unknown)."""
    if bandwidth_hz is None or bandwidth_hz <= 0.0:
        return 0.0
    return ONSET_SEARCH_BANDWIDTHS / bandwidth_hz


def onset_search_window_s(bandwidth_hz: float | None) -> float:
    """How far before the direct sound the onset search starts (s)."""
    return ONSET_SEARCH_MARGIN_S + pulse_spread_s(bandwidth_hz)


def decay_lead_in_s(settings: AnalysisSettings) -> float:
    """Signal needed before the direct sound for the band analysis (s)."""
    narrowest = min(iec_band(center, 1).bandwidth_hz for center in settings.octave_bands_hz)
    return max(DECAY_LEAD_IN_MIN_S, DECAY_LEAD_IN_BANDWIDTHS / narrowest)


@dataclass(frozen=True)
class SchroederCurve:
    #: Time of each EDC sample (s from the time origin).
    time_s: FloatArray
    edc_db: FloatArray
    #: Lundeby estimate; its indices are relative to :attr:`onset_index`.
    truncation: TruncationEstimate
    compensation_energy: float
    #: Onset (integration start) and time origin, as indices of the input signal.
    onset_index: int = 0
    time_origin_index: int = 0

    @property
    def truncation_index(self) -> int:
        """Truncation point as an index of the input signal."""
        return self.onset_index + self.truncation.truncation_index


def _curve_from_truncation(
    power: FloatArray,
    sample_rate: int,
    onset: int,
    trunc: TruncationEstimate,
    *,
    compensate: bool,
    time_origin_index: int,
) -> SchroederCurve:
    segment = power[onset : onset + trunc.truncation_index]
    if segment.shape[0] == 0:
        segment = power[onset : onset + 1]
    compensation = 0.0
    if (
        compensate
        and trunc.late_slope_db_per_s is not None
        and onset + trunc.truncation_index < power.shape[0]
    ):
        # Energy of the extrapolated exponential decay after the truncation:
        # p(t) = p_c * 10^(slope * (t - t_c) / 10)  ->  integral = p_c * (-10 / (slope * ln 10)).
        slope = trunc.late_slope_db_per_s
        p_c = 10.0 ** (trunc.noise_floor_db / 10.0)
        compensation = p_c * (-10.0 / (slope * np.log(10.0))) * sample_rate
    edc = np.cumsum(segment[::-1])[::-1] + compensation
    edc_db = _to_db(edc / max(float(edc[0]), _EPS))
    time_s = (
        np.arange(segment.shape[0], dtype=np.float64) + onset - time_origin_index
    ) / sample_rate
    return SchroederCurve(
        time_s=time_s,
        edc_db=edc_db,
        truncation=trunc,
        compensation_energy=compensation,
        onset_index=onset,
        time_origin_index=time_origin_index,
    )


def schroeder_curve(
    band_ir: FloatArray,
    sample_rate: int,
    *,
    compensate: bool = True,
    onset_index: int | None = None,
    time_origin_index: int = 0,
) -> SchroederCurve:
    """Energy decay curve (dB, 0 dB at the onset) with noise truncation.

    ``onset_index`` defaults to :func:`find_onset` over the whole signal;
    ``time_s`` is measured from ``time_origin_index``.
    """
    power = np.asarray(band_ir, dtype=np.float64) ** 2
    onset = find_onset(power) if onset_index is None else int(onset_index)
    trunc = estimate_truncation(power[onset:], sample_rate)
    return _curve_from_truncation(
        power,
        sample_rate,
        onset,
        trunc,
        compensate=compensate,
        time_origin_index=time_origin_index,
    )


def fit_decay_metric(
    name: str,
    curve: SchroederCurve,
    evaluation_range_db: tuple[float, float],
    *,
    noise_margin_db: float,
    first_index: int = 0,
) -> DecayMetric:
    """Fit one metric; report INSUFFICIENT_RANGE instead of a number when the
    evaluation range is not at least ``noise_margin_db`` above the noise.

    The fit starts at the first curve sample at or below the upper limit, but
    not before curve index ``first_index`` (the end of the direct sound).
    """
    upper, lower = evaluation_range_db
    available = curve.truncation.peak_db - curve.truncation.noise_floor_db
    needed = abs(lower) + noise_margin_db
    if available < needed:
        return DecayMetric(
            name=name,
            seconds=None,
            validity=Validity.INSUFFICIENT_RANGE,
            evaluation_range_db=evaluation_range_db,
            reason=diag(
                "Insufficient decay range: {available:.1f} dB available, {needed:.0f} dB needed "
                "({range:.0f} dB range + {margin:.0f} dB above noise)",
                available=available,
                needed=needed,
                range=abs(lower),
                margin=noise_margin_db,
            ),
        )
    edc = curve.edc_db
    below_upper = np.nonzero(edc <= upper)[0]
    below_lower = np.nonzero(edc <= lower)[0]
    if below_upper.shape[0] == 0 or below_lower.shape[0] == 0:
        return DecayMetric(
            name=name,
            seconds=None,
            validity=Validity.INSUFFICIENT_RANGE,
            evaluation_range_db=evaluation_range_db,
            reason=diag(
                "Insufficient decay range: the decay curve does not reach the evaluation range"
            ),
        )
    i0 = max(int(below_upper[0]), first_index)
    i1 = int(below_lower[0])
    if i1 - i0 < 3:
        return DecayMetric(
            name=name,
            seconds=None,
            validity=Validity.UNRELIABLE,
            evaluation_range_db=evaluation_range_db,
            reason=(
                diag("Evaluation range covers fewer than 3 samples after the direct sound")
                if first_index > int(below_upper[0])
                else diag("Evaluation range covers fewer than 3 samples")
            ),
        )
    slope, _, r2 = _linear_fit(curve.time_s[i0 : i1 + 1], edc[i0 : i1 + 1])
    if not np.isfinite(slope) or slope >= 0.0:
        return DecayMetric(
            name=name,
            seconds=None,
            validity=Validity.UNRELIABLE,
            evaluation_range_db=evaluation_range_db,
            reason=diag("Decay slope is not negative"),
        )
    seconds = -60.0 / slope
    nonlinearity = 1000.0 * (1.0 - r2)
    return DecayMetric(
        name=name,
        seconds=float(seconds),
        validity=Validity.VALID,
        evaluation_range_db=evaluation_range_db,
        nonlinearity_permille=float(nonlinearity),
    )


def _fit_all(
    curve: SchroederCurve, noise_margin_db: float, first_index: int
) -> tuple[DecayMetric, DecayMetric, DecayMetric]:
    return (
        fit_decay_metric(
            "EDT", curve, _EDT_RANGE, noise_margin_db=noise_margin_db, first_index=first_index
        ),
        fit_decay_metric(
            "T20", curve, _T20_RANGE, noise_margin_db=noise_margin_db, first_index=first_index
        ),
        fit_decay_metric(
            "T30", curve, _T30_RANGE, noise_margin_db=noise_margin_db, first_index=first_index
        ),
    )


def _decimate_curve(
    curve: SchroederCurve, sample_rate: int, step_s: float = 0.001
) -> tuple[FloatArray, FloatArray]:
    step = max(1, round(step_s * sample_rate))
    return curve.time_s[::step], curve.edc_db[::step]


def _truncation_sensitivity(
    chosen: Sequence[DecayMetric], alternative: Sequence[DecayMetric]
) -> list[str]:
    """Differences between metrics fitted with two truncation estimates."""
    changes: list[str] = []
    for metric, other in zip(chosen, alternative, strict=True):
        if metric.validity is not Validity.VALID or metric.seconds is None:
            continue
        if other.seconds is None:
            changes.append(
                diag(
                    "{metric} {seconds:.2f} s vs no value",
                    metric=metric.name,
                    seconds=metric.seconds,
                )
            )
        elif abs(metric.seconds / other.seconds - 1.0) > TRUNCATION_SENSITIVITY:
            changes.append(
                diag(
                    "{metric} {seconds:.2f} s vs {other:.2f} s",
                    metric=metric.name,
                    seconds=metric.seconds,
                    other=other.seconds,
                )
            )
    return changes


def _edt_direct_check(edt: DecayMetric, direct_step_db: float | None) -> DecayMetric:
    """Mark EDT unreliable when the direct sound covers most of its range."""
    if direct_step_db is None or direct_step_db <= EDT_MAX_DIRECT_STEP_DB:
        return edt
    share = 100.0 * (1.0 - 10.0 ** (-direct_step_db / 10.0))
    return edt.marked_unreliable(
        diag(
            "the decay curve drops {step:.1f} dB across the direct sound (it carries "
            "{share:.0f} % of the energy; limit {limit:g} dB): EDT describes the direct sound "
            "rather than the room at this position",
            step=direct_step_db,
            share=share,
            limit=EDT_MAX_DIRECT_STEP_DB,
        )
    )


def straightness_limits(bandwidth_hz: float, t30_s: float) -> tuple[float, float]:
    """(max |C| in percent, max xi in permille) for a decay of ``t30_s`` in a
    band of ``bandwidth_hz``; see :data:`CURVATURE_SPREAD_PERCENT`."""
    root_bt = float(np.sqrt(max(bandwidth_hz * t30_s, 1e-12)))
    return (
        max(MAX_CURVATURE_PERCENT, CURVATURE_SPREAD_PERCENT / root_bt),
        max(MAX_NONLINEARITY_PERMILLE, NONLINEARITY_SPREAD_PERMILLE / root_bt),
    )


def _straightness_check(
    t20: DecayMetric, t30: DecayMetric, bandwidth_hz: float
) -> tuple[DecayMetric, DecayMetric, float | None, list[str]]:
    """Curvature from VALID T20/T30 and the non-straight-decay rules."""
    if not (
        t20.validity is Validity.VALID
        and t30.validity is Validity.VALID
        and t20.seconds is not None
        and t30.seconds is not None
        and t20.seconds > 0.0
    ):
        return t20, t30, None, []
    curvature = 100.0 * (t30.seconds / t20.seconds - 1.0)
    max_curvature, max_xi = straightness_limits(bandwidth_hz, t30.seconds)
    warnings: list[str] = []
    if abs(curvature) > max_curvature:
        warning = diag(
            "the decay curve is not straight (curvature C = {curvature:.0f} %, limit "
            "{limit:.0f} %): possibly a double slope, coupled volumes or strong early "
            "reflections; no single reverberation time describes it",
            curvature=curvature,
            limit=max_curvature,
        )
        warnings.append(warning)
        t20 = t20.marked_unreliable(warning)
        t30 = t30.marked_unreliable(warning)
    checked: list[DecayMetric] = []
    for metric in (t20, t30):
        xi = metric.nonlinearity_permille
        if metric.validity is Validity.VALID and xi is not None and xi > max_xi:
            warning = diag(
                "the {metric} fit is not straight (xi = {xi:.0f} permille, limit "
                "{limit:.0f}): {metric} is not a reliable reverberation time here",
                metric=metric.name,
                xi=xi,
                limit=max_xi,
            )
            warnings.append(warning)
            metric = metric.marked_unreliable(warning)
        checked.append(metric)
    return checked[0], checked[1], curvature, warnings


def _tail_compensation(trunc: TruncationEstimate, sample_rate: int) -> tuple[float, float]:
    """Energy and first moment of the extrapolated tail, in sample-power units.

    The moment is ``∫ u p(u) du`` from the truncation instant, times the sample
    rate, so it is added to ``Σ t·h²`` after ``energy * t_truncation``. Same
    exponential as the Schroeder compensation. ``(0, 0)`` when there is no
    negative late slope.
    """
    slope = trunc.late_slope_db_per_s
    if slope is None or not np.isfinite(slope) or slope >= 0.0:
        return 0.0, 0.0
    if not np.isfinite(trunc.noise_floor_db):
        return 0.0, 0.0
    p_c = 10.0 ** (trunc.noise_floor_db / 10.0)
    beta = slope * np.log(10.0) / 10.0
    energy = p_c * (-1.0 / beta) * sample_rate
    moment = p_c * sample_rate / (beta * beta)
    if not np.isfinite(energy) or not np.isfinite(moment) or energy < 0.0:
        return 0.0, 0.0
    return float(energy), float(moment)


def _insufficient_energy(available_db: float) -> tuple[EnergyMetric, ...]:
    reason = diag(
        "Insufficient decay range for an early/late energy ratio: {available:.1f} dB "
        "available, {needed:.0f} dB needed",
        available=available_db,
        needed=ENERGY_MIN_DECAY_RANGE_DB,
    )
    specs = (("C50", "dB"), ("C80", "dB"), ("D50", "%"), ("Ts", "s"))
    return tuple(
        EnergyMetric(name, None, unit, Validity.INSUFFICIENT_RANGE, reason) for name, unit in specs
    )


def _split_index(origin: int, split_s: float, sample_rate: int) -> int:
    """First sample at or after ``split_s`` measured from ``origin``."""
    return origin + int(np.round(split_s * sample_rate))


def _early_late(
    power: FloatArray,
    onset: int,
    trunc_abs: int,
    split: int,
    compensation: float,
) -> tuple[float, float] | None:
    """``(early, late)`` sample-power sums, or ``None`` when the split is unusable."""
    if split <= onset or split >= trunc_abs:
        return None
    early = float(np.sum(power[onset:split]))
    late = float(np.sum(power[split:trunc_abs])) + compensation
    if early <= 0.0 or late <= 0.0 or not np.isfinite(early + late):
        return None
    return early, late


def _window_missed(name: str, truncation_s: float, split_s: float) -> EnergyMetric:
    unit = {"C50": "dB", "C80": "dB", "D50": "%"}[name]
    return EnergyMetric(
        name=name,
        value=None,
        unit=unit,
        validity=Validity.NOT_COMPUTED,
        reason=diag(
            "the noise truncation ({truncation_s:.3f} s) is not after the {split_ms:.0f} ms "
            "early window, so the late energy is not measured",
            truncation_s=truncation_s,
            split_ms=split_s * 1000.0,
        ),
    )


def _energy_metrics(
    power: FloatArray,
    sample_rate: int,
    onset: int,
    trunc: TruncationEstimate,
    origin: int,
) -> tuple[EnergyMetric, EnergyMetric, EnergyMetric, EnergyMetric]:
    """C50, C80, D50 (percent) and centre time from one truncated squared response."""
    available = float(trunc.peak_db - trunc.noise_floor_db)
    if not np.isfinite(available) or available < ENERGY_MIN_DECAY_RANGE_DB:
        c50, c80, d50, centre = _insufficient_energy(available if np.isfinite(available) else 0.0)
        return c50, c80, d50, centre

    trunc_abs = min(power.shape[0], onset + trunc.truncation_index)
    compensation, tail_moment = (
        _tail_compensation(trunc, sample_rate) if trunc_abs < power.shape[0] else (0.0, 0.0)
    )
    truncation_s = (trunc_abs - origin) / sample_rate

    def clarity(name: str, split_s: float) -> EnergyMetric:
        split = _split_index(origin, split_s, sample_rate)
        parts = _early_late(power, onset, trunc_abs, split, compensation)
        if parts is None:
            return _window_missed(name, truncation_s, split_s)
        early, late = parts
        return EnergyMetric(
            name=name,
            value=float(10.0 * np.log10(early / late)),
            unit="dB",
            validity=Validity.VALID,
        )

    def definition(split_s: float) -> EnergyMetric:
        split = _split_index(origin, split_s, sample_rate)
        parts = _early_late(power, onset, trunc_abs, split, compensation)
        if parts is None:
            return _window_missed("D50", truncation_s, split_s)
        early, late = parts
        return EnergyMetric(
            name="D50",
            value=float(100.0 * early / (early + late)),
            unit="%",
            validity=Validity.VALID,
        )

    c50 = clarity("C50", C50_SPLIT_S)
    c80 = clarity("C80", C80_SPLIT_S)
    d50 = definition(C50_SPLIT_S)

    start = min(max(origin, onset), trunc_abs)
    if trunc_abs <= onset:
        centre = EnergyMetric(
            name="Ts",
            value=None,
            unit="s",
            validity=Validity.NOT_COMPUTED,
            reason=diag("the response is too short for a centre time"),
        )
    else:
        idx = np.arange(start, trunc_abs)
        times = (idx - origin) / sample_rate
        moment = float(np.sum(times * power[start:trunc_abs]))
        energy = float(np.sum(power[onset:trunc_abs])) + compensation
        moment += compensation * truncation_s + tail_moment
        if energy <= 0.0 or not np.isfinite(moment) or not np.isfinite(energy):
            centre = EnergyMetric(
                name="Ts",
                value=None,
                unit="s",
                validity=Validity.NOT_COMPUTED,
                reason=diag("the response is too short for a centre time"),
            )
        else:
            centre = EnergyMetric(
                name="Ts", value=float(moment / energy), unit="s", validity=Validity.VALID
            )
    return c50, c80, d50, centre


def _energy_truncation_changes(
    chosen: tuple[EnergyMetric, EnergyMetric, EnergyMetric, EnergyMetric],
    alternative: tuple[EnergyMetric, EnergyMetric, EnergyMetric, EnergyMetric],
) -> list[tuple[str, str]]:
    """``(name, sentence)`` for energy parameters that move under the other truncation."""
    limits = {
        "C50": ENERGY_C_SENSITIVITY_DB,
        "C80": ENERGY_C_SENSITIVITY_DB,
        "D50": ENERGY_D50_SENSITIVITY_PERCENT,
        "Ts": ENERGY_TS_SENSITIVITY_S,
    }
    changes: list[tuple[str, str]] = []
    for metric, other in zip(chosen, alternative, strict=True):
        if metric.validity is not Validity.VALID or metric.value is None:
            continue
        if other.value is None:
            changes.append(
                (
                    metric.name,
                    diag(
                        "{metric} has no truncation-independent value",
                        metric=metric.name,
                    ),
                )
            )
            continue
        if abs(metric.value - other.value) <= limits[metric.name]:
            continue
        if metric.unit == "dB":
            text = diag(
                "{metric} {value:.1f} dB vs {other:.1f} dB",
                metric=metric.name,
                value=metric.value,
                other=other.value,
            )
        elif metric.unit == "%":
            text = diag(
                "{metric} {value:.1f} % vs {other:.1f} %",
                metric=metric.name,
                value=metric.value,
                other=other.value,
            )
        else:
            text = diag(
                "{metric} {seconds:.3f} s vs {other:.3f} s",
                metric=metric.name,
                seconds=metric.value,
                other=other.value,
            )
        changes.append((metric.name, text))
    return changes


def _mark_energy_unreliable(
    metrics: tuple[EnergyMetric, EnergyMetric, EnergyMetric, EnergyMetric],
    reason: str,
    names: set[str] | None = None,
) -> tuple[EnergyMetric, EnergyMetric, EnergyMetric, EnergyMetric]:
    """Mark every VALID energy parameter in ``names`` (default: all of them)."""
    marked: list[EnergyMetric] = []
    for metric in metrics:
        if names is None or metric.name in names:
            marked.append(metric.marked_unreliable(reason))
        else:
            marked.append(metric)
    return marked[0], marked[1], marked[2], marked[3]


def analyze_band(
    band_ir: FloatArray,
    sample_rate: int,
    band: Band | None,
    *,
    noise_margin_db: float,
    direct_index: int | None = None,
    time_origin_index: int | None = None,
    onset_search_start: int | None = None,
    direct_spread_s: float = DIRECT_SOUND_MARGIN_S,
    broadband_bandwidth_hz: float | None = None,
) -> BandDecay:
    """Decay analysis of one (band-filtered) response.

    ``direct_index`` is the broadband direct sound in ``band_ir``. When it is
    ``None`` the plain ISO ranges are fitted from the onset, the EDT
    direct-sound check is skipped and the early/late energy parameters are
    timed from the onset (when it is later than ``time_origin_index``).
    ``time_origin_index`` (default: ``direct_index`` if given, else 0) is
    time 0 of all other reported times.
    ``onset_search_start`` (default: :func:`onset_search_window_s` of the band
    before a given ``direct_index``, else 0) is where the onset search begins.
    ``direct_spread_s`` is how long the direct sound lasts after its peak.
    ``broadband_bandwidth_hz`` (default: Nyquist) is the bandwidth used for
    the straightness limits when ``band`` is ``None``.
    """
    signal = np.asarray(band_ir, dtype=np.float64)
    power = signal**2
    if broadband_bandwidth_hz is None:
        broadband_bandwidth_hz = sample_rate / 2.0
    if direct_index is None:
        origin = 0 if time_origin_index is None else time_origin_index
        search_start = 0 if onset_search_start is None else onset_search_start
    else:
        origin = direct_index if time_origin_index is None else time_origin_index
        if onset_search_start is None:
            window = onset_search_window_s(band.bandwidth_hz if band is not None else None)
            search_start = max(0, direct_index - round(window * sample_rate))
        else:
            search_start = onset_search_start
    onset = find_onset(power, search_start=search_start)
    trunc = estimate_truncation(power[onset:], sample_rate)
    curve = _curve_from_truncation(
        power, sample_rate, onset, trunc, compensate=True, time_origin_index=origin
    )
    # First curve sample after the direct sound (and its pulse spread); without
    # a known direct sound the plain ISO ranges are used.
    first_index = 0
    if direct_index is not None:
        first_index = max(0, direct_index + round(direct_spread_s * sample_rate) + 1 - onset)
    edt, t20, t30 = _fit_all(curve, noise_margin_db, first_index)
    warnings: list[str] = []

    direct_step_db: float | None = None
    if direct_index is not None and first_index < curve.edc_db.shape[0]:
        direct_step_db = float(-curve.edc_db[first_index])
    edt = _edt_direct_check(edt, direct_step_db)
    # Early/late energy is timed from the direct sound; without one, from the
    # onset -- not from the first sample, or leading silence would move it.
    energy_origin = origin if direct_index is not None else max(origin, onset)
    c50, c80, d50, centre = _energy_metrics(power, sample_rate, onset, trunc, energy_origin)

    if trunc.problem is not None:
        rejected = trunc.rejected_estimate()
        if rejected is None:
            changes = [
                diag("{metric} has no truncation-independent value", metric=m.name)
                for m in (edt, t20, t30)
                if m.validity is Validity.VALID
            ]
            energy_changes = [
                (
                    m.name,
                    diag("{metric} has no truncation-independent value", metric=m.name),
                )
                for m in (c50, c80, d50, centre)
                if m.validity is Validity.VALID
            ]
        else:
            alternative = _curve_from_truncation(
                power, sample_rate, onset, rejected, compensate=True, time_origin_index=origin
            )
            changes = _truncation_sensitivity(
                (edt, t20, t30), _fit_all(alternative, noise_margin_db, first_index)
            )
            energy_changes = _energy_truncation_changes(
                (c50, c80, d50, centre),
                _energy_metrics(power, sample_rate, onset, rejected, energy_origin),
            )
        if changes:
            reason = diag(
                "the noise truncation is not trustworthy ({problem}) and the result depends "
                "on it ({changes})",
                problem=trunc.problem,
                changes="; ".join(changes),
            )
            warnings.append(reason)
            edt = edt.marked_unreliable(reason)
            t20 = t20.marked_unreliable(reason)
            t30 = t30.marked_unreliable(reason)
        if energy_changes:
            energy_reason = diag(
                "the noise truncation is not trustworthy ({problem}) and the result depends "
                "on it ({changes})",
                problem=trunc.problem,
                changes="; ".join(text for _name, text in energy_changes),
            )
            if energy_reason not in warnings:
                warnings.append(energy_reason)
            c50, c80, d50, centre = _mark_energy_unreliable(
                (c50, c80, d50, centre),
                energy_reason,
                {name for name, _text in energy_changes},
            )

    bt_product: float | None = None
    filter_warning: str | None = None
    if band is not None:
        reference_t = next((m.seconds for m in (t30, t20, edt) if m.seconds is not None), None)
        if reference_t is not None:
            bt_product = band.bandwidth_hz * reference_t
            if bt_product < MIN_BT_PRODUCT:
                filter_warning = diag(
                    "B*T = {bt:.1f} < {minimum:g}: the band filter's own decay is comparable "
                    "to the measured decay; values in this band are unreliable",
                    bt=bt_product,
                    minimum=MIN_BT_PRODUCT,
                )
                edt = edt.marked_unreliable(filter_warning)
                t20 = t20.marked_unreliable(filter_warning)
                t30 = t30.marked_unreliable(filter_warning)
                c50, c80, d50, centre = _mark_energy_unreliable(
                    (c50, c80, d50, centre), filter_warning
                )

    t20, t30, curvature, straightness_warnings = _straightness_check(
        t20, t30, band.bandwidth_hz if band is not None else broadband_bandwidth_hz
    )
    warnings.extend(straightness_warnings)

    rt60: float | None = None
    basis: str | None = None
    for metric in (t30, t20):
        if metric.validity is Validity.VALID and metric.seconds is not None:
            rt60 = metric.seconds
            basis = metric.name
            break

    edc_time, edc_db = _decimate_curve(curve, sample_rate)
    return BandDecay(
        band_label=band.label if band is not None else "broadband",
        center_hz=band.label_hz if band is not None else None,
        low_hz=band.low_hz if band is not None else None,
        high_hz=band.high_hz if band is not None else None,
        noise_floor_db=float(trunc.noise_floor_db - trunc.peak_db),
        peak_to_noise_db=float(trunc.peak_db - trunc.noise_floor_db),
        truncation_time_s=float((curve.truncation_index - origin) / sample_rate),
        edt=edt,
        t20=t20,
        t30=t30,
        rt60_estimate_s=rt60,
        rt60_basis=basis,
        curvature_percent=curvature,
        filter_bt_product=bt_product,
        filter_warning=filter_warning,
        edc_time_s=edc_time,
        edc_db=edc_db,
        onset_time_s=float((onset - origin) / sample_rate),
        mid_band_hz=band.center_hz if band is not None else None,
        warnings=tuple(warnings),
        c50=c50,
        c80=c80,
        d50=d50,
        centre_time=centre,
    )


def _outside_excitation_reason(band: Band, excitation: ExcitationBand) -> str:
    """Why ``band`` has no decay values; one sentence per excitation source."""
    params = {
        "band": band.label,
        "band_low": band.low_hz,
        "band_high": band.high_hz,
        "low": excitation.low_hz,
        "high": excitation.high_hz,
    }
    source = excitation.source
    if source == EXCITATION_SOURCE_SETTINGS:
        return diag(
            "the {band} band ({band_low:.0f}-{band_high:.0f} Hz) is not fully inside the "
            "excitation range ({low:.0f}-{high:.0f} Hz, sweep settings): it contains only "
            "leakage and noise, so no decay values are reported",
            **params,
        )
    if source == EXCITATION_SOURCE_ESTIMATED:
        return diag(
            "the {band} band ({band_low:.0f}-{band_high:.0f} Hz) is not fully inside the "
            "excitation range ({low:.0f}-{high:.0f} Hz, estimated from reference audio): it "
            "contains only leakage and noise, so no decay values are reported",
            **params,
        )
    if source == EXCITATION_SOURCE_DECLARED:
        return diag(
            "the {band} band ({band_low:.0f}-{band_high:.0f} Hz) is not fully inside the "
            "excitation range ({low:.0f}-{high:.0f} Hz, declared by the user): it contains "
            "only leakage and noise, so no decay values are reported",
            **params,
        )
    if source == EXCITATION_SOURCE_UNKNOWN:
        return diag(
            "the {band} band ({band_low:.0f}-{band_high:.0f} Hz) is not fully inside the "
            "excitation range ({low:.0f}-{high:.0f} Hz, unknown): it contains only leakage "
            "and noise, so no decay values are reported",
            **params,
        )
    return diag(
        "the {band} band ({band_low:.0f}-{band_high:.0f} Hz) is not fully inside the "
        "excitation range ({low:.0f}-{high:.0f} Hz, {source}): it contains only leakage and "
        "noise, so no decay values are reported",
        source=source,
        **params,
    )


def _outside_excitation_band(band: Band, excitation: ExcitationBand) -> BandDecay:
    reason = _outside_excitation_reason(band, excitation)

    def withheld(name: str, evaluation_range: tuple[float, float]) -> DecayMetric:
        return DecayMetric(
            name=name,
            seconds=None,
            validity=Validity.OUTSIDE_EXCITATION,
            evaluation_range_db=evaluation_range,
            reason=reason,
        )

    return BandDecay(
        band_label=band.label,
        center_hz=band.label_hz,
        low_hz=band.low_hz,
        high_hz=band.high_hz,
        noise_floor_db=None,
        peak_to_noise_db=None,
        truncation_time_s=None,
        edt=withheld("EDT", _EDT_RANGE),
        t20=withheld("T20", _T20_RANGE),
        t30=withheld("T30", _T30_RANGE),
        rt60_estimate_s=None,
        rt60_basis=None,
        curvature_percent=None,
        filter_bt_product=None,
        filter_warning=None,
        edc_time_s=np.zeros(0, dtype=np.float64),
        edc_db=np.zeros(0, dtype=np.float64),
        onset_time_s=None,
        mid_band_hz=band.center_hz,
        warnings=(reason,),
        c50=EnergyMetric("C50", None, "dB", Validity.OUTSIDE_EXCITATION, reason),
        c80=EnergyMetric("C80", None, "dB", Validity.OUTSIDE_EXCITATION, reason),
        d50=EnergyMetric("D50", None, "%", Validity.OUTSIDE_EXCITATION, reason),
        centre_time=EnergyMetric("Ts", None, "s", Validity.OUTSIDE_EXCITATION, reason),
    )


def _result_notes(
    broadband: BandDecay,
    bands: Sequence[BandDecay],
    excitation: ExcitationBand | None,
) -> tuple[str, ...]:
    notes: list[str] = []
    outside = [b for b in bands if b.t30.validity is Validity.OUTSIDE_EXCITATION]
    if outside and excitation is not None:
        labels = ", ".join(b.band_label for b in outside)
        notes.append(
            diag(
                "decay analysis: the {bands} band(s) are not fully inside the excitation range "
                "({low:.0f}-{high:.0f} Hz); no decay values are reported for them",
                bands=labels,
                low=excitation.low_hz,
                high=excitation.high_hz,
            )
        )
    for band in (broadband, *bands):
        if band.t30.validity is Validity.OUTSIDE_EXCITATION:
            continue
        for warning in band.warnings:
            if band.band_label == "broadband":
                notes.append(diag("decay analysis, broadband: {warning}", warning=warning))
            else:
                notes.append(
                    diag(
                        "decay analysis, {band}: {warning}",
                        band=band.band_label,
                        warning=warning,
                    )
                )
    return tuple(notes)


def analyze_decay(
    ir: FloatArray,
    sample_rate: int,
    settings: AnalysisSettings,
    *,
    direct_index: int | None = None,
    excitation_band: ExcitationBand | None = None,
) -> DecayResult:
    """Broadband and octave-band decay analysis.

    ``ir`` should contain :func:`decay_lead_in_s` of signal before the direct
    sound at ``direct_index`` (missing lead-in is zero-padded). Without
    ``direct_index`` the onset search starts at the beginning of ``ir``, the
    plain ISO ranges are fitted and times are measured from its first sample,
    except C50, C80, D50 and ``Ts``, which are timed from each curve's onset.
    Bands that are not fully inside ``excitation_band`` are returned with
    ``Validity.OUTSIDE_EXCITATION`` and no numbers; bands above 0.9 * Nyquist
    are skipped.
    """
    signal = np.asarray(ir, dtype=np.float64)
    known = direct_index is not None
    lead = round(decay_lead_in_s(settings) * sample_rate)
    pad = max(0, lead - (direct_index if direct_index is not None else 0))
    if pad:
        signal = np.concatenate([np.zeros(pad, dtype=np.float64), signal])
    direct = (direct_index if direct_index is not None else 0) + pad
    origin = direct
    excitation_bw = (
        excitation_band.high_hz - excitation_band.low_hz if excitation_band is not None else None
    )
    spread_s = DIRECT_SOUND_MARGIN_S + pulse_spread_s(excitation_bw)
    noise_margin = settings.decay_noise_margin_db

    def search_start(bandwidth_hz: float | None) -> int:
        if not known:
            return 0
        return max(0, direct - round(onset_search_window_s(bandwidth_hz) * sample_rate))

    broadband = analyze_band(
        signal,
        sample_rate,
        None,
        noise_margin_db=noise_margin,
        direct_index=direct if known else None,
        time_origin_index=origin,
        onset_search_start=search_start(excitation_bw),
        direct_spread_s=spread_s,
        broadband_bandwidth_hz=excitation_bw,
    )
    bands: list[BandDecay] = []
    for center in settings.octave_bands_hz:
        band = iec_band(center, 1)
        if not band_fits(band, sample_rate):
            continue
        if excitation_band is not None and not excitation_band.contains(band.low_hz, band.high_hz):
            bands.append(_outside_excitation_band(band, excitation_band))
            continue
        filtered = apply_bandpass(signal, bandpass_sos(band, sample_rate), time_reversed=True)
        bands.append(
            analyze_band(
                filtered,
                sample_rate,
                band,
                noise_margin_db=noise_margin,
                direct_index=direct if known else None,
                time_origin_index=origin,
                onset_search_start=search_start(band.bandwidth_hz),
                direct_spread_s=spread_s,
            )
        )
    return DecayResult(
        method=DECAY_METHOD,
        broadband=broadband,
        bands=tuple(bands),
        notes=_result_notes(broadband, bands, excitation_band),
        time_origin=DECAY_TIME_ORIGIN if known else TIME_ORIGIN_SIGNAL_START,
    )
