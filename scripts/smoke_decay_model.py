"""Verify the bundled local model using one synthetic IR; never play audio."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

import numpy as np
import soundfile as sf
from smoke_bundle import find_binary


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="backslashreplace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, help="frozen bundle directory")
    parser.add_argument("--roomscope", type=Path, help="installed or frozen command-line binary")
    parser.add_argument("--out", type=Path, required=True, help="temporary smoke directory")
    args = parser.parse_args()
    binary = find_binary(args.root, args.roomscope)
    work = args.out.resolve()
    work.mkdir(parents=True, exist_ok=True)
    sample_rate = 8000
    t = np.arange(5 * sample_rate, dtype=np.float64) / sample_rate
    power = np.exp(-6 * np.log(10) * t / 0.3) + 10**-2.5 * np.exp(-6 * np.log(10) * t / 2.0)
    tail = np.random.default_rng(20265004).normal(size=t.size) * np.sqrt(power + 1e-8) * 0.02
    tail[0] = 1.0  # a known, stronger direct pulse; excluded from the model fit
    signal = np.concatenate([np.zeros(sample_rate // 10), tail])
    source = work / "synthetic-ir.wav"
    sf.write(source, signal, sample_rate, subtype="FLOAT")
    argv = [
        str(binary),
        "--format",
        "json",
        "analyze-ir",
        "--ir",
        str(source),
        "--band",
        "20",
        "3500",
        "--out",
        str(work / "session"),
        "--decay-fit",
        "neural",
        "--no-curves",
    ]
    env = os.environ.copy()
    env.update(
        ROOMSCOPE_AUDIO_BACKEND="fake",
        ROOMSCOPE_HOME=str(work / "home"),
        PYTHONIOENCODING="utf-8",
        NO_COLOR="1",
    )
    env.pop("FORCE_COLOR", None)
    try:
        done = subprocess.run(
            argv, capture_output=True, text=True, encoding="utf-8", env=env, timeout=120
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SystemExit(
            f"local model smoke could not complete: {exc}\ncommand: {shlex.join(argv)}"
        ) from exc
    if done.returncode:
        raise SystemExit(
            f"local model smoke failed (exit {done.returncode})\ncommand: {shlex.join(argv)}\n{done.stdout}\n{done.stderr}"
        )
    try:
        report = json.loads(done.stdout)
        fit = report["decay"]["broadband"]["multi_decay"]
        saved = json.loads((work / "session" / "result.json").read_text(encoding="utf-8"))
        expected_resource = (
            Path(__file__).resolve().parents[1]
            / "src/roomscope/model_data/decay_initializer_v1.json"
        )
        expected_sha = hashlib.sha256(expected_resource.read_bytes()).hexdigest()
        actual_times = np.asarray([component["rt60_s"] for component in fit["components"]])
        valid = (
            fit["validity"] == "valid"
            and fit["initializer"] == "neural"
            and fit["initializer_model"] == "roomscope-decay-initializer-v1"
            and fit["initializer_parameters"] == 2245
            and fit["initializer_sha256"] == expected_sha
            and actual_times.shape == (2,)
            and np.allclose(actual_times, (0.3, 2.0), rtol=0.1)
            and saved["decay"]["broadband"]["multi_decay"] == fit
        )
    except (ValueError, OSError, KeyError, TypeError) as exc:
        raise SystemExit(
            f"local model smoke returned an invalid report: {exc}\n{done.stderr}"
        ) from exc
    if not valid:
        raise SystemExit(
            f"local model smoke rejected parameters or model provenance:\n{json.dumps(fit, indent=2)}"
        )
    print(
        f"local decay model smoke ok: {binary}; component times {actual_times.tolist()}; sha256 {expected_sha}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
