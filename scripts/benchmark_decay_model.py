"""Compare physical and neural-initialized decay fits against synthetic truth.

This uses independently sampled Gaussian impulse responses, not the analytic
chi-square blocks used for network training. There is no audio backend. The
report includes rejection counts: withheld cases are never counted as accurate.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np

from roomscope.core.decay import analyze_band
from roomscope.core.decay_model import neural_initial_guess
from roomscope.core.multi_decay import fit_multi_decay
from roomscope.models.audio import FloatArray
from roomscope.models.result import Validity

SEED = 20263004
SAMPLE_RATE = 8000


def synthetic_response(
    times: tuple[float, ...], powers: tuple[float, ...], floor_db: float, *, seed: int
) -> FloatArray:
    duration = max(2.5, 2.5 * max(times))
    t = np.arange(round(duration * SAMPLE_RATE), dtype=np.float64) / SAMPLE_RATE
    power = np.full(t.size, 10.0 ** (floor_db / 10.0), dtype=np.float64)
    for decay_time, amplitude in zip(times, powers, strict=True):
        power += amplitude * np.exp(-6.0 * np.log(10.0) * t / decay_time)
    rng = np.random.default_rng(seed)
    return np.asarray(rng.normal(size=t.size) * np.sqrt(power), dtype=np.float64)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    cases: list[tuple[tuple[float, ...], tuple[float, ...], float]] = []
    for rt in (0.2, 0.4, 0.8, 1.2):
        for noise in (-75.0, -60.0):
            cases.append(((rt,), (1.0,), noise))
    for fast, slow in ((0.2, 1.1), (0.35, 2.0), (0.6, 3.2)):
        for slow_db in (-12.0, -25.0):
            for noise in (-75.0, -60.0):
                cases.append(((fast, slow), (1.0, 10.0 ** (slow_db / 10.0)), noise))
    records: list[dict[str, object]] = []
    statistics: dict[str, dict[str, object]] = {}
    errors: dict[str, list[float]] = {"physical": [], "neural": []}
    counts = {name: {"correct_count": 0, "wrong_count": 0, "withheld": 0} for name in errors}
    elapsed = dict.fromkeys(errors, 0.0)
    for index, (truth, amplitudes, noise) in enumerate(cases):
        for replicate in range(3):
            seed = SEED + 3 * index + replicate
            signal = synthetic_response(truth, amplitudes, noise, seed=seed)
            classic = analyze_band(signal, SAMPLE_RATE, None, noise_margin_db=10.0)
            record: dict[str, object] = {
                "truth_component_rt60_s": list(truth),
                "truth_power_coefficients": list(amplitudes),
                "noise_power_db": noise,
                "seed": seed,
                "classic_rt60_s": classic.rt60_estimate_s,
                "classic_t20_validity": classic.t20.validity.value,
                "classic_t30_validity": classic.t30.validity.value,
            }
            for mode in errors:
                start = time.perf_counter()
                fit = fit_multi_decay(signal, SAMPLE_RATE, initializer=mode)
                elapsed[mode] += time.perf_counter() - start
                record[mode] = fit.to_dict()
                if fit.validity is not Validity.VALID:
                    counts[mode]["withheld"] += 1
                elif len(fit.components) != len(truth):
                    counts[mode]["wrong_count"] += 1
                else:
                    counts[mode]["correct_count"] += 1
                    errors[mode].extend(
                        abs(component.rt60_s / expected - 1.0) * 100.0
                        for component, expected in zip(fit.components, truth, strict=True)
                    )
            records.append(record)
    for mode, values in errors.items():
        statistics[mode] = {
            **counts[mode],
            "accepted_component_median_relative_error_percent": float(np.median(values))
            if values
            else None,
            "accepted_component_p95_relative_error_percent": float(np.percentile(values, 95))
            if values
            else None,
            "elapsed_seconds": elapsed[mode],
        }
    noise = np.random.default_rng(SEED - 1).normal(size=4 * SAMPLE_RATE)
    negatives = {
        "silence": np.zeros(4 * SAMPLE_RATE),
        "stationary_noise": noise,
        "increasing_power": noise * np.exp(np.arange(noise.size) / SAMPLE_RATE),
        "noise_floor_change": synthetic_response((0.5,), (1.0,), -70, seed=SEED - 2),
    }
    changed = negatives["noise_floor_change"].copy()
    changed[changed.size // 2 :] += np.random.default_rng(SEED - 3).normal(
        0, 0.03, changed.size - changed.size // 2
    )
    negatives["noise_floor_change"] = changed
    rejection = {
        name: fit_multi_decay(signal, SAMPLE_RATE, initializer="neural").to_dict()
        for name, signal in negatives.items()
    }
    seed_info = neural_initial_guess(np.geomspace(1.0, 1e-6, 128), 0.02)
    report = {
        "schema_version": 1,
        "scope": "synthetic only; no physical interface, real-room or model generalization evidence",
        "sample_rate": SAMPLE_RATE,
        "generator_seed": SEED,
        "cases": len(records),
        "model_id": seed_info.model_id,
        "model_parameter_count": seed_info.parameter_count,
        "model_sha256": seed_info.sha256,
        "summary": statistics,
        "negative_cases": rejection,
        "records": records,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {"report": str(args.out), "cases": len(records), "summary": statistics}, indent=2
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
