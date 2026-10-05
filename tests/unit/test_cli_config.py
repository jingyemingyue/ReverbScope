"""``reverbscope config``: the settings from the command line.

Every key with its accepted spellings, refused values (exit code 2, nothing
written), the JSON output, the file the desktop app reads, the other
settings kept on a change, a damaged file left alone, and the language:
stored, confirmed in the language just chosen, and used by the next command.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from reverbscope import i18n
from reverbscope.cli.config import KEYS
from reverbscope.cli.main import main
from reverbscope.i18n import activate, current_locale
from reverbscope.settings import UserSettings, load_settings, save_settings, settings_path
from tests.zh_tokens import english_words


@pytest.fixture
def home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Path]:
    """Its own settings folder, and a system language read from LANG only
    (no Mac preferences, no Windows display language) on every platform."""
    monkeypatch.setenv("REVERBSCOPE_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("COLUMNS", "100")
    monkeypatch.delenv("REVERBSCOPE_AUDIO_BACKEND", raising=False)
    monkeypatch.delenv("REVERBSCOPE_EDITION", raising=False)
    monkeypatch.setattr(i18n, "MACOS_PREFERENCES", (str(tmp_path / "no.plist"),))
    monkeypatch.setattr(i18n, "_windows_ui_language", lambda: None)
    try:
        yield tmp_path
    finally:
        activate("en")


def _run(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, str, str]:
    capsys.readouterr()
    try:
        code = main(list(argv))
    except SystemExit as exc:
        code = int(exc.code or 0)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def _stored() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(settings_path().read_text(encoding="utf-8"))
    return data


# --- Listing -----------------------------------------------------------------------------


def test_config_lists_every_setting_and_the_file(
    home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, err = _run(capsys, "config")
    assert code == 0 and err == ""
    for key in KEYS:
        assert f"  {key} " in out, key
    assert "follow the system (now English)" in out
    assert str(settings_path()) in out
    assert "Nothing is stored yet" in out
    assert not settings_path().exists()  # showing writes nothing


def test_config_as_json_is_the_settings_and_nothing_else(
    home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, err = _run(capsys, "--format", "json", "config")
    assert code == 0 and err == ""
    assert json.loads(out) == UserSettings().to_dict()
    code, out, _err = _run(capsys, "--format", "json", "config", "profile", "vocal")
    assert code == 0
    assert json.loads(out)["default_profile"] == "vocal" == _stored()["default_profile"]
    code, out, _err = _run(capsys, "--format", "json", "config", "language")
    assert json.loads(out)["default_profile"] == "vocal"


# --- Every key ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("key", "value", "field", "stored"),
    [
        ("language", "zh_CN", "language", "zh_CN"),
        ("language", "zh", "language", "zh_CN"),
        ("language", "zh-CN", "language", "zh_CN"),
        ("language", "zh_Hans", "language", "zh_CN"),
        ("language", "en_US", "language", "en"),
        ("language", "EN", "language", "en"),
        ("language", "auto", "language", ""),
        ("profile", "vocal", "default_profile", "vocal"),
        ("profile", "Acoustic-Guitar", "default_profile", "acoustic_guitar"),
        ("profile", "auto", "default_profile", "generic"),
        ("backend", "fake", "audio_backend", "fake"),
        ("backend", "PortAudio", "audio_backend", "portaudio"),
        ("backend", "sounddevice", "audio_backend", "portaudio"),
        ("backend", "auto", "audio_backend", ""),
        ("copy-recording", "off", "copy_recording", False),
        ("copy-recording", "no", "copy_recording", False),
        ("copy-recording", "on", "copy_recording", True),
        ("copy-recording", "auto", "copy_recording", True),
        ("developer-tools", "on", "developer_tools", True),
        ("developer-tools", "true", "developer_tools", True),
        ("developer-tools", "auto", "developer_tools", False),
        ("theme", "dark", "theme", "dark"),
        ("theme", "Light", "theme", "light"),
        ("theme", "system", "theme", ""),
        ("theme", "auto", "theme", ""),
        # The field names of settings.json name the same settings.
        ("default_profile", "drums", "default_profile", "drums"),
        ("copy_recording", "off", "copy_recording", False),
        ("audio-backend", "fake", "audio_backend", "fake"),
    ],
)
def test_every_setting_is_stored_as_the_desktop_app_reads_it(
    home: Path,
    capsys: pytest.CaptureFixture[str],
    key: str,
    value: str,
    field: str,
    stored: object,
) -> None:
    code, out, err = _run(capsys, "--lang", "en", "config", key, value)
    assert code == 0, err
    assert _stored()[field] == stored
    assert getattr(load_settings(), field) == stored
    assert "Saved in" in out or "保存" in out


def test_the_output_folder_is_stored_as_an_absolute_path(
    home: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    (home / "sessions").mkdir()
    monkeypatch.chdir(home)
    assert _run(capsys, "config", "output-folder", "sessions")[0] == 0
    assert _stored()["output_dir"] == str((home / "sessions").resolve())
    assert _run(capsys, "config", "output_dir", "auto")[0] == 0
    assert _stored()["output_dir"] == ""


@pytest.mark.parametrize(
    ("argv", "message"),
    [
        (["colour", "on"], "unknown setting 'colour'"),
        (["language", "fr"], "unknown language 'fr'; available: zh_CN, en, or auto"),
        (["language", "zh_TW"], "unknown language 'zh_TW'"),
        (["profile", "opera"], "unknown profile 'opera'"),
        (["backend", "asio"], "unknown audio backend 'asio'"),
        (["output-folder", "no-such-folder"], "'no-such-folder' is not an existing folder"),
        (["output-folder", "a-file.txt"], "'a-file.txt' is not an existing folder"),
        (["copy-recording", "maybe"], "copy-recording is on or off, not 'maybe'"),
        (["developer-tools", "2"], "developer-tools is on or off"),
        (["theme", "blue"], "unknown theme 'blue'"),
    ],
)
def test_a_value_a_setting_cannot_take_writes_nothing(
    home: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    argv: list[str],
    message: str,
) -> None:
    monkeypatch.chdir(home)
    (home / "a-file.txt").write_text("x", encoding="utf-8")
    code, out, err = _run(capsys, "config", *argv)
    assert code == 2 and out == ""
    assert message in " ".join(err.split()), err
    assert "Nothing was changed" in err and "reverbscope config --help" in err
    assert not settings_path().exists()
    save_settings(UserSettings(language="zh_CN", default_profile="vocal"))
    before = settings_path().read_bytes()
    assert _run(capsys, "config", *argv)[0] == 2
    assert settings_path().read_bytes() == before


def test_a_refusal_is_translated(home: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, _out, err = _run(capsys, "--lang", "zh_CN", "config", "language", "fr")
    assert code == 2
    assert "未知的语言 'fr'；可用：zh_CN、en 或 auto" in err and "没有做任何更改" in err


def test_a_change_keeps_every_other_setting(home: Path, capsys: pytest.CaptureFixture[str]) -> None:
    save_settings(
        UserSettings(language="zh_CN", default_profile="vocal", copy_recording=False, theme="dark")
    )
    assert _run(capsys, "config", "backend", "fake")[0] == 0
    assert (
        _stored()
        == UserSettings(
            language="zh_CN",
            default_profile="vocal",
            audio_backend="fake",
            copy_recording=False,
            theme="dark",
        ).to_dict()
    )


def test_a_damaged_settings_file_is_left_alone(
    home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """load_settings() reads a damaged file as the defaults; writing those
    back with one new value would lose every other setting."""
    settings_path().parent.mkdir(parents=True)
    settings_path().write_text('{"language": "zh_CN", ', encoding="utf-8")
    code, out, err = _run(capsys, "--lang", "en", "config", "theme", "dark")
    assert code == 1 and out == ""
    assert "nothing was changed" in err and str(settings_path()) in " ".join(err.split())
    assert settings_path().read_text(encoding="utf-8") == '{"language": "zh_CN", '
    code, out, err = _run(capsys, "--lang", "en", "config")
    assert code == 0 and "the defaults are shown" in err
    assert "language         auto" in out


def test_a_damaged_settings_file_is_described_in_the_interface_language(
    home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The Chinese error quoted the JSON parser's English sentence
    ("Expecting property name enclosed in double quotes: line 2 column 1")."""
    damaged = '{"language": "zh_CN",\n}\n'
    settings_path().parent.mkdir(parents=True)
    settings_path().write_text(damaged, encoding="utf-8")
    # Python 3.14 reports a trailing comma where it stands (line 1), older
    # versions where the next name was expected (line 2): ask the parser.
    with pytest.raises(json.JSONDecodeError) as parsed:
        json.loads(damaged)
    line, column = parsed.value.lineno, parsed.value.colno
    code, _out, err = _run(capsys, "--lang", "zh_CN", "config", "profile", "vocal")
    shown = " ".join(err.split())
    assert code == 1 and f"第 {line} 行第 {column} 列不是有效的 JSON" in shown, shown
    assert "Expecting" not in shown and "Illegal" not in shown and "没有做任何更改" in shown
    _code, _out, err = _run(capsys, "--lang", "en", "config", "profile", "vocal")
    assert f"invalid JSON at line {line}, column {column}" in " ".join(err.split())


# --- The language ------------------------------------------------------------------------


def test_the_confirmation_is_in_the_language_just_chosen(
    home: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LANG", "en_US.UTF-8")
    code, out, _err = _run(capsys, "--lang", "en", "config", "language", "zh_CN")
    assert code == 0
    assert "以后都会使用简体中文。" in out
    assert "reverbscope config language auto" in out and "改回跟随系统" in out
    assert current_locale() == "zh_CN"
    assert _stored()["language"] == "zh_CN"
    code, out, _err = _run(capsys, "config", "language", "en")
    assert "ReverbScope uses English from now on." in out
    assert current_locale() == "en"
    monkeypatch.setenv("LANG", "zh_CN.UTF-8")
    code, out, _err = _run(capsys, "config", "language", "auto")
    assert "已改回跟随系统语言：当前为简体中文。" in out
    assert "环境变量 LANG=zh_CN.UTF-8" in out
    assert _stored()["language"] == ""


def test_the_stored_language_is_used_by_the_next_command(
    home: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Chinese from the setting, whatever LANG says; --lang still wins for one command."""
    monkeypatch.setenv("LANG", "en_US.UTF-8")
    assert _run(capsys, "config", "language", "zh_CN")[0] == 0
    activate("en")  # a new process starts in English
    code, out, _err = _run(capsys, "--backend", "fake", "devices")
    assert code == 0 and "主机" in out
    code, out, _err = _run(capsys, "--lang", "en", "--backend", "fake", "devices")
    assert "主机" not in out
    # The stored language comes before REVERBSCOPE_LANG.
    monkeypatch.setenv("REVERBSCOPE_LANG", "en")
    code, out, _err = _run(capsys, "--backend", "fake", "devices")
    assert "主机" in out


@pytest.mark.parametrize(
    ("argv", "env", "stored", "because"),
    [
        ([], {"LANG": "zh_CN.UTF-8"}, "", "原因      环境变量 LANG=zh_CN.UTF-8"),
        ([], {"LANG": "en_US.UTF-8", "LANGUAGE": "zh_CN:en"}, "", "环境变量 LANGUAGE=zh_CN:en"),
        (["--lang", "en"], {"LANG": "zh_CN.UTF-8"}, "", "--lang en on this command line"),
        ([], {"REVERBSCOPE_LANG": "zh_CN"}, "", "环境变量 REVERBSCOPE_LANG=zh_CN"),
        (
            [],
            {"REVERBSCOPE_LANG": "en"},
            "zh_CN",
            "已保存的设置（reverbscope config language zh_CN）",
        ),
        ([], {"LANG": "fr_FR.UTF-8"}, "", "fr_FR has no translation, so English is used"),
    ],
)
def test_config_language_shows_what_is_in_effect_and_why(
    home: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    argv: list[str],
    env: dict[str, str],
    stored: str,
    because: str,
) -> None:
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    if stored:
        save_settings(UserSettings(language=stored))
    activate(None)
    code, out, _err = _run(capsys, *argv, "config", "language")
    assert code == 0
    assert because in " ".join(out.split()) or because in out, out


def test_one_setting_shows_its_values(home: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _err = _run(capsys, "config", "profile")
    assert code == 0
    assert "acoustic_guitar" in out and "reverbscope config profile VALUE" in out
    code, out, _err = _run(capsys, "config", "theme")
    assert "desktop app only" in out


# --- Chinese -------------------------------------------------------------------------------


def test_every_config_screen_is_chinese(
    home: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from reverbscope.interpretation import available_profiles

    monkeypatch.setenv("LANG", "zh_CN.UTF-8")
    typed = (*KEYS, *available_profiles(), "auto", "system", "zh_CN", "on", "off", "light", "dark")
    # Paths and environment variables are shown as they are.
    data = (str(settings_path()), str(home), "LANG=zh_CN.UTF-8")
    runs = [
        ["config"],
        ["config", "language"],
        ["config", "profile"],
        ["config", "theme"],
        ["config", "copy-recording", "off"],
        ["config", "theme", "light"],
        ["config", "language", "zh_CN"],
        ["config", "language", "auto"],
        ["config", "--help"],
    ]
    for argv in runs:
        code, out, err = _run(capsys, "--lang", "zh_CN", *argv)
        assert code == 0, (argv, err)
        found = english_words(out + err, data=data, values=typed)
        assert found == [], (argv, found, out)


@pytest.mark.parametrize(
    ("value", "option"), [("off", "--copy-recording"), ("on", "--no-copy-recording")]
)
@pytest.mark.parametrize("lang", ["en", "zh_CN"])
def test_the_copy_recording_override_is_shown_where_it_goes(
    home: Path, capsys: pytest.CaptureFixture[str], value: str, option: str, lang: str
) -> None:
    """The confirmation said "--copy-recording and --no-copy-recording
    override it for one command", and `analyze … --no-copy-recording` was
    refused: they are root options and go before the command."""
    from reverbscope.cli.main import build_parser

    code, out, _err = _run(capsys, "--lang", lang, "config", "copy-recording", value)
    assert code == 0
    row = next(line.strip() for line in out.splitlines() if "copy-recording" in line)
    assert row.startswith(f"reverbscope {option} <"), out
    # As shown: the option, then any command.
    args = build_parser().parse_args([option, "sweep", "--out", "x.wav"])
    assert args.copy_recording is (option == "--copy-recording")


def test_chinese_lists_use_the_chinese_separator(
    home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Lists read "zh_CN, en，或 auto" and "language, profile, backend", half-
    and full-width punctuation mixed, next to "portaudio、fake 或 auto"."""
    shown = []
    for argv in (["config", "--help"], ["config", "language", "fr"], ["config", "foo"]):
        _code, out, err = _run(capsys, "--lang", "zh_CN", *argv)
        shown.append(" ".join((out + err).split()))
    help_text, language, unknown = shown
    assert "zh_CN、en 或 auto（跟随系统）" in help_text
    assert "vocal、voiceover 或 auto" in help_text
    assert "可用：zh_CN、en 或 auto" in language
    assert "可用的设置项：language、profile、backend、" in unknown
    for text in shown:
        assert not re.search(r"[A-Za-z0-9_]，或|[a-z_], [a-z]", text), text
    _code, out, err = _run(capsys, "config", "language", "fr")
    assert "available: zh_CN, en, or auto" in err


def test_a_setting_has_the_name_the_desktop_app_gives_it(
    home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`config profile drums` confirmed "默认配置：鼓" ("default configuration")
    while its errors and every --help say 录音配置, and the output folder was
    a 会话文件夹 here but the 默认输出文件夹 in the Settings dialog."""
    from reverbscope.cli import config

    activate("zh_CN")
    assert config.title("profile") == i18n._("Default profile") == "默认录音配置"
    assert config.title("output-folder").startswith(i18n._("Default output folder"))
    _code, out, _err = _run(capsys, "--lang", "zh_CN", "config", "profile", "drums")
    assert "默认录音配置：" in out, out
    _code, _out, err = _run(capsys, "--lang", "zh_CN", "config", "profile", "foo")
    assert "录音配置" in err
    _code, out, _err = _run(capsys, "--lang", "zh_CN", "config")
    assert "默认录音配置：" in out and "默认输出文件夹（桌面版）：" in out, out


def test_showing_an_unknown_setting_does_not_talk_of_changes(
    home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, _out, err = _run(capsys, "config", "colour")
    assert code == 2 and "unknown setting 'colour'" in err
    assert "Nothing was changed" not in err


def test_a_variable_that_comes_before_a_setting_is_named(
    home: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("REVERBSCOPE_AUDIO_BACKEND", "fake")
    code, out, _err = _run(capsys, "config", "backend", "portaudio")
    assert code == 0 and _stored()["audio_backend"] == "portaudio"
    assert "REVERBSCOPE_AUDIO_BACKEND=fake chooses the backend before this setting" in out
    monkeypatch.setenv("REVERBSCOPE_EDITION", "user")
    code, out, _err = _run(capsys, "config")
    assert "REVERBSCOPE_EDITION=user decides before this setting" in out
