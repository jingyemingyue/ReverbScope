"""Finding cards.

On a terminal that draws frames, each interpretation finding of an analysis or
a comparison is a card: a small frame titled with its severity word and topic,
its border coloured by the severity (yellow for a warning, cyan for a notice,
dim for information). Where the frames are off (a pipe, a file, a terminal
narrower than ``use_boxes`` allows, ``--style plain``, the desktop app's report
text) the status lines stay exactly as they were; a text that a card cannot
hold whole (a path is never cut) is laid out without the card.

Every frame line is measured in display columns: Chinese text, ANSI colour and
the ASCII fallback (a classic Windows console, a cp936 or cp1252 pipe) must
keep the sides and the corners of a frame on one column.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path

import pytest

from reverbscope.cli.console import Console, strip_ansi
from reverbscope.cli.main import main
from reverbscope.cli.render import (
    REPORT_CONSOLE,
    render_analysis,
    render_comparison,
    severity_status,
    severity_word,
)
from reverbscope.demo import DemoRun, run_demo
from reverbscope.i18n import activate
from reverbscope.interpretation import Finding, interpret, interpret_comparison
from reverbscope.interpretation.interpreter import Severity
from reverbscope.labels import topic_text
from tests.frames import (
    BOTTOM,
    ESC,
    LANGS,
    TOP,
    VARIANTS,
    WIDTHS,
    Stream,
    boxed_console,
    check_card,
    find_cards,
    invoke,
)


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


@pytest.fixture(scope="module")
def demo(tmp_path_factory: pytest.TempPathFactory) -> DemoRun:
    return run_demo(tmp_path_factory.mktemp("cards") / "out")


@pytest.fixture
def home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Path]:
    monkeypatch.setenv("REVERBSCOPE_HOME", str(tmp_path / "home"))
    for name in ("NO_COLOR", "FORCE_COLOR", "TERM", "COLUMNS", "REVERBSCOPE_CLI_STYLE"):
        monkeypatch.delenv(name, raising=False)
    try:
        yield tmp_path
    finally:
        activate("en")


def _title(console: Console, finding: Finding) -> str:
    severity = str(finding.severity)
    return console.readable(
        f"{console.mark(severity_status(severity))} {severity_word(severity)}"
        f"{console.sep()}{topic_text(finding.topic)}"
    )


def _findings(demo: DemoRun) -> dict[str, Sequence[Finding]]:
    return {
        "analysis": interpret(demo.takes[0].result, "vocal"),
        "comparison": interpret_comparison(demo.comparison, "vocal"),
    }


def _reports(demo: DemoRun, console: Console) -> dict[str, str]:
    findings = _findings(demo)
    return {
        "analysis": render_analysis(console, demo.takes[0].result, findings["analysis"], "vocal"),
        "comparison": render_comparison(console, demo.comparison, findings["comparison"], "vocal"),
    }


# --- Finding cards -----------------------------------------------------------------


def test_the_demo_has_findings_of_every_severity(demo: DemoRun) -> None:
    """The tests below are only as good as the findings they draw."""
    severities = {str(f.severity) for f in _findings(demo)["analysis"]}
    assert severities == {"warning", "notice", "info"}
    assert _findings(demo)["comparison"]


@pytest.mark.parametrize("language", LANGS, indirect=True)
@pytest.mark.parametrize("variant", sorted(VARIANTS))
@pytest.mark.parametrize("width", WIDTHS)
def test_every_finding_is_a_card_with_its_severity_and_topic_in_the_border(
    demo: DemoRun, language: str, variant: str, width: int
) -> None:
    """In English and in Chinese, with colour, in ASCII and on the two legacy
    code pages, at four widths: one card per finding, every frame line as wide
    as the console, the title the severity word and the topic."""
    console = boxed_console(width, variant)
    findings = _findings(demo)
    for name, text in _reports(demo, console).items():
        cards = find_cards(text)
        assert len(cards) == len(findings[name]), (name, text)
        for card, finding in zip(cards, findings[name], strict=True):
            check_card(card, width)
            assert card.title == _title(console, finding), card.lines[0]
            if variant in ("unicode", "colour"):
                # The whole message, wrapped inside the sides and not cut.
                said = "".join("".join(card.body).split())
                assert said == "".join(finding.message.split()), card.body
        if variant == "cp1252":
            strip_ansi(text).encode("cp1252")  # Chinese became "?", one per column
        if variant == "gbk":
            strip_ansi(text).encode("gbk")
        if not console.unicode and language == "en":
            # ASCII frames, marks and signs; "°" stays where the stream can write it.
            assert {char for char in strip_ansi(text) if not char.isascii()} <= {"°"}, name


def test_the_cards_are_after_the_interpretation_heading_and_nothing_else_is_one(
    demo: DemoRun,
) -> None:
    text = _reports(demo, boxed_console(80))["analysis"]
    lines = text.splitlines()
    heading = next(i for i, line in enumerate(lines) if line.startswith("── Interpretation"))
    first = next(i for i, line in enumerate(lines) if TOP.match(line))
    assert first == heading + 1, "the first card follows the heading"
    # The title panel and the tables are not cards; the cards run to the end.
    assert not any(TOP.match(line) for line in lines[:heading])
    assert all(TOP.match(line) or line[0] in "│╰" for line in lines[first:]), "\n".join(
        lines[first:]
    )


@pytest.mark.parametrize("language", LANGS, indirect=True)
def test_the_titles_say_the_severity_and_the_topic_in_words(demo: DemoRun, language: str) -> None:
    cards = find_cards(_reports(demo, boxed_console(80))["analysis"])
    titles = [card.title for card in cards]
    if language == "en":
        assert "! Notice · reverberation" in titles
        assert "! Warning · noise" in titles
        assert "i Info · noise" in titles
    else:
        assert "! 提示 · 混响" in titles
        assert "! 警告 · 噪声" in titles
        assert "i 信息 · 噪声" in titles
    ascii_cards = find_cards(_reports(demo, boxed_console(80, "ascii"))["analysis"])
    if language == "en":
        assert "! Notice / reverberation" in [card.title for card in ascii_cards]
        assert all(card.lines[0].startswith("+- ") for card in ascii_cards)


@pytest.mark.parametrize("language", LANGS, indirect=True)
def test_the_border_is_coloured_by_the_severity_and_the_text_is_not(
    demo: DemoRun, language: str
) -> None:
    """Colour is on the border and the mark only: a letter or a digit coloured
    yellow or cyan cannot be read on a light background."""
    console = boxed_console(80, "colour")
    text = _reports(demo, console)["analysis"]
    codes = {"warning": "33", "notice": "36", "info": "2"}
    lines = text.splitlines()
    tops = [i for i, line in enumerate(lines) if TOP.match(strip_ansi(line))]
    findings = _findings(demo)["analysis"]
    assert len(tops) == len(findings) and {str(f.severity) for f in findings} == set(codes)
    for index, finding in zip(tops, findings, strict=True):
        code = codes[str(finding.severity)]
        edge = f"{ESC}{code}m"
        mark = console.mark(severity_status(str(finding.severity)))
        title = console.readable(
            f"{severity_word(str(finding.severity))}{console.sep()}{topic_text(finding.topic)}"
        )
        # The mark is in the border's colour, the title is bold; a mark that is
        # a letter (the "i" of a note) is bold too, never coloured.
        top = lines[index]
        shown = f"{ESC}1m{mark}{ESC}0m" if mark.isalnum() else f"{edge}{mark}{ESC}0m"
        assert top.startswith(f"{edge}╭─{ESC}0m {shown} {ESC}1m{title}{ESC}0m {edge}─")
        assert top.endswith(f"╮{ESC}0m")
        stop = next(i for i in range(index + 1, len(lines)) if BOTTOM.match(strip_ansi(lines[i])))
        assert lines[stop].startswith(f"{edge}╰") and lines[stop].endswith(f"╯{ESC}0m")
        for body in lines[index + 1 : stop]:
            assert body.startswith(f"{edge}│{ESC}0m ") and body.endswith(f" {edge}│{ESC}0m"), body
            assert ESC not in body[len(f"{edge}│{ESC}0m ") : -len(f" {edge}│{ESC}0m")]
    # Without colour, no escape sequence at all.
    assert ESC not in _reports(demo, boxed_console(80, "unicode"))["analysis"]


def test_unframed_findings_are_the_status_lines_they_always_were(demo: DemoRun) -> None:
    """A pipe, a file, a terminal narrower than ``use_boxes`` allows, ``--style
    plain`` and the desktop app's report text: a status line with the severity
    and the topic, the message under it, a blank line between the findings."""
    findings = _findings(demo)["analysis"]
    result = demo.takes[0].result
    plain = Console(width=80)
    lines = render_analysis(plain, result, findings, "vocal").splitlines()
    start = lines.index("  ! Notice · early reflections")
    assert lines[start - 2 : start] == ["", "Interpretation (Vocals profile)"]
    assert lines[start + 1].startswith("    A strong early reflection is present")
    assert "" in lines[start:] and not any(char in "".join(lines) for char in "╭╮╰╯"), (
        "no card without frames"
    )
    # The same lines in ASCII.
    ascii_lines = render_analysis(Console(width=80, unicode=False), result, findings, "vocal")
    assert "  [WARN] Notice | early reflections" in ascii_lines.splitlines()
    # The desktop app's report is the unframed layout.
    from reverbscope.cli.report import format_report

    gui = format_report(result, findings, "vocal").splitlines()
    assert "  ! Notice · early reflections" in gui and not any(TOP.match(line) for line in gui)
    assert REPORT_CONSOLE.boxed is False


def test_a_finding_that_a_card_cannot_hold_whole_leaves_all_findings_unframed(
    demo: DemoRun,
) -> None:
    """A path is never cut: when one card cannot hold its text, the findings are
    laid out as lines, all of them, so that the section does not mix two looks."""
    path = "/a/very/long/path/that/does/not/fit/in/a/card/of/sixty/columns/wide/take.wav"
    findings = [
        *_findings(demo)["analysis"][:2],
        Finding(topic="noise", severity=Severity.NOTICE, message=f"The file {path} is odd."),
    ]
    text = render_analysis(boxed_console(60), demo.takes[0].result, findings, "vocal")
    lines = text.splitlines()
    assert not any(TOP.match(strip_ansi(line)) for line in lines)
    assert "  ! Notice · early reflections" in lines
    assert f"    {path}" in lines  # whole, on a line of its own
    # Without the odd finding the same console draws cards.
    assert (
        len(
            find_cards(
                render_analysis(boxed_console(60), demo.takes[0].result, findings[:2], "vocal")
            )
        )
        == 2
    )


def test_a_text_from_a_file_cannot_forge_a_card(demo: DemoRun) -> None:
    """A finding read from someone else's file may carry a line break or an
    escape code: it is shown as an escape and stays inside its card."""
    evil = Finding(
        topic="noise",
        severity=Severity.WARNING,
        message="clean\n╰──╯\n\x1b[2J\x1b[31m forged",
    )
    text = render_analysis(boxed_console(60), demo.takes[0].result, [evil], "vocal")
    (card,) = find_cards(text)
    check_card(card, 60)
    assert "\x1b" not in text and "\\x1b[2J" in " ".join(card.body)
    assert "\\n" in " ".join(card.body)


@pytest.mark.parametrize("width", [30, 40, 47])
def test_a_terminal_narrower_than_the_boxed_style_gets_nocards(demo: DemoRun, width: int) -> None:
    stream = Stream(tty=True)
    # WT_SESSION: on Windows only Windows Terminal and alike show the symbols.
    env = {"COLUMNS": str(width), "WT_SESSION": "1"}
    console = Console.for_stream(stream, "never", env)
    assert not console.boxed
    text = render_analysis(console, demo.takes[0].result, _findings(demo)["analysis"], "vocal")
    assert not any(TOP.match(line) for line in text.splitlines())
    assert "  ! Notice · early reflections" in text.splitlines()


def test_a_forced_boxed_style_on_a_very_narrow_console_still_fits_or_gives_way(
    demo: DemoRun,
) -> None:
    for width in (20, 24, 30, 36):
        console = boxed_console(width)
        text = render_analysis(console, demo.takes[0].result, _findings(demo)["analysis"], "vocal")
        for card in find_cards(text):
            check_card(card, width)


def test_the_cards_of_a_report_follow_the_style_on_the_command_line(
    home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["demo", "--out", str(home / "d")]) == 0
    session = str(home / "d" / "position-a")
    capsys.readouterr()
    code, out, _err = invoke(["--style", "boxed", "--lang", "zh_CN", "show", session], capsys)
    assert code == 0
    assert any(card.title == "! 提示 · 混响" for card in find_cards(out))
    code, out, _err = invoke(["show", session], capsys)
    assert code == 0 and not find_cards(out) and "  ! Notice · reverberation" in out
    code, out, _err = invoke(["--style", "plain", "show", session], capsys)
    assert not find_cards(out)
    code, out, _err = invoke(["--style", "boxed", "--format", "json", "show", session], capsys)
    assert code == 0 and "╭" not in out and out.lstrip().startswith("{")
    other = str(home / "d" / "position-b")
    code, out, _err = invoke(["--style", "boxed", "compare", session, other], capsys)
    assert code == 0 and find_cards(out), "the comparison's findings are cards as well"
