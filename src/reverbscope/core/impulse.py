"""Impulse response envelopes.

The direct sound is *not* located here: it is found on the deconvolved signal
together with the sweep passes and the detection margin
(:func:`reverbscope.core.deconvolution.locate_impulse_response`).
"""

from __future__ import annotations

import numpy as np
from scipy.ndimage import uniform_filter1d
from scipy.signal import hilbert

from reverbscope.models.audio import FloatArray

_EPS = 1e-300


def moving_average(x: FloatArray, window_samples: int) -> FloatArray:
    """Centred moving average over ``window_samples``, zeros outside ``x``.

    The result has the length of ``x`` whatever the window. A running sum
    costs O(N) where a direct convolution costs O(N * window): the resonance
    check smooths over two periods of a low-frequency mode, which at 192 kHz
    is ~13 500 samples on a million-sample response, and a convolution took
    over ten seconds per call there.
    """
    if window_samples <= 1:
        return np.asarray(x, dtype=np.float64)
    # Same centring as np.convolve(..., mode="same") for odd and even windows.
    return np.asarray(
        uniform_filter1d(np.asarray(x, dtype=np.float64), window_samples, mode="constant"),
        dtype=np.float64,
    )


def envelope(ir: FloatArray, sample_rate: int, smoothing_ms: float = 0.0) -> FloatArray:
    """Analytic (Hilbert) magnitude envelope, optionally smoothed."""
    analytic = hilbert(ir)
    env = np.abs(analytic)
    window = round(smoothing_ms * sample_rate / 1000.0)
    return moving_average(np.asarray(env, dtype=np.float64), window)


def envelope_db(ir: FloatArray, sample_rate: int, smoothing_ms: float = 0.0) -> FloatArray:
    env = envelope(ir, sample_rate, smoothing_ms)
    return np.asarray(20.0 * np.log10(np.maximum(env, _EPS)), dtype=np.float64)
