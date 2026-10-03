"""The command line in Simplified Chinese: the root help, every subcommand's
help, argparse's own texts and errors, the environment report and the text
reports of an analysis and a comparison show no English beyond the names in
tests/zh_tokens.py."""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Iterator
from pathlib import Path

import numpy as np
import pytest
from scipy.signal import fftconvolve

from reverbscope.cli.main import build_parser, main
from reverbscope.i18n import activate
from tests.conftest import make_rir
from tests.zh_tokens import english_words


@pytest.fixture
def zh_cli(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[None]:
    monkeypatch.setenv("REVERBSCOPE_HOME", str(tmp_path / "home"))
    try:
        yield
    finally:
        activate("en")


def _help_texts() -> dict[str, str]:
    from reverbscope.cli.main import _translate_argparse

    activate("zh_CN")
    _translate_argparse()
    texts: dict[str, str] = {}

    def walk(parser: argparse.ArgumentParser, path: str) -> None:
        texts[path] = parser.format_help()
        for action in parser._actions:
            if isinstance(action, argparse._SubParsersAction):
                for name, sub in action.choices.items():
                    walk(sub, f"{path} {name}")

    walk(build_parser(), "reverbscope")
    return texts


def _prose(help_text: str) -> str:
    """The help without its usage block, option names and metavars."""
    lines = help_text.split("\n\n", 1)[1].splitlines() if "\n\n" in help_text else []
    kept = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(("-", "{")) or re.match(r"^[a-z][\w-]*\s{2,}", stripped):
            parts = re.split(r"\s{2,}", stripped, maxsplit=1)
            stripped = parts[1] if len(parts) > 1 else ""
        kept.append(stripped)
    # argparse wraps long flags ("--speaker-" / "distance") across lines.
    return re.sub(r"-\n\s*", "-", "\n".join(kept))


def test_every_help_screen_is_chinese(zh_cli: None) -> None:
    texts = _help_texts()
    assert len(texts) >= 15
    for path, text in texts.items():
        assert text.startswith("用法："), path
        found = english_words(_prose(text))
        assert found == [], f"{path}: {found}"
    root = texts["reverbscope"]
    assert "命令：" in root and "选项" in root and "显示此帮助信息并退出" in root


def test_argparse_errors_are_chinese(zh_cli: None, capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        main(["--lang", "zh_CN", "measure"])
    err = capsys.readouterr().err
    assert "错误" in err and "缺少必需的参数" in err, err
    with pytest.raises(SystemExit):
        main(["--lang", "zh_CN", "analyze", "--profile", "nope"])
    err = capsys.readouterr().err
    assert "无效选项" in err, err


def test_environment_report_is_chinese(zh_cli: None, capsys: pytest.CaptureFixture[str]) -> None:
    from reverbscope.audio.backend import get_backend

    assert main(["--lang", "zh_CN", "--backend", "fake", "doctor"]) == 0
    out = capsys.readouterr().out
    devices = tuple(d.name for d in get_backend("fake").list_devices())
    # Package names, versions and the platform string are data.
    prose = "\n".join(
        line
        for line in out.splitlines()
        if not re.match(r"^\s+[\w-]+\s{2,}\S", line) and not line.startswith("Python ")
    )
    assert english_words(prose, data=devices) == [], out


def _take(tmp_path: Path, rt60_s: float, name: str) -> Path:
    from reverbscope.io.wav import read_wav, write_wav

    sweep = tmp_path / "sweep.wav"
    if not sweep.exists():
        assert main(["sweep", "--out", str(sweep), "--duration", "2", "--post-silence", "2"]) == 0
    signal = read_wav(sweep)
    ir = make_rir(signal.sample_rate, rt60_s=rt60_s, reflections=[(0.011, 0.8)])
    rec = fftconvolve(signal.samples, ir)[: signal.n_samples + ir.shape[0]]
    rec = rec + np.random.default_rng(3).normal(0.0, 3e-5, rec.shape[0])
    recording = write_wav(tmp_path / f"{name}.wav", rec, signal.sample_rate, subtype="FLOAT")
    out = tmp_path / name
    assert (
        main(
            [
                "analyze",
                "--recording",
                str(recording),
                "--sweep",
                str(sweep),
                "--out",
                str(out),
                "--speaker-distance",
                "1.5",
            ]
        )
        == 0
    )
    return out


def test_reports_of_an_analysis_and_a_comparison_are_chinese(
    zh_cli: None, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    first = _take(tmp_path, 0.4, "a")
    second = _take(tmp_path, 1.1, "b")
    capsys.readouterr()
    assert main(["--lang", "zh_CN", "show", str(first)]) == 0
    report = capsys.readouterr().out
    assert main(["--lang", "zh_CN", "compare", str(first), str(second)]) == 0
    comparison = capsys.readouterr().out
    for name, text in (("show", report), ("compare", comparison)):
        prose = "\n".join(line for line in text.splitlines() if str(tmp_path) not in line)
        found = english_words(prose)
        assert found == [], f"{name}: {sorted(set(found))}\n{text}"


def test_files_written_in_chinese_stay_language_neutral(
    zh_cli: None, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Result files keep English notes whatever the interface language, so a
    session reads the same everywhere and old readers still parse it."""
    from reverbscope.io.wav import read_wav, write_wav

    sweep = tmp_path / "sweep.wav"
    assert main(["sweep", "--out", str(sweep), "--duration", "2", "--post-silence", "2"]) == 0
    signal = read_wav(sweep)
    ir = make_rir(signal.sample_rate, rt60_s=1.2, reflections=[(0.011, 0.8)])
    rec = fftconvolve(signal.samples, ir)[: signal.n_samples + ir.shape[0]]
    rec = rec + np.random.default_rng(5).normal(0.0, 3e-5, rec.shape[0])
    recording = write_wav(tmp_path / "rec.wav", rec, signal.sample_rate, subtype="FLOAT")
    out = tmp_path / "session"
    args = ["--lang", "zh_CN", "analyze", "--recording", str(recording), "--sweep", str(sweep)]
    assert main([*args, "--out", str(out), "--speaker-distance", "1.5"]) == 0
    capsys.readouterr()
    for name in ("result.json", "session.json"):
        text = (out / name).read_text(encoding="utf-8")
        cjk = re.findall(r"[　-〿一-鿿＀-￯]", text)
        assert cjk == [], f"{name} stores Chinese text: {''.join(cjk[:40])}"
        json.loads(text)


def _cjk(text: str) -> list[str]:
    return re.findall(r"[　-〿一-鿿＀-￯]", text)


def test_comparison_and_project_files_stay_language_neutral(
    zh_cli: None, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    first = _take(tmp_path, 0.4, "a")
    second = _take(tmp_path, 1.1, "b")
    comparison = tmp_path / "comparison.json"
    project = tmp_path / "project"
    zh = ["--lang", "zh_CN"]
    assert main([*zh, "compare", str(first), str(second), "--out", str(comparison)]) == 0
    assert main([*zh, "project", "init", "--out", str(project), "--name", "Room"]) == 0
    for session, position in ((first, "P1"), (second, "P2")):
        assert (
            main([*zh, "project", "add", str(project), str(session), "--position", position]) == 0
        )
    assert main([*zh, "project", "average", str(project)]) == 0
    capsys.readouterr()
    files = [comparison, *sorted(project.rglob("*.json"))]
    assert len(files) >= 2
    for path in files:
        text = path.read_text(encoding="utf-8")
        assert _cjk(text) == [], f"{path.name} stores Chinese text"


def test_an_english_session_is_shown_in_chinese_and_left_untouched(
    zh_cli: None, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Sessions written in English (by this or an earlier version) open in the
    Chinese interface with translated notes; nothing is written back."""
    session = _take(tmp_path, 1.1, "english")
    before = {p.name: p.read_bytes() for p in session.glob("*.json")}
    stored = json.loads((session / "result.json").read_text(encoding="utf-8"))
    assert _cjk(json.dumps(stored, ensure_ascii=False)) == []
    capsys.readouterr()
    assert main(["--lang", "zh_CN", "show", str(session)]) == 0
    shown = capsys.readouterr().out
    assert "解读（" in shown
    assert {p.name: p.read_bytes() for p in session.glob("*.json")} == before
