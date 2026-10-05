"""A project is an index of session folders for one room (SHOULD in v1.0)."""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Any

from reverbscope.errors import SessionError
from reverbscope.models.loadutil import drop_unknown, read_schema_version

PROJECT_SCHEMA_VERSION = 1


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
        dirs = payload.get("session_dirs") or ()
        return cls(label=str(payload.get("label", "")), session_dirs=tuple(str(p) for p in dirs))


@dataclass
class Project:
    """One room, several positions. Sessions remain standalone folders."""

    name: str = ""
    notes: str = ""
    positions: tuple[PositionEntry, ...] = ()
    schema_version: int = PROJECT_SCHEMA_VERSION
    reverbscope_version: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "name": self.name,
            "notes": self.notes,
            "positions": [p.to_dict() for p in self.positions],
            "reverbscope_version": self.reverbscope_version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Project:
        if not isinstance(data, dict):
            raise SessionError("project data must be a JSON object")
        version = read_schema_version(data, PROJECT_SCHEMA_VERSION, "project")
        payload = drop_unknown(data, {f.name for f in fields(cls)}, kind="project")
        positions = tuple(
            PositionEntry.from_dict(item)
            if isinstance(item, dict)
            else PositionEntry(label=str(item))
            for item in payload.get("positions") or ()
        )
        return cls(
            name=str(payload.get("name", "")),
            notes=str(payload.get("notes", "")),
            positions=positions,
            schema_version=version,
            reverbscope_version=str(payload.get("reverbscope_version", "")),
        )
