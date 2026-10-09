"""The progress bar.

While a take plays, the progress line on stderr is a coloured bar
(``━━━╸───``, ``==>---`` where the stream cannot write the glyphs) with the
percentage and the clock. It is never wider than the terminal minus one
column, loses the bar first and then the clock on a narrow terminal, and the
percentage is what is never cut. Without a terminal the label is written once.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from contextlib import contextmanager

import pytest

from reverbscope.cli.console import Console, ProgressLine, cell_width, strip_ansi
from reverbscope.i18n import activate
from tests.frames import ESC, LANGS, Stream


@contextmanager
def _in(lang: str) -> Iterator[None]:
    activate(lang)
    try:
        yield
    finally:
        activate("en")


# --- The progress bar -----------------------------------------------------------------

_METERS = {
    "unicode": Console(interactive=True, width=80, boxed=True),
    "colour": Console(interactive=True, width=80, boxed=True, color=True),
    "plain": Console(interactive=True, width=80),
    "ascii": Console(interactive=True, width=80, boxed=True, unicode=False, encoding="cp1252"),
    "gbk": Console(interactive=True, width=80, unicode=False, encoding="gbk"),
}
LABELS = {
    "en": ("Playing the sweep and recording", "x" * 80),
    "zh_CN": ("正在播放扫频并录音", "录" * 60),
}


@pytest.mark.parametrize("name", list(_METERS))
@pytest.mark.parametrize("lang", LANGS)
def test_the_progress_line_is_never_wider_than_the_terminal_minus_one_column(
    name: str, lang: str
) -> None:
    """On an 80-column terminal a line of 80 columns made the cursor wrap, so
    every redraw started a new row; the numbers are what is never cut."""
    for label in LABELS[lang]:
        progress = ProgressLine(_METERS[name], None, label, 9.0)
        for columns in range(20, 101):
            for fraction in (0.0, 0.01, 0.37, 0.5, 0.999, 1.0):
                text = progress.line(fraction, columns - 1)
                assert cell_width(text) <= columns - 1, (columns, fraction, text)
                assert f"{fraction * 100:3.0f}%" in text, (columns, fraction, text)


@pytest.mark.parametrize("name", list(_METERS))
@pytest.mark.parametrize("lang", LANGS)
def test_the_bar_goes_first_then_the_clock_never_the_percentage(name: str, lang: str) -> None:
    for label in (*LABELS[lang], "Recording"):
        progress = ProgressLine(_METERS[name], None, label, 9.0)
        previous = (False, False)
        for width in range(19, 120):
            text = strip_ansi(progress.line(0.42, width))
            has_bar = bool(re.search(r"[━╸─=>]{3}|-{3}", text))
            has_clock = "00:03 / 00:09" in text
            assert " 42%" in text
            assert not has_bar or has_clock, (width, text)  # no bar without the clock
            # As the terminal widens, the clock comes back before the bar does.
            assert (has_bar, has_clock) >= previous, (width, text)
            previous = (has_bar, has_clock)
        assert previous == (True, True)


def test_the_progress_line_has_a_bar_the_percentage_and_the_clock() -> None:
    progress = ProgressLine(_METERS["unicode"], None, "Recording", 9.0)
    assert progress.line(0.5, 79) == (
        "  Recording  " + "━" * 16 + "╸" + "─" * 15 + "   50%  00:04 / 00:09"
    )
    # A narrow terminal loses the bar first, then the clock; the label gives way.
    assert progress.line(0.5, 40) == "  Recording   50%  00:04 / 00:09"
    assert progress.line(0.5, 25) == "  Recording   50%"
    assert progress.line(0.5, 5) == "   50%"
    long = ProgressLine(_METERS["unicode"], None, "Playing the sweep and recording", 9.0)
    assert long.line(0.5, 45) == "  Playing the sweep and…   50%  00:04 / 00:09"
    assert long.line(0.5, 30) == "  Playing the sweep and…   50%"


def test_the_bar_shows_where_it_stands_without_colour() -> None:
    bar = _METERS["unicode"].meter
    assert bar(0.0, 10) == "╸─────────"
    assert bar(0.5, 10) == "━━━━━╸────"
    assert bar(0.99, 10) == "━━━━━━━━━╸"
    assert bar(1.0, 10) == "━" * 10
    # ASCII where the stream cannot write the glyphs.
    for name in ("ascii", "gbk"):
        assert _METERS[name].meter(0.0, 10) == ">---------", name
        assert _METERS[name].meter(0.5, 10) == "=====>----", name
        assert _METERS[name].meter(1.0, 10) == "=" * 10, name
    # A stream that writes the bar but not its head draws the bar's own glyph there.
    no_head = Console(interactive=True, encoding="cp437")
    assert no_head.meter(0.5, 10) == "━━━━━━────"
    assert _METERS["unicode"].meter(0.5, 1) == "╸"


def test_the_bar_is_coloured_by_what_it_is_and_green_when_full() -> None:
    bar = _METERS["colour"].meter
    assert bar(0.5, 10) == f"{ESC}36m━━━━━╸{ESC}0m{ESC}2m────{ESC}0m"
    assert bar(1.0, 10) == f"{ESC}32m{'━' * 10}{ESC}0m"
    assert bar(0.0, 10) == f"{ESC}36m╸{ESC}0m{ESC}2m{'─' * 9}{ESC}0m"
    line = ProgressLine(_METERS["colour"], None, "Recording", 9.0).line(0.5, 79)
    # The numbers are not coloured: the percentage is plain, the clock dim.
    assert f"   50%  {ESC}2m00:04 / 00:09{ESC}0m" in line
    plain = ProgressLine(_METERS["unicode"], None, "Recording", 9.0).line(0.5, 79)
    assert ESC not in plain and strip_ansi(line) == plain


def test_the_ascii_line_is_ascii_whatever_the_label() -> None:
    for name in ("ascii", "gbk"):
        for label in ("Playing the sweep and recording", "x" * 80):
            for columns in (20, 40, 60, 80):
                text = ProgressLine(_METERS[name], None, label, 9.0).line(0.5, columns - 1)
                assert text.isascii(), text
    cut = ProgressLine(_METERS["ascii"], None, "x" * 80, 9.0).line(0.5, 59)
    assert "..." in cut and "…" not in cut
    # Chinese on a stream that cannot write it: one "?" per column, never wider.
    chinese = ProgressLine(_METERS["ascii"], None, "正在播放扫频并录音", 9.0).line(0.5, 59)
    assert "????????????????" in chinese and cell_width(chinese) <= 59


def test_a_label_cannot_send_a_control_sequence_to_the_terminal() -> None:
    text = ProgressLine(_METERS["colour"], None, "\x1b[2Jclear\x1b]0;title\x07", 9.0).line(0.5, 79)
    assert "\\x1b[2Jclear" in text and "\x1b[2J" not in text and "\x07" not in text


def _frames(stream: Stream) -> list[str]:
    return stream.getvalue().rstrip("\n").split("\r")[1:]


@pytest.mark.parametrize("lang", LANGS)
def test_a_terminal_draws_the_bar_and_never_reaches_the_last_column(
    monkeypatch: pytest.MonkeyPatch, lang: str
) -> None:
    from reverbscope.i18n import _

    with _in(lang):
        label = _("Playing the sweep and recording")
        for columns in range(20, 121):
            monkeypatch.setenv("COLUMNS", str(columns))
            stream = Stream(tty=True)
            progress = ProgressLine(_METERS["unicode"], stream, label, 7.0, interval=0.0)
            for step in range(11):
                progress.update(step / 10)
            progress.finish()
            frames = _frames(stream)
            assert frames, columns
            assert max(cell_width(frame) for frame in frames) <= min(columns, 100) - 1, columns
            assert "100%" in frames[-1]
            if columns >= 32:  # below it the clock gives way to the label
                assert "00:07 / 00:07" in frames[-1], columns
            if columns >= 70:
                assert "━" in frames[-1] and "╸" in frames[0]


def test_a_terminal_made_narrower_while_a_take_plays_does_not_wrap_the_blanks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The old line wiped the longer frame before it with as many blanks as it
    had been wide: after the terminal shrank, those blanks wrapped to a new row."""
    stream = Stream(tty=True)
    progress = ProgressLine(_METERS["unicode"], stream, "Recording", 9.0, interval=0.0)
    monkeypatch.setenv("COLUMNS", "100")
    progress.update(0.3)
    monkeypatch.setenv("COLUMNS", "40")
    progress.update(0.6)
    wide, narrow = _frames(stream)
    assert cell_width(wide) > 60 and cell_width(narrow) <= 39, (wide, narrow)
    progress.finish()
    assert cell_width(_frames(stream)[-1]) <= 39


def test_the_last_frame_of_a_take_is_a_full_green_bar(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COLUMNS", "80")
    stream = Stream(tty=True)
    progress = ProgressLine(_METERS["colour"], stream, "Recording", 9.0, interval=0.0)
    progress.update(0.4)
    progress.finish()
    assert f"{ESC}32m{'━' * 32}{ESC}0m" in _frames(stream)[-1]
    # A take that stopped early keeps the last position it reached.
    stopped = Stream(tty=True)
    early = ProgressLine(_METERS["colour"], stopped, "Recording", 9.0, interval=0.0)
    early.update(0.4)
    early.finish(completed=False)
    assert "100%" not in stopped.getvalue() and " 40%" in stopped.getvalue()


def test_a_file_gets_the_label_once_and_never_a_bar() -> None:
    stream = Stream(tty=False)
    progress = ProgressLine(Console(), stream, "Recording", 9.0)
    for step in range(101):
        progress.update(step / 100)
    progress.finish()
    assert stream.getvalue() == "Recording …\n"
