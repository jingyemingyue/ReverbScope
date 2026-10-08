"""Closed-form checks that do not call the production helpers for the expected value.

The signal is an alternating-sign exponential, so its squared envelope is
exactly ``exp(-t / tau)`` with ``tau = RT60 / ln(1e6)``. Expected EDT, T20 and
T30 are that RT60. Expected clarity, definition and centre time are the
integrals of the same envelope. A sample is late when its own time stamp is
at or after the split, which is not the same as rounding the split index.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from reverbscope.core.decay import analyze_band, analyze_decay
from reverbscope.core.filters import bandpass_sos, iec_band
from reverbscope.core.frequency_response import frequency_response
from reverbscope.errors import ConfigurationError, InvalidAudioError
from reverbscope.models.configuration import AnalysisSettings
from reverbscope.models.result import Validity

# 60 dB in nepers: power decays as exp(-t / tau), tau = RT60 / LN_MILLION.
LN_MILLION = math.log(1e6)


def _alternating(sample_rate: int, rt60_s: float, length_s: float) -> np.ndarray:
    n = int(length_s * sample_rate)
    t = np.arange(n, dtype=np.float64) / sample_rate
    sign = np.where(np.arange(n) % 2 == 0, 1.0, -1.0)
    return np.exp(-LN_MILLION * t / (2.0 * rt60_s)) * sign


def _clarity_db(split_s: float, rt60_s: float) -> float:
    tau = rt60_s / LN_MILLION
    return float(10.0 * math.log10(math.exp(split_s / tau) - 1.0))


def _definition_percent(split_s: float, rt60_s: float) -> float:
    tau = rt60_s / LN_MILLION
    return float(100.0 * (1.0 - math.exp(-split_s / tau)))


def _centre_time_s(rt60_s: float) -> float:
    return rt60_s / LN_MILLION


def _band(sample_rate: int, rt60_s: float, *, length_s: float | None = None):
    length = 2.0 * rt60_s if length_s is None else length_s
    return analyze_band(
        _alternating(sample_rate, rt60_s, length),
        sample_rate,
        None,
        noise_margin_db=10.0,
    )


@pytest.mark.parametrize("sample_rate", [8000, 11025, 22050, 44100, 48000, 88200, 96000, 192000])
@pytest.mark.parametrize("rt60_s", [0.1, 0.5, 2.0])
def test_rt_matches_the_envelope_at_every_rate(sample_rate: int, rt60_s: float) -> None:
    band = _band(sample_rate, rt60_s)
    for metric in (band.edt, band.t20, band.t30):
        assert metric.validity is Validity.VALID
        assert metric.seconds == pytest.approx(rt60_s, rel=0.01)
    assert band.rt60_estimate_s == pytest.approx(rt60_s, rel=0.01)
    assert band.rt60_basis == "T30"


@pytest.mark.parametrize("rt60_s", [0.1, 0.2, 0.5, 1.0, 2.0, 5.0, 10.0])
def test_rt_matches_the_envelope_from_a_tenth_to_ten_seconds(rt60_s: float) -> None:
    band = _band(48000, rt60_s)
    assert band.t30.validity is Validity.VALID
    assert band.t20.seconds == pytest.approx(rt60_s, rel=0.01)
    assert band.t30.seconds == pytest.approx(rt60_s, rel=0.01)
    assert band.edt.seconds == pytest.approx(rt60_s, rel=0.02)


@pytest.mark.parametrize("sample_rate", [22050, 44100, 48000, 96000])
def test_energy_ratios_match_the_integral(sample_rate: int) -> None:
    rt60_s = 0.5
    band = _band(sample_rate, rt60_s)
    assert band.c50.validity is Validity.VALID
    assert band.c50.value == pytest.approx(_clarity_db(0.05, rt60_s), abs=0.4)
    assert band.c80.value == pytest.approx(_clarity_db(0.08, rt60_s), abs=0.4)
    assert band.d50.value == pytest.approx(_definition_percent(0.05, rt60_s), abs=1.0)
    assert band.centre_time.value == pytest.approx(_centre_time_s(rt60_s), abs=0.002)


def _with_impulse(sample_rate: int, index: int) -> np.ndarray:
    ir = 0.05 * _alternating(sample_rate, 0.5, 1.2)
    ir[0] = 1.0
    ir[index] += 1.0
    return ir


def test_samples_before_50_and_80_ms_are_early_and_the_next_sample_is_late() -> None:
    """The cut is the first sample whose time is at or after the nominal split.

    At 22.05 kHz, 50 ms is 1102.5 samples. Sample 1102 is at 49.98 ms and must
    count as early; sample 1103 is at 50.02 ms and must count as late. Rounding
    the index would do the opposite.
    """
    sample_rate = 22050
    bare = analyze_band(
        0.05 * _alternating(sample_rate, 0.5, 1.2), sample_rate, None, noise_margin_db=10.0
    )
    bare_c50 = bare.c50.value
    bare_c80 = bare.c80.value
    assert bare_c50 is not None and bare_c80 is not None

    def clarity(index: int, name: str) -> float:
        band = analyze_band(
            _with_impulse(sample_rate, index), sample_rate, None, noise_margin_db=10.0
        )
        metric = band.c50 if name == "C50" else band.c80
        assert metric.validity is Validity.VALID
        assert metric.value is not None
        return float(metric.value)

    # 50 ms: 1102 / 22050 = 49.977 ms, 1103 / 22050 = 50.023 ms.
    assert 1102 / sample_rate < 0.05 < 1103 / sample_rate
    assert clarity(1102, "C50") > bare_c50
    assert clarity(1103, "C50") < bare_c50
    # 80 ms is an integer number of samples here (1764). That sample is late;
    # the one before it is early.
    assert 1763 / sample_rate < 0.08 == 1764 / sample_rate
    assert clarity(1763, "C80") > bare_c80
    assert clarity(1764, "C80") < bare_c80


@pytest.mark.parametrize(
    ("delay_ms", "early"),
    [(49.0, True), (50.0, False), (51.0, False), (79.0, True), (80.0, False), (81.0, False)],
)
def test_exact_millisecond_boundaries_at_48_khz(delay_ms: float, early: bool) -> None:
    sample_rate = 48000
    index = round(delay_ms / 1000.0 * sample_rate)
    assert index / sample_rate == pytest.approx(delay_ms / 1000.0, abs=1e-12)
    name = "C50" if delay_ms < 70.0 else "C80"
    bare = analyze_band(
        0.05 * _alternating(sample_rate, 0.5, 1.2), sample_rate, None, noise_margin_db=10.0
    )
    bare_value = bare.c50.value if name == "C50" else bare.c80.value
    band = analyze_band(_with_impulse(sample_rate, index), sample_rate, None, noise_margin_db=10.0)
    value = band.c50.value if name == "C50" else band.c80.value
    assert bare_value is not None and value is not None
    if early:
        assert value > bare_value
    else:
        assert value < bare_value


def test_silence_dc_and_noise_do_not_invent_an_rt60() -> None:
    sample_rate = 48000
    settings = AnalysisSettings()
    silence = analyze_decay(np.zeros(sample_rate), sample_rate, settings)
    assert silence.broadband.rt60_estimate_s is None
    assert silence.broadband.t30.validity is not Validity.VALID
    dc = analyze_decay(np.ones(sample_rate), sample_rate, settings)
    assert dc.broadband.rt60_estimate_s is None
    assert dc.broadband.t30.validity is not Validity.VALID
    noise = np.random.default_rng(1).normal(0.0, 1.0, 2 * sample_rate)
    noisy = analyze_decay(noise, sample_rate, settings)
    assert noisy.broadband.rt60_estimate_s is None
    assert noisy.broadband.t30.seconds is None


@pytest.mark.parametrize("snr_db", [30.0, 35.0])
def test_low_snr_exponential_does_not_publish_t30(snr_db: float) -> None:
    sample_rate = 48000
    rt60_s = 0.5
    clean = _alternating(sample_rate, rt60_s, 1.5)
    # The start of the alternating exponential has amplitude 1, so this noise
    # is ``snr_db`` below the direct sample, not below the RMS of the tail.
    noise = np.random.default_rng(4).normal(0.0, 10 ** (-snr_db / 20.0), clean.shape[0])
    band = analyze_band(clean + noise, sample_rate, None, noise_margin_db=10.0)
    assert band.t30.validity is not Validity.VALID
    assert band.t30.seconds is None
    assert band.rt60_estimate_s is None or band.rt60_basis != "T30"


def test_high_snr_exponential_keeps_t30() -> None:
    sample_rate = 48000
    rt60_s = 0.5
    clean = _alternating(sample_rate, rt60_s, 1.5)
    noise = np.random.default_rng(4).normal(0.0, 10 ** (-60.0 / 20.0), clean.shape[0])
    band = analyze_band(clean + noise, sample_rate, None, noise_margin_db=10.0)
    assert band.t30.validity is Validity.VALID
    assert band.t30.seconds == pytest.approx(rt60_s, rel=0.02)
    assert band.rt60_estimate_s == pytest.approx(rt60_s, rel=0.02)


def test_gain_polarity_and_float32_do_not_move_rt60() -> None:
    sample_rate = 48000
    ir = _alternating(sample_rate, 0.5, 1.2)
    reference = analyze_band(ir, sample_rate, None, noise_margin_db=10.0)
    for scaled in (ir * 0.5, ir * 2.0, -ir, np.float64(ir.astype(np.float32))):
        band = analyze_band(scaled, sample_rate, None, noise_margin_db=10.0)
        assert band.t30.seconds == pytest.approx(reference.t30.seconds, rel=1e-6)
        assert band.c50.value == pytest.approx(reference.c50.value, abs=1e-6)
        assert band.centre_time.value == pytest.approx(reference.centre_time.value, abs=1e-8)
    shifted = np.concatenate([np.zeros(sample_rate), ir])
    moved = analyze_band(shifted, sample_rate, None, noise_margin_db=10.0, direct_index=sample_rate)
    assert moved.t30.seconds == pytest.approx(reference.t30.seconds, rel=1e-6)
    assert moved.c50.value == pytest.approx(reference.c50.value, abs=0.05)


def test_public_decay_apis_reject_non_finite_and_bad_rates() -> None:
    settings = AnalysisSettings()
    ir = _alternating(48000, 0.3, 0.6)
    with pytest.raises(InvalidAudioError, match="NaN or infinite"):
        analyze_decay(np.array([1.0, np.nan]), 48000, settings)
    with pytest.raises(InvalidAudioError, match="NaN or infinite"):
        analyze_decay(np.array([1.0, np.inf]), 48000, settings)
    with pytest.raises(InvalidAudioError, match="NaN or infinite"):
        analyze_band(np.full(1000, 1e300), 48000, None, noise_margin_db=10.0)
    with pytest.raises(InvalidAudioError, match="one-dimensional"):
        analyze_decay(np.ones((100, 2)), 48000, settings)
    for rate in (0, -1, True):
        with pytest.raises(ConfigurationError, match="positive integer"):
            analyze_decay(ir, rate, settings)  # type: ignore[arg-type]
    # Pathological but finite inputs must not crash, and must not look measured.
    for pathological in (
        np.zeros(0),
        np.array([1.0]),
        np.zeros(48000),
        np.full(100, 1e-300),
        np.array([1.0, -1.0, 1.0]),
    ):
        result = analyze_decay(pathological, 12345 if pathological.size else 8000, settings)
        assert result.broadband.rt60_estimate_s is None
        assert result.broadband.t30.validity is not Validity.VALID


def test_bands_above_nyquist_are_omitted_not_invented() -> None:
    ir = _alternating(44100, 0.4, 0.8)
    result = analyze_decay(ir, 44100, AnalysisSettings(octave_bands_hz=(1000.0, 8000.0, 16000.0)))
    labels = [band.band_label for band in result.bands]
    assert "1 kHz" in labels
    assert "16 kHz" not in labels
    assert all(band.high_hz is not None and band.high_hz < 0.9 * 22050.0 for band in result.bands)
    with pytest.raises(ConfigurationError, match="Nyquist"):
        bandpass_sos(iec_band(16000.0, 1), 44100)


def test_frequency_response_follows_gain_and_rejects_bad_input() -> None:
    sample_rate = 48000
    ir = np.zeros(sample_rate)
    ir[10] = 1.0
    flat = frequency_response(ir, sample_rate, smoothing_fraction=0)
    assert np.allclose(flat.magnitude_db_raw, 0.0, atol=1e-9)
    quiet = ir.copy()
    quiet[10] = 1e-6
    dropped = frequency_response(quiet, sample_rate, smoothing_fraction=0)
    assert np.allclose(dropped.magnitude_db_raw, 20.0 * math.log10(1e-6), atol=1e-6)
    flipped = ir.copy()
    flipped[10] = -0.5
    negative = frequency_response(flipped, sample_rate, smoothing_fraction=0)
    assert np.allclose(negative.magnitude_db_raw, 20.0 * math.log10(0.5), atol=1e-9)
    with pytest.raises(InvalidAudioError, match="NaN or infinite"):
        frequency_response(np.array([0.0, np.nan, 1.0]), sample_rate)
    with pytest.raises(InvalidAudioError, match="one-dimensional"):
        frequency_response(np.ones((16, 2)), sample_rate)
    with pytest.raises(ConfigurationError, match="positive integer"):
        frequency_response(ir, 0)
    with pytest.raises(ConfigurationError, match="positive integer"):
        frequency_response(ir, False)  # type: ignore[arg-type]
