"""Stage the release files of one workflow run and refresh the draft Release.

Used by the ``draft-release`` job of ``.github/workflows/release.yml``
(docs/RELEASE_PLAN.md §3). Three subcommands:

``stage``
    Collect the artifacts that one workflow run downloaded, refuse anything
    that is not exactly the expected file set (:func:`expected_assets`),
    check every runner's ``SHA256SUMS-<OS>-<ARCH>`` file against the files it
    names, and copy the set into one flat folder with one ``SHA256SUMS`` for
    every download (the per-runner files stay workflow artifacts).

``sync``
    Open or refresh the single draft Release ``v<version>`` so that it holds
    exactly the staged files, targets the tested commit, is a draft and a
    pre-release, and carries the given notes. ``--dry-run`` only prints the
    plan (it is safe to run with a read-only token).

``verify``
    Read the draft back and check it against the staged files (also the last
    step of ``sync``).

The script fails closed rather than guessing: a published release, more
than one draft for the version, a draft pointing at another tag, a tag that
points at another commit, or an asset name it does not know (not in the
current manifest and not a known name from an earlier workflow) all stop it
before anything is changed. An asset is only ever deleted from a release
that was re-read as a draft immediately before the delete, so published
Releases are never touched. Nothing here publishes a Release, creates a tag
or uploads to PyPI.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

#: ``SHA256SUMS-<RUNNER_OS>-<RUNNER_ARCH>`` -> the downloads that runner builds
#: (the bundle matrix of release.yml and ``Target`` in build_release.py): the
#: Desktop Edition (GUI + command line) and the Terminal Edition (command line
#: only, no Qt) of each platform. The names say edition, system and CPU.
CHECKSUM_FILES: Mapping[str, tuple[str, ...]] = {
    "SHA256SUMS-Linux-X64": (
        "ReverbScope-Desktop-Linux-x86_64.tar.gz",
        "ReverbScope-Terminal-Linux-x86_64.tar.gz",
    ),
    "SHA256SUMS-macOS-ARM64": (
        "ReverbScope-Desktop-macOS-arm64.dmg",
        "ReverbScope-Terminal-macOS-arm64.tar.gz",
    ),
    "SHA256SUMS-macOS-X64": (
        "ReverbScope-Desktop-macOS-x86_64.dmg",
        "ReverbScope-Terminal-macOS-x86_64.tar.gz",
    ),
    "SHA256SUMS-Windows-X64": (
        "ReverbScope-Desktop-Windows-x64-Setup.exe",
        "ReverbScope-Desktop-Windows-x64.zip",
        "ReverbScope-Terminal-Windows-x64.zip",
    ),
}
#: One checksum file on the Release for every download it carries.
RELEASE_CHECKSUMS = "SHA256SUMS"
#: Produced by the sbom job.
SBOM_FILES = ("cyclonedx.sbom.json", "generated-bundle.lock")
#: Names earlier versions of release.yml attached to a draft. They are
#: removed from the draft; any other unknown name stops the refresh.
LEGACY_ASSETS = frozenset(
    {
        "ReverbScope.dmg",
        "SHA256SUMS-Linux",
        "SHA256SUMS-macOS",
        "SHA256SUMS-Windows",
        # 0.4.1 drafts before the Desktop / Terminal editions
        "reverbscope-linux-x86_64.tar.gz",
        "ReverbScope-macos-arm64.dmg",
        "ReverbScope-macos-x86_64.dmg",
        "reverbscope-windows-x64.zip",
        "ReverbScope-setup.exe",
        *CHECKSUM_FILES,
    }
)
_SHA = re.compile(r"[0-9a-f]{40}")
_SUM_LINE = re.compile(r"([0-9a-f]{64}) [ *](\S.*)")


class ReleaseError(RuntimeError):
    """The files or the Release are not in a state the script may act on."""


def python_dist_files(version: str) -> tuple[str, str]:
    """The wheel and sdist names hatchling gives ``reverbscope`` at *version*."""
    return (f"reverbscope-{version}-py3-none-any.whl", f"reverbscope-{version}.tar.gz")


def downloads(version: str) -> tuple[str, ...]:
    """Every file a user may download: both editions, then the Python files."""
    archives = tuple(name for names in CHECKSUM_FILES.values() for name in names)
    return (*archives, *python_dist_files(version))


def expected_assets(version: str) -> frozenset[str]:
    """Every file one successful run attaches to the draft, and nothing else."""
    return frozenset({*downloads(version), *SBOM_FILES, RELEASE_CHECKSUMS})


def run_files(version: str) -> frozenset[str]:
    """What one workflow run downloads: the assets, with per-runner checksums."""
    return (expected_assets(version) - {RELEASE_CHECKSUMS}) | set(CHECKSUM_FILES)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


# --------------------------------------------------------------------------- stage


def parse_checksums(text: str, source: str) -> dict[str, str]:
    """``sha256sum`` lines -> {file name: hex digest}; malformed lines fail."""
    sums: dict[str, str] = {}
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        match = _SUM_LINE.fullmatch(line)
        if match is None:
            raise ReleaseError(f"{source}:{number}: not a sha256sum line: {line!r}")
        digest, name = match.groups()
        if name in sums:
            raise ReleaseError(f"{source}: {name} is listed twice")
        sums[name] = digest
    return sums


def release_checksums(files: Mapping[str, Path], version: str) -> str:
    """``sha256sum`` lines for every download, in :func:`downloads` order."""
    return "".join(f"{sha256_file(files[name])}  {name}\n" for name in downloads(version))


def verify_release_checksums(files: Mapping[str, Path], version: str) -> None:
    """The Release's ``SHA256SUMS`` names every download once, with its digest."""
    sums = parse_checksums(files[RELEASE_CHECKSUMS].read_text(encoding="utf-8"), RELEASE_CHECKSUMS)
    if set(sums) != set(downloads(version)):
        raise ReleaseError(
            f"{RELEASE_CHECKSUMS} lists {sorted(sums)}, expected {sorted(downloads(version))}"
        )
    for name, digest in sums.items():
        actual = sha256_file(files[name])
        if actual != digest:
            raise ReleaseError(f"{RELEASE_CHECKSUMS}: {name} is {actual}, the file says {digest}")


def verify_checksums(files: Mapping[str, Path]) -> None:
    """Each checksum file names exactly its runner's archives, with their digests."""
    for sums_name, archives in CHECKSUM_FILES.items():
        sums = parse_checksums(files[sums_name].read_text(encoding="utf-8"), sums_name)
        if set(sums) != set(archives):
            raise ReleaseError(
                f"{sums_name} lists {sorted(sums)}, expected exactly {sorted(archives)}"
            )
        for name, digest in sums.items():
            actual = sha256_file(files[name])
            if actual != digest:
                raise ReleaseError(f"{sums_name}: {name} is {actual}, the file says {digest}")


def collect(artifacts: Path) -> dict[str, Path]:
    """Every file below *artifacts* by base name; the same name twice fails."""
    found: dict[str, Path] = {}
    for path in sorted(p for p in artifacts.rglob("*") if p.is_file()):
        if path.name in found:
            raise ReleaseError(f"{path.name} comes from two artifacts: {found[path.name]}, {path}")
        found[path.name] = path
    return found


def stage(artifacts: Path, out: Path, version: str) -> dict[str, Path]:
    """Check the downloaded artifacts and copy them flat into *out*."""
    if not artifacts.is_dir():
        raise ReleaseError(f"{artifacts} is not a folder")
    found = collect(artifacts)
    expected = run_files(version)
    missing = sorted(expected - found.keys())
    unexpected = sorted(found.keys() - expected)
    if missing or unexpected:
        raise ReleaseError(f"release file set is wrong: missing {missing}, unexpected {unexpected}")
    verify_checksums(found)
    if out.exists() and any(out.iterdir()):
        raise ReleaseError(f"{out} is not empty")
    out.mkdir(parents=True, exist_ok=True)
    staged = {}
    for name, path in sorted(found.items()):
        if name in CHECKSUM_FILES:
            continue  # checked above; the Release carries one SHA256SUMS instead
        staged[name] = out / name
        shutil.copy2(path, staged[name])
    staged[RELEASE_CHECKSUMS] = out / RELEASE_CHECKSUMS
    staged[RELEASE_CHECKSUMS].write_text(release_checksums(staged, version), encoding="utf-8")
    verify_release_checksums(staged, version)
    return staged


def load_staged(folder: Path, version: str) -> dict[str, Path]:
    """A folder written by :func:`stage`, checked again."""
    files = {path.name: path for path in folder.iterdir() if path.is_file()}
    if set(files) != expected_assets(version):
        raise ReleaseError(f"{folder} does not hold exactly the release files")
    verify_release_checksums(files, version)
    return files


# ---------------------------------------------------------------------- GitHub API


class Client(Protocol):
    """The Release endpoints the script uses (a fake in the tests)."""

    def list_releases(self) -> list[dict[str, Any]]: ...

    def get_release(self, release_id: int) -> dict[str, Any]: ...

    def tag_commit(self, tag: str) -> str | None: ...

    def create_release(self, fields: Mapping[str, Any]) -> dict[str, Any]: ...

    def update_release(self, release_id: int, fields: Mapping[str, Any]) -> dict[str, Any]: ...

    def delete_asset(self, asset_id: int) -> None: ...

    def upload_asset(self, release_id: int, path: Path) -> dict[str, Any]: ...


class GitHubClient:
    """urllib client for the REST API; ``get_release`` includes every asset."""

    def __init__(
        self,
        repository: str,
        token: str,
        api: str = "https://api.github.com",
        uploads: str = "https://uploads.github.com",
    ) -> None:
        self._repo = f"{api}/repos/{repository}"
        self._uploads = f"{uploads}/repos/{repository}"
        self._token = token

    def _call(
        self,
        method: str,
        url: str,
        body: Mapping[str, Any] | None = None,
        *,
        data: Any = None,
        headers: Mapping[str, str] | None = None,
    ) -> Any:
        all_headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self._token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "reverbscope-release-draft",
        }
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            all_headers["Content-Type"] = "application/json"
        all_headers.update(headers or {})
        request = urllib.request.Request(url, data=data, method=method, headers=all_headers)
        with urllib.request.urlopen(request, timeout=600) as response:
            payload = response.read()
        return json.loads(payload) if payload else None

    def _pages(self, url: str) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        page = 1
        while True:
            batch = self._call("GET", f"{url}?per_page=100&page={page}")
            items.extend(batch)
            if len(batch) < 100:
                return items
            page += 1

    def list_releases(self) -> list[dict[str, Any]]:
        return self._pages(f"{self._repo}/releases")

    def get_release(self, release_id: int) -> dict[str, Any]:
        release: dict[str, Any] = self._call("GET", f"{self._repo}/releases/{release_id}")
        release["assets"] = self._pages(f"{self._repo}/releases/{release_id}/assets")
        return release

    def tag_commit(self, tag: str) -> str | None:
        quoted = urllib.parse.quote(tag, safe="")
        try:
            ref = self._call("GET", f"{self._repo}/git/ref/tags/{quoted}")
        except urllib.error.HTTPError as error:
            if error.code == 404:
                return None
            raise
        target = ref["object"]
        while target["type"] == "tag":  # annotated tag -> the object it points at
            target = self._call("GET", f"{self._repo}/git/tags/{target['sha']}")["object"]
        return str(target["sha"])

    def create_release(self, fields: Mapping[str, Any]) -> dict[str, Any]:
        release: dict[str, Any] = self._call("POST", f"{self._repo}/releases", fields)
        return release

    def update_release(self, release_id: int, fields: Mapping[str, Any]) -> dict[str, Any]:
        release: dict[str, Any] = self._call("PATCH", f"{self._repo}/releases/{release_id}", fields)
        return release

    def delete_asset(self, asset_id: int) -> None:
        self._call("DELETE", f"{self._repo}/releases/assets/{asset_id}")

    def upload_asset(self, release_id: int, path: Path) -> dict[str, Any]:
        name = urllib.parse.quote(path.name, safe="")
        url = f"{self._uploads}/releases/{release_id}/assets?name={name}"
        headers = {
            "Content-Type": "application/octet-stream",
            "Content-Length": str(path.stat().st_size),
        }
        with path.open("rb") as handle:
            asset: dict[str, Any] = self._call("POST", url, data=handle, headers=headers)
        return asset


# ------------------------------------------------------------------------- planning


@dataclass(frozen=True)
class Plan:
    """What :func:`sync` will do to the draft."""

    tag: str
    release_id: int | None  # None: no draft yet, one is created
    replace: tuple[str, ...]  # current names, re-uploaded from this run
    obsolete: tuple[str, ...]  # legacy names, removed

    def describe(self) -> str:
        where = "create a new draft" if self.release_id is None else f"draft {self.release_id}"
        lines = [f"{self.tag}: {where}"]
        lines += [f"  replace  {name}" for name in self.replace]
        lines += [f"  remove   {name}" for name in self.obsolete]
        return "\n".join(lines)


def matching_releases(releases: Iterable[Mapping[str, Any]], tag: str) -> list[Mapping[str, Any]]:
    """Releases that are, or could be, the Release for *tag* (tag or title)."""
    return [r for r in releases if r.get("tag_name") == tag or r.get("name") == tag]


def plan_sync(
    releases: Iterable[Mapping[str, Any]],
    draft: Mapping[str, Any] | None,
    version: str,
) -> Plan:
    """Decide what to do; refuse every state that is not a clean draft or nothing.

    *draft* is the matching release re-read with its full asset list (or None
    when *releases* holds no match).
    """
    tag = f"v{version}"
    matches = matching_releases(releases, tag)
    published = [r for r in matches if not r.get("draft")]
    if published:
        ids = ", ".join(str(r["id"]) for r in published)
        raise ReleaseError(f"{tag} is already published (release {ids}); refusing to touch it")
    if len(matches) > 1:
        ids = ", ".join(str(r["id"]) for r in matches)
        raise ReleaseError(f"{len(matches)} drafts match {tag} ({ids}); delete the extra ones")
    if not matches:
        return Plan(tag, None, (), ())
    if draft is None or draft.get("id") != matches[0].get("id"):
        raise ReleaseError(f"draft {matches[0].get('id')} was not re-read")
    if not draft.get("draft"):
        raise ReleaseError(f"release {draft['id']} is no longer a draft; refusing to touch it")
    tag_name = str(draft.get("tag_name") or "")
    if tag_name != tag and not tag_name.startswith("untagged-"):
        raise ReleaseError(f"draft {draft['id']} is named {tag} but tagged {tag_name!r}")
    names = [str(asset["name"]) for asset in draft.get("assets", [])]
    duplicates = sorted({name for name in names if names.count(name) > 1})
    if duplicates:
        raise ReleaseError(f"draft {draft['id']} has duplicate assets {duplicates}")
    expected = expected_assets(version)
    unknown = sorted(set(names) - expected - LEGACY_ASSETS)
    if unknown:
        raise ReleaseError(
            f"draft {draft['id']} holds assets this workflow does not produce: {unknown}. "
            "Remove them by hand if they are not needed, then re-run the workflow."
        )
    replace = tuple(sorted(name for name in names if name in expected))
    obsolete = tuple(sorted(name for name in names if name in LEGACY_ASSETS))
    return Plan(tag, int(draft["id"]), replace, obsolete)


def check_commit(client: Client, tag: str, sha: str) -> None:
    """*sha* is a full commit id and an existing *tag* points at it."""
    if _SHA.fullmatch(sha) is None:
        raise ReleaseError(f"{sha!r} is not a full commit SHA")
    tagged = client.tag_commit(tag)
    if tagged is not None and tagged != sha:
        raise ReleaseError(f"tag {tag} points at {tagged}, not at the tested commit {sha}")


def _require_draft(client: Client, release_id: int) -> dict[str, Any]:
    release = client.get_release(release_id)
    if release.get("draft") is not True:
        raise ReleaseError(f"release {release_id} is not a draft; refusing to change it")
    return release


def delete_draft_asset(client: Client, release_id: int, name: str) -> None:
    """Delete *name* from *release_id*, re-reading it as a draft first."""
    release = _require_draft(client, release_id)
    for asset in release.get("assets", []):
        if asset["name"] == name:
            client.delete_asset(int(asset["id"]))


def upload(client: Client, release_id: int, path: Path, attempts: int = 3) -> None:
    """Upload *path*; after a failed attempt remove any partial asset and retry."""
    for attempt in range(1, attempts + 1):
        try:
            _require_draft(client, release_id)
            client.upload_asset(release_id, path)
            return
        except (urllib.error.URLError, OSError, TimeoutError) as error:
            if attempt == attempts:
                raise ReleaseError(f"upload of {path.name} failed: {error}") from error
            print(f"upload of {path.name} failed ({error}); retrying", file=sys.stderr)
            delete_draft_asset(client, release_id, path.name)


def verify(
    client: Client,
    release_id: int,
    version: str,
    sha: str,
    files: Mapping[str, Path],
    notes: str | None = None,
) -> None:
    """The draft is exactly this run's result, or ReleaseError lists what is not."""
    tag = f"v{version}"
    release = client.get_release(release_id)
    problems = []
    for key, wanted in (
        ("draft", True),
        ("prerelease", True),
        ("tag_name", tag),
        ("name", tag),
        ("target_commitish", sha),
    ):
        if release.get(key) != wanted:
            problems.append(f"{key} is {release.get(key)!r}, expected {wanted!r}")
    if notes is not None and _normal(release.get("body")) != _normal(notes):
        problems.append("body differs from the release notes of this run")
    assets = release.get("assets", [])
    names = sorted(str(asset["name"]) for asset in assets)
    if names != sorted(expected_assets(version)) or set(names) != set(files):
        problems.append(f"assets are {names}, expected {sorted(files)}")
    for asset in assets:
        path = files.get(asset["name"])
        if path is None:
            continue
        if asset.get("state") != "uploaded":
            problems.append(f"{asset['name']} is in state {asset.get('state')!r}")
        if asset.get("size") != path.stat().st_size:
            problems.append(f"{asset['name']} is {asset.get('size')} bytes, local file differs")
        digest = asset.get("digest")
        if digest is not None and digest != f"sha256:{sha256_file(path)}":
            problems.append(f"{asset['name']} digest {digest} does not match the local file")
    if problems:
        raise ReleaseError(f"draft {release_id} is not as expected:\n  " + "\n  ".join(problems))


def _normal(text: object) -> str:
    return str(text or "").replace("\r\n", "\n").strip()


def sync(
    client: Client,
    version: str,
    sha: str,
    files: Mapping[str, Path],
    notes: str,
    *,
    dry_run: bool = False,
) -> Plan:
    """Make the single draft ``v<version>`` hold exactly *files* at *sha*."""
    if set(files) != expected_assets(version):
        raise ReleaseError("the staged files are not the release file set")
    tag = f"v{version}"
    check_commit(client, tag, sha)
    releases = client.list_releases()
    matches = matching_releases(releases, tag)
    draft = client.get_release(int(matches[0]["id"])) if len(matches) == 1 else None
    plan = plan_sync(releases, draft, version)
    print(plan.describe())
    if dry_run:
        return plan
    fields = {
        "tag_name": tag,
        "target_commitish": sha,
        "name": tag,
        "body": notes,
        "draft": True,
        "prerelease": True,
    }
    if plan.release_id is None:
        created = client.create_release(fields)
        release_id = int(created["id"])
        if created.get("draft") is not True:
            raise ReleaseError(f"release {release_id} was not created as a draft")
    else:
        release_id = plan.release_id
        _require_draft(client, release_id)
        client.update_release(release_id, fields)
    for name in (*plan.obsolete, *plan.replace):
        delete_draft_asset(client, release_id, name)
    for _name, path in sorted(files.items()):
        upload(client, release_id, path)
    verify(client, release_id, version, sha, files, notes)
    print(f"draft {release_id} holds {len(files)} files from commit {sha}")
    return plan


# ------------------------------------------------------------------------------ CLI


def _client() -> GitHubClient:
    repository = os.environ.get("GITHUB_REPOSITORY")
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not repository or not token:
        raise ReleaseError("GITHUB_REPOSITORY and GH_TOKEN must be set")
    return GitHubClient(repository, token)


def _find_draft(client: Client, version: str) -> int:
    tag = f"v{version}"
    matches = matching_releases(client.list_releases(), tag)
    if len(matches) != 1 or not matches[0].get("draft"):
        raise ReleaseError(f"expected exactly one draft for {tag}, found {len(matches)}")
    return int(matches[0]["id"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    stage_p = sub.add_parser("stage", help="check and flatten downloaded artifacts")
    stage_p.add_argument("--artifacts", type=Path, required=True)
    stage_p.add_argument("--out", type=Path, required=True)
    stage_p.add_argument("--version", required=True)
    for name in ("sync", "verify"):
        p = sub.add_parser(name)
        p.add_argument("--assets", type=Path, required=True, help="folder written by stage")
        p.add_argument("--version", required=True)
        p.add_argument("--sha", required=True, help="the tested commit")
        p.add_argument("--notes", type=Path, required=True)
        if name == "sync":
            p.add_argument("--dry-run", action="store_true", help="print the plan only")
    args = parser.parse_args(argv)
    try:
        if args.command == "stage":
            staged = stage(args.artifacts, args.out, args.version)
            for name, path in staged.items():
                print(f"{sha256_file(path)}  {name}")
            return 0
        files = load_staged(args.assets, args.version)
        notes = args.notes.read_text(encoding="utf-8")
        client = _client()
        if args.command == "sync":
            sync(client, args.version, args.sha, files, notes, dry_run=args.dry_run)
        else:
            check_commit(client, f"v{args.version}", args.sha)
            release_id = _find_draft(client, args.version)
            verify(client, release_id, args.version, args.sha, files, notes)
            print(f"draft {release_id} verified")
    except ReleaseError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", "replace")
        print(f"error: GitHub API {error.code} for {error.url}: {detail}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
