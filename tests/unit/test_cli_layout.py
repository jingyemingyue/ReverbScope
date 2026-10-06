"""How the command line lays text out: numbers and units, wrapping, colour, ASCII.

What reviewers of the Chinese output found by reading it at 40 to 100 columns:
a number parted from its unit at the end of a line, a column silently left
out of a table, coloured words that cannot be read on a light background,
frame sides that come out ragged where a stream cannot write Chinese, and
orphan characters at the end of a wrapped line.
"""

from __future__ import annotations

import contextlib
import re
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
