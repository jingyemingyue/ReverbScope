from __future__ import annotations

import numpy as np
import pytest

from reverbscope.core.frequency_response import frequency_response
from reverbscope.errors import ConfigurationError
from reverbscope.models.result import ExcitationBand


def test_delta_is_flat_zero_db(sample_rate: int) -> None:
    ir = np.zeros(sample_rate)
    ir[10] = 1.0
    fr = frequency_response(ir, sample_rate, smoothing_fraction=6)
    assert fr.frequencies_hz[0] > 0.0
    assert fr.frequencies_hz[-1] == pytest.approx(sample_rate / 2)
    assert np.allclose(fr.magnitude_db_raw, 0.0, atol=1e-9)
    assert fr.magnitude_db_smoothed is not None
    assert np.allclose(fr.magnitude_db_smoothed, 0.0, atol=1e-9)
    assert fr.smoothing_fraction == 6
    assert not fr.gated


def test_gain_is_reported_in_db(sample_rate: int) -> None:
    ir = np.zeros(sample_rate // 2)
    ir[0] = 0.5
    fr = frequency_response(ir, sample_rate, smoothing_fraction=0)
    assert fr.magnitude_db_smoothed is None
    assert np.allclose(fr.magnitude_db_raw, 20 * np.log10(0.5), atol=1e-9)


def test_comb_filter_notch_depth(sample_rate: int) -> None:
    delay = int(0.001 * sample_rate)  # 1 ms -> first notch at 500 Hz
    ir = np.zeros(sample_rate)
    ir[0] = 1.0
    ir[delay] = 0.5
    fr = frequency_response(ir, sample_rate, smoothing_fraction=0)
    i_notch = int(np.argmin(np.abs(fr.frequencies_hz - 500.0)))
    i_peak = int(np.argmin(np.abs(fr.frequencies_hz - 1000.0)))
    assert fr.magnitude_db_raw[i_notch] == pytest.approx(20 * np.log10(0.5), abs=0.05)
    assert fr.magnitude_db_raw[i_peak] == pytest.approx(20 * np.log10(1.5), abs=0.05)


def _level_db(fr, frequency_hz: float) -> float:  # type: ignore[no-untyped-def]
    return float(fr.magnitude_db_raw[int(np.argmin(np.abs(fr.frequencies_hz - frequency_hz)))])


def test_gate_is_measured_from_the_direct_sound(sample_rate: int) -> None:
    """B7: the gate was counted from the first IR sample, so the display
    pre-delay ate into it and the 5 ms end taper attenuated the direct sound
    (an 8 ms gate read -3.76 dB at 1 kHz, a 4 ms gate -6000 dB)."""
    direct = round(0.005 * sample_rate)
    ir = np.zeros(sample_rate)
    ir[direct] = 1.0
    fr = frequency_response(
        ir, sample_rate, direct_index=direct, window_s=0.008, smoothing_fraction=0
    )
    assert _level_db(fr, 1000.0) == pytest.approx(0.0, abs=0.05)
    assert fr.gated
    assert fr.window_s == pytest.approx(0.008, abs=1e-4)
    assert fr.lead_in_s == pytest.approx(0.005, abs=1e-4)


def test_gate_shorter_than_its_taper_is_refused(sample_rate: int) -> None:
    """B7: a 4 ms gate silently returned an empty response (-6000 dB)."""
    direct = round(0.005 * sample_rate)
    ir = np.zeros(sample_rate)
    ir[direct] = 1.0
    with pytest.raises(ConfigurationError, match="end taper"):
        frequency_response(ir, sample_rate, direct_index=direct, window_s=0.004)
    with pytest.raises(ConfigurationError, match="direct_index"):
        frequency_response(ir, sample_rate, direct_index=ir.shape[0])


def test_true_resolution_is_reported_next_to_the_bin_spacing(sample_rate: int) -> None:
    """B7: zero padding to a 1 Hz bin spacing was described as '>= 1 Hz
    resolution', although a 20 ms gate resolves no better than 50 Hz."""
    ir = np.zeros(2 * sample_rate)
    ir[0] = 1.0
    fr = frequency_response(ir, sample_rate, window_s=0.02, smoothing_fraction=0)
    assert fr.window_s == pytest.approx(0.02, abs=1e-4)
    assert fr.resolution_hz == pytest.approx(1.0 / 0.02, rel=0.02)
    assert fr.bin_spacing_hz <= 1.0
    assert fr.bin_spacing_hz < fr.resolution_hz

    ungated = frequency_response(ir, sample_rate, smoothing_fraction=0)
    assert ungated.resolution_hz == pytest.approx(0.5, rel=0.02)
    assert not ungated.gated


def test_lead_in_is_analysed_and_reported(sample_rate: int) -> None:
    """A7: the frequency response ran on the cut impulse response, so the
    pre-ringing of the band-limited direct sound (its low-frequency content)
    was lost and a loopback read -1.5 dB at 31.5 Hz."""
    direct = round(0.2 * sample_rate)
    ir = np.zeros(sample_rate)
    ir[direct] = 1.0
    fr = frequency_response(ir, sample_rate, direct_index=direct, smoothing_fraction=0)
    assert fr.lead_in_s == pytest.approx(0.2, abs=1e-4)
    assert fr.window_s == pytest.approx((sample_rate - 1 - direct) / sample_rate, abs=1e-4)
    assert fr.resolution_hz == pytest.approx(1.0, rel=0.02)


def test_excitation_band_is_stored(sample_rate: int) -> None:
    ir = np.zeros(sample_rate)
    ir[0] = 1.0
    band = ExcitationBand(low_hz=30.0, high_hz=18000.0, source="sweep settings")
    fr = frequency_response(ir, sample_rate, excitation_band=band, smoothing_fraction=0)
    assert fr.excitation_band is band
    assert fr.to_dict(include_curves=False)["excitation_band"]["low_hz"] == 30.0
