from __future__ import annotations

from pathlib import Path

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
