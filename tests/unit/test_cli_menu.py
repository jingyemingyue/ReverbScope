"""The interactive menu: ``roomscope menu``, and bare ``roomscope`` on a terminal.

Every item is driven with scripted answers, as a person would type them: the
demo, the sweep and an analysis of the demo's recording run for real, a take
runs on the fake interface, and the results of the demo are shown and
compared. Ctrl+C, the end of input, paths that do not exist, numbers out of
range, quoted, escaped and Chinese paths, ``~``, and the refusal where nobody
can type are covered too.
"""

from __future__ import annotations

import contextlib
import io
import os
import re
import shutil
import sys
from collections.abc import Iterator, Sequence
from pathlib import Path

import pytest

from roomscope.cli import menu
from roomscope.cli.console import cell_width, shell_command
from roomscope.cli.main import main
from roomscope.cli.menu import Menu, clean_path, run_menu
from roomscope.demo import run_demo
from roomscope.i18n import activate
from tests.frames import FRAME_GLYPHS, frame_blocks
from tests.zh_tokens import english_words

#: An answer that presses Ctrl+C instead of typing.
CTRL_C = object()
#: Written in English on purpose: the way back for a reader of English.
ENGLISH_HINT = "English interface: roomscope config language en"
POSIX = os.name != "nt"


class Script:
    """The answers typed at the menu's questions, in order; then end of input.

    Each prompt and answer is written to stdout as a terminal would echo it,
    so the captured output reads like the session on screen.
    """

    def __init__(self, *answers: object) -> None:
        self.answers = list(answers)
        self.prompts: list[str] = []

    def __call__(self, prompt: str) -> str:
        self.prompts.append(prompt)
        sys.stdout.write(prompt)
        if not self.answers:
            raise EOFError
        answer = self.answers.pop(0)
        if answer is CTRL_C:
            raise KeyboardInterrupt
        sys.stdout.write(f"{answer}\n")
        return str(answer)


class Commands:
    """Records the command lines the menu runs; runs those naming ``run`` for real."""

    def __init__(self, *, code: int = 0, run: Sequence[str] = ()) -> None:
        self.calls: list[list[str]] = []
        self.code = code
        self.run = set(run)

    def __call__(self, argv: list[str]) -> int:
        self.calls.append(list(argv))
        if self.run.intersection(argv):
            return main(list(argv))
        return self.code


@pytest.fixture
def here(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Path]:
    """An empty working folder, its own settings, 80 columns, no colour."""
    monkeypatch.setenv("ROOMSCOPE_HOME", str(tmp_path / "home"))
    for name in (
        "NO_COLOR",
        "FORCE_COLOR",
        "TERM",
        "PYTHONIOENCODING",
        "ROOMSCOPE_AUDIO_BACKEND",
        menu.ENV_NO_MENU,
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("COLUMNS", "80")
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    try:
        yield work
    finally:
        activate("en")


@pytest.fixture(scope="module")
def demo_folder(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """What ``roomscope demo`` writes: a sweep, two recordings, two sessions, a comparison."""
    folder = tmp_path_factory.mktemp("menu_demo") / "roomscope-demo"
    run_demo(folder)
    return folder


def drive(
    *answers: object,
    root: Sequence[str] = (),
    dispatch: Commands | None = None,
    terminal_edition: bool = False,
) -> tuple[int, Script]:
    script = Script(*answers)
    code = run_menu(
        script, sys.stdout, root=root, dispatch=dispatch, terminal_edition=terminal_edition
    )
    return code, script


def same_as(*argv: str) -> str:
    return "→ Same as the command: " + shell_command(["roomscope", *argv])


# --- The screen ---------------------------------------------------------------------------


def test_the_menu_lists_every_item_and_0_leaves(
    here: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, script = drive("0")
    out = capsys.readouterr().out
    assert code == 0
    # The heading is a panel holding the one sentence that says what to do.
    head = out.lstrip().splitlines()[:4]
    assert head[0].startswith("╭─ RoomScope menu ─") and head[0].endswith("╮")
    assert "Type a number and press Enter." in head[1] and head[1].startswith("│ ")
    assert head[2].startswith("│ ") and head[3].startswith("╰") and head[3].endswith("╯")
    assert {cell_width(line) for line in head} == {80}
    for row in (
        "1  Try the demo",
        "2  Write the test signal",
        "3  Analyse a recording",
        "4  Measure with your interface",
        "5  View results",
        "6  Compare two positions",
        "7  Open the desktop app",
        "8  Settings",
        "9  Environment report",
        "0  Quit",
    ):
        assert f"\n  {row}" in out, row
    assert script.prompts == ["Choose a number: "]
    assert all(len(line) <= 80 for line in out.splitlines())


@pytest.mark.parametrize("answer", ["q", "Q", "quit", "exit"])
def test_q_leaves_too(here: Path, capsys: pytest.CaptureFixture[str], answer: str) -> None:
    assert drive(answer)[0] == 0


@pytest.mark.parametrize("answer", ["０", "ｑ", "ＱＵＩＴ", " 0 "])
def test_a_full_width_answer_is_read_as_typed_on_a_chinese_keyboard(
    here: Path, capsys: pytest.CaptureFixture[str], answer: str
) -> None:
    assert drive(answer)[0] == 0
    assert "no item" not in capsys.readouterr().out.lower()


def test_a_full_width_number_chooses_the_item(
    here: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    dispatch = Commands()
    code, _script = drive("９", "", "0", dispatch=dispatch)
    assert code == 0
    assert dispatch.calls == [["doctor"]]


def test_the_chinese_word_for_quit_leaves_the_chinese_menu(
    here: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    activate("zh_CN")
    code, _script = drive("退出")
    out = capsys.readouterr().out
    assert code == 0 and "菜单中没有" not in out
    assert "也可以输入 q 或“退出”" in out
    activate("en")
    assert drive("退出")[0] == 0  # English has no such word: asked again, then the input ends
    assert "There is no item" in capsys.readouterr().out


def test_the_menu_is_chinese_in_chinese(here: Path, capsys: pytest.CaptureFixture[str]) -> None:
    activate("zh_CN")
    code, script = drive("0")
    out = capsys.readouterr().out
    assert code == 0
    for row in (
        "1  体验演示",
        "2  生成测试信号",
        "3  分析录音",
        "4  用声卡直接测量",
        "5  查看结果",
        "6  对比两个位置",
        "7  打开桌面应用",
        "8  设置",
        "9  环境报告",
        "0  退出",
    ):
        assert f"\n  {row}" in out, row
    assert script.prompts == ["请输入编号："]
    assert english_words(out.replace(ENGLISH_HINT, "")) == []


@pytest.mark.parametrize("lang", ["zh_CN", "zh_TW", "ja", "ko", "es", "fr", "de"])
def test_every_language_has_its_menu(
    here: Path, capsys: pytest.CaptureFixture[str], lang: str
) -> None:
    activate(lang)
    _code, script = drive("3", CTRL_C, "0")
    out = capsys.readouterr().out
    for english in ("RoomScope menu", "Try the demo", "0  Quit ", "Choose a number"):
        assert english not in out, (lang, english)
    assert not any("Recording" in prompt for prompt in script.prompts)


def test_the_terminal_edition_has_no_desktop_app_item(
    here: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    dispatch = Commands()
    code, _script = drive("7", "0", dispatch=dispatch, terminal_edition=True)
    out = capsys.readouterr().out
    assert code == 0 and dispatch.calls == []
    assert "Open the desktop app" not in out
    assert "There is no item 7 in the menu" in out


@pytest.mark.parametrize("lang", ["en", "zh_CN"])
@pytest.mark.parametrize("width", [40, 50, 60, 80, 100])
def test_the_menu_fits_the_screen_and_its_frames_line_up(
    here: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    lang: str,
    width: int,
) -> None:
    monkeypatch.setenv("COLUMNS", str(width))
    activate(lang)
    code, _script = drive("8", "0", "2", "", "", "", "", dispatch=Commands())
    out = capsys.readouterr().out
    assert code == 0
    # A command to copy is never wrapped, so it may run past a narrow screen.
    assert all(
        cell_width(line) <= width for line in out.splitlines() if "roomscope " not in line
    ), out
    blocks = frame_blocks(out)
    assert blocks  # the heading is a panel
    for block in blocks:
        assert {cell_width(line) for line in block} == {width}, "\n".join(block)
    # A line with a command to copy is bare: no border, no bar.
    commands = [line for line in out.splitlines() if "roomscope " in line]
    assert any("roomscope sweep --out" in line for line in commands)
    for line in commands:
        assert not set(line) & set(FRAME_GLYPHS), line


def test_the_menu_follows_the_style_stored_by_config(
    here: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["config", "style", "plain"]) == 0
    capsys.readouterr()
    code, _script = drive("5", "0")
    out = capsys.readouterr().out
    assert code == 0
    assert out.lstrip().startswith("RoomScope menu\n──────────────\n")
    assert not set(out) & set("╭╮╰╯│┏┃▌")
    assert "\n  1  Try the demo" in out


def test_a_question_longer_than_the_screen_is_written_in_lines(
    here: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("COLUMNS", "60")
    code, script = drive("2", "", "", "", "", dispatch=Commands())
    out = capsys.readouterr().out
    assert code == 0
    rate = script.prompts[2]  # the last line of the question about the sample rate
    assert rate.endswith("[48000]: ") and "Sample rate" not in rate
    assert cell_width(rate) <= 60 - 10  # room to type the answer
    first = out[: out.index(rate)].splitlines()[-1]
    assert first.startswith("  Sample rate in Hz (44100,")


def test_a_narrow_screen_lists_sessions_without_a_table(
    here: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    demo_folder: Path,
) -> None:
    monkeypatch.setenv("COLUMNS", "60")
    shutil.copytree(demo_folder, here / "roomscope-demo")
    code, _script = drive("5", "1", dispatch=Commands(), root=["--lang", "en"])
    out = capsys.readouterr().out
    assert code == 0
    listed = out[out.index("View results\n") : out.index("Session number")]
    assert not set(listed) & set("┏┃┡│└")
    lines = listed.splitlines()
    first = next(i for i, line in enumerate(lines) if "position-b" in line)
    assert lines[first].startswith("  1  ")  # the number, then the folder to type
    assert lines[first + 1].lstrip().startswith("B: moved 1 m back from the desk")
    assert all(cell_width(line) <= 60 for line in lines)


def test_an_unknown_choice_is_asked_again(here: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, script = drive("", "x", "42", "0")
    out = capsys.readouterr().out
    assert code == 0
    assert "There is no item x in the menu" in out and "There is no item 42" in out
    assert out.count("RoomScope menu") == 1  # asked again, not redrawn
    assert len(script.prompts) == 4


# --- Keys ---------------------------------------------------------------------------------


def test_ctrl_c_at_a_question_goes_back_to_the_menu(
    here: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    dispatch = Commands()
    code, _script = drive("3", CTRL_C, "0", dispatch=dispatch)
    out = capsys.readouterr().out
    assert code == 0 and dispatch.calls == []
    assert out.count("RoomScope menu") == 2
    assert "Traceback" not in out


def test_ctrl_c_at_the_menu_leaves_with_130(here: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert drive(CTRL_C)[0] == 130


@pytest.mark.parametrize(
    "answers",
    [(), ("2",), ("2", "sweep.wav"), ("8",), ("8", "1"), ("5",), ("9",)],
    ids=["menu", "question", "second-question", "settings", "language", "sessions", "pause"],
)
def test_end_of_input_leaves_cleanly_anywhere(
    here: Path, capsys: pytest.CaptureFixture[str], answers: tuple[str, ...]
) -> None:
    code, _script = drive(*answers, dispatch=Commands())
    captured = capsys.readouterr()
    assert code == 0
    assert "Traceback" not in captured.out + captured.err


# --- Answers that look like numbers -------------------------------------------------------


@pytest.mark.parametrize(
    "typed", ["①", "²", "٣٣٣٣٣", "1" * 5000, "9" * 400, "-1", "1.5", "１２３４"]
)
def test_a_number_prompt_asks_again_instead_of_failing(typed: str) -> None:
    """``①`` and ``²`` are digits to ``str.isdigit`` but not to ``int``; a string
    of thousands of digits is more than ``int`` takes. Each is taken as the
    number it stands for or refused in words, never a crash of the whole menu."""
    for check in (
        menu.number_between(0, 4),
        menu.one_of([0, 1], "x"),
        menu.sample_rate,
        menu.sweep_seconds,
        menu.level_dbfs,
    ):
        with contextlib.suppress(menu.InvalidAnswerError):
            check(typed)


@pytest.mark.parametrize(
    ("check", "typed", "value"),
    [
        (menu.number_between(0, 4), "３", 3),
        (menu.number_between(0, 4), "②", 2),  # a circled digit is the digit
        (menu.one_of([0, 1, 2], "x"), "２", 2),
        (menu.sample_rate, "４８０００", 48000),
        (menu.sample_rate, "44．1 kHz", 44100),
        (menu.sweep_seconds, "１０", 10.0),
        (menu.level_dbfs, "－２０", -20.0),
    ],
)
def test_a_full_width_digit_or_sign_is_a_number_too(check, typed, value) -> None:  # type: ignore[no-untyped-def]
    assert check(typed) == value


@pytest.mark.parametrize("typed", ["⑩", "½", "9" * 5000])
def test_the_menu_keeps_asking_when_a_number_is_not_one(
    here: Path, capsys: pytest.CaptureFixture[str], typed: str
) -> None:
    dispatch = Commands()
    code, _script = drive("8", typed, "0", "0", dispatch=dispatch)
    captured = capsys.readouterr()
    assert code == 0 and dispatch.calls == []
    assert "Type a number from 0 to 4." in captured.out
    assert "unexpected error" not in captured.out + captured.err


def test_a_session_number_that_is_not_a_number_is_asked_again(
    here: Path, capsys: pytest.CaptureFixture[str], demo_folder: Path
) -> None:
    shutil.copytree(demo_folder, here / "roomscope-demo")
    dispatch = Commands()
    code, _script = drive("5", "½", "9" * 5000, "１", "", dispatch=dispatch)
    out = capsys.readouterr().out
    assert code == 0
    assert out.count("was not found") == 2  # read as paths, which do not exist
    assert len(dispatch.calls) == 1 and dispatch.calls[0][0] == "show"


# --- Paths --------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("typed", "posix", "expected"),
    [
        ("  take.wav  ", True, "take.wav"),
        ('"My Take.wav"', True, "My Take.wav"),
        ("'My Take.wav' ", True, "My Take.wav"),
        ("“我的 录音.wav”", True, "我的 录音.wav"),
        (r"/Users/me/My\ Take\ \(1\).wav ", True, "/Users/me/My Take (1).wav"),
        (r"我的\ 录音.wav", True, "我的 录音.wav"),
        (r"'My\ Take.wav'", True, r"My\ Take.wav"),  # quoted: nothing to undo
        # GNOME and KDE write an apostrophe as '\'' inside the quotes.
        ("'it'\\''s a take.wav'", True, "it's a take.wav"),
        ("'it'\\''s'\\''s a take.wav'", True, "it's's a take.wav"),
        ('"it\'s a take.wav"', True, "it's a take.wav"),
        ("'it's a take.wav'", True, "it's a take.wav"),  # one pair of quotes, apostrophe inside
        ("It's Bob's.wav", True, "It's Bob's.wav"),  # not quoted: an apostrophe is a letter
        (r"C:\Takes\take.wav", False, r"C:\Takes\take.wav"),
        (r'"C:\My Takes\take.wav"', False, r"C:\My Takes\take.wav"),
        (r"& 'C:\My Takes\take.wav'", False, r"C:\My Takes\take.wav"),
    ],
)
def test_a_typed_or_dropped_path_is_cleaned(typed: str, posix: bool, expected: str) -> None:
    assert clean_path(typed, posix=posix) == expected


def test_a_path_that_starts_with_a_dash_is_not_an_option() -> None:
    assert menu.path_arg(Path("-take.wav")) == os.curdir + os.sep + "-take.wav"
    assert menu.path_arg(Path("take.wav")) == "take.wav"


# --- 1 Demo -------------------------------------------------------------------------------


def test_the_demo_runs_here_and_shows_its_command(
    here: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, script = drive("1", "", "")
    out = capsys.readouterr().out
    assert code == 0
    assert script.prompts[1] == "  Folder for the demo files [roomscope-demo]: "
    assert same_as("demo") in out
    assert "RoomScope demo" in out  # the command's own report, in this process
    assert (here / "roomscope-demo" / "position-a" / "session.json").is_file()
    assert script.prompts[-2:] == ["Press Enter to return to the menu ", "Choose a number: "]


def test_the_demo_asks_before_replacing_a_demo(
    here: Path, capsys: pytest.CaptureFixture[str], demo_folder: Path
) -> None:
    shutil.copytree(demo_folder, here / "roomscope-demo")
    (here / "notes").mkdir()
    (here / "notes" / "todo.txt").write_text("keep", encoding="utf-8")
    dispatch = Commands()
    code, _script = drive(
        "1", "", "n", "notes", "elsewhere", "", "1", "", "y", "", dispatch=dispatch
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "roomscope-demo holds an earlier demo. Replace it? [y/N]: n" in out
    assert "notes already exists and was not written by roomscope demo" in out
    assert dispatch.calls == [["demo", "--out", "elsewhere"], ["demo"]]
    assert (here / "notes" / "todo.txt").read_text(encoding="utf-8") == "keep"


# --- 2 Sweep ------------------------------------------------------------------------------


def test_the_sweep_is_written_with_the_defaults(
    here: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("COLUMNS", "100")  # the longest question fits on one line
    code, script = drive("2", "", "", "", "")
    out = capsys.readouterr().out
    assert code == 0
    assert script.prompts[1:4] == [
        "  File for the test signal [sweep.wav]: ",
        "  Sample rate in Hz (44100, 48000, 88200, 96000, 176400, 192000) [48000]: ",
        "  Length of the sweep in seconds [10]: ",
    ]
    assert same_as("sweep", "--out", "sweep.wav") in out
    assert (here / "sweep.wav").is_file()


def test_the_sweep_rechecks_rate_and_length(here: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (here / "sweep.wav").write_bytes(b"")
    dispatch = Commands()
    answers = ("2", "", "", "my sweep", "12345", "96k", "0.1", "long", "15 s", "")
    code, _script = drive(*answers, dispatch=dispatch)
    out = capsys.readouterr().out
    assert code == 0
    assert "sweep.wav already exists. Replace it? [y/N]: " in out
    assert out.count("Type one of these sample rates: 44100, 48000") == 1
    assert out.count("Type a duration from 0.5 to 120 s.") == 2
    argv = ["sweep", "--out", "my sweep.wav", "--sample-rate", "96000", "--duration", "15"]
    assert dispatch.calls == [argv]
    assert same_as(*argv) in out


# --- 3 Analyze ----------------------------------------------------------------------------


def test_a_recording_of_the_demo_is_analysed(
    here: Path, capsys: pytest.CaptureFixture[str], demo_folder: Path
) -> None:
    shutil.copytree(demo_folder, here / "roomscope-demo")
    recording = str(Path("roomscope-demo", "position-a.wav"))
    sweep = str(Path("roomscope-demo", "sweep.wav"))
    code, script = drive("3", "missing.wav", "roomscope-demo", recording, "", "", "")
    out = capsys.readouterr().out
    assert code == 0
    assert "missing.wav was not found; check the path and type it again." in out
    assert "roomscope-demo is a folder; type the path of a file." in out
    # The sweep next to the recording, and a new session folder, are the defaults.
    assert f"  Test signal played for it [{sweep}]: " in script.prompts
    assert "  Folder for the results [session-1]: " in script.prompts
    argv = ["analyze", "--recording", recording, "--sweep", sweep, "--out", "session-1"]
    assert same_as(*argv) in out
    assert "RoomScope analysis" in out
    assert (here / "session-1" / "session.json").is_file()


def _take(here: Path) -> Path:
    take = here / "录音 一.wav"
    take.write_bytes(b"RIFF")
    (here / "sweep.wav").write_bytes(b"RIFF")
    return take


@pytest.mark.parametrize(
    "form", ["quoted", "double-quoted", "escaped", "home", "chinese-quotes", "plain"]
)
def test_a_recording_path_may_be_quoted_escaped_chinese_or_under_home(
    here: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, form: str
) -> None:
    take = _take(here)
    monkeypatch.setenv("HOME", str(here))
    monkeypatch.setenv("USERPROFILE", str(here))
    typed, expected = {
        "quoted": (f"'{take}'", str(take)),
        "double-quoted": (f'"{take}"', str(take)),
        "escaped": ("录音\\ 一.wav", "录音 一.wav"),
        "home": (str(Path("~", "录音 一.wav")), str(take)),
        "chinese-quotes": (f"“{take}”", str(take)),
        "plain": ("录音 一.wav", "录音 一.wav"),
    }[form]
    if form == "escaped" and not POSIX:
        pytest.skip("a backslash separates folders on Windows")
    dispatch = Commands()
    code, _script = drive("3", typed, "", "", "", dispatch=dispatch)
    out = capsys.readouterr().out
    assert code == 0
    argv = ["analyze", "--recording", expected, "--sweep", "sweep.wav", "--out", "session-1"]
    assert dispatch.calls == [argv]
    # The command to copy quotes the space.
    assert same_as(*argv) in out
    assert "'" in same_as(*argv) or '"' in same_as(*argv)


@pytest.mark.skipif(not POSIX, reason="a POSIX shell reads the command")
@pytest.mark.parametrize(
    "name", ["录音(1).wav", "a&b.wav", "a;b.wav", "#hash.wav", "$HOME.wav", "a*b.wav", "a|b.wav"]
)
def test_the_command_to_copy_runs_the_same_in_a_shell(
    here: Path, capsys: pytest.CaptureFixture[str], name: str
) -> None:
    """A name with a bracket, an ampersand or a dollar is quoted, so the line
    printed under "Same as the command" is one command with the same words."""
    import shlex
    import subprocess

    (here / name).write_bytes(b"RIFF")
    (here / "sweep.wav").write_bytes(b"RIFF")
    dispatch = Commands()
    code, _script = drive("3", name, "", "", "", dispatch=dispatch)
    out = capsys.readouterr().out
    assert code == 0
    argv = ["analyze", "--recording", name, "--sweep", "sweep.wav", "--out", "session-1"]
    assert dispatch.calls == [argv]
    line = next(
        line.split(": ", 1)[1] for line in out.splitlines() if "Same as the command: " in line
    )
    assert line == shell_command(["roomscope", *argv])
    assert shlex.split(line)[1:] == argv
    shell = shutil.which("bash") or shutil.which("sh")
    assert shell is not None
    echoed = subprocess.run(
        [shell, "-c", line.replace("roomscope", "printf '<%s>' ", 1)],
        capture_output=True,
        text=True,
        check=True,
        cwd=here,
        env={"PATH": os.environ["PATH"], "HOME": "/nonexistent"},
    )
    assert echoed.stdout == "".join(f"<{word}>" for word in argv)


def test_the_results_folder_of_a_saved_session_is_not_replaced_silently(
    here: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _take(here)
    (here / "session-1").mkdir()
    (here / "session-1" / "session.json").write_text("{}", encoding="utf-8")
    (here / "a file").write_text("", encoding="utf-8")
    dispatch = Commands()
    answers = ("3", "录音 一.wav", "", "session-1", "n", "a file", "", "")
    code, _script = drive(*answers, dispatch=dispatch)
    out = capsys.readouterr().out
    assert code == 0
    assert "session-1 holds a saved session. Replace it? [y/N]: n" in out
    assert "a file is a file; type a folder." in out
    assert dispatch.calls[0][-2:] == ["--out", "session-2"]


# --- 4 Measure ----------------------------------------------------------------------------


def test_a_take_on_the_fake_interface(here: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = ["--backend", "fake"]
    code, script = drive("4", "", "", "", "", "", "y", "", root=root)
    out = capsys.readouterr().out
    assert code == 0
    # The devices as "roomscope devices" lists them, then the questions.
    assert same_as(*root, "devices") in out
    assert "Audio devices" in out and "RoomScope fake interface" in out
    assert script.prompts[1:7] == [
        "  Input device (the microphone) [system default]: ",
        "  Output device (the loudspeakers) [system default]: ",
        "  Input channel of the microphone [1]: ",
        "  Level of the sweep in dBFS [-20]: ",
        "  Folder for the session [session-1]: ",
        "  Type y to play the sweep now [y/N]: ",
    ]
    # The plan and the monitor warning come before the question, the take after it.
    plan = out.index("Measurement plan")
    warning = out.index("Start with your monitor/interface output at a low level")
    question = out.index("Type y to play the sweep now")
    assert plan < warning < question < out.index(same_as(*root, "measure", "--out", "session-1"))
    assert re.search(r"^│ Level\s+-20 dBFS\s+│$", out, re.MULTILINE)  # the plan is a panel
    assert (here / "session-1" / "recording.wav").is_file()


def test_nothing_plays_without_an_explicit_y(
    here: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    dispatch = Commands()
    for answer in ("", "n", "ok"):
        code, _script = drive("4", "", "", "", "", "", answer, "", root=["--backend", "fake"])
        assert code == 0
    out = capsys.readouterr().out
    assert out.count("Nothing was played.") == 3
    assert dispatch.calls == []


def test_measure_rechecks_numbers_and_asks_before_a_loud_level(
    here: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    dispatch = Commands()
    answers = ("4", "5", "0", "7", "", "9", "3", "6", "-6", "n", "-6", "y", "", "y", "")
    code, _script = drive(*answers, root=["--backend", "fake"], dispatch=dispatch)
    out = capsys.readouterr().out
    assert code == 0
    assert "Type one of these input devices: 0, or press Enter." in out
    assert "Type one of these output devices: 0, or press Enter." in out
    assert "Type a number from 1 to 8." in out
    assert "Type a level from -80 to 0 dBFS." in out
    assert out.count("-6 dBFS is above -12 dBFS. Is the monitor level already turned down?") == 2
    assert dispatch.calls == [
        [
            "--backend",
            "fake",
            "measure",
            "--out",
            "session-1",
            "--input-device",
            "0",
            "--input-channel",
            "3",
            "--level",
            "-6",
            "--acknowledge-level",
        ]
    ]


# --- 5 Show and 6 Compare -----------------------------------------------------------------


def test_sessions_here_and_in_the_output_folder_are_listed_and_shown(
    here: Path, capsys: pytest.CaptureFixture[str], demo_folder: Path, tmp_path: Path
) -> None:
    shutil.copytree(demo_folder, here / "roomscope-demo")
    output = tmp_path / "takes"
    shutil.copytree(demo_folder / "position-b", output / "take-b")
    assert main(["config", "output-folder", str(output)]) == 0
    capsys.readouterr()
    code, _script = drive("5", "4", "1", "")
    out = capsys.readouterr().out
    assert code == 0
    # A table, or one block a session where the output folder's path is too long for one.
    table = out[out.index("View results\n") : out.index("Session number")]
    assert str(Path("roomscope-demo", "position-a")) in table
    assert str(Path("roomscope-demo", "position-b")) in table
    assert str(output.resolve() / "take-b") in table or str(output / "take-b") in table
    assert "Type a number from 1 to 3." in out
    assert "RoomScope analysis" in out  # roomscope show, run here


def test_the_session_table_keeps_a_line_a_session(
    here: Path, capsys: pytest.CaptureFixture[str], demo_folder: Path
) -> None:
    shutil.copytree(demo_folder, here / "roomscope-demo")
    code, _script = drive("5", "", dispatch=Commands(code=0), root=["--lang", "en"])
    out = capsys.readouterr().out
    assert code == 0
    table = out[out.index("View results\n") : out.index("Session number")].splitlines()
    rows = [line for line in table if "position-" in line]
    assert len(rows) == 2  # one line a session, the long position cut, not wrapped
    # A bordered table: every line as wide as the others, none wider than the screen.
    assert {cell_width(line) for line in table if line and line[0] in "┏┃┡│└"} == {80}
    assert all(line.startswith("│ ") for line in rows)
    assert "No." in "".join(table)  # the narrow header is whole
    long_position = next(line for line in rows if "position-a" in line)
    assert "close to the desk and the side wall" not in long_position
    assert "…" in long_position or "..." in long_position


def test_a_comparison_or_a_folder_can_be_typed_instead(
    here: Path, capsys: pytest.CaptureFixture[str], demo_folder: Path
) -> None:
    shutil.copytree(demo_folder, here / "roomscope-demo")
    comparison = str(Path("roomscope-demo", "comparison.json"))
    dispatch = Commands()
    code, _script = drive("5", "nowhere", comparison, "", dispatch=dispatch)
    out = capsys.readouterr().out
    assert code == 0
    assert "nowhere was not found" in out
    assert dispatch.calls == [["show", comparison]]


def test_no_sessions_asks_for_a_path(here: Path, capsys: pytest.CaptureFixture[str]) -> None:
    dispatch = Commands()
    code, script = drive("5", "1", dispatch=dispatch)
    out = capsys.readouterr().out
    assert code == 0 and dispatch.calls == []
    assert "No saved sessions were found in this folder or in the output folder." in out
    assert "  Path of a session folder or comparison.json: " in script.prompts
    assert "Type the path of a session folder." in out


def test_compare_takes_a_baseline_then_another_candidate(
    here: Path, capsys: pytest.CaptureFixture[str], demo_folder: Path
) -> None:
    shutil.copytree(demo_folder, here / "roomscope-demo")
    dispatch = Commands(run=["compare"])
    code, _script = drive("6", "1", "1", "2", "", dispatch=dispatch)
    out = capsys.readouterr().out
    assert code == 0
    assert "That is the baseline; choose another session." in out
    (call,) = dispatch.calls
    assert call[0] == "compare" and sorted(call[1:]) == sorted(
        str(Path("roomscope-demo", name)) for name in ("position-a", "position-b")
    )
    assert "RoomScope comparison" in out


# --- 7 GUI and 9 Doctor -------------------------------------------------------------------


def test_the_desktop_app_and_the_environment_report_run_their_commands(
    here: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    dispatch = Commands()
    code, _script = drive("7", "", "9", "", root=["--lang", "en"], dispatch=dispatch)
    out = capsys.readouterr().out
    assert code == 0
    assert dispatch.calls == [["--lang", "en", "gui"], ["--lang", "en", "doctor"]]
    assert same_as("--lang", "en", "doctor") in out


def test_a_failed_command_is_named_in_words(here: Path, capsys: pytest.CaptureFixture[str]) -> None:
    drive("9", "", dispatch=Commands(code=1))
    assert "The command did not succeed: an error stopped it (exit status 1)." in (
        capsys.readouterr().out
    )

    def refuse(argv: list[str]) -> int:
        raise SystemExit(2)

    run_menu(Script("9", ""), sys.stdout, dispatch=refuse, terminal_edition=False)
    assert "it could not run as asked (exit status 2)" in capsys.readouterr().out


# --- 8 Settings ---------------------------------------------------------------------------


def test_the_language_is_changed_through_roomscope_config(
    here: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    dispatch = Commands(run=["config"])
    code, script = drive("8", "1", "1", "0", "9", "", root=["--lang", "en"], dispatch=dispatch)
    out = capsys.readouterr().out
    assert code == 0
    assert dispatch.calls[0] == ["--lang", "en", "config", "language", "zh_CN"]
    # The language chosen applies from now on, also to the commands run next.
    assert dispatch.calls[1] == ["doctor"]
    assert '"language": "zh_CN"' in (here.parent / "home" / "settings.json").read_text("utf-8")
    after = out[out.index(same_as("--lang", "en", "config", "language", "zh_CN")) :]
    assert "界面语言" in after and "1  体验演示" in after
    assert script.prompts[-2:] == ["按回车返回菜单 ", "请输入编号："]


def test_the_language_list_names_every_catalog_and_the_system(
    here: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    dispatch = Commands()
    code, _script = drive("8", "1", "9", "0", dispatch=dispatch)
    out = capsys.readouterr().out
    assert code == 0
    listed = out[out.index("Interface language\n") :]
    for row in (
        "1  简体中文",
        "2  English",
        "3  繁體中文",
        "4  日本語",
        "5  한국어",
        "6  Español",
        "7  Français",
        "8  Deutsch",
        "9  follow the system",
    ):
        assert f"\n  {row}" in listed, row
    assert dispatch.calls == [["config", "language", "auto"]]


def test_profile_backend_and_output_folder_are_changed_through_roomscope_config(
    here: Path, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    from roomscope.interpretation import available_profiles
    from roomscope.settings import load_settings

    drums = str(list(available_profiles()).index("drums") + 1)
    folder = tmp_path / "takes"
    folder.mkdir()
    answers = ("8", "2", drums, "3", "2", "4", "nowhere", str(folder), "4", "", "0", "0")
    dispatch = Commands(run=["config"])
    code, _script = drive(*answers, dispatch=dispatch)
    out = capsys.readouterr().out
    assert code == 0
    assert dispatch.calls == [
        ["config", "profile", "drums"],
        ["config", "backend", "fake"],
        ["config", "output-folder", str(folder)],
    ]
    stored = load_settings()
    assert (stored.default_profile, stored.audio_backend) == ("drums", "fake")
    assert Path(stored.output_dir) == folder.resolve()
    assert "nowhere is not an existing folder." in out
    assert "Nothing was changed." in out  # Enter kept the folder
    assert "4  Output folder" in out and str(folder.resolve()) in out


# --- Starting -----------------------------------------------------------------------------


class _Tty(io.StringIO):
    def isatty(self) -> bool:
        return True


def test_bare_roomscope_opens_the_menu_on_a_terminal(
    here: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stdout = _Tty()
    monkeypatch.setattr(sys, "stdin", _Tty("0\n"))
    monkeypatch.setattr(sys, "stdout", stdout)
    assert main([]) == 0
    assert "RoomScope menu" in stdout.getvalue()
    assert "Choose a number: " in stdout.getvalue()


@pytest.mark.parametrize("why", ["no-menu", "json", "pipe-in", "pipe-out"])
def test_bare_roomscope_keeps_the_home_screen_otherwise(
    here: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], why: str
) -> None:
    argv: list[str] = []
    if why == "no-menu":
        monkeypatch.setenv(menu.ENV_NO_MENU, "1")
    if why == "json":
        argv = ["--format", "json"]
    monkeypatch.setattr(sys, "stdin", io.StringIO("0\n") if why == "pipe-in" else _Tty("0\n"))
    if why != "pipe-out":
        monkeypatch.setattr(sys, "stdout", _Tty())
    assert main(argv) == 2
    err = capsys.readouterr().err
    assert "roomscope demo" in err and "RoomScope menu" not in err


@pytest.mark.parametrize("lang", ["en", "zh_CN"])
def test_the_menu_command_refuses_where_nobody_can_type(
    here: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], lang: str
) -> None:
    monkeypatch.setattr(sys, "stdin", io.StringIO("0\n"))
    assert main(["--lang", lang, "menu"]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    message = {
        "en": "the menu needs a terminal to type the answers in",
        "zh_CN": "菜单需要在终端里输入回答",
    }[lang]
    assert message in captured.err and "roomscope --help" in captured.err
    if lang == "zh_CN":
        assert english_words(captured.err) == []


def test_the_menu_command_refuses_json(
    here: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "stdin", _Tty("0\n"))
    monkeypatch.setattr(sys, "stdout", _Tty())
    assert main(["--format", "json", "menu"]) == 2
    assert "the menu prints text, not JSON" in capsys.readouterr().err


def test_the_options_before_the_command_are_kept(here: Path) -> None:
    from roomscope.cli.main import build_parser

    args = build_parser().parse_args(
        ["--lang", "zh_CN", "--color", "never", "--backend", "fake", "--no-copy-recording", "-v"]
    )
    assert menu.root_options(args) == [
        "--lang",
        "zh_CN",
        "--color",
        "never",
        "--backend",
        "fake",
        "--no-copy-recording",
        "--verbose",
    ]
    assert menu.root_options(build_parser().parse_args([])) == []


def test_the_menu_writes_only_through_the_console(here: Path) -> None:
    """The look comes from Console; the menu writes no escape sequence of its own."""
    source = Path(menu.__file__).read_text(encoding="utf-8")
    assert "\\x1b" not in source and "\\033" not in source
    assert isinstance(Menu(read=input, out=io.StringIO(), dispatch=main).console().width, int)
