from __future__ import annotations

import json
from pathlib import Path

import pytest

from roomscope.core.pipeline import Reference, analyze, synthetic_recording
from roomscope.io.recent import recent_session_paths, remember_session
from roomscope.io.session_store import save_measurement
from roomscope.models.configuration import SweepSettings
from roomscope.models.session import MeasurementSession
from tests.conftest import make_rir


def _save_session(directory: Path, sweep: SweepSettings, room: str) -> Path:
    ir = make_rir(sweep.sample_rate, rt60_s=0.3)
    rec = synthetic_recording(sweep, ir, noise_rms=1e-5)
    result = analyze(rec, Reference.from_settings(sweep))
    save_measurement(directory, MeasurementSession(room_name=room), result, include_curves=False)
    return directory


def test_remember_session_orders_and_drops_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, short_sweep: SweepSettings
) -> None:
    monkeypatch.setenv("ROOMSCOPE_HOME", str(tmp_path / "home"))
    first = _save_session(tmp_path / "one", short_sweep, "One")
    second = _save_session(tmp_path / "two", short_sweep, "Two")
    remember_session(first)
    remember_session(second / "session.json")
    paths = recent_session_paths()
    assert paths == [second.resolve(), first.resolve()]

    gone = tmp_path / "missing"
    gone.mkdir()
    (gone / "session.json").write_text("{}", encoding="utf-8")
    remember_session(gone)
    gone.joinpath("session.json").unlink()
    gone.rmdir()
    assert recent_session_paths() == [second.resolve(), first.resolve()]


def test_recent_store_ignores_corrupt_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("ROOMSCOPE_HOME", str(home))
    (home / "recent_sessions.json").write_text("{not json", encoding="utf-8")
    assert recent_session_paths() == []
    (home / "recent_sessions.json").write_text(
        json.dumps({"sessions": [1, None]}), encoding="utf-8"
    )
    assert recent_session_paths() == []


def test_an_unwritable_recent_list_does_not_fail_the_save(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """The session is already saved; the list is a convenience."""
    blocker = tmp_path / "not-a-folder"
    blocker.write_text("", encoding="utf-8")
    monkeypatch.setenv("ROOMSCOPE_HOME", str(blocker / "home"))
    with caplog.at_level("WARNING", logger="roomscope.io.recent"):
        remember_session(tmp_path)
    assert any("recent-sessions list" in record.getMessage() for record in caplog.records)
