"""Check that every GitHub Action pinned under .github/workflows exists upstream.

``tests/unit/test_action_pins.py`` proves that each pin has the shape of a
commit SHA. That passed for ``actions/deploy-pages@d6db9010...``, which is not
a commit of that repository, and the Pages deploy job failed the first time it
ran with "Unable to resolve action". This script asks each action's repository
for the pinned commit (``git fetch --depth 1`` of that one commit into a
scratch repository, which also proves GitHub serves it) and names the
workflow file and line of every pin that cannot be fetched.

It needs git and the network (the CI lint job has both). Exit status: 0 when
every pin exists, 1 when a pin is missing or upstream cannot be reached, or
when nothing could be scanned.
"""

from __future__ import annotations

import argparse
import contextlib
import functools
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import NamedTuple

USES = re.compile(r"^\s*(?:-\s+)?uses:\s*(?P<ref>\S+)")
SHA = re.compile(r"^[0-9a-f]{40}$")
ATTEMPTS = 3
#: Seconds to wait before the second and the third attempt when upstream
#: cannot be reached (a missing commit is a definite answer and is not retried).
BACKOFF = (2.0, 5.0)

#: ``fetch(repo, sha)`` returns None when the commit exists, else why not.
Fetch = Callable[[str, str], "str | None"]


class Pin(NamedTuple):
    path: Path
    line: int
    repo: str  # "owner/name": the action's repository, a sub-path dropped
    sha: str


def _workflow_files(root: Path) -> list[Path]:
    return sorted([*root.glob("*.yml"), *root.glob("*.yaml")])


def scan(root: Path) -> tuple[list[Pin], list[str]]:
    """The pins of every workflow under ``root`` and what could not be read."""
    pins: list[Pin] = []
    errors: list[str] = []
    for path in _workflow_files(root):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            errors.append(f"{path}: cannot read workflow: {exc}")
            continue
        for number, line in enumerate(text.splitlines(), start=1):
            match = USES.match(line)
            if match is None:
                continue
            ref = match.group("ref").strip("'\"")
            if ref.startswith(("./", "docker://")):
                continue
            name, _, sha = ref.partition("@")
            if not SHA.match(sha):
                errors.append(f"{path}:{number}: {ref} is pinned to a name, not to a commit SHA")
                continue
            pins.append(Pin(path, number, "/".join(name.split("/")[:2]), sha))
    return pins, errors


def explain(stderr: str) -> tuple[bool, str]:
    """``(definite, why)`` for a failed ``git fetch``.

    A definite answer (the commit or the repository is not there) is final;
    anything else (DNS, TLS, a 5xx from upstream) may pass on a retry.
    """
    lines = [line for line in stderr.strip().splitlines() if line.strip()]
    if "not our ref" in stderr or "couldn't find remote ref" in stderr:
        return True, "that commit is not in the repository"
    if "could not read Username" in stderr or "Repository not found" in stderr:
        return True, "the repository does not exist or is private"
    return False, lines[-1].strip() if lines else "git printed nothing"


def fetch_commit(
    repo: str,
    sha: str,
    scratch: Path,
    *,
    run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    sleep: Callable[[float], None] = time.sleep,
) -> str | None:
    """None if ``repo`` has commit ``sha``, else the reason it could not be had."""
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    command = [
        "git",
        "fetch",
        "--quiet",
        "--depth",
        "1",
        "--no-tags",
        f"https://github.com/{repo}.git",
        sha,
    ]
    last = ""
    for attempt in range(ATTEMPTS):
        if attempt:
            sleep(BACKOFF[attempt - 1])
        try:
            done = run(
                command,
                cwd=scratch,
                env=env,
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            last = f"git fetch did not run: {exc}"
            continue
        if done.returncode == 0:
            return None
        definite, why = explain(done.stderr)
        if definite:
            return why
        last = why
    return f"upstream could not be reached in {ATTEMPTS} attempts ({last})"


def check(root: Path, fetch: Fetch | None = None) -> list[str]:
    """One error per workflow line whose pinned action cannot be fetched upstream."""
    if not root.is_dir():
        return [
            f"{root}: workflow directory not found; run from the repository root or pass --root"
        ]
    if not _workflow_files(root):
        return [f"{root}: no workflow files found"]
    pins, errors = scan(root)
    if not pins:
        return errors
    with contextlib.ExitStack() as stack:
        if fetch is None:
            if shutil.which("git") is None:
                return [*errors, f"{root}: git is not installed; the pins cannot be checked"]
            scratch = Path(stack.enter_context(tempfile.TemporaryDirectory()))
            init = subprocess.run(
                ["git", "init", "--quiet"], cwd=scratch, capture_output=True, text=True, check=False
            )
            if init.returncode != 0:
                return [*errors, f"cannot create a scratch repository: {init.stderr.strip()}"]
            fetch = functools.partial(fetch_commit, scratch=scratch)
        answers: dict[tuple[str, str], str | None] = {}
        for pin in pins:
            key = (pin.repo, pin.sha)
            if key not in answers:
                answers[key] = fetch(pin.repo, pin.sha)
            problem = answers[key]
            if problem is not None:
                errors.append(f"{pin.path}:{pin.line}: {pin.repo}@{pin.sha[:12]}: {problem}")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--root", type=Path, default=Path(".github/workflows"), help="workflows directory"
    )
    args = parser.parse_args(argv)
    errors = check(args.root)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    pins, _ = scan(args.root)
    distinct = len({(pin.repo, pin.sha) for pin in pins})
    files = len({pin.path for pin in pins})
    print(f"action pins ok: {distinct} distinct pins in {files} workflows exist upstream")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
