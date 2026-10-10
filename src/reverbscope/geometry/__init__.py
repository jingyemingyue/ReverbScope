"""Room geometry: the entered room, what a measurement says about it, and scans.

No Qt here: the room view in ``ui/room/`` draws what these modules compute,
and the scan reader runs on a worker thread.
"""

from __future__ import annotations

from reverbscope.geometry.room import (
    GEOMETRY_FILE,
    GEOMETRY_SCHEMA_VERSION,
    GeometryError,
    Point,
    RoomBox,
    RoomGeometry,
    ScanReference,
    example_room,
    load_geometry,
    rename_position,
    save_geometry,
    with_microphone,
    without_microphone,
)

__all__ = [
    "GEOMETRY_FILE",
    "GEOMETRY_SCHEMA_VERSION",
    "GeometryError",
    "Point",
    "RoomBox",
    "RoomGeometry",
    "ScanReference",
    "example_room",
    "load_geometry",
    "rename_position",
    "save_geometry",
    "with_microphone",
    "without_microphone",
]
