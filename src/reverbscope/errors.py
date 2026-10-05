"""Error model for ReverbScope.

Every error raised by ReverbScope derives from :class:`ReverbScopeError` so that
front ends (CLI, GUI) can distinguish expected failures (bad input, missing
device, insufficient data) from programming errors.
"""

from __future__ import annotations


class ReverbScopeError(Exception):
    """Base class for all ReverbScope errors."""


class ConfigurationError(ReverbScopeError, ValueError):
    """A setting or parameter is invalid (wrong range, unsupported value)."""


class InvalidAudioError(ReverbScopeError):
    """An audio file or signal cannot be used (unreadable, empty, silent, wrong format)."""


class SampleRateMismatchError(InvalidAudioError):
    """Reference and recording sample rates differ and cannot be reconciled."""


class AnalysisError(ReverbScopeError):
    """The analysis pipeline could not produce a result."""


class InsufficientDataError(AnalysisError):
    """The data does not contain enough information for the requested metric."""


class AudioDeviceError(ReverbScopeError):
    """An audio device operation (enumeration, playback, recording) failed."""


class AudioBackendUnavailableError(AudioDeviceError):
    """The optional audio backend (sounddevice / PortAudio) is not available."""


class MeasurementCancelledError(ReverbScopeError):
    """Stop was pressed during playback; the output was silenced."""


class SessionError(ReverbScopeError):
    """A measurement session could not be saved or loaded."""
