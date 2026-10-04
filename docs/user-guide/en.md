# RoomScope user guide

**English** | [简体中文](zh-CN.md)

RoomScope measures a recording room so you can hear what the room is doing to
close-miked sources. It does not score the room and it does not correct it.

This page is the English guide. The Chinese translation is
[zh-CN.md](zh-CN.md).

## Install

Download from the project's
[Releases page](https://github.com/jingyemingyue/RoomScope/releases).
Step-by-step instructions for every system, updating, uninstalling and
troubleshooting are in [INSTALLATION.md](../INSTALLATION.md); this section is
the short version. Each
Release lists a `SHA256SUMS` file; compare it with the file you
downloaded (`shasum -a 256 <file>` on macOS / Linux,
`Get-FileHash <file>` in PowerShell).

RoomScope comes in two editions. The **Desktop Edition** is the app this
guide describes, with the command line included; the **Terminal Edition** is
the command line only (no windows or charts), for scripts, servers and
computers without a desktop.

| System | Desktop Edition | Start RoomScope |
| --- | --- | --- |
| Windows 10/11 x64 | `RoomScope-Desktop-Windows-x64-Setup.exe` (installer) or `RoomScope-Desktop-Windows-x64.zip` | Start menu → RoomScope, or `roomscope-gui.exe` in the zip |
| macOS 14+, Apple silicon | `RoomScope-Desktop-macOS-arm64.dmg` | Drag RoomScope to Applications, then open it |
| macOS 14+, Intel | `RoomScope-Desktop-macOS-x86_64.dmg` | Drag RoomScope to Applications, then open it |
| Linux x86_64 | `RoomScope-Desktop-Linux-x86_64.tar.gz` | `tar xzf RoomScope-Desktop-Linux-x86_64.tar.gz && roomscope/roomscope-gui` |

| System | Terminal Edition | Start RoomScope |
| --- | --- | --- |
| Windows 10/11 x64 | `RoomScope-Terminal-Windows-x64.zip` | Extract, double-click `RoomScope Terminal.cmd`, type `roomscope.exe demo` |
| macOS 14+, Apple silicon | `RoomScope-Terminal-macOS-arm64.tar.gz` | `tar xzf` it, then `roomscope-terminal/roomscope demo` |
| macOS 14+, Intel | `RoomScope-Terminal-macOS-x86_64.tar.gz` | `tar xzf` it, then `roomscope-terminal/roomscope demo` |
| Linux x86_64 | `RoomScope-Terminal-Linux-x86_64.tar.gz` | `tar xzf` it, then `roomscope-terminal/roomscope demo` |

The Windows and Linux Desktop Edition bundles carry two programs: the desktop
app `roomscope-gui` and the command-line tool `roomscope` (run `roomscope --help`
in a terminal). On macOS the app's executable is also the CLI when it is given
arguments: `/Applications/RoomScope.app/Contents/MacOS/RoomScope --help`.

**The bundles are not signed for distribution** until the maintainer holds
signing identities (the macOS app has an ad hoc signature and is not
notarized; the Windows files have no Authenticode signature), so the
operating system warns the first time:

* **macOS:** open the app once; when macOS says it cannot verify it, choose
  *Done*, then System Settings → Privacy & Security → *Open Anyway* (the
  button appears after that first attempt) and confirm. Since macOS 15
  Sequoia, right-click → Open no longer bypasses this check; it still works on
  macOS 14 ([Apple](https://developer.apple.com/news/?id=saqachfa)). Grant
  microphone access when asked (`NSMicrophoneUsageDescription` is in the
  bundle Info.plist). The bundled NumPy and SciPy need macOS 14 or later;
  the DMGs were built and started on macOS 15 (Intel) and 26 (Apple silicon)
  CI runners only.
* **Windows:** SmartScreen may warn; choose “More info” → “Run anyway”. The
  installer installs for the current user and needs no administrator rights;
  uninstall from Settings → Apps.
* **Linux:** the tarball needs the system's PortAudio, OpenGL/EGL and
  XCB libraries (on Debian / Ubuntu: `sudo apt install libportaudio2 libegl1
  libgl1 libxkbcommon-x11-0 libxcb-cursor0`), and a CJK font such as
  `fonts-noto-cjk` for Chinese text in charts. `packaging/linux/roomscope.desktop`
  is a desktop entry you can adapt.

**From Python.** RoomScope is not on PyPI yet. With Python 3.12 or newer,
install the wheel attached to the Release into a virtual environment:

```bash
python3 -m venv roomscope-env
roomscope-env/bin/pip install "./roomscope-<version>-py3-none-any.whl[gui]"
roomscope-env/bin/roomscope gui
```

Leave out `[gui]` for the CLI and the Python API only. `pip install -e ".[gui]"`
is the developer install from a clone.

The About dialog and `THIRD_PARTY_LICENSES/` list Qt, libsndfile and the other
bundled licenses.

## Try it first: the demo

`roomscope demo` shows the whole workflow without an interface or a
microphone. It writes a sweep, simulates what a microphone would record at two
positions in a made-up room (one close to a desk and a side wall, one moved
back), analyses both with the same code as a real measurement, and compares
them. The walkthrough it prints ends with the commands to open the full
reports, the comparison, the desktop app, and your own first measurement.

Nothing in the demo is a measurement: the terminal says so first, each saved
session has the mode `synthetic_demo` and a note saying it was simulated, and
the demo never overwrites a folder it did not write. `roomscope demo --out
<folder>` chooses where the files go.

## Universal DAW Mode

1. `roomscope sweep --sample-rate <project rate> --out sweep.wav` (or the GUI
   “Universal DAW Mode” generate button, with the project's sample rate).
   Keep the `.roomscope-sweep.json` sidecar next to the WAV.
2. Import the WAV on a new DAW track, with time-stretching (Warp, Flex,
   Follow Tempo) off and no plug-in on its path. Route it to one loudspeaker.
3. Arm a second track with the measurement microphone, input monitoring off,
   and record while the sweep plays. Export the recorded track whole, without
   trimming or normalising.
4. Optional loopback: bounce a two-channel export (microphone + electrical
   return) and pass `--channel 0 --loopback-channel 1`.
5. `roomscope analyze --recording take.wav --sweep sweep.wav --out session/`,
   or in the GUI's “Universal DAW Mode” choose the files with “Choose
   Recording...” and “Choose Reference Sweep...”.

**Step-by-step notes for Pro Tools, Logic Pro / GarageBand, Cubase / Nuendo,
Studio One, Ableton Live, REAPER, FL Studio, Bitwig Studio and Audacity, and
what each report message means in DAW terms:
[daw-setup.md](daw-setup.md).**

## Standalone Mode and the loopback cable

`roomscope devices` lists interfaces. `roomscope measure --out session/` plays
the sweep and records. `--input-channels 1,2 --loopback-channel 2` records an
electrical return on input 2.

Start at a low monitor level. Levels above −12 dBFS need `--acknowledge-level`
every time; that confirmation is never saved.

**Demo** (GUI or `roomscope --backend fake measure`) runs the same flow on a
synthetic room. Nothing is sent to a loudspeaker.

### Per platform

`roomscope devices` prints each device with its host API in brackets.

* **Windows.** Every interface is listed once per host API. Prefer
  `[Windows WASAPI]` (or `[Windows WDM-KS]`); avoid `[MME]` and
  `[Windows DirectSound]`, which pass through the Windows mixer. In shared
  mode WASAPI only runs at the device's shared-mode format
  ([Microsoft: Device formats](https://learn.microsoft.com/en-us/windows/win32/coreaudio/device-formats)):
  set it to the measurement rate in the Sound control panel (Control Panel ▸
  Hardware and Sound ▸ Sound ▸ the device ▸ Properties ▸ Advanced ▸ *Default
  Format*), and set *Audio enhancements* to Off (Settings ▸ Sound ▸ the device)
  ([Microsoft support](https://support.microsoft.com/en-us/windows/fix-sound-or-audio-problems-in-windows-73025246-b61c-40fb-671a-2535c7cd56c8)). Allow desktop apps to use the microphone
  (Settings ▸ Privacy & security ▸ Microphone). The bundles carry no ASIO
  support (the ASIO DLLs are built with Steinberg's proprietary SDK and are
  removed, DEPENDENCIES.md §3); an interface that only works through ASIO is
  measured in Universal DAW Mode.
* **macOS.** Core Audio. Allow RoomScope in System Settings ▸ Privacy &
  Security ▸ Microphone; without that permission the recording is silent and
  RoomScope reports *"recording is silent"*. Set the interface's rate in Audio
  MIDI Setup, and combine separate input and output devices into an
  aggregate device there if needed.
* **Linux.** ALSA through the system PortAudio (`libportaudio2`). A `hw:`
  device gives the interface's own rates; `pipewire`, `pulse` or `default`
  go through the sound server, which may resample: RoomScope shows the
  device rate next to the requested one before measuring. Your user may need
  to be in the `audio` group.

## Reading a result

Each metric has a validity flag. `insufficient_decay_range` means the number is
withheld, not that it is zero. There is no single score. A recording profile
may add one notice when broadband C50 or C80 is a poor fit for that kind of
recording; the threshold is an engineering choice for the profile, not a grade.

Core diagnostics (`warnings`, `notes`, `reason`) stay in English in
`result.json` so bug reports compare across languages. The interface and the
text report show them in the interface language.

The Results page has eight tabs:

| Tab | What it shows |
| --- | --- |
| Overview | Key figures (reverberation, background noise, early reflections, direct sound) with their trust level, the findings, and tables of broadband and octave-band EDT / T20 / T30 / RT60 and C50 / C80 / D50 / centre time, each with validity. |
| Full report | The same text report that `roomscope analyze` prints, with the warnings at the end. “Copy report” copies it. |
| Impulse Response | The deconvolved IR. The peak is the direct sound; it is not normalised to 1.0. |
| Frequency Response | Raw (dotted) and smoothed (solid) magnitude. A dashed curve is the electrical loopback when compensation ran. 0 dB is the interface, not “flat in the room”. |
| Decay | Schroeder / energy-decay curves. Broadband is a solid line; octave bands use changing dash patterns so colour is not the only cue. |
| Noise | Quiet-segment spectrum and 50/60 Hz hum candidates. |
| Early Reflections | ETC peaks (delay ms, level dB re direct). Open markers for candidates. |
| Placement | Excess path, and — only with a tape-measured loudspeaker distance — loudspeaker height, the plane above both devices, and horizontal separation. No wall is named. |

Low-frequency resonance candidates are listed in the Full report (and in
`resonances.csv` after `roomscope export`). They are not a separate tab.

## Placement

The Results page has a Placement tab. Without a tape-measured loudspeaker
distance RoomScope only reports each arrival's excess path. With the
distance (and, for the vertical axis, the microphone height) it reports
loudspeaker height, the plane above both devices and the horizontal
separation. It never names a wall or gives room length or width.

Enter the tape numbers in Universal DAW Mode or Standalone Mode before
Analyze, or pass `--speaker-distance` / `--mic-height` / `--temperature`
on the CLI.

## Comparing two positions

`roomscope compare baseline/ candidate/ --same-input-gain` (or the GUI Compare
page). A decay delta is only VALID when both sides are VALID. The noise delta
needs an explicit “input gain unchanged” declaration. A change is never called
significant; ISO 3382-1’s just-noticeable difference for T is quoted as context.

The Compare page lists matched early reflections (delay ±0.5 ms) and
low-frequency resonances (within 1/6 octave, with decay-distinguishable
flags). `roomscope compare … --out comparison.json` writes the numbers only;
`roomscope show comparison.json` prints the report again and **re-derives**
findings (they are never stored in the file).

## Projects and averaging

A project folder holds `project.json` and ordinary session folders.
`roomscope project init --out room/ --name Booth` then
`roomscope project add room/ session/ --position desk`.
`roomscope project average room/` averages VALID T values only, never decay
curves, and names the ISO 3382-2 class the position counts reach.

## Export and language

`roomscope export session/ --format csv --out curves/` writes every curve.
`--lang zh_CN` (or Settings → Language, or `ROOMSCOPE_LANG`) translates
findings, the text-report labels, the GUI and CLI help (`roomscope --help`
and every subcommand). Units stay untranslated; digits stay ASCII.
Diagnostic notes and warnings are stored in English in `result.json` and
shown translated.

In a terminal the command line uses colour and the symbols ✓ ! ×; piped into
a file or another program it writes plain text. `--color never` or the
`NO_COLOR` environment variable turns colour off, `--color always` keeps it
in a pipe.

## Troubleshooting

| Symptom | What to check |
| --- | --- |
| Direct-sound confidence not high | Wrong sweep sidecar; loudspeaker distortion; trim the recording? Do not trim. |
| Wrong reference | The `.roomscope-sweep.json` next to the WAV must be the file RoomScope wrote for *this* sweep (same duration, band and fades). A sweep from another session, or the recording used as the reference, will mis-locate the IR. |
| Multiple passes in one bounce | Play the sweep once. With several passes in the same WAV, RoomScope analyses one of them (of the passes about as loud as the loudest, the one followed by the longest recorded decay, usually the last), ignores the others, ends the IR where the next pass starts and warns. Bounce a single take. |
| Clipping warning | Lower playback or input gain. |
| Insufficient decay range | Longer sweep, slightly louder playback, or a quieter room. |
| Device rate mismatch | The GUI shows the device rate next to the requested one; pick a supported rate. |
| Loopback refused | The return must look like an electrical pulse, not a room. If the second channel is another microphone, compensation is refused and the analysis continues uncompensated. |

## Reporting a problem

**Help ▸ Environment Report for Bug Reports** shows what a maintainer needs
first: the RoomScope version and build commit, the OS, library versions,
settings and audio devices (*Probe sample rates* adds the rates each device
accepts; nothing is played). *Copy* it into the issue; *Open Issue Page*
opens the template chooser. From a terminal the same report is
`roomscope doctor` (`--probe`, `--json`). Nothing is sent automatically;
read the text before posting, since device names can contain personal names.

`roomscope session bundle session/ --out report.zip` zips a session folder.
`--no-audio` leaves the WAVs out if you do not want to share a recording of
the room. Attach the zip to a measurement issue. Settings and the rotating
log live under `$ROOMSCOPE_HOME` (`~/.roomscope` by default); the report's
*Open Data Folder* button opens it.

Ran RoomScope with a real interface or through a DAW? The *Audio interface
test report* and *DAW compatibility report* templates record it; those runs
are the only source of [HARDWARE_TESTS.md](../HARDWARE_TESTS.md).
