from __future__ import annotations

from pathlib import Path

import pytest

from reverbscope.settings import UserSettings, load_settings, save_settings, settings_path


def test_settings_round_trip_and_defaults(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("REVERBSCOPE_HOME", str(tmp_path / "home"))
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
    monkeypatch.setenv("REVERBSCOPE_HOME", str(tmp_path / "home"))
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

    monkeypatch.setenv("REVERBSCOPE_HOME", str(tmp_path))
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

    from reverbscope.errors import SessionError
    from reverbscope.io import jsonutil

    monkeypatch.setenv("REVERBSCOPE_HOME", str(tmp_path))
    save_settings(UserSettings(language="zh_CN"))

    def disk_full(_fd: int) -> None:
        raise OSError(28, "No space left on device")

    with pytest.MonkeyPatch.context() as full_disk:
        full_disk.setattr(jsonutil.os, "fsync", disk_full)
        with pytest.raises(SessionError):
            save_settings(UserSettings(language="en"))
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
    monkeypatch.setenv("REVERBSCOPE_HOME", str(tmp_path / "home"))
    real = tmp_path / "dotfiles" / "reverbscope-settings.json"
    real.parent.mkdir()
    real.write_text(json.dumps({"language": "zh_CN"}), encoding="utf-8")
    real.chmod(0o600)
    settings_path().parent.mkdir()
    settings_path().symlink_to(real)
    save_settings(replace(load_settings(), language="en"))
    assert settings_path().is_symlink()
    assert json.loads(real.read_text(encoding="utf-8"))["language"] == "en"
    assert stat.S_IMODE(real.stat().st_mode) == 0o600


def test_settings_saved_with_a_byte_order_mark_are_used(tmp_path: Path, monkeypatch) -> None:
    """A settings.json edited in Notepad ("UTF-8 with BOM") was ignored
    without a word: the chosen language was lost."""
    monkeypatch.setenv("REVERBSCOPE_HOME", str(tmp_path))
    (tmp_path / "settings.json").write_bytes(
        b'\xef\xbb\xbf{"schema_version": 1, "language": "zh_CN"}'
    )
    assert load_settings().language == "zh_CN"


def test_settings_whose_folder_cannot_be_created_are_a_session_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``save_settings`` made the folder with a bare ``mkdir``: a file where
    ``$REVERBSCOPE_HOME`` should be raised FileExistsError out of the Settings
    dialog."""
    from reverbscope.errors import SessionError
    from reverbscope.settings import UserSettings, save_settings

    blocker = tmp_path / "blocker"
    blocker.write_text("x", encoding="utf-8")
    monkeypatch.setenv("REVERBSCOPE_HOME", str(blocker))
    with pytest.raises(SessionError, match="cannot create"):
        save_settings(UserSettings())


def test_a_home_folder_that_cannot_be_examined_keeps_the_defaults(
    tmp_path: Path, monkeypatch
) -> None:
    """Every command reads the settings before it can report anything; a
    REVERBSCOPE_HOME longer than the file system's name limit made stat() raise
    OSError there, and each command ended in a Python traceback."""
    monkeypatch.setenv("REVERBSCOPE_HOME", str(tmp_path / ("h" * 300)))
    assert load_settings() == UserSettings()


def test_commands_report_an_overlong_home_folder_without_a_traceback(
    tmp_path: Path, monkeypatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from reverbscope.cli.main import main

    monkeypatch.setenv("REVERBSCOPE_HOME", str(tmp_path / ("h" * 300)))
    capsys.readouterr()
    assert main(["doctor"]) == 0
    assert "ReverbScope environment report" in capsys.readouterr().out
    assert main(["config"]) == 1
    err = capsys.readouterr().err
    assert "File name too long" in err and "Traceback" not in err
