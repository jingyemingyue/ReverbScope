from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from scipy.signal import fftconvolve

from reverbscope.cli.main import main
from reverbscope.io.wav import read_wav, write_wav
from reverbscope.models.configuration import SweepSettings
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


def test_show_json_reports_session_paths_as_stored(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    short_sweep: SweepSettings,
) -> None:
    """``show --format json`` printed the recording as ``sess/recording.wav``
    (relative to where you ran it) while session.json says ``recording.wav``
    (relative to the session folder, like the other members)."""
    from reverbscope.core.pipeline import Reference, analyze, synthetic_recording
    from reverbscope.io.session_store import save_measurement
    from reverbscope.models.session import MeasurementSession

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


def test_show_comparison_interprets_with_the_candidates_profile(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`show comparison.json` used the General profile, not the candidate
    session's profile that `compare` used, and ignored the default profile."""
    from reverbscope.settings import UserSettings, save_settings

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
    """reverbscope --backend fake measure saved an ordinary Standalone session,
    indistinguishable from a take on real hardware."""
    from reverbscope.demo import DEMO_MODE

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


def test_project_init_keeps_an_existing_project(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Running init again (shell history, or to set a name) must not drop the
    positions: a fresh project.json lists none."""
    project = tmp_path / "room"
    assert main(["project", "init", "--out", str(project), "--name", "Studio"]) == 0
    stored = (
        (project / "project.json")
        .read_text(encoding="utf-8")
        .replace('"positions": []', '"positions": [{"label": "A", "session_dirs": ["position-a"]}]')
    )
    (project / "project.json").write_text(stored, encoding="utf-8")
    capsys.readouterr()

    assert main(["project", "init", "--out", str(project)]) == 1
    err = " ".join(capsys.readouterr().err.split())
    assert "already contains a project.json; use --force to replace it" in err
    assert (project / "project.json").read_text(encoding="utf-8") == stored

    assert main(["project", "init", "--out", str(project), "--force"]) == 0
    payload = json.loads((project / "project.json").read_text(encoding="utf-8"))
    assert payload["name"] == "room" and payload["positions"] == []


def test_show_escapes_control_characters_from_a_received_session(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`show`, `show --list` and `project show` printed a crafted room name,
    stored warning or position label raw: ESC sequences cleared the screen
    or retitled the terminal, and a line break forged a report line."""
    from dataclasses import replace

    from reverbscope.core.pipeline import Reference, analyze, synthetic_recording
    from reverbscope.io.session_store import save_measurement
    from reverbscope.models.session import MeasurementSession

    settings = SweepSettings(duration_s=1.0, pre_silence_s=0.5, post_silence_s=1.0)
    rec = synthetic_recording(settings, make_rir(settings.sample_rate, rt60_s=0.3), noise_rms=1e-5)
    result = replace(
        analyze(rec, Reference.from_settings(settings)), warnings=("stored\x1b[2Jwarning",)
    )
    project = tmp_path / "inbox"
    session = project / "received"
    crafted = MeasurementSession(
        room_name="Booth\x1b[2J\x1b]0;pwned\x07", measurement_position="A\nRT60 0.30 s"
    )
    save_measurement(session, crafted, result, include_curves=False)
    (project / "project.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "name": "P\x1b[2J",
                "positions": [{"label": "A\x1b[8m", "session_dirs": ["received"]}],
            }
        ),
        encoding="utf-8",
    )
    capsys.readouterr()

    assert main(["--color", "always", "show", str(session)]) == 0
    report = capsys.readouterr().out
    assert main(["--color", "always", "show", "--list", str(project)]) == 0
    listing = capsys.readouterr().out
    assert main(["project", "show", str(project)]) == 0
    projects = capsys.readouterr().out
    for out in (report, listing, projects):
        assert "\x1b[2J" not in out and "\x07" not in out and "\x1b[8m" not in out
    assert "Booth\\x1b[2J\\x1b]0;pwned\\x07" in report and "Booth\\x1b[2J" in listing
    assert "A\\nRT60 0.30 s" in report and "stored\\x1b[2Jwarning" in report
    assert "P\\x1b[2J" in projects and "A\\x1b[8m" in projects


def test_show_keeps_stored_text_to_its_own_line_and_free_of_escape_codes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A stored warning kept its line breaks and any escape code that looks
    like one of ReverbScope's own colours: it forged a report row ("Data quality
    ✓ ... no warnings"), and raw ESC[32m reached a stream with colour off. The
    same went for every other text field of result.json."""
    from dataclasses import replace

    from reverbscope.core.pipeline import Reference, analyze, synthetic_recording
    from reverbscope.io.session_store import save_measurement
    from reverbscope.models.session import MeasurementSession

    settings = SweepSettings(duration_s=1.0, pre_silence_s=0.5, post_silence_s=1.0)
    rec = synthetic_recording(settings, make_rir(settings.sample_rate, rt60_s=0.3), noise_rms=1e-5)
    analysed = analyze(rec, Reference.from_settings(settings))
    forged = "harmless\n\n  Data quality       \x1b[32m✓ direct sound: no warnings\x1b[0m"
    bands = tuple(
        replace(band, band_label="500 Hz\nFORGED-BAND", rt60_basis="T30\x1b[1mbold\x1b[0m")
        if index == 0
        else band
        for index, band in enumerate(analysed.decay.bands)
    )
    result = replace(
        analysed,
        warnings=(forged, "x"),
        decay=replace(analysed.decay, bands=bands),
        noise=replace(
            analysed.noise, notes=("noise\n  Noise floor   \x1b[32m✓ FORGED-NOISE\x1b[0m",)
        ),
    )
    session = tmp_path / "received"
    save_measurement(session, MeasurementSession(), result, include_curves=False)
    capsys.readouterr()

    for mode in ("never", "always"):
        assert main(["--color", mode, "show", str(session)]) == 0
        report = capsys.readouterr().out
        # The text is shown as typed, its control characters as escapes ...
        assert "harmless\\n\\n" in report and "\\x1b[32m" in report
        assert "500 Hz\\nFORGED-BAND" in report and "T30\\x1b[1mbold" in report
        # ... on the line of its own warning, not as rows of the report.
        rows = [line.strip() for line in report.splitlines()]
        forged_rows = [
            row
            for row in rows
            if row.startswith(("Data quality", "Noise floor", "FORGED-BAND"))
            and ("no warnings" in row or "FORGED" in row)
        ]
        assert forged_rows == []
        if mode == "never":
            assert "\x1b" not in report
        else:
            # Only the codes ReverbScope writes itself: none after "harmless".
            assert "\x1b[32m✓ direct sound" not in report and "\x1b[32m✓ FORGED-NOISE" not in report


def test_project_average_keeps_a_stored_band_label_to_its_row(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The averaged table printed a band label from result.json as it was
    stored: a line break in it forged a row of the table."""
    from dataclasses import replace

    from reverbscope.core.pipeline import Reference, analyze, synthetic_recording
    from reverbscope.io.session_store import save_measurement
    from reverbscope.models.session import MeasurementSession

    settings = SweepSettings(duration_s=1.0, pre_silence_s=0.5, post_silence_s=1.0)
    rec = synthetic_recording(settings, make_rir(settings.sample_rate, rt60_s=0.3), noise_rms=1e-5)
    analysed = analyze(rec, Reference.from_settings(settings))
    bands = (
        replace(analysed.decay.bands[0], band_label="63 Hz\nFORGEDROW 9.99 s"),
        *analysed.decay.bands[1:],
    )
    result = replace(analysed, decay=replace(analysed.decay, bands=bands))
    project = tmp_path / "room"
    for name in ("a", "b"):
        save_measurement(project / name, MeasurementSession(), result, include_curves=False)
    (project / "project.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "name": "room",
                "positions": [
                    {"label": "A", "session_dirs": ["a"]},
                    {"label": "B", "session_dirs": ["b"]},
                ],
            }
        ),
        encoding="utf-8",
    )
    capsys.readouterr()

    assert main(["--color", "never", "project", "average", str(project)]) == 0
    table = capsys.readouterr().out
    assert "63 Hz\\nFORGEDROW 9.99 s" in table
    assert not [line for line in table.splitlines() if line.startswith("FORGEDROW")]


@pytest.mark.parametrize(
    ("option", "named"),
    [
        (["--mic-height", "1.2"], "--mic-height"),
        (["--speaker-distance", "-1"], "--speaker-distance"),
        (["--temperature", "80"], "--temperature"),
        (["--smoothing", "-1"], "--smoothing"),
    ],
)
def test_measure_refuses_an_analysis_option_before_playing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], option: list[str], named: str
) -> None:
    """--mic-height without --speaker-distance (and the other analysis
    options) were checked only after the sweep had been played and recorded,
    and the error then suggested the device commands."""
    out = tmp_path / "m_option"
    argv = ["--backend", "fake", "measure", "--duration", "1", "--post-silence", "1"]
    code = main([*argv, "--out", str(out), *option])
    captured = capsys.readouterr()
    assert code == 1
    assert named in captured.err and "Nothing was played." in captured.err
    assert "reverbscope measure --help" in captured.err
    assert "devices --probe" not in captured.err
    assert "Playing the sweep" not in captured.err and "Recorded" not in captured.out
    assert not out.exists()


def _fingerprints(folder: Path) -> dict[str, bytes]:
    return {path.name: path.read_bytes() for path in sorted(folder.iterdir())}


def test_measure_refuses_a_folder_that_holds_a_sweep_but_no_session(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """measure --out on a folder with the user's own sweep replaced that sweep
    and its sidecar with the take's, without a word."""
    folder = tmp_path / "meas"
    assert main(["sweep", "--out", str(folder / "sweep.wav"), "--sample-rate", "96000"]) == 0
    before = _fingerprints(folder)
    capsys.readouterr()
    argv = ["--backend", "fake", "measure", "--duration", "1", "--post-silence", "1"]
    assert main([*argv, "--out", str(folder)]) == 1
    err = capsys.readouterr().err
    assert "sweep.wav" in err and "Nothing was played." in err
    assert "reverbscope measure --out" in err
    assert _fingerprints(folder) == before


def test_a_take_that_fails_keeps_the_previous_session_whole(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A second take into a session folder wrote its sweep.wav, sidecar and
    recording.wav before the analysis, so a take that was then refused left
    the old session.json beside another take's audio."""
    from reverbscope.core import pipeline
    from reverbscope.errors import AnalysisError

    folder = tmp_path / "session"
    argv = ["--backend", "fake", "measure", "--post-silence", "1", "--out", str(folder)]
    assert main([*argv, "--duration", "1"]) == 0
    before = _fingerprints(folder)
    assert {"sweep.wav", "sweep.reverbscope-sweep.json", "recording.wav"} <= set(before)
    saved = json.loads((folder / "session.json").read_text(encoding="utf-8"))
    assert (saved["sweep_path"], saved["recording_path"]) == ("sweep.wav", "recording.wav")
    capsys.readouterr()

    def refuse(*_args: object, **_kwargs: object) -> None:
        raise AnalysisError("no sweep found in the recording")

    monkeypatch.setattr(pipeline, "analyze", refuse)
    assert main([*argv, "--duration", "2"]) == 1
    assert "no sweep found" in capsys.readouterr().err
    assert _fingerprints(folder) == before


@pytest.mark.parametrize(
    "command", [["devices"], ["devices", "--probe"], ["devices", "--host-apis"], ["doctor"]]
)
def test_devices_and_doctor_warn_that_json_is_deprecated(
    capsys: pytest.CaptureFixture[str], command: list[str]
) -> None:
    """devices --json and doctor --json read the flag directly and never said
    it will be removed, unlike show, compare, analyze and project average."""
    assert main(["--backend", "fake", *command, "--json"]) == 0
    captured = capsys.readouterr()
    json.loads(captured.out)
    assert captured.err.count("--json is deprecated") == 1
    assert main(["--backend", "fake", "--format", "json", *command]) == 0
    assert "deprecated" not in capsys.readouterr().err
