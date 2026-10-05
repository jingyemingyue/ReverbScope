"""The command line in Simplified Chinese: the root help, every subcommand's
help, argparse's own texts and errors, the environment report and the text
reports of an analysis and a comparison show no English beyond the names in
tests/zh_tokens.py."""

from __future__ import annotations

import argparse
import json
import re
import shutil
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


#: Written in English on purpose: the way back for a reader of English.
ENGLISH_HINT = "English interface: reverbscope config language en"


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
    """Values a screen lists as one types them: the choices of its options
    (--color auto, demo --profile vocal) and the values of ``reverbscope config``."""
    parser = build_parser()
    for name in path.split()[1:]:
        parser = next(
            a for a in parser._actions if isinstance(a, argparse._SubParsersAction)
        ).choices[name]
    values = tuple(
        str(choice)
        for action in parser._actions
        if action.option_strings and action.choices is not None
        for choice in action.choices
    )
    if path == "reverbscope export":
        from reverbscope.io.exporters.registry import available_exporters

        return (*values, *available_exporters())
    if path != "reverbscope config":
        return values
    from reverbscope.interpretation import available_profiles

    return (*values, *available_profiles(), "auto", "on", "off", "system", "light", "dark")


def test_every_help_screen_is_chinese(zh_cli: None) -> None:
    texts = _help_texts()
    assert len(texts) >= 15
    for path, text in texts.items():
        assert text.startswith("用法："), path
        found = english_words(_prose(text), values=_typed_values(path))
        assert found == [], f"{path}: {found}"
    root = texts["reverbscope"]
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
    assert texts["reverbscope"].startswith("用法：reverbscope [-h] [--version] [--lang 语言]")
    assert "<命令> ..." in texts["reverbscope"].split("\n\n", 1)[0]
    assert texts["reverbscope project add"].startswith(
        "用法：reverbscope project add 项目 会话 --position 标签 [选项]"
    )
    analyze = texts["reverbscope analyze"]
    for shown in ("--recording WAV文件", "--sweep 文件", "--out 目录", "--channel 声道"):
        assert shown in analyze, shown
    # The help says 1/N: the smoothing placeholder keeps its letter.
    assert re.search(r"--smoothing N +分数倍频程平滑 1/N", analyze)
    assert "--band 下限 上限" in texts["reverbscope analyze-ir"]
    assert "--input-device 序号" in texts["reverbscope measure"]
    assert "--sources 数量" in texts["reverbscope project average"]


def _help_columns(text: str) -> set[int]:
    """Display columns where the help of an option starts, in one screen."""
    from reverbscope.cli.console import cell_width

    columns: set[int] = set()
    for line in text.splitlines():
        found = re.match(r"^(  \S.*?\S  +)\S", line)
        if found and not line.startswith("  reverbscope "):
            columns.add(cell_width(found.group(1)))
        elif re.match(r"^ {6,}\S", line):
            columns.add(len(line) - len(line.lstrip()))
    return columns


def test_option_help_lines_up_with_chinese_placeholders(zh_cli: None) -> None:
    """argparse pads with %-*s, which counts a Chinese character as one column."""
    for path, text in _help_texts().items():
        if path == "reverbscope":
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
            ["project", "add"],
            "缺少必需的参数：项目、会话、--position",
            "the following arguments are required: project, session, --position",
        ),
        (
            ["project", "bogus"],
            "无效选项：'bogus'（可选：'init'、'add'、'average'、'show'）",
            "invalid choice: 'bogus' (choose from 'init', 'add', 'average', 'show')",
        ),
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
            typed = ("bad", "bogus", "result", "session", "comparison", "project", "sidecar")
            typed += ("init", "add", "average", "show")
            data = ("x.wav", "abc", "long", "yes")
            assert english_words(_everything_shown(err), data=data, values=typed) == []


def _options_with_choices(lang: str) -> list[tuple[str, argparse.Action]]:
    activate(lang)
    found: list[tuple[str, argparse.Action]] = []

    def walk(parser: argparse.ArgumentParser, path: str) -> None:
        for action in parser._actions:
            if isinstance(action, argparse._SubParsersAction):
                for name, sub in action.choices.items():
                    walk(sub, f"{path} {name}")
            elif action.option_strings and action.choices is not None:
                found.append((f"{path} {action.option_strings[0]}", action))

    walk(build_parser(), "reverbscope")
    return found


@pytest.mark.parametrize("lang", ["zh_CN", "en"])
def test_an_option_whose_placeholder_hides_its_choices_names_them(zh_cli: None, lang: str) -> None:
    """The Chinese --color help said 默认自动 … 始终着色或从不着色 under the
    placeholder 何时, so a reader typed --color 始终 and was refused."""
    hidden = [(name, a) for name, a in _options_with_choices(lang) if a.metavar is not None]
    assert hidden, "no option hides its choices behind a placeholder"
    for name, action in hidden:
        for choice in action.choices or ():
            assert re.search(rf"(?<![\w-]){re.escape(str(choice))}(?![\w-])", str(action.help)), (
                name,
                choice,
                action.help,
            )


@pytest.mark.parametrize("lang", ["zh_CN", "en"])
def test_a_default_of_an_option_with_choices_is_the_value_to_type(zh_cli: None, lang: str) -> None:
    """demo --help said （默认：人声） (English: Vocals) for --profile vocal."""
    for name, action in _options_with_choices(lang):
        named = re.search(r"(?:default|默认)[:：]?\s*([\w.-]+)", str(action.help))
        if named and action.default is not None and named.group(1).isascii():
            assert named.group(1) == str(action.default), (name, action.help)
    demo = dict(_options_with_choices(lang))["reverbscope demo --profile"]
    assert "vocal" in str(demo.help), demo.help


@pytest.mark.parametrize(
    ("argv", "chinese", "english"),
    [
        (
            ["sweep", "--out", "x.wav", "--start-hz", "30000"],
            "--end-hz 必须大于 --start-hz",
            "--end-hz must be greater than --start-hz",
        ),
        (
            ["sweep", "--out", "x.wav", "--duration", "-1"],
            "--duration 必须至少为 0.5 s",
            "--duration must be >= 0.5 s",
        ),
        (
            ["analyze", "--recording", "r.wav", "--sweep", "s.wav", "--temperature", "80"],
            "--temperature 必须在 -20 °C 到 50 °C 之间",
            "--temperature must be between -20 °C and 50 °C",
        ),
        (
            ["analyze", "--recording", "r.wav", "--sweep", "s.wav", "--mic-height", "1"],
            "--mic-height 需要同时给出 --speaker-distance",
            "--mic-height needs --speaker-distance",
        ),
    ],
)
def test_a_refused_setting_names_the_option_that_set_it(
    zh_cli: None,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    argv: list[str],
    chinese: str,
    english: str,
) -> None:
    """The errors named the settings' fields ("end_hz must be greater than
    start_hz", "duration_s 必须 >= 0.5 s"), not the options the user typed."""
    monkeypatch.chdir(tmp_path)
    # The analysis settings are checked once the files are read.
    assert main(["sweep", "--out", "s.wav", "--duration", "1"]) == 0
    shutil.copyfile("s.wav", "r.wav")
    capsys.readouterr()
    for lang, expected in (("zh_CN", chinese), ("en", english)):
        assert main(["--lang", lang, *argv]) != 0
        err = " ".join(capsys.readouterr().err.split())
        assert expected in err, err
        assert not re.search(r"\b[a-z]+_(hz|s|c|m)\b", err), err
    assert not (tmp_path / "x.wav").exists()


@pytest.mark.parametrize(
    "command",
    [
        ["analyze", "--recording", "r.wav", "--sweep", "s.wav"],
        ["analyze-ir", "--ir", "r.wav", "--band", "100", "8000"],
        ["project", "init"],
    ],
)
def test_an_out_that_is_a_file_is_refused_before_any_work(
    zh_cli: None,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    command: list[str],
) -> None:
    """analyze ran the whole analysis and then failed with the system's
    English "File exists" inside the Chinese error; project init likewise."""
    from reverbscope.core import pipeline

    monkeypatch.chdir(tmp_path)
    assert main(["sweep", "--out", "s.wav", "--duration", "1"]) == 0
    shutil.copyfile("s.wav", "r.wav")
    Path("victim.wav").write_bytes(b"keep")
    capsys.readouterr()

    def never(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("analysed before the --out check")

    monkeypatch.setattr(pipeline, "analyze", never)
    monkeypatch.setattr(pipeline, "analyze_impulse_response", never)
    assert main(["--lang", "zh_CN", *command, "--out", "victim.wav"]) == 1
    err = " ".join(capsys.readouterr().err.split())
    assert "victim.wav 是一个文件；--out 需要一个用来保存" in err, err
    assert "File exists" not in err
    named = "project init" if command[0] == "project" else command[0]
    assert f"reverbscope {named} --out" in err
    assert Path("victim.wav").read_bytes() == b"keep"


def test_an_operating_system_error_is_explained_in_chinese(
    zh_cli: None,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Python gives OSError.strerror in English on Linux and macOS."""
    import errno

    from reverbscope.io import project_store

    def refuse(path: object, _project: object) -> None:
        raise PermissionError(errno.EACCES, "Permission denied", str(path))

    monkeypatch.setattr(project_store, "save_project", refuse)
    assert main(["--lang", "zh_CN", "project", "init", "--out", str(tmp_path / "p")]) == 1
    err = capsys.readouterr().err
    assert "没有权限：" in err and "Permission denied" not in err


def test_chinese_lines_join_their_parts_with_chinese_punctuation(
    zh_cli: None, capsys: pytest.CaptureFixture[str]
) -> None:
    """ "扬声器高度: 不可比较", "输入, 输出", "两侧都有：110 Hz; 消失：…": the
    renderers joined translated phrases with ASCII colons, commas and
    semicolons that never reached the catalog."""
    from reverbscope.cli.console import Console
    from reverbscope.cli.render import _delta_statuses
    from reverbscope.models.comparison import MetricDelta
    from reverbscope.models.result import Validity

    assert main(["--lang", "zh_CN", "--backend", "fake", "devices"]) == 0
    assert "输入、输出" in capsys.readouterr().out
    assert main(["--lang", "zh_CN", "--backend", "fake", "doctor", "--probe"]) == 0
    assert "默认输入、默认输出" in capsys.readouterr().out
    assert main(["--lang", "zh_CN", "--backend", "fake", "devices", "--host-apis"]) == 0
    assert "fake：" in capsys.readouterr().out
    deltas = [
        MetricDelta(f"placement.{name}", None, None, Validity.NOT_COMPARABLE, reason="")
        for name in ("source_height_m", "ceiling_height_m")
    ]
    text = "\n".join(_delta_statuses(Console(), deltas))
    assert "扬声器高度、" in text and "：不可比较" in text
    assert not re.search(r"[\u4e00-\u9fff][,;:] ", text), text


def test_the_export_format_default_is_the_value_to_type(zh_cli: None) -> None:
    """导出器名称（默认 CSV）, but `--format CSV` is refused: the exporter is csv."""
    export = _help_texts()["reverbscope export"]
    assert "（默认 csv）" in export and "CSV" not in export


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
    # The settings are named in Chinese; their stored values are shown as
    # reverbscope config takes them.
    assert "界面语言" in out and "reverbscope config" in out
    typed = ("auto", "generic", "system", "on", "off", "portaudio", "fake")
    assert english_words(prose, data=devices, values=typed) == [], out


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
