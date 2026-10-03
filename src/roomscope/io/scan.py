"""Import an external lidar / photogrammetry scan as a room point cloud or mesh.

RoomScope does not talk to a lidar. The user already has a file. This module
reads two common interchange formats and nothing else:

* **PLY** (Stanford Triangle Format, Greg Turk) — the usual lidar / point-cloud
  export. ASCII 1.0 only; binary PLY is refused with a clear error.
  Documented at http://paulbourke.net/dataformats/ply/
* **Wavefront OBJ** — vertex list plus optional triangular faces.
  Library of Congress FDD000507.

The parser is a clean-room reader of those public layouts. No Open3D,
trimesh, or CloudCompare source was used. Coordinates are taken as metres
as stored in the file; RoomScope does not align the scan to the microphone.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import numpy as np

from roomscope.errors import SessionError
from roomscope.i18n import _, diag
from roomscope.models.result import AnalysisResult, FloatArray, RoomScan

#: How many points we keep for the picture and for ``result.json``.
MAX_STORED_POINTS = 4000
PLY_FORMAT_REFERENCE = (
    "Stanford Triangle Format (PLY), ASCII 1.0; Greg Turk / http://paulbourke.net/dataformats/ply/"
)
OBJ_FORMAT_REFERENCE = (
    "Wavefront OBJ vertex and face records; "
    "https://www.loc.gov/preservation/digital/formats/fdd/fdd000507.shtml"
)


class ScanError(SessionError):
    """The scan file cannot be used as a room model input."""


def load_scan(path: Path | str) -> RoomScan:
    """Read ``path`` as a PLY or OBJ scan. Coordinates stay in file units (m)."""
    source = Path(path)
    if not source.is_file():
        raise ScanError(_("scan file not found: {path}").format(path=source))
    suffix = source.suffix.lower()
    if suffix == ".ply":
        points, faces, notes = _read_ply(source)
        reference = PLY_FORMAT_REFERENCE
        fmt = "ply"
    elif suffix == ".obj":
        points, faces, notes = _read_obj(source)
        reference = OBJ_FORMAT_REFERENCE
        fmt = "obj"
    else:
        raise ScanError(
            _("scan file must be a .ply or .obj file, not {name}").format(name=source.name)
        )
    if points.shape[0] < 3:
        raise ScanError(_("scan file has fewer than three vertices: {path}").format(path=source))
    stored, downsampled = _downsample(points)
    if downsampled:
        notes = (
            *notes,
            diag(
                "imported scan was downsampled from {count} to {kept} points for the picture",
                count=int(points.shape[0]),
                kept=int(stored.shape[0]),
            ),
        )
    mins = tuple(float(v) for v in stored.min(axis=0))
    maxs = tuple(float(v) for v in stored.max(axis=0))
    return RoomScan(
        format=fmt,
        source_name=source.name,
        points_m=stored,
        faces=faces,
        bounds_min_m=(mins[0], mins[1], mins[2]),
        bounds_max_m=(maxs[0], maxs[1], maxs[2]),
        point_count=int(points.shape[0]),
        format_reference=reference,
        notes=notes,
    )


def load_scan_optional(path: Path | str | None) -> RoomScan | None:
    """``load_scan`` or ``None`` when ``path`` is empty."""
    if path is None or str(path).strip() == "":
        return None
    return load_scan(path)


def attach_room_scan(result: AnalysisResult, path: Path | str | None) -> AnalysisResult:
    """Return ``result`` with :attr:`room_scan` set when ``path`` is given."""
    scan = load_scan_optional(path)
    if scan is None:
        return result
    return replace(result, room_scan=scan)


def _downsample(points: FloatArray) -> tuple[FloatArray, bool]:
    if points.shape[0] <= MAX_STORED_POINTS:
        return points, False
    step = int(np.ceil(points.shape[0] / MAX_STORED_POINTS))
    return np.asarray(points[::step], dtype=np.float64), True


def _read_ply(path: Path) -> tuple[FloatArray, tuple[tuple[int, int, int], ...], tuple[str, ...]]:
    text = path.read_text(encoding="utf-8", errors="replace")
    if text.startswith("ply\n") is False and not text.startswith("ply\r"):
        raise ScanError(_("not a PLY file: {path}").format(path=path))
    lines = text.splitlines()
    if len(lines) < 3:
        raise ScanError(_("PLY header is incomplete: {path}").format(path=path))
    fmt = ""
    vertex_count = 0
    face_count = 0
    properties: list[str] = []
    section = ""
    header_end = 0
    for index, raw in enumerate(lines):
        line = raw.strip()
        if line == "end_header":
            header_end = index + 1
            break
        if line.startswith("format "):
            fmt = line.split()[1].lower()
        elif line.startswith("element vertex "):
            section = "vertex"
            vertex_count = int(line.split()[2])
            properties = []
        elif line.startswith("element face "):
            section = "face"
            face_count = int(line.split()[2])
        elif line.startswith("element "):
            section = "other"
        elif line.startswith("property ") and section == "vertex":
            properties.append(line.split()[-1].lower())
    if header_end == 0:
        raise ScanError(_("PLY file has no end_header: {path}").format(path=path))
    if fmt and fmt != "ascii":
        raise ScanError(
            _("binary PLY is not read; export ASCII 1.0 PLY from the scanner: {path}").format(
                path=path
            )
        )
    try:
        xi, yi, zi = properties.index("x"), properties.index("y"), properties.index("z")
    except ValueError as exc:
        raise ScanError(
            _("PLY vertices need x, y and z properties: {path}").format(path=path)
        ) from exc
    body = lines[header_end:]
    if len(body) < vertex_count:
        raise ScanError(_("PLY vertex list is short: {path}").format(path=path))
    points = np.zeros((vertex_count, 3), dtype=np.float64)
    for row, line in enumerate(body[:vertex_count]):
        parts = line.split()
        if len(parts) <= max(xi, yi, zi):
            raise ScanError(_("PLY vertex {row} is short: {path}").format(row=row, path=path))
        points[row] = (float(parts[xi]), float(parts[yi]), float(parts[zi]))
    faces: list[tuple[int, int, int]] = []
    for line in body[vertex_count : vertex_count + face_count]:
        parts = line.split()
        if len(parts) < 4:
            continue
        count = int(parts[0])
        if count >= 3:
            faces.append((int(parts[1]), int(parts[2]), int(parts[3])))
    notes = (
        diag("imported PLY scan; coordinates are file units treated as metres"),
        diag("no lidar was attached; this is a file the user already had"),
    )
    return points, tuple(faces), notes


def _read_obj(path: Path) -> tuple[FloatArray, tuple[tuple[int, int, int], ...], tuple[str, ...]]:
    vertices: list[tuple[float, float, float]] = []
    faces: list[tuple[int, int, int]] = []
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if line.startswith("v "):
            parts = line.split()
            if len(parts) < 4:
                continue
            vertices.append((float(parts[1]), float(parts[2]), float(parts[3])))
        elif line.startswith("f "):
            idx = []
            for token in line.split()[1:]:
                idx.append(int(token.split("/")[0]))
            if len(idx) >= 3:
                faces.append((idx[0] - 1, idx[1] - 1, idx[2] - 1))
    if not vertices:
        raise ScanError(_("OBJ file has no vertices: {path}").format(path=path))
    notes = (
        diag("imported OBJ mesh; coordinates are file units treated as metres"),
        diag("no lidar was attached; this is a file the user already had"),
    )
    return np.asarray(vertices, dtype=np.float64), tuple(faces), notes
