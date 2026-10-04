from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from scipy.signal import fftconvolve

from roomscope.cli.main import main
from roomscope.io.wav import read_wav, write_wav
from roomscope.models.configuration import SweepSettings
from tests.conftest import make_rir


def test_version_flag(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert "roomscope" in capsys.readouterr().out


def test_sweep_and_analyze_commands(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    sweep = tmp_path / "sweep.wav"
    assert main(["sweep", "--out", str(sweep), "--duration", "2", "--post-silence", "1.5"]) == 0
    assert sweep.is_file() and (tmp_path / "sweep.roomscope-sweep.json").is_file()

    signal = read_wav(sweep)
    # diffuse_level was 0.01: there the single -9 dB reflection carries about half
    # of the energy after the direct sound, the broadband decay is curved by the
    # ISO 3382-2 measure (C = 12 %) and RoomScope now withholds the RT60 (see
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
    assert "RoomScope analysis" in captured.out
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
    assert "RoomScope analysis" in shown
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
    assert "RoomScope comparison" in shown
    assert main(["show", str(out), "--json"]) == 0
    reloaded = json.loads(capsys.readouterr().out)
    assert reloaded["comparable"] == payload["comparable"]
    assert "findings" in reloaded
    assert "findings" not in json.loads(out.read_text(encoding="utf-8"))
    assert main(["schema", "comparison"]) == 0
    schema = capsys.readouterr().out
    assert '"title": "RoomScope comparison.json"' in schema


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


def test_show_json_reports_session_paths_as_stored(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    short_sweep: SweepSettings,
) -> None:
    """``show --format json`` printed the recording as ``sess/recording.wav``
    (relative to where you ran it) while session.json says ``recording.wav``
    (relative to the session folder, like the other members)."""
    from roomscope.core.pipeline import Reference, analyze, synthetic_recording
    from roomscope.io.session_store import save_measurement
    from roomscope.models.session import MeasurementSession

    rec = synthetic_recording(short_sweep, make_rir(short_sweep.sample_rate, rt60_s=0.3))
    result = analyze(rec, Reference.from_settings(short_sweep))
    take = write_wav(tmp_path / "take.wav", rec.samples, rec.sample_rate, subtype="FLOAT")
    save_measurement(
        tmp_path / "sess",
        MeasurementSession(recording_path=str(take)),
        result,
        include_curves=False,
        copy_recording=True,
    )
    monkeypatch.chdir(tmp_path)
    capsys.readouterr()
    assert main(["--format", "json", "show", "sess", "--no-curves"]) == 0
    session = json.loads(capsys.readouterr().out)["session"]
    assert session["recording_path"] == "recording.wav"
    assert session["impulse_response_path"] == "impulse_response.wav"


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
    assert (session / "sweep.roomscope-sweep.json").is_file()
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
    assert "RoomScope 分析" in out
    assert "混响" in out
    assert "概览" in out and "诊断" in out
    from roomscope.i18n import activate

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
    from roomscope.i18n import activate

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
    from roomscope.i18n import activate

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


def test_show_comparison_interprets_with_the_candidates_profile(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`show comparison.json` used the General profile, not the candidate
    session's profile that `compare` used, and ignored the default profile."""
    from roomscope.settings import UserSettings, save_settings

    for name, rt60 in (("a", 0.7), ("b", 0.4)):
        ir = write_wav(tmp_path / f"{name}.wav", make_rir(48000, rt60_s=rt60) * 0.5, 48000)
        argv = ["analyze-ir", "--ir", str(ir), "--band", "100", "8000", "--profile", "vocal"]
        assert main([*argv, "--out", str(tmp_path / name)]) == 0
    saved = tmp_path / "ab.json"
    assert main(["compare", str(tmp_path / "a"), str(tmp_path / "b"), "--out", str(saved)]) == 0
    assert "Vocals profile" in capsys.readouterr().out
    assert main(["show", str(saved)]) == 0
    assert "Vocals profile" in capsys.readouterr().out
    # Without the candidate session, the default profile applies.
    (tmp_path / "b").rename(tmp_path / "moved")
    save_settings(UserSettings(default_profile="choir"))
    assert main(["show", str(saved)]) == 0
    assert "Choir / ensemble profile" in capsys.readouterr().out


def test_a_take_on_the_fake_backend_is_saved_as_a_synthetic_demo(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """roomscope --backend fake measure saved an ordinary Standalone session,
    indistinguishable from a take on real hardware."""
    from roomscope.demo import DEMO_MODE

    out = tmp_path / "fake-take"
    code = main(
        [
            "--backend",
            "fake",
            "measure",
            "--out",
            str(out),
            "--duration",
            "1",
            "--post-silence",
            "1",
            "--notes",
            "first try",
        ]
    )
    assert code == 0, capsys.readouterr().err
    saved = json.loads((out / "session.json").read_text(encoding="utf-8"))
    assert saved["mode"] == DEMO_MODE
    assert saved["notes"].startswith("SYNTHETIC DEMO")
    assert saved["notes"].endswith("first try")
    capsys.readouterr()
    assert main(["show", str(out)]) == 0
    assert "Synthetic demo" in capsys.readouterr().out


def test_measure_refuses_a_test_signal_too_short_to_analyse_before_playing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A 0.9 s signal was played and recorded, then always refused by the
    analysis ("recording is shorter than one second")."""
    out = tmp_path / "m_short"
    code = main(
        [
            "--backend",
            "fake",
            "measure",
            "--duration",
            "0.5",
            "--pre-silence",
            "0.1",
            "--post-silence",
            "0.3",
            "--out",
            str(out),
        ]
    )
    err = capsys.readouterr().err
    assert code == 1
    assert "0.90 s" in err and "--post-silence" in err
    assert "Nothing was played." in err
    assert "devices --probe" not in err
    assert not (out / "recording.wav").exists()
