"""Imported PLY/OBJ room scans. No lidar is attached to this VM."""

from __future__ import annotations

from pathlib import Path

import pytest

from roomscope.core.pipeline import Reference, analyze, synthetic_recording
from roomscope.io.scan import (
    MAX_STORED_POINTS,
    OBJ_FORMAT_REFERENCE,
    PLY_FORMAT_REFERENCE,
    ScanError,
    attach_room_scan,
    load_scan,
    load_scan_optional,
)
from roomscope.models.result import AnalysisResult
from tests.conftest import make_rir

FIXTURE = Path("tests/fixtures/synthetic_room.ply")


def test_checked_in_ply_is_a_synthetic_shoebox_not_a_lidar_capture() -> None:
    scan = load_scan(FIXTURE)
    assert scan.format == "ply"
    assert scan.source_name == "synthetic_room.ply"
    assert scan.point_count == 43
    assert scan.points_m.shape == (43, 3)
    assert scan.bounds_min_m == pytest.approx((0.0, 0.0, 0.0))
    assert scan.bounds_max_m == pytest.approx((4.0, 3.0, 2.5))
    assert len(scan.faces) == 12
    assert "paulbourke.net/dataformats/ply" in scan.format_reference
    assert scan.format_reference == PLY_FORMAT_REFERENCE
    joined = " ".join(scan.notes)
    assert "no lidar was attached" in joined
    text = FIXTURE.read_text(encoding="utf-8")
    assert "Not a lidar capture" in text
    assert text.startswith("ply\nformat ascii 1.0\n")


def test_obj_mesh_and_optional_empty_path(tmp_path: Path) -> None:
    path = tmp_path / "box.obj"
    path.write_text(
        "# RoomScope synthetic OBJ. Not a lidar capture.\n"
        "v 0 0 0\n"
        "v 1 0 0\n"
        "v 1 1 0\n"
        "v 0 1 0\n"
        "v 0 0 2\n"
        "f 1 2 3\n"
        "f 1 3 4\n",
        encoding="utf-8",
    )
    scan = load_scan(path)
    assert scan.format == "obj"
    assert scan.point_count == 5
    assert scan.bounds_max_m[2] == pytest.approx(2.0)
    assert scan.faces[0] == (0, 1, 2)
    assert scan.format_reference == OBJ_FORMAT_REFERENCE
    assert load_scan_optional(None) is None
    assert load_scan_optional("") is None


def test_binary_ply_and_unknown_suffix_are_refused(tmp_path: Path) -> None:
    binary = tmp_path / "cloud.ply"
    binary.write_bytes(
        b"ply\nformat binary_little_endian 1.0\n"
        b"element vertex 3\nproperty float x\nproperty float y\n"
        b"property float z\nend_header\n" + b"\x00" * 36
    )
    with pytest.raises(ScanError, match="binary PLY"):
        load_scan(binary)
    other = tmp_path / "room.xyz"
    other.write_text("0 0 0\n", encoding="utf-8")
    with pytest.raises(ScanError, match=r"must be a \.ply or \.obj"):
        load_scan(other)
    with pytest.raises(ScanError, match="not found"):
        load_scan(tmp_path / "missing.ply")


def test_scan_is_downsampled_for_the_picture(tmp_path: Path) -> None:
    n = MAX_STORED_POINTS + 250
    path = tmp_path / "dense.ply"
    body = [
        "ply",
        "format ascii 1.0",
        f"element vertex {n}",
        "property float x",
        "property float y",
        "property float z",
        "end_header",
    ]
    body.extend(f"{i} 0 0" for i in range(n))
    path.write_text("\n".join(body) + "\n", encoding="utf-8")
    scan = load_scan(path)
    assert scan.point_count == n
    assert scan.points_m.shape[0] <= MAX_STORED_POINTS
    assert any("downsampled" in note for note in scan.notes)


def test_attach_room_scan_on_synthetic_analysis(short_sweep) -> None:
    result = analyze(
        synthetic_recording(
            short_sweep,
            make_rir(short_sweep.sample_rate, rt60_s=0.3, reflections=[(0.018, 0.35)]),
            noise_rms=1e-5,
        ),
        Reference.from_settings(short_sweep),
    )
    attached = attach_room_scan(result, FIXTURE)
    assert attached.room_scan is not None
    assert attached.room_scan.source_name == "synthetic_room.ply"
    payload = attached.to_dict(include_curves=False)
    loaded = AnalysisResult.from_dict(payload)
    assert loaded.room_scan is not None
    assert loaded.room_scan.point_count == 43
    assert attach_room_scan(result, None).room_scan is None
    from jsonschema import Draft202012Validator

    from roomscope.models.session import MeasurementSession
    from roomscope.schemas import load_schema

    Draft202012Validator(load_schema("result")).validate(attached.to_dict())
    Draft202012Validator(load_schema("session")).validate(
        MeasurementSession(scan_path=str(FIXTURE)).to_dict()
    )
