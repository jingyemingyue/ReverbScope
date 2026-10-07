"""Small existing-schema results for health tests; no new DSP fixtures."""

import numpy as np

from reverbscope.models.result import (
    AnalysisResult,
    BandDecay,
    ClippingCheck,
    DecayMetric,
    DecayResult,
    EnergyMetric,
    ExcitationBand,
    FrequencyResponseResult,
    ImpulseResponseResult,
    NoiseResult,
    ReflectionsResult,
    ResonanceResult,
    Validity,
)


def healthy_result() -> AnalysisResult:
    band = BandDecay(
        band_label="broadband",
        center_hz=None,
        low_hz=None,
        high_hz=None,
        noise_floor_db=-60.0,
        peak_to_noise_db=60.0,
        truncation_time_s=0.5,
        edt=DecayMetric("EDT", 0.4, Validity.VALID, (0, -10)),
        t20=DecayMetric("T20", 0.4, Validity.VALID, (-5, -25)),
        t30=DecayMetric("T30", 0.4, Validity.VALID, (-5, -35)),
        rt60_estimate_s=0.4,
        rt60_basis="T30",
        curvature_percent=0.0,
        filter_bt_product=None,
        filter_warning=None,
        edc_time_s=np.array([0.0, 0.2, 0.4]),
        edc_db=np.array([0.0, -30.0, -60.0]),
        c50=EnergyMetric("C50", 5.0, "dB", Validity.VALID),
        c80=EnergyMetric("C80", 8.0, "dB", Validity.VALID),
        d50=EnergyMetric("D50", 75.0, "%", Validity.VALID),
        centre_time=EnergyMetric("Ts", 0.03, "s", Validity.VALID),
    )
    return AnalysisResult(
        created_at="2026-10-07T00:00:00Z",
        sample_rate=48000,
        sweep_settings={},
        analysis_settings={},
        impulse_response=ImpulseResponseResult(
            sample_rate=48000,
            samples=np.array([0.0, 1.0, 0.1, 0.01]),
            direct_sound_index=1,
            pre_delay_samples=1,
            peak_value=1.0,
            valid_length_s=1.5,
            pre_peak_margin_db=40.0,
            direct_sound_confidence="high",
            sweep_start_in_recording_s=1.0,
            excitation_band=ExcitationBand(20.0, 20000.0, "sweep_definition"),
            direct_level_dbfs=-12.0,
        ),
        decay=DecayResult("Lundeby", band, ()),
        frequency_response=FrequencyResponseResult(
            np.array([100.0, 1000.0]), np.zeros(2), np.zeros(2), 3, 0.5
        ),
        noise=NoiseResult("pre-sweep", 0.0, 0.8, -80.0, -70.0, (), None, None),
        reflections=ReflectionsResult(
            0.0, "high", (0.5, 80.0), -20.0, (), analysed_window_ms=(0.5, 80.0)
        ),
        resonances=ResonanceResult(300.0, ()),
        clipping=ClippingCheck(-12.0, 0, 0, False),
    )
