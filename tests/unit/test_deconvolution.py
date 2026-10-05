from __future__ import annotations

import numpy as np
import pytest

from reverbscope.core.deconvolution import confidence_label, deconvolve, locate_impulse_response
from reverbscope.core.pipeline import Reference, analyze
from reverbscope.core.sweep import inverse_filter, measurement_signal, reference_pulse
from reverbscope.errors import AnalysisError, InvalidAudioError
from reverbscope.models.audio import AudioSignal
from reverbscope.models.configuration import SweepSettings


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


def test_clipping_is_warned(short_sweep: SweepSettings) -> None:
    sr = short_sweep.sample_rate
    sig = np.clip(measurement_signal(short_sweep) * 20.0, -1.0, 1.0)
    result = analyze(AudioSignal(sig, sr), Reference.from_settings(short_sweep))
    assert any("clipping" in w for w in result.warnings)
