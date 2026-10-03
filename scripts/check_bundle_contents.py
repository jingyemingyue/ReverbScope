"""Fail a bundle that contains GPL-only Qt modules or ASIO DLLs.

``--terminal`` also fails a Terminal Edition bundle that contains any file of
the GUI: PySide6, shiboken6, a Qt library, matplotlib or ``roomscope/ui``.

ARCHITECTURE_V1.md §6.2: a frozen tree must not ship GPL-only Qt modules or
``*asio*.dll``. PySide6 Essentials wheels still contain ``.pyi`` stubs, a
few QML / input plugins and versioned ``Qt/lib`` libraries whose names match
the ban list (``libQt6QuickTimeline.so.6``, the virtual-keyboard QML
plugins); those are ignored only in ``--installed-essentials`` mode, which
instead fails if Addons is installed or a real GPL extension module is
present. ``--strip`` deletes the offending files from a frozen tree before
the gate is evaluated; the release workflow runs it once with ``--strip``
and once without.

Library file names carry the Qt major version (``Qt6QuickTimeline.dll``,
``libQt6QuickTimeline.so.6``) while the module names do not
(``QtQuickTimeline``), so names are compared with ``qt6`` folded to ``qt``.

QML plugins do not carry the module name at all
(``qml/QtQuick/VirtualKeyboard/Plugins/Pinyin/libqtvkbpinyinplugin.so``), so a
frozen tree is also checked by directory: every file below a GPL-only QML
module directory is an offender (and is removed by ``--strip``). RoomScope has
no QML UI and PyInstaller collects QML only when something imports QtQml, so a
frozen tree that still contains any file below a ``qml/`` directory fails the
gate as well; ``--strip`` does not hide that, because it means the import
graph changed.
"""

from __future__ import annotations

import argparse
import sys
from importlib.metadata import PackageNotFoundError, distribution
from pathlib import Path

GPL_ONLY_QT = (
    "QtCharts",
    "QtDataVisualization",
    "QtGraphs",
    "QtLottie",
    "QtQuickTimeline",
    "QtVirtualKeyboard",
    "QtQuick3D",
    "QtHttpServer",
    "QtNetworkAuth",
    "QtShaderTools",
)

# QML module directories of GPL-only Qt modules, relative to a ``qml/``
# directory (``Qt/qml`` in a wheel, ``Contents/Resources/qml`` or
# ``_internal/PySide6/Qt/qml`` in a frozen tree), and the module they belong to.
GPL_ONLY_QML_DIRS: dict[tuple[str, ...], str] = {
    ("QtCharts",): "QtCharts",
    ("QtDataVisualization",): "QtDataVisualization",
    ("QtGraphs",): "QtGraphs",
    ("QtQuick3D",): "QtQuick3D",
    ("QtQuick", "Timeline"): "QtQuickTimeline",
    ("QtQuick", "VirtualKeyboard"): "QtVirtualKeyboard",
    ("Qt", "labs", "lottieqt"): "QtLottie",
}

_BINARY_SUFFIXES = {".so", ".dll", ".dylib", ".pyd"}

# LGPL Essentials modules that a frozen app may ship. The gate bans GPL-only
# modules, not every Qt library beyond QtCore/QtGui/QtWidgets.
ALLOWED_HINT = "QtCore, QtGui, QtWidgets, QtDBus (Linux) and other PySide6 Essentials LGPL modules"


def _is_binary(path: Path) -> bool:
    suffix = path.suffix.lower()
    if suffix in _BINARY_SUFFIXES:
        return True
    lowered = path.name.lower()
    # ``QtCharts.abi3.so`` uses suffix ``.so`` already; keep the extra check
    # for names like ``foo.abi3.so`` on case-insensitive volumes.
    if lowered.endswith((".abi3.so", ".abi3.pyd")):
        return True
    # Versioned shared objects as shipped on Linux: ``libQt6Charts.so.6``,
    # ``libQt6Charts.so.6.11.2``; ``path.suffix`` sees only ``.6`` / ``.2``.
    if ".so." in lowered or ".dylib." in lowered:
        return True
    # macOS framework binaries carry no suffix at all:
    # ``QtCharts.framework/Versions/A/QtCharts``.
    return not path.suffix and any(part.lower().endswith(".framework") for part in path.parts)


def _name_hits_gpl(name: str) -> str | None:
    lowered = name.lower().replace("qt6", "qt")
    for banned in GPL_ONLY_QT:
        if banned.lower() in lowered:
            return banned
    return None


def _framework_hit(path: Path) -> str | None:
    for part in path.parts:
        if part.lower().endswith(".framework"):
            hit = _name_hits_gpl(part)
            if hit is not None:
                return hit
    return None


def _relative_parts(path: Path, root: Path) -> tuple[str, ...]:
    try:
        return path.relative_to(root).parts
    except ValueError:
        return path.parts


def _qml_dir_hit(path: Path, root: Path) -> str | None:
    """Return the GPL-only module whose QML directory contains ``path``."""
    parts = [part.lower() for part in _relative_parts(path, root)]
    for index, part in enumerate(parts):
        if part != "qml":
            continue
        below = parts[index + 1 :]
        for prefix, module in GPL_ONLY_QML_DIRS.items():
            wanted = [item.lower() for item in prefix]
            # ``below`` ends with the file name, so the file must sit inside
            # the module directory, not be named like it.
            if len(below) > len(wanted) and below[: len(wanted)] == wanted:
                return module
    return None


def qml_trees(root: Path) -> dict[Path, int]:
    """``qml/`` directories of a frozen tree that hold files, with their file counts.

    RoomScope has no QML UI; PyInstaller collects a QML tree only when
    something imports QtQml. Only the outermost ``qml`` directory of each
    file is counted, so one collected tree is reported once.
    """
    trees: dict[Path, int] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        parts = _relative_parts(path, root)
        # The file's own name is not a directory; only its parents count.
        for index, part in enumerate(parts[:-1]):
            if part.lower() == "qml":
                tree = root.joinpath(*parts[: index + 1])
                trees[tree] = trees.get(tree, 0) + 1
                break
    return trees


def _under_essentials_qt_tree(path: Path, root: Path) -> bool:
    """Stock wheel content that Essentials ships and RoomScope never imports."""
    try:
        relative = path.relative_to(root).as_posix().lower()
    except ValueError:
        relative = path.as_posix().lower()
    marked = f"/{relative}"
    return "/qt/plugins/" in marked or "/qt/qml/" in marked or "/qt/lib/" in marked


def _is_asio_dll(path: Path) -> bool:
    return path.suffix.lower() == ".dll" and "asio" in path.name.lower()


def offending(root: Path, *, installed_essentials: bool = False) -> list[tuple[Path, str]]:
    """Return ``(path, reason)`` for every file the gate objects to."""
    found: list[tuple[Path, str]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if _is_asio_dll(path):
            found.append((path, "ASIO DLL present"))
        if path.suffix.lower() == ".pyi":
            continue
        banned = _name_hits_gpl(path.name)
        if banned is None and not path.suffix:
            # A macOS framework directory carries the module name; the files
            # inside it (the binary, Resources/…) may not.
            banned = _framework_hit(path)
        if banned is None and not installed_essentials:
            # QML plugins and their qmldir / .qml files are named after the
            # plugin, not the module (``libqtvkbpinyinplugin.so``).
            qml_module = _qml_dir_hit(path, root)
            if qml_module is not None:
                found.append((path, f"GPL-only Qt QML module present ({qml_module})"))
                continue
        if banned is None:
            continue
        if installed_essentials and not _is_binary(path):
            continue
        if installed_essentials and _under_essentials_qt_tree(path, root):
            continue
        if not installed_essentials and not _is_binary(path) and path.suffix.lower() != ".py":
            continue
        found.append((path, f"GPL-only Qt module present ({banned})"))
    return found


def strip(root: Path) -> list[Path]:
    """Delete every offending file from a frozen tree and return what was removed."""
    removed: list[Path] = []
    for path, _reason in offending(root):
        if path.is_file():
            path.unlink()
            removed.append(path)
    # Remove the directories that stripping emptied (framework / QML module
    # directories), walking up from each removed file; never touch ``root``.
    resolved_root = root.resolve()
    parents = {parent for path in removed for parent in path.parents}
    for directory in sorted(parents, key=lambda item: len(item.parts), reverse=True):
        if directory.resolve() == resolved_root or resolved_root not in directory.resolve().parents:
            continue
        if directory.is_dir() and not any(directory.iterdir()):
            directory.rmdir()
    return removed


#: What the Terminal Edition must not contain: the GUI package, Qt and the
#: plotting stack. Matched against every path below the bundle except its
#: license texts, case-insensitively.
TERMINAL_FORBIDDEN = (
    ("pyside6", "PySide6"),
    ("shiboken6", "shiboken6"),
    ("matplotlib", "matplotlib"),
    ("roomscope/ui/", "roomscope.ui (the GUI)"),
)


def _is_qt_library(name: str) -> bool:
    """``libQt6Core.so.6``, ``Qt6Core.dll``, ``QtCore.framework``, ``QtWidgets.abi3.so``."""
    lowered = name.lower()
    stem = lowered[3:] if lowered.startswith("lib") else lowered
    return stem.startswith(("qt6", "qt5")) or (
        stem.startswith("qt") and (".framework" in stem or ".abi3." in stem)
    )


def gui_files(root: Path) -> list[tuple[Path, str]]:
    """Files of the GUI in a tree that must be the Terminal Edition."""
    found: list[tuple[Path, str]] = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if relative.split("/", 1)[0] == "THIRD_PARTY_LICENSES" or not path.is_file():
            continue
        lowered = f"{relative.lower()}/"
        hit = next((label for token, label in TERMINAL_FORBIDDEN if token in lowered), None)
        # Inside the bundle only: a folder above it ("Qt6Projects") is no Qt library.
        if hit is None and any(_is_qt_library(part) for part in path.relative_to(root).parts):
            hit = "a Qt library"
        if hit is not None:
            found.append((path, hit))
    return found


def check(
    root: Path,
    *,
    require_licenses: bool = False,
    installed_essentials: bool = False,
    terminal: bool = False,
) -> list[str]:
    errors: list[str] = []
    if not root.is_dir():
        return [f"not a directory: {root}"]
    if installed_essentials:
        try:
            distribution("PySide6_Addons")
        except PackageNotFoundError:
            pass
        else:
            errors.append("PySide6_Addons is installed; RoomScope must use PySide6_Essentials only")
    errors.extend(
        f"{reason}: {path}"
        for path, reason in offending(root, installed_essentials=installed_essentials)
    )
    if not installed_essentials:
        errors.extend(
            f"QML tree present ({count} files; RoomScope has no QML UI, so something "
            f"imported QtQml): {tree}"
            for tree, count in qml_trees(root).items()
        )
    if terminal:
        errors.extend(f"Terminal Edition contains {what}: {path}" for path, what in gui_files(root))
    if require_licenses:
        licenses = root / "THIRD_PARTY_LICENSES"
        if not licenses.is_dir():
            errors.append("THIRD_PARTY_LICENSES/ is missing")
        else:
            index = licenses / "INDEX.txt"
            if not index.is_file():
                errors.append("THIRD_PARTY_LICENSES/INDEX.txt is missing")
            elif "unresolved: none" not in index.read_text(encoding="utf-8"):
                errors.append("THIRD_PARTY_LICENSES/INDEX.txt lists unresolved packages")
            texts = licenses / "_texts"
            wanted = ("PortAudio-LICENSE.txt",)
            if not terminal:
                wanted = ("LGPL-3.0.txt", "GPL-3.0.txt", *wanted)
            for filename in wanted:
                if not (texts / filename).is_file():
                    errors.append(f"THIRD_PARTY_LICENSES/_texts/{filename} is missing")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True, help="bundle or site-packages tree")
    parser.add_argument(
        "--require-licenses",
        action="store_true",
        help="require THIRD_PARTY_LICENSES/ with no unresolved packages",
    )
    parser.add_argument(
        "--installed-essentials",
        action="store_true",
        help="gate a PySide6_Essentials install (ignore wheel stubs and stock plugins)",
    )
    parser.add_argument(
        "--strip",
        action="store_true",
        help="delete GPL-only Qt modules and ASIO DLLs from a frozen tree, then gate it",
    )
    parser.add_argument(
        "--terminal",
        action="store_true",
        help="the Terminal Edition: fail on any PySide6, Qt, matplotlib or GUI file",
    )
    args = parser.parse_args(argv)
    if args.strip:
        if args.installed_essentials:
            parser.error("--strip applies to a frozen tree, not to --installed-essentials")
        for path in strip(args.root):
            print(f"stripped {path}")
    errors = check(
        args.root,
        require_licenses=args.require_licenses,
        installed_essentials=args.installed_essentials,
        terminal=args.terminal,
    )
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    if args.terminal:
        print(f"Terminal Edition gate passed for {args.root} (no PySide6, Qt, matplotlib or GUI)")
    else:
        print(f"bundle gate passed for {args.root} ({ALLOWED_HINT})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
