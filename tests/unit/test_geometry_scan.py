from __future__ import annotations

import hashlib
import struct
from pathlib import Path

import numpy as np
import pytest

from reverbscope.geometry.room import Point
from reverbscope.geometry.scan import (
    ScanCancelledError,
    ScanError,
    align_to_floor_corner,
    file_sha256,
    place_scan,
    read_scan,
    voxel_thin,
)

CUBE = np.array(
    [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0], [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1]],
    dtype=np.float64,
)
QUADS = [[0, 1, 2, 3], [4, 5, 6, 7]]
TRIS = [[0, 1, 2], [0, 2, 3]]


def _ascii_ply(path: Path, vertices: np.ndarray, faces: list[list[int]], extra: str = "") -> Path:
    lines = [
        "ply",
        "format ascii 1.0",
        "comment made by a test",
        f"element vertex {len(vertices)}",
        "property float x",
        "property float y",
        "property float z",
        "property uchar red",
        f"element face {len(faces)}",
        "property list uchar int vertex_indices",
        extra,
        "end_header",
    ]
    lines = [line for line in lines if line]
    lines += [f"{v[0]} {v[1]} {v[2]} 255" for v in vertices]
    lines += [" ".join([str(len(f))] + [str(i) for i in f]) for f in faces]
    path.write_text("\n".join(lines) + "\n", encoding="ascii")
    return path


def _binary_ply(
    path: Path,
    vertices: np.ndarray,
    faces: list[list[int]],
    order: str,
    *,
    vtype: str = "double",
    count_type: str = "uchar",
) -> Path:
    name = "binary_little_endian" if order == "<" else "binary_big_endian"
    header = (
        f"ply\nformat {name} 1.0\n"
        f"element vertex {len(vertices)}\n"
        f"property {vtype} x\nproperty {vtype} y\nproperty {vtype} z\n"
        "property float confidence\n"
        f"element face {len(faces)}\n"
        f"property list {count_type} uint vertex_indices\n"
        "end_header\n"
    ).encode("ascii")
    vchar = {"double": "d", "float": "f", "short": "h"}[vtype]
    cchar = {"uchar": "B", "int": "i"}[count_type]
    cast = int if vchar == "h" else float
    body = b"".join(
        struct.pack(f"{order}{vchar}{vchar}{vchar}f", *(cast(c) for c in v), 0.5) for v in vertices
    )
    for face in faces:
        body += struct.pack(f"{order}{cchar}", len(face))
        body += struct.pack(f"{order}{len(face)}I", *face)
    path.write_bytes(header + body)
    return path


def _obj(path: Path, text: str) -> Path:
    path.write_text(text, encoding="ascii")
    return path


# ----------------------------------------------------------------- PLY


def test_ascii_ply_with_quads(tmp_path: Path) -> None:
    mesh = read_scan(_ascii_ply(tmp_path / "a.ply", CUBE, QUADS))
    assert mesh.format == "ply"
    assert mesh.vertices.dtype == np.float32 and mesh.vertices.shape == (8, 3)
    np.testing.assert_allclose(mesh.vertices, CUBE)
    assert mesh.faces is not None and mesh.faces.dtype == np.int32
    assert mesh.faces.tolist() == [[0, 1, 2], [0, 2, 3], [4, 5, 6], [4, 6, 7]]


def test_ascii_ply_skips_other_elements(tmp_path: Path) -> None:
    path = tmp_path / "b.ply"
    text = (
        "ply\nformat ascii 1.0\nelement camera 1\nproperty float fov\n"
        "element vertex 3\nproperty double x\nproperty double y\nproperty double z\n"
        "end_header\n70.0\n0 0 0\n1 0 0\n0 1 0\n"
    )
    path.write_text(text, encoding="ascii")
    mesh = read_scan(path)
    assert mesh.vertices.shape == (3, 3)
    assert mesh.faces is None


def test_ascii_ply_with_crlf(tmp_path: Path) -> None:
    path = _ascii_ply(tmp_path / "c.ply", CUBE, TRIS)
    path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
    mesh = read_scan(path)
    assert mesh.faces is not None and mesh.faces.shape == (2, 3)


@pytest.mark.parametrize("order", ["<", ">"])
def test_binary_ply_triangles(tmp_path: Path, order: str) -> None:
    mesh = read_scan(_binary_ply(tmp_path / "t.ply", CUBE, TRIS, order))
    np.testing.assert_allclose(mesh.vertices, CUBE)
    assert mesh.faces is not None and mesh.faces.tolist() == TRIS


@pytest.mark.parametrize("order", ["<", ">"])
def test_binary_ply_mixed_polygons(tmp_path: Path, order: str) -> None:
    faces = [[0, 1, 2], [4, 5, 6, 7], [1, 2]]
    mesh = read_scan(_binary_ply(tmp_path / "m.ply", CUBE, faces, order, count_type="int"))
    assert mesh.faces is not None
    assert mesh.faces.tolist() == [[0, 1, 2], [4, 5, 6], [4, 6, 7]]


@pytest.mark.parametrize("vtype", ["float", "short"])
def test_binary_ply_vertex_types(tmp_path: Path, vtype: str) -> None:
    mesh = read_scan(_binary_ply(tmp_path / "v.ply", CUBE * 2, QUADS, "<", vtype=vtype))
    np.testing.assert_allclose(mesh.vertices, CUBE * 2)
    assert mesh.faces is not None and len(mesh.faces) == 4


def test_ply_point_cloud_without_faces(tmp_path: Path) -> None:
    path = tmp_path / "p.ply"
    header = (
        b"ply\nformat binary_little_endian 1.0\nelement vertex 2\n"
        b"property float x\nproperty float y\nproperty float z\nend_header\n"
    )
    path.write_bytes(header + struct.pack("<6f", 1, 2, 3, 4, 5, 6))
    mesh = read_scan(path)
    assert mesh.faces is None
    assert mesh.vertices.tolist() == [[1, 2, 3], [4, 5, 6]]


def test_mesh_arrays_are_read_only(tmp_path: Path) -> None:
    mesh = read_scan(_ascii_ply(tmp_path / "a.ply", CUBE, TRIS))
    with pytest.raises(ValueError):
        mesh.vertices[0, 0] = 9.0


@pytest.mark.parametrize(
    "content",
    [
        b"plx\nformat ascii 1.0\nend_header\n",
        b"ply\nformat ascii 1.0\nelement vertex 1\nproperty float x\n",
        b"ply\nformat binary_middle_endian 1.0\nend_header\n",
        b"ply\nelement vertex 1\nproperty float x\nproperty float y\nproperty float z\nend_header\n",
        b"ply\nformat ascii 1.0\nelement vertex 1\nproperty quad x\nend_header\n0\n",
        b"ply\nformat ascii 1.0\nproperty float x\nend_header\n",
        b"ply\nformat ascii 1.0\nelement vertex one\nend_header\n",
        b"ply\nformat ascii 1.0\nelement vertex 1\nproperty float x\nend_header\n0\n",
        b"ply\nformat ascii 1.0\nelement face 0\nend_header\n",
        b"ply\nformat ascii 1.0\nbogus line\nend_header\n",
    ],
)
def test_corrupt_ply_headers(tmp_path: Path, content: bytes) -> None:
    path = tmp_path / "bad.ply"
    path.write_bytes(content)
    with pytest.raises(ScanError):
        read_scan(path)


def test_truncated_binary_body(tmp_path: Path) -> None:
    path = _binary_ply(tmp_path / "t.ply", CUBE, TRIS, "<")
    path.write_bytes(path.read_bytes()[:-30])
    with pytest.raises(ScanError, match="ends before"):
        read_scan(path)


def test_ascii_body_too_short(tmp_path: Path) -> None:
    path = _ascii_ply(tmp_path / "a.ply", CUBE, TRIS)
    text = path.read_text(encoding="ascii").splitlines()
    path.write_text("\n".join(text[:-3]) + "\n", encoding="ascii")
    with pytest.raises(ScanError):
        read_scan(path)


def test_ascii_value_not_a_number(tmp_path: Path) -> None:
    path = _ascii_ply(tmp_path / "a.ply", CUBE, TRIS)
    path.write_text(path.read_text(encoding="ascii").replace("0.0 0.0 0.0", "a b c", 1))
    with pytest.raises(ScanError):
        read_scan(path)


def test_face_index_out_of_range(tmp_path: Path) -> None:
    with pytest.raises(ScanError, match="does not exist"):
        read_scan(_binary_ply(tmp_path / "f.ply", CUBE, [[0, 1, 99]], "<"))


def test_non_finite_vertex(tmp_path: Path) -> None:
    bad = CUBE.copy()
    bad[2, 1] = np.nan
    with pytest.raises(ScanError, match="finite"):
        read_scan(_binary_ply(tmp_path / "n.ply", bad, TRIS, "<"))


# ----------------------------------------------------------------- OBJ


def test_obj_all_face_forms(tmp_path: Path) -> None:
    text = (
        "# a comment\nmtllib room.mtl\no room\n"
        "v 0 0 0\nv 1 0 0\nv 1 1 0\nv 0 1 0 1.0\n"
        "vt 0 0\nvn 0 0 1\n"
        "f 1 2 3\n"
        "f 1/1 3/1 4/1\n"
        "f 1//1 2//1 3//1\n"
        "f 1/1/1 2/1/1 3/1/1 4/1/1\n"
    )
    mesh = read_scan(_obj(tmp_path / "r.obj", text))
    assert mesh.format == "obj"
    assert mesh.vertices.shape == (4, 3)
    assert mesh.faces is not None
    assert mesh.faces.tolist() == [[0, 1, 2], [0, 2, 3], [0, 1, 2], [0, 1, 2], [0, 2, 3]]


def test_obj_negative_indices(tmp_path: Path) -> None:
    text = "v 0 0 0\nv 1 0 0\nv 1 1 0\nf -3 -2 -1\nv 0 1 0\nf -4 -2 -1\n"
    mesh = read_scan(_obj(tmp_path / "n.obj", text))
    assert mesh.faces is not None and mesh.faces.tolist() == [[0, 1, 2], [0, 2, 3]]


def test_obj_point_cloud(tmp_path: Path) -> None:
    mesh = read_scan(_obj(tmp_path / "p.obj", "v 1 2 3\nv 4 5 6\n"))
    assert mesh.faces is None
    assert mesh.vertices.tolist() == [[1, 2, 3], [4, 5, 6]]


@pytest.mark.parametrize(
    "text",
    [
        "v 1 2\n",
        "v 1 two 3\n",
        "v 0 0 0\nf 1 2 x\n",
        "v 0 0 0\nf 0 1 1\n",
        "v 0 0 0\nv 1 0 0\nf 1 2 5\n",
        "# nothing here\n",
    ],
)
def test_corrupt_obj(tmp_path: Path, text: str) -> None:
    with pytest.raises(ScanError):
        read_scan(_obj(tmp_path / "bad.obj", text))


# ----------------------------------------------------------------- limits and hashing


def test_unsupported_extension(tmp_path: Path) -> None:
    path = tmp_path / "room.stl"
    path.write_bytes(b"solid")
    with pytest.raises(ScanError, match="PLY or OBJ"):
        read_scan(path)


def test_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ScanError):
        read_scan(tmp_path / "gone.ply")


def test_size_limit_checked_before_reading(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = _ascii_ply(tmp_path / "a.ply", CUBE, TRIS)
    opened: list[Path] = []
    original = Path.open

    def spy(self: Path, *args: object, **kwargs: object):  # type: ignore[no-untyped-def]
        opened.append(self)
        return original(self, *args, **kwargs)  # type: ignore[call-overload]

    monkeypatch.setattr(Path, "open", spy)
    with pytest.raises(ScanError, match="larger than 10 bytes"):
        read_scan(path, max_bytes=10)
    assert opened == []


def test_vertex_limit_ply(tmp_path: Path) -> None:
    with pytest.raises(ScanError, match="more than 7 vertices"):
        read_scan(_binary_ply(tmp_path / "t.ply", CUBE, TRIS, "<"), max_vertices=7)
    assert read_scan(_binary_ply(tmp_path / "u.ply", CUBE, TRIS, "<"), max_vertices=8)


def test_vertex_limit_obj(tmp_path: Path) -> None:
    text = "".join(f"v {i} 0 0\n" for i in range(10))
    with pytest.raises(ScanError, match="more than 9 vertices"):
        read_scan(_obj(tmp_path / "v.obj", text), max_vertices=9)


@pytest.mark.parametrize("kind", ["ply", "obj"])
def test_cancellation(tmp_path: Path, kind: str) -> None:
    if kind == "ply":
        path = _ascii_ply(tmp_path / "a.ply", CUBE, TRIS)
    else:
        path = _obj(tmp_path / "a.obj", "v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n")
    with pytest.raises(ScanCancelledError):
        read_scan(path, cancelled=lambda: True)


def test_cancellation_after_reading(tmp_path: Path) -> None:
    calls = {"n": 0}

    def later() -> bool:
        calls["n"] += 1
        return calls["n"] > 2

    with pytest.raises(ScanCancelledError):
        read_scan(_ascii_ply(tmp_path / "a.ply", CUBE, TRIS), cancelled=later)


def test_sha256(tmp_path: Path) -> None:
    path = _binary_ply(tmp_path / "t.ply", CUBE, TRIS, ">")
    expected = hashlib.sha256(path.read_bytes()).hexdigest()
    assert read_scan(path).sha256 == expected
    assert file_sha256(path) == expected


def test_units_note_is_set(tmp_path: Path) -> None:
    mesh = read_scan(_obj(tmp_path / "p.obj", "v 1 2 3\n"))
    assert "units" in mesh.source_units_note


# ----------------------------------------------------------------- placement


def test_place_scan_units() -> None:
    origin = Point(0, 0, 0)
    for units, scale in [("m", 1), ("cm", 0.01), ("mm", 0.001), ("in", 0.0254), ("ft", 0.3048)]:
        placed = place_scan(
            np.array([[100.0, 0, 0]]), units=units, up_axis="z", yaw_deg=0, offset=origin
        )
        np.testing.assert_allclose(placed, [[100 * scale, 0, 0]])


@pytest.mark.parametrize(
    ("up", "expected"),
    [
        ("z", [1, 2, 3]),
        ("-z", [1, -2, -3]),
        ("y", [1, -3, 2]),
        ("-y", [1, 3, -2]),
        ("x", [-3, 2, 1]),
        ("-x", [3, 2, -1]),
    ],
)
def test_place_scan_up_axis(up: str, expected: list[float]) -> None:
    placed = place_scan(
        np.array([[1.0, 2.0, 3.0]]), units="m", up_axis=up, yaw_deg=0, offset=Point(0, 0, 0)
    )
    np.testing.assert_allclose(placed[0], expected, atol=1e-12)


@pytest.mark.parametrize("up", ["z", "-z", "y", "-y", "x", "-x"])
def test_up_axis_goes_to_plus_z(up: str) -> None:
    axis = {"x": 0, "y": 1, "z": 2}[up[-1]]
    vector = np.zeros((1, 3))
    vector[0, axis] = -1.0 if up.startswith("-") else 1.0
    placed = place_scan(vector, units="m", up_axis=up, yaw_deg=0, offset=Point(0, 0, 0))
    np.testing.assert_allclose(placed[0], [0, 0, 1], atol=1e-12)


def test_place_scan_yaw_and_offset() -> None:
    placed = place_scan(
        np.array([[1.0, 0.0, 0.5]]), units="m", up_axis="z", yaw_deg=90, offset=Point(2, 3, 0.1)
    )
    np.testing.assert_allclose(placed[0], [2.0, 4.0, 0.6], atol=1e-12)


def test_place_scan_does_not_mutate_input() -> None:
    vertices = CUBE.astype(np.float32)
    before = vertices.copy()
    place_scan(vertices, units="cm", up_axis="y", yaw_deg=30, offset=Point(1, 1, 1))
    np.testing.assert_array_equal(vertices, before)


@pytest.mark.parametrize(
    ("units", "up", "yaw"), [("km", "z", 0.0), ("m", "w", 0.0), ("m", "z", float("nan"))]
)
def test_place_scan_refuses_bad_choices(units: str, up: str, yaw: float) -> None:
    with pytest.raises(ScanError):
        place_scan(CUBE, units=units, up_axis=up, yaw_deg=yaw, offset=Point(0, 0, 0))


def test_align_to_floor_corner() -> None:
    vertices = CUBE + np.array([-2.0, 3.0, 0.5])
    offset = align_to_floor_corner(vertices)
    assert offset == Point(2.0, -3.0, -0.5)
    placed = place_scan(vertices, units="m", up_axis="z", yaw_deg=0, offset=offset)
    np.testing.assert_allclose(placed.min(axis=0), [0, 0, 0], atol=1e-12)
    with pytest.raises(ScanError):
        align_to_floor_corner(np.zeros((0, 3)))


# ----------------------------------------------------------------- thinning


def test_voxel_thin_one_point_per_voxel() -> None:
    rng = np.random.default_rng(3)
    points = rng.uniform(0, 1, (5000, 3))
    thinned = voxel_thin(points, 0.25, 10_000)
    assert len(thinned) == 64
    cells = np.floor(thinned / 0.25).astype(int)
    assert len(np.unique(cells, axis=0)) == len(thinned)


def test_voxel_thin_is_deterministic_and_keeps_first_points() -> None:
    points = np.array([[0.0, 0, 0], [0.01, 0, 0], [1.0, 0, 0], [1.02, 0, 0]])
    thinned = voxel_thin(points, 0.1, 100)
    np.testing.assert_array_equal(thinned, points[[0, 2]])
    np.testing.assert_array_equal(voxel_thin(points, 0.1, 100), thinned)


def test_voxel_thin_respects_max_points() -> None:
    rng = np.random.default_rng(4)
    points = rng.uniform(0, 4, (20000, 3))
    thinned = voxel_thin(points, 0.05, 500)
    assert 0 < len(thinned) <= 500


def test_voxel_thin_edge_cases() -> None:
    assert voxel_thin(np.zeros((0, 3)), 0.1, 10).shape == (0, 3)
    with pytest.raises(ScanError):
        voxel_thin(CUBE, 0.0, 10)
    with pytest.raises(ScanError):
        voxel_thin(CUBE, 0.1, 0)
    before = CUBE.copy()
    voxel_thin(CUBE, 0.5, 3)
    np.testing.assert_array_equal(CUBE, before)
