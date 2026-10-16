"""Time and memory of the analysis chain on synthetic recordings.

Measures what a user waits for: ``analyze`` on a 2 s, 10 s and 60 s sweep
at 48 kHz and 96 kHz (the peak memory it allocates, through tracemalloc),
the result's JSON round trip, a comparison, the text report and, with
``--gui``, the workstation's chart views drawn offscreen. Synthetic rooms only:
the numbers say how long ReverbScope takes, never anything about a room.

    python scripts/benchmark.py            # the full set (a few minutes)
    python scripts/benchmark.py --quick    # 2 s and 10 s at 48 kHz
    python scripts/benchmark.py --json     # machine-readable

One run on one machine: compare runs on the same machine, and read
``docs/PERFORMANCE.md`` for what the numbers meant on the reference
container and which steps dominate.
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
import tempfile
import time
import tracemalloc
from collections.abc import Callable
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

CASES: tuple[tuple[float, int], ...] = (
    (2.0, 48000),
    (10.0, 48000),
    (60.0, 48000),
    (10.0, 96000),
    (60.0, 96000),
)
QUICK: tuple[tuple[float, int], ...] = ((2.0, 48000), (10.0, 48000))


def timed(function: Callable[[], Any]) -> tuple[Any, float]:
    """``(value, seconds)`` of one call."""
    start = time.perf_counter()
    value = function()
    return value, time.perf_counter() - start


def peak_mib(function: Callable[[], Any]) -> float:
    """The peak of the allocations ``function`` makes (MiB), in a run of its
    own: tracemalloc slows allocation-heavy code several times over, so it
    never shares a run with a timing."""
    tracemalloc.start()
    tracemalloc.reset_peak()
    try:
        function()
        _current, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    return peak / (1024 * 1024)


def analysis_case(duration_s: float, sample_rate: int, *, gui: bool) -> dict[str, Any]:
    from reverbscope.audio.fake import make_rir
    from reverbscope.cli.render import REPORT_CONSOLE, render_analysis
    from reverbscope.core.compare import compare
    from reverbscope.core.pipeline import Reference, analyze, synthetic_recording
    from reverbscope.interpretation import interpret
    from reverbscope.io.session_store import load_measurement, save_measurement
    from reverbscope.models.configuration import SweepSettings
    from reverbscope.models.session import MeasurementSession

    sweep = SweepSettings(
        sample_rate=sample_rate, duration_s=duration_s, pre_silence_s=1.0, post_silence_s=2.0
    )
    ir = make_rir(sample_rate, rt60_s=0.6, reflections=[(0.012, 0.4)], diffuse_level=0.03, seed=1)
    recording, make_s = timed(lambda: synthetic_recording(sweep, ir, noise_rms=1e-5, seed=1))
    reference, ref_s = timed(lambda: Reference.from_settings(sweep))
    result, analyze_s = timed(lambda: analyze(recording, reference))
    analyze_mib = peak_mib(lambda: analyze(recording, reference))
    _findings, interpret_s = timed(lambda: interpret(result, "vocal"))
    text, render_s = timed(lambda: render_analysis(REPORT_CONSOLE, result, [], "vocal"))
    with tempfile.TemporaryDirectory() as folder:
        session_dir = Path(folder) / "take"
        _, save_s = timed(
            lambda: save_measurement(session_dir, MeasurementSession(), result, recording=recording)
        )
        result_bytes = (session_dir / "result.json").stat().st_size
        _, load_s = timed(lambda: load_measurement(session_dir))
        load_mib = peak_mib(lambda: load_measurement(session_dir))
    _comparison, compare_s = timed(lambda: compare(result, result))
    row: dict[str, Any] = {
        "duration_s": duration_s,
        "sample_rate": sample_rate,
        "samples": int(recording.samples.shape[0]),
        "synthesis_s": make_s,
        "reference_s": ref_s,
        "analyze_s": analyze_s,
        "analyze_peak_mib": analyze_mib,
        "interpret_s": interpret_s,
        "render_s": render_s,
        "report_chars": len(text),
        "save_s": save_s,
        "result_json_bytes": result_bytes,
        "load_s": load_s,
        "load_peak_mib": load_mib,
        "compare_s": compare_s,
    }
    if gui:
        row["plots_s"] = plots_seconds(result)
    return row


def plots_seconds(result: Any) -> float:
    """The workstation's five chart views drawn offscreen (pyqtgraph), in seconds."""
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    from reverbscope.models.session import MeasurementSession
    from reverbscope.ui.views.decay import DecayView
    from reverbscope.ui.views.frequency import FrequencyView
    from reverbscope.ui.views.impulse import ImpulseView
    from reverbscope.ui.views.noise import NoiseView
    from reverbscope.ui.views.overview import OverviewView
    from reverbscope.ui.workspace import WorkspaceModel

    app = QApplication.instance() or QApplication([])
    model = WorkspaceModel()
    model.add_take(MeasurementSession(), result, [], "", "generic", unsaved=False, synthetic=True)
    start = time.perf_counter()
    for view_type in (OverviewView, ImpulseView, FrequencyView, DecayView, NoiseView):
        view = view_type(model)
        view.resize(1000, 600)
        view.show()
        view.redraw()
        app.processEvents()
        view.grab()
        view.close()
        view.deleteLater()
    seconds = time.perf_counter() - start
    model.shutdown()
    return seconds


def environment() -> dict[str, Any]:
    import numpy
    import scipy

    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "numpy": numpy.__version__,
        "scipy": scipy.__version__,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--quick", action="store_true", help="2 s and 10 s at 48 kHz only")
    parser.add_argument(
        "--gui", action="store_true", help="also time the workstation's chart views"
    )
    parser.add_argument("--json", action="store_true", help="print JSON instead of a table")
    args = parser.parse_args(argv)
    cases = QUICK if args.quick else CASES
    rows = [analysis_case(duration, rate, gui=args.gui) for duration, rate in cases]
    report = {"environment": environment(), "cases": rows}
    if args.json:
        print(json.dumps(report, indent=1))
        return 0
    env = report["environment"]
    print(f"ReverbScope benchmark: Python {env['python']}, {env['platform']}, {env['machine']}")
    print(f"numpy {env['numpy']}, scipy {env['scipy']}; synthetic rooms, one run per case")
    print()
    headers = ["sweep", "rate", "analyze", "peak", "load", "report", "compare", "result.json"]
    if args.gui:
        headers.append("plots")
    print("  ".join(h.rjust(11) for h in headers))
    for row in rows:
        cells = [
            f"{row['duration_s']:.0f} s",
            f"{row['sample_rate'] // 1000} kHz",
            f"{row['analyze_s']:.2f} s",
            f"{row['analyze_peak_mib']:.0f} MiB",
            f"{row['load_s'] * 1000:.0f} ms",
            f"{row['render_s'] * 1000:.0f} ms",
            f"{row['compare_s'] * 1000:.0f} ms",
            f"{row['result_json_bytes'] / 1024:.0f} KiB",
        ]
        if args.gui:
            cells.append(f"{row['plots_s']:.2f} s")
        print("  ".join(cell.rjust(11) for cell in cells))
    return 0


if __name__ == "__main__":
    sys.exit(main())
