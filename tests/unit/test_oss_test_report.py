"""Tester evidence must survive reruns and never turn collection into hardware PASS."""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def report_tool() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "prepare_test_report", ROOT / "scripts" / "prepare_test_report.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("language", ["en", "zh-CN"])
def test_environment_success_does_not_certify_hardware(
    report_tool: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, language: str
) -> None:
    calls: list[list[str]] = []

    def run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        assert not kwargs.get("shell")
        return subprocess.CompletedProcess(command, 0, json.dumps({"reverbscope": "0.5.0rc2"}))

    monkeypatch.setattr(report_tool.subprocess, "run", run)
    out = tmp_path / "fresh run"
    report_tool.prepare(
        out, "/Applications/My App.app/Contents/MacOS/My App", "Studio One 7", language, True, True
    )
    assert calls == [
        ["/Applications/My App.app/Contents/MacOS/My App", "doctor", "--json", "--probe"]
    ]
    data = json.loads((out / "run.json").read_text(encoding="utf-8"))
    assert data["environment_collection"] == "Automated PASS"
    assert data["sample_rates_probed"] is True
    assert set(data["checks"].values()) == {"NOT RUN"}
    assert {"stop", "disconnect", "save_reopen", "loopback", "daw_roundtrip"} <= data[
        "checks"
    ].keys()
    assert (out / "report.md").read_text(encoding="utf-8").count("| NOT RUN |") == len(
        data["checks"]
    )
    for path in out.iterdir():
        assert "/Applications/My App" not in path.read_text(encoding="utf-8")


def test_public_beta_environment_is_accepted_without_renaming_its_version(
    report_tool: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The actual public beta's doctor JSON still uses the roomscope key."""
    monkeypatch.setattr(
        report_tool.subprocess,
        "run",
        lambda *_a, **_k: subprocess.CompletedProcess([], 0, '{"roomscope": "0.5.0b1"}'),
    )
    status, environment = report_tool.collect_environment("roomscope", False)
    assert status == "Automated PASS"
    assert environment["roomscope"] == "0.5.0b1"


@pytest.mark.parametrize(
    ("code", "stdout"),
    [(1, "/Users/private/take.wav"), (0, "not json"), (0, "[]"), (0, '{"unknown": "version"}')],
)
def test_collection_failures_are_explicit_and_private(
    report_tool: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, code: int, stdout: str
) -> None:
    monkeypatch.setattr(
        report_tool.subprocess,
        "run",
        lambda *_a, **_k: subprocess.CompletedProcess([], code, stdout, "/Users/private/error"),
    )
    out = tmp_path / "failed-run"
    report_tool.prepare(out, "bad-app", "NOT RUN", "en", False, True)
    run = json.loads((out / "run.json").read_text(encoding="utf-8"))
    assert run["environment_collection"] == "FAIL"
    assert set(run["checks"].values()) == {"NOT RUN"}
    assert "/Users/private" not in "".join(p.read_text(encoding="utf-8") for p in out.iterdir())


@pytest.mark.parametrize(
    "failure", [OSError("private path"), subprocess.TimeoutExpired("private path", 45)]
)
def test_unavailable_or_hung_app_preserves_a_not_run_report(
    report_tool: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: Exception
) -> None:
    def run(*_args: Any, **_kwargs: Any) -> Any:
        raise failure

    monkeypatch.setattr(report_tool.subprocess, "run", run)
    report_tool.prepare(tmp_path / "run", "app", "NOT RUN", "en", False, True)
    report = json.loads((tmp_path / "run" / "run.json").read_text(encoding="utf-8"))
    assert report["environment_collection"] == "FAIL"
    assert "private path" not in (tmp_path / "run" / "environment.json").read_text(encoding="utf-8")


def test_existing_run_is_not_overwritten_or_recollected(
    report_tool: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unexpected(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("recollecting could overwrite evidence")

    monkeypatch.setattr(report_tool, "collect_environment", unexpected)
    out = tmp_path / "run"
    out.mkdir()
    evidence = out / "report.md"
    evidence.write_text("Hardware PASS from an actual tester", encoding="utf-8")
    with pytest.raises(FileExistsError):
        report_tool.prepare(out, "app", "DAW", "en", False, True)
    assert evidence.read_text(encoding="utf-8") == "Hardware PASS from an actual tester"


def test_blank_report_never_invokes_an_app(
    report_tool: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unexpected(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("skip-environment must not enumerate hardware")

    monkeypatch.setattr(report_tool, "collect_environment", unexpected)
    report_tool.prepare(tmp_path / "blank", "app", "NOT RUN", "en", True, False)
    data = json.loads((tmp_path / "blank" / "run.json").read_text(encoding="utf-8"))
    assert data["environment_collection"] == "NOT RUN"
    assert not data["sample_rates_probed"]


def test_collected_data_omits_paths_settings_and_exception_text(
    report_tool: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    raw = {
        "reverbscope": "0.5.0rc2",
        "build": {"commit": "a" * 40, "package": "/Users/private/build"},
        "paths": {"log": "D:\\private\\recording.log"},
        "settings": {"output_dir": "/mnt/private/recordings"},
        "audio": {
            "devices": [{"name": "Anna's USB microphone", "note": "/mnt/private/take"}],
            "error": "/secret/failure",
        },
    }
    monkeypatch.setattr(
        report_tool.subprocess,
        "run",
        lambda *_a, **_k: subprocess.CompletedProcess([], 0, json.dumps(raw)),
    )
    status, result = report_tool.collect_environment("app", False)
    assert status == "Automated PASS"
    assert result["build_commit"] == "a" * 40
    assert not {"settings", "paths", "build"} & result.keys()
    text = json.dumps(result)
    assert "private" not in text and "secret" not in text
    assert "Anna's USB microphone" in text  # needs the explicitly documented human review


def test_public_install_guide_names_assets_from_a_published_release() -> None:
    snapshot = json.loads(
        (ROOT / "docs/evidence/oss-readiness-2026-10-15.json").read_text(encoding="utf-8")
    )
    public = [r for r in snapshot["releases"] if not r["draft"]]
    latest = max(public, key=lambda r: r["published_at"])
    assert latest["tag"] == "v0.5.0b1"
    assets = {a["name"] for a in latest["assets"]}
    pattern = r"(?:RoomScope|roomscope)-[\w.-]+\.(?:dmg|zip|exe|tar\.gz|whl)\b"
    for filename in ("PUBLIC_TESTING.md", "PUBLIC_TESTING.zh-CN.md"):
        text = (ROOT / "docs" / filename).read_text(encoding="utf-8")
        # The Windows GUI launcher is inside the ZIP, not a separate asset.
        mentioned = set(re.findall(pattern, text)) - {"roomscope-gui.exe"}
        assert mentioned <= assets, mentioned - assets
        assert {name for name in assets if name.startswith("RoomScope-")} <= mentioned
        assert latest["url"] in text
        assert "roomscope demo" in text


def test_application_answers_fit_the_inspected_form_limits() -> None:
    text = (ROOT / "docs/OSS_APPLICATION_DRAFT.md").read_text(encoding="utf-8")
    section = text.split("## Copy-ready form fields", 1)[1].split("## Proposed next", 1)[0]
    answers = re.findall(r"(?ms)^### [^\n]+\n\n(.*?)(?=^### |\Z)", section)
    assert len(answers) == 3
    assert all(0 < len(answer.strip()) <= 500 for answer in answers)
