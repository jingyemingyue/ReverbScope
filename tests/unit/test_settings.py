from __future__ import annotations

from pathlib import Path

from roomscope.settings import UserSettings, load_settings, save_settings, settings_path


def test_settings_round_trip_and_defaults(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ROOMSCOPE_HOME", str(tmp_path / "home"))
    first = load_settings()
    assert first.copy_recording is True
    assert first.language == ""
    assert not settings_path().is_file()
    first.language = "zh_CN"
    first.default_profile = "vocal"
    first.audio_backend = "fake"
    first.copy_recording = False
    path = save_settings(first)
    assert path == settings_path()
    loaded = load_settings()
    assert loaded.language == "zh_CN"
    assert loaded.default_profile == "vocal"
    assert loaded.audio_backend == "fake"
    assert loaded.copy_recording is False


def test_settings_ignore_unknown_and_unreadable(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ROOMSCOPE_HOME", str(tmp_path / "home"))
    extra = UserSettings.from_dict(
        {
            "schema_version": 1,
            "language": "en",
            "acknowledge_level": True,
            "mystery": 1,
        }
    )
    assert extra.language == "en"
    assert not hasattr(extra, "acknowledge_level")
    settings_path().parent.mkdir(parents=True, exist_ok=True)
    settings_path().write_text("not json", encoding="utf-8")
    assert load_settings().language == ""


def test_mistyped_settings_fall_back_to_the_defaults(tmp_path: Path, monkeypatch) -> None:
    """``"language": 1`` stopped every command; ``"developer_tools": "false"``
    read as True."""
    import json

    monkeypatch.setenv("ROOMSCOPE_HOME", str(tmp_path))
    settings_path().write_text(
        json.dumps(
            {
                "language": 1,
                "audio_backend": ["fake"],
                "developer_tools": "false",
                "copy_recording": False,
                "default_profile": "vocal",
            }
        ),
        encoding="utf-8",
    )
    loaded = load_settings()
    assert loaded == UserSettings(copy_recording=False, default_profile="vocal")


def test_a_failed_settings_write_keeps_the_old_file(tmp_path: Path, monkeypatch) -> None:
    import pytest

    from roomscope.errors import SessionError
    from roomscope.io import jsonutil

    monkeypatch.setenv("ROOMSCOPE_HOME", str(tmp_path))
    save_settings(UserSettings(language="zh_CN"))

    def disk_full(_fd: int) -> None:
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(jsonutil.os, "fsync", disk_full)
    with pytest.raises(SessionError):
        save_settings(UserSettings(language="en"))
    monkeypatch.undo()
    monkeypatch.setenv("ROOMSCOPE_HOME", str(tmp_path))
    assert load_settings().language == "zh_CN"


def test_saving_settings_keeps_a_symlinked_settings_file(tmp_path: Path, monkeypatch) -> None:
    """settings.json kept as a link into a dotfiles folder became a plain
    0644 file on the first save, and the dotfile kept the old settings."""
    import json
    import stat
    import sys
    from dataclasses import replace

    import pytest

    if sys.platform == "win32":
        pytest.skip("symbolic links need a privilege on Windows")
    monkeypatch.setenv("ROOMSCOPE_HOME", str(tmp_path / "home"))
    real = tmp_path / "dotfiles" / "roomscope-settings.json"
    real.parent.mkdir()
    real.write_text(json.dumps({"language": "zh_CN"}), encoding="utf-8")
    real.chmod(0o600)
    settings_path().parent.mkdir()
    settings_path().symlink_to(real)
    save_settings(replace(load_settings(), language="en"))
    assert settings_path().is_symlink()
    assert json.loads(real.read_text(encoding="utf-8"))["language"] == "en"
    assert stat.S_IMODE(real.stat().st_mode) == 0o600
