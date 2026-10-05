from __future__ import annotations

import numpy as np
import pytest

from reverbscope.core.filters import iec_band
from reverbscope.core.noise import (
    NOISE_FLOOR_DBFS,
    QuietSegment,
    analyze_noise,
    peak_dbfs,
    quiet_segment_candidates,
    rms_dbfs,
    select_quiet_part,
    sweep_level_dbfs,
)
from reverbscope.models.configuration import DEFAULT_OCTAVE_BANDS_HZ


def _whole(x: np.ndarray, source: str = "pre-sweep") -> QuietSegment:
    return QuietSegment(0, x.shape[0], source)


def _analyze(x: np.ndarray, sample_rate: int, **kwargs: object):  # type: ignore[no-untyped-def]
    return analyze_noise(
        x,
        sample_rate,
        _whole(x),
        octave_bands_hz=DEFAULT_OCTAVE_BANDS_HZ,
        **kwargs,  # type: ignore[arg-type]
    )


def test_full_scale_sine_is_zero_dbfs_rms(sample_rate: int) -> None:
    t = np.arange(sample_rate) / sample_rate
    sine = np.sin(2 * np.pi * 1000.0 * t)
    assert rms_dbfs(sine) == pytest.approx(0.0, abs=0.01)
    assert peak_dbfs(0.5 * sine) == pytest.approx(-6.02, abs=0.01)


def test_quiet_segment_prefers_pre_sweep(sample_rate: int) -> None:
    candidates = quiet_segment_candidates(
        recording_length=10 * sample_rate,
        sample_rate=sample_rate,
        first_sweep_start_index=2 * sample_rate,
        last_sweep_end_index=5 * sample_rate,
        min_segment_s=0.5,
    )
    assert candidates[0].source == "pre-sweep"
    assert candidates[0].start == int(0.05 * sample_rate)
    assert candidates[0].end == 2 * sample_rate - int(0.1 * sample_rate)
    # The tail candidate starts after the *last* sweep, not after the first.
    assert candidates[1].source == "tail" and candidates[1].start == 8 * sample_rate


def test_quiet_segment_falls_back_to_tail_or_none(sample_rate: int) -> None:
    tail = quiet_segment_candidates(
        recording_length=12 * sample_rate,
        sample_rate=sample_rate,
        first_sweep_start_index=int(0.1 * sample_rate),
        last_sweep_end_index=3 * sample_rate,
        min_segment_s=0.5,
    )
    assert [c.source for c in tail] == ["tail"] and tail[0].note
    none = quiet_segment_candidates(
        recording_length=4 * sample_rate,
        sample_rate=sample_rate,
        first_sweep_start_index=int(0.1 * sample_rate),
        last_sweep_end_index=3 * sample_rate,
        min_segment_s=0.5,
    )
    assert none == ()


def _noise(sample_rate: int, seconds: float, seed: int = 0, sigma: float = 1e-4) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.normal(0.0, sigma, int(seconds * sample_rate))


def test_white_noise_has_no_hum(sample_rate: int) -> None:
    x = _noise(sample_rate, 3.0)
    res = _analyze(x, sample_rate)
    assert res.rms_dbfs == pytest.approx(20 * np.log10(1e-4 * np.sqrt(2)), abs=0.2)
    assert not any(h.detected for h in res.hum)
    assert len(res.band_levels_dbfs) == len(DEFAULT_OCTAVE_BANDS_HZ)
    assert res.psd_db is not None and res.psd_frequencies_hz is not None


def test_psd_integrates_to_the_reported_rms_level(sample_rate: int) -> None:
    """B8: the Welch PSD was referenced to the peak, so integrating it gave a
    level 3.01 dB below the AES17 RMS level that is reported next to it."""
    x = _noise(sample_rate, 20.0, sigma=1e-3)
    res = _analyze(x, sample_rate)
    assert res.psd_db is not None and res.psd_frequencies_hz is not None
    spacing = float(res.psd_frequencies_hz[1] - res.psd_frequencies_hz[0])
    integral_db = 10 * np.log10(np.sum(10 ** (res.psd_db / 10.0)) * spacing)
    assert res.rms_dbfs is not None
    assert integral_db == pytest.approx(res.rms_dbfs, abs=0.1)
    assert "integral" in res.psd_reference


@pytest.mark.parametrize("center_hz", [63.0, 1000.0, 8000.0])
def test_white_noise_band_levels_match_the_ideal_band_power(
    sample_rate: int, center_hz: float
) -> None:
    """A10/B8: zero-phase (forward-backward) filtering applied |H|^2, so the
    band levels of stationary noise read about 0.6 dB low."""
    sigma = 1e-3
    x = _noise(sample_rate, 20.0, sigma=sigma)
    res = _analyze(x, sample_rate)
    levels = dict(res.band_levels_dbfs)
    band = iec_band(center_hz, 1)
    ideal_db = 10 * np.log10(2 * sigma**2 * band.bandwidth_hz / (sample_rate / 2))
    assert levels[center_hz] == pytest.approx(ideal_db, abs=0.3)


def _buzz(sample_rate: int, base_hz: float, orders: range | tuple[int, ...]) -> np.ndarray:
    x = _noise(sample_rate, 3.0)
    t = np.arange(x.shape[0]) / sample_rate
    for k in orders:
        x = x + 3e-4 / k * np.sin(2 * np.pi * base_hz * k * t + k)
    return x


@pytest.mark.parametrize(
    ("base_hz", "orders"),
    [
        (50.0, tuple(range(1, 13))),
        (60.0, tuple(range(1, 13))),
        (50.0, tuple(range(2, 13, 2))),  # full-wave rectifier buzz: no fundamental
        (60.0, tuple(range(2, 13, 2))),
    ],
)
def test_hum_is_reported_only_for_its_own_mains_base(
    sample_rate: int, base_hz: float, orders: tuple[int, ...]
) -> None:
    """B5/D1: 300 and 600 Hz belong to both series, so a full 50 Hz buzz also
    marked 60 Hz as detected (and the interpretation warned about both)."""
    res = _analyze(_buzz(sample_rate, base_hz, orders), sample_rate)
    by_base = {h.base_hz: h for h in res.hum}
    other = 60.0 if base_hz == 50.0 else 50.0
    assert by_base[base_hz].detected
    assert not by_base[other].detected
    # The shared harmonics stay in the list of the other base (transparency),
    # they just do not count towards detection.
    assert all(f % 300.0 == 0 for f in [f for f, _ in by_base[other].harmonics])
    assert by_base[other].distinct_harmonics_hz == ()
    # Harmonics up to the 12th (below 1 kHz) are searched for.
    assert set(by_base[base_hz].distinct_harmonics_hz) == {
        base_hz * k for k in orders if (base_hz * k) % 300.0 != 0
    }


def test_mains_hum_detected_at_right_base_frequency(sample_rate: int) -> None:
    x = _noise(sample_rate, 3.0)
    t = np.arange(x.shape[0]) / sample_rate
    # Including the 10th harmonic (600 Hz), which 50 Hz also explains.
    for k, amp in ((1, 5e-4), (2, 2.5e-4), (3, 1e-4), (5, 5e-5), (10, 5e-5)):
        x = x + amp * np.sin(2 * np.pi * 60.0 * k * t)
    res = _analyze(x, sample_rate)
    by_base = {h.base_hz: h for h in res.hum}
    assert by_base[60.0].detected
    assert [f for f, _ in by_base[60.0].harmonics][:3] == [60.0, 120.0, 180.0]
    assert not by_base[50.0].detected


def test_both_bases_present_keeps_the_better_explained_one(sample_rate: int) -> None:
    x = _buzz(sample_rate, 50.0, tuple(range(1, 13)))
    t = np.arange(x.shape[0]) / sample_rate
    for k in (1, 2):  # a weaker 60 Hz series on top
        x = x + 1e-4 * np.sin(2 * np.pi * 60.0 * k * t)
    res = _analyze(x, sample_rate)
    by_base = {h.base_hz: h for h in res.hum}
    assert by_base[50.0].detected and not by_base[60.0].detected
    assert by_base[60.0].note and "50 Hz" in by_base[60.0].note


def test_no_segment_gives_notes_only(sample_rate: int) -> None:
    res = analyze_noise(
        np.zeros(sample_rate), sample_rate, None, octave_bands_hz=DEFAULT_OCTAVE_BANDS_HZ
    )
    assert res.rms_dbfs is None and res.segment_source is None
    assert res.notes


def test_short_segment_skips_hum(sample_rate: int) -> None:
    x = _noise(sample_rate, 0.1)
    res = analyze_noise(
        x,
        sample_rate,
        _whole(x, "tail"),
        octave_bands_hz=DEFAULT_OCTAVE_BANDS_HZ,
        min_segment_s=0.05,
    )
    assert res.hum == ()
    assert any("too short" in n for n in res.notes)


def test_digital_silence_is_not_a_noise_level(sample_rate: int) -> None:
    """C3: an all-zero pre-sweep segment (a DAW export that starts before the
    recorded region) was reported as '-6000.0 dBFS RMS'."""
    res = _analyze(np.zeros(2 * sample_rate), sample_rate)
    assert res.rms_dbfs is None and res.peak_dbfs is None
    assert res.band_levels_dbfs == ()
    assert any("digital silence" in n for n in res.notes)


def test_numerical_residue_is_not_a_noise_level(sample_rate: int) -> None:
    """C3: a noiseless synthetic float recording reported -321.5 dBFS."""
    res = _analyze(_noise(sample_rate, 2.0, sigma=1e-18), sample_rate)
    assert res.rms_dbfs is None
    assert any(f"{NOISE_FLOOR_DBFS:g} dBFS" in n for n in res.notes)


def test_zero_run_is_dropped_and_the_rest_is_measured(sample_rate: int) -> None:
    """C3: half a segment of digital zeros pulled the level 3 dB down."""
    sigma = 10 ** (-67 / 20) / np.sqrt(2)
    x = _noise(sample_rate, 2.0, sigma=sigma)
    x[:sample_rate] = 0.0
    res = _analyze(x, sample_rate)
    assert res.rms_dbfs == pytest.approx(-67.0, abs=1.0)
    assert res.segment_duration_s == pytest.approx(1.0, abs=0.01)
    assert any("digital zeros" in n for n in res.notes)


def test_loud_part_of_the_segment_is_excluded(sample_rate: int) -> None:
    """E2: a sweep pass inside the 'quiet' segment was measured as noise."""
    sigma = 10 ** (-75 / 20) / np.sqrt(2)
    x = _noise(sample_rate, 4.0, sigma=sigma)
    t = np.arange(sample_rate) / sample_rate
    x[sample_rate : 2 * sample_rate] += 0.05 * np.sin(2 * np.pi * 400.0 * t)
    res = _analyze(x, sample_rate)
    assert res.rms_dbfs == pytest.approx(-75.0, abs=1.0)
    assert res.segment_duration_s is not None and res.segment_duration_s <= 2.1
    assert any("were excluded" in n for n in res.notes)


def test_segment_as_loud_as_the_sweep_is_rejected(sample_rate: int) -> None:
    """E2: a looped sweep without silence gave a 'background noise' level that
    was really the sweep itself."""
    t = np.arange(2 * sample_rate) / sample_rate
    sweepish = 0.2 * np.sin(2 * np.pi * 300.0 * t)
    res = analyze_noise(
        sweepish,
        sample_rate,
        _whole(sweepish),
        octave_bands_hz=DEFAULT_OCTAVE_BANDS_HZ,
        sweep_level_dbfs=rms_dbfs(sweepish),
    )
    assert res.rms_dbfs is None
    assert any("not background noise" in n for n in res.notes)


def test_unusable_candidate_falls_back_to_the_next_one(sample_rate: int) -> None:
    sigma = 10 ** (-70 / 20) / np.sqrt(2)
    x = _noise(sample_rate, 4.0, sigma=sigma)
    x[: 2 * sample_rate] = 0.0
    res = analyze_noise(
        x,
        sample_rate,
        QuietSegment(0, sample_rate, "pre-sweep"),
        octave_bands_hz=DEFAULT_OCTAVE_BANDS_HZ,
        fallbacks=(QuietSegment(2 * sample_rate, 4 * sample_rate, "tail"),),
    )
    assert res.segment_source == "tail"
    assert res.rms_dbfs == pytest.approx(-70.0, abs=1.0)
    assert any("digital silence" in n for n in res.notes)


def test_select_quiet_part_keeps_a_clean_segment(sample_rate: int) -> None:
    x = _noise(sample_rate, 2.0)
    selection = select_quiet_part(x, sample_rate, _whole(x), min_segment_s=0.5)
    assert selection.segment is not None
    assert selection.segment.start == 0 and selection.segment.end == x.shape[0]
    assert selection.notes == ()


def test_sweep_level_needs_enough_samples(sample_rate: int) -> None:
    x = _noise(sample_rate, 1.0, sigma=0.1)
    assert sweep_level_dbfs(x, sample_rate, 0, sample_rate) == pytest.approx(rms_dbfs(x), abs=0.01)
    assert sweep_level_dbfs(x, sample_rate, sample_rate, sample_rate) is None


def test_short_remainder_is_still_measured_with_a_note(sample_rate: int) -> None:
    """C3: after the digital silence is dropped, 0.4 s of real noise are a
    better answer than no level at all."""
    sigma = 10 ** (-67 / 20) / np.sqrt(2)
    x = _noise(sample_rate, 1.0, sigma=sigma)
    x[: round(0.6 * sample_rate)] = 0.0
    res = _analyze(x, sample_rate, min_segment_s=0.8)
    assert res.rms_dbfs == pytest.approx(-67.0, abs=1.0)
    assert res.segment_duration_s == pytest.approx(0.4, abs=0.02)
    assert any("shorter part" in n for n in res.notes)
    # Below the measurable length nothing is reported.
    short = _noise(sample_rate, 1.0, sigma=sigma)
    short[: round(0.9 * sample_rate)] = 0.0
    assert _analyze(short, sample_rate, min_segment_s=0.8).rms_dbfs is None
