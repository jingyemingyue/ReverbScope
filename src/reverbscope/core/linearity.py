"""Checks that the measurement chain stayed linear.

Two failures are detected here, because both make the deconvolved impulse
response something other than the room's:

Clipping (flat tops)
--------------------
An absolute threshold (``|x| >= 0.999``) misses every recording that was
clipped and then attenuated - by a fader, clip gain or an export ceiling -
and it wrongly flags an unclipped file that was normalised to 0 dBFS.
:func:`detect_clipping` instead looks for *plateaus*: runs of at least
:data:`CLIPPING_MIN_RUN` consecutive samples at the file's own maximum
magnitude, with a slope discontinuity at both ends (a smooth crest reaches
its maximum with curvature, a clipped one with a kink). The tolerance follows
the file's quantisation step, so that a dithered export is still recognised.
Clipping in the *playback* path is a different failure and is not visible in
the recording at all; that is what the aliased-distortion probe below is for.

Aliased (digital) distortion
----------------------------
Farina's rule that harmonic products appear *before* the linear impulse
response holds only for alias-free distortion. A nonlinearity in the digital
domain at the sample rate - a clipped DAW bus, a saturator or plug-in without
oversampling, float-to-int clipping on export - folds the harmonics that
exceed the Nyquist frequency back to ``|k*f(t) - m*fs|``. For a rising sweep
those trajectories *fall*, so the ascending inverse filter spreads them over
seconds *after* the direct sound, where they look like a long decay. The
pre-peak margin and the clipping check cannot see this: the recording itself
need not clip.

:func:`aliased_distortion_levels` therefore probes for them directly. For
order ``k`` it builds the part of the k-th harmonic sweep that is folded once
(``k*f(t)`` between ``fs/2`` and ``fs``, alias ``fs - k*f(t)``), scaled like
the played sweep, and deconvolves the recording with its inverse filter
(time-reversed, ``exp(t/L)``-weighted, normalised to unit in-band magnitude
like the linear one). An aliased product then compresses into a pulse at a
known position, and its energy relative to the linear response - measured in
the same short window and the same frequency band - is the level of that
distortion product. The band is the part of the folded trajectory that is
inside the excitation band and away from the frequencies where the linear
sweep or a lower-order *non-aliased* harmonic crosses the same trajectory in
time and frequency; a floor taken from windows before the expected position
bounds whatever else disperses into that band. A product is called
significant when it stands at least :data:`ALIAS_DETECTION_MARGIN_DB` above
that floor and reaches :data:`ALIAS_SIGNIFICANT_DB` relative to the linear
response, which is where the folded products start to bend the late decay.

Limitations: the probe needs the sweep definition (a reference given only as
audio has no known phase), and it covers the orders in
:data:`ALIAS_PROBE_ORDERS` with a single fold. Harmonics that fold more than
once, or orders above those, are not probed; at 88.2 kHz and above the second
and third harmonics of a 20 kHz sweep do not alias into the swept range at
all, so the probe reports that it is not applicable.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy import fft as sfft
from scipy.signal import fftconvolve

from reverbscope.core.sweep import sweep_time_axis
from reverbscope.i18n import diag
from reverbscope.models.audio import FloatArray
from reverbscope.models.configuration import SweepSettings
from reverbscope.models.result import AliasedDistortion, ClippingCheck, ExcitationBand

_TINY = 1e-300

#: Shortest run of samples at the file maximum that counts as a flat top.
CLIPPING_MIN_RUN = 3
#: Number of such runs needed before clipping is reported.
CLIPPING_MIN_RUNS = 8
#: Plateaus below this level are not reported: a quantised low-frequency crest
#: of a quiet signal is flat as well, and a file clipped this far below full
#: scale cannot be told from one.
CLIPPING_MIN_LEVEL_DBFS = -20.0
#: Plateau tolerance relative to the file maximum (for float files).
CLIPPING_RELATIVE_TOLERANCE = 1e-7
#: ... or this many quantisation steps for a quantised file (covers dither).
CLIPPING_QUANTISATION_STEPS = 2.0
#: A plateau must end with a step of at least this many tolerances, otherwise
#: it is the quantised crest of a smooth waveform, not a clipped one. At 8,
#: no unclipped signal of the calibration set is flagged (sweeps of 2 to 30 s
#: and sines from 20 Hz to 1 kHz at 0 dBFS, 16-bit and 24-bit, dithered or
#: not) and every clip of 3 dB or more of overdrive is, at any export level.
#: Missed: 1 dB of overdrive on 16-bit low-frequency content (its kink is as
#: small as the quantisation step) and on content above a few kHz (its
#: plateau is shorter than three samples).
CLIPPING_MIN_EDGE_STEPS = 8.0
#: Quantisation grids that are recognised (16-bit and 24-bit PCM).
CLIPPING_QUANTISATION_GRIDS = (2.0**-15, 2.0**-23)

#: Harmonic orders whose once-folded alias trajectory is probed.
ALIAS_PROBE_ORDERS = (2, 3)
#: Half length of the (Hann-windowed) analysis window centred on the expected
#: position of an aliased product (s).
ALIAS_WINDOW_HALF_S = 0.004
#: Guard added to that window when excluding interfering frequencies (s).
ALIAS_GUARD_S = 0.005
#: Extra guard below the window for the room's own reverberation (s).
ALIAS_REVERB_GUARD_S = 0.050
#: Frequency guard around an excluded trajectory, in bins of the analysis
#: window: an interfering chirp leaks into its neighbourhood, and the Hann
#: window's sidelobes are below -60 dB only this far away.
ALIAS_GUARD_BINS = 8.0
#: Floor window: chunks between these distances before the expected position (s).
ALIAS_FLOOR_FAR_S = 0.5
ALIAS_FLOOR_NEAR_S = 0.02
ALIAS_FLOOR_MAX_CHUNKS = 20
#: A product must stand this far above the floor to be a measurement.
ALIAS_DETECTION_MARGIN_DB = 6.0
#: ... and this far above (dB re the linear response) to matter: below it the
#: folded products stay under the noise of a normal measurement, above it they
#: bend the late decay (calibrated on synthetic rooms, see tests).
ALIAS_SIGNIFICANT_DB = -40.0
#: Highest analysed frequency as a fraction of the sample rate (the converters'
#: anti-alias filters roll off above roughly this).
ALIAS_MAX_NYQUIST_FRACTION = 0.45
#: Narrowest usable analysis band, in bins of the analysis window.
ALIAS_MIN_BAND_BINS = 8.0


def quantisation_step(x: FloatArray) -> float | None:
    """The PCM quantisation step of ``x``, or ``None`` for float data.

    Integer WAV data read as floats sits exactly on a ``1/2^(bits-1)`` grid.
    Knowing the step turns "the samples are equal" into a question with a
    definite answer even for a dithered export.
    """
    for step in CLIPPING_QUANTISATION_GRIDS:
        scaled = x / step
        if np.all(np.abs(scaled - np.round(scaled)) < 1e-6):
            return step
    return None


def _runs(mask: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Start (inclusive) and stop (exclusive) indices of the runs of ``True``."""
    edges = np.flatnonzero(np.diff(np.concatenate([[0], mask.view(np.int8), [0]])))
    return edges[0::2], edges[1::2]


def detect_clipping(x: FloatArray) -> ClippingCheck:
    """Look for flat-topped peaks at the recording's own maximum level.

    The level of the plateaus is reported as well, because a recording clipped
    before a gain change plateaus below 0 dBFS.
    """
    magnitude = np.abs(np.asarray(x, dtype=np.float64))
    peak = float(np.max(magnitude)) if magnitude.shape[0] else 0.0
    step = quantisation_step(magnitude)
    tolerance = max(
        CLIPPING_RELATIVE_TOLERANCE * peak,
        CLIPPING_QUANTISATION_STEPS * step if step is not None else 0.0,
    )
    empty = ClippingCheck(
        peak_dbfs=float(20.0 * math.log10(max(peak, _TINY))),
        runs=0,
        samples=0,
        clipped=False,
        quantisation_step=step,
    )
    if peak <= 0.0 or 20.0 * math.log10(peak) < CLIPPING_MIN_LEVEL_DBFS:
        return empty
    at_peak = magnitude >= peak - tolerance
    starts, stops = _runs(at_peak)
    long_enough = (stops - starts) >= CLIPPING_MIN_RUN
    starts, stops = starts[long_enough], stops[long_enough]
    if starts.shape[0] == 0:
        return empty
    # A clipped peak enters and leaves its plateau with a step (the slope of
    # the unclipped waveform); a quantised smooth crest leaves it by one
    # quantisation level.
    before = np.where(starts > 0, magnitude[np.maximum(starts - 1, 0)], 0.0)
    after = np.where(
        stops < magnitude.shape[0], magnitude[np.minimum(stops, magnitude.shape[0] - 1)], 0.0
    )
    step_out = np.maximum(peak - before, peak - after)
    kinked = step_out >= CLIPPING_MIN_EDGE_STEPS * max(tolerance, _TINY)
    starts, stops = starts[kinked], stops[kinked]
    runs = int(starts.shape[0])
    return ClippingCheck(
        peak_dbfs=empty.peak_dbfs,
        runs=runs,
        samples=int(np.sum(stops - starts)),
        clipped=runs >= CLIPPING_MIN_RUNS,
        quantisation_step=step,
    )


@dataclass(frozen=True)
class _AliasTrajectory:
    """The once-folded part of the k-th harmonic sweep."""

    order: int
    #: Sweep samples ``[start, stop)`` whose k-th harmonic exceeds Nyquist.
    start: int
    stop: int
    #: Folded frequencies at those samples (descending), ``fs - k*f(t)``.
    low_hz: float
    high_hz: float


def _alias_trajectory(
    settings: SweepSettings, order: int, band: ExcitationBand
) -> _AliasTrajectory | None:
    """Samples of the sweep whose ``order``-th harmonic folds once, or ``None``."""
    sample_rate = settings.sample_rate
    nyquist = sample_rate / 2.0
    low_f = max(band.low_hz, nyquist / order)
    high_f = min(band.high_hz, sample_rate / order)
    if high_f <= low_f:
        return None
    rate = settings.sweep_rate
    start = math.ceil(rate * math.log(low_f / settings.start_hz) * sample_rate)
    stop = math.floor(rate * math.log(high_f / settings.start_hz) * sample_rate)
    start, stop = max(0, start), min(settings.sweep_samples, stop)
    if stop - start < 16:
        return None
    return _AliasTrajectory(
        order=order,
        start=start,
        stop=stop,
        low_hz=sample_rate - order * high_f,
        high_hz=sample_rate - order * low_f,
    )


def _crossing_frequency(
    sample_rate: int, order: int, other: int, delay_s: float, sweep_rate_s: float
) -> float:
    """Frequency at which the non-aliased ``other``-th harmonic reaches the probe.

    Through the probe's inverse filter, a component following ``other*f(t)``
    arrives ``L*ln(order*g / (other*(fs - g)))`` from the expected position of
    the folded ``order``-th harmonic; this inverts that relation.
    """
    e = math.exp(delay_s / sweep_rate_s)
    return float(other * sample_rate * e / (order + other * e))


def _analysis_band(
    trajectory: _AliasTrajectory,
    settings: SweepSettings,
    band: ExcitationBand,
    *,
    window_bins_hz: float,
) -> tuple[tuple[float, float] | None, str | None]:
    """Highest usable part of the folded trajectory (Hz), or ``None``.

    Excluded are frequencies outside the excitation band or the converters'
    passband, those where the linear sweep or a lower-order non-aliased
    harmonic arrives inside the analysis window (with a guard of
    :data:`ALIAS_GUARD_BINS` window bins, because those components are 30 dB
    to 60 dB stronger and leak into their neighbourhood), and those whose
    interference arrives before the floor window, where the floor could not
    see it. The highest wide enough piece is preferred: above every crossing,
    the interfering components arrive only *after* the analysis window.
    """
    sample_rate = settings.sample_rate
    rate = settings.sweep_rate
    guard_hz = ALIAS_GUARD_BINS * window_bins_hz
    low = max(trajectory.low_hz, band.low_hz)
    high = min(trajectory.high_hz, band.high_hz, ALIAS_MAX_NYQUIST_FRACTION * sample_rate)
    if high <= low:
        return None, diag(
            "harmonic {order} folds back to {low_khz:.1f}-{high_khz:.1f} kHz, outside the "
            "swept range, where the inverse filter has no gain: such products cannot reach the "
            "impulse response",
            order=trajectory.order,
            low_khz=trajectory.low_hz / 1000.0,
            high_khz=trajectory.high_hz / 1000.0,
        )
    edges = [(low, high)]
    for other in range(1, trajectory.order):
        blocked_low = (
            _crossing_frequency(
                sample_rate,
                trajectory.order,
                other,
                -(ALIAS_WINDOW_HALF_S + ALIAS_GUARD_S + ALIAS_REVERB_GUARD_S),
                rate,
            )
            - guard_hz
        )
        blocked_high = (
            _crossing_frequency(
                sample_rate, trajectory.order, other, ALIAS_WINDOW_HALF_S + ALIAS_GUARD_S, rate
            )
            + guard_hz
        )
        # Interference that arrives before the floor window is not bounded by
        # the floor either, so keep only frequencies at or after it.
        seen_from = _crossing_frequency(
            sample_rate, trajectory.order, other, -(ALIAS_FLOOR_FAR_S - ALIAS_GUARD_S), rate
        )
        pieces: list[tuple[float, float]] = []
        for lo, hi in edges:
            lo = max(lo, seen_from)
            if hi <= lo:
                continue
            if blocked_high <= lo or blocked_low >= hi:
                pieces.append((lo, hi))
                continue
            if blocked_low > lo:
                pieces.append((lo, blocked_low))
            if blocked_high < hi:
                pieces.append((blocked_high, hi))
        edges = pieces
    wide = [p for p in edges if p[1] - p[0] >= ALIAS_MIN_BAND_BINS * window_bins_hz]
    if not wide:
        return None, diag(
            "no wide enough part of the folded trajectory of harmonic {order} can be "
            "separated from the sweep and its non-aliased harmonics",
            order=trajectory.order,
        )
    return max(wide, key=lambda p: p[1]), None


def _harmonic_reference(settings: SweepSettings, trajectory: _AliasTrajectory) -> FloatArray:
    """The played sweep's ``order``-th harmonic over the folded segment.

    Sampling ``sin(k*phi(t))`` at the sample rate *is* the folded (aliased)
    signal, so no explicit folding is needed. The amplitude follows the played
    sweep, which makes the measured level a level relative to the fundamental.
    """
    t = sweep_time_axis(settings)[trajectory.start : trajectory.stop]
    rate = settings.sweep_rate
    phase = 2.0 * np.pi * settings.start_hz * rate * (np.exp(t / rate) - 1.0)
    reference = settings.amplitude * np.sin(trajectory.order * phase)
    fade = max(1, round(0.002 * settings.sample_rate))
    ramp = np.sin(0.5 * np.pi * np.arange(fade, dtype=np.float64) / fade) ** 2
    reference[:fade] *= ramp
    reference[-fade:] *= ramp[::-1]
    return np.asarray(reference, dtype=np.float64)


def _probe_inverse(
    settings: SweepSettings, trajectory: _AliasTrajectory, band: tuple[float, float]
) -> FloatArray:
    """Inverse filter of the folded trajectory, unit in-band magnitude.

    The energy density of the folded chirp is proportional to ``1/(fs - g)``,
    i.e. to ``1/(k*f(t))``, so the time-reversed reference is weighted with
    ``exp(t/L)`` exactly like the linear inverse filter, and the result is
    scaled by the median of ``|R(f) I(f)|`` over the analysis band.
    """
    reference = _harmonic_reference(settings, trajectory)
    t = sweep_time_axis(settings)[trajectory.start : trajectory.stop]
    inverse = reference[::-1] * np.exp(t / settings.sweep_rate)
    n = reference.shape[0]
    nfft = int(sfft.next_fast_len(n, real=True))
    freqs = np.fft.rfftfreq(nfft, 1.0 / settings.sample_rate)
    select = (freqs >= band[0]) & (freqs <= band[1])
    spectra = np.abs(sfft.rfft(reference, nfft) * sfft.rfft(inverse, nfft))
    gain = float(np.median(spectra[select])) if np.any(select) else 0.0
    if not math.isfinite(gain) or gain <= 0.0:
        return np.asarray(inverse, dtype=np.float64)
    return np.asarray(inverse / gain, dtype=np.float64)


def _band_energy(segment: FloatArray, sample_rate: int, band: tuple[float, float]) -> float:
    """In-band energy of a Hann-windowed segment (independent of the FFT length).

    A Hann window is used rather than a flat one because the interfering
    chirps are 30 dB to 60 dB stronger than the products that are looked for,
    and their spectral leakage would otherwise cover the whole band.
    """
    n = segment.shape[0]
    windowed = segment * np.hanning(n)
    nfft = int(sfft.next_fast_len(n, real=True))
    spectrum = sfft.rfft(windowed, nfft)
    freqs = np.fft.rfftfreq(nfft, 1.0 / sample_rate)
    select = (freqs >= band[0]) & (freqs <= band[1])
    return float(np.sum(np.abs(spectrum[select]) ** 2)) / nfft


def _not_measured(order: int, reason: str, band: tuple[float, float] | None) -> AliasedDistortion:
    return AliasedDistortion(
        order=order,
        band_hz=band,
        level_db=None,
        floor_db=None,
        significant=False,
        reason=reason,
    )


def aliased_distortion_levels(
    recording: FloatArray,
    h_full: FloatArray,
    *,
    sample_rate: int,
    settings: SweepSettings,
    excitation_band: ExcitationBand,
    peak_index: int,
    reference_length: int,
    orders: tuple[int, ...] = ALIAS_PROBE_ORDERS,
) -> tuple[AliasedDistortion, ...]:
    """Levels of the folded harmonic products in ``recording`` (dB re linear).

    ``peak_index`` is the direct sound in ``h_full`` and ``reference_length``
    the length of the inverse filter, which together give the position of the
    played sweep in the recording. Each result says whether the product is
    significant; see the module docstring for the method.
    """
    direct_in_recording = peak_index - (reference_length - 1)
    half = round(ALIAS_WINDOW_HALF_S * sample_rate)
    window = 2 * half + 1
    results: list[AliasedDistortion] = []
    for order in orders:
        trajectory = _alias_trajectory(settings, order, excitation_band)
        if trajectory is None:
            results.append(
                _not_measured(
                    order,
                    diag(
                        "harmonic {order} of this sweep does not fold back into the swept range "
                        "at {sample_rate} Hz",
                        order=order,
                        sample_rate=sample_rate,
                    ),
                    None,
                )
            )
            continue
        band, reason = _analysis_band(
            trajectory, settings, excitation_band, window_bins_hz=sample_rate / window
        )
        if band is None:
            assert reason is not None
            results.append(_not_measured(order, reason, (trajectory.low_hz, trajectory.high_hz)))
            continue
        inverse = _probe_inverse(settings, trajectory, band)
        target = direct_in_recording + trajectory.stop - 1
        far = round(ALIAS_FLOOR_FAR_S * sample_rate)
        near = round(ALIAS_FLOOR_NEAR_S * sample_rate)
        lo = target - far - inverse.shape[0] + 1
        hi = target + half + 1
        if lo < 0 or hi > recording.shape[0] or peak_index + half + 1 > h_full.shape[0]:
            results.append(
                _not_measured(order, diag("the probe window lies outside the recording"), band)
            )
            continue
        probe = np.asarray(fftconvolve(recording[lo:hi], inverse), dtype=np.float64)

        def at(centre: int, *, probe: FloatArray = probe, lo: int = lo) -> FloatArray:
            start = centre - half - lo
            return probe[start : start + window]

        linear = _band_energy(h_full[peak_index - half : peak_index + half + 1], sample_rate, band)
        if linear <= 0.0:
            results.append(
                _not_measured(
                    order, diag("the linear response has no energy in the probe band"), band
                )
            )
            continue
        level = _band_energy(at(target), sample_rate, band)
        centres = np.arange(target - far + half, target - near - half, window)
        if centres.shape[0] > ALIAS_FLOOR_MAX_CHUNKS:
            picks = np.linspace(0, centres.shape[0] - 1, ALIAS_FLOOR_MAX_CHUNKS)
            centres = centres[picks.round().astype(int)]
        if centres.shape[0] == 0:
            results.append(
                _not_measured(
                    order, diag("no content before the probe window to compare with"), band
                )
            )
            continue
        floor = max(_band_energy(at(int(c)), sample_rate, band) for c in centres)
        level_db = 10.0 * math.log10(max(level, _TINY) / linear)
        floor_db = 10.0 * math.log10(max(floor, _TINY) / linear)
        detected = level_db >= floor_db + ALIAS_DETECTION_MARGIN_DB
        results.append(
            AliasedDistortion(
                order=order,
                band_hz=band,
                level_db=float(level_db) if detected else None,
                floor_db=float(floor_db),
                significant=detected and level_db >= ALIAS_SIGNIFICANT_DB,
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
