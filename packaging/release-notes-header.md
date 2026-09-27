## RoomScope v{version}

**Early public pre-release for testing.** RoomScope measures a recording room
with a sine sweep and tells you whether a microphone position is usable —
next to any DAW, or on its own. Free and open source (Apache-2.0).

> **Current builds are unsigned development/pre-release builds**, and
> **hardware validation is still in progress**: nothing has been measured
> through a real audio interface or a real DAW yet. Please read
> *Important limitations* below.

### Download

Download **one** file for your computer from **Assets** at the bottom of this
page.

| Your computer | File | Then |
| --- | --- | --- |
| **macOS** 14+, Apple silicon (M1 or later) | `RoomScope-macos-arm64.dmg` | Open the DMG, drag **RoomScope** onto **Applications**, open it from Applications |
| **macOS** 14+, Intel | `RoomScope-macos-x86_64.dmg` | Same as above |
| **Windows** 10 / 11, 64-bit | `RoomScope-setup.exe` (installer) | Run it, then Start menu → **RoomScope** |
| | or `roomscope-windows-x64.zip` (no installer) | **Extract All…**, open the folder, double-click **`roomscope-gui.exe`** |
| **Linux** x86_64 (glibc 2.39+) | `roomscope-linux-x86_64.tar.gz` | Extract, run `roomscope/roomscope-gui` |
| **Python developers** (3.12+) | `roomscope-{version}-py3-none-any.whl` (wheel) or `roomscope-{version}.tar.gz` (source) | `pip install "./roomscope-{version}-py3-none-any.whl[gui]"`, then `roomscope gui` |

**First launch of an unsigned build**

* **macOS:** macOS says Apple could not verify RoomScope. Click **Done**, then
  **System Settings → Privacy & Security → Open Anyway** and confirm. Needed
  once. Do not turn off Gatekeeper or System Integrity Protection; it is not
  necessary.
* **Windows:** if SmartScreen says *Windows protected your PC*, click
  **More info → Run anyway**.

Full steps, checksums, updating, uninstalling and troubleshooting:
[Installation guide](https://github.com/jingyemingyue/RoomScope/blob/v{version}/docs/INSTALLATION.md)
([简体中文](https://github.com/jingyemingyue/RoomScope/blob/v{version}/docs/INSTALLATION.zh-CN.md)).
Then open RoomScope and click **Demo (no interface)** to see a complete result
without playing anything.

### What works

Implemented, and tested on synthetic rooms on Linux, macOS and Windows CI
machines:

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
* **Desktop GUI and command line** (`roomscope`), plus a Python API; session
  folders, shareable bundles and CSV export.
* **English and Simplified Chinese** throughout: GUI, command line, reports,
  Windows installer.
* **Help → Environment Report for Bug Reports** (`roomscope doctor`) for
  issue reports; nothing is sent automatically.

### Important limitations

* **This is a pre-release** for early testers, not a finished product.
* **Hardware validation is still in progress.** No measurement through a real
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
* macOS 14 is the declared minimum, but the DMGs have only run on macOS 15
  (Intel) and macOS 26 (Apple silicon) CI machines so far.
* Not on PyPI yet: `pip install roomscope` does not install this project.

**Help test it:** a result from your interface or DAW — pass or fail — is the
most useful contribution right now:
[interface report](https://github.com/jingyemingyue/RoomScope/issues/new?template=hardware.yml) ·
[DAW report](https://github.com/jingyemingyue/RoomScope/issues/new?template=daw.yml) ·
[bug report](https://github.com/jingyemingyue/RoomScope/issues/new?template=bug.yml).

Checksums: `SHA256SUMS-*`. Also attached: a CycloneDX SBOM
(`cyclonedx.sbom.json`) and the pinned bundle lock (`generated-bundle.lock`).

---

