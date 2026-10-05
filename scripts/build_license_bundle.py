"""Build THIRD_PARTY_LICENSES/ for a desktop bundle (ARCHITECTURE_V1.md §6.2).

Copies license files from installed distributions, adds the license texts
that the wheels omit (LGPL-3.0 and GPL-3.0 for Qt / PySide6, the PortAudio
license) from ``packaging/licenses/``, copies the libsndfile LGPL-2.1 text and
source notes that soundfile keeps outside its metadata, adds short notices
(libsndfile, FreeType, Qhull, Agg), and fails if a required package still has no license text or if
PySide6 is installed but the LGPL / GPL texts are missing. matplotlib's old
``ttconv`` module is treated as resolved: matplotlib 3.10+ (which ReverbScope
requires) no longer contains it.
"""

from __future__ import annotations

import argparse
import sys
from importlib.metadata import PackageNotFoundError, distribution
from pathlib import Path

REQUIRED = [
    "numpy",
    "scipy",
    "soundfile",
    "sounddevice",
    "matplotlib",
    "cffi",
    "pycparser",
    "pillow",
    "contourpy",
    "cycler",
    "fonttools",
    "kiwisolver",
    "packaging",
    "pyparsing",
    "python-dateutil",
    "six",
]

OPTIONAL = ["PySide6_Essentials", "shiboken6", "PySide6"]

#: What the Terminal Edition ships (``REVERBSCOPE_PACKAGE=terminal`` in
#: packaging/reverbscope.spec): the analysis and audio stack, without Qt and
#: without matplotlib and its dependencies.
TERMINAL_REQUIRED = [
    "numpy",
    "scipy",
    "soundfile",
    "sounddevice",
    "cffi",
    "pycparser",
    "packaging",
]
#: Notices that concern only the GUI's libraries.
GUI_NOTICES = ("freetype", "agg", "pyside6", "ttconv")

# Verbatim license texts kept in the repository because the wheels omit them
# (DEPENDENCIES.md §3-§4). Every bundle ships all of them; the LGPL / GPL
# texts are additionally *required* whenever PySide6 is installed.
TEXTS_DIR = Path(__file__).resolve().parents[1] / "packaging" / "licenses"
TEXTS = ("LGPL-3.0.txt", "GPL-3.0.txt", "PortAudio-LICENSE.txt")
QT_TEXTS = ("LGPL-3.0.txt", "GPL-3.0.txt")

# License files a wheel keeps outside its .dist-info folder. soundfile's
# wheels bundle libsndfile (LGPL-2.1-or-later, text in _soundfile_data/COPYING)
# and list the source of libsndfile's own components (mpg123, LAME, FLAC, Ogg,
# Vorbis, Opus) in licensing/license_notes.md (DEPENDENCIES.md §3).
# (path, required when the library is bundled)
PACKAGE_LICENSE_FILES = {
    "soundfile": (("_soundfile_data/COPYING", True), ("licensing/license_notes.md", False)),
}
#: Package files that mean a bundled library needs the files above.
BUNDLED_LIBRARY_MARKERS = {"soundfile": "_soundfile_data/libsndfile"}

KNOWN_NOTICES = {
    "portaudio": (
        "PortAudio (http://www.portaudio.com) is used through the sounddevice\n"
        "wheel. Its license text is in _texts/PortAudio-LICENSE.txt.\n"
    ),
    "libsndfile": (
        "libsndfile (https://github.com/libsndfile/libsndfile) is bundled in the\n"
        "soundfile wheel as a separate shared library under the GNU Lesser General\n"
        "Public License 2.1 or later; it may be replaced by a compatible build.\n"
        "The LGPL-2.1 text is soundfile/_soundfile_data_COPYING. Where the wheel\n"
        "provides it, soundfile/licensing_license_notes.md names the source of\n"
        "each library inside libsndfile (mpg123, LAME, FLAC, Ogg, Vorbis, Opus).\n"
        "libsndfile source: https://github.com/libsndfile/libsndfile/releases\n"
    ),
    "freetype": (
        "This software uses FreeType (https://www.freetype.org/) under the\n"
        "FreeType License (FTL). FreeType appears in matplotlib, Pillow and Qt.\n"
        "Credit: Portions of this software are copyright (c) The FreeType Project\n"
        "(www.freetype.org). All rights reserved.\n"
    ),
    "qhull": (
        "Qhull (http://www.qhull.org/) is used by SciPy and matplotlib.\n"
        "Qhull is copyright (c) C.B. Barber and The Geometry Center.\n"
        "See the Qhull license shipped with SciPy / matplotlib.\n"
    ),
    "agg": (
        "Anti-Grain Geometry (AGG) is used by matplotlib.\n"
        "Copyright (c) 2002-2005 Maxim Shemanarev (McSeem).\n"
    ),
    "pyside6": (
        "This program uses Qt and PySide6 under the GNU Lesser General Public\n"
        "License version 3 (LGPL-3.0). Qt libraries are loaded as separate shared\n"
        "libraries and may be replaced by interface-compatible versions.\n\n"
        "The LGPL-3.0 text is in _texts/LGPL-3.0.txt and the GPL-3.0 text it\n"
        "incorporates is in _texts/GPL-3.0.txt.\n\n"
        "Qt source: https://download.qt.io/official_releases/qt/\n"
        "PySide6 source: https://code.qt.io/cgit/pyside/pyside-setup.git/\n"
        "LGPL-3.0: https://www.gnu.org/licenses/lgpl-3.0.html\n"
        "GPL-3.0: https://www.gnu.org/licenses/gpl-3.0.html\n"
    ),
    "ttconv": (
        "matplotlib's historical ttconv TrueType converter is not present in\n"
        "matplotlib 3.10 and later (fonttools is used instead). ReverbScope requires\n"
        "matplotlib>=3.10, so ttconv is not bundled. Status: resolved.\n"
    ),
}


def _installed(name: str) -> bool:
    try:
        distribution(name)
    except PackageNotFoundError:
        return False
    return True


def _license_files(name: str) -> list[tuple[str, bytes]]:
    try:
        dist = distribution(name)
    except PackageNotFoundError:
        return []
    found: list[tuple[str, bytes]] = []
    seen: set[str] = set()
    for file in dist.files or []:
        upper = file.name.upper()
        if ".dist-info" not in str(file):
            continue
        if not any(token in upper for token in ("LICENSE", "LICENCE", "COPYING", "NOTICE")):
            continue
        stored = str(file).replace("/", "_")
        if stored in seen:
            continue
        try:
            found.append((stored, Path(file.locate()).read_bytes()))
        except OSError:
            continue
        seen.add(stored)
    return found


def _package_license_files(name: str) -> tuple[list[tuple[str, bytes]], list[str]]:
    """``PACKAGE_LICENSE_FILES`` of ``name`` and the ones that are missing.

    A file counts as missing only when the wheel bundles the library it
    covers (``BUNDLED_LIBRARY_MARKERS``); a build against a system library
    carries neither.
    """
    try:
        dist = distribution(name)
    except PackageNotFoundError:
        return [], []
    files = {str(file): file for file in dist.files or []}
    marker = BUNDLED_LIBRARY_MARKERS.get(name)
    bundled = marker is not None and any(path.startswith(marker) for path in files)
    found: list[tuple[str, bytes]] = []
    missing: list[str] = []
    for wanted, required in PACKAGE_LICENSE_FILES.get(name, ()):
        file = files.get(wanted)
        try:
            if file is None:
                raise OSError(wanted)
            found.append((wanted.replace("/", "_"), Path(file.locate()).read_bytes()))
        except OSError:
            if bundled and required:
                missing.append(f"{name}:{wanted}")
    return found, missing


def build(out: Path, *, texts_dir: Path = TEXTS_DIR, terminal: bool = False) -> list[str]:
    """Write the bundle and return the names of unresolved items.

    Unresolved items are required packages without a license file and, when
    PySide6 is installed, missing LGPL / GPL texts (reported as ``text:<name>``).
    ``terminal`` writes the Terminal Edition's bundle: no Qt, no matplotlib.
    """
    out.mkdir(parents=True, exist_ok=True)
    unresolved: list[str] = []
    for name in TERMINAL_REQUIRED if terminal else REQUIRED:
        files = _license_files(name)
        if not files:
            unresolved.append(name)
            continue
        extra, missing = _package_license_files(name)
        unresolved.extend(missing)
        dest = out / name
        dest.mkdir(exist_ok=True)
        for filename, data in [*files, *extra]:
            (dest / filename).write_bytes(data)
    qt_installed = False
    for name in () if terminal else OPTIONAL:
        files = _license_files(name)
        dest = out / name.replace(" ", "_")
        dest.mkdir(exist_ok=True)
        for filename, data in files:
            (dest / filename).write_bytes(data)
        if name.lower().startswith("pyside") or name == "shiboken6":
            (dest / "LGPL-NOTICE.txt").write_text(KNOWN_NOTICES["pyside6"], encoding="utf-8")
            qt_installed = qt_installed or _installed(name)
    texts = out / "_texts"
    texts.mkdir(exist_ok=True)
    for filename in TEXTS:
        if terminal and filename in QT_TEXTS:
            continue
        src = texts_dir / filename
        if src.is_file():
            (texts / filename).write_bytes(src.read_bytes())
        elif filename in QT_TEXTS and qt_installed:
            unresolved.append(f"text:{filename}")
    extras = out / "_notices"
    extras.mkdir(exist_ok=True)
    for key, text in KNOWN_NOTICES.items():
        if terminal and key in GUI_NOTICES:
            continue
        (extras / f"{key}.txt").write_text(text, encoding="utf-8")
    root = Path(__file__).resolve().parents[1]
    for name in ("LICENSE", "NOTICE"):
        src = root / name
        if src.is_file():
            (out / name).write_bytes(src.read_bytes())
    summary = out / "INDEX.txt"
    qt_line = "PySide6 installed; LGPL-3.0 and GPL-3.0 texts in _texts/"
    if terminal:
        qt_line = "not included (Terminal Edition)"
    elif not qt_installed:
        qt_line = "PySide6 not installed"
    lines = [
        "ReverbScope third-party license bundle",
        f"unresolved: {', '.join(unresolved) if unresolved else 'none'}",
        f"qt: {qt_line}",
        "ttconv: resolved (not present in matplotlib>=3.10)",
        "ASIO: Windows sounddevice ASIO DLLs must be stripped by check_bundle_contents.py",
    ]
    summary.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return unresolved


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True, help="THIRD_PARTY_LICENSES directory")
    parser.add_argument(
        "--terminal",
        action="store_true",
        help="the Terminal Edition's bundle (no Qt, no matplotlib)",
    )
    args = parser.parse_args(argv)
    unresolved = build(args.out, terminal=args.terminal)
    if unresolved:
        print("unresolved packages: " + ", ".join(unresolved), file=sys.stderr)
        return 1
    print(f"wrote {args.out} (no unresolved packages)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
