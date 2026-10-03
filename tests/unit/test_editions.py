"""Desktop Edition and Terminal Edition (docs/EDITIONS.md).

The Terminal Edition is the same program built without Qt, PySide6 and
matplotlib (``REVERBSCOPE_PACKAGE=terminal`` in packaging/reverbscope.spec). These
tests cover what that build relies on without building it: the edition
marker in ``build_info.json``, the command line's behaviour when the GUI is
absent, the gate that fails a Terminal bundle with GUI files in it, and the
Terminal license bundle. The frozen builds themselves are checked by
``scripts/smoke_bundle.py --terminal`` in the release workflow.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pytest

from reverbscope import edition
from reverbscope.cli.main import main
from reverbscope.i18n import activate

ROOT = Path(__file__).resolve().parents[2]
TERMINAL_SENTENCE = (
    "This is the Terminal Edition of ReverbScope. Install the Desktop Edition to use the GUI."
)
TERMINAL_SENTENCE_ZH = "当前安装的是 ReverbScope 终端版。如需图形界面，请安装桌面版。"


def _script(name: str) -> ModuleType:
    path = ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"{name}_for_editions", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


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


def test_the_spec_builds_both_editions_and_leaves_the_gui_out_of_one() -> None:
    spec = (ROOT / "packaging" / "reverbscope.spec").read_text(encoding="utf-8")
    assert 'os.environ.get("REVERBSCOPE_PACKAGE", "desktop")' in spec
    assert '"package": PACKAGE' in spec  # build_info.json records it
    excludes = spec[
        spec.index("TERMINAL_EXCLUDES = [") : spec.index("]", spec.index("TERMINAL_EXCLUDES"))
    ]
    for module in ("PySide6", "shiboken6", "reverbscope.ui", "matplotlib"):
        assert f'"{module}"' in excludes, module
    assert 'name="reverbscope-terminal" if TERMINAL else "reverbscope"' in spec
    assert 'if sys.platform != "darwin" and not TERMINAL:' in spec  # no windowed launcher
    assert 'if sys.platform == "darwin" and not TERMINAL:' in spec  # no .app


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
        lambda name, module: None if module in ("matplotlib", "PySide6", "shiboken6") else "1.0",
    )
    code, out, _err = _run(["--backend", "fake", "doctor"], capsys)
    assert code == 0
    assert "Terminal Edition" in out
    assert out.count("not included (Terminal Edition)") == 3
    code, out, _err = _run(["--format", "json", "--backend", "fake", "doctor"], capsys)
    report = json.loads(out)
    assert report["build"]["package"] == "terminal"
    assert report["packages"]["PySide6_Essentials"] is None


# --- The Terminal Edition gate and license bundle ------------------------------------------


def _tree(root: Path, files: list[str]) -> Path:
    for name in files:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x")
    return root


def test_the_terminal_gate_finds_every_kind_of_gui_file(tmp_path: Path) -> None:
    gate = _script("check_bundle_contents")
    root = _tree(
        tmp_path / "reverbscope-terminal",
        [
            "reverbscope",
            "_internal/numpy/core/_multiarray_umath.so",
            "_internal/PySide6/QtCore.abi3.so",
            "_internal/shiboken6/libshiboken6.abi3.so.6.11",
            "_internal/libQt6Core.so.6",
            "_internal/Qt6Gui.dll",
            "_internal/QtWidgets.framework/Versions/A/QtWidgets",
            "_internal/matplotlib/mpl-data/matplotlibrc",
            "_internal/reverbscope/ui/results.pyc",
            # License texts may name Qt; they are not the library.
            "THIRD_PARTY_LICENSES/PySide6_Essentials/LICENSE",
        ],
    )
    found = {path.relative_to(root).as_posix() for path, _what in gate.gui_files(root)}
    assert found == {
        "_internal/PySide6/QtCore.abi3.so",
        "_internal/shiboken6/libshiboken6.abi3.so.6.11",
        "_internal/libQt6Core.so.6",
        "_internal/Qt6Gui.dll",
        "_internal/QtWidgets.framework/Versions/A/QtWidgets",
        "_internal/matplotlib/mpl-data/matplotlibrc",
        "_internal/reverbscope/ui/results.pyc",
    }
    assert gate.check(root, terminal=True)
    assert gate.main(["--root", str(root), "--terminal"]) == 1


def test_a_clean_terminal_tree_passes_with_its_license_bundle(tmp_path: Path) -> None:
    gate = _script("check_bundle_contents")
    root = _tree(
        tmp_path / "reverbscope-terminal",
        ["reverbscope", "_internal/numpy/__init__.pyc", "_internal/libportaudio.so"],
    )
    licenses = root / "THIRD_PARTY_LICENSES"
    (licenses / "_texts").mkdir(parents=True)
    (licenses / "_texts" / "PortAudio-LICENSE.txt").write_text("x", encoding="utf-8")
    (licenses / "INDEX.txt").write_text("unresolved: none\n", encoding="utf-8")
    assert gate.check(root, require_licenses=True, terminal=True) == []
    # The Desktop Edition still needs the Qt license texts.
    assert gate.check(root, require_licenses=True)


def test_the_terminal_license_bundle_has_no_qt(tmp_path: Path) -> None:
    builder = _script("build_license_bundle")
    out = tmp_path / "THIRD_PARTY_LICENSES"
    assert builder.build(out, terminal=True) == []
    names = {path.name for path in out.iterdir()}
    assert {"numpy", "scipy", "soundfile", "sounddevice", "INDEX.txt"} <= names
    assert not {"PySide6", "PySide6_Essentials", "shiboken6", "matplotlib"} & names
    assert sorted(p.name for p in (out / "_texts").iterdir()) == ["PortAudio-LICENSE.txt"]
    assert not (out / "_notices" / "pyside6.txt").exists()
    assert "qt: not included (Terminal Edition)" in (out / "INDEX.txt").read_text(encoding="utf-8")


def test_the_windows_terminal_launcher_opens_a_prompt_in_its_folder() -> None:
    launcher = ROOT / "packaging" / "windows" / "terminal" / "ReverbScope Terminal.cmd"
    text = launcher.read_bytes().decode("ascii")
    assert 'cd /d "%~dp0"' in text and "cmd /k reverbscope.exe" in text
    assert "*.cmd text eol=crlf" in (ROOT / ".gitattributes").read_text(encoding="utf-8")
