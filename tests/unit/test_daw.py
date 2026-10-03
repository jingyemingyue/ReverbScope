"""Follow the DAW the user names. Never guess. This VM has no DAW installed."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from roomscope.cli.main import main
from roomscope.daw import (
    FAKE_DAWS_ENV,
    FOLLOWED_SETTINGS,
    SOURCE_DECLARED,
    SOURCE_FAKE,
    DawChoiceNeeded,
    DawProject,
    apply_daw_follow,
    open_daw_projects,
    parse_fake_daws,
    resolve_daw_follow,
)
from roomscope.errors import ConfigurationError
from roomscope.io.wav import read_wav
from roomscope.models.configuration import SweepSettings
from roomscope.models.session import MeasurementSession
from roomscope.schemas import load_schema

TWO_FAKES = "Logic Pro:48000:Song A;REAPER:44100:Film"


def _project(daw: str, rate: int, project: str = "", *, source: str = SOURCE_FAKE) -> DawProject:
    return DawProject(daw=daw, sample_rate=rate, project=project, source=source)


def test_followed_settings_are_only_sample_rate() -> None:
    """The sweep sample rate is the only session setting treated as DAW-dependent."""
    assert FOLLOWED_SETTINGS == ("sample_rate",)


def test_open_daw_projects_is_empty_without_fake_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(FAKE_DAWS_ENV, raising=False)
    assert open_daw_projects() == ()


def test_parse_and_open_fake_daws(monkeypatch: pytest.MonkeyPatch) -> None:
    parsed = parse_fake_daws(TWO_FAKES)
    assert [item.daw for item in parsed] == ["Logic Pro", "REAPER"]
    assert parsed[0].sample_rate == 48000 and parsed[0].project == "Song A"
    assert parsed[1].sample_rate == 44100 and parsed[1].project == "Film"
    assert all(item.source == SOURCE_FAKE for item in parsed)

    monkeypatch.setenv(FAKE_DAWS_ENV, TWO_FAKES)
    assert open_daw_projects() == parsed
    injected = (_project("Cubase", 96000, "Score"),)
    assert open_daw_projects(injected) == injected


@pytest.mark.parametrize(
    "text",
    ["REAPER", "REAPER:", "REAPER:fast:Film", " :48000", "REAPER:48000x"],
)
def test_parse_fake_daws_rejects_bad_entries(text: str) -> None:
    with pytest.raises(ConfigurationError):
        parse_fake_daws(text)


def test_resolve_none_asks() -> None:
    with pytest.raises(DawChoiceNeeded) as exc:
        resolve_daw_follow(())
    assert exc.value.reason == "none"
    assert exc.value.candidates == ()
    assert "will not guess" in str(exc.value)


def test_resolve_one_follows_without_asking() -> None:
    chosen = resolve_daw_follow((_project("REAPER", 44100, "Film"),))
    assert chosen.daw == "REAPER" and chosen.sample_rate == 44100


def test_resolve_several_asks_and_lists_both() -> None:
    listed = (
        _project("Logic Pro", 48000, "Song A"),
        _project("REAPER", 44100, "Film"),
    )
    with pytest.raises(DawChoiceNeeded) as exc:
        resolve_daw_follow(listed)
    assert exc.value.reason == "several"
    assert exc.value.candidates == listed
    message = str(exc.value)
    assert "Logic Pro" in message and "REAPER" in message
    assert "will not guess" in message


def test_resolve_exact_name_not_a_prefix() -> None:
    listed = (
        _project("REAPER", 44100, "Film"),
        _project("Logic Pro", 48000, "Song A"),
    )
    chosen = resolve_daw_follow(listed, daw="reaper")
    assert chosen.daw == "REAPER"

    with pytest.raises(DawChoiceNeeded) as exc:
        resolve_daw_follow(listed, daw="REA")
    assert exc.value.reason == "unknown"


def test_resolve_same_daw_two_projects_still_asks() -> None:
    listed = (
        _project("REAPER", 44100, "Film"),
        _project("REAPER", 48000, "Podcast"),
    )
    with pytest.raises(DawChoiceNeeded) as exc:
        resolve_daw_follow(listed, daw="REAPER")
    assert exc.value.reason == "several"
    assert len(exc.value.candidates) == 2

    chosen = resolve_daw_follow(listed, daw="REAPER", project="Podcast")
    assert chosen.project == "Podcast" and chosen.sample_rate == 48000


def test_resolve_declared_name_and_rate_when_none() -> None:
    chosen = resolve_daw_follow((), daw="Bitwig Studio", declared_rate=96000)
    assert chosen.daw == "Bitwig Studio"
    assert chosen.sample_rate == 96000
    assert chosen.source == SOURCE_DECLARED


def test_resolve_declared_name_without_rate_still_asks() -> None:
    with pytest.raises(DawChoiceNeeded) as exc:
        resolve_daw_follow((), daw="REAPER")
    assert exc.value.reason == "none"


def test_resolve_refuses_conflicting_declared_rate() -> None:
    with pytest.raises(ConfigurationError, match="does not match"):
        resolve_daw_follow((_project("REAPER", 44100, "Film"),), declared_rate=48000)


def test_apply_daw_follow_copies_sample_rate_only() -> None:
    settings = SweepSettings(sample_rate=48000, duration_s=2.0, level_dbfs=-12.0)
    followed = apply_daw_follow(settings, _project("REAPER", 44100, "Film"))
    assert followed.sample_rate == 44100
    assert followed.duration_s == settings.duration_s
    assert followed.level_dbfs == settings.level_dbfs


def test_cli_daw_empty_lists_none_and_asks(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv(FAKE_DAWS_ENV, raising=False)
    assert main(["daw"]) == 0
    out = capsys.readouterr().out
    assert "No DAW project was found" in out
    assert "will not guess" in out
    assert "Sample rate" in out

    assert main(["--format", "json", "daw"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["candidates"] == []
    assert payload["needs_choice"] is True
    assert payload["reason"] == "none"
    assert payload["followed_settings"] == ["sample_rate"]


def test_cli_daw_several_lists_both_and_asks(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv(FAKE_DAWS_ENV, TWO_FAKES)
    assert main(["daw"]) == 0
    out = capsys.readouterr().out
    assert "Logic Pro" in out and "REAPER" in out
    assert "More than one" in out
    assert "not guess" in out

    assert main(["--format", "json", "daw"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["reason"] == "several"
    assert payload["needs_choice"] is True
    assert [item["daw"] for item in payload["candidates"]] == ["Logic Pro", "REAPER"]


def test_cli_follow_daw_without_choice_asks(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv(FAKE_DAWS_ENV, TWO_FAKES)
    code = main(["sweep", "--out", str(tmp_path / "sweep.wav"), "--follow-daw"])
    assert code == 1
    err = capsys.readouterr().err
    compact = " ".join(err.split())
    assert "More than one" in compact
    assert "not guess" in compact
    assert not (tmp_path / "sweep.wav").exists()


def test_cli_follow_named_fake_writes_that_rate(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv(FAKE_DAWS_ENV, TWO_FAKES)
    sweep = tmp_path / "sweep.wav"
    assert main(["sweep", "--out", str(sweep), "--follow-daw", "--daw", "REAPER"]) == 0
    out = capsys.readouterr().out
    assert "Following" in out and "REAPER" in out
    assert read_wav(sweep).sample_rate == 44100


def test_cli_declared_name_and_rate_when_none(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv(FAKE_DAWS_ENV, raising=False)
    sweep = tmp_path / "sweep.wav"
    assert (
        main(
            [
                "sweep",
                "--out",
                str(sweep),
                "--follow-daw",
                "--daw",
                "Logic Pro",
                "--sample-rate",
                "96000",
            ]
        )
        == 0
    )
    assert read_wav(sweep).sample_rate == 96000


def test_cli_plain_sweep_keeps_default_rate_with_fakes_present(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(FAKE_DAWS_ENV, TWO_FAKES)
    sweep = tmp_path / "sweep.wav"
    assert main(["sweep", "--out", str(sweep), "--duration", "2"]) == 0
    assert read_wav(sweep).sample_rate == 48000


def test_cli_conflicting_rate_is_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv(FAKE_DAWS_ENV, "REAPER:44100:Film")
    code = main(
        [
            "sweep",
            "--out",
            str(tmp_path / "sweep.wav"),
            "--follow-daw",
            "--daw",
            "REAPER",
            "--sample-rate",
            "48000",
        ]
    )
    assert code == 1
    assert "does not match" in capsys.readouterr().err


def test_session_schema_accepts_daw_fields() -> None:
    session = MeasurementSession(daw_name="REAPER", daw_project="Film")
    payload = session.to_dict()
    Draft202012Validator(load_schema("session")).validate(payload)
    loaded = MeasurementSession.from_dict(payload)
    assert loaded.daw_name == "REAPER" and loaded.daw_project == "Film"
