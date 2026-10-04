"""What the text reports print (cli/render.py), checked on hand-made results."""

from __future__ import annotations

from dataclasses import replace

from roomscope.cli.console import Console, cell_width
from roomscope.cli.render import (
    REPORT_CONSOLE,
    _decay_deltas,
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
