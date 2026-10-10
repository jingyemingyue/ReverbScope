from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any

import jsonschema
import pytest

from reverbscope.geometry.room import (
    GEOMETRY_FILE,
    GEOMETRY_SCHEMA_VERSION,
    GeometryError,
    Point,
    RoomBox,
    RoomGeometry,
    ScanReference,
    example_room,
    geometry_file,
    load_geometry,
    rename_position,
    save_geometry,
    with_microphone,
    without_microphone,
)

SCHEMA = Path("src/reverbscope/schemas/room-geometry.schema.json")
SHA = "ab" * 32


def _full() -> RoomGeometry:
    return RoomGeometry(
        room=RoomBox(6.0, 4.5, 3.0),
        source=Point(1.0, 2.0, 1.2),
        microphones={"A": Point(3.0, 2.2, 1.2), "B": Point(4.0, 1.0, 1.1)},
        scan=ScanReference("room.ply", "cm", "y", 15.0, Point(0.1, 0.2, 0.0), SHA),
        notes="drums by the window",
    )


def _schema() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(SCHEMA.read_text(encoding="utf-8"))
    return data


def test_round_trip_through_dict() -> None:
    geometry = _full()
    assert RoomGeometry.from_dict(geometry.to_dict()) == geometry


def test_round_trip_through_file(tmp_path: Path) -> None:
    geometry = _full()
    written = save_geometry(tmp_path, geometry)
    assert written == tmp_path / GEOMETRY_FILE
    assert load_geometry(tmp_path) == geometry
    assert load_geometry(written) == geometry


def test_microphone_order_is_kept(tmp_path: Path) -> None:
    geometry = RoomGeometry(microphones={"Z": Point(0, 0, 0), "A": Point(1, 1, 1)})
    save_geometry(tmp_path, geometry)
    loaded = load_geometry(tmp_path)
    assert loaded is not None
    assert list(loaded.microphones) == ["Z", "A"]


def test_missing_file_is_none(tmp_path: Path) -> None:
    assert load_geometry(tmp_path) is None
    assert load_geometry(tmp_path / GEOMETRY_FILE) is None


def test_geometry_file_accepts_folder_or_file(tmp_path: Path) -> None:
    assert geometry_file(tmp_path) == tmp_path / GEOMETRY_FILE
    assert geometry_file(tmp_path / "other.json") == tmp_path / "other.json"


def test_empty_geometry_is_valid() -> None:
    geometry = RoomGeometry()
    assert geometry.to_dict()["room"] is None
    assert RoomGeometry.from_dict({}) == geometry


def test_unknown_keys_go_to_extra_and_are_written_back(tmp_path: Path) -> None:
    data = _full().to_dict()
    data["future_layer"] = {"walls": [1, 2]}
    loaded = RoomGeometry.from_dict(data)
    assert loaded.extra == {"future_layer": {"walls": [1, 2]}}
    save_geometry(tmp_path, loaded)
    stored = json.loads((tmp_path / GEOMETRY_FILE).read_text(encoding="utf-8"))
    assert stored["future_layer"] == {"walls": [1, 2]}


def test_save_keeps_unknown_keys_already_in_the_file(tmp_path: Path) -> None:
    data = _full().to_dict()
    data["added_by_another_tool"] = 42
    (tmp_path / GEOMETRY_FILE).write_text(json.dumps(data), encoding="utf-8")
    save_geometry(tmp_path, example_room())
    stored = json.loads((tmp_path / GEOMETRY_FILE).read_text(encoding="utf-8"))
    assert stored["added_by_another_tool"] == 42
    assert stored["room"] == {"length_m": 5.0, "width_m": 4.0, "height_m": 2.7}


def test_extra_is_a_private_copy() -> None:
    nested = {"list": [1]}
    geometry = RoomGeometry(extra={"x_future": nested})
    nested["list"].append(2)
    assert geometry.extra["x_future"] == {"list": [1]}
    with pytest.raises(TypeError):
        geometry.extra["new"] = 1  # type: ignore[index]


def test_microphones_are_read_only_and_not_shared() -> None:
    mics = {"A": Point(1, 1, 1)}
    geometry = RoomGeometry(microphones=mics)
    mics["B"] = Point(2, 2, 2)
    assert list(geometry.microphones) == ["A"]
    with pytest.raises(TypeError):
        geometry.microphones["C"] = Point(0, 0, 0)  # type: ignore[index]


def test_extra_may_not_shadow_known_keys() -> None:
    with pytest.raises(GeometryError):
        RoomGeometry(extra={"room": None})


def test_newer_version_is_read_and_flagged(tmp_path: Path) -> None:
    data = _full().to_dict()
    data["schema_version"] = GEOMETRY_SCHEMA_VERSION + 1
    (tmp_path / GEOMETRY_FILE).write_text(json.dumps(data), encoding="utf-8")
    loaded = load_geometry(tmp_path)
    assert loaded is not None
    assert loaded.newer
    assert loaded.room == RoomBox(6.0, 4.5, 3.0)


def test_newer_file_is_not_overwritten(tmp_path: Path) -> None:
    data = _full().to_dict()
    data["schema_version"] = GEOMETRY_SCHEMA_VERSION + 1
    target = tmp_path / GEOMETRY_FILE
    target.write_text(json.dumps(data), encoding="utf-8")
    before = target.read_bytes()
    with pytest.raises(GeometryError, match="newer"):
        save_geometry(tmp_path, example_room())
    assert target.read_bytes() == before


def test_newer_geometry_object_is_not_written(tmp_path: Path) -> None:
    geometry = RoomGeometry(schema_version=GEOMETRY_SCHEMA_VERSION + 1)
    with pytest.raises(GeometryError):
        save_geometry(tmp_path, geometry)
    assert not (tmp_path / GEOMETRY_FILE).exists()


def test_atomic_write_keeps_old_file_on_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    save_geometry(tmp_path, _full())
    before = (tmp_path / GEOMETRY_FILE).read_bytes()

    def broken(src: object, dst: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", broken)
    with pytest.raises(GeometryError, match="disk full"):
        save_geometry(tmp_path, example_room())
    monkeypatch.undo()
    assert (tmp_path / GEOMETRY_FILE).read_bytes() == before
    assert sorted(p.name for p in tmp_path.iterdir()) == [GEOMETRY_FILE]


def test_atomic_write_leaves_no_temporary_files(tmp_path: Path) -> None:
    save_geometry(tmp_path, _full())
    save_geometry(tmp_path, example_room())
    assert sorted(p.name for p in tmp_path.iterdir()) == [GEOMETRY_FILE]


def test_save_creates_the_folder(tmp_path: Path) -> None:
    written = save_geometry(tmp_path / "new" / "room", example_room())
    assert written.is_file()


def test_unreadable_file_is_replaced_on_save(tmp_path: Path) -> None:
    (tmp_path / GEOMETRY_FILE).write_text("{not json", encoding="utf-8")
    save_geometry(tmp_path, example_room())
    assert load_geometry(tmp_path) == example_room()


def test_bad_json_is_a_geometry_error(tmp_path: Path) -> None:
    (tmp_path / GEOMETRY_FILE).write_text("{not json", encoding="utf-8")
    with pytest.raises(GeometryError):
        load_geometry(tmp_path)


def test_non_object_is_a_geometry_error(tmp_path: Path) -> None:
    (tmp_path / GEOMETRY_FILE).write_text("[1, 2]", encoding="utf-8")
    with pytest.raises(GeometryError):
        load_geometry(tmp_path)


@pytest.mark.parametrize(
    "change",
    [
        {"room": {"length_m": "5", "width_m": 4, "height_m": 3}},
        {"room": {"length_m": 5, "width_m": 4}},
        {"room": {"length_m": 0, "width_m": 4, "height_m": 3}},
        {"room": {"length_m": -1, "width_m": 4, "height_m": 3}},
        {"room": {"length_m": 500, "width_m": 4, "height_m": 3}},
        {"room": [5, 4, 3]},
        {"source": {"x": True, "y": 0, "z": 0}},
        {"source": {"x": None, "y": 0, "z": 0}},
        {"source": {"x": 1e9, "y": 0, "z": 0}},
        {"microphones": [["A", {"x": 0, "y": 0, "z": 0}]]},
        {"microphones": {"": {"x": 0, "y": 0, "z": 0}}},
        {"microphones": {"  ": {"x": 0, "y": 0, "z": 0}}},
        {"microphones": {"A": {"x": 0, "y": 0}}},
        {"notes": 5},
        {"schema_version": "1"},
        {"schema_version": True},
        {"schema_version": 0},
        {"scan": {"file": "a.ply", "units": "km", "up_axis": "z", "yaw_deg": 0,
                  "offset": {"x": 0, "y": 0, "z": 0}, "sha256": SHA}},
        {"scan": {"file": "a.ply", "units": "m", "up_axis": "w", "yaw_deg": 0,
                  "offset": {"x": 0, "y": 0, "z": 0}, "sha256": SHA}},
        {"scan": {"file": "a.ply", "units": "m", "up_axis": "z", "yaw_deg": 0,
                  "offset": {"x": 0, "y": 0, "z": 0}, "sha256": "xyz"}},
        {"scan": {"file": "", "units": "m", "up_axis": "z", "yaw_deg": 0,
                  "offset": {"x": 0, "y": 0, "z": 0}, "sha256": SHA}},
    ],
)  # fmt: skip
def test_bad_types_are_rejected(change: dict[str, Any]) -> None:
    data = _full().to_dict()
    data.update(change)
    with pytest.raises(GeometryError):
        RoomGeometry.from_dict(data)


def test_non_finite_numbers_are_rejected() -> None:
    with pytest.raises(GeometryError):
        Point(math.nan, 0.0, 0.0)
    with pytest.raises(GeometryError):
        RoomBox(math.inf, 1.0, 1.0)


def test_from_dict_does_not_mutate_input() -> None:
    data = _full().to_dict()
    data["future"] = {"a": [1]}
    snapshot = json.dumps(data, sort_keys=True)
    geometry = RoomGeometry.from_dict(data)
    geometry.to_dict()["future"]["a"].append(2)
    assert json.dumps(data, sort_keys=True) == snapshot


def test_rename_position_renames_the_microphone_in_place() -> None:
    renamed = rename_position(_full(), "A", "Mix")
    assert list(renamed.microphones) == ["Mix", "B"]
    assert renamed.microphones["Mix"] == Point(3.0, 2.2, 1.2)


def test_rename_position_without_microphone_is_a_no_op() -> None:
    geometry = _full()
    assert rename_position(geometry, "C", "D") is geometry
    assert rename_position(geometry, "A", "A") is geometry


def test_rename_position_onto_an_existing_label_is_refused() -> None:
    with pytest.raises(GeometryError):
        rename_position(_full(), "A", "B")


def test_with_and_without_microphone() -> None:
    geometry = _full()
    added = with_microphone(geometry, "C", Point(1, 1, 1))
    assert list(added.microphones) == ["A", "B", "C"]
    moved = with_microphone(added, "A", Point(2, 2, 2))
    assert moved.microphones["A"] == Point(2, 2, 2)
    assert list(moved.microphones) == ["A", "B", "C"]
    removed = without_microphone(moved, "B")
    assert list(removed.microphones) == ["A", "C"]
    assert without_microphone(removed, "missing") is removed
    assert list(geometry.microphones) == ["A", "B"]
    with pytest.raises(GeometryError):
        with_microphone(geometry, " ", Point(0, 0, 0))


def test_example_room_is_a_small_studio() -> None:
    room = example_room()
    assert room.room == RoomBox(5.0, 4.0, 2.7)
    assert room.source is not None and room.room.contains(room.source)
    mic = room.microphone("A")
    assert mic is not None and room.room.contains(mic)


def test_example_room_is_never_written_by_itself(tmp_path: Path) -> None:
    example_room()
    assert load_geometry(tmp_path) is None


@pytest.mark.parametrize("geometry", [_full(), example_room(), RoomGeometry()])
def test_to_dict_validates_against_schema(geometry: RoomGeometry) -> None:
    jsonschema.validate(geometry.to_dict(), _schema())


def test_to_dict_with_extra_validates_against_schema() -> None:
    geometry = RoomGeometry(extra={"future": [1, 2, 3]})
    jsonschema.validate(geometry.to_dict(), _schema())


def test_schema_refuses_a_bad_box() -> None:
    data = example_room().to_dict()
    data["room"]["length_m"] = 0
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(data, _schema())


def test_contains() -> None:
    box = RoomBox(5.0, 4.0, 2.7)
    assert box.contains(Point(0, 0, 0))
    assert box.contains(Point(5, 4, 2.7))
    assert not box.contains(Point(5.1, 1, 1))
    assert not box.contains(Point(1, 1, -0.01))
