"""Panels, bordered tables and the terminal style (``ROOMSCOPE_CLI_STYLE``).

Every line of a frame has the same display width (CJK text, colour and the
ASCII forms included), a frame that cannot hold its text gives way to the
unframed layout, the desktop app's report text has no frames, the style is
chosen by ROOMSCOPE_CLI_STYLE, then a stored choice, then ``boxed``, and
the JSON output does not depend on it.
"""

from __future__ import annotations

import io
import json
from collections.abc import Iterator
from pathlib import Path

import pytest

from roomscope.cli.console import (
    FRAME_MIN_WIDTH,
    Console,
    Verbatim,
    cell_width,
    cli_style,
    strip_ansi,
)
from roomscope.cli.main import main
from roomscope.i18n import activate
from tests.frames import FRAME_GLYPHS, words

CONSOLES = {
    "unicode": Console(width=60, frames=True),
    "colour": Console(width=60, frames=True, color=True),
    "ascii": Console(width=60, frames=True, unicode=False, encoding="cp1252"),
    "narrow": Console(width=40, frames=True),
}


def _same_width(lines: list[str], width: int | None = None) -> None:
    widths = {cell_width(line) for line in lines}
    assert len(widths) == 1, "\n".join(lines)
    if width is not None:
        assert widths == {width}, "\n".join(lines)


@pytest.fixture
def zh() -> Iterator[None]:
    activate("zh_CN")
    yield
    activate("en")


# --- Panels -------------------------------------------------------------------------------


@pytest.mark.parametrize("name", list(CONSOLES))
def test_a_title_panel_holds_the_facts_and_lines_up(zh: None, name: str) -> None:
    c = CONSOLES[name]
    lines = c.title(
        "RoomScope 分析报告",
        [("会话", "position-a"), ("采样率", "48 kHz"), ("创建时间", "2026-10-05 14:10 +00:00")],
    )
    _same_width(lines, c.width)
    # What cp1252 cannot write is one "?" per column, so the sides stay straight.
    title = "RoomScope 分析报告" if c.unicode else "RoomScope " + "?" * 8
    assert title in strip_ansi(lines[0])
    assert len(lines) == 5  # top, three facts, bottom
    top = strip_ansi(lines[0])
    assert top.startswith("╭─ " if c.unicode else "+- ") and top.endswith("╮" if c.unicode else "+")


def test_a_panel_wraps_chinese_inside_its_border(zh: None) -> None:
    c = Console(width=44, frames=True)
    text = "直达声后约 2 ms 有一条强早期反射（-3.1 dB）。近距离人声会被这样早的反射染色。"
    lines = c.panel("! 提示 · 早期反射", c.inner().paragraph(text, indent=0), "warn")
    _same_width(lines, 44)
    assert len(lines) > 3
    assert words("\n".join(lines)).replace(" ", "") == ("! 提示 · 早期反射" + text).replace(" ", "")


def test_a_path_too_long_for_the_panel_follows_it_bare() -> None:
    """A path is never cut or wrapped, and it is a thing to copy: the panel
    holds the other facts and the path follows under the same labels."""
    c = Console(width=50, frames=True)
    path = Verbatim("/a/very/long/path/that/does/not/fit/in/a/panel/of/fifty/columns")
    lines = c.title("RoomScope analysis", [("Session", path), ("Sample rate", "48 kHz")])
    assert lines[-1] == "  Session      " + path  # under the labels of the panel
    panel = lines[:-1]
    _same_width(panel, 50)
    assert "Sample rate  48 kHz" in "\n".join(panel) and path not in "\n".join(panel)
    # Nothing else to show: the title alone is in the panel.
    only = c.title("RoomScope analysis", [("Session", path)])
    assert only[0].startswith("╭") and only[-1] == "  Session  " + path
    _same_width(only[:-1], 50)
    # A body too wide for the panel (a path inside a sentence): no panel.
    unframed = c.title("RoomScope", body=lambda inner, _indent: [inner.paragraph(path)[0]])
    assert not set("".join(unframed)) & set("╭│╰")
    assert c.frame("x" * 45, ["text"]) is None  # a title is never cut either


def test_a_title_with_nothing_under_it_is_a_titled_border_not_a_box_round_a_word() -> None:
    lines = Console(width=50, frames=True).title("Audio systems (host APIs)")
    assert len(lines) == 2
    assert lines[0].startswith("╭─ Audio systems (host APIs) ─") and lines[1].startswith("╰")
    _same_width(lines, 50)


def test_without_frames_a_title_is_the_unframed_heading() -> None:
    c = Console(width=60)
    assert c.title("RoomScope analysis", [("Sample rate", "48 kHz")]) == [
        "RoomScope analysis",
        "──────────────────",
        "",
        "  Sample rate  48 kHz",
    ]


def test_frames_need_forty_columns() -> None:
    assert not Console(width=FRAME_MIN_WIDTH - 1, frames=True).boxed
    assert Console(width=FRAME_MIN_WIDTH, frames=True).boxed
    stream = io.StringIO()
    assert not Console.for_stream(stream, environ={"COLUMNS": "39"}).frames
    assert Console.for_stream(stream, environ={"COLUMNS": "40"}).frames


# --- Tables -------------------------------------------------------------------------------


@pytest.mark.parametrize("name", list(CONSOLES))
def test_a_table_has_a_heavier_header_and_lines_up(zh: None, name: str) -> None:
    c = CONSOLES[name]
    lines = c.table(
        ["项目", "状态", "结果"],
        [
            ["混响", c.badge("warn"), "RT60 0.70 s · EDT 0.45 s"],
            ["清晰度", c.badge("ok"), c.muted("C50 +9.8 dB")],
        ],
        wrap_column=2,
        expand=True,
    )
    _same_width(lines, c.width)
    first, rule = strip_ansi(lines[0]), strip_ansi(lines[2])
    if c.unicode:
        assert first[0] + first[-1] == "┏┓" and rule[0] + rule[-1] == "┡┩"
        assert strip_ansi(lines[-1])[0] == "└" and "┃ 项目" in strip_ansi(lines[1])
    else:
        assert set(first) == {"+", "="} and set(rule) == {"+", "="}
        assert set(strip_ansi(lines[-1])) == {"+", "-"}
        assert strip_ansi(lines[3]).count("|") == 4  # the sides only: "·" is "/" here


def test_a_wrapping_column_keeps_every_line_the_same_width(zh: None) -> None:
    c = Console(width=48, frames=True)
    long = "最强 -3.1 dB，位于 2.4 ms · 2 个高于 -20 dB · 可能的共振：110 Hz (+11.3 dB)"
    lines = c.table(["项目", "状态", "结果"], [["早期反射", c.badge("warn"), long]], wrap_column=2)
    _same_width(lines, 48)
    assert len(lines) > 5  # the result went over several lines
    assert words("\n".join(lines[3:-1])).replace(" ", "").endswith("(+11.3dB)")


def test_a_wide_header_goes_on_two_lines_before_the_table_gives_up() -> None:
    c = Console(width=60, frames=True)
    headers = ["Band", "EDT", "T20", "T30", "RT60", "Decay range"]
    rows = [["Broadband", "0.45 s", "0.64 s", "0.70 s", "0.70 s", "109.3 dB"]]
    lines = c.table(headers, rows, align="lrrrrr")
    _same_width(lines, 60)
    assert "Decay" in lines[1] and "range" in lines[2]


def test_a_column_without_a_header_does_not_stop_a_table_that_is_too_wide() -> None:
    """The comparison's status column has no header: narrowing the headers of the
    others to fit the width crashed on it (``max()`` of nothing)."""
    c = Console(width=70, frames=True)
    headers = ["Band", "Metric", "Baseline value", "Candidate value", "Delta", "Change", ""]
    rows = [["Broadband", "RT60", "0.511", "0.703", "+0.192", "+37.5 %", c.mark("ok")]]
    lines = c.table(headers, rows, align="llrrrrl")
    assert lines[0].startswith("┏")
    _same_width(lines)
    assert cell_width(lines[0]) <= 70
    assert "Baseline" in lines[1] and "value" in lines[2]  # the wide headers took two lines


def test_a_table_that_cannot_fit_falls_back_to_blocks() -> None:
    c = Console(width=40, frames=True)
    rows = [["0", "A device with a rather long name", "Windows WASAPI", "48 kHz"]]
    lines = c.table(["#", "Device", "Host API", "Rate"], rows, title_columns=2)
    assert not set("".join(lines)) & set(FRAME_GLYPHS)
    assert lines[0].strip() == "0 A device with a rather long name"


def test_a_grid_holds_label_and_value_pairs() -> None:
    c = Console(width=60, frames=True, color=True)
    lines = c.grid([("Level", "-69.2 dBFS RMS · peak -65.8 dBFS"), ("Segment", "pre-sweep")])
    _same_width(lines)
    assert strip_ansi(lines[0]).startswith("┌") and strip_ansi(lines[-1]).startswith("└")
    assert Console(width=60).grid([("Level", "x")]) == Console(width=60).fields([("Level", "x")])


def test_ascii_frames_never_show_a_bar_inside_a_cell() -> None:
    """``|`` is the side of an ASCII frame: a separator is ``/`` there."""
    c = CONSOLES["ascii"]
    lines = c.grid([("Level", f"-69.2 dBFS RMS{c.sep()}peak · -65.8 dBFS")])
    assert lines[1] == "| Level | -69.2 dBFS RMS / peak / -65.8 dBFS |"
    assert Console(unicode=False).sep() == " | "  # unchanged without frames


# --- Sections, badges, errors ---------------------------------------------------------------


def test_sections_start_with_a_bar() -> None:
    assert Console(frames=True).section("Reverberation", "to 60 dB") == [
        "",
        "▌Reverberation  to 60 dB",
    ]
    assert Console(frames=True, unicode=False).section("Noise")[1] == "> Noise"
    assert Console().section("Noise")[1] == "Noise"


def test_badges_carry_a_mark_and_a_word(zh: None) -> None:
    c = Console(frames=True)
    assert [c.badge(kind) for kind in ("ok", "warn", "error", "info")] == [
        "✓ 良好",
        "! 注意",
        "✗ 问题",
        "i 说明",
    ]
    activate("en")
    assert [c.badge(kind) for kind in ("ok", "warn", "error", "info", "skip", "unsure")] == [
        "✓ good",
        "! check",
        "✗ problem",
        "i note",
        "– no data",
        "? unsure",
    ]
    ascii_console = Console(frames=True, unicode=False)
    assert ascii_console.badge("ok") == "+ good" and ascii_console.badge("error") == "x problem"
    # Only the mark is coloured; the word stays bold in the colour of the text.
    assert (
        Console(frames=True, color=True).badge("warn") == "\x1b[33;1m!\x1b[0m \x1b[1mcheck\x1b[0m"
    )


def test_an_error_is_a_red_panel_and_its_hints_stay_bare(zh: None) -> None:
    from roomscope.cli.render import render_error

    c = Console(width=60, frames=True)
    text = render_error(
        c,
        "找不到音频文件：take.wav",
        detail="没有播放任何声音。",
        hints=["roomscope analyze --help"],
    )
    lines = text.splitlines()
    assert lines[0].startswith("╭─ ✗ 错误 ")
    _same_width(lines[:4], 60)
    assert lines[-1] == "    roomscope analyze --help"


# --- The style: ROOMSCOPE_CLI_STYLE, then a stored choice, then boxed -----------------------


def test_the_style_is_the_variable_then_the_setting_then_boxed() -> None:
    assert cli_style("", {}) == "boxed"
    assert cli_style("plain", {}) == "plain"
    assert cli_style("plain", {"ROOMSCOPE_CLI_STYLE": "boxed"}) == "boxed"
    assert cli_style("", {"ROOMSCOPE_CLI_STYLE": " Plain "}) == "plain"
    assert cli_style("plain", {"ROOMSCOPE_CLI_STYLE": "fancy"}) == "plain"  # unknown: passed over
    stream = io.StringIO()
    assert Console.for_stream(stream, environ={}).frames
    assert not Console.for_stream(stream, environ={}, style="plain").frames
    assert not Console.for_stream(stream, environ={"ROOMSCOPE_CLI_STYLE": "plain"}).frames


def _run(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, str, str]:
    capsys.readouterr()
    try:
        code = main(list(argv))
    except SystemExit as exc:
        code = int(exc.code or 0)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


# --- What the style never changes ------------------------------------------------------------


@pytest.fixture
def demo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> Path:
    monkeypatch.chdir(tmp_path)
    assert _run(capsys, "demo")[0] == 0
    return tmp_path / "roomscope-demo"


def test_json_output_does_not_depend_on_the_style(
    demo: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    runs = (
        ["show", "roomscope-demo/position-a"],
        ["compare", "roomscope-demo/position-a", "roomscope-demo/position-b"],
        ["show", "roomscope-demo/comparison.json"],
        ["--backend", "fake", "devices"],
        ["--backend", "fake", "doctor"],
        ["config"],
    )
    for argv in runs:
        shown = {}
        for style in ("boxed", "plain"):
            monkeypatch.setenv("ROOMSCOPE_CLI_STYLE", style)
            code, out, _err = _run(capsys, "--format", "json", *argv)
            assert code == 0, argv
            shown[style] = out
        assert shown["boxed"] == shown["plain"], argv
        json.loads(shown["boxed"])


def test_the_desktop_reports_have_no_frames(demo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The GUI's report panes and roomscope.cli.report: the unframed layout,
    whatever the style of the command line."""
    from roomscope.cli.render import REPORT_CONSOLE, render_analysis, render_comparison
    from roomscope.cli.report import format_comparison_report, format_report
    from roomscope.interpretation import interpret
    from roomscope.io.session_store import load_comparison, load_measurement

    monkeypatch.setenv("ROOMSCOPE_CLI_STYLE", "boxed")
    measurement = load_measurement(demo / "position-a")
    findings = interpret(measurement.result, "vocal")
    comparison = load_comparison(demo / "comparison.json")
    unframed = Console(color=False, unicode=True, width=96)
    assert not REPORT_CONSOLE.frames
    texts = [
        render_analysis(REPORT_CONSOLE, measurement.result, findings, "vocal"),
        render_comparison(REPORT_CONSOLE, comparison, (), "vocal"),
        format_report(measurement.result, findings, "vocal"),
        format_comparison_report(comparison),
    ]
    assert texts[0] == render_analysis(unframed, measurement.result, findings, "vocal")
    for text in texts:
        assert not set(text) & (set(FRAME_GLYPHS) - {"─"})
        assert "✗" not in text


class _Tty(io.StringIO):
    def isatty(self) -> bool:
        return True


def test_the_session_list_is_a_table_on_a_terminal_and_tab_separated_in_a_pipe(
    demo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scripts read ``show --list`` from a pipe: one ``path<TAB>label`` line
    per session there, whatever the style."""
    import sys

    from tests.frames import frame_blocks

    monkeypatch.setenv("COLUMNS", "100")
    monkeypatch.setenv("NO_COLOR", "1")
    terminal = _Tty()
    monkeypatch.setattr(sys, "stdout", terminal)
    assert main(["show", "--list", "roomscope-demo"]) == 0
    shown = terminal.getvalue()
    assert "Saved sessions" in shown and "┏" in shown and "\t" not in shown
    assert "roomscope-demo/position-a" in shown and "Synthetic demo room" in shown
    for block in frame_blocks(shown):
        _same_width(block)
    pipe = io.StringIO()
    monkeypatch.setattr(sys, "stdout", pipe)
    assert main(["show", "--list", "roomscope-demo"]) == 0
    lines = pipe.getvalue().splitlines()
    assert len(lines) == 2 and all(line.count("\t") == 1 for line in lines)
    assert all(" · " in line for line in lines)


def test_a_project_is_shown_under_its_name(
    demo: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from tests.frames import frame_blocks

    monkeypatch.setenv("COLUMNS", "100")
    assert _run(capsys, "project", "init", "--out", "booth", "--name", "Booth A")[0] == 0
    for label in ("a", "b"):
        argv = ["project", "add", "booth", f"roomscope-demo/position-{label}", "--position", label]
        assert _run(capsys, *argv)[0] == 0
    code, out, _err = _run(capsys, "project", "show", "booth")
    assert code == 0
    assert "Booth A" in out.splitlines()[1] and out.startswith("╭")
    assert str(demo / "position-b") in out  # a path is never cut
    for block in frame_blocks(out):
        _same_width(block)
    monkeypatch.setenv("ROOMSCOPE_CLI_STYLE", "plain")
    _code, out, _err = _run(capsys, "project", "show", "booth")
    assert out.splitlines()[0] == "Booth A" and out.splitlines()[1].startswith("  a\t")
    # A project without sessions is its panel alone, not a table with no rows.
    monkeypatch.setenv("ROOMSCOPE_CLI_STYLE", "boxed")
    assert _run(capsys, "project", "init", "--out", "empty", "--name", "Empty")[0] == 0
    _code, out, _err = _run(capsys, "project", "show", "empty")
    assert len(out.splitlines()) == 2 and "Empty" in out.splitlines()[0]
