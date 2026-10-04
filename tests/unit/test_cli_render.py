"""What the text reports print (cli/render.py), checked on hand-made results."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from roomscope.cli.console import Console, cell_width
from roomscope.cli.render import (
    REPORT_CONSOLE,
    _decay_deltas,
    _reflections,
    _resonances,
    at_a_glance,
    comparison_at_a_glance,
    render_analysis,
)
from roomscope.core.pipeline import Reference, analyze, synthetic_recording
from roomscope.interpretation import interpret, interpret_comparison
from roomscope.labels import signed_number
from roomscope.models.comparison import ComparisonResult, MetricDelta
from roomscope.models.configuration import SweepSettings
from roomscope.models.result import AnalysisResult, ResonanceResult, Validity
from tests.conftest import make_rir

WIDE = Console(color=False, unicode=True, width=100)


def _unchanged(name: str, value: float, unit: str) -> MetricDelta:
    """A delta that is a rounding error below zero, as for a re-imported IR."""
    return MetricDelta(
        name,
        value,
        value,
        Validity.VALID,
        delta_s=-1e-12 if unit == "s" else None,
        delta_percent=-1e-10 if unit == "s" else None,
        delta=-1e-12,
        unit=unit,
    )


def test_signed_number_has_no_negative_zero() -> None:
    assert signed_number(-1e-12, 3) == "+0.000"
    assert signed_number(-0.04, 1) == "+0.0"
    assert signed_number(-0.05001, 1) == "-0.1"
    assert signed_number(1.25, 2) == "+1.25"


def test_unchanged_metrics_never_read_negative_zero() -> None:
    """#50: comparing a session with its own re-imported IR printed -0.0 %."""
    rt = _unchanged("broadband.rt60_estimate", 0.703, "s")
    decay = (_unchanged("broadband.t20", 0.639, "s"), rt, _unchanged("broadband.c50", 1e-9, "dB"))
    noise = (_unchanged("noise.rms_dbfs", -80.0, "dBFS"),)
    comparison = ComparisonResult(
        comparable=True,
        common_band=(100.0, 5000.0),
        decay=decay,
        noise=noise,
        settings={"same_input_gain": True},
    )
    lines = _decay_deltas(WIDE, decay) + comparison_at_a_glance(WIDE, comparison)
    text = WIDE.fit("\n".join(lines))
    assert "-0.0" not in text, text
    assert "(+0.0 %)" in text and "+0.000" in text
    messages = " ".join(item.message for item in interpret_comparison(comparison, "generic"))
    assert "+0.0 % of the baseline" in messages and "(+0.0 dB)" in messages, messages
    assert "-0.0" not in messages, messages


def test_a_narrow_table_keeps_the_change_of_db_metrics() -> None:
    """#28: below about 62 columns, C50/C80/D50 rows showed only a dash."""
    items = [
        MetricDelta(
            "broadband.t20",
            0.5,
            0.6,
            Validity.VALID,
            delta_s=0.1,
            delta_percent=20.0,
            delta=0.1,
            unit="s",
        ),
        MetricDelta("broadband.c50", 9.0, 10.0, Validity.VALID, delta=1.0, unit="dB"),
    ]
    narrow = Console(color=False, unicode=True, width=58)
    lines = _decay_deltas(narrow, items)
    assert all(cell_width(line) <= 58 for line in lines), lines
    c50 = next(line for line in lines if "C50" in line)
    assert "+1.000" in c50, lines
    t20 = next(line for line in lines if "T20" in line)
    assert "+0.100" in t20, lines


def test_a_refused_comparison_reports_no_findings() -> None:
    """#64: a refused pair said "none above the threshold on either side",
    "no potential resonance" and "no quiet segment" although nothing was
    compared."""
    from roomscope.cli.render import render_comparison

    refused = ComparisonResult(
        comparable=False, common_band=None, notes=("the excitation bands do not overlap",)
    )
    text = render_comparison(REPORT_CONSOLE, refused)
    assert "the excitation bands do not overlap" in text
    for claim in (
        "none above the threshold on either side",
        "no potential resonance",
        "no quiet segment",
        "Reverberation",
    ):
        assert claim not in text, text


def test_reflections_skipped_for_confidence_are_not_called_absent() -> None:
    from roomscope.i18n import diag

    note = diag(
        "early reflections are not compared unless both sides have high direct-sound "
        "confidence (baseline {baseline_confidence}, candidate {candidate_confidence})",
        baseline_confidence="high",
        candidate_confidence="low",
    )
    comparison = ComparisonResult(comparable=True, common_band=(100.0, 5000.0), notes=(note,))
    text = "\n".join(comparison_at_a_glance(WIDE, comparison))
    assert "none above the threshold" not in text
    assert "not compared" in text


def test_a_resonance_search_that_did_not_run_is_not_called_clean(
    short_sweep: SweepSettings,
) -> None:
    """#65: a sweep from 400 Hz printed "no potential resonance below 300 Hz"."""
    result = _analysed(replace(short_sweep, start_hz=400.0))
    searched = result.resonances.searched_range_hz
    assert searched is None or searched[0] < searched[1], searched
    text = render_analysis(REPORT_CONSOLE, result, interpret(result))
    assert "no potential resonance" not in text, text
    assert "not searched" in text and "Not searched." in text


def test_a_narrowed_resonance_search_names_its_range(short_sweep: SweepSettings) -> None:
    result = _analysed(short_sweep)

    def low_end(searched: tuple[float, float]) -> list[str]:
        res = ResonanceResult(max_frequency_hz=300.0, candidates=(), searched_range_hz=searched)
        shown = replace(result, resonances=res)
        return [line for line in at_a_glance(WIDE, shown, []) if "Low end" in line] + _resonances(
            WIDE, shown
        )

    assert "243–300 Hz" in WIDE.fit("\n".join(low_end((243.0, 300.0))))
    # Older files stored a search that did not run as an inverted range.
    assert "Not searched." in "\n".join(low_end((495.0, 300.0)))


def _analysed(sweep: SweepSettings) -> AnalysisResult:
    ir = make_rir(sweep.sample_rate, rt60_s=0.3)
    return analyze(synthetic_recording(sweep, ir, noise_rms=1e-5), Reference.from_settings(sweep))


def _imported(length_s: float, **kwargs: object) -> AnalysisResult:
    from roomscope.core.pipeline import analyze_impulse_response
    from roomscope.models.audio import AudioSignal

    ir = make_rir(48000, rt60_s=0.05, length_s=length_s, start_delay_s=0.01, **kwargs)  # type: ignore[arg-type]
    return analyze_impulse_response(AudioSignal(ir, 48000), excitation_band=(20.0, 20000.0))


def test_the_reflection_window_starts_at_its_real_start() -> None:
    """#83: the heading said "1–80 ms" for the 0.8 ms default start."""
    result = _imported(0.5, reflections=[(0.00085, 0.5)])
    lines = WIDE.fit("\n".join(_reflections(WIDE, result))).splitlines()
    assert "0.8–80 ms" in lines[1], lines
    assert any(line.strip().startswith("0.9 ms") for line in lines), lines


def test_a_truncated_reflection_search_says_how_far_it_got() -> None:
    """#67: an IR 50 ms long after the direct sound was reported as the whole
    1-80 ms window, "none above -20 dB"."""
    result = _imported(0.06)
    assert result.reflections.window_truncated
    lines = WIDE.fit("\n".join(_reflections(WIDE, result))).splitlines()
    assert "–80 ms" not in lines[1] and "0.8–50 ms" in lines[1], lines
    flat = " ".join(" ".join(lines).split())
    assert "only that part of the 0.8-80 ms window could be searched" in flat, lines
    glance = next(line for line in at_a_glance(WIDE, result, []) if "Early reflections" in line)
    assert "50.0 ms that could be searched" in WIDE.fit(glance), glance
    assert WIDE.symbol("unsure") in glance


def test_the_validity_legend_wraps_between_entries() -> None:
    """#71: the legend was one line, 44 cells on a 40-column terminal."""
    from roomscope.cli.render import _legend

    narrow = Console(color=False, unicode=True, width=40)
    every = [
        Validity.UNRELIABLE,
        Validity.INSUFFICIENT_RANGE,
        Validity.NOT_COMPUTED,
        Validity.OUTSIDE_EXCITATION,
    ]
    lines = _legend(narrow, every)
    assert len(lines) > 1 and all(cell_width(line) <= 40 for line in lines), lines
    assert "– outside the sweep's range" in lines[-1], lines
    assert _legend(WIDE, every) == [
        "  ? unreliable   ! insufficient range   – not computed   – outside the sweep's range"
    ]


def test_listing_and_project_lines_follow_the_stream_encoding(
    tmp_path: Path, short_sweep: SweepSettings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """#71: "show --list" and "project average" printed "·" and "×" as "?"
    on an ASCII stream instead of the console's "|" and "x"."""
    import io
    import sys

    from roomscope.cli.main import main
    from roomscope.io.project_store import add_session, save_project
    from roomscope.io.session_store import save_measurement
    from roomscope.models.project import Project
    from roomscope.models.session import MeasurementSession

    result = _analysed(short_sweep)
    project = tmp_path / "room"
    save_project(project, Project(name="room"))
    for name in ("desk", "sofa"):
        folder = project / name
        save_measurement(
            folder, MeasurementSession(sweep_settings=short_sweep), result, copy_recording=False
        )
        add_session(project, folder, position=name)

    def run(argv: list[str]) -> str:
        raw = io.BytesIO()
        stream = io.TextIOWrapper(raw, encoding="ascii", errors="replace", newline="\n")
        monkeypatch.setenv("PYTHONIOENCODING", "ascii")
        monkeypatch.setattr(sys, "stdout", stream)
        assert main(argv) == 0
        stream.flush()
        return raw.getvalue().decode("ascii")

    listing = run(["show", "--list", str(project)])
    assert "?" not in listing and " | " in listing, listing
    assert all(line.count("\t") == 1 for line in listing.splitlines()), listing
    average = run(["project", "average", str(project)])
    assert "(1 source x 2 mic, 2 combinations)" in average, average


def _subcommand_help(name: str) -> str:
    import argparse

    from roomscope.cli.main import build_parser

    parser = build_parser()
    action = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
    return " ".join(action.choices[name].format_help().split())


def test_loopback_channel_help_names_the_separate_file_first() -> None:
    """#14: a separate --loopback file's channel is read from that file."""
    text = _subcommand_help("analyze")
    assert "of the recording (or of --loopback if it is multi-channel)" not in text
    assert "of --loopback when it is given, otherwise of the recording" in text


def test_analyze_ir_band_help_covers_broadband_metrics() -> None:
    """#90: without --band, broadband EDT/T20/T30/C50... are not computed either."""
    text = _subcommand_help("analyze-ir")
    assert "required for band metrics" not in text
    assert "required for every decay and clarity metric, broadband included" in text
