# ReverbScope user guide

**English** | [简体中文](zh-CN.md)

ReverbScope measures a recording room so you can hear what the room is doing to
close-miked sources. It does not score the room and it does not correct it.

This page is the English guide. The Chinese translation is
[zh-CN.md](zh-CN.md).

## Install

Download from the project's
[Releases page](https://github.com/jingyemingyue/ReverbScope/releases).
Step-by-step instructions for every system, updating, uninstalling and
troubleshooting are in [INSTALLATION.md](../INSTALLATION.md); this section is
the short version. Each
Release lists a `SHA256SUMS` file; compare it with the file you
downloaded (`shasum -a 256 <file>` on macOS / Linux,
`Get-FileHash <file>` in PowerShell).

ReverbScope comes in two editions. The **Desktop Edition** is the app this
guide describes, with the command line included; the **Terminal Edition** is
the command line only (no windows or charts), for scripts, servers and
computers without a desktop.

| System | Desktop Edition | Start ReverbScope |
| --- | --- | --- |
| Windows 10/11 x64 | `ReverbScope-Desktop-Windows-x64-Setup.exe` (installer) or `ReverbScope-Desktop-Windows-x64.zip` | Start menu → ReverbScope, or `reverbscope-gui.exe` in the zip |
| macOS 14+, Apple silicon | `ReverbScope-Desktop-macOS-arm64.dmg` | Drag ReverbScope to Applications, then open it |
| macOS 14+, Intel | `ReverbScope-Desktop-macOS-x86_64.dmg` | Drag ReverbScope to Applications, then open it |
| Linux x86_64 | `ReverbScope-Desktop-Linux-x86_64.tar.gz` | `tar xzf ReverbScope-Desktop-Linux-x86_64.tar.gz && reverbscope/reverbscope-gui` |

| System | Terminal Edition | Start ReverbScope |
| --- | --- | --- |
| Windows 10/11 x64 | `ReverbScope-Terminal-Windows-x64.zip` | Extract, double-click `ReverbScope Terminal.cmd`, type `reverbscope.exe demo` |
| macOS 14+, Apple silicon | `ReverbScope-Terminal-macOS-arm64.tar.gz` | `tar xzf` it, then `reverbscope-terminal/reverbscope demo` |
| macOS 14+, Intel | `ReverbScope-Terminal-macOS-x86_64.tar.gz` | `tar xzf` it, then `reverbscope-terminal/reverbscope demo` |
| Linux x86_64 | `ReverbScope-Terminal-Linux-x86_64.tar.gz` | `tar xzf` it, then `reverbscope-terminal/reverbscope demo` |

The Windows and Linux Desktop Edition bundles carry two programs: the desktop
app `reverbscope-gui` and the command-line tool `reverbscope` (run `reverbscope --help`
in a terminal). On macOS the app's executable is also the CLI when it is given
arguments: `/Applications/ReverbScope.app/Contents/MacOS/ReverbScope --help`.

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
  `fonts-noto-cjk` for Chinese text in charts. `packaging/linux/reverbscope.desktop`
  is a desktop entry you can adapt.

**From Python.** ReverbScope is not on PyPI yet. With Python 3.12 or newer,
install the wheel attached to the Release into a virtual environment:

```bash
python3 -m venv reverbscope-env
reverbscope-env/bin/pip install "./reverbscope-<version>-py3-none-any.whl[gui]"
reverbscope-env/bin/reverbscope gui
```

Leave out `[gui]` for the CLI and the Python API only. `pip install -e ".[gui]"`
is the developer install from a clone.

The About dialog and `THIRD_PARTY_LICENSES/` list Qt, libsndfile and the other
bundled licenses.

## Try it first: the demo

`reverbscope demo` shows the whole workflow without an interface or a
microphone. It writes a sweep, simulates what a microphone would record at two
positions in a made-up room (one close to a desk and a side wall, one moved
back), analyses both with the same code as a real measurement, and compares
them. The walkthrough it prints ends with the commands to open the full
reports, the comparison, the desktop app, and your own first measurement.

Nothing in the demo is a measurement: the terminal says so first, each saved
session has the mode `synthetic_demo` and a note saying it was simulated, and
the demo never overwrites a folder it did not write. `reverbscope demo --out
<folder>` chooses where the files go. The room, position and microphone names
the demo gives its sessions are written in the language it ran in, and shown
in the interface language when a session is opened, listed or reported.

## Universal DAW Mode

1. `reverbscope sweep --sample-rate <project rate> --out sweep.wav` (or the GUI
   “Universal DAW Mode” generate button, with the project's sample rate).
   Keep the `.reverbscope-sweep.json` sidecar next to the WAV.
2. Import the WAV on a new DAW track, with time-stretching (Warp, Flex,
   Follow Tempo) off and no plug-in on its path. Route it to one loudspeaker.
3. Arm a second track with the measurement microphone, input monitoring off,
   and record while the sweep plays. Export the recorded track whole, without
   trimming or normalising.
4. Optional loopback: bounce a two-channel export (microphone + electrical
   return) and pass `--channel 0 --loopback-channel 1`.
5. `reverbscope analyze --recording take.wav --sweep sweep.wav --out session/`,
   or in the GUI's “Universal DAW Mode” choose the files with “Choose
   Recording...” and “Choose Reference Sweep...”.

**Step-by-step notes for Pro Tools, Logic Pro / GarageBand, Cubase / Nuendo,
Fender Studio Pro (formerly PreSonus Studio One), Ableton Live, REAPER, FL Studio, Bitwig Studio, Digital Performer and Audacity, and
what each report message means in DAW terms:
[daw-setup.md](daw-setup.md).**

## Standalone Mode and the loopback cable

`reverbscope devices` lists interfaces. `reverbscope measure --out session/` plays
the sweep and records. `--input-channels 1,2 --loopback-channel 2` records an
electrical return on input 2.

The take's `sweep.wav` and `recording.wav` reach the folder only together with
the session that describes them: a take that is stopped or refused leaves the
folder as it was. Measuring into a session folder again replaces that session.
A folder that holds a sweep or a recording but no session (for example your
own `reverbscope sweep --out folder/sweep.wav`) is refused before anything is
played.

Start at a low monitor level. Levels above −12 dBFS need `--acknowledge-level`
every time; that confirmation is never saved.

**Demo** (GUI or `reverbscope --backend fake measure`) runs the same flow on a
synthetic room. Nothing is sent to a loudspeaker.

### Per platform

`reverbscope devices` prints each device with its host API in brackets.

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
* **macOS.** Core Audio. Allow ReverbScope in System Settings ▸ Privacy &
  Security ▸ Microphone; without that permission the recording is silent and
  ReverbScope reports *"recording is silent"*. Set the interface's rate in Audio
  MIDI Setup, and combine separate input and output devices into an
  aggregate device there if needed.
* **Linux.** ALSA through the system PortAudio (`libportaudio2`). A `hw:`
  device gives the interface's own rates; `pipewire`, `pulse` or `default`
  go through the sound server, which may resample: ReverbScope shows the
  device rate next to the requested one before measuring. Your user may need
  to be in the `audio` group.

## Reading a result

Each metric has a validity flag. `insufficient_decay_range` means the number is
withheld, not that it is zero. There is no single score. A recording profile
may add one notice when broadband C50 or C80 is a poor fit for that kind of
recording; the threshold is an engineering choice for the profile, not a grade.

**Measurement health** sits right under the key figures: the card below the
four tiles of the Overview tab, and the section right after "At a glance" in
the text report. It lists the checks the
analysis made on the take itself (reference, sweep, playback speed, direct
sound, level, distortion, dropouts, decay range, noise floor, recording
length, and the loopback and the audio device when they took part), each
*good*, *warning*, *invalid* or *unknown*, with the reason, the figures it
affects and what to do next. *Invalid* means a figure cannot be trusted (the
recording clipped, the sweep was played at the wrong speed); *unknown* means
the check could not be made (an imported impulse response). A sweep played at
the wrong speed lists where each DAW sets its sample rate or switches
time-stretching off, the same steps as [Measuring through your
DAW](daw-setup.md), also under the error when the analysis cannot finish.
The worst check gives the overall status; there is no score.

Core diagnostics (`warnings`, `notes`, `reason`) stay in English in
`result.json` so bug reports compare across languages. The interface and the
text report show them in the interface language.

The Results page has eight tabs:

| Tab | What it shows |
| --- | --- |
| Overview | Key figures (reverberation, background noise, early reflections, direct sound) with their trust level, the measurement-health card, the findings, and tables of broadband and octave-band EDT / T20 / T30 / RT60 and C50 / C80 / D50 / centre time, each with validity. |
| Full report | The same text report that `reverbscope analyze` prints, with the warnings at the end. “Copy report” copies it. |
| Impulse Response | The deconvolved IR. The peak is the direct sound; it is not normalised to 1.0. |
| Frequency Response | Raw (dotted) and smoothed (solid) magnitude. A dashed curve is the electrical loopback when compensation ran. 0 dB is the interface, not “flat in the room”. |
| Decay | Schroeder / energy-decay curves. Broadband is a solid line; octave bands use changing dash patterns so colour is not the only cue. |
| Noise | Quiet-segment spectrum and 50/60 Hz hum candidates. |
| Early Reflections | ETC peaks (delay ms, level dB re direct). Open markers for candidates. |
| Placement | Excess path, and — only with a tape-measured loudspeaker distance — loudspeaker height, the plane above both devices, and horizontal separation. No wall is named. |

Low-frequency resonance candidates are listed in the Full report (and in
`resonances.csv` after `reverbscope export`). They are not a separate tab.

## Placement

The Results page has a Placement tab. Without a tape-measured loudspeaker
distance ReverbScope only reports each arrival's excess path. With the
distance (and, for the vertical axis, the microphone height) it reports
loudspeaker height, the plane above both devices and the horizontal
separation. It never names a wall or gives room length or width.

Enter the tape numbers in Universal DAW Mode or Standalone Mode before
Analyze, or pass `--speaker-distance` / `--mic-height` / `--temperature`
on the CLI.

## Comparing two positions

`reverbscope compare baseline/ candidate/ --same-input-gain` (or the GUI Compare
page). A decay delta is only VALID when both sides are VALID. The noise delta
needs an explicit “input gain unchanged” declaration. A change is never called
significant; ISO 3382-1’s just-noticeable difference for T is quoted as context.

**Verdict.** Under the candidate's recording profile the comparison says, for
reverberation, clarity, early reflections, noise floor and low end, whether
the candidate is a *meaningful improvement*, a *meaningful degradation*,
*probably insignificant*, *not comparable*, or whether the evidence is
*insufficient*, with the reason each time (the card under the session
picker on the Compare page; the section after "At a glance" in the report; `verdict` in
`--format json`). The judgement uses the profile's thresholds (a vocal booth
does not care whether 0.30 s became 0.22 s; a room microphone calls a room
that became too dry a degradation), the just-noticeable differences, and the
measurement health of both takes when they are at hand; it never calls a
change statistically significant on one pair of positions
([MEASUREMENT_METHODOLOGY.md](../MEASUREMENT_METHODOLOGY.md) §11a).

The Compare page lists matched early reflections (delay ±0.5 ms) and
low-frequency resonances (within 1/6 octave, with decay-distinguishable
flags). Resonances are compared only in the range both takes searched: one
found where the other take never looked (its sweep started higher) is
neither gone nor new, and when one take did not search at all the low end
reads "not compared" (in the report, and as a note under the Resonances tab;
the Early Reflections tab explains the same way when the direct sound is not
trusted on both sides). `reverbscope compare … --out comparison.json` writes the numbers only;
`reverbscope show comparison.json` prints the report again and **re-derives**
findings (they are never stored in the file).

## Projects and averaging

A project folder holds `project.json` and ordinary session folders.
`reverbscope project init --out room/ --name Booth` then
`reverbscope project add room/ session/ --position desk`. Running `project init`
again on a folder that has a `project.json` is refused; `--force` starts the
project over, without its positions.
`reverbscope project average room/` averages VALID T values only, never decay
curves, and names the ISO 3382-2 class the position counts reach. The RT60
column is the mean of each session's own RT60 (T30, else T20). `n` is the
number of sessions averaged in a row; a value that averages fewer shows its
own count, for example `0.91 s (1)`.

## Export and language

`reverbscope export session/ --format csv --out curves/` writes every curve.
Exporting another session into the same folder removes the curve files that
session does not have (a `--no-curves` session has none), so the folder never
mixes two sessions.

ReverbScope follows the system's language: on a Mac the preferred languages
(System Settings → General → Language & Region; Terminal, iTerm and VS Code
set `LANG=en_US.UTF-8` whatever they are, so `LANG` comes after them), on
Windows the display language, on Linux `LANGUAGE`, `LC_ALL`, `LC_MESSAGES`
and `LANG`. `LC_ALL=C` (or `LC_MESSAGES=C`) gives English on every system,
as it does for other programs: `LC_ALL=C reverbscope show session/` for a bug
report. To keep one language whatever the system says, store it once:

```bash
reverbscope config language zh_CN   # 中文
reverbscope config language en      # English
reverbscope config language auto    # follow the system again
```

`reverbscope config language` shows the language in effect and why. The
desktop app's Settings → Language writes the same setting. `--lang zh_CN`
picks a language for one command and `REVERBSCOPE_LANG` for a shell; the
order is `--lang`, the stored setting, `REVERBSCOPE_LANG`, the system. The
home screen (bare `reverbscope`) and `reverbscope --help` end with the command
for the other language, written in that language.

Chinese translates findings, the text-report labels, the GUI and the whole
CLI help (`reverbscope --help` and every subcommand, placeholders and
argparse's own messages included). Units stay untranslated; digits stay
ASCII. Diagnostic notes and warnings are stored in English in `result.json`
and shown translated.

`reverbscope config` lists the other settings the desktop app keeps and
changes them from the command line, also in the Terminal Edition:
`profile` (the default recording profile), `backend` (`portaudio` or
`fake`), `output-folder`, `copy-recording` and `developer-tools` (`on` or
`off`), and `theme` (`system`, `light` or `dark`; desktop app only). For
example `reverbscope config profile vocal`; `auto` goes back to a setting's
default, and `reverbscope --format json config` prints the settings as JSON.

In a terminal the command line uses colour and the symbols ✓ ! ×; piped into
a file or another program it writes plain text. `--color never` or the
`NO_COLOR` environment variable turns colour off, `--color always` keeps it
in a pipe.

Piped or redirected output is UTF-8. Windows PowerShell decodes it in the
console's code page and garbles Chinese (`> report.txt`, `| Select-String`);
run `$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new()`
once in that window first, or see
[Saving a report from PowerShell](../INSTALLATION.md#terminal-edition).
Command Prompt is not affected.

## Troubleshooting

| Symptom | What to check |
| --- | --- |
| Direct-sound confidence not high | Wrong sweep sidecar; loudspeaker distortion; trim the recording? Do not trim. |
| Wrong reference | The `.reverbscope-sweep.json` next to the WAV must be the file ReverbScope wrote for *this* sweep (same duration, band and fades). A sweep from another session, or the recording used as the reference, will mis-locate the IR. |
| Multiple passes in one bounce | Play the sweep once. With several passes in the same WAV, ReverbScope analyses one of them (of the passes about as loud as the loudest, the one followed by the longest recorded decay, usually the last), ignores the others, ends the IR where the next pass starts and warns. Bounce a single take. |
| Clipping warning | Lower playback or input gain. |
| Insufficient decay range | Longer sweep, slightly louder playback, or a quieter room. |
| Device rate mismatch | The GUI shows the device rate next to the requested one; pick a supported rate. |
| Loopback refused | The return must look like an electrical pulse, not a room. If the second channel is another microphone, compensation is refused and the analysis continues uncompensated. |

## Reporting a problem

**Help ▸ Environment Report for Bug Reports** shows what a maintainer needs
first: the ReverbScope version and build commit, the OS, library versions,
settings and audio devices (*Probe sample rates* adds the rates each device
accepts; nothing is played). *Copy* it into the issue; *Open Issue Page*
opens the template chooser. From a terminal the same report is
`reverbscope doctor` (`--probe`, `--json`). Nothing is sent automatically;
read the text before posting, since device names can contain personal names.

`reverbscope session bundle session/ --out report.zip` zips a session folder.
`--no-audio` leaves the WAVs out if you do not want to share a recording of
the room. Paths in its JSON files show your home folder as `~`, as the
environment report does. Attach the zip to a measurement issue. Settings and the rotating
log live under `$REVERBSCOPE_HOME` (`~/.reverbscope` by default); the report's
*Open Data Folder* button opens it.

Ran ReverbScope with a real interface or through a DAW? The *Audio interface
test report* and *DAW compatibility report* templates record it; those runs
are the only source of [HARDWARE_TESTS.md](../HARDWARE_TESTS.md).
