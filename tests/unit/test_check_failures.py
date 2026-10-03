"""Offline gates must fail when they cannot inspect their requested inputs."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _script(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("name", ["check_doc_links", "check_src_safety"])
@pytest.mark.parametrize("kind", ["missing", "file", "empty"])
def test_unscannable_roots_fail(
    name: str, kind: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "scan"
    if kind == "file":
        root.write_text("not a directory", encoding="utf-8")
    elif kind == "empty":
        root.mkdir()
    script = _script(name)
    assert script.main(["--root", str(root)]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert str(root) in captured.err
    assert "no " in captured.err if kind == "empty" else "directory not found" in captured.err
    assert "Traceback" not in captured.err


@pytest.mark.parametrize(
    ("name", "filename"), [("check_doc_links", "guide.md"), ("check_src_safety", "module.py")]
)
def test_invalid_utf8_is_a_located_failure(name: str, filename: str, tmp_path: Path) -> None:
    path = tmp_path / filename
    path.write_bytes(b"\xff")
    errors = _script(name).check(tmp_path)
    assert len(errors) == 1
    assert str(path) in errors[0] and "cannot read" in errors[0]


def test_python_syntax_error_reports_its_line(tmp_path: Path) -> None:
    path = tmp_path / "bad.py"
    path.write_text("# first line\nif True\n    pass\n", encoding="utf-8")
    errors = _script("check_src_safety").check(tmp_path)
    assert len(errors) == 1
    assert f"{path}:2: cannot parse Python" in errors[0]


def test_a_failed_read_does_not_hide_other_broken_links(tmp_path: Path) -> None:
    (tmp_path / "bad-encoding.md").write_bytes(b"\xff")
    (tmp_path / "broken-link.md").write_text("[missing](missing.md)", encoding="utf-8")
    errors = _script("check_doc_links").check(tmp_path)
    assert len(errors) == 2
    assert "cannot read Markdown" in errors[0]
    assert "broken link missing.md" in errors[1]
