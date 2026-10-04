"""Small, locally trained decay-fit initializer; NumPy inference only.

This independently trained network proposes parameters for ``multi_decay``.
It never supplies the reported acoustic parameters directly: the constrained
physical fit and its rejection checks still have to succeed. Conceptual
references and the synthetic training domain are in docs/LOCAL_DECAY_MODEL.md.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from functools import lru_cache
from importlib.resources import files
from typing import Any

import numpy as np

from roomscope.models.audio import FloatArray

MODEL_ID = "roomscope-decay-initializer-v1"
MODEL_PARAMETERS = 2245
MODEL_RESOURCE = "model_data/decay_initializer_v1.json"
INPUT_POINTS = 64
INPUT_CLIP_DB = 100.0


class DecayModelError(ValueError):
    """An unavailable, incompatible or malformed local initializer."""


@dataclass(frozen=True)
class DecayModelSeed:
    #: Fast/slow times in seconds, then instantaneous fast/slow power and
    #: stationary noise power, all powers relative to the first observed block.
    values: tuple[float, float, float, float, float]
    model_id: str
    parameter_count: int
    sha256: str


def decay_features(block_power: FloatArray) -> FloatArray:
    """64 log-power observations on the normalized record timeline.

    The source values are non-overlapping block averages. Interpolation acts
    on dB values at block centres; this is also the training preprocessing.
    """
    power = np.asarray(block_power, dtype=np.float64)
    if power.ndim != 1 or power.size < 4 or not np.all(np.isfinite(power)):
        raise DecayModelError("local decay model needs at least four finite power blocks")
    if np.any(power < 0) or power[0] <= 0:
        raise DecayModelError("local decay model needs non-negative power and a positive start")
    level = 10.0 * np.log10(np.maximum(power / power[0], 1e-10))
    centres = (np.arange(power.size, dtype=np.float64) + 0.5) / power.size
    target = (np.arange(INPUT_POINTS, dtype=np.float64) + 0.5) / INPUT_POINTS
    return np.asarray(
        np.clip(np.interp(target, centres, level), -INPUT_CLIP_DB, 0.0) / INPUT_CLIP_DB,
        dtype=np.float64,
    )


def _matrix(payload: dict[str, Any], key: str, shape: tuple[int, ...]) -> FloatArray:
    try:
        value = np.asarray(payload[key], dtype=np.float64)
    except (KeyError, TypeError, ValueError) as exc:
        raise DecayModelError(f"local decay model has invalid {key}") from exc
    if value.shape != shape or not np.all(np.isfinite(value)):
        raise DecayModelError(f"local decay model has invalid {key}: expected finite shape {shape}")
    value.setflags(write=False)
    return value


@dataclass(frozen=True)
class _Network:
    input_mean: FloatArray
    input_scale: FloatArray
    output_mean: FloatArray
    output_scale: FloatArray
    hidden_weight: FloatArray
    hidden_bias: FloatArray
    output_weight: FloatArray
    output_bias: FloatArray
    sha256: str


@lru_cache(maxsize=1)
def _load_network() -> _Network:
    try:
        raw = files("roomscope").joinpath(MODEL_RESOURCE).read_bytes()
        if len(raw) > 1_000_000:
            raise DecayModelError("local decay model exceeds its 1 MB artifact limit")
        payload = json.loads(raw)
    except (OSError, ValueError) as exc:
        raise DecayModelError(f"cannot load local decay model: {exc}") from exc
    if not isinstance(payload, dict):
        raise DecayModelError("local decay model must be a JSON object")
    if (
        payload.get("format_version") != 1
        or payload.get("model_id") != MODEL_ID
        or payload.get("architecture") != [64, 32, 5]
        or payload.get("parameter_count") != MODEL_PARAMETERS
        or payload.get("feature_format") != "normalized-block-log-power-v1"
        or payload.get("output_format") != "log-duration-times-and-relative-power-v1"
    ):
        raise DecayModelError("local decay model metadata is incompatible with this initializer")
    network = _Network(
        input_mean=_matrix(payload, "input_mean", (64,)),
        input_scale=_matrix(payload, "input_scale", (64,)),
        output_mean=_matrix(payload, "output_mean", (5,)),
        output_scale=_matrix(payload, "output_scale", (5,)),
        hidden_weight=_matrix(payload, "hidden_weight", (64, 32)),
        hidden_bias=_matrix(payload, "hidden_bias", (32,)),
        output_weight=_matrix(payload, "output_weight", (32, 5)),
        output_bias=_matrix(payload, "output_bias", (5,)),
        sha256=hashlib.sha256(raw).hexdigest(),
    )
    if np.any(network.input_scale <= 0) or np.any(network.output_scale <= 0):
        raise DecayModelError("local decay model normalization scales must be positive")
    return network


def neural_initial_guess(block_power: FloatArray, block_duration_s: float) -> DecayModelSeed:
    """Predict a bounded seed for an exact block-average exponential fit.

    Times scale with the duration covered by the power blocks. Parameter
    ordering and every numerical prediction are checked again by the fitter.
    Loading reads one bundled JSON file; no audio, network or subprocess runs.
    """
    if not np.isfinite(block_duration_s) or block_duration_s <= 0:
        raise DecayModelError("local decay model block duration must be positive and finite")
    features = decay_features(block_power)
    network = _load_network()
    inputs = (features - network.input_mean) / network.input_scale
    hidden = np.tanh(inputs @ network.hidden_weight + network.hidden_bias)
    output = hidden @ network.output_weight + network.output_bias
    logs = output * network.output_scale + network.output_mean
    if not np.all(np.isfinite(logs)):
        raise DecayModelError("local decay model produced non-finite parameters")
    values = np.exp(np.clip(logs, -25.0, 3.0))
    duration = block_duration_s * np.asarray(block_power).size
    fast, slow = float(values[0] * duration), float(values[1] * duration)
    fast_power, slow_power = float(values[2]), float(values[3])
    if fast > slow:
        fast, slow = slow, fast
        fast_power, slow_power = slow_power, fast_power
    fast = float(np.clip(fast, 0.01 * duration, 2.0 * duration))
    slow = float(np.clip(slow, max(1.01 * fast, 0.02 * duration), 3.0 * duration))
    return DecayModelSeed(
        values=(fast, slow, fast_power, slow_power, float(values[4])),
        model_id=MODEL_ID,
        parameter_count=MODEL_PARAMETERS,
        sha256=network.sha256,
    )
