"""Exporter registry: built-in CSV plus ``reverbscope.exporters`` entry points."""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from reverbscope.errors import ConfigurationError
from reverbscope.i18n import _
from reverbscope.models.result import AnalysisResult

if TYPE_CHECKING:
    from importlib.metadata import EntryPoint

log = logging.getLogger("reverbscope.exporters")


class ResultExporter(Protocol):
    name: str

    def export(self, result: AnalysisResult, directory: Path) -> list[Path]: ...


class _CallableExporter:
    def __init__(self, name: str, func: Callable[[AnalysisResult, Path], list[Path]]) -> None:
        self.name = name
        self._func = func

    def export(self, result: AnalysisResult, directory: Path) -> list[Path]:
        return self._func(result, directory)


def _builtin() -> dict[str, ResultExporter]:
    from reverbscope.io.exporters.csv import CsvExporter

    return {"csv": CsvExporter()}


def _declares_builtin(item: EntryPoint, exporter: ResultExporter) -> bool:
    """``item`` names the class of the built-in ``exporter``.

    ReverbScope's own ``pyproject.toml`` registers the built-in CSV exporter
    under ``reverbscope.exporters`` as well (the documented extension point),
    so every install sees it there; it is not a third-party exporter.
    """
    cls = type(exporter)
    return (item.module, item.attr) == (cls.__module__, cls.__qualname__)


def _entry_points() -> dict[str, ResultExporter]:
    found: dict[str, ResultExporter] = {}
    try:
        from importlib.metadata import entry_points
    except ImportError:  # pragma: no cover
        return found
    selected = entry_points().select(group="reverbscope.exporters")
    builtin = _builtin()
    for item in selected:
        if item.name in builtin and _declares_builtin(item, builtin[item.name]):
            continue
        if item.name in found or item.name in builtin:
            log.warning("ignoring third-party exporter %r; name collides", item.name)
            continue
        try:
            loaded = item.load()
        except Exception as exc:
            log.warning("exporter %r failed to import: %s", item.name, exc)
            continue
        if callable(loaded) and not hasattr(loaded, "export"):
            found[item.name] = _CallableExporter(item.name, loaded)
        else:
            found[item.name] = loaded
    return found


def available_exporters() -> list[str]:
    return sorted({*_builtin(), *_entry_points()})


def get_exporter(name: str) -> ResultExporter:
    table = {**_entry_points(), **_builtin()}
    try:
        return table[name]
    except KeyError as exc:
        raise ConfigurationError(
            _("unknown exporter {name}; available: {available}").format(
                name=repr(name), available=available_exporters()
            )
        ) from exc
