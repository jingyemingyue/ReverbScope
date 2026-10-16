"""Narrow terminals and narrow encodings.

Every command, in both languages, from 20 to 100 columns, on a terminal that
writes UTF-8, cp1252 (no Chinese, no ✓) or cp936 (Chinese, no ✓): nothing
crashes, no line is wider than the terminal (a path or a command to copy
apart), the sides of every frame stay on one column, and a number is never
parted from its unit. What a stream cannot write becomes one "?" per display
column, so that the frames and the tables it draws stay straight.
"""

from __future__ import annotations

import io
from itertools import pairwise
from pathlib import Path

import pytest

from reverbscope.cli.console import GLUE, Console, cell_width, strip_ansi, wrap
from reverbscope.cli.interactive import ANSWER_ROOM, Session
from reverbscope.i18n import activate
from tests.terminals import ENCODINGS, Workspace, capture, layouts, menu_screen, problems

LANGS = ("en", "zh_CN")
WIDTHS = (20, 30, 39, 40, 48, 60, 80, 100)


@pytest.mark.parametrize("lang", LANGS)
def test_no_screen_breaks_on_a_narrow_terminal(
    cli_workspace: Workspace, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, lang: str
) -> None:
    """The frames are asked for (``--style boxed``), whatever the width."""
    monkeypatch.chdir(tmp_path)
    for columns in WIDTHS:
        for argv in layouts(cli_workspace):
            text = capture(argv, monkeypatch, columns=columns, lang=lang)
            assert problems(text, columns) == [], (argv, columns)


@pytest.mark.parametrize("lang", LANGS)
def test_no_screen_breaks_in_a_narrow_encoding_or_in_colour(
    cli_workspace: Workspace, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, lang: str
) -> None:
    monkeypatch.chdir(tmp_path)
    some = [
        ("show", cli_workspace.a),
        ("show", str(cli_workspace.demo / "comparison.json")),
        ("compare", cli_workspace.a, cli_workspace.b),
        ("project", "overview", str(cli_workspace.room)),
        ("--backend", "fake", "doctor"),
        ("config",),
        ("profiles", "vocal"),
        ("compare", cli_workspace.a),
        (),
    ]
    for encoding in ENCODINGS[1:]:
        for columns in (20, 39, 80):
            for argv in some:
                text = capture(argv, monkeypatch, columns=columns, lang=lang, encoding=encoding)
                assert problems(text, columns) == [], (argv, columns, encoding)
    for style in ("boxed", "auto"):
        for columns in (20, 48):
            for argv in some:
                text = capture(
                    argv, monkeypatch, columns=columns, lang=lang, color="always", style=style
                )
                assert problems(text, columns, color="always") == [], (argv, columns, style)


@pytest.mark.parametrize("lang", LANGS)
def test_the_comparison_does_not_crash_at_any_width(
    cli_workspace: Workspace, monkeypatch: pytest.MonkeyPatch, lang: str
) -> None:
    """The old preview line ended ``compare`` at about 60 columns with ``max()
    iterable argument is empty``: a table column without a header had no
    widest word."""
    compare = ("compare", cli_workspace.a, cli_workspace.b)
    for columns, style in [(w, "boxed") for w in range(24, 101, 6)] + [
        (20, "plain"),
        (60, "plain"),
    ]:
        text = capture(compare, monkeypatch, columns=columns, lang=lang, style=style)
        assert problems(text, columns) == [], (columns, style)


def test_a_table_column_without_a_header_fits_at_any_width() -> None:
    headers = ["Band", "Baseline", "Candidate", "Δ", "Δ %", ""]
    rows = [["63 Hz", "0.79 s", "0.62 s", "-0.17 s", "-21.5 %", "✓"]] * 3
    for width in range(20, 101):
        console = Console(width=width, boxed=True)
        framed = console.framed_table(headers, rows, align="lrrrrl", wrap_column=0)
        if framed is not None:
            assert {cell_width(line) for line in framed} <= set(range(width + 1)), width
            assert len({cell_width(line) for line in framed}) == 1, width
        assert all(cell_width(line) <= width for line in console.table(headers, rows)), width


# --- A heading, a label or a word wider than the line -----------------------------------------


@pytest.mark.parametrize("boxed", [True, False])
def test_a_heading_wider_than_the_terminal_wraps(boxed: bool) -> None:
    console = Console(width=20, boxed=boxed)
    lines = console.section("Low-frequency resonances", "A note that is long enough to wrap.")
    assert lines[0] == ""
    assert all(cell_width(line) <= 20 for line in lines), lines
    assert " ".join(" ".join(strip_ansi(line).split()) for line in lines[1:3]).startswith(
        "Low-frequency"
    )
    # Where the heading fits, it still sits in its rule across the terminal.
    wide = Console(width=60, boxed=True).section("Low-frequency resonances")
    assert wide[1].startswith("── Low-frequency resonances ─") and cell_width(wide[1]) == 60
    # The rule needs a column to spare after the heading.
    assert Console(width=28, boxed=True).section("Low-frequency resonances")[1].count("─") == 0
    assert Console(width=29, boxed=True).section("Low-frequency resonances")[1].endswith(" ─")


@pytest.mark.parametrize("width", range(20, 40))
def test_a_label_wider_than_the_line_wraps(width: int) -> None:
    console = Console(width=width)
    rows = console.fields([("Default output folder (desktop app)", "not set"), ("Mode", "demo")])
    assert all(cell_width(line) <= width for line in rows), rows
    assert strip_ansi(" ".join(rows)).split().count("not") == 1


@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("columns", range(20, 29))
def test_the_settings_fit_a_terminal_of_any_width(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, lang: str, columns: int
) -> None:
    monkeypatch.setenv("REVERBSCOPE_HOME", str(tmp_path / "home"))
    text = capture(("config",), monkeypatch, columns=columns, lang=lang)
    assert problems(text, columns) == []
    assert "developer-tools" in text


def test_a_hint_in_full_width_brackets_keeps_its_closing_mark() -> None:
    """``（…）。`` was held as one piece without the ``。`` that follows it: the
    mark hung past the margin, two columns beyond the terminal."""
    text = "（条款未对照标准原文核实）。"
    for width in range(24, 40):
        lines = wrap(text, width, first="    ")
        assert all(cell_width(line) <= width for line in lines), (width, lines)
        assert not any(line.strip().startswith("。") for line in lines), (width, lines)
    assert wrap(text, 32, first="    ") == ["    （条款未对照标准原文核实）。"]
    # Where the line holds the hint and its mark, the hint still moves down whole.
    sentence = "各位置的 RT60 在房间内相差 32 %（最大值减最小值，除以平均值）。"
    assert wrap(sentence, 60, first="  ") == [
        "  各位置的 RT60 在房间内相差 32 %",
        "  （最大值减最小值，除以平均值）。",
    ]


def test_a_word_cut_where_it_must_be_keeps_a_number_with_its_unit() -> None:
    """A word longer than the line (what a cp1252 stream makes of Chinese: a run
    of "?") is cut where it must be, but not between ``110`` and ``Hz``."""
    text = "?" * 12 + "110 Hz?? 11.3 dB??"
    for width in range(20, 36):
        lines = wrap(text, width, first="  ")
        assert GLUE not in "".join(lines)
        flat = [" ".join(line.split()) for line in lines]
        for above, below in pairwise(flat):
            assert not (above[-1:].isdigit() and below.split()[0] in ("Hz", "dB")), (width, lines)


# --- The menu on a narrow terminal -------------------------------------------------------------


@pytest.mark.parametrize("lang", LANGS)
def test_the_menu_wraps_its_items_under_their_numbers(lang: str) -> None:
    """A title longer than the line ran past the edge of the terminal."""
    for width in WIDTHS:
        text = menu_screen(lang, boxed=width >= 48, width=width)
        assert problems(text, width) == [], width
        # The numbering is what it was, and a wrapped title hangs under its text.
        assert "\n   1  " in text and "\n  10  " in text and "\n   q  " in text
    narrow = menu_screen("en", boxed=False, width=30).splitlines()
    start = next(i for i, line in enumerate(narrow) if line.startswith("   1  "))
    assert narrow[start : start + 3] == [
        "   1  Try the demo (synthetic",
        "      room, no audio",
        "      interface)",
    ]


def test_a_question_longer_than_the_screen_is_written_in_lines() -> None:
    """The answer was typed after the terminal had wrapped the question, in the
    middle of its text: only the last line is the prompt, and it leaves room."""
    activate("en")
    asked: list[str] = []
    out = io.StringIO()
    session = Session(Console(width=40), lambda prompt: asked.append(prompt) or "", out)
    question = "Sample rate in Hz (44100, 48000, 96000)"
    assert session.ask(question, "48000") == "48000"
    said = out.getvalue().splitlines()
    assert said and all(cell_width(line) + ANSWER_ROOM <= 40 for line in said)
    assert len(asked) == 1 and cell_width(asked[0].rstrip()) + ANSWER_ROOM <= 40
    assert " ".join(" ".join([*said, asked[0]]).split()) == f"{question} [48000]:"
    # A question that fits is the prompt as it always was.
    out = io.StringIO()
    asked.clear()
    session = Session(Console(width=80), lambda prompt: asked.append(prompt) or "", out)
    session.ask("Folder", "x")
    assert asked == ["Folder [x]: "] and out.getvalue() == ""
