"""Colour sits on marks, bars and borders; a word or a number is never coloured or dim.

Yellow, green and cyan text has a contrast of 1.7 to 3.5 on the usual light
backgrounds, dim text 1.9 to 3.7. Status words, headings, titles, commands and
the numbers of the menu are bold in the colour of the terminal's text; labels,
notes and descriptions are plain; dim is for decoration (rules, borders, the
rest of a progress bar). A mark that is a letter (the ASCII ``[OK]``, ``x``
and ``i``) is bold, not coloured.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from reverbscope.cli.console import Console, ProgressLine
from reverbscope.cli.interactive import menu_items, run_menu
from reverbscope.cli.render import render_demo
from reverbscope.i18n import activate
from tests.terminals import Workspace, capture, coloured_words, screens

ESC = "\x1b["
LANGS = ("zh_CN", "en")


def test_the_detector_finds_a_coloured_word() -> None:
    assert coloured_words("\x1b[33mwarn\x1b[0m \x1b[1mbold\x1b[0m \x1b[2m✓\x1b[0m") == ["warn"]
    assert coloured_words("\x1b[36m━\x1b[0m\x1b[1mTitle\x1b[0m") == []
    assert coloured_words("\x1b[32;1m✓\x1b[0m \x1b[1mgood\x1b[0m") == []
    assert coloured_words("\x1b[2m0.5 s\x1b[0m") == ["0", "5", "s"]
    assert coloured_words("\x1b[31;1m[ERROR]\x1b[0m") == ["ERROR"]
    assert coloured_words("\x1b[36mi\x1b[0m") == ["i"]  # a mark that is a letter is bold
    assert coloured_words("\x1b[2m────\x1b[0m \x1b[31m│\x1b[0m") == []


@pytest.mark.parametrize("style", ["boxed", "plain"])
@pytest.mark.parametrize("lang", LANGS)
def test_no_word_or_number_is_coloured_or_dim(
    cli_workspace: Workspace,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    lang: str,
    style: str,
) -> None:
    """Twenty-one screens, in both languages and both styles, in colour."""
    monkeypatch.chdir(tmp_path)
    in_colour = 0
    for argv in screens(cli_workspace):
        text = capture(argv, monkeypatch, columns=90, lang=lang, color="always", style=style)
        in_colour += ESC in text
        assert coloured_words(text) == [], (argv, style)
    assert in_colour >= 17  # the lists of sessions and of folders have nothing to colour


@pytest.mark.parametrize("lang", LANGS)
def test_the_demo_and_an_analysis_colour_no_word(
    cli_workspace: Workspace,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    lang: str,
) -> None:
    monkeypatch.setattr("reverbscope.demo.run_demo", lambda *_a, **_k: cli_workspace.run)
    monkeypatch.chdir(tmp_path)
    ir = cli_workspace.demo / "position-a" / "impulse_response.wav"
    for argv in (
        ("demo", "--out", str(tmp_path / "demo")),
        ("analyze-ir", "--ir", str(ir), "--band", "20", "20000", "--out", str(tmp_path / "ir")),
    ):
        text = capture(argv, monkeypatch, columns=90, lang=lang, color="always")
        assert ESC in text and coloured_words(text) == [], argv


@pytest.mark.parametrize("lang", LANGS)
def test_an_ascii_stream_colours_no_letter_either(
    cli_workspace: Workspace,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    lang: str,
) -> None:
    """``[OK]``, ``[WARN]``, ``x`` and ``i`` are the marks of a stream that
    cannot write ✓ and ✗; as letters they are bold, not coloured."""
    monkeypatch.chdir(tmp_path)
    for encoding in ("cp1252", "cp936"):
        for argv in (
            ("show", cli_workspace.a),
            ("compare", cli_workspace.a, cli_workspace.b),
            ("project", "overview", str(cli_workspace.room)),
            ("--backend", "fake", "doctor"),
            ("show", str(cli_workspace.root / "missing")),
        ):
            for style in ("boxed", "plain"):
                text = capture(
                    argv,
                    monkeypatch,
                    columns=90,
                    lang=lang,
                    color="always",
                    style=style,
                    encoding=encoding,
                )
                assert ESC in text and coloured_words(text) == [], (argv, encoding, style)


def test_a_title_a_command_and_a_heading_are_bold_not_coloured() -> None:
    c = Console(width=60, boxed=True, color=True)
    top = c.frame("Title", ["x"], "warn")
    assert top is not None and f"{ESC}1mTitle{ESC}0m" in top[0]
    assert c.command("reverbscope show x") == f"{ESC}1mreverbscope show x{ESC}0m"
    assert c.muted("a note") == "a note"
    assert c.faint("────") == f"{ESC}2m────{ESC}0m"
    assert c.badge("ok") == f"{ESC}32m✓{ESC}0m {ESC}1mgood{ESC}0m"
    # The heading is bold, its rule dim.
    heading = c.section("Reverberation")[1]
    assert f"{ESC}1mReverberation{ESC}0m" in heading and f"{ESC}2m──{ESC}0m" in heading
    plain = Console(width=60, color=True)
    assert plain.section("Reverberation")[1] == f"{ESC}1mReverberation{ESC}0m"
    # A label, a note and a table's heading: plain, plain, bold.
    assert plain.fields([("Label", "value")]) == ["  Label  value"]
    assert plain.table(["Band"], [["63 Hz"]])[0] == f"  {ESC}1mBand{ESC}0m"


def test_a_mark_that_is_a_letter_is_bold_a_glyph_is_coloured() -> None:
    unicode = Console(color=True)
    assert unicode.symbol("ok") == f"{ESC}32m✓{ESC}0m"
    assert unicode.symbol("warn") == f"{ESC}33;1m!{ESC}0m"
    assert unicode.symbol("info") == f"{ESC}1mi{ESC}0m"
    ascii_console = Console(color=True, unicode=False)
    assert ascii_console.symbol("ok") == f"{ESC}1m[OK]{ESC}0m"
    assert ascii_console.symbol("error") == f"{ESC}1m[ERROR]{ESC}0m"
    assert ascii_console.symbol("next") == f"{ESC}36m->{ESC}0m"
    assert ascii_console.badge("error") == f"{ESC}1mx{ESC}0m {ESC}1mproblem{ESC}0m"
    assert ascii_console.badge("warn") == f"{ESC}33;1m!{ESC}0m {ESC}1mcheck{ESC}0m"


def test_an_unreliable_number_is_not_coloured_its_mark_is() -> None:
    from types import SimpleNamespace

    from reverbscope.cli.render import _energy_cell, _metric_cell
    from reverbscope.models.result import Validity

    c = Console(color=True)
    unreliable = SimpleNamespace(seconds=0.22, validity=Validity.UNRELIABLE)
    assert _metric_cell(c, unreliable) == f"0.22 s {ESC}33m?{ESC}0m"  # type: ignore[arg-type]
    energy = SimpleNamespace(value=-3.2, unit="dB", validity=Validity.UNRELIABLE)
    assert _energy_cell(c, energy).startswith("-3.2 dB ")  # type: ignore[arg-type]
    # Without colour the cell is what it always was.
    assert _metric_cell(Console(), unreliable) == "0.22 s ?"  # type: ignore[arg-type]


def test_the_menu_is_bold_numbers_and_plain_descriptions() -> None:
    out = io.StringIO()
    c = Console(width=80, boxed=True, color=True)
    run_menu(c, ask=lambda _prompt: "q", run=lambda _argv: 0, out=out)
    text = out.getvalue()
    assert ESC in text and coloured_words(text) == []
    for item in menu_items():
        assert f"{ESC}1m{item.key.rjust(2)}{ESC}0m  {item.title}" in text, item.key


def test_the_progress_line_dims_only_the_rest_of_the_bar() -> None:
    c = Console(width=80, color=True, interactive=True)
    line = ProgressLine(c, None, "Recording", 9.0).line(0.5, 79)
    assert coloured_words(line) == []
    assert "50%  00:04 / 00:09" in line and f"{ESC}2m─" in line


@pytest.mark.parametrize("lang", LANGS)
def test_the_demo_walkthrough_colours_no_word(cli_workspace: Workspace, lang: str) -> None:
    from reverbscope.interpretation import interpret

    findings = [interpret(take.result, "vocal") for take in cli_workspace.run.takes]
    activate(lang)
    for boxed in (True, False):
        c = Console(width=90, boxed=boxed, color=True, interactive=True)
        text = render_demo(c, cli_workspace.run, findings, gui_available=False)
        assert ESC in text and coloured_words(text) == [], boxed
