"""Synthetic energy models and rejected inputs; no audio backend is involved."""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from roomscope.core import decay_model
from roomscope.core.multi_decay import fit_multi_decay
from roomscope.models.audio import FloatArray
from roomscope.models.result import Validity

RATE = 48000
DECAY = 6.0 * np.log(10.0)


def _signal(
    times: tuple[float, ...] = (0.3, 2.0),
    weights: tuple[float, ...] = (1.0, 10 ** (-25.0 / 10.0)),
    *,
    noise: float = 1e-7,
    rate: int = RATE,
    duration: float = 3.0,
    seed: int = 42,
    random: bool = True,
) -> FloatArray:
    t = np.arange(round(duration * rate)) / rate
    power = sum(a * np.exp(-DECAY * t / rt) for rt, a in zip(times, weights, strict=True)) + noise
    carrier = np.random.default_rng(seed).normal(size=len(t)) if random else np.ones(len(t))
    return np.asarray(carrier * np.sqrt(power), dtype=np.float64)


@pytest.mark.parametrize("rt", [0.15, 0.6, 2.0])
def test_single_exponential_is_recovered_without_splitting(rt: float) -> None:
    fitted = fit_multi_decay(_signal((rt,), (1.0,), duration=2.0 * rt), RATE)
    assert fitted.validity is Validity.VALID, fitted.reason
    assert len(fitted.components) == 1
    assert fitted.components[0].rt60_s == pytest.approx(rt, rel=0.035)
    assert fitted.components[0].relative_power == 1.0
    assert fitted.components[0].rt60_std_s is not None
    assert fitted.bic_difference is not None and fitted.bic_difference < 10.0


@pytest.mark.parametrize("noise", [1e-8, 1e-6])
def test_double_decay_has_two_times_and_noise_separate_from_iso(noise: float) -> None:
    fitted = fit_multi_decay(_signal(noise=noise, duration=5.0), RATE)
    assert fitted.validity is Validity.VALID, fitted.reason
    assert [c.rt60_s for c in fitted.components] == pytest.approx([0.3, 2.0], rel=0.045)
    assert sum(c.relative_power for c in fitted.components) == pytest.approx(1.0)
    assert fitted.components[1].relative_power == pytest.approx(0.0031523, rel=0.2)
    assert fitted.noise_relative_power is not None and fitted.noise_relative_power > 0.0
    assert fitted.residual_rms_db is not None and fitted.residual_rms_db < 0.4
    assert fitted.bic_difference is not None and fitted.bic_difference > 10.0


def test_unresolved_second_decay_cannot_be_replaced_by_a_biased_single_time() -> None:
    fitted = fit_multi_decay(_signal(noise=10 ** (-45.0 / 10.0), duration=5.0), RATE)
    assert fitted.validity is Validity.UNRELIABLE
    assert not fitted.components
    assert fitted.bic_difference is not None and fitted.bic_difference > 10.0
    assert "second decay is favored" in (fitted.reason or "")


def test_exact_block_average_avoids_bias_for_fast_decay() -> None:
    rt = 0.1
    signal = _signal((rt,), (1.0,), noise=1e-7, duration=0.3, random=False)
    fitted = fit_multi_decay(signal, RATE)
    assert fitted.validity is Validity.VALID, fitted.reason
    assert fitted.components[0].rt60_s == pytest.approx(rt, rel=0.003)


def test_noiseless_exponential_does_not_require_a_noise_floor() -> None:
    fitted = fit_multi_decay(_signal((0.6,), (1.0,), noise=0.0, duration=3.0, random=False), RATE)
    assert fitted.validity is Validity.VALID, fitted.reason
    assert fitted.components[0].rt60_s == pytest.approx(0.6, rel=0.002)


@pytest.mark.parametrize("rate", [8000, 96000])
def test_time_constants_are_independent_of_sample_rate(rate: int) -> None:
    fitted = fit_multi_decay(_signal(rate=rate, random=False), rate)
    assert fitted.validity is Validity.VALID, fitted.reason
    assert [c.rt60_s for c in fitted.components] == pytest.approx([0.3, 2.0], rel=0.003)


def test_selected_segment_excludes_direct_pulse_and_preserves_time_origin() -> None:
    decay = _signal((0.6,), (1.0,), random=False)
    lead = round(0.1 * RATE)
    signal = np.concatenate((np.zeros(lead), decay))
    signal[0] = 100.0
    fitted = fit_multi_decay(signal, RATE, start_index=lead, time_origin_index=lead // 2)
    assert fitted.validity is Validity.VALID, fitted.reason
    assert fitted.fit_start_s == pytest.approx(0.05)
    assert fitted.fit_end_s == pytest.approx(3.05)
    assert fitted.components[0].rt60_s == pytest.approx(0.6, rel=0.003)


def test_amplitude_scaling_cannot_change_component_times() -> None:
    signal = _signal(random=False)
    small = fit_multi_decay(signal * 1e-120, RATE)
    large = fit_multi_decay(signal * 1e150, RATE)
    assert small.validity is large.validity is Validity.VALID
    assert [c.rt60_s for c in small.components] == pytest.approx(
        [c.rt60_s for c in large.components]
    )
    assert small.noise_relative_power == pytest.approx(large.noise_relative_power)


@pytest.mark.parametrize(
    ("signal", "rate", "start", "reason"),
    [
        (np.zeros(1000), RATE, 0, "12 averaged blocks"),
        (np.zeros(RATE), RATE, 0, "no measurable decay"),
        (np.zeros((RATE, 2)), RATE, 0, "finite mono"),
        (np.array([1.0, np.nan]), RATE, 0, "finite mono"),
        (np.array([1.0, np.inf]), RATE, 0, "finite mono"),
        (np.ones(RATE), 0, 0, "positive sample rate"),
        (np.ones(RATE), RATE, -1, "outside"),
        (np.ones(RATE), RATE, RATE, "outside"),
    ],
)
def test_invalid_or_unmeasurable_inputs_have_reasons(
    signal: FloatArray, rate: int, start: int, reason: str
) -> None:
    fitted = fit_multi_decay(signal, rate, start_index=start)
    assert fitted.validity is not Validity.VALID
    assert not fitted.components
    assert reason in (fitted.reason or "")


@pytest.mark.parametrize("rising", [False, True])
def test_stationary_noise_or_rising_energy_cannot_claim_a_decay(rising: bool) -> None:
    t = np.arange(RATE) / RATE
    signal = np.random.default_rng(5).normal(size=RATE)
    if rising:
        signal *= np.exp(2.0 * t)
    fitted = fit_multi_decay(signal, RATE)
    assert fitted.validity is Validity.INSUFFICIENT_RANGE
    assert not fitted.components
    assert "less than 15 dB" in (fitted.reason or "")


def test_a_single_transient_does_not_prove_an_exponential_decay() -> None:
    signal = np.random.default_rng(4).normal(0.0, 1e-5, RATE)
    signal[0] = 1.0
    fitted = fit_multi_decay(signal, RATE)
    assert fitted.validity is not Validity.VALID
    assert not fitted.components


def test_a_time_varying_noise_floor_is_rejected_for_model_mismatch() -> None:
    t = np.arange(3 * RATE) / RATE
    power = np.exp(-DECAY * t / 0.6) + 1e-6 * (1.0 + 20.0 * np.sin(2 * np.pi * 7 * t) ** 16)
    signal = np.random.default_rng(42).normal(size=len(t)) * np.sqrt(power)
    fitted = fit_multi_decay(signal, RATE)
    assert fitted.validity is Validity.UNRELIABLE
    assert not fitted.components
    assert "does not explain" in (fitted.reason or "")


def test_neural_initializer_records_bundled_model_provenance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed = decay_model.DecayModelSeed(
        values=(0.3, 2.0, 1.0, 0.003, 1e-7),
        model_id="synthetic-seed",
        parameter_count=2245,
        sha256="a" * 64,
    )
    monkeypatch.setattr(decay_model, "neural_initial_guess", lambda power, duration: seed)
    fitted = fit_multi_decay(_signal(), RATE, initializer="neural")
    assert fitted.validity is Validity.VALID, fitted.reason
    assert fitted.initializer == "neural"
    assert fitted.initializer_model == "synthetic-seed"
    assert fitted.initializer_parameters == 2245
    assert fitted.initializer_sha256 == "a" * 64
    physical = fit_multi_decay(_signal(), RATE)
    assert [c.rt60_s for c in fitted.components] == pytest.approx(
        [c.rt60_s for c in physical.components], rel=1e-5
    )


@pytest.mark.parametrize("failure", ["missing", "nonfinite"])
def test_failed_local_model_uses_physical_fit_with_explanation(
    monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    def unavailable(power: FloatArray, duration: float) -> decay_model.DecayModelSeed:
        if failure == "missing":
            raise OSError("synthetic missing model fixture")
        return replace(
            decay_model.DecayModelSeed((0.3, 2.0, 1.0, 0.003, 1e-7), "bad", 2245, "a" * 64),
            values=(float("nan"), 2.0, 1.0, 0.003, 1e-7),
        )

    monkeypatch.setattr(decay_model, "neural_initial_guess", unavailable)
    fitted = fit_multi_decay(_signal(), RATE, initializer="neural")
    assert fitted.validity is Validity.VALID, fitted.reason
    assert fitted.initializer == "physical"
    assert fitted.initializer_model is None and fitted.initializer_sha256 is None
    assert "used physical initialization" in (fitted.reason or "")


def test_initializer_name_is_validated() -> None:
    with pytest.raises(ValueError, match="initializer must"):
        fit_multi_decay(np.ones(100), RATE, initializer="unknown")
