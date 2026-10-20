**English** | [简体中文](README.zh-CN.md)

# ReverbScope

ReverbScope tells you whether a room and a microphone position are usable
before you record. It plays an exponential sine sweep through your
loudspeaker, records it with a measurement microphone, derives the room
impulse response and reports reverberation (EDT, T20, T30, RT60), clarity
(C50, C80, D50), early reflections, background noise and the frequency
response, each with its unit and a validity flag. It is for recording
engineers, home and small-studio recordists and anyone learning room
acoustics. It runs offline next to any DAW or on its own, as a desktop app
and a command line, in English and Simplified Chinese. Apache-2.0.

**Status: pre-release.** The analysis, the desktop app and the command line
are covered by automated tests on Linux, macOS and Windows. Nothing has yet
been measured through a real audio interface or a DAW and reported, so treat
every number as unvalidated until the
[hardware test matrix](docs/HARDWARE_TESTS.md) has entries.

[![CI](https://github.com/jingyemingyue/ReverbScope/actions/workflows/ci.yml/badge.svg)](https://github.com/jingyemingyue/ReverbScope/actions/workflows/ci.yml)
[![Latest pre-release](https://img.shields.io/github/v/release/jingyemingyue/ReverbScope?include_prereleases&label=pre-release)](https://github.com/jingyemingyue/ReverbScope/releases)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)](pyproject.toml)

![The ReverbScope desktop app on main: the overview of one microphone position with reverberation, background noise, early reflections and direct sound, the measurement health and the band tables, and the inspector on the right (synthetic demo data)](docs/images/gui-results.png)

<sub>The desktop app on `main` (taken at 0.5.0b3) with a session from
`reverbscope demo`. Synthetic demo data: no real room was measured.</sub>

## What's new

The full history is in [CHANGELOG.md](CHANGELOG.md).

* **On `main` (Unreleased):** the desktop app is one workstation window: a
  measurement list, views for overview, frequency response, impulse response,
  decay, noise, spectrogram, waterfall, room, comparison and report, an
  inspector, and a measure strip. Charts zoom, pan, read out values with
  units and export PNG, SVG or CSV. **Help → Send Feedback...** and
  **Report a Bug...** open a prefilled GitHub issue form.
* **0.5.0b4 (2026-10-18):** documentation and release-notes housekeeping on
  top of 0.5.0b3.
* **0.5.0b3 (2026-10-09):** measurement health on every result (the checks
  made on the take itself, each with its reason and what to do next),
  verdicts for comparing two positions, project overviews for several
  positions, boxed terminal reports and an interactive `reverbscope` menu.

Builds 0.5.0b2 to 0.5.0b4 and 0.5.0rc1 / rc2 exist only as Draft releases.
The newest **public** pre-release is
[v0.5.0b1](https://github.com/jingyemingyue/ReverbScope/releases/tag/v0.5.0b1)
(2026-10-01), published under the project's former name **RoomScope**.

## Download and install

Builds are attached to
[GitHub Releases](https://github.com/jingyemingyue/ReverbScope/releases).
They are pre-release builds, not a stable release. Each bundle includes
Python and every dependency; no Python install is needed.

**What you can download today:** v0.5.0b1 under the old name. Its files and
command start with `RoomScope` / `roomscope` instead of `ReverbScope` /
`reverbscope`; the [public-beta guide](docs/PUBLIC_TESTING.md) lists them
with checksums and first-launch steps. The tables below name the files of
the renamed builds, which every Release from 0.5.0b2 on carries once the
maintainer publishes one.

### 🖥 Desktop Edition

The desktop app and the `reverbscope` command line. For most people.

| Platform | File | Architecture | Install |
| --- | --- | --- | --- |
| macOS 14 or later | `ReverbScope-Desktop-macOS-arm64.dmg` | Apple silicon | Open the DMG, drag **ReverbScope** to **Applications** |
| macOS 14 or later | `ReverbScope-Desktop-macOS-x86_64.dmg` | Intel | Same |
| Windows 10 / 11 | `ReverbScope-Desktop-Windows-x64-Setup.exe` | x64 | Run the installer, then Start → **ReverbScope** |
| Windows 10 / 11 | `ReverbScope-Desktop-Windows-x64.zip` | x64 | Extract everything, run `reverbscope-gui.exe` |
| Linux, glibc 2.39 or later | `ReverbScope-Desktop-Linux-x86_64.tar.gz` | x86_64 | Extract, run `reverbscope/reverbscope-gui` |

**First launch.** The builds are not signed: they are not notarized by Apple
and carry no Windows Authenticode signature, so the system warns once.

* **macOS:** click **Done**, then **System Settings → Privacy & Security →
  Open Anyway**. Do not turn off Gatekeeper or System Integrity Protection;
  it is not needed.
* **Windows:** SmartScreen → **More info → Run anyway**.

Allow microphone access when the system asks; without it the recording is
silent.

### ⌨️ Terminal Edition

The same measurement and analysis on the command line, without the window.
For scripts, servers and computers without a desktop.

| Platform | File | Architecture | Run |
| --- | --- | --- | --- |
| macOS 14 or later | `ReverbScope-Terminal-macOS-arm64.tar.gz` | Apple silicon | `reverbscope-terminal/reverbscope demo` |
| macOS 14 or later | `ReverbScope-Terminal-macOS-x86_64.tar.gz` | Intel | `reverbscope-terminal/reverbscope demo` |
| Windows 10 / 11 | `ReverbScope-Terminal-Windows-x64.zip` | x64 | Open `ReverbScope Terminal.cmd`, then `reverbscope.exe demo` |
| Linux, glibc 2.39 or later | `ReverbScope-Terminal-Linux-x86_64.tar.gz` | x86_64 | `reverbscope-terminal/reverbscope demo` |

On macOS, if the extracted `reverbscope` is refused, run
`xattr -dr com.apple.quarantine reverbscope-terminal` once. It clears the
download mark on those files only.

### Which one?

| | Desktop Edition | Terminal Edition |
| --- | --- | --- |
| Desktop app with charts | Yes | No |
| `reverbscope` command line | Yes | Yes |
| Measurement, analysis, comparison, projects | Yes | Yes |
| English / 简体中文 | Yes | Yes |

If unsure, take the Desktop Edition. Every Release also carries `SHA256SUMS`
to check the download, a Python wheel and a source archive. The
[installation guide](docs/INSTALLATION.md) covers checksums, the wheel,
Linux system libraries, updating, uninstalling and troubleshooting.

## Try it without hardware

`reverbscope demo` runs the whole workflow on a simulated room. It needs no
microphone or interface and plays nothing.

1. Open a terminal where the program is. The downloads do not add
   `reverbscope` to your `PATH`: on Windows the installer puts it in
   `%LOCALAPPDATA%\Programs\ReverbScope`; on macOS the Desktop Edition's
   command is `/Applications/ReverbScope.app/Contents/MacOS/ReverbScope`.
2. Run the demo. It simulates two microphone positions, analyses and
   compares them with the same code as a real measurement, and prints the
   next commands to try. Every saved session is marked as a synthetic demo.

   ```bash
   reverbscope demo --out demo/
   ```

3. To look at the same data in the desktop app, choose **File → Open
   Session...** and pick one of the folders the demo wrote. The app itself
   has no demo mode.

![reverbscope demo in a terminal: results for two simulated positions, their comparison and the next steps (synthetic data)](docs/images/cli-demo.svg)

## Using the desktop app

The [user guide](docs/user-guide/en.md) describes every control; this is the
short version.

### First launch

The window has three columns: the **measurement list** on the left, the
**views** in the middle and the **inspector** on the right, with the
**measure strip** along the bottom. While nothing is open, the start panel
shows saved sessions and a **Getting started** guide (**Help →
Getting started** brings it back after it is dismissed). **List** and **Inspector** on the view
bar hide a side; **View → Reset the layout** restores the default.
**Settings** (Ctrl+, / ⌘,) sets the language, theme (system, light or dark),
default recording profile, audio backend and output folder.

### Choose the audio devices

In the measure strip, choose **Audio interface** (ReverbScope plays and
records) or **DAW recording** (your DAW plays and records). For an audio
interface, pick the **input** device, the **sample rate** and the
**microphone channel**; **Advanced** holds the output device and an optional
loopback channel; **Set up...** opens every setting of the mode. On Windows,
prefer the interface's *WASAPI* or *WDM-KS* entry. **Help → Environment
Report for Bug Reports** lists every device with the rates it accepts.

### Measure, step by step

1. Turn the monitors **down**. ReverbScope never changes the system volume.
2. Place the microphone and the loudspeaker, and enter the **position** name.
3. Press **Start** (Ctrl+Return). The sweep plays and is recorded; **Stop**
   or Esc stops it at once. A playback level above −12 dBFS has to be
   acknowledged in **Set up...** first.
4. The take is analysed and appears in the list as *unsaved*. Save it with
   **File → Save Session...** (Ctrl+S).

In **DAW recording** mode, **Set up...** writes the test signal for your
DAW and imports the recorded file; the [DAW notes](docs/user-guide/daw-setup.md)
give the steps for ten DAWs.

### Read the results

Each view shows the selected measurements in their list colours. Ctrl+1 to
Ctrl+9 (⌘ on macOS) switch views.

| View | What to look at |
| --- | --- |
| Overview | Key figures with their validity, the measurement health and the octave-band tables (EDT, T20, T30, RT60, C50, C80, D50, centre time) |
| Frequency | Magnitude response with the display smoothing named; a difference pane when a baseline is set |
| Time | Impulse response and energy-time curve with the early reflections; click one to select it |
| Decay | Schroeder decay curves per band with the evaluation range shaded |
| Spectral | Spectrogram, waterfall (cumulative spectral decay) and the noise spectrum with hum candidates |
| Room | The room box you entered and what a measurement constrains; it never names a wall from one microphone |
| Report | The full text report, also available with **Copy report** |

The **inspector** shows the current measurement's health (what was found,
what it affects, what to do next), key figures with trust labels and the
selected reflection.

### Compare positions

Measure or open two takes, right-click one in the list and choose **Use as
baseline**, then select the other and open **Compare**: it gives a verdict
per aspect (reverberation, clarity, early reflections, noise floor, low end)
and a difference chart. **Project...** collects the takes of one room by
position and opens an overview with what to measure next.

### Save, export and report

* **Export** on any chart saves PNG or SVG, or the drawn curves as CSV.
* **Axes...** sets exact limits; **Frame**, R or a double-click resets them.
* A saved session folder holds `result.json`, `impulse_response.wav`,
  `session.json` and the recording; the [user guide](docs/user-guide/en.md)
  explains bundles and CSV export from the command line.

## Features

Implemented on `main` and covered by automated tests with synthetic data:

* **Two ways to measure.** *Standalone*: ReverbScope plays and records
  through the interface you choose (PortAudio via `sounddevice`). *Universal
  DAW Mode*: your DAW plays the sweep and records the microphone; ReverbScope
  reads the exported file (WAV, Broadcast WAV, RF64, Wave64, AIFF, CAF, FLAC)
  and never talks to the DAW.
* **Analysis.** Exponential sine sweep and deconvolution; EDT, T20, T30 and
  an RT60 estimate per octave band; C50, C80, D50 and centre time;
  frequency response; background noise and mains hum; early reflections;
  low-frequency resonance candidates.
* **Measurement health.** The take itself is checked (sweep, playback speed,
  direct sound, level, distortion, dropouts, decay range, noise floor,
  recording length), each check good, warning, invalid or unknown with the
  reason and the next step.
* **Comparison and projects.** Per-aspect verdicts between two takes and a
  project overview of several positions in one room. No ranking.
* **Honest numbers.** Every value carries its unit and a validity flag. Levels
  are dBFS (uncalibrated). When the data does not support a figure,
  ReverbScope says why instead of estimating one. There is no room score.
* **Recording profiles** (vocal, voiceover, acoustic guitar, drums, room
  microphone, choir) that tune the advice, not the measurement.
* **Desktop app and command line** with the same numbers and words; English
  and Simplified Chinese; light and dark themes.
* **Offline.** No network access, accounts or telemetry.

How ReverbScope compares with REW, Open Sound Meter, ARTA, Smaart and others,
and when another tool is the better choice: [docs/COMPARISON.md](docs/COMPARISON.md).

## Requirements and hardware

* **Computer:** macOS 14 or later (Apple silicon or Intel), Windows 10 / 11
  x64, or Linux x86_64 with glibc 2.39 or later. Python 3.12 or later for the
  wheel or a source install.
* **Audio interface** with at least one input and one output, or a DAW that
  can play and record WAV files. Interfaces that work only through ASIO are
  measured in Universal DAW Mode, because the bundles carry no ASIO support.
* **Microphone:** an omnidirectional measurement microphone gives the most
  meaningful results. Without calibration, levels stay in dBFS.
* **Loudspeaker:** one monitor or loudspeaker to play the sweep.
* **Optional:** a loopback cable from the output that drives the loudspeaker
  to a second input, which records an electrical reference of the playback
  chain next to the microphone.

Which systems, DAW export formats and host APIs were verified, and how:
[docs/COMPATIBILITY.md](docs/COMPATIBILITY.md).

## Command line

The Desktop and Terminal editions and a Python install all include
`reverbscope`. `reverbscope` without a command opens an interactive menu on
a terminal.

```bash
# Universal DAW Mode: write the test signal, record it in your DAW, analyse
reverbscope sweep --out sweep_48k.wav
reverbscope analyze --recording recording.wav --sweep sweep_48k.wav --out results/

# Standalone Mode: list devices, then measure
reverbscope devices
reverbscope measure --out session1/ --input-device 2 --output-device 3

# Show and compare saved sessions
reverbscope show results/
reverbscope compare results/ session1/ --same-input-gain

# Several positions of one room
reverbscope project init --out room/ --name Booth
reverbscope project add room/ session1/ --position desk
reverbscope project overview room/

# Environment report for a bug report
reverbscope doctor --probe
```

Every command and option: `reverbscope --help` and the
[user guide](docs/user-guide/en.md).

## Documentation

| Document | Content |
| --- | --- |
| [Installation](docs/INSTALLATION.md) | Every platform, checksums, Python, updating, troubleshooting |
| [User guide](docs/user-guide/en.md) | Measuring, reading results, comparing, projects, export |
| [DAW setup](docs/user-guide/daw-setup.md) | Step-by-step notes for ten DAWs |
| [Measurement methodology](docs/MEASUREMENT_METHODOLOGY.md) | Algorithms, units, validity rules, references |
| [Audio devices](docs/AUDIO_DEVICES.md) | Host APIs and how devices are probed |
| [Status](docs/STATUS.md) | What is implemented, tested and missing |
| [Roadmap](docs/ROADMAP.md) | What comes next |
| [Architecture](docs/ARCHITECTURE.md) | Package layout and data flow |
| [Documentation index](docs/index.md) | Everything else |

Most documents have a Simplified Chinese version; see
[README.zh-CN.md](README.zh-CN.md).

## Building from source

Python 3.12 or later. ReverbScope is not on PyPI yet.

```bash
git clone https://github.com/jingyemingyue/ReverbScope.git
cd ReverbScope
python3.12 -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev,gui]"
reverbscope --help
reverbscope gui
```

On Linux, PortAudio (`libportaudio2`) and the Qt system libraries listed in
the [installation guide](docs/INSTALLATION.md#linux) are needed.
`scripts/build_release.py` builds both editions for the current platform
with PyInstaller; the Windows installer uses Inno Setup and the macOS disk
image `packaging/macos/make_dmg.sh`. The Release workflow
(`.github/workflows/release.yml`) builds every asset on GitHub's runners.

### Python API

```python
from reverbscope import analyze
from reverbscope.io.wav import load_reference, read_wav

result = analyze(read_wav("recording.wav"), load_reference("sweep_48k.wav"))
print(result.decay.broadband.rt60_estimate_s, result.decay.broadband.rt60_basis)
```

The stability rules for the API and the file formats are in
[docs/API_STABILITY.md](docs/API_STABILITY.md).

## Testing

```bash
ruff check . && ruff format --check .
mypy --platform linux
python scripts/check_doc_links.py && python scripts/check_cli_docs.py && python scripts/check_src_safety.py
QT_QPA_PLATFORM=offscreen pytest --cov=reverbscope.core --cov=reverbscope.models --cov-fail-under=85
```

CI runs the tests on Ubuntu with Python 3.12, 3.13 and 3.14 and on macOS and
Windows with Python 3.12, plus linting, type checks, the sdist and wheel
build and the license-bundle gates. The tests use synthetic signals and a
fake audio backend; they are not hardware tests.

## Feedback

* In the desktop app: **Help → Send Feedback...** or **Help → Report a
  Bug...** opens a GitHub issue form with the version and system filled in.
  The app sends nothing itself.
* On GitHub: [choose an issue form](https://github.com/jingyemingyue/ReverbScope/issues/new/choose)
  (bug, measurement problem, question or feedback, feature request, audio
  interface or DAW test report). [SUPPORT.md](SUPPORT.md) says which one to
  use and what to attach.
* Security problems: privately, as in [SECURITY.md](SECURITY.md).

## Contributing

The most useful contribution now is a run on a real audio interface or
through a real DAW, whether it works or not. The
[test guide](docs/COMMUNITY_TESTING.md) says what to run, and results are
collected in [docs/HARDWARE_TESTS.md](docs/HARDWARE_TESTS.md).

For code and documentation, read [CONTRIBUTING.md](CONTRIBUTING.md) and the
[code of conduct](CODE_OF_CONDUCT.md). Small first tasks are in
[docs/COMMUNITY_TASKS.md](docs/COMMUNITY_TASKS.md). How AI assistance is used
and reviewed in this project: [docs/AI_ASSISTANCE.md](docs/AI_ASSISTANCE.md).

## License and third-party notices

ReverbScope is licensed under the Apache License 2.0; see [LICENSE](LICENSE)
and [NOTICE](NOTICE). No third-party source code is vendored
([docs/CODE_PROVENANCE.md](docs/CODE_PROVENANCE.md)). Every dependency and its
license is listed in [docs/DEPENDENCIES.md](docs/DEPENDENCIES.md). The desktop
bundles use Qt through PySide6 Essentials under the LGPL-3.0, and every
bundle ships the license texts of what it contains in `THIRD_PARTY_LICENSES`
(also under **Help → Third-party licenses...**).

## Acknowledgements

The methods follow published work: A. Farina (2000) for the exponential sine
sweep, M. R. Schroeder (1965) for backward integration, A. Lundeby et al.
(1995) for the truncation point, and ISO 3382-1 / -2 for the room-acoustic
parameters. ReverbScope is built on NumPy, SciPy, soundfile (libsndfile),
sounddevice (PortAudio), PySide6 (Qt), pyqtgraph and matplotlib. Full
references: [docs/MEASUREMENT_METHODOLOGY.md](docs/MEASUREMENT_METHODOLOGY.md).

## Maintainer

ReverbScope is maintained by [@jingyemingyue](https://github.com/jingyemingyue).
