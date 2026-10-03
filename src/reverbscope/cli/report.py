"""Plain-text reports, kept for code that imported them from here.

The layout lives in :mod:`reverbscope.cli.render`; these functions return the
same text the terminal shows, without colour, in the width of the GUI's
report panes. Scripts usually print the result, so the symbols follow
``sys.stdout``: where it cannot encode ``✓`` or ``─`` (a cp1252 pipe on
Windows) the ASCII forms are used, as the command line does. The wording is
not a Tier 1 interface: read ``result.json`` or ``--format json`` for values.
"""

from __future__ import annotations

import sys
from collections.abc import Sequence
from dataclasses import replace

from reverbscope.cli.console import Console
from reverbscope.cli.render import REPORT_CONSOLE, render_analysis, render_comparison
from reverbscope.interpretation import Finding
from reverbscope.models.comparison import ComparisonResult
from reverbscope.models.result import AnalysisResult


def _console() -> Console:
    """The GUI's plain layout, with symbols ``sys.stdout`` can write."""
    probe = Console.for_stream(sys.stdout, "never")
    return replace(REPORT_CONSOLE, unicode=probe.unicode)


def format_report(
    result: AnalysisResult,
    findings: Sequence[Finding] | None = None,
    profile_name: str = "generic",
) -> str:
    """The analysis report as plain text (see :func:`~reverbscope.cli.render.render_analysis`)."""
    return render_analysis(_console(), result, findings or (), profile_name)


def format_comparison_report(
    comparison: ComparisonResult,
    findings: Sequence[Finding] | None = None,
    profile_name: str = "generic",
) -> str:
    """The comparison report as plain text (see :func:`~reverbscope.cli.render.render_comparison`)."""
    return render_comparison(_console(), comparison, findings or (), profile_name)
