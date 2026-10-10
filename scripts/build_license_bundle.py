"""Build THIRD_PARTY_LICENSES/ for a desktop bundle (ARCHITECTURE_V1.md §6.2).

Copies license files from installed distributions, adds the license texts
that the wheels omit (LGPL-3.0 and GPL-3.0 for Qt / PySide6, the PortAudio
license, the notices of the third-party code inside Qt) from
``packaging/licenses/``, copies the libsndfile LGPL-2.1 text and source notes
that soundfile keeps outside its metadata, adds short notices (libsndfile,
FreeType, Qhull, Agg) and the licence of the Python that builds the bundle,
and fails if a required package still has no license text or if PySide6 is
installed but the LGPL / GPL texts are missing. matplotlib's old ``ttconv``
module is treated as resolved: matplotlib 3.10+ (which ReverbScope requires)
no longer contains it.

``--frozen <bundle>`` (after PyInstaller) also covers the native libraries
that PyInstaller copied from the build machine or the Python installation
(GLib, OpenSSL, the C++ runtime, libpython ...): on Debian and Ubuntu each one
gets its package's copyright file and a pointer to the source package;
elsewhere the libraries that a Python installation brings get the notices in
``packaging/licenses/native/``. ``NATIVE.txt`` lists the notice of every
library, and any library without one is unresolved.
"""

from __future__ import annotations

import argparse
import filecmp
import functools
import importlib.util
import re
import shutil
import subprocess
import sys
import sysconfig
from importlib.metadata import PackageNotFoundError, distribution
from pathlib import Path
from types import ModuleType
from typing import NamedTuple

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
    # soundfile imports it at run time (DEPENDENCIES.md).
    "typing-extensions",
    # The desktop charts (GUI_2_ARCHITECTURE.md §9); pyqtgraph imports colorama
    # on every platform (pyqtgraph.util.cprint).
    "pyqtgraph",
    "colorama",
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
    "typing-extensions",
]
#: Notices that concern only the GUI's libraries.
GUI_NOTICES = ("freetype", "agg", "pyside6", "ttconv")

# Verbatim license texts kept in the repository because the wheels omit them
# (DEPENDENCIES.md §3-§4). Every bundle ships all of them; the LGPL / GPL
# texts are additionally *required* whenever PySide6 is installed.
TEXTS_DIR = Path(__file__).resolve().parents[1] / "packaging" / "licenses"
TEXTS = ("LGPL-3.0.txt", "GPL-3.0.txt", "PortAudio-LICENSE.txt")
QT_TEXTS = ("LGPL-3.0.txt", "GPL-3.0.txt")
#: The copyright notices of the third-party code inside Qt (PCRE2, HarfBuzz,
#: libpng, MD4C, ...), written by scripts/qt_third_party_notice.py.
QT_THIRD_PARTY = "qt-third-party.txt"
#: Native libraries that a Python installation brings along, by lower-case
#: file-name prefix, for builds where the system's package database cannot
#: name them (Windows, macOS, a Python installed outside the system's
#: packages). "python" is the interpreter's own licence; the others are files
#: in packaging/licenses/native/.
NATIVE_NOTICES = (
    (("libpython3", "python3"), "python"),
    (("libssl", "libcrypto"), "openssl"),
    (("libffi",), "libffi"),
    (("liblzma",), "xz"),
    (("vcruntime140", "msvcp140", "concrt140", "ucrtbase", "api-ms-win-"), "msvc-runtime"),
)
PYTHON_NOTICE = "_notices/python.txt"
_COMMON_LICENSE = re.compile(r"/usr/share/common-licenses/([A-Za-z0-9.+_-]+)")

# License files a wheel keeps outside its .dist-info folder. soundfile's
# wheels bundle libsndfile (LGPL-2.1-or-later, text in _soundfile_data/COPYING)
# and list the source of libsndfile's own components (mpg123, LAME, FLAC, Ogg,
# Vorbis, Opus) in licensing/license_notes.md (DEPENDENCIES.md §3).
# (path, required when the library is bundled)
# pyqtgraph's colour-map data is not its own: the viridis and inferno tables
# the desktop bundle keeps (packaging/pyinstaller_filters.py) are CC0, whose
# legal code sits next to them in the package.
PACKAGE_LICENSE_FILES = {
    "soundfile": (("_soundfile_data/COPYING", True), ("licensing/license_notes.md", False)),
    "pyqtgraph": (
        (
            "pyqtgraph/colors/maps/CC0 legal code - applies to virids, magma, plasma, "
            "inferno and cividis.txt",
            False,
        ),
    ),
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


def python_license() -> bytes | None:
    """The licence file of the Python that builds the bundle.

    Every bundle carries that interpreter: its standard library and
    libpython (python3.dll on Windows).
    """
    stdlib = Path(sysconfig.get_path("stdlib"))
    for candidate in (stdlib / "LICENSE.txt", Path(sys.base_prefix) / "LICENSE.txt"):
        if candidate.is_file():
            return candidate.read_bytes()
    return None


class SystemPackage(NamedTuple):
    """The Debian or Ubuntu package that installed a library on the build machine."""

    name: str
    version: str
    source: str
    source_version: str

    @property
    def copyright(self) -> Path:
        return Path("/usr/share/doc") / self.name / "copyright"


def _output(*argv: str) -> str | None:
    try:
        done = subprocess.run(argv, capture_output=True, text=True, check=False)
    except OSError:
        return None
    return done.stdout if done.returncode == 0 else None


@functools.cache
def _ldconfig() -> str:
    return _output(shutil.which("ldconfig") or "/sbin/ldconfig", "-p") or ""


def _system_copies(name: str) -> list[Path]:
    """The build machine's libraries called ``name`` (ldconfig, then the usual folders)."""
    found: list[Path] = []
    for line in _ldconfig().splitlines():
        head, arrow, path = line.partition("=>")
        if arrow and head.split()[:1] == [name]:
            found.append(Path(path.strip()))
    multiarch = sysconfig.get_config_var("MULTIARCH") or ""
    folders = [Path(base, multiarch) for base in ("/lib", "/usr/lib") if multiarch]
    folders += [Path(base) for base in ("/lib64", "/usr/lib64", "/lib", "/usr/lib")]
    found += [folder / name for folder in folders if (folder / name).is_file()]
    return list(dict.fromkeys(found))


def system_package(library: Path) -> SystemPackage | None:
    """The package that installed the build machine's copy of ``library``.

    Only a byte-identical copy counts, so the libpython of a separately
    installed Python is not credited to the system's python package. None
    without dpkg (any system other than Debian and its derivatives).
    """
    if shutil.which("dpkg-query") is None:
        return None
    for copy in _system_copies(library.name):
        if not filecmp.cmp(copy, library, shallow=False):
            continue
        # With merged /usr, dpkg knows a library under /usr/lib or under /lib.
        paths = [str(copy.resolve()), str(copy)]
        paths += [f"/usr{path}" for path in paths if path.startswith("/lib")]
        paths += [path.removeprefix("/usr") for path in paths if path.startswith("/usr/lib")]
        for path in dict.fromkeys(paths):
            owners = _output("dpkg-query", "-S", path) or ""
            rows = owners.splitlines()
            line = next((row for row in rows if not row.startswith("diversion")), "")
            if ": " not in line:
                continue
            qualified = line.split(": ", 1)[0].split(",")[0].strip()
            fields = _output(
                "dpkg-query",
                "-W",
                "-f",
                "${Version}\t${source:Package}\t${source:Version}",
                qualified,
            )
            if not fields:
                continue
            version, source, source_version = ([*fields.strip().split("\t"), "", ""])[:3]
            return SystemPackage(
                qualified.split(":", 1)[0], version, source or qualified, source_version or version
            )
    return None


def _source_url(package: SystemPackage) -> str:
    try:
        release = Path("/etc/os-release").read_text(encoding="utf-8")
    except OSError:
        release = ""
    distro = next(
        (
            line.split("=", 1)[1].strip('"')
            for line in release.splitlines()
            if line.startswith("ID=")
        ),
        "",
    )
    if distro == "ubuntu":
        return f"https://launchpad.net/ubuntu/+source/{package.source}/{package.source_version}"
    if distro == "debian":
        return f"https://sources.debian.org/src/{package.source}/{package.source_version}/"
    return f"apt-get source {package.source}={package.source_version}"


def _write_package_notice(folder: Path, package: SystemPackage, libraries: list[str]) -> bool:
    try:
        text = package.copyright.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    common = folder / "common-licenses"
    for reference in sorted(set(_COMMON_LICENSE.findall(text))):
        source = Path("/usr/share/common-licenses") / reference.rstrip(".")
        if source.is_file():
            common.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, common / source.name)
    these, them = ("these libraries", "them") if len(libraries) > 1 else ("this library", "it")
    header = (
        f"{', '.join(sorted(libraries))}\n\n"
        f"PyInstaller copied {these} unchanged from the build machine, where the\n"
        f"package {package.name} {package.version} installed {them}.\n"
        f"Source code: source package {package.source} {package.source_version},\n"
        f"{_source_url(package)}\n"
        "The package's copyright file follows. The licence texts it refers to in\n"
        "/usr/share/common-licenses are in common-licenses/ next to this file.\n\n"
    )
    (folder / f"{package.name}.txt").write_text(header + text, encoding="utf-8")
    return True


def _gate() -> ModuleType:
    """scripts/check_bundle_contents.py, which decides what a native library is."""
    path = Path(__file__).with_name("check_bundle_contents.py")
    spec = importlib.util.spec_from_file_location("check_bundle_contents", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def native_notices(out: Path, frozen: Path) -> tuple[dict[str, str], list[str]]:
    """Write a notice for each native library of ``frozen`` that no package ships.

    Returns each library's notice (a path inside ``out``) and the libraries
    left without one (``native:<file name>``).
    """
    folder = out / "_notices" / "native"
    folder.mkdir(parents=True, exist_ok=True)
    notices: dict[str, str] = {}
    unresolved: list[str] = []
    packages: dict[str, tuple[SystemPackage, list[str]]] = {}
    for library in _gate().loose_native_libraries(frozen):
        package = system_package(library)
        if package is not None:
            packages.setdefault(package.name, (package, []))[1].append(library.name)
            continue
        lowered = library.name.lower()
        key = next((key for prefixes, key in NATIVE_NOTICES if lowered.startswith(prefixes)), None)
        text = TEXTS_DIR / "native" / f"{key}.txt"
        if key == "python":
            notices[library.name] = PYTHON_NOTICE
        elif key is not None and text.is_file():
            shutil.copyfile(text, folder / text.name)
            notices[library.name] = f"_notices/native/{text.name}"
        else:
            unresolved.append(f"native:{library.name}")
    for package, libraries in packages.values():
        if _write_package_notice(folder, package, libraries):
            notices.update(dict.fromkeys(libraries, f"_notices/native/{package.name}.txt"))
        else:
            unresolved += [f"native:{name}" for name in libraries]
    return notices, unresolved


def package_binary_notices(out: Path, frozen: Path) -> tuple[dict[str, str], list[str]]:
    """Write the notice of each binary a wheel keeps in its package folder.

    ``check_bundle_contents.PACKAGE_BINARY_NOTICES`` names them (PySide6's
    ``opengl32sw.dll`` on Windows). Returns each file's notice (a path inside
    ``out``) and the files left without one (``native:<file name>``).
    """
    gate = _gate()
    notices: dict[str, str] = {}
    unresolved: list[str] = []
    for path in gate.package_binaries(frozen):
        notice = gate.PACKAGE_BINARY_NOTICES[path.name.lower()]
        source = TEXTS_DIR / "native" / Path(notice).name
        if not source.is_file():
            unresolved.append(f"native:{path.name}")
            continue
        target = out / notice
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        notices[path.name] = notice
    return notices, unresolved


def build(
    out: Path,
    *,
    texts_dir: Path = TEXTS_DIR,
    terminal: bool = False,
    frozen: Path | None = None,
) -> list[str]:
    """Write the bundle and return the names of unresolved items.

    Unresolved items are required packages without a license file, the
    Python licence when it cannot be found, when PySide6 is installed missing
    LGPL / GPL texts and Qt notices (reported as ``text:<name>``) and, with
    ``frozen``, native libraries without a notice (``native:<name>``).
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
    if not terminal:
        qt_notice = texts_dir / QT_THIRD_PARTY
        if qt_notice.is_file():
            (extras / QT_THIRD_PARTY).write_bytes(qt_notice.read_bytes())
        elif qt_installed:
            unresolved.append(f"text:{QT_THIRD_PARTY}")
    python = python_license()
    if python is None:
        unresolved.append("text:Python LICENSE.txt")
    else:
        (out / PYTHON_NOTICE).write_bytes(python)
    native: dict[str, str] | None = None
    if frozen is not None:
        native, missing_native = native_notices(out, frozen)
        unresolved.extend(missing_native)
        lines = [
            "Native libraries in this bundle that no Python package ships, each with",
            "the notice that covers it (scripts/build_license_bundle.py --frozen).",
            "",
            *(f"{name}\t{notice}" for name, notice in sorted(native.items())),
        ]
        (out / _gate().NATIVE_INDEX).write_text("\n".join(lines) + "\n", encoding="utf-8")
        packaged, missing_packaged = package_binary_notices(out, frozen)
        unresolved.extend(missing_packaged)
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
        "native: not scanned (pass --frozen <bundle> after PyInstaller)"
        if native is None
        else f"native: {len(native)} libraries outside Python packages, notices in NATIVE.txt",
        "package binaries: not scanned (pass --frozen <bundle> after PyInstaller)"
        if native is None
        else "package binaries: "
        + (", ".join(f"{name} -> {notice}" for name, notice in sorted(packaged.items())) or "none"),
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
    parser.add_argument(
        "--frozen",
        type=Path,
        help="the PyInstaller output folder: also cover its native libraries",
    )
    args = parser.parse_args(argv)
    unresolved = build(args.out, terminal=args.terminal, frozen=args.frozen)
    if unresolved:
        print("unresolved packages: " + ", ".join(unresolved), file=sys.stderr)
        return 1
    print(f"wrote {args.out} (no unresolved packages)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
