"""CLI presentation: demo, help, progress, colour and the "At a glance" summaries."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from roomscope.cli.main import main
from roomscope.cli.report import (
    _merge_sides,
    comparison_summary_lines,
    display_width,
    format_comparison_report,
    format_report,
    pad,
    summary_lines,
)
from roomscope.cli.style import ProgressLine, Style, color_supported
from roomscope.demo import DEMO_MODE, DemoRun, run_demo


@pytest.fixture(scope="module")
def demo_run(tmp_path_factory: pytest.TempPathFactory) -> DemoRun:
    return run_demo(tmp_path_factory.mktemp("demo") / "out")


def test_demo_designs_the_problems_it_describes(demo_run: DemoRun) -> None:
    """The demo narrative (desk reflection, room mode, hum) must match the analysis."""
    a, b = (take.result for take in demo_run.takes)
    assert any(abs(r.delay_ms - 2.4) < 0.3 for r in a.reflections.reflections)
    assert not any(abs(r.delay_ms - 2.4) < 0.3 for r in b.reflections.reflections)
    for result in (a, b):
        assert any(abs(c.frequency_hz - 110.0) < 5.0 for c in result.resonances.candidates)
    assert any(h.detected for h in a.noise.hum)
    assert a.noise.rms_dbfs is not None and b.noise.rms_dbfs is not None
    assert b.noise.rms_dbfs < a.noise.rms_dbfs
    statuses = {m.status for m in demo_run.comparison.reflections}
    assert "disappeared" in statuses


def test_demo_sessions_are_marked_synthetic(demo_run: DemoRun) -> None:
    for take in demo_run.takes:
        session = json.loads((take.session_dir / "session.json").read_text(encoding="utf-8"))
        assert session["mode"] == DEMO_MODE
        assert "SYNTHETIC" in session["notes"]
        assert take.recording_path.is_file()
    assert demo_run.sweep_path.is_file()
    assert demo_run.comparison_path.is_file()


def test_demo_command_prints_a_short_labelled_walkthrough(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out_dir = tmp_path / "demo"
    assert main(["demo", "--out", str(out_dir)]) == 0
    captured = capsys.readouterr()
    assert "SYNTHETIC DATA" in captured.out
    assert "Comparison A -> B" in captured.out
    assert "roomscope show" in captured.out
    assert "\x1b[" not in captured.out  # captured stdout is not a terminal
    assert (out_dir / "position-a" / "session.json").is_file()
    assert main(["show", str(out_dir / "position-a")]) == 0
    shown = capsys.readouterr().out
    assert "At a glance" in shown


def test_bare_command_prints_overview(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 0
    out = capsys.readouterr().out
    assert "Quick start" in out
    assert "roomscope demo" in out


def test_help_shows_defaults(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["analyze", "--help"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "(default: 6)" in out  # --smoothing
    assert "placement (optional tape measurements)" in out
    assert "deprecated: use --format json" in out


def test_progress_line_is_quiet_in_logs() -> None:
    stream = io.StringIO()
    progress = ProgressLine("recording", stream)
    for step in range(201):
        progress(step / 200)
    progress.finish()
    lines = stream.getvalue().splitlines()
    assert [line.split()[-2] for line in lines] == ["0", "25", "50", "75", "100"]


class _Tty(io.StringIO):
    def isatty(self) -> bool:
        return True


def test_progress_line_redraws_in_place_on_a_terminal() -> None:
    stream = _Tty()
    progress = ProgressLine("recording", stream)
    for step in range(101):
        progress(step / 100)
    progress.finish()
    text = stream.getvalue()
    assert text.count("\n") == 1 and text.endswith("\n")
    assert "\r" in text and "100 %" in text


def test_measure_progress_is_bounded(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = main(
        [
            "--backend",
            "fake",
            "measure",
            "--out",
            str(tmp_path / "m"),
            "--duration",
            "2",
            "--post-silence",
            "1.5",
        ]
    )
    assert code == 0
    err = capsys.readouterr().err
    assert err.count(" %") <= 5


def test_colour_detection(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("FORCE_COLOR", raising=False)
    monkeypatch.delenv("TERM", raising=False)
    # A Windows console needs VT processing switched on; pretend it succeeded.
    monkeypatch.setattr("roomscope.cli.style._enable_windows_vt", lambda: True)
    assert not color_supported(io.StringIO())
    assert color_supported(_Tty())
    assert not color_supported(_Tty(), requested=False)
    monkeypatch.setenv("FORCE_COLOR", "1")
    assert color_supported(io.StringIO())
    monkeypatch.setenv("NO_COLOR", "1")
    assert not color_supported(_Tty())


def test_reports_are_plain_unless_styled(demo_run: DemoRun) -> None:
    result = demo_run.takes[0].result
    plain = format_report(result)
    assert "\x1b[" not in plain
    assert "At a glance" in plain
    assert "\x1b[1m" in format_report(result, style=Style(color=True))
    comparison = format_comparison_report(demo_run.comparison)
    assert "\x1b[" not in comparison
    assert "Potential low-frequency resonances:" in comparison


def test_summaries_quote_the_result(demo_run: DemoRun) -> None:
    result = demo_run.takes[0].result
    glance = "\n".join(summary_lines(result))
    assert f"{result.decay.broadband.rt60_estimate_s:.2f} s" in glance
    assert "2.4 ms" in glance
    compared = "\n".join(comparison_summary_lines(demo_run.comparison))
    assert "2 gone" in compared
    assert "at both: 110 Hz" in compared


def test_identical_reasons_are_merged() -> None:
    same = "baseline unreliable (x; y); candidate unreliable (x; y)"
    assert _merge_sides(same) == "both sides unreliable (x; y)"
    different = "baseline unreliable (x); candidate insufficient_decay_range"
    assert _merge_sides(different) == different


def test_pad_counts_wide_characters() -> None:
    assert display_width("混响") == 4
    assert pad("混响", 8) == "混响    "
    assert pad("Reverberation", 20) == "Reverberation       "


def test_gui_without_pyside6_prints_a_hint(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import sys

    # A CLI-only install: importing Qt fails. The command must explain, not crash.
    monkeypatch.setitem(sys.modules, "PySide6", None)
    monkeypatch.setitem(sys.modules, "PySide6.QtWidgets", None)
    assert main(["gui"]) == 2
    assert "PySide6_Essentials" in capsys.readouterr().err


def test_narrow_console_encoding_does_not_crash(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import sys

    from roomscope.cli.main import _tolerate_narrow_encodings

    raw = io.BytesIO()
    narrow = io.TextIOWrapper(raw, encoding="cp1252", newline="\n")
    monkeypatch.setattr(sys, "stdout", narrow)
    _tolerate_narrow_encodings()
    sys.stdout.write("mean |Δ| 2.4→9.3 ms —\n")
    narrow.flush()
    # "—" exists in cp1252; "Δ" and "→" do not and are replaced.
    assert raw.getvalue() == "mean |?| 2.4?9.3 ms —\n".encode("cp1252")
