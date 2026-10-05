"""Frequency response from the impulse response.

The raw magnitude is the FFT of the (optionally time-windowed) impulse
response and is always kept. Smoothing is a configurable fractional-octave
power average computed *from* the raw curve and stored separately.

Gating and resolution
---------------------
The analysed segment starts ``lead_in_s`` before the *direct sound* and ends
``window_s`` after it. Counting the gate from the direct sound instead of from
the first sample makes it independent of the display pre-delay, and the end
taper can no longer eat into the direct sound: a window shorter than the taper
plus :data:`MIN_DIRECT_SOUND_S` is refused instead of silently returning an
empty or attenuated response.

The lead-in keeps the pre-ringing of the band-limited direct sound, which is
part of its low-frequency content: cutting a few milliseconds before the peak
costs about 1.5 dB at 31.5 Hz on a loopback.

The FFT is zero-padded to a fine bin spacing, which *interpolates* the
spectrum; it does not add resolution. Both numbers are reported:
``bin_spacing_hz`` (the distance between exported points) and
``resolution_hz`` = 1 / analysed duration (the width of the narrowest feature
that can be separated).
"""

from __future__ import annotations

import numpy as np

from reverbscope.core.filters import fractional_octave_smooth
from reverbscope.errors import ConfigurationError
from reverbscope.i18n import _, diag
from reverbscope.models.audio import FloatArray
from reverbscope.models.result import ExcitationBand, FrequencyResponseResult

DEFAULT_FR_REFERENCE = diag("relative dB (0 dB = flat loopback of the reference sweep)")

_EPS = 1e-300

#: A gate must keep at least this much of the impulse response after the
#: direct sound, on top of the end taper.
MIN_DIRECT_SOUND_S = 0.001


def _taper_end(segment: FloatArray, sample_rate: int, taper_ms: float) -> FloatArray:
    """Half-cosine fade over the last ``taper_ms`` so that a hard window edge
    does not add ripple. Returns a copy."""
    out = np.array(segment, dtype=np.float64)
    n_taper = min(out.shape[0], round(taper_ms * sample_rate / 1000.0))
    if n_taper > 1:
        k = np.arange(n_taper, dtype=np.float64)
        out[-n_taper:] *= np.cos(0.5 * np.pi * (k + 1) / n_taper) ** 2
    return out


def frequency_response(
    ir: FloatArray,
    sample_rate: int,
    *,
    direct_index: int = 0,
    window_s: float | None = None,
    smoothing_fraction: int = 6,
    min_resolution_hz: float = 1.0,
    end_taper_ms: float = 5.0,
    excitation_band: ExcitationBand | None = None,
    reference: str | None = None,
) -> FrequencyResponseResult:
    """Magnitude response (dB, relative) of ``ir``.

    ``direct_index`` is the position of the direct sound in ``ir``; everything
    before it is lead-in and is always analysed. ``window_s`` limits the
    analysed part *after* the direct sound (a form of gating); ``None`` uses
    the whole impulse response. The FFT length is chosen so that the bin
    spacing is at most ``min_resolution_hz``.

    Raises :class:`~reverbscope.errors.ConfigurationError` for a window that is
    shorter than its own end taper plus :data:`MIN_DIRECT_SOUND_S`, which
    would attenuate or exclude the direct sound.
    """
    if not 0 <= direct_index < ir.shape[0]:
        raise ConfigurationError("direct_index is outside the impulse response")
    taper_s = end_taper_ms / 1000.0
    if window_s is not None:
        if window_s < taper_s + MIN_DIRECT_SOUND_S:
            raise ConfigurationError(
                _(
                    "the frequency-response window ({window_ms:.1f} ms) is shorter than its "
                    "{taper_ms:g} ms end taper plus {minimum_ms:g} ms: it would attenuate or "
                    "exclude the direct sound. Use a longer window"
                ).format(
                    window_ms=window_s * 1000.0,
                    taper_ms=end_taper_ms,
                    minimum_ms=MIN_DIRECT_SOUND_S * 1000.0,
                )
            )
        stop = min(ir.shape[0], direct_index + max(2, round(window_s * sample_rate)) + 1)
        segment = _taper_end(ir[:stop], sample_rate, end_taper_ms)
    else:
        stop = ir.shape[0]
        segment = np.asarray(ir, dtype=np.float64)
    lead_in_s = direct_index / sample_rate
    window_after_s = (stop - 1 - direct_index) / sample_rate
    duration_s = segment.shape[0] / sample_rate

    n_min = int(np.ceil(sample_rate / min_resolution_hz))
    nfft = 1 << max(segment.shape[0], n_min).bit_length()
    spectrum = np.fft.rfft(segment, nfft)
    freqs = np.fft.rfftfreq(nfft, 1.0 / sample_rate)
    magnitude_db = 20.0 * np.log10(np.maximum(np.abs(spectrum), _EPS))
    # Drop the DC bin: it is meaningless on a logarithmic frequency axis.
    freqs = np.asarray(freqs[1:], dtype=np.float64)
    magnitude_db = np.asarray(magnitude_db[1:], dtype=np.float64)
    smoothed: FloatArray | None = None
    if smoothing_fraction > 0:
        smoothed = fractional_octave_smooth(freqs, magnitude_db, smoothing_fraction)
    return FrequencyResponseResult(
        frequencies_hz=freqs,
        magnitude_db_raw=magnitude_db,
        magnitude_db_smoothed=smoothed,
        smoothing_fraction=smoothing_fraction,
        window_s=float(window_after_s),
        lead_in_s=float(lead_in_s),
        resolution_hz=float(1.0 / duration_s) if duration_s > 0.0 else float("inf"),
        bin_spacing_hz=float(sample_rate / nfft),
        gated=window_s is not None,
        excitation_band=excitation_band,
        reference=DEFAULT_FR_REFERENCE if reference is None else reference,
    )
