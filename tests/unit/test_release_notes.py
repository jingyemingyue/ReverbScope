"""The user-facing download text names the files a Release really carries.

The release notes (packaging/release-notes-header.md with the changelog the
draft job inserts), the READMEs, the installation and user guides, EDITIONS
and COMPATIBILITY tell people which file to download. A renamed artifact in
scripts/release_draft.py must fail here rather than leave a download
instruction pointing at a file that no longer exists, and a file name in the
docs that no Release carries fails as well.
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
#: Every other user document that names downloads.
NAMING_DOCS = (
    *DOWNLOAD_DOCS,
    ROOT / "docs" / "user-guide" / "en.md",
    ROOT / "docs" / "user-guide" / "zh-CN.md",
    ROOT / "docs" / "EDITIONS.md",
    ROOT / "docs" / "EDITIONS.zh-CN.md",
    ROOT / "docs" / "COMPATIBILITY.md",
    ROOT / "docs" / "COMPATIBILITY.zh-CN.md",
    ROOT / ".github" / "ISSUE_TEMPLATE" / "bug.yml",
    ROOT / ".github" / "ISSUE_TEMPLATE" / "bug-zh-CN.yml",
)
#: A download-like file name: ReverbScope-… / reverbscope-… with an archive suffix.
_ASSET_NAME = re.compile(
    r"(?<![\w/-])(?:ReverbScope|reverbscope)-[\w.-]*?\.(?:dmg|zip|exe|tar\.gz|whl)\b"
)
RELEASES_PAGE = "https://github.com/jingyemingyue/ReverbScope/releases"
#: Programs inside the Windows ZIP / installed folder (packaging/reverbscope.spec).
IN_BUNDLE = {"reverbscope-gui.exe", "reverbscope.exe"}


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


def _changelog_section() -> str:
    text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    match = re.search(r"(?ms)^## \[" + re.escape(_version()) + r"\].*?\n(.*?)(?=^## \[|\Z)", text)
    assert match is not None
    return match.group(1).strip()


def _notes() -> str:
    # The same substitutions as the draft-release job in release.yml.
    header = HEADER.read_text(encoding="utf-8").replace("{version}", _version())
    changes = re.sub(r"(?m)^### ", "#### ", _changelog_section())
    return header.replace("{changes}", "### Changes in this version\n\n" + changes)


def _downloads() -> tuple[str, ...]:
    return tuple(_release_draft().downloads(_version()))


def _known_names() -> set[str]:
    module = _release_draft()
    return set(module.expected_assets(_version())) | IN_BUNDLE


def test_release_notes_open_with_the_version_and_the_pre_release_line() -> None:
    lines = [line for line in _notes().splitlines() if line.strip()]
    assert lines[0] == f"## ReverbScope v{_version()}"
    assert "Beta 3, for testing." in lines[1]


def test_the_beta_header_names_the_beta_it_ships_with() -> None:
    """Version 0.5.0b3 went out with notes that said "Beta 2" because the
    header's number was not part of the version bump."""
    match = re.fullmatch(r"\d+\.\d+\.\d+b(\d+)", _version())
    if match is None:
        pytest.skip("not a beta version")
    number = match.group(1)
    text = HEADER.read_text(encoding="utf-8")
    assert f"**Beta {number}, for testing.**" in text
    assert f"This is beta {number} of the software" in text
    assert f"**This is beta {number}**" in text
    assert not re.search(rf"(?i)\bbeta (?!{number}\b)\d", text)


def test_release_notes_name_every_download_that_the_release_carries() -> None:
    notes = _notes()
    for name in _downloads():
        assert f"`{name}`" in notes, name
    assert "`SHA256SUMS`" in notes
    assert "{version}" not in notes and "{changes}" not in notes


RELEASE_ORDER = (
    "### Choose your edition",
    "#### 🖥 Desktop Edition",
    "#### ⌨️ Terminal Edition",
    "### Known limitations",
    "### Checksums",
    "### Changes in this version",
    "### Technical information",
)


def test_release_notes_put_the_user_choice_first() -> None:
    notes = _notes()
    positions = [notes.index(section) for section in RELEASE_ORDER]
    assert positions == sorted(positions)
    choose, technical = notes.index(RELEASE_ORDER[0]), notes.index(RELEASE_ORDER[-1])
    # Desktop files in the Desktop table, Terminal files in the Terminal table.
    desktop = notes[notes.index(RELEASE_ORDER[1]) : notes.index(RELEASE_ORDER[2])]
    terminal = notes[notes.index(RELEASE_ORDER[2]) : notes.index(RELEASE_ORDER[3])]
    for name in _archives():
        assert f"`{name}`" in (desktop if "-Desktop-" in name else terminal), name
    # Developer files come after the user sections, never before the choice.
    for developer_file in ("cyclonedx.sbom.json", "generated-bundle.lock", ".whl"):
        assert notes.index(developer_file) > technical, developer_file
    assert "SBOM" not in notes[:choose] and "wheel" not in notes[:choose]


def test_release_notes_are_honest_about_signing_and_hardware() -> None:
    notes = _notes()
    for fact in (
        "This is beta 3 of the software, not the 0.5.0 hardware release.",
        "hardware validation has not started",
        "should not yet be treated as hardware-validated",
        "This is beta 3",
        "not 0.5.0",
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
    for name in _archives():
        assert name in text, name
    assert "reverbscope-gui.exe" in text
    flat = " ".join(re.sub(r"(?m)^>", "", text).split())
    for fact in ("Gatekeeper", "SIP" if "zh-CN" in doc.name else "System Integrity Protection"):
        assert fact in flat, fact


def test_the_windows_program_names_come_from_the_bundle_spec() -> None:
    spec = (ROOT / "packaging" / "reverbscope.spec").read_text(encoding="utf-8")
    from reverbscope.__main__ import GUI_LAUNCHER_STEM

    assert GUI_LAUNCHER_STEM == "reverbscope-gui"
    assert "GUI_LAUNCHER_STEM" in spec or '"reverbscope-gui"' in spec


def test_readme_offers_the_download_before_the_developer_install() -> None:
    for name in ("README.md", "README.zh-CN.md"):
        text = (ROOT / name).read_text(encoding="utf-8")
        download = text.index(RELEASES_PAGE)
        assert download < text.index("git clone"), name
        assert download < text.index("pip install -e"), name
        # Within the first screen of the README.
        assert text[:download].count("\n") < 30, name


@pytest.mark.parametrize("doc", [*NAMING_DOCS, HEADER], ids=lambda p: p.name)
def test_every_file_name_in_the_docs_is_a_real_release_asset(doc: Path) -> None:
    """A renamed or removed download cannot linger in a download instruction."""
    text = _notes() if doc == HEADER else doc.read_text(encoding="utf-8")
    unknown = sorted(set(_ASSET_NAME.findall(text)) - _known_names())
    assert not unknown, unknown


def test_the_old_file_names_are_gone_from_user_documents() -> None:
    old = _release_draft().LEGACY_ASSETS - {"ReverbScope.dmg"}
    for doc in NAMING_DOCS:
        text = doc.read_text(encoding="utf-8")
        found = sorted(name for name in old if name in text)
        assert not found, (doc.name, found)


@pytest.mark.parametrize("name", ["README.md", "README.zh-CN.md"])
def test_readme_shows_both_editions_before_anything_else(name: str) -> None:
    text = (ROOT / name).read_text(encoding="utf-8")
    zh = "zh-CN" in name
    desktop = text.index("### 🖥 ")
    terminal = text.index("### ⌨️ ")
    compare = text.index("### 该选哪个？" if zh else "### Which one?")
    demo = text.index("## 30 秒体验" if zh else "## Try it in 30 seconds")
    first_section = text.index("\n## ")
    assert first_section < desktop < terminal < compare < demo
    # Every download of each edition is in its own table.
    for archive in _archives():
        table = text[desktop:terminal] if "-Desktop-" in archive else text[terminal:compare]
        assert archive in table, archive
    # Development, API and architecture come after the user sections.
    for later in ("git clone", "pip install -e", "Python API"):
        assert text.index(later) > demo, later
    # The pre-release status is stated in the download section; no stable release is claimed.
    assert ("预发布" if zh else "pre-release") in text[:desktop]
    assert "latest stable" not in text.lower()


@pytest.mark.parametrize(
    ("name", "screenshot"),
    [
        ("README.md", "docs/images/cli-demo.svg"),
        ("README.zh-CN.md", "docs/images/cli-demo.zh-CN.svg"),
    ],
)
def test_readme_uses_its_own_language_demo_and_labels_synthetic_images(
    name: str, screenshot: str
) -> None:
    text = (ROOT / name).read_text(encoding="utf-8")
    assert screenshot in text
    # Screenshots, not badges: one GUI hero and one terminal demo.
    images = [
        (alt, path)
        for alt, path in re.findall(r"!\[([^\]]*)\]\(([^)]+)\)", text)
        if path.startswith("docs/images/")
    ]
    assert len(images) == 2, images
    for alt, path in images:
        assert (ROOT / path).is_file(), path
        assert "synthetic" in alt.lower() or "合成" in alt, alt


# --- the release-candidate header (packaging/release-notes-header-rc.md) ---

HEADER_RC = ROOT / "packaging" / "release-notes-header-rc.md"


def _rc_notes(version: str = "0.5.0rc1") -> str:
    header = HEADER_RC.read_text(encoding="utf-8").replace("{version}", version)
    changes = re.sub(r"(?m)^### ", "#### ", _changelog_section())
    return header.replace("{changes}", "### Changes in this version\n\n" + changes)


def test_the_header_is_chosen_by_the_version() -> None:
    module = _release_draft()
    assert module.release_notes_header("0.5.0b2") == HEADER.name
    assert module.release_notes_header("0.5.0") == HEADER.name
    assert module.release_notes_header("0.5.0rc1") == HEADER_RC.name
    assert module.release_notes_header("1.0.0rc3") == HEADER_RC.name
    assert module.release_notes_header("0.5.0rc1.dev1") == HEADER.name
    assert (ROOT / "packaging" / module.release_notes_header("0.5.0rc1")).is_file()
    # The workflow's draft job renders with that function, not a fixed name.
    workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    assert "rd.release_notes_header(" in workflow


def test_rc_notes_say_what_a_candidate_is_in_both_languages() -> None:
    notes = _rc_notes()
    lines = [line for line in notes.splitlines() if line.strip()]
    assert lines[0] == "## ReverbScope v0.5.0rc1"
    assert "Release candidate, for hardware and DAW validation." in lines[1]
    for statement in (
        "ReverbScope 0.5.0rc1 is a release candidate for hardware and DAW\n> validation. "
        "It is not the final 0.5.0 stable release.",
        "这是 0.5.0 正式版之前的候选测试版（release candidate），不代表已经完成\n> 所有真实硬件和 DAW 验证。",
        "Its feature set is\n> frozen",
        "Current builds are unsigned.",
        "**What has been verified:**",
        "**What has not been fully verified:**",
        "real audio\n  interfaces, microphones, loudspeakers, rooms, every DAW, every driver and\n"
        "  host API, and signing / notarization",
        "should not\n  yet be treated as hardware-validated",
        "not notarized",
        "Authenticode",
        "Open Anyway",
        "Run anyway",
        "docs/HARDWARE_TESTS.md",
        "reverbscope doctor --probe --out report.txt",
    ):
        assert statement in notes, statement
    # The header itself never calls the candidate a beta (the inserted
    # changelog section may mention the beta line).
    header = HEADER_RC.read_text(encoding="utf-8")
    assert "beta" not in header.lower()
    assert "spctl --master-disable" not in notes
    assert "csrutil" not in notes


def test_rc_notes_keep_the_download_tables_and_order_of_the_beta_notes() -> None:
    notes = _rc_notes()
    positions = [notes.index(section) for section in RELEASE_ORDER]
    assert positions == sorted(positions)
    choose, technical = notes.index(RELEASE_ORDER[0]), notes.index(RELEASE_ORDER[-1])
    desktop = notes[notes.index(RELEASE_ORDER[1]) : notes.index(RELEASE_ORDER[2])]
    terminal = notes[notes.index(RELEASE_ORDER[2]) : notes.index(RELEASE_ORDER[3])]
    for name in _archives():
        assert f"`{name}`" in (desktop if "-Desktop-" in name else terminal), name
    for developer_file in ("cyclonedx.sbom.json", "generated-bundle.lock", ".whl"):
        assert notes.index(developer_file) > technical, developer_file
    assert "SBOM" not in notes[:choose] and "wheel" not in notes[:choose]
    known = set(_release_draft().expected_assets("0.5.0rc1")) | IN_BUNDLE
    unknown = sorted(set(_ASSET_NAME.findall(notes)) - known)
    assert not unknown, unknown
