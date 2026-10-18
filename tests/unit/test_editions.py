"""Editions (docs/EDITIONS.md).

Only the Desktop Edition (GUI + the ``reverbscope`` command line) is built;
packaging/reverbscope.spec refuses ``REVERBSCOPE_PACKAGE=terminal``. The
standalone Terminal Edition's packaging, gate and license bundle are gone.
The run-time code that still recognises a ``"package": "terminal"`` marker
(``reverbscope.edition``, kept for bundles already downloaded) is covered
below until a follow-up removes it.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from reverbscope import edition
from reverbscope.cli.main import main
from reverbscope.i18n import activate

ROOT = Path(__file__).resolve().parents[2]
TERMINAL_SENTENCE = (
    "This is the Terminal Edition of ReverbScope. Install the Desktop Edition to use the GUI."
)
TERMINAL_SENTENCE_ZH = "当前安装的是 ReverbScope 终端版。如需图形界面，请安装桌面版。"


@pytest.fixture
def terminal(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Path]:
    """This process behaves as the Terminal Edition bundle."""
    monkeypatch.setenv("REVERBSCOPE_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(edition, "package", lambda build_info=None: edition.TERMINAL_PACKAGE)
    monkeypatch.chdir(tmp_path)
    try:
        yield tmp_path
    finally:
        activate("en")


def _run(argv: list[str], capsys: pytest.CaptureFixture[str]) -> tuple[int, str, str]:
    capsys.readouterr()
    try:
        code = main(argv)
    except SystemExit as exc:
        code = int(exc.code or 0)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


# --- The edition marker ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ({"version": "0.4.1", "commit": "abc", "package": "terminal"}, "terminal"),
        ({"version": "0.4.1", "commit": "abc", "package": "desktop"}, "desktop"),
        ({"version": "0.4.1", "commit": "abc"}, None),  # a bundle from before the editions
        ({"package": "server"}, None),  # not an edition ReverbScope knows
        ([], None),
    ],
)
def test_package_reads_build_info(tmp_path: Path, content: object, expected: str | None) -> None:
    info = tmp_path / "build_info.json"
    info.write_text(json.dumps(content), encoding="utf-8")
    assert edition.package(info) == expected


def test_a_source_checkout_is_neither_edition() -> None:
    assert edition.package(Path("/nonexistent/build_info.json")) is None
    assert not edition.is_terminal_package()


def test_the_spec_builds_only_the_desktop_edition() -> None:
    spec = (ROOT / "packaging" / "reverbscope.spec").read_text(encoding="utf-8")
    assert 'os.environ.get("REVERBSCOPE_PACKAGE", "desktop")' in spec
    assert 'if PACKAGE != "desktop":' in spec  # REVERBSCOPE_PACKAGE=terminal is refused
    assert '"package": PACKAGE' in spec  # build_info.json records it
    assert "TERMINAL" not in spec
    assert 'name="reverbscope",' in spec
    assert 'if sys.platform != "darwin":' in spec  # the windowed launcher
    assert 'if sys.platform == "darwin":' in spec  # the .app
    assert not (ROOT / "packaging" / "windows" / "terminal").exists()


# --- The command line without a GUI ------------------------------------------------------


@pytest.mark.parametrize(
    ("lang", "sentence"), [("en", TERMINAL_SENTENCE), ("zh_CN", TERMINAL_SENTENCE_ZH)]
)
def test_gui_in_the_terminal_edition_is_a_sentence_not_a_traceback(
    terminal: Path, capsys: pytest.CaptureFixture[str], lang: str, sentence: str
) -> None:
    code, out, err = _run(["--lang", lang, "gui"], capsys)
    assert code == 2 and out == ""
    flat = "".join(err.split()) if lang == "zh_CN" else " ".join(err.split())
    assert ("".join(sentence.split()) if lang == "zh_CN" else sentence) in flat
    assert edition.RELEASES_URL in err
    assert "Traceback" not in err and "PySide6" not in err


def test_the_terminal_edition_never_imports_the_gui(
    terminal: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """reverbscope.ui is not in the bundle: an import of it would be a crash."""
    for name in list(sys.modules):
        if name == "reverbscope.ui" or name.startswith("reverbscope.ui."):
            monkeypatch.delitem(sys.modules, name)
    monkeypatch.setitem(sys.modules, "reverbscope.ui", None)
    for argv in (["gui"], ["demo"], [], ["--backend", "fake", "doctor"]):
        code, _out, err = _run(argv, capsys)
        assert "Traceback" not in err, argv
        assert code in (0, 2), (argv, err)


def test_home_and_demo_point_the_terminal_edition_at_the_desktop_download(
    terminal: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _code, _out, home = _run([], capsys)
    assert "ReverbScope Terminal Edition" in home
    assert "reverbscope doctor" in home and "reverbscope gui" not in home
    code, demo, _err = _run(["demo"], capsys)
    assert code == 0
    assert "Desktop Edition" in demo and edition.RELEASES_URL in demo
    assert "reverbscope gui" not in demo and "pip install" not in demo


def test_saved_next_steps_in_the_terminal_edition(
    terminal: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, _err = _run(
        ["--backend", "fake", "measure", "--out", "m", "--duration", "1", "--post-silence", "1"],
        capsys,
    )
    assert code == 0
    steps = out[out.index("Next steps") :]
    assert edition.RELEASES_URL in steps and "reverbscope gui" not in steps


def test_doctor_names_the_edition_and_the_missing_gui_libraries(
    terminal: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    import reverbscope.diagnostics as diagnostics

    monkeypatch.setattr(
        diagnostics, "build_info", lambda path=None: {"commit": "abc", "package": "terminal"}
    )
    monkeypatch.setattr(
        diagnostics,
        "_package_version",
        lambda name, module: (
            None if module in ("matplotlib", "PySide6", "shiboken6", "pyqtgraph") else "1.0"
        ),
    )
    code, out, _err = _run(["--backend", "fake", "doctor"], capsys)
    assert code == 0
    assert "Terminal Edition" in out
    assert out.count("not included (Terminal Edition)") == 4
    code, out, _err = _run(["--format", "json", "--backend", "fake", "doctor"], capsys)
    report = json.loads(out)
    assert report["build"]["package"] == "terminal"
    assert report["packages"]["PySide6_Essentials"] is None
