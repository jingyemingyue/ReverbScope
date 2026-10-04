"""Optional fit wiring is isolated from ISO metrics and measurement trust gates."""

from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path
from types import ModuleType
from typing import Any

import numpy as np
import pytest
from jsonschema import Draft202012Validator

from roomscope.cli.main import _analysis_settings, build_parser, main
from roomscope.core import decay
from roomscope.core.filters import iec_band
from roomscope.core.pipeline import (
    Reference,
    analyze,
    analyze_impulse_response,
    synthetic_recording,
)
from roomscope.io.wav import write_wav
from roomscope.models.audio import AudioSignal
from roomscope.models.configuration import AnalysisSettings, SweepSettings
from roomscope.models.result import (
    AnalysisResult,
    DecayComponent,
    DecayMetric,
    MultiDecayFit,
    Validity,
)
from roomscope.schemas import load_schema
from tests.conftest import make_rir


@pytest.fixture
def fit_spy(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Only the wiring is under test; numerical fitting has its own analytic fixtures."""
    calls: list[dict[str, Any]] = []
    module = ModuleType("roomscope.core.multi_decay")

    def fit(signal: np.ndarray, sample_rate: int, **kwargs: Any) -> MultiDecayFit:
        calls.append({"signal": signal.copy(), "sample_rate": sample_rate, **kwargs})
        return MultiDecayFit(
            method="synthetic fit stand-in",
            validity=Validity.VALID,
            components=(DecayComponent(0.5, 1.0, 0.01),),
            fit_start_s=(kwargs["start_index"] - kwargs["time_origin_index"]) / sample_rate,
            fit_end_s=(len(signal) - kwargs["time_origin_index"]) / sample_rate,
            initializer=kwargs["initializer"],
            residual_rms_db=0.1,
        )

    module.fit_multi_decay = fit  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, module.__name__, module)
    return calls


@pytest.mark.parametrize("mode", ["physical", "neural"])
def test_enabled_fit_leaves_iso_outputs_identical_and_roundtrips(
    fit_spy: list[dict[str, Any]], mode: str
) -> None:
    sr = 48000
    ir = make_rir(sr, rt60_s=0.5, diffuse_level=0.05)
    settings = AnalysisSettings(octave_bands_hz=(1000.0,))
    baseline = decay.analyze_decay(ir, sr, settings, direct_index=0)
    assert not fit_spy
    enabled = decay.analyze_decay(ir, sr, replace(settings, decay_fit=mode), direct_index=0)
    assert len(fit_spy) == 2
    assert all(call["initializer"] == mode for call in fit_spy)
    # Fitting uses raw band amplitude after the direct sound, rather than a compensated EDC.
    first = fit_spy[0]
    assert first["start_index"] > first["time_origin_index"]
    assert first["signal"][first["time_origin_index"]] == ir[0]
    for plain, extra in zip(
        (baseline.broadband, *baseline.bands), (enabled.broadband, *enabled.bands), strict=True
    ):
        extra_payload = extra.to_dict()
        assert "multi_decay" not in plain.to_dict()
        extra_payload.pop("multi_decay")
        assert extra_payload == plain.to_dict()


def test_outside_excitation_bands_do_not_invoke_fit(fit_spy: list[dict[str, Any]]) -> None:
    from roomscope.models.result import ExcitationBand

    ir = make_rir(48000, rt60_s=0.5)
    result = decay.analyze_decay(
        ir,
        48000,
        AnalysisSettings(octave_bands_hz=(63.0, 1000.0), decay_fit="neural"),
        excitation_band=ExcitationBand(500.0, 2000.0, "declared by the user"),
    )
    assert len(fit_spy) == 2  # broadband and 1 kHz only
    assert result.bands[0].multi_decay is None
    assert result.bands[0].t30.validity is Validity.OUTSIDE_EXCITATION


def test_truncation_distrust_reaches_optional_fit(
    fit_spy: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    original = decay.estimate_truncation

    def estimate(power: np.ndarray, sample_rate: int) -> decay.TruncationEstimate:
        return replace(original(power, sample_rate), problem="gated tail")

    monkeypatch.setattr(decay, "estimate_truncation", estimate)
    band = decay.analyze_band(
        make_rir(48000, rt60_s=0.5), 48000, None, noise_margin_db=10, decay_fit="physical"
    )
    assert band.multi_decay is not None
    assert band.multi_decay.validity is Validity.UNRELIABLE
    assert "gated tail" in (band.multi_decay.reason or "")


def test_filter_ringing_gate_uses_component_time_when_iso_time_is_missing(
    fit_spy: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    def no_iso(*args: object) -> tuple[DecayMetric, DecayMetric, DecayMetric]:
        return tuple(  # type: ignore[return-value]
            DecayMetric(name, None, Validity.NOT_COMPUTED, (0, -10))
            for name in ("EDT", "T20", "T30")
        )

    monkeypatch.setattr(decay, "_fit_all", no_iso)
    result = decay.analyze_band(
        make_rir(48000, rt60_s=0.5),
        48000,
        iec_band(8.0, 1),
        noise_margin_db=10,
        decay_fit="physical",
    )
    assert result.filter_bt_product is None and result.filter_warning is None
    assert result.multi_decay is not None and result.multi_decay.validity is Validity.UNRELIABLE
    assert "B*T" in (result.multi_decay.reason or "")


def test_fast_component_cannot_borrow_a_slow_iso_time_to_pass_the_filter_gate(
    fit_spy: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    module = sys.modules["roomscope.core.multi_decay"]
    original = module.fit_multi_decay

    def fast_and_slow(*args: Any, **kwargs: Any) -> MultiDecayFit:
        return replace(
            original(*args, **kwargs),
            components=(DecayComponent(0.03, 0.5), DecayComponent(2.0, 0.5)),
        )

    monkeypatch.setattr(module, "fit_multi_decay", fast_and_slow)
    result = decay.analyze_band(
        make_rir(48000, rt60_s=0.5, diffuse_level=0.05),
        48000,
        iec_band(63.0, 1),
        noise_margin_db=10,
        decay_fit="physical",
    )
    assert result.filter_bt_product is not None and result.filter_bt_product >= decay.MIN_BT_PRODUCT
    assert result.filter_warning is None
    assert result.multi_decay is not None and result.multi_decay.validity is Validity.UNRELIABLE
    assert "B*T" in (result.multi_decay.reason or "")


@pytest.mark.parametrize("declare_band", [False, True])
def test_imported_ir_withholds_unknown_band_and_distrusts_unverified_direct_sound(
    fit_spy: list[dict[str, Any]], declare_band: bool
) -> None:
    sr = 48000
    signal = AudioSignal(make_rir(sr, rt60_s=0.4, diffuse_level=0.04), sr)
    declared = (40.0, 16000.0) if declare_band else None
    base = analyze_impulse_response(signal, excitation_band=declared)
    result = analyze_impulse_response(
        signal, AnalysisSettings(decay_fit="neural"), excitation_band=declared
    )
    assert result.impulse_response.direct_sound_confidence == "low"
    for baseline, band in zip(
        (base.decay.broadband, *base.decay.bands),
        (result.decay.broadband, *result.decay.bands),
        strict=True,
    ):
        fit = band.multi_decay
        if fit is None:  # no inference outside the excitation range
            continue
        plain = band.to_dict()
        plain.pop("multi_decay")
        assert plain == baseline.to_dict()
        if declare_band:
            assert fit.validity is Validity.UNRELIABLE
            assert "confidence is low" in (fit.reason or "")
        else:
            assert fit.validity is Validity.NOT_COMPUTED and not fit.components
            assert "excitation band unknown" in (fit.reason or "")


def test_clipped_recording_cannot_gain_a_valid_model_result(
    fit_spy: list[dict[str, Any]], short_sweep: SweepSettings
) -> None:
    samples = synthetic_recording(
        short_sweep, make_rir(short_sweep.sample_rate, rt60_s=0.5), noise_rms=1e-5
    ).samples
    recording = AudioSignal(np.clip(samples * 10, -1.0, 1.0), short_sweep.sample_rate)
    result = analyze(
        recording,
        Reference.from_settings(short_sweep),
        AnalysisSettings(decay_fit="physical"),
    )
    assert result.clipping is not None and result.clipping.clipped
    for band in (result.decay.broadband, *result.decay.bands):
        if band.multi_decay is not None:
            assert band.multi_decay.validity is Validity.UNRELIABLE
            assert "recording clips" in (band.multi_decay.reason or "")


@pytest.mark.parametrize("mode", ["off", "physical", "neural"])
def test_cli_opt_in_and_saved_result_contract(
    fit_spy: list[dict[str, Any]], tmp_path: Path, capsys: pytest.CaptureFixture[str], mode: str
) -> None:
    ir = np.concatenate([np.zeros(2400), make_rir(48000, rt60_s=0.5, diffuse_level=0.05)])
    path = tmp_path / "synthetic.wav"
    write_wav(path, ir, 48000, subtype="FLOAT")
    out = tmp_path / "session"
    argv = [
        "--format",
        "json",
        "analyze-ir",
        "--ir",
        str(path),
        "--band",
        "40",
        "16000",
        "--out",
        str(out),
        "--decay-fit",
        mode,
    ]
    args = build_parser().parse_args(argv)
    assert _analysis_settings(args).decay_fit == mode
    assert main(argv) == 0
    report = json.loads(capsys.readouterr().out)
    payload = json.loads((out / "result.json").read_text(encoding="utf-8"))
    assert report["decay"] == payload["decay"]
    Draft202012Validator(load_schema("result")).validate(payload)
    for include_curves in (False, True):
        loaded = AnalysisResult.from_dict(payload)
        roundtrip = loaded.to_dict(include_curves=include_curves)
        Draft202012Validator(load_schema("result")).validate(roundtrip)
        fit = loaded.decay.broadband.multi_decay
        assert (fit is None) == (mode == "off")
        if fit is not None:
            assert roundtrip["decay"]["broadband"]["multi_decay"] == fit.to_dict()
    assert (out / "session.json").is_file()
    session = json.loads((out / "session.json").read_text())
    assert session["analysis_settings"].get("decay_fit", "off") == mode


def test_real_neural_cli_fits_two_synthetic_decays_and_records_local_provenance(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Exercise the shipped network and physical optimizer through the actual CLI."""
    sr = 48000
    t = np.arange(2 * sr) / sr
    expected = 0.8 * np.exp(-6 * np.log(10) * t / 0.3) + 0.2 * np.exp(-6 * np.log(10) * t / 1.2)
    tail = 0.05 * np.random.default_rng(56).normal(size=t.size) * np.sqrt(expected + 1e-6)
    tail[0] = 1.0
    path = tmp_path / "analytic-two-decay.wav"
    write_wav(path, np.concatenate([np.zeros(sr // 10), tail]), sr, subtype="FLOAT")
    out = tmp_path / "neural-session"
    assert (
        main(
            [
                "--format",
                "json",
                "analyze-ir",
                "--ir",
                str(path),
                "--band",
                "40",
                "16000",
                "--out",
                str(out),
                "--decay-fit",
                "neural",
                "--no-curves",
            ]
        )
        == 0
    )
    report = json.loads(capsys.readouterr().out)
    assert report["impulse_response"]["direct_sound_confidence"] == "high"
    fit = report["decay"]["broadband"]["multi_decay"]
    assert fit["validity"] in ("valid", "unreliable")
    assert [component["rt60_s"] for component in fit["components"]] == pytest.approx(
        [0.3, 1.2], rel=0.1
    )
    assert fit["initializer"] == "neural"
    assert fit["initializer_model"] == "roomscope-decay-initializer-v1"
    assert fit["initializer_parameters"] == 2245
    assert len(fit["initializer_sha256"]) == 64
    payload = json.loads((out / "result.json").read_text(encoding="utf-8"))
    Draft202012Validator(load_schema("result")).validate(payload)
    assert payload["decay"]["broadband"]["multi_decay"] == fit
    loaded = AnalysisResult.from_dict(payload)
    assert loaded.decay.broadband.multi_decay is not None
    assert loaded.decay.broadband.multi_decay.to_dict() == fit
    session = json.loads((out / "session.json").read_text(encoding="utf-8"))
    assert session["analysis_settings"]["decay_fit"] == "neural"
