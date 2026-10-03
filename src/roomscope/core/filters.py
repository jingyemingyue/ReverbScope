"""Band filters and fractional-octave smoothing.

Band definition (IEC 61260-1:2014)
----------------------------------
IEC 61260-1:2014 specifies only base-10 filters (foreword item c; base-2
designs are covered by the informative Annex D):

* octave frequency ratio ``G = 10^(3/10)`` (clause 5.2),
* reference frequency ``f_r = 1000 Hz`` (clause 5.3),
* exact mid-band frequencies ``f_m = f_r * G^(x/b)`` when the denominator
  ``b`` of the bandwidth designator ``1/b`` is odd, and
  ``f_m = f_r * G^((2x+1)/(2b))`` when it is even (clause 5.4),
* band-edge frequencies whose geometric mean is ``f_m`` (clause 3.8), here
  ``f_m * G^(-1/(2b))`` and ``f_m * G^(+1/(2b))`` (the clause stating this
  formula was not verified against the standard text),
* bands are labelled by their *nominal* mid-band frequencies (clause 5.5,
  Annex E), e.g. "63 Hz" for ``f_m = 63.096 Hz``.

:func:`iec_band` returns such a band for a nominal frequency.
:func:`fractional_octave_band` returns a band of the same relative width
centred exactly on an arbitrary frequency (used around resonance
candidates). The band-pass filters are Butterworth designs, applied
time-reversed for decay analysis (Jacobsen & Rindel 1987) and as a single
forward pass with the start transient removed for level measurements
(:func:`band_level_samples`); they are *not* certified IEC 61260-1 class-1
filters and RoomScope does not claim standard-compliant band levels. The smoothing helper keeps its own
definition (see :func:`fractional_octave_smooth`).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy.signal import butter, sosfilt

from roomscope.errors import ConfigurationError
from roomscope.models.audio import FloatArray

#: Octave frequency ratio of base-10 filters (IEC 61260-1:2014, 5.2).
OCTAVE_RATIO = 10.0 ** (3.0 / 10.0)
#: Reference frequency (IEC 61260-1:2014, 5.3).
REFERENCE_FREQUENCY_HZ = 1000.0
#: Fraction of a band filter's impulse-response energy that must have arrived
#: before a single-pass band level is measured (:func:`settling_samples`).
LEVEL_SETTLING_ENERGY_FRACTION = 0.999
#: A frequency given to :func:`iec_band` is taken as the nominal label of the
#: nearest exact mid-band frequency when it lies within this relative distance
#: of it (and within a quarter of the band spacing). The nominal values of
#: IEC 61260-1 Annex E differ from the exact ones by about 1 % at most
#: (e.g. 160 Hz vs 158.49 Hz).
NOMINAL_TOLERANCE = 0.02


@dataclass(frozen=True)
class Band:
    #: Mid-band frequency the edges are centred on (geometric mean of the edges).
    center_hz: float
    low_hz: float
    high_hz: float
    #: Nominal mid-band frequency used as the label (``None``: ``center_hz``).
    nominal_hz: float | None = None

    @property
    def bandwidth_hz(self) -> float:
        return self.high_hz - self.low_hz

    @property
    def label_hz(self) -> float:
        return self.nominal_hz if self.nominal_hz is not None else self.center_hz

    @property
    def label(self) -> str:
        value = self.label_hz
        if value >= 1000.0:
            return f"{value / 1000.0:g} kHz"
        return f"{value:g} Hz"


def _check_band_arguments(frequency_hz: float, fraction: int) -> None:
    if not (math.isfinite(frequency_hz) and frequency_hz > 0.0) or fraction <= 0:
        raise ConfigurationError("band centre and fraction must be positive")


def _half_width_ratio(fraction: int) -> float:
    return float(OCTAVE_RATIO ** (1.0 / (2.0 * fraction)))


def exact_mid_band_hz(index: int, fraction: int = 1) -> float:
    """Exact mid-band frequency number ``index`` (``x``) of a ``1/fraction``-octave
    set (IEC 61260-1:2014, 5.4)."""
    if fraction <= 0:
        raise ConfigurationError("fraction must be positive")
    odd = fraction % 2 == 1
    exponent = index / fraction if odd else (2 * index + 1) / (2 * fraction)
    return float(REFERENCE_FREQUENCY_HZ * OCTAVE_RATIO**exponent)


def nearest_band_index(frequency_hz: float, fraction: int = 1) -> int:
    """Index ``x`` of the exact mid-band frequency closest to ``frequency_hz``."""
    _check_band_arguments(frequency_hz, fraction)
    position = fraction * math.log(frequency_hz / REFERENCE_FREQUENCY_HZ) / math.log(OCTAVE_RATIO)
    if fraction % 2 == 0:
        position -= 0.5
    return round(position)


def fractional_octave_band(center_hz: float, fraction: int = 1) -> Band:
    """A ``1/fraction``-octave band (base-10 ratio) centred exactly on ``center_hz``.

    Use :func:`iec_band` for the standard bands identified by a nominal
    frequency; this function is for bands around arbitrary frequencies.
    """
    _check_band_arguments(center_hz, fraction)
    half = _half_width_ratio(fraction)
    return Band(center_hz=center_hz, low_hz=center_hz / half, high_hz=center_hz * half)


def iec_band(nominal_hz: float, fraction: int = 1) -> Band:
    """The IEC 61260-1 base-10 band with nominal mid-band frequency ``nominal_hz``.

    The band is centred on the exact mid-band frequency nearest to
    ``nominal_hz`` and labelled with ``nominal_hz`` (``iec_band(63.0)`` has
    ``center_hz = 63.096``, edges 44.67 and 89.13 Hz, label "63 Hz"). A
    frequency farther than :data:`NOMINAL_TOLERANCE` (or a quarter of the band
    spacing) from every exact mid-band frequency is not a nominal frequency of
    the set; the band is then centred on ``nominal_hz`` itself (a non-standard
    band with the same relative width).
    """
    _check_band_arguments(nominal_hz, fraction)
    exact = exact_mid_band_hz(nearest_band_index(nominal_hz, fraction), fraction)
    tolerance = min(math.log1p(NOMINAL_TOLERANCE), math.log(OCTAVE_RATIO) / (4.0 * fraction))
    centre = exact if abs(math.log(nominal_hz / exact)) <= tolerance else nominal_hz
    half = _half_width_ratio(fraction)
    return Band(
        center_hz=centre, low_hz=centre / half, high_hz=centre * half, nominal_hz=nominal_hz
    )


def band_fits(band: Band, sample_rate: int, max_relative_to_nyquist: float = 0.9) -> bool:
    return band.high_hz < max_relative_to_nyquist * sample_rate / 2.0 and band.low_hz > 0.0


def bandpass_sos(band: Band, sample_rate: int, order: int = 3) -> FloatArray:
    """Butterworth band-pass in second-order sections (``order`` poles per skirt)."""
    if not band_fits(band, sample_rate):
        raise ConfigurationError(
            f"band {band.label} does not fit below the Nyquist frequency at {sample_rate} Hz"
        )
    nyquist = sample_rate / 2.0
    sos = butter(
        order, [band.low_hz / nyquist, band.high_hz / nyquist], btype="bandpass", output="sos"
    )
    return np.asarray(sos, dtype=np.float64)


def apply_bandpass(x: FloatArray, sos: FloatArray, *, time_reversed: bool = True) -> FloatArray:
    """Apply the filter forward, or time-reversed (filter the reversed signal and
    reverse the result) so that the filter's own decay does not lengthen the
    measured decay.

    Time-reversed filtering is anti-causal: output sample ``i`` depends only on
    input samples ``>= i``, and the filter's ringing appears *before* each
    input event (about ``4 / bandwidth`` at -40 dB for the default
    Butterworth band-pass). A signal therefore needs that much lead-in before
    the direct sound for the band's direct-sound energy to be kept.
    """
    if time_reversed:
        return np.asarray(sosfilt(sos, x[::-1])[::-1], dtype=np.float64)
    return np.asarray(sosfilt(sos, x), dtype=np.float64)


#: ``(sample_rate, energy_fraction, max_s, sos.tobytes())`` -> settling length.
_SETTLING_CACHE: dict[tuple[int, float, float, bytes], int] = {}


def settling_samples(
    sos: FloatArray,
    sample_rate: int,
    *,
    energy_fraction: float = LEVEL_SETTLING_ENERGY_FRACTION,
    max_s: float = 4.0,
) -> int:
    """Length of the start transient of a single forward pass of ``sos`` (samples).

    For stationary input the output variance after ``n`` samples is
    ``sigma^2 * sum_{i<n} h_i^2``, so the transient is over once the filter's
    own impulse response has delivered ``energy_fraction`` of its energy. The
    remaining fraction biases a measured level by
    ``10*log10(energy_fraction)`` at most (0.004 dB at the default 0.999).

    The impulse is grown from a short seed until the second half of the
    computed response holds less than ``1 - energy_fraction`` of the energy
    (or ``max_s`` is reached), then the result is cached. The 0.999 crossing
    matches a full ``max_s`` impulse on the octave-band filters RoomScope uses.
    """
    sections = np.asarray(sos, dtype=np.float64)
    key = (sample_rate, float(energy_fraction), float(max_s), sections.tobytes())
    cached = _SETTLING_CACHE.get(key)
    if cached is not None:
        return cached
    max_n = max(16, round(max_s * sample_rate))
    n = max(16, min(max_n, round(0.125 * sample_rate)))
    result = 0
    while True:
        impulse = np.zeros(n, dtype=np.float64)
        impulse[0] = 1.0
        energy = np.cumsum(np.asarray(sosfilt(sections, impulse), dtype=np.float64) ** 2)
        total = float(energy[-1])
        if total <= 0.0:
            result = 0
            break
        half = n // 2
        tail = total - float(energy[half - 1]) if half else total
        if tail <= (1.0 - energy_fraction) * total or n >= max_n:
            result = int(np.searchsorted(energy, energy_fraction * total)) + 1
            break
        n = min(max_n, n * 2)
    _SETTLING_CACHE[key] = result
    return result


def band_level_samples(
    x: FloatArray,
    sos: FloatArray,
    sample_rate: int,
    *,
    min_settled_samples: int = 16,
    energy_fraction: float = LEVEL_SETTLING_ENERGY_FRACTION,
) -> FloatArray | None:
    """``x`` band-pass filtered for a *level* measurement, transient removed.

    A single forward pass is used: the level of a stationary signal does not
    need phase information, and zero-phase (forward-backward) filtering would
    apply ``|H|^2``, putting the nominal band edges at -6.02 dB instead of
    -3.01 dB and narrowing the noise-equivalent bandwidth (white noise then
    reads about 0.6 dB below the ideal band power). The first
    :func:`settling_samples` output samples are discarded.

    Returns ``None`` when fewer than ``min_settled_samples`` samples remain.
    """
    settled = settling_samples(sos, sample_rate, energy_fraction=energy_fraction)
    if x.shape[0] - settled < min_settled_samples:
        return None
    return np.asarray(sosfilt(sos, x)[settled:], dtype=np.float64)


def fractional_octave_smooth(
    frequencies_hz: FloatArray,
    magnitude_db: FloatArray,
    fraction: int,
) -> FloatArray:
    """Power-average ``magnitude_db`` over a +/- 1/(2*fraction)-octave window.

    Works on any ascending frequency grid. At low frequencies where the window
    is narrower than one bin the value is returned unchanged.
    """
    if fraction <= 0:
        return np.asarray(magnitude_db, dtype=np.float64)
    if frequencies_hz.shape != magnitude_db.shape:
        raise ConfigurationError("frequency and magnitude arrays must have the same shape")
    half = 2.0 ** (1.0 / (2.0 * fraction))
    power = 10.0 ** (np.asarray(magnitude_db, dtype=np.float64) / 10.0)
    cumulative = np.concatenate([[0.0], np.cumsum(power)])
    lo = np.searchsorted(frequencies_hz, frequencies_hz / half, side="left")
    hi = np.searchsorted(frequencies_hz, frequencies_hz * half, side="right")
    hi = np.maximum(hi, lo + 1)
    mean_power = (cumulative[hi] - cumulative[lo]) / (hi - lo)
    return np.asarray(10.0 * np.log10(np.maximum(mean_power, 1e-300)), dtype=np.float64)
