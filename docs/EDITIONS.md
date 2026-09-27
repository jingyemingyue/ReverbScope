# Developer edition and installer edition

**English** | [简体中文](EDITIONS.zh-CN.md)

RoomScope is one code base with two defaults. Both run the same analysis
(`roomscope.core.pipeline.analyze`), read and write the same session files and
report the same numbers; they differ in what is shown around it. The Chinese
translation is [EDITIONS.zh-CN.md](EDITIONS.zh-CN.md).

| | Developer edition | Installer edition (recommended for users) |
| --- | --- | --- |
| How you get it | `git clone` + `pip install -e ".[dev,gui]"`, or `pip install roomscope-<version>-py3-none-any.whl` | `RoomScope-setup.exe`, `RoomScope-macos-<arch>.dmg`, `roomscope-linux-x86_64.tar.gz` from the Releases page |
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

## Developer edition: what it is for

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
* **Building releases.** `scripts/build_release.py` builds the installer
  edition of the current platform locally ([RELEASE_PLAN.md](RELEASE_PLAN.md) §3a).

## Installer edition: what it keeps simple

The installer edition opens on the Home page with the three workflows, and
its Settings dialog holds only what a user changes: language, theme (system,
light, dark), default recording profile, audio backend, default output folder
and whether the raw recording is copied into each session. Standalone Mode
still lists devices per host API, preselects the platform's recommended one,
stars the recommended input and output, and checks the host API, the channels
and separate clocks before anything is played.
