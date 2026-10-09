"""How the command line lays out and punctuates Chinese: lists, brackets, colons
and clauses, wrapping, quotes.

What reviewers of the Chinese output found by reading it at 40 to 100 columns:
ASCII brackets and commas inside Chinese sentences, a number parted from its
unit at the end of a line, a closing mark that starts one, a hint cut in two,
and a last line of one character.
"""

from __future__ import annotations

import contextlib
import re
from collections.abc import Callable, Iterator, Sequence
from itertools import pairwise
from pathlib import Path

import pytest

from reverbscope.cli.console import GLUE, cell_width, strip_ansi, wrap
from reverbscope.cli.main import main
from reverbscope.demo import run_demo
from reverbscope.i18n import activate, annotated, clause_join, labelled, list_join, quoted
from tests.frames import unframe
from tests.zh_tokens import ascii_punctuation

WIDTHS = (40, 60, 80, 100)
Call = Callable[..., str]


@pytest.fixture(scope="module")
def workspace(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A demo (two sessions and their comparison) and a project made of them."""
    root = tmp_path_factory.mktemp("layout")
    demo = root / "demo"
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("REVERBSCOPE_HOME", str(root / "home"))
        run_demo(demo)
        for argv in (
            ["project", "init", "--out", str(root / "room"), "--name", "Studio"],
            ["project", "add", str(root / "room"), str(demo / "position-a"), "--position", "A"],
            ["project", "add", str(root / "room"), str(demo / "position-b"), "--position", "B"],
        ):
            assert main(argv) == 0
    return root


@pytest.fixture
def run(
    workspace: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> Iterator[Call]:
    monkeypatch.setenv("REVERBSCOPE_HOME", str(tmp_path / "home"))
    for name in ("NO_COLOR", "FORCE_COLOR", "TERM", "PYTHONIOENCODING", "REVERBSCOPE_CLI_STYLE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)

    def call(*argv: str, columns: int = 80, style: str = "boxed") -> str:
        monkeypatch.setenv("COLUMNS", str(columns))
        capsys.readouterr()
        with contextlib.suppress(SystemExit):
            main(["--style", style, *argv])
        captured = capsys.readouterr()
        return captured.out + captured.err

    try:
        yield call
    finally:
        activate("en")


def _screens(workspace: Path) -> list[tuple[str, ...]]:
    demo = workspace / "demo"
    a, b = str(demo / "position-a"), str(demo / "position-b")
    return [
        ("show", a),
        ("show", b),
        ("show", str(demo / "comparison.json")),
        ("compare", a, b),
        ("compare", a, b, "--same-input-gain"),
        ("project", "overview", str(workspace / "room")),
        ("project", "average", str(workspace / "room")),
        ("--backend", "fake", "devices", "--probe"),
        ("--backend", "fake", "doctor", "--probe"),
        ("profiles", "--all"),
        ("config",),
        ("sweep", "--out", "sweep.wav", "--duration", "2"),
    ]


# --- Lists, brackets, colons and clauses follow the interface language ------------------------


@pytest.mark.parametrize(
    ("lang", "bracketed", "labelled_as", "clause", "listed", "quote"),
    [
        ("en", "110 Hz (+11.3 dB)", "A: b", "x; y", "x, y", "'bad'"),
        ("zh_CN", "110 Hz（+11.3 dB）", "A：b", "x；y", "x、y", "“bad”"),
    ],
)
def test_brackets_colons_clauses_lists_and_quotes_are_the_languages(
    lang: str, bracketed: str, labelled_as: str, clause: str, listed: str, quote: str
) -> None:
    """Chinese writes full-width brackets (with no space before them), colons and
    semicolons, a list with 、 and a typed value between “ ”; English stays
    as it was."""
    activate(lang)
    try:
        assert annotated("110 Hz", "+11.3 dB") == bracketed
        assert labelled("A", "b") == labelled_as
        assert clause_join(["x", "y"]) == clause
        assert list_join(["x", "y"]) == listed
        assert quoted("bad") == quote
    finally:
        activate("en")


def test_a_quoted_value_is_what_python_writes_in_english() -> None:
    assert quoted("it's") == repr("it's") == '"it\'s"'
    assert quoted("a\\b") == repr("a\\b")


def test_chinese_lists_and_notes_in_the_reports(run: Call, workspace: Path) -> None:
    session = str(workspace / "demo" / "position-a")
    text = " ".join(unframe(run("--lang", "zh_CN", "show", session, columns=120)).split())
    assert "可能的共振：110 Hz（+11.3 dB）" in text
    assert "50 Hz（+57 dB）、100 Hz（+48 dB）、150 Hz（+43 dB）" in text
    assert "RT60 0.70 s（T30）" in text
    assert "声速 343.2 m/s，气温 20 °C（假定）" in text
    assert "几何 – 未确定（需添加 --speaker-distance）" in text
    compared = " ".join(
        unframe(
            run("--lang", "zh_CN", "compare", session, session.replace("-a", "-b"), columns=120)
        ).split()
    )
    assert "RT60 0.70 s → 0.51 s（-27.3 %）" in compared
    assert "C50（dB）" in compared
    devices = " ".join(
        unframe(run("--lang", "zh_CN", "--backend", "fake", "devices", columns=120)).split()
    )
    assert "输入、输出" in devices
    health = " ".join(
        unframe(
            run("--lang", "zh_CN", "project", "overview", str(workspace / "room"), columns=120)
        ).split()
    )
    assert "警告（电平）" in health and "数值后带（k）" in health
    assert "主机 API fake（1）" in " ".join(
        unframe(run("--lang", "zh_CN", "--backend", "fake", "doctor", columns=120)).split()
    )


def test_the_english_text_keeps_its_brackets_and_commas(run: Call, workspace: Path) -> None:
    """English is not touched: the brackets are ASCII, a list is joined with commas."""
    session = str(workspace / "demo" / "position-a")
    text = " ".join(
        unframe(run("--lang", "en", "show", session, columns=120, style="plain")).split()
    )
    assert "RT60 0.70 s (T30)" in text
    assert "110 Hz (+11.3 dB)" in text
    assert "50 Hz (+57 dB), 100 Hz (+48 dB), 150 Hz (+43 dB)" in text
    assert "343.2 m/s at 20 °C (assumed)" in text
    assert "– not determined (add --speaker-distance)" in text


@pytest.mark.parametrize("style", ["boxed", "plain"])
@pytest.mark.parametrize("columns", [48, 60, 100])
def test_no_chinese_screen_uses_ascii_punctuation(
    run: Call, workspace: Path, style: str, columns: int
) -> None:
    """Every screen that carries a report in Chinese writes its brackets, commas,
    colons and quotes full-width, in every renderer and at every width."""
    problems = {}
    for argv in _screens(workspace):
        text = run("--lang", "zh_CN", *argv, columns=columns, style=style)
        assert "Traceback" not in text, argv
        found = ascii_punctuation(unframe(text))
        if found:
            problems[" ".join(argv[:3])] = found[:3]
    assert problems == {}


def test_lists_in_the_help_and_the_findings_use_the_chinese_comma(run: Call) -> None:
    """The sample rates of ``sweep --help`` and the frequencies of a resonance
    finding were joined with ASCII commas inside Chinese sentences."""
    from reverbscope.interpretation import available_profiles, get_profile
    from reverbscope.interpretation.profiles import ProfileBase
    from reverbscope.models.result import ResonanceCandidate

    help_text = " ".join(unframe(run("--lang", "zh_CN", "sweep", "--help", columns=200)).split())
    assert "44100、48000、88200、96000、176400、192000" in help_text
    assert "44100, 48000" not in help_text
    candidates = [
        ResonanceCandidate(
            frequency_hz=frequency,
            level_above_baseline_db=8.0,
            narrowband_decay_20db_s=0.6,
            filter_ringing_20db_s=0.1,
            decay_distinguishable=True,
            surroundings_decay_20db_s=0.3,
        )
        for frequency in (48.0, 96.0)
    ]
    for name in available_profiles():
        profile = get_profile(name)
        assert isinstance(profile, ProfileBase)
        activate("zh_CN")
        try:
            chinese = profile.resonance_message(candidates)
        finally:
            activate("en")
        assert "48 Hz、96 Hz" in chinese, (name, chinese)
        assert "48 Hz, 96 Hz" in profile.resonance_message(candidates), name


# --- A number stays with its unit ---------------------------------------------------------------

#: The units a number is never parted from, in Latin and in Chinese.
UNITS = r"(?:dBFS|dB|kHz|Hz|ms|s|m|°C|%|摄氏度|赫兹|倍频程|分贝|[个项次条遍处])"
CLOSING = "，。、；：！？）」』”’》〉】〕"
OPENING = "（「『“‘《〈【〔"


def _split_units(text: str) -> list[tuple[str, str]]:
    """Every pair of lines where one ends in a number and the next starts with its unit."""
    lines = [" ".join(unframe(strip_ansi(line)).split()) for line in text.splitlines()]
    return [
        (above, below)
        for above, below in pairwise(lines)
        if re.search(r"\d$", above) and re.match(rf"{UNITS}(?![A-Za-z])", below)
    ]


@pytest.mark.parametrize("width", range(20, 101, 3))
@pytest.mark.parametrize(
    "text",
    [
        "（直达声占能量的 74 %；上限 5 dB）：EDT 描述的是早期衰减，而不是整个衰减过程。",
        "C50 是 50 ms 处的早期能量除以后期能量。C80 是 80 ms 处的同一比值（音乐）。",
        "可能的交流声，基频 50 Hz 的倍频：50 Hz（+57 dB）、100 Hz（+48 dB）、150 Hz（+43 dB）",
        "C80 is the same at 80 ms (music). D50 is the share of energy in the first 50 ms.",
        "44.1 · 48 · 88.2 · 96 · 176.4 · 192 kHz · default input",
        "-69.2 dBFS RMS, peak -65.8 dBFS; 343.2 m/s at 20 °C, a 2 m path, RT60 0.51 s",
        "数据质量：直达声置信度高 · 1 条警告，见“诊断”；未提供气温时按 20 摄氏度计算，共 3 个位置，2 项良好",
    ],
)
def test_wrapping_never_parts_a_number_from_its_unit(text: str, width: int) -> None:
    lines = wrap(text, width, first="  ")
    assert _split_units("\n".join(lines)) == []
    assert GLUE not in "".join(lines)  # the glue is only for the line breaks


def test_glue_units_holds_a_number_to_its_chinese_counter_too() -> None:
    from reverbscope.cli.console import glue_units

    assert glue_units("1 条警告，20 摄氏度，3 个位置") == (
        f"1{GLUE}条警告，20{GLUE}摄氏度，3{GLUE}个位置"
    )
    assert glue_units("RT60 and 2 seconds, 5 sec") == "RT60 and 2 seconds, 5 sec"
    assert glue_units("Band s, a Hz") == "Band s, a Hz"  # no digit before the unit
    assert glue_units("110 Hz (+11.3 dB)") == f"110{GLUE}Hz (+11.3{GLUE}dB)"


@pytest.mark.parametrize("lang", ["zh_CN", "en"])
@pytest.mark.parametrize("columns", WIDTHS)
def test_no_screen_parts_a_number_from_its_unit(
    run: Call, workspace: Path, lang: str, columns: int
) -> None:
    for argv in _screens(workspace):
        text = run("--lang", lang, *argv, columns=columns)
        assert GLUE not in text, argv
        assert _split_units(text) == [], (argv, columns)


# --- Wrapping: closing marks, two-character words, hints and the last line ----------------------


def _text(lines: Sequence[str]) -> str:
    return "".join(line.strip() for line in lines)


CHINESE_TEXTS = [
    "扫频时长，单位秒（默认：10）：会话编号，或会话、对比的路径：1。运行 reverbscope --help 查看所有命令和选项。",
    "采样率（Hz）：44100、48000、88200、96000、176400、192000（默认：48000）",
    "鼓，近距离话筒（底鼓、军鼓、通鼓），有无顶部话筒均可。",
    "2 个话筒位置达到 ISO 3382-2 的简易级；工程级需要第二个声源位置：再加 1 个话筒位置（共 3 个），每个位置都在扬声器的两个位置各测一次。",
    "只有一对位置：判定只针对这两次测量，不代表整个房间，而且仅凭这些证据，任何变化都不具有统计显著性。",
    "音频流的 PortAudio 延迟等级（默认：PortAudio 的高延迟）",
]


@pytest.mark.parametrize("text", CHINESE_TEXTS, ids=range(len(CHINESE_TEXTS)))
@pytest.mark.parametrize("width", range(24, 70))
def test_a_wrapped_chinese_text_breaks_in_the_right_places(text: str, width: int) -> None:
    lines = wrap(text, width, first="  ")
    assert _text(lines).replace(" ", "") == text.replace(" ", "")
    for line in lines[1:]:
        assert line.strip()[:1] not in CLOSING, (width, lines)
    for line in lines:
        assert line.rstrip()[-1:] not in OPENING, (width, lines)
        assert cell_width(line) <= width, (width, lines)
    if len(lines) > 1:
        # The last line is more than one character (and its mark).
        assert cell_width(lines[-1].strip().rstrip(CLOSING)) > 2, (width, lines)
    # A short note in brackets, a default hint among them, is not cut in two
    # (unless it is longer than a line).
    longest = max((cell_width(note) for note in re.findall(r"（[^（）]*）", text)), default=0)
    if width - 2 >= longest:
        for line in lines:
            assert line.count("（") == line.count("）"), (width, lines)


def test_the_two_halves_of_a_word_are_kept_together() -> None:
    assert wrap("会话编号，或会话、对比的路径：1", 26) == ["会话编号，或会话、对比的", "路径：1"]
    assert wrap("运行 reverbscope --help 查看所有命令和选项。", 40) == [
        "运行 reverbscope --help 查看所有命令和",
        "选项。",
    ]


def test_a_default_hint_stays_whole_with_its_colon() -> None:
    text = "扫频时长，单位秒（默认：10）："
    assert wrap(text, 30, first="  ") == ["  扫频时长，单位秒", "  （默认：10）："]
    # A hint that cannot fit one line is split where it must be.
    assert "".join(wrap(text, 12)) == text
    # ） and ： never stand alone on a line.
    for width in range(18, 40):
        for line in wrap(text, width, first="  "):
            assert line.strip() not in ("）：", "：", "）")


def test_the_last_line_is_not_one_lone_character() -> None:
    for width in range(30, 40):
        lines = wrap("语言、录音配置、音频后端、输出文件夹", width, first="  ")
        assert all(cell_width(line.strip()) > 2 for line in lines), lines
    assert wrap("统计显著性。", 11) == ["统计显", "著性。"]


def test_english_text_wraps_as_it_did() -> None:
    text = "Potential low-frequency resonances around 48 Hz, 96 Hz (+8.0 dB): these ring longer."
    assert wrap(text, 30, first="  ") == [
        "  Potential low-frequency",
        "  resonances around 48 Hz,",
        "  96 Hz (+8.0 dB): these ring",
        "  longer.",
    ]


@pytest.mark.parametrize("style", ["boxed", "plain"])
@pytest.mark.parametrize("columns", WIDTHS)
def test_no_chinese_screen_breaks_a_line_in_a_bad_place(
    run: Call, workspace: Path, style: str, columns: int
) -> None:
    """On every screen, at every width, no line starts with a closing mark, ends
    with an opening bracket or is one lone character."""
    problems: dict[str, list[str]] = {}
    screens = [*_screens(workspace), ("sweep", "--help"), ("analyze", "--help"), ("--help",)]
    for argv in screens:
        text = run("--lang", "zh_CN", *argv, columns=columns, style=style)
        for line in unframe(text).splitlines():
            shown = line.strip()
            if not shown or shown.startswith(("$", "reverbscope")):
                continue
            lone = len(shown.rstrip(CLOSING)) == 1 and cell_width(shown.rstrip(CLOSING)) == 2
            if shown[0] in CLOSING or shown[-1] in OPENING or lone:
                problems.setdefault(" ".join(argv[:3]), []).append(shown)
    assert problems == {}
