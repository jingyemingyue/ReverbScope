"""Regressions found by the 2026-09 cross-platform audit (Windows / macOS paths
that the Linux CI does not exercise). Each test emulates the platform
behaviour it guards against."""

from __future__ import annotations

import io
import json
import logging
import os
import sys
from pathlib import Path

import pytest

from roomscope.core.pipeline import Reference, analyze, synthetic_recording
from roomscope.errors import SessionError
from roomscope.i18n import normalize_lang
from roomscope.io.project_store import (
    add_session,
    list_project_sessions,
    project_file,
    save_project,
)
from roomscope.io.session_store import _copy_into, bundle_session, save_measurement
from roomscope.models.configuration import SweepSettings
from roomscope.models.project import Project
from roomscope.models.session import MeasurementSession
from tests.conftest import make_rir


@pytest.fixture(scope="module")
def result(short_sweep: SweepSettings):  # type: ignore[no-untyped-def]
    ir = make_rir(short_sweep.sample_rate, rt60_s=0.3)
    return analyze(
        synthetic_recording(short_sweep, ir, noise_rms=1e-5), Reference.from_settings(short_sweep)
    )


def test_project_stores_forward_slashes_and_reads_backslashes(tmp_path: Path, result) -> None:  # type: ignore[no-untyped-def]
    project_dir = tmp_path / "room"
    save_project(project_dir, Project(name="Booth"))
    session = project_dir / "sessions" / "pos-a"
    save_measurement(session, MeasurementSession(room_name="Booth"), result, include_curves=False)
    add_session(project_dir, session, position="desk")
    raw = json.loads(project_file(project_dir).read_text(encoding="utf-8"))
    stored = raw["positions"][0]["session_dirs"][0]
    assert stored == "sessions/pos-a"

    # A project written on Windows: the same entry with a backslash.
    raw["positions"][0]["session_dirs"] = ["sessions\\pos-a"]
    project_file(project_dir).write_text(json.dumps(raw), encoding="utf-8")
    items = list_project_sessions(project_dir)
    assert items[0] == ("desk", items[0][1])
    assert items[0][1].resolve() == session.resolve()
    assert len(items) == 1

    # Adding the same session again (the path spelled the other way) is a no-op.
    add_session(project_dir, session, position="desk")
    raw = json.loads(project_file(project_dir).read_text(encoding="utf-8"))
    assert len(raw["positions"][0]["session_dirs"]) == 1


def test_bundle_inside_the_session_folder_is_refused(tmp_path: Path, result) -> None:  # type: ignore[no-untyped-def]
    out = tmp_path / "session"
    save_measurement(out, MeasurementSession(room_name="Booth"), result, include_curves=False)
    with pytest.raises(SessionError, match="outside the session folder"):
        bundle_session(out, out)
    with pytest.raises(SessionError, match="outside the session folder"):
        bundle_session(out, out / "report.zip")
    assert not (out / "session.zip").exists()


PAYLOAD = b"RIFF\x24\x00\x00\x00WAVE"


def _state(path: Path) -> tuple[int, int, int, bytes]:
    """Identity and content of a file: inode / file ID, size, mtime, bytes."""
    stat = path.stat()
    return stat.st_ino, stat.st_size, stat.st_mtime_ns, path.read_bytes()


def _case_insensitive(directory: Path) -> bool:
    """True when ``directory`` is on a case-insensitive file system
    (APFS / HFS+ and NTFS by default; ext4 is case-sensitive)."""
    probe = directory / "CaseProbe.tmp"
    probe.write_bytes(b"")
    try:
        return (directory / "caseprobe.tmp").exists()
    finally:
        probe.unlink()


@pytest.mark.parametrize("alias", ["identical path", "hard link"])
def test_copy_onto_the_same_file_is_a_no_op(tmp_path: Path, alias: str) -> None:
    """When source and destination are one file, ``_copy_into`` returns without
    touching it. ``shutil.copy2`` would raise SameFileError, which the session
    store used to report as "cannot copy". Hard links exist on ext4, APFS and
    NTFS, so both cases run on Linux, macOS and Windows."""
    src = tmp_path / "Recording.wav"
    src.write_bytes(PAYLOAD)
    if alias == "identical path":
        dest = tmp_path / "Recording.wav"
    else:
        dest = tmp_path / "take.wav"
        try:
            os.link(src, dest)
        except OSError as exc:  # e.g. FAT / exFAT, which have no hard links
            pytest.skip(f"this file system has no hard links: {exc}")
    assert os.path.samefile(src, dest)
    before = _state(src)
    assert _copy_into(src, dest) == dest
    assert _state(src) == before
    assert _state(dest) == before


def test_copy_to_a_name_that_differs_only_in_case(tmp_path: Path) -> None:
    """A DAW export "Recording.wav" copied into its own folder as "recording.wav".

    On a case-insensitive file system (macOS, Windows) the two names are one
    file and the copy must be a no-op; on a case-sensitive one (Linux) they are
    two files and the copy must produce an identical second file. The test
    asks the file system which case applies, so it checks something real on
    every platform.
    """
    src = tmp_path / "Recording.wav"
    src.write_bytes(PAYLOAD)
    dest = tmp_path / "recording.wav"
    before = _state(src)
    assert _copy_into(src, dest) == dest
    if _case_insensitive(tmp_path):
        assert os.path.samefile(src, dest)
        assert _state(src) == before
    else:
        assert not os.path.samefile(src, dest)
        assert src.read_bytes() == dest.read_bytes() == PAYLOAD
        assert _state(src) == before


def test_copy_over_a_different_file_replaces_it(tmp_path: Path) -> None:
    """Negative control: the same-file shortcut must not swallow a real copy."""
    src = tmp_path / "take.wav"
    src.write_bytes(PAYLOAD)
    dest = tmp_path / "session" / "recording.wav"
    dest.parent.mkdir()
    dest.write_bytes(b"an older recording")
    assert not os.path.samefile(src, dest)
    assert _copy_into(src, dest) == dest
    assert dest.read_bytes() == PAYLOAD
    assert src.read_bytes() == PAYLOAD


@pytest.mark.parametrize(
    ("tag", "expected"),
    [
        ("zh-Hans-CN", "zh_CN"),
        ("zh-Hans", "zh_CN"),
        ("Chinese (Simplified)_China", "zh_CN"),
        (["zh_CN", "UTF-8"][0], "zh_CN"),
        ("en-US", "en_US"),
    ],
)
def test_os_language_tags_are_normalised(tag: str, expected: str) -> None:
    assert normalize_lang(tag) == expected


def test_session_list_survives_dates_windows_cannot_convert(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pytest.importorskip("PySide6")
    from datetime import datetime

    from roomscope.ui import browser

    def refuse(self: datetime, tz: object = None) -> datetime:
        raise OSError(22, "Invalid argument")

    class Moment(datetime):
        astimezone = refuse  # type: ignore[assignment]

    monkeypatch.setattr(browser, "_when", browser._when)
    import datetime as datetime_module

    monkeypatch.setattr(datetime_module, "datetime", Moment)
    assert browser._when("1900-01-01T00:00:00+00:00") == "1900-01-01T00:00:00+00:00"
    assert browser._when("not a date") == "not a date"


def test_log_rotation_keeps_logging_when_the_file_is_locked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from logging.handlers import RotatingFileHandler

    from roomscope.logging_config import _SharedRotatingFileHandler

    def locked(self: RotatingFileHandler) -> None:
        raise PermissionError(32, "The process cannot access the file")

    monkeypatch.setattr(RotatingFileHandler, "doRollover", locked)
    handler = _SharedRotatingFileHandler(tmp_path / "roomscope.log", maxBytes=10, backupCount=1)
    logger = logging.getLogger("roomscope-test-rotation")
    logger.propagate = False
    logger.addHandler(handler)
    errors = io.StringIO()
    monkeypatch.setattr(sys, "stderr", errors)
    try:
        for index in range(5):
            logger.warning("record %d is longer than the limit", index)
    finally:
        logger.removeHandler(handler)
        handler.close()
    assert "Logging error" not in errors.getvalue()
    assert "record 4" in (tmp_path / "roomscope.log").read_text(encoding="utf-8")


@pytest.mark.skipif(sys.platform == "win32", reason="the rename probe is for Windows")
def test_log_rotation_never_vacates_the_log_name_on_posix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The Windows rename probe ran everywhere: on POSIX, another process that
    opened roomscope.log between its two renames lost its records to a
    deleted file."""
    from roomscope import logging_config
    from roomscope.logging_config import _SharedRotatingFileHandler

    renames: list[tuple[str, str]] = []
    real_replace = os.replace

    def recording_replace(source: object, target: object) -> None:
        renames.append((os.fspath(source), os.fspath(target)))  # type: ignore[arg-type]
        real_replace(source, target)  # type: ignore[arg-type]

    monkeypatch.setattr(logging_config.os, "replace", recording_replace)
    base = tmp_path / "roomscope.log"
    handler = _SharedRotatingFileHandler(base, maxBytes=10, backupCount=1)
    logger = logging.getLogger("roomscope-test-posix-rotation")
    logger.propagate = False
    logger.addHandler(handler)
    try:
        for index in range(2):
            logger.warning("record %d is longer than the limit", index)
    finally:
        logger.removeHandler(handler)
        handler.close()
    assert not [target for _, target in renames if target.endswith(".rotating")]
    assert "record 0" in Path(f"{base}.1").read_text(encoding="utf-8")
    assert "record 1" in base.read_text(encoding="utf-8")


def test_default_devices_are_marked(monkeypatch: pytest.MonkeyPatch) -> None:
    """sounddevice returns the defaults as an indexable _InputOutputPair."""
    from roomscope.audio import devices

    class Pair:
        def __init__(self, a: int, b: int) -> None:
            self._items = [a, b]

        def __getitem__(self, index: int) -> int:
            return self._items[index]

    class FakeSd:
        class default:  # noqa: N801 - mirrors sounddevice.default
            device = Pair(1, 0)

        @staticmethod
        def query_devices() -> list[dict[str, object]]:
            return [
                {
                    "name": "Speakers",
                    "hostapi": 0,
                    "max_input_channels": 0,
                    "max_output_channels": 2,
                    "default_samplerate": 48000.0,
                },
                {
                    "name": "Mic",
                    "hostapi": 0,
                    "max_input_channels": 1,
                    "max_output_channels": 0,
                    "default_samplerate": 48000.0,
                },
            ]

        @staticmethod
        def query_hostapis() -> list[dict[str, object]]:
            return [
                {
                    "name": "Windows WASAPI",
                    "devices": [0, 1],
                    "default_input_device": 1,
                    "default_output_device": 0,
                }
            ]

    monkeypatch.setattr(devices, "sounddevice_module", lambda: FakeSd)
    listed = devices.list_devices()
    assert listed[1].is_default_input and not listed[1].is_default_output
    assert listed[0].is_default_output and not listed[0].is_default_input


def test_cli_output_to_a_pipe_is_utf8(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import importlib

    cli = importlib.import_module("roomscope.cli.main")

    raw = io.BytesIO()
    stream = io.TextIOWrapper(raw, encoding="cp1252", errors="strict")
    monkeypatch.delenv("PYTHONIOENCODING", raising=False)
    monkeypatch.setattr(sys, "stdout", stream)
    cli._prepare_streams()
    sys.stdout.write("Δ → 录音棚\n")
    sys.stdout.flush()
    assert raw.getvalue().decode("utf-8").strip() == "Δ → 录音棚"


def test_a_locked_log_keeps_its_backups(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The stdlib shifts .1 -> .2 -> .3 before it renames the live file; when
    that rename failed (Windows, another RoomScope process) every record
    pushed one more backup out."""
    import os

    from roomscope import logging_config
    from roomscope.logging_config import _SharedRotatingFileHandler

    base = tmp_path / "roomscope.log"
    for index in (1, 2, 3):
        Path(f"{base}.{index}").write_text(f"backup {index}", encoding="utf-8")
    handler = _SharedRotatingFileHandler(base, maxBytes=10, backupCount=3)
    real_replace = os.replace

    def locked_replace(source: object, target: object) -> None:
        if os.fspath(source) == handler.baseFilename:  # type: ignore[arg-type]
            raise PermissionError(32, "The process cannot access the file")
        real_replace(source, target)  # type: ignore[arg-type]

    monkeypatch.setattr(logging_config, "_RENAME_FAILS_WHILE_OPEN", True)
    monkeypatch.setattr(logging_config.os, "replace", locked_replace)
    monkeypatch.setattr(handler, "rotate", locked_replace)
    logger = logging.getLogger("roomscope-test-backups")
    logger.propagate = False
    logger.addHandler(handler)
    try:
        for index in range(4):
            logger.warning("record %d is longer than the limit", index)
    finally:
        logger.removeHandler(handler)
        handler.close()
    backups = [Path(f"{base}.{index}").read_text(encoding="utf-8") for index in (1, 2, 3)]
    assert backups == ["backup 1", "backup 2", "backup 3"]
    assert "record 3" in base.read_text(encoding="utf-8")
