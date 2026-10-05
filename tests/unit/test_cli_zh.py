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

from roomscope.cli.main import build_parser, main
from roomscope.i18n import activate
from tests.conftest import make_rir
from tests.zh_tokens import english_words


@pytest.fixture
def zh_cli(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[None]:
    monkeypatch.setenv("ROOMSCOPE_HOME", str(tmp_path / "home"))
    try:
        yield
    finally:
        activate("en")


def _help_texts() -> dict[str, str]:
    from roomscope.cli.main import _translate_argparse

    activate("zh_CN")
    _translate_argparse()
    texts: dict[str, str] = {}

    def walk(parser: argparse.ArgumentParser, path: str) -> None:
        texts[path] = parser.format_help()
        for action in parser._actions:
            if isinstance(action, argparse._SubParsersAction):
                for name, sub in action.choices.items():
                    walk(sub, f"{path} {name}")

    walk(build_parser(), "roomscope")
    return texts


#: Written in English on purpose: the way back for a reader of English.
ENGLISH_HINT = "English interface: roomscope config language en"


def _prose(help_text: str) -> str:
    """The help without its usage block, option names and metavars."""
    help_text = help_text.replace(ENGLISH_HINT, "")
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


def _typed_values(path: str) -> tuple[str, ...]:
    """Values a screen lists as one types them: those of ``roomscope config``."""
    if path != "roomscope config":
        return ()
    from roomscope.interpretation import available_profiles

    return (*available_profiles(), "auto", "on", "off", "system", "light", "dark")


def test_every_help_screen_is_chinese(zh_cli: None) -> None:
    texts = _help_texts()
    assert len(texts) >= 15
    for path, text in texts.items():
        assert text.startswith("用法："), path
        found = english_words(_prose(text), values=_typed_values(path))
        assert found == [], f"{path}: {found}"
    root = texts["roomscope"]
    assert "命令：" in root and "选项" in root and "显示此帮助信息并退出" in root


def _everything_shown(help_text: str) -> str:
    """The whole help screen, usage line and placeholders included, without
    what a user types as it is: option names and the values of a choice list
    ({text,json}); commands are removed by english_words()."""
    text = re.sub(r"\{[^{}\s]*\}", " ", help_text.replace(ENGLISH_HINT, ""))
    # Command names in the command lists ("    analyze-ir  分析…").
    text = re.sub(r"(?m)^( +)[a-z][a-z-]*(?= {2,}\S)", r"\1", text)
    return re.sub(r"(?<![\w.-])--?[A-Za-z][\w-]*", " ", text)


def test_usage_lines_and_placeholders_are_chinese_too(zh_cli: None) -> None:
    """The usage line and the option list showed DIR, WAV, N, TEXT, <command>…"""
    texts = _help_texts()
    for path, text in texts.items():
        found = english_words(_everything_shown(text), values=_typed_values(path))
        assert found == [], f"{path}: {found}"
    assert texts["roomscope"].startswith("用法：roomscope [-h] [--version] [--lang 语言]")
    assert "<命令> ..." in texts["roomscope"].split("\n\n", 1)[0]
    assert texts["roomscope project add"].startswith(
        "用法：roomscope project add 项目 会话 --position 标签 [选项]"
    )
    analyze = texts["roomscope analyze"]
    for shown in ("--recording WAV文件", "--sweep 文件", "--out 目录", "--channel 声道"):
        assert shown in analyze, shown
    # The help says 1/N: the smoothing placeholder keeps its letter.
    assert re.search(r"--smoothing N +分数倍频程平滑 1/N", analyze)
    assert "--band 下限 上限" in texts["roomscope analyze-ir"]
    assert "--input-device 序号" in texts["roomscope measure"]
    assert "--sources 数量" in texts["roomscope project average"]


def _help_columns(text: str) -> set[int]:
    """Display columns where the help of an option starts, in one screen."""
    from roomscope.cli.console import cell_width

    columns: set[int] = set()
    for line in text.splitlines():
        found = re.match(r"^(  \S.*?\S  +)\S", line)
        if found and not line.startswith("  roomscope "):
            columns.add(cell_width(found.group(1)))
        elif re.match(r"^ {6,}\S", line):
            columns.add(len(line) - len(line.lstrip()))
    return columns


def test_option_help_lines_up_with_chinese_placeholders(zh_cli: None) -> None:
    """argparse pads with %-*s, which counts a Chinese character as one column."""
    for path, text in _help_texts().items():
        if path == "roomscope":
            continue  # the grouped command list has its own column
        # One column per screen, except the choice lists argparse cannot wrap;
        # the list of settings below the options has its own.
        options = text.split("\n设置项：\n", 1)[0]
        shown = "\n".join(line for line in options.splitlines() if "{" not in line)
        assert len(_help_columns(shown)) <= 1, (path, _help_columns(shown), text)


def test_argparse_errors_are_chinese(zh_cli: None, capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        main(["--lang", "zh_CN", "measure"])
    err = capsys.readouterr().err
    assert "错误" in err and "缺少必需的参数" in err, err
    with pytest.raises(SystemExit):
        main(["--lang", "zh_CN", "analyze", "--profile", "nope"])
    err = capsys.readouterr().err
    assert "无效选项" in err, err


@pytest.mark.parametrize(
    ("argv", "chinese", "english"),
    [
        (
            ["project"],
            "缺少必需的参数：{init,add,average,show}",
            "the following arguments are required: {init,add,average,show}",
        ),
        (["session"], "缺少必需的参数：{bundle}", "the following arguments are required: {bundle}"),
        (
            ["schema"],
            "缺少必需的参数：{result,session,comparison,project,sidecar}",
            "the following arguments are required: {result,session,comparison,project,sidecar}",
        ),
        (
            ["schema", "bad"],
            "参数 {result,session,comparison,project,sidecar}：无效选项：'bad'",
            "argument {result,session,comparison,project,sidecar}: invalid choice: 'bad'",
        ),
        (["show"], "缺少必需的参数：路径", "the following arguments are required: path"),
        (
            ["analyze-ir", "--ir", "x.wav", "--band", "20"],
            "参数 --band：需要 2 个参数值",
            "argument --band: expected 2 arguments",
        ),
        (
            ["devices", "--probe=yes"],
            "参数 --probe：该选项不接受值（给出了 'yes'）",
            "argument --probe: ignored explicit argument 'yes'",
        ),
        (
            ["sweep", "--out", "x.wav", "--sample-rate", "abc"],
            "参数 --sample-rate：无效的整数值：'abc'",
            "argument --sample-rate: invalid int value: 'abc'",
        ),
        (
            ["sweep", "--out", "x.wav", "--duration", "long"],
            "参数 --duration：无效的数字值：'long'",
            "argument --duration: invalid float value: 'long'",
        ),
    ],
)
def test_every_argparse_error_is_translated(
    zh_cli: None,
    capsys: pytest.CaptureFixture[str],
    argv: list[str],
    chinese: str,
    english: str,
) -> None:
    """In Chinese, "expected 2 arguments", "ignored explicit argument" and the
    type in "invalid int value" stayed English; a missing project or session
    action was named by its internal dest (project_command)."""
    for lang, expected in (("zh_CN", chinese), ("en", english)):
        with pytest.raises(SystemExit) as exc:
            main(["--lang", lang, *argv])
        assert exc.value.code == 2
        err = capsys.readouterr().err
        assert expected in " ".join(err.split()), err
        assert "_command" not in err
        if lang == "zh_CN":
            typed = ("bad", "result", "session", "comparison", "project", "sidecar")
            data = ("x.wav", "abc", "long", "yes")
            assert english_words(_everything_shown(err), data=data, values=typed) == []


def test_environment_report_is_chinese(zh_cli: None, capsys: pytest.CaptureFixture[str]) -> None:
    from roomscope.audio.backend import get_backend

    assert main(["--lang", "zh_CN", "--backend", "fake", "doctor"]) == 0
    out = capsys.readouterr().out
    devices = tuple(d.name for d in get_backend("fake").list_devices())
    # Package names, versions and the platform string are data.
    prose = "\n".join(
        line
        for line in out.splitlines()
        if not re.match(r"^\s+[\w-]+\s{2,}\S", line) and not line.startswith("Python ")
    )
    # The settings are named in Chinese; their stored values are shown as
    # roomscope config takes them.
    assert "界面语言" in out and "roomscope config" in out
    typed = ("auto", "generic", "system", "on", "off", "portaudio", "fake")
    assert english_words(prose, data=devices, values=typed) == [], out


def _take(tmp_path: Path, rt60_s: float, name: str) -> Path:
    from roomscope.io.wav import read_wav, write_wav

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
    from roomscope.io.wav import read_wav, write_wav

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


@pytest.mark.parametrize(
    ("lang", "room", "position", "microphone"),
    [
        ("en", "Synthetic demo room", "A: close to the desk and the side wall", "simulated omni"),
        ("zh_CN", "合成演示房间", "A：靠近桌面和侧墙", "模拟全指向话筒"),
    ],
)
def test_the_demo_names_its_room_in_the_interface_language(
    zh_cli: None,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    lang: str,
    room: str,
    position: str,
    microphone: str,
) -> None:
    """``show`` of a Chinese demo printed "Synthetic demo room" and
    "A: close to the desk and the side wall": names a user would have typed
    in their own language, so the demo writes them in the interface's."""
    out_dir = tmp_path / "demo"
    assert main(["--lang", lang, "demo", "--out", str(out_dir)]) == 0
    session = json.loads((out_dir / "position-a" / "session.json").read_text(encoding="utf-8"))
    assert (session["room_name"], session["measurement_position"]) == (room, position)
    assert session["microphone_name"] == microphone
    assert session["notes"].startswith("SYNTHETIC DEMO")  # the marker stays as it is
    capsys.readouterr()
    assert main(["--lang", lang, "show", str(out_dir / "position-a")]) == 0
    shown = capsys.readouterr().out
    assert room in shown and position in shown and microphone in shown
    if lang == "zh_CN":
        prose = "\n".join(line for line in shown.splitlines() if str(tmp_path) not in line)
        assert english_words(prose) == [], shown
