"""Flat-top (clipping) detection and the aliased-distortion probe."""

from __future__ import annotations

import numpy as np
import pytest

from reverbscope.core.linearity import (
    CLIPPING_MIN_RUNS,
    detect_clipping,
    quantisation_step,
)
from reverbscope.core.sweep import generate_ess, measurement_signal
from reverbscope.models.configuration import SweepSettings


def _quantise(x: np.ndarray, bits: int = 24, dither: float = 0.0, seed: int = 0) -> np.ndarray:
    """``x`` on the grid of a PCM export of ``bits`` bits, optionally dithered."""
    step = 2.0 ** -(bits - 1)
    if dither:
        x = x + np.random.default_rng(seed).triangular(-dither, 0.0, dither, x.shape[0]) * step
    return np.asarray(np.round(np.clip(x, -1.0, 1.0 - step) / step) * step)


def _sine(sample_rate: int, frequency_hz: float, seconds: float, amplitude: float) -> np.ndarray:
    t = np.arange(int(seconds * sample_rate)) / sample_rate
    return amplitude * np.sin(2 * np.pi * frequency_hz * t)


def test_quantisation_step_is_recognised(sample_rate: int) -> None:
    x = _sine(sample_rate, 100.0, 0.2, 0.5)
    assert quantisation_step(_quantise(x, 16)) == pytest.approx(2.0**-15)
    assert quantisation_step(_quantise(x, 24)) == pytest.approx(2.0**-23)
    assert quantisation_step(x) is None


def test_unclipped_signals_are_not_flagged(sample_rate: int) -> None:
    """A6: an unclipped recording normalised to 0 dBFS produced a 'probable
    clipping' warning, because 205 samples were at or above 0.999."""
    settings = SweepSettings(sample_rate=sample_rate, duration_s=2.0)
    sweep = measurement_signal(settings)
    for signal in (
        sweep,  # an ESS at -12 dBFS
        sweep / np.max(np.abs(sweep)),  # the same, normalised to 0 dBFS
        _quantise(sweep / np.max(np.abs(sweep)), 24),
        _sine(sample_rate, 1000.0, 0.5, 1.0),  # a full-scale sine
        _quantise(_sine(sample_rate, 30.0, 0.5, 0.999), 24),  # flat quantised crests
    ):
        check = detect_clipping(signal)
        assert not check.clipped, check


@pytest.mark.parametrize("gain_db", [0.0, -0.5, -1.0, -6.02])
def test_clipped_sine_is_flagged_whatever_the_export_level(
    sample_rate: int, gain_db: float
) -> None:
    """C22: clipping was detected with an absolute threshold of 0.999, so a
    clipped file exported 0.1 dB below full scale was not flagged."""
    clipped = np.clip(_sine(sample_rate, 100.0, 1.0, 1.5), -1.0, 1.0) * 10 ** (gain_db / 20)
    check = detect_clipping(_quantise(clipped, 24))
    assert check.clipped
    assert check.peak_dbfs == pytest.approx(gain_db, abs=0.05)
    assert check.runs > CLIPPING_MIN_RUNS


def test_ceiling_below_full_scale_is_flagged(sample_rate: int) -> None:
    """C22: a file clipped at a 0.5 ceiling (12 dB of overdrive, then a
    fader) was reported as clean with a 'high' confidence."""
    check = detect_clipping(np.clip(_sine(sample_rate, 200.0, 1.0, 2.0), -0.5, 0.5))
    assert check.clipped and check.peak_dbfs == pytest.approx(-6.02, abs=0.05)


def test_dithered_export_of_a_clipped_signal_is_flagged(sample_rate: int) -> None:
    clipped = np.clip(_sine(sample_rate, 100.0, 1.0, 1.5), -1.0, 1.0) * 0.9
    check = detect_clipping(_quantise(clipped, 16, dither=1.0))
    assert check.clipped and check.quantisation_step == pytest.approx(2.0**-15)


def test_a_few_flat_samples_are_not_enough(sample_rate: int) -> None:
    signal = generate_ess(SweepSettings(sample_rate=sample_rate, duration_s=2.0))
    signal = signal / np.max(np.abs(signal))
    # Two clipped peaks: a single transient, not a clipped measurement.
    signal[1000:1010] = 1.0
    signal[5000:5010] = -1.0
    check = detect_clipping(signal)
    assert check.runs == 2 and not check.clipped


def test_quiet_signals_are_never_reported(sample_rate: int) -> None:
    """Below the level floor, the flat tops of a quantised low-frequency
    crest cannot be told from a clipped one."""
    clipped = np.clip(_sine(sample_rate, 100.0, 1.0, 1.5), -1.0, 1.0) * 10 ** (-30 / 20)
    assert not detect_clipping(_quantise(clipped, 16)).clipped


@pytest.mark.parametrize("duration_s", [2.0, 10.0, 30.0])
def test_long_sweeps_in_16_bit_are_not_flagged(sample_rate: int, duration_s: float) -> None:
    """A quantised low-frequency crest is flat too: at 16 bits, the 20-100 Hz
    part of an unclipped sweep has runs of a dozen samples at its maximum.
    They are told apart by the step at the end of the plateau."""
    settings = SweepSettings(sample_rate=sample_rate, duration_s=duration_s)
    sweep = measurement_signal(settings)
    for signal in (sweep, sweep / np.max(np.abs(sweep))):
        assert not detect_clipping(_quantise(signal, 16)).clipped
        assert not detect_clipping(_quantise(signal, 16, dither=1.0)).clipped


def test_alias_probe_inverse_is_flat_over_the_folded_band() -> None:
    """The exp(t/L) weight was applied to the reversed reference, i.e. as
    1/f(t): |R I| tilted by -4 / +5 dB across the folded band."""
    from scipy import fft as sfft

    from reverbscope.core.linearity import (
        _alias_trajectory,
        _harmonic_reference,
        _probe_inverse,
    )
    from reverbscope.core.sweep import excitation_band_hz
    from reverbscope.models.result import ExcitationBand

    settings = SweepSettings(duration_s=2.0)
    low, high = excitation_band_hz(settings)
    band = ExcitationBand(low_hz=low, high_hz=high, source="settings")
    trajectory = _alias_trajectory(settings, 3, band)
    assert trajectory is not None
    folded = (trajectory.low_hz + 200.0, min(trajectory.high_hz, 0.45 * 48000) - 200.0)
    reference = _harmonic_reference(settings, trajectory)
    inverse = _probe_inverse(settings, trajectory, folded)
    nfft = int(sfft.next_fast_len(2 * reference.shape[0], real=True))
    freqs = np.fft.rfftfreq(nfft, 1.0 / 48000)
    select = (freqs >= folded[0]) & (freqs <= folded[1])
    magnitude = np.abs(sfft.rfft(reference, nfft) * sfft.rfft(inverse, nfft))[select]
    tenth = magnitude.shape[0] // 10
    ends = 20.0 * np.log10([np.median(magnitude[:tenth]), np.median(magnitude[-tenth:])])
    assert np.all(np.abs(ends) < 0.2)


# --------------------------------------------------------------- dropouts


def test_detect_dropouts_finds_zero_and_frozen_runs_but_not_clipping() -> None:
    from reverbscope.core.linearity import DROPOUT_MIN_MS, detect_dropouts
    from reverbscope.core.sweep import measurement_signal
    from reverbscope.models.configuration import SweepSettings

    settings = SweepSettings(
        sample_rate=48000, duration_s=1.0, pre_silence_s=0.2, post_silence_s=0.2
    )
    rate = settings.sample_rate
    rng = np.random.default_rng(1)
    signal = measurement_signal(settings) + rng.normal(0.0, 1e-4, settings.total_samples)
    start = round(settings.pre_silence_s * rate)
    zero = start + int(0.3 * rate)
    signal[zero : zero + int(0.004 * rate)] = 0.0
    frozen = start + int(0.6 * rate)
    signal[frozen : frozen + int(0.0025 * rate)] = 0.05  # a held value below the peak
    # A flat top at the file's own peak is clipping, not a dropout.
    clipped = np.clip(signal, -0.2, 0.2)
    check = detect_dropouts(
        clipped, rate, sweep_start=start, sweep_length=settings.sweep_samples, settings=settings
    )
    assert check.min_duration_ms == pytest.approx(DROPOUT_MIN_MS)
    assert [round(d.duration_ms, 1) for d in check.dropouts] == [4.0, 2.5]
    assert check.dropouts[0].start_s == pytest.approx(zero / rate, abs=2 / rate)
    assert check.dropouts[0].sweep_hz is not None
    assert check.searched_s[0] > start / rate  # the fade-in is left out
    assert check.total_ms == pytest.approx(6.5, abs=0.1)
    # A run shorter than the limit, and a clean sweep, are no dropouts.
    short = signal.copy()
    short[zero : zero + int(0.004 * rate)] = measurement_signal(settings)[
        zero : zero + int(0.004 * rate)
    ]
    short[frozen : frozen + 20] = short[frozen]
    short[frozen + 20 : frozen + int(0.0025 * rate)] = measurement_signal(settings)[
        frozen + 20 : frozen + int(0.0025 * rate)
    ]
    assert (
        detect_dropouts(
            short, rate, sweep_start=start, sweep_length=settings.sweep_samples, settings=settings
        ).dropouts
        == ()
    )


def test_detect_dropouts_returns_empty_when_search_window_is_too_short() -> None:
    from reverbscope.core.linearity import detect_dropouts

    signal = np.random.default_rng(0).normal(0.0, 0.1, 1000)
    # Shorter than DROPOUT_MIN_SAMPLES / DROPOUT_MIN_MS at 48 kHz.
    check = detect_dropouts(signal, 48000, sweep_start=0, sweep_length=10)
    assert check.dropouts == ()
    settings = SweepSettings(sample_rate=48000, duration_s=0.5, fade_in_s=0.2, fade_out_s=0.2)
    # Fades eat the whole short sweep window.
    faded = detect_dropouts(signal, 48000, sweep_start=0, sweep_length=100, settings=settings)
    assert faded.dropouts == ()
    assert faded.searched_s[0] == pytest.approx(faded.searched_s[1])


def test_alias_trajectory_is_none_when_harmonics_do_not_fold_or_are_too_short() -> None:
    from reverbscope.core.linearity import _alias_trajectory
    from reverbscope.models.result import ExcitationBand

    settings = SweepSettings(duration_s=2.0)
    # Order-2 fold needs content above Nyquist/2; a band entirely below that.
    assert (
        _alias_trajectory(
            settings, 2, ExcitationBand(low_hz=20.0, high_hz=5000.0, source="settings")
        )
        is None
    )
    # A half-hertz strip around the fold edge is shorter than 16 samples.
    assert (
        _alias_trajectory(
            settings,
            2,
            ExcitationBand(low_hz=12_000.0, high_hz=12_000.5, source="settings"),
        )
        is None
    )


def test_analysis_band_rejects_fold_outside_excitation() -> None:
    from reverbscope.core.linearity import _AliasTrajectory, _analysis_band
    from reverbscope.models.result import ExcitationBand

    settings = SweepSettings(duration_s=2.0)
    traj = _AliasTrajectory(order=3, start=100, stop=200, low_hz=5000.0, high_hz=8000.0)
    band, reason = _analysis_band(
        traj,
        settings,
        ExcitationBand(low_hz=20.0, high_hz=1000.0, source="settings"),
        window_bins_hz=10.0,
    )
    assert band is None
    assert reason is not None
    assert "outside the swept range" in reason


def test_probe_inverse_skips_normalisation_when_band_has_no_bins() -> None:
    from reverbscope.core.linearity import _alias_trajectory, _probe_inverse
    from reverbscope.core.sweep import excitation_band_hz
    from reverbscope.models.result import ExcitationBand

    settings = SweepSettings(duration_s=2.0)
    low, high = excitation_band_hz(settings)
    traj = _alias_trajectory(
        settings, 3, ExcitationBand(low_hz=low, high_hz=high, source="settings")
    )
    assert traj is not None
    inverse = _probe_inverse(settings, traj, (1e9, 1e9 + 1.0))
    assert inverse.shape[0] == traj.stop - traj.start
    assert np.max(np.abs(inverse)) > 0.0


def test_aliased_distortion_reports_outside_window_and_empty_linear_energy() -> None:
    from reverbscope.core.linearity import aliased_distortion_levels
    from reverbscope.core.sweep import excitation_band_hz, inverse_filter
    from reverbscope.models.result import ExcitationBand

    settings = SweepSettings(duration_s=1.0)
    rate = settings.sample_rate
    low, high = excitation_band_hz(settings)
    exc = ExcitationBand(low_hz=low, high_hz=high, source="settings")
    inv = inverse_filter(settings)

    tiny = aliased_distortion_levels(
        np.zeros(100),
        np.zeros(50),
        sample_rate=rate,
        settings=settings,
        excitation_band=exc,
        peak_index=25,
        reference_length=inv.shape[0],
        orders=(3,),
    )
    assert tiny[0].level_db is None
    assert "outside the recording" in (tiny[0].reason or "")

    direct = 10_000
    peak_index = direct + (inv.shape[0] - 1)
    half = round(0.004 * rate)
    rec = np.random.default_rng(0).normal(0.0, 1e-6, peak_index + half + 20_000)
    h_full = np.zeros(peak_index + half + 1000)
    empty = aliased_distortion_levels(
        rec,
        h_full,
        sample_rate=rate,
        settings=settings,
        excitation_band=exc,
        peak_index=peak_index,
        reference_length=inv.shape[0],
        orders=(3,),
    )
    assert empty[0].level_db is None
    assert "no energy in the probe band" in (empty[0].reason or "")
