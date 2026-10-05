"""Exponential sine sweep (ESS) generation, excitation band and inverse filters.

Method
------
The sweep follows Farina (2000): with ``L = T / ln(f2/f1)`` the signal is

    x(t) = sin( 2*pi*f1*L * (exp(t/L) - 1) ),     0 <= t < T

whose instantaneous frequency ``f(t) = f1 * exp(t/L)`` rises exponentially
from ``f1`` to ``f2``. The analytic inverse filter is the time-reversed sweep
multiplied by an amplitude envelope that falls 6 dB per octave,
``exp(-t/L)``, so that the convolution of sweep and inverse filter is
(approximately) a band-limited Dirac pulse. Harmonic distortion products of
the loudspeaker appear *before* the linear impulse response at
``dt_k = L * ln(k)`` for the k-th harmonic, which is why they can be
separated by simple windowing.

Level normalisation
-------------------
Both inverse filters are scaled so that the *in-band magnitude* of the
sweep convolved with its inverse is 1 (median of ``|X(f) * I(f)|`` over
:func:`normalisation_band_hz`). A perfect loopback therefore has a 0 dB
frequency response at every sample rate and for any sub-sample delay. The
peak value of the resulting pulse is *not* 1: a band-limited pulse peaks at
roughly ``2 * bandwidth / fs`` times its in-band magnitude, and less when the
direct sound falls between two samples.

Excitation band
---------------
Outside the frequency range the sweep actually covered, the deconvolved
response contains only roll-off, leakage and noise.

* From a sweep definition (:func:`excitation_band_hz`): the sweep reaches full
  amplitude at the end of the fade-in and leaves it at the start of the
  fade-out, so ``f_lo = f1 * exp(fade_in_s / L)`` and
  ``f_hi = f2 * exp(-fade_out_s / L)``. Using the full fade lengths is the
  conservative choice (the fades are sin^2/cos^2 ramps that already pass
  -6 dB halfway).
* From reference audio (:func:`estimate_reference_band_hz`): the power
  spectrum of an ESS falls as 1/f, so ``f * |X(f)|^2`` is flat over the swept
  range. It is power-averaged over 1/3 octave; the reference band is the
  contiguous region around its maximum that stays within
  ``REFERENCE_BAND_EDGE_DB`` (3 dB) of the plateau (median over a
  logarithmic frequency grid of the region within ``REFERENCE_BAND_COARSE_DB``
  of the maximum). The -3 dB point of a smoothed step lies at the step, so
  sharp sweep edges are not moved outwards by the smoothing. The estimator
  assumes a logarithmic sweep; for excitation whose ``f * |X|^2`` is not flat
  (e.g. a linear sweep) the band comes out narrower than the real excitation,
  which is the conservative direction.

Spectral inverse (Kirkeby-type regularisation)
---------------------------------------------
For a reference given only as audio, ``H_inv = conj(X) / (|X|^2 + beta(f))``
with a frequency-dependent regularisation that is small inside the band and
large outside it, the Kirkeby-type inverse described for sweeps by Farina
(2007, section 3.1; the original Kirkeby-Nelson paper is not in the verified
literature record, docs/research/literature.md). ReverbScope's choice of shape:
``beta(f) = P_ref(f) * 10^(b(f)/10)`` where ``P_ref(f) = C / f`` is the pink
trend of the reference (``C`` its plateau level) and ``b(f)`` is
``SPECTRAL_REG_IN_BAND_DB`` inside the band and ``SPECTRAL_REG_OUT_OF_BAND_DB``
outside the reference band, with sin^2 transitions (in log frequency) that
occupy the outermost ``SPECTRAL_REG_TRANSITION_OCTAVES`` inside the reference
band. The excitation band reported for this inverse is the reference band
without those transitions, i.e. the range where the inverse is exact. A
constant ``beta`` would boost the inverse wherever ``|X|^2`` crosses it (just
below ``f1`` and above ``f2``), amplifying subsonic rumble and HF noise and
producing a long deterministic tail.

Everything here is an independent implementation from the published
equations (see docs/MEASUREMENT_METHODOLOGY.md); no third-party code was used.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy import fft as sfft
from scipy.signal import fftconvolve

from reverbscope.core.filters import fractional_octave_smooth
from reverbscope.errors import ConfigurationError
from reverbscope.i18n import _
from reverbscope.models.audio import FloatArray
from reverbscope.models.configuration import SweepSettings

#: Samples of a reference signal below this level (dB re its peak magnitude)
#: at the start and the end are treated as silence and trimmed.
REFERENCE_SILENCE_THRESHOLD_DB = -60.0
#: Fractional-octave smoothing of ``f * |X|^2`` for the band estimate (1/3 octave).
REFERENCE_BAND_SMOOTHING_FRACTION = 3
#: Region around the maximum used to find the plateau level (dB below the maximum).
REFERENCE_BAND_COARSE_DB = 20.0
#: The reference band ends where the smoothed ``f * |X|^2`` falls this far
#: below the plateau (dB).
REFERENCE_BAND_EDGE_DB = 3.0
#: Regularisation inside the band, dB re the pink trend of the reference.
SPECTRAL_REG_IN_BAND_DB = -20.0
#: Regularisation outside the reference band, dB re the pink trend.
SPECTRAL_REG_OUT_OF_BAND_DB = 20.0
#: Width of each regularisation transition (octaves), placed inside the reference band.
SPECTRAL_REG_TRANSITION_OCTAVES = 1.0 / 3.0
_LOG_GRID_POINTS_PER_OCTAVE = 24
_TINY = 1e-300


def _raised_cosine_fades(n: int, fade_in: int, fade_out: int) -> FloatArray:
    """Window that is 1 except for sin^2 ramps of ``fade_in``/``fade_out`` samples."""
    window = np.ones(n, dtype=np.float64)
    if fade_in > 0:
        k = np.arange(fade_in, dtype=np.float64)
        window[:fade_in] = np.sin(0.5 * np.pi * k / fade_in) ** 2
    if fade_out > 0:
        k = np.arange(fade_out, dtype=np.float64)
        window[n - fade_out :] = np.cos(0.5 * np.pi * (k + 1) / fade_out) ** 2
    return window


def sweep_time_axis(settings: SweepSettings) -> FloatArray:
    return np.arange(settings.sweep_samples, dtype=np.float64) / settings.sample_rate


def instantaneous_frequency(settings: SweepSettings, t: FloatArray) -> FloatArray:
    """``f(t) = f1 * exp(t / L)`` in Hz."""
    return settings.start_hz * np.exp(t / settings.sweep_rate)


def generate_ess(settings: SweepSettings, *, apply_level: bool = True) -> FloatArray:
    """Return the sweep only (no leading/trailing silence), peak-scaled to ``level_dbfs``."""
    t = sweep_time_axis(settings)
    rate = settings.sweep_rate
    phase = 2.0 * np.pi * settings.start_hz * rate * (np.exp(t / rate) - 1.0)
    x = np.sin(phase)
    fade_in = round(settings.fade_in_s * settings.sample_rate)
    fade_out = round(settings.fade_out_s * settings.sample_rate)
    x *= _raised_cosine_fades(x.shape[0], fade_in, fade_out)
    if apply_level:
        x *= settings.amplitude
    return x


def measurement_signal(settings: SweepSettings) -> FloatArray:
    """Pre-silence + sweep + post-silence, the file that is played through the DAW."""
    pre = round(settings.pre_silence_s * settings.sample_rate)
    post = round(settings.post_silence_s * settings.sample_rate)
    return np.concatenate(
        [np.zeros(pre), generate_ess(settings), np.zeros(post)],
    ).astype(np.float64)


def excitation_band_hz(settings: SweepSettings) -> tuple[float, float]:
    """Frequencies swept at full amplitude: ``(f1*exp(fade_in/L), f2*exp(-fade_out/L))``.

    Because ``fade_in_s + fade_out_s < duration_s`` (enforced by
    :class:`SweepSettings`), the result is never empty.
    """
    rate = settings.sweep_rate
    low = settings.start_hz * math.exp(settings.fade_in_s / rate)
    high = settings.end_hz * math.exp(-settings.fade_out_s / rate)
    return float(low), float(high)


def frequency_at_sweep_time(settings: SweepSettings, t_s: float) -> float:
    """Instantaneous sweep frequency ``f1 * exp(t/L)`` (Hz) at ``t_s`` seconds."""
    return float(settings.start_hz * math.exp(t_s / settings.sweep_rate))


def normalisation_band_hz(low_hz: float, high_hz: float) -> tuple[float, float]:
    """Inner part of an excitation band used for level normalisation.

    ``[2*low, high/2]`` for bands of at least four octaves; for narrower bands
    the central half (in log frequency), so that the band edges (fades,
    Fresnel ripple, regularisation) never influence the normalisation.
    """
    if not (0.0 < low_hz < high_hz):
        raise ConfigurationError("invalid excitation band")
    q = min(2.0, (high_hz / low_hz) ** 0.25)
    return float(low_hz * q), float(high_hz / q)


def _inband_gain(
    freqs: FloatArray,
    reference_spectrum: np.ndarray,
    inverse_spectrum: np.ndarray,
    band: tuple[float, float],
) -> float:
    """Median of ``|X * I|`` over the normalisation band of ``band``."""
    lo, hi = normalisation_band_hz(*band)
    select = (freqs >= lo) & (freqs <= hi)
    if not np.any(select):
        # Band narrower than one bin: use the bin closest to its centre.
        select = np.zeros(freqs.shape[0], dtype=bool)
        select[int(np.argmin(np.abs(freqs - math.sqrt(lo * hi))))] = True
    gain = float(np.median(np.abs(reference_spectrum[select] * inverse_spectrum[select])))
    if not math.isfinite(gain) or gain <= 0.0:
        raise ConfigurationError("inverse filter normalisation failed (no in-band energy)")
    return gain


def inverse_filter(settings: SweepSettings) -> FloatArray:
    """Analytic inverse filter (Farina 2000), normalised to unit in-band gain.

    The filter is scaled so that the *level-scaled* reference sweep convolved
    with it has an in-band magnitude of 1 (see module docstring). A perfect
    loopback therefore yields a 0 dB frequency response, and a gain ``g`` in
    the measurement chain yields ``20*log10(g)`` dB.
    """
    reference = generate_ess(settings)
    unit = generate_ess(settings, apply_level=False)
    t = sweep_time_axis(settings)
    envelope = np.exp(-t / settings.sweep_rate)
    inv = unit[::-1] * envelope
    n = reference.shape[0]
    nfft = int(sfft.next_fast_len(n, real=True))
    freqs = np.fft.rfftfreq(nfft, 1.0 / settings.sample_rate)
    gain = _inband_gain(
        freqs,
        sfft.rfft(reference, nfft),
        sfft.rfft(inv, nfft),
        excitation_band_hz(settings),
    )
    return np.asarray(inv / gain, dtype=np.float64)


def active_region(
    signal: FloatArray, threshold_db: float = REFERENCE_SILENCE_THRESHOLD_DB
) -> tuple[int, int]:
    """``(start, stop)`` of the part of ``signal`` above ``threshold_db`` re its peak.

    Leading and trailing samples whose magnitude stays below the threshold are
    considered silence (e.g. the silences of a ReverbScope test file).
    """
    if signal.ndim != 1 or signal.shape[0] == 0:
        raise ConfigurationError(_("reference signal must be a non-empty mono array"))
    magnitude = np.abs(signal)
    peak = float(np.max(magnitude))
    if not math.isfinite(peak) or peak <= 0.0:
        raise ConfigurationError(_("reference signal is silent"))
    above = np.flatnonzero(magnitude >= peak * 10.0 ** (threshold_db / 20.0))
    return int(above[0]), int(above[-1]) + 1


def _contiguous_around(mask: np.ndarray, index: int) -> tuple[int, int]:
    """Inclusive bounds of the run of ``True`` in ``mask`` that contains ``index``."""
    outside_before = np.flatnonzero(~mask[:index])
    lo = int(outside_before[-1]) + 1 if outside_before.size else 0
    outside_after = np.flatnonzero(~mask[index:])
    hi = index + int(outside_after[0]) - 1 if outside_after.size else mask.shape[0] - 1
    return lo, hi


@dataclass(frozen=True)
class _ReferenceBand:
    low_hz: float
    high_hz: float
    #: Plateau of ``f * |X|^2`` (linear, same FFT scaling as the spectrum).
    plateau: float


def _reference_band_from_power(freqs: FloatArray, power: FloatArray) -> _ReferenceBand:
    """Band estimate from an rfft power spectrum (DC bin excluded by the caller)."""
    weighted_db = 10.0 * np.log10(np.maximum(freqs * power, _TINY))
    smoothed = fractional_octave_smooth(freqs, weighted_db, REFERENCE_BAND_SMOOTHING_FRACTION)
    k = int(np.argmax(smoothed))
    lo, hi = _contiguous_around(smoothed >= smoothed[k] - REFERENCE_BAND_COARSE_DB, k)
    if hi > lo:
        octaves = math.log2(freqs[hi] / freqs[lo])
        grid = np.geomspace(
            freqs[lo], freqs[hi], max(2, int(octaves * _LOG_GRID_POINTS_PER_OCTAVE) + 1)
        )
        plateau_db = float(np.median(np.interp(grid, freqs, smoothed)))
    else:
        plateau_db = float(smoothed[k])
    plateau_db = min(plateau_db, float(smoothed[k]))
    lo, hi = _contiguous_around(smoothed >= plateau_db - REFERENCE_BAND_EDGE_DB, k)
    return _ReferenceBand(
        low_hz=float(freqs[lo]), high_hz=float(freqs[hi]), plateau=10.0 ** (plateau_db / 10.0)
    )


def _reference_spectrum(
    reference: FloatArray, nfft: int, sample_rate: int
) -> tuple[FloatArray, np.ndarray]:
    spectrum = sfft.rfft(reference, nfft)
    freqs = np.fft.rfftfreq(nfft, 1.0 / sample_rate)
    return freqs, spectrum


def estimate_reference_band_hz(reference: FloatArray, sample_rate: int) -> tuple[float, float]:
    """Frequency range covered by a (logarithmic-sweep) reference signal.

    See the module docstring for the method. The result is the -3 dB extent
    of the smoothed pink-weighted spectrum; the band in which the spectral
    inverse is exact is narrower (:func:`design_spectral_inverse`).
    """
    if reference.ndim != 1 or reference.shape[0] < 16:
        raise ConfigurationError(
            _("reference signal must be a mono array with at least 16 samples")
        )
    nfft = int(sfft.next_fast_len(reference.shape[0], real=True))
    freqs, spectrum = _reference_spectrum(reference, nfft, sample_rate)
    power = np.abs(spectrum[1:]) ** 2
    if float(np.max(power)) <= 0.0:
        raise ConfigurationError(_("reference signal is silent"))
    band = _reference_band_from_power(freqs[1:], power)
    return band.low_hz, band.high_hz


@dataclass(frozen=True)
class SpectralInverse:
    """Result of :func:`design_spectral_inverse`."""

    inverse: FloatArray
    #: Range in which the inverse is exact (reference band minus transitions), Hz.
    band_low_hz: float
    band_high_hz: float
    #: -3 dB extent of the reference spectrum (see module docstring), Hz.
    reference_low_hz: float
    reference_high_hz: float


def _regularisation_shape_db(
    freqs: FloatArray, band: tuple[float, float], reference_band: tuple[float, float]
) -> FloatArray:
    """``b(f)`` in dB: in-band value inside ``band``, out-of-band value outside
    ``reference_band``, sin^2 transitions (log frequency) in between."""
    lo, hi = band
    ref_lo, ref_hi = reference_band
    b_in, b_out = SPECTRAL_REG_IN_BAND_DB, SPECTRAL_REG_OUT_OF_BAND_DB
    safe = np.maximum(freqs, _TINY)
    x = np.zeros(freqs.shape[0], dtype=np.float64)
    low_side = safe < lo
    x[low_side] = np.log2(lo / safe[low_side]) / math.log2(lo / ref_lo)
    high_side = safe > hi
    x[high_side] = np.log2(safe[high_side] / hi) / math.log2(ref_hi / hi)
    x = np.clip(x, 0.0, 1.0)
    return np.asarray(b_in + (b_out - b_in) * np.sin(0.5 * np.pi * x) ** 2, dtype=np.float64)


def design_spectral_inverse(reference: FloatArray, sample_rate: int) -> SpectralInverse:
    """Kirkeby-type regularised spectral inverse of an arbitrary reference.

    The inverse has the length of ``reference`` and is aligned like the
    analytic inverse (the linear response of a loopback appears at index
    ``len(reference) - 1`` of the full convolution). It is normalised to unit
    in-band gain. Leading/trailing silence should be removed first
    (:func:`active_region`), otherwise it counts as part of the sweep.
    """
    if reference.ndim != 1 or reference.shape[0] < 16:
        raise ConfigurationError(
            _("reference signal must be a mono array with at least 16 samples")
        )
    if not np.all(np.isfinite(reference)):
        raise ConfigurationError(_("reference signal contains NaN or infinite samples"))
    n = reference.shape[0]
    nfft = int(sfft.next_fast_len(2 * n - 1, real=True))
    freqs, spectrum = _reference_spectrum(reference, nfft, sample_rate)
    power = np.abs(spectrum) ** 2
    if float(np.max(power[1:])) <= 0.0:
        raise ConfigurationError(_("reference signal is silent"))
    ref_band = _reference_band_from_power(freqs[1:], power[1:])
    ratio = 2.0**SPECTRAL_REG_TRANSITION_OCTAVES
    band = (ref_band.low_hz * ratio, ref_band.high_hz / ratio)
    if band[0] >= band[1]:
        raise ConfigurationError(
            _(
                "the reference signal only covers {low_hz:.0f}-{high_hz:.0f} Hz; "
                "that is too narrow for a sweep measurement"
            ).format(low_hz=ref_band.low_hz, high_hz=ref_band.high_hz)
        )
    shape_db = _regularisation_shape_db(freqs, band, (ref_band.low_hz, ref_band.high_hz))
    pink = ref_band.plateau / np.maximum(freqs, freqs[1])
    beta = pink * 10.0 ** (shape_db / 10.0)
    inv = sfft.irfft(np.conj(spectrum) / (power + beta), nfft)
    # The inverse of a causal signal of length n is anti-causal; rotate so that
    # it occupies [0, n) like the analytic inverse filter (time-reversed sweep).
    inv = np.asarray(np.roll(inv, n - 1)[:n], dtype=np.float64)
    gain = _inband_gain(freqs, spectrum, sfft.rfft(inv, nfft), band)
    return SpectralInverse(
        inverse=np.asarray(inv / gain, dtype=np.float64),
        band_low_hz=float(band[0]),
        band_high_hz=float(band[1]),
        reference_low_hz=ref_band.low_hz,
        reference_high_hz=ref_band.high_hz,
    )


def inverse_filter_spectral(reference: FloatArray, sample_rate: int) -> FloatArray:
    """Array-only shortcut for :func:`design_spectral_inverse`."""
    return design_spectral_inverse(reference, sample_rate).inverse


def reference_pulse(settings: SweepSettings) -> FloatArray:
    """Convolution of the reference sweep with its inverse filter (ideal loopback)."""
    return np.asarray(
        fftconvolve(generate_ess(settings), inverse_filter(settings), mode="full"),
        dtype=np.float64,
    )


def harmonic_pre_response_offsets_s(settings: SweepSettings, max_order: int = 5) -> list[float]:
    """Time (s) by which the k-th harmonic response precedes the linear IR."""
    return [settings.sweep_rate * float(np.log(k)) for k in range(2, max_order + 1)]
