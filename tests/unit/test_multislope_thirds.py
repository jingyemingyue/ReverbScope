"""One-third-octave decay analysis with the single/double-slope fit.

``AnalysisSettings.third_octave_decay`` (opt-in) adds the IEC 61260-1
one-third-octave bands inside the octave bands to the decay result. The
synthetic decays are those of ``test_multislope.py`` (Gaussian noise with one
or two exponential envelopes and a floor 75 dB down); the tolerances are
regression choices for these fixed seeds, not accuracy claims (methodology
§3c gives the Monte Carlo the thresholds were checked with).
"""

from __future__ import annotations

import json
import math
from dataclasses import replace

import numpy as np
import pytest

from reverbscope.core.decay import (
    analyze_band,
    analyze_third_octave_decay,
    decay_lead_in_s,
    third_octave_decay_bands,
    third_octave_lead_in_s,
)
from reverbscope.core.filters import (
    OCTAVE_RATIO,
    apply_bandpass,
    bandpass_sos,
    iec_band,
    third_octave_bands_of,
    third_octave_nominal_hz,
)
from reverbscope.errors import ConfigurationError
from reverbscope.models.configuration import AnalysisSettings
from reverbscope.models.result import AnalysisResult, BandDecay, Validity
from reverbscope.models.result_load import decay_result_from_dict
from tests.unit.test_multislope import LEAD, RATE, decay, expected_ratio_db

THIRDS_50_TO_10K = [
    "50 Hz", "63 Hz", "80 Hz", "100 Hz", "125 Hz", "160 Hz", "200 Hz", "250 Hz", "315 Hz",
    "400 Hz", "500 Hz", "630 Hz", "800 Hz", "1 kHz", "1.25 kHz", "1.6 kHz", "2 kHz",
    "2.5 kHz", "3.15 kHz", "4 kHz", "5 kHz", "6.3 kHz", "8 kHz", "10 kHz",
]  # fmt: skip


def third_fit(signal: np.ndarray, nominal_hz: float) -> BandDecay:
    """One one-third-octave band through the public per-band analysis."""
    band = iec_band(nominal_hz, 3)
    filtered = apply_bandpass(signal, bandpass_sos(band, RATE), time_reversed=True)
    return analyze_band(filtered, RATE, band, noise_margin_db=10.0, direct_index=LEAD)


def coupled_impulse_response() -> np.ndarray:
    signal = decay(0.4, 1.6, -25.0, seed=8)
    signal[LEAD] = 4.0 * math.sqrt(float(np.sum(signal**2)))
    return signal


# --- bands --------------------------------------------------------------------


def test_the_default_octaves_give_the_iec_thirds_from_50_hz_to_10_khz() -> None:
    bands = third_octave_decay_bands(AnalysisSettings())
    assert [b.label for b in bands] == THIRDS_50_TO_10K
    for band in bands:
        # Base-10 one-third-octave edges around the exact mid-band frequency.
        assert band.high_hz / band.low_hz == pytest.approx(OCTAVE_RATIO ** (1 / 3))
        assert band.center_hz == pytest.approx(iec_band(band.label_hz, 3).center_hz)
    # Each octave holds exactly its three thirds.
    octave = iec_band(1000.0, 1)
    inside = [
        b
        for b in bands
        if octave.low_hz * 0.999 <= b.low_hz and b.high_hz <= octave.high_hz * 1.001
    ]
    assert [b.label for b in inside] == ["800 Hz", "1 kHz", "1.25 kHz"]


def test_third_octave_nominal_frequencies_follow_annex_e() -> None:
    assert [third_octave_nominal_hz(i) for i in range(-13, -7)] == [50, 63, 80, 100, 125, 160]
    assert third_octave_nominal_hz(-15) == 31.5
    assert third_octave_nominal_hz(13) == 20000.0
    assert [b.label for b in third_octave_bands_of((125.0, 125.0))] == [
        "100 Hz",
        "125 Hz",
        "160 Hz",
    ]


def test_third_octave_lead_in_covers_the_narrowest_third() -> None:
    settings = AnalysisSettings()
    narrowest = min(b.bandwidth_hz for b in third_octave_decay_bands(settings))
    assert third_octave_lead_in_s(settings) == pytest.approx(5.0 / narrowest)
    assert third_octave_lead_in_s(settings) > decay_lead_in_s(settings)


def test_the_setting_is_off_by_default_and_must_be_a_flag() -> None:
    assert AnalysisSettings().third_octave_decay is False
    # A settings file written before the option loads with it off.
    data = AnalysisSettings().to_dict()
    del data["third_octave_decay"]
    assert AnalysisSettings.from_dict(data).third_octave_decay is False
    on = AnalysisSettings.from_dict({**data, "third_octave_decay": True})
    assert on.third_octave_decay is True
    with pytest.raises(ConfigurationError, match="third_octave_decay"):
        AnalysisSettings.from_dict({**data, "third_octave_decay": "yes"})


# --- the fit in narrow bands ----------------------------------------------------


@pytest.mark.parametrize("nominal", [50.0, 63.0, 80.0, 100.0])
def test_double_slope_is_recovered_in_low_third_octave_bands(nominal: float) -> None:
    """50-100 Hz thirds (B = 12-23 Hz): T1 = 1 s, T2 = 3 s, slow part -25 dB.
    T1 is less certain than in an octave band (B*T1 = 12-23), hence 35 %."""
    fit = third_fit(decay(1.0, 3.0, -25.0, seed=3), nominal).multi_slope
    assert fit is not None
    assert fit.validity is Validity.VALID
    assert fit.selected_slopes == 2
    model = fit.selected
    assert model is not None
    assert model.decay_times_s[0] == pytest.approx(1.0, rel=0.35)
    assert model.decay_times_s[1] == pytest.approx(3.0, rel=0.10)
    ratio = model.amplitudes_db[1] - model.amplitudes_db[0]
    assert ratio == pytest.approx(expected_ratio_db(1.0, 3.0, -25.0), abs=3.0)
    assert fit.knee_time_s is not None and fit.fit_start_s is not None
    assert fit.fit_start_s < fit.knee_time_s


@pytest.mark.parametrize("nominal", [250.0, 1000.0, 4000.0])
def test_double_slope_is_recovered_in_mid_third_octave_bands(nominal: float) -> None:
    fit = third_fit(decay(0.4, 1.6, -25.0, seed=3), nominal).multi_slope
    assert fit is not None
    assert fit.validity is Validity.VALID
    assert fit.selected_slopes == 2
    model = fit.selected
    assert model is not None
    assert model.decay_times_s[0] == pytest.approx(0.4, rel=0.15)
    assert model.decay_times_s[1] == pytest.approx(1.6, rel=0.10)
    ratio = model.amplitudes_db[1] - model.amplitudes_db[0]
    assert ratio == pytest.approx(expected_ratio_db(0.4, 1.6, -25.0), abs=4.5)


@pytest.mark.parametrize("nominal", [50.0, 63.0, 80.0, 100.0, 250.0, 1000.0, 4000.0])
@pytest.mark.parametrize("t60", [0.8, 1.5, 3.0])
def test_single_slope_is_not_split_in_third_octave_bands(nominal: float, t60: float) -> None:
    fit = third_fit(decay(t60, seed=1), nominal).multi_slope
    assert fit is not None
    assert fit.validity is Validity.VALID
    assert fit.selected_slopes == 1
    model = fit.selected
    assert model is not None
    assert model.decay_times_s[0] == pytest.approx(t60, rel=0.15)


def test_low_third_octave_bands_rarely_split_a_short_single_slope() -> None:
    """The false-split gate where it is weakest: 50, 63, 80 and 100 Hz thirds
    with decays of B*T of about 7-9 (0.8, 0.5, 0.4 and 0.3 s). The EDC of a
    band this narrow fluctuates by several dB; the thresholds are those of
    the octave bands (methodology §3c). Documented limit: at most 10 of 96
    VALID two-slope selections (7 of 96 when written; the 63 Hz octave test
    allows 2 of 24)."""
    split = 0
    for nominal, t60 in ((50.0, 0.8), (63.0, 0.5), (80.0, 0.4), (100.0, 0.3)):
        for seed in range(24):
            fit = third_fit(decay(t60, seed=seed), nominal).multi_slope
            assert fit is not None
            if fit.selected_slopes == 2 and fit.validity is Validity.VALID:
                split += 1
    assert split <= 10


def test_a_fast_slope_shorter_than_the_filter_is_unreliable_in_a_low_third() -> None:
    # 50 Hz third (B = 11.6 Hz), T = 0.25 s: B*T1 = 2.9 < 4.
    fit = third_fit(decay(0.25, noise_db=-90.0, seed=7, seconds=0.8), 50.0).multi_slope
    assert fit is not None
    if fit.selected_slopes is not None:
        assert fit.validity is Validity.UNRELIABLE
        assert fit.reason is not None and "B*T1" in fit.reason


# --- the analysis path ----------------------------------------------------------


def test_analyze_third_octave_decay_returns_every_band_with_a_fit() -> None:
    signal = coupled_impulse_response()
    lead = round(third_octave_lead_in_s(AnalysisSettings()) * RATE)
    padded = np.concatenate([np.zeros(lead - LEAD), signal])
    bands = analyze_third_octave_decay(padded, RATE, AnalysisSettings(), direct_index=lead)
    assert [b.band_label for b in bands] == THIRDS_50_TO_10K
    assert all(b.multi_slope is not None for b in bands)
    assert all(b.mid_band_hz is not None for b in bands)
    # The 1 kHz third finds the coupled decay of the synthetic room.
    one_k = next(b for b in bands if b.band_label == "1 kHz")
    assert one_k.multi_slope is not None and one_k.multi_slope.selected_slopes == 2


def _analyze(settings: AnalysisSettings, **kwargs: object) -> AnalysisResult:
    from reverbscope.core.pipeline import analyze_impulse_response
    from reverbscope.models.audio import AudioSignal

    return analyze_impulse_response(
        AudioSignal(coupled_impulse_response(), RATE),
        settings,
        **kwargs,  # type: ignore[arg-type]
    )


def test_octave_results_are_identical_with_or_without_thirds() -> None:
    """The opt-in adds bands; the octave and broadband numbers, the notes and
    every other part of the result stay bit-identical."""
    off = _analyze(AnalysisSettings(), excitation_band=(20.0, 20_000.0)).to_dict()
    on_result = _analyze(
        AnalysisSettings(third_octave_decay=True), excitation_band=(20.0, 20_000.0)
    )
    on = on_result.to_dict()
    assert "third_octave_bands" not in off["decay"]
    thirds = on["decay"].pop("third_octave_bands")
    assert [b["band_label"] for b in thirds] == THIRDS_50_TO_10K
    for data in (off, on):
        data.pop("created_at", None)
        data["analysis_settings"].pop("third_octave_decay")
    assert on == off


def test_thirds_follow_the_unreliable_and_not_computed_rules() -> None:
    result = _analyze(AnalysisSettings(third_octave_decay=True), excitation_band=(20.0, 20_000.0))
    thirds = result.decay.third_octave_bands
    assert thirds is not None
    marked = result.decay.with_all_unreliable("clipped")
    assert marked.third_octave_bands is not None
    assert all(
        b.t30.validity is not Validity.VALID
        and (b.multi_slope is None or b.multi_slope.validity is not Validity.VALID)
        for b in marked.third_octave_bands
    )
    # An imported response without a declared band: nothing is computed,
    # in the thirds either.
    undeclared = _analyze(AnalysisSettings(third_octave_decay=True))
    assert undeclared.decay.third_octave_bands is not None
    assert all(
        b.t30.validity is Validity.NOT_COMPUTED and b.multi_slope is None
        for b in undeclared.decay.third_octave_bands
    )


def test_thirds_outside_the_excitation_have_no_numbers() -> None:
    result = _analyze(AnalysisSettings(third_octave_decay=True), excitation_band=(90.0, 20_000.0))
    thirds = {b.band_label: b for b in result.decay.third_octave_bands or ()}
    assert thirds["50 Hz"].t30.validity is Validity.OUTSIDE_EXCITATION
    assert thirds["50 Hz"].multi_slope is None
    assert thirds["125 Hz"].t30.validity is not Validity.OUTSIDE_EXCITATION


def test_round_trip_schema_and_older_files() -> None:
    from jsonschema import Draft202012Validator

    from reverbscope.schemas import load_schema

    result = _analyze(AnalysisSettings(third_octave_decay=True), excitation_band=(20.0, 20_000.0))
    payload = json.loads(json.dumps(result.to_dict()))
    validator = Draft202012Validator(load_schema("result"))
    validator.validate(payload)
    loaded = decay_result_from_dict(payload["decay"])
    assert loaded.third_octave_bands is not None
    assert [b.to_dict() for b in loaded.third_octave_bands] == payload["decay"][
        "third_octave_bands"
    ]
    # Without curves too.
    validator.validate(json.loads(json.dumps(result.to_dict(include_curves=False))))
    # A file without the key (the default, or written before it existed).
    del payload["decay"]["third_octave_bands"]
    validator.validate(payload)
    assert decay_result_from_dict(payload["decay"]).third_octave_bands is None
    payload["decay"]["third_octave_bands"] = None
    validator.validate(payload)
    assert decay_result_from_dict(payload["decay"]).third_octave_bands is None
    # Not a list: refused, as other malformed records are.
    from reverbscope.errors import SessionError

    payload["decay"]["third_octave_bands"] = {"50 Hz": {}}
    with pytest.raises(SessionError, match="third_octave_bands"):
        decay_result_from_dict(payload["decay"])


def test_a_result_without_thirds_keeps_none_through_replace() -> None:
    result = _analyze(AnalysisSettings(), excitation_band=(20.0, 20_000.0))
    assert result.decay.third_octave_bands is None
    assert replace(result.decay).with_all_unreliable("x").third_octave_bands is None
