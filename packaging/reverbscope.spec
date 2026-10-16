# PyInstaller one-directory spec (ARCHITECTURE_V1.md §6.2).
# Builds are unsigned until the maintainer holds signing identities.
#
# Two editions from one spec (docs/EDITIONS.md):
#
#   REVERBSCOPE_PACKAGE=desktop (default)  GUI + CLI: dist/reverbscope (and
#                                        dist/ReverbScope.app on macOS)
#   REVERBSCOPE_PACKAGE=terminal           CLI only, no Qt / PySide6, no
#                                        pyqtgraph and no matplotlib:
#                                        dist/reverbscope-terminal
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

# Both editions. Nothing at run time imports these, but NumPy's and SciPy's
# test helpers (and cffi's distutils shim) pull them into the analysis; they
# would ship without their licence texts in THIRD_PARTY_LICENSES.
DEV_ONLY_EXCLUDES = [
    # Build tools a developer environment has installed.
    "setuptools",
    "pkg_resources",
    "_distutils_hack",
    "yaml",
    # Test runners.
    "pytest",
    "_pytest",
    "pluggy",
    "iniconfig",
    "pygments",
    "py",
    # Optional for pdb/cmd/code; on Linux it would bring GNU libreadline (GPL).
    "readline",
]

# The terminal edition: the command line and the analysis only. The GUI
# package, Qt and the plotting stack (only the GUI draws charts) stay out;
# ``reverbscope gui`` then says it is the Terminal Edition.
TERMINAL_EXCLUDES = [
    "PySide6",
    "shiboken6",
    "reverbscope.ui",
    "pyqtgraph",
    "colorama",
    "matplotlib",
    "PIL",
    "kiwisolver",
    "contourpy",
    "fontTools",
    "tkinter",
    "_tkinter",
    *DEV_ONLY_EXCLUDES,
]

# The desktop charts (GUI_2_ARCHITECTURE.md §9): pyqtgraph draws with
# QPainter. Its 3D package (PyOpenGL), examples, Jupyter widget and numba
# kernels stay out, and so do the optional libraries they would pull in.
# pyqtgraph imports QtTest only for its own test helpers, inside try/except.
PYQTGRAPH_EXCLUDES = [
    "PySide6.QtTest",
    "pyqtgraph.opengl",
    "pyqtgraph.examples",
    "pyqtgraph.jupyter",
    "pyqtgraph.functions_numba",
    "OpenGL",
    "OpenGL_accelerate",
    "jupyter_rfb",
    "numba",
    "cupy",
    "h5py",
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
        *DEV_ONLY_EXCLUDES,
        *PYQTGRAPH_EXCLUDES,
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
sys.path.insert(0, str(ROOT / "packaging"))
from pyinstaller_filters import without_plugin, without_unused_colormaps

# pyqtgraph's hook copies all of its ~70 colour-map tables; the app uses
# viridis and inferno (reverbscope.ui.pg.COLORMAPS).
a.datas = without_unused_colormaps(a.datas)
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
    # Qt's GTK3 platform theme only gives Qt's own dialogs a GTK look. It links
    # GTK, GDK, Pango, Cairo, ATK and gdk-pixbuf, so PyInstaller copied about
    # thirty of the build runner's libraries, most of them LGPL, into the
    # tarball and carried Ubuntu's GTK to other distributions. Without it Qt
    # draws its own dialogs; the libraries that only it loads go with it.
    from PyInstaller.depend.bindepend import get_imports

    def _loads(path):
        return {Path(name).name for name, _resolved in get_imports(path)}

    a.binaries = without_plugin(a.binaries, "platformthemes/libqgtk3.so", _loads)

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
    # AppKit picks the app's language among the localizations the bundle
    # declares (Info.plist CFBundleLocalizations and the .lproj folders); with
    # English alone, the native file panels, the app menu and the microphone
    # prompt stayed English in the Chinese app. A translated purpose string can
    # only come from <language>.lproj/InfoPlist.strings, which BUNDLE puts in
    # Contents/Resources.
    localized = [
        (f"{strings.parent.name}/{strings.name}", str(strings), "DATA")
        for strings in sorted((ROOT / "packaging" / "macos").glob("*.lproj/InfoPlist.strings"))
    ]
    app = BUNDLE(  # noqa: F821
        gui_coll,
        localized,
        name="ReverbScope.app",
        icon=None,
        bundle_identifier="org.reverbscope.ReverbScope",
        info_plist=MACOS_INFO,
    )
