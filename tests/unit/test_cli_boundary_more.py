"""More CLI boundary inputs beyond empty WAV / sample-rate / Chinese paths.

Asserts exit codes and the ``error:`` marker. Does not lock exact wording.
Complements ``test_cli_boundary_inputs`` (draft #124) without duplicating it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from reverbscope.cli.main import main


def _run(argv: list[str]) -> int:
    try:
        return int(main(argv))
    except SystemExit as exc:
        code = exc.code
        if code is None:
            return 0
        return int(code) if isinstance(code, int) else 1


def test_sweep_rejects_a_duration_below_half_a_second(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _run(["sweep", "--out", str(tmp_path / "s.wav"), "--duration", "0"]) == 1
    err = capsys.readouterr().err
    assert "error:" in err
    assert "duration" in err


def test_compare_requires_a_candidate(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert _run(["compare", str(tmp_path / "only-baseline")]) == 2
    err = capsys.readouterr().err
    assert "error:" in err
    assert "candidate" in err


def test_export_missing_session_fails_cleanly(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _run(["export", str(tmp_path / "no-session"), "--format", "csv"]) == 1
    assert "error:" in capsys.readouterr().err


def test_analyze_ir_missing_file_fails_cleanly(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _run(["analyze-ir", "--ir", str(tmp_path / "missing.wav")]) == 1
    err = capsys.readouterr().err
    assert "error:" in err
    assert "not found" in err


def test_project_show_without_a_project_json_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = tmp_path / "empty-folder"
    folder.mkdir()
    assert _run(["project", "show", str(folder)]) == 1
    err = capsys.readouterr().err
    assert "error:" in err
    assert "project.json" in err


def test_schema_requires_a_document_type(capsys: pytest.CaptureFixture[str]) -> None:
    assert _run(["schema"]) == 2
    err = capsys.readouterr().err
    assert "error:" in err


def test_profiles_rejects_an_unknown_name(capsys: pytest.CaptureFixture[str]) -> None:
    assert _run(["profiles", "no-such-profile-xyz"]) == 2
    err = capsys.readouterr().err
    assert "error:" in err
    assert "invalid choice" in err


def test_doctor_exits_zero_without_devices(capsys: pytest.CaptureFixture[str]) -> None:
    """``doctor`` is a diagnostics entry point: it must not crash when no
    audio hardware is present (this Linux agent has none)."""
    assert _run(["doctor"]) == 0
    # stderr may be empty; stdout may list checks. Either way, no traceback.
    captured = capsys.readouterr()
    assert "Traceback" not in captured.err
    assert "Traceback" not in captured.out
