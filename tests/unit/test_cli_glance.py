"""The overview as a bordered table with a status word.

On a terminal that draws frames, "At a glance" of an analysis and of a
comparison is a table of three columns (topic, status, result) whose status
cell shows the mark and a word (``✓ 良好``, ``! 提示``, ``! 警告``, ``✗ 问题``,
``i 说明``; ``✓ good``, ``! notice``, ``! warning``, ``✗ problem``, ``i note``;
the warning and the notice are the words of the cards and of the health
section, ``? unsure`` is for a topic the measurement health doubts), so that colour is never
the only signal. Where the frames are off (a pipe, a file, a terminal narrower
than ``use_boxes`` allows, ``--style plain``) the aligned lines of the plain
layout stay exactly as they were.

Every frame line of a report is measured in display columns: Chinese text,
ANSI colour and the ASCII fallback (a classic Windows console, a cp936 or
cp1252 pipe) must keep the sides and the corners of a frame on one column.
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import replace

import pytest

from reverbscope.cli.console import (
    GLUE,
    Console,
    cell_width,
    char_width,
    strip_ansi,
)
from reverbscope.cli.render import (
    REFLECTIONS_NOT_COMPARED,
    at_a_glance,
    comparison_at_a_glance,
    render_analysis,
    render_comparison,
    render_demo,
)
from reverbscope.core.compare import compare
from reverbscope.demo import DemoRun, run_demo
from reverbscope.i18n import activate
from reverbscope.interpretation import interpret, interpret_comparison
from reverbscope.models.result import ClippingCheck

WIDTHS = (48, 60, 80, 100)
LANGS = ("en", "zh_CN")
#: The narrowest console that draws the overview as a table, and the narrowest
#: that gives it a status column as well: its result column is kept 28 columns
#: wide, and an English topic and status are wider than a Chinese one.
TABLE_FROM = {"en": 56, "zh_CN": 48}
STATUS_FROM = {"en": 68, "zh_CN": 56}

#: The ways a stream is drawn: Unicode frames, the same in colour, ASCII frames
#: (a stream that cannot write the box glyphs) and the two legacy Windows code
#: pages, one of which cannot write Chinese at all.
VARIANTS = {
    "unicode": {"unicode": True, "color": False, "encoding": "utf-8"},
    "colour": {"unicode": True, "color": True, "encoding": "utf-8"},
    "ascii": {"unicode": False, "color": False, "encoding": "utf-8"},
    "ascii-colour": {"unicode": False, "color": True, "encoding": "utf-8"},
    "gbk": {"unicode": False, "color": False, "encoding": "gbk"},
    "cp1252": {"unicode": False, "color": False, "encoding": "cp1252"},
}


@pytest.fixture(scope="module")
def demo(tmp_path_factory: pytest.TempPathFactory) -> DemoRun:
    return run_demo(tmp_path_factory.mktemp("glance") / "out")


@pytest.fixture
def language(request: pytest.FixtureRequest) -> Iterator[str]:
    lang: str = getattr(request, "param", "en")
    activate(lang)
    try:
        yield lang
    finally:
        activate("en")


@contextmanager
def _in(lang: str) -> Iterator[None]:
    activate(lang)
    try:
        yield
    finally:
        activate("en")


def _console(width: int, variant: str = "unicode", **kwargs: object) -> Console:
    options: dict[str, object] = {**VARIANTS[variant], "boxed": True, "width": width, **kwargs}
    return Console(**options)  # type: ignore[arg-type]


# --- Measuring frames ----------------------------------------------------------------

#: The lines of a bordered table: its rules and its rows, indented by two.
_RULE = re.compile(r"^  [┌├└+][─\-┬┼┴+]*[┐┤┘+]$")
_ROW = re.compile(r"^  [│|] .* [│|]$")
_SIDES = "│|"


def _positions(line: str, chars: str) -> list[int]:
    found, column = [], 0
    for char in line:
        if char in chars:
            found.append(column)
        column += char_width(char)
    return found


def _tables(text: str) -> list[list[str]]:
    """The bordered tables of ``text``, without colour: their lines."""
    blocks: list[list[str]] = []
    current: list[str] = []
    for raw in text.splitlines():
        line = strip_ansi(raw).replace(GLUE, " ")  # the layout's glue; fit() writes a space
        if _RULE.match(line) or _ROW.match(line):
            current.append(line)
            continue
        if current:
            blocks.append(current)
            current = []
    if current:
        blocks.append(current)
    return blocks


def _check_frames(text: str, width: int, *, tables_expected: bool = True) -> list[list[str]]:
    """Every frame line of ``text`` is as wide as its siblings; returns the tables."""
    lines = [strip_ansi(line) for line in text.splitlines()]
    # The title's panel and the rules through the section headings span the console.
    assert cell_width(lines[0]) == width and cell_width(lines[2]) == width, lines[:3]
    assert lines[0][0] in "╭+" and lines[2][0] in "╰+"
    assert cell_width(lines[1]) == width and lines[1][0] in "│|"
    for line in lines:
        if line.startswith(("── ", "-- ")):
            assert cell_width(line) == width, line
    tables = _tables(text)
    assert bool(tables) or not tables_expected, text
    for table in tables:
        assert len({cell_width(line) for line in table}) == 1, "\n".join(table)
        assert cell_width(table[0]) <= width, "\n".join(table)
        # A "|" is a side in an ASCII frame only: in a Unicode one it may be text (|Δ|).
        ascii_frame = table[0].lstrip().startswith("+")
        junctions, sides = ("+", "|") if ascii_frame else ("┌┬┐├┼┤└┴┘", "│")
        corners = _positions(table[0], junctions)
        for line in table:
            if _RULE.match(line):
                assert _positions(line, junctions) == corners, "\n".join(table)
            else:
                assert _positions(line, sides) == corners, "\n".join(table)
    return tables


def _unframed(text: str) -> Iterator[str]:
    """The lines that must fit the console: all but a path or a command to copy."""
    for line in strip_ansi(text).splitlines():
        if "reverbscope " in line or "/" in line or "\\" in line or "http" in line:
            continue
        yield line


def _reports(demo: DemoRun, console: Console) -> dict[str, str]:
    findings = [interpret(take.result, "vocal") for take in demo.takes]
    first, second = demo.takes[0].result, demo.takes[1].result
    return {
        "demo": render_demo(console, demo, findings, gui_available=True),
        "analysis": render_analysis(console, first, findings[0], "vocal"),
        "second": render_analysis(console, second, findings[1], "vocal"),
        "comparison": render_comparison(
            console, demo.comparison, interpret_comparison(demo.comparison, "vocal"), "vocal"
        ),
    }


# --- Frame lines keep one display width ---------------------------------------------


@pytest.mark.parametrize("language", LANGS, indirect=True)
@pytest.mark.parametrize("variant", sorted(VARIANTS))
@pytest.mark.parametrize("width", WIDTHS)
def test_every_frame_line_has_the_display_width_of_its_siblings(
    demo: DemoRun, language: str, variant: str, width: int
) -> None:
    """Title panel, section rules and the tables, in English and in Chinese,
    with colour, in ASCII and on the two legacy code pages, at four widths."""
    console = _console(width, variant)
    for name, text in _reports(demo, console).items():
        shown = strip_ansi(text)
        if variant == "cp1252":
            shown.encode("cp1252")  # Chinese became "?", one per column
        if variant == "gbk":
            shown.encode("gbk")
            # GBK cannot write the no-break space that holds "0.70 s" together.
            assert not re.search(r"\d\?(s|ms|dB|Hz|kHz|%)\b", shown), name
        if not console.unicode and language == "en":
            # ASCII frames, marks and signs; "°" stays where the stream can write it.
            assert {char for char in shown if not char.isascii()} <= {"°"}, name
        if name in ("demo", "analysis", "second", "comparison"):
            drawn = width >= TABLE_FROM[language]
            tables = _check_frames(text, width, tables_expected=drawn)
            # The overviews are the tables that span the console: three in the demo.
            spanning = [t for t in tables if cell_width(t[0]) == width]
            if name == "demo":
                assert len(spanning) == (3 if drawn else 0), name
            if name == "comparison":
                assert bool(spanning) == drawn, name
        for line in _unframed(text):
            assert cell_width(line) <= width, (name, width, line)
        if variant in ("colour", "ascii-colour"):
            assert "\x1b[" in text and "\x1b[0m" in text


@pytest.mark.parametrize("language", LANGS, indirect=True)
@pytest.mark.parametrize("variant", ["unicode", "colour", "ascii", "gbk"])
@pytest.mark.parametrize("width", WIDTHS)
def test_the_overview_table_spans_the_console_whatever_it_holds(
    demo: DemoRun, language: str, variant: str, width: int
) -> None:
    console = _console(width, variant)
    for lines in (
        at_a_glance(console, demo.takes[0].result, interpret(demo.takes[0].result, "vocal")),
        comparison_at_a_glance(console, demo.comparison),
    ):
        text = "\n".join(lines)
        if width < TABLE_FROM[language]:
            assert _tables(text) == [], text  # the aligned lines of every release
            continue
        (table,) = _tables(text)
        assert {cell_width(line) for line in table} == {width}, "\n".join(table)
        if width >= STATUS_FROM[language]:
            # The status column is there, with the word.
            assert len(_positions(table[1], _SIDES)) == 4


def test_the_wide_cp1252_pipe_keeps_chinese_frames_straight(demo: DemoRun) -> None:
    """A cp1252 stream replaces a Chinese character with one "?"; a frame was
    ragged because the character took two columns when the line was laid out."""
    activate("zh_CN")
    try:
        console = _console(80, "cp1252")
        text = render_demo(
            console,
            demo,
            [interpret(take.result, "vocal") for take in demo.takes],
            gui_available=True,
        )
    finally:
        activate("en")
    lines = text.splitlines()
    assert {cell_width(line) for line in lines[:3]} == {80}
    assert "?" in lines[1] and "演示" not in text
    assert all(cell_width(line) == 80 for line in lines if line.startswith("-- "))


# --- The words ----------------------------------------------------------------------


def _table(lines: Sequence[str]) -> list[str]:
    """The one bordered table in ``lines``: top rule, header, rule, rows, bottom rule."""
    (table,) = _tables("\n".join(lines))
    return table


def _cells(row: str) -> list[str]:
    return [cell.strip() for cell in row.strip().strip("│").split("│")]


def test_the_overview_of_an_analysis_has_a_status_word_in_chinese(demo: DemoRun) -> None:
    """The owner's mock: item | status | result, the mark and the word in the
    status cell."""
    first = demo.takes[0].result
    with _in("zh_CN"):
        table = _table(at_a_glance(_console(100), first, interpret(first, "vocal")))
    assert table[1].startswith("  │ 方面     │ 状态   │ 结果")
    rows = {_cells(row)[0]: row for row in table[3:-1]}
    assert rows["混响"].startswith("  │ 混响     │ ! 提示 │ RT60 0.70 s（T30） · EDT 0.45 s")
    assert rows["清晰度"].startswith(
        "  │ 清晰度   │ ✓ 良好 │ C50 +9.8 dB · C80 +12.9 dB · D50 91 %"
    )
    assert {_cells(row)[1] for row in table[3:-1]} == {"! 提示", "! 警告", "✓ 良好"}
    assert {cell_width(line) for line in table} == {100}


def test_the_overview_of_an_analysis_has_a_status_word_in_english(demo: DemoRun) -> None:
    first = demo.takes[0].result
    table = _table(at_a_glance(_console(100), first, interpret(first, "vocal")))
    assert _cells(table[1]) == ["Topic", "Status", "Result"]
    rows = {_cells(row)[0]: _cells(row)[1] for row in table[3:-1]}
    assert rows["Reverberation"] == "! notice" and rows["Clarity"] == "✓ good"
    assert rows["Noise floor"] == "! warning"  # mains hum, a warning in its card too
    assert rows["Data quality"] == "✓ good"


def test_a_mark_has_the_word_its_card_and_the_health_section_use(demo: DemoRun) -> None:
    """``!`` was ``注意`` in the overview, ``警告`` in the health section and ``提示``
    in the card of the same finding: three words for one mark."""
    first = demo.takes[0].result
    findings = interpret(first, "vocal")
    severities = {(str(f.topic), str(f.severity)) for f in findings}
    assert ("reverberation", "notice") in severities and ("noise", "warning") in severities
    for lang, notice, warning in (("en", "notice", "warning"), ("zh_CN", "提示", "警告")):
        with _in(lang):
            glance = at_a_glance(_console(100), first, findings)
            cards = "\n".join(render_analysis(_console(100), first, findings, "vocal").splitlines())
        words = {_cells(row)[0]: _cells(row)[1] for row in _table(glance)[3:-1]}
        assert notice in words[next(k for k in words if k in ("Reverberation", "混响"))]
        assert warning in words[next(k for k in words if k in ("Noise floor", "本底噪声"))]
        # The same words open the cards of the report.
        assert f"! {notice.capitalize()} ·" in cards or f"! {notice} ·" in cards
        assert f"! {warning.capitalize()} ·" in cards or f"! {warning} ·" in cards


def test_a_problem_and_a_note_have_their_words_in_the_overview(demo: DemoRun) -> None:
    clipping = ClippingCheck(peak_dbfs=0.0, runs=3, samples=40, clipped=True)
    clipped = replace(demo.takes[0].result, clipping=clipping)
    table = _table(at_a_glance(_console(100), clipped, ()))
    assert {_cells(row)[0]: _cells(row)[1] for row in table[3:-1]}["Data quality"] == "✗ problem"
    with _in("zh_CN"):
        table = _table(at_a_glance(_console(100), clipped, ()))
    assert {_cells(row)[0]: _cells(row)[1] for row in table[3:-1]}["数据质量"] == "✗ 问题"


def test_the_comparison_overview_says_whether_a_topic_was_compared(demo: DemoRun) -> None:
    with _in("zh_CN"):
        table = _table(comparison_at_a_glance(_console(100), demo.comparison))
    assert table[1].startswith("  │ 方面     │ 状态     │ 结果")
    assert table[3].startswith("  │ 混响     │ ✓ 已对比 │ RT60 0.70 s → 0.51 s（-27.3 %）")
    english = _table(comparison_at_a_glance(_console(100), demo.comparison))
    assert english[3].startswith("  │ Reverberation      │ ✓ compared │ RT60 0.70 s → 0.51 s")
    # Whether a change is good is not what the column says.
    assert {_cells(row)[1] for row in english[3:-1]} == {"✓ compared"}


def test_a_topic_that_was_not_compared_says_so_in_the_status(demo: DemoRun) -> None:
    one_sided = replace(
        demo.comparison,
        reflections=(),
        notes=(REFLECTIONS_NOT_COMPARED + " both sides have high direct-sound confidence",),
    )
    table = _table(comparison_at_a_glance(_console(100), one_sided))
    row = next(row for row in table if "Early reflections" in row)
    assert _cells(row)[1] == "– not compared"
    assert _cells(row)[2].startswith("not compared: the direct-sound confidence")
    with _in("zh_CN"):
        table = _table(comparison_at_a_glance(_console(100), one_sided))
    row = next(row for row in table if "早期反射" in row)
    assert _cells(row)[1] == "– 未对比"


# --- A topic the measurement health puts in doubt --------------------------------------


def _statuses(lines: Sequence[str]) -> dict[str, str]:
    return {_cells(row)[0]: _cells(row)[1] for row in _table(lines)[3:-1] if _cells(row)[0]}


def test_a_topic_a_health_check_puts_in_doubt_is_unsure_not_good(demo: DemoRun) -> None:
    """A clipped recording lists clarity under "Affects" in the health section;
    the overview next to it said ``✓ good`` for the same topic."""
    first = demo.takes[0].result
    assert _statuses(at_a_glance(_console(100), first, interpret(first, "vocal")))["Clarity"] == (
        "✓ good"
    )
    clipping = ClippingCheck(peak_dbfs=0.0, runs=3, samples=40, clipped=True)
    clipped = replace(first, clipping=clipping)
    findings = interpret(clipped, "vocal")
    assert _statuses(at_a_glance(_console(100), clipped, findings))["Clarity"] == "? unsure"
    with _in("zh_CN"):
        assert _statuses(at_a_glance(_console(100), clipped, findings))["清晰度"] == "? 不确定"
    # A topic that carries its own mark keeps it, and so does the one no check bears on.
    assert _statuses(at_a_glance(_console(100), clipped, findings))["Data quality"] == "✗ problem"
    # Without the status column the mark is the same one.
    narrow = at_a_glance(_console(48), clipped, findings)
    assert any("? C50" in strip_ansi(line) for line in narrow), narrow


def test_the_plain_overview_keeps_its_marks_whatever_the_health_says(demo: DemoRun) -> None:
    """What a pipe or a file receives does not change."""
    clipping = ClippingCheck(peak_dbfs=0.0, runs=3, samples=40, clipped=True)
    clipped = replace(demo.takes[0].result, clipping=clipping)
    plain = at_a_glance(Console(width=100), clipped, interpret(clipped, "vocal"))
    assert any(line.startswith("  Clarity") and "✓ C50" in line for line in plain), plain


def test_a_comparison_with_an_invalid_side_is_unsure_in_every_topic(demo: DemoRun) -> None:
    from reverbscope.interpretation.verdicts import judge_comparison

    clipping = ClippingCheck(peak_dbfs=0.0, runs=3, samples=40, clipped=True)
    clipped = replace(demo.takes[1].result, clipping=clipping)
    first = demo.takes[0].result
    # Judged with the results at hand, as the compare command does.
    verdict = judge_comparison(demo.comparison, baseline=first, candidate=clipped)
    statuses = _statuses(comparison_at_a_glance(_console(100), demo.comparison, verdict))
    assert set(statuses.values()) == {"? unsure"}, statuses
    assert "Frequency response" in statuses
    with _in("zh_CN"):
        zh = _statuses(comparison_at_a_glance(_console(100), demo.comparison, verdict))
    assert set(zh.values()) == {"? 不确定"}, zh
    # From the file alone nothing is known of the results' health.
    alone = _statuses(comparison_at_a_glance(_console(100), demo.comparison))
    assert set(alone.values()) == {"✓ compared"}
    healthy = judge_comparison(demo.comparison, baseline=first, candidate=demo.takes[1].result)
    assert healthy.in_doubt == ()
    assert "in_doubt" not in healthy.to_dict()


# --- Narrow terminals: the table gives way, one thing at a time ------------------------


def test_a_narrow_table_wraps_its_result_column_and_keeps_the_status(demo: DemoRun) -> None:
    with _in("zh_CN"):
        lines = comparison_at_a_glance(_console(56), demo.comparison)
    table = _table(lines)
    assert all(cell_width(line) <= 56 for line in lines)
    assert _cells(table[1])[1] == "状态" and _cells(table[3])[1] == "✓ 已对比"
    # A wrapped row continues under its result; the other cells stay empty.
    assert any(re.match(r"^  │ {10}│ {10}│ \S", line) for line in table), "\n".join(table)


def test_the_status_column_is_left_out_only_when_nothing_else_fits_and_the_table_says_so(
    demo: DemoRun,
) -> None:
    first = demo.takes[0].result
    findings = interpret(first, "vocal")
    # The result column is kept 28 columns wide. English labels are the widest:
    # up to 66 columns the status column goes.
    narrow = at_a_glance(_console(60), first, findings)
    text = "\n".join(strip_ansi(line) for line in narrow)
    assert "Status" not in text and _cells(_table(narrow)[1]) == ["Topic", "Result"]
    assert "The status column is left out: widen the terminal to see it." in " ".join(text.split())
    assert "✓" in text and "!" in text  # the marks stay in front of the results
    assert all(cell_width(line) <= 60 for line in narrow)
    # With room for it: the status column, and no note.
    for width in (68, 80):
        wider = "\n".join(
            strip_ansi(line) for line in at_a_glance(_console(width), first, findings)
        )
        assert "Status" in wider and "left out" not in wider
    # Chinese labels are short: 48 columns hold the table, 56 the status column too.
    with _in("zh_CN"):
        lines = at_a_glance(_console(48), first, findings)
        assert _cells(_table(lines)[1]) == ["方面", "结果"]
        assert "已省略状态列" in "".join(strip_ansi("".join(lines)).split())
        chinese = "\n".join(strip_ansi(line) for line in at_a_glance(_console(56), first, findings))
    assert "状态" in chinese and "已省略" not in chinese


def test_a_terminal_too_narrow_for_a_readable_result_gets_the_aligned_lines(
    demo: DemoRun,
) -> None:
    """A result squeezed into 16 columns wrapped into three or four lines of a few
    words and the table was twice as tall as the lines (and cut words in two):
    below 56 columns in English the overview is the aligned lines it always was."""
    first = demo.takes[0].result
    findings = interpret(first, "vocal")
    for width in (48, 52, 54):
        lines = at_a_glance(_console(width), first, findings)
        assert _tables("\n".join(lines)) == [], width
        assert lines[2].startswith("  Reverberation") and "!" in lines[2]
        assert all(cell_width(line) <= width for line in lines)
    # Where it is drawn, no result column is narrower than 28 columns.
    for width in range(56, 70):
        table = _table(at_a_glance(_console(width), first, findings))
        assert cell_width(table[1].split("│")[-2]) - 2 >= 28, (width, table[1])


def test_a_wrapped_result_keeps_the_colour_of_its_mark_when_the_status_column_is_left_out(
    demo: DemoRun,
) -> None:
    """Colour is only ever on the mark: the mark in front of a result that wraps
    is as coloured as the one in front of a result that fits."""
    first = demo.takes[0].result
    findings = interpret(first, "vocal")
    boxed = at_a_glance(_console(60, "colour"), first, findings)
    table = _table(boxed)
    assert "Status" not in "\n".join(table)
    assert {cell_width(line) for line in table} == {60}
    # Six topics, each one's first line starts its result with a coloured mark.
    coloured = [line for line in boxed if re.search(r"\x1b\[[0-9;]*m[!✓]\x1b\[0m ", line)]
    assert len(coloured) == 6, "\n".join(boxed)


def test_nothing_fits_at_all_and_the_plain_lines_come_back(demo: DemoRun) -> None:
    first = demo.takes[0].result
    findings = interpret(first, "vocal")
    tiny = at_a_glance(_console(30), first, findings)
    assert not any("┌" in line or "│" in line for line in tiny)
    # The fields of the plain layout, under the heading the boxed style draws.
    assert tiny[2:] == at_a_glance(Console(width=30), first, findings)[2:]


def test_the_plain_layout_is_the_lines_it_always_was(demo: DemoRun) -> None:
    """Without frames (a pipe, --style plain, a narrow terminal) the aligned
    lines of the #48 line stay, symbol and no word."""
    first = demo.takes[0].result
    lines = at_a_glance(Console(width=80), first, interpret(first, "vocal"))
    assert lines[:2] == ["", "At a glance"]
    assert lines[2] == "  Reverberation       ! RT60 0.70 s (T30) · EDT 0.45 s"
    assert lines[3] == "  Clarity             ✓ C50 +9.8 dB · C80 +12.9 dB · D50 91 %"
    assert not any("good" in line or "check" in line or "Status" in line for line in lines)
    ascii_lines = at_a_glance(Console(width=80, unicode=False), first, interpret(first, "vocal"))
    assert ascii_lines[2].startswith("  Reverberation       [WARN] RT60 0.70 s (T30) | EDT")


@pytest.fixture(scope="module")
def ungained(demo: DemoRun):  # type: ignore[no-untyped-def]
    """The comparison the command line makes when the input gain is not declared equal."""
    first, second = (take.result for take in demo.takes)
    return compare(first, second)


def test_the_advice_to_declare_the_gain_is_a_line_of_its_own_under_the_table(ungained) -> None:  # type: ignore[no-untyped-def]
    """A flag to copy does not belong inside a bordered cell."""
    boxed = comparison_at_a_glance(_console(100), ungained)
    table = _table(boxed)
    noise = next(row for row in table if "Noise floor" in row)
    # The result says "not compared: unreliable"; the status says the same.
    assert _cells(noise)[1] == "? not compared"
    assert "not compared:" in _cells(noise)[2]
    assert not any("--same-input-gain" in row for row in table)
    assert strip_ansi(boxed[-1]).strip() == (
        "i add --same-input-gain if the input gain was unchanged"
    )
    # Without frames it stays in the line, as it was.
    plain = comparison_at_a_glance(Console(width=100), ungained)
    flat = " ".join(" ".join(plain).split())
    assert "· add --same-input-gain if the input gain was unchanged" in flat
    assert not any(line.strip().startswith("i add --same") for line in plain)


def test_the_delta_table_says_when_it_leaves_out_its_percentage(demo: DemoRun) -> None:
    sentence = "Δ % is left out: widen the terminal to see it."

    def report(width: int, boxed: bool) -> str:
        console = Console(width=width, boxed=boxed)
        return " ".join(render_comparison(console, demo.comparison, (), "vocal").split())

    dropped = []
    for width in range(48, 101, 4):
        text = report(width, True)
        has_column = "Δ %" in text.replace(sentence, "")
        # The column is there, or the line under the table says it is not.
        assert has_column != (sentence in text), width
        dropped.append(not has_column)
    assert dropped[0] and not dropped[-1]
    # Without frames the layout is as it was: the column goes, nothing is said.
    assert all(sentence not in report(width, False) for width in (48, 56, 64, 100))
    with _in("zh_CN"):
        assert "已省略 Δ %；把终端调宽即可看到。" in " ".join(report(48, True).split())


def test_pipes_get_no_frames_and_no_status_column(
    demo: DemoRun, capsys: pytest.CaptureFixture[str]
) -> None:
    from reverbscope.cli.main import main

    assert main(["--color", "never", "show", str(demo.takes[0].session_dir)]) == 0
    piped = capsys.readouterr().out
    assert "At a glance" in piped and not any(glyph in piped for glyph in "┌│╭")
    assert "Status" not in piped


def test_a_clipped_recording_has_one_error_glyph_on_a_framed_screen(demo: DemoRun) -> None:
    """The table said ``✗ problem`` and the health section under it ``× invalid``."""
    clipping = ClippingCheck(peak_dbfs=0.0, runs=3, samples=40, clipped=True)
    clipped = replace(demo.takes[0].result, clipping=clipping)
    findings = interpret(clipped, "vocal")
    for lang in LANGS:
        with _in(lang):
            boxed = render_analysis(_console(80), clipped, findings, "vocal")
            plain = render_analysis(Console(width=80), clipped, findings, "vocal")
        marks = {line.lstrip()[:1] for line in boxed.splitlines()} & {"✗", "×"}
        assert marks == {"✗"} and "×" not in boxed, (lang, marks)
        # Without frames the lines are the ones they were.
        assert "× " in plain and "✗" not in plain
