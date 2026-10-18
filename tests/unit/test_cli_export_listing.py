"""Export and session listings keep a failed or unreadable take visible.

A CSV export wrote straight into the previous files, so a full disk part-way
through left one session's curves beside another's. ``show --list`` and the
project commands skipped a ``session.json`` they could not read without saying
so. ``export --out`` that named a file was reported only after the session had
been loaded, and in the operating system's English.
"""

from __future__ import annotations

import errno
import json
from pathlib import Path

import pytest

from reverbscope.cli.main import main
from reverbscope.io.session_store import save_measurement
from reverbscope.models.result import AnalysisResult
from reverbscope.models.session import MeasurementSession


def _save(folder: Path, result: AnalysisResult, *, position: str = "A") -> None:
    save_measurement(
        folder,
        MeasurementSession(room_name="Booth", measurement_position=position),
        result,
        include_curves=True,
        copy_recording=False,
    )


def _bytes(folder: Path) -> dict[str, bytes]:
    return {path.name: path.read_bytes() for path in folder.iterdir() if path.is_file()}


def test_a_failed_csv_export_leaves_the_previous_files_whole(
    tmp_path: Path, analysed_result: AnalysisResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Opening the next curve with ``"w"`` truncated it before the write failed."""
    from reverbscope.errors import SessionError
    from reverbscope.io.exporters.csv import export_csv

    export_csv(analysed_result, tmp_path)
    before = _bytes(tmp_path)
    assert "frequency_response.csv" in before
    (tmp_path / "notes.txt").write_text("mine", encoding="utf-8")
    before = _bytes(tmp_path)

    real_open = Path.open

    def open_and_fail(self: Path, mode: str = "r", *args: object, **kwargs: object):
        handle = real_open(self, mode, *args, **kwargs)  # type: ignore[arg-type]
        writing = "w" in mode
        name = self.name
        if writing and (
            name == "frequency_response.csv" or name.startswith(".frequency_response.")
        ):
            handle.close()
            raise OSError(errno.ENOSPC, "No space left on device", str(self))
        return handle

    monkeypatch.setattr(Path, "open", open_and_fail)
    with pytest.raises(SessionError, match="cannot write"):
        export_csv(analysed_result, tmp_path)
    assert _bytes(tmp_path) == before
    assert not any(name.startswith(".") for name in _bytes(tmp_path))


def test_a_replace_that_fails_puts_the_earlier_curve_back(
    tmp_path: Path, analysed_result: AnalysisResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The first curve of a new export must not stay behind when the next replace fails."""
    import os
    from dataclasses import replace

    from reverbscope.errors import SessionError
    from reverbscope.io.exporters import csv as csv_export

    export_csv = csv_export.export_csv
    export_csv(analysed_result, tmp_path)
    before = _bytes(tmp_path)
    changed = replace(
        analysed_result,
        decay=replace(
            analysed_result.decay,
            broadband=replace(analysed_result.decay.broadband, band_label="CHANGED-LABEL"),
        ),
    )
    real_replace = os.replace
    seen = {"n": 0}

    def fail_second(src: object, dst: object, *args: object, **kwargs: object) -> None:
        if (
            Path(str(dst)).name == "energy_metrics.csv"
            and ".energy_metrics." in Path(str(src)).name
        ):
            seen["n"] += 1
            if seen["n"] == 1:
                raise OSError(errno.ENOSPC, "No space left on device", str(dst))
        real_replace(src, dst, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(csv_export.os, "replace", fail_second)
    with pytest.raises(SessionError, match="cannot write"):
        export_csv(changed, tmp_path)
    assert _bytes(tmp_path) == before
    assert b"CHANGED-LABEL" not in (tmp_path / "decay_metrics.csv").read_bytes()
    assert not any(name.startswith(".") for name in _bytes(tmp_path))


def test_export_refuses_a_file_and_an_unknown_format_before_reading(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from reverbscope.io import session_store

    victim = tmp_path / "victim.csv"
    victim.write_text("keep", encoding="utf-8")

    def never(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("the session was read")

    monkeypatch.setattr(session_store, "load_measurement", never)
    assert main(["export", str(tmp_path / "missing"), "--out", str(victim)]) == 1
    err = " ".join(capsys.readouterr().err.split())
    assert "victim.csv is a file" in err and "folder" in err
    assert victim.read_text(encoding="utf-8") == "keep"

    assert main(["--lang", "zh_CN", "export", str(tmp_path / "missing"), "--out", str(victim)]) == 1
    zh = " ".join(capsys.readouterr().err.split())
    assert "是一个文件" in zh and "曲线" in zh and "File exists" not in zh

    assert main(["export", str(tmp_path / "missing"), "--format", "nope"]) == 1
    assert "unknown exporter" in capsys.readouterr().err


def test_export_shows_a_control_character_in_the_folder_name_as_an_escape(
    tmp_path: Path, analysed_result: AnalysisResult, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = tmp_path / "booth\x1b[2J"
    _save(folder, analysed_result)
    assert main(["--color", "never", "export", str(folder)]) == 0
    out = capsys.readouterr().out
    assert "\x1b" not in out
    assert "\\x1b[2J" in out
    assert (folder / "export" / "decay_metrics.csv").is_file()


def test_show_list_names_a_session_it_cannot_read(
    tmp_path: Path, analysed_result: AnalysisResult, capsys: pytest.CaptureFixture[str]
) -> None:
    good = tmp_path / "good"
    _save(good, analysed_result)
    broken = tmp_path / "broken"
    broken.mkdir()
    (broken / "session.json").write_text("not json", encoding="utf-8")
    hidden = tmp_path / ".hidden"
    hidden.mkdir()
    (hidden / "session.json").write_text("not json", encoding="utf-8")

    assert main(["--color", "never", "show", "--list", str(tmp_path)]) == 0
    captured = capsys.readouterr()
    assert str(good) in captured.out
    assert "broken" not in captured.out
    assert "could not be read" in captured.err and "broken" in captured.err
    assert ".hidden" not in captured.err

    assert main(["--lang", "zh_CN", "--color", "never", "show", "--list", str(tmp_path)]) == 0
    assert "无法读取" in capsys.readouterr().err


def test_project_commands_name_an_unlisted_session_they_cannot_read(
    tmp_path: Path, analysed_result: AnalysisResult, capsys: pytest.CaptureFixture[str]
) -> None:
    from reverbscope.io.project_store import add_session, save_project
    from reverbscope.models.project import Project

    project = tmp_path / "room"
    save_project(project, Project(name="Booth"))
    _save(project / "desk", analysed_result, position="desk")
    add_session(project, project / "desk", position="desk")
    stray = project / "stray"
    stray.mkdir()
    (stray / "session.json").write_text("{", encoding="utf-8")

    assert main(["--color", "never", "project", "show", str(project)]) == 0
    captured = capsys.readouterr()
    assert "desk" in captured.out
    assert "could not be read" in captured.err and "stray" in captured.err

    assert main(["--color", "never", "project", "average", str(project)]) == 0
    averaged = capsys.readouterr()
    assert "ISO 3382-2 class" in averaged.out
    assert "could not be read" in averaged.err and "stray" in averaged.err

    assert main(["--color", "never", "project", "overview", str(project)]) == 0
    overview = " ".join(capsys.readouterr().out.split())
    assert "stray" in overview and "not read" in overview
    assert main(["--format", "json", "project", "overview", str(project)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert any(item[0].endswith("stray") for item in payload["skipped"])
