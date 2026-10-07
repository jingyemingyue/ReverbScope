"""Wall time and peak memory of the analysis path at three scales.

No third-party profiler: ``time.perf_counter`` and ``tracemalloc``. The cases
are a normal 48 kHz measurement, a heavy 96 kHz one and a 192 kHz one. Run
from the repository root with the project virtualenv.
"""

from __future__ import annotations

import time
import tracemalloc

from reverbscope.audio.fake import make_rir
from reverbscope.core.pipeline import Reference, analyze, synthetic_recording
from reverbscope.models.configuration import AnalysisSettings, SweepSettings


def _case(sample_rate: int, duration_s: float, length_s: float) -> tuple[float, float]:
    settings = SweepSettings(
        sample_rate=sample_rate,
        duration_s=duration_s,
        post_silence_s=max(3.0, length_s),
    )
    room = make_rir(
        sample_rate,
        rt60_s=0.8,
        length_s=length_s,
        diffuse_level=0.03,
        reflections=((0.015, 0.45), (0.028, 0.25)),
        seed=1,
    )
    recording = synthetic_recording(settings, room, noise_rms=1e-6, seed=1)
    reference = Reference.from_settings(settings)
    tracemalloc.start()
    started = time.perf_counter()
    analyze(recording, reference, AnalysisSettings())
    elapsed = time.perf_counter() - started
    _current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return elapsed, peak / (1024.0 * 1024.0)


def main() -> None:
    cases = (
        ("normal 48 kHz, 10 s sweep, 2 s room", 48000, 10.0, 2.0),
        ("heavy 96 kHz, 20 s sweep, 6 s room", 96000, 20.0, 6.0),
        ("stress 192 kHz, 10 s sweep, 2 s room", 192000, 10.0, 2.0),
    )
    for label, sample_rate, duration_s, length_s in cases:
        elapsed, peak_mb = _case(sample_rate, duration_s, length_s)
        print(f"{label}: {elapsed:.3f} s, peak {peak_mb:.1f} MB")


if __name__ == "__main__":
    main()
