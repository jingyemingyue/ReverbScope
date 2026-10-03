"""Inventory of every audio device RoomScope can reach, with measurement advice.

A sweep measurement needs one sample clock for playback and recording, no
sample-rate conversion and no processing in the path (Müller & Massarani
2001; Farina 2007; see docs/AUDIO_DEVICES.md). The operating system offers
the same interface several times, once per host API, and those paths differ
exactly in that respect: a Windows interface appears under MME, DirectSound,
WASAPI and WDM-KS; an ALSA card appears as ``hw:`` and through ``default`` /
``pulse`` / ``pipewire``. This module lists every host API and device,
probes which of RoomScope's sample rates each device accepts for one channel
(PortAudio's ``Pa_IsFormatSupported`` through the backend's
``check_sample_rate``; nothing is played, although Core Audio and ALSA open
the device briefly to answer), groups the entries that are the same physical
device, and marks the path RoomScope recommends for each group.

What "supported" means depends on the host API (docs/AUDIO_DEVICES.md §4):
WASAPI shared mode accepts only the device's Default Format rate; PortAudio
does not check the rate on DirectSound, so every rate looks accepted there;
MME, DirectSound, ALSA ``default`` / ``pulse`` / ``pipewire`` and Core Audio
(unless told not to) convert a rate the device is not running at.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field, replace
from typing import Any

from roomscope.audio.backend import AudioBackend, DeviceInfo, StreamOptions
from roomscope.audio.referenced import (
    HOST_API_DOCUMENTED_LATENCY,
    REFERENCED_HOST_API_LATENCY,
    referenced_catalog_dict,
)
from roomscope.errors import RoomScopeError
from roomscope.i18n import _, diag
from roomscope.models.configuration import SUPPORTED_SAMPLE_RATES

#: PortAudio host API names (as PortAudio reports them) -> short kind.
HOST_API_KINDS: dict[str, str] = {
    "Windows WASAPI": "wasapi",
    "Windows WDM-KS": "wdmks",
    "ASIO": "asio",
    "Windows DirectSound": "directsound",
    "MME": "mme",
    "Core Audio": "coreaudio",
    "ALSA": "alsa",
    "JACK Audio Connection Kit": "jack",
    "OSS": "oss",
    "fake": "fake",
}

#: Preference per platform, best first. Paths that bypass the system mixer
#: (WASAPI exclusive / WDM-KS / ASIO, ALSA ``hw:``) and keep one clock rank
#: above shared-mode paths that may resample and mix.
HOST_API_PREFERENCE: dict[str, tuple[str, ...]] = {
    "win32": ("wasapi", "asio", "wdmks", "directsound", "mme"),
    "darwin": ("coreaudio",),
    "linux": ("alsa", "jack", "oss"),
}

#: One sentence per host API on what matters for a measurement. Stored in the
#: JSON reports in English (:func:`~roomscope.i18n.diag`); shown with
#: :func:`~roomscope.i18n.localize`.
HOST_API_NOTES: dict[str, str] = {
    "wasapi": diag(
        "WASAPI: shared mode goes through the Windows audio engine and accepts only the "
        "device's Default Format rate; exclusive mode (--wasapi-exclusive) bypasses the "
        "engine at a rate the hardware supports"
    ),
    "wdmks": diag(
        "WDM kernel streaming: bypasses the Windows mixer; the device must support the rate"
    ),
    "asio": diag("ASIO: direct driver path (not included in RoomScope's desktop bundles)"),
    "directsound": diag(
        "DirectSound: deprecated, runs on the Windows audio engine; resamples and mixes, "
        "and PortAudio does not check its rates (all look accepted); prefer WASAPI"
    ),
    "mme": diag(
        "MME: legacy path through the Windows audio engine; resamples and mixes, truncates "
        "device names; prefer WASAPI"
    ),
    "coreaudio": diag(
        "Core Audio: the device runs at its nominal rate (Audio MIDI Setup) and PortAudio "
        "converts other rates, unless --coreaudio-set-rate sets the device rate and refuses "
        "to convert"
    ),
    "alsa": diag(
        "ALSA: a hw: device is direct; default, pulse, pipewire, dmix and plug devices may resample"
    ),
    "jack": diag("JACK: runs at the JACK server's rate only"),
    "oss": diag("OSS: legacy Linux interface"),
    "fake": diag("synthetic backend: nothing is played"),
}

#: PortAudio name for each known kind (the inverse of :data:`HOST_API_KINDS`).
HOST_API_NAMES: dict[str, str] = {kind: name for name, kind in HOST_API_KINDS.items()}

#: ALSA device names that are plugins or sound servers rather than hardware.
_ALSA_VIRTUAL = re.compile(
    r"^(default|sysdefault|pulse|pipewire|jack|dmix|dsnoop|plug|samplerate|speexrate|"
    r"upmix|vdownmix|lavrate|surround\d*|front|rear|center_lfe|side|iec958|spdif|hdmi|"
    r"null|oss)\b",
    re.IGNORECASE,
)
_ALSA_HW = re.compile(r"\(hw:\s*\d+\s*,\s*\d+\)")
#: MME truncates device names to 31 characters.
_MME_NAME_LENGTH = 31


def host_api_kind(name: str) -> str:
    return HOST_API_KINDS.get(name, name.strip().lower().replace(" ", "_") or "unknown")


def physical_key(device: DeviceInfo) -> str:
    """Key shared by the entries of one physical device across host APIs."""
    name = device.name.strip().lower()
    name = _ALSA_HW.sub("", name).strip()
    name = re.sub(r"\s+", " ", name)
    return name[:_MME_NAME_LENGTH].rstrip()


def adapter_key(device: DeviceInfo) -> str:
    """The hardware adapter behind an endpoint name.

    Windows names endpoints "<endpoint> (<adapter>)" ("Line (Focusrite USB
    Audio)", "Speakers (Focusrite USB Audio)"), MME cuts that at 31
    characters, and ALSA names hardware "<card>: <device> (hw:X,Y)".
    """
    name = device.name.strip()
    if host_api_kind(device.host_api) == "alsa" and ":" in name:
        return name.split(":", 1)[0].strip().lower()
    if "(" in name:
        inner = name.split("(", 1)[1].rstrip(") ").strip()
        if inner:
            return inner.lower()
    return physical_key(device)


def same_adapter(a: DeviceInfo, b: DeviceInfo) -> bool:
    """True when two endpoints belong to one adapter (one sample clock).

    A truncated MME name matches the full name it starts with.
    """
    ka, kb = adapter_key(a), adapter_key(b)
    if not ka or not kb:
        return False
    short, long_ = sorted((ka, kb), key=len)
    return (long_.startswith(short) and len(short) >= 8) or ka == kb


def is_direct_path(device: DeviceInfo) -> bool:
    """True for paths that do not go through a system mixer or resampler."""
    kind = host_api_kind(device.host_api)
    # Core Audio converts by default, WASAPI shared goes through the engine:
    # both become direct only through stream options.
    if kind in {"wdmks", "asio", "jack", "fake"}:
        return True
    if kind == "alsa":
        return bool(_ALSA_HW.search(device.name)) and not _ALSA_VIRTUAL.match(device.name)
    # WASAPI is direct only in exclusive mode, which is a stream option.
    return False


@dataclass(frozen=True)
class HostApiInfo:
    index: int
    name: str
    kind: str
    device_count: int
    default_input: int | None
    default_output: int | None
    rank: int | None
    note: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DeviceProbe:
    """One device entry, what it accepts, and whether RoomScope recommends it."""

    device: DeviceInfo
    host_api_kind: str
    #: Sample rates (Hz) the host API accepts for 1 input / 1 output channel.
    input_rates: tuple[int, ...] = ()
    output_rates: tuple[int, ...] = ()
    #: Entries sharing this key are the same physical device.
    group: str = ""
    direct_path: bool = False
    recommended_input: bool = False
    recommended_output: bool = False
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["device"] = asdict(self.device)
        return data


@dataclass(frozen=True)
class HostApiCatalogEntry:
    """One known host API, from :data:`HOST_API_KINDS` plus this machine's table."""

    kind: str
    name: str
    rank: int | None
    present: bool
    device_count: int
    documented_low_latency_s: float | None
    documented_high_latency_s: float | None
    documented_latency_note: str
    note: str
    documented_latency_source_url: str = ""
    documented_latency_source_locator: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DeviceInventory:
    platform: str
    backend: str
    portaudio_version: str | None
    host_apis: tuple[HostApiInfo, ...]
    devices: tuple[DeviceProbe, ...]
    rates_probed: tuple[int, ...]
    notes: tuple[str, ...] = field(default=())
    #: Rates RoomScope will ask a device to accept (not a hardware result).
    supported_sample_rates: tuple[int, ...] = SUPPORTED_SAMPLE_RATES
    #: Every host API RoomScope knows, including ones absent on this machine.
    host_api_catalog: tuple[HostApiCatalogEntry, ...] = ()
    #: Manufacturer / repo specs. Not a hardware-matrix result.
    referenced: dict[str, Any] = field(default_factory=referenced_catalog_dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "platform": self.platform,
            "backend": self.backend,
            "portaudio_version": self.portaudio_version,
            "rates_probed": list(self.rates_probed),
            "supported_sample_rates": list(self.supported_sample_rates),
            "host_apis": [api.to_dict() for api in self.host_apis],
            "host_api_catalog": [entry.to_dict() for entry in self.host_api_catalog],
            "devices": [probe.to_dict() for probe in self.devices],
            "notes": list(self.notes),
            "referenced": self.referenced,
        }

    def recommended(self, kind: str) -> list[DeviceProbe]:
        attr = "recommended_input" if kind == "input" else "recommended_output"
        return [probe for probe in self.devices if getattr(probe, attr)]


def _platform_key(platform: str) -> str:
    if platform.startswith("win"):
        return "win32"
    if platform == "darwin":
        return "darwin"
    return "linux"


def _host_api_catalog(present: Sequence[HostApiInfo], platform: str) -> list[HostApiCatalogEntry]:
    """Every kind in :data:`HOST_API_KINDS`, marked present when this machine listed it."""
    by_kind = {api.kind: api for api in present}
    preferred = HOST_API_PREFERENCE.get(_platform_key(platform), ())
    kinds = list(dict.fromkeys([*preferred, *HOST_API_NAMES]))
    catalog: list[HostApiCatalogEntry] = []
    for kind in kinds:
        low, high, latency_note = HOST_API_DOCUMENTED_LATENCY.get(kind, (None, None, ""))
        sourced = REFERENCED_HOST_API_LATENCY.get(kind)
        found = by_kind.get(kind)
        catalog.append(
            HostApiCatalogEntry(
                kind=kind,
                name=found.name if found is not None else HOST_API_NAMES.get(kind, kind),
                rank=_rank(kind, platform),
                present=found is not None,
                device_count=found.device_count if found is not None else 0,
                documented_low_latency_s=low,
                documented_high_latency_s=high,
                documented_latency_note=latency_note,
                documented_latency_source_url=sourced.citation.url if sourced else "",
                documented_latency_source_locator=sourced.citation.locator if sourced else "",
                note=HOST_API_NOTES.get(kind, ""),
            )
        )
    return catalog


def describe_device(device: DeviceInfo) -> str:
    """Name, host API, channel counts and known rates already on ``device``."""
    rates = device.supported_sample_rates
    rate_text = (
        ", ".join(str(rate) for rate in rates) + " Hz"
        if rates
        else f"{device.default_sample_rate:.0f} Hz default"
    )
    return (
        f"{device.name} [{device.host_api}] "
        f"{device.max_input_channels} in / {device.max_output_channels} out; {rate_text}"
    )


def session_audio_interface(
    devices: Sequence[DeviceInfo],
    input_device: int | None,
    output_device: int | None,
) -> str:
    """``MeasurementSession.audio_interface`` from devices the take will open."""
    by_index = {device.index: device for device in devices}

    def pick(index: int | None, default_attr: str) -> DeviceInfo | None:
        if index is not None:
            return by_index.get(index)
        return next((device for device in devices if getattr(device, default_attr)), None)

    inp = pick(input_device, "is_default_input")
    out = pick(output_device, "is_default_output")
    if inp is None and out is None:
        return ""
    if inp is not None and out is not None and inp.index == out.index:
        return describe_device(inp)
    parts: list[str] = []
    if inp is not None:
        parts.append("in: " + describe_device(inp))
    if out is not None:
        parts.append("out: " + describe_device(out))
    return "; ".join(parts)


def _rank(kind: str, platform: str) -> int | None:
    order = HOST_API_PREFERENCE.get(_platform_key(platform), ())
    return order.index(kind) if kind in order else None


def _supported(
    backend: AudioBackend, device: DeviceInfo, rates: Sequence[int], kind: str
) -> tuple[int, ...]:
    accepted: list[int] = []
    for rate in rates:
        try:
            backend.check_sample_rate(device.index, int(rate), kind=kind, channels=1)
        except RoomScopeError:
            continue
        except Exception:  # a driver that fails the query is "not supported"
            continue
        accepted.append(int(rate))
    return tuple(accepted)


def _sort_key(probe: DeviceProbe, platform: str) -> tuple[int, int, int]:
    rank = _rank(probe.host_api_kind, platform)
    return (0 if probe.direct_path else 1, rank if rank is not None else 99, probe.device.index)


def build_inventory(
    backend: AudioBackend,
    *,
    probe_rates: bool = True,
    rates: Sequence[int] = SUPPORTED_SAMPLE_RATES,
    platform: str | None = None,
) -> DeviceInventory:
    """List every device of ``backend``, probe its rates and recommend paths."""
    platform = platform or sys.platform
    devices = backend.list_devices()
    host_apis = _host_apis(backend, devices, platform)
    probes: list[DeviceProbe] = []
    for device in devices:
        kind = host_api_kind(device.host_api)
        notes: list[str] = []
        note = HOST_API_NOTES.get(kind)
        if note:
            notes.append(note)
        if kind == "alsa" and _ALSA_VIRTUAL.match(device.name):
            notes.append(diag("ALSA plugin or sound-server device: may resample and mix"))
        advertised = tuple(int(rate) for rate in device.supported_sample_rates)
        if probe_rates:
            input_rates = _supported(backend, device, rates, "input") if device.is_input else ()
            output_rates = _supported(backend, device, rates, "output") if device.is_output else ()
        elif advertised:
            # Backend-advertised rates (the fake device lists SUPPORTED_SAMPLE_RATES).
            # Not a PortAudio probe and not a hardware-matrix result.
            input_rates = advertised if device.is_input else ()
            output_rates = advertised if device.is_output else ()
        else:
            input_rates = ()
            output_rates = ()
        if probe_rates and device.is_input and not input_rates:
            notes.append(diag("accepts none of RoomScope's sample rates for recording"))
        if probe_rates and device.is_output and not output_rates:
            notes.append(diag("accepts none of RoomScope's sample rates for playback"))
        probes.append(
            DeviceProbe(
                device=device,
                host_api_kind=kind,
                input_rates=input_rates,
                output_rates=output_rates,
                group=physical_key(device),
                direct_path=is_direct_path(device),
                notes=tuple(notes),
            )
        )
    probes = _mark_recommended(probes, platform, probe_rates)
    inventory_notes: list[str] = []
    if not probes:
        inventory_notes.append(diag("no audio device found; Universal DAW Mode still works"))
    return DeviceInventory(
        platform=platform,
        backend=getattr(backend, "name", "unknown"),
        portaudio_version=_portaudio_version(backend),
        host_apis=tuple(host_apis),
        devices=tuple(probes),
        rates_probed=tuple(int(rate) for rate in rates) if probe_rates else (),
        notes=tuple(inventory_notes),
        supported_sample_rates=tuple(int(rate) for rate in rates),
        host_api_catalog=tuple(_host_api_catalog(host_apis, platform)),
    )


def _mark_recommended(
    probes: list[DeviceProbe], platform: str, probe_rates: bool
) -> list[DeviceProbe]:
    """Recommend, per physical device and direction, the best-ranked usable entry."""
    best: dict[tuple[str, str], DeviceProbe] = {}
    for probe in probes:
        for direction in ("input", "output"):
            has = probe.device.is_input if direction == "input" else probe.device.is_output
            rates = probe.input_rates if direction == "input" else probe.output_rates
            if not has or (probe_rates and not rates):
                continue
            key = (probe.group, direction)
            current = best.get(key)
            if current is None or _sort_key(probe, platform) < _sort_key(current, platform):
                best[key] = probe
    marked: list[DeviceProbe] = []
    for probe in probes:
        marked.append(
            replace(
                probe,
                recommended_input=best.get((probe.group, "input")) is probe,
                recommended_output=best.get((probe.group, "output")) is probe,
            )
        )
    return marked


def _host_apis(
    backend: AudioBackend, devices: Sequence[DeviceInfo], platform: str
) -> list[HostApiInfo]:
    raw = _query_host_apis(backend)
    if raw is None:
        names = sorted({device.host_api for device in devices})
        # Without PortAudio's table (the fake backend), a host API's default
        # devices are its devices marked as the system defaults.
        raw = [
            {
                "name": name,
                "devices": [d.index for d in devices if d.host_api == name],
                "default_input_device": next(
                    (d.index for d in devices if d.host_api == name and d.is_default_input), -1
                ),
                "default_output_device": next(
                    (d.index for d in devices if d.host_api == name and d.is_default_output), -1
                ),
            }
            for name in names
        ]
    apis: list[HostApiInfo] = []
    for index, info in enumerate(raw):
        name = str(info.get("name", f"host API {index}"))
        kind = host_api_kind(name)
        default_in = int(info.get("default_input_device", -1))
        default_out = int(info.get("default_output_device", -1))
        apis.append(
            HostApiInfo(
                index=index,
                name=name,
                kind=kind,
                device_count=len(info.get("devices", ())),
                default_input=default_in if default_in >= 0 else None,
                default_output=default_out if default_out >= 0 else None,
                rank=_rank(kind, platform),
                note=HOST_API_NOTES.get(kind, ""),
            )
        )
    return apis


def _query_host_apis(backend: AudioBackend) -> list[dict[str, Any]] | None:
    if getattr(backend, "name", "") != "portaudio":
        return None
    try:
        from roomscope.audio.devices import sounddevice_module

        return [dict(api) for api in sounddevice_module().query_hostapis()]
    except Exception:
        return None


def _portaudio_version(backend: AudioBackend) -> str | None:
    if getattr(backend, "name", "") != "portaudio":
        return None
    try:
        from roomscope.audio.devices import sounddevice_module

        return str(sounddevice_module().get_portaudio_version()[1])
    except Exception:
        return None


def separate_clocks_warning(
    devices: Sequence[DeviceInfo], input_device: int | None, output_device: int | None
) -> str | None:
    """A warning when playback and recording use different physical devices.

    Two devices run on two sample clocks; the drift between them stretches the
    recorded sweep against the reference and smears the deconvolved response
    (Farina 2007). One interface for both, or an aggregate device with drift
    correction, avoids it.
    """
    by_index = {device.index: device for device in devices}
    inp = by_index.get(input_device) if input_device is not None else None
    out = by_index.get(output_device) if output_device is not None else None
    if inp is None:
        inp = next((d for d in devices if d.is_default_input), None)
    if out is None:
        out = next((d for d in devices if d.is_default_output), None)
    if inp is None or out is None or host_api_kind(inp.host_api) == "fake":
        return None
    if same_adapter(inp, out):
        return None
    return _(
        "playback ({output}) and recording ({input}) use different devices, which run on "
        "separate sample clocks; their drift smears the measurement. Use one interface for both, "
        "or an aggregate device with drift correction (macOS), and check the result with a "
        "loopback"
    ).format(output=out.name, input=inp.name)


def check_channels(
    devices: Sequence[DeviceInfo],
    *,
    input_device: int | None,
    output_device: int | None,
    input_channels: Sequence[int],
    output_channel: int,
) -> None:
    """Refuse channels the selected devices do not have, before anything is played."""
    from roomscope.errors import ConfigurationError

    by_index = {device.index: device for device in devices}

    def pick(index: int | None, default_attr: str) -> DeviceInfo | None:
        if index is not None:
            return by_index.get(index)
        return next((d for d in devices if getattr(d, default_attr)), None)

    inp = pick(input_device, "is_default_input")
    out = pick(output_device, "is_default_output")
    if inp is not None and input_channels and max(input_channels) > inp.max_input_channels:
        raise ConfigurationError(
            _(
                "input channel {channel} does not exist on {device} ({count} input channel(s))"
            ).format(channel=max(input_channels), device=inp.name, count=inp.max_input_channels)
        )
    if out is not None and output_channel > out.max_output_channels:
        raise ConfigurationError(
            _(
                "output channel {channel} does not exist on {device} ({count} output channel(s))"
            ).format(channel=output_channel, device=out.name, count=out.max_output_channels)
        )


def resolve_duplex(
    devices: Sequence[DeviceInfo],
    host_apis: Sequence[HostApiInfo],
    input_device: int | None,
    output_device: int | None,
) -> tuple[int | None, int | None]:
    """Input and output devices for one full-duplex stream on one host API.

    PortAudio opens a full-duplex stream only when both devices belong to the
    same host API (otherwise ``Pa_OpenStream`` fails with
    ``paBadIODeviceCombination``, "Illegal combination of I/O devices"). When
    only one device is chosen, the other side becomes that host API's default
    device (on Windows the system default is MME's, which would not match a
    WASAPI choice). Both ``None`` keeps PortAudio's defaults.
    """
    from roomscope.errors import ConfigurationError

    if input_device is None and output_device is None:
        return None, None
    by_index = {device.index: device for device in devices}
    for index in (input_device, output_device):
        if index is not None and index not in by_index:
            raise ConfigurationError(_("there is no audio device {index}").format(index=index))
    chosen_in = by_index.get(input_device) if input_device is not None else None
    chosen_out = by_index.get(output_device) if output_device is not None else None
    if chosen_in is not None and chosen_out is not None:
        if chosen_in.host_api != chosen_out.host_api:
            raise ConfigurationError(
                _(
                    "input {input} ({input_api}) and output {output} ({output_api}) belong to "
                    "different host APIs; PortAudio records and plays in one stream only within "
                    "one host API. Choose both on the same host API"
                ).format(
                    input=repr(chosen_in.name),
                    input_api=chosen_in.host_api,
                    output=repr(chosen_out.name),
                    output_api=chosen_out.host_api,
                )
            )
        return input_device, output_device
    anchor = chosen_in or chosen_out
    assert anchor is not None
    api = next((a for a in host_apis if a.name == anchor.host_api), None)
    if chosen_in is None:
        other = api.default_input if api is not None else None
        missing = _("{api} has no default input device; choose the input device on {api} as well")
    else:
        other = api.default_output if api is not None else None
        missing = _("{api} has no default output device; choose the output device on {api} as well")
    if other is None or other not in by_index:
        raise ConfigurationError(missing.format(api=anchor.host_api))
    return (other, output_device) if chosen_in is None else (input_device, other)


@dataclass(frozen=True)
class DevicePlan:
    """The devices a Standalone take will open, after :func:`preflight`."""

    input_device: int | None
    output_device: int | None
    #: Set when playback and recording run on two sample clocks.
    clock_warning: str | None = None


def preflight(
    backend: AudioBackend,
    inventory: DeviceInventory,
    *,
    input_device: int | None,
    output_device: int | None,
    input_channels: Sequence[int],
    output_channel: int,
    sample_rate: int,
    options: StreamOptions | None = None,
) -> DevicePlan:
    """Everything the GUI and the CLI check before a Standalone take plays a sample.

    In this order, so each check sees the devices the stream will open:
    both directions on one host API (:func:`resolve_duplex`), the channels
    exist (:func:`check_channels`), each device accepts ``sample_rate`` with
    the channel count the stream opens (``max(input_channels)`` in,
    ``output_channel`` out) and the stream's host-API ``options`` (WASAPI
    exclusive accepts rates shared mode refuses; ``Pa_IsFormatSupported``,
    nothing is played), and
    a warning for separate clocks. A ``None`` device is PortAudio's default.
    Raises :class:`~roomscope.errors.ConfigurationError` for the device or
    channel choice and :class:`~roomscope.errors.AudioDeviceError` for a rate
    the device refuses.
    """
    devices = [probe.device for probe in inventory.devices]
    inp, out = resolve_duplex(devices, inventory.host_apis, input_device, output_device)
    check_channels(
        devices,
        input_device=inp,
        output_device=out,
        input_channels=input_channels,
        output_channel=output_channel,
    )
    for kind, index, channels, default_attr in (
        ("input", inp, max(input_channels, default=1), "is_default_input"),
        ("output", out, output_channel, "is_default_output"),
    ):
        device = (
            next((d for d in devices if d.index == index), None)
            if index is not None
            else next((d for d in devices if getattr(d, default_attr)), None)
        )
        if device is not None:
            check_host_api_options(device, options)
            backend.check_sample_rate(
                device.index, sample_rate, kind=kind, channels=channels, options=options
            )
    return DevicePlan(inp, out, separate_clocks_warning(devices, inp, out))


def check_host_api_options(device: DeviceInfo, options: StreamOptions | None) -> None:
    """Refuse a host-API option the stream would silently drop on ``device``.

    The stream applies WASAPI exclusive mode only on a Windows WASAPI device
    and the Core Audio rate change only on a Core Audio device
    (:func:`roomscope.audio.portaudio.host_api_settings`); anywhere else the
    take would run in the default shared mode while the user believes the
    option was used. The GUI offers each option only for its host API.
    """
    from roomscope.errors import ConfigurationError

    if options is None:
        return
    if options.wasapi_exclusive and device.host_api != "Windows WASAPI":
        raise ConfigurationError(
            _(
                "WASAPI exclusive mode was requested, but {device} is a {api} device; "
                "choose a Windows WASAPI device or drop --wasapi-exclusive"
            ).format(device=repr(device.name), api=device.host_api)
        )
    if options.coreaudio_change_device_rate and device.host_api != "Core Audio":
        raise ConfigurationError(
            _(
                "setting the Core Audio device rate was requested, but {device} is a {api} "
                "device; drop --coreaudio-set-rate"
            ).format(device=repr(device.name), api=device.host_api)
        )
