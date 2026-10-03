"""Audio device access for Standalone Mode (optional; needs ``sounddevice``)."""

from __future__ import annotations

from reverbscope.audio.backend import (
    SAFE_MAX_LEVEL_DBFS,
    SAFETY_MESSAGE,
    AudioBackend,
    DeviceInfo,
    get_backend,
)
from reverbscope.audio.playrec import play_and_record

__all__ = [
    "SAFETY_MESSAGE",
    "SAFE_MAX_LEVEL_DBFS",
    "AudioBackend",
    "DeviceInfo",
    "get_backend",
    "list_devices",
    "play_and_record",
]


def list_devices() -> list[DeviceInfo]:
    from reverbscope.audio.devices import list_devices as _list

    return _list()
