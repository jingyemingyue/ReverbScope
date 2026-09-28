"""First-run experience and the look of the command line, pinned by golden files.

``roomscope demo`` (synthetic data through the real pipeline), the home
screen, next steps, the error block, and the terminal matrix: English and
Chinese at 80 and 60 columns, NO_COLOR, TERM=dumb, redirected stdout, a
cp1252 stream and JSON on stdout.

Golden files live in ``tests/golden``. Measured numbers are replaced by ``#``
before the comparison, so a last-digit difference between platforms (numpy
on Accelerate or OpenBLAS) does not fail the layout test. Regenerate with
``ROOMSCOPE_UPDATE_GOLDEN=1 pytest tests/unit/test_cli_ux.py`` and review the
diff like code.
"""

from __future__ import annotations

import io
import json
import os
import re
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from roomscope import __version__
from roomscope.cli.console import Console, cell_width
from roomscope.cli.main import main
from roomscope.demo import DEMO_MODE, DemoRun, run_demo
from roomscope.i18n import activate
from tests.zh_tokens import english_words

GOLDEN = Path(__file__).resolve().parent.parent / "golden"
UPDATE = bool(os.environ.get("ROOMSCOPE_UPDATE_GOLDEN"))
ESC = "\x1b["
_NUMBER = re.compile(r"(?<![A-Za-z0-9.])[-+]?\d+(?:\.\d+)?")
_DATE = re.compile(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2} [+-]\d{2}:\d{2}")


def _normalise(text: str) -> str:
    """Numbers and dates to ``#``; names with digits (T20, RT60, cp1252) stay."""
    text = text.replace(__version__, "<version>")
    text = _DATE.sub("<date>", text)
    return _NUMBER.sub("#", text)


def _golden(name: str, text: str) -> None:
    path = GOLDEN / f"{name}.txt"
    if UPDATE:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
        return
    assert path.is_file(), f"missing {path}; run with ROOMSCOPE_UPDATE_GOLDEN=1"
    expected = path.read_text(encoding="utf-8")
    assert text == expected, f"{name} changed; run with ROOMSCOPE_UPDATE_GOLDEN=1 and review"


@pytest.fixture
def cli(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> Iterator[tuple[Path, pytest.MonkeyPatch]]:
    """A clean terminal: its own home, no colour overrides, relative paths."""
    monkeypatch.setenv("ROOMSCOPE_HOME", str(tmp_path / "home"))
    for name in ("NO_COLOR", "FORCE_COLOR", "TERM", "COLUMNS", "PYTHONIOENCODING"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)
    try:
        yield tmp_path, monkeypatch
    finally:
        activate("en")


@pytest.fixture(scope="module")
def demo_run(tmp_path_factory: pytest.TempPathFactory) -> DemoRun:
    return run_demo(tmp_path_factory.mktemp("demo") / "out")


def _run(argv: list[str], capsys: pytest.CaptureFixture[str]) -> tuple[int, str, str]:
    capsys.readouterr()
    try:
        code = main(argv)
    except SystemExit as exc:
        code = int(exc.code or 0)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


# --- The demo --------------------------------------------------------------------------


def test_the_demo_finds_the_problems_it_says_it_shows(demo_run: DemoRun) -> None:
    """Every sentence under "What the demo shows" must be true of the analysis."""
    a, b = (take.result for take in demo_run.takes)
    assert any(abs(r.delay_ms - 2.4) < 0.3 for r in a.reflections.reflections)
    assert not any(abs(r.delay_ms - 2.4) < 0.3 for r in b.reflections.reflections)
    for result in (a, b):
        assert any(abs(c.frequency_hz - 110.0) < 5.0 for c in result.resonances.candidates)
    assert any(h.detected for h in a.noise.hum)
    assert a.noise.rms_dbfs is not None and b.noise.rms_dbfs is not None
    assert b.noise.rms_dbfs < a.noise.rms_dbfs - 6.0
    assert "disappeared" in {m.status for m in demo_run.comparison.reflections}
    assert "matched" in {m.status for m in demo_run.comparison.resonances}


def test_demo_sessions_are_marked_synthetic(demo_run: DemoRun) -> None:
    for take in demo_run.takes:
        session = json.loads((take.session_dir / "session.json").read_text(encoding="utf-8"))
        assert session["mode"] == DEMO_MODE
        assert "SYNTHETIC" in session["notes"]
        assert take.recording_path.is_file()
    assert demo_run.sweep_path.is_file()
    assert demo_run.comparison_path.is_file()


def test_demo_walkthrough_and_its_next_steps_work(
    cli: tuple[Path, pytest.MonkeyPatch], capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, err = _run(["demo"], capsys)
    assert code == 0, err
    assert "Synthetic data" in out and "not a measurement" in out
    assert "Comparison A → B" in out and "What the demo shows" in out
    assert ESC not in out and "\r" not in out and err == ""
    # The commands it suggests run as printed.
    for line in out.splitlines():
        command = line.strip()
        if command.startswith(("roomscope show", "roomscope compare")):
            code, shown, _err = _run(command.split()[1:], capsys)
            assert code == 0, command
            assert "At a glance" in shown
    # Running it again replaces its own folder.
    assert _run(["demo"], capsys)[0] == 0


def test_demo_never_overwrites_a_folder_it_did_not_write(
    cli: tuple[Path, pytest.MonkeyPatch], capsys: pytest.CaptureFixture[str]
) -> None:
    root, _mp = cli
    mine = root / "roomscope-demo"
    mine.mkdir()
    (mine / "notes.txt").write_text("mine", encoding="utf-8")
    code, out, err = _run(["demo"], capsys)
    assert code == 2 and out == ""
    assert "already exists" in err and "Nothing was changed" in err
    assert sorted(p.name for p in mine.iterdir()) == ["notes.txt"]


def test_demo_refuses_json_and_leaves_stdout_empty(
    cli: tuple[Path, pytest.MonkeyPatch], capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, err = _run(["--format", "json", "demo"], capsys)
    assert code == 2 and out == ""
    assert "--format json show" in err


def test_demo_on_a_cli_only_install(
    cli: tuple[Path, pytest.MonkeyPatch], capsys: pytest.CaptureFixture[str]
) -> None:
    """Without PySide6 the demo runs and points at the desktop app instead of `gui`."""
    _root, monkeypatch = cli
    monkeypatch.setattr("roomscope.ui.app.pyside6_import_error", lambda: "no PySide6")
    code, out, _err = _run(["demo"], capsys)
    assert code == 0
    assert 'pip install "PySide6_Essentials>=6.6"' in out
    assert "     roomscope gui" not in out


# --- Golden files: English and Chinese, 80 and 60 columns -------------------------------


@pytest.mark.parametrize("lang", ["en", "zh_CN"])
@pytest.mark.parametrize("columns", [80, 60])
def test_golden_demo(
    cli: tuple[Path, pytest.MonkeyPatch],
    capsys: pytest.CaptureFixture[str],
    lang: str,
    columns: int,
) -> None:
    _root, monkeypatch = cli
    monkeypatch.setenv("COLUMNS", str(columns))
    code, out, _err = _run(["--lang", lang, "demo"], capsys)
    assert code == 0
    assert all(cell_width(line) <= columns for line in out.splitlines() if "roomscope " not in line)
    _golden(f"demo-{lang}-{columns}", _normalise(out))


@pytest.mark.parametrize("lang", ["en", "zh_CN"])
@pytest.mark.parametrize("columns", [80, 60])
def test_golden_sweep_next_steps(
    cli: tuple[Path, pytest.MonkeyPatch],
    capsys: pytest.CaptureFixture[str],
    lang: str,
    columns: int,
) -> None:
    _root, monkeypatch = cli
    monkeypatch.setenv("COLUMNS", str(columns))
    code, out, _err = _run(["--lang", lang, "sweep", "--out", "sweep.wav"], capsys)
    assert code == 0
    assert all(cell_width(line) <= columns for line in out.splitlines() if "roomscope " not in line)
    _golden(f"sweep-{lang}-{columns}", out)


@pytest.mark.parametrize("lang", ["en", "zh_CN"])
def test_golden_home_screen(
    cli: tuple[Path, pytest.MonkeyPatch], capsys: pytest.CaptureFixture[str], lang: str
) -> None:
    """Bare ``roomscope``: a short home screen; still the usage error's exit code."""
    _root, monkeypatch = cli
    monkeypatch.setenv("COLUMNS", "80")
    code, out, err = _run(["--lang", lang], capsys)
    assert code == 2 and out == ""
    assert "roomscope demo" in err and "roomscope --help" in err
    assert len(err.splitlines()) <= 10
    _golden(f"home-{lang}", _normalise(err))


@pytest.mark.parametrize("lang", ["en", "zh_CN"])
def test_golden_measure_plan_with_the_fake_interface(
    cli: tuple[Path, pytest.MonkeyPatch], capsys: pytest.CaptureFixture[str], lang: str
) -> None:
    _root, monkeypatch = cli
    monkeypatch.setenv("COLUMNS", "80")
    argv = ["--lang", lang, "--backend", "fake", "measure", "--out", "m"]
    code, out, err = _run([*argv, "--duration", "1", "--post-silence", "1"], capsys)
    assert code == 0
    # The plan, the checks, the safety note and the take; the report follows.
    head = out[: out.index("RoomScope " + ("analysis" if lang == "en" else "分析"))]
    assert len(err.strip().splitlines()) == 1  # one milestone in a log, no percentages
    _golden(f"measure-plan-{lang}", _normalise(head))


@pytest.mark.parametrize("lang", ["en", "zh_CN"])
def test_golden_errors(
    cli: tuple[Path, pytest.MonkeyPatch], capsys: pytest.CaptureFixture[str], lang: str
) -> None:
    """User errors: one block with commands to try, no traceback, the documented codes."""
    _root, monkeypatch = cli
    monkeypatch.setenv("COLUMNS", "80")
    blocks = []
    for argv, expected in (
        (["analyze", "--recording", "take.wav", "--sweep", "sweep.wav"], 1),
        (["sweep"], 2),
        (["sweep", "--out", "x.wav", "--duration", "long"], 2),
        (["--backend", "fake", "measure", "--out", "m", "--input-channel", "9"], 1),
        (["show", "missing-session"], 1),
    ):
        code, out, err = _run(["--lang", lang, *argv], capsys)
        assert code == expected, (argv, err)
        assert out == "" and "Traceback" not in err
        blocks.append(err)
    _golden(f"errors-{lang}", "\n".join(blocks))


def test_the_chinese_demo_and_home_show_no_english_prose(
    cli: tuple[Path, pytest.MonkeyPatch], capsys: pytest.CaptureFixture[str]
) -> None:
    for argv in (["--lang", "zh_CN", "demo"], ["--lang", "zh_CN"]):
        _code, out, err = _run(argv, capsys)
        text = "\n".join(
            line
            for line in (out + err).splitlines()
            # Paths and the pip command are data the user types, not prose.
            if "roomscope-demo" not in line and "pip install" not in line
        )
        assert english_words(text) == [], (argv, text)


# --- The terminal matrix -----------------------------------------------------------------


class _Tty(io.StringIO):
    def __init__(self, encoding: str = "utf-8") -> None:
        super().__init__()
        self._encoding = encoding

    def isatty(self) -> bool:
        return True

    @property
    def encoding(self) -> str:  # type: ignore[override]
        return self._encoding


def _demo_on(
    stream: io.StringIO, env: dict[str, str], monkeypatch: pytest.MonkeyPatch, *argv: str
) -> str:
    monkeypatch.setattr("roomscope.cli.console._enable_windows_vt", lambda _stream: True)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(sys, "stdout", stream)
    assert main([*argv, "demo"]) == 0
    return stream.getvalue()


def test_a_terminal_gets_colour(cli: tuple[Path, pytest.MonkeyPatch]) -> None:
    _root, monkeypatch = cli
    assert ESC in _demo_on(_Tty(), {}, monkeypatch)


@pytest.mark.parametrize(
    "env", [{"NO_COLOR": "1"}, {"TERM": "dumb"}], ids=["NO_COLOR", "TERM=dumb"]
)
def test_no_color_and_dumb_terminals_get_plain_text(
    cli: tuple[Path, pytest.MonkeyPatch], env: dict[str, str]
) -> None:
    _root, monkeypatch = cli
    text = _demo_on(_Tty(), env, monkeypatch)
    assert ESC not in text and "\r" not in text
    assert "✓" in text  # the symbols stay: colour was never the only signal


def test_force_color_and_color_always_style_a_pipe(cli: tuple[Path, pytest.MonkeyPatch]) -> None:
    _root, monkeypatch = cli
    assert ESC in _demo_on(io.StringIO(), {"FORCE_COLOR": "1"}, monkeypatch)
    assert ESC not in _demo_on(io.StringIO(), {"FORCE_COLOR": "1"}, monkeypatch, "--color", "never")


def test_redirected_output_is_plain_and_stable(cli: tuple[Path, pytest.MonkeyPatch]) -> None:
    _root, monkeypatch = cli
    text = _demo_on(io.StringIO(), {}, monkeypatch)
    assert ESC not in text and "\r" not in text
    assert all(cell_width(line) <= 100 for line in text.splitlines() if "roomscope " not in line)


def test_a_cp1252_stream_gets_ascii_symbols_and_never_fails(
    cli: tuple[Path, pytest.MonkeyPatch],
) -> None:
    """A legacy Windows code page: ASCII status words, no UnicodeEncodeError."""
    _root, monkeypatch = cli
    raw = io.BytesIO()
    stream = io.TextIOWrapper(raw, encoding="cp1252", errors="strict", newline="\n")
    monkeypatch.setenv("PYTHONIOENCODING", "cp1252")  # the user chose it: keep it
    monkeypatch.setattr(sys, "stdout", stream)
    assert main(["demo"]) == 0
    stream.flush()
    text = raw.getvalue().decode("cp1252")
    assert "[OK]" in text and "[WARN]" in text and "->" in text
    assert "✓" not in text and "→" not in text
    _golden("demo-en-cp1252", _normalise(text))


def test_a_narrow_encoding_replaces_what_it_cannot_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Chinese text on a cp1252 terminal: replaced, never a crash after the work."""
    import importlib

    cli_main = importlib.import_module("roomscope.cli.main")

    monkeypatch.delenv("PYTHONIOENCODING", raising=False)
    raw = io.BytesIO()

    class _Console(io.TextIOWrapper):
        def isatty(self) -> bool:
            return True

    stream = _Console(raw, encoding="cp1252", errors="strict", newline="\n")
    monkeypatch.setattr(sys, "stdout", stream)
    cli_main._prepare_streams()
    sys.stdout.write("录音棚 Δ\n")
    stream.flush()
    assert raw.getvalue() == b"??? ?\n"


def test_json_stdout_carries_nothing_but_json(
    cli: tuple[Path, pytest.MonkeyPatch], capsys: pytest.CaptureFixture[str]
) -> None:
    _root, monkeypatch = cli
    assert _run(["demo"], capsys)[0] == 0
    monkeypatch.setenv("FORCE_COLOR", "1")  # even when colour is forced
    for argv in (
        ["--format", "json", "show", "roomscope-demo/position-a"],
        ["--format", "json", "compare", "roomscope-demo/position-a", "roomscope-demo/position-b"],
        ["--format", "json", "--backend", "fake", "devices"],
        ["--format", "json", "--backend", "fake", "measure", "--out", "m", "--duration", "1",
         "--post-silence", "1"],
    ):  # fmt: skip
        code, out, _err = _run(argv, capsys)
        assert code == 0, argv
        json.loads(out)
        assert ESC not in out and "\r" not in out and "Next steps" not in out, argv


# --- Console building blocks -------------------------------------------------------------


def test_steps_keep_commands_whole_and_number_the_text() -> None:
    console = Console(width=40)
    lines = console.steps(
        [
            ("Compare this session with another position measured later:", "roomscope "
             "compare /a/very/long/path/to/session-1 /another/long/path/session-2"),
            ("Open the desktop app:", "roomscope gui"),
        ]
    )  # fmt: skip
    assert lines[0].startswith("  1. ")
    assert any(line.strip().startswith("2. ") for line in lines)
    long = "roomscope compare /a/very/long/path/to/session-1 /another/long/path/session-2"
    assert "     " + long in lines
    assert all(cell_width(line) <= 40 for line in lines if "roomscope" not in line)


def test_commands_stack_on_a_narrow_terminal() -> None:
    items = [("roomscope sweep --out sweep.wav", "Write the test signal to play from your DAW")]
    wide = Console(width=100).commands(items)
    narrow = Console(width=44).commands(items)
    assert len(wide) == 1
    assert narrow[0].strip() == "roomscope sweep --out sweep.wav" and len(narrow) >= 2
