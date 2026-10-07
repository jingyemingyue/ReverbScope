"""Interpretation layer: turns measured numbers into recording-oriented advice.

Strictly separate from the DSP layer: it only reads an :class:`AnalysisResult`
and never changes it. Recording profiles (vocal, drums, ...) plug in through
:class:`RecordingProfile`; pick one with :func:`interpret`'s ``profile_name``.
"""

from __future__ import annotations

from reverbscope.interpretation.interpreter import (
    Finding,
    Severity,
    interpret,
    interpret_comparison,
)
from reverbscope.interpretation.profiles import (
    AcousticGuitarProfile,
    ChoirProfile,
    DrumsProfile,
    GenericProfile,
    ProfileBase,
    RecordingProfile,
    RoomMicProfile,
    VocalProfile,
    VoiceOverProfile,
)
from reverbscope.interpretation.registry import available_profiles, get_profile, profile_origins
from reverbscope.interpretation.verdicts import (
    AspectVerdict,
    ComparisonVerdict,
    Verdict,
    judge_comparison,
)

__all__ = [
    "AcousticGuitarProfile",
    "AspectVerdict",
    "ChoirProfile",
    "ComparisonVerdict",
    "DrumsProfile",
    "Finding",
    "GenericProfile",
    "ProfileBase",
    "RecordingProfile",
    "RoomMicProfile",
    "Severity",
    "Verdict",
    "VocalProfile",
    "VoiceOverProfile",
    "available_profiles",
    "get_profile",
    "interpret",
    "interpret_comparison",
    "judge_comparison",
    "profile_origins",
]
