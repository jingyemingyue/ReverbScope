"""``reverbscope`` with no command on a terminal: the menu."""

from __future__ import annotations

import io
import os
from collections.abc import Sequence
from pathlib import Path

import pytest

from reverbscope.cli.console import Console
from reverbscope.cli.interactive import MENU_VARIABLE, menu_items, parse_path, run_menu
from reverbscope.cli.main import main
from reverbscope.i18n import activate


def _menu(
    answers: Sequence[object], *, terminal_edition: bool = False, prefix: Sequence[str] = ()
) -> tuple[int, list[list[str]], str]:
    pending = iter(answers)
    runs: list[list[str]] = []
    out = io.StringIO()

    def ask(_prompt: str) -> str:
        try:
            answer = next(pending)
        except StopIteration:
            raise EOFError from None
        if isinstance(answer, BaseException):
            raise answer
        return str(answer)

    def run(argv: list[str]) -> int:
        runs.append(list(argv))
        return 0

    code = run_menu(
        Console(width=80),
        ask=ask,
        run=run,
        out=out,
        terminal_edition=terminal_edition,
        prefix=prefix,
    )
    # The console wraps sentences: compare on one line.
    return code, runs, " ".join(out.getvalue().split())


def test_every_item_builds_its_command_and_shows_it(tmp_path: Path) -> None:
    recording = tmp_path / "take.wav"
    recording.write_bytes(b"RIFF")
    sweep = tmp_path / "sweep.wav"
    sweep.write_bytes(b"RIFF")
    for name in ("a", "b", "room"):
        (tmp_path / name).mkdir()
    code, runs, out = _menu(
        [
            "1",
            "2", str(tmp_path / "signal.wav"), "44100",
            "3", str(recording), "", str(tmp_path / "saved"),
            "5", str(tmp_path / "a"),
            "6", str(tmp_path / "a"), str(tmp_path / "b"), "y",
            "7", str(tmp_path / "room"),
            "8", "9", "10",
            "q",
        ]
    )  # fmt: skip
    assert code == 0
    assert runs == [
        ["demo"],
        ["sweep", "--out", str(tmp_path / "signal.wav"), "--sample-rate", "44100"],
        # The sweep beside the recording is the default for the test signal.
        [
            "analyze", "--recording", str(recording), "--sweep", str(sweep),
            "--out", str(tmp_path / "saved"),
        ],
        ["show", str(tmp_path / "a")],
        ["compare", str(tmp_path / "a"), str(tmp_path / "b"), "--same-input-gain"],
        ["project", "overview", str(tmp_path / "room")],
        ["config"],
        ["doctor"],
        ["gui"],
    ]  # fmt: skip
    assert "reverbscope demo" in out and "reverbscope project overview" in out
    assert "The same from the command line" in out


def test_the_measurement_item_plays_nothing_without_a_yes(tmp_path: Path) -> None:
    code, runs, out = _menu(["4", str(tmp_path / "s"), "n", "q"])
    assert code == 0 and runs == []
    assert "nothing has been played yet" in out and "Nothing was played." in out
    code, runs, out = _menu(["4", str(tmp_path / "s"), "y", "q"])
    assert runs == [["measure", "--out", str(tmp_path / "s")]]


def test_a_missing_path_is_asked_again_and_an_empty_answer_goes_back(tmp_path: Path) -> None:
    code, runs, out = _menu(["5", str(tmp_path / "nope"), "", "q"])
    assert code == 0 and runs == []
    assert "does not exist" in out and "Back to the menu." in out
    code, runs, out = _menu(["7", str(tmp_path / "file"), "", "q"])
    assert "is not a folder" in out and runs == []


def test_a_sample_rate_outside_the_supported_list_is_refused(tmp_path: Path) -> None:
    _code, runs, out = _menu(["2", str(tmp_path / "s.wav"), "12345", "48000", "q"])
    assert "Choose one of" in out
    assert runs == [["sweep", "--out", str(tmp_path / "s.wav"), "--sample-rate", "48000"]]


def test_ctrl_c_at_a_question_returns_and_at_the_menu_leaves() -> None:
    code, runs, out = _menu(["3", KeyboardInterrupt(), "q"])
    assert code == 0 and runs == [] and "Back to the menu." in out
    assert _menu([KeyboardInterrupt()])[0] == 0
    assert _menu([])[0] == 0  # end of input
    code, runs, out = _menu(["x", "q"])
    assert "Choose a number from the list" in out


def test_the_prefix_goes_before_every_command_shown_and_run() -> None:
    _code, runs, out = _menu(["1", "q"], prefix=["--lang", "zh_CN", "--style", "plain"])
    assert runs == [["--lang", "zh_CN", "--style", "plain", "demo"]]
    assert "reverbscope --lang zh_CN --style plain demo" in out


def test_the_terminal_edition_has_no_desktop_item() -> None:
    assert [item.key for item in menu_items(terminal_edition=True)] == [
        str(n) for n in range(1, 10)
    ]
    assert [item.key for item in menu_items()][-1] == "10"


def test_a_dragged_path_is_understood() -> None:
    assert parse_path("") is None
    assert parse_path('"/tmp/my room/take.wav"') == Path("/tmp/my room/take.wav")
    assert parse_path("'/tmp/my room/take.wav'") == Path("/tmp/my room/take.wav")
    assert parse_path("~/take.wav") == Path.home() / "take.wav"
    if os.name != "nt":
        assert parse_path(r"/tmp/my\ room/take.wav") == Path("/tmp/my room/take.wav")
    else:
        assert parse_path("C:\\rooms\\take.wav").name == "take.wav"


def test_the_menu_speaks_chinese() -> None:
    activate("zh_CN")
    try:
        titles = [item.title for item in menu_items()]
    finally:
        activate("en")
    assert all(any("\u4e00" <= ch <= "\u9fff" for ch in title) for title in titles), titles


def test_a_terminal_gets_the_menu_and_a_pipe_the_home_screen(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # In a pipe (pytest's capture): the home screen, the usage exit code.
    assert main([]) == 2
    captured = capsys.readouterr()
    assert "ReverbScope" in captured.err and captured.out == ""
    # On a terminal: the menu, which q leaves.
    monkeypatch.setattr("reverbscope.cli.console.is_terminal", lambda _stream: True)
    monkeypatch.setattr("builtins.input", lambda _prompt="": "q")
    assert main([]) == 0
    assert "Try the demo" in capsys.readouterr().out
    # Unless the menu is switched off.
    monkeypatch.setenv(MENU_VARIABLE, "1")
    assert main([]) == 2
