"""``sounddevice_module`` must treat a failed PortAudio start as "no backend".

On Ubuntu CI without a PulseAudio server, ``import sounddevice`` raises
``PortAudioError`` during ``Pa_Initialize`` (not ``ImportError`` / ``OSError``).
Standalone Mode then needs a clear unavailable error; Universal DAW Mode and
offline analysis must keep working. Unexpected programming errors during
import must still surface.
"""

from __future__ import annotations

import builtins
import sys
from types import ModuleType

import pytest

from reverbscope.audio import devices
from reverbscope.errors import AudioBackendUnavailableError


def _without_cached_sounddevice(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delitem(sys.modules, "sounddevice", raising=False)


def _raise_on_sounddevice_import(monkeypatch: pytest.MonkeyPatch, exc: BaseException) -> None:
    real_import = builtins.__import__

    def fake_import(
        name: str,
        globals: object = None,
        locals: object = None,
        fromlist: tuple[str, ...] = (),
        level: int = 0,
    ) -> object:
        if name == "sounddevice" or name.startswith("sounddevice."):
            raise exc
        return real_import(name, globals, locals, fromlist, level)

    _without_cached_sounddevice(monkeypatch)
    monkeypatch.setattr(builtins, "__import__", fake_import)


def test_a_missing_sounddevice_package_is_backend_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _raise_on_sounddevice_import(monkeypatch, ImportError("No module named 'sounddevice'"))
    with pytest.raises(AudioBackendUnavailableError) as caught:
        devices.sounddevice_module()
    assert isinstance(caught.value.__cause__, ImportError)


def test_a_missing_native_library_is_backend_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _raise_on_sounddevice_import(
        monkeypatch, OSError("libportaudio.so.2: cannot open shared object file")
    )
    with pytest.raises(AudioBackendUnavailableError) as caught:
        devices.sounddevice_module()
    assert isinstance(caught.value.__cause__, OSError)


def test_a_portaudio_init_failure_at_import_is_backend_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PulseAudio with no server: sounddevice raises PortAudioError while importing."""

    class PortAudioError(Exception):
        pass

    PortAudioError.__module__ = "sounddevice"
    _raise_on_sounddevice_import(
        monkeypatch,
        PortAudioError(
            "Error initializing PortAudio: Unanticipated host error "
            "[PaErrorCode -9999]: 'PulseAudio_Initialize: Can't connect to server'"
        ),
    )
    with pytest.raises(AudioBackendUnavailableError) as caught:
        devices.sounddevice_module()
    assert type(caught.value.__cause__).__name__ == "PortAudioError"
    assert "PulseAudio" in str(caught.value.__cause__)


def test_an_unexpected_runtime_error_at_import_is_not_converted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _raise_on_sounddevice_import(monkeypatch, RuntimeError("programmer mistake in loader"))
    with pytest.raises(RuntimeError, match="programmer mistake"):
        devices.sounddevice_module()


def test_a_working_sounddevice_import_returns_the_module(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stub = ModuleType("sounddevice")
    stub.__dict__["marker"] = "ok"  # type: ignore[attr-defined]
    _without_cached_sounddevice(monkeypatch)
    monkeypatch.setitem(sys.modules, "sounddevice", stub)
    assert devices.sounddevice_module() is stub


def test_list_devices_surfaces_init_failure_as_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``PortAudioBackend.list_devices`` goes through ``sounddevice_module`` first."""

    class PortAudioError(Exception):
        pass

    PortAudioError.__module__ = "sounddevice"
    _raise_on_sounddevice_import(
        monkeypatch, PortAudioError("Error initializing PortAudio: Can't connect to server")
    )
    with pytest.raises(AudioBackendUnavailableError):
        devices.list_devices()
