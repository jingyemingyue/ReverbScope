"""Release smoke failure paths against subprocess stand-ins, without a bundle."""

from __future__ import annotations

import importlib.util
import json
import os
import shlex
import subprocess
import sys
import textwrap
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
BINARY = Path("a bundle/roomscope")


@pytest.fixture
def smoke() -> ModuleType:
    spec = importlib.util.spec_from_file_location("smoke_bundle", ROOT / "scripts/smoke_bundle.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _report() -> dict[str, Any]:
    return {
        "packages": {"numpy": "2.5.3", "scipy": "1.18.1"},
        "audio_callbacks": "ok",
        "build": {"commit": "abc", "package": "desktop"},
        "machine": "AMD64",
    }


def _reply(smoke: ModuleType, monkeypatch: pytest.MonkeyPatch, stdout: str) -> None:
    def run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        assert kwargs["encoding"] == "utf-8" and kwargs["timeout"] == 120
        return subprocess.CompletedProcess(argv, 0, stdout, "")

    monkeypatch.setattr(smoke.subprocess, "run", run)


def test_subprocess_failure_retains_the_command_and_both_streams(
    smoke: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    def run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(argv, 7, "partial output\n", "具体原因\n")

    monkeypatch.setattr(smoke.subprocess, "run", run)
    with pytest.raises(SystemExit) as failure:
        smoke.check_doctor(BINARY)
    message = str(failure.value)
    assert "exit 7, expected 0" in message
    assert f"{shlex.quote(str(BINARY))} --backend fake doctor --json" in message
    assert "stdout:\npartial output" in message and "stderr:\n具体原因" in message
    assert "Traceback" not in message


@pytest.mark.parametrize("kind", ["missing", "permission", "timeout"])
def test_launch_and_timeout_errors_are_readable(
    smoke: ModuleType, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    def run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        if kind == "missing":
            raise FileNotFoundError(2, "No such file", argv[0])
        if kind == "permission":
            raise PermissionError(13, "Permission denied", argv[0])
        raise subprocess.TimeoutExpired(argv, 120, output=b"partial output", stderr="超时".encode())

    monkeypatch.setattr(smoke.subprocess, "run", run)
    with pytest.raises(SystemExit) as failure:
        smoke.check_doctor(BINARY)
    message = str(failure.value)
    assert str(BINARY) in message and "Traceback" not in message
    if kind == "timeout":
        assert "timed out after 120 s" in message
        assert "partial output" in message and "超时" in message
    else:
        assert "cannot start command" in message


@pytest.mark.parametrize("output", ["not JSON", "{} trailing text", "[]", "null"])
def test_doctor_rejects_invalid_json_and_non_objects(
    smoke: ModuleType, monkeypatch: pytest.MonkeyPatch, output: str
) -> None:
    _reply(smoke, monkeypatch, output)
    with pytest.raises(SystemExit) as failure:
        smoke.check_doctor(BINARY)
    message = str(failure.value)
    assert "doctor" in message and "JSON" in message and "command:" in message
    assert "Traceback" not in message


@pytest.mark.parametrize("packages", [None, [], {}, "bad"])
def test_doctor_rejects_malformed_package_metadata(
    smoke: ModuleType, monkeypatch: pytest.MonkeyPatch, packages: object
) -> None:
    report = {**_report(), "packages": packages}
    _reply(smoke, monkeypatch, json.dumps(report))
    with pytest.raises(SystemExit, match="packages must be a non-empty object"):
        smoke.check_doctor(BINARY)


@pytest.mark.parametrize("version", [None, "", 123, {"version": "2.5.3"}])
def test_doctor_requires_version_strings(
    smoke: ModuleType, monkeypatch: pytest.MonkeyPatch, version: object
) -> None:
    report = {**_report(), "packages": {"numpy": version}}
    _reply(smoke, monkeypatch, json.dumps(report))
    with pytest.raises(SystemExit, match="no version for: numpy"):
        smoke.check_doctor(BINARY)


@pytest.mark.parametrize("build", [[], ["abc"], "abc", 12])
def test_doctor_rejects_malformed_build_metadata(
    smoke: ModuleType, monkeypatch: pytest.MonkeyPatch, build: object
) -> None:
    _reply(smoke, monkeypatch, json.dumps({**_report(), "build": build}))
    with pytest.raises(SystemExit, match="invalid build metadata"):
        smoke.check_doctor(BINARY)


def test_source_installs_do_not_need_build_metadata(
    smoke: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    report = {**_report(), "build": None}
    _reply(smoke, monkeypatch, json.dumps(report))
    assert smoke.check_doctor(BINARY) == report


def test_cli_only_smoke_does_not_require_optional_qt(
    smoke: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    report = _report()
    report["packages"].update(
        {"matplotlib": "3.11.2", "PySide6_Essentials": None, "shiboken6": None}
    )
    _reply(smoke, monkeypatch, json.dumps(report))
    assert smoke.check_doctor(BINARY, require_gui=False) == report
    with pytest.raises(SystemExit, match="no version for: PySide6_Essentials, shiboken6"):
        smoke.check_doctor(BINARY)
    report["packages"]["matplotlib"] = None
    _reply(smoke, monkeypatch, json.dumps(report))
    with pytest.raises(SystemExit, match="no version for: matplotlib"):
        smoke.check_doctor(BINARY, require_gui=False)


def test_doctor_checks_requested_edition_and_machine(
    smoke: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    _reply(smoke, monkeypatch, json.dumps(_report()))
    smoke.check_doctor(BINARY, "abc", expect_package="desktop", expect_machine="x86_64")
    with pytest.raises(SystemExit, match="expected 'terminal'"):
        smoke.check_doctor(BINARY, expect_package="terminal")
    with pytest.raises(SystemExit, match="expected 'arm64'"):
        smoke.check_doctor(BINARY, expect_machine="arm64")


def test_terminal_smoke_refuses_bundled_gui_libraries(
    smoke: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    report = _report()
    report["packages"]["PySide6_Essentials"] = "6.11.2"
    _reply(smoke, monkeypatch, json.dumps(report))
    with pytest.raises(
        SystemExit, match="Terminal Edition carries GUI libraries: PySide6_Essentials"
    ):
        smoke.check_doctor(BINARY, terminal=True)


@pytest.mark.parametrize("json_output", ["{}", "null", "{}\nextra report"])
def test_first_run_checks_languages_and_clean_json(
    smoke: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, json_output: str
) -> None:
    calls: list[list[str]] = []

    def run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        assert kwargs["encoding"] == "utf-8"
        assert kwargs["env"]["ROOMSCOPE_HOME"] == str(tmp_path / "home")
        assert kwargs["env"]["NO_COLOR"] == "1"
        assert "FORCE_COLOR" not in kwargs["env"]
        if "demo" in argv:
            assert kwargs["timeout"] == 300
            output = "Synthetic data" if argv[2] == "en" else "合成数据"
        else:
            assert kwargs["timeout"] == 120
            output = json_output
        return subprocess.CompletedProcess(argv, 0, output, "")

    monkeypatch.setenv("FORCE_COLOR", "1")
    monkeypatch.setattr(smoke.subprocess, "run", run)
    if json_output == "{}":
        smoke.check_first_run(BINARY, tmp_path)
    else:
        with pytest.raises(SystemExit, match="JSON"):
            smoke.check_first_run(BINARY, tmp_path)
    assert [argv[2] for argv in calls[:2]] == ["en", "zh_CN"]
    assert calls[2][1:4] == ["--format", "json", "show"]


def test_first_run_refuses_success_without_the_demo_marker(
    smoke: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        smoke.subprocess,
        "run",
        lambda argv, **kwargs: subprocess.CompletedProcess(argv, 0, "empty success", ""),
    )
    with pytest.raises(SystemExit, match="--lang en demo failed"):
        smoke.check_first_run(BINARY, tmp_path)


@pytest.mark.parametrize("code", [0, 2])
def test_terminal_gui_refusal_requires_exit_two_in_both_languages(
    smoke: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, code: int
) -> None:
    languages: list[str] = []

    def run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        lang = argv[2]
        languages.append(lang)
        assert argv[3] == "gui"
        assert kwargs["timeout"] == 120 and kwargs["encoding"] == "utf-8"
        sentence = smoke.TERMINAL_GUI_TEXT[lang].replace(" ", "\n")
        return subprocess.CompletedProcess(argv, code, "", sentence)

    monkeypatch.setattr(smoke.subprocess, "run", run)
    if code == 2:
        smoke.check_terminal_gui_refusal(BINARY, tmp_path)
        assert languages == ["en", "zh_CN"]
    else:
        with pytest.raises(SystemExit, match="exit 0, expected 2"):
            smoke.check_terminal_gui_refusal(BINARY, tmp_path)


def test_smoke_output_directory_failure_is_readable(smoke: ModuleType, tmp_path: Path) -> None:
    out = tmp_path / "file"
    out.write_text("keep me", encoding="utf-8")
    with pytest.raises(SystemExit) as failure:
        smoke.main(["--roomscope", str(BINARY), "--no-gui", "--out", str(out)])
    assert f"cannot create smoke output directory {out}" in str(failure.value)
    assert out.read_text(encoding="utf-8") == "keep me"


def test_cli_smoke_is_bounded_isolated_and_always_uses_fake_acquisition(
    smoke: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[list[str]] = []
    out = tmp_path / "session"

    def run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        assert kwargs["timeout"] == 120 and kwargs["encoding"] == "utf-8"
        assert kwargs["env"]["ROOMSCOPE_HOME"] == str(tmp_path / "session-home")
        if "--version" in argv:
            output = "roomscope 0.5.0b1"
        elif "doctor" in argv:
            assert argv[1:3] == ["--backend", "fake"]
            output = json.dumps(_report())
        else:
            assert argv[1:4] == ["--backend", "fake", "measure"]
            out.mkdir()
            (out / "session.json").write_text("{}", encoding="utf-8")
            output = "saved\n"
        return subprocess.CompletedProcess(argv, 0, output, "")

    monkeypatch.setattr(smoke.subprocess, "run", run)
    smoke.smoke(BINARY, out, gui=False, first_run=False)
    assert len(calls) == 3


@pytest.mark.parametrize("failed", [False, True], ids=["success", "failure"])
def test_smoke_logs_and_uncaught_failures_survive_a_narrow_parent_encoding(
    tmp_path: Path, failed: bool
) -> None:
    """Exercise interpreter-rendered SystemExit too, using only subprocess stand-ins."""
    binary = tmp_path / "中文 bundle" / "roomscope"
    out = tmp_path / "合成 session"
    harness = textwrap.dedent(
        """
        import importlib.util
        import json
        import subprocess
        import sys
        from pathlib import Path

        spec = importlib.util.spec_from_file_location("smoke_bundle", sys.argv[1])
        smoke = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(smoke)
        binary, out, failed = sys.argv[2:]

        def fake_run(argv, **kwargs):
            if "--version" in argv:
                return subprocess.CompletedProcess(argv, 0, "roomscope 0.5.0b1", "")
            if "doctor" in argv:
                report = {"packages": {"numpy": "2.5.3"}, "audio_callbacks": "ok"}
                return subprocess.CompletedProcess(argv, 0, json.dumps(report), "")
            assert argv[1:4] == ["--backend", "fake", "measure"]
            if failed == "true":
                return subprocess.CompletedProcess(argv, 7, "部分结果 Δ\\n", "测量失败 Δ\\n")
            (Path(out) / "session.json").write_text("{}", encoding="utf-8")
            return subprocess.CompletedProcess(argv, 0, "已保存 Δ\\n", "合成警告 Δ\\n")

        smoke.subprocess.run = fake_run
        raise SystemExit(smoke.main([
            "--roomscope", binary, "--out", out, "--no-gui", "--skip-first-run"
        ]))
        """
    )
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "cp1252:strict"
    done = subprocess.run(
        [
            sys.executable,
            "-c",
            harness,
            str(ROOT / "scripts" / "smoke_bundle.py"),
            str(binary),
            str(out),
            "true" if failed else "false",
        ],
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    assert "Traceback" not in done.stderr and "UnicodeEncodeError" not in done.stderr
    if failed:
        assert done.returncode == 1
        assert "exit 7, expected 0" in done.stderr
        assert str(binary) in done.stderr and str(out) in done.stderr
        assert "stdout:\n部分结果 Δ" in done.stderr
        assert "stderr:\n测量失败 Δ" in done.stderr
        assert not (out / "session.json").exists()
    else:
        assert done.returncode == 0
        assert f"已保存 Δ\nsmoke ok: {binary}\n" == done.stdout
        assert done.stderr == "合成警告 Δ\n"
        assert (out / "session.json").is_file()
