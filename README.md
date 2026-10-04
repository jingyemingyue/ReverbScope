**English** | [简体中文](README.zh-CN.md)

# RoomScope

**Measure your recording room with a sine sweep and find out whether a
microphone position is usable — next to any DAW, or on its own.**

[![Latest pre-release](https://img.shields.io/github/v/release/jingyemingyue/RoomScope?include_prereleases&label=pre-release&color=1a7f8e)](https://github.com/jingyemingyue/RoomScope/releases)
[![CI](https://github.com/jingyemingyue/RoomScope/actions/workflows/ci.yml/badge.svg)](https://github.com/jingyemingyue/RoomScope/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)

![RoomScope results page: reverberation, background noise with mains hum, early reflections and direct sound for one microphone position, with the interpretation below (synthetic demo data)](docs/images/gui-results.png)

<sub>The results page for the built-in demo room. Synthetic data: no real room was measured.</sub>

## Download

### **[→ Download from GitHub Releases](https://github.com/jingyemingyue/RoomScope/releases)**

**Status: 0.5.0 beta 1 (pre-release)** — free, open source, for testing. **This is not
the hardware release:** nothing has been measured through a real audio
interface or DAW yet, so treat the numbers as unvalidated
([help test it](#help-test-beta-1)). Neither edition needs Python.

Choose **one edition**, then the file for your computer under **Assets** on
the newest release:

### 🖥 Desktop Edition

For most people: the app with windows and charts, plus the `roomscope`
command line.

| Platform | Download | Architecture | Notes |
| --- | --- | --- | --- |
| **macOS** 14+ | [`RoomScope-Desktop-macOS-arm64.dmg`](https://github.com/jingyemingyue/RoomScope/releases) | Apple silicon (M1 or later) | Open the DMG, drag **RoomScope** to **Applications** |
| **macOS** 14+ | [`RoomScope-Desktop-macOS-x86_64.dmg`](https://github.com/jingyemingyue/RoomScope/releases) | Intel | Same as above |
| **Windows** 10 / 11 | [`RoomScope-Desktop-Windows-x64-Setup.exe`](https://github.com/jingyemingyue/RoomScope/releases) | x64 | Installer; then Start menu → **RoomScope** |
| **Windows** 10 / 11 | [`RoomScope-Desktop-Windows-x64.zip`](https://github.com/jingyemingyue/RoomScope/releases) | x64 | No installer: extract, double-click **`roomscope-gui.exe`** |
| **Linux** (glibc 2.39+) | [`RoomScope-Desktop-Linux-x86_64.tar.gz`](https://github.com/jingyemingyue/RoomScope/releases) | x86_64 | Extract, run `roomscope/roomscope-gui` |

**First launch.** The builds are unsigned (not notarized by Apple, no Windows
Authenticode signature), so the system warns once:

* **macOS:** click **Done**, then **System Settings → Privacy & Security →
  Open Anyway**. Do not turn off Gatekeeper or System Integrity Protection;
  it is not necessary.
* **Windows:** SmartScreen → **More info → Run anyway**.

Not sure which Mac you have? Apple menu → **About This Mac**: *Chip: Apple M…*
means Apple silicon, *Processor: Intel* means Intel.

### ⌨️ Terminal Edition

For the command line, scripts and automation, servers and computers without
a desktop: the same measurement and analysis without the GUI, about half the
size.

| Platform | Download | Architecture | Command |
| --- | --- | --- | --- |
| **macOS** 14+ | [`RoomScope-Terminal-macOS-arm64.tar.gz`](https://github.com/jingyemingyue/RoomScope/releases) | arm64 (Apple silicon) | `roomscope-terminal/roomscope demo` |
| **macOS** 14+ | [`RoomScope-Terminal-macOS-x86_64.tar.gz`](https://github.com/jingyemingyue/RoomScope/releases) | x86_64 (Intel) | `roomscope-terminal/roomscope demo` |
| **Windows** 10 / 11 | [`RoomScope-Terminal-Windows-x64.zip`](https://github.com/jingyemingyue/RoomScope/releases) | x64 | Open **`RoomScope Terminal.cmd`**, then `roomscope.exe demo` |
| **Linux** (glibc 2.39+) | [`RoomScope-Terminal-Linux-x86_64.tar.gz`](https://github.com/jingyemingyue/RoomScope/releases) | x86_64 | `roomscope-terminal/roomscope demo` |

Extract the archive first (`tar xzf <file>`; on Windows **Extract All…**). On
macOS, if a downloaded `roomscope` is refused, run
`xattr -dr com.apple.quarantine roomscope-terminal` once: it clears the
download mark on those files only and does not turn off Gatekeeper. It is a
stop-gap for these unsigned pre-release builds.

### Which one?

| | Desktop Edition | Terminal Edition |
| --- | --- | --- |
| GUI (windows, charts) | ✅ | — |
| Command line (`roomscope`) | ✅ | ✅ |
| Room analysis and comparison | ✅ | ✅ |
| Standalone measurement (plays and records) | ✅ | ✅ |
| English / 简体中文 | ✅ | ✅ |
| Python required | No | No |
| Best for | Most users | Command line, automation, lightweight or headless computers |

Not sure? Take the **Desktop Edition**: it contains the command line too.
Step-by-step install, checksums (`SHA256SUMS`), updating and uninstalling:
**[Installation guide](docs/INSTALLATION.md)** ([简体中文](docs/INSTALLATION.zh-CN.md)).

## Try it in 30 seconds

No microphone and no audio interface needed; nothing is played.

* **Desktop Edition:** open RoomScope and click **Demo (no interface)**.
* **Either edition, in a terminal:**

  ```bash
  roomscope demo
  ```

![roomscope demo in a terminal: at-a-glance results for two simulated positions, their comparison, and numbered next steps (synthetic data)](docs/images/cli-demo.svg)

`roomscope demo` simulates one room at two microphone positions, runs the
real analysis and comparison on them and says what to do next. The desktop
**Demo** runs one Standalone Mode take on a simulated room instead. Every
number either one shows describes the simulation, and every session either
one saves is marked as a synthetic demo.

**Then measure for real:** turn the monitors **down** (RoomScope never
changes system volume), then either let RoomScope play and record through
your interface (**Standalone Mode**) or play its sweep in your DAW
(**Universal DAW Mode**). The [user guide](docs/user-guide/en.md)
([简体中文](docs/user-guide/zh-CN.md)) explains every page.

## What RoomScope measures

RoomScope is an open-source, DAW-independent recording environment analyzer.
It answers practical questions a recording engineer asks about a room and a
microphone position:

* Is this room usable for recording?
* What acoustic problems does this position have (strong early reflections,
  long decay, low-frequency build-up, mains hum, high noise floor)?
* Did moving the microphone or the performer improve things?

It measures the room with an exponential sine sweep (ESS), derives the room
impulse response by deconvolution, and reports reverberation (EDT / T20 /
T30 / estimated RT60), early/late energy (C50, C80, D50, centre time),
frequency response, background noise, early reflections and potential
low-frequency resonances. Every number carries its unit, its algorithm
source and a validity flag; when the data is not good enough, RoomScope
says *"Insufficient decay range"* instead of inventing a figure. There is
deliberately no "room score". A recording profile may add one notice when
C50 or C80 is a poor fit for that kind of recording; the threshold is an
engineering choice, not a grade. The GUI, the command line and the reports
are available in English and Simplified Chinese.

Status: **0.5.0 beta 1 (pre-release)** on the way to 1.0
([RELEASE_PLAN.md](docs/RELEASE_PLAN.md)). The DSP core, CLI, GUI, compare,
loopback, zh-CN catalog, session bundles and both editions' bundles exist and are
covered by synthetic tests on Linux, macOS and Windows. **Not yet:** any result
measured on real hardware (the hardware matrix and the validation campaign are
empty), signed bundles, a PyPI package. Beta 1 does not meet the 0.5.0 exit
criteria in the release plan. Snapshot of what works:
[docs/STATUS.md](docs/STATUS.md).

## Help test beta 1

The beta 1 builds exist so that people with real interfaces and DAWs can find
out what works. A failed check is as useful as a pass.

1. Install a build ([Download](#download); the Gatekeeper / SmartScreen
   warning is expected).
2. Open RoomScope and run **Demo (no interface)** once: it shows what a
   result looks like without playing anything.
3. Turn the monitors down, then run **Standalone Mode** with your interface
   and a microphone, or **Universal DAW Mode** through your DAW
   ([DAW notes](docs/user-guide/daw-setup.md)).
4. Report what happened, with **Help → Environment Report for Bug Reports**
   pasted in:
   * [Audio interface test report](https://github.com/jingyemingyue/RoomScope/issues/new?template=hardware.yml):
     device list, full takes at 44.1 / 48 / 96 kHz, channels above 2,
     loopback, Stop during playback, dropouts, unplugging during a take;
   * [DAW compatibility report](https://github.com/jingyemingyue/RoomScope/issues/new?template=daw.yml):
     the same sweep recorded and exported through one DAW.

Results go into [docs/HARDWARE_TESTS.md](docs/HARDWARE_TESTS.md) with a link
to the report. Only runs on a physical interface count there.

## DAW workflow (Universal DAW Mode)

Designed for any DAW that can import, play, record and export WAV files.
RoomScope never talks to the DAW. It reads what DAWs export (Broadcast WAV,
RF64, Wave64, AIFF, CAF, FLAC; 16/24/32-bit PCM or 32-bit float; mono or
multi-channel) and, when the sweep's sidecar file is used, names the usual
cause when the DAW played the sweep at the wrong speed (a project at another
sample rate, or a Warp / Flex / Follow Tempo stretch larger than the
estimate's own spread: about 1.3 % for the default 10 s sweep, more for
shorter sweeps).
Step-by-step notes, written from each vendor's documentation, cover Pro
Tools, Logic Pro / GarageBand, Cubase / Nuendo, Fender Studio Pro (Studio
One), Ableton Live, REAPER, FL Studio, Bitwig, Digital Performer and
Audacity: [docs/user-guide/daw-setup.md](docs/user-guide/daw-setup.md).
**None of them has been run with RoomScope in a real DAW yet**
([HARDWARE_TESTS.md](docs/HARDWARE_TESTS.md)); a DAW compatibility report is
the most useful contribution you can make.

1. **Generate Test Signal** – RoomScope writes a sweep WAV (plus a small JSON
   sidecar with the exact sweep definition).
2. **Record Through Your DAW** – import the WAV on a track, play it through
   your interface and monitors, record the measurement microphone on another
   track.
3. **Import Recording** – export the recorded track as WAV (same sample rate
   as the project; any length, no trimming needed).
4. **Analyze** – RoomScope finds the sweep automatically, deconvolves it and
   produces the report.

## Standalone workflow

RoomScope plays the sweep and records the microphone itself through the
audio interface you select (PortAudio via `sounddevice`). Start with the
monitor level low: the default sweep level is conservative and RoomScope
does not touch system volume or audio settings (the one opt-in exception, a
macOS option that sets the device's sample rate, is described in
[SECURITY.md](SECURITY.md#safety-of-standalone-mode)).

Both modes call exactly the same analysis pipeline
(`roomscope.core.pipeline.analyze`).

## Command line

Both editions include the command line. It is `roomscope` in the Terminal
Edition, in the Windows / Linux Desktop Edition (next to `roomscope-gui`) and
in a Python install; in the macOS Desktop Edition it is
`/Applications/RoomScope.app/Contents/MacOS/RoomScope`.

```bash
# 1. Generate the test signal (48 kHz, 20 Hz–20 kHz, 10 s sweep, -12 dBFS)
roomscope sweep --out sweep_48k.wav

# 2. Play it through your DAW, record the mic, export recording.wav

# 3. Analyze
roomscope analyze --recording recording.wav --sweep sweep_48k.wav --out results/

# Optional: two tape measurements unlock the vertical geometry
roomscope analyze --recording recording.wav --sweep sweep_48k.wav \
  --speaker-distance 1.65 --mic-height 0.40 --temperature 21

# Optional: interpret for a kind of recording (generic | vocal | voiceover |
# acoustic_guitar | drums | room_mic | choir)
roomscope analyze --recording recording.wav --sweep sweep_48k.wav --profile voiceover

# Re-open a saved session (same report; --profile overrides the stored one)
roomscope show results/
roomscope show results/ --list

# Compare two saved sessions (every delta carries a validity)
roomscope compare results/ position-b/ --same-input-gain
roomscope schema result

# Two-channel DAW export: microphone + electrical loopback
roomscope analyze --recording take.wav --sweep sweep_48k.wav --channel 0 --loopback-channel 1

# Standalone: list devices, then measure (optional loopback on input 2)
roomscope devices
roomscope measure --out session1/ --input-device 2 --output-device 3 \
  --input-channels 1,2 --loopback-channel 2 --sample-rate 48000

# Demo / CI: no interface
roomscope demo --out demo/
roomscope --backend fake measure --out fake-take/ --duration 2 --post-silence 1.5

# Language, bundle, CSV, project
roomscope --lang zh_CN analyze --recording take.wav --sweep sweep.wav
roomscope session bundle session1/ --no-audio --out report.zip
roomscope export session1/ --format csv --out curves/
roomscope project init --out room/ --name Booth
roomscope project add room/ session1/ --position desk
roomscope project average room/

# GUI (Desktop Edition, or a Python install with the gui extra)
roomscope gui
```

`--speaker-distance` is the straight line from the loudspeaker to the
microphone capsule; `--mic-height` is the capsule above the first solid
horizontal surface below it. With both, RoomScope reports the loudspeaker
height, the plane above the devices and the horizontal separation. It reports
**no coordinates, no room length or width, and never names a wall**: one
omnidirectional microphone at one position measures path lengths, not
directions, which leaves the geometry underdetermined by two even with the
distance supplied. The result JSON carries that argument with it.

`--profile` chooses how the measured numbers are turned into advice
(`generic` by default; `vocal`, `voiceover`, `acoustic_guitar`, `drums`,
`room_mic` and `choir` have per-recording thresholds and wording). The report
prints the profile name next to `Interpretation` so the advice is never
mistaken for room-agnostic truth. The GUI offers the same selector in both
measurement modes.

`results/` receives `result.json` (all metrics and curves),
`impulse_response.wav` (raw IR, float32) and `session.json` (measurement
metadata). Raw recordings are never modified. `roomscope show` and the GUI
**Open Session** / Home session list reopen that directory; the IR WAV is
the authoritative sample record (`result.json` stores metrics, not IR
samples). Recently opened or saved sessions are remembered under
`$ROOMSCOPE_HOME` (default `~/.roomscope`).

## Documentation

| Document | Content |
| --- | --- |
| [docs/INSTALLATION.md](docs/INSTALLATION.md) | Download and install on macOS, Windows, Linux or with Python; updating, uninstalling, unsigned-build warnings, troubleshooting; [中文](docs/INSTALLATION.zh-CN.md) |
| [docs/index.md](docs/index.md) | Documentation hub |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Package layout, data flow, extension points |
| [docs/ARCHITECTURE_V1.md](docs/ARCHITECTURE_V1.md) | v1.0 design being executed: API tiers, comparison, loopback, packaging, i18n, validation gates |
| [docs/ARCHITECTURE_V1.zh-CN.md](docs/ARCHITECTURE_V1.zh-CN.md) | Chinese digest of the v1.0 design |
| [docs/MEASUREMENT_METHODOLOGY.md](docs/MEASUREMENT_METHODOLOGY.md) | Algorithms, units, validity rules, references |
| [docs/DEPENDENCIES.md](docs/DEPENDENCIES.md) | Every runtime/dev dependency with license and purpose |
| [docs/THIRD_PARTY_REVIEW.md](docs/THIRD_PARTY_REVIEW.md) | Audit of external repositories that were studied |
| [docs/CODE_PROVENANCE.md](docs/CODE_PROVENANCE.md) | Provenance of any adapted or copied code (currently none) |
| [docs/LICENSE_DECISION.md](docs/LICENSE_DECISION.md) | Why RoomScope is Apache-2.0 |
| [docs/STATUS.md](docs/STATUS.md) | Implemented / tested / known limitations / next milestone |
| [docs/user-guide/en.md](docs/user-guide/en.md) | User guide (English): install, measure, read, compare, bundle |
| [docs/user-guide/zh-CN.md](docs/user-guide/zh-CN.md) | 用户指南（简体中文） |
| [docs/AUDIO_DEVICES.md](docs/AUDIO_DEVICES.md) | Host APIs (WASAPI, WDM-KS, MME, Core Audio, ALSA, JACK, …), what each does to a measurement, and how RoomScope probes and chooses devices, with sources; [中文](docs/AUDIO_DEVICES.zh-CN.md) |
| [docs/COMPATIBILITY.md](docs/COMPATIBILITY.md) | Platforms, Python and dependency floors, DAW export formats, host APIs — and what verified each; [中文](docs/COMPATIBILITY.zh-CN.md) |
| [docs/EDITIONS.md](docs/EDITIONS.md) | Desktop Edition vs. Terminal Edition, and the developer tools; [中文](docs/EDITIONS.zh-CN.md) |
| [docs/COMPARISON.md](docs/COMPARISON.md) | How RoomScope differs from REW, Open Sound Meter, ARTA, Smaart, SoundID and others, and when another tool is the better choice; [中文](docs/COMPARISON.zh-CN.md) |
| [docs/user-guide/daw-setup.md](docs/user-guide/daw-setup.md) | Step-by-step DAW notes (Pro Tools, Logic, Cubase, Studio One, Live, REAPER, FL Studio, Bitwig, Audacity); [中文](docs/user-guide/daw-setup.zh-CN.md) |
| [docs/PROJECT_BRIEF.zh-CN.md](docs/PROJECT_BRIEF.zh-CN.md) | Original project brief (Chinese) |

## Development install

For contributors. Python 3.12 or newer; RoomScope is not on PyPI yet, so
install from a clone:

```bash
git clone https://github.com/jingyemingyue/RoomScope.git
cd RoomScope
python3.12 -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev,gui]"
roomscope --help
roomscope gui
```

Each release also carries a wheel (`roomscope-<version>-py3-none-any.whl`)
and a source archive; see [Installation → Python](docs/INSTALLATION.md#python-wheel-and-source).
`scripts/build_release.py` builds both editions of the current platform
locally ([RELEASE_PLAN.md](docs/RELEASE_PLAN.md) §3a).

## Technical architecture

### Python API

```python
from roomscope import analyze, compare, interpret_comparison
from roomscope.io.wav import read_wav, load_reference
from roomscope.core import Reference

recording = read_wav("recording.wav")
reference = load_reference("sweep_48k.wav")  # uses the JSON sidecar if present
result = analyze(recording, reference)
print(result.decay.broadband.rt60_estimate_s, result.decay.broadband.rt60_basis)
for r in result.reflections.reflections:
    print(f"{r.delay_ms:.1f} ms  {r.relative_db:.1f} dB")
```

### What makes RoomScope different

* **It refuses to invent a number.** Every metric carries its unit, its
  algorithm source and a validity flag; a decay too short for T30 says
  *insufficient range* instead of a figure. There is no single "room score".
* **It lives next to your DAW, not inside it.** It needs only a DAW that
  plays and records WAV, and it names the usual cause when the DAW played the
  sweep at the wrong speed (sample-rate mismatch or Warp / Flex / Follow
  Tempo). The per-DAW steps are documented, not yet tested in each DAW.
* **It speaks the recording engineer's question** — "is this position usable
  for a vocal, a drum room mic, a choir?" — through labelled interpretation
  profiles, and compares two positions with a validity on every delta.
* **It says what one microphone cannot know.** Placement geometry never names
  a wall or derives coordinates the measurement cannot support.

A sourced comparison with other tools is in [docs/COMPARISON.md](docs/COMPARISON.md).

### Design principles

* **DAW-independent** – no DAW SDKs, ever. WAV in, WAV out.
* **Core-first** – DSP functions are pure NumPy/SciPy functions with no GUI,
  device or file-format dependencies, so a CLI, a desktop app, a plug-in or
  a Python API can share them.
* **Scientific correctness over features** – algorithms come from published
  papers and standards (Farina 2000, Schroeder 1965, Lundeby 1995,
  ISO 3382-1/-2, ...); see [docs/MEASUREMENT_METHODOLOGY.md](docs/MEASUREMENT_METHODOLOGY.md).
* **Honest numbers** – dBFS unless calibrated, validity flags on every metric,
  no pseudo-scientific room score.
* **Clean-room implementation and license hygiene** – no third-party source is
  vendored ([docs/CODE_PROVENANCE.md](docs/CODE_PROVENANCE.md)); every dependency and
  every reference repository is audited
  ([docs/DEPENDENCIES.md](docs/DEPENDENCIES.md),
  [docs/THIRD_PARTY_REVIEW.md](docs/THIRD_PARTY_REVIEW.md)).

## Contributing

This is the version intended for other developers to read, clone and review.
Pull requests are welcome once you have run the checks in
[CONTRIBUTING.md](CONTRIBUTING.md). Please also read the
[code of conduct](CODE_OF_CONDUCT.md).

Useful starting points:

* [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — package layout and the one
  analysis entry point (`roomscope.core.pipeline.analyze`)
* [docs/MEASUREMENT_METHODOLOGY.md](docs/MEASUREMENT_METHODOLOGY.md) — every
  metric's algorithm, units and validity rules
* [docs/STATUS.md](docs/STATUS.md) — implemented / tested / next milestone
* `examples/synthetic_measurement.py` — end-to-end run with no hardware

```bash
pytest
ruff check . && ruff format --check .
mypy
```

CI (pytest on Ubuntu 3.12–3.14 plus macOS/Windows 3.12, ruff, mypy,
sdist/wheel) runs on every push and pull request.

## License

Apache License 2.0 – see [LICENSE](LICENSE) and [NOTICE](NOTICE).
