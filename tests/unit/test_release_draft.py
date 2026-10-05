"""scripts/release_draft.py: the draft Release holds exactly one run's files.

The fake client below keeps releases in memory and records every change, so
the tests can check both the final state and that nothing outside a draft
was touched.
"""

from __future__ import annotations

import hashlib
import importlib.util
import re
import sys
import urllib.error
from collections.abc import Mapping
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest


def _load() -> ModuleType:
    path = Path("scripts") / "release_draft.py"
    spec = importlib.util.spec_from_file_location("release_draft", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["release_draft"] = module
    spec.loader.exec_module(module)
    return module


rd = _load()
VERSION = "0.4.1"
SETUP = "ReverbScope-Desktop-Windows-x64-Setup.exe"
TAG = "v0.4.1"
SHA = "ab4e0573cf1208f6c74b673c866511fc89269aa9"
OLD_SHA = "909f332838a896d76025f0dc2024ced5dbd48910"
WORKFLOW = Path(".github/workflows/release.yml").read_text(encoding="utf-8")


# ----------------------------------------------------------------------- fixtures


def _write_run(folder: Path, version: str = VERSION) -> Path:
    """The artifact folders one workflow run downloads, with valid checksums."""
    layout = {
        "python-dist": rd.python_dist_files(version),
        "sbom": rd.SBOM_FILES,
        "bundle-ubuntu-latest": rd.CHECKSUM_FILES["SHA256SUMS-Linux-X64"],
        "bundle-macos-latest": rd.CHECKSUM_FILES["SHA256SUMS-macOS-ARM64"],
        "bundle-macos-15-intel": rd.CHECKSUM_FILES["SHA256SUMS-macOS-X64"],
        "bundle-windows-latest": rd.CHECKSUM_FILES["SHA256SUMS-Windows-X64"],
    }
    for artifact, names in layout.items():
        (folder / artifact).mkdir(parents=True)
        for name in names:
            (folder / artifact / name).write_bytes(f"{name} built from {SHA}".encode())
    sums_dir = {
        "SHA256SUMS-Linux-X64": "bundle-ubuntu-latest",
        "SHA256SUMS-macOS-ARM64": "bundle-macos-latest",
        "SHA256SUMS-macOS-X64": "bundle-macos-15-intel",
        "SHA256SUMS-Windows-X64": "bundle-windows-latest",
    }
    for sums, artifact in sums_dir.items():
        lines = []
        for name in rd.CHECKSUM_FILES[sums]:
            digest = hashlib.sha256((folder / artifact / name).read_bytes()).hexdigest()
            lines.append(f"{digest}  {name}")
        (folder / artifact / sums).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return folder


@pytest.fixture
def staged(tmp_path: Path) -> dict[str, Path]:
    run = _write_run(tmp_path / "artifacts")
    return dict(rd.stage(run, tmp_path / "release-assets", VERSION))


class FakeGitHub:
    """In-memory releases; ``log`` records every mutating call."""

    def __init__(self, releases: list[dict[str, Any]] | None = None) -> None:
        self.releases = {r["id"]: r for r in releases or []}
        self.tags: dict[str, str] = {}
        self.log: list[tuple[str, Any]] = []
        self.fail_uploads: dict[str, int] = {}
        self._next = 1000

    def _asset_owner(self, asset_id: int) -> dict[str, Any]:
        for release in self.releases.values():
            if any(a["id"] == asset_id for a in release["assets"]):
                return release
        raise KeyError(asset_id)

    def list_releases(self) -> list[dict[str, Any]]:
        return [dict(r, assets=list(r["assets"])) for r in self.releases.values()]

    def get_release(self, release_id: int) -> dict[str, Any]:
        release = self.releases[release_id]
        return dict(release, assets=[dict(a) for a in release["assets"]])

    def tag_commit(self, tag: str) -> str | None:
        return self.tags.get(tag)

    def create_release(self, fields: Mapping[str, Any]) -> dict[str, Any]:
        self._next += 1
        release = {"id": self._next, "assets": [], **fields}
        self.releases[release["id"]] = release
        self.log.append(("create", release["id"]))
        return dict(release)

    def update_release(self, release_id: int, fields: Mapping[str, Any]) -> dict[str, Any]:
        self.releases[release_id].update(fields)
        self.log.append(("update", release_id))
        return self.get_release(release_id)

    def delete_asset(self, asset_id: int) -> None:
        release = self._asset_owner(asset_id)
        if not release["draft"]:
            raise AssertionError("the script deleted an asset of a published release")
        release["assets"] = [a for a in release["assets"] if a["id"] != asset_id]
        self.log.append(("delete", asset_id))

    def upload_asset(self, release_id: int, path: Path) -> dict[str, Any]:
        release = self.releases[release_id]
        if any(a["name"] == path.name for a in release["assets"]):
            raise AssertionError(f"{path.name} uploaded over an existing asset")
        self._next += 1
        data = path.read_bytes()
        asset = {
            "id": self._next,
            "name": path.name,
            "size": len(data),
            "state": "uploaded",
            "digest": "sha256:" + hashlib.sha256(data).hexdigest(),
        }
        if self.fail_uploads.get(path.name, 0) > 0:
            self.fail_uploads[path.name] -= 1
            asset["state"] = "starter"  # a partial upload GitHub keeps
            release["assets"].append(asset)
            raise urllib.error.URLError("connection reset")
        release["assets"].append(asset)
        self.log.append(("upload", path.name))
        return asset


def _asset(asset_id: int, name: str) -> dict[str, Any]:
    return {"id": asset_id, "name": name, "size": 1, "state": "uploaded", "digest": None}


def _release(release_id: int, *, draft: bool, names: tuple[str, ...] = (), **extra: Any) -> dict:
    release = {
        "id": release_id,
        "tag_name": TAG,
        "name": TAG,
        "draft": draft,
        "prerelease": True,
        "target_commitish": OLD_SHA,
        "body": "old notes",
        "assets": [_asset(release_id * 100 + i, n) for i, n in enumerate(names)],
    }
    release.update(extra)
    return release


# The v0.4.1 draft as the workflow on main left it on 2026-09-24.
OLD_DRAFT_NAMES = (
    "cyclonedx.sbom.json",
    "generated-bundle.lock",
    "reverbscope-0.4.1-py3-none-any.whl",
    "reverbscope-0.4.1.tar.gz",
    "reverbscope-linux-x86_64.tar.gz",
    "reverbscope-windows-x64.zip",
    "ReverbScope.dmg",
    "SHA256SUMS-Linux",
    "SHA256SUMS-macOS",
    "SHA256SUMS-Windows",
)


# ---------------------------------------------------------------------- manifest


def test_expected_manifest_is_exact() -> None:
    assert rd.expected_assets(VERSION) == {
        # Desktop Edition (GUI + command line)
        "ReverbScope-Desktop-macOS-arm64.dmg",
        "ReverbScope-Desktop-macOS-x86_64.dmg",
        "ReverbScope-Desktop-Windows-x64-Setup.exe",
        "ReverbScope-Desktop-Windows-x64.zip",
        "ReverbScope-Desktop-Linux-x86_64.tar.gz",
        # Terminal Edition (command line only)
        "ReverbScope-Terminal-macOS-arm64.tar.gz",
        "ReverbScope-Terminal-macOS-x86_64.tar.gz",
        "ReverbScope-Terminal-Windows-x64.zip",
        "ReverbScope-Terminal-Linux-x86_64.tar.gz",
        # Python, checksums, SBOM
        "reverbscope-0.4.1-py3-none-any.whl",
        "reverbscope-0.4.1.tar.gz",
        "SHA256SUMS",
        "cyclonedx.sbom.json",
        "generated-bundle.lock",
    }
    assert not rd.expected_assets(VERSION) & rd.LEGACY_ASSETS


def test_every_download_name_says_edition_system_and_cpu() -> None:
    pattern = re.compile(
        r"ReverbScope-(Desktop|Terminal)-(macOS-(arm64|x86_64)|Windows-x64|Linux-x86_64)"
        r"(-Setup\.exe|\.dmg|\.zip|\.tar\.gz)"
    )
    archives = [name for names in rd.CHECKSUM_FILES.values() for name in names]
    assert all(pattern.fullmatch(name) for name in archives), archives
    for names in rd.CHECKSUM_FILES.values():
        assert any("-Desktop-" in name for name in names)
        assert sum("-Terminal-" in name for name in names) == 1


def test_manifest_matches_the_workflow_and_local_builder() -> None:
    """The bundle job's upload list and checksum names produce this manifest."""
    for archives in rd.CHECKSUM_FILES.values():
        for archive in archives:
            # shutil.make_archive adds ".zip"; the macOS names use $(uname -m).
            assert (
                archive in WORKFLOW
                or archive.removesuffix(".zip") in WORKFLOW
                or archive.startswith(("ReverbScope-Desktop-macOS-", "ReverbScope-Terminal-macOS-"))
            ), archive
    assert "ReverbScope-Desktop-macOS-$(uname -m).dmg" in WORKFLOW
    assert "ReverbScope-Terminal-macOS-$(uname -m).tar.gz" in WORKFLOW
    assert "dist/ReverbScope-Desktop-*" in WORKFLOW and "dist/ReverbScope-Terminal-*" in WORKFLOW
    # The runner's checksum file is written from the manifest, not a copied list.
    assert "rd.CHECKSUM_FILES[sums_name]" in WORKFLOW
    matrix = re.search(r"os: \[(.*?)\]", WORKFLOW)
    assert matrix is not None
    assert len(matrix.group(1).split(",")) == len(rd.CHECKSUM_FILES)
    for name in rd.SBOM_FILES:
        assert name in WORKFLOW

    spec = importlib.util.spec_from_file_location("build_release", "scripts/build_release.py")
    assert spec is not None and spec.loader is not None
    builder = importlib.util.module_from_spec(spec)
    sys.modules["build_release"] = builder
    spec.loader.exec_module(builder)
    for system, arch, machine in (
        ("Linux", "X64", "x86_64"),
        ("macOS", "ARM64", "arm64"),
        ("macOS", "X64", "x86_64"),
        ("Windows", "X64", "AMD64"),
    ):
        target = builder.Target(system, arch, machine)
        assert rd.CHECKSUM_FILES[target.checksum_name] == target.archives


def test_draft_job_uses_the_script_not_a_tag_lookup() -> None:
    """softprops/action-gh-release finds a release by tag, which misses drafts."""
    job = WORKFLOW[WORKFLOW.index("  draft-release:") :]
    job = job[: job.index("\n  pypi:")]
    assert "softprops/action-gh-release" not in job
    assert "release_draft.py stage" in WORKFLOW
    assert "release_draft.py sync" in job
    assert "release_draft.py verify" in job
    assert "--is-ancestor" in job
    assert "if: needs.prepare.outputs.draft == 'true'" in job


# ------------------------------------------------------------------------- stage


def test_stage_accepts_one_complete_run(tmp_path: Path) -> None:
    run = _write_run(tmp_path / "artifacts")
    staged = rd.stage(run, tmp_path / "out", VERSION)
    assert set(staged) == rd.expected_assets(VERSION)
    assert {p.name for p in (tmp_path / "out").iterdir()} == rd.expected_assets(VERSION)
    assert set(rd.load_staged(tmp_path / "out", VERSION)) == rd.expected_assets(VERSION)


def test_stage_rejects_a_legacy_or_extra_file(tmp_path: Path) -> None:
    run = _write_run(tmp_path / "artifacts")
    (run / "bundle-macos-latest" / "ReverbScope.dmg").write_bytes(b"old")
    with pytest.raises(rd.ReleaseError, match=r"unexpected \['ReverbScope.dmg'\]"):
        rd.stage(run, tmp_path / "out", VERSION)
    assert not (tmp_path / "out").exists()


def test_stage_rejects_a_missing_platform(tmp_path: Path) -> None:
    run = _write_run(tmp_path / "artifacts")
    for path in (run / "bundle-macos-15-intel").iterdir():
        path.unlink()
    with pytest.raises(rd.ReleaseError, match=re.escape("ReverbScope-Desktop-macOS-x86_64.dmg")):
        rd.stage(run, tmp_path / "out", VERSION)


def test_stage_rejects_a_wrong_version(tmp_path: Path) -> None:
    run = _write_run(tmp_path / "artifacts", version="0.4.0")
    with pytest.raises(rd.ReleaseError, match=re.escape("reverbscope-0.4.1.tar.gz")):
        rd.stage(run, tmp_path / "out", VERSION)


def test_stage_rejects_the_same_name_from_two_artifacts(tmp_path: Path) -> None:
    run = _write_run(tmp_path / "artifacts")
    (run / "sbom" / "ReverbScope-Terminal-Windows-x64.zip").write_bytes(b"x")
    with pytest.raises(rd.ReleaseError, match="two artifacts"):
        rd.stage(run, tmp_path / "out", VERSION)


def test_stage_rejects_a_checksum_that_does_not_match(tmp_path: Path) -> None:
    run = _write_run(tmp_path / "artifacts")
    (run / "bundle-windows-latest" / SETUP).write_bytes(b"rebuilt later")
    with pytest.raises(rd.ReleaseError, match=re.escape(f"{SETUP} is")):
        rd.stage(run, tmp_path / "out", VERSION)


def test_stage_rejects_a_checksum_file_naming_other_files(tmp_path: Path) -> None:
    run = _write_run(tmp_path / "artifacts")
    sums = run / "bundle-windows-latest" / "SHA256SUMS-Windows-X64"
    sums.write_text(sums.read_text(encoding="utf-8").splitlines()[0] + "\n", encoding="utf-8")
    with pytest.raises(rd.ReleaseError, match="expected exactly"):
        rd.stage(run, tmp_path / "out", VERSION)


@pytest.mark.parametrize(
    "text",
    ["nothex  file", "a" * 64 + "file", f"{'a' * 64}  f\n{'b' * 64}  f"],
)
def test_parse_checksums_rejects_malformed_lines(text: str) -> None:
    with pytest.raises(rd.ReleaseError):
        rd.parse_checksums(text, "SUMS")


def test_parse_checksums_accepts_sha256sum_output() -> None:
    digest = "0" * 64
    assert rd.parse_checksums(f"{digest}  a.zip\n{digest} *b.exe\n", "S") == {
        "a.zip": digest,
        "b.exe": digest,
    }


# ---------------------------------------------------------------------- planning


def test_plan_refuses_a_published_release() -> None:
    releases = [_release(1, draft=False, names=OLD_DRAFT_NAMES)]
    with pytest.raises(rd.ReleaseError, match="already published"):
        rd.plan_sync(releases, None, VERSION)


def test_plan_refuses_a_published_release_next_to_a_draft() -> None:
    releases = [_release(1, draft=False), _release(2, draft=True, tag_name="untagged-x")]
    with pytest.raises(rd.ReleaseError, match="already published"):
        rd.plan_sync(releases, releases[1], VERSION)


def test_plan_refuses_several_drafts() -> None:
    releases = [_release(1, draft=True), _release(2, draft=True, tag_name="untagged-y")]
    with pytest.raises(rd.ReleaseError, match="2 drafts"):
        rd.plan_sync(releases, None, VERSION)


def test_plan_refuses_a_draft_tagged_for_another_version() -> None:
    draft = _release(1, draft=True, tag_name="v0.4.0")
    with pytest.raises(rd.ReleaseError, match=re.escape("tagged 'v0.4.0'")):
        rd.plan_sync([draft], draft, VERSION)


def test_plan_refuses_unknown_assets() -> None:
    draft = _release(1, draft=True, names=(*OLD_DRAFT_NAMES, "ReverbScope-signed-by-hand.dmg"))
    with pytest.raises(rd.ReleaseError, match=re.escape("ReverbScope-signed-by-hand.dmg")):
        rd.plan_sync([draft], draft, VERSION)


def test_plan_refuses_duplicate_asset_names() -> None:
    draft = _release(1, draft=True, names=("ReverbScope.dmg", "ReverbScope.dmg"))
    with pytest.raises(rd.ReleaseError, match="duplicate"):
        rd.plan_sync([draft], draft, VERSION)


def test_plan_detects_legacy_assets_on_the_current_draft() -> None:
    draft = _release(1, draft=True, names=OLD_DRAFT_NAMES)
    plan = rd.plan_sync([draft], draft, VERSION)
    assert plan.release_id == 1
    assert plan.obsolete == (
        "ReverbScope.dmg",
        "SHA256SUMS-Linux",
        "SHA256SUMS-Windows",
        "SHA256SUMS-macOS",
        "reverbscope-linux-x86_64.tar.gz",
        "reverbscope-windows-x64.zip",
    )
    assert "reverbscope-0.4.1.tar.gz" in plan.replace
    assert "ReverbScope.dmg" not in plan.replace


def test_plan_removes_the_names_from_before_the_editions() -> None:
    """The v0.4.1 draft as the workflow left it before Desktop / Terminal (Release #26)."""
    names = (
        "cyclonedx.sbom.json",
        "generated-bundle.lock",
        "reverbscope-0.4.1-py3-none-any.whl",
        "reverbscope-0.4.1.tar.gz",
        "reverbscope-linux-x86_64.tar.gz",
        "ReverbScope-macos-arm64.dmg",
        "ReverbScope-macos-x86_64.dmg",
        "reverbscope-windows-x64.zip",
        SETUP,
        "SHA256SUMS-Linux-X64",
        "SHA256SUMS-macOS-ARM64",
        "SHA256SUMS-macOS-X64",
        "SHA256SUMS-Windows-X64",
    )
    draft = _release(1, draft=True, names=names)
    plan = rd.plan_sync([draft], draft, VERSION)
    assert set(plan.obsolete) == set(names) - rd.expected_assets(VERSION)
    assert set(plan.replace) == set(names) & rd.expected_assets(VERSION)


def test_stage_writes_one_checksum_file_for_every_download(tmp_path: Path) -> None:
    run = _write_run(tmp_path / "artifacts")
    staged = rd.stage(run, tmp_path / "out", VERSION)
    lines = staged["SHA256SUMS"].read_text(encoding="utf-8").splitlines()
    assert [line.split("  ", 1)[1] for line in lines] == list(rd.downloads(VERSION))
    assert not any(name.startswith("SHA256SUMS-") for name in staged)
    staged["ReverbScope-Terminal-Linux-x86_64.tar.gz"].write_bytes(b"changed after staging")
    with pytest.raises(
        rd.ReleaseError, match=re.escape("ReverbScope-Terminal-Linux-x86_64.tar.gz is")
    ):
        rd.load_staged(tmp_path / "out", VERSION)


def test_plan_ignores_other_versions() -> None:
    older = _release(1, draft=False, tag_name="v0.4.0", name="v0.4.0", names=("ReverbScope.dmg",))
    plan = rd.plan_sync([older], None, VERSION)
    assert plan == rd.Plan(TAG, None, (), ())


def test_check_commit_refuses_a_tag_on_another_commit() -> None:
    client = FakeGitHub()
    client.tags[TAG] = OLD_SHA
    with pytest.raises(rd.ReleaseError, match="not at the tested commit"):
        rd.check_commit(client, TAG, SHA)
    client.tags[TAG] = SHA
    rd.check_commit(client, TAG, SHA)


@pytest.mark.parametrize("sha", ["main", SHA[:7], SHA.upper(), ""])
def test_check_commit_needs_a_full_sha(sha: str) -> None:
    with pytest.raises(rd.ReleaseError, match="full commit SHA"):
        rd.check_commit(FakeGitHub(), TAG, sha)


# -------------------------------------------------------------------------- sync


def test_sync_replaces_same_names_and_removes_obsolete_ones(staged: dict[str, Path]) -> None:
    client = FakeGitHub([_release(7, draft=True, names=OLD_DRAFT_NAMES, tag_name="untagged-1")])
    rd.sync(client, VERSION, SHA, staged, "new notes")
    release = client.releases[7]
    assert sorted(a["name"] for a in release["assets"]) == sorted(rd.expected_assets(VERSION))
    assert release["target_commitish"] == SHA
    assert release["tag_name"] == TAG
    assert release["body"] == "new notes"
    assert release["draft"] is True and release["prerelease"] is True
    # Every old asset was deleted (same name or legacy), none survived.
    old_ids = {7 * 100 + i for i in range(len(OLD_DRAFT_NAMES))}
    assert not old_ids & {a["id"] for a in release["assets"]}
    assert {entry[1] for entry in client.log if entry[0] == "delete"} == old_ids
    assert ("create", 1001) not in client.log  # the existing draft was reused


def test_sync_creates_a_draft_when_there_is_none(staged: dict[str, Path]) -> None:
    older = _release(1, draft=False, tag_name="v0.4.0", name="v0.4.0", names=("ReverbScope.dmg",))
    client = FakeGitHub([older])
    rd.sync(client, VERSION, SHA, staged, "notes")
    created = [r for r in client.releases.values() if r["id"] != 1]
    assert len(created) == 1 and created[0]["draft"] is True
    assert created[0]["target_commitish"] == SHA
    assert client.releases[1]["assets"] == [_asset(100, "ReverbScope.dmg")]


def test_sync_never_touches_a_published_release(staged: dict[str, Path]) -> None:
    published = _release(3, draft=False, names=OLD_DRAFT_NAMES)
    client = FakeGitHub([published])
    with pytest.raises(rd.ReleaseError, match="already published"):
        rd.sync(client, VERSION, SHA, staged, "notes")
    assert client.log == []
    assert [a["name"] for a in client.releases[3]["assets"]] == list(OLD_DRAFT_NAMES)


def test_delete_refuses_a_release_published_in_the_meantime() -> None:
    client = FakeGitHub([_release(4, draft=True, names=("ReverbScope.dmg",))])
    client.releases[4]["draft"] = False  # published between plan and delete
    with pytest.raises(rd.ReleaseError, match="not a draft"):
        rd.delete_draft_asset(client, 4, "ReverbScope.dmg")
    assert client.log == []


def test_sync_refuses_a_tag_on_another_commit(staged: dict[str, Path]) -> None:
    client = FakeGitHub([_release(5, draft=True, names=OLD_DRAFT_NAMES)])
    client.tags[TAG] = OLD_SHA
    with pytest.raises(rd.ReleaseError, match="not at the tested commit"):
        rd.sync(client, VERSION, SHA, staged, "notes")
    assert client.log == []


def test_sync_dry_run_changes_nothing(staged: dict[str, Path]) -> None:
    client = FakeGitHub([_release(6, draft=True, names=OLD_DRAFT_NAMES)])
    plan = rd.sync(client, VERSION, SHA, staged, "notes", dry_run=True)
    assert plan.release_id == 6 and len(plan.obsolete) == 6
    assert client.log == []


def test_sync_is_idempotent(staged: dict[str, Path]) -> None:
    client = FakeGitHub([_release(8, draft=True, names=OLD_DRAFT_NAMES)])
    rd.sync(client, VERSION, SHA, staged, "notes")
    plan = rd.sync(client, VERSION, SHA, staged, "notes")
    assert plan.obsolete == ()
    assert set(plan.replace) == rd.expected_assets(VERSION)
    names = [a["name"] for a in client.releases[8]["assets"]]
    assert sorted(names) == sorted(rd.expected_assets(VERSION))


def test_sync_retries_a_failed_upload_without_leaving_a_partial(staged: dict[str, Path]) -> None:
    client = FakeGitHub([_release(9, draft=True)])
    client.fail_uploads[SETUP] = 1
    rd.sync(client, VERSION, SHA, staged, "notes")
    states = {a["name"]: a["state"] for a in client.releases[9]["assets"]}
    assert states[SETUP] == "uploaded"
    assert set(states.values()) == {"uploaded"}


def test_sync_gives_up_after_repeated_upload_failures(staged: dict[str, Path]) -> None:
    client = FakeGitHub([_release(10, draft=True)])
    client.fail_uploads[SETUP] = 5
    with pytest.raises(rd.ReleaseError, match=re.escape(f"upload of {SETUP} failed")):
        rd.sync(client, VERSION, SHA, staged, "notes")


# ------------------------------------------------------------------------ verify


def test_verify_checks_target_digest_and_names(staged: dict[str, Path]) -> None:
    client = FakeGitHub([_release(11, draft=True)])
    rd.sync(client, VERSION, SHA, staged, "notes")
    rd.verify(client, 11, VERSION, SHA, staged, "notes")

    client.releases[11]["target_commitish"] = OLD_SHA
    with pytest.raises(rd.ReleaseError, match="target_commitish"):
        rd.verify(client, 11, VERSION, SHA, staged, "notes")
    client.releases[11]["target_commitish"] = SHA

    asset = next(a for a in client.releases[11]["assets"] if a["name"] == SETUP)
    asset["digest"] = "sha256:" + "0" * 64
    with pytest.raises(rd.ReleaseError, match="digest"):
        rd.verify(client, 11, VERSION, SHA, staged, "notes")
    asset["digest"] = None

    client.releases[11]["assets"].append(_asset(1, "ReverbScope.dmg"))
    with pytest.raises(rd.ReleaseError, match="assets are"):
        rd.verify(client, 11, VERSION, SHA, staged, "notes")
    client.releases[11]["assets"].pop()

    with pytest.raises(rd.ReleaseError, match="body differs"):
        rd.verify(client, 11, VERSION, SHA, staged, "other notes")

    client.releases[11]["draft"] = False
    with pytest.raises(rd.ReleaseError, match="draft is False"):
        rd.verify(client, 11, VERSION, SHA, staged, "notes")


def test_main_stage_command(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    run = _write_run(tmp_path / "artifacts")
    argv = ["stage", "--artifacts", str(run), "--out", str(tmp_path / "o"), "--version", VERSION]
    assert rd.main(argv) == 0
    assert SETUP in capsys.readouterr().out
    (run / "sbom" / "stray.txt").write_text("x", encoding="utf-8")
    argv[4] = str(tmp_path / "o2")
    assert rd.main(argv) == 1
    assert "unexpected ['stray.txt']" in capsys.readouterr().err
