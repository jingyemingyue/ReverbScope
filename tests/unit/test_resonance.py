from __future__ import annotations

import numpy as np
import pytest
from scipy.signal import lfilter, sosfilt

from reverbscope.core.filters import OCTAVE_RATIO, bandpass_sos, fractional_octave_band
from reverbscope.core.frequency_response import frequency_response
from reverbscope.core.resonance import (
    SURROUNDINGS_RATIO,
    _decay_20db_s,
    _notch_bands,
    band_decay_20db_s,
    candidate_decays_20db_s,
    detect_potential_resonances,
    filter_ringing_20db_s,
    notch_band,
)
from reverbscope.models.result import ExcitationBand
from tests.conftest import DECAY_CONSTANT, make_rir


def _detect(ir: np.ndarray, sample_rate: int, **kwargs: object):  # type: ignore[no-untyped-def]
    fr = frequency_response(ir, sample_rate, smoothing_fraction=0)
    return detect_potential_resonances(
        ir,
        sample_rate,
        fr,
        max_hz=300.0,
        min_prominence_db=6.0,
        **kwargs,  # type: ignore[arg-type]
    )


def test_ringing_low_frequency_mode_is_a_candidate(sample_rate: int) -> None:
    ir = make_rir(sample_rate, rt60_s=0.3, length_s=2.0, diffuse_level=0.01)
    t = np.arange(ir.shape[0]) / sample_rate
    # A 62 Hz mode ringing with RT60 = 1.5 s
    ir = ir + 0.15 * np.sin(2 * np.pi * 62.0 * t) * np.exp(-DECAY_CONSTANT * t / (2 * 1.5))
    res = _detect(ir, sample_rate)
    assert res.candidates
    best = max(res.candidates, key=lambda c: c.level_above_baseline_db)
    assert best.frequency_hz == pytest.approx(62.0, abs=3.0)
    assert best.narrowband_decay_20db_s is not None
    assert best.filter_ringing_20db_s is not None
    assert best.surroundings_decay_20db_s is not None
    # 20 dB in 0.5 s is what a 1.5 s RT60 gives.
    assert best.narrowband_decay_20db_s == pytest.approx(0.5, rel=0.15)
    assert best.narrowband_decay_20db_s > SURROUNDINGS_RATIO * best.surroundings_decay_20db_s
    assert best.decay_distinguishable is True
    assert any("Candidates only" in n for n in res.notes)


def _peaking(sample_rate: int, f0: float, gain_db: float, q: float) -> np.ndarray:
    """Impulse response of a peaking-EQ boost (a response peak with a short decay)."""
    a_gain = 10 ** (gain_db / 40)
    w = 2 * np.pi * f0 / sample_rate
    alpha = np.sin(w) / (2 * q)
    b = np.array([1 + alpha * a_gain, -2 * np.cos(w), 1 - alpha * a_gain])
    a = np.array([1 + alpha / a_gain, -2 * np.cos(w), 1 - alpha / a_gain])
    impulse = np.zeros(2 * sample_rate)
    impulse[0] = 1.0
    return np.asarray(lfilter(b / a[0], a / a[0], impulse))


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_response_peak_without_a_longer_decay_is_not_distinguishable(
    sample_rate: int, seed: int
) -> None:
    """B6: a +15 dB peak in the direct path of a room whose whole low end
    decays with RT 0.6 s was called 'distinguishable', because the only
    reference was the analysis filter's own ringing (about 20 ms)."""
    n = 2 * sample_rate
    t = np.arange(n) / sample_rate
    tail = (
        0.03
        * np.random.default_rng(seed).normal(0.0, 1.0, n)
        * np.exp(-DECAY_CONSTANT * t / (2 * 0.6))
    )
    ir = np.concatenate([np.zeros(240), _peaking(sample_rate, 100.0, 15.0, 6.0) + tail])
    res = _detect(ir, sample_rate, direct_index=240)
    assert not any(c.decay_distinguishable for c in res.candidates)
    if seed == 1:  # the boost is a candidate, and the old rule would have passed
        candidate = next(c for c in res.candidates if abs(c.frequency_hz - 100.0) < 15.0)
        assert candidate.narrowband_decay_20db_s is not None
        assert candidate.filter_ringing_20db_s is not None
        assert candidate.narrowband_decay_20db_s > 2.0 * candidate.filter_ringing_20db_s
        assert candidate.surroundings_decay_20db_s is not None


def test_filter_ringing_reference_uses_the_same_time_reversed_filtering(
    sample_rate: int,
) -> None:
    """B6: the reference was the *forward* filtered impulse, about 1.7 times
    longer than the time-reversed filtering used for the measurement."""
    reversed_ringing = filter_ringing_20db_s(sample_rate, 62.0)
    sos = bandpass_sos(fractional_octave_band(62.0, 3), sample_rate, order=2)
    impulse = np.zeros(2 * sample_rate)
    impulse[0] = 1.0
    forward = _decay_20db_s(np.asarray(sosfilt(sos, impulse)), sample_rate, 2.0 / 62.0)
    assert reversed_ringing is not None and forward is not None
    assert forward > 1.4 * reversed_ringing


def test_notch_removes_the_candidate_frequency_only(sample_rate: int) -> None:
    t = np.arange(sample_rate) / sample_rate

    def level_db(frequency_hz: float) -> float:
        tone = np.sin(2 * np.pi * frequency_hz * t)
        cut = notch_band(tone, sample_rate, 100.0)[sample_rate // 4 : -sample_rate // 4]
        return float(20 * np.log10(np.sqrt(np.mean(cut**2)) / np.sqrt(0.5)))

    assert level_db(100.0) < -30.0  # the candidate's own frequency
    for neighbour in (100.0 * 2 ** (-2 / 3), 100.0 * 2 ** (2 / 3)):
        assert level_db(neighbour) == pytest.approx(0.0, abs=1.0)


def test_surroundings_are_measured_without_the_candidate_band(sample_rate: int) -> None:
    """B6: a long mode leaks through the skirts of the neighbouring band
    filters, so without the notch the surroundings repeat its own decay."""
    ir = make_rir(sample_rate, rt60_s=0.3, length_s=2.0, diffuse_level=0.01)
    t = np.arange(ir.shape[0]) / sample_rate
    ir = ir + 0.15 * np.sin(2 * np.pi * 62.0 * t) * np.exp(-DECAY_CONSTANT * t / (2 * 1.5))
    neighbour = 62.0 * 2 ** (2 / 3)
    leaked = band_decay_20db_s(ir, sample_rate, neighbour)
    clean = band_decay_20db_s(notch_band(ir, sample_rate, 62.0), sample_rate, neighbour)
    assert leaked is not None and clean is not None
    assert leaked > 3.0 * clean


def test_flat_response_has_no_candidates(sample_rate: int) -> None:
    ir = np.zeros(sample_rate)
    ir[0] = 1.0
    res = _detect(ir, sample_rate)
    assert res.candidates == ()


def test_search_is_clamped_to_the_excitation_band(sample_rate: int) -> None:
    """A2/B3: the roll-off below the swept range creates peaks that are not
    room resonances (a sweep edge at 241 Hz produced a finding)."""
    ir = make_rir(sample_rate, rt60_s=0.3, length_s=2.0, diffuse_level=0.01)
    t = np.arange(ir.shape[0]) / sample_rate
    ir = ir + 0.15 * np.sin(2 * np.pi * 62.0 * t) * np.exp(-DECAY_CONSTANT * t / (2 * 1.5))
    band = ExcitationBand(low_hz=100.0, high_hz=18000.0, source="sweep settings")
    res = _detect(ir, sample_rate, excitation_band=band)
    assert res.searched_range_hz is not None
    assert res.searched_range_hz[0] > 100.0
    assert all(c.frequency_hz >= res.searched_range_hz[0] for c in res.candidates)
    assert any("excited" in n for n in res.notes)
    # The 62 Hz mode is outside the excited range and is not reported at all.
    assert not any(abs(c.frequency_hz - 62.0) < 10.0 for c in res.candidates)


def test_short_response_cannot_resolve_low_peaks(sample_rate: int) -> None:
    """B7: the resolution check counted zero-padded bins, so it never fired."""
    ir = make_rir(sample_rate, rt60_s=0.1, length_s=0.05, diffuse_level=0.02)
    res = _detect(ir, sample_rate)
    # Nothing below 300 Hz can be resolved, so no search was made at all.
    assert res.searched_range_hz is None
    assert any("resolution" in n for n in res.notes)
    assert any("no search was made" in n for n in res.notes)


def test_a_band_that_misses_the_range_stores_no_searched_range(sample_rate: int) -> None:
    """#65: a sweep from 400 Hz stored the range (495, 300) and the note
    "the search is limited to 495-300 Hz"."""
    ir = make_rir(sample_rate, rt60_s=0.3, length_s=2.0, diffuse_level=0.01)
    band = ExcitationBand(low_hz=400.0, high_hz=18000.0, source="sweep settings")
    res = _detect(ir, sample_rate, excitation_band=band)
    assert res.candidates == ()
    assert res.searched_range_hz is None
    assert not any("limited to" in n for n in res.notes), res.notes
    assert any("no search was made" in n for n in res.notes)


@pytest.mark.parametrize("window", [1, 2, 3, 4, 101, 250, 999])
def test_moving_average_is_the_centred_zero_padded_mean(window: int) -> None:
    from reverbscope.core.impulse import moving_average

    x = np.abs(np.random.default_rng(0).normal(size=1000))
    expected = np.convolve(x, np.ones(window) / window, mode="same")
    assert moving_average(x, window) == pytest.approx(expected, abs=1e-12)


def test_moving_average_keeps_the_input_length_for_a_longer_window() -> None:
    """np.convolve's "same" mode returned max(N, window) samples."""
    from reverbscope.core.impulse import moving_average

    smoothed = moving_average(np.arange(10.0), 25)
    assert smoothed.shape == (10,)
    assert smoothed == pytest.approx(np.full(10, 45.0 / 25.0))


def test_smoothing_a_low_mode_at_192_khz_takes_linear_time() -> None:
    """R3-9: two periods of a 28 Hz band at 192 kHz are 13 511 samples; a direct
    convolution over a 5 s response took 13-22 s per call, and an analysis
    with one low mode spent 105 s smoothing envelopes."""
    import time

    from reverbscope.core.impulse import moving_average

    x = np.abs(np.random.default_rng(0).normal(size=960_960))
    started = time.perf_counter()
    smoothed = moving_average(x, 13_511)
    assert time.perf_counter() - started < 1.0
    assert smoothed.shape == x.shape


def _room_with_modes(sample_rate: int, seed: int, *modes: float) -> np.ndarray:
    """A room with RT 0.3 s plus modes ringing with RT 1.5 s."""
    ir = make_rir(sample_rate, rt60_s=0.3, length_s=2.0, diffuse_level=0.01, seed=seed)
    t = np.arange(ir.shape[0]) / sample_rate
    for frequency in modes:
        ir = ir + 0.15 * np.sin(2 * np.pi * frequency * t) * np.exp(-DECAY_CONSTANT * t / (2 * 1.5))
    return ir


@pytest.mark.parametrize("seed", [0, 1])
def test_two_modes_an_octave_apart_are_both_distinguishable(sample_rate: int, seed: int) -> None:
    """Only the candidate's own band was notched, so the 124 Hz mode, one
    octave above a 62 Hz mode (the first two axial modes of one dimension),
    leaked into its neighbouring bands and each read the other's 0.5 s decay
    as its surroundings: neither was distinguishable, though each was alone."""
    res = _detect(_room_with_modes(sample_rate, seed, 62.0, 124.0), sample_rate)
    for frequency in (62.0, 124.0):
        found = min(res.candidates, key=lambda c: abs(c.frequency_hz - frequency))
        assert found.frequency_hz == pytest.approx(frequency, abs=3.0)
        assert found.narrowband_decay_20db_s == pytest.approx(0.5, rel=0.15)
        assert found.surroundings_decay_20db_s is not None
        assert found.surroundings_decay_20db_s < 0.2
        assert found.decay_distinguishable is True


def test_a_candidate_decay_leaves_out_the_other_candidates(sample_rate: int) -> None:
    """With the other candidates notched out of the surroundings only, a peak
    an octave below a long mode would read the mode's leaked decay against
    clean surroundings and pass as a resonance of its own."""
    ir = _room_with_modes(sample_rate, 0, 124.0)
    assert band_decay_20db_s(ir, sample_rate, 62.0) == pytest.approx(0.5, rel=0.1)
    decay, surroundings = candidate_decays_20db_s(
        ir, sample_rate, 62.0, excitation_band=None, other_candidates_hz=[124.0]
    )
    assert decay is not None and surroundings is not None
    assert decay < 0.2
    assert decay < SURROUNDINGS_RATIO * surroundings


@pytest.mark.parametrize("seed", [0, 1])
@pytest.mark.parametrize("modes", [(45.0, 90.0, 180.0), (45.0, 62.0, 90.0, 124.0)])
def test_three_or_more_nearby_modes_are_each_distinguishable(
    sample_rate: int, seed: int, modes: tuple[float, ...]
) -> None:
    """Every neighbouring band that overlapped another candidate was skipped,
    and with three or more candidates within an octave or so of each other
    that left fewer than two clean bands: a third to a half of the genuinely
    ringing modes (RT 1.5 s in a room of 0.3 s) had no surroundings and were
    never called distinguishable. The reference now reaches further out."""
    res = _detect(_room_with_modes(sample_rate, seed, *modes), sample_rate)
    assert len(res.candidates) == len(modes)
    for frequency in modes:
        found = min(res.candidates, key=lambda c: abs(c.frequency_hz - frequency))
        assert found.frequency_hz == pytest.approx(frequency, rel=0.05)
        assert found.surroundings_decay_20db_s is not None
        assert found.surroundings_decay_20db_s < 0.2
        assert found.decay_distinguishable is True
    assert not any("too few measurable" in note for note in res.notes)


def test_covered_neighbours_are_replaced_by_the_next_clean_ones(sample_rate: int) -> None:
    """Candidates 0.8 octave either side cover the bands at +-2/3 and +-1
    octave: the surroundings come from the bands further out, and a room
    without a mode there reads the room's own decay (no resonance)."""
    ir = make_rir(sample_rate, rt60_s=0.3, length_s=2.0, diffuse_level=0.01, seed=3)
    others = [100.0 * 2**-0.8, 100.0 * 2**0.8]
    decay, surroundings = candidate_decays_20db_s(
        ir, sample_rate, 100.0, excitation_band=None, other_candidates_hz=others
    )
    assert decay is not None and surroundings is not None
    assert surroundings == pytest.approx(decay, rel=0.8)
    assert decay < SURROUNDINGS_RATIO * surroundings


def test_the_nearest_clean_bands_are_still_the_surroundings(sample_rate: int) -> None:
    """With nothing in the way the reference is the median of the bands at
    +-2/3 and +-1 octave, as it was calibrated; the farther bands are only
    a stand-in for a covered one."""
    ir = make_rir(sample_rate, rt60_s=0.3, length_s=2.0, diffuse_level=0.01, seed=4)
    centre = 100.0
    expected = []
    for offset in (-1.0, -2 / 3, 2 / 3, 1.0):
        decay = band_decay_20db_s(
            _notch_bands(ir, sample_rate, [centre]), sample_rate, centre * OCTAVE_RATIO**offset
        )
        assert decay is not None
        expected.append(decay)
    _, surroundings = candidate_decays_20db_s(
        ir, sample_rate, centre, excitation_band=None, other_candidates_hz=[]
    )
    assert surroundings == pytest.approx(float(np.median(expected)))
