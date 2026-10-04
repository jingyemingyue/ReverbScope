"""A project is an index of session folders for one room (SHOULD in v1.0)."""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Any

from roomscope.errors import SessionError
from roomscope.i18n import _
from roomscope.models.loadutil import drop_unknown, read_schema_version, record_name

PROJECT_SCHEMA_VERSION = 1


def _list(value: Any, kind: str, name: str) -> list[Any]:
    """A JSON array from a project file. A string would otherwise be read as
    one folder per character, and a number would raise ``TypeError``."""
    if value is None:
        return []
    if not isinstance(value, list):
        raise SessionError(
            _("invalid {kind} in file: {error}").format(
                kind=record_name(kind), error=_("{field} must be a list").format(field=name)
            )
        )
    return value


@dataclass(frozen=True)
class PositionEntry:
    """One labelled position that points at one or more session directories."""

    label: str
    session_dirs: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {"label": self.label, "session_dirs": list(self.session_dirs)}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PositionEntry:
        payload = drop_unknown(data, {f.name for f in fields(cls)}, kind="position entry")
        dirs = _list(payload.get("session_dirs"), "position entry", "session_dirs")
        return cls(label=str(payload.get("label", "")), session_dirs=tuple(str(p) for p in dirs))


@dataclass
class Project:
    """One room, several positions. Sessions remain standalone folders."""

    name: str = ""
    notes: str = ""
    positions: tuple[PositionEntry, ...] = ()
    schema_version: int = PROJECT_SCHEMA_VERSION
    roomscope_version: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "name": self.name,
            "notes": self.notes,
            "positions": [p.to_dict() for p in self.positions],
            "roomscope_version": self.roomscope_version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Project:
        if not isinstance(data, dict):
            raise SessionError(
                _("{kind} must be a JSON object").format(kind=record_name("project"))
            )
        version = read_schema_version(data, PROJECT_SCHEMA_VERSION, "project")
        payload = drop_unknown(data, {f.name for f in fields(cls)}, kind="project")
        positions = tuple(
            PositionEntry.from_dict(item)
            if isinstance(item, dict)
            else PositionEntry(label=str(item))
            for item in _list(payload.get("positions"), "project", "positions")
        )
        return cls(
            name=str(payload.get("name", "")),
            notes=str(payload.get("notes", "")),
            positions=positions,
            schema_version=version,
            roomscope_version=str(payload.get("roomscope_version", "")),
        )
