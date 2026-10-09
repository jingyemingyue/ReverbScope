"""The terminal examples in the user guides are lines the command prints.

The Chinese guide showed an overview table of 50 columns whose row wrapped
between ``2`` and its counter ``个`` (the command keeps them together) and a
finding card broken inside the word 检查; they were typed, not printed. Every
line of a ``text`` block in a guide must be a line that ``reverbscope show``,
the error panel or the progress bar writes in that guide's language.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

import pytest

from reverbscope.cli.console import Console, ProgressLine
from reverbscope.cli.main import main
from reverbscope.demo import run_demo
from reverbscope.i18n import _, activate

ROOT = Path(__file__).resolve().parents[2]
GUIDES = {
    "en": ROOT / "docs" / "user-guide" / "en.md",
    "zh_CN": ROOT / "docs" / "user-guide" / "zh-CN.md",
}
#: Terminal widths an example may have been taken at.
WIDTHS = (52, 56, 60, 64, 72, 80)
_BLOCK = re.compile(r"^```text\n(.*?)^```", re.S | re.M)


@pytest.fixture(scope="module")
def position_a(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("guide") / "demo"
    run_demo(out)
    return out / "position-a"


@pytest.fixture
def terminal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    monkeypatch.setenv("REVERBSCOPE_HOME", str(tmp_path / "home"))
    for name in ("NO_COLOR", "FORCE_COLOR", "TERM", "PYTHONIOENCODING"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)
    try:
        yield tmp_path
    finally:
        activate("en")


def _printed(
    lang: str,
    session: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> set[str]:
    """Every line the guide's commands print in ``lang``, at the widths above."""
    lines: set[str] = set()
    for width in WIDTHS:
        monkeypatch.setenv("COLUMNS", str(width))
        for argv in (["show", str(session), "--profile", "vocal"], ["show", "take-1"]):
            capsys.readouterr()
            main(["--lang", lang, "--style", "boxed", "--color", "never", *argv])
            captured = capsys.readouterr()
            lines.update(line.rstrip() for line in (captured.out + captured.err).splitlines())
    activate(lang)
    # The progress line of a take, on an 80-column terminal (one column is left free).
    meter = Console(interactive=True, width=80, boxed=True)
    lines.add(ProgressLine(meter, None, _("Playing the sweep and recording"), 9.0).line(0.42, 79))
    return lines


@pytest.mark.parametrize("lang", sorted(GUIDES))
def test_every_example_line_of_the_guide_is_a_line_the_command_prints(
    lang: str,
    position_a: Path,
    terminal: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    blocks = _BLOCK.findall(GUIDES[lang].read_text(encoding="utf-8"))
    # The overview table, a finding card, the error panel and the progress bar.
    assert len(blocks) == 4
    printed = _printed(lang, position_a, capsys, monkeypatch)
    typed = [line.rstrip() for block in blocks for line in block.splitlines() if line.strip()]
    assert [line for line in typed if line not in printed] == []
