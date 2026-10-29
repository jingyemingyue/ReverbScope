"""CLI boundary inputs: empty files, invalid sample rates, long paths, Chinese paths.

Asserts exit codes and that failures surface as errors. Does not change or
lock exact CLI wording beyond the existing ``error:`` marker.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from scipy.signal import fftconvolve

from reverbscope.cli.main import main
from reverbscope.io.wav import read_wav, write_wav
from tests.conftest import make_rir


def _run(argv: list[str]) -> int:
    try:
        return int(main(argv))
    except SystemExit as exc:
        code = exc.code
        if code is None:
            return 0
        return int(code) if isinstance(code, int) else 1


def test_empty_wav_is_refused_by_analyze_ir(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    empty = tmp_path / "empty.wav"
    empty.write_bytes(b"")
    assert _run(["analyze-ir", "--ir", str(empty)]) == 1
    assert "error:" in capsys.readouterr().err


def test_empty_recording_is_refused_by_analyze(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    empty = tmp_path / "empty.wav"
    empty.write_bytes(b"")
    sweep = tmp_path / "sweep.wav"
    assert _run(["sweep", "--out", str(sweep), "--duration", "1", "--post-silence", "0.5"]) == 0
    capsys.readouterr()
    assert _run(["analyze", "--recording", str(empty), "--sweep", str(sweep)]) == 1
    assert "error:" in capsys.readouterr().err


@pytest.mark.parametrize("command", ["sweep", "measure"])
def test_invalid_sample_rate_is_rejected(
    command: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    argv = [command, "--sample-rate", "12345", "--out", str(tmp_path / "out")]
    if command == "measure":
        argv.extend(["--level", "-20", "--i-understand-the-level"])
    assert _run(argv) == 2
    err = capsys.readouterr().err
    assert "error:" in err
    assert "sample-rate" in err or "12345" in err


def test_sweep_writes_under_a_long_directory_name(tmp_path: Path) -> None:
    folder = tmp_path / ("seg-" + "x" * 160)
    folder.mkdir()
    target = folder / "sweep.wav"
    assert _run(["sweep", "--out", str(target), "--duration", "1", "--post-silence", "0.5"]) == 0
    assert target.is_file()
    assert (
        target.with_suffix(".reverbscope-sweep.json").is_file()
        or (folder / "sweep.reverbscope-sweep.json").is_file()
    )


def test_chinese_path_round_trip_analyze_show_export(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    room = tmp_path / "客厅-北墙"
    room.mkdir()
    sweep = room / "扫频.wav"
    assert _run(["sweep", "--out", str(sweep), "--duration", "1", "--post-silence", "0.5"]) == 0
    signal = read_wav(sweep)
    ir = make_rir(signal.sample_rate, rt60_s=0.35, reflections=[(0.02, 0.3)], diffuse_level=0.02)
    rec = fftconvolve(signal.samples, ir)[: signal.n_samples + ir.shape[0]]
    rec = np.stack([np.zeros_like(rec), rec], axis=1)
    recording = write_wav(room / "录音.wav", rec, signal.sample_rate, subtype="FLOAT")
    session = room / "会话-1"
    assert (
        _run(
            [
                "analyze",
                "--recording",
                str(recording),
                "--sweep",
                str(sweep),
                "--out",
                str(session),
                "--room",
                "客厅",
            ]
        )
        == 0
    )
    assert (session / "session.json").is_file()
    capsys.readouterr()
    assert _run(["show", str(session)]) == 0
    assert "ReverbScope" in capsys.readouterr().out
    export_dir = room / "导出"
    assert _run(["export", str(session), "--format", "csv", "--out", str(export_dir)]) == 0
    assert any(export_dir.glob("*.csv"))


@pytest.mark.parametrize(
    "argv_builder",
    [
        lambda p: ["show", str(p / "没有这个会话")],
        lambda p: ["export", str(p / "没有这个会话")],
        lambda p: ["compare", str(p / "甲"), str(p / "乙")],
        lambda p: ["analyze-ir", "--ir", str(p / "不存在.wav")],
        lambda p: [
            "analyze",
            "--recording",
            str(p / "不存在.wav"),
            "--sweep",
            str(p / "也不存在.wav"),
        ],
    ],
)
def test_missing_chinese_paths_fail_cleanly(
    argv_builder, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = _run(argv_builder(tmp_path))
    assert code in {1, 2}
    assert "error:" in capsys.readouterr().err
