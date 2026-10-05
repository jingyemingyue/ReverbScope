"""ReverbScope: an open-source, DAW-independent recording environment analyzer.

The package is organised core-first:

* :mod:`reverbscope.core` -- pure DSP functions (sweep, deconvolution, decay, ...).
* :mod:`reverbscope.models` -- data models (settings, results, measurement session).
* :mod:`reverbscope.io` -- WAV and session storage.
* :mod:`reverbscope.audio` -- optional audio device access for Standalone Mode.
* :mod:`reverbscope.interpretation` -- recording-engineer oriented explanations.
* :mod:`reverbscope.cli` / :mod:`reverbscope.ui` -- thin front ends over the core.

Tier 1 names are loaded through :func:`__getattr__` so ``import reverbscope``
does not import SciPy, PortAudio or Qt. The list is locked against
``docs/ARCHITECTURE_V1.md`` §5.1.
"""

from __future__ import annotations

from typing import Any

from reverbscope.errors import (
    AnalysisError as AnalysisError,
)
from reverbscope.errors import (
    AudioBackendUnavailableError as AudioBackendUnavailableError,
)
from reverbscope.errors import (
    AudioDeviceError as AudioDeviceError,
)
from reverbscope.errors import (
    ConfigurationError as ConfigurationError,
)
from reverbscope.errors import (
    InsufficientDataError as InsufficientDataError,
)
from reverbscope.errors import (
    InvalidAudioError as InvalidAudioError,
)
from reverbscope.errors import (
    ReverbScopeError as ReverbScopeError,
)
from reverbscope.errors import (
    SampleRateMismatchError as SampleRateMismatchError,
)
from reverbscope.errors import (
    SessionError as SessionError,
)
from reverbscope.version import __version__ as __version__

# Names exported by reverbscope/__init__.py (ARCHITECTURE_V1.md §5.1). Keep this
# tuple and the document in lockstep; tests/unit/test_public_api.py checks both.
TIER1_EXPORTS: tuple[str, ...] = (
    "__version__",
    "analyze",
    "analyze_impulse_response",
    "Reference",
    "compare",
    "ComparisonResult",
    "SweepSettings",
    "AnalysisSettings",
    "AnalysisResult",
    "Validity",
    "DecayResult",
    "BandDecay",
    "DecayMetric",
    "FrequencyResponseResult",
    "NoiseResult",
    "ReflectionsResult",
    "Reflection",
    "ResonanceResult",
    "PlacementResult",
    "LoopbackResult",
    "MeasurementSession",
    "Project",
    "interpret",
    "interpret_comparison",
    "Finding",
    "Severity",
    "available_profiles",
    "read_wav",
    "write_wav",
    "write_sweep_file",
    "load_reference",
    "save_measurement",
    "load_measurement",
    "load_session",
    "list_sessions",
    "ReverbScopeError",
    "ConfigurationError",
    "InvalidAudioError",
    "SampleRateMismatchError",
    "AnalysisError",
    "InsufficientDataError",
    "AudioDeviceError",
    "AudioBackendUnavailableError",
    "SessionError",
)

_LAZY: dict[str, tuple[str, str]] = {
    "analyze": ("reverbscope.core.pipeline", "analyze"),
    "analyze_impulse_response": ("reverbscope.core.pipeline", "analyze_impulse_response"),
    "Reference": ("reverbscope.core.pipeline", "Reference"),
    "compare": ("reverbscope.core.compare", "compare"),
    "ComparisonResult": ("reverbscope.models.comparison", "ComparisonResult"),
    "SweepSettings": ("reverbscope.models.configuration", "SweepSettings"),
    "AnalysisSettings": ("reverbscope.models.configuration", "AnalysisSettings"),
    "AnalysisResult": ("reverbscope.models.result", "AnalysisResult"),
    "Validity": ("reverbscope.models.result", "Validity"),
    "DecayResult": ("reverbscope.models.result", "DecayResult"),
    "BandDecay": ("reverbscope.models.result", "BandDecay"),
    "DecayMetric": ("reverbscope.models.result", "DecayMetric"),
    "FrequencyResponseResult": ("reverbscope.models.result", "FrequencyResponseResult"),
    "NoiseResult": ("reverbscope.models.result", "NoiseResult"),
    "ReflectionsResult": ("reverbscope.models.result", "ReflectionsResult"),
    "Reflection": ("reverbscope.models.result", "Reflection"),
    "ResonanceResult": ("reverbscope.models.result", "ResonanceResult"),
    "PlacementResult": ("reverbscope.models.result", "PlacementResult"),
    "LoopbackResult": ("reverbscope.models.result", "LoopbackResult"),
    "MeasurementSession": ("reverbscope.models.session", "MeasurementSession"),
    "Project": ("reverbscope.models.project", "Project"),
    "interpret": ("reverbscope.interpretation.interpreter", "interpret"),
    "interpret_comparison": ("reverbscope.interpretation.interpreter", "interpret_comparison"),
    "Finding": ("reverbscope.interpretation.interpreter", "Finding"),
    "Severity": ("reverbscope.interpretation.interpreter", "Severity"),
    "available_profiles": ("reverbscope.interpretation.profiles", "available_profiles"),
    "read_wav": ("reverbscope.io.wav", "read_wav"),
    "write_wav": ("reverbscope.io.wav", "write_wav"),
    "write_sweep_file": ("reverbscope.io.wav", "write_sweep_file"),
    "load_reference": ("reverbscope.io.wav", "load_reference"),
    "save_measurement": ("reverbscope.io.session_store", "save_measurement"),
    "load_measurement": ("reverbscope.io.session_store", "load_measurement"),
    "load_session": ("reverbscope.io.session_store", "load_session"),
    "list_sessions": ("reverbscope.io.session_store", "list_sessions"),
}

__all__ = list(TIER1_EXPORTS)


def __getattr__(name: str) -> Any:
    target = _LAZY.get(name)
    if target is None:
        raise AttributeError(f"module 'reverbscope' has no attribute {name!r}")
    module_name, attr = target
    from importlib import import_module

    value = getattr(import_module(module_name), attr)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(TIER1_EXPORTS))
