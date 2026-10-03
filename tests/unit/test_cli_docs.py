"""Documentation examples are parsed, including commands that would use hardware."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _script() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "check_cli_docs", ROOT / "scripts/check_cli_docs.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def docs(tmp_path: Path) -> Path:
    (tmp_path / "docs").mkdir()
    return tmp_path


def test_repository_cli_examples_match_the_parser() -> None:
    count, errors = _script().check(ROOT)
    assert count > 0
    assert errors == []


def test_parser_checks_hardware_examples_without_running_them(
    docs: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from roomscope.audio import backend, devices
    from roomscope.cli.main import COMMANDS

    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("a documentation syntax check must not run commands or access devices")

    for name in COMMANDS:
        monkeypatch.setitem(COMMANDS, name, forbidden)
    monkeypatch.setattr(backend, "get_backend", forbidden)
    monkeypatch.setattr(devices, "sounddevice_module", forbidden)
    (docs / "README.md").write_text(
        "```bash\nroomscope measure --out take --input-device 2\n"
        "roomscope doctor --probe\nroomscope gui\nroomscope --help\n```\n",
        encoding="utf-8",
    )
    assert _script().check(docs) == (4, [])


def test_comments_quotes_continuations_and_bundle_paths(docs: Path) -> None:
    (docs / "docs/guide.md").write_text(
        "# Example\n```console\n# ignored comment \\\n"
        "$ roomscope analyze --recording 'a take.wav' \\\n"
        '  --sweep sweep.wav --out "a session" # keep the quotes\n'
        '"/a bundle/roomscope" --version\n'
        "./roomscope --help\nroomscope-env/bin/roomscope schema result\n"
        "RoomScope.exe project init --out room --name 'A room'\n```\n"
        "~~~sh\nroomscope project add room take --position A\n~~~\n"
        "```python\nroomscope old-command\n```\n"
        "`roomscope partial-example`\n```bash\necho 'roomscope old-command'\n```\n",
        encoding="utf-8",
    )
    assert _script().check(docs) == (6, [])


@pytest.mark.parametrize(
    ("command", "detail"),
    [
        ("roomscope old-command", "invalid choice"),
        ("roomscope sweep --out sweep.wav --old-option", "unrecognized arguments"),
        ("roomscope sweep", "--out"),
        ("roomscope measure --out take --sample-rate not-a-number", "invalid int value"),
        ("roomscope --format yaml show take", "invalid choice"),
        ("roomscope project add room take", "--position"),
        ("roomscope measure --backend fake --out take", "unrecognized arguments"),
        ("roomscope analyze --recording 'unclosed", "invalid shell quoting"),
        ('"a bundle/roomscope" analyze --recording \'unclosed', "invalid shell quoting"),
        ("roomscope sweep --out sweep.wav \\", "invalid shell quoting"),
    ],
)
def test_bad_examples_report_the_file_line_command_and_reason(
    docs: Path, command: str, detail: str
) -> None:
    path = docs / "docs/guide.md"
    path.write_text(f"# Guide\n\n```bash\n{command}\n```\n", encoding="utf-8")
    _count, errors = _script().check(docs)
    assert len(errors) == 1
    assert f"{path}:4: {command}" in errors[0]
    assert detail in errors[0]


def test_all_stale_examples_are_reported(docs: Path) -> None:
    (docs / "README.md").write_text("```bash\nroomscope missing-a\n```", encoding="utf-8")
    (docs / "docs/guide.md").write_text("```sh\nroomscope missing-b\n```", encoding="utf-8")
    count, errors = _script().check(docs)
    assert count == 2 and len(errors) == 2
    assert "README.md:2" in errors[0] and "guide.md:2" in errors[1]


def test_unreadable_markdown_is_reported(docs: Path) -> None:
    path = docs / "docs/bad.md"
    path.write_bytes(b"\xff")
    _count, errors = _script().check(docs)
    assert len(errors) == 1 and f"{path}: cannot read Markdown" in errors[0]


def test_empty_or_wrong_checkout_cannot_report_success(docs: Path) -> None:
    script = _script()
    assert "no RoomScope commands" in script.check(docs)[1][0]
    assert "documentation directory not found" in script.check(docs / "missing")[1][0]


def test_main_reports_success_and_failure_on_the_correct_stream(
    docs: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    script = _script()
    assert script.main(["--root", str(docs)]) == 1
    failure = capsys.readouterr()
    assert failure.out == "" and "no RoomScope commands" in failure.err
    (docs / "README.md").write_text("```bash\nroomscope schema result\n```", encoding="utf-8")
    assert script.main(["--root", str(docs)]) == 0
    success = capsys.readouterr()
    assert "1 commands parsed" in success.out and success.err == ""
