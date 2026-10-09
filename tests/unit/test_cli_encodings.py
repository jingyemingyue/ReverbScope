"""Frames follow what the stream can write.

A stream whose encoding writes the symbols (``✓ × – ─ · …``) but not the box
glyphs (the Japanese JIS X 0213 encodings have no ``╭``) gets ASCII frames,
and its error mark is the letter ``x``. What a terminal cannot write is shown
as one "?" per display column, so that the sides of a frame and the columns of
a table stay straight; a pipe or a file keeps the stream's own text.
"""

from __future__ import annotations

import pytest

from reverbscope.cli.console import Console, cell_width, frames_writable
from reverbscope.i18n import activate
from tests.terminals import Workspace, capture, problems


def test_an_encoding_that_writes_the_symbols_but_not_the_box_gets_ascii_frames() -> None:
    """The JIS X 0213 encodings write ✓ × – ─ · … but not ╭ ╮ ╰ ╯ ╸ ✗."""
    for encoding in ("euc_jisx0213", "shift_jis_2004", "iso2022_jp_3"):
        assert not frames_writable(encoding), encoding
    for encoding in ("utf-8", "UTF-8", "utf-16"):
        assert frames_writable(encoding), encoding
    assert not frames_writable("cp1252") and not frames_writable("ascii")
    jis = Console(unicode=True, boxed=True, width=40, encoding="euc_jisx0213")
    assert jis.unicode_frames is False
    card = jis.frame("Title", ["text"], "warn", mark="warn")
    assert card is not None
    assert card[0].startswith("+- ! Title ") and card[0].endswith("-+")
    assert card[1] == "| text" + " " * 33 + "|"
    assert card[-1] == "+" + "-" * 38 + "+"
    assert jis.title("Panel")[0] == "+" + "-" * 38 + "+"
    grid = jis.framed_table(["A", "B"], [["1", "2"]])
    assert grid is not None and grid[0].strip().startswith("+") and "┌" not in "".join(grid)
    # The symbols stay Unicode; the mark whose glyph it cannot write does not.
    assert jis.sep() == " · " and jis.symbol("ok") == "✓"
    assert jis.mark("ok") == "✓" and jis.mark("error") == "x"
    # |Δ| would read as two more sides of an ASCII frame.
    assert jis.readable("|Δ| 5 %") == "abs(delta) 5 %"
    assert Console(unicode=True, boxed=True, width=40).readable("|Δ| 5 %") == "|Δ| 5 %"
    assert Console(unicode=True, width=40, encoding="euc_jisx0213").readable("|Δ|") == "|Δ|"


def test_a_report_on_such_a_stream_draws_straight_ascii_frames(
    cli_workspace: Workspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    for columns in (48, 80):
        text = capture(
            ("compare", cli_workspace.a, cli_workspace.b),
            monkeypatch,
            columns=columns,
            encoding="euc_jisx0213",
        )
        assert problems(text, columns) == []
        assert "+-" in text and not any(glyph in text for glyph in "╭╮╰╯┌┐└┘│")
        assert "??" not in text  # nothing the stream cannot write is left in the text
        assert "|Δ|" not in text and "abs(delta)" in text


def test_a_terminal_that_cannot_write_chinese_keeps_a_plain_table_straight() -> None:
    """A "?" for each column of a character it cannot write, so that the cells of
    a table keep their columns; a pipe or a file keeps the stream's own text."""
    rows = [["混响", "1"], ["clarity", "22"]]
    terminal = Console(unicode=False, interactive=True, encoding="cp1252", width=60)
    lines = terminal.table(["设置", "值"], rows, align="lr")
    assert len({cell_width(line) for line in lines}) == 1, lines
    assert lines[2].startswith("  ????  ") and lines[0].lstrip().startswith("????  ")
    pipe = Console(unicode=False, encoding="cp1252", width=60)
    assert pipe.readable("混响") == "混响"  # the stream writes its own "?"
    assert terminal.readable("混响 110") == "???? 110"


@pytest.mark.parametrize("encoding", ["euc_jisx0213", "shift_jis_2004"])
@pytest.mark.parametrize("columns", [48, 70, 80])
def test_a_chinese_report_on_a_jis_x_0213_stream_keeps_its_frames_straight(
    cli_workspace: Workspace, monkeypatch: pytest.MonkeyPatch, encoding: str, columns: int
) -> None:
    """The stream writes ✓ and ─ but not every Chinese character (态 is missing):
    the character was written as one "?" for two columns and every side of a
    table came out a column short. It is one "?" per column here too."""
    for argv in (("compare", cli_workspace.a, cli_workspace.b), ("show", cli_workspace.a)):
        text = capture(argv, monkeypatch, columns=columns, lang="zh_CN", encoding=encoding)
        assert problems(text, columns) == [], text
        assert "??" in text  # the stream cannot write 态 or 对, two columns each
        assert not any(glyph in text for glyph in "╭╮╰╯┌┐└┘│")  # ASCII frames


def test_a_chinese_sentence_keeps_its_quotation_marks_on_a_stream_that_writes_them() -> None:
    """GBK cannot write ✓, so every sign became ASCII: ``仍属"偏长"`` and ``...``
    in a Chinese sentence, though GBK writes “ ” and …. English keeps its rule."""
    gbk = Console(unicode=False, encoding="gbk")
    sentence = "对此配置而言仍属“偏长”，请稍候…"
    activate("zh_CN")
    try:
        assert gbk.fit(sentence) == sentence
        # The signs it writes but a sentence does not need stay ASCII, so that
        # a table's columns do not depend on a double-width arrow.
        assert gbk.fit("0.70 s → 0.51 s，|Δ| ≤ 3 dB") == "0.70 s -> 0.51 s，|delta| <= 3 dB"
        # A stream that cannot write Chinese cannot write the sentence anyway.
        assert Console(unicode=False, encoding="cp1252").fit(sentence) == (
            '对此配置而言仍属"偏长"，请稍候...'
        )
    finally:
        activate("en")
    assert gbk.fit("a “b” …") == 'a "b" ...'


def test_a_chinese_report_on_a_gbk_stream_has_chinese_quotation_marks(
    cli_workspace: Workspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    text = capture(
        ("compare", cli_workspace.a, cli_workspace.b),
        monkeypatch,
        columns=80,
        lang="zh_CN",
        encoding="cp936",
    )
    assert "仍属“偏长”" in text and '"偏长"' not in text
    assert problems(text, 80) == []
