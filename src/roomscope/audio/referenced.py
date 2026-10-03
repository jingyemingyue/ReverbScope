"""Referenced device parameters from public sources (not RoomScope measurements).

These values fill catalog fields that this machine cannot probe. Each non-empty
field records the source repository or document. They do **not** fill
``docs/HARDWARE_TESTS.md`` and are not Pass/Fail hardware results.

No third-party source was copied: only published numbers and the URLs they
were read from. See ``docs/CODE_PROVENANCE.md`` and ``docs/AUDIO_DEVICES.md``
§4b.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from roomscope.i18n import diag

#: PortAudio tag already cited in docs/AUDIO_DEVICES.md [9]–[12].
PORTAUDIO_TAG = "v19.7.0"
PORTAUDIO_BLOB = f"https://github.com/PortAudio/portaudio/blob/{PORTAUDIO_TAG}"


@dataclass(frozen=True)
class Citation:
    """Where one referenced value was read."""

    title: str
    url: str
    locator: str
    kind: str  # open_source_repo | manufacturer_doc | vendor_doc

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class ReferencedHostApiLatency:
    kind: str
    low_latency_s: float | None
    high_latency_s: float | None
    note: str
    citation: Citation
    #: When the source gives frames/fs, this is the fs used to report milliseconds.
    assumed_sample_rate_hz: int | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["citation"] = self.citation.to_dict()
        return data


@dataclass(frozen=True)
class ReferencedInterface:
    """One interface as a manufacturer or project document states it."""

    name: str
    analog_inputs: int | None
    analog_outputs: int | None
    loopback_inputs: int | None
    sample_rates_hz: tuple[int, ...]
    sample_rate_min_hz: int | None
    sample_rate_max_hz: int | None
    bit_depth: str | None
    extra: str
    citation: Citation
    not_stated: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["citation"] = self.citation.to_dict()
        data["sample_rates_hz"] = list(self.sample_rates_hz)
        data["not_stated"] = list(self.not_stated)
        return data


@dataclass(frozen=True)
class ReferencedMixerDefault:
    name: str
    sample_rate_hz: int | None
    channels: int | None
    extra: str
    citation: Citation

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["citation"] = self.citation.to_dict()
        return data


_PA = PORTAUDIO_BLOB

REFERENCED_HOST_API_LATENCY: dict[str, ReferencedHostApiLatency] = {
    "wasapi": ReferencedHostApiLatency(
        kind="wasapi",
        low_latency_s=0.010,
        high_latency_s=0.010,
        note=diag("shared-mode engine buffer default 10 ms; exclusive uses the device period"),
        citation=Citation(
            title="Microsoft Learn, Low Latency Audio",
            url="https://learn.microsoft.com/en-us/windows-hardware/drivers/audio/low-latency-audio",
            locator="Audio Engine: default shared-mode periodicity 10 ms",
            kind="vendor_doc",
        ),
    ),
    "wdmks": ReferencedHostApiLatency(
        kind="wdmks",
        low_latency_s=0.010,
        high_latency_s=0.040,
        note=diag("WaveRT compiled defaults 10 / 40 ms (WaveCyclic 10 / 85 ms)"),
        citation=Citation(
            title=f"PortAudio {PORTAUDIO_TAG} WDM-KS",
            url=f"{_PA}/src/hostapi/wdmks/pa_win_wdmks.c",
            locator="Type_kWaveRT: defaultLow=0.01, defaultHigh=0.04; "
            "Type_kWaveCyclic: defaultLow=0.01 (0.02 before Vista), "
            "defaultHigh=4096.0/48000.0",
            kind="open_source_repo",
        ),
    ),
    "asio": ReferencedHostApiLatency(
        kind="asio",
        low_latency_s=None,
        high_latency_s=None,
        note=diag("preferred / maximum driver buffer"),
        citation=Citation(
            title=f"PortAudio {PORTAUDIO_TAG} ASIO host API",
            url=f"{_PA}/src/hostapi/asio",
            locator="no compiled second; PortAudio uses the driver's preferred / maximum buffer",
            kind="open_source_repo",
        ),
    ),
    "directsound": ReferencedHostApiLatency(
        kind="directsound",
        low_latency_s=0.120,
        high_latency_s=0.240,
        note=diag("PortAudio compiled defaults 120 / 240 ms"),
        citation=Citation(
            title=f"PortAudio {PORTAUDIO_TAG} DirectSound",
            url=f"{_PA}/src/hostapi/dsound/pa_win_ds.c",
            locator="PA_DS_WIN_WDM_DEFAULT_LATENCY_ (.120); "
            "defaultHighLatency = defaultLowLatency * 2",
            kind="open_source_repo",
        ),
    ),
    "mme": ReferencedHostApiLatency(
        kind="mme",
        low_latency_s=0.090,
        high_latency_s=0.180,
        note=diag("PortAudio compiled defaults 90 / 180 ms"),
        citation=Citation(
            title=f"PortAudio {PORTAUDIO_TAG} MME",
            url=f"{_PA}/src/hostapi/wmme/pa_win_wmme.c",
            locator="PA_MME_WIN_WDM_DEFAULT_LATENCY_ (0.090); "
            "defaultHighLatency = defaultLowLatency * 2 (Windows 2000 and later)",
            kind="open_source_repo",
        ),
    ),
    "coreaudio": ReferencedHostApiLatency(
        kind="coreaudio",
        low_latency_s=0.010,
        high_latency_s=0.100,
        note=diag("fallback 10 / 100 ms when the device latency is unreadable"),
        citation=Citation(
            title=f"PortAudio {PORTAUDIO_TAG} Core Audio",
            url=f"{_PA}/src/hostapi/coreaudio/pa_mac_core.c",
            locator="InitializeDeviceInfoFromDevice: fallback "
            "defaultLowInputLatency = .01, defaultHighInputLatency = .10 "
            "when CalculateDefaultDeviceLatencies fails",
            kind="open_source_repo",
        ),
    ),
    "alsa": ReferencedHostApiLatency(
        kind="alsa",
        low_latency_s=0.008,
        high_latency_s=0.032,
        note=diag(
            "compiled default (512-128)/fs / (2048-512)/fs: 8 / 32 ms at 48 kHz if hardware allows"
        ),
        citation=Citation(
            title=f"PortAudio {PORTAUDIO_TAG} ALSA",
            url=f"{_PA}/src/hostapi/alsa/pa_linux_alsa.c",
            locator="GropeDevice: alsaBufferFrames=512, alsaPeriodFrames=128 then "
            "2048 / 512; latency = (buffer - period) / defaultSr",
            kind="open_source_repo",
        ),
        assumed_sample_rate_hz=48000,
    ),
    "jack": ReferencedHostApiLatency(
        kind="jack",
        low_latency_s=None,
        high_latency_s=None,
        note=diag("port latency divided by the JACK server rate"),
        citation=Citation(
            title=f"PortAudio {PORTAUDIO_TAG} JACK",
            url=f"{_PA}/src/hostapi/jack/pa_jack.c",
            locator="jack_port_get_latency(p) / jack_get_sample_rate; no compiled seconds",
            kind="open_source_repo",
        ),
    ),
    "oss": ReferencedHostApiLatency(
        kind="oss",
        low_latency_s=0.008,
        high_latency_s=0.032,
        note=diag(
            "requested 4 fragments × 128 frames; low=(nfrags-1)*frag/fs "
            "(8 / 32 ms at 48 kHz if the driver keeps those sizes)"
        ),
        citation=Citation(
            title=f"PortAudio {PORTAUDIO_TAG} OSS",
            url=f"{_PA}/src/hostapi/oss/pa_unix_oss.c",
            locator="QueryDirection: 4 fragments, 128 frames-per-frag; "
            "defaultLowLatency = ((frgmt>>16)-1)*fragFrames/rate; "
            "defaultHighLatency = 4 * low when fragFrames < 256",
            kind="open_source_repo",
        ),
        assumed_sample_rate_hz=48000,
    ),
    "fake": ReferencedHostApiLatency(
        kind="fake",
        low_latency_s=None,
        high_latency_s=None,
        note=diag("synthetic backend: nothing is played"),
        citation=Citation(
            title="RoomScope FakeBackend",
            url="https://github.com/jingyemingyue/RoomScope/blob/main/src/roomscope/audio/fake.py",
            locator="FakeBackend.list_devices: synthetic device, nothing is played",
            kind="open_source_repo",
        ),
    ),
}

#: Same numbers the host-API catalog already exposed; citations live above.
HOST_API_DOCUMENTED_LATENCY: dict[str, tuple[float | None, float | None, str]] = {
    kind: (entry.low_latency_s, entry.high_latency_s, entry.note)
    for kind, entry in REFERENCED_HOST_API_LATENCY.items()
}

REFERENCED_INTERFACES: tuple[ReferencedInterface, ...] = (
    ReferencedInterface(
        name="Focusrite Scarlett 2i2 4th Gen",
        analog_inputs=2,
        analog_outputs=2,
        loopback_inputs=2,
        sample_rates_hz=(44100, 48000, 88200, 96000, 176400, 192000),
        sample_rate_min_hz=44100,
        sample_rate_max_hz=192000,
        bit_depth="24-bit",
        extra="Inputs 1–2 are Mic/Line/Inst; outputs 1–2 share the headphone feed; "
        "loopback is two extra record channels. Easy Start is limited to 48 kHz.",
        citation=Citation(
            title="Focusrite, 2i2 4th Gen Specifications",
            url="https://userguides.focusrite.com/hc/en-gb/articles/19640392541202-2i2-4th-Gen-Specifications",
            locator="Supported Sample Rates; Bit Depth 24-bit; Scarlett 2i2 input/output channels",
            kind="manufacturer_doc",
        ),
        not_stated=(
            diag("PortAudio host-API name on a given OS"),
            diag("measured round-trip latency"),
            diag("whether Windows/Core Audio expose loopback as extra channels"),
        ),
    ),
    ReferencedInterface(
        name="Focusrite Scarlett 18i20 4th Gen",
        analog_inputs=8,
        analog_outputs=None,
        loopback_inputs=2,
        sample_rates_hz=(44100, 48000, 88200, 96000, 176400, 192000),
        sample_rate_min_hz=44100,
        sample_rate_max_hz=192000,
        bit_depth="24-bit",
        extra="User guide: eight analogue inputs; ADAT up to 16 channels at 44.1/48 kHz. "
        "Analogue output count was not taken from a page that stated it clearly.",
        citation=Citation(
            title="Focusrite, Using your 18i20 4th Gen / 18i20 4th Gen Specifications",
            url="https://userguides.focusrite.com/hc/en-gb/articles/21616163352722-Using-your-18i20-4th-Gen",
            locator="'eight analogue inputs'; spec table Supported Sample Rates / Bit Depth 24-bit "
            "(https://userguides.focusrite.com/hc/en-gb/articles/21616107507218-18i20-4th-Gen-Specifications)",
            kind="manufacturer_doc",
        ),
        not_stated=(
            diag("analogue line-output count"),
            diag("PortAudio channel count including ADAT at each rate"),
            diag("measured round-trip latency"),
        ),
    ),
    ReferencedInterface(
        name="RME Babyface Pro FS",
        analog_inputs=4,
        analog_outputs=4,
        loopback_inputs=None,
        sample_rates_hz=(),
        sample_rate_min_hz=28000,
        sample_rate_max_hz=200000,
        bit_depth="24-bit",
        extra="Product page: 4 analog inputs, 4 analog outputs (2×XLR + 2×phones); "
        "ADAT 8/4/2 channels at 48/96/192 kHz; 'Supported sample rates: 28 kHz up to 200 kHz'. "
        "No discrete rate list was stated, so RoomScope's six rates are not copied here.",
        citation=Citation(
            title="RME, Babyface Pro FS",
            url="https://rme-audio.de/babyface-pro-fs.html",
            locator="4 x Analog I/O; Supported sample rates: 28 kHz up to 200 kHz; "
            "ADAT Standard / Double Speed / Quad Speed",
            kind="manufacturer_doc",
        ),
        not_stated=(
            diag("discrete sample-rate list (only a 28–200 kHz range is stated)"),
            diag("measured round-trip latency"),
            diag("PortAudio host-API name on a given OS"),
        ),
    ),
)

REFERENCED_MIXER_DEFAULTS: tuple[ReferencedMixerDefault, ...] = (
    ReferencedMixerDefault(
        name="ALSA dmix",
        sample_rate_hz=48000,
        channels=2,
        extra="defaults.pcm.dmix.rate 48000; defaults.pcm.dmix.channels 2",
        citation=Citation(
            title="alsa-lib v1.2.13 alsa.conf",
            url="https://github.com/alsa-project/alsa-lib/blob/v1.2.13/src/conf/alsa.conf",
            locator="defaults.pcm.dmix.rate 48000; defaults.pcm.dmix.channels 2",
            kind="open_source_repo",
        ),
    ),
    ReferencedMixerDefault(
        name="PipeWire graph",
        sample_rate_hz=48000,
        channels=None,
        extra="default.clock.rate = 48000; default.clock.allowed-rates = [ ] "
        "(graph-rate switching off by default)",
        citation=Citation(
            title="PipeWire pipewire.conf(5)",
            url="https://docs.pipewire.org/page_man_pipewire_conf_5.html",
            locator="CONTEXT PROPERTIES: default.clock.rate = 48000; "
            "default.clock.allowed-rates = [ ]",
            kind="vendor_doc",
        ),
    ),
)

#: Fields this pass still has no citable public source for.
REFERENCED_GAPS: tuple[str, ...] = (
    diag(
        "This machine's PortAudio device list (ALSA 0 devices, OSS 0 devices): no physical interface"
    ),
    diag("Measured full-duplex round-trip latency on any interface"),
    diag("Pa_IsFormatSupported results on a physical interface (sample-rate negotiation)"),
    diag("ASIO compiled numeric default latency (PortAudio stores the driver's buffer only)"),
    diag("JACK compiled numeric default latency (only jack_port_get_latency / server rate)"),
    diag("Core Audio device-specific latency (only the 10 / 100 ms fallback is sourced)"),
    diag(
        "Scarlett 18i20 4th Gen analogue line-output count (spec page did not yield a clear figure)"
    ),
    diag("USB Audio Class 1.0 / 2.0 discrete rate tables (USB-IF PDFs were not re-read)"),
    diag(
        "Hardware bit depth of a PortAudio stream (RoomScope writes 32-bit float; "
        "manufacturer pages above state 24-bit converters)"
    ),
)


def referenced_catalog_dict() -> dict[str, Any]:
    """JSON object stored on the inventory. Not a hardware-matrix result."""
    return {
        "disclaimer": (
            "Referenced data from public sources. Not a RoomScope measurement "
            "and not a HARDWARE_TESTS.md PASS."
        ),
        "host_api_latency": [entry.to_dict() for entry in REFERENCED_HOST_API_LATENCY.values()],
        "interfaces": [entry.to_dict() for entry in REFERENCED_INTERFACES],
        "mixer_defaults": [entry.to_dict() for entry in REFERENCED_MIXER_DEFAULTS],
        "gaps": list(REFERENCED_GAPS),
    }
