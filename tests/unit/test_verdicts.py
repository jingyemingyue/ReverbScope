"""Verdicts on a comparison: improvement, degradation, insignificant, not comparable, insufficient."""

from __future__ import annotations

import json
from dataclasses import replace

import numpy as np
import pytest

from reverbscope.core.compare import compare
from reverbscope.core.pipeline import Reference, analyze, synthetic_recording
from reverbscope.interpretation.verdicts import (
    ASPECT_CLARITY,
    ASPECT_LOW_END,
    ASPECT_NOISE,
    ASPECT_REFLECTIONS,
    ASPECT_REVERBERATION,
    Verdict,
    judge_comparison,
    verdict_chip,
    verdict_word,
)
from reverbscope.models.audio import AudioSignal
from reverbscope.models.comparison import CompareSettings
from reverbscope.models.configuration import SweepSettings
from reverbscope.models.result import AnalysisResult
from tests.conftest import make_rir


def _result(
    sweep: SweepSettings,
    *,
    rt60_s: float,
    reflections: list[tuple[float, float]] = (),
    seed: int = 0,
    noise_rms: float = 1e-5,
) -> AnalysisResult:
    ir = make_rir(
        sweep.sample_rate,
        rt60_s=rt60_s,
        reflections=list(reflections),
        diffuse_level=0.02,
        seed=seed,
    )
    return analyze(
        synthetic_recording(sweep, ir, noise_rms=noise_rms, seed=seed),
        Reference.from_settings(sweep),
    )


def _by_aspect(verdicts) -> dict[str, object]:  # type: ignore[no-untyped-def]
    return {aspect.aspect: aspect for aspect in verdicts.aspects}


def test_the_same_room_twice_changes_nothing(short_sweep: SweepSettings) -> None:
    a = _result(short_sweep, rt60_s=0.4, reflections=[(0.018, 0.3)], seed=1)
    b = _result(short_sweep, rt60_s=0.4, reflections=[(0.018, 0.3)], seed=2)
    comparison = compare(a, b, settings=CompareSettings(same_input_gain=True))
    verdict = judge_comparison(comparison, "vocal", baseline=a, candidate=b)
    by = _by_aspect(verdict)
    assert by[ASPECT_REVERBERATION].verdict is Verdict.INSIGNIFICANT
    assert by[ASPECT_CLARITY].verdict is Verdict.INSIGNIFICANT
    assert by[ASPECT_REFLECTIONS].verdict is Verdict.INSIGNIFICANT
    assert by[ASPECT_NOISE].verdict is Verdict.INSIGNIFICANT
    assert by[ASPECT_LOW_END].verdict is Verdict.INSIGNIFICANT
    assert verdict.count(Verdict.IMPROVEMENT) == 0 and verdict.count(Verdict.DEGRADATION) == 0
    assert "0 improved, 0 degraded" in verdict.headline()
    assert any("One pair of positions" in line for line in verdict.conditions)
    assert json.dumps(verdict.to_dict())


def test_a_long_decay_that_became_short_is_an_improvement_for_a_vocal(
    short_sweep: SweepSettings,
) -> None:
    long = _result(short_sweep, rt60_s=0.9, seed=1)
    short = _result(short_sweep, rt60_s=0.4, seed=2)
    better = _by_aspect(judge_comparison(compare(long, short), "vocal"))[ASPECT_REVERBERATION]
    assert better.verdict is Verdict.IMPROVEMENT
    assert "0.90 s to 0.40 s" in better.reason and "long" in better.reason
    assert (
        better.evidence["baseline_label"] == "long"
        and better.evidence["candidate_label"] == "short"
    )
    worse = _by_aspect(judge_comparison(compare(short, long), "vocal"))[ASPECT_REVERBERATION]
    assert worse.verdict is Verdict.DEGRADATION


def test_two_short_decays_do_not_matter_for_a_vocal_even_when_they_differ(
    short_sweep: SweepSettings,
) -> None:
    """0.30 s to 0.22 s is a 27 % change, well past the JND, and both are
    short for a vocal booth: a real change with no consequence."""
    a = _result(short_sweep, rt60_s=0.30, seed=1)
    b = _result(short_sweep, rt60_s=0.22, seed=2)
    aspect = _by_aspect(judge_comparison(compare(a, b), "vocal"))[ASPECT_REVERBERATION]
    assert aspect.verdict is Verdict.INSIGNIFICANT
    assert "does not matter" in aspect.reason and "Vocal" in aspect.reason
    assert abs(aspect.evidence["delta_percent"]) > 5.0


def test_a_strong_reflection_that_vanished_is_an_improvement(short_sweep: SweepSettings) -> None:
    with_reflection = _result(short_sweep, rt60_s=0.35, reflections=[(0.010, 0.5)], seed=1)
    without = _result(short_sweep, rt60_s=0.35, seed=2)
    gone = _by_aspect(judge_comparison(compare(with_reflection, without), "vocal"))[
        ASPECT_REFLECTIONS
    ]
    assert gone.verdict is Verdict.IMPROVEMENT and "gone" in gone.reason
    appeared = _by_aspect(judge_comparison(compare(without, with_reflection), "vocal"))[
        ASPECT_REFLECTIONS
    ]
    assert appeared.verdict is Verdict.DEGRADATION and "appeared" in appeared.reason
    weak_a = _result(short_sweep, rt60_s=0.35, reflections=[(0.010, 0.2)], seed=1)
    weak_b = _result(short_sweep, rt60_s=0.35, reflections=[(0.010, 0.15)], seed=2)
    weak = _by_aspect(judge_comparison(compare(weak_a, weak_b), "vocal"))[ASPECT_REFLECTIONS]
    assert weak.verdict is Verdict.INSIGNIFICANT and "threshold" in weak.reason


def test_the_noise_floor_needs_the_gain_declared_equal(short_sweep: SweepSettings) -> None:
    quiet = _result(short_sweep, rt60_s=0.4, seed=1, noise_rms=1e-5)
    loud = _result(short_sweep, rt60_s=0.4, seed=2, noise_rms=4e-5)  # +12 dB
    undeclared = _by_aspect(judge_comparison(compare(quiet, loud), "generic"))[ASPECT_NOISE]
    assert undeclared.verdict is Verdict.INSUFFICIENT
    assert "declare the input gain" in undeclared.reason
    declared = compare(quiet, loud, settings=CompareSettings(same_input_gain=True))
    worse = _by_aspect(judge_comparison(declared, "generic"))[ASPECT_NOISE]
    assert worse.verdict is Verdict.DEGRADATION and "louder" in worse.reason
    assert worse.evidence["delta_db"] == pytest.approx(12.0, abs=1.5)
    better = compare(loud, quiet, settings=CompareSettings(same_input_gain=True))
    assert (
        _by_aspect(judge_comparison(better, "generic"))[ASPECT_NOISE].verdict is Verdict.IMPROVEMENT
    )


def test_a_room_microphone_judges_a_room_that_became_too_dry(short_sweep: SweepSettings) -> None:
    """For a room mic the room is the instrument: C80 above the profile's
    bound is a degradation, however the decay reads."""
    live = _result(short_sweep, rt60_s=1.0, seed=1)
    dead = _result(short_sweep, rt60_s=0.1, seed=2)
    by = _by_aspect(judge_comparison(compare(live, dead), "room_mic"))
    assert by[ASPECT_CLARITY].verdict is Verdict.DEGRADATION
    assert "too dry" in by[ASPECT_CLARITY].reason
    assert by[ASPECT_CLARITY].evidence["metric"] == "C80"
    assert by[ASPECT_REVERBERATION].verdict is Verdict.IMPROVEMENT  # judged against "too long" only


def test_drums_have_no_clarity_aspect(short_sweep: SweepSettings) -> None:
    a = _result(short_sweep, rt60_s=0.4, seed=1)
    b = _result(short_sweep, rt60_s=0.4, seed=2)
    verdict = judge_comparison(compare(a, b), "drums")
    assert ASPECT_CLARITY not in _by_aspect(verdict)
    assert len(verdict.aspects) == 4


def test_an_imported_side_has_unknown_health_not_warnings(short_sweep: SweepSettings) -> None:
    """An imported impulse response cannot be checked for its reference, its
    sweep or its level: that is unknown health, not a warning, and it leaves
    every verdict in place. The single-pair caveat comes last."""
    from reverbscope.core.pipeline import analyze_impulse_response

    rate = short_sweep.sample_rate
    samples = make_rir(rate, rt60_s=0.4, length_s=2.0, start_delay_s=0.05, seed=1)
    samples = samples + np.random.default_rng(3).normal(0.0, 1e-6, samples.shape[0])
    imported = analyze_impulse_response(
        AudioSignal(samples=samples, sample_rate=rate, source="file"),
        excitation_band=(50.0, 10000.0),
    )
    measured = _result(short_sweep, rt60_s=0.4, seed=2)
    comparison = compare(imported, measured)
    verdict = judge_comparison(comparison, "vocal", baseline=imported, candidate=measured)
    unknown = [line for line in verdict.conditions if "baseline measurement" in line]
    assert len(unknown) == 1 and "unknown" in unknown[0] and "warning" not in unknown[0]
    assert not any("invalid" in aspect.reason for aspect in verdict.aspects)
    assert "One pair of positions" in verdict.conditions[-1]


def test_an_invalid_side_leaves_insufficient_evidence(short_sweep: SweepSettings) -> None:
    a = _result(short_sweep, rt60_s=0.4, reflections=[(0.010, 0.5)], seed=1)
    clean = synthetic_recording(
        short_sweep,
        make_rir(short_sweep.sample_rate, rt60_s=0.4, reflections=[(0.010, 0.5)]),
        noise_rms=1e-5,
        seed=2,
    )
    clipped = analyze(
        AudioSignal(
            samples=np.clip(clean.samples * 4.0, -0.3, 0.3),
            sample_rate=clean.sample_rate,
            source="daw",
        ),
        Reference.from_settings(short_sweep),
    )
    comparison = compare(a, clipped)
    verdict = judge_comparison(comparison, "vocal", baseline=a, candidate=clipped)
    by = _by_aspect(verdict)
    assert by[ASPECT_REVERBERATION].verdict is Verdict.NOT_COMPARABLE  # the deltas themselves
    for aspect in (ASPECT_REFLECTIONS, ASPECT_LOW_END):
        assert by[aspect].verdict is Verdict.INSUFFICIENT, aspect
        assert "invalid" in by[aspect].reason
    assert any("candidate measurement is invalid" in line for line in verdict.conditions)
    # Judged from the comparison alone (reverbscope show comparison.json), the
    # health is unknown: the reflections stay unjudged for the comparison's
    # own reason (the clipped take's direct sound is not trusted), and the
    # low end, which the comparison did make, is judged on its numbers.
    alone = _by_aspect(judge_comparison(comparison, "vocal"))
    assert "invalid" not in alone[ASPECT_REFLECTIONS].reason
    assert "confidence" in alone[ASPECT_REFLECTIONS].reason
    assert alone[ASPECT_LOW_END].verdict is not Verdict.INSUFFICIENT


def test_a_refused_pair_is_not_comparable_on_every_aspect(short_sweep: SweepSettings) -> None:
    a = _result(short_sweep, rt60_s=0.4, seed=1)
    narrow = replace(
        a,
        impulse_response=replace(
            a.impulse_response,
            excitation_band=replace(a.impulse_response.excitation_band, high_hz=30.0),  # type: ignore[arg-type]
        ),
    )
    verdict = judge_comparison(compare(a, narrow), "vocal")
    assert verdict.aspects and all(v.verdict is Verdict.NOT_COMPARABLE for v in verdict.aspects)
    assert "cannot be compared" in verdict.aspects[0].reason
    assert verdict.count(Verdict.NOT_COMPARABLE) == len(verdict.aspects)


def test_conditions_name_what_the_takes_do_not_share(short_sweep: SweepSettings) -> None:
    a = _result(short_sweep, rt60_s=0.4, seed=1)
    louder = replace(short_sweep, level_dbfs=-6.0)
    b = _result(louder, rt60_s=0.4, seed=2)
    verdict = judge_comparison(compare(a, b), "generic")
    assert any("sweep levels differ" in line for line in verdict.conditions)


def test_words_are_translated(short_sweep: SweepSettings) -> None:
    from reverbscope.i18n import activate

    a = _result(short_sweep, rt60_s=0.4, seed=1)
    b = _result(short_sweep, rt60_s=0.4, seed=2)
    comparison = compare(a, b)
    activate("zh_CN")
    try:
        verdict = judge_comparison(comparison, "vocal")
        assert verdict.locale == "zh_CN"
        assert verdict_word(Verdict.IMPROVEMENT) != "meaningful improvement"
        assert verdict_chip(Verdict.NOT_COMPARABLE) != "not comparable"
        assert all(aspect.title != aspect.aspect for aspect in verdict.aspects)
        assert "improved" not in verdict.headline()
    finally:
        activate("en")


def test_the_cli_prints_and_exports_the_verdict(
    tmp_path, short_sweep: SweepSettings, capsys: pytest.CaptureFixture[str]
) -> None:
    from reverbscope.cli.main import main
    from reverbscope.io.session_store import save_measurement
    from reverbscope.models.session import MeasurementSession

    a = _result(short_sweep, rt60_s=0.9, seed=1)
    b = _result(short_sweep, rt60_s=0.4, seed=2)
    save_measurement(
        tmp_path / "a", MeasurementSession(recording_profile="vocal"), a, copy_recording=False
    )
    save_measurement(
        tmp_path / "b", MeasurementSession(recording_profile="vocal"), b, copy_recording=False
    )
    assert (
        main(
            ["compare", str(tmp_path / "a"), str(tmp_path / "b"), "--out", str(tmp_path / "c.json")]
        )
        == 0
    )
    text = capsys.readouterr().out
    assert "Verdict (Vocals profile)" in text and "meaningful improvement" in text
    assert main(["--format", "json", "show", str(tmp_path / "c.json")]) == 0
    payload = json.loads(capsys.readouterr().out)
    aspects = {item["aspect"]: item for item in payload["verdict"]["aspects"]}
    assert aspects["reverberation"]["verdict"] == "meaningful_improvement"
    assert payload["verdict"]["profile"] == "vocal"
    assert "verdict" not in json.loads((tmp_path / "c.json").read_text(encoding="utf-8"))
