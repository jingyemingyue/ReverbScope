"""Repeatable steady-state display benchmark; no GUI or audio device required."""

from __future__ import annotations

import argparse
import json
import os
import platform
import statistics
import sys
import time

THREAD_VARIABLES = (
    "OPENBLAS_NUM_THREADS",
    "OMP_NUM_THREADS",
    "MKL_NUM_THREADS",
    "BLIS_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--threads", type=int, choices=(1, 2, 4, 8), default=1)
    args = parser.parse_args()
    # These must be set before importing NumPy/SciPy: changing the environment
    # after pytest has imported them does not reconfigure a loaded BLAS runtime.
    for name in THREAD_VARIABLES:
        os.environ[name] = str(args.threads)

    import numpy as np
    import scipy

    from reverbscope.display.timefreq import cumulative_spectral_decay, spectrogram

    sample_rate = 48000
    direct_index = 240
    seconds = 2.0
    t = np.arange(int(seconds * sample_rate)) / sample_rate
    mode = np.sin(2 * np.pi * 1000.0 * t) * np.exp(-6.91 * t / 0.5)
    ir = np.concatenate([np.zeros(direct_index), mode])

    def transform() -> None:
        spectrogram(ir, sample_rate, direct_index)
        cumulative_spectral_decay(ir, sample_rate, direct_index)

    transform()  # Exclude imports and first-use FFT/BLAS initialization.
    wall_times = []
    cpu_times = []
    for _ in range(5):
        wall_start = time.perf_counter()
        cpu_start = time.process_time()
        transform()
        cpu_times.append(time.process_time() - cpu_start)
        wall_times.append(time.perf_counter() - wall_start)
    sys.stdout.write(
        json.dumps(
            {
                "sample_rate": sample_rate,
                "direct_index": direct_index,
                "duration_s": seconds,
                "samples": int(ir.size),
                "wall_seconds": wall_times,
                "cpu_seconds": cpu_times,
                "median_seconds": statistics.median(wall_times),
                "thread_environment": {name: os.environ[name] for name in THREAD_VARIABLES},
                "python": platform.python_version(),
                "platform": platform.platform(),
                "numpy": np.__version__,
                "scipy": scipy.__version__,
            }
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
