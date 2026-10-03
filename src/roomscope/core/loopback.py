"""Optional electrical loopback (reference) channel.

One interface output drives the loudspeaker and is also returned electrically
into a second input. The deconvolved loopback must look like a pulse, not a
room: a channel that decays like a microphone recording is refused and the
analysis continues uncompensated.

Compensation is regularised spectral division (Kirkeby et al. 1998,
MEASUREMENT_METHODOLOGY.md reference [22]; the same shape
``roomscope.core.sweep.design_spectral_inverse`` uses) inside the excitation
band::

    H_room = H_mic · conj(H_lb) / (|H_lb|² + ε(f))

``H_lb`` is a short FIR cut around the loopback peak. Its time origin is the
peak: the samples before the peak are placed at negative time (the end of the
FFT frame) and the frame is zero-padded well beyond ``len(h_mic)``, so the
division is linear, not circular, and removes the interface *response*
without moving the microphone's direct sound (±1 sample; a pure-delay
interface leaves ``h_mic`` unchanged).
The loopback peak is still the electrical time zero: ``path_delay_ms`` is the
delay of the microphone's direct sound relative to it, and
``distance_upper_bound_m = c · path_delay`` is a bound (loudspeaker DSP
latency only adds delay).

Nothing here estimates clock drift: both channels share one converter clock.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy import fft as sfft

from roomscope.core.deconvolution import LocatedImpulseResponse, confidence_label
from roomscope.core.placement import speed_of_sound_m_s
from roomscope.core.sweep import (
    SPECTRAL_REG_TRANSITION_OCTAVES,
    _regularisation_shape_db,
)
from roomscope.i18n import diag
from roomscope.models.audio import FloatArray
from roomscope.models.result import ExcitationBand, LoopbackResult

#: Window of the deconvolved loopback used as the interface FIR (ms).
LOOPBACK_FIR_PRE_MS = 5.0
LOOPBACK_FIR_POST_MS = 15.0
#: 99 % of the energy after the peak must land inside this many milliseconds.
MAX_ELECTRICAL_SETTLE_MS = 10.0
#: The record must reach at least this far past the peak to be checked.
MIN_SETTLE_RECORD_MS = 80.0
#: The noise floor is estimated from the last quarter (at least 100 ms) of
#: the valid deconvolved record, starting no earlier than 200 ms after the
#: peak (median of the squared samples, divided by the median of χ²₁).
NOISE_ESTIMATE_START_MS = 200.0
NOISE_ESTIMATE_FRACTION = 0.25
MIN_NOISE_ESTIMATE_MS = 100.0
#: Frame padding for compensation, in FIR lengths on each side of ``h_mic``,
#: so that the regularised inverse's tails never wrap into the response.
COMPENSATION_PAD_FIR_LENGTHS = 4
#: Late peak (5–80 ms) must sit at least this far below the direct-sound sample.
MIN_LATE_PEAK_DROP_DB = 25.0
LATE_PEAK_START_MS = 5.0
LATE_PEAK_END_MS = 80.0
#: Frequency-response reference string when compensation was applied.
LOOPBACK_FR_REFERENCE = diag("relative dB (0 dB = the interface loopback)")
#: Stated acceptance for a synthetic interface response after compensation
#: (median absolute error over the normalisation band).
COMPENSATION_TOLERANCE_DB = 1.0


@dataclass(frozen=True)
class LoopbackAssessment:
    """Outcome of :func:`assess_loopback` before compensation is applied."""

    accepted: bool
    reason: str | None
    located: LocatedImpulseResponse | None
    fir: FloatArray | None
    settle_ms: float | None
    drop_db: float | None
    notes: tuple[str, ...] = ()
    #: Index of the loopback peak inside ``fir``: the FIR's time origin.
    fir_peak_index: int = 0


def _valid_stop(h_full: FloatArray, end_index: int | None) -> int:
    if end_index is None:
        return int(h_full.shape[0])
    return max(0, min(int(end_index), int(h_full.shape[0])))


def noise_power(
    h_full: FloatArray,
    peak_index: int,
    sample_rate: int,
    *,
    end_index: int | None = None,
) -> float:
    """Noise power per sample of the deconvolved record, far after the peak.

    Taken from the last ``NOISE_ESTIMATE_FRACTION`` (at least
    ``MIN_NOISE_ESTIMATE_MS``) of ``[peak + NOISE_ESTIMATE_START_MS,
    end_index)`` as the median of the squared samples divided by the median of
    a χ²₁ variable (0.4549), i.e. the mean square of Gaussian noise.
    ``end_index`` should be the end of the *valid* record
    (``peak_index + located.valid_length_samples``): past it the linear
    deconvolution only partly overlaps the recording and the noise fades,
    which would bias the estimate low. 0.0 when the region is too short.
    """
    stop = _valid_stop(h_full, end_index)
    first = peak_index + round(NOISE_ESTIMATE_START_MS * sample_rate / 1000.0)
    minimum = round(MIN_NOISE_ESTIMATE_MS * sample_rate / 1000.0)
    if stop - first < minimum:
        return 0.0
    length = max(minimum, round(NOISE_ESTIMATE_FRACTION * (stop - first)))
    region = np.asarray(h_full[stop - length : stop], dtype=np.float64)
    return float(np.median(region**2) / 0.454936423119572)


def energy_settling_ms(
    h_full: FloatArray,
    peak_index: int,
    sample_rate: int,
    *,
    end_index: int | None = None,
) -> float | None:
    """Time after the peak by which 99 % of the energy has arrived (ms).

    The energy runs from the peak to the end of the valid record with the
    noise power (:func:`noise_power`, same ``end_index``) subtracted from
    every sample. A longer post-roll therefore adds noise that is taken out
    again instead of pushing the 99 % point later (#12), while a room's decay
    tail, however weak its first 80 ms, still counts in full. ``None`` when
    the record ends less than ``MIN_SETTLE_RECORD_MS`` after the peak or holds
    no energy above the noise.
    """
    stop = _valid_stop(h_full, end_index)
    if stop - peak_index < round(MIN_SETTLE_RECORD_MS * sample_rate / 1000.0):
        return None
    tail = np.asarray(h_full[peak_index:stop], dtype=np.float64) ** 2
    net = np.cumsum(tail - noise_power(h_full, peak_index, sample_rate, end_index=stop))
    total = float(net[-1])
    if total <= 0.0:
        return None
    idx = int(np.argmax(net >= 0.99 * total))
    return idx / sample_rate * 1000.0


def late_peak_drop_db(h_full: FloatArray, peak_index: int, sample_rate: int) -> float | None:
    """How far (dB) the strongest sample 5–80 ms after the peak sits below it."""
    start = peak_index + round(LATE_PEAK_START_MS * sample_rate / 1000.0)
    stop = peak_index + round(LATE_PEAK_END_MS * sample_rate / 1000.0)
    if stop > h_full.shape[0] or stop <= start:
        return None
    peak = float(np.max(np.abs(h_full[peak_index : peak_index + 1])))
    late = float(np.max(np.abs(h_full[start:stop])))
    if peak <= 0.0:
        return None
    return 20.0 * math.log10(peak / max(late, 1e-300))


def loopback_fir(h_full: FloatArray, peak_index: int, sample_rate: int) -> tuple[FloatArray, int]:
    """Short interface FIR around the loopback peak, copied out of ``h_full``.

    Returns ``(fir, fir_peak_index)``: ``fir[fir_peak_index]`` is the loopback
    peak, i.e. the FIR's time origin. The samples before it (converter
    pre-ringing) belong at negative time; :func:`compensate` places them there.
    """
    start = max(0, peak_index - round(LOOPBACK_FIR_PRE_MS * sample_rate / 1000.0))
    stop = min(
        h_full.shape[0],
        peak_index + round(LOOPBACK_FIR_POST_MS * sample_rate / 1000.0) + 1,
    )
    if stop - start < 16:
        start = max(0, peak_index - 8)
        stop = min(h_full.shape[0], peak_index + 8)
    fir = np.asarray(h_full[start:stop], dtype=np.float64)
    return fir, int(peak_index - start)


def assess_loopback(
    located: LocatedImpulseResponse,
    h_full: FloatArray,
    sample_rate: int,
    *,
    clipped: bool,
) -> LoopbackAssessment:
    """Refuse a loopback that is not an electrical pulse.

    A silent, clipped, low-confidence or room-like channel is rejected so that
    compensation cannot corrupt the microphone path.
    """
    notes: list[str] = []
    if clipped:
        return LoopbackAssessment(
            accepted=False,
            reason=diag("the loopback channel clips; compensation is not applied"),
            located=located,
            fir=None,
            settle_ms=None,
            drop_db=None,
            notes=tuple(notes),
        )
    confidence = confidence_label(located.pre_peak_margin_db)
    if confidence != "high":
        if confidence == "medium":
            reason = diag(
                "the loopback peak does not stand far enough above the content before it "
                "(confidence medium); the channel may be a microphone, not an "
                "electrical return. Compensation is not applied"
            )
        else:
            reason = diag(
                "the loopback peak does not stand far enough above the content before it "
                "(confidence low); the channel may be a microphone, not an "
                "electrical return. Compensation is not applied"
            )
        return LoopbackAssessment(
            accepted=False,
            reason=reason,
            located=located,
            fir=None,
            settle_ms=None,
            drop_db=None,
            notes=tuple(notes),
        )
    valid_end = located.peak_index + located.valid_length_samples
    settle = energy_settling_ms(h_full, located.peak_index, sample_rate, end_index=valid_end)
    drop = late_peak_drop_db(h_full, located.peak_index, sample_rate)
    if settle is None or drop is None:
        return LoopbackAssessment(
            accepted=False,
            reason=diag(
                "the loopback recording is too short after the peak to check that the "
                "return is electrical; compensation is not applied"
            ),
            located=located,
            fir=None,
            settle_ms=settle,
            drop_db=drop,
            notes=tuple(notes),
        )
    if settle > MAX_ELECTRICAL_SETTLE_MS or drop < MIN_LATE_PEAK_DROP_DB:
        return LoopbackAssessment(
            accepted=False,
            reason=diag(
                "the loopback still carries energy {settle_ms:.1f} ms after the peak "
                "(late peak {drop_db:.1f} dB down); that looks like a room, not a cable. "
                "Compensation is not applied",
                settle_ms=settle,
                drop_db=drop,
            ),
            located=located,
            fir=None,
            settle_ms=settle,
            drop_db=drop,
            notes=tuple(notes),
        )
    fir, fir_peak = loopback_fir(h_full, located.peak_index, sample_rate)
    notes.append(
        diag(
            "loopback settled in {settle_ms:.1f} ms (late peak {drop_db:.1f} dB down); "
            "using a {fir_samples}-sample interface FIR around the peak",
            settle_ms=settle,
            drop_db=drop,
            fir_samples=fir.shape[0],
        )
    )
    return LoopbackAssessment(
        accepted=True,
        reason=None,
        located=located,
        fir=fir,
        settle_ms=settle,
        drop_db=drop,
        notes=tuple(notes),
        fir_peak_index=fir_peak,
    )


def _two_sided_frame(fir: FloatArray, fir_peak_index: int, nfft: int) -> FloatArray:
    """Place ``fir`` in an ``nfft`` frame with its peak at index 0.

    ``fir[fir_peak_index:]`` is causal and starts the frame; the samples
    before the peak wrap to the end of the frame, i.e. to negative time.
    """
    if not 0 <= fir_peak_index < fir.shape[0]:
        raise ValueError("fir_peak_index must index into fir")
    frame = np.zeros(nfft, dtype=np.float64)
    causal = fir[fir_peak_index:]
    frame[: causal.shape[0]] = causal
    if fir_peak_index:
        frame[nfft - fir_peak_index :] = fir[:fir_peak_index]
    return frame


def compensate(
    h_mic: FloatArray,
    fir: FloatArray,
    sample_rate: int,
    excitation_band: ExcitationBand,
    *,
    fir_peak_index: int,
) -> FloatArray:
    """Return ``h_mic`` divided by the interface FIR, regularised outside the band.

    ``fir_peak_index`` is the FIR's time origin (see :func:`loopback_fir`):
    dividing by a FIR whose peak is at its origin removes the interface
    response without moving ``h_mic`` in time. The FFT frame is padded by
    ``COMPENSATION_PAD_FIR_LENGTHS`` FIR lengths, so the division is linear.
    """
    pad = COMPENSATION_PAD_FIR_LENGTHS * fir.shape[0]
    nfft = int(sfft.next_fast_len(h_mic.shape[0] + 2 * pad, real=True))
    spec_mic = sfft.rfft(h_mic, nfft)
    spec_lb = sfft.rfft(_two_sided_frame(fir, fir_peak_index, nfft))
    freqs = np.fft.rfftfreq(nfft, 1.0 / sample_rate)
    lo = float(excitation_band.low_hz)
    hi = float(excitation_band.high_hz)
    ratio = 2.0 ** float(SPECTRAL_REG_TRANSITION_OCTAVES)
    ref_lo = max(lo / ratio, 1.0)
    ref_hi = min(hi * ratio, sample_rate / 2.0 - 1.0)
    if ref_lo >= ref_hi:
        ref_lo, ref_hi = lo, hi
    shape_db = _regularisation_shape_db(freqs, (lo, hi), (ref_lo, ref_hi))
    power = np.abs(spec_lb) ** 2
    in_band = (freqs >= lo) & (freqs <= hi)
    scale = float(np.median(power[in_band])) if np.any(in_band) else float(np.median(power[1:]))
    scale = max(scale, 1e-30)
    eps = scale * 10.0 ** (shape_db / 10.0)
    spec_room = spec_mic * np.conj(spec_lb) / (power + eps)
    compensated = np.asarray(sfft.irfft(spec_room, nfft)[: h_mic.shape[0]], dtype=np.float64)
    return compensated


def path_metrics(
    *,
    mic_peak_index: int,
    loopback_peak_index: int,
    sample_rate: int,
    reference_length: int,
    temperature_c: float | None,
) -> tuple[int, float, float]:
    """``(latency_samples, path_delay_ms, distance_upper_bound_m)``.

    ``latency_samples`` is the loopback peak relative to ``len(reference) - 1``:
    where the sweep starts in the loopback recording. That is the interface's
    I/O delay only when the recording started exactly as the sweep did; a
    RoomScope take adds its pre-silence, a DAW take wherever the sweep was
    placed. ``path_delay_ms`` is the microphone peak relative to the loopback
    peak, which needs no such start.
    """
    latency = int(loopback_peak_index - (reference_length - 1))
    path_delay_ms = (mic_peak_index - loopback_peak_index) / sample_rate * 1000.0
    temperature = 20.0 if temperature_c is None else float(temperature_c)
    bound = speed_of_sound_m_s(temperature) * max(path_delay_ms, 0.0) / 1000.0
    return latency, float(path_delay_ms), float(bound)


def make_loopback_result(
    *,
    channel: int | None,
    assessment: LoopbackAssessment,
    sample_rate: int,
    reference_length: int,
    mic_peak_index: int | None,
    temperature_c: float | None,
    compensation_applied: bool,
) -> LoopbackResult:
    """Build the stored :class:`LoopbackResult` from an assessment."""
    located = assessment.located
    latency: int | None = None
    delay_ms: float | None = None
    bound: float | None = None
    hz: FloatArray | None = None
    db: FloatArray | None = None
    notes = list(assessment.notes)
    if located is not None and mic_peak_index is not None:
        latency, delay_ms, bound = path_metrics(
            mic_peak_index=mic_peak_index,
            loopback_peak_index=located.peak_index,
            sample_rate=sample_rate,
            reference_length=reference_length,
            temperature_c=temperature_c,
        )
        if delay_ms < 0.0:
            notes.append(
                diag(
                    "the microphone peak precedes the loopback peak by {lead_ms:.2f} ms; "
                    "the path-delay bound is not reported",
                    lead_ms=-delay_ms,
                )
            )
            bound = None
    if assessment.fir is not None and assessment.fir.shape[0] >= 16:
        nfft = int(sfft.next_fast_len(max(4096, 2 * assessment.fir.shape[0]), real=True))
        spectrum = sfft.rfft(assessment.fir, nfft)
        freqs = np.fft.rfftfreq(nfft, 1.0 / sample_rate)
        mag = 20.0 * np.log10(np.maximum(np.abs(spectrum), 1e-300))
        hz = np.asarray(freqs[1:], dtype=np.float64)
        db = np.asarray(mag[1:], dtype=np.float64)
    return LoopbackResult(
        channel=channel,
        compensation_applied=compensation_applied,
        reason=assessment.reason,
        latency_samples=latency,
        path_delay_ms=delay_ms,
        distance_upper_bound_m=bound,
        interface_response_hz=hz,
        interface_response_db=db,
        notes=tuple(notes),
    )
