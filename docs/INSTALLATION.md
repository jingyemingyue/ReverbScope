# Installing ReverbScope

**English** | [简体中文](INSTALLATION.zh-CN.md)

**Download page:** <https://github.com/jingyemingyue/ReverbScope/releases>

Open that page, take the newest release at the top, expand **Assets** and
download the one file for your computer. ReverbScope comes in two editions;
neither needs Python or Git:

* **Desktop Edition** — the app with windows and charts, plus the command
  line. For most people.
* **Terminal Edition** — the command line only, built without the GUI (no
  Qt), about half the size. For scripts, automation, servers and computers
  without a desktop.

ReverbScope 0.4.x is an **early public pre-release for testing**. The builds are
**unsigned** (see [Unsigned-build warnings](#unsigned-build-warnings)) and
**no measurement has been validated on real audio hardware yet**
([HARDWARE_TESTS.md](HARDWARE_TESTS.md)).

## Which file do I need?

**Desktop Edition** (GUI + command line):

| Your computer | File | Section |
| --- | --- | --- |
| Mac with Apple silicon (M1 or later), macOS 14 or later | `ReverbScope-Desktop-macOS-arm64.dmg` | [macOS](#macos) |
| Mac with an Intel processor, macOS 14 or later | `ReverbScope-Desktop-macOS-x86_64.dmg` | [macOS](#macos) |
| Windows 10 or 11, 64-bit | `ReverbScope-Desktop-Windows-x64-Setup.exe` (installer) or `ReverbScope-Desktop-Windows-x64.zip` (no installer) | [Windows](#windows) |
| Linux x86_64 (glibc 2.39 or newer, e.g. Ubuntu 24.04+) | `ReverbScope-Desktop-Linux-x86_64.tar.gz` | [Linux](#linux) |

**Terminal Edition** (command line only):

| Your computer | File | Section |
| --- | --- | --- |
| Mac with Apple silicon, macOS 14 or later | `ReverbScope-Terminal-macOS-arm64.tar.gz` | [Terminal Edition](#terminal-edition) |
| Mac with an Intel processor, macOS 14 or later | `ReverbScope-Terminal-macOS-x86_64.tar.gz` | [Terminal Edition](#terminal-edition) |
| Windows 10 or 11, 64-bit | `ReverbScope-Terminal-Windows-x64.zip` | [Terminal Edition](#terminal-edition) |
| Linux x86_64 (glibc 2.39 or newer) | `ReverbScope-Terminal-Linux-x86_64.tar.gz` | [Terminal Edition](#terminal-edition) |

**Python developers** (any system with Python 3.12–3.14):
`reverbscope-<version>-py3-none-any.whl` or `reverbscope-<version>.tar.gz`, see
[Python](#python-wheel-and-source).

The other files on the release are for checking and auditing:
`SHA256SUMS` (checksums of every download, see
[Check the download](#check-the-download)), `cyclonedx.sbom.json` (software
bill of materials) and `generated-bundle.lock` (the exact library versions
inside the builds).

## Supported systems

| System | Status |
| --- | --- |
| macOS 14 Sonoma or later, Apple silicon or Intel | Supported. The DMGs are built, mounted, installed and started, and the Terminal Edition built and run, on GitHub's macOS 26 (Apple silicon) and macOS 15 (Intel) runners. macOS 14 is the minimum of the bundled NumPy / SciPy; it has not been run yet. macOS 13 and older are not supported. |
| Windows 10 / 11, x64 | Supported. The installer is built, installed silently, started and uninstalled, and the Terminal Edition built and run, on GitHub's Windows runner. No test on a personal Windows PC has been recorded yet. Windows on ARM and 32-bit Windows are not tested. |
| Linux x86_64 | Supported with glibc 2.39 or newer. Both editions built and smoke-tested on GitHub's Ubuntu runner. |
| Python | 3.12, 3.13, 3.14 (CI runs all three on Ubuntu, 3.12 on macOS and Windows). |

More detail on what verified each row: [COMPATIBILITY.md](COMPATIBILITY.md).

## macOS

This section is the **Desktop Edition**; the command-line-only download is
under [Terminal Edition](#terminal-edition).

### Install

1. On the [download page](https://github.com/jingyemingyue/ReverbScope/releases),
   download `ReverbScope-Desktop-macOS-arm64.dmg` (Apple silicon) or
   `ReverbScope-Desktop-macOS-x86_64.dmg` (Intel). Not sure? Apple menu →
   **About This Mac**: *Chip: Apple M…* is Apple silicon, *Processor: Intel*
   is Intel.
2. Double-click the DMG in your Downloads folder. A window opens with
   **ReverbScope** and a shortcut to **Applications**.
3. Drag **ReverbScope** onto **Applications**.
4. Eject the disk image (the ⏏ button next to *ReverbScope* in the Finder
   sidebar).
5. Open **Applications** and double-click **ReverbScope**. The first time,
   macOS shows a warning; follow [the next section](#first-launch-on-macos).

Launch ReverbScope from Applications, not from inside the disk image.

### First launch on macOS

The app is not notarized by Apple, so the first launch is blocked:

1. macOS says *“ReverbScope” Not Opened* / *Apple could not verify “ReverbScope”
   is free of malware…*. Click **Done** (not *Move to Trash*).
2. Open **System Settings → Privacy & Security** and scroll down to the
   **Security** section. It shows *“ReverbScope” was blocked to protect your Mac*.
3. Click **Open Anyway**, confirm with **Open Anyway** again and enter your
   login password if asked.

ReverbScope opens, and later launches open it without a warning. The
**Open Anyway** button appears only after that first attempt, for about an
hour. On macOS 14 you can also Control-click ReverbScope in Applications and
choose **Open**; since macOS 15 that shortcut no longer skips the check
([Apple](https://developer.apple.com/news/?id=saqachfa)). Apple's own
description of this dialog:
[Safely open apps on your Mac](https://support.apple.com/en-us/102445).

**You do not need to turn off Gatekeeper or System Integrity Protection, and
we recommend you do not.** ReverbScope needs no Terminal commands to open.

### Microphone access

The first **Standalone Mode** measurement asks *“ReverbScope” would like to
access the microphone*: click **Allow**. If you clicked *Don't Allow*, turn it
on later in **System Settings → Privacy & Security → Microphone**. The
recording stays on your computer; ReverbScope has no network code.

### Command line on macOS (optional)

The app's executable is also the command-line tool:

```bash
/Applications/ReverbScope.app/Contents/MacOS/ReverbScope --help
/Applications/ReverbScope.app/Contents/MacOS/ReverbScope doctor
```

## Windows

This section is the **Desktop Edition**; the command-line-only download is
under [Terminal Edition](#terminal-edition).

### Installer (recommended)

1. On the [download page](https://github.com/jingyemingyue/ReverbScope/releases),
   download `ReverbScope-Desktop-Windows-x64-Setup.exe`.
2. Run it. If SmartScreen says *Windows protected your PC*, click
   **More info → Run anyway** (see [warnings](#unsigned-build-warnings)).
3. If Setup asks whether to install for all users or only for you, choose
   **only for me** (no administrator rights needed). ReverbScope is then
   installed in `%LOCALAPPDATA%\Programs\ReverbScope`. Setup is in English or
   Simplified Chinese, following the Windows display language; you can tick
   *Create a desktop shortcut*.
4. Start ReverbScope from the **Start menu → ReverbScope** (or leave *Launch
   ReverbScope* ticked on the last page). The command-line tool is installed
   next to it: `reverbscope.exe` in the installation folder.

### ZIP (no installer)

1. Download `ReverbScope-Desktop-Windows-x64.zip`.
2. Right-click it → **Extract All…** → **Extract**. Do not run anything from
   inside the ZIP without extracting it: the program needs the `_internal`
   folder next to it.
3. Open the extracted folder `ReverbScope-Desktop-Windows-x64`. It contains:

   ```text
   reverbscope-gui.exe        the desktop app (double-click this)
   reverbscope.exe            the command-line tool
   _internal\               libraries (keep next to the .exe files)
   THIRD_PARTY_LICENSES\    licenses of the bundled components
   ```

4. Double-click **`reverbscope-gui.exe`**. SmartScreen may warn: **More info →
   Run anyway**.

You can move the whole folder anywhere (for example into `Documents`), as
long as `_internal` stays next to the `.exe` files. For the command-line
tool, open a terminal in that folder and run `.\reverbscope.exe --help`.

### Microphone access on Windows

If no input device appears or the recording is silent, check **Settings →
Privacy & security → Microphone**: *Microphone access* and *Let desktop apps
access your microphone* must be on.

## Linux

The **Desktop Edition** (the command-line-only download is under
[Terminal Edition](#terminal-edition)):

```bash
tar xzf ReverbScope-Desktop-Linux-x86_64.tar.gz
reverbscope/reverbscope-gui          # desktop app
reverbscope/reverbscope --help       # command-line tool
```

The bundle uses the system's PortAudio and graphics libraries. On Debian /
Ubuntu:

```bash
sudo apt install libportaudio2 libegl1 libgl1 libxkbcommon-x11-0 libxcb-cursor0
sudo apt install fonts-noto-cjk   # only for Chinese text in charts
```

`packaging/linux/reverbscope.desktop` in the source tree is a desktop entry you
can adapt. The bundle needs glibc 2.39 or newer (Ubuntu 24.04, Debian 13,
Fedora 40 or later).

## Terminal Edition

The command line without the GUI: every `reverbscope` command (`demo`, `sweep`,
`analyze`, `measure`, `compare`, `devices`, `doctor`, `project`, `session`,
`export`, …) in English and Chinese, with the same analysis as the Desktop
Edition. It is built without Qt, PySide6 and the chart library, so it is
about half the size, and `reverbscope gui` only says which download has the
GUI.

**macOS** (`ReverbScope-Terminal-macOS-arm64.tar.gz` for Apple silicon,
`ReverbScope-Terminal-macOS-x86_64.tar.gz` for Intel) and **Linux**
(`ReverbScope-Terminal-Linux-x86_64.tar.gz`):

```bash
tar xzf ReverbScope-Terminal-macOS-arm64.tar.gz      # or the file you downloaded
cd reverbscope-terminal
./reverbscope demo                                    # try it: synthetic data, nothing is played
./reverbscope --help
```

Keep the `_internal` folder next to `reverbscope`. To type `reverbscope` from
anywhere, add the folder to your `PATH` (for example
`export PATH="$HOME/reverbscope-terminal:$PATH"` in `~/.zshrc` or `~/.bashrc`).

On **macOS**, a browser marks downloaded files, and macOS refuses to run an
unsigned command-line program with that mark (*“reverbscope” cannot be opened
because the developer cannot be verified*). Clear the mark on this folder
once, in the folder that contains `reverbscope-terminal`:

```bash
xattr -dr com.apple.quarantine reverbscope-terminal
```

This changes only these files; it does not turn off Gatekeeper, and you
should not. It is a stop-gap for these unsigned pre-release builds; signed
builds will not need it. A file downloaded with `curl` has no such mark. The Linux
Terminal Edition needs `libportaudio2` for measurements
(`sudo apt install libportaudio2`), not the graphics libraries.

**Windows** (`ReverbScope-Terminal-Windows-x64.zip`): right-click →
**Extract All…**, open the extracted folder and double-click
**`ReverbScope Terminal.cmd`**. It opens a Command Prompt in that folder, ready
for `reverbscope.exe demo` or `reverbscope.exe --help`. (Double-clicking
`reverbscope.exe` itself closes its window as soon as it has printed.) From
PowerShell, `.\reverbscope.exe demo` in the folder does the same.

## Python (wheel and source)

ReverbScope is **not on PyPI yet**, so `pip install reverbscope` does not install
this project; until this page says otherwise, a `reverbscope` package on PyPI
is not from us. Use the files attached to the release, or a clone.

### Wheel from a release

Python 3.12 or newer. Download `reverbscope-<version>-py3-none-any.whl`, then:

```bash
python3 -m venv reverbscope-env
source reverbscope-env/bin/activate          # Windows: reverbscope-env\Scripts\activate
pip install "./reverbscope-0.5.0b1-py3-none-any.whl[gui]"
reverbscope --help
reverbscope gui                              # or: reverbscope-gui
```

Leave out `[gui]` for the command-line tool and the Python API only (no
PySide6, which takes about 230 MB installed); `reverbscope gui` then tells you how
to add it. A first run without an audio interface:

```bash
reverbscope --backend fake measure --out demo/ --duration 2 --post-silence 1.5
reverbscope show demo/
```

`reverbscope-<version>.tar.gz` is the source archive: `pip install
"./reverbscope-0.5.0b1.tar.gz[gui]"` builds the same wheel locally.

### Developer install (from Git)

```bash
git clone https://github.com/jingyemingyue/ReverbScope.git
cd ReverbScope
python3.12 -m venv .venv
source .venv/bin/activate                  # Windows: .venv\Scripts\activate
pip install -e ".[dev,gui]"
reverbscope --help
pytest
```

The checks a contributor runs are in [CONTRIBUTING.md](../CONTRIBUTING.md).
A developer install shows the Audio Device Inspector and the advanced stream
options that the desktop builds hide ([EDITIONS.md](EDITIONS.md)).

## Check the download

Optional. Each release has one `SHA256SUMS` file with a line for every
download. Compute the checksum of your file and compare it with the line for
that file name:

```bash
shasum -a 256 ReverbScope-Desktop-macOS-arm64.dmg          # macOS
sha256sum ReverbScope-Terminal-Linux-x86_64.tar.gz         # Linux
```

```powershell
Get-FileHash .\ReverbScope-Desktop-Windows-x64-Setup.exe   # Windows PowerShell (SHA256)
```

A match shows the file is the one attached to the release. It does not prove
who built it; that is what code signing will add.

## Unsigned-build warnings

**Current builds are unsigned development/pre-release builds.** The macOS
app carries only an ad hoc signature and is not notarized by Apple; the
Windows files carry no Authenticode signature. Your system therefore cannot
tell who published them and warns once:

| System | What you see | What to do |
| --- | --- | --- |
| macOS 15 and later | *Apple could not verify “ReverbScope” is free of malware…* | **Done**, then **System Settings → Privacy & Security → Open Anyway** ([details](#first-launch-on-macos)) |
| macOS 14 | *“ReverbScope” can't be opened because Apple cannot check it for malicious software* (or *…from an unidentified developer*) | Control-click → **Open**, or the Privacy & Security route above |
| Windows 10 / 11 | *Windows protected your PC* (SmartScreen) | **More info → Run anyway** |
| Windows 11 with Smart App Control on | The app is blocked without a *Run anyway* option | Unsigned builds cannot run there; use the [Python install](#python-wheel-and-source) until signed builds exist |

The builds come from the public
[release workflow](https://github.com/jingyemingyue/ReverbScope/actions/workflows/release.yml),
and each one records the commit it was built from (**Help → Environment
Report for Bug Reports**). Signing is planned before 1.0
([RELEASE_PLAN.md](RELEASE_PLAN.md) §5).

## Updating

Download the new file from the same page and:

* **macOS:** quit ReverbScope, open the new DMG and drag ReverbScope onto
  Applications again; choose **Replace**. The first-launch warning can appear
  once more for the new build.
* **Windows installer:** run the new `ReverbScope-Desktop-Windows-x64-Setup.exe`;
  it replaces the installed version.
* **Windows ZIP / Linux / Terminal Edition:** delete the old folder and
  extract the new archive.
* **Wheel:** `pip install --upgrade "./reverbscope-<new version>-py3-none-any.whl[gui]"`
  in the same virtual environment.
* **Developer install:** `git pull`, then `pip install -e ".[dev,gui]"` again.

Settings, the recent-sessions list and the log in `~/.reverbscope` are kept,
and your saved session folders are never touched.

## Uninstalling

* **macOS:** quit ReverbScope and drag **ReverbScope** from Applications to the
  Trash.
* **Windows installer:** **Settings → Apps → Installed apps → ReverbScope →
  Uninstall**, or Start menu → *Uninstall ReverbScope*.
* **Windows ZIP / Linux / Terminal Edition:** delete the extracted folder.
* **Python:** `pip uninstall reverbscope`, or delete the virtual environment
  folder.

To remove ReverbScope's settings, log, recent-sessions list and font cache as
well, delete the `.reverbscope` folder in your home folder
(`~/.reverbscope` on macOS / Linux, `%USERPROFILE%\.reverbscope` on Windows;
`REVERBSCOPE_HOME` overrides it). Measurements you saved stay wherever you
saved them.

## Troubleshooting

| Problem | What to do |
| --- | --- |
| macOS: *Apple could not verify “ReverbScope”…* | Expected for this unsigned build: [First launch on macOS](#first-launch-on-macos). |
| macOS: *“ReverbScope” is damaged and can't be opened* | The download is incomplete or was changed. Delete it, download it again and [check the checksum](#check-the-download). Do not work around this message. |
| macOS: *not supported on this type of Mac*, or it does not start on macOS 13 or older | Use the DMG that matches your Mac; macOS 14 or later is required. |
| macOS / Windows: no microphone input | Allow microphone access ([macOS](#microphone-access), [Windows](#microphone-access-on-windows)), then **Help → Environment Report for Bug Reports** lists what ReverbScope sees. |
| Windows: nothing happens, or a missing-DLL error | Extract the whole ZIP first (**Extract All…**) and keep `_internal` next to `reverbscope-gui.exe`. |
| Windows: no *Run anyway* button | Smart App Control or a company policy blocks unsigned apps; see the [table above](#unsigned-build-warnings). |
| Linux: `libEGL.so.1`, `libportaudio` or *xcb* plugin errors | Install the [system libraries](#linux). |
| Linux: Chinese chart labels show empty boxes | `sudo apt install fonts-noto-cjk` |
| `reverbscope gui` says *This is the Terminal Edition* | The Terminal Edition has no GUI; download the Desktop Edition (the command line works in both). |
| macOS: *“reverbscope” cannot be opened because the developer cannot be verified* (Terminal Edition) | Clear the download mark once: `xattr -dr com.apple.quarantine reverbscope-terminal` ([Terminal Edition](#terminal-edition)). |
| Windows: `reverbscope.exe` opens and closes at once | It is a command-line program: double-click `ReverbScope Terminal.cmd` instead, or run it from a Command Prompt. |
| `reverbscope gui` says PySide6 could not be loaded | Install the GUI extra: `pip install "PySide6_Essentials>=6.6"` (or reinstall the wheel with `[gui]`). |
| `pip install reverbscope` finds nothing, or something else | ReverbScope is not on PyPI yet; use the [wheel](#wheel-from-a-release). |
| Anything else | Open a [bug report](https://github.com/jingyemingyue/ReverbScope/issues/new?template=bug.yml) and paste **Help → Environment Report for Bug Reports** (or `reverbscope doctor`). Nothing is sent automatically. |

Next: the [user guide](user-guide/en.md) walks through a first measurement.
