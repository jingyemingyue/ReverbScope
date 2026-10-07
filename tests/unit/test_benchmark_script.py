"""``scripts/benchmark.py`` runs and reports every figure it promises."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent


def _load() -> object:
    path = ROOT / "scripts" / "benchmark.py"
    spec = importlib.util.spec_from_file_location("reverbscope_benchmark", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_one_case_reports_time_memory_and_sizes() -> None:
    benchmark = _load()
    row = benchmark.analysis_case(2.0, 48000, gui=False)  # type: ignore[attr-defined]
    assert row["samples"] >= 48000 * 5  # the sweep, its silences and the room's tail
    for key in ("analyze_s", "load_s", "render_s", "compare_s", "save_s", "interpret_s"):
        assert row[key] > 0.0, key
    assert row["analyze_peak_mib"] > 1.0
    assert row["result_json_bytes"] > 10_000 and row["report_chars"] > 500
    assert json.dumps(row)
    assert benchmark.environment()["numpy"]  # type: ignore[attr-defined]
