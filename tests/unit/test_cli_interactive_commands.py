"""The commands the menu runs: with the options it was started with, and how they end.

``reverbscope --backend fake`` is a menu that measures on the simulated
interface: the option goes before every command it runs and shows. A command
that cannot start (the desktop app on a computer without a screen), is
refused or is interrupted does not end the menu, and ``--format json`` does
not get a menu that prints text.
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

import pytest

from reverbscope.cli import interactive
from reverbscope.cli.interactive import option_value, root_options
from reverbscope.cli.main import build_parser, main
from tests.menus import drive


@pytest.fixture(autouse=True)
def _work_in_a_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


def _args(*argv: str):  # type: ignore[no-untyped-def]
    return build_parser().parse_args(list(argv))


def test_the_options_before_the_command_go_before_every_command_of_the_menu() -> None:
    args = _args(
        "--lang", "zh_CN", "--color", "never", "--style", "plain", "--backend", "fake",
        "--no-copy-recording", "-v",
    )  # fmt: skip
    assert root_options(args, lang="zh_CN", color="never") == [
        "--lang", "zh_CN", "--color", "never", "--style", "plain", "--backend", "fake",
        "--no-copy-recording", "--verbose",
    ]  # fmt: skip
    assert root_options(_args(), lang="en") == ["--lang", "en"]
    assert root_options(_args("--copy-recording"), lang="en") == [
        "--lang",
        "en",
        "--copy-recording",
    ]
    # What the user did not ask for is not added.
    assert root_options(_args("--color", "auto", "--style", "auto"), lang="en", color="auto") == [
        "--lang",
        "en",
    ]
    assert option_value(["--lang", "en", "--backend", "fake"], "--backend") == "fake"
    assert option_value(["--lang", "en", "--backend"], "--backend") is None
    assert option_value([], "--backend") is None


class _Tty(io.StringIO):
    def isatty(self) -> bool:
        return True


def _on_a_terminal(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, object]]:
    """Make stdin and stdout terminals; record what the menu is started with."""
    monkeypatch.setattr(sys, "stdin", _Tty("q\n"))
    monkeypatch.setattr(sys, "stdout", _Tty())
    started: list[dict[str, object]] = []

    def run_menu(console: object, **options: object) -> int:
        started.append(options)
        return 0

    monkeypatch.setattr(interactive, "run_menu", run_menu)
    return started


def test_bare_reverbscope_starts_the_menu_with_the_options_it_was_given(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started = _on_a_terminal(monkeypatch)
    assert main(["--lang", "en", "--backend", "fake", "--no-copy-recording"]) == 0
    (options,) = started
    assert options["prefix"] == ["--lang", "en", "--backend", "fake", "--no-copy-recording"]


def test_the_menu_that_measures_on_the_simulated_interface_is_told_so() -> None:
    visit = drive(
        ["4", "take-1", "", "y", "q"], prefix=root_options(_args("--backend", "fake"), lang="en")
    )
    assert visit.runs == [["--lang", "en", "--backend", "fake", "measure", "--out", "take-1"]]
    assert "reverbscope --lang en --backend fake measure --out take-1" in visit.text


def test_json_gets_the_home_screen_not_a_menu(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    started = _on_a_terminal(monkeypatch)
    assert main(["--format", "json"]) == 2
    assert started == []
    captured = capsys.readouterr()
    assert captured.out == "" and "reverbscope demo" in captured.err


# --- How a command ends --------------------------------------------------------------------


def test_the_desktop_app_on_a_computer_without_a_screen_does_not_end_the_menu(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Qt aborts the process (exit status 134) when there is no display: the
    command says so first and ends with 2, and the menu is still there."""
    from reverbscope.ui import app

    monkeypatch.setattr(app, "pyside6_import_error", lambda: None)
    monkeypatch.setattr(app, "display_missing", lambda *args: True)
    visit = drive(["10", "q"], run=main, out=sys.stdout, prefix=["--lang", "en"])
    err = " ".join(capsys.readouterr().err.replace("│", " ").split())
    assert visit.code == 0
    assert "needs a graphical display" in err
    assert len(visit.prompts) == 2  # the menu asked again after the failure


def test_a_command_interrupted_with_ctrl_c_does_not_end_the_menu() -> None:
    def interrupted(_argv: list[str]) -> int:
        raise KeyboardInterrupt

    visit = drive(["1", "q"], run=interrupted)
    assert visit.code == 0 and "The command ended with exit code 130." in visit.text
    assert len(visit.prompts) == 2


def test_a_command_the_parser_refuses_does_not_end_the_menu() -> None:
    def refused(_argv: list[str]) -> int:
        raise SystemExit(2)

    visit = drive(["1", "q"], run=refused)
    assert visit.code == 0 and "The command ended with exit code 2." in visit.text
    assert len(visit.prompts) == 2
