"""The menu must not hand an existing file or session to a writer without a yes.

No and Enter keep the old bytes and never build a command for that path.
A yes uses the same argv the direct command already accepts. The direct
``--out`` commands themselves are not given a new question.
"""

from __future__ import annotations

import io
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

import pytest

from reverbscope.cli.console import Console
from reverbscope.cli.interactive import run_menu
from reverbscope.cli.main import main
from reverbscope.i18n import activate
from reverbscope.io.wav import sidecar_path


def _menu(
    answers: Sequence[object],
    run=None,  # type: ignore[no-untyped-def]
) -> tuple[int, list[list[str]], str, list[str]]:
    pending = iter(answers)
    runs: list[list[str]] = []
    prompts: list[str] = []
    out = io.StringIO()

    def ask(prompt: str) -> str:
        prompts.append(prompt)
        try:
            answer = next(pending)
        except StopIteration:
            raise EOFError from None
        if isinstance(answer, BaseException):
            raise answer
        return str(answer)

    def default_run(argv: list[str]) -> int:
        runs.append(list(argv))
        return 0

    code = run_menu(Console(width=80), ask=ask, run=run or default_run, out=out)
    return code, runs, " ".join(out.getvalue().split()), prompts


def _asked(prompts: Sequence[str], text: str) -> bool:
    return any(text in prompt for prompt in prompts)


def test_sweep_no_and_enter_keep_an_existing_file_and_its_sidecar(tmp_path: Path) -> None:
    wav = tmp_path / "sweep.wav"
    side = sidecar_path(wav)
    wav.write_bytes(b"OLD-WAV")
    side.write_bytes(b"OLD-SIDE")
    fresh = tmp_path / "fresh.wav"
    for refusal in ("n", ""):
        _code, runs, _out, prompts = _menu(["2", str(wav), refusal, str(fresh), "48000", "q"])
        assert wav.read_bytes() == b"OLD-WAV"
        assert side.read_bytes() == b"OLD-SIDE"
        assert _asked(prompts, "already exists")
        assert runs == [["sweep", "--out", str(fresh), "--sample-rate", "48000"]]
        assert all(str(wav) not in arg for command in runs for arg in command)


def test_a_sidecar_alone_is_enough_to_ask(tmp_path: Path) -> None:
    wav = tmp_path / "sweep.wav"
    side = sidecar_path(wav)
    side.write_bytes(b"OLD-SIDE")
    fresh = tmp_path / "fresh.wav"
    _code, runs, _out, prompts = _menu(["2", str(wav), "n", str(fresh), "48000", "q"])
    assert not wav.exists()
    assert side.read_bytes() == b"OLD-SIDE"
    assert _asked(prompts, str(side))
    assert runs == [["sweep", "--out", str(fresh), "--sample-rate", "48000"]]


def test_sweep_yes_uses_the_current_command_without_a_force_flag(tmp_path: Path) -> None:
    wav = tmp_path / "sweep.wav"
    wav.write_bytes(b"OLD-WAV")
    _code, runs, _out, prompts = _menu(["2", str(wav), "y", "48000", "q"])
    assert _asked(prompts, "already exists")
    assert runs == [["sweep", "--out", str(wav), "--sample-rate", "48000"]]
    assert all("--force" not in arg for command in runs for arg in command)


def test_measure_no_and_enter_do_not_reuse_a_saved_session(tmp_path: Path) -> None:
    session = tmp_path / "take"
    session.mkdir()
    (session / "session.json").write_bytes(b"OLD-SESSION")
    (session / "result.json").write_bytes(b"OLD-RESULT")
    other = tmp_path / "other"
    for refusal in ("n", ""):
        _code, runs, _out, prompts = _menu(["4", str(session), refusal, str(other), "y", "q"])
        assert (session / "session.json").read_bytes() == b"OLD-SESSION"
        assert (session / "result.json").read_bytes() == b"OLD-RESULT"
        assert _asked(prompts, "already holds a saved session")
        assert runs == [["measure", "--out", str(other)]]
        assert "Play and record now?" in prompts[-2]


def test_replacing_a_session_still_asks_before_anything_is_played(tmp_path: Path) -> None:
    session = tmp_path / "take"
    session.mkdir()
    (session / "session.json").write_bytes(b"OLD-SESSION")
    _code, runs, out, prompts = _menu(["4", str(session), "y", "n", "q"])
    assert runs == []
    assert (session / "session.json").read_bytes() == b"OLD-SESSION"
    assert _asked(prompts, "already holds a saved session")
    assert _asked(prompts, "Play and record now?")
    assert "Nothing was played." in out


def test_analyze_no_and_enter_can_fall_back_to_show_only(tmp_path: Path) -> None:
    recording = tmp_path / "rec.wav"
    sweep = tmp_path / "sig.wav"
    recording.write_bytes(b"REC")
    sweep.write_bytes(b"SIG")
    folder = tmp_path / "out"
    folder.mkdir()
    (folder / "session.json").write_bytes(b"OLD-SESSION")
    (folder / "result.json").write_bytes(b"OLD-RESULT")
    _code, runs, _out, prompts = _menu(["3", str(recording), str(sweep), str(folder), "n", "", "q"])
    assert (folder / "session.json").read_bytes() == b"OLD-SESSION"
    assert (folder / "result.json").read_bytes() == b"OLD-RESULT"
    assert _asked(prompts, "already holds a saved session")
    assert runs == [["analyze", "--recording", str(recording), "--sweep", str(sweep)]]


def test_a_folder_with_results_but_no_session_still_asks(tmp_path: Path) -> None:
    recording = tmp_path / "rec.wav"
    sweep = tmp_path / "sig.wav"
    recording.write_bytes(b"REC")
    sweep.write_bytes(b"SIG")
    folder = tmp_path / "out"
    folder.mkdir()
    (folder / "result.json").write_bytes(b"OLD-RESULT")
    (folder / "impulse_response.wav").write_bytes(b"OLD-IR")
    _code, runs, _out, prompts = _menu(["3", str(recording), str(sweep), str(folder), "n", "", "q"])
    assert (folder / "result.json").read_bytes() == b"OLD-RESULT"
    assert (folder / "impulse_response.wav").read_bytes() == b"OLD-IR"
    assert _asked(prompts, str(folder))
    assert not _asked(prompts, "already holds a saved session")
    assert runs == [["analyze", "--recording", str(recording), "--sweep", str(sweep)]]


def test_analyze_yes_reuses_the_session_with_the_current_command(tmp_path: Path) -> None:
    recording = tmp_path / "rec.wav"
    sweep = tmp_path / "sig.wav"
    recording.write_bytes(b"REC")
    sweep.write_bytes(b"SIG")
    folder = tmp_path / "out"
    folder.mkdir()
    (folder / "session.json").write_bytes(b"OLD-SESSION")
    _code, runs, _out, _prompts = _menu(["3", str(recording), str(sweep), str(folder), "y", "q"])
    assert runs == [
        ["analyze", "--recording", str(recording), "--sweep", str(sweep), "--out", str(folder)]
    ]


def test_two_measurements_in_one_minute_do_not_share_a_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    class Frozen(datetime):
        @classmethod
        def now(cls, tz: object = None) -> datetime:
            return datetime(2026, 10, 16, 12, 34)

    monkeypatch.setattr("reverbscope.cli.interactive.datetime", Frozen)
    created: list[Path] = []

    def run(argv: list[str]) -> int:
        out = Path(argv[argv.index("--out") + 1])
        out.mkdir()
        (out / "session.json").write_bytes(b"x")
        created.append(out)
        return 0

    _code, _runs, _out, prompts = _menu(["4", "", "y", "4", "", "n", "q"], run=run)
    folder_prompts = [prompt for prompt in prompts if "Folder for the new session" in prompt]
    assert len(folder_prompts) == 2
    assert folder_prompts[0] != folder_prompts[1]
    assert "session-20261016-1234-2" in folder_prompts[1]
    assert len(created) == 1
    assert created[0].name == "session-20261016-1234"


def test_new_session_folder_skips_a_file_and_a_dangling_link(tmp_path: Path) -> None:
    from reverbscope.cli.interactive import new_session_folder

    now = datetime(2026, 1, 2, 3, 4)
    (tmp_path / "session-20260102-0304").write_bytes(b"file")
    link = tmp_path / "session-20260102-0304-2"
    link.symlink_to(tmp_path / "missing")
    chosen = new_session_folder(tmp_path, now=now)
    assert chosen == tmp_path / "session-20260102-0304-3"
    assert not chosen.exists()
    assert link.is_symlink()


def test_a_quoted_chinese_path_is_protected_like_any_other(
    tmp_path: Path,
) -> None:
    from reverbscope.cli.interactive import parse_path

    folder = tmp_path / "中文 房间"
    folder.mkdir()
    (folder / "session.json").write_bytes(b"OLD")
    recording = tmp_path / "rec.wav"
    sweep = tmp_path / "sig.wav"
    recording.write_bytes(b"REC")
    sweep.write_bytes(b"SIG")
    quoted = f'"{folder}"'
    assert parse_path(quoted) == folder
    activate("zh_CN")
    try:
        _code, runs, _out, prompts = _menu(["3", str(recording), str(sweep), quoted, "n", "", "q"])
    finally:
        activate("en")
    assert (folder / "session.json").read_bytes() == b"OLD"
    assert any("已存在" in prompt or "已有一个保存的会话" in prompt for prompt in prompts)
    assert str(folder) in " ".join(prompts)
    assert runs == [["analyze", "--recording", str(recording), "--sweep", str(sweep)]]


def test_eof_and_ctrl_c_during_a_replace_question_do_not_run(
    tmp_path: Path,
) -> None:
    wav = tmp_path / "sweep.wav"
    wav.write_bytes(b"OLD-WAV")
    code, runs, out, _prompts = _menu(["2", str(wav), EOFError()])
    assert code == 0 and runs == []
    assert wav.read_bytes() == b"OLD-WAV"
    code, runs, out, _prompts = _menu(["2", str(wav), KeyboardInterrupt(), "q"])
    assert code == 0 and runs == []
    assert "Back to the menu." in out
    assert wav.read_bytes() == b"OLD-WAV"


def test_direct_sweep_still_overwrites_without_asking(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def refuse_input(*_args: object, **_kwargs: object) -> str:
        raise AssertionError("the direct command asked a question")

    monkeypatch.setattr("builtins.input", refuse_input)
    target = tmp_path / "sweep.wav"
    target.write_bytes(b"OLD-WAV")
    code = main(
        [
            "sweep",
            "--out",
            str(target),
            "--sample-rate",
            "48000",
            "--duration",
            "1",
            "--pre-silence",
            "0.1",
            "--post-silence",
            "0.1",
        ]
    )
    assert code == 0
    assert target.read_bytes() != b"OLD-WAV"
    assert sidecar_path(target).is_file()
