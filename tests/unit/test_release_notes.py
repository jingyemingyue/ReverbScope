"""The user-facing download text names the files a Release really carries.

The release notes (packaging/release-notes-header.md), README and the
installation guides tell people which file to download. A renamed artifact
in scripts/release_draft.py must fail here rather than leave a download
instruction pointing at a file that no longer exists.
"""

from __future__ import annotations

import importlib.util
import re
import sys
import tomllib
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]
HEADER = ROOT / "packaging" / "release-notes-header.md"
DOWNLOAD_DOCS = (
    ROOT / "README.md",
    ROOT / "README.zh-CN.md",
    ROOT / "docs" / "INSTALLATION.md",
    ROOT / "docs" / "INSTALLATION.zh-CN.md",
)
RELEASES_PAGE = "https://github.com/jingyemingyue/RoomScope/releases"
#: Programs inside the Windows ZIP / installed folder (packaging/roomscope.spec).
IN_BUNDLE = {"roomscope-gui.exe", "roomscope.exe"}


def _release_draft() -> ModuleType:
    path = ROOT / "scripts" / "release_draft.py"
    spec = importlib.util.spec_from_file_location("release_draft_for_notes", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _version() -> str:
    with (ROOT / "pyproject.toml").open("rb") as fh:
        return str(tomllib.load(fh)["project"]["version"])


def _archives() -> set[str]:
    module = _release_draft()
    return {name for names in module.CHECKSUM_FILES.values() for name in names}


def _notes() -> str:
    # The same substitution as the draft-release job in release.yml.
    return HEADER.read_text(encoding="utf-8").replace("{version}", _version())


def test_release_notes_open_with_the_version_and_the_pre_release_line() -> None:
    lines = [line for line in _notes().splitlines() if line.strip()]
    assert lines[0] == f"## RoomScope v{_version()}"
    assert "Early public pre-release for testing." in lines[1]


def test_release_notes_name_every_download_that_the_release_carries() -> None:
    notes = _notes()
    for name in sorted(_archives() | set(_release_draft().python_dist_files(_version()))):
        assert f"`{name}`" in notes, name
    assert "{version}" not in notes


@pytest.mark.parametrize("section", ["### Download", "### What works", "### Important limitations"])
def test_release_notes_have_the_user_sections_in_order(section: str) -> None:
    notes = _notes()
    order = ["### Download", "### What works", "### Important limitations"]
    assert section in notes
    positions = [notes.index(s) for s in order]
    assert positions == sorted(positions)


def test_release_notes_are_honest_about_signing_and_hardware() -> None:
    notes = _notes()
    for fact in (
        "Current builds are unsigned development/pre-release builds",
        "Hardware validation is still in progress",
        "should not yet be treated as hardware-validated",
        "This is a pre-release",
        "not notarized",
        "Authenticode",
        "Open Anyway",
        "Run anyway",
    ):
        assert fact in notes, fact
    # Never tell people to switch off macOS protections.
    assert "spctl --master-disable" not in notes
    assert "csrutil" not in notes


@pytest.mark.parametrize("doc", DOWNLOAD_DOCS, ids=lambda p: p.name)
def test_download_docs_use_real_file_names_and_the_stable_releases_page(doc: Path) -> None:
    text = doc.read_text(encoding="utf-8")
    assert RELEASES_PAGE in text
    # A draft or per-asset URL would break after publishing or the next release.
    assert "/releases/tag/untagged-" not in text
    assert "/releases/download/" not in text
    # /releases/latest skips pre-releases, so it must not be the download link.
    assert "/releases/latest" not in text
    for name in ("RoomScope-macos-arm64.dmg", "RoomScope-macos-x86_64.dmg"):
        assert name in text, name
    assert "roomscope-windows-x64.zip" in text
    assert "roomscope-gui.exe" in text
    mentioned = set(
        re.findall(r"`((?:RoomScope|roomscope)[\w.-]*\.(?:dmg|zip|exe|tar\.gz))`", text)
    )
    unknown = mentioned - _archives() - IN_BUNDLE
    assert not unknown, sorted(unknown)
    flat = " ".join(re.sub(r"(?m)^>", "", text).split())
    for fact in ("Gatekeeper", "SIP" if "zh-CN" in doc.name else "System Integrity Protection"):
        assert fact in flat, fact


def test_the_windows_program_names_come_from_the_bundle_spec() -> None:
    spec = (ROOT / "packaging" / "roomscope.spec").read_text(encoding="utf-8")
    from roomscope.__main__ import GUI_LAUNCHER_STEM

    assert GUI_LAUNCHER_STEM == "roomscope-gui"
    assert "GUI_LAUNCHER_STEM" in spec or '"roomscope-gui"' in spec


def test_readme_offers_the_download_before_the_developer_install() -> None:
    for name in ("README.md", "README.zh-CN.md"):
        text = (ROOT / name).read_text(encoding="utf-8")
        download = text.index(RELEASES_PAGE)
        assert download < text.index("git clone"), name
        assert download < text.index("pip install -e"), name
        # Within the first screen of the README.
        assert text[:download].count("\n") < 30, name
