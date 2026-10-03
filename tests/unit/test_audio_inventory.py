"""Device inventory, host-API resolution and stream options against a simulated
Windows machine: one USB interface listed under MME, DirectSound, WASAPI and
WDM-KS (PortAudio reports every device once per host API; MME truncates the
name to 31 characters), plus the laptop's own speakers. Nothing is played and
no PortAudio is loaded; this is not hardware evidence (docs/HARDWARE_TESTS.md).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from roomscope.audio.backend import DeviceInfo, StreamOptions
from roomscope.audio.inventory import (
    build_inventory,
    check_channels,
    check_host_api_options,
    physical_key,
    preflight,
    resolve_duplex,
    separate_clocks_warning,
    session_audio_interface,
)
from roomscope.errors import AudioDeviceError, ConfigurationError
from roomscope.models.configuration import SUPPORTED_SAMPLE_RATES
from roomscope.models.session import STANDALONE_BIT_DEPTH

HOST_APIS = [
    {"name": "MME", "devices": [0, 1, 2], "default_input_device": 0, "default_output_device": 1},
    {
        "name": "Windows DirectSound",
        "devices": [3, 4],
        "default_input_device": 3,
        "default_output_device": 4,
    },
    {
        "name": "Windows WASAPI",
        "devices": [5, 6, 7],
        "default_input_device": 5,
        "default_output_device": 6,
    },
    {
        "name": "Windows WDM-KS",
        "devices": [8, 9],
        "default_input_device": 8,
        "default_output_device": 9,
    },
]

#: (index, name, host API index, inputs, outputs, accepted rates)
RAW = [
    (0, "Line (Focusrite USB Audio Inter", 0, 2, 0, {44100, 48000, 96000}),
    (1, "Speakers (Focusrite USB Audio I", 0, 0, 2, {44100, 48000, 96000}),
    (2, "Speakers (Realtek(R) Audio)", 0, 0, 2, {44100, 48000}),
    (3, "Line (Focusrite USB Audio Interface)", 1, 2, 0, {44100, 48000, 96000}),
    (4, "Speakers (Focusrite USB Audio Interface)", 1, 0, 2, {44100, 48000, 96000}),
    (5, "Line (Focusrite USB Audio Interface)", 2, 2, 0, {48000}),
    (6, "Speakers (Focusrite USB Audio Interface)", 2, 0, 2, {48000}),
    (7, "Speakers (Realtek(R) Audio)", 2, 0, 2, {48000}),
    (8, "Line (Focusrite USB Audio Interface)", 3, 2, 0, {44100, 48000, 88200, 96000}),
    (9, "Speakers (Focusrite USB Audio Interface)", 3, 0, 2, {44100, 48000, 88200, 96000}),
]


def _devices() -> list[DeviceInfo]:
    return [
        DeviceInfo(
            index=index,
            name=name,
            host_api=HOST_APIS[api]["name"],  # type: ignore[arg-type]
            max_input_channels=n_in,
            max_output_channels=n_out,
            default_sample_rate=48000.0,
            is_default_input=index == 0,
            is_default_output=index == 1,
            host_api_index=api,
        )
        for index, name, api, n_in, n_out, _rates in RAW
    ]


@dataclass
class WindowsBackend:
    """An AudioBackend whose check_sample_rate follows the table above."""

    name: str = "portaudio"
    checked: list[tuple[int, int, str]] = field(default_factory=list)

    def list_devices(self) -> list[DeviceInfo]:
        return _devices()

    def check_sample_rate(
        self,
        device: int,
        sample_rate: int,
        *,
        kind: str,
        channels: int | None = None,
        options: StreamOptions | None = None,
    ) -> None:
        assert channels == 1  # probed for one channel, not the device maximum
        assert options is None  # probing asks with PortAudio's defaults
        self.checked.append((device, sample_rate, kind))
        if sample_rate not in RAW[device][5]:
            raise AudioDeviceError(f"{sample_rate} not supported")

    def play_and_record(self, *args: Any, **kwargs: Any) -> Any:  # pragma: no cover
        raise AssertionError("nothing may be played")


@pytest.fixture
def windows(monkeypatch: pytest.MonkeyPatch) -> WindowsBackend:
    from roomscope.audio import inventory

    monkeypatch.setattr(inventory, "_query_host_apis", lambda backend: HOST_APIS)
    monkeypatch.setattr(inventory, "_portaudio_version", lambda backend: "PortAudio V19.7.0")
    return WindowsBackend()


def test_every_host_api_and_device_is_listed(windows: WindowsBackend) -> None:
    inventory = build_inventory(windows, platform="win32")
    assert [api.name for api in inventory.host_apis] == [a["name"] for a in HOST_APIS]
    assert len(inventory.devices) == len(RAW)
    assert {api.kind for api in inventory.host_apis} == {"mme", "directsound", "wasapi", "wdmks"}
    wasapi = next(api for api in inventory.host_apis if api.kind == "wasapi")
    assert wasapi.rank == 0 and wasapi.default_output == 6
    assert inventory.portaudio_version == "PortAudio V19.7.0"


def test_rates_are_probed_per_direction(windows: WindowsBackend) -> None:
    inventory = build_inventory(windows, platform="win32")
    by_index = {probe.device.index: probe for probe in inventory.devices}
    assert by_index[8].input_rates == (44100, 48000, 88200, 96000)
    assert by_index[8].output_rates == ()
    assert by_index[6].output_rates == (48000,)
    # An input-only device is never asked for output rates.
    assert all(kind == "input" for device, _rate, kind in windows.checked if device == 0)


def test_one_physical_device_is_grouped_across_host_apis() -> None:
    devices = _devices()
    # MME's truncated "Line (Focusrite USB Audio Inter" matches the full name.
    assert physical_key(devices[0]) == physical_key(devices[3]) == physical_key(devices[5])
    assert physical_key(devices[2]) == physical_key(devices[7])
    assert physical_key(devices[1]) != physical_key(devices[2])


def test_the_preferred_host_api_is_recommended(windows: WindowsBackend) -> None:
    inventory = build_inventory(windows, platform="win32")
    recommended_in = {p.device.index for p in inventory.recommended("input")}
    recommended_out = {p.device.index for p in inventory.recommended("output")}
    # WDM-KS bypasses the mixer (a direct path) and wins over WASAPI shared;
    # MME and DirectSound are never recommended while a better path exists.
    assert recommended_in == {8}
    assert recommended_out == {9, 7}
    mme = next(p for p in inventory.devices if p.device.index == 0)
    assert any("prefer WASAPI" in note for note in mme.notes)


def test_duplex_devices_are_kept_on_one_host_api(windows: WindowsBackend) -> None:
    inventory = build_inventory(windows, probe_rates=False, platform="win32")
    devices = [p.device for p in inventory.devices]
    # A WASAPI input with the "system default" output uses WASAPI's default output,
    # not the MME default (PortAudio refuses mixed host APIs).
    assert resolve_duplex(devices, inventory.host_apis, 5, None) == (5, 6)
    assert resolve_duplex(devices, inventory.host_apis, None, 9) == (8, 9)
    assert resolve_duplex(devices, inventory.host_apis, None, None) == (None, None)
    with pytest.raises(ConfigurationError, match="different host APIs"):
        resolve_duplex(devices, inventory.host_apis, 5, 1)
    with pytest.raises(ConfigurationError, match="no audio device 42"):
        resolve_duplex(devices, inventory.host_apis, 42, None)


def test_channels_are_checked_before_playing() -> None:
    devices = _devices()
    check_channels(
        devices, input_device=5, output_device=6, input_channels=[1, 2], output_channel=2
    )
    with pytest.raises(ConfigurationError, match="input channel 3 does not exist"):
        check_channels(
            devices, input_device=5, output_device=6, input_channels=[1, 3], output_channel=1
        )
    with pytest.raises(ConfigurationError, match="output channel 3 does not exist"):
        check_channels(
            devices, input_device=5, output_device=6, input_channels=[1], output_channel=3
        )


@dataclass
class StreamCheckBackend:
    """Records the (device, rate, kind, channels) a pre-flight asks about."""

    name: str = "portaudio"
    checked: list[tuple[int, int, str, int | None]] = field(default_factory=list)
    options: list[StreamOptions | None] = field(default_factory=list)

    def list_devices(self) -> list[DeviceInfo]:
        return _devices()

    def check_sample_rate(
        self,
        device: int,
        sample_rate: int,
        *,
        kind: str,
        channels: int | None = None,
        options: StreamOptions | None = None,
    ) -> None:
        self.checked.append((device, sample_rate, kind, channels))
        self.options.append(options)
        if sample_rate not in RAW[device][5]:
            raise AudioDeviceError(f"{kind} device {device} refuses {sample_rate} Hz")

    def play_and_record(self, *args: Any, **kwargs: Any) -> Any:  # pragma: no cover
        raise AssertionError("nothing may be played")


def test_preflight_checks_the_devices_the_stream_will_open(windows: WindowsBackend) -> None:
    """GUI and CLI share this; the rate is asked of the resolved devices."""
    inventory = build_inventory(windows, probe_rates=False, platform="win32")
    backend = StreamCheckBackend()
    plan = preflight(
        backend,
        inventory,
        input_device=None,
        output_device=6,
        input_channels=[1, 2],
        output_channel=2,
        sample_rate=48000,
    )
    assert (plan.input_device, plan.output_device) == (5, 6)
    # The channel counts the stream opens, not one channel and not the maximum.
    assert backend.checked == [(5, 48000, "input", 2), (6, 48000, "output", 2)]
    assert plan.clock_warning is None
    # The system default input (MME, device 0) takes 44.1 kHz; the stream would
    # open WASAPI's default input (device 5), which does not.
    with pytest.raises(AudioDeviceError, match="input device 5"):
        preflight(
            backend,
            inventory,
            input_device=None,
            output_device=6,
            input_channels=[1],
            output_channel=1,
            sample_rate=44100,
        )
    # A missing channel is refused before any device is queried.
    backend.checked.clear()
    with pytest.raises(ConfigurationError, match="input channel 3"):
        preflight(
            backend,
            inventory,
            input_device=5,
            output_device=6,
            input_channels=[3],
            output_channel=1,
            sample_rate=48000,
        )
    assert backend.checked == []
    # Nothing chosen: PortAudio's default devices are the ones checked.
    plan = preflight(
        backend,
        inventory,
        input_device=None,
        output_device=None,
        input_channels=[1],
        output_channel=1,
        sample_rate=44100,
    )
    assert (plan.input_device, plan.output_device) == (None, None)
    assert backend.checked == [(0, 44100, "input", 1), (1, 44100, "output", 1)]
    plan = preflight(
        backend,
        inventory,
        input_device=5,
        output_device=7,
        input_channels=[1],
        output_channel=1,
        sample_rate=48000,
    )
    assert plan.clock_warning is not None and "separate sample clocks" in plan.clock_warning
    # The stream's host-API options reach the rate check (WASAPI exclusive).
    exclusive = StreamOptions(wasapi_exclusive=True)
    preflight(
        backend,
        inventory,
        input_device=5,
        output_device=6,
        input_channels=[1],
        output_channel=1,
        sample_rate=48000,
        options=exclusive,
    )
    assert backend.options[-2:] == [exclusive, exclusive]


def test_exclusive_mode_rate_is_checked_in_exclusive_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """Review finding: --wasapi-exclusive at 96 kHz was refused by a shared-mode
    check (shared mode accepts only the engine rate), before the exclusive
    stream that would have run at 96 kHz was ever opened."""
    from roomscope.audio import devices, portaudio

    class SharedOrExclusiveSd(_FakeSd):
        @staticmethod
        def check_input_settings(**kwargs: Any) -> None:
            exclusive = isinstance(kwargs["extra_settings"], _Settings)
            if kwargs["samplerate"] != 48000 and not exclusive:
                raise RuntimeError("Invalid sample rate [PaErrorCode -9997]")

        check_output_settings = check_input_settings

    monkeypatch.setattr(devices, "sounddevice_module", lambda: SharedOrExclusiveSd)
    monkeypatch.setattr(portaudio, "sounddevice_module", lambda: SharedOrExclusiveSd)
    backend = portaudio.PortAudioBackend()
    with pytest.raises(AudioDeviceError, match="does not support 96000 Hz"):
        backend.check_sample_rate(5, 96000, kind="input", channels=1)
    backend.check_sample_rate(
        5, 96000, kind="input", channels=1, options=StreamOptions(wasapi_exclusive=True)
    )


def test_fake_backend_default_devices_resolve(tmp_path: Any) -> None:
    """Review finding: with only one fake device chosen, the other side had no
    host-API default and roomscope measure refused the take."""
    from roomscope.audio.fake import FakeBackend
    from roomscope.cli.main import main

    inventory = build_inventory(FakeBackend(), probe_rates=False)
    devices = [probe.device for probe in inventory.devices]
    assert resolve_duplex(devices, inventory.host_apis, 0, None) == (0, 0)
    assert resolve_duplex(devices, inventory.host_apis, None, 0) == (0, 0)
    measure = ["--backend", "fake", "measure", "--input-device", "0", "--out", str(tmp_path)]
    code = main([*measure, "--duration", "1", "--post-silence", "1"])
    assert code == 0
    import json

    session = json.loads((tmp_path / "session.json").read_text(encoding="utf-8"))
    assert "RoomScope fake interface" in session["audio_interface"]
    assert "8 in / 2 out" in session["audio_interface"]
    assert "44100" in session["audio_interface"]
    assert session["bit_depth"] == STANDALONE_BIT_DEPTH


def test_separate_clocks_are_warned() -> None:
    devices = _devices()
    assert separate_clocks_warning(devices, 5, 6) is None
    # MME's truncated "Line (Focusrite USB Audio Inter" is the same adapter.
    assert separate_clocks_warning(devices, 0, 4) is None
    warning = separate_clocks_warning(devices, 5, 7)
    assert warning is not None and "separate sample clocks" in warning


def test_inventory_includes_software_capability_catalog(windows: WindowsBackend) -> None:
    inventory = build_inventory(windows, platform="win32", probe_rates=False)
    assert inventory.supported_sample_rates == SUPPORTED_SAMPLE_RATES
    kinds = {entry.kind for entry in inventory.host_api_catalog}
    assert {"wasapi", "coreaudio", "alsa", "fake", "mme"}.issubset(kinds)
    wasapi = next(entry for entry in inventory.host_api_catalog if entry.kind == "wasapi")
    assert wasapi.present is True
    assert wasapi.documented_low_latency_s == 0.010
    coreaudio = next(entry for entry in inventory.host_api_catalog if entry.kind == "coreaudio")
    assert coreaudio.present is False
    data = inventory.to_dict()
    assert data["supported_sample_rates"] == list(SUPPORTED_SAMPLE_RATES)
    assert any(entry["kind"] == "alsa" for entry in data["host_api_catalog"])
    oss = next(entry for entry in inventory.host_api_catalog if entry.kind == "oss")
    assert oss.documented_low_latency_s == 0.008
    assert oss.documented_high_latency_s == 0.032
    assert "pa_unix_oss.c" in oss.documented_latency_source_url
    assert "HARDWARE_TESTS.md PASS" in data["referenced"]["disclaimer"]


def test_referenced_catalog_cites_sources_and_leaves_gaps() -> None:
    from roomscope.audio.referenced import (
        REFERENCED_GAPS,
        REFERENCED_HOST_API_LATENCY,
        REFERENCED_INTERFACES,
        REFERENCED_MIXER_DEFAULTS,
        referenced_catalog_dict,
    )

    for entry in REFERENCED_HOST_API_LATENCY.values():
        assert entry.citation.url.startswith("http")
        assert entry.citation.locator
    two_i_two = next(item for item in REFERENCED_INTERFACES if "2i2" in item.name)
    assert two_i_two.analog_inputs == 2 and two_i_two.analog_outputs == 2
    assert two_i_two.sample_rates_hz == (44100, 48000, 88200, 96000, 176400, 192000)
    assert two_i_two.bit_depth == "24-bit"
    assert "userguides.focusrite.com" in two_i_two.citation.url
    eighteen = next(item for item in REFERENCED_INTERFACES if "18i20" in item.name)
    assert eighteen.analog_inputs == 8
    assert eighteen.analog_outputs is None
    babyface = next(item for item in REFERENCED_INTERFACES if "Babyface" in item.name)
    assert babyface.analog_inputs == 4 and babyface.analog_outputs == 4
    assert babyface.sample_rates_hz == ()
    assert babyface.sample_rate_min_hz == 28000
    dmix = next(item for item in REFERENCED_MIXER_DEFAULTS if item.name == "ALSA dmix")
    assert dmix.sample_rate_hz == 48000 and dmix.channels == 2
    assert "alsa-lib" in dmix.citation.url
    assert any("USB Audio Class" in gap for gap in REFERENCED_GAPS)
    catalog = referenced_catalog_dict()
    assert catalog["gaps"]
    assert "Not a RoomScope measurement" in catalog["disclaimer"]


def test_fake_device_advertises_supported_rates_without_probing() -> None:
    from roomscope.audio.fake import FakeBackend

    inventory = build_inventory(FakeBackend(), probe_rates=False)
    probe = inventory.devices[0]
    assert probe.device.max_input_channels == 8
    assert probe.device.max_output_channels == 2
    assert probe.device.supported_sample_rates == SUPPORTED_SAMPLE_RATES
    assert probe.input_rates == SUPPORTED_SAMPLE_RATES
    assert probe.output_rates == SUPPORTED_SAMPLE_RATES
    assert inventory.rates_probed == ()
    assert session_audio_interface([probe.device], 0, 0).startswith("RoomScope fake interface")


def test_json_inventory_round_trips(windows: WindowsBackend) -> None:
    import json

    data = json.loads(json.dumps(build_inventory(windows, platform="win32").to_dict()))
    assert data["platform"] == "win32"
    assert len(data["devices"]) == len(RAW)
    assert data["devices"][8]["recommended_input"] is True


class _Settings:
    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs


class _FakeSd:
    WasapiSettings = _Settings
    CoreAudioSettings = _Settings

    class default:  # noqa: N801 - mirrors sounddevice.default
        device = (0, 1)

    @staticmethod
    def query_devices(index: int) -> dict[str, Any]:
        return {"hostapi": RAW[index][2]}

    @staticmethod
    def query_hostapis(index: int) -> dict[str, Any]:
        return HOST_APIS[index]


def test_stream_options_map_to_the_device_host_api() -> None:
    from roomscope.audio.portaudio import host_api_settings

    exclusive = StreamOptions(wasapi_exclusive=True)
    setting = host_api_settings(_FakeSd, 5, "input", exclusive)
    assert isinstance(setting, _Settings) and setting.kwargs == {"exclusive": True}
    # The same option on an MME device is ignored, not an error.
    assert host_api_settings(_FakeSd, 0, "input", exclusive) is None
    # WASAPI's auto-convert is not offered (it inserts the engine's resampler).
    assert not hasattr(StreamOptions(), "wasapi_auto_convert")


def test_stream_options_are_validated() -> None:
    assert StreamOptions().is_default
    assert not StreamOptions(latency="low").is_default
    with pytest.raises(ConfigurationError):
        StreamOptions(latency="fast")


def test_cli_devices_probe_and_doctor(capsys: pytest.CaptureFixture[str]) -> None:
    from roomscope.cli.main import main

    assert main(["--backend", "fake", "devices", "--probe"]) == 0
    out = capsys.readouterr().out
    assert "recommended input" in out and "44.1 · 48 · 88.2 · 96" in out
    assert main(["--backend", "fake", "devices", "--json"]) == 0
    assert '"devices"' in capsys.readouterr().out
    assert main(["--backend", "fake", "doctor"]) == 0
    report = capsys.readouterr().out
    assert "RoomScope" in report and "numpy" in report and "\nAudio\n" in report
    assert main(["--backend", "fake", "devices", "--referenced"]) == 0
    referenced = capsys.readouterr().out
    assert "Scarlett 2i2" in referenced and "not a HARDWARE_TESTS.md PASS" in referenced
    assert "Babyface Pro FS" in referenced and "Gaps with no citable source" in referenced


def test_edition_follows_environment_and_bundle(monkeypatch: pytest.MonkeyPatch) -> None:
    import sys

    from roomscope.edition import DEVELOPER, USER, edition

    monkeypatch.delenv("ROOMSCOPE_EDITION", raising=False)
    monkeypatch.delattr(sys, "frozen", raising=False)
    assert edition() == DEVELOPER
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert edition() == USER
    monkeypatch.setenv("ROOMSCOPE_EDITION", "developer")
    assert edition() == DEVELOPER


@pytest.mark.parametrize(
    ("options", "device", "message"),
    [
        (StreamOptions(wasapi_exclusive=True), 0, "is a MME device"),
        (StreamOptions(wasapi_exclusive=True), 8, "WASAPI exclusive mode was requested"),
        (StreamOptions(coreaudio_change_device_rate=True), 5, "drop --coreaudio-set-rate"),
    ],
)
def test_host_api_option_on_another_host_api_is_refused(
    options: StreamOptions, device: int, message: str
) -> None:
    """Review finding: `measure --wasapi-exclusive` on the MME default ran a
    shared-mode take without a word, and the tester reported it as exclusive."""
    by_index = {d.index: d for d in _devices()}
    with pytest.raises(ConfigurationError, match=message):
        check_host_api_options(by_index[device], options)
    check_host_api_options(by_index[device], StreamOptions())
    check_host_api_options(by_index[device], None)


def test_preflight_refuses_exclusive_mode_on_the_default_mme_device(
    windows: WindowsBackend,
) -> None:
    inventory = build_inventory(windows, probe_rates=False, platform="win32")
    backend = StreamCheckBackend()
    with pytest.raises(ConfigurationError, match="WASAPI exclusive"):
        preflight(
            backend,
            inventory,
            input_device=None,
            output_device=None,
            input_channels=[1],
            output_channel=1,
            sample_rate=48000,
            options=StreamOptions(wasapi_exclusive=True),
        )
    assert backend.checked == []
