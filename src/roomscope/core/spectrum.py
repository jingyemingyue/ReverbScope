"""Spectrum of RoomScope's own impulse response.

The frequency-response tab is a gated FFT of a window around the direct
sound. The noise tab is a Welch PSD of a *quiet* recording segment. This
module measures the energy spectrum of the deconvolved IR itself, with the
same Welch / AES17 density scaling already used in :mod:`roomscope.core.noise`
(Welch 1967). It does not talk to an analyser or a hardware RTA.
"""

from __future__ import annotations

import numpy as np
from scipy.signal import welch

from roomscope.models.audio import FloatArray
from roomscope.models.result import SPECTRUM_METHOD, SPECTRUM_SOURCE, SpectrumResult

_EPS = 1e-300


def measure_spectrum(signal: FloatArray, sample_rate: int) -> SpectrumResult:
    """Welch PSD of ``signal`` (typically the impulse response) in AES17 dBFS.

    ``nperseg`` is at most half a second of samples so a 2 Hz bin is available
    when the IR is long enough, matching the noise estimator.
    """
    x = np.asarray(signal, dtype=np.float64)
    if x.ndim > 1:
        x = np.asarray(x[:, 0], dtype=np.float64)
    if x.size < 8:
        return SpectrumResult(
            frequencies_hz=np.zeros(0, dtype=np.float64),
            level_db=np.zeros(0, dtype=np.float64),
            peak_hz=None,
            peak_db=None,
            nperseg=int(x.size),
        )
    nperseg = int(min(x.shape[0], max(8, sample_rate // 2)))
    freqs, psd = welch(x, fs=sample_rate, window="hann", nperseg=nperseg, scaling="density")
    freqs = np.asarray(freqs, dtype=np.float64)
    level_db = np.asarray(10.0 * np.log10(np.maximum(2.0 * psd, _EPS)), dtype=np.float64)
    audible = freqs > 0.0
    peak_hz: float | None = None
    peak_db: float | None = None
    if np.any(audible):
        index = int(np.argmax(level_db[audible]))
        peak_hz = float(freqs[audible][index])
        peak_db = float(level_db[audible][index])
    return SpectrumResult(
        frequencies_hz=freqs,
        level_db=level_db,
        peak_hz=peak_hz,
        peak_db=peak_db,
        nperseg=nperseg,
        method=SPECTRUM_METHOD,
        source=SPECTRUM_SOURCE,
    )
