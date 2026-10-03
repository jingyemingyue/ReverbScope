## RoomScope v{version}

**Beta 1, for testing.** RoomScope measures a recording room
with a sine sweep and tells you whether a microphone position is usable —
next to any DAW, or on its own. Free and open source (Apache-2.0).
RoomScope is offered as **two betas** (both still beta): this published
pre-release is the **stable beta** (fewer bugs, narrower feature set).
The **preview beta** (stronger features, may be unstable) is the
development line and is not this file unless the release title says
Preview.

> **This is beta 1 of the software, not the 0.5.0 hardware release.**
> Current builds are unsigned, and **hardware validation has not started**:
> nothing has been measured through a real audio interface or a real DAW yet.
> Please read *Known limitations* below.

### Choose your edition

Download **one** file for your computer from **Assets** at the bottom of this
page. Neither edition needs Python.

#### 🖥 Desktop Edition — for most people

The app with windows, charts and buttons, plus the `roomscope` command line.

| Your computer | Download | Then |
| --- | --- | --- |
| **macOS** 14+, Apple silicon (M1 or later) | `RoomScope-Desktop-macOS-arm64.dmg` | Open the DMG, drag **RoomScope** onto **Applications**, open it from Applications |
| **macOS** 14+, Intel | `RoomScope-Desktop-macOS-x86_64.dmg` | Same as above |
| **Windows** 10 / 11, 64-bit | `RoomScope-Desktop-Windows-x64-Setup.exe` (installer) | Run it, then Start menu → **RoomScope** |
| | or `RoomScope-Desktop-Windows-x64.zip` (no installer) | **Extract All…**, open the folder, double-click **`roomscope-gui.exe`** |
| **Linux** x86_64 (glibc 2.39+) | `RoomScope-Desktop-Linux-x86_64.tar.gz` | Extract, run `roomscope/roomscope-gui` |

#### ⌨️ Terminal Edition — command line only

For the command line, scripts, servers and computers without a desktop. No
windows or charts, and about half the download size: the same measurement
and analysis, `roomscope demo`, English and Chinese.

| Your computer | Download | Then |
| --- | --- | --- |
| **macOS** 14+, Apple silicon | `RoomScope-Terminal-macOS-arm64.tar.gz` | `tar xzf` it, then `roomscope-terminal/roomscope demo` |
| **macOS** 14+, Intel | `RoomScope-Terminal-macOS-x86_64.tar.gz` | Same as above |
| **Windows** 10 / 11, 64-bit | `RoomScope-Terminal-Windows-x64.zip` | **Extract All…**, double-click **`RoomScope Terminal.cmd`**, type `roomscope demo` |
| **Linux** x86_64 (glibc 2.39+) | `RoomScope-Terminal-Linux-x86_64.tar.gz` | `tar xzf` it, then `roomscope-terminal/roomscope demo` |

Not sure? Take the **Desktop Edition**: it contains the command line too.

**First launch of an unsigned build**

* **macOS app:** macOS says Apple could not verify RoomScope. Click **Done**,
  then **System Settings → Privacy & Security → Open Anyway** and confirm.
  Needed once. Do not turn off Gatekeeper or System Integrity Protection; it
  is not necessary.
* **macOS Terminal Edition:** if macOS refuses to run `roomscope` from a
  folder your browser downloaded, run
  `xattr -dr com.apple.quarantine roomscope-terminal` once in that folder
  (it clears the download mark on these files only).
* **Windows:** if SmartScreen says *Windows protected your PC*, click
  **More info → Run anyway**.

Full steps, checksums, updating, uninstalling and troubleshooting:
[Installation guide](https://github.com/jingyemingyue/RoomScope/blob/v{version}/docs/INSTALLATION.md)
([简体中文](https://github.com/jingyemingyue/RoomScope/blob/v{version}/docs/INSTALLATION.zh-CN.md)).
Then try it without a microphone: click **Demo (no interface)** in the app, or
run `roomscope demo`.

### Known limitations

* **This is beta 1**, not a finished product, and **not 0.5.0**. In the
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
* Not on PyPI yet: `pip install roomscope` does not install this project.

**Help test it:** a result from your interface or DAW — pass or fail — is the
most useful contribution right now:
[interface report](https://github.com/jingyemingyue/RoomScope/issues/new?template=hardware.yml) ·
[DAW report](https://github.com/jingyemingyue/RoomScope/issues/new?template=daw.yml) ·
[bug report](https://github.com/jingyemingyue/RoomScope/issues/new?template=bug.yml).

### Checksums

`SHA256SUMS` lists the SHA-256 of every download above. Compare it with the
file you downloaded: `shasum -a 256 <file>` (macOS, Linux) or
`Get-FileHash <file>` (PowerShell).

{changes}

### Technical information

**What works** — implemented, and tested on synthetic rooms on Linux, macOS
and Windows CI machines:

* **Universal DAW Mode** (DAW-independent): RoomScope writes an exponential
  sine sweep (ESS) WAV; you play and record it in any DAW and load the
  recording back. Reads WAV / BWF / RF64 / W64 / AIFF / CAF / FLAC exports and
  names a DAW that played the sweep at the wrong speed.
* **Standalone Mode**: RoomScope plays the sweep and records the microphone
  through the audio interface you choose, with an optional loopback channel.
* **Room impulse response analysis**: deconvolution of the sweep, or
  `roomscope analyze-ir` for an impulse response from another tool.
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
* **Help → Environment Report for Bug Reports** (`roomscope doctor`) for
  issue reports; nothing is sent automatically.

**For Python developers** (3.12+): `roomscope-{version}-py3-none-any.whl`
(wheel) or `roomscope-{version}.tar.gz` (source), then
`pip install "./roomscope-{version}-py3-none-any.whl[gui]"` and `roomscope gui`.

**Also attached:** a CycloneDX SBOM (`cyclonedx.sbom.json`) and the pinned
bundle lock (`generated-bundle.lock`) the builds used.
