"""Electrical-loopback validation and regularised compensation."""

from __future__ import annotations

import numpy as np
import pytest
from scipy.signal import fftconvolve

from reverbscope.core.deconvolution import deconvolve, locate_impulse_response
from reverbscope.core.loopback import (
    COMPENSATION_TOLERANCE_DB,
    LOOPBACK_FR_REFERENCE,
    MAX_ELECTRICAL_SETTLE_MS,
    MIN_LATE_PEAK_DROP_DB,
    assess_loopback,
    energy_settling_ms,
    late_peak_drop_db,
)
from reverbscope.core.pipeline import Reference, analyze, synthetic_recording
from reverbscope.core.sweep import inverse_filter, measurement_signal, normalisation_band_hz
from reverbscope.errors import ConfigurationError, SampleRateMismatchError
from reverbscope.models.audio import AudioSignal
from reverbscope.models.configuration import AnalysisSettings, SweepSettings
from reverbscope.models.result import Validity
from tests.conftest import fr_median_db, make_rir


def _pad_to(samples: np.ndarray, n: int) -> np.ndarray:
    if samples.shape[0] >= n:
        return np.asarray(samples[:n], dtype=np.float64)
    return np.pad(np.asarray(samples, dtype=np.float64), (0, n - samples.shape[0]))


def _locate(h: np.ndarray, rec_len: int, sweep: SweepSettings):
    return locate_impulse_response(
        h,
        recording_length=rec_len,
        reference_length=sweep.sweep_samples,
        sample_rate=sweep.sample_rate,
        pre_delay_ms=5.0,
        max_length_s=1.0,
        sweep_rate_s=sweep.sweep_rate,
    )


def test_electrical_loopback_is_accepted(short_sweep: SweepSettings) -> None:
    rec = measurement_signal(short_sweep)
    h = deconvolve(rec, inverse_filter(short_sweep))
    located = _locate(h, rec.shape[0], short_sweep)
    settle = energy_settling_ms(h, located.peak_index, short_sweep.sample_rate)
    drop = late_peak_drop_db(h, located.peak_index, short_sweep.sample_rate)
    assert settle is not None and settle <= MAX_ELECTRICAL_SETTLE_MS
    assert drop is not None and drop >= MIN_LATE_PEAK_DROP_DB
    assessment = assess_loopback(located, h, short_sweep.sample_rate, clipped=False)
    assert assessment.accepted
    assert assessment.fir is not None


def test_room_like_loopback_is_refused(short_sweep: SweepSettings) -> None:
    ir = make_rir(short_sweep.sample_rate, rt60_s=0.4, reflections=[(0.018, 0.35)])
    rec = synthetic_recording(short_sweep, ir, noise_rms=1e-5)
    h = deconvolve(rec.samples, inverse_filter(short_sweep))
    located = _locate(h, rec.n_samples, short_sweep)
    assessment = assess_loopback(located, h, short_sweep.sample_rate, clipped=False)
    assert assessment.accepted is False
    assert assessment.reason is not None
    assert "room" in assessment.reason or "cable" in assessment.reason


def test_clipped_loopback_is_refused(short_sweep: SweepSettings) -> None:
    rec = measurement_signal(short_sweep)
    h = deconvolve(rec, inverse_filter(short_sweep))
    located = _locate(h, rec.shape[0], short_sweep)
    assessment = assess_loopback(located, h, short_sweep.sample_rate, clipped=True)
    assert assessment.accepted is False
    assert assessment.reason is not None
    assert "clip" in assessment.reason


def test_analyze_without_loopback_leaves_slot_empty(short_sweep: SweepSettings) -> None:
    ir = make_rir(short_sweep.sample_rate, rt60_s=0.3, reflections=[(0.018, 0.3)])
    result = analyze(
        synthetic_recording(short_sweep, ir, noise_rms=1e-5),
        Reference.from_settings(short_sweep),
    )
    assert result.impulse_response.loopback is None


def test_stereo_loopback_channel_must_differ_from_mic(short_sweep: SweepSettings) -> None:
    ir = make_rir(short_sweep.sample_rate, rt60_s=0.3)
    mic = synthetic_recording(short_sweep, ir, noise_rms=1e-5).samples
    stereo = np.stack([mic, mic], axis=1)
    rec = AudioSignal(stereo, short_sweep.sample_rate)
    with pytest.raises(ConfigurationError, match="differ"):
        analyze(
            rec,
            Reference.from_settings(short_sweep),
            AnalysisSettings(channel=0, loopback_channel=0),
        )


def test_separate_loopback_sample_rate_must_match(short_sweep: SweepSettings) -> None:
    ir = make_rir(short_sweep.sample_rate, rt60_s=0.3)
    rec = synthetic_recording(short_sweep, ir, noise_rms=1e-5)
    other = AudioSignal(rec.samples, 44100)
    with pytest.raises(SampleRateMismatchError):
        analyze(rec, Reference.from_settings(short_sweep), loopback=other)


def test_compensate_flattens_a_known_interface_fir(short_sweep: SweepSettings) -> None:
    sr = short_sweep.sample_rate
    interface = np.array([1.0, 0.35, 0.12, 0.04], dtype=np.float64)
    room = make_rir(sr, rt60_s=0.35, reflections=[(0.018, 0.3)], diffuse_level=0.01)
    colored = np.asarray(fftconvolve(interface, room), dtype=np.float64)
    mic = synthetic_recording(short_sweep, colored, noise_rms=1e-6)
    lb_ir = np.zeros(int(0.05 * sr), dtype=np.float64)
    lb_ir[: interface.shape[0]] = interface
    lb_raw = synthetic_recording(short_sweep, lb_ir, noise_rms=1e-7)
    loopback = AudioSignal(_pad_to(lb_raw.samples, mic.n_samples), sr)
    dry = analyze(
        synthetic_recording(short_sweep, room, noise_rms=1e-6), Reference.from_settings(short_sweep)
    )
    wet = analyze(mic, Reference.from_settings(short_sweep))
    fixed = analyze(mic, Reference.from_settings(short_sweep), loopback=loopback)
    assert fixed.impulse_response.loopback is not None
    assert fixed.impulse_response.loopback.compensation_applied is True
    assert fixed.frequency_response.reference == LOOPBACK_FR_REFERENCE
    band = dry.impulse_response.excitation_band
    assert band is not None
    lo, hi = normalisation_band_hz(band.low_hz, band.high_hz)

    def median_err(a, b) -> float:
        freqs = a.frequency_response.frequencies_hz
        select = (freqs >= lo) & (freqs <= hi)
        # interpolate b onto a's grid
        from numpy import interp

        b_on_a = interp(
            freqs[select],
            b.frequency_response.frequencies_hz,
            b.frequency_response.magnitude_db_raw,
        )
        return float(np.median(np.abs(a.frequency_response.magnitude_db_raw[select] - b_on_a)))

    assert median_err(fixed, dry) < COMPENSATION_TOLERANCE_DB
    assert median_err(wet, dry) > COMPENSATION_TOLERANCE_DB
    assert abs(fr_median_db(fixed) - fr_median_db(dry)) < COMPENSATION_TOLERANCE_DB


def test_room_used_as_loopback_does_not_corrupt_mic(short_sweep: SweepSettings) -> None:
    ir = make_rir(short_sweep.sample_rate, rt60_s=0.4, reflections=[(0.018, 0.35)])
    rec = synthetic_recording(short_sweep, ir, noise_rms=1e-5)
    result = analyze(rec, Reference.from_settings(short_sweep), loopback=rec)
    assert result.impulse_response.loopback is not None
    assert result.impulse_response.loopback.compensation_applied is False
    assert result.impulse_response.loopback.reason is not None


def test_path_delay_and_tape_bound(short_sweep: SweepSettings) -> None:
    sr = short_sweep.sample_rate
    delay_s = 0.006
    room = make_rir(sr, rt60_s=0.3, reflections=[(0.018, 0.3)], start_delay_s=delay_s)
    mic = synthetic_recording(short_sweep, room, noise_rms=1e-6)
    loopback = AudioSignal(_pad_to(measurement_signal(short_sweep), mic.n_samples), sr)
    result = analyze(
        mic,
        Reference.from_settings(short_sweep),
        AnalysisSettings(placement_distance_m=5.0, placement_mic_height_m=1.2),
        loopback=loopback,
    )
    lb = result.impulse_response.loopback
    assert lb is not None and lb.compensation_applied
    assert lb.path_delay_ms is not None
    assert lb.path_delay_ms == pytest.approx(delay_s * 1000.0, abs=0.4)
    assert lb.distance_upper_bound_m is not None
    assert lb.distance_upper_bound_m < 5.0
    assert result.placement is not None
    assert any("exceeds the loopback path-delay bound" in n for n in result.placement.notes)
    if result.placement.source_height_m.validity is Validity.VALID:
        raise AssertionError("tape longer than the bound must not stay VALID")


def _interface_fir(sr: int, delay_samples: int) -> np.ndarray:
    """A linear-phase converter-like response: windowed-sinc low-pass at 0.4 fs
    (31 taps, so it carries symmetric pre-ringing) plus a pure latency."""
    taps = 31
    n = np.arange(taps) - (taps - 1) / 2
    lowpass = 0.8 * np.sinc(0.8 * n) * np.hanning(taps)
    lowpass /= np.sum(lowpass)
    fir = np.zeros(delay_samples + taps, dtype=np.float64)
    fir[delay_samples:] = lowpass
    return fir


def test_compensation_keeps_the_direct_sound_in_place(short_sweep: SweepSettings) -> None:
    """#12: dividing by the interface FIR must not move the acoustic time origin."""
    sr = short_sweep.sample_rate
    interface = _interface_fir(sr, delay_samples=37)
    room = make_rir(sr, rt60_s=0.35, reflections=[(0.018, 0.3)], diffuse_level=0.01)
    mic = synthetic_recording(short_sweep, np.asarray(fftconvolve(interface, room)), noise_rms=1e-6)
    lb_ir = np.zeros(int(0.05 * sr), dtype=np.float64)
    lb_ir[: interface.shape[0]] = interface
    lb_raw = synthetic_recording(short_sweep, lb_ir, noise_rms=1e-7)
    loopback = AudioSignal(_pad_to(lb_raw.samples, mic.n_samples), sr)
    reference = Reference.from_settings(short_sweep)

    plain = analyze(mic, reference)
    fixed = analyze(mic, reference, loopback=loopback)
    assert fixed.impulse_response.loopback is not None
    assert fixed.impulse_response.loopback.compensation_applied is True
    one_sample = 1.0 / sr + 1e-12
    for field in ("sweep_start_in_recording_s", "first_sweep_start_in_recording_s"):
        before = getattr(plain.impulse_response, field)
        after = getattr(fixed.impulse_response, field)
        assert abs(after - before) <= one_sample, (field, before, after)
    # The reflection keeps its delay relative to the direct sound as well.
    strongest = max(fixed.reflections.reflections, key=lambda r: r.relative_db)
    assert strongest.delay_ms == pytest.approx(18.0, abs=0.2)


def test_compensate_with_a_pure_delay_leaves_the_response_in_place(
    short_sweep: SweepSettings,
) -> None:
    """A FIR that is only a delay (peak at its origin) must not shift ``h_mic``."""
    from reverbscope.core.loopback import compensate, loopback_fir
    from reverbscope.models.result import ExcitationBand

    sr = short_sweep.sample_rate
    room = make_rir(sr, rt60_s=0.3, reflections=[(0.012, 0.4)], diffuse_level=0.01)
    rec = synthetic_recording(short_sweep, room, noise_rms=1e-7)
    h = deconvolve(rec.samples, inverse_filter(short_sweep))
    peak = int(np.argmax(np.abs(h)))
    # A loopback that is the ideal pulse, 240 samples of pre-roll kept in the FIR.
    pulse = deconvolve(measurement_signal(short_sweep), inverse_filter(short_sweep))
    fir, origin = loopback_fir(pulse, int(np.argmax(np.abs(pulse))), sr)
    assert origin == round(5.0 * sr / 1000.0)
    band = ExcitationBand(
        low_hz=short_sweep.start_hz, high_hz=short_sweep.end_hz, source="settings"
    )
    out = compensate(h, fir, sr, band, fir_peak_index=origin)
    assert out.shape == h.shape
    assert int(np.argmax(np.abs(out))) == peak
    # Nothing wraps around: the start of the frame stays more than 80 dB down.
    head = slice(0, peak - round(0.5 * sr))
    assert np.max(np.abs(out[head])) < 1e-4 * np.max(np.abs(out))
    # The old behaviour (origin at the start of the FIR) advanced the response
    # by the FIR pre-roll; keep that failure mode visible.
    shifted = compensate(h, fir, sr, band, fir_peak_index=0)
    assert int(np.argmax(np.abs(shifted))) == peak - origin


def test_settling_time_does_not_depend_on_recording_length() -> None:
    """#12: a legitimate loopback with a modest noise floor is accepted whatever
    the post-roll; the noise is taken out of the energy before the 99 % point
    is found, and it is estimated inside the valid record only."""
    results = {}
    for post in (1.5, 8.0):
        sweep = SweepSettings(
            sample_rate=48000,
            duration_s=2.0,
            pre_silence_s=1.0,
            post_silence_s=post,
            level_dbfs=-12.0,
        )
        clean = measurement_signal(sweep)
        rec = clean + np.random.default_rng(1).normal(0.0, 0.02, clean.shape[0])
        h = deconvolve(rec, inverse_filter(sweep))
        located = _locate(h, rec.shape[0], sweep)
        end = located.peak_index + located.valid_length_samples
        settle = energy_settling_ms(h, located.peak_index, sweep.sample_rate, end_index=end)
        assessment = assess_loopback(located, h, sweep.sample_rate, clipped=False)
        assert assessment.accepted, (post, assessment.reason)
        assert settle is not None
        assert assessment.settle_ms == settle
        results[post] = settle
    assert max(results.values()) <= 1.0
    assert abs(results[1.5] - results[8.0]) <= 0.5


@pytest.mark.parametrize(("rt60_s", "diffuse"), [(1.5, 0.002), (4.0, 0.001)])
def test_a_reverberant_near_field_microphone_is_not_taken_for_a_cable(
    rt60_s: float, diffuse: float
) -> None:
    """A close microphone in a live room has a weak first 80 ms but a long,
    energetic tail; the whole valid tail is weighed, so it is refused as in
    0.4.0 (review of #12)."""
    sweep = SweepSettings(
        sample_rate=48000, duration_s=2.0, pre_silence_s=0.5, post_silence_s=3.0, level_dbfs=-12.0
    )
    ir = make_rir(48000, rt60_s=rt60_s, diffuse_level=diffuse, length_s=3.0, seed=3)
    rec = synthetic_recording(sweep, ir, noise_rms=1e-6, seed=9)
    h = deconvolve(rec.samples, inverse_filter(sweep))
    located = _locate(h, rec.n_samples, sweep)
    assessment = assess_loopback(located, h, sweep.sample_rate, clipped=False)
    assert assessment.accepted is False
    assert assessment.settle_ms is not None and assessment.settle_ms > MAX_ELECTRICAL_SETTLE_MS
    assert assessment.reason is not None and "room" in assessment.reason


def test_noise_is_estimated_inside_the_valid_record() -> None:
    """Past the valid record the linear deconvolution fades out; including it
    would bias the noise estimate low (review of #12)."""
    from reverbscope.core.loopback import noise_power

    sweep = SweepSettings(
        sample_rate=48000, duration_s=2.0, pre_silence_s=1.0, post_silence_s=1.5, level_dbfs=-12.0
    )
    clean = measurement_signal(sweep)
    rec = clean + np.random.default_rng(2).normal(0.0, 0.02, clean.shape[0])
    h = deconvolve(rec, inverse_filter(sweep))
    located = _locate(h, rec.shape[0], sweep)
    end = located.peak_index + located.valid_length_samples
    inside = noise_power(h, located.peak_index, sweep.sample_rate, end_index=end)
    everything = noise_power(h, located.peak_index, sweep.sample_rate)
    # The mean square of the valid region just before its end is the truth here.
    truth = float(np.mean(h[end - 24000 : end] ** 2))
    assert inside == pytest.approx(truth, rel=0.1)
    assert everything < 0.5 * truth
