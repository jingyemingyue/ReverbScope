"""Known-answer and failure-path tests for the opt-in research methods."""

from __future__ import annotations

import math

import numpy as np
import pytest

from reverbscope.core import bayesian_decay
from reverbscope.core.bayesian_decay import DecaySlope, fit_bayesian_decay
from reverbscope.core.decay import model_based_truncation
from reverbscope.core.modal import _levinson_durbin
from reverbscope.errors import InvalidAudioError
from reverbscope.models.audio import FloatArray


def test_power_decay_t60_is_a_millionfold_energy_drop() -> None:
    slope = DecaySlope(amplitude=1.0, tau_s=0.1)
    assert 10.0 * math.log10(math.exp(-slope.t60_s / slope.tau_s)) == pytest.approx(-60)


@pytest.mark.parametrize("scale", [1e-12, 1.0, 1e12])
def test_single_exponential_fit_preserves_time_and_power_scale(scale: float) -> None:
    rate = 1000
    t = np.arange(1500) / rate
    power = scale * (np.exp(-t * math.log(1e6) / 0.8) + 1e-5)
    result = fit_bayesian_decay(power, rate, max_slopes=1)
    assert result is not None
    assert result.n_slopes == 1
    assert result.slopes[0].t60_s == pytest.approx(0.8, rel=0.01)
    assert result.noise_power == pytest.approx(scale * 1e-5, rel=0.05)


def test_failed_lower_model_order_does_not_shift_the_selected_fit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fit(
        t: FloatArray, power: FloatArray, n_slopes: int
    ) -> tuple[FloatArray, FloatArray, float, float] | None:
        if n_slopes == 1:
            return None
        return np.array([0.8, 0.2]), np.array([0.1, 0.3]), 0.01, 0.1

    monkeypatch.setattr(bayesian_decay, "_fit_n_slopes_gn", fit)
    result = fit_bayesian_decay(np.linspace(1, 0.01, 100), 1000, max_slopes=2)
    assert result is not None
    assert result.n_slopes == 2
    assert len(result.slopes) == 2
    assert math.isinf(result.bic_values[0])


@pytest.mark.parametrize("bad_power", [-np.ones(100), np.full(100, np.nan)])
def test_model_fits_reject_nonphysical_power(bad_power: FloatArray) -> None:
    with pytest.raises(InvalidAudioError):
        fit_bayesian_decay(bad_power, 1000)
    with pytest.raises(InvalidAudioError):
        model_based_truncation(bad_power, 1000)


@pytest.mark.parametrize("max_slopes", [0, 4])
def test_model_order_must_stay_within_the_supported_range(max_slopes: int) -> None:
    with pytest.raises(ValueError, match="max_slopes"):
        fit_bayesian_decay(np.ones(100), 1000, max_slopes=max_slopes)


def test_truncation_model_recovers_an_exponential_and_stationary_floor() -> None:
    rate = 1000
    tau = 0.1
    noise = 1e-4
    t = np.arange(2000) / rate
    result = model_based_truncation(np.exp(-t / tau) + noise, rate)
    assert result is not None
    index, noise_db, fitted_tau = result
    assert index == pytest.approx(-tau * math.log(noise * 10) * rate, abs=2)
    assert noise_db == pytest.approx(-40, abs=0.1)
    assert fitted_tau == pytest.approx(tau, rel=0.01)


def test_linear_prediction_coefficients_solve_the_yule_walker_system() -> None:
    # An AR(1) process with coefficient 0.8 has r[k] = r[0] * 0.8**k.
    # With the module's polynomial convention the coefficient is -0.8.
    autocorrelation = 0.8 ** np.arange(5)
    coefficients = _levinson_durbin(autocorrelation, 4)
    assert coefficients == pytest.approx([-0.8, 0, 0, 0], abs=1e-10)
