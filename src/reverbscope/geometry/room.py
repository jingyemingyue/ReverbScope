"""The room geometry the user entered: ``room-geometry.json``.

The file holds only what the user typed or imported (GUI_2_ARCHITECTURE.md
§6.4): the room box, the loudspeaker, the microphone of each position, an
optional scan reference and free notes. Measurements never write to it, so a
value read from it is always an *entered* value, never a measured one.

Coordinates are metres with the origin at one floor corner of the box: x
along the length, y along the width, z up. Faces are named by coordinate
(``x0`` is the face at x = 0, ``z1`` the ceiling), never "front wall": the
program does not know which way the user faces.

Writes are atomic, unknown top-level keys are kept, and a file written by a
newer ReverbScope (a higher ``schema_version``) is read but never
overwritten, so an older copy of the program cannot drop what it does not
understand.
"""

from __future__ import annotations

import copy
import json
import logging
import math
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path
from types import MappingProxyType
from typing import Any

from reverbscope.errors import ReverbScopeError, SessionError
from reverbscope.i18n import _
from reverbscope.io.jsonutil import make_folder, read_json_object, write_text_atomic

log = logging.getLogger("reverbscope.geometry")

GEOMETRY_FILE = "room-geometry.json"
GEOMETRY_SCHEMA_VERSION = 1

#: Larger than any room ReverbScope is meant for (a concert hall is about
#: 60 m long); a bigger number is a typo in the units (cm entered as m).
MAX_ROOM_DIMENSION_M = 200.0
#: Positions may lie outside the box (the box may be wrong, or the
#: loudspeaker stands in a doorway) but not kilometres away.
MAX_COORDINATE_M = 1000.0

SCAN_UNITS = ("m", "cm", "mm", "in", "ft")
UP_AXES = ("z", "-z", "y", "-y", "x", "-x")

_TOP_LEVEL_KEYS = frozenset({"schema_version", "room", "source", "microphones", "scan", "notes"})
_SHA256 = re.compile(r"[0-9a-f]{64}")


class GeometryError(ReverbScopeError, ValueError):
    """The room geometry is invalid, unreadable, or may not be written."""


def _invalid(error: str) -> GeometryError:
    return GeometryError(_("invalid room geometry: {error}").format(error=error))


def _number(value: object, name: str, *, limit: float = MAX_COORDINATE_M) -> float:
    """A finite real number within ``±limit``.

    ``bool`` is an ``int`` in Python; ``true`` in a coordinate field is a
    damaged file, not 1 m.
    """
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise _invalid(_("{field} must be a number").format(field=name))
    number = float(value)
    if not math.isfinite(number):
        raise _invalid(_("{field} must be a finite number").format(field=name))
    if abs(number) > limit:
        raise _invalid(
            _("{field} is {value:g} m; values beyond {limit:g} m are refused").format(
                field=name, value=number, limit=limit
            )
        )
    return number


def _text(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise _invalid(_("{field} must be text").format(field=name))
    return value


def _label(value: object) -> str:
    label = _text(value, "label")
    if not label.strip():
        raise _invalid(_("a position label must not be empty"))
    return label


def _object(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise _invalid(_("{field} must be a JSON object").format(field=name))
    return value


def _known(data: Mapping[str, Any], known: set[str], name: str) -> Mapping[str, Any]:
    """Nested records are fixed: an unknown key in one is logged and dropped."""
    unknown = sorted(set(data) - known)
    if unknown:
        log.info("ignoring unknown %s fields: %s", name, unknown)
    return data


@dataclass(frozen=True)
class Point:
    """A position in room coordinates (m)."""

    x: float
    y: float
    z: float

    def __post_init__(self) -> None:
        for name in ("x", "y", "z"):
            object.__setattr__(self, name, _number(getattr(self, name), name))

    def to_dict(self) -> dict[str, float]:
        return {"x": self.x, "y": self.y, "z": self.z}

    @classmethod
    def from_dict(cls, data: object, name: str = "point") -> Point:
        payload = _known(_object(data, name), {"x", "y", "z"}, name)
        missing = [key for key in ("x", "y", "z") if key not in payload]
        if missing:
            raise _invalid(
                _("{field} is missing {keys}").format(field=name, keys=", ".join(missing))
            )
        return cls(x=payload["x"], y=payload["y"], z=payload["z"])

    def distance_to(self, other: Point) -> float:
        return math.dist((self.x, self.y, self.z), (other.x, other.y, other.z))

    def as_tuple(self) -> tuple[float, float, float]:
        return (self.x, self.y, self.z)


@dataclass(frozen=True)
class RoomBox:
    """The rectangular room the user entered (m). A box is an assumption about
    the room, never a measurement of it."""

    length_m: float
    width_m: float
    height_m: float

    def __post_init__(self) -> None:
        for name in ("length_m", "width_m", "height_m"):
            value = _number(getattr(self, name), name, limit=MAX_ROOM_DIMENSION_M)
            if value <= 0.0:
                raise _invalid(_("{field} must be greater than 0 m").format(field=name))
            object.__setattr__(self, name, value)

    def to_dict(self) -> dict[str, float]:
        return {"length_m": self.length_m, "width_m": self.width_m, "height_m": self.height_m}

    @classmethod
    def from_dict(cls, data: object) -> RoomBox:
        keys = ("length_m", "width_m", "height_m")
        payload = _known(_object(data, "room"), set(keys), "room")
        missing = [key for key in keys if key not in payload]
        if missing:
            raise _invalid(
                _("{field} is missing {keys}").format(field="room", keys=", ".join(missing))
            )
        return cls(
            length_m=payload["length_m"], width_m=payload["width_m"], height_m=payload["height_m"]
        )

    @property
    def dimensions(self) -> tuple[float, float, float]:
        return (self.length_m, self.width_m, self.height_m)

    def contains(self, point: Point, tolerance_m: float = 1e-9) -> bool:
        """True when ``point`` is inside the box or on one of its faces."""
        return all(
            -tolerance_m <= value <= size + tolerance_m
            for value, size in zip(point.as_tuple(), self.dimensions, strict=True)
        )


@dataclass(frozen=True)
class ScanReference:
    """How an imported scan file is placed in the room.

    The SHA-256 ties the placement to the exact file: a scan that was
    re-exported (or replaced) under the same name is detected instead of
    being drawn with a placement chosen for another file.
    """

    file: str
    units: str
    up_axis: str
    yaw_deg: float
    offset: Point
    sha256: str

    def __post_init__(self) -> None:
        if not _text(self.file, "file").strip():
            raise _invalid(_("the scan file name must not be empty"))
        if self.units not in SCAN_UNITS:
            raise _invalid(
                _("{field} must be one of {values}").format(
                    field="units", values=", ".join(SCAN_UNITS)
                )
            )
        if self.up_axis not in UP_AXES:
            raise _invalid(
                _("{field} must be one of {values}").format(
                    field="up_axis", values=", ".join(UP_AXES)
                )
            )
        object.__setattr__(self, "yaw_deg", _number(self.yaw_deg, "yaw_deg", limit=360.0))
        if not isinstance(self.offset, Point):
            raise _invalid(_("{field} must be a JSON object").format(field="offset"))
        if not isinstance(self.sha256, str) or not _SHA256.fullmatch(self.sha256):
            raise _invalid(_("sha256 must be 64 lower-case hexadecimal digits"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "file": self.file,
            "units": self.units,
            "up_axis": self.up_axis,
            "yaw_deg": self.yaw_deg,
            "offset": self.offset.to_dict(),
            "sha256": self.sha256,
        }

    @classmethod
    def from_dict(cls, data: object) -> ScanReference:
        keys = ("file", "units", "up_axis", "yaw_deg", "offset", "sha256")
        payload = _known(_object(data, "scan"), set(keys), "scan")
        missing = [key for key in keys if key not in payload]
        if missing:
            raise _invalid(
                _("{field} is missing {keys}").format(field="scan", keys=", ".join(missing))
            )
        return cls(
            file=_text(payload["file"], "file"),
            units=_text(payload["units"], "units"),
            up_axis=_text(payload["up_axis"], "up_axis"),
            yaw_deg=payload["yaw_deg"],
            offset=Point.from_dict(payload["offset"], "offset"),
            sha256=_text(payload["sha256"], "sha256"),
        )


def _microphones(value: Mapping[str, Point] | Iterable[tuple[str, Point]]) -> dict[str, Point]:
    pairs = value.items() if isinstance(value, Mapping) else value
    result: dict[str, Point] = {}
    for label, point in pairs:
        name = _label(label)
        if name in result:
            raise _invalid(_("position '{label}' is listed twice").format(label=name))
        if not isinstance(point, Point):
            raise _invalid(_("{field} must be a JSON object").format(field=name))
        result[name] = point
    return result


def _empty_mapping() -> Mapping[str, Any]:
    return MappingProxyType({})


@dataclass(frozen=True)
class RoomGeometry:
    """Everything in ``room-geometry.json``.

    ``microphones`` maps a position label to its microphone, in the order the
    user entered them. ``extra`` holds the top-level keys this version does
    not know, so that saving keeps them. Both are read-only views of private
    copies: a caller's dict is never shared, and never changed.
    """

    room: RoomBox | None = None
    source: Point | None = None
    microphones: Mapping[str, Point] = field(default_factory=_empty_mapping)
    scan: ScanReference | None = None
    notes: str = ""
    schema_version: int = GEOMETRY_SCHEMA_VERSION
    extra: Mapping[str, Any] = field(default_factory=_empty_mapping)

    def __post_init__(self) -> None:
        if self.room is not None and not isinstance(self.room, RoomBox):
            raise _invalid(_("{field} must be a JSON object").format(field="room"))
        if self.source is not None and not isinstance(self.source, Point):
            raise _invalid(_("{field} must be a JSON object").format(field="source"))
        if self.scan is not None and not isinstance(self.scan, ScanReference):
            raise _invalid(_("{field} must be a JSON object").format(field="scan"))
        _text(self.notes, "notes")
        if (
            isinstance(self.schema_version, bool)
            or not isinstance(self.schema_version, int)
            or self.schema_version < 1
        ):
            raise _invalid(_("schema_version must be a positive integer"))
        object.__setattr__(self, "microphones", MappingProxyType(_microphones(self.microphones)))
        extra = {str(key): copy.deepcopy(value) for key, value in dict(self.extra).items()}
        clash = sorted(set(extra) & _TOP_LEVEL_KEYS)
        if clash:
            raise _invalid(_("{field} must not repeat a known key").format(field="extra"))
        object.__setattr__(self, "extra", MappingProxyType(extra))

    # ``microphones`` and ``extra`` are mapping views, which do not hash.
    __hash__ = None  # type: ignore[assignment]

    @property
    def newer(self) -> bool:
        """True when the file was written by a newer ReverbScope: readable, but
        :func:`save_geometry` will not overwrite it."""
        return self.schema_version > GEOMETRY_SCHEMA_VERSION

    def microphone(self, label: str) -> Point | None:
        return self.microphones.get(label)

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "schema_version": self.schema_version,
            "room": self.room.to_dict() if self.room is not None else None,
            "source": self.source.to_dict() if self.source is not None else None,
            "microphones": {label: point.to_dict() for label, point in self.microphones.items()},
            "scan": self.scan.to_dict() if self.scan is not None else None,
            "notes": self.notes,
        }
        for key, value in self.extra.items():
            data[key] = copy.deepcopy(value)
        return data

    @classmethod
    def from_dict(cls, data: object) -> RoomGeometry:
        payload = _object(data, "room geometry")
        version = payload.get("schema_version", GEOMETRY_SCHEMA_VERSION)
        if isinstance(version, bool) or not isinstance(version, int) or version < 1:
            raise _invalid(_("schema_version must be a positive integer"))
        room = payload.get("room")
        source = payload.get("source")
        scan = payload.get("scan")
        microphones = _object(payload.get("microphones", {}), "microphones")
        return cls(
            room=RoomBox.from_dict(room) if room is not None else None,
            source=Point.from_dict(source, "source") if source is not None else None,
            microphones={
                _label(label): Point.from_dict(point, str(label))
                for label, point in microphones.items()
            },
            scan=ScanReference.from_dict(scan) if scan is not None else None,
            notes=_text(payload.get("notes", ""), "notes"),
            schema_version=version,
            extra={key: value for key, value in payload.items() if key not in _TOP_LEVEL_KEYS},
        )


def geometry_file(path: str | Path) -> Path:
    """``path`` itself when it names a ``.json`` file, else the file in that folder."""
    given = Path(path)
    if given.suffix.lower() == ".json" and not given.is_dir():
        return given
    return given / GEOMETRY_FILE


def _read(path: Path) -> dict[str, Any]:
    try:
        return read_json_object(path)
    except SessionError as exc:
        raise GeometryError(str(exc)) from exc


def load_geometry(path: str | Path) -> RoomGeometry | None:
    """The geometry in ``path`` (a folder or the file), or None when there is none.

    A missing file is the normal state of a project nobody drew a room for;
    a file that exists but cannot be read is the user's to know about, so it
    raises :class:`GeometryError`.
    """
    target = geometry_file(path)
    if not target.is_file():
        return None
    return RoomGeometry.from_dict(_read(target))


def save_geometry(directory: str | Path, geometry: RoomGeometry) -> Path:
    """Write ``geometry`` atomically to ``directory/room-geometry.json``.

    The old file stays whole if anything fails (temporary file, fsync, then
    ``os.replace``). A file written by a newer ReverbScope is refused rather
    than replaced: this version would drop what it cannot read. Unknown
    top-level keys of the file being replaced are kept, so a key another tool
    added survives an edit here.
    """
    base = Path(directory)
    target = base / GEOMETRY_FILE if base.suffix.lower() != ".json" else base
    if geometry.newer:
        raise GeometryError(
            _(
                "{path} was written by a newer ReverbScope (schema {version}); "
                "this version does not overwrite it"
            ).format(path=target, version=geometry.schema_version)
        )
    kept: dict[str, Any] = {}
    if target.is_file():
        try:
            existing = _read(target)
        except GeometryError as exc:
            # The user asked to save; a file that cannot be read holds nothing
            # this version could keep.
            log.warning("replacing unreadable %s: %s", target, exc)
            existing = {}
        version = existing.get("schema_version", GEOMETRY_SCHEMA_VERSION)
        if (
            isinstance(version, int)
            and not isinstance(version, bool)
            and version > GEOMETRY_SCHEMA_VERSION
        ):
            raise GeometryError(
                _(
                    "{path} was written by a newer ReverbScope (schema {version}); "
                    "this version does not overwrite it"
                ).format(path=target, version=version)
            )
        kept = {key: value for key, value in existing.items() if key not in _TOP_LEVEL_KEYS}
    data = geometry.to_dict()
    for key, value in kept.items():
        data.setdefault(key, value)
    try:
        make_folder(target.parent)
    except SessionError as exc:
        raise GeometryError(str(exc)) from exc
    try:
        write_text_atomic(target, json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    except (OSError, TypeError, ValueError) as exc:
        raise GeometryError(
            _("cannot write {path}: {error}").format(path=target, error=exc)
        ) from exc
    return target


def example_room() -> RoomGeometry:
    """A plausible small studio, for trying the room view.

    5.0 x 4.0 x 2.7 m with the loudspeaker and microphone "A" off the centre
    lines, so that no two first-order paths arrive together. It is an
    example only: nothing writes it unless the user saves it.
    """
    return RoomGeometry(
        room=RoomBox(length_m=5.0, width_m=4.0, height_m=2.7),
        source=Point(1.2, 1.6, 1.25),
        microphones={"A": Point(3.4, 2.1, 1.2)},
    )


def with_microphone(geometry: RoomGeometry, label: str, point: Point) -> RoomGeometry:
    """``geometry`` with the microphone of ``label`` set (added last when new)."""
    microphones = dict(geometry.microphones)
    microphones[_label(label)] = point
    return replace(geometry, microphones=microphones)


def without_microphone(geometry: RoomGeometry, label: str) -> RoomGeometry:
    """``geometry`` without the microphone of ``label`` (unchanged when absent)."""
    if label not in geometry.microphones:
        return geometry
    return replace(
        geometry,
        microphones={name: point for name, point in geometry.microphones.items() if name != label},
    )


def rename_position(geometry: RoomGeometry, old: str, new: str) -> RoomGeometry:
    """Rename the microphone entry of a position renamed in the project.

    The entry keeps its place in the order. A position without a microphone
    needs nothing; renaming onto a label that already has one would silently
    drop a microphone, so it is refused.
    """
    new_label = _label(new)
    if old == new_label or old not in geometry.microphones:
        return geometry
    if new_label in geometry.microphones:
        raise GeometryError(
            _("position '{label}' already has a microphone").format(label=new_label)
        )
    return replace(
        geometry,
        microphones={
            (new_label if name == old else name): point
            for name, point in geometry.microphones.items()
        },
    )
