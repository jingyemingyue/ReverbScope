from __future__ import annotations

from pathlib import Path

import pytest

from roomscope.core.pipeline import Reference, analyze, synthetic_recording
from roomscope.io.exporters import available_exporters, get_exporter
from roomscope.io.exporters.csv import export_csv
from roomscope.models.configuration import SweepSettings
from tests.conftest import make_rir


def test_csv_exporter_writes_every_curve(tmp_path: Path, short_sweep: SweepSettings) -> None:
    result = analyze(
        synthetic_recording(
            short_sweep,
            make_rir(short_sweep.sample_rate, rt60_s=0.35, reflections=[(0.018, 0.35)]),
            noise_rms=1e-5,
        ),
        Reference.from_settings(short_sweep),
    )
    assert "csv" in available_exporters()
    written = get_exporter("csv").export(result, tmp_path)
    names = {path.name for path in written}
    assert "decay_metrics.csv" in names
    assert "energy_metrics.csv" in names
    assert "frequency_response.csv" in names
    assert "reflections.csv" in names
    metrics = (tmp_path / "decay_metrics.csv").read_text(encoding="utf-8")
    assert "T20" in metrics
    energy = (tmp_path / "energy_metrics.csv").read_text(encoding="utf-8")
    assert "C50" in energy and "Ts" in energy
    again = export_csv(result, tmp_path / "copy")
    assert again


def test_roomscopes_own_csv_entry_point_is_not_a_third_party_collision(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """pyproject.toml registers the built-in CSV exporter under the entry-point
    group too; every install saw it there and logged a false "third-party ...
    collides" warning on each ``roomscope export``."""
    import importlib.metadata as metadata
    import logging

    from roomscope.io.exporters import registry

    class Points:
        def __init__(self, items: list[metadata.EntryPoint]) -> None:
            self._items = items

        def select(self, *, group: str) -> list[metadata.EntryPoint]:
            return [item for item in self._items if item.group == group]

    own = metadata.EntryPoint(
        "csv", "roomscope.io.exporters.csv:CsvExporter", "roomscope.exporters"
    )
    other = metadata.EntryPoint("csv", "somewhere.else:CsvExporter", "roomscope.exporters")

    monkeypatch.setattr(metadata, "entry_points", lambda: Points([own]))
    with caplog.at_level(logging.WARNING, logger="roomscope.exporters"):
        assert registry.available_exporters() == ["csv"]
    assert not caplog.records

    monkeypatch.setattr(metadata, "entry_points", lambda: Points([other]))
    with caplog.at_level(logging.WARNING, logger="roomscope.exporters"):
        assert registry.available_exporters() == ["csv"]
    assert any("collides" in record.getMessage() for record in caplog.records)


def test_a_third_party_exporter_registered_as_a_class_is_instantiated(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Registered like pyproject.toml registers CsvExporter (``pkg:Class``),
    the class itself was returned and ``export`` failed for a missing argument."""
    import importlib.metadata as metadata
    import sys
    import types

    from roomscope.io.exporters import registry

    module = types.ModuleType("third_party_exporter")

    class JsonLines:
        name = "jsonl"

        def export(self, result: object, directory: Path) -> list[Path]:
            target = directory / "out.jsonl"
            target.write_text("{}\n", encoding="utf-8")
            return [target]

    module.JsonLines = JsonLines  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "third_party_exporter", module)
    point = metadata.EntryPoint("jsonl", "third_party_exporter:JsonLines", "roomscope.exporters")

    class Points:
        def select(self, *, group: str) -> list[metadata.EntryPoint]:
            return [point]

    monkeypatch.setattr(metadata, "entry_points", lambda: Points())
    exporter = registry.get_exporter("jsonl")
    assert isinstance(exporter, JsonLines)
    assert exporter.export(object(), tmp_path) == [tmp_path / "out.jsonl"]  # type: ignore[arg-type]


def _loopback_result(sweep: SweepSettings):
    """An analysis with a compensated loopback and its interface curve."""
    from dataclasses import replace

    import numpy as np

    from roomscope.models.result import LoopbackResult

    result = analyze(
        synthetic_recording(sweep, make_rir(sweep.sample_rate, rt60_s=0.35), noise_rms=1e-5),
        Reference.from_settings(sweep),
    )
    loopback = LoopbackResult(
        channel=1,
        compensation_applied=True,
        interface_response_hz=np.array([100.0, 1000.0, 10000.0]),
        interface_response_db=np.array([-0.5, 0.0, -1.0]),
    )
    return replace(result, impulse_response=replace(result.impulse_response, loopback=loopback))


def test_no_curves_leaves_out_the_interface_curve_and_keeps_the_point_count(
    short_sweep: SweepSettings,
) -> None:
    """--no-curves still wrote the interface response (2 x 2048 values), and a
    reloaded --no-curves result reported frequency_response.points 0."""
    from roomscope.models.result import AnalysisResult

    result = _loopback_result(short_sweep)
    full = result.to_dict(include_curves=True)
    assert full["impulse_response"]["loopback"]["interface_response_hz"] == [100.0, 1000.0, 10000.0]
    slim = result.to_dict(include_curves=False)
    assert "interface_response_hz" not in slim["impulse_response"]["loopback"]
    points = slim["frequency_response"]["points"]
    assert points == result.frequency_response.frequencies_hz.shape[0] > 0
    reloaded = AnalysisResult.from_dict(slim)
    assert reloaded.frequency_response.frequencies_hz.size == 0
    assert reloaded.to_dict(include_curves=False)["frequency_response"]["points"] == points
    assert reloaded.to_dict(include_curves=True)["frequency_response"]["points"] == points


def test_csv_export_includes_the_interface_curve_and_resonance_decays(
    tmp_path: Path, short_sweep: SweepSettings
) -> None:
    names = {path.name for path in export_csv(_loopback_result(short_sweep), tmp_path)}
    assert "interface_response.csv" in names
    lines = (tmp_path / "interface_response.csv").read_text(encoding="utf-8").splitlines()
    assert lines == ["frequency_hz,magnitude_db", "100.0,-0.5", "1000.0,0.0", "10000.0,-1.0"]
    header = (tmp_path / "resonances.csv").read_text(encoding="utf-8").splitlines()[0]
    assert header.split(",") == [
        "frequency_hz",
        "level_above_baseline_db",
        "narrowband_decay_20db_s",
        "decay_distinguishable",
        "filter_ringing_20db_s",
        "surroundings_decay_20db_s",
    ]
