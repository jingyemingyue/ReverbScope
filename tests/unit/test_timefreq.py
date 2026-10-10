"""Spectrogram and waterfall display data (display/timefreq.py, GUI_2 §5.3)."""

from __future__ import annotations

import json
import string
import time
from typing import Any

import numpy as np
import pytest

from reverbscope.core.pipeline import Reference, analyze, synthetic_recording
from reverbscope.display import DisplayDataError
from reverbscope.display.timefreq import (
    SpectrogramParams,
    TimeFrequencyParamError,
    TimeFrequencyResult,
    TransformCancelledError,
    WaterfallParams,
    cumulative_spectral_decay,
    spectrogram,
)
from reverbscope.models.audio import FloatArray
from reverbscope.models.configuration import SweepSettings
from tests.conftest import make_rir

SR = 48000
T60 = 0.5
PRE = 240  # 5 ms of silence before the direct sound


def decaying_mode(
    freq_hz: float = 1000.0, t60_s: float = T60, length_s: float = 1.5, pre: int = PRE
) -> FloatArray:
    """One room mode: a sine whose energy falls 60 dB in ``t60_s``."""
    t = np.arange(int(length_s * SR)) / SR
    mode = np.sin(2 * np.pi * freq_hz * t) * np.exp(-6.91 * t / t60_s)
    return np.concatenate([np.zeros(pre), mode])


def tone(freq_hz: float, length_s: float = 0.5) -> FloatArray:
    return np.sin(2 * np.pi * freq_hz * np.arange(int(length_s * SR)) / SR)


def placeholders(template: str) -> set[str]:
    return {name for _, name, _, _ in string.Formatter().parse(template) if name}


def nearest(freqs: FloatArray, f: float) -> int:
    return int(np.argmin(np.abs(freqs - f)))


# ---------------------------------------------------------------- parameters


@pytest.mark.parametrize(
    "kwargs",
    [
        {"window_ms": 0.0},
        {"window_ms": -5.0},
        {"window_ms": float("nan")},
        {"hop_ms": 0.0},
        {"hop_ms": 30.0},
        {"freq_range_hz": (0.0, None)},
        {"freq_range_hz": (1000.0, 500.0)},
        {"freq_range_hz": (20.0, float("inf"))},
        {"time_range_ms": (10.0, 5.0)},
        {"time_range_ms": (float("-inf"), None)},
        {"max_duration_ms": 0.0},
        {"points_per_octave": 0},
        {"points_per_octave": 97},
        {"normalization": "loudest"},
        {"floor_db": 0.0},
    ],
)
def test_spectrogram_params_validate(kwargs: dict[str, Any]) -> None:
    with pytest.raises(TimeFrequencyParamError) as info:
        SpectrogramParams(**kwargs)
    assert isinstance(info.value, DisplayDataError)
    assert info.value.text()


@pytest.mark.parametrize(
    "kwargs",
    [
        {"window_ms": 0.0},
        {"rise_ms": -1.0},
        {"rise_ms": 250.0},
        {"taper_percent": 101.0},
        {"taper_percent": -1.0},
        {"step_ms": 0.0},
        {"slices": 0},
        {"freq_range_hz": (-1.0, None)},
        {"points_per_octave": 200},
        {"smoothing": -1},
        {"smoothing": 97},
        {"floor_db": 3.0},
        {"start_ms": float("nan")},
    ],
)
def test_waterfall_params_validate(kwargs: dict[str, Any]) -> None:
    with pytest.raises(TimeFrequencyParamError) as info:
        WaterfallParams(**kwargs)
    assert info.value.text()


def test_default_params_are_valid_and_frozen() -> None:
    params = SpectrogramParams()
    with pytest.raises(AttributeError):
        params.window_ms = 5.0  # type: ignore[misc]
    assert WaterfallParams().slices == 30


def test_fmax_above_nyquist_and_window_too_short_are_refused() -> None:
    ir = decaying_mode()
    with pytest.raises(DisplayDataError, match="Nyquist"):
        spectrogram(ir, SR, PRE, SpectrogramParams(freq_range_hz=(20.0, 30000.0)))
    with pytest.raises(DisplayDataError, match="Nyquist"):
        cumulative_spectral_decay(ir, SR, PRE, WaterfallParams(freq_range_hz=(20.0, 30000.0)))
    with pytest.raises(TimeFrequencyParamError, match="4 samples"):
        spectrogram(ir, SR, PRE, SpectrogramParams(window_ms=0.05, hop_ms=0.01))


def test_a_range_without_a_grid_point_is_refused() -> None:
    params = SpectrogramParams(freq_range_hz=(1001.0, 1002.0), points_per_octave=1)
    with pytest.raises(TimeFrequencyParamError, match="No grid frequency"):
        spectrogram(decaying_mode(), SR, PRE, params)


# ---------------------------------------------------------------- grid and axes


@pytest.mark.parametrize("n", [1, 3, 12, 48, 96])
def test_grid_is_anchored_at_1_khz(n: int) -> None:
    result = spectrogram(decaying_mode(), SR, PRE, SpectrogramParams(points_per_octave=n))
    freqs = result.freqs_hz
    assert 1000.0 in freqs.tolist()
    np.testing.assert_allclose(freqs[1:] / freqs[:-1], 2.0 ** (1.0 / n), rtol=1e-12)
    assert freqs[0] >= 20.0 and freqs[-1] <= SR / 2
    assert freqs[0] / 2 ** (1 / n) < 20.0  # nothing in range was left out
    k = np.log2(freqs / 1000.0) * n
    np.testing.assert_allclose(k, np.round(k), atol=1e-9)


def test_spectrogram_shape_and_zero_is_a_frame_centre() -> None:
    result = spectrogram(decaying_mode(), SR, PRE)
    assert result.kind == "spectrogram"
    assert result.levels_db.shape == (result.times_ms.size, result.freqs_hz.size)
    assert 0.0 in result.times_ms.tolist()
    np.testing.assert_allclose(np.diff(result.times_ms), 2.0)
    assert result.times_ms[0] >= -5.0
    assert result.times_ms[-1] <= 1000.0  # capped by max_duration_ms


def test_spectrogram_time_range_is_respected() -> None:
    params = SpectrogramParams(time_range_ms=(10.0, 50.0), hop_ms=5.0)
    result = spectrogram(decaying_mode(), SR, PRE, params)
    np.testing.assert_allclose(result.times_ms, np.arange(10.0, 50.01, 5.0))


def test_frames_without_half_a_window_of_data_are_dropped_and_noted() -> None:
    ir = decaying_mode(length_s=0.1, pre=0)
    result = spectrogram(ir, SR, 0, SpectrogramParams(time_range_ms=(-20.0, None)))
    # Half of a 20 ms window (10 ms) must hold data: the first centre is the
    # first sample; the ten centres from -20 ms to -2 ms are dropped.
    assert result.times_ms[0] == 0.0
    assert result.times_ms[-1] == pytest.approx(98.0)
    dropped = [p for t, p in result.notes if "dropped" in t]
    assert dropped and dropped[0]["dropped"] == 10


def test_waterfall_shape_and_slice_starts() -> None:
    params = WaterfallParams(start_ms=5.0, step_ms=20.0, slices=10)
    result = cumulative_spectral_decay(decaying_mode(), SR, PRE, params)
    assert result.kind == "waterfall"
    assert result.levels_db.shape == (10, result.freqs_hz.size)
    np.testing.assert_allclose(result.times_ms, 5.0 + 20.0 * np.arange(10), atol=1000 / SR)
    assert result.unit == "dB re first slice peak"


def test_slices_starting_after_the_end_are_dropped_and_noted() -> None:
    ir = decaying_mode(length_s=0.1)
    result = cumulative_spectral_decay(ir, SR, PRE, WaterfallParams(step_ms=10.0, slices=30))
    assert result.times_ms.size == 10
    notes = dict(result.notes)
    assert any("dropped" in t for t in notes)


# ---------------------------------------------------------------- bad input


@pytest.mark.parametrize("transform", [spectrogram, cumulative_spectral_decay])
@pytest.mark.parametrize(
    ("samples", "index"),
    [
        (np.zeros(0), 0),
        (np.array([0.0, np.nan, 1.0] * 1000), 0),
        (np.array([0.0, np.inf, 1.0] * 1000), 0),
        (np.ones(3000), 3000),
        (np.ones(3000), -1),
        (np.ones((3000, 2)), 0),
    ],
)
def test_bad_input_raises_a_translatable_error(
    transform: Any, samples: FloatArray, index: int
) -> None:
    with pytest.raises(DisplayDataError) as info:
        transform(samples, SR, index)
    assert info.value.text()
    assert not isinstance(info.value, TimeFrequencyParamError)


@pytest.mark.parametrize("transform", [spectrogram, cumulative_spectral_decay])
def test_bad_sample_rate_is_refused(transform: Any) -> None:
    with pytest.raises(DisplayDataError, match="sample rate"):
        transform(decaying_mode(), 0, PRE)


def test_too_short_for_one_frame_or_slice() -> None:
    with pytest.raises(DisplayDataError, match="too short") as info:
        spectrogram(np.ones(100), SR, 0, SpectrogramParams(time_range_ms=(50.0, 60.0)))
    assert info.value.text()
    with pytest.raises(DisplayDataError, match="first waterfall slice") as info2:
        cumulative_spectral_decay(np.ones(100), SR, 0, WaterfallParams(start_ms=50.0))
    assert info2.value.text()


def test_errors_are_shown_translated() -> None:
    from reverbscope.i18n import activate

    activate("zh_CN")
    try:
        with pytest.raises(DisplayDataError) as info:
            spectrogram(np.zeros(0), SR, 0)
        assert info.value.text()
    finally:
        activate("en")


# ---------------------------------------------------------------- cancellation


@pytest.mark.parametrize("transform", [spectrogram, cumulative_spectral_decay])
def test_cancellation_raises(transform: Any) -> None:
    with pytest.raises(TransformCancelledError):
        transform(decaying_mode(), SR, PRE, cancelled=lambda: True)


@pytest.mark.parametrize("transform", [spectrogram, cumulative_spectral_decay])
def test_cancellation_midway_and_polling(transform: Any) -> None:
    calls = []

    def cancelled() -> bool:
        calls.append(1)
        return len(calls) > 2

    with pytest.raises(TransformCancelledError):
        transform(decaying_mode(), SR, PRE, cancelled=cancelled)
    polled: list[int] = []
    transform(decaying_mode(), SR, PRE, cancelled=lambda: polled.append(1) is not None)
    assert len(polled) >= 3


def test_waterfall_polls_once_per_slice() -> None:
    polled: list[int] = []
    cumulative_spectral_decay(
        decaying_mode(), SR, PRE, cancelled=lambda: polled.append(1) is not None
    )
    assert len(polled) >= 30


# ---------------------------------------------------------------- levels


def test_peak_normalisation_puts_the_maximum_at_0_db() -> None:
    result = spectrogram(decaying_mode(), SR, PRE)
    assert result.unit == "dB re peak"
    assert float(np.max(result.levels_db)) == pytest.approx(0.0, abs=1e-9)


def test_direct_normalisation_puts_the_direct_frame_at_0_db() -> None:
    result = spectrogram(decaying_mode(), SR, PRE, SpectrogramParams(normalization="direct"))
    assert result.unit == "dB re direct sound"
    row = result.times_ms.tolist().index(0.0)
    assert float(np.max(result.levels_db[row])) == pytest.approx(0.0, abs=1e-9)


def test_direct_normalisation_works_when_0_ms_is_outside_the_range() -> None:
    params = SpectrogramParams(normalization="direct", time_range_ms=(100.0, 200.0))
    result = spectrogram(decaying_mode(), SR, PRE, params)
    assert float(np.max(result.levels_db)) < -5.0  # the mode has decayed


def test_no_normalisation_is_full_scale() -> None:
    sine = tone(1000.0, 0.5)
    result = spectrogram(sine, SR, 0, SpectrogramParams(normalization="none"))
    assert result.unit == "dB re full scale²"
    assert result.reference_db == 0.0
    row = result.times_ms.tolist().index(100.0)
    assert float(np.max(result.levels_db[row])) == pytest.approx(0.0, abs=0.5)


def test_reference_db_traces_a_level_back_to_full_scale() -> None:
    ir = decaying_mode()
    absolute = spectrogram(ir, SR, PRE, SpectrogramParams(normalization="none", floor_db=-300))
    peak = spectrogram(ir, SR, PRE, SpectrogramParams(floor_db=-300))
    np.testing.assert_allclose(peak.levels_db + peak.reference_db, absolute.levels_db, atol=1e-9)


def test_waterfall_first_slice_peak_is_0_db() -> None:
    result = cumulative_spectral_decay(decaying_mode(), SR, PRE)
    assert float(np.max(result.levels_db[0])) == pytest.approx(0.0, abs=1e-9)


@pytest.mark.parametrize("floor", [-20.0, -45.0])
def test_floor_clipping(floor: float) -> None:
    s = spectrogram(decaying_mode(), SR, PRE, SpectrogramParams(floor_db=floor))
    w = cumulative_spectral_decay(decaying_mode(), SR, PRE, WaterfallParams(floor_db=floor))
    for result in (s, w):
        assert float(np.min(result.levels_db)) == floor
        assert any("display only" in t for t, _ in result.notes)


@pytest.mark.parametrize("freq", [250.0, 1000.0, 4000.0, 8000.0 * 2 ** (5 / 48)])
def test_a_pure_tone_peaks_at_its_grid_frequency(freq: float) -> None:
    sine = tone(freq)
    s = spectrogram(sine, SR, 0, SpectrogramParams(window_ms=40.0))
    row = s.times_ms.tolist().index(200.0)
    assert s.freqs_hz[np.argmax(s.levels_db[row])] == pytest.approx(freq, rel=1e-9)
    w = cumulative_spectral_decay(sine, SR, 0, WaterfallParams(window_ms=100.0, slices=3))
    assert w.freqs_hz[np.argmax(w.levels_db[0])] == pytest.approx(freq, rel=1e-9)


def test_smoothing_is_noted_and_spreads_a_tone() -> None:
    sine = tone(1000.0)
    params = WaterfallParams(window_ms=100.0, slices=3)
    raw = cumulative_spectral_decay(sine, SR, 0, params)
    smooth = cumulative_spectral_decay(
        sine, SR, 0, WaterfallParams(window_ms=100.0, slices=3, smoothing=3)
    )
    i = nearest(raw.freqs_hz, 1000.0 * 2 ** (6 / 48))  # 1/8 octave above the tone
    assert smooth.levels_db[0, i] > raw.levels_db[0, i] + 10.0
    assert any("smoothing" in t for t, _ in smooth.notes)
    assert not any("smoothing" in t for t, _ in raw.notes)


# ---------------------------------------------------------------- physics


def test_waterfall_decays_at_60_over_t60_db_per_second() -> None:
    result = cumulative_spectral_decay(decaying_mode(), SR, PRE)
    level = result.levels_db[:, nearest(result.freqs_hz, 1000.0)]
    slope = np.polyfit(result.times_ms / 1000.0, level, 1)[0]
    assert slope == pytest.approx(-60.0 / T60, rel=0.1)


def test_spectrogram_band_decays_at_60_over_t60_db_per_second() -> None:
    result = spectrogram(decaying_mode(), SR, PRE)
    level = result.levels_db[:, nearest(result.freqs_hz, 1000.0)]
    select = (result.times_ms >= 20.0) & (result.times_ms <= 400.0)
    slope = np.polyfit(result.times_ms[select] / 1000.0, level[select], 1)[0]
    assert slope == pytest.approx(-60.0 / T60, rel=0.1)


# ---------------------------------------------------------------- notes, purity, speed


@pytest.mark.parametrize(
    "result_of",
    [
        lambda ir: spectrogram(ir, SR, PRE),
        lambda ir: spectrogram(ir, SR, PRE, SpectrogramParams(normalization="direct")),
        lambda ir: spectrogram(ir, SR, PRE, SpectrogramParams(normalization="none")),
        lambda ir: cumulative_spectral_decay(ir, SR, PRE, WaterfallParams(smoothing=6)),
        lambda ir: cumulative_spectral_decay(ir[:9600], SR, PRE),
    ],
)
def test_notes_fill_every_placeholder(result_of: Any) -> None:
    result: TimeFrequencyResult = result_of(decaying_mode())
    assert len(result.notes) >= 4
    for template, params in result.notes:
        assert placeholders(template) <= set(params), template
        assert template.format(**params)


def test_notes_say_window_and_unit() -> None:
    result = spectrogram(decaying_mode(), SR, PRE)
    text = " ".join(t.format(**p) for t, p in result.notes)
    assert "Hann window of 20 ms" in text
    assert "hop 2 ms" in text
    assert "dB re the largest value shown" in text
    assert "anchored at 1 kHz" in text


@pytest.mark.parametrize("transform", [spectrogram, cumulative_spectral_decay])
def test_inputs_are_not_mutated(transform: Any) -> None:
    ir = decaying_mode()
    ir.flags.writeable = False  # any in-place write would raise
    copy = ir.copy()
    transform(ir, SR, PRE)
    np.testing.assert_array_equal(ir, copy)


def test_two_seconds_at_48_khz_is_fast() -> None:
    ir = decaying_mode(length_s=2.0)
    started = time.perf_counter()
    spectrogram(ir, SR, PRE)
    cumulative_spectral_decay(ir, SR, PRE)
    assert time.perf_counter() - started < 1.0


def test_analysis_result_is_unchanged(short_sweep: SweepSettings) -> None:
    """§5: display data never changes a stored result."""
    ir = make_rir(short_sweep.sample_rate, rt60_s=0.3, reflections=[(0.018, 0.35)])
    rec = synthetic_recording(short_sweep, ir, noise_rms=1e-5)
    result = analyze(rec, Reference.from_settings(short_sweep))
    before = json.dumps(result.to_dict(include_curves=True), sort_keys=True)
    samples_before = result.impulse_response.samples.copy()
    response = result.impulse_response
    spectrogram(response.samples, response.sample_rate, response.direct_sound_index)
    cumulative_spectral_decay(response.samples, response.sample_rate, response.direct_sound_index)
    assert json.dumps(result.to_dict(include_curves=True), sort_keys=True) == before
    np.testing.assert_array_equal(result.impulse_response.samples, samples_before)
