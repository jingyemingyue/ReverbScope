from __future__ import annotations

import numpy as np
import pytest
from scipy.signal import fftconvolve, firwin

from roomscope.core.reflections import detect_early_reflections
from tests.conftest import make_rir


def _detect(ir: np.ndarray, sample_rate: int, direct_index: int):  # type: ignore[no-untyped-def]
    return detect_early_reflections(
        ir,
        sample_rate,
        direct_index,
        min_delay_ms=0.8,
        max_delay_ms=80.0,
        threshold_db=-20.0,
        prominence_db=6.0,
        direct_sound_confidence="high",
    )


def test_discrete_reflections_found_with_delay_and_level(sample_rate: int) -> None:
    ir = make_rir(
        sample_rate,
        rt60_s=0.3,
        reflections=[
            (0.018, 10 ** (-9 / 20)),
            (0.035, 10 ** (-15 / 20)),
            (0.050, 10 ** (-28 / 20)),
        ],
        diffuse_level=0.0,
    )
    res = _detect(ir, sample_rate, 0)
    delays = [r.delay_ms for r in res.reflections]
    levels = [r.relative_db for r in res.reflections]
    assert delays == pytest.approx([18.0, 35.0], abs=0.1)
    assert levels == pytest.approx([-9.0, -15.0], abs=0.5)


def test_reflections_found_in_band_limited_ir_with_diffuse_tail(sample_rate: int) -> None:
    ir = make_rir(
        sample_rate, rt60_s=0.4, reflections=[(0.018, 10 ** (-9 / 20))], diffuse_level=0.01
    )
    # Band-limit like a real 20 Hz - 20 kHz measurement chain.
    lowpass = firwin(255, 18000.0, fs=sample_rate)
    ir = fftconvolve(ir, lowpass, mode="full")
    direct = int(np.argmax(np.abs(ir)))
    res = _detect(ir, sample_rate, direct)
    strong = [r for r in res.reflections if r.relative_db > -12.0]
    assert len(strong) == 1
    assert strong[0].delay_ms == pytest.approx(18.0, abs=0.2)
    assert strong[0].relative_db == pytest.approx(-9.0, abs=1.0)


def test_no_reflections_for_pure_delta(sample_rate: int) -> None:
    ir = np.zeros(sample_rate // 2)
    ir[100] = 1.0
    res = _detect(ir, sample_rate, 100)
    assert res.reflections == ()
    assert res.direct_sound_time_s == pytest.approx(100 / sample_rate)


def test_low_confidence_adds_note(sample_rate: int) -> None:
    ir = np.zeros(sample_rate // 2)
    ir[100] = 1.0
    res = detect_early_reflections(
        ir,
        sample_rate,
        100,
        min_delay_ms=0.8,
        max_delay_ms=80.0,
        threshold_db=-20.0,
        prominence_db=6.0,
        direct_sound_confidence="low",
    )
    assert any("confidence is low" in n for n in res.notes)


def test_truncated_search_window_is_reported(sample_rate: int) -> None:
    """C17: when the impulse response ended before the search window, the
    result looked like 'no reflections found' with no note."""
    ir = make_rir(
        sample_rate,
        rt60_s=0.3,
        length_s=0.025,
        reflections=[(0.018, 10 ** (-9 / 20))],
        diffuse_level=0.0,
    )
    res = _detect(ir, sample_rate, 0)
    assert res.window_ms == (0.8, 80.0)
    assert res.analysed_window_ms is not None
    assert res.analysed_window_ms[1] == pytest.approx(25.0, abs=0.1)
    assert res.window_truncated
    assert any("only that part" in n for n in res.notes)
    # What is inside the shortened window is still found.
    assert [r.delay_ms for r in res.reflections] == pytest.approx([18.0], abs=0.1)


def test_full_window_is_not_reported_as_truncated(sample_rate: int) -> None:
    ir = make_rir(sample_rate, rt60_s=0.3, length_s=0.5, diffuse_level=0.01)
    res = _detect(ir, sample_rate, 0)
    assert res.analysed_window_ms == pytest.approx((0.8, 80.0))
    assert not res.window_truncated
    assert not any("only that part" in n for n in res.notes)


@pytest.mark.parametrize("delay_ms", [5.0, 80.0])
@pytest.mark.parametrize("sample_rate", [44100, 48000, 96000])
@pytest.mark.parametrize("hold_ms", [0.0, 0.1])
def test_reflection_at_a_search_boundary_is_found(
    sample_rate: int, delay_ms: float, hold_ms: float
) -> None:
    """Cropping before peak detection must not remove a real peak's neighbour."""
    direct = round(0.010 * sample_rate)
    ir = np.zeros(round(0.15 * sample_rate))
    ir[direct] = 1.0
    ir[direct + round(delay_ms * sample_rate / 1000.0)] = 0.3
    result = detect_early_reflections(
        ir,
        sample_rate,
        direct,
        min_delay_ms=5.0,
        max_delay_ms=80.0,
        threshold_db=-20.0,
        prominence_db=6.0,
        direct_sound_confidence="high",
        hold_ms=hold_ms,
    )
    assert [r.delay_ms for r in result.reflections] == pytest.approx([delay_ms], abs=0.1)


def test_peaks_outside_the_window_are_not_reported(sample_rate: int) -> None:
    direct = round(0.010 * sample_rate)
    ir = np.zeros(round(0.15 * sample_rate))
    ir[direct] = 1.0
    for delay_ms, amplitude in [(4.0, 0.5), (5.0, 0.3), (80.0, 0.3), (81.0, 0.5)]:
        ir[direct + round(delay_ms * sample_rate / 1000.0)] = amplitude
    result = detect_early_reflections(
        ir,
        sample_rate,
        direct,
        min_delay_ms=5.0,
        max_delay_ms=80.0,
        threshold_db=-20.0,
        prominence_db=6.0,
        direct_sound_confidence="high",
    )
    assert [r.delay_ms for r in result.reflections] == pytest.approx([5.0, 80.0], abs=0.1)
