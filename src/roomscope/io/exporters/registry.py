"""Exporter registry: built-in CSV plus ``roomscope.exporters`` entry points."""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from roomscope.errors import ConfigurationError
from roomscope.i18n import _
from roomscope.models.result import AnalysisResult

log = logging.getLogger("roomscope.exporters")


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
    from roomscope.io.exporters.csv import CsvExporter

    return {"csv": CsvExporter()}


def _entry_points() -> dict[str, ResultExporter]:
    found: dict[str, ResultExporter] = {}
    try:
        from importlib.metadata import entry_points
    except ImportError:  # pragma: no cover
        return found
    selected = entry_points().select(group="roomscope.exporters")
    for item in selected:
        if item.name in found or item.name in _builtin():
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
