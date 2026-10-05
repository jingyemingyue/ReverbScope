"""Panels, bordered tables, section bars and badges (``Console.frames``).

Every line of a frame has the same display width (CJK text, colour and the
ASCII forms included), a frame that cannot hold its text gives way to the
unframed layout, and without frames the text is laid out as before.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from roomscope.cli.console import (
    FRAME_MIN_WIDTH,
    Console,
    Verbatim,
    cell_width,
    strip_ansi,
)
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
    assert "RoomScope 分析报告" in strip_ansi(lines[0])
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


def test_a_panel_without_room_for_a_path_is_not_drawn() -> None:
    """A path is never cut: the text is laid out without the frame."""
    c = Console(width=50, frames=True)
    path = Verbatim("/a/very/long/path/that/does/not/fit/in/a/panel/of/fifty/columns")
    lines = c.title("RoomScope analysis", [("Session", path)])
    assert not set("".join(lines)) & set("╭│╰")
    assert path in "\n".join(lines)
    assert c.frame("x" * 45, ["text"]) is None  # nor is a title


def test_a_title_with_nothing_under_it_is_inside_its_panel() -> None:
    lines = Console(width=50, frames=True).title("Audio systems (host APIs)")
    assert len(lines) == 3 and "Audio systems (host APIs)" in lines[1]
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
    assert not Console(width=100).boxed


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


# --- Sections and badges ------------------------------------------------------------------


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
    assert Console(frames=True, color=True).badge("warn") == "\x1b[33;1m! check\x1b[0m"
