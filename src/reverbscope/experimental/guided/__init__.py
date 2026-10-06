"""Guided acoustic assistant (experimental).

Data flow, and the only one this package is allowed to implement::

    Measurement pipeline
        -> deterministic diagnostic engine
        -> structured findings
        -> recommendation planner
        -> knowledge catalog
        -> explanation provider
        -> GUI / CLI

AI providers explain structured findings. They do not measure, do not invent
numbers, and do not decide whether a comparison improved.
"""

from __future__ import annotations

from reverbscope.experimental.guided.findings import (
    Confidence,
    FindingType,
    Priority,
    Severity,
    StructuredFinding,
)
from reverbscope.experimental.guided.service import GuidedReport, run_guided

__all__ = [
    "Confidence",
    "FindingType",
    "GuidedReport",
    "Priority",
    "Severity",
    "StructuredFinding",
    "run_guided",
]
