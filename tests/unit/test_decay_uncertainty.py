"""Uncertainty of the single/double-slope decay fit (ADR 0006).

Calibration: synthetic responses (Gaussian noise under one or two exponential
envelopes plus a noise floor, ``tests/unit/test_multislope.decay``) with known
decay times, a fresh noise realisation per seed. The 68 % and 95 % intervals
should contain the generating decay times about that often. The bounds below
are wide enough for the seed count here (binomial spread about 0.03) and
narrow enough to catch an interval that is several times too narrow or too
wide. The full study (17 cases x 150 seeds) is in docs/validation/
decay-uncertainty.md.
"""

from __future__ import annotations

import json
import math

import numpy as np
import pytest

from reverbscope.core.decay import analyze_band
from reverbscope.core.filters import apply_bandpass, bandpass_sos, iec_band
from reverbscope.core.multislope import DATA_RATE_FACTOR, Z68, Z95
from reverbscope.errors import SessionError
from reverbscope.models.result import BandDecay, DecaySlopeModel, SlopeUncertainty, Validity
from reverbscope.models.result_load import band_decay_from_dict, slope_uncertainty_from_dict
from tests.unit.test_multislope import LEAD, RATE, decay

#: (T1, T2, late level dB, band centre Hz, fraction): single and double,
#: octave and one-third octave.
CALIBRATION_CASES = [
    (0.6, None, None, 1000.0, 1),
    (1.5, None, None, 500.0, 1),
    (1.0, None, None, 2000.0, 3),
    (0.4, 1.6, -25.0, 1000.0, 1),
    (1.0, 3.0, -25.0, 500.0, 3),
]
SEEDS = range(500, 530)


def _band(signal: np.ndarray, nominal_hz: float, fraction: int) -> BandDecay:
    band = iec_band(nominal_hz, fraction)
    filtered = apply_bandpass(signal, bandpass_sos(band, RATE), time_reversed=True)
    return analyze_band(filtered, RATE, band, noise_margin_db=10.0, direct_index=LEAD)


def _z_scores() -> dict[str, list[float]]:
    """``(log T_hat - log T_true) / sd(log T)`` per case kind."""
    scores: dict[str, list[float]] = {"single": [], "double": []}
    for t1, t2, late, nominal, fraction in CALIBRATION_CASES:
        truth = (t1,) if t2 is None else (t1, t2)
        for seed in SEEDS:
            fit = _band(decay(t1, t2, late, seed=seed), nominal, fraction).multi_slope
            assert fit is not None
            model = fit.model(len(truth))
            assert model is not None and model.uncertainty is not None
            for value, sd, true in zip(
                model.decay_times_s, model.uncertainty.decay_times_sd_s, truth, strict=True
            ):
                scores["single" if t2 is None else "double"].append(
                    (math.log(value) - math.log(true)) / (sd / value)
                )
    return scores


@pytest.fixture(scope="module")
def z_scores() -> dict[str, list[float]]:
    return _z_scores()


@pytest.mark.parametrize("kind", ["single", "double"])
def test_intervals_cover_the_generating_decay_times(
    z_scores: dict[str, list[float]], kind: str
) -> None:
    z = np.abs(np.array(z_scores[kind]))
    covered_68 = float(np.mean(z <= Z68))
    covered_95 = float(np.mean(z <= Z95))
    assert 0.58 <= covered_68 <= 0.88, covered_68
    assert 0.89 <= covered_95 <= 1.0, covered_95


def test_the_analysis_term_alone_is_far_too_narrow() -> None:
    """Xiang & Sü Gül's posterior width at the decay data rate describes how
    precisely one curve fixes T, not the spread of the random decay: on its
    own it would cover far less than 95 % (why the stochastic term exists)."""
    misses = 0
    count = 0
    for seed in SEEDS:
        fit = _band(decay(1.0, seed=seed), 1000.0, 1).multi_slope
        assert fit is not None
        model = fit.model(1)
        assert model is not None and model.uncertainty is not None
        spread = model.uncertainty
        assert spread.decay_times_analysis_sd_s[0] < spread.decay_times_sd_s[0]
        z = math.log(model.decay_times_s[0]) / (
            spread.decay_times_analysis_sd_s[0] / model.decay_times_s[0]
        )
        misses += abs(z) > Z95
        count += 1
    assert misses / count > 0.3


def test_data_rate_reproduces_the_papers_choices() -> None:
    """Xiang & Sü Gül (2025): 2.18 s at 50 Hz (Ozawa Hall, Table I's lowest
    adequate rate) and 11.5 s at 10 Hz (Süleymaniye Mosque)."""
    ozawa, mosque = DATA_RATE_FACTOR / 2.18, DATA_RATE_FACTOR / 11.5
    assert ozawa == pytest.approx(50.0, rel=0.05)
    assert mosque == pytest.approx(10.0, rel=0.05)


def test_double_slope_uncertainty_fields() -> None:
    fit = _band(decay(0.4, 1.6, -25.0, seed=3), 1000.0, 1).multi_slope
    assert fit is not None and fit.selected_slopes == 2 and fit.validity is Validity.VALID
    model = fit.selected
    assert model is not None and model.uncertainty is not None
    u = model.uncertainty
    assert len(u.decay_times_sd_s) == 2 and len(u.amplitudes_sd_db) == 2
    for value, sd, (low68, high68), (low95, high95) in zip(
        model.decay_times_s,
        u.decay_times_sd_s,
        u.decay_times_ci68_s,
        u.decay_times_ci95_s,
        strict=True,
    ):
        assert sd > 0.0
        assert low95 < low68 < value < high68 < high95
        # Log-normal: the interval is wider above than below.
        assert high95 - value > value - low95
    assert u.knee_time_sd_s is not None and u.knee_time_sd_s > 0.0
    assert u.noise_sd_db is not None
    assert u.data_rate_hz == pytest.approx(DATA_RATE_FACTOR / model.decay_times_s[0])
    one = fit.model(1)
    assert one is not None and one.uncertainty is not None
    assert one.uncertainty.knee_time_sd_s is None


def test_uncertainty_does_not_change_the_fit() -> None:
    """The ISO metrics and the fitted numbers are those of the fit alone."""
    from reverbscope.core import multislope

    signal = _band(decay(0.4, 1.6, -25.0, seed=3), 1000.0, 1)
    original = multislope.slope_uncertainty
    try:
        multislope.slope_uncertainty = lambda *args, **kwargs: None  # type: ignore[assignment]
        bare = _band(decay(0.4, 1.6, -25.0, seed=3), 1000.0, 1)
    finally:
        multislope.slope_uncertainty = original
    assert bare.t30.seconds == signal.t30.seconds and bare.edt.seconds == signal.edt.seconds
    assert bare.multi_slope is not None and signal.multi_slope is not None
    for with_u, without in zip(signal.multi_slope.models, bare.multi_slope.models, strict=True):
        assert without.uncertainty is None and with_u.uncertainty is not None
        assert with_u.decay_times_s == without.decay_times_s
        assert with_u.amplitudes == without.amplitudes
        assert with_u.bic == without.bic


def test_round_trip_older_files_and_bad_payloads() -> None:
    band = _band(decay(0.4, 1.6, -25.0, seed=3), 1000.0, 1)
    data = json.loads(json.dumps(band.to_dict()))
    loaded = band_decay_from_dict(data)
    assert loaded.multi_slope is not None and band.multi_slope is not None
    assert loaded.multi_slope.to_dict() == band.multi_slope.to_dict()
    # A file written before the uncertainty existed: no key, ``None``.
    for model in data["multi_slope"]["models"]:
        del model["uncertainty"]
    older = band_decay_from_dict(data).multi_slope
    assert older is not None and all(m.uncertainty is None for m in older.models)
    assert slope_uncertainty_from_dict(None, 1) is None
    good = band.multi_slope.models[1].uncertainty
    assert good is not None
    broken = good.to_dict()
    broken["decay_times_sd_s"] = [0.1]
    with pytest.raises(SessionError):
        slope_uncertainty_from_dict(broken, 2)


def test_a_parameter_at_its_bound_has_no_uncertainty() -> None:
    """No Gaussian approximation at a bound: ``None`` rather than a number."""
    from reverbscope.core.multislope import _Fit, slope_uncertainty

    t = np.linspace(0.05, 1.0, 100)
    jac = np.ones((100, 3))
    jac[:, 0] = 0.0  # log T at its bound
    fit = _Fit(
        decay_times_s=(0.5,),
        amplitudes=(1.0,),
        noise_term=1e-6,
        rss_db2=1.0,
        max_miss_db=0.1,
        converged=True,
        residuals_db=np.full(100, 0.1),
        log_params=np.log(np.array([0.5, 1.0, 1e-6])),
        jacobian_db=jac,
        order=(0,),
    )
    assert slope_uncertainty(fit, t, 1.2, 700.0) is None


def test_model_without_uncertainty_still_serialises() -> None:
    model = DecaySlopeModel(
        slope_count=1,
        decay_times_s=(1.0,),
        amplitudes=(1.0,),
        noise_term=1e-6,
        bic=0.0,
        rms_residual_db=0.1,
    )
    assert model.to_dict()["uncertainty"] is None
    spread = SlopeUncertainty(
        decay_times_sd_s=(0.05,),
        decay_times_ci68_s=((0.95, 1.05),),
        decay_times_ci95_s=((0.9, 1.1),),
        amplitudes_sd_db=(0.2,),
        noise_sd_db=None,
        knee_time_sd_s=None,
        decay_times_analysis_sd_s=(0.01,),
        data_points=120.0,
        data_rate_hz=110.0,
        grid_adequate=False,
    )
    assert slope_uncertainty_from_dict(spread.to_dict(), 1) == spread
