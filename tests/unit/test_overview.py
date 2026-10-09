"""The project overview: positions, repeatability, fit, verdicts, next steps."""

from __future__ import annotations

import json

import numpy as np

from reverbscope.core.pipeline import Reference, analyze, synthetic_recording
from reverbscope.i18n import activate
from reverbscope.interpretation.overview import (
    Fit,
    ProjectEntry,
    fit_word,
    summarize_project,
)
from reverbscope.interpretation.verdicts import Verdict
from reverbscope.models.audio import AudioSignal
from reverbscope.models.configuration import SweepSettings
from reverbscope.models.result import AnalysisResult
from reverbscope.models.session import MeasurementSession
from tests.conftest import make_rir


def _result(
    sweep: SweepSettings,
    *,
    rt60_s: float,
    reflections: list[tuple[float, float]] = (),
    seed: int = 0,
) -> AnalysisResult:
    ir = make_rir(
        sweep.sample_rate,
        rt60_s=rt60_s,
        reflections=list(reflections),
        diffuse_level=0.02,
        seed=seed,
    )
    return analyze(
        synthetic_recording(sweep, ir, noise_rms=1e-5, seed=seed),
        Reference.from_settings(sweep),
    )


def _entry(position: str, name: str, result: AnalysisResult, when: str) -> ProjectEntry:
    session = MeasurementSession(
        room_name="Studio",
        measurement_position=position,
        created_at=when,
        recording_profile="vocal",
    )
    return ProjectEntry(position=position, directory=name, session=session, result=result)


def test_two_positions_with_a_repeat_take(short_sweep: SweepSettings) -> None:
    a1 = _result(short_sweep, rt60_s=0.35, seed=1)
    a2 = _result(short_sweep, rt60_s=0.35, seed=2)
    b = _result(short_sweep, rt60_s=0.9, reflections=[(0.010, 0.5)], seed=3)
    overview = summarize_project(
        [
            _entry("A", "a-1", a1, "2026-10-07T10:00:00Z"),
            _entry("B", "b-1", b, "2026-10-07T10:20:00Z"),
            _entry("A", "a-2", a2, "2026-10-07T10:10:00Z"),
        ],
        "vocal",
        project_name="Booth",
    )
    assert [p.label for p in overview.positions] == ["A", "B"]
    first, second = overview.positions
    assert len(first.sessions) == 2 and first.repeatable is True
    assert first.repeat_spread_percent is not None and first.repeat_spread_percent < 5.0
    assert first.representative_session.directory == "a-2"  # the latest of two good takes
    assert first.verdict is None and "first position" in first.verdict_text
    assert first.representative_session.fit is Fit.FITS
    # B is long and has a strong reflection for a vocal booth: it warns, and
    # against A it is a degradation.
    assert second.representative_session.fit is Fit.WARNINGS
    assert "reverberation" in second.representative_session.warnings
    assert second.verdict is not None
    assert second.verdict.count(Verdict.DEGRADATION) >= 1
    assert "against position A" in second.verdict_text
    assert second.repeatable is None
    assert overview.averaged is not None and overview.averaged.n_microphone_positions == 2
    assert overview.iso_3382_2_class == "survey"
    assert overview.spatial_spread_percent is not None and overview.spatial_spread_percent > 50.0
    assert [p.label for p in overview.fitting] == ["A"]
    steps = "\n".join(overview.next_steps)
    assert "second take at B" in steps
    assert "A is the one position that fits" in steps
    assert "second source position" in steps and "--sources 2" in steps
    assert "rank" not in steps
    payload = json.loads(json.dumps(overview.to_dict()))
    assert payload["positions"][1]["verdict"]["aspects"]
    assert payload["averaged"]["iso_3382_2_class"] == "survey"


def test_takes_that_disagree_are_said_so(short_sweep: SweepSettings) -> None:
    overview = summarize_project(
        [
            _entry("desk", "d-1", _result(short_sweep, rt60_s=0.3, seed=1), "2026-10-07T10:00:00Z"),
            _entry("desk", "d-2", _result(short_sweep, rt60_s=0.5, seed=2), "2026-10-07T10:05:00Z"),
        ],
        "vocal",
    )
    (desk,) = overview.positions
    assert desk.repeatable is False
    assert desk.repeat_spread_percent is not None and desk.repeat_spread_percent > 30.0
    assert any("differ by" in step and "desk" in step for step in overview.next_steps)
    # One position: the survey class needs a second microphone position.
    assert any("1 more" in step and "survey" in step for step in overview.next_steps)
    assert overview.spatial_spread_percent is None


def test_an_invalid_take_cannot_be_judged_and_is_not_the_representative(
    short_sweep: SweepSettings,
) -> None:
    good = _result(short_sweep, rt60_s=0.4, seed=1)
    clean = synthetic_recording(short_sweep, make_rir(short_sweep.sample_rate, rt60_s=0.4), seed=2)
    clipped = analyze(
        AudioSignal(
            samples=np.clip(clean.samples * 4.0, -0.3, 0.3),
            sample_rate=clean.sample_rate,
            source="daw",
        ),
        Reference.from_settings(short_sweep),
    )
    overview = summarize_project(
        [
            _entry("A", "a-good", good, "2026-10-07T10:00:00Z"),
            _entry("A", "a-clipped", clipped, "2026-10-07T11:00:00Z"),
            _entry("B", "b-clipped", clipped, "2026-10-07T12:00:00Z"),
        ],
        "vocal",
    )
    a, b = overview.positions
    # The later take is invalid: the good one represents the position.
    assert a.representative_session.directory == "a-good"
    assert [take.fit for take in a.sessions] == [Fit.FITS, Fit.UNKNOWN]
    assert "invalid" in a.sessions[1].fit_reason
    assert b.representative_session.fit is Fit.UNKNOWN
    assert any(step.startswith("Measure B again") for step in overview.next_steps)
    # Judged against A with the health of both at hand: no verdict is drawn
    # from an invalid take.
    assert b.verdict is not None
    assert b.verdict.count(Verdict.INSUFFICIENT) >= 1


def test_an_empty_project_and_unlisted_sessions(short_sweep: SweepSettings) -> None:
    empty = summarize_project([], "generic", project_name="Room")
    assert empty.positions == () and empty.averaged is None
    assert empty.next_steps and "No position yet" in empty.next_steps[0]
    loose = summarize_project(
        [_entry("", "loose", _result(short_sweep, rt60_s=0.4, seed=1), "2026-10-07T10:00:00Z")],
        "generic",
        skipped=[("broken", "no session.json")],
    )
    assert loose.positions == () and len(loose.unlisted) == 1
    assert loose.averaged is not None and loose.averaged.n_sessions == 1
    assert any("belong to no position" in step for step in loose.next_steps)
    assert loose.to_dict()["skipped"] == [["broken", "no session.json"]]


def test_the_overview_speaks_chinese(short_sweep: SweepSettings) -> None:
    entries = [
        _entry("A", "a", _result(short_sweep, rt60_s=0.35, seed=1), "2026-10-07T10:00:00Z"),
        _entry("B", "b", _result(short_sweep, rt60_s=0.9, seed=2), "2026-10-07T10:10:00Z"),
    ]
    activate("zh_CN")
    try:
        overview = summarize_project(entries, "vocal")
        assert overview.locale == "zh_CN"
        texts = [overview.positions[1].verdict_text, *overview.next_steps]
        texts += [take.fit_reason for p in overview.positions for take in p.sessions]
        assert all(any("一" <= ch <= "鿿" for ch in text) for text in texts), texts
        assert fit_word(Fit.UNKNOWN) != "cannot say"
    finally:
        activate("en")
