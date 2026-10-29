from __future__ import annotations

import numpy as np
import pytest

from reverbscope.core.deconvolution import (
    HarmonicWindow,
    LocatedImpulseResponse,
    confidence_label,
    deconvolve,
    harmonic_distortion_levels,
    locate_impulse_response,
)
from reverbscope.core.pipeline import Reference, analyze
from reverbscope.core.sweep import inverse_filter, measurement_signal, reference_pulse
from reverbscope.errors import AnalysisError, InvalidAudioError
from reverbscope.models.audio import AudioSignal
from reverbscope.models.configuration import SweepSettings
from reverbscope.models.result import ExcitationBand


def test_loopback_gives_unit_impulse_at_pre_delay(short_sweep: SweepSettings) -> None:
    sr = short_sweep.sample_rate
    rec = AudioSignal(measurement_signal(short_sweep), sr)
    result = analyze(rec, Reference.from_settings(short_sweep))
    ir = result.impulse_response
    # Inverse filters are normalised to unit *in-band* gain (0 dB loopback FR),
    # not to a time-domain peak of 1. A band-limited pulse peaks near
    # 2 * bandwidth / fs (~0.82 at 48 kHz for the default sweep).
    loopback_peak = float(np.max(reference_pulse(short_sweep)))
    assert ir.peak_value == pytest.approx(loopback_peak, abs=1e-6)
    assert ir.direct_sound_index == ir.pre_delay_samples == round(5e-3 * sr)
    assert ir.sweep_start_in_recording_s == pytest.approx(short_sweep.pre_silence_s, abs=1e-3)
    assert ir.direct_sound_confidence == "high"
    assert ir.valid_length_s == pytest.approx(short_sweep.post_silence_s, abs=1e-3)


def test_delayed_and_attenuated_loopback(short_sweep: SweepSettings) -> None:
    sr = short_sweep.sample_rate
    delay = int(0.37 * sr)
    sig = np.concatenate([np.zeros(delay), measurement_signal(short_sweep)]) * 0.5
    result = analyze(AudioSignal(sig, sr), Reference.from_settings(short_sweep))
    ir = result.impulse_response
    loopback_peak = float(np.max(reference_pulse(short_sweep)))
    assert ir.peak_value == pytest.approx(0.5 * loopback_peak, abs=1e-6)
    assert ir.sweep_start_in_recording_s == pytest.approx(
        0.37 + short_sweep.pre_silence_s, abs=1e-3
    )


def test_recording_shorter_than_sweep_rejected(short_sweep: SweepSettings) -> None:
    sr = short_sweep.sample_rate
    inv = inverse_filter(short_sweep)
    with pytest.raises(InvalidAudioError):
        deconvolve(np.ones(inv.shape[0] // 2), inv)
    sig = AudioSignal(np.ones(int(1.5 * sr)) * 0.1, sr)
    with pytest.raises(InvalidAudioError):
        analyze(sig, Reference.from_settings(short_sweep))


def test_silent_recording_rejected(short_sweep: SweepSettings) -> None:
    sr = short_sweep.sample_rate
    sig = AudioSignal(np.zeros(short_sweep.total_samples), sr)
    with pytest.raises(InvalidAudioError, match="silent"):
        analyze(sig, Reference.from_settings(short_sweep))


def test_recording_without_tail_rejected(short_sweep: SweepSettings) -> None:
    sr = short_sweep.sample_rate
    no_tail = SweepSettings(**{**short_sweep.to_dict(), "post_silence_s": 0.0})
    sig = AudioSignal(measurement_signal(no_tail), sr)
    with pytest.raises(AnalysisError, match="decay"):
        analyze(sig, Reference.from_settings(short_sweep))


def test_a_recording_that_stops_inside_the_sweep_says_so(short_sweep: SweepSettings) -> None:
    """R3-7: an export that ends 0.5 s before the sweep did was told "the
    direct sound was found at the very end of the recording"."""
    from reverbscope.i18n import activate, localize

    sr = short_sweep.sample_rate
    sweep_end_s = short_sweep.pre_silence_s + short_sweep.duration_s
    cut = AudioSignal(measurement_signal(short_sweep)[: round((sweep_end_s - 0.5) * sr)], sr)
    with pytest.raises(InvalidAudioError) as refused:
        analyze(cut, Reference.from_settings(short_sweep))
    message = str(refused.value)
    assert message == (
        "the recording ends about 0.50 s before the sweep does, so the end of the sweep and "
        "the room decay after it were not recorded. Export the whole take, with the silence "
        "after the sweep"
    )
    activate("zh_CN")
    assert localize(message) == (
        "录音比扫频早约 0.50 s 结束，扫频的末尾及其后的房间衰减都没有录下。"
        "请导出整条录音，包括扫频之后的静音"
    )


def test_locate_reports_truncation_and_margin(short_sweep: SweepSettings) -> None:
    sr = short_sweep.sample_rate
    rec = measurement_signal(short_sweep)
    h = deconvolve(rec, inverse_filter(short_sweep))
    located = locate_impulse_response(
        h,
        recording_length=rec.shape[0],
        reference_length=short_sweep.sweep_samples,
        sample_rate=sr,
        pre_delay_ms=5.0,
        max_length_s=0.5,
    )
    assert located.truncated_by_max_length is True
    assert located.samples.shape[0] == int(0.5 * sr) + round(5e-3 * sr) + 1
    assert located.pre_peak_margin_db > 30.0
    assert confidence_label(located.pre_peak_margin_db) == "high"


def test_confidence_labels() -> None:
    assert confidence_label(25.0) == "high"
    assert confidence_label(15.0) == "medium"
    assert confidence_label(5.0) == "low"
    assert confidence_label(None) == "low"
    assert confidence_label(float("nan")) == "low"


def test_clipping_is_warned(short_sweep: SweepSettings) -> None:
    sr = short_sweep.sample_rate
    sig = np.clip(measurement_signal(short_sweep) * 20.0, -1.0, 1.0)
    result = analyze(AudioSignal(sig, sr), Reference.from_settings(short_sweep))
    assert any("clipping" in w for w in result.warnings)


def test_deconvolve_rejects_non_mono_arrays() -> None:
    with pytest.raises(InvalidAudioError, match="mono arrays"):
        deconvolve(np.ones((10, 2)), np.ones(5))
    with pytest.raises(InvalidAudioError, match="mono arrays"):
        deconvolve(np.ones(10), np.ones((5, 2)))


def test_locate_rejects_an_empty_or_silent_deconvolution() -> None:
    with pytest.raises(AnalysisError, match="empty"):
        locate_impulse_response(
            np.array([]),
            recording_length=10,
            reference_length=5,
            sample_rate=48000,
            pre_delay_ms=5.0,
            max_length_s=1.0,
        )
    with pytest.raises(AnalysisError, match="no usable peak"):
        locate_impulse_response(
            np.zeros(100),
            recording_length=50,
            reference_length=20,
            sample_rate=48000,
            pre_delay_ms=5.0,
            max_length_s=1.0,
        )


def _located_with_harmonics(
    h: np.ndarray,
    peak: int,
    windows: tuple[HarmonicWindow, ...],
) -> LocatedImpulseResponse:
    return LocatedImpulseResponse(
        samples=h[peak : peak + 2000],
        direct_index=0,
        pre_delay_samples=0,
        peak_index=peak,
        peak_value=float(h[peak]),
        valid_length_samples=2000,
        sweep_start_index_in_recording=0,
        sweep_start_raw_index=0,
        pre_peak_margin_db=40.0,
        truncated_by_max_length=False,
        harmonic_windows=windows,
        excluded_windows=(),
    )


def test_harmonic_distortion_names_impossible_windows() -> None:
    sample_rate = 48000
    h = np.zeros(5000)
    h[1000] = 1.0
    ideal = np.zeros(200)
    ideal[100] = 1.0

    above = harmonic_distortion_levels(
        h,
        _located_with_harmonics(
            h,
            1000,
            (HarmonicWindow(order=2, offset_s=0.01, start=100, stop=200, before=50, after=50),),
        ),
        sample_rate=sample_rate,
        excitation_band=ExcitationBand(low_hz=5000.0, high_hz=6000.0, source="settings"),
        ideal_pulse=ideal,
    )
    assert len(above) == 1
    assert above[0].level_db is None
    assert "above the excitation band" in (above[0].reason or "")

    outside = harmonic_distortion_levels(
        h,
        _located_with_harmonics(
            h,
            1000,
            (HarmonicWindow(order=2, offset_s=0.01, start=-10, stop=50, before=50, after=50),),
        ),
        sample_rate=sample_rate,
        excitation_band=ExcitationBand(low_hz=20.0, high_hz=20000.0, source="settings"),
        ideal_pulse=ideal,
    )
    assert "outside the deconvolved signal" in (outside[0].reason or "")

    too_short = harmonic_distortion_levels(
        h,
        _located_with_harmonics(
            h,
            1000,
            (HarmonicWindow(order=2, offset_s=0.01, start=800, stop=810, before=5, after=5),),
        ),
        sample_rate=sample_rate,
        excitation_band=ExcitationBand(low_hz=20.0, high_hz=20000.0, source="settings"),
        ideal_pulse=ideal,
    )
    assert "too short to resolve the common band" in (too_short[0].reason or "")
    assert too_short[0].band_hz is not None
