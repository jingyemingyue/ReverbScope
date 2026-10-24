from __future__ import annotations

from pathlib import Path

import pytest

from reverbscope.core.pipeline import Reference, analyze, synthetic_recording
from reverbscope.io.exporters import available_exporters, get_exporter
from reverbscope.io.exporters.csv import export_csv
from reverbscope.models.configuration import SweepSettings
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


def test_reverbscopes_own_csv_entry_point_is_not_a_third_party_collision(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """pyproject.toml registers the built-in CSV exporter under the entry-point
    group too; every install saw it there and logged a false "third-party ...
    collides" warning on each ``reverbscope export``."""
    import importlib.metadata as metadata
    import logging

    from reverbscope.io.exporters import registry

    class Points:
        def __init__(self, items: list[metadata.EntryPoint]) -> None:
            self._items = items

        def select(self, *, group: str) -> list[metadata.EntryPoint]:
            return [item for item in self._items if item.group == group]

    own = metadata.EntryPoint(
        "csv", "reverbscope.io.exporters.csv:CsvExporter", "reverbscope.exporters"
    )
    other = metadata.EntryPoint("csv", "somewhere.else:CsvExporter", "reverbscope.exporters")

    monkeypatch.setattr(metadata, "entry_points", lambda: Points([own]))
    with caplog.at_level(logging.WARNING, logger="reverbscope.exporters"):
        assert registry.available_exporters() == ["csv"]
    assert not caplog.records

    monkeypatch.setattr(metadata, "entry_points", lambda: Points([other]))
    with caplog.at_level(logging.WARNING, logger="reverbscope.exporters"):
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

    from reverbscope.io.exporters import registry

    module = types.ModuleType("third_party_exporter")

    class JsonLines:
        name = "jsonl"

        def export(self, result: object, directory: Path) -> list[Path]:
            target = directory / "out.jsonl"
            target.write_text("{}\n", encoding="utf-8")
            return [target]

    module.JsonLines = JsonLines  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "third_party_exporter", module)
    point = metadata.EntryPoint("jsonl", "third_party_exporter:JsonLines", "reverbscope.exporters")

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

    from reverbscope.models.result import LoopbackResult

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
    from reverbscope.models.result import AnalysisResult

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


def test_an_unknown_exporter_lists_the_others_by_name() -> None:
    """The error printed the Python list: "available: ['csv']"."""
    import pytest

    from reverbscope.errors import ConfigurationError
    from reverbscope.io.exporters import get_exporter

    with pytest.raises(ConfigurationError) as exc:
        get_exporter("nope")
    listed = str(exc.value).split("available: ", 1)[1]
    assert "csv" in listed.split(", ") and "[" not in listed, exc.value


def test_an_export_removes_the_curves_of_an_earlier_export_it_does_not_have(
    tmp_path: Path, short_sweep: SweepSettings
) -> None:
    """A --no-curves session exported into a folder used before left the
    earlier session's decay_edc.csv, frequency_response.csv and noise_psd.csv
    beside its own metrics, with nothing to tell them apart."""
    from reverbscope.models.result import AnalysisResult

    result = analyze(
        synthetic_recording(
            short_sweep, make_rir(short_sweep.sample_rate, rt60_s=0.3), noise_rms=1e-5
        ),
        Reference.from_settings(short_sweep),
    )
    full = {path.name for path in export_csv(result, tmp_path)}
    assert {"decay_edc.csv", "frequency_response.csv"} <= full
    (tmp_path / "notes.txt").write_text("mine", encoding="utf-8")
    slim = AnalysisResult.from_dict(result.to_dict(include_curves=False))
    written = {path.name for path in export_csv(slim, tmp_path)}
    assert "frequency_response.csv" not in written
    assert {path.name for path in tmp_path.iterdir()} == written | {"notes.txt"}


def test_an_export_folder_that_cannot_be_created_is_a_session_error(
    tmp_path: Path, short_sweep: SweepSettings
) -> None:
    from reverbscope.core.pipeline import Reference, analyze, synthetic_recording
    from reverbscope.errors import SessionError
    from reverbscope.io.exporters.csv import export_csv
    from tests.conftest import make_rir

    rate = short_sweep.sample_rate
    result = analyze(
        synthetic_recording(short_sweep, make_rir(rate, rt60_s=0.3)),
        Reference.from_settings(short_sweep),
    )
    blocker = tmp_path / "blocker"
    blocker.write_text("x", encoding="utf-8")
    with pytest.raises(SessionError, match="cannot create"):
        export_csv(result, blocker / "csv")


def test_csv_export_writes_both_decay_models_of_each_band(tmp_path: Path) -> None:
    """decay_slopes.csv: one row per fitted model and band, the selected one
    marked, the knee only on the selected two-slope row."""
    import csv
    import math
    from dataclasses import replace

    import numpy as np

    from reverbscope.core.pipeline import analyze_impulse_response
    from reverbscope.models.audio import AudioSignal
    from tests.unit.test_multislope import LEAD, RATE, decay

    signal = decay(0.4, 1.6, -25.0, seed=8)
    signal[LEAD] = 4.0 * math.sqrt(float(np.sum(signal**2)))
    result = analyze_impulse_response(AudioSignal(signal, RATE), excitation_band=(20.0, 20_000.0))
    written = {path.name for path in export_csv(result, tmp_path)}
    assert "decay_slopes.csv" in written
    with (tmp_path / "decay_slopes.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert list(rows[0]) == [
        "band", "resolution", "slopes", "validity", "selected", "t1_s", "t2_s", "a1_db", "a2_db",
        "a1_share_percent", "a2_share_percent", "noise_term", "bic", "delta_bic",
        "knee_time_s", "knee_level_db",
    ]  # fmt: skip
    broadband = result.decay.broadband
    fit = broadband.multi_slope
    assert fit is not None and fit.selected_slopes == 2
    assert {r["resolution"] for r in rows} == {"broadband", "octave"}
    mine = [r for r in rows if r["band"] == broadband.band_label]
    assert [r["slopes"] for r in mine] == ["1", "2"]
    one, two = mine
    assert one["selected"] == "no" and two["selected"] == "yes"
    assert one["t2_s"] == "" and one["knee_time_s"] == ""
    model = fit.model(2)
    assert model is not None
    assert float(two["t1_s"]) == pytest.approx(model.decay_times_s[0])
    assert float(two["t2_s"]) == pytest.approx(model.decay_times_s[1])
    assert float(two["a2_share_percent"]) == pytest.approx(model.energy_shares_percent[1])
    assert float(two["delta_bic"]) == pytest.approx(fit.delta_bic)
    assert two["knee_time_s"] != "" and two["knee_level_db"] != ""
    # Every analysed band has at least one row.
    labels = {r["band"] for r in rows}
    assert {b.band_label for b in result.decay.bands if b.multi_slope is not None} <= labels

    # Without any fit (a file written before the fit existed) the export
    # leaves the file out and removes the one an earlier export wrote.
    bare = replace(
        result,
        decay=replace(
            result.decay,
            broadband=replace(broadband, multi_slope=None),
            bands=tuple(replace(b, multi_slope=None) for b in result.decay.bands),
        ),
    )
    assert "decay_slopes.csv" not in {path.name for path in export_csv(bare, tmp_path)}
    assert not (tmp_path / "decay_slopes.csv").exists()


def test_csv_export_marks_the_band_resolution_of_third_octave_rows(tmp_path: Path) -> None:
    """With the one-third-octave analysis, decay_slopes.csv also holds those
    bands, told apart from the octave bands of the same label (63 Hz, 125 Hz,
    ...) by the resolution column; the other files keep their rows."""
    import csv
    import math

    import numpy as np

    from reverbscope.core.pipeline import analyze_impulse_response
    from reverbscope.models.audio import AudioSignal
    from reverbscope.models.configuration import AnalysisSettings
    from tests.unit.test_multislope import LEAD, RATE, decay

    signal = decay(0.4, 1.6, -25.0, seed=8)
    signal[LEAD] = 4.0 * math.sqrt(float(np.sum(signal**2)))
    audio = AudioSignal(signal, RATE)
    result = analyze_impulse_response(
        audio, AnalysisSettings(third_octave_decay=True), excitation_band=(20.0, 20_000.0)
    )
    export_csv(result, tmp_path / "thirds")
    with (tmp_path / "thirds" / "decay_slopes.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    thirds = result.decay.third_octave_bands
    assert thirds is not None
    third_rows = [r for r in rows if r["resolution"] == "third_octave"]
    assert {r["band"] for r in third_rows} == {b.band_label for b in thirds}
    both = {r["resolution"] for r in rows if r["band"] == "63 Hz"}
    assert both == {"octave", "third_octave"}
    one_k = next(b for b in thirds if b.band_label == "1 kHz")
    fit = one_k.multi_slope
    assert fit is not None and fit.selected_slopes == 2
    model = fit.model(2)
    assert model is not None
    chosen = next(r for r in third_rows if r["band"] == "1 kHz" and r["selected"] == "yes")
    assert chosen["slopes"] == "2"
    assert float(chosen["t2_s"]) == pytest.approx(model.decay_times_s[1])

    # The octave files are those of the default analysis.
    octave = analyze_impulse_response(audio, excitation_band=(20.0, 20_000.0))
    export_csv(octave, tmp_path / "octave")
    for name in ("decay_metrics.csv", "energy_metrics.csv", "decay_edc.csv"):
        assert (tmp_path / "thirds" / name).read_text(encoding="utf-8") == (
            tmp_path / "octave" / name
        ).read_text(encoding="utf-8")
    plain = (tmp_path / "octave" / "decay_slopes.csv").read_text(encoding="utf-8").splitlines()
    assert all("third_octave" not in line for line in plain)
