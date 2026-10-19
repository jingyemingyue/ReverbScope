"""Emit deterministic public-path snapshots for a selected source checkout.

Run from that checkout with PYTHONPATH=src:. and pass the output JSON path.
Requires the project's dev dependencies and tests.conftest synthetic helper.
Compare full JSON objects, not rounded metrics. No hardware is accessed.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
from tests.conftest import make_rir

from reverbscope.core.decay import analyze_band
from reverbscope.core.pipeline import (
    Reference,
    analyze,
    analyze_impulse_response,
    synthetic_recording,
)
from reverbscope.models.audio import AudioSignal
from reverbscope.models.configuration import AnalysisSettings, SweepSettings

out = {}
for cut in [45, 50, 55]:
    time = np.arange(16000) / 8000
    signal = np.exp(-math.log(1000) * time / 0.8)
    signal[time >= 0.8 * cut / 60] = 0
    out[f"band{cut}"] = analyze_band(signal, 8000, None, noise_margin_db=10).to_dict()
    if cut == 50:
        out["imported_ir"] = analyze_impulse_response(AudioSignal(signal, 8000)).to_dict(
            include_curves=True
        )
for duration in [0.5, 2.0]:
    for noise in [0.0, 1e-5]:
        settings = SweepSettings(
            sample_rate=48000,
            duration_s=duration,
            start_hz=40,
            end_hz=3000,
            post_silence_s=1.5,
        )
        room = make_rir(48000, rt60_s=0.4, reflections=[(0.018, 0.1)], diffuse_level=0.01)
        recording = synthetic_recording(settings, room, noise_rms=noise)
        out[f"sweep-{duration}-{noise}"] = analyze(
            recording, Reference.from_settings(settings)
        ).to_dict(include_curves=True)
        if duration == 0.5 and noise == 0.0:
            out["sweep-long-preroll"] = analyze(
                recording,
                Reference.from_settings(settings),
                AnalysisSettings(ir_pre_delay_ms=100),
            ).to_dict(include_curves=True)
# Wall-clock creation time is metadata, not an algorithm output.
for value in out.values():
    if "created_at" in value:
        value["created_at"] = "<runtime timestamp>"
Path(sys.argv[1]).write_text(json.dumps(out, sort_keys=True, allow_nan=False), encoding="utf-8")
