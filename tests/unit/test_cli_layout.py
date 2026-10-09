"""How the command line lays out and punctuates Chinese: lists, brackets, colons
and clauses, wrapping, quotes.

What reviewers of the Chinese output found by reading it at 40 to 100 columns:
ASCII brackets and commas inside Chinese sentences, a number parted from its
unit at the end of a line, a closing mark that starts one, a hint cut in two,
and a last line of one character.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

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
