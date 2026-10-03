"""Welch spectrum of RoomScope's own impulse response (synthetic / fake)."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from roomscope.audio.fake import FakeBackend
from roomscope.audio.fake import make_rir as fake_make_rir
from roomscope.cli.main import main
from roomscope.core.pipeline import (
    Reference,
    analyze,
    analyze_impulse_response,
    synthetic_recording,
)
from roomscope.core.spectrum import measure_spectrum
from roomscope.core.sweep import measurement_signal
from roomscope.io.wav import write_sweep_file, write_wav
from roomscope.models.audio import AudioSignal
from roomscope.models.result import SPECTRUM_SOURCE
from tests.conftest import make_rir

SCAN = Path("tests/fixtures/synthetic_room.ply")


def test_measure_spectrum_peaks_at_one_kilohertz() -> None:
    sample_rate = 48_000
    time = np.arange(sample_rate, dtype=np.float64) / sample_rate
    spectrum = measure_spectrum(np.sin(2.0 * np.pi * 1000.0 * time), sample_rate)
    assert spectrum.source == SPECTRUM_SOURCE
    assert spectrum.peak_hz is not None
    assert spectrum.peak_hz == pytest.approx(1000.0, abs=4.0)
    assert spectrum.level_db.size == spectrum.frequencies_hz.size
    assert "Welch" in spectrum.method


def test_analyze_impulse_response_spectrum_follows_damped_tone() -> None:
    sample_rate = 48_000
    time = np.arange(int(0.8 * sample_rate), dtype=np.float64) / sample_rate
    samples = np.exp(-time / 0.18) * np.cos(2.0 * np.pi * 250.0 * time)
    result = analyze_impulse_response(AudioSignal(samples, sample_rate))
    assert result.spectrum is not None
    assert result.spectrum.peak_hz == pytest.approx(250.0, abs=8.0)


def test_synthetic_analyze_writes_a_spectrum(short_sweep) -> None:
    result = analyze(
        synthetic_recording(
            short_sweep,
            make_rir(short_sweep.sample_rate, rt60_s=0.35, reflections=[(0.018, 0.35)]),
            noise_rms=1e-5,
        ),
        Reference.from_settings(short_sweep),
    )
    assert result.spectrum is not None
    assert result.spectrum.frequencies_hz.size > 8
    assert result.spectrum.peak_hz is not None
    assert result.spectrum.source == "impulse_response"


def test_fake_backend_recording_has_a_spectrum(short_sweep) -> None:
    backend = FakeBackend(
        rir=fake_make_rir(short_sweep.sample_rate, rt60_s=0.3, diffuse_level=0.01)
    )
    recording = backend.play_and_record(
        measurement_signal(short_sweep),
        short_sweep.sample_rate,
        input_device=None,
        output_device=None,
        input_channels=[1],
        output_channel=1,
        level_dbfs=-20.0,
    )
    result = analyze(recording, Reference.from_settings(short_sweep))
    assert result.spectrum is not None
    assert result.spectrum.peak_hz is not None
    assert result.room_scan is None


def test_cli_analyze_imports_scan_and_reports_spectrum(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], short_sweep
) -> None:
    sweep = tmp_path / "sweep.wav"
    write_sweep_file(short_sweep, sweep)
    ir = make_rir(short_sweep.sample_rate, rt60_s=0.35, reflections=[(0.018, 0.35)])
    recording = synthetic_recording(short_sweep, ir, noise_rms=1e-5)
    rec_path = write_wav(
        tmp_path / "recording.wav",
        recording.samples,
        recording.sample_rate,
        subtype="FLOAT",
    )
    out = tmp_path / "session"
    code = main(
        [
            "analyze",
            "--recording",
            str(rec_path),
            "--sweep",
            str(sweep),
            "--scan",
            str(SCAN),
            "--out",
            str(out),
        ]
    )
    captured = capsys.readouterr()
    assert code == 0
    assert "Imported scan" in captured.out
    assert "Spectrum" in captured.out
    payload = json.loads((out / "result.json").read_text(encoding="utf-8"))
    assert payload["room_scan"]["format"] == "ply"
    assert payload["room_scan"]["point_count"] == 43
    assert payload["spectrum"]["source"] == "impulse_response"
    assert payload["spectrum"]["peak_hz"] is not None
    session = json.loads((out / "session.json").read_text(encoding="utf-8"))
    assert session["scan_path"] == str(SCAN)
