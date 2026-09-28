"""Plain-text reports, kept for code that imported them from here.

The layout lives in :mod:`roomscope.cli.render`; these functions return the
same text the terminal shows, without colour, in the width of the GUI's
report panes. The wording is not a Tier 1 interface: read ``result.json`` or
``--format json`` for values.
"""

from __future__ import annotations

from collections.abc import Sequence

from roomscope.cli.render import REPORT_CONSOLE, render_analysis, render_comparison
from roomscope.interpretation import Finding
from roomscope.models.comparison import ComparisonResult
from roomscope.models.result import AnalysisResult


def format_report(
    result: AnalysisResult,
    findings: Sequence[Finding] | None = None,
    profile_name: str = "generic",
) -> str:
    """The analysis report as plain text (see :func:`~roomscope.cli.render.render_analysis`)."""
    return render_analysis(REPORT_CONSOLE, result, findings or (), profile_name)


def format_comparison_report(
    comparison: ComparisonResult,
    findings: Sequence[Finding] | None = None,
    profile_name: str = "generic",
) -> str:
    """The comparison report as plain text (see :func:`~roomscope.cli.render.render_comparison`)."""
    return render_comparison(REPORT_CONSOLE, comparison, findings or (), profile_name)
