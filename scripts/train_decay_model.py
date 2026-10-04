"""Train RoomScope's tiny initializer on analytic synthetic block powers.

No recorded audio, third-party data, weights or ML framework are used.
Run with OPENBLAS_NUM_THREADS=1 for predictable CPU resource use. The
normalization and generator are versioned with the reviewable JSON artifact.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from roomscope.core.decay_model import (
    MODEL_ID,
    MODEL_PARAMETERS,
    decay_features,
)
from roomscope.models.audio import FloatArray

DEFAULT_SEED = 20261004
K = 6.0 * np.log(10.0)
ROOT = Path(__file__).resolve().parents[1]


def _block_component(time: float, times: FloatArray, width: float) -> FloatArray:
    beta = K / time
    average = -np.expm1(-beta * width) / (beta * width)
    return np.asarray(average * np.exp(-beta * times), dtype=np.float64)


def synthetic_training_data(count: int, seed: int) -> tuple[FloatArray, FloatArray]:
    """Distinct random mixtures with dimensionless times and known parameters.

    Synthetic block fluctuations follow a chi-square law: a mean of squares
    of independent Gaussian pressure samples. The degrees of freedom vary
    to cover both very clean and noticeably fluctuating block powers.
    """
    rng = np.random.default_rng(seed)
    inputs = np.empty((count, 64), dtype=np.float64)
    targets = np.empty((count, 5), dtype=np.float64)
    for index in range(count):
        fast = np.exp(rng.uniform(np.log(0.025), np.log(0.5)))
        slow = np.exp(rng.uniform(np.log(max(1.8 * fast, 0.10)), np.log(min(10 * fast, 2.0))))
        slow_amplitude = 10.0 ** rng.uniform(-3.0, 0.0)
        floor = 10.0 ** rng.uniform(-9.0, -2.0)
        blocks = int(rng.choice((32, 64, 96, 128, 192)))
        width = 1.0 / blocks
        times = np.arange(blocks, dtype=np.float64) * width

        power = (
            _block_component(fast, times, width)
            + slow_amplitude * _block_component(slow, times, width)
            + floor
        )
        degrees = np.exp(rng.uniform(np.log(32.0), np.log(5000.0)))
        observed = power * rng.chisquare(degrees, blocks) / degrees
        inputs[index] = decay_features(observed)
        targets[index] = np.log(
            (fast, slow, 1.0 / observed[0], slow_amplitude / observed[0], floor / observed[0])
        )
    return inputs, targets


def train(inputs: FloatArray, targets: FloatArray, *, seed: int, epochs: int) -> dict[str, object]:
    """One tanh hidden layer, linear log-parameter outputs, minibatch Adam."""
    rng = np.random.default_rng(seed)
    input_mean = np.mean(inputs, axis=0)
    input_scale = np.maximum(np.std(inputs, axis=0), 0.025)
    output_mean = np.mean(targets, axis=0)
    output_scale = np.maximum(np.std(targets, axis=0), 0.1)
    features = (inputs - input_mean) / input_scale
    labels = (targets - output_mean) / output_scale
    arrays = [
        rng.normal(0, 1 / np.sqrt(64), (64, 32)),
        np.zeros(32, dtype=np.float64),
        rng.normal(0, 1 / np.sqrt(32), (32, 5)),
        np.zeros(5, dtype=np.float64),
    ]
    first = [np.zeros_like(value) for value in arrays]
    second = [np.zeros_like(value) for value in arrays]
    step = 0
    for epoch in range(epochs):
        order = rng.permutation(features.shape[0])
        learning_rate = 0.003 * (0.2 + 0.8 * (1.0 - epoch / epochs))
        for offset in range(0, order.size, 256):
            batch = order[offset : offset + 256]
            x, y = features[batch], labels[batch]
            hidden = np.tanh(x @ arrays[0] + arrays[1])
            prediction = hidden @ arrays[2] + arrays[3]
            delta = 2.0 * (prediction - y) / (batch.size * 5)
            hidden_delta = (delta @ arrays[2].T) * (1.0 - hidden**2)
            gradients = [
                x.T @ hidden_delta + 1e-5 * arrays[0],
                np.sum(hidden_delta, axis=0),
                hidden.T @ delta + 1e-5 * arrays[2],
                np.sum(delta, axis=0),
            ]
            step += 1
            for index, gradient in enumerate(gradients):
                first[index] = 0.9 * first[index] + 0.1 * gradient
                second[index] = 0.999 * second[index] + 0.001 * gradient**2
                corrected_first = first[index] / (1.0 - 0.9**step)
                corrected_second = second[index] / (1.0 - 0.999**step)
                arrays[index] -= (
                    learning_rate * corrected_first / (np.sqrt(corrected_second) + 1e-8)
                )

    def rounded(value: FloatArray) -> list[object]:
        return np.round(value, 10).tolist()  # type: ignore[no-any-return]

    return {
        "format_version": 1,
        "model_id": MODEL_ID,
        "architecture": [64, 32, 5],
        "parameter_count": MODEL_PARAMETERS,
        "feature_format": "normalized-block-log-power-v1",
        "output_format": "log-duration-times-and-relative-power-v1",
        "training": {
            "generator": "analytic-block-exponential-chi-square-v1",
            "seed": seed,
            "samples": int(inputs.shape[0]),
            "epochs": epochs,
            "optimizer": "minibatch Adam, mean squared standardized log-parameter loss",
            "data_source": "independently generated analytic mixtures; no recordings",
            "license": "Apache-2.0 (RoomScope's own synthetic training and weights)",
            "fast_time_over_duration": [0.025, 0.5],
            "slow_time_over_duration": [0.10, 2.0],
            "slow_to_fast_power": [0.001, 1.0],
            "noise_to_fast_power": [1e-9, 0.01],
            "blocks": [32, 64, 96, 128, 192],
            "independent_gaussian_degrees_per_block": [32, 5000],
            "pressure_distribution": "zero-mean Gaussian with stationary noise",
            "limitations": "initializer only; no real-room, modal, transient or device evidence",
        },
        "input_mean": rounded(input_mean),
        "input_scale": rounded(input_scale),
        "output_mean": rounded(output_mean),
        "output_scale": rounded(output_scale),
        "hidden_weight": rounded(arrays[0]),
        "hidden_bias": rounded(arrays[1]),
        "output_weight": rounded(arrays[2]),
        "output_bias": rounded(arrays[3]),
    }


def evaluate(payload: dict[str, object], *, seed: int, samples: int = 1000) -> dict[str, object]:
    """Held-out generator seed; raw prediction errors, before any physical fit."""
    inputs, expected = synthetic_training_data(samples, seed)
    features = (inputs - np.asarray(payload["input_mean"])) / np.asarray(payload["input_scale"])
    hidden = np.tanh(features @ np.asarray(payload["hidden_weight"]) + payload["hidden_bias"])
    logs = (hidden @ np.asarray(payload["output_weight"]) + payload["output_bias"]) * np.asarray(
        payload["output_scale"]
    ) + np.asarray(payload["output_mean"])
    time_error_percent = 100.0 * np.abs(np.exp(logs[:, :2] - expected[:, :2]) - 1.0)
    noise_error_db = 10.0 / np.log(10.0) * np.abs(logs[:, 4] - expected[:, 4])
    return {
        "held_out_seed": seed,
        "samples": samples,
        "raw_fast_time_median_error_percent": float(np.median(time_error_percent[:, 0])),
        "raw_slow_time_median_error_percent": float(np.median(time_error_percent[:, 1])),
        "raw_fast_time_p90_error_percent": float(np.percentile(time_error_percent[:, 0], 90)),
        "raw_slow_time_p90_error_percent": float(np.percentile(time_error_percent[:, 1], 90)),
        "raw_noise_median_error_db": float(np.median(noise_error_db)),
        "scope": "synthetic held-out initial guesses; not accuracy of final acoustic estimates",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out", type=Path, default=ROOT / "src/roomscope/model_data/decay_initializer_v1.json"
    )
    parser.add_argument("--samples", type=int, default=12000)
    parser.add_argument("--epochs", type=int, default=120)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    args = parser.parse_args()
    if args.samples < 256 or args.epochs < 1:
        parser.error("--samples must be >= 256 and --epochs must be >= 1")
    inputs, targets = synthetic_training_data(args.samples, args.seed)
    payload = train(inputs, targets, seed=args.seed, epochs=args.epochs)
    validation = evaluate(payload, seed=args.seed + 1)
    payload["held_out_initializer_evaluation"] = validation
    raw = (json.dumps(payload, indent=2, allow_nan=False) + "\n").encode("utf-8")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(raw)
    print(
        json.dumps(
            {
                "artifact": str(args.out),
                "bytes": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
                **validation,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
