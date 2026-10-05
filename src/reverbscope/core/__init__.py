"""Pure DSP core. No GUI, device or file-format code lives here.

All functions take and return NumPy arrays or small dataclasses so that they
can be tested with synthetic signals.
"""

from __future__ import annotations

from reverbscope.core.compare import compare
from reverbscope.core.pipeline import Reference, analyze, analyze_impulse_response
from reverbscope.core.sweep import generate_ess, inverse_filter, measurement_signal

__all__ = [
    "Reference",
    "analyze",
    "analyze_impulse_response",
    "compare",
    "generate_ess",
    "inverse_filter",
    "measurement_signal",
]
