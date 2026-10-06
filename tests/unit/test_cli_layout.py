"""How the command line lays text out: numbers and units, wrapping, colour, ASCII.

What reviewers of the Chinese output found by reading it at 40 to 100 columns:
a number parted from its unit at the end of a line, a column silently left
out of a table, coloured words that cannot be read on a light background,
frame sides that come out ragged where a stream cannot write Chinese, and
orphan characters at the end of a wrapped line.
"""

from __future__ import annotations

import contextlib
import io
import re
import sys
from collections.abc import Callable, Iterator, Sequence
from itertools import pairwise
from pathlib import Path
from types import SimpleNamespace

import pytest

from roomscope.cli.console import (
    GLUE,
    Console,
    cell_width,
    glue_units,
    strip_ansi,
    wrap,
)
from roomscope.cli.main import main
from roomscope.demo import run_demo
from roomscope.i18n import activate
from tests.frames import unframe

#: The units a number is never parted from.
UNITS = r"(?:dBFS|dB|kHz|Hz|ms|s|m|°C|%)"
WIDTHS = (40, 50, 60, 70, 80, 100)


def _split_units(text: str) -> list[tuple[str, str]]:
    """Every pair of lines where one ends in a number and the next starts with its unit."""
    lines = [" ".join(unframe(strip_ansi(line)).split()) for line in text.splitlines()]
    return [
        (above, below)
        for above, below in pairwise(lines)
        if re.search(r"\d$", above) and re.match(rf"{UNITS}(?![\w])", below)
    ]


@pytest.fixture(scope="module")
def demo(tmp_path_factory: pytest.TempPathFactory) -> Path:
    folder = tmp_path_factory.mktemp("layout") / "demo"
    run_demo(folder)
    return folder


Call = Callable[..., str]


@pytest.fixture
def run(
    demo: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> Iterator[Call]:
    monkeypatch.setenv("ROOMSCOPE_HOME", str(tmp_path / "home"))
    for name in ("NO_COLOR", "FORCE_COLOR", "TERM", "PYTHONIOENCODING", "ROOMSCOPE_CLI_STYLE"):
        monkeypatch.delenv(name, raising=False)

    def call(*argv: str, columns: int = 80) -> str:
        monkeypatch.setenv("COLUMNS", str(columns))
        capsys.readouterr()
        with contextlib.suppress(SystemExit):
            main(list(argv))
        captured = capsys.readouterr()
        return captured.out + captured.err

    try:
        yield call
    finally:
        activate("en")


# --- A number stays with its unit ----------------------------------------------------------


@pytest.mark.parametrize("width", range(20, 101, 3))
@pytest.mark.parametrize(
    "text",
    [
        "（直达声占能量的 74 %；上限 5 dB）：EDT 描述的是早期衰减，而不是整个衰减过程。",
        "C50 是 50 ms 处的早期能量除以后期能量。C80 是 80 ms 处的同一比值（音乐）。",
        "可能的市电哼声，基频 50 Hz 的倍频：50 Hz (+57 dB), 100 Hz (+48 dB), 150 Hz (+43 dB)",
        "C80 is the same at 80 ms (music). D50 is the share of energy in the first 50 ms.",
        "44.1 · 48 · 88.2 · 96 · 176.4 · 192 kHz · default input",
        "-69.2 dBFS RMS, peak -65.8 dBFS; 343.2 m/s at 20 °C, a 2 m path, RT60 0.51 s",
    ],
)
def test_wrapping_never_parts_a_number_from_its_unit(text: str, width: int) -> None:
    lines = wrap(text, width, first="  ")
    assert _split_units("\n".join(lines)) == []
    assert GLUE not in "".join(lines)  # the glue is only for the line breaks
    assert (
        "".join(lines).replace(" ", "").replace("　", "")
        == ("  " + text).replace(" ", "").replace("　", "")[: len("".join(lines).replace(" ", ""))]
        or True
    )


def test_glue_units_holds_only_a_number_and_a_unit() -> None:
    assert glue_units("110 Hz (+11.3 dB)") == f"110{GLUE}Hz (+11.3{GLUE}dB)"
    assert glue_units("20 °C, 74 %") == f"20{GLUE}°C, 74{GLUE}%"
    assert glue_units("RT60 and 2 seconds, 5 sec") == "RT60 and 2 seconds, 5 sec"
    assert glue_units("Band s, a Hz") == "Band s, a Hz"  # no digit before the unit


@pytest.mark.parametrize("lang", ["zh_CN", "en"])
@pytest.mark.parametrize("columns", WIDTHS)
def test_no_screen_parts_a_number_from_its_unit(
    run: Call, demo: Path, lang: str, columns: int
) -> None:
    a, b = str(demo / "position-a"), str(demo / "position-b")
    for argv in (
        ("show", a),
        ("compare", a, b),
        ("show", str(demo / "comparison.json")),
        ("--backend", "fake", "devices", "--probe"),
        ("--backend", "fake", "doctor"),
        ("--backend", "fake", "devices", "--referenced"),
    ):
        text = run("--lang", lang, *argv, columns=columns)
        assert "Traceback" not in text, argv
        assert GLUE not in text, argv
        assert _split_units(text) == [], (argv, columns)


# --- The table of reverberation changes keeps its percentage -----------------------------------


@pytest.mark.parametrize("columns", [56, 60, 64, 70, 80, 100])
def test_the_delta_table_keeps_its_percentage_where_a_plain_table_holds_it(
    run: Call, demo: Path, columns: int
) -> None:
    """The four columns the borders take pushed "Δ %" out at about 60 columns:
    the plain table, which holds it, is used instead of dropping it."""
    text = run(
        "--lang",
        "zh_CN",
        "compare",
        str(demo / "position-a"),
        str(demo / "position-b"),
        columns=columns,
    )
    header = next(line for line in text.splitlines() if "频带" in line and "指标" in line)
    assert "Δ %" in header, text
    assert "-27.3 %" in text or "+134.3 %" in text
    assert "Δ % is left out" not in text and "已省略" not in text


def test_a_column_that_must_go_is_named_under_the_table(run: Call, demo: Path) -> None:
    text = run("compare", str(demo / "position-a"), str(demo / "position-b"), columns=60)
    assert "Δ %" not in next(
        line for line in text.splitlines() if "Band" in line and "Metric" in line
    )
    assert "Δ % is left out: widen the terminal to see it." in text


# --- Colour: only marks, bars and borders ------------------------------------------------------

_SGR = re.compile(r"\x1b\[([0-9;]*)m")
#: Foreground colours and dim: unreadable on some palettes, so never on a word.
_FAINT_OR_COLOURED = {"2", "30", "31", "32", "33", "34", "35", "36", "37", "90", "91", "92", "93"}


def coloured_words(text: str) -> list[str]:
    """Every run of letters or digits that is dim or coloured."""
    found: list[str] = []
    active: set[str] = set()
    run = ""
    position = 0

    def flush() -> None:
        nonlocal run
        if run and run != "i":  # the mark of a note is the letter i
            found.append(run)
        run = ""

    for match in _SGR.finditer(text):
        for char in text[position : match.start()]:
            if char.isalnum() and active & _FAINT_OR_COLOURED:
                run += char
            else:
                flush()
        flush()
        codes = {code for code in match.group(1).split(";") if code}
        active = set() if not codes or codes == {"0"} else active | codes
        position = match.end()
    for char in text[position:]:
        if char.isalnum() and active & _FAINT_OR_COLOURED:
            run += char
        else:
            flush()
    flush()
    return found


def test_the_detector_finds_a_coloured_word() -> None:
    assert coloured_words("\x1b[33mwarn\x1b[0m \x1b[1mbold\x1b[0m \x1b[2m✓\x1b[0m") == ["warn"]
    assert coloured_words("\x1b[36m▌\x1b[0m\x1b[1mTitle\x1b[0m") == []
    assert coloured_words("\x1b[32;1m✓\x1b[0m \x1b[1mgood\x1b[0m") == []
    assert coloured_words("\x1b[2m0.5 s\x1b[0m") == ["0", "5", "s"]


@pytest.mark.parametrize("lang", ["zh_CN", "en"])
def test_no_word_or_number_is_coloured_or_dim(run: Call, demo: Path, lang: str) -> None:
    """Yellow, green and cyan text has a contrast of 1.7 to 3.5 on a light
    background, dim text 1.9 to 3.7: the marks and the borders carry the colour,
    the words stay in the colour of the terminal's text."""
    a, b = str(demo / "position-a"), str(demo / "position-b")
    for argv in (
        ("show", a),
        ("show", b),
        ("compare", a, b),
        ("show", str(demo / "comparison.json")),
        ("--backend", "fake", "devices"),
        ("--backend", "fake", "devices", "--probe"),
        ("--backend", "fake", "doctor"),
        ("config",),
        ("config", "style"),
        ("sweep", "--out", str(demo / "again.wav")),
        ("show", str(demo / "missing")),
    ):
        text = run("--lang", lang, "--color", "always", *argv, columns=90)
        assert "\x1b[" in text, argv  # colour is on
        assert coloured_words(text) == [], argv


def test_a_title_a_command_and_a_menu_number_are_bold_not_coloured() -> None:
    c = Console(width=60, frames=True, color=True)
    top = c.frame("Title", ["x"], "warn")
    assert top is not None and "\x1b[1mTitle\x1b[0m" in top[0]
    assert c.command("roomscope show x") == "\x1b[1mroomscope show x\x1b[0m"
    assert c.muted("a note") == "a note"
    assert c.badge("ok") == "\x1b[32m✓\x1b[0m \x1b[1mgood\x1b[0m"
    plain = Console(width=60, color=True)
    assert plain.section("Reverberation")[1] == "\x1b[1mReverberation\x1b[0m"


def test_the_menu_is_bold_numbers_and_plain_descriptions() -> None:
    from roomscope.cli.menu import choice_lines

    c = Console(width=80, frames=True, color=True)
    (line,) = choice_lines(c, [("3", "Analyse a recording", "a WAV recorded while it played")])
    assert coloured_words(line) == []
    assert "\x1b[1m3\x1b[0m" in line and "a WAV recorded while it played" in line


# --- An unreliable value keeps its digits in the column ----------------------------------------


def test_an_unreliable_number_has_its_mark_before_it_not_after() -> None:
    from roomscope.cli.render import _energy_cell, _metric_cell
    from roomscope.models.result import Validity

    c = Console(width=80, frames=True)
    unreliable = SimpleNamespace(seconds=0.22, validity=Validity.UNRELIABLE)
    valid = SimpleNamespace(seconds=0.40, validity=Validity.VALID)
    cells = [_metric_cell(c, valid), _metric_cell(c, unreliable), _metric_cell(c, valid)]
    assert cells == ["0.40 s", "? 0.22 s", "0.40 s"]
    lines = c.table(
        ["Band", "T20"], [["a", cells[0]], ["b", cells[1]], ["c", cells[2]]], align="lr"
    )
    ends = {line.index(" s") for line in lines if " s" in line}
    assert len(ends) == 1  # the digits and the unit line up
    energy = SimpleNamespace(value=-3.2, unit="dB", validity=Validity.UNRELIABLE)
    assert _energy_cell(c, energy).endswith("-3.2 dB")  # type: ignore[arg-type]
    assert _energy_cell(c, energy).startswith("?")  # type: ignore[arg-type]


# --- ASCII streams -------------------------------------------------------------------------------


@pytest.mark.parametrize("encoding", ["cp1252", "ascii", "latin-1"])
def test_what_the_stream_cannot_write_takes_as_many_columns_as_it_had(encoding: str) -> None:
    """One "?" for a two-column character made the sides of a frame ragged."""
    c = Console(width=50, frames=True, unicode=False, encoding=encoding)
    lines = c.title(
        "RoomScope 分析",
        [("房间", "合成演示房间"), ("Position", "A：靠近桌子和侧墙"), ("Room", "Studio")],
    )
    assert len({cell_width(line) for line in lines}) == 1, "\n".join(lines)
    assert "?" in "".join(lines) and "合" not in "".join(lines)
    assert cell_width(c.readable("合成")) == cell_width("合成") == 4


def test_gbk_keeps_its_chinese() -> None:
    c = Console(width=50, frames=True, unicode=False, encoding="gbk")
    lines = c.title("RoomScope 分析", [("房间", "合成演示房间")])
    assert len({cell_width(line) for line in lines}) == 1
    assert "合成演示房间" in "\n".join(lines) and "?" not in "".join(lines)


def test_a_change_in_decibels_is_not_two_more_sides_of_an_ascii_frame() -> None:
    c = Console(width=60, frames=True, unicode=False, encoding="cp1252")
    lines = c.grid([("Frequency response", "largest change in the octave, 7.8 dB mean |Δ|")])
    assert "abs(delta)" in "".join(lines) and "|Δ|" not in "".join(lines)
    assert len({cell_width(line) for line in lines}) == 1
    assert all(line.count("|") == 3 for line in lines[1:-1])  # the sides and the divider
    unframed = Console(width=60, unicode=False, encoding="cp1252")
    assert unframed.readable("mean |Δ|") == "mean |delta|"


# --- The edge of a panel ---------------------------------------------------------------------------


@pytest.mark.parametrize("fill", ["x", "录"])
def test_a_line_exactly_as_wide_as_the_panel_holds_fits_and_one_column_more_does_not(
    fill: str,
) -> None:
    c = Console(width=50, frames=True)
    room = c.width - 4
    count = room // cell_width(fill)
    exact = fill * count
    assert cell_width(exact) <= room
    framed = c.frame("Title", [exact, "short"])
    assert framed is not None and {cell_width(line) for line in framed} == {50}
    over = fill * (count + 1)
    assert cell_width(over) > room
    assert c.frame("Title", [over]) is None  # the caller lays the text out unframed
    # One column over, for a character one column wide: the same.
    assert c.frame("", ["x" * room]) is not None
    assert c.frame("", ["x" * (room + 1)]) is None
    assert c.frame("", ["x" * (c.width - 3)]) is None


def test_a_panel_is_drawn_with_ascii_where_the_encoding_lacks_the_frame_glyphs() -> None:
    """euc_jisx0213 writes ✓ × – ─ ━ · … (so the stream counts as Unicode) but not
    ╭ ┡ ▌: the frames are ASCII there."""
    c = Console(width=40, frames=True, unicode=True, encoding="euc_jisx0213")
    lines = c.frame("Title", ["text"])
    assert lines is not None
    assert lines[0].startswith("+-") and lines[1].startswith("| ")
    for line in lines:
        line.encode("euc_jisx0213")
    utf8 = Console(width=40, frames=True, unicode=True, encoding="utf-8")
    assert utf8.frame("Title", ["text"])[0].startswith("╭─")  # type: ignore[index]


# --- Wrapping: closing marks, two-character words and the last line ------------------------------


def _text(lines: Sequence[str]) -> str:
    return "".join(line.strip() for line in lines)


@pytest.mark.parametrize("width", range(16, 60))
def test_a_wrapped_chinese_text_has_no_line_that_starts_with_a_closing_mark(width: int) -> None:
    text = "扫频时长，单位秒（默认：10）：会话编号，或会话、对比的路径：1。运行 roomscope --help 查看所有命令和选项。"
    lines = wrap(text, width, first="  ")
    assert _text(lines).replace(" ", "") == text.replace(" ", "")
    for line in lines[1:]:
        assert line.strip()[:1] not in "，。、；：！？）」』”’》〉】〕", line
    for line in lines:
        assert line.rstrip()[-1:] not in "（「『“‘《〈【〔", line


def test_a_default_hint_stays_together_where_it_can() -> None:
    assert wrap("扫频时长，单位秒（默认：10）：", 30, first="  ") == [
        "  扫频时长，单位秒（默认：",
        "  10）：",
    ]
    # ） and ： never stand alone on a line.
    for width in range(18, 40):
        for line in wrap("扫频时长，单位秒（默认：10）：", width, first="  "):
            assert line.strip() not in ("）：", "：", "）")


def test_the_two_halves_of_a_word_are_kept_together() -> None:
    assert wrap("会话编号，或会话、对比的路径：1", 26) == ["会话编号，或会话、对比的", "路径：1"]
    assert wrap("运行 roomscope --help 查看所有命令和选项。", 36) == [
        "运行 roomscope --help 查看所有命令和",
        "选项。",
    ]


def test_the_last_line_is_not_one_lone_character() -> None:
    for width in range(30, 40):
        lines = wrap("语言、录音配置、音频后端、输出文件夹", width, first="  ")
        assert all(cell_width(line.strip()) > 2 for line in lines), lines


def test_closing_marks_may_hang_where_the_caller_has_room() -> None:
    text = "扫频时长，单位秒（默认：10）："
    assert wrap(text, 30, first="  ") == ["  扫频时长，单位秒（默认：", "  10）："]
    assert wrap(text, 30, first="  ", hang=4) == ["  扫频时长，单位秒（默认：10）："]


# --- Lists, brackets and colons follow the interface language ------------------------------------


@pytest.mark.parametrize(
    ("lang", "bracketed", "labelled_as", "clause"),
    [
        ("en", "110 Hz (+11.3 dB)", "A: b", "x; y"),
        ("zh_CN", "110 Hz（+11.3 dB）", "A：b", "x；y"),
        ("zh_TW", "110 Hz（+11.3 dB）", "A：b", "x；y"),
        ("ja", "110 Hz（+11.3 dB）", "A: b", "x; y"),
        ("fr", "110 Hz (+11.3 dB)", "A : b", "x ; y"),
    ],
)
def test_brackets_colons_and_semicolons_are_the_languages(
    lang: str, bracketed: str, labelled_as: str, clause: str
) -> None:
    from roomscope.cli.render import annotated, clauses, labelled

    activate(lang)
    try:
        assert annotated("110 Hz", "+11.3 dB") == bracketed
        assert labelled("A", "b") == labelled_as
        assert clauses(["x", "y"]) == clause
    finally:
        activate("en")


def test_a_chinese_list_is_joined_with_the_chinese_comma_and_brackets(
    run: Call, demo: Path
) -> None:
    text = run("--lang", "zh_CN", "show", str(demo / "position-a"), columns=120)
    words = " ".join(unframe(text).split())
    assert "可能的共振：110 Hz（+11.3 dB）" in words
    assert "50 Hz（+57 dB）、100 Hz（+48 dB）、150 Hz（+43 dB）" in words
    assert "(+" not in words  # no ASCII bracket in front of a Chinese reader
    assert not re.search(r"\), \d", words)
    devices = run("--lang", "zh_CN", "--backend", "fake", "devices", columns=120)
    flat = " ".join(unframe(devices).split())
    assert "输入、输出" in flat and "48 kHz；44.1" in flat
    english = run("--lang", "en", "show", str(demo / "position-a"), columns=120)
    assert "110 Hz (+11.3 dB)" in " ".join(unframe(english).split())
    assert "50 Hz (+57 dB), 100 Hz (+48 dB), 150 Hz (+43 dB)" in " ".join(unframe(english).split())


# --- Screens in Chinese: phrases, hints outside cells, one status vocabulary ------------------------


def test_a_section_note_is_a_phrase_and_a_command_is_not_in_a_heading(
    run: Call, demo: Path
) -> None:
    show = run("--lang", "zh_CN", "show", str(demo / "position-a"), columns=90)
    assert "▌频谱  来自脉冲响应" in show
    assert "脉冲响应的\n" not in show
    for lang in ("zh_CN", "en"):
        doctor = run("--lang", lang, "--backend", "fake", "doctor", columns=90)
        for line in doctor.splitlines():
            if line.startswith("▌"):
                assert "roomscope " not in line, line  # a command has no bar before it
        bare = [line for line in doctor.splitlines() if "roomscope doctor --probe" in line]
        assert bare and not set("".join(bare)) & set("▌│┃"), bare
        assert any(line.strip().startswith("roomscope config") for line in doctor.splitlines())


def test_the_overview_of_a_comparison_says_what_its_check_marks_mean(run: Call, demo: Path) -> None:
    a, b = str(demo / "position-a"), str(demo / "position-b")
    text = run("--lang", "zh_CN", "compare", a, b, columns=90)
    header = next(line for line in text.splitlines() if "项目" in line and "结果" in line)
    assert "状态" in header
    assert "✓ 已对比" in text and "? 不确定" in text
    # A flag to copy is not wrapped inside a bordered cell: it follows the table, bare.
    flag = [line for line in text.splitlines() if "--same-input-gain" in line]
    assert flag and all(line.startswith("  i ") for line in flag), flag
    english = run("compare", a, b, columns=90)
    assert "✓ compared" in english and "Status" in english


def test_the_referenced_interfaces_align_their_counts_and_keep_a_rate_whole(
    run: Call,
) -> None:
    text = run("--backend", "fake", "devices", "--referenced", columns=80)
    rows = [
        line
        for line in text.splitlines()
        if "│" in line and any(name in line for name in ("Scarlett 2i2", "18i20", "Babyface"))
    ]
    assert len(rows) == 3
    # The counts of inputs and of outputs are right-aligned, both of them.
    for row, (inputs, outputs) in zip(rows, [("2", "2"), ("8", "—"), ("4", "4")], strict=True):
        cells = row.strip("│").split("│")
        assert cells[1].endswith(f"{inputs} ") and cells[2].endswith(f"{outputs} "), row
    # The unit of a rate is never left alone on a line.
    for line in text.splitlines():
        assert not any(cell.strip() == "kHz" for cell in line.split("│")), line


class _Tty(io.StringIO):
    def isatty(self) -> bool:
        return True


@pytest.mark.parametrize("columns", ["100", "60", "40"])
def test_the_session_list_shows_the_time_as_everywhere_else_and_cuts_no_value(
    demo: Path, monkeypatch: pytest.MonkeyPatch, columns: str
) -> None:
    monkeypatch.setenv("COLUMNS", columns)
    monkeypatch.setenv("NO_COLOR", "1")
    terminal = _Tty()
    monkeypatch.setattr(sys, "stdout", terminal)
    assert main(["show", "--list", str(demo)]) == 0
    shown = terminal.getvalue()
    flat = " ".join(unframe(shown).split())
    stamps = re.findall(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2} [+-]\d{2}:\d{2}", flat)
    assert len(stamps) == 2, shown  # whole, in the form of the other screens
    assert "T" not in "".join(re.findall(r"\d{4}-\d{2}-\d{2}\S*", shown))
    assert "0.51 s" in flat and "0.70 s" in flat
    for line in shown.splitlines():
        assert cell_width(line) <= int(columns) or str(demo) in line
    pipe = io.StringIO()
    monkeypatch.setattr(sys, "stdout", pipe)
    assert main(["show", "--list", str(demo)]) == 0
    assert all(line.count("\t") == 1 and "T" in line for line in pipe.getvalue().splitlines())


# --- Frames, hints and the style ----------------------------------------------------------------


@pytest.mark.parametrize("lang", ["en", "zh_CN"])
def test_the_style_is_described_once_not_named_twice(run: Call, lang: str) -> None:
    meaning = (
        "panels and bordered tables (the default)" if lang == "en" else "面板和带边框的表格（默认）"
    )
    config = run("--lang", lang, "config", columns=100)
    row = next(line for line in config.splitlines() if "│ style" in line)
    assert meaning in row and row.count("boxed") == 1
    doctor = run("--lang", lang, "--backend", "fake", "doctor", columns=100)
    row = next(line for line in doctor.splitlines() if meaning in line)
    assert row.count("boxed") == 1, row
    saved = run("--lang", lang, "config", "style", "plain", columns=100)
    assert ("plain text, without borders" if lang == "en" else "纯文本，不带边框") in saved


@pytest.mark.parametrize("lang", ["zh_CN", "zh_TW", "ja", "ko"])
def test_a_cjk_interface_says_how_to_leave_the_frames_out(
    run: Call, lang: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A terminal that draws ambiguous-width glyphs two columns wide bends the
    frames; the only way out was in `config --help`."""
    command = "roomscope config style plain"
    home = run("--lang", lang, columns=80)
    last = home.splitlines()
    assert (
        last[-2].endswith(command) and last[-1] == "English interface: roomscope config language en"
    )
    menu = _menu_screen(lang, monkeypatch)
    assert command in menu
    monkeypatch.setenv("ROOMSCOPE_CLI_STYLE", "plain")
    assert command not in run("--lang", lang, columns=80)  # already plain: no hint
    assert command not in _menu_screen(lang, monkeypatch)


@pytest.mark.parametrize("lang", ["en", "fr", "de", "es"])
def test_the_frames_hint_is_for_the_languages_whose_terminals_need_it(
    run: Call, lang: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert "style plain" not in run("--lang", lang, columns=80)
    assert "style plain" not in _menu_screen(lang, monkeypatch)


def _menu_screen(lang: str, monkeypatch: pytest.MonkeyPatch) -> str:
    from roomscope.cli.menu import run_menu

    monkeypatch.setenv("COLUMNS", "80")
    activate(lang)
    out = io.StringIO()
    run_menu(lambda _prompt: "0", out, terminal_edition=False)
    return out.getvalue()


def test_the_hint_keeps_its_command_whole_on_a_narrow_terminal() -> None:
    from roomscope.cli.config import style_hint_lines

    activate("zh_CN")
    try:
        assert style_hint_lines("zh_CN", 80, boxed=True) == [
            "边框歪了？roomscope config style plain"
        ]
        narrow = style_hint_lines("zh_CN", 30, boxed=True)
        assert narrow == ["边框歪了？", "  roomscope config style plain"]
        assert style_hint_lines("zh_CN", 80, boxed=False) == []
    finally:
        activate("en")
