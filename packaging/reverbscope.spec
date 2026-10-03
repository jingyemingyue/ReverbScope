# PyInstaller one-directory spec (ARCHITECTURE_V1.md §6.2).
# Builds are unsigned until the maintainer holds signing identities.
#
# Two editions from one spec (docs/EDITIONS.md):
#
#   REVERBSCOPE_PACKAGE=desktop (default)  GUI + CLI: dist/reverbscope (and
#                                        dist/ReverbScope.app on macOS)
#   REVERBSCOPE_PACKAGE=terminal           CLI only, no Qt / PySide6 and no
#                                        matplotlib: dist/reverbscope-terminal
#
# Build the terminal edition with its own work folder so the two builds do
# not share PyInstaller's cache:
#   REVERBSCOPE_PACKAGE=terminal pyinstaller --workpath build/terminal packaging/reverbscope.spec
# -*- mode: python ; coding: utf-8 -*-

import json
import os
import plistlib
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(SPECPATH).resolve().parent  # noqa: F821
PACKAGE = os.environ.get("REVERBSCOPE_PACKAGE", "desktop").strip().lower()
if PACKAGE not in ("desktop", "terminal"):
    raise SystemExit(f"REVERBSCOPE_PACKAGE must be desktop or terminal, not {PACKAGE!r}")
TERMINAL = PACKAGE == "terminal"
MACOS_INFO = plistlib.loads((ROOT / "packaging" / "macos" / "Info.plist").read_bytes())
VERSION = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
MACOS_INFO["CFBundleShortVersionString"] = VERSION
MACOS_INFO["CFBundleVersion"] = VERSION


def _commit():
    """The commit being built: GitHub Actions' GITHUB_SHA, else git, else None."""
    if os.environ.get("GITHUB_SHA"):
        return os.environ["GITHUB_SHA"]
    try:
        done = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return done.stdout.strip() or None


# reverbscope doctor reports which commit a bundle came from (several draft
# builds can carry the same version number).
BUILD_INFO = {"version": VERSION, "commit": _commit(), "package": PACKAGE}
if os.environ.get("GITHUB_RUN_ID") and os.environ.get("GITHUB_REPOSITORY"):
    BUILD_INFO["ci_run"] = "{}/{}/actions/runs/{}".format(
        os.environ.get("GITHUB_SERVER_URL", "https://github.com"),
        os.environ["GITHUB_REPOSITORY"],
        os.environ["GITHUB_RUN_ID"],
    )
BUILD_INFO_FILE = Path(workpath) / "build_info.json"  # noqa: F821
BUILD_INFO_FILE.parent.mkdir(parents=True, exist_ok=True)
BUILD_INFO_FILE.write_text(json.dumps(BUILD_INFO, indent=1), encoding="utf-8")

# The terminal edition: the command line and the analysis only. The GUI
# package, Qt and the plotting stack (only the GUI draws charts) stay out;
# ``reverbscope gui`` then says it is the Terminal Edition.
TERMINAL_EXCLUDES = [
    "PySide6",
    "shiboken6",
    "reverbscope.ui",
    "matplotlib",
    "PIL",
    "kiwisolver",
    "contourpy",
    "fontTools",
    "tkinter",
    "_tkinter",
    # Build tools a developer environment has installed; nothing at run time imports them.
    "setuptools",
    "pkg_resources",
    "_distutils_hack",
    "yaml",
    # Test runners that NumPy's and SciPy's test helpers would pull in.
    "pytest",
    "_pytest",
    "pluggy",
    "iniconfig",
    "pygments",
    "py",
]

a = Analysis(
    [str(ROOT / "src" / "reverbscope" / "__main__.py")],
    pathex=[str(ROOT / "src")],
    binaries=[],
    datas=[
        (str(ROOT / "src" / "reverbscope" / "schemas"), "reverbscope/schemas"),
        (str(ROOT / "src" / "reverbscope" / "locale"), "reverbscope/locale"),
        (str(BUILD_INFO_FILE), "reverbscope"),
    ],
    hiddenimports=["reverbscope.cli.main"] if TERMINAL else ["reverbscope.cli.main", "reverbscope.ui.app"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=TERMINAL_EXCLUDES
    if TERMINAL
    else [
        "PySide6.QtCharts",
        "PySide6.QtDataVisualization",
        "PySide6.QtGraphs",
        "PySide6.QtLottie",
        "PySide6.QtQuick3D",
        "PySide6.QtHttpServer",
        "PySide6.QtNetworkAuth",
        "PySide6.QtShaderTools",
        "PySide6.QtQuickTimeline",
        "PySide6.QtVirtualKeyboard",
    ],
    noarchive=False,
)
# Linux: use the distribution's PortAudio, ALSA and JACK libraries, as the
# user guide says (libportaudio2). The sounddevice hook would otherwise copy
# the build runner's libportaudio with libasound and libjack (and Berkeley DB,
# which libjack links): a libasound built for Ubuntu looks for ALSA plugins,
# PipeWire's among them, in Ubuntu's directory and misses them elsewhere.
if sys.platform.startswith("linux"):
    SYSTEM_AUDIO_LIBS = ("libportaudio.so", "libasound.so", "libjack.so", "libdb-")
    a.binaries = [
        entry for entry in a.binaries if not Path(entry[0]).name.startswith(SYSTEM_AUDIO_LIBS)
    ]

pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="reverbscope",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
)
# Windows and Linux: a windowed ``reverbscope-gui`` launcher next to the console
# executable, sharing its libraries. Explorer, the Start menu and desktop files
# start it without arguments and ``reverbscope.__main__.desktop_args`` opens the
# GUI; the console ``reverbscope`` keeps the CLI and never flashes a window.
launchers = [exe]
if sys.platform != "darwin" and not TERMINAL:
    launchers.append(
        EXE(
            pyz,
            a.scripts,
            [],
            exclude_binaries=True,
            name="reverbscope-gui",
            debug=False,
            bootloader_ignore_signals=False,
            strip=False,
            upx=False,
            console=False,
        )
    )
coll = COLLECT(
    *launchers,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="reverbscope-terminal" if TERMINAL else "reverbscope",
)

# Keep the console executable for CLI users. Finder needs a separate windowed
# bootloader so the .app opens the GUI and receives normal macOS app events.
if sys.platform == "darwin" and not TERMINAL:
    gui_exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name="ReverbScope",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        console=False,
    )
    gui_coll = COLLECT(
        gui_exe,
        a.binaries,
        a.datas,
        strip=False,
        upx=False,
        name="reverbscope-gui",
    )
    app = BUNDLE(  # noqa: F821
        gui_coll,
        name="ReverbScope.app",
        icon=None,
        bundle_identifier="org.reverbscope.ReverbScope",
        info_plist=MACOS_INFO,
    )
