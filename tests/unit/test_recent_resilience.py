"""A failed convenience-history lookup must not hide good or saved sessions."""

from __future__ import annotations

import errno
import json
from pathlib import Path

import pytest

from reverbscope.io import jsonutil, recent


def _session(base: Path, name: str) -> Path:
    folder = base / name
    folder.mkdir()
    (folder / "session.json").write_text("{}", encoding="utf-8")
    return folder.resolve()


def _history(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, sessions: list[Path]) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("REVERBSCOPE_HOME", str(home))
    store = home / recent.RECENT_FILENAME
    store.write_text(
        json.dumps({"sessions": [str(folder) for folder in sessions]}), encoding="utf-8"
    )
    return store


@pytest.mark.parametrize("unreadable", ["directory", "marker"])
def test_an_unsearchable_recent_entry_keeps_later_sessions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, unreadable: str
) -> None:
    bad = _session(tmp_path, "no-longer-searchable")
    first = _session(tmp_path, "first-readable")
    second = _session(tmp_path, "second-readable")
    store = _history(tmp_path, monkeypatch, [bad, first, second])
    before = store.read_bytes()
    method = "is_dir" if unreadable == "directory" else "is_file"
    target = bad if unreadable == "directory" else bad / "session.json"
    original = getattr(Path, method)

    def inaccessible(path: Path) -> bool:
        if path == target:
            raise PermissionError(errno.EACCES, "Permission denied", str(path))
        return original(path)

    with monkeypatch.context() as denied:
        denied.setattr(Path, method, inaccessible)
        assert recent.recent_session_paths() == [first, second]
        assert recent.recent_session_paths(limit=1) == [first]
    assert store.read_bytes() == before


def test_a_recent_store_that_cannot_be_examined_returns_no_sessions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    saved = _session(tmp_path, "saved")
    store = _history(tmp_path, monkeypatch, [saved])
    before = store.read_bytes()
    original = Path.is_file

    def inaccessible(path: Path) -> bool:
        if path == store:
            raise PermissionError(errno.EACCES, "Permission denied", str(path))
        return original(path)

    with monkeypatch.context() as denied:
        denied.setattr(Path, "is_file", inaccessible)
        assert recent.recent_session_paths() == []
    assert store.read_bytes() == before
    assert (saved / "session.json").read_text(encoding="utf-8") == "{}"


@pytest.mark.parametrize("operation", ["examine", "read"])
def test_remembering_after_a_failed_history_read_preserves_the_saved_take_and_history(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, operation: str
) -> None:
    older = _session(tmp_path, "older")
    saved = _session(tmp_path, "already-saved")
    store = _history(tmp_path, monkeypatch, [older])
    before = store.read_bytes()
    original_is_file = Path.is_file
    original_read_text = Path.read_text

    def cannot_examine(path: Path) -> bool:
        if path == store:
            raise PermissionError(errno.EACCES, "Permission denied", str(path))
        return original_is_file(path)

    def cannot_read(path: Path, *args: object, **kwargs: object) -> str:
        if path == store:
            raise PermissionError(errno.EACCES, "Permission denied", str(path))
        return original_read_text(path, *args, **kwargs)

    with monkeypatch.context() as denied:
        if operation == "examine":
            denied.setattr(Path, "is_file", cannot_examine)
        else:
            denied.setattr(Path, "read_text", cannot_read)
        recent.remember_session(saved)
    assert store.read_bytes() == before
    assert (saved / "session.json").read_text(encoding="utf-8") == "{}"


def test_a_failed_history_write_keeps_the_history_and_the_saved_take(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    older = _session(tmp_path, "older")
    saved = _session(tmp_path, "already-saved")
    store = _history(tmp_path, monkeypatch, [older])
    before = store.read_bytes()

    def full_disk(_descriptor: int) -> None:
        raise OSError(errno.ENOSPC, "No space left on device")

    with monkeypatch.context() as failed_write:
        failed_write.setattr(jsonutil.os, "fsync", full_disk)
        with caplog.at_level("WARNING", logger="reverbscope.io.recent"):
            recent.remember_session(saved)
    assert store.read_bytes() == before
    assert (saved / "session.json").read_text(encoding="utf-8") == "{}"
    assert list(store.parent.iterdir()) == [store]
    assert any("recent-sessions list" in record.getMessage() for record in caplog.records)


def test_healthy_history_keeps_order_deduplication_and_positive_limits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = _session(tmp_path, "first")
    second = _session(tmp_path, "second")
    third = _session(tmp_path, "third")
    _history(tmp_path, monkeypatch, [])
    for session in (third, second, first):
        recent.remember_session(session)
    assert recent.recent_session_paths() == [first, second, third]
    recent.remember_session(second / "session.json")
    assert recent.recent_session_paths() == [second, first, third]
    assert recent.recent_session_paths(limit=1) == [second]
    assert recent.recent_session_paths(limit=2) == [second, first]
