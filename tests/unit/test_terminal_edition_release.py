"""Terminal Edition must ship with every release (macOS arm64/x86_64, Linux).

Maintainer decision (2026-10-29): keep the Terminal Edition; do not drop it
(#80 must not be ported). These asserts fail if a change removes the three
archives from the draft manifest, the local builder, the release workflow or
the release-note download tables.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
HEADER = ROOT / "packaging" / "release-notes-header.md"
HEADER_RC = ROOT / "packaging" / "release-notes-header-rc.md"

REQUIRED_TERMINAL_ARCHIVES = (
    "ReverbScope-Terminal-macOS-arm64.tar.gz",
    "ReverbScope-Terminal-macOS-x86_64.tar.gz",
    "ReverbScope-Terminal-Linux-x86_64.tar.gz",
)


def _release_draft() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "release_draft", ROOT / "scripts" / "release_draft.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["release_draft"] = module
    spec.loader.exec_module(module)
    return module


def _build_release() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "build_release", ROOT / "scripts" / "build_release.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["build_release"] = module
    spec.loader.exec_module(module)
    return module


rd = _release_draft()


def test_expected_assets_include_required_terminal_archives() -> None:
    assets = rd.expected_assets("0.5.0b6")
    missing = [name for name in REQUIRED_TERMINAL_ARCHIVES if name not in assets]
    assert not missing, f"Terminal Edition missing from expected_assets: {missing}"


def test_checksum_manifest_lists_required_terminal_archives() -> None:
    listed = {name for names in rd.CHECKSUM_FILES.values() for name in names}
    missing = [name for name in REQUIRED_TERMINAL_ARCHIVES if name not in listed]
    assert not missing, f"Terminal Edition missing from CHECKSUM_FILES: {missing}"
    assert "ReverbScope-Terminal-macOS-arm64.tar.gz" in rd.CHECKSUM_FILES["SHA256SUMS-macOS-ARM64"]
    assert "ReverbScope-Terminal-macOS-x86_64.tar.gz" in rd.CHECKSUM_FILES["SHA256SUMS-macOS-X64"]
    assert "ReverbScope-Terminal-Linux-x86_64.tar.gz" in rd.CHECKSUM_FILES["SHA256SUMS-Linux-X64"]


def test_build_release_names_required_terminal_archives() -> None:
    builder = _build_release()
    by_target = {
        ("macOS", "ARM64", "arm64"): "ReverbScope-Terminal-macOS-arm64.tar.gz",
        ("macOS", "X64", "x86_64"): "ReverbScope-Terminal-macOS-x86_64.tar.gz",
        ("Linux", "X64", "x86_64"): "ReverbScope-Terminal-Linux-x86_64.tar.gz",
    }
    for (system, arch, machine), archive in by_target.items():
        target = builder.Target(system, arch, machine)
        assert archive in target.archives, (target, target.archives)


def test_release_workflow_builds_and_uploads_terminal_edition() -> None:
    assert "REVERBSCOPE_PACKAGE: terminal" in WORKFLOW
    assert "name: Terminal Edition (command line only, no Qt)" in WORKFLOW
    assert "name: Smoke Terminal Edition" in WORKFLOW
    assert "name: Terminal Edition archive" in WORKFLOW
    assert "dist/ReverbScope-Terminal-Linux-x86_64.tar.gz" in WORKFLOW
    assert "ReverbScope-Terminal-macOS-$(uname -m).tar.gz" in WORKFLOW
    assert "dist/ReverbScope-Terminal-*" in WORKFLOW
    assert "--expect-package terminal" in WORKFLOW
    assert "--terminal" in WORKFLOW


@pytest.mark.parametrize("header", [HEADER, HEADER_RC], ids=["header", "header-rc"])
def test_release_notes_list_required_terminal_archives(header: Path) -> None:
    text = header.read_text(encoding="utf-8")
    assert "Terminal Edition" in text
    missing = [name for name in REQUIRED_TERMINAL_ARCHIVES if name not in text]
    assert not missing, f"{header.name} dropped Terminal Edition archives: {missing}"
