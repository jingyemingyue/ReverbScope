"""Run the whole ReverbScope chain on a synthetic room, without any hardware.

    python examples/synthetic_measurement.py [output_dir]

Builds a sweep, a synthetic room impulse response (direct sound, one strong
reflection at 18 ms, a diffuse tail with RT60 = 0.45 s, mains hum in the
background), "records" it, analyses it, prints the report and saves a session.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from scipy.signal import fftconvolve

from reverbscope.cli.report import format_report
from reverbscope.core import Reference, analyze, measurement_signal
from reverbscope.interpretation import interpret
from reverbscope.io.session_store import save_measurement
from reverbscope.io.wav import write_sweep_file, write_wav
from reverbscope.models.audio import AudioSignal
from reverbscope.models.configuration import SweepSettings
from reverbscope.models.session import MeasurementSession


def synthetic_room(sample_rate: int, rt60_s: float = 0.45, seed: int = 0) -> np.ndarray:
    n = int(1.5 * sample_rate)
    t = np.arange(n) / sample_rate
    rng = np.random.default_rng(seed)
    ir = rng.normal(0.0, 1.0, n) * np.exp(-np.log(1e6) * t / (2.0 * rt60_s)) * 0.01
    ir[0] += 1.0  # direct sound
    ir[int(0.018 * sample_rate)] += 10 ** (-9 / 20)  # reflection: 18 ms, -9 dB
    return ir


def main(out_dir: Path) -> None:
    settings = SweepSettings(
        sample_rate=48000, duration_s=5.0, pre_silence_s=1.0, post_silence_s=2.5
    )
    sweep_path, _ = write_sweep_file(settings, out_dir / "sweep.wav")

    ir = synthetic_room(settings.sample_rate)
    excitation = measurement_signal(settings)
    recorded = fftconvolve(excitation, ir)[: excitation.shape[0] + ir.shape[0]]
    t = np.arange(recorded.shape[0]) / settings.sample_rate
    rng = np.random.default_rng(1)
    recorded += rng.normal(0.0, 3e-5, recorded.shape[0])
    for k, amp in ((1, 2e-4), (2, 1e-4), (3, 5e-5)):
        recorded += amp * np.sin(2 * np.pi * 50.0 * k * t)
    recording_path = write_wav(
        out_dir / "recording.wav", recorded, settings.sample_rate, subtype="FLOAT"
    )

    result = analyze(AudioSignal(recorded, settings.sample_rate), Reference.from_settings(settings))
    findings = interpret(result)
    print(format_report(result, findings))

    session = MeasurementSession(
        room_name="Synthetic room",
        sweep_settings=settings,
        sweep_path=str(sweep_path),
        recording_path=str(recording_path),
    )
    print("\nSession saved to", save_measurement(out_dir / "session", session, result))


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else Path("synthetic_output"))
