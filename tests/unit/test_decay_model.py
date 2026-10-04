"""Local initializer contracts, with analytic powers and damaged JSON only."""

from __future__ import annotations

import copy
import json
from importlib.resources import files
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from roomscope.core import decay_model
from roomscope.models.audio import FloatArray


@pytest.fixture(autouse=True)
def clear_model_cache() -> Any:
    decay_model._load_network.cache_clear()
    yield
    decay_model._load_network.cache_clear()


def _power() -> FloatArray:
    width = 5.0 / 128
    starts = np.arange(128, dtype=np.float64) * width
    power = np.full(128, 10.0 ** (-65.0 / 10.0), dtype=np.float64)
    for time, amplitude in ((0.3, 1.0), (2.0, 10.0 ** (-25.0 / 10.0))):
        beta = 6.0 * np.log(10.0) / time
        power += amplitude * np.exp(-beta * starts) * (-np.expm1(-beta * width)) / (beta * width)
    return power


def test_bundled_network_proposes_a_finite_ordered_seed_for_two_known_decays() -> None:
    seed = decay_model.neural_initial_guess(_power(), 5.0 / 128)
    fast, slow, fast_power, slow_power, noise = seed.values
    assert fast == pytest.approx(0.3, rel=0.3)
    assert slow == pytest.approx(2.0, rel=0.3)
    assert 0 < fast < slow and fast_power > slow_power > noise > 0
    assert seed.model_id == decay_model.MODEL_ID
    assert seed.parameter_count == 2245 and len(seed.sha256) == 64


def test_time_scaling_and_signal_gain_have_the_correct_units() -> None:
    power = _power()
    seed = decay_model.neural_initial_guess(power, 5.0 / 128)
    rescaled = decay_model.neural_initial_guess(power * 10000.0, 10.0 / 128)
    assert rescaled.values[:2] == pytest.approx(np.asarray(seed.values[:2]) * 2.0)
    assert rescaled.values[2:] == pytest.approx(seed.values[2:])
    assert rescaled.sha256 == seed.sha256


@pytest.mark.parametrize(
    "power",
    [[], [1, 2, 3], [0, 0, 0, 0], [1, -1, 1, 1], [1, np.nan, 1, 1], [[1, 1, 1, 1]]],
)
def test_invalid_input_never_produces_an_acoustic_seed(power: object) -> None:
    with pytest.raises(decay_model.DecayModelError):
        decay_model.neural_initial_guess(np.asarray(power, dtype=np.float64), 0.02)


@pytest.mark.parametrize("duration", [0.0, -1.0, np.nan, np.inf])
def test_invalid_block_duration_is_refused(duration: float) -> None:
    with pytest.raises(decay_model.DecayModelError, match="duration"):
        decay_model.neural_initial_guess(_power(), duration)


@pytest.mark.parametrize(
    "damage",
    [
        "version",
        "architecture",
        "shape",
        "missing",
        "nonfinite",
        "zero_scale",
        "not_json",
        "object",
    ],
)
def test_damaged_weights_fail_with_a_local_model_diagnostic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, damage: str
) -> None:
    original = json.loads(files("roomscope").joinpath(decay_model.MODEL_RESOURCE).read_bytes())
    payload = copy.deepcopy(original)
    if damage == "version":
        payload["format_version"] = 999
    elif damage == "architecture":
        payload["architecture"] = [64, 64, 5]
    elif damage == "shape":
        payload["hidden_weight"] = [[1.0]]
    elif damage == "missing":
        del payload["output_bias"]
    elif damage == "nonfinite":
        payload["output_bias"][0] = float("inf")
    elif damage == "zero_scale":
        payload["input_scale"][0] = 0.0
    elif damage == "object":
        payload = []
    resource = tmp_path / decay_model.MODEL_RESOURCE
    resource.parent.mkdir(parents=True)
    resource.write_text("broken" if damage == "not_json" else json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(decay_model, "files", lambda _package: tmp_path)
    with pytest.raises(decay_model.DecayModelError, match="local decay model"):
        decay_model.neural_initial_guess(_power(), 5.0 / 128)


def test_missing_model_is_diagnosed_and_loading_is_cached(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(decay_model, "files", lambda _package: tmp_path)
    with pytest.raises(decay_model.DecayModelError, match="cannot load"):
        decay_model.neural_initial_guess(_power(), 5.0 / 128)
    calls = 0

    def resource(package: str) -> Any:
        nonlocal calls
        calls += 1
        return files(package)

    monkeypatch.setattr(decay_model, "files", resource)
    decay_model.neural_initial_guess(_power(), 5.0 / 128)
    decay_model.neural_initial_guess(_power(), 5.0 / 128)
    assert calls == 1
