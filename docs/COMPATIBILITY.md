# Compatibility

**English** | [简体中文](COMPATIBILITY.zh-CN.md)

What ReverbScope runs on and works with, and **what verified each row**. A row
that says "not verified" is a claim nobody has checked yet. The Chinese
translation is [COMPATIBILITY.zh-CN.md](COMPATIBILITY.zh-CN.md). Last reviewed
2026-09-29.

## Operating systems and bundles

| Platform | Deliverable | Verified by |
| --- | --- | --- |
| Windows 10/11 x64 | Desktop: `ReverbScope-Desktop-Windows-x64-Setup.exe`, `ReverbScope-Desktop-Windows-x64.zip`; Terminal: `ReverbScope-Terminal-Windows-x64.zip` | Release workflow on `windows-latest`: frozen bundle smoke (CLI, demo in English and Chinese, JSON on stdout, fake measurement, offscreen GUI, windowed launcher started without arguments), installer built with Inno Setup, installed per-user, Start menu entry checked, smoke-tested from the install folder, uninstalled with its Start menu entries; Terminal Edition gated for no Qt / PySide6 / matplotlib and smoke-tested (demo, JSON, `gui` refused politely); CI test suite on Windows / Python 3.12 |
| macOS 14+, Apple silicon | Desktop: `ReverbScope-Desktop-macOS-arm64.dmg`; Terminal: `ReverbScope-Terminal-macOS-arm64.tar.gz` | Release workflow on `macos-latest` (macOS 26): DMG mounted, app copied, `gui --smoke`, Finder-style launch kept running, ad-hoc signature verified, `lipo` architecture arm64, a hardened-runtime copy started; both editions report `arm64` from `reverbscope doctor`; Terminal Edition gated for no Qt and smoke-tested; CI test suite on macOS / Python 3.12. macOS 14 is the minimum of the bundled NumPy / SciPy wheels (`macosx_14_0`, `LSMinimumSystemVersion` 14.0) and has not been run |
| macOS 14+, Intel | Desktop: `ReverbScope-Desktop-macOS-x86_64.dmg`; Terminal: `ReverbScope-Terminal-macOS-x86_64.tar.gz` | Release workflow on `macos-15-intel` (macOS 15): the same checks, architecture x86_64 |
| Linux x86_64 (glibc of the CI runner or newer) | Desktop: `ReverbScope-Desktop-Linux-x86_64.tar.gz`; Terminal: `ReverbScope-Terminal-Linux-x86_64.tar.gz` | Release workflow on `ubuntu-latest` and a local build (`scripts/build_release.py`): bundle gates, smoke of both editions, `reverbscope-gui` launch; CI tests on Ubuntu / Python 3.12–3.14 |
| Anything else (ARM Windows / Linux, older macOS) | wheel only | not verified; `scripts/build_release.py` refuses to name an ARM build as x86_64 |

No bundle has been used on a person's own machine with real audio hardware
yet ([HARDWARE_TESTS.md](HARDWARE_TESTS.md)); the rows above are CI and local
builds.

## Python and dependencies

| | Lowest declared | Newest checked |
| --- | --- | --- |
| Python | 3.12 | 3.14 |
| NumPy | 1.26 | 2.5.3 |
| SciPy | 1.12 | 1.18.1 |
| soundfile / libsndfile | 0.12 | 0.14.0 / 1.2.2 |
| sounddevice / PortAudio | 0.4.6 | 0.5.6 / V19.7 (bundled on Windows, macOS); Linux uses the system's `libportaudio2` (V19.6 on Ubuntu 24.04) |
| matplotlib | **3.10** | 3.11.2 |
| PySide6_Essentials | 6.6 | 6.11.2 |

Verified 2026-09-24 by installing exactly the declared minimums on Python 3.12
and the newest releases on Python 3.13 and 3.14 and running the whole suite.
The minimums passed except matplotlib 3.8 / 3.9, whose wheels still contain
the `_ttconv` extension ([DEPENDENCIES.md](DEPENDENCIES.md) §6); the floor was
raised to 3.10, which then passed. On 3.13 and 3.14 the declared minimums
cannot be installed (no wheels) and a resolver picks newer versions (e.g.
PySide6_Essentials 6.8.0.2 on 3.13); only the Python 3.12 floor set was
tested. The desktop bundles pin `requirements/bundle.lock`.

## Recording files (Universal DAW Mode)

Tested with the same take in every container (`tests/integration/test_daw_exports.py`):
WAV (16 / 24 / 32-bit PCM, 32-bit float), WAVE_FORMAT_EXTENSIBLE, Broadcast
WAV with `bext`, `iXML` and `JUNK` chunks (Pro Tools), RF64, Wave64, AIFF, CAF
(Logic Pro recordings) and FLAC; mono and stereo bounces of a mono microphone.
Sample rates 44.1–192 kHz. A sweep the DAW played at the wrong speed (an
unconverted sample rate or time-stretching) is diagnosed
([MEASUREMENT_METHODOLOGY.md](MEASUREMENT_METHODOLOGY.md) §2b).

## DAWs

Step-by-step notes for Pro Tools, Logic Pro, GarageBand, Cubase / Nuendo,
Fender Studio Pro (Studio One), Ableton Live, REAPER, FL Studio, Bitwig
Studio, Digital Performer and Audacity, plus a checklist for any other DAW,
are in [user-guide/daw-setup.md](user-guide/daw-setup.md). They are written
from each vendor's documentation, with a source per step (a few third-party
sources are marked): a documented workflow. **No DAW has been run with
ReverbScope on real hardware yet**; the per-DAW matrix in
[HARDWARE_TESTS.md](HARDWARE_TESTS.md) is empty.

## Audio host APIs (Standalone Mode)

Every host API PortAudio offers is listed and probed (`reverbscope devices
--probe`): MME, DirectSound, WASAPI (shared, or exclusive with
`--wasapi-exclusive`), WDM-KS and ASIO where present on Windows; Core Audio on
macOS (`--coreaudio-set-rate` to avoid conversion); ALSA (`hw:` and plugin
devices), JACK and OSS on Linux. Input and output are kept on one host API,
channels are checked before playing, and separate devices are warned about.
Behaviour of each host API, with sources: [AUDIO_DEVICES.md](AUDIO_DEVICES.md).
Verified with simulated device tables (`tests/unit/test_audio_inventory.py`)
and the synthetic backend; **not verified with real interfaces**.

## Cross-platform behaviour

Audited 2026-09-24 and fixed with tests that emulate the platform
(`tests/unit/test_cross_platform.py`): UTF-8 output when the CLI is piped on
Windows, portable `project.json` paths, case-insensitive file systems
(confirmed on the macOS and Windows CI runners), Windows log rotation with two
processes, Windows display language and `zh-Hans` locale tags, dates Windows
cannot convert, a session bundle written inside its own folder. File I/O in
the package passes `encoding="utf-8"` everywhere (checked with
`-X warn_default_encoding`); non-ASCII paths work (libsndfile opens them with
the wide-character API on Windows).
