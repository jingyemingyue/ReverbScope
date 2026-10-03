"""Execute the documented offline recipe and verify its artifact contracts."""

from __future__ import annotations

import csv
import hashlib
import json
import runpy
import shlex
import sys
import zipfile
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from roomscope.audio import backend, devices
from roomscope.cli.main import COMMANDS, main
from roomscope.schemas import load_schema

ROOT = Path(__file__).resolve().parents[2]


def _validate(name: str, path: Path) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    Draft202012Validator(load_schema(name)).validate(payload)


def test_documented_workflow_uses_only_synthetic_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("the offline recipe must not access a real audio device or launch a GUI")

    get_backend = backend.get_backend

    def fake_only(name: str | None = None):
        assert name == "fake", "device commands must explicitly select --backend fake"
        return get_backend(name)

    monkeypatch.setattr(backend, "get_backend", fake_only)
    monkeypatch.setattr(devices, "sounddevice_module", forbidden)
    monkeypatch.setitem(COMMANDS, "gui", forbidden)
    monkeypatch.setitem(sys.modules, "sounddevice", None)
    monkeypatch.chdir(tmp_path)

    extract = runpy.run_path(str(ROOT / "scripts/check_cli_docs.py"))["commands"]
    markdown = (ROOT / "docs/OFFLINE_CHECKS.md").read_text(encoding="utf-8")
    seen: set[str] = set()
    for line, command in extract(markdown):
        argv = shlex.split(command, comments=True)
        if not argv or argv[0] != "roomscope":
            continue
        sources: dict[Path, bytes] = {}
        if argv[1] == "analyze":
            for option in ("--recording", "--sweep"):
                path = Path(argv[argv.index(option) + 1])
                sources[path] = hashlib.sha256(path.read_bytes()).digest()
        capsys.readouterr()
        assert main(argv[1:]) == 0, f"OFFLINE_CHECKS.md:{line}: {command}"
        captured = capsys.readouterr()
        assert "Traceback" not in captured.err, command
        for path, digest in sources.items():
            assert hashlib.sha256(path.read_bytes()).digest() == digest, path
        if argv[1:3] == ["--format", "json"] or argv[1:5] == [
            "--backend",
            "fake",
            "--format",
            "json",
        ]:
            payload = json.loads(captured.out)
            assert isinstance(payload, dict), command
            if "session" in payload:
                Draft202012Validator(load_schema("session")).validate(payload.pop("session"))
                payload.pop("findings", None)
                Draft202012Validator(load_schema("result")).validate(payload)
        seen.update(arg for arg in argv if arg in COMMANDS)

    assert {
        "devices",
        "doctor",
        "demo",
        "analyze",
        "show",
        "compare",
        "export",
        "session",
        "project",
        "measure",
    } <= seen
    for session in (
        "offline-import",
        "offline-take",
        "offline-demo/position-a",
        "offline-demo/position-b",
    ):
        _validate("session", tmp_path / session / "session.json")
        _validate("result", tmp_path / session / "result.json")
    _validate("comparison", tmp_path / "offline-comparison.json")
    _validate("project", tmp_path / "offline-project/project.json")
    _validate("sidecar", tmp_path / "offline-demo/sweep.roomscope-sweep.json")
    csv_files = list((tmp_path / "offline-csv").glob("*.csv"))
    assert csv_files
    for path in csv_files:
        with path.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.reader(handle))
        assert len(rows) > 1 and all(len(row) == len(rows[0]) for row in rows), path
    with zipfile.ZipFile(tmp_path / "offline-report.zip") as archive:
        names = archive.namelist()
        assert any(Path(name).name == "session.json" for name in names)
        assert any(Path(name).name == "result.json" for name in names)
        assert not any(Path(name).suffix.lower() == ".wav" for name in names)
