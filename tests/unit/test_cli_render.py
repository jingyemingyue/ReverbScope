"""What the text reports print (cli/render.py), checked on hand-made results."""

from __future__ import annotations

from roomscope.cli.console import Console
from roomscope.cli.render import _decay_deltas, comparison_at_a_glance
from roomscope.interpretation import interpret_comparison
from roomscope.labels import signed_number
from roomscope.models.comparison import ComparisonResult, MetricDelta
from roomscope.models.result import Validity

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
