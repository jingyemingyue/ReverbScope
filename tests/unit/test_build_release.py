"""scripts/build_release.py builds the same files, under the same names, as
the release workflow's bundle job, so a local build can be attached to the
draft Release in its place."""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path
from types import ModuleType

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
    values = {"skip_tests": False, "python_dist": False, "allow_unlocked": False}
    values.update(overrides)
    return argparse.Namespace(**values)


@pytest.mark.parametrize(
    ("target", "archives", "checksums"),
    [
        (
            ("Linux", "X64", "x86_64"),
            ("ReverbScope-Desktop-Linux-x86_64.tar.gz", "ReverbScope-Terminal-Linux-x86_64.tar.gz"),
            "SHA256SUMS-Linux-X64",
        ),
        (
            ("Windows", "X64", "AMD64"),
            (
                "ReverbScope-Desktop-Windows-x64-Setup.exe",
                "ReverbScope-Desktop-Windows-x64.zip",
                "ReverbScope-Terminal-Windows-x64.zip",
            ),
            "SHA256SUMS-Windows-X64",
        ),
        (
            ("macOS", "ARM64", "arm64"),
            ("ReverbScope-Desktop-macOS-arm64.dmg", "ReverbScope-Terminal-macOS-arm64.tar.gz"),
            "SHA256SUMS-macOS-ARM64",
        ),
        (
            ("macOS", "X64", "x86_64"),
            ("ReverbScope-Desktop-macOS-x86_64.dmg", "ReverbScope-Terminal-macOS-x86_64.tar.gz"),
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
        "# comment\nnumpy==0.0.1\nreverbscope-surely-not-installed==1.0\n", encoding="utf-8"
    )
    problems = MODULE.lock_mismatches(lock)
    assert any(p.startswith("numpy: ") and "lock pins 0.0.1" in p for p in problems)
    assert any("reverbscope-surely-not-installed: not installed" in p for p in problems)


def test_checksum_lines_use_sha256sum_format(tmp_path: Path) -> None:
    path = tmp_path / "a.zip"
    path.write_bytes(b"abc")
    assert MODULE.checksum_lines([path]) == (
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad  a.zip\n"
    )
