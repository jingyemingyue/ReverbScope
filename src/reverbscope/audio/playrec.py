"""Compatibility wrapper around :func:`reverbscope.audio.backend.get_backend`.

Safety rules (docs/PROJECT_BRIEF.zh-CN.md, section 12): the default level is
conservative, the caller must show :data:`SAFETY_MESSAGE` before the first
measurement, and this module never changes system volume, device settings or
anything outside the stream it opens.
"""

from __future__ import annotations

from reverbscope.audio.backend import (
    DEFAULT_STANDALONE_LEVEL_DBFS,
    SAFE_MAX_LEVEL_DBFS,
    SAFETY_MESSAGE,
    get_backend,
    scale_to_level,
)
from reverbscope.models.audio import AudioSignal, FloatArray

__all__ = [
    "DEFAULT_STANDALONE_LEVEL_DBFS",
    "SAFETY_MESSAGE",
    "SAFE_MAX_LEVEL_DBFS",
    "play_and_record",
    "scale_to_level",
]


def play_and_record(
    signal: FloatArray,
    sample_rate: int,
    *,
    input_device: int | None,
    output_device: int | None,
    input_channel: int = 1,
    output_channel: int = 1,
    level_dbfs: float = DEFAULT_STANDALONE_LEVEL_DBFS,
    extra_record_s: float = 0.0,
) -> AudioSignal:
    """Play ``signal`` on ``output_channel`` (1-based) while recording
    ``input_channel`` (1-based). Returns the mono recording.

    Uses the backend selected by :func:`get_backend`. Prefer calling a
    backend's ``play_and_record`` directly when you need progress, Stop or
    several input channels.
    """
    return get_backend().play_and_record(
        signal,
        sample_rate,
        input_device=input_device,
        output_device=output_device,
        input_channels=[input_channel],
        output_channel=output_channel,
        level_dbfs=level_dbfs,
        extra_record_s=extra_record_s,
    )
