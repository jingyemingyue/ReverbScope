from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from scipy.signal import fftconvolve

from reverbscope.cli.main import main
from reverbscope.io.wav import read_wav, write_wav
from tests.conftest import make_rir


def test_version_flag(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert "reverbscope" in capsys.readouterr().out


def test_sweep_and_analyze_commands(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    sweep = tmp_path / "sweep.wav"
    assert main(["sweep", "--out", str(sweep), "--duration", "2", "--post-silence", "1.5"]) == 0
    assert sweep.is_file() and (tmp_path / "sweep.reverbscope-sweep.json").is_file()

    signal = read_wav(sweep)
    # diffuse_level was 0.01: there the single -9 dB reflection carries about half
    # of the energy after the direct sound, the broadband decay is curved by the
    # ISO 3382-2 measure (C = 12 %) and ReverbScope now withholds the RT60 (see
    # tests/unit/test_decay.py). With 0.02 the decay is straight (C ~ 1 %), so
    # this test keeps checking the CLI's RT60 output.
    ir = make_rir(signal.sample_rate, rt60_s=0.4, reflections=[(0.018, 0.35)], diffuse_level=0.02)
    rec = fftconvolve(signal.samples, ir)[: signal.n_samples + ir.shape[0]]
    rec = np.stack([np.zeros_like(rec), rec], axis=1)
    recording = write_wav(tmp_path / "recording.wav", rec, signal.sample_rate, subtype="FLOAT")

    out = tmp_path / "session"
    code = main(
        [
            "analyze",
            "--recording",
            str(recording),
            "--sweep",
            str(sweep),
            "--out",
            str(out),
            "--room",
            "R",
        ]
    )
    captured = capsys.readouterr()
    assert code == 0
    assert "ReverbScope analysis" in captured.out
    assert "18.0 ms" in captured.out
    assert (out / "session.json").is_file() and (out / "result.json").is_file()

    code = main(
        [
            "analyze",
            "--recording",
            str(recording),
            "--sweep",
            str(sweep),
            "--json",
            "--no-curves",
            "--channel",
            "1",
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["decay"]["broadband"]["rt60_estimate_s"] == pytest.approx(0.4, rel=0.15)
    assert payload["findings"]


def test_analyze_accepts_recording_profile(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    sweep = tmp_path / "sweep.wav"
    assert main(["sweep", "--out", str(sweep), "--duration", "2", "--post-silence", "1.5"]) == 0
    signal = read_wav(sweep)
    ir = make_rir(signal.sample_rate, rt60_s=0.4, reflections=[(0.018, 0.35)], diffuse_level=0.02)
    rec = fftconvolve(signal.samples, ir)[: signal.n_samples + ir.shape[0]]
    recording = write_wav(tmp_path / "recording.wav", rec, signal.sample_rate, subtype="FLOAT")

    assert (
        main(
            [
                "analyze",
                "--recording",
                str(recording),
                "--sweep",
                str(sweep),
                "--profile",
                "vocal",
            ]
        )
        == 0
    )
    assert "Interpretation (Vocals profile)" in capsys.readouterr().out

    with pytest.raises(SystemExit):
        main(
            [
                "analyze",
                "--recording",
                str(recording),
                "--sweep",
                str(sweep),
                "--profile",
                "not_a_profile",
            ]
        )


def test_show_prints_saved_session_and_lists_folder(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    sweep = tmp_path / "sweep.wav"
    assert main(["sweep", "--out", str(sweep), "--duration", "2", "--post-silence", "1.5"]) == 0
    signal = read_wav(sweep)
    ir = make_rir(signal.sample_rate, rt60_s=0.4, reflections=[(0.018, 0.35)], diffuse_level=0.02)
    rec = fftconvolve(signal.samples, ir)[: signal.n_samples + ir.shape[0]]
    recording = write_wav(tmp_path / "recording.wav", rec, signal.sample_rate, subtype="FLOAT")
    session = tmp_path / "session"
    assert (
        main(
            [
                "analyze",
                "--recording",
                str(recording),
                "--sweep",
                str(sweep),
                "--out",
                str(session),
                "--room",
                "Booth",
                "--profile",
                "vocal",
            ]
        )
        == 0
    )
    capsys.readouterr()

    assert main(["show", str(session)]) == 0
    shown = capsys.readouterr().out
    assert "ReverbScope analysis" in shown
    assert "Interpretation (Vocals profile)" in shown
    assert str(session) in shown

    assert main(["show", str(session), "--json", "--no-curves"]) == 0
    shown_json = capsys.readouterr()
    payload = json.loads(shown_json.out)
    assert "--json is deprecated" in shown_json.err
    assert "DeprecationWarning" not in shown_json.err
    assert payload["session"]["room_name"] == "Booth"
    assert payload["session"]["recording_profile"] == "vocal"
    assert payload["findings"]

    assert main(["show", str(tmp_path), "--list"]) == 0
    listing = capsys.readouterr().out
    assert str(session) in listing
    assert "Booth" in listing

    assert main(["show", str(tmp_path / "empty"), "--list"]) == 1
    assert "error:" in capsys.readouterr().err


def test_compare_and_schema_commands(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    sweep = tmp_path / "sweep.wav"
    assert main(["sweep", "--out", str(sweep), "--duration", "2", "--post-silence", "1.5"]) == 0
    signal = read_wav(sweep)
    ir = make_rir(signal.sample_rate, rt60_s=0.4, reflections=[(0.018, 0.35)], diffuse_level=0.02)
    rec = fftconvolve(signal.samples, ir)[: signal.n_samples + ir.shape[0]]
    recording = write_wav(tmp_path / "recording.wav", rec, signal.sample_rate, subtype="FLOAT")
    a = tmp_path / "a"
    b = tmp_path / "b"
    assert (
        main(
            [
                "analyze",
                "--recording",
                str(recording),
                "--sweep",
                str(sweep),
                "--out",
                str(a),
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "analyze",
                "--recording",
                str(recording),
                "--sweep",
                str(sweep),
                "--out",
                str(b),
            ]
        )
        == 0
    )
    capsys.readouterr()
    out = tmp_path / "comparison.json"
    assert main(["compare", str(a), str(b), "--out", str(out), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert "comparable" in payload
    assert all("validity" in item for item in payload["decay"])
    assert "findings" in payload
    assert out.is_file()
    assert main(["show", str(out)]) == 0
    shown = capsys.readouterr().out
    assert "ReverbScope comparison" in shown
    assert main(["show", str(out), "--json"]) == 0
    reloaded = json.loads(capsys.readouterr().out)
    assert reloaded["comparable"] == payload["comparable"]
    assert "findings" in reloaded
    assert "findings" not in json.loads(out.read_text(encoding="utf-8"))
    assert main(["schema", "comparison"]) == 0
    schema = capsys.readouterr().out
    assert '"title": "ReverbScope comparison.json"' in schema


def test_analyze_missing_file_returns_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(
        [
            "analyze",
            "--recording",
            str(tmp_path / "nope.wav"),
            "--sweep",
            str(tmp_path / "nope2.wav"),
        ]
    )
    assert code == 1
    assert "error:" in capsys.readouterr().err


def test_measure_refuses_loud_level_without_acknowledgement(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(["measure", "--out", str(tmp_path / "m"), "--level", "-3"])
    assert code == 2
    assert "acknowledge" in capsys.readouterr().err


def test_session_bundle_export_and_project(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    sweep = tmp_path / "sweep.wav"
    assert main(["sweep", "--out", str(sweep), "--duration", "2", "--post-silence", "1.5"]) == 0
    signal = read_wav(sweep)
    ir = make_rir(signal.sample_rate, rt60_s=0.4, reflections=[(0.018, 0.35)], diffuse_level=0.02)
    rec = fftconvolve(signal.samples, ir)[: signal.n_samples + ir.shape[0]]
    recording = write_wav(tmp_path / "recording.wav", rec, signal.sample_rate, subtype="FLOAT")
    session = tmp_path / "session"
    assert (
        main(
            [
                "--copy-recording",
                "analyze",
                "--recording",
                str(recording),
                "--sweep",
                str(sweep),
                "--out",
                str(session),
                "--room",
                "Booth",
            ]
        )
        == 0
    )
    capsys.readouterr()
    assert (session / "recording.wav").is_file()
    assert (session / "sweep.reverbscope-sweep.json").is_file()
    bundle = tmp_path / "report.zip"
    assert main(["session", "bundle", str(session), "--no-audio", "--out", str(bundle)]) == 0
    assert bundle.is_file()
    export_dir = tmp_path / "csv"
    assert main(["export", str(session), "--format", "csv", "--out", str(export_dir)]) == 0
    assert (export_dir / "decay_metrics.csv").is_file()
    project = tmp_path / "room"
    assert main(["project", "init", "--out", str(project), "--name", "Booth"]) == 0
    assert main(["project", "add", str(project), str(session), "--position", "desk"]) == 0
    assert main(["project", "show", str(project)]) == 0
    shown = capsys.readouterr().out
    assert "desk" in shown
    assert main(["project", "average", str(project), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["iso_3382_2_class"] in {"below_survey", "survey", "engineering", "precision"}


def test_lang_zh_cn_translates_report(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    sweep = tmp_path / "sweep.wav"
    assert main(["sweep", "--out", str(sweep), "--duration", "2", "--post-silence", "1.5"]) == 0
    signal = read_wav(sweep)
    ir = make_rir(signal.sample_rate, rt60_s=0.4, diffuse_level=0.02)
    rec = fftconvolve(signal.samples, ir)[: signal.n_samples + ir.shape[0]]
    recording = write_wav(tmp_path / "recording.wav", rec, signal.sample_rate, subtype="FLOAT")
    assert (
        main(
            [
                "--lang",
                "zh_CN",
                "analyze",
                "--recording",
                str(recording),
                "--sweep",
                str(sweep),
            ]
        )
        == 0
    )
    out = capsys.readouterr().out
    assert "ReverbScope 分析" in out
    assert "混响" in out
    assert "概览" in out and "诊断" in out
    from reverbscope.i18n import activate

    activate("en")


def test_lang_zh_cn_translates_cli_help(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--lang", "zh_CN", "--help"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "不依赖 DAW" in out
    assert "调试日志" in out
    assert "分析用该扫频录下的录音" in out
    with pytest.raises(SystemExit) as exc:
        main(["--lang", "zh_CN", "analyze", "--help"])
    assert exc.value.code == 0
    analyze = capsys.readouterr().out
    assert "分析用该扫频录下的录音" in analyze
    assert "不要裁切" in analyze
    assert "附属文件" in analyze
    assert "显示此帮助信息并退出" in out
    from reverbscope.i18n import activate

    activate("en")


def test_lang_zh_cn_translates_cli_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    sweep = tmp_path / "sweep.wav"
    assert main(["--lang", "zh_CN", "sweep", "--out", str(sweep), "--duration", "2"]) == 0
    swept = capsys.readouterr().out
    assert "下一步" in swept or "导入" in swept
    assert main(["--lang", "zh_CN", "--backend", "fake", "devices"]) == 0
    listed = capsys.readouterr().out
    assert "主机" in listed
    from reverbscope.i18n import activate

    activate("en")


def test_fake_backend_devices_and_measure(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["--backend", "fake", "devices"]) == 0
    listed = capsys.readouterr().out
    assert "fake" in listed
    out = tmp_path / "standalone"
    code = main(
        [
            "--backend",
            "fake",
            "measure",
            "--out",
            str(out),
            "--duration",
            "2",
            "--post-silence",
            "1.5",
            "--level",
            "-20",
            "--input-channels",
            "1,2",
            "--loopback-channel",
            "2",
        ]
    )
    captured = capsys.readouterr()
    assert code == 0, captured.err
    assert (out / "session.json").is_file()
    assert (out / "recording.wav").is_file()
    assert "Loopback" in captured.out or "loopback" in captured.out.lower()
