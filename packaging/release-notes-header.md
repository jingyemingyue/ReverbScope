## ReverbScope v{version}

**Beta 4, for testing.** ReverbScope measures a recording room
with a sine sweep and tells you whether a microphone position is usable —
next to any DAW, or on its own. Free and open source (Apache-2.0).

> **This is beta 4 of the software, not the 0.5.0 hardware release.**
> Current builds are unsigned, and **hardware validation has not started**:
> nothing has been measured through a real audio interface or a real DAW yet.
> Please read *Known limitations* below.

### Download

Download **one** file for your computer from **Assets** at the bottom of this
page. No Python needed.

#### 🖥 Desktop Edition

The app with windows, charts and buttons. It also contains the `reverbscope`
command line for advanced use; there is no separate Terminal download.

| Your computer | Download | Then |
| --- | --- | --- |
| **macOS** 14+, Apple silicon (M1 or later) | `ReverbScope-Desktop-macOS-arm64.dmg` | Open the DMG, drag **ReverbScope** onto **Applications**, open it from Applications |
| **macOS** 14+, Intel | `ReverbScope-Desktop-macOS-x86_64.dmg` | Same as above |
| **Windows** 10 / 11, 64-bit | `ReverbScope-Desktop-Windows-x64-Setup.exe` (installer) | Run it, then Start menu → **ReverbScope** |
| | or `ReverbScope-Desktop-Windows-x64.zip` (no installer) | **Extract All…**, open the folder, double-click **`reverbscope-gui.exe`** |
| **Linux** x86_64 (glibc 2.39+) | `ReverbScope-Desktop-Linux-x86_64.tar.gz` | Extract, run `reverbscope/reverbscope-gui` |

**First launch of an unsigned build**

* **macOS app:** macOS says Apple could not verify ReverbScope. Click **Done**,
  then **System Settings → Privacy & Security → Open Anyway** and confirm.
  Needed once. Do not turn off Gatekeeper or System Integrity Protection; it
  is not necessary.
* **Windows:** if SmartScreen says *Windows protected your PC*, click
  **More info → Run anyway**.

Full steps, checksums, updating, uninstalling and troubleshooting:
[Installation guide](https://github.com/jingyemingyue/ReverbScope/blob/v{version}/docs/INSTALLATION.md)
([简体中文](https://github.com/jingyemingyue/ReverbScope/blob/v{version}/docs/INSTALLATION.zh-CN.md)).
Then try it without a microphone: run `reverbscope demo` in a terminal opened
in the folder that holds the program (the desktop app has no demo mode).
Installers do not add it to `PATH`; on a Mac it is
`/Applications/ReverbScope.app/Contents/MacOS/ReverbScope demo`.

### Known limitations

* **This is beta 4**, not a finished product, and **not 0.5.0**. In the
  release plan, 0.5.0 means a person has run the hardware matrix. No cell
  is PASS yet.
* **Hardware validation has not started.** No measurement through a real
  audio interface, microphone or DAW has been recorded yet; the hardware
  matrix and the validation campaign are empty. **Measurement accuracy
  should not yet be treated as hardware-validated**: use the numbers to
  compare positions and to learn, and do not rely on them for acoustic
  treatment decisions until a validated release.
* **The builds are unsigned.** macOS: ad hoc signature only, not notarized by
  Apple. Windows: no Authenticode signature. The first launch shows a
  warning (see above); Windows 11 with Smart App Control on blocks unsigned
  apps entirely.
* Levels are **dBFS, not dB SPL**, unless you calibrate.
* The per-DAW steps are written from each vendor's documentation and have
  not been run in each DAW yet.
* macOS 14 is the declared minimum, but the macOS builds have only run on
  macOS 15 (Intel) and macOS 26 (Apple silicon) CI machines so far.
* So far the downloads have been installed and started only on GitHub's CI
  machines, not yet on a tester's own Mac, Windows PC or Linux desktop, and
  nobody has seen the Windows installer's Simplified Chinese screens on a
  Chinese Windows yet.
* Not on PyPI yet: `pip install reverbscope` does not install this project.
* The v0.5.0b1 downloads were still named `RoomScope-*` and `roomscope-*`;
  from this version every download carries the ReverbScope name. The
  earlier release is left as it was.

**Help test it:** a result from your interface or DAW — pass or fail — is the
most useful contribution right now:
[interface report](https://github.com/jingyemingyue/ReverbScope/issues/new?template=hardware.yml) ·
[DAW report](https://github.com/jingyemingyue/ReverbScope/issues/new?template=daw.yml) ·
[bug report](https://github.com/jingyemingyue/ReverbScope/issues/new?template=bug.yml).

### Checksums

`SHA256SUMS` lists the SHA-256 of every download above. Compare it with the
file you downloaded: `shasum -a 256 <file>` (macOS, Linux) or
`Get-FileHash <file>` (PowerShell).

{changes}

### Technical information

**What works** — implemented, and tested on synthetic rooms on Linux, macOS
and Windows CI machines:

* **Universal DAW Mode** (DAW-independent): ReverbScope writes an exponential
  sine sweep (ESS) WAV; you play and record it in any DAW and load the
  recording back. Reads WAV / BWF / RF64 / W64 / AIFF / CAF / FLAC exports and
  names a DAW that played the sweep at the wrong speed.
* **Standalone Mode**: ReverbScope plays the sweep and records the microphone
  through the audio interface you choose, with an optional loopback channel.
* **Room impulse response analysis**: deconvolution of the sweep, or
  `reverbscope analyze-ir` for an impulse response from another tool.
* **Reverberation**: EDT, T20, T30 and an estimated RT60, broadband and per
  octave band, each with a validity flag (*insufficient decay range* instead
  of an invented number).
* **Frequency response**, **early reflections**, **background noise floor**
  and mains hum, **potential low-frequency resonances**, and placement
  geometry from two tape measurements.
* **Microphone-position comparison** with a validity on every difference;
  projects that average several positions.
* Advice per kind of recording (vocal, voice-over, acoustic guitar, drums,
  room mic, choir); no "room score".
* **English and Simplified Chinese** throughout: GUI, command line, reports,
  Windows installer.
* **Help → Environment Report for Bug Reports** (`reverbscope doctor`) for
  issue reports; nothing is sent automatically.

**For Python developers** (3.12+): `reverbscope-{version}-py3-none-any.whl`
(wheel) or `reverbscope-{version}.tar.gz` (source), then
`pip install "./reverbscope-{version}-py3-none-any.whl[gui]"` and `reverbscope gui`.

**Also attached:** a CycloneDX SBOM (`cyclonedx.sbom.json`) and the pinned
bundle lock (`generated-bundle.lock`) the builds used.
