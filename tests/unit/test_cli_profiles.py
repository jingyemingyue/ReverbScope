"""``reverbscope profiles``: the profiles and what each one watches for."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from reverbscope.cli.main import main
from reverbscope.interpretation import available_profiles


@pytest.fixture
def home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setenv("REVERBSCOPE_HOME", str(tmp_path / "home"))
    return tmp_path / "home"


def test_the_list_names_every_profile_and_the_default(
    home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["--color", "never", "profiles"]) == 0
    out = capsys.readouterr().out
    assert "ReverbScope recording profiles" in out
    for name in available_profiles():
        assert name in out
    assert "(default)" in out and "generic" in out
    assert "watches for" in " ".join(out.split())


def test_one_profile_in_full_and_json(home: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--color", "never", "profiles", "drums"]) == 0
    out = " ".join(capsys.readouterr().out.split())
    assert "Drums (drums)" in out
    assert "not judged" in out and "-6 dB" in out and "20 ms" in out
    assert main(["--format", "json", "profiles", "vocal"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload[0]["name"] == "vocal"
    assert payload[0]["thresholds"]["strong_reflection_db"] == -12.0
    assert main(["--format", "json", "profiles", "--all"]) == 0
    assert len(json.loads(capsys.readouterr().out)) == len(available_profiles())


def test_an_unknown_profile_is_a_usage_error(
    home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["profiles", "banjo"])
    assert exc.value.code == 2
    assert "invalid choice" in capsys.readouterr().err


def test_the_default_profile_is_marked_in_the_brackets_of_the_language(
    home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Chinese writes no space before a full-width bracket: ``generic（默认）``,
    not ``generic （默认）``; English keeps ``generic (default)``."""
    from reverbscope.i18n import activate

    try:
        assert main(["--lang", "zh_CN", "--color", "never", "profiles"]) == 0
        zh = capsys.readouterr().out
    finally:
        activate("en")
    assert "generic（默认）" in zh
    assert "generic （默认）" not in zh
    assert main(["--lang", "en", "--color", "never", "profiles"]) == 0
    assert "generic (default)" in capsys.readouterr().out
