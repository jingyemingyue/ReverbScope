"""Reading and placing a room scan (PLY or OBJ).

A scan is shown under the entered room as a reference the user aligns by
eye; it is never measured from. Files come from phone apps and scanners the
program does not control, so every reader is bounded: the size is checked
before reading, the vertex count while reading, and a ``cancelled`` callback
is polled per chunk so the import dialog's Cancel works on a large file. The
reader runs on a worker thread and imports no Qt.

Neither format records its units or its up axis reliably; the import dialog
asks, and :func:`place_scan` applies the answer.
"""

from __future__ import annotations

import hashlib
import math
import struct
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import numpy as np
from numpy.typing import NDArray

from reverbscope.errors import ReverbScopeError
from reverbscope.geometry.room import Point
from reverbscope.i18n import _

ScanFormat = Literal["ply", "obj"]

MAX_SCAN_BYTES = 256 * 1024 * 1024
MAX_SCAN_VERTICES = 5_000_000
#: A header longer than this is not a PLY header.
_MAX_HEADER_BYTES = 64 * 1024
_READ_CHUNK = 4 * 1024 * 1024
_ROWS_PER_CHUNK = 65536

UNIT_SCALE = {"m": 1.0, "cm": 0.01, "mm": 0.001, "in": 0.0254, "ft": 0.3048}

#: Proper rotations (determinant +1) that bring each up axis onto +z. A
#: mirror would turn the scan inside out, so none is a reflection.
_UP_ROTATION: dict[str, NDArray[np.float64]] = {
    "z": np.eye(3),
    "-z": np.array([[1.0, 0.0, 0.0], [0.0, -1.0, 0.0], [0.0, 0.0, -1.0]]),
    # Y-up (most phone apps and OBJ exports): (x, y, z) -> (x, -z, y).
    "y": np.array([[1.0, 0.0, 0.0], [0.0, 0.0, -1.0], [0.0, 1.0, 0.0]]),
    "-y": np.array([[1.0, 0.0, 0.0], [0.0, 0.0, 1.0], [0.0, -1.0, 0.0]]),
    "x": np.array([[0.0, 0.0, -1.0], [0.0, 1.0, 0.0], [1.0, 0.0, 0.0]]),
    "-x": np.array([[0.0, 0.0, 1.0], [0.0, 1.0, 0.0], [-1.0, 0.0, 0.0]]),
}

_PLY_TYPES = {
    "char": "i1",
    "int8": "i1",
    "uchar": "u1",
    "uint8": "u1",
    "short": "i2",
    "int16": "i2",
    "ushort": "u2",
    "uint16": "u2",
    "int": "i4",
    "int32": "i4",
    "uint": "u4",
    "uint32": "u4",
    "float": "f4",
    "float32": "f4",
    "double": "f8",
    "float64": "f8",
}
_FACE_LISTS = ("vertex_indices", "vertex_index")


class ScanError(ReverbScopeError):
    """A scan file cannot be read (unsupported, corrupt, too large)."""


class ScanCancelledError(ScanError):
    """The user cancelled the import."""


@dataclass(frozen=True)
class ScanMesh:
    """Vertices (file units, file axes) and triangles of one scan file.

    The arrays are read-only: a mesh is shared between the worker thread
    that read it and the view that draws it.
    """

    vertices: NDArray[np.float32]
    faces: NDArray[np.int32] | None
    format: ScanFormat
    sha256: str
    source_units_note: str


def _check_cancel(cancelled: Callable[[], bool] | None) -> None:
    if cancelled is not None and cancelled():
        raise ScanCancelledError(_("the scan import was cancelled"))


def _corrupt(path: Path, detail: str) -> ScanError:
    return ScanError(
        _("{name} cannot be read as a scan: {detail}").format(name=path.name, detail=detail)
    )


def _too_many_vertices(path: Path, limit: int) -> ScanError:
    return ScanError(
        _("{name} has more than {limit} vertices; larger scans are refused").format(
            name=path.name, limit=limit
        )
    )


def _read_bytes(
    path: Path, max_bytes: int, cancelled: Callable[[], bool] | None
) -> tuple[bytes, str]:
    """The whole file and its SHA-256, refusing an oversized file before reading."""
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise ScanError(_("cannot read {path}: {error}").format(path=path, error=exc)) from exc
    if size > max_bytes:
        raise ScanError(
            _("{name} is {size} bytes; scan files larger than {limit} bytes are refused").format(
                name=path.name, size=size, limit=max_bytes
            )
        )
    digest = hashlib.sha256()
    parts: list[bytes] = []
    total = 0
    try:
        with path.open("rb") as handle:
            while True:
                _check_cancel(cancelled)
                chunk = handle.read(_READ_CHUNK)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:  # the file grew while it was read
                    raise ScanError(
                        _(
                            "{name} is {size} bytes; scan files larger than {limit} bytes "
                            "are refused"
                        ).format(name=path.name, size=total, limit=max_bytes)
                    )
                digest.update(chunk)
                parts.append(chunk)
    except OSError as exc:
        raise ScanError(_("cannot read {path}: {error}").format(path=path, error=exc)) from exc
    return b"".join(parts), digest.hexdigest()


def file_sha256(path: str | Path) -> str:
    """SHA-256 of a file, to check that a stored scan reference still names it."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(_READ_CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _fan(polygon: list[int] | NDArray[np.int64]) -> list[tuple[int, int, int]]:
    """Fan triangles of a convex polygon; fewer than three corners give none."""
    first = int(polygon[0]) if len(polygon) else 0
    return [(first, int(polygon[i]), int(polygon[i + 1])) for i in range(1, len(polygon) - 1)]


def _faces_array(
    triangles: NDArray[np.int64] | None, vertex_count: int, path: Path
) -> NDArray[np.int32] | None:
    if triangles is None or triangles.size == 0:
        return None
    if int(triangles.min()) < 0 or int(triangles.max()) >= vertex_count:
        raise _corrupt(path, _("a face refers to a vertex that does not exist"))
    faces = np.ascontiguousarray(triangles, dtype=np.int32)
    faces.setflags(write=False)
    return faces


def _finish_vertices(vertices: NDArray[Any], path: Path) -> NDArray[np.float32]:
    if vertices.shape[0] == 0:
        raise _corrupt(path, _("the file contains no vertices"))
    result = np.ascontiguousarray(vertices, dtype=np.float32)
    if not np.all(np.isfinite(result)):
        raise _corrupt(path, _("a vertex coordinate is not a finite number"))
    result.setflags(write=False)
    return result


# ----------------------------------------------------------------------------- PLY


@dataclass(frozen=True)
class _PlyProperty:
    name: str
    dtype: str
    #: Count type of a list property (None for a scalar).
    count_dtype: str | None = None


@dataclass(frozen=True)
class _PlyElement:
    name: str
    count: int
    properties: tuple[_PlyProperty, ...]

    @property
    def scalar_only(self) -> bool:
        return all(prop.count_dtype is None for prop in self.properties)


def _ply_type(token: str, path: Path) -> str:
    dtype = _PLY_TYPES.get(token)
    if dtype is None:
        raise _corrupt(path, _("unknown PLY property type '{type}'").format(type=token))
    return dtype


def _parse_ply_header(data: bytes, path: Path) -> tuple[str, list[_PlyElement], int]:
    end = data.find(b"end_header", 0, _MAX_HEADER_BYTES)
    if end < 0:
        raise _corrupt(path, _("the PLY header does not end"))
    newline = data.find(b"\n", end)
    body_start = len(data) if newline < 0 else newline + 1
    text = data[:end].decode("ascii", errors="replace").replace("\r", "")
    lines = text.split("\n")
    if not lines or lines[0].strip() != "ply":
        raise _corrupt(path, _("the file does not start with a PLY header"))
    encoding = ""
    elements: list[_PlyElement] = []
    current: tuple[str, int, list[_PlyProperty]] | None = None
    for raw in lines[1:]:
        tokens = raw.split()
        if not tokens or tokens[0] in ("comment", "obj_info"):
            continue
        keyword = tokens[0]
        if keyword == "format":
            if len(tokens) < 2 or tokens[1] not in (
                "ascii",
                "binary_little_endian",
                "binary_big_endian",
            ):
                raise _corrupt(path, _("unsupported PLY format"))
            encoding = tokens[1]
        elif keyword == "element":
            if len(tokens) != 3 or not tokens[2].isdigit():
                raise _corrupt(path, _("a PLY element line is malformed"))
            if current is not None:
                elements.append(_PlyElement(current[0], current[1], tuple(current[2])))
            current = (tokens[1], int(tokens[2]), [])
        elif keyword == "property":
            if current is None:
                raise _corrupt(path, _("a PLY property comes before any element"))
            if len(tokens) == 5 and tokens[1] == "list":
                current[2].append(
                    _PlyProperty(tokens[4], _ply_type(tokens[3], path), _ply_type(tokens[2], path))
                )
            elif len(tokens) == 3:
                current[2].append(_PlyProperty(tokens[2], _ply_type(tokens[1], path)))
            else:
                raise _corrupt(path, _("a PLY property line is malformed"))
        else:
            raise _corrupt(path, _("unexpected line in the PLY header"))
    if current is not None:
        elements.append(_PlyElement(current[0], current[1], tuple(current[2])))
    if not encoding:
        raise _corrupt(path, _("the PLY header has no format line"))
    return encoding, elements, body_start


def _xyz_columns(element: _PlyElement, path: Path) -> list[int]:
    names = [prop.name for prop in element.properties]
    if not all(axis in names for axis in ("x", "y", "z")):
        raise _corrupt(path, _("the PLY vertices have no x, y and z"))
    if any(element.properties[names.index(axis)].count_dtype for axis in ("x", "y", "z")):
        raise _corrupt(path, _("the PLY vertices have no x, y and z"))
    return [names.index(axis) for axis in ("x", "y", "z")]


def _face_list_index(element: _PlyElement) -> int | None:
    for index, prop in enumerate(element.properties):
        if prop.count_dtype is not None and prop.name in _FACE_LISTS:
            return index
    return None


class _AsciiBody:
    """Whitespace-separated tokens of an ASCII PLY body, read line by line."""

    def __init__(self, data: bytes, start: int) -> None:
        text = data[start:].decode("ascii", errors="replace")
        # Blank lines carry no element; "\r\r\n" (a file converted to CRLF
        # twice) would otherwise read as one.
        self.lines = [line for line in text.splitlines() if line.strip()]
        self.position = 0

    def take(self, count: int, path: Path) -> list[str]:
        if self.position + count > len(self.lines):
            raise _corrupt(path, _("the file ends before all its elements were read"))
        chunk = self.lines[self.position : self.position + count]
        self.position += count
        return chunk


def _ascii_scalar_rows(rows: list[str], width: int, path: Path) -> NDArray[np.float64]:
    try:
        values = np.array(" ".join(rows).split(), dtype=np.float64)
    except ValueError as exc:
        raise _corrupt(path, _("a value in the file is not a number")) from exc
    if values.size != width * len(rows):
        raise _corrupt(path, _("an element has the wrong number of values"))
    return values.reshape(len(rows), width)


def _ascii_list_rows(
    rows: list[str], element: _PlyElement, list_index: int | None, path: Path
) -> list[tuple[int, int, int]]:
    """Triangles from ASCII rows that may hold list properties."""
    triangles: list[tuple[int, int, int]] = []
    for row in rows:
        tokens = row.split()
        position = 0
        try:
            for index, prop in enumerate(element.properties):
                if prop.count_dtype is None:
                    position += 1
                    continue
                count = int(tokens[position])
                values = [
                    int(float(token)) for token in tokens[position + 1 : position + 1 + count]
                ]
                if len(values) != count or count < 0:
                    raise _corrupt(path, _("an element has the wrong number of values"))
                position += 1 + count
                if index == list_index:
                    triangles.extend(_fan(values))
        except (IndexError, ValueError) as exc:
            raise _corrupt(path, _("an element has the wrong number of values")) from exc
        if position > len(tokens):
            raise _corrupt(path, _("an element has the wrong number of values"))
    return triangles


def _read_ply_ascii(
    data: bytes,
    elements: list[_PlyElement],
    start: int,
    path: Path,
    cancelled: Callable[[], bool] | None,
) -> tuple[NDArray[np.float64], NDArray[np.int64] | None]:
    body = _AsciiBody(data, start)
    vertices: NDArray[np.float64] | None = None
    triangles: list[tuple[int, int, int]] = []
    has_faces = False
    for element in elements:
        is_vertex = element.name == "vertex" and vertices is None
        is_face = element.name == "face"
        columns = _xyz_columns(element, path) if is_vertex else []
        list_index = _face_list_index(element) if is_face else None
        has_faces = has_faces or list_index is not None
        parts: list[NDArray[np.float64]] = []
        remaining = element.count
        while remaining > 0:
            _check_cancel(cancelled)
            count = min(remaining, _ROWS_PER_CHUNK)
            rows = body.take(count, path)
            remaining -= count
            if is_vertex and element.scalar_only:
                parts.append(_ascii_scalar_rows(rows, len(element.properties), path)[:, columns])
            elif is_vertex:
                raise _corrupt(path, _("PLY vertices with list properties are not supported"))
            elif is_face:
                triangles.extend(_ascii_list_rows(rows, element, list_index, path))
            # Any other element is skipped, one line per instance.
        if is_vertex:
            vertices = np.concatenate(parts) if parts else np.zeros((0, 3))
    if vertices is None:
        raise _corrupt(path, _("the file contains no vertices"))
    faces = np.array(triangles, dtype=np.int64).reshape(-1, 3) if has_faces else None
    return vertices, faces


def _binary_struct(element: _PlyElement, order: str) -> np.dtype[Any]:
    return np.dtype(
        [(f"p{index}", order + prop.dtype) for index, prop in enumerate(element.properties)]
    )


def _read_ply_binary(
    data: bytes,
    elements: list[_PlyElement],
    start: int,
    encoding: str,
    path: Path,
    cancelled: Callable[[], bool] | None,
) -> tuple[NDArray[np.float64], NDArray[np.int64] | None]:
    order = "<" if encoding == "binary_little_endian" else ">"
    position = start
    vertices: NDArray[np.float64] | None = None
    faces: NDArray[np.int64] | None = None
    for element in elements:
        is_vertex = element.name == "vertex" and vertices is None
        is_face = element.name == "face"
        if element.scalar_only:
            dtype = _binary_struct(element, order)
            needed = dtype.itemsize * element.count
            if position + needed > len(data):
                raise _corrupt(path, _("the file ends before all its elements were read"))
            if is_vertex:
                columns = _xyz_columns(element, path)
                table = np.frombuffer(data, dtype=dtype, count=element.count, offset=position)
                out = np.empty((element.count, 3), dtype=np.float64)
                for begin in range(0, element.count, _ROWS_PER_CHUNK * 16):
                    _check_cancel(cancelled)
                    stop = min(element.count, begin + _ROWS_PER_CHUNK * 16)
                    for axis, column in enumerate(columns):
                        out[begin:stop, axis] = table[f"p{column}"][begin:stop]
                vertices = out
            position += needed
            continue
        if is_vertex:
            raise _corrupt(path, _("PLY vertices with list properties are not supported"))
        list_index = _face_list_index(element) if is_face else None
        position, found = _binary_list_element(
            data, element, position, order, list_index, path, cancelled
        )
        if list_index is not None:
            faces = found
    if vertices is None:
        raise _corrupt(path, _("the file contains no vertices"))
    return vertices, faces


def _binary_list_element(
    data: bytes,
    element: _PlyElement,
    position: int,
    order: str,
    list_index: int | None,
    path: Path,
    cancelled: Callable[[], bool] | None,
) -> tuple[int, NDArray[np.int64]]:
    """Read (or skip) an element with list properties; triangles of ``list_index``.

    Fast path: when every instance has the same list lengths (a mesh of
    triangles), the element is one structured array. Otherwise each instance
    is read in turn.
    """
    lists = [i for i, prop in enumerate(element.properties) if prop.count_dtype is not None]
    if len(lists) == 1 and element.count > 0:
        fast = _uniform_list_element(data, element, position, order, lists[0], path)
        if fast is not None:
            table, end = fast
            if list_index is None:
                return end, np.zeros((0, 3), dtype=np.int64)
            polygons = np.asarray(table[f"p{list_index}"], dtype=np.int64)
            if polygons.ndim == 1:
                polygons = polygons.reshape(-1, 1)
            corners = polygons.shape[1]
            if corners < 3:
                return end, np.zeros((0, 3), dtype=np.int64)
            fan = [
                np.stack([polygons[:, 0], polygons[:, i], polygons[:, i + 1]], axis=1)
                for i in range(1, corners - 1)
            ]
            # Keep each polygon's triangles together, polygon by polygon.
            return end, np.stack(fan, axis=1).reshape(-1, 3)
    triangles: list[tuple[int, int, int]] = []
    for instance in range(element.count):
        if instance % _ROWS_PER_CHUNK == 0:
            _check_cancel(cancelled)
        for index, prop in enumerate(element.properties):
            try:
                if prop.count_dtype is None:
                    position += np.dtype(prop.dtype).itemsize
                    continue
                count_type = np.dtype(order + prop.count_dtype)
                (count,) = struct.unpack_from(order + count_type.char, data, position)
                position += count_type.itemsize
                item = np.dtype(order + prop.dtype)
                if count < 0 or position + count * item.itemsize > len(data):
                    raise _corrupt(path, _("the file ends before all its elements were read"))
                if index == list_index:
                    values = np.frombuffer(data, dtype=item, count=count, offset=position)
                    triangles.extend(_fan(values.astype(np.int64)))
                position += count * item.itemsize
            except struct.error as exc:
                raise _corrupt(path, _("the file ends before all its elements were read")) from exc
        if position > len(data):
            raise _corrupt(path, _("the file ends before all its elements were read"))
    return position, np.array(triangles, dtype=np.int64).reshape(-1, 3)


def _uniform_list_element(
    data: bytes, element: _PlyElement, position: int, order: str, list_at: int, path: Path
) -> tuple[NDArray[Any], int] | None:
    """The element as a structured array when all its lists have one length."""
    head = 0
    for prop in element.properties[:list_at]:
        head += np.dtype(prop.dtype).itemsize
    prop = element.properties[list_at]
    assert prop.count_dtype is not None
    count_type = np.dtype(order + prop.count_dtype)
    if position + head + count_type.itemsize > len(data):
        raise _corrupt(path, _("the file ends before all its elements were read"))
    first = int(np.frombuffer(data, dtype=count_type, count=1, offset=position + head)[0])
    if first < 0 or first > 64:
        return None
    fields: list[tuple[str, Any] | tuple[str, Any, tuple[int, ...]]] = []
    for index, item in enumerate(element.properties):
        if index == list_at:
            fields.append((f"n{index}", count_type))
            fields.append((f"p{index}", np.dtype(order + item.dtype), (first,)))
        else:
            fields.append((f"p{index}", np.dtype(order + item.dtype)))
    dtype = np.dtype(fields)
    needed = dtype.itemsize * element.count
    if position + needed > len(data):
        return None
    table = np.frombuffer(data, dtype=dtype, count=element.count, offset=position)
    if not np.all(table[f"n{list_at}"] == first):
        return None
    return table, position + needed


def _read_ply(
    data: bytes, path: Path, max_vertices: int, cancelled: Callable[[], bool] | None
) -> tuple[NDArray[np.float32], NDArray[np.int32] | None]:
    encoding, elements, start = _parse_ply_header(data, path)
    vertex = next((element for element in elements if element.name == "vertex"), None)
    if vertex is None:
        raise _corrupt(path, _("the file contains no vertices"))
    if vertex.count > max_vertices:
        raise _too_many_vertices(path, max_vertices)
    face = next((element for element in elements if element.name == "face"), None)
    if face is not None and face.count > 4 * max_vertices:
        raise _corrupt(path, _("the file declares more faces than its vertices can form"))
    if encoding == "ascii":
        raw, triangles = _read_ply_ascii(data, elements, start, path, cancelled)
    else:
        raw, triangles = _read_ply_binary(data, elements, start, encoding, path, cancelled)
    vertices = _finish_vertices(raw, path)
    return vertices, _faces_array(triangles, vertices.shape[0], path)


# ----------------------------------------------------------------------------- OBJ


def _obj_index(token: str, count: int) -> int:
    """A 0-based vertex index from an OBJ face corner (``v``, ``v/vt``, ``v//vn``, ``v/vt/vn``)."""
    value = int(token.split("/", 1)[0])
    if value == 0:
        raise ValueError("0 is not an OBJ index")
    return count + value if value < 0 else value - 1


def _read_obj(
    data: bytes, path: Path, max_vertices: int, cancelled: Callable[[], bool] | None
) -> tuple[NDArray[np.float32], NDArray[np.int32] | None]:
    # latin-1 maps every byte, so a stray non-ASCII comment cannot fail the read.
    lines = data.decode("latin-1").splitlines()
    coordinates: list[float] = []
    count = 0
    triangles: list[tuple[int, int, int]] = []
    for number, line in enumerate(lines, start=1):
        if number % _ROWS_PER_CHUNK == 0:
            _check_cancel(cancelled)
        if line.startswith("v "):
            tokens = line.split()
            if len(tokens) < 4:
                raise _corrupt(
                    path,
                    _("line {line} has a vertex without three coordinates").format(line=number),
                )
            try:
                coordinates.extend((float(tokens[1]), float(tokens[2]), float(tokens[3])))
            except ValueError as exc:
                raise _corrupt(
                    path, _("line {line} has a value that is not a number").format(line=number)
                ) from exc
            count += 1
            if count > max_vertices:
                raise _too_many_vertices(path, max_vertices)
        elif line.startswith("f "):
            try:
                corners = [_obj_index(token, count) for token in line.split()[1:]]
            except ValueError as exc:
                raise _corrupt(
                    path, _("line {line} has a face index that is not valid").format(line=number)
                ) from exc
            triangles.extend(_fan(corners))
        elif line.startswith(("v\t", "f\t")):
            raise _corrupt(path, _("line {line} cannot be read").format(line=number))
        # vt, vn, o, g, s, usemtl, mtllib, l, p and comments carry nothing to draw.
    _check_cancel(cancelled)
    vertices = _finish_vertices(np.array(coordinates, dtype=np.float64).reshape(-1, 3), path)
    faces = np.array(triangles, dtype=np.int64).reshape(-1, 3) if triangles else None
    return vertices, _faces_array(faces, vertices.shape[0], path)


# ----------------------------------------------------------------------------- public


def read_scan(
    path: str | Path,
    *,
    max_bytes: int = MAX_SCAN_BYTES,
    max_vertices: int = MAX_SCAN_VERTICES,
    cancelled: Callable[[], bool] | None = None,
) -> ScanMesh:
    """Read a PLY (ASCII, binary little or big endian) or OBJ scan.

    Polygons are fan-triangulated (scans are made of triangles and the odd
    convex quad). Raises :class:`ScanError` for an unsupported, corrupt or
    oversized file and :class:`ScanCancelledError` when ``cancelled``
    returns true.
    """
    source = Path(path)
    suffix = source.suffix.lower()
    if suffix not in (".ply", ".obj"):
        raise ScanError(
            _("{name} is not a PLY or OBJ file; only these scan formats can be read").format(
                name=source.name
            )
        )
    data, sha256 = _read_bytes(source, max_bytes, cancelled)
    kind: ScanFormat = "ply" if suffix == ".ply" else "obj"
    if kind == "ply":
        vertices, faces = _read_ply(data, source, max_vertices, cancelled)
    else:
        vertices, faces = _read_obj(data, source, max_vertices, cancelled)
    return ScanMesh(
        vertices=vertices,
        faces=faces,
        format=kind,
        sha256=sha256,
        source_units_note=_(
            "the file does not record its units or which axis is up; choose them when importing"
        ),
    )


def place_scan(
    vertices: NDArray[Any],
    *,
    units: str,
    up_axis: str,
    yaw_deg: float,
    offset: Point,
) -> NDArray[np.float64]:
    """Scan vertices in room coordinates (m): scale, up axis to +z, yaw, offset.

    The order matters: the yaw turns the scan about the room's vertical,
    which exists only once the up axis is on +z, and the offset is in room
    metres. A new array is returned; ``vertices`` is not changed.
    """
    scale = UNIT_SCALE.get(units)
    if scale is None:
        raise ScanError(
            _("{field} must be one of {values}").format(field="units", values=", ".join(UNIT_SCALE))
        )
    rotation = _UP_ROTATION.get(up_axis)
    if rotation is None:
        raise ScanError(
            _("{field} must be one of {values}").format(
                field="up_axis", values=", ".join(_UP_ROTATION)
            )
        )
    if not math.isfinite(yaw_deg):
        raise ScanError(_("{field} must be a finite number").format(field="yaw_deg"))
    points = np.asarray(vertices, dtype=np.float64).reshape(-1, 3)
    yaw = math.radians(yaw_deg)
    turn = np.array(
        [
            [math.cos(yaw), -math.sin(yaw), 0.0],
            [math.sin(yaw), math.cos(yaw), 0.0],
            [0.0, 0.0, 1.0],
        ]
    )
    transform = turn @ rotation * scale
    return np.asarray(points @ transform.T + np.array(offset.as_tuple()), dtype=np.float64)


def align_to_floor_corner(vertices: NDArray[Any]) -> Point:
    """The offset that puts the scan's bounding-box minimum at the room origin.

    The room's origin is a floor corner, so for a scan of the whole room
    this puts the scan's floor on z = 0 and its corner on the origin; the
    user then fine-tunes by eye.
    """
    points = np.asarray(vertices, dtype=np.float64).reshape(-1, 3)
    if points.shape[0] == 0:
        raise ScanError(_("the scan has no vertices to align"))
    low = points.min(axis=0)
    return Point(float(-low[0]), float(-low[1]), float(-low[2]))


def voxel_thin(vertices: NDArray[Any], voxel_m: float, max_points: int) -> NDArray[np.float64]:
    """At most ``max_points`` points, one per occupied voxel, for drawing.

    Each voxel keeps its first vertex in file order, so the same file always
    gives the same points (a random subset would flicker between redraws).
    When there are still too many voxels the voxel size is doubled until the
    points fit.
    """
    if not math.isfinite(voxel_m) or voxel_m <= 0.0:
        raise ScanError(_("the voxel size must be a positive number"))
    if max_points < 1:
        raise ScanError(_("at least one point must be kept"))
    points = np.asarray(vertices, dtype=np.float64).reshape(-1, 3)
    if points.shape[0] == 0:
        return points.copy()
    origin = points.min(axis=0)
    size = voxel_m
    for _attempt in range(64):
        cells = np.floor((points - origin) / size).astype(np.int64)
        _cells, first = np.unique(cells, axis=0, return_index=True)
        if first.shape[0] <= max_points:
            return points[np.sort(first)].copy()
        size *= 2.0
    return points[:max_points].copy()  # pragma: no cover - 64 doublings cover any scan
