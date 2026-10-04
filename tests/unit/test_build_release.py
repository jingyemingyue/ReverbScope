"""scripts/build_release.py builds the same files, under the same names, as
the release workflow's bundle job, so a local build can be attached to the
draft Release in its place."""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest


def _load() -> ModuleType:
    path = Path("scripts") / "build_release.py"
    spec = importlib.util.spec_from_file_location("build_release", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["build_release"] = module
    spec.loader.exec_module(module)
    return module


MODULE = _load()
WORKFLOW = Path(".github/workflows/release.yml").read_text(encoding="utf-8")


def _args(**overrides: bool) -> argparse.Namespace:
    values = {
        "skip_tests": False,
        "python_dist": False,
        "allow_unlocked": False,
        "no_installer": False,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


@pytest.mark.parametrize(
    ("target", "archives", "checksums"),
    [
        (
            ("Linux", "X64", "x86_64"),
            ("RoomScope-Desktop-Linux-x86_64.tar.gz", "RoomScope-Terminal-Linux-x86_64.tar.gz"),
            "SHA256SUMS-Linux-X64",
        ),
        (
            ("Windows", "X64", "AMD64"),
            (
                "RoomScope-Desktop-Windows-x64-Setup.exe",
                "RoomScope-Desktop-Windows-x64.zip",
                "RoomScope-Terminal-Windows-x64.zip",
            ),
            "SHA256SUMS-Windows-X64",
        ),
        (
            ("macOS", "ARM64", "arm64"),
            ("RoomScope-Desktop-macOS-arm64.dmg", "RoomScope-Terminal-macOS-arm64.tar.gz"),
            "SHA256SUMS-macOS-ARM64",
        ),
        (
            ("macOS", "X64", "x86_64"),
            ("RoomScope-Desktop-macOS-x86_64.dmg", "RoomScope-Terminal-macOS-x86_64.tar.gz"),
            "SHA256SUMS-macOS-X64",
        ),
    ],
)
def test_file_names_match_the_release_workflow(
    target: tuple[str, str, str], archives: tuple[str, ...], checksums: str
) -> None:
    built = MODULE.Target(*target)
    assert built.archives == archives
    assert built.checksum_name == checksums
    # The workflow writes each runner's checksum file from the same manifest.
    assert "rd.CHECKSUM_FILES[sums_name]" in WORKFLOW


@pytest.mark.parametrize(
    ("target", "expected"),
    [
        (("Linux", "X64", "x86_64"), "Linux archive (Desktop Edition)"),
        (("Windows", "X64", "AMD64"), "Windows installer"),
        (("macOS", "ARM64", "arm64"), "macOS disk image"),
    ],
)
def test_plan_follows_the_workflow_steps(
    tmp_path: Path, target: tuple[str, str, str], expected: str
) -> None:
    steps = MODULE.plan(MODULE.Target(*target), _args(), tmp_path)
    names = [step.name for step in steps]
    for name in (
        "License bundle",
        "PyInstaller",
        "Copy licenses and remove disallowed modules",
        "Smoke frozen binary (Desktop Edition)",
        "Terminal Edition (command line only, no Qt)",
        "Smoke Terminal Edition",
        expected,
        "Terminal Edition archive",
        "Checksums of distributable files",
    ):
        assert name in names
        if name != "PyInstaller":
            # Same step names as the workflow, so the two stay comparable.
            assert f"name: {name}" in WORKFLOW
    assert (
        names.index("PyInstaller")
        < names.index("Smoke frozen binary (Desktop Edition)")
        < names.index("Smoke Terminal Edition")
        < names.index(expected)
    )
    assert names[-1] == "Checksums of distributable files"


def test_optional_steps_are_skipped_by_default(tmp_path: Path) -> None:
    steps = {
        step.name: step
        for step in MODULE.plan(MODULE.Target("Linux", "X64", "x86_64"), _args(), tmp_path)
    }
    assert steps["sdist and wheel"].skipped
    assert steps["Test suite"].skipped is None
    skipped = MODULE.plan(
        MODULE.Target("Linux", "X64", "x86_64"), _args(skip_tests=True, python_dist=True), tmp_path
    )
    by_name = {step.name: step for step in skipped}
    assert by_name["Test suite"].skipped and by_name["sdist and wheel"].skipped is None


def test_lock_mismatches_names_each_difference(tmp_path: Path) -> None:
    lock = tmp_path / "bundle.lock"
    lock.write_text(
        "# comment\nnumpy==0.0.1\nroomscope-surely-not-installed==1.0\n", encoding="utf-8"
    )
    problems = MODULE.lock_mismatches(lock)
    assert any(p.startswith("numpy: ") and "lock pins 0.0.1" in p for p in problems)
    assert any("roomscope-surely-not-installed: not installed" in p for p in problems)


def test_checksum_lines_use_sha256sum_format(tmp_path: Path) -> None:
    path = tmp_path / "a.zip"
    path.write_bytes(b"abc")
    assert MODULE.checksum_lines([path]) == (
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad  a.zip\n"
    )


WINDOWS = ("Windows", "X64", "AMD64")


def _never(*argv: object, **kwargs: object) -> None:
    raise AssertionError(f"nothing may run here: {argv}")


def _steps(target: tuple[str, str, str], **overrides: bool) -> dict[str, Any]:
    steps = MODULE.plan(MODULE.Target(*target), _args(**overrides), Path("unused"))
    return {step.name: step for step in steps}


def test_a_missing_inno_setup_is_refused_before_anything_is_deleted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The earlier build's zips and SHA256SUMS were deleted first, then the
    script refused and built nothing."""
    previous = ("RoomScope-Desktop-Windows-x64.zip", "SHA256SUMS-Windows-X64")
    for name in previous:
        (tmp_path / name).write_bytes(b"previous build")
    monkeypatch.setattr(MODULE, "DIST", tmp_path)
    monkeypatch.setattr(MODULE, "current_target", lambda: MODULE.Target(*WINDOWS))
    monkeypatch.setattr(MODULE, "find_iscc", lambda: None)
    monkeypatch.setattr(MODULE, "lock_mismatches", lambda lock: [])
    monkeypatch.setattr(MODULE, "_python", _never)
    monkeypatch.setattr(MODULE, "_run", _never)
    assert MODULE.main([]) == 1
    assert "pass --no-installer" in capsys.readouterr().out
    assert all((tmp_path / name).read_bytes() == b"previous build" for name in previous)


def test_the_sdist_cleanup_keeps_another_runners_terminal_archive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Windows globs ignore case: ``roomscope-*.tar.gz`` matched
    ``RoomScope-Terminal-Linux-x86_64.tar.gz``."""
    names = (
        "RoomScope-Terminal-Linux-x86_64.tar.gz",
        "roomscope-0.1.tar.gz",
        "roomscope-0.1-py3-none-any.whl",
    )
    for name in names:
        (tmp_path / name).write_bytes(b"x")
    built: list[tuple[object, ...]] = []
    monkeypatch.setattr(MODULE, "DIST", tmp_path)
    monkeypatch.setattr(MODULE, "_python", lambda *argv, **kwargs: built.append(argv))
    _steps(("Linux", "X64", "x86_64"), python_dist=True)["sdist and wheel"].run()
    assert sorted(path.name for path in tmp_path.iterdir()) == [names[0]]
    assert built == [("-m", "build", "--outdir", tmp_path)]


def test_checksums_are_written_with_lf_and_allow_a_missing_installer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A SHA256SUMS with CRLF lines (Windows text mode) fails ``shasum -c``
    once the runners' files are merged."""
    archives = ("RoomScope-Desktop-Windows-x64.zip", "RoomScope-Terminal-Windows-x64.zip")
    for name in archives:
        (tmp_path / name).write_bytes(name.encode())
    monkeypatch.setattr(MODULE, "DIST", tmp_path)
    monkeypatch.setattr(MODULE, "find_iscc", lambda: None)
    step = _steps(WINDOWS, no_installer=True)["Checksums of distributable files"]
    step.run()
    written = (tmp_path / "SHA256SUMS-Windows-X64").read_bytes()
    assert b"\r\n" not in written
    assert [line.split(b"  ")[1] for line in written.splitlines()] == [
        name.encode() for name in archives
    ]
    (tmp_path / archives[0]).unlink()
    with pytest.raises(SystemExit, match="missing release files"):
        step.run()


def test_every_script_only_the_release_workflow_runs_triggers_it() -> None:
    """compile_bundle_lock.py (the sbom job) was missing from the path
    filters, so a pull request that broke it did not run the workflow."""
    import re

    import yaml

    release = yaml.safe_load(WORKFLOW)
    ci = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    run_by_release = set(re.findall(r"scripts/\w+\.py", yaml.safe_dump(release["jobs"])))
    only_release = run_by_release - set(re.findall(r"scripts/\w+\.py", ci))
    assert "scripts/compile_bundle_lock.py" in only_release
    triggers = release[True]  # YAML 1.1 reads the key "on" as True
    for event in ("push", "pull_request"):
        assert only_release <= set(triggers[event]["paths"]), event
