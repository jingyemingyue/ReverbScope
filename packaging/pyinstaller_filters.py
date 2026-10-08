"""Filters that packaging/reverbscope.spec applies to PyInstaller's binaries.

They live outside the spec so that tests can run them without PyInstaller.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence

#: An ``Analysis.binaries`` entry: (path in the bundle, source path, type).
Entry = tuple[str, str, str]


def _top_level(entry: Entry) -> bool:
    # PyInstaller puts the build machine's libraries at the top of the bundle;
    # a wheel's own libraries keep their package folder (PySide6/Qt/lib/...).
    return "/" not in entry[0].replace("\\", "/")


def without_plugin(
    binaries: Sequence[Entry], plugin: str, loads: Callable[[str], Iterable[str]]
) -> list[Entry]:
    """``binaries`` without ``plugin`` and the libraries that only it loads.

    ``plugin`` is the end of a bundle path (``platformthemes/libqgtk3.so``).
    ``loads`` returns the file names of every library a binary loads,
    directly or through other libraries, as ``ldd`` lists them. A library
    goes only when it sits at the top of the bundle and nothing that stays
    loads it, so Qt keeps the GLib that QtCore links.
    """
    gone = [entry for entry in binaries if entry[0].replace("\\", "/").endswith(plugin)]
    if not gone:
        return list(binaries)
    kept = [entry for entry in binaries if entry not in gone]
    candidates = {name for entry in gone for name in loads(entry[1])}
    staying = [entry for entry in kept if not (_top_level(entry) and entry[0] in candidates)]
    needed = {name for entry in staying for name in loads(entry[1])}
    unused = candidates - needed
    return [entry for entry in kept if not (_top_level(entry) and entry[0] in unused)]
