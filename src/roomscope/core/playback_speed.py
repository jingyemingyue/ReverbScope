"""Was the sweep played at the speed it was generated at?

A DAW can change the speed of the test file without anyone noticing:

* **Sample-rate mismatch.** A sweep generated at 48 kHz, placed in a
  44.1 kHz project that does not convert files on import, is played 8.1 %
  slower and 8.1 % lower in pitch (and the other way round). Exporting the
  recording at another rate than the project's is not a cause: the DAW
  converts on export, and the pipeline regenerates the reference sweep at the
  recording's rate.
* **Time-stretching.** Warp (Ableton Live), Flex Time (Logic Pro), Follow
  Tempo (Studio One), elastic audio (Pro Tools), stretch modes (Bitwig,
  FL Studio, REAPER) change the duration and usually keep the pitch.

Either way the deconvolution with the generated sweep no longer collapses the
recording to an impulse, and all the analysis can say is that the direct
sound is not identifiable. This module measures the sweep rate in the
recording itself, so the report can name the cause.

Method: an exponential sine sweep passes frequency ``f`` at
``t(f) = L * ln(f / f1)`` (Farina 2000), a straight line in ``ln f`` of slope
``L``. In the recording's short-time spectrum, the frame in which each
frequency bin is loudest is when the sweep passed it (reverberation only adds
later, weaker energy). A Theil-Sen line through ``(ln f, t)`` of the bins
where that maximum clearly stands out gives the measured ``L'``, and
``speed = L / L'``: 1.0 when the sweep was played as generated,
``played_rate / generated_rate`` for a file played without conversion, and
``1 / stretch`` for a pitch-preserving time-stretch. The estimate is used only
to explain a measurement that already failed, never to correct one.
"""

from __future__ import annotations

import math

import numpy as np
from scipy.signal import stft
from scipy.stats import theilslopes

from roomscope.models.audio import FloatArray
from roomscope.models.configuration import SweepSettings
from roomscope.models.result import KIND_SAMPLE_RATE, KIND_TIME_STRETCH, PlaybackSpeed

#: Sample rates a DAW project or an audio file commonly uses (Hz).
COMMON_SAMPLE_RATES_HZ: tuple[int, ...] = (
    22050,
    24000,
    32000,
    44100,
    48000,
    88200,
    96000,
    176400,
    192000,
)
#: A played rate within this fraction of a common sample rate is named as one.
#: Ratios between common rates differ by at least 8 %; a DAW stretch of a few
#: percent (a tempo 5 % off) must not be named as a sample rate.
SAMPLE_RATE_MATCH_TOLERANCE = 0.025
#: The estimate of a correctly played sweep scatters around 1, with either
#: sign, more for a short sweep in a reverberant room. Worst case over 72
#: synthetic rooms per sweep length (RT60 1-4 s, diffuse level 0.05-0.3,
#: ``tests/conftest.make_rir``): 8.2 % at 0.5 s, 4.5 % at 1 s, 1.9 % at 3 s,
#: 1.4 % at 5 s, 0.9 % at 10 s. :func:`speed_tolerance` stays about 20 % above
#: that; speeds within it of 1 are "as generated".
SPEED_TOLERANCE = 0.0125
SPEED_SPREAD_AT_1_S = 0.055
SPEED_SPREAD_EXPONENT = 0.75
#: A frequency bin is used when its loudest frame is this far (dB) above the
#: bin's median over time: the passing sweep, not noise, made that maximum.
FRAME_DOMINANCE_DB = 20.0
#: Frequency range (Hz) searched for the sweep; low frequencies carry the most
#: room modes and noise, and the top octave may be outside a shifted sweep.
SEARCH_LOW_HZ = 200.0
SEARCH_HIGH_FRACTION_OF_NYQUIST = 0.85
SEARCH_HIGH_HZ = 16000.0
#: The fit needs this many frequency bins spanning this many octaves.
MIN_FRAMES = 12
MIN_OCTAVES = 1.5
#: Points fed to the Theil-Sen fit (its cost is quadratic).
MAX_FIT_FRAMES = 600


def measure_sweep_speed(
    recording: FloatArray, sample_rate: int, settings: SweepSettings
) -> float | None:
    """Generated sweep rate ``L`` over the measured one; ``None`` without a sweep track.

    For every frequency bin the time at which the recording's energy there
    peaks is the moment the sweep passed that frequency: reverberation only
    adds later, weaker energy. The line ``t = t0 + L' * ln f`` through those
    moments gives the measured rate ``L'``.
    """
    mono = np.asarray(recording, dtype=np.float64)
    if mono.ndim != 1 or mono.shape[0] < sample_rate // 2:
        return None
    nperseg = 1 << max(8, round(math.log2(sample_rate * 0.04)))
    hop = max(1, nperseg // 8)
    freqs, times, spec = stft(
        mono,
        fs=sample_rate,
        window="hann",
        nperseg=nperseg,
        noverlap=nperseg - hop,
        boundary=None,
        padded=False,
    )
    if times.shape[0] < 3:
        return None
    high = min(SEARCH_HIGH_HZ, SEARCH_HIGH_FRACTION_OF_NYQUIST * sample_rate / 2.0)
    band = np.flatnonzero((freqs >= SEARCH_LOW_HZ) & (freqs <= high))
    if band.shape[0] < MIN_FRAMES:
        return None
    level = 20.0 * np.log10(np.abs(spec[band, :]) + 1e-300)
    peak_frame = np.argmax(level, axis=1)
    rows = np.arange(level.shape[0])
    peak_db = level[rows, peak_frame]
    dominance = peak_db - np.median(level, axis=1)
    usable = (
        (dominance >= FRAME_DOMINANCE_DB)
        & (peak_db >= float(np.max(peak_db)) - 60.0)
        & (peak_frame > 0)
        & (peak_frame < level.shape[1] - 1)
    )
    picked = np.flatnonzero(usable)
    if picked.shape[0] < MIN_FRAMES:
        return None
    # Parabolic interpolation of the log magnitude around the peak frame.
    j = peak_frame[picked]
    a = level[picked, j - 1]
    b = level[picked, j]
    c = level[picked, j + 1]
    denom = a - 2.0 * b + c
    delta = np.where(np.abs(denom) > 1e-12, 0.5 * (a - c) / denom, 0.0)
    t = times[j] + np.clip(delta, -0.5, 0.5) * (hop / sample_rate)
    log_f = np.log(freqs[band[picked]])
    if (log_f.max() - log_f.min()) / math.log(2.0) < MIN_OCTAVES:
        return None
    if picked.shape[0] > MAX_FIT_FRAMES:
        pick = np.linspace(0, picked.shape[0] - 1, MAX_FIT_FRAMES).round().astype(int)
        t, log_f = t[pick], log_f[pick]
    measured_rate = float(theilslopes(t, log_f)[0])
    if not math.isfinite(measured_rate) or measured_rate <= 0.0:
        return None
    return settings.sweep_rate / measured_rate


def speed_tolerance(duration_s: float) -> float:
    """How far from 1 a measured speed may be and still count as "as generated"."""
    spread = SPEED_SPREAD_AT_1_S / float(max(duration_s, 1e-3)) ** SPEED_SPREAD_EXPONENT
    return max(SPEED_TOLERANCE, float(spread))


def diagnose_playback_speed(
    recording: FloatArray, sample_rate: int, settings: SweepSettings
) -> PlaybackSpeed | None:
    """A :class:`PlaybackSpeed` when the sweep was not played as generated.

    ``settings`` is the sweep as generated (its ``sample_rate`` is the rate of
    the file the user played). ``None`` when the measured speed is within
    :func:`speed_tolerance` of 1 for this sweep length (a short sweep in a
    reverberant room is not named as stretched) or no sweep track can be
    measured.
    """
    speed = measure_sweep_speed(recording, sample_rate, settings)
    if speed is None or abs(speed - 1.0) <= speed_tolerance(settings.duration_s):
        return None
    generated = settings.sample_rate
    played = speed * generated
    nearest = min(COMMON_SAMPLE_RATES_HZ, key=lambda rate: abs(rate - played))
    if nearest != generated and abs(nearest - played) <= SAMPLE_RATE_MATCH_TOLERANCE * nearest:
        return PlaybackSpeed(
            speed_ratio=speed,
            kind=KIND_SAMPLE_RATE,
            generated_rate_hz=generated,
            played_rate_hz=nearest,
        )
    return PlaybackSpeed(speed_ratio=speed, kind=KIND_TIME_STRETCH, generated_rate_hz=generated)
