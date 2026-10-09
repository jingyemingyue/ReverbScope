from __future__ import annotations

import importlib.util
import re
import subprocess
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]
_SHA = re.compile(r"^[0-9a-f]{40}$")
_GOOD = "11d5960a326750d5838078e36cf38b85af677262"
_MISSING = "d6db90100687cd14c0b8c27b0d7b104d0d63bbba"


def _script() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "check_action_pins", ROOT / "scripts" / "check_action_pins.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_github_actions_are_pinned_by_sha() -> None:
    for path in Path(".github/workflows").glob("*.yml"):
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped.startswith("uses:"):
                continue
            ref = stripped.split("uses:", 1)[1].strip().split()[0]
            if ref.startswith("./"):
                continue
            sha = ref.rsplit("@", 1)[-1]
            assert _SHA.match(sha), f"{path}: unpinned action {stripped}"


def _workflows(folder: Path, body: str, name: str = "demo.yml") -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_text(body, encoding="utf-8")
    return folder


_DEMO = f"""\
name: demo
jobs:
  build:
    steps:
      - uses: actions/checkout@{_GOOD} # v4
      - uses: actions/deploy-pages@{_MISSING} # v4
      - uses: ./local-action
      - uses: docker://alpine:3.20
      - uses: actions/checkout@{_GOOD} # v4
"""


def _upstream_has(*known: str):  # type: ignore[no-untyped-def]
    calls: list[tuple[str, str]] = []

    def fetch(repo: str, sha: str) -> str | None:
        calls.append((repo, sha))
        return None if sha in known else "that commit is not in the repository"

    fetch.calls = calls  # type: ignore[attr-defined]
    return fetch


def test_the_repository_workflows_are_scanned_completely() -> None:
    pins, errors = _script().scan(ROOT / ".github" / "workflows")
    assert errors == []
    expected = 0
    for path in (ROOT / ".github" / "workflows").glob("*.yml"):
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip().removeprefix("- ")
            if stripped.startswith("uses:") and not stripped.split()[1].startswith("./"):
                expected += 1
    assert len(pins) == expected > 0
    assert {"actions/checkout", "actions/deploy-pages"} <= {pin.repo for pin in pins}
    assert all(_SHA.match(pin.sha) for pin in pins)


def test_a_pin_upstream_does_not_have_is_named_with_its_file_and_line(tmp_path: Path) -> None:
    root = _workflows(tmp_path / "wf", _DEMO)
    errors = _script().check(root, fetch=_upstream_has(_GOOD))
    assert len(errors) == 1
    assert f"{root / 'demo.yml'}:6: actions/deploy-pages@{_MISSING[:12]}" in errors[0]
    assert "not in the repository" in errors[0]


def test_a_pin_used_twice_is_asked_once_and_reported_at_both_places(tmp_path: Path) -> None:
    body = _DEMO + f"      - uses: actions/deploy-pages@{_MISSING} # v4\n"
    fetch = _upstream_has(_GOOD)
    errors = _script().check(_workflows(tmp_path / "wf", body), fetch=fetch)
    assert [error.split(": ")[0].rsplit(":", 1)[1] for error in errors] == ["6", "10"]
    assert sorted(fetch.calls) == [  # one question per distinct pin
        ("actions/checkout", _GOOD),
        ("actions/deploy-pages", _MISSING),
    ]


def test_local_and_docker_actions_are_not_asked_about(tmp_path: Path) -> None:
    fetch = _upstream_has(_GOOD)
    body = "jobs:\n  a:\n    steps:\n      - uses: ./x\n      - uses: docker://alpine:3.20\n"
    assert _script().check(_workflows(tmp_path / "wf", body), fetch=fetch) == []
    assert fetch.calls == []


def test_a_name_instead_of_a_commit_is_reported_without_asking(tmp_path: Path) -> None:
    fetch = _upstream_has()
    body = "jobs:\n  a:\n    steps:\n      - uses: actions/checkout@v4\n"
    errors = _script().check(_workflows(tmp_path / "wf", body), fetch=fetch)
    assert len(errors) == 1 and "pinned to a name, not to a commit SHA" in errors[0]
    assert ":4:" in errors[0] and fetch.calls == []


def test_a_sub_path_action_is_asked_in_its_repository(tmp_path: Path) -> None:
    fetch = _upstream_has(_GOOD)
    body = f"jobs:\n  a:\n    steps:\n      - uses: owner/repo/sub/dir@{_GOOD}\n"
    assert _script().check(_workflows(tmp_path / "wf", body), fetch=fetch) == []
    assert fetch.calls == [("owner/repo", _GOOD)]


@pytest.mark.parametrize(
    ("stderr", "definite", "why"),
    [
        (
            "fatal: remote error: upload-pack: not our ref " + _MISSING,
            True,
            "not in the repository",
        ),
        ("fatal: couldn't find remote ref " + _MISSING, True, "not in the repository"),
        (
            "fatal: could not read Username for 'https://github.com': terminal prompts disabled",
            True,
            "does not exist or is private",
        ),
        (
            "fatal: unable to access 'https://github.com/a/b.git/': Could not resolve host: github.com",
            False,
            "Could not resolve host",
        ),
        ("", False, "git printed nothing"),
    ],
)
def test_git_failures_are_told_apart(stderr: str, definite: bool, why: str) -> None:
    got_definite, got_why = _script().explain(stderr)
    assert got_definite is definite
    assert why in got_why


def _answers(*results: tuple[int, str]):  # type: ignore[no-untyped-def]
    queue = list(results)
    commands: list[list[str]] = []

    def run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        code, stderr = queue.pop(0)
        return subprocess.CompletedProcess(command, code, "", stderr)

    run.commands = commands  # type: ignore[attr-defined]
    return run


_OFFLINE = (128, "fatal: unable to access 'https://github.com/a/b.git/': Could not resolve host")


def test_an_unreachable_upstream_is_retried_with_a_pause_then_reported(tmp_path: Path) -> None:
    script = _script()
    pauses: list[float] = []
    run = _answers(_OFFLINE, _OFFLINE, _OFFLINE)
    why = script.fetch_commit("a/b", _GOOD, tmp_path, run=run, sleep=pauses.append)
    assert why is not None and "3 attempts" in why and "Could not resolve host" in why
    assert pauses == list(script.BACKOFF)
    assert len(run.commands) == 3


def test_a_retry_that_succeeds_is_a_pass(tmp_path: Path) -> None:
    run = _answers(_OFFLINE, (0, ""))
    assert _script().fetch_commit("a/b", _GOOD, tmp_path, run=run, sleep=lambda _s: None) is None
    assert run.commands[0][-2:] == ["https://github.com/a/b.git", _GOOD]


def test_a_missing_commit_is_final_and_not_retried(tmp_path: Path) -> None:
    run = _answers((128, "fatal: remote error: upload-pack: not our ref " + _MISSING))
    why = _script().fetch_commit(
        "actions/deploy-pages", _MISSING, tmp_path, run=run, sleep=lambda _s: pytest.fail("slept")
    )
    assert why == "that commit is not in the repository"
    assert len(run.commands) == 1


def test_a_git_that_cannot_run_is_reported_not_raised(tmp_path: Path) -> None:
    def broken(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError("git")

    why = _script().fetch_commit("a/b", _GOOD, tmp_path, run=broken, sleep=lambda _s: None)
    assert why is not None and "git fetch did not run" in why
