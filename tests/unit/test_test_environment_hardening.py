"""Guards so a future change cannot quietly undo isolation again."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest


def test_infrastructure_fixtures_do_not_take_the_shared_monkeypatch() -> None:
    """Autouse isolation must not list ``monkeypatch`` among its parameters."""
    import inspect

    import tests.conftest as conf

    for name in (
        "isolate_reverbscope_home",
        "pin_language",
        "session_isolated_reverbscope_home",
    ):
        fixture = getattr(conf, name)
        raw = getattr(fixture, "__pytest_wrapped__", fixture)
        func = getattr(raw, "obj", raw)
        parameters = inspect.signature(func).parameters
        assert "monkeypatch" not in parameters, name


def test_preexisting_reverbscope_home_is_overlaid_not_ignored(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A process that already set REVERBSCOPE_HOME still gets a per-test folder."""
    # The autouse fixture already overlaid; the value must be a pytest temp.
    home = Path(os.environ["REVERBSCOPE_HOME"]).resolve()
    assert "pytest" in str(home) or "reverbscope_home" in str(home)
    assert home != (Path.home() / ".reverbscope").resolve()
    monkeypatch.setenv("REVERBSCOPE_HOME", str(tmp_path / "custom"))
    assert Path(os.environ["REVERBSCOPE_HOME"]).resolve() == (tmp_path / "custom").resolve()
    monkeypatch.undo()
    # Infrastructure overlay returns.
    assert Path(os.environ["REVERBSCOPE_HOME"]).resolve() == home


def test_order_english_then_chinese_then_english(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from tests.frames import invoke

    monkeypatch.setenv("REVERBSCOPE_HOME", str(tmp_path / "home"))
    code, _out, err = invoke(["--lang", "en", "--style", "boxed", "show", "x", "--bogus"], capsys)
    assert code == 2 and err.startswith("╭─ ✗ Error ─")
    code, _out, err = invoke(
        ["--lang", "zh_CN", "--style", "boxed", "show", "x", "--bogus"], capsys
    )
    assert code == 2 and err.startswith("╭─ ✗ 错误 ─")
    code, _out, err = invoke(["--lang", "en", "--style", "boxed", "show", "x", "--bogus"], capsys)
    assert code == 2 and err.startswith("╭─ ✗ Error ─")


def test_child_process_without_inherited_home_is_not_required() -> None:
    """Document that subprocess tests must pass the isolated env explicitly.

    Clearing REVERBSCOPE_HOME in a child is a deliberate escape; the parent
    suite must keep its own value.
    """
    parent = os.environ.get("REVERBSCOPE_HOME")
    assert parent
    done = subprocess.run(
        [
            sys.executable,
            "-c",
            "import os; print(os.environ.get('REVERBSCOPE_HOME', ''))",
        ],
        check=True,
        capture_output=True,
        text=True,
        env={k: v for k, v in os.environ.items() if k != "REVERBSCOPE_HOME"},
    )
    assert done.stdout.strip() == ""
    assert os.environ.get("REVERBSCOPE_HOME") == parent
