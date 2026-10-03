"""Audio device enumeration through PortAudio (``sounddevice``).

``sounddevice`` is imported lazily so that the DSP core and the Universal DAW
Mode work on systems without a usable PortAudio backend.
"""

from __future__ import annotations

from typing import Any

from reverbscope.audio.backend import DeviceInfo
from reverbscope.errors import AudioBackendUnavailableError, AudioDeviceError
from reverbscope.i18n import _


def sounddevice_module() -> Any:
    try:
        import sounddevice
    except (ImportError, OSError) as exc:
        raise AudioBackendUnavailableError(
            _(
                "the audio backend (sounddevice / PortAudio) is not available; "
                "Standalone Mode needs it, Universal DAW Mode does not"
            )
        ) from exc
    return sounddevice


def list_devices() -> list[DeviceInfo]:
    sd = sounddevice_module()
    try:
        raw = sd.query_devices()
        host_apis = sd.query_hostapis()
        defaults = sd.default.device
    except Exception as exc:
        raise AudioDeviceError(_("cannot query audio devices: {error}").format(error=exc)) from exc
    # sounddevice returns an _InputOutputPair (indexable, not a tuple); -1 is
    # PortAudio's paNoDevice.
    try:
        default_in, default_out = int(defaults[0]), int(defaults[1])
    except (TypeError, IndexError, ValueError):
        default_in = default_out = int(defaults) if isinstance(defaults, int) else -1
    devices: list[DeviceInfo] = []
    for index, info in enumerate(raw):
        api_index = int(info.get("hostapi", 0))
        api_name = (
            str(host_apis[api_index]["name"]) if 0 <= api_index < len(host_apis) else "unknown"
        )
        devices.append(
            DeviceInfo(
                index=index,
                name=str(info.get("name", f"device {index}")),
                host_api=api_name,
                max_input_channels=int(info.get("max_input_channels", 0)),
                max_output_channels=int(info.get("max_output_channels", 0)),
                default_sample_rate=float(info.get("default_samplerate", 0.0)),
                is_default_input=index == default_in,
                is_default_output=index == default_out,
                host_api_index=api_index,
                default_low_input_latency_s=_latency(info, "default_low_input_latency"),
                default_high_input_latency_s=_latency(info, "default_high_input_latency"),
                default_low_output_latency_s=_latency(info, "default_low_output_latency"),
                default_high_output_latency_s=_latency(info, "default_high_output_latency"),
            )
        )
    return devices


def _latency(info: Any, key: str) -> float | None:
    try:
        value = float(info.get(key))
    except (TypeError, ValueError):
        return None
    return value if value >= 0.0 else None


def check_sample_rate(
    device_index: int,
    sample_rate: int,
    *,
    kind: str,
    channels: int | None = None,
    extra_settings: Any = None,
) -> None:
    """Raise :class:`AudioDeviceError` if the device cannot run at ``sample_rate``.

    ``channels=None`` lets sounddevice use the device's maximum channel count,
    which a device may refuse at a rate it supports with fewer channels.
    """
    sd = sounddevice_module()
    try:
        if kind == "input":
            sd.check_input_settings(
                device=device_index,
                samplerate=sample_rate,
                channels=channels,
                extra_settings=extra_settings,
            )
        else:
            sd.check_output_settings(
                device=device_index,
                samplerate=sample_rate,
                channels=channels,
                extra_settings=extra_settings,
            )
    except Exception as exc:
        template = (
            _("input device {device} does not support {rate} Hz: {error}")
            if kind == "input"
            else _("output device {device} does not support {rate} Hz: {error}")
        )
        raise AudioDeviceError(
            template.format(device=device_index, rate=sample_rate, error=exc)
        ) from exc
