# Editions: Desktop, Terminal and developer tools

**English** | [简体中文](EDITIONS.zh-CN.md)

RoomScope is one code base. It is downloaded in two **editions**, and any
copy can show or hide the **developer tools**. Every variant runs the same
analysis (`roomscope.core.pipeline.analyze`), reads and writes the same
session files and reports the same numbers. The Chinese translation is
[EDITIONS.zh-CN.md](EDITIONS.zh-CN.md).

Downloads are also offered as **two betas** (both still beta): a
**stable beta** (fewer bugs, narrower feature set) on the published
[Releases page](https://github.com/jingyemingyue/RoomScope/releases), and
a **preview beta** (stronger features, may be unstable) on this
development line. No preview Release was published. See
[INSTALLATION.md](INSTALLATION.md).

## Desktop Edition and Terminal Edition

| | Desktop Edition | Terminal Edition |
| --- | --- | --- |
| Downloads | `RoomScope-Desktop-macOS-arm64.dmg`, `RoomScope-Desktop-macOS-x86_64.dmg`, `RoomScope-Desktop-Windows-x64-Setup.exe`, `RoomScope-Desktop-Windows-x64.zip`, `RoomScope-Desktop-Linux-x86_64.tar.gz` | `RoomScope-Terminal-macOS-arm64.tar.gz`, `RoomScope-Terminal-macOS-x86_64.tar.gz`, `RoomScope-Terminal-Windows-x64.zip`, `RoomScope-Terminal-Linux-x86_64.tar.gz` |
| GUI (windows, charts) | yes | no: `roomscope gui` says to install the Desktop Edition |
| Command line (`roomscope`, every command) | yes | yes |
| Analysis, comparison, Standalone measurement, English / Chinese | yes | yes |
| Inside | Python runtime, NumPy, SciPy, soundfile, sounddevice, matplotlib, PySide6 Essentials (Qt) | Python runtime, NumPy, SciPy, soundfile, sounddevice; no Qt, PySide6 or matplotlib |
| Python required | no | no |
| Best for | most users | the command line, automation, servers and computers without a desktop |

Both are built by the same job of the release workflow from one PyInstaller
spec (`packaging/roomscope.spec`, `ROOMSCOPE_PACKAGE=desktop|terminal`). The
Terminal Edition leaves `roomscope.ui`, PySide6, shiboken6 and matplotlib out;
`scripts/check_bundle_contents.py --terminal` fails the build if any file of
them is left, and `scripts/smoke_bundle.py --terminal` runs the demo in
English and Chinese, checks that `--format json` prints only JSON and that
`roomscope gui` refuses with a sentence, not a traceback. `build_info.json`
records the edition (`"package"`), and `roomscope doctor` shows it. On
Linux x86_64 the Terminal Edition is about 60 MB compressed against about
150 MB for the Desktop Edition.

## Developer tools

The developer tools are a second, independent choice: two defaults of the
same program.

| | Developer defaults | Installed defaults (recommended for users) |
| --- | --- | --- |
| How you get it | `git clone` + `pip install -e ".[dev,gui]"`, or `pip install roomscope-<version>-py3-none-any.whl` | either edition from the Releases page |
| Detected by | not a frozen bundle (`sys.frozen` unset) | a PyInstaller bundle |
| Help ▸ Environment Report for Bug Reports (with sample-rate probe) | yes | yes |
| Developer menu (Audio Device Inspector, Open Data Folder) | yes | no, unless switched on |
| Advanced audio options in Standalone Mode (latency, WASAPI exclusive, Core Audio set-rate) | yes | no, unless switched on |
| Everyday settings (language, theme, default profile, audio backend, output folder) | yes | yes |
| Extending RoomScope | Python API, `roomscope.exporters` entry points, tests, `scripts/build_release.py` | — |

Override the choice for one run with `ROOMSCOPE_EDITION=developer` or
`ROOMSCOPE_EDITION=user`; an installed RoomScope switches the developer tools on
permanently with Settings ▸ *Show developer tools* (after a restart). The
command-line tool is the same in both editions: `roomscope devices --probe`,
`roomscope doctor` and the `measure` options `--latency`, `--wasapi-exclusive`
and `--coreaudio-set-rate` are always available.

### Developer defaults: what they are for

* **Debugging a device path.** Developer ▸ *Audio Device Inspector* lists every
  host API and device, probes the sample rates each accepts for one channel
  (nothing is played) and copies the inventory as JSON for an issue. What each
  host API does to the signal, with sources, is in
  [AUDIO_DEVICES.md](AUDIO_DEVICES.md).
* **Bug reports** (both editions). Help ▸ *Environment Report for Bug Reports*
  (or `roomscope doctor`, `--probe` for sample rates) shows the version and
  build commit, the versions of NumPy, SciPy, libsndfile, PortAudio and Qt,
  the settings, the paths RoomScope uses (home folder as `~`) and the audio
  devices it sees. Nothing is sent; the user copies it into an issue.
* **Extending.** Exporters register under the `roomscope.exporters` entry point
  (see `roomscope.io.exporters`); the analysis is a plain Python API
  (README ▸ Python API). Contributions follow [CONTRIBUTING.md](../CONTRIBUTING.md).
* **Building releases.** `scripts/build_release.py` builds both editions of
  the current platform locally ([RELEASE_PLAN.md](RELEASE_PLAN.md) §3a).

### Installed defaults: what they keep simple

An installed Desktop Edition opens on the Home page with the three workflows, and
its Settings dialog holds only what a user changes: language, theme (system,
light, dark), default recording profile, audio backend, default output folder
and whether the raw recording is copied into each session. Standalone Mode
still lists devices per host API, preselects the platform's recommended one,
stars the recommended input and output, and checks the host API, the channels
and separate clocks before anything is played.
