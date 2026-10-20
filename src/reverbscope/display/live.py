"""Display data for the live input monitor: level meter ballistics and a live spectrum.

Nothing here imports Qt, and nothing here is a measurement. The live monitor
shows what the selected input carries *before* a take, so the level can be
set; no number computed here is stored, exported, or fed to the analysis.
The analysis keeps its own DSP in ``core``; this module only turns a few
milliseconds of input into what the meter and the spectrum draw, like the
display transforms of :mod:`reverbscope.display.curves`.

Levels are dBFS (uncalibrated, C4). Every constant below is ReverbScope's own
display choice, not a standard; the docs repeat them
(docs/design/LIVE_INPUT_MONITOR.md).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field

import numpy as np

from reverbscope.models.audio import FloatArray

#: The lowest level a meter or the spectrum reports (dBFS); silence reads this.
SILENCE_DBFS = -150.0
#: The meter scale: bottom and top (dBFS).
METER_FLOOR_DBFS = -60.0
METER_CEILING_DBFS = 0.0
#: Scale marks drawn on the meter (dBFS).
METER_TICKS_DBFS: tuple[float, ...] = (0.0, -3.0, -6.0, -12.0, -18.0, -24.0, -36.0, -48.0, -60.0)
#: The peak-hold marker stays this long before it falls (s).
PEAK_HOLD_S = 1.5
#: How fast a bar (and a released hold marker) falls (dB per second). The rise
#: is immediate: a peak is drawn in the frame that contains it.
RELEASE_DB_PER_S = 20.0
#: The window of the RMS reading (s): long enough to read steady noise calmly.
RMS_WINDOW_S = 0.3
#: A sample at or above this latches the clip indicator (dBFS). The same
#: -0.1 dBFS line the measurement health uses for a recording at full scale.
CLIP_DBFS = -0.1

#: Analysis lengths offered for the live spectrum (samples).
FFT_SIZES: tuple[int, ...] = (2048, 4096, 8192, 16384)
DEFAULT_FFT_SIZE = 8192
#: Exponential averaging time constants offered (s); 0 is no averaging.
AVERAGING_TIMES_S: tuple[float, ...] = (0.0, 0.1, 0.3, 1.0)
DEFAULT_AVERAGING_S = 0.3
#: Fractional-octave display smoothing offered (1/N octave; 0 is none).
SMOOTHING_FRACTIONS: tuple[int, ...] = (0, 3, 6, 12)
DEFAULT_SMOOTHING = 0
#: Frequency span of the live spectrum (Hz); the top is clipped to Nyquist.
SPECTRUM_MIN_HZ = 20.0
SPECTRUM_MAX_HZ = 20000.0
#: The peak-hold trace falls at this rate after its hold time (dB per second).
SPECTRUM_PEAK_HOLD_S = 1.0
SPECTRUM_PEAK_DECAY_DB_PER_S = 12.0
#: Default dB span of the live spectrum (dBFS).
SPECTRUM_DB_RANGE: tuple[float, float] = (-120.0, 0.0)

NOTE_NAMES = ("C", "C♯", "D", "D♯", "E", "F", "F♯", "G", "G♯", "A", "A♯", "B")


def amplitude_to_dbfs(value: float) -> float:
    """A linear amplitude (1.0 = full scale) in dBFS, floored at :data:`SILENCE_DBFS`."""
    value = abs(float(value))
    if not math.isfinite(value) or value <= 10.0 ** (SILENCE_DBFS / 20.0):
        return SILENCE_DBFS
    return 20.0 * math.log10(value)


def power_to_db(power: FloatArray) -> FloatArray:
    """Mean-square values in dB, floored at :data:`SILENCE_DBFS`."""
    floor = 10.0 ** (SILENCE_DBFS / 10.0)
    return np.asarray(10.0 * np.log10(np.maximum(power, floor)), dtype=np.float64)


def block_peak_dbfs(block: FloatArray) -> list[float]:
    """Sample peak of each column of ``block`` (frames x channels) in dBFS."""
    data = np.asarray(block)
    if data.ndim == 1:
        data = data[:, None]
    if data.shape[0] == 0:
        return [SILENCE_DBFS] * int(data.shape[1])
    # abs().max keeps the dtype of the block (float32 from the ring is enough).
    return [amplitude_to_dbfs(float(v)) for v in np.max(np.abs(data), axis=0)]


def block_rms_dbfs(block: FloatArray) -> list[float]:
    """RMS of each column of ``block`` in dBFS (a full-scale sine reads -3.01)."""
    data = np.asarray(block)
    if data.ndim == 1:
        data = data[:, None]
    if data.shape[0] == 0:
        return [SILENCE_DBFS] * int(data.shape[1])
    # mean of squares in float64 so long windows of float32 do not underflow.
    power = np.mean(np.asarray(data, dtype=np.float64) ** 2, axis=0)
    return [amplitude_to_dbfs(float(v)) for v in np.sqrt(power)]


def meter_fraction(dbfs: float) -> float:
    """Where ``dbfs`` sits on the meter scale, 0 (floor) to 1 (0 dBFS)."""
    span = METER_CEILING_DBFS - METER_FLOOR_DBFS
    return min(1.0, max(0.0, (dbfs - METER_FLOOR_DBFS) / span))


@dataclass
class Ballistics:
    """Instant attack, linear release in dB/s, and a held maximum.

    ``update`` takes the level of the newest block and the time since the
    previous one; ``level`` is what the bar draws, ``hold`` the marker.
    """

    hold_s: float = PEAK_HOLD_S
    release_db_per_s: float = RELEASE_DB_PER_S
    level: float = SILENCE_DBFS
    hold: float = SILENCE_DBFS
    hold_age_s: float = 0.0

    def update(self, dbfs: float, dt_s: float) -> float:
        dt_s = max(0.0, float(dt_s))
        fallen = self.level - self.release_db_per_s * dt_s
        self.level = max(float(dbfs), fallen, SILENCE_DBFS)
        if dbfs >= self.hold:
            self.hold = float(dbfs)
            self.hold_age_s = 0.0
        else:
            self.hold_age_s += dt_s
            if self.hold_age_s > self.hold_s:
                # After the hold time the marker falls at the release rate,
                # never below the bar.
                self.hold = max(self.level, self.hold - self.release_db_per_s * dt_s)
        return self.level

    def reset(self) -> None:
        self.level = SILENCE_DBFS
        self.hold = SILENCE_DBFS
        self.hold_age_s = 0.0


@dataclass
class MeterChannel:
    """One channel of the level meter: peak and RMS ballistics and the clip latch."""

    peak: Ballistics = field(default_factory=Ballistics)
    rms: Ballistics = field(default_factory=Ballistics)
    #: Latched by a sample at or above :data:`CLIP_DBFS`; only :meth:`reset_clip` clears it.
    clipped: bool = False
    #: The newest readings (dBFS), before ballistics: the numeric readout.
    last_peak_dbfs: float = SILENCE_DBFS
    last_rms_dbfs: float = SILENCE_DBFS

    def update(self, peak_dbfs: float, rms_dbfs: float, dt_s: float) -> None:
        self.last_peak_dbfs = float(peak_dbfs)
        self.last_rms_dbfs = float(rms_dbfs)
        self.peak.update(peak_dbfs, dt_s)
        self.rms.update(rms_dbfs, dt_s)
        if peak_dbfs >= CLIP_DBFS:
            self.clipped = True

    def reset_clip(self) -> None:
        self.clipped = False

    def reset(self) -> None:
        self.peak.reset()
        self.rms.reset()
        self.clipped = False
        self.last_peak_dbfs = SILENCE_DBFS
        self.last_rms_dbfs = SILENCE_DBFS


def periodic_hann(size: int) -> FloatArray:
    """The periodic Hann window of ``size`` samples (the FFT convention)."""
    n = np.arange(size, dtype=np.float64)
    return np.asarray(0.5 - 0.5 * np.cos(2.0 * np.pi * n / size), dtype=np.float64)


def amplitude_spectrum_power(frame: FloatArray, window: FloatArray) -> FloatArray:
    """One-sided spectrum of ``frame`` as squared *peak amplitude* (1.0 = full-scale sine).

    The window's coherent gain is divided out, so a sine of amplitude A that
    falls on a bin reads A**2 there (0 dBFS for a full-scale sine). Noise reads
    lower the longer the frame; that is the usual spectrum-analyser display,
    not a power spectral density.
    """
    data = np.asarray(frame, dtype=np.float64)
    spectrum = np.fft.rfft(data * window)
    scale = 2.0 / float(np.sum(window))
    amplitude = np.abs(spectrum) * scale
    amplitude[0] *= 0.5
    if data.shape[0] % 2 == 0:
        amplitude[-1] *= 0.5
    return np.asarray(amplitude * amplitude, dtype=np.float64)


def display_frequencies(sample_rate: int, points: int) -> FloatArray:
    """Log-spaced display frequencies from 20 Hz to 20 kHz or just below Nyquist."""
    top = min(SPECTRUM_MAX_HZ, 0.5 * float(sample_rate) * 0.999)
    points = max(2, int(points))
    return np.asarray(np.geomspace(SPECTRUM_MIN_HZ, top, points), dtype=np.float64)


def log_resample(
    power: FloatArray, sample_rate: int, frequencies: FloatArray, fraction: int = 0
) -> FloatArray:
    """Map a linear-bin spectrum onto log-spaced ``frequencies``.

    With ``fraction`` 0 each display point takes the *largest* bin inside its
    own log cell (half-way to its neighbours), so a tone keeps its height
    however many bins share a pixel; where a cell is narrower than one bin
    the spectrum is interpolated. With ``fraction`` N (3, 6, 12) each point is
    the mean power over 1/N octave centred on it: fractional-octave display
    smoothing, which lowers an isolated tone and keeps the level of noise.
    """
    power = np.asarray(power, dtype=np.float64)
    bins = power.shape[0]
    fft_size = 2 * (bins - 1)
    bin_hz = float(sample_rate) / fft_size
    f = np.asarray(frequencies, dtype=np.float64)
    position = f / bin_hz
    interpolated = np.interp(position, np.arange(bins, dtype=np.float64), power)
    if fraction and fraction > 0:
        half = 2.0 ** (0.5 / float(fraction))
        lo_edge, hi_edge = f / half, f * half
    else:
        edges = np.sqrt(f[:-1] * f[1:])
        lo_edge = np.concatenate(([f[0] * f[0] / edges[0]], edges))
        hi_edge = np.concatenate((edges, [f[-1] * f[-1] / edges[-1]]))
    lo = np.clip(np.ceil(lo_edge / bin_hz).astype(np.int64), 0, bins)
    hi = np.clip(np.floor(hi_edge / bin_hz).astype(np.int64) + 1, 0, bins)
    wide = hi - lo >= 2 if fraction else hi - lo >= 1
    out: FloatArray = np.asarray(interpolated, dtype=np.float64).copy()
    if not np.any(wide):
        return out
    if fraction and fraction > 0:
        cumulative = np.concatenate(([0.0], np.cumsum(power)))
        count = (hi - lo).astype(np.float64)
        with np.errstate(invalid="ignore", divide="ignore"):
            mean = (cumulative[hi] - cumulative[lo]) / np.maximum(count, 1.0)
        out[wide] = mean[wide]
        return out
    # Peak per cell. Adjacent log cells may share a boundary bin, so a plain
    # reduceat partition is not safe; take the max of each [lo, hi) range.
    starts = lo[wide]
    stops = hi[wide]
    peaks = np.empty(starts.shape[0], dtype=np.float64)
    for i, start, stop in zip(range(starts.shape[0]), starts, stops, strict=True):
        peaks[i] = float(power[start:stop].max())
    out[wide] = np.maximum(peaks, interpolated[wide])
    return out


def note_name(hz: float, a4_hz: float = 440.0) -> str:
    """The nearest equal-tempered note (``A4``), or ``""`` outside 16 Hz to 20 kHz."""
    if not math.isfinite(hz) or hz < 16.0 or hz > 20000.0:
        return ""
    midi = round(69.0 + 12.0 * math.log2(hz / a4_hz))
    return f"{NOTE_NAMES[midi % 12]}{midi // 12 - 1}"


@dataclass
class LiveSpectrum:
    """Running spectrum state: averaging, peak hold and display mapping.

    ``update`` takes the newest ``fft_size`` samples of one channel and the time
    since the previous call; ``frequencies``, ``level_db`` and ``peak_db`` are
    what the chart draws.
    """

    sample_rate: int
    fft_size: int = DEFAULT_FFT_SIZE
    averaging_s: float = DEFAULT_AVERAGING_S
    smoothing: int = DEFAULT_SMOOTHING
    points: int = 600
    peak_hold_s: float = SPECTRUM_PEAK_HOLD_S
    peak_decay_db_per_s: float = SPECTRUM_PEAK_DECAY_DB_PER_S
    _window: FloatArray = field(init=False, repr=False)
    _coherent_scale: float = field(default=1.0, init=False, repr=False)
    _average: FloatArray | None = field(default=None, init=False, repr=False)
    _peak: FloatArray | None = field(default=None, init=False, repr=False)
    _peak_age: FloatArray | None = field(default=None, init=False, repr=False)
    frequencies: FloatArray = field(init=False, repr=False)
    level_db: FloatArray = field(init=False, repr=False)
    peak_db: FloatArray = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.configure()

    def configure(
        self,
        *,
        sample_rate: int | None = None,
        fft_size: int | None = None,
        points: int | None = None,
    ) -> None:
        """Change the rate, the analysis length or the display points; restarts averaging."""
        if sample_rate is not None:
            self.sample_rate = int(sample_rate)
        if fft_size is not None:
            self.fft_size = int(fft_size)
        if points is not None:
            self.points = max(16, int(points))
        self._window = periodic_hann(self.fft_size)
        # Coherent gain of the Hann window: a bin-centred sine reads its peak.
        self._coherent_scale = 2.0 / float(np.sum(self._window))
        self.frequencies = display_frequencies(self.sample_rate, self.points)
        self.reset()

    def reset(self) -> None:
        self._average = None
        self._peak = None
        self._peak_age = None
        self.level_db = np.full(self.frequencies.shape, SILENCE_DBFS)
        self.peak_db = self.level_db.copy()

    def reset_peaks(self) -> None:
        self._peak = None
        self._peak_age = None
        self.peak_db = self.level_db.copy()

    @property
    def bin_hz(self) -> float:
        return float(self.sample_rate) / float(self.fft_size)

    def update(self, samples: FloatArray, dt_s: float) -> None:
        data = np.asarray(samples, dtype=np.float64).reshape(-1)
        if data.shape[0] < self.fft_size:
            data = np.concatenate((np.zeros(self.fft_size - data.shape[0]), data))
        else:
            data = data[-self.fft_size :]
        # Inline the one-sided amplitude spectrum with the cached coherent gain
        # so each frame does not re-sum the Hann window.
        spectrum = np.fft.rfft(data * self._window)
        amplitude = np.abs(spectrum) * self._coherent_scale
        amplitude[0] *= 0.5
        if data.shape[0] % 2 == 0:
            amplitude[-1] *= 0.5
        power = amplitude * amplitude
        if self._average is None or self.averaging_s <= 0.0 or self._average.shape != power.shape:
            self._average = power
        else:
            # Exponential averaging of power with time constant averaging_s,
            # independent of the frame rate.
            keep = math.exp(-max(dt_s, 0.0) / self.averaging_s)
            self._average *= keep
            self._average += (1.0 - keep) * power
        shown = log_resample(self._average, self.sample_rate, self.frequencies, self.smoothing)
        self.level_db = power_to_db(shown)
        if self._peak is None or self._peak_age is None or self._peak.shape != self.level_db.shape:
            self._peak = self.level_db.copy()
            self._peak_age = np.zeros_like(self.level_db)
        else:
            higher = self.level_db >= self._peak
            self._peak_age = np.where(higher, 0.0, self._peak_age + max(dt_s, 0.0))
            falling = self._peak_age > self.peak_hold_s
            decayed = np.where(
                falling, self._peak - self.peak_decay_db_per_s * max(dt_s, 0.0), self._peak
            )
            self._peak = np.maximum(self.level_db, decayed)
        self.peak_db = self._peak

    def value_at(self, hz: float) -> float | None:
        """The drawn level at ``hz`` (interpolated in log frequency), or ``None`` outside."""
        f = self.frequencies
        if not math.isfinite(hz) or hz < f[0] or hz > f[-1]:
            return None
        return float(np.interp(math.log10(hz), np.log10(f), self.level_db))


def pink_noise_filter() -> tuple[Sequence[float], Sequence[float]]:
    """IIR coefficients that turn white noise into pink (-3 dB/octave) noise.

    Paul Kellet's economy filter (public-domain music-dsp note), accurate to
    about +-0.5 dB above 10 Hz at 44.1/48 kHz. Used by the synthetic input
    the live monitor shows in Demo mode, tests and screenshots.
    """
    b = (0.049922035, -0.095993537, 0.050612699, -0.004408786)
    a = (1.0, -2.494956002, 2.017265875, -0.522189400)
    return b, a
