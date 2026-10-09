"""What the menu makes of an answer that is not quite what it asked for.

A Chinese input method types ``９`` and ``ｙ``; a number may be ``①`` or ``²``
(digits to ``str.isdigit``, not to ``int``) or five thousand digits (more than
``int`` takes); a terminal drops a dragged file as ``'it'\\''s a take.wav'``.
Each is understood or refused in words; none ends the menu or prints a
traceback.
"""

from __future__ import annotations

import os
import shlex
from pathlib import Path

import pytest

from reverbscope.cli.interactive import clean_path, fold, parse_path, path_arg, whole_number
from tests.menus import drive

POSIX = os.name != "nt"
RATE_ERROR = "Choose one of 44100, 48000, 88200, 96000, 176400, 192000."


@pytest.fixture(autouse=True)
def _work_in_a_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


# --- Numbers --------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("typed", "value"),
    [
        ("48000", 48000),
        (" 48000 ", 48000),
        ("４８０００", 48000),  # full-width digits, as a Chinese input method types them
        ("①", 1),  # a circled digit is the digit
        ("²", 2),
        ("٣", 3),
    ],
)
def test_a_digit_of_another_form_is_the_number(typed: str, value: int) -> None:
    assert whole_number(typed) == value


@pytest.mark.parametrize(
    "typed", ["", "x", "-1", "+1", "1.5", "1e3", "½", "1" * 5000, "9" * 400, "1 000", "０x"]
)
def test_anything_else_is_not_a_number_and_never_raises(typed: str) -> None:
    assert whole_number(typed) is None


def test_fold_turns_full_width_letters_and_signs_into_ascii() -> None:
    assert fold(" ＱＵＩＴ ") == "QUIT"
    assert fold("ｙ") == "y"
    assert fold("４４．１") == "44.1"
    # A file name is never folded: NFKC would rename the file. Only answers are.
    assert parse_path("ｆｉｌｅ.wav") == Path("ｆｉｌｅ.wav")


@pytest.mark.parametrize(
    "typed", ["①", "²", "٣٣٣٣٣", "1" * 5000, "9" * 400, "-1", "1.5", "１２３４", "⑩", "½"]
)
def test_a_rate_that_is_not_a_rate_is_refused_in_words(
    typed: str, caplog: pytest.LogCaptureFixture
) -> None:
    visit = drive(["2", "s.wav", typed, "48000", "q"])
    assert visit.code == 0
    assert visit.text.count(RATE_ERROR) == 1
    assert "could not be completed" not in visit.text
    assert visit.runs == [["sweep", "--out", "s.wav", "--sample-rate", "48000"]]
    assert "Traceback" not in caplog.text


def test_a_full_width_rate_is_the_rate() -> None:
    visit = drive(["2", "s.wav", "４４１００", "q"])
    assert visit.runs == [["sweep", "--out", "s.wav", "--sample-rate", "44100"]]
    assert RATE_ERROR not in visit.text


# --- The menu's own words -------------------------------------------------------------------


def test_a_full_width_number_chooses_the_item() -> None:
    visit = drive(["９", "q"])
    assert visit.runs == [["doctor"]]
    visit = drive(["１", "①", "q"])
    assert visit.runs == [["demo"], ["demo"]]
    visit = drive(["１０", "q"])
    assert visit.runs == [["gui"]]


@pytest.mark.parametrize("typed", ["q", "Q", "quit", "exit", "ｑ", "ＱＵＩＴ", " q ", "0", "０"])
def test_q_in_any_form_leaves_without_a_complaint(typed: str) -> None:
    visit = drive([typed, "9"])
    assert visit.code == 0 and visit.runs == []
    assert "Choose a number from the list" not in visit.text


def test_the_chinese_word_for_quit_leaves_the_chinese_menu() -> None:
    visit = drive(["退出", "9"], lang="zh_CN")
    assert visit.code == 0 and visit.runs == []
    assert "请输入列表中的编号" not in visit.text
    # English has no such word: asked again, then the input ends.
    visit = drive(["退出", "q"])
    assert visit.code == 0
    assert "Choose a number from the list, or q." in visit.text


def test_the_menu_keeps_asking_when_the_choice_is_not_one() -> None:
    visit = drive(["9" * 5000, "½", "-1", "42", "q"])
    assert visit.code == 0 and visit.runs == []
    assert visit.text.count("Choose a number from the list, or q.") == 4


@pytest.mark.parametrize("answer", ["y", "Y", "yes", "ｙ", "ＹＥＳ", " y "])
def test_a_yes_in_any_form_is_a_yes(answer: str) -> None:
    Path("a").mkdir()
    Path("b").mkdir()
    visit = drive(["6", "a", "b", answer, "q"])
    assert visit.runs == [["compare", "a", "b", "--same-input-gain"]]


def test_anything_but_a_yes_is_a_no() -> None:
    Path("a").mkdir()
    Path("b").mkdir()
    for answer in ("", "n", "no", "ok", "yy", "是吗"):
        visit = drive(["6", "a", "b", answer, "q"])
        assert visit.runs == [["compare", "a", "b"]], answer


def test_a_chinese_yes_is_a_yes_in_the_chinese_menu() -> None:
    Path("a").mkdir()
    Path("b").mkdir()
    visit = drive(["6", "a", "b", "是", "q"], lang="zh_CN")
    assert visit.runs == [["compare", "a", "b", "--same-input-gain"]]


# --- Paths ----------------------------------------------------------------------------------


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
        # GNOME Terminal and KDE write an apostrophe as '\'' between two quoted parts.
        ("'it'\\''s a take.wav'", True, "it's a take.wav"),
        ("'it'\\''s'\\''s a take.wav'", True, "it's's a take.wav"),
        ("'/home/me/it'\\''s a take.wav'", True, "/home/me/it's a take.wav"),
        (r"it\'s\ a\ take.wav", True, "it's a take.wav"),
        ('"it\'s a take.wav"', True, "it's a take.wav"),
        ("'it's a take.wav'", True, "it's a take.wav"),  # one pair of quotes, an apostrophe inside
        ("It's Bob's.wav", True, "It's Bob's.wav"),  # not quoted: an apostrophe is a letter
        ("don't.wav", True, "don't.wav"),
        (r"C:\Takes\take.wav", False, r"C:\Takes\take.wav"),
        (r'"C:\My Takes\take.wav"', False, r"C:\My Takes\take.wav"),
        (r"& 'C:\My Takes\take.wav'", False, r"C:\My Takes\take.wav"),
    ],
)
def test_a_typed_or_dragged_path_is_read_as_a_shell_reads_it(
    typed: str, posix: bool, expected: str
) -> None:
    assert clean_path(typed, posix=posix) == expected


def test_parse_path_expands_the_home_folder_and_ignores_an_empty_answer() -> None:
    assert parse_path("") is None and parse_path("   ") is None and parse_path("''") is None
    assert parse_path("~/take.wav") == Path.home() / "take.wav"
    if POSIX:
        # No such user: the text stays as it was typed rather than raising. (Windows
        # takes any "~name" for a folder next to the home folder.)
        assert parse_path("~no-such-user-here/take.wav") == Path("~no-such-user-here/take.wav")


@pytest.mark.skipif(not POSIX, reason="a POSIX terminal drops the file")
def test_a_dragged_file_with_an_apostrophe_is_found(tmp_path: Path) -> None:
    take = tmp_path / "it's a take.wav"
    take.write_bytes(b"RIFF")
    dragged = shlex.quote(str(take))  # 'it'"'"'s' for Python; GNOME writes '\''
    gnome = "'" + str(take).replace("'", "'\\''") + "'"
    for typed in (dragged, gnome):
        visit = drive(["5", typed, "q"])
        assert visit.runs == [["show", str(take)]], typed
        assert "does not exist" not in visit.text


@pytest.mark.parametrize("what", ["name too long", "nul"])
def test_a_name_the_file_system_refuses_does_not_exist(
    what: str, caplog: pytest.LogCaptureFixture
) -> None:
    typed = "x" * 300 if what == "name too long" else "a\x00b"
    visit = drive(["5", typed, "", "q"])
    assert visit.code == 0 and visit.runs == []
    assert "does not exist; try again, or leave empty to go back." in visit.text
    assert "could not be completed" not in visit.text
    assert "Traceback" not in caplog.text


def test_a_file_name_that_starts_with_a_dash_is_not_taken_for_an_option() -> None:
    """``reverbscope show -take.wav`` is an unknown option to argparse: the menu
    gave the command the name as it was typed and the usage error ended it."""
    assert path_arg(Path("-take.wav")) == os.curdir + os.sep + "-take.wav"
    assert path_arg(Path("take.wav")) == "take.wav"
    assert path_arg(Path("dir/-take.wav")) == str(Path("dir/-take.wav"))
    Path("-take.wav").write_bytes(b"RIFF")
    Path("-session").mkdir()
    (Path("-session") / "project.json").write_text("{}")  # the menu asks for a project
    visit = drive(["5", "-take.wav", "6", "-session", "-session", "n", "7", "-session", "q"])
    dash = os.curdir + os.sep
    assert visit.runs == [
        ["show", f"{dash}-take.wav"],
        ["compare", f"{dash}-session", f"{dash}-session"],
        ["project", "overview", f"{dash}-session"],
    ]
    # The command to copy has a slash for the separator on Windows.
    assert f"reverbscope show {dash.replace(os.sep, '/')}-take.wav" in visit.text
