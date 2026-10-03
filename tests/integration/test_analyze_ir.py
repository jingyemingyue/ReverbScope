"""``analyze_impulse_response`` and ``reverbscope analyze-ir`` (#10).

The imported-IR path must recover what the full sweep pipeline recovers from
the same room, refuse files that are not impulse responses, and handle other
sample rates and multi-channel files the way ``analyze`` does.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from reverbscope.core.deconvolution import find_sweep_passes
from reverbscope.core.pipeline import (
    IMPORTED_IR_MIN_MARGIN_DB,
    Reference,
    analyze,
    analyze_impulse_response,
    synthetic_recording,
)
from reverbscope.core.sweep import measurement_signal
from reverbscope.errors import AnalysisError
from reverbscope.io.wav import write_wav
from reverbscope.models.audio import AudioSignal
from reverbscope.models.configuration import AnalysisSettings, SweepSettings
from reverbscope.models.result import Validity
from tests.conftest import make_rir

RT60_S = 0.45
MODE_HZ = 55.0


def _room_ir(sample_rate: int, *, rt60_s: float = RT60_S, with_mode: bool = True) -> np.ndarray:
    """Synthetic room: 18 ms reflection at -9 dB plus a slowly decaying 55 Hz mode."""
    ir = make_rir(
        sample_rate, rt60_s=rt60_s, reflections=[(0.018, 10 ** (-9 / 20))], diffuse_level=0.01
    )
    if with_mode:
        t = np.arange(ir.shape[0]) / sample_rate
        ir = ir + 0.03 * np.sin(2 * np.pi * MODE_HZ * t) * np.exp(-6.9 * t / 1.4)
    return np.asarray(ir, dtype=np.float64)


def _sweep(sample_rate: int) -> SweepSettings:
    return SweepSettings(
        sample_rate=sample_rate,
        duration_s=2.0,
        pre_silence_s=1.0,
        post_silence_s=1.5,
        level_dbfs=-12.0,
    )


@pytest.fixture(scope="module")
def full_and_ir() -> tuple:
    """A full sweep analysis and the impulse_response.wav it would save."""
    sweep = _sweep(48000)
    full = analyze(
        synthetic_recording(sweep, _room_ir(48000), noise_rms=3e-5),
        Reference.from_settings(sweep),
    )
    return full, AudioSignal(np.asarray(full.impulse_response.samples), 48000)


def test_imported_ir_recovers_what_the_full_pipeline_recovers(full_and_ir: tuple) -> None:
    full, ir = full_and_ir
    band = full.excitation_band
    assert band is not None
    result = analyze_impulse_response(ir, excitation_band=(band.low_hz, band.high_hz))

    assert result.impulse_response.direct_sound_confidence == "high"
    assert result.decay.broadband.rt60_estimate_s == pytest.approx(
        full.decay.broadband.rt60_estimate_s, rel=0.01
    )
    assert result.decay.broadband.rt60_basis == full.decay.broadband.rt60_basis
    by_label = {b.band_label: b for b in result.decay.bands}
    for band_full in full.decay.bands:
        band_ir = by_label[band_full.band_label]
        assert band_ir.t30.validity == band_full.t30.validity
        if band_full.rt60_estimate_s is not None:
            assert band_ir.rt60_estimate_s == pytest.approx(band_full.rt60_estimate_s, rel=0.02)
    # Mid bands see the room, not the mode.
    for label in ("1 kHz", "2 kHz"):
        assert by_label[label].rt60_estimate_s == pytest.approx(RT60_S, rel=0.1)

    def strong(res):
        return [
            (r.delay_ms, r.relative_db) for r in res.reflections.reflections if r.relative_db > -15
        ]

    assert len(strong(result)) == len(strong(full)) == 1
    (delay, level), (delay_full, level_full) = strong(result)[0], strong(full)[0]
    assert delay == pytest.approx(18.0, abs=0.1) and delay == pytest.approx(delay_full, abs=0.05)
    assert level == pytest.approx(-9.0, abs=0.5) and level == pytest.approx(level_full, abs=0.2)

    resonances = [c for c in result.resonances.candidates if c.decay_distinguishable]
    assert [round(c.frequency_hz) for c in resonances] == [
        round(c.frequency_hz) for c in full.resonances.candidates if c.decay_distinguishable
    ]
    assert any(abs(c.frequency_hz - MODE_HZ) < 2.0 for c in resonances)
    assert result.noise.rms_dbfs is None
    assert any("impulse response imported" in w for w in result.warnings)


def test_without_a_declared_band_no_band_metric_is_computed(full_and_ir: tuple) -> None:
    _full, ir = full_and_ir
    result = analyze_impulse_response(ir)
    assert result.excitation_band is not None
    assert result.excitation_band.source == "unknown"
    for band in (result.decay.broadband, *result.decay.bands):
        for metric in (band.edt, band.t20, band.t30):
            assert metric.validity is Validity.NOT_COMPUTED
            assert metric.seconds is None
        assert band.rt60_estimate_s is None
    # Reflections do not depend on the band and are still reported.
    assert any(abs(r.delay_ms - 18.0) < 0.2 for r in result.reflections.reflections)


def test_imported_ir_at_44_1_khz() -> None:
    sr = 44100
    ir = np.concatenate([np.zeros(round(0.05 * sr)), _room_ir(sr, with_mode=False)])
    ir = ir + np.random.default_rng(2).normal(0.0, 1e-6, ir.shape[0])
    result = analyze_impulse_response(AudioSignal(ir, sr), excitation_band=(40.0, 16000.0))
    assert result.sample_rate == sr
    assert result.impulse_response.direct_sound_confidence == "high"
    assert result.decay.broadband.rt60_estimate_s == pytest.approx(RT60_S, rel=0.1)
    assert any(abs(r.delay_ms - 18.0) < 0.1 for r in result.reflections.reflections)


def test_stereo_ir_analyses_the_requested_channel() -> None:
    sr = 48000
    pre = np.zeros(round(0.05 * sr))
    # Plain diffuse rooms (no discrete reflection, so the broadband decay is
    # single-slope) with a 50 ms pre-roll and a -140 dB noise floor.
    left = np.concatenate([pre, make_rir(sr, rt60_s=0.3, diffuse_level=0.05, seed=3)])
    right = np.concatenate([pre, make_rir(sr, rt60_s=0.8, diffuse_level=0.05, seed=3)])
    n = max(left.shape[0], right.shape[0])
    stereo = np.random.default_rng(4).normal(0.0, 1e-7, (n, 2))
    stereo[: left.shape[0], 0] += left
    stereo[: right.shape[0], 1] += right
    signal = AudioSignal(stereo, sr)
    band = (40.0, 16000.0)
    first = analyze_impulse_response(signal, AnalysisSettings(channel=0), excitation_band=band)
    assert first.analysis_settings["channel_analysed"] == 0
    assert first.decay.broadband.rt60_estimate_s == pytest.approx(0.3, rel=0.1)
    second = analyze_impulse_response(signal, AnalysisSettings(channel=1), excitation_band=band)
    assert second.analysis_settings["channel_analysed"] == 1
    assert second.decay.broadband.rt60_estimate_s == pytest.approx(0.8, rel=0.1)
    # Without a channel setting the louder (higher-RMS) channel is taken, as in
    # ``analyze``, and the choice is stated.
    default = analyze_impulse_response(signal, excitation_band=band)
    assert default.analysis_settings["channel_analysed"] == 1
    assert any("highest RMS" in w for w in default.warnings)


@pytest.mark.parametrize("kind", ["noise", "sweep"])
def test_a_file_that_is_not_an_impulse_response_is_refused(kind: str) -> None:
    sr = 48000
    if kind == "noise":
        samples = np.random.default_rng(1).normal(0.0, 0.1, 2 * sr)
    else:
        # The test signal itself (6 s): loud everywhere, so no peak stands out.
        samples = measurement_signal(SweepSettings(sample_rate=sr, duration_s=2.0))
    with pytest.raises(AnalysisError, match="cannot be analysed as an impulse response"):
        analyze_impulse_response(AudioSignal(samples, sr), excitation_band=(20.0, 20000.0))
    assert IMPORTED_IR_MIN_MARGIN_DB == 10.0


@pytest.mark.parametrize("cutoff_hz", [80.0, 120.0])
def test_a_band_limited_ir_with_a_declared_band_is_accepted(cutoff_hz: float) -> None:
    """A sub-woofer IR rises for ~2 / cutoff before it peaks; with its band
    declared that rise is not taken for content before the direct sound."""
    from scipy.signal import butter, sosfilt

    sr = 48000
    room = make_rir(sr, rt60_s=0.5, diffuse_level=0.02)
    low_passed = sosfilt(butter(4, cutoff_hz, "lowpass", fs=sr, output="sos"), room)
    ir = np.concatenate([np.zeros(round(0.1 * sr)), low_passed])
    ir = ir + np.random.default_rng(0).normal(0.0, 1e-6, ir.shape[0])
    result = analyze_impulse_response(AudioSignal(ir, sr), excitation_band=(20.0, cutoff_hz))
    assert result.impulse_response.direct_sound_confidence == "high"


def test_an_ir_whose_direct_sound_is_weaker_than_a_reflection_is_refused() -> None:
    sr = 48000
    ir = make_rir(sr, rt60_s=0.5, diffuse_level=0.02, direct=0.6, reflections=[(0.003, 1.5)])
    ir = np.concatenate([np.zeros(round(0.1 * sr)), ir])
    with pytest.raises(AnalysisError, match="weaker than a later arrival"):
        analyze_impulse_response(AudioSignal(ir, sr), excitation_band=(20.0, 20000.0))


def test_pass_search_is_skipped_without_a_sweep() -> None:
    """With a one-sample reference every loud sample used to be a candidate
    pass, which took quadratic time on a loud file (the sweep case above ran
    for minutes before the guard)."""
    magnitude = np.ones(400_000)
    assert find_sweep_passes(magnitude, 1234, reference_length=1, sample_rate=48000) == (1234,)


def test_cli_analyze_ir_json_round_trip(
    tmp_path: Path, full_and_ir: tuple, capsys: pytest.CaptureFixture[str]
) -> None:
    from reverbscope.cli.main import main

    full, ir = full_and_ir
    band = full.excitation_band
    assert band is not None
    ir_path = write_wav(tmp_path / "room_ir.wav", ir.samples, ir.sample_rate, subtype="FLOAT")
    out = tmp_path / "imported"
    code = main(
        [
            "--format",
            "json",
            "analyze-ir",
            "--ir",
            str(ir_path),
            "--band",
            f"{band.low_hz:.6f}",
            f"{band.high_hz:.6f}",
            "--out",
            str(out),
            "--profile",
            "vocal",
        ]
    )
    captured = capsys.readouterr()
    assert code == 0, captured.err
    payload = json.loads(captured.out)
    assert payload["decay"]["broadband"]["rt60_estimate_s"] == pytest.approx(
        full.decay.broadband.rt60_estimate_s, rel=0.01
    )
    assert payload["impulse_response"]["excitation_band"]["source"] == "declared by the user"
    assert payload["findings"] and all(f["message"] for f in payload["findings"])
    session = json.loads((out / "session.json").read_text(encoding="utf-8"))
    assert session["mode"] == "analyze_ir"
    assert (out / "impulse_response.wav").is_file()
    # The saved session reopens.
    assert main(["show", str(out)]) == 0
    assert "ReverbScope analysis" in capsys.readouterr().out


def test_cli_analyze_ir_refuses_a_recording(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from reverbscope.cli.main import main

    samples = np.random.default_rng(1).normal(0.0, 0.1, 96000)
    path = write_wav(tmp_path / "noise.wav", samples, 48000, subtype="FLOAT")
    assert main(["analyze-ir", "--ir", str(path)]) == 1
    assert "cannot be analysed as an impulse response" in capsys.readouterr().err
