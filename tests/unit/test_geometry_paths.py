from __future__ import annotations

import math
from dataclasses import replace

import numpy as np
import pytest

from reverbscope.core.placement import speed_of_sound_m_s
from reverbscope.geometry.paths import (
    FACES,
    SINGLE_MICROPHONE_NOTE,
    ConsistencyCheck,
    PredictedPath,
    consistency_checks,
    constraint_for,
    direct_distance,
    face_label,
    face_text,
    match_reflection,
    mirror_point,
    overlay_refusal,
    predict_first_order,
    specular_point,
    speed_for,
    tolerance_ms,
)
from reverbscope.geometry.room import GeometryError, Point, RoomBox, RoomGeometry
from reverbscope.models.result import (
    KIND_SAMPLE_RATE,
    AnalysisResult,
    LoopbackResult,
    PlaybackSpeed,
    Reflection,
)

C = 343.0
BOX = RoomBox(5.0, 4.0, 3.0)
SOURCE = Point(1.0, 1.0, 1.0)
MIC = Point(4.0, 3.0, 1.5)


def _geometry(**changes: object) -> RoomGeometry:
    base = RoomGeometry(room=BOX, source=SOURCE, microphones={"A": MIC})
    return replace(base, **changes)  # type: ignore[arg-type]


def _check(checks: list[ConsistencyCheck], name: str) -> ConsistencyCheck:
    return next(check for check in checks if check.name == name)


# ----------------------------------------------------------------- faces and mirrors


def test_face_text_names_the_coordinate() -> None:
    assert face_text("x0", BOX) == "the face at x = 0.00 m"
    assert face_text("x1", BOX) == "the face at x = 5.00 m"
    assert face_text("y1", BOX) == "the face at y = 4.00 m"
    assert face_text("z1", BOX) == "the face at z = 3.00 m"


def test_face_label_never_says_wall() -> None:
    labels = [face_label(face) for face in FACES]
    assert labels[0] == "the face at x = 0"
    assert all("wall" not in label for label in labels)
    assert len(set(labels)) == 6


def test_unknown_face_is_refused() -> None:
    with pytest.raises(GeometryError):
        face_text("w0", BOX)


@pytest.mark.parametrize(
    ("face", "expected"),
    [
        ("x0", Point(-1.0, 1.0, 1.0)),
        ("x1", Point(9.0, 1.0, 1.0)),
        ("y0", Point(1.0, -1.0, 1.0)),
        ("y1", Point(1.0, 7.0, 1.0)),
        ("z0", Point(1.0, 1.0, -1.0)),
        ("z1", Point(1.0, 1.0, 5.0)),
    ],
)
def test_mirror_point(face: str, expected: Point) -> None:
    assert mirror_point(SOURCE, face, BOX) == expected


def test_mirror_twice_is_identity() -> None:
    for face in FACES:
        assert mirror_point(mirror_point(MIC, face, BOX), face, BOX) == MIC


def test_specular_point_on_a_symmetric_pair() -> None:
    point = specular_point(Point(1, 2, 1.5), Point(4, 2, 1.5), "x0", BOX)
    assert point == Point(0.0, 2.0, 1.5)
    floor = specular_point(Point(1, 2, 1.5), Point(4, 2, 1.5), "z0", BOX)
    assert floor is not None
    assert floor.z == 0.0 and floor.x == pytest.approx(2.5)


def test_specular_point_obeys_equal_angles() -> None:
    for face in FACES:
        point = specular_point(SOURCE, MIC, face, BOX)
        assert point is not None
        image = mirror_point(SOURCE, face, BOX)
        # On the straight image-microphone line, and on the face.
        assert image.distance_to(point) + point.distance_to(MIC) == pytest.approx(
            image.distance_to(MIC)
        )
        assert SOURCE.distance_to(point) == pytest.approx(image.distance_to(point))


def test_specular_point_outside_the_face_is_none() -> None:
    # Both positions beyond the y extent: the x = 0 hit lies off the face.
    assert specular_point(Point(1, 5, 1), Point(4, 5, 1), "x0", BOX) is None


def test_specular_point_with_positions_on_both_sides_is_none() -> None:
    assert specular_point(Point(1, 2, 1), Point(6, 2, 1), "x1", BOX) is None


def test_specular_point_on_the_face_is_none() -> None:
    assert specular_point(Point(0, 2, 1), Point(4, 2, 1), "x0", BOX) is None


# ----------------------------------------------------------------- predictions


def test_direct_distance() -> None:
    assert direct_distance(_geometry(), "A") == pytest.approx(math.sqrt(9 + 4 + 0.25))
    assert direct_distance(_geometry(), "B") is None
    assert direct_distance(_geometry(source=None), "A") is None


def test_predicted_delays_match_hand_calculation() -> None:
    d = math.sqrt(3**2 + 2**2 + 0.5**2)
    images = {
        "x0": (-1, 1, 1),
        "x1": (9, 1, 1),
        "y0": (1, -1, 1),
        "y1": (1, 7, 1),
        "z0": (1, 1, -1),
        "z1": (1, 1, 5),
    }
    expected = {
        face: (math.dist(image, (4, 3, 1.5)) - d) / C * 1000.0 for face, image in images.items()
    }
    paths = predict_first_order(_geometry(), "A", C)
    assert {path.face for path in paths} == set(FACES)
    for path in paths:
        assert path.delay_ms == pytest.approx(expected[path.face])
        assert path.path_length_m == pytest.approx(math.dist(images[path.face], (4, 3, 1.5)))
    assert [p.delay_ms for p in paths] == sorted(p.delay_ms for p in paths)


def test_predicted_floor_delay_by_hand() -> None:
    # Source and mic 1.5 m high, 3 m apart: floor path sqrt(3^2 + 3^2).
    geometry = RoomGeometry(room=BOX, source=Point(1, 2, 1.5), microphones={"A": Point(4, 2, 1.5)})
    paths = {p.face: p for p in predict_first_order(geometry, "A", C)}
    assert paths["z0"].delay_ms == pytest.approx((math.sqrt(18) - 3) / C * 1000)
    assert paths["x0"].delay_ms == pytest.approx(2 / C * 1000)


@pytest.mark.parametrize("missing", ["room", "source", "microphones"])
def test_predictions_need_box_source_and_mic(missing: str) -> None:
    empty: object = {} if missing == "microphones" else None
    assert predict_first_order(_geometry(**{missing: empty}), "A", C) == []


def test_predictions_skip_a_face_the_path_misses() -> None:
    geometry = _geometry(source=Point(1, 5, 1), microphones={"A": Point(4, 5, 1)})
    faces = {p.face for p in predict_first_order(geometry, "A", C)}
    assert "x0" not in faces and "x1" not in faces


# ----------------------------------------------------------------- tolerance and match


def test_tolerance_formula() -> None:
    assert tolerance_ms(48000, 343.0) == pytest.approx(1000 / 48000 + 2 * 0.05 / 343.0 * 1000)
    assert tolerance_ms(44100, 340.0, 0.0) == pytest.approx(1000 / 44100)
    assert tolerance_ms(48000, 343.0, 0.1) > tolerance_ms(48000, 343.0, 0.05)


@pytest.mark.parametrize(
    "args", [(0, 343.0, 0.05), (48000, 0.0, 0.05), (48000, 343.0, -1.0), (48000, math.nan, 0.05)]
)
def test_tolerance_refuses_bad_input(args: tuple[int, float, float]) -> None:
    with pytest.raises(GeometryError):
        tolerance_ms(*args)


def _path(face: str, delay: float) -> PredictedPath:
    return PredictedPath(face=face, point=Point(0, 0, 0), path_length_m=1.0, delay_ms=delay)  # type: ignore[arg-type]


def test_match_none() -> None:
    match = match_reflection(10.0, [_path("x0", 5.0), _path("z0", 15.0)], 0.3)
    assert match.kind == "none"
    assert match.candidates == ()
    assert "0.30 ms" in match.text(BOX)


def test_match_single_with_residual() -> None:
    match = match_reflection(5.1, [_path("x0", 5.0), _path("z0", 15.0)], 0.3)
    assert match.kind == "single"
    path, residual = match.candidates[0]
    assert path.face == "x0"
    assert residual == pytest.approx(0.1)
    text = match.text(BOX)
    assert "the face at x = 0.00 m" in text and "+0.10 ms" in text
    assert "not a located wall" in text


def test_match_ambiguous_lists_all_sorted_by_residual() -> None:
    preds = [_path("x0", 5.0), _path("y1", 5.25), _path("z1", 4.85), _path("z0", 9.0)]
    match = match_reflection(5.2, preds, 0.4)
    assert match.kind == "ambiguous"
    assert [c[0].face for c in match.candidates] == ["y1", "x0", "z1"]
    residuals = [abs(c[1]) for c in match.candidates]
    assert residuals == sorted(residuals)
    text = match.text(BOX)
    assert "3 first-order paths" in text and "the face at z = 3.00 m" in text


def test_match_on_the_tolerance_edge_is_a_match() -> None:
    assert match_reflection(5.5, [_path("x0", 5.0)], 0.5).kind == "single"


# ----------------------------------------------------------------- constraint


def test_constraint_interval_formula() -> None:
    c = constraint_for(5.0, 2.0, 340.0)
    excess = 340.0 * 0.005
    total = 2.0 + excess
    assert c.excess_path_m == pytest.approx(excess)
    assert c.total_path_m == pytest.approx(total)
    assert c.semi_major_m == pytest.approx(total / 2)
    assert c.semi_minor_m == pytest.approx(math.sqrt((total / 2) ** 2 - 1.0))
    assert c.distance_from_microphone_m == pytest.approx(((total - 2.0) / 2, (total + 2.0) / 2))
    assert not c.excess_only
    assert "ellipsoid" in c.text


def test_constraint_contains_the_specular_point() -> None:
    d = SOURCE.distance_to(MIC)
    for path in predict_first_order(_geometry(), "A", C):
        c = constraint_for(path.delay_ms, d, C)
        low, high = c.distance_from_microphone_m or (0.0, 0.0)
        r = path.point.distance_to(MIC)
        assert low - 1e-9 <= r <= high + 1e-9
        assert SOURCE.distance_to(path.point) + r == pytest.approx(c.total_path_m)


def test_constraint_without_distance_has_only_the_excess_path() -> None:
    c = constraint_for(3.0, None, 343.0)
    assert c.excess_only
    assert c.excess_path_m == pytest.approx(1.029)
    assert c.total_path_m is None and c.distance_from_microphone_m is None
    assert "nothing more is known" in c.text


@pytest.mark.parametrize("args", [(-1.0, 2.0, 343.0), (math.inf, 2.0, 343.0), (1.0, -2.0, 343.0)])
def test_constraint_refuses_bad_input(args: tuple[float, float, float]) -> None:
    with pytest.raises(GeometryError):
        constraint_for(*args)


def test_single_microphone_note_says_it_cannot_locate() -> None:
    assert "cannot locate" in SINGLE_MICROPHONE_NOTE


# ----------------------------------------------------------------- overlay refusal


def test_no_refusal_for_a_good_result(analysed_result: AnalysisResult) -> None:
    assert overlay_refusal(analysed_result) is None


def test_refusal_for_low_confidence(analysed_result: AnalysisResult) -> None:
    ir = replace(analysed_result.impulse_response, direct_sound_confidence="low")
    reason = overlay_refusal(replace(analysed_result, impulse_response=ir))
    assert reason is not None and "direct sound" in reason
    reflections = replace(analysed_result.reflections, direct_sound_confidence="low")
    assert overlay_refusal(replace(analysed_result, reflections=reflections)) is not None


def test_refusal_for_wrong_speed(analysed_result: AnalysisResult) -> None:
    speed = PlaybackSpeed(0.919, KIND_SAMPLE_RATE, 48000, 44100)
    ir = replace(
        analysed_result.impulse_response, playback_speed=speed, direct_sound_confidence="low"
    )
    reason = overlay_refusal(replace(analysed_result, impulse_response=ir))
    assert reason is not None and "wrong speed" in reason


def test_refusal_without_impulse_response(analysed_result: AnalysisResult) -> None:
    ir = replace(analysed_result.impulse_response, samples=np.zeros(0))
    reason = overlay_refusal(replace(analysed_result, impulse_response=ir))
    assert reason is not None and "no impulse response" in reason


def test_refusal_without_reflection_search(analysed_result: AnalysisResult) -> None:
    reflections = replace(
        analysed_result.reflections, analysed_window_ms=(0.8, 0.8), reflections=()
    )
    reason = overlay_refusal(replace(analysed_result, reflections=reflections))
    assert reason is not None and "no reflections were searched" in reason


# ----------------------------------------------------------------- consistency checks


def _with(
    result: AnalysisResult,
    *,
    distance: float | None = None,
    mic_height: float | None = None,
    temperature: float | None = None,
    reflections: tuple[float, ...] | None = None,
    bound: float | None = None,
) -> AnalysisResult:
    assert result.placement is not None
    placement = replace(result.placement, distance_m=distance, mic_height_m=mic_height)
    if temperature is not None:
        placement = replace(
            placement,
            temperature_c=temperature,
            temperature_assumed=False,
            speed_of_sound_m_s=speed_of_sound_m_s(temperature),
        )
    result = replace(result, placement=placement)
    if reflections is not None:
        found = tuple(Reflection(delay_ms=d, relative_db=-10.0) for d in reflections)
        result = replace(result, reflections=replace(result.reflections, reflections=found))
    if bound is not None:
        loopback = LoopbackResult(
            channel=2, compensation_applied=True, distance_upper_bound_m=bound
        )
        result = replace(
            result, impulse_response=replace(result.impulse_response, loopback=loopback)
        )
    return result


def test_check_names_are_stable(analysed_result: AnalysisResult) -> None:
    names = [check.name for check in consistency_checks(analysed_result, _geometry(), "A")]
    assert names == [
        "speed_of_sound",
        "source_inside",
        "microphone_inside",
        "direct_distance",
        "microphone_height",
        "loopback_bound",
        "earliest_reflection",
    ]


def test_speed_assumed_without_temperature(analysed_result: AnalysisResult) -> None:
    check = _check(consistency_checks(analysed_result, _geometry(), "A"), "speed_of_sound")
    assert check.status == "unknown" and "assumed" in check.text and "20" in check.text
    speed, temperature, assumed = speed_for(replace(analysed_result, placement=None))
    assert (temperature, assumed) == (20.0, True)
    assert speed == pytest.approx(343.2, abs=0.05)


def test_speed_from_entered_temperature(analysed_result: AnalysisResult) -> None:
    result = _with(analysed_result, temperature=25.0)
    check = _check(consistency_checks(result, _geometry(), "A"), "speed_of_sound")
    assert check.status == "ok"
    assert speed_for(result)[0] == pytest.approx(speed_of_sound_m_s(25.0))


def test_inside_checks(analysed_result: AnalysisResult) -> None:
    checks = consistency_checks(analysed_result, _geometry(), "A")
    assert _check(checks, "source_inside").status == "ok"
    assert _check(checks, "microphone_inside").status == "ok"
    outside = consistency_checks(analysed_result, _geometry(source=Point(6, 1, 1)), "A")
    assert _check(outside, "source_inside").status == "warn"
    no_box = consistency_checks(analysed_result, _geometry(room=None), "A")
    assert _check(no_box, "microphone_inside").status == "unknown"
    assert "not entered" in _check(no_box, "microphone_inside").text


def test_direct_distance_check(analysed_result: AnalysisResult) -> None:
    d = SOURCE.distance_to(MIC)
    ok = consistency_checks(_with(analysed_result, distance=d + 0.05), _geometry(), "A")
    assert _check(ok, "direct_distance").status == "ok"
    warn = consistency_checks(_with(analysed_result, distance=d + 0.5), _geometry(), "A")
    assert _check(warn, "direct_distance").status == "warn"
    assert "-0.50 m" in _check(warn, "direct_distance").text
    unknown = consistency_checks(_with(analysed_result), _geometry(), "A")
    assert _check(unknown, "direct_distance").status == "unknown"
    no_mic = consistency_checks(analysed_result, _geometry(), "B")
    assert _check(no_mic, "direct_distance").status == "unknown"


def test_microphone_height_check(analysed_result: AnalysisResult) -> None:
    ok = consistency_checks(_with(analysed_result, mic_height=1.45), _geometry(), "A")
    assert _check(ok, "microphone_height").status == "ok"
    warn = consistency_checks(_with(analysed_result, mic_height=1.0), _geometry(), "A")
    assert _check(warn, "microphone_height").status == "warn"
    unknown = consistency_checks(_with(analysed_result), _geometry(), "A")
    assert _check(unknown, "microphone_height").status == "unknown"


def test_loopback_bound_check(analysed_result: AnalysisResult) -> None:
    d = SOURCE.distance_to(MIC)
    ok = consistency_checks(_with(analysed_result, bound=d + 1.0), _geometry(), "A")
    assert _check(ok, "loopback_bound").status == "ok"
    warn = consistency_checks(_with(analysed_result, bound=d - 1.0), _geometry(), "A")
    assert _check(warn, "loopback_bound").status == "warn"
    none = consistency_checks(analysed_result, _geometry(), "A")
    assert _check(none, "loopback_bound").status == "unknown"
    no_positions = consistency_checks(
        _with(analysed_result, bound=3.0), _geometry(source=None), "A"
    )
    assert _check(no_positions, "loopback_bound").status == "unknown"


def test_earliest_reflection_agrees(analysed_result: AnalysisResult) -> None:
    speed = speed_for(analysed_result)[0]
    earliest = predict_first_order(_geometry(), "A", speed)[0]
    result = _with(analysed_result, reflections=(earliest.delay_ms + 0.01, 12.0))
    check = _check(consistency_checks(result, _geometry(), "A"), "earliest_reflection")
    assert check.status == "ok"
    assert face_text(earliest.face, BOX) in check.text


def test_earliest_reflection_too_early_or_late(analysed_result: AnalysisResult) -> None:
    speed = speed_for(analysed_result)[0]
    earliest = predict_first_order(_geometry(), "A", speed)[0]
    early = _with(analysed_result, reflections=(earliest.delay_ms - 1.0,))
    check = _check(consistency_checks(early, _geometry(), "A"), "earliest_reflection")
    assert check.status == "warn" and "before" in check.text
    late = _with(analysed_result, reflections=(earliest.delay_ms + 1.0,))
    check = _check(consistency_checks(late, _geometry(), "A"), "earliest_reflection")
    assert check.status == "warn" and "after" in check.text


def test_earliest_reflection_unknown_cases(analysed_result: AnalysisResult) -> None:
    no_box = consistency_checks(analysed_result, _geometry(room=None), "A")
    assert _check(no_box, "earliest_reflection").status == "unknown"
    none_found = _with(analysed_result, reflections=())
    check = _check(consistency_checks(none_found, _geometry(), "A"), "earliest_reflection")
    assert check.status == "unknown"
    ir = replace(analysed_result.impulse_response, direct_sound_confidence="low")
    low = replace(analysed_result, impulse_response=ir)
    check = _check(consistency_checks(low, _geometry(), "A"), "earliest_reflection")
    assert check.status == "unknown" and check.text == overlay_refusal(low)


def test_no_check_claims_to_locate_a_wall(analysed_result: AnalysisResult) -> None:
    d = SOURCE.distance_to(MIC)
    speed = speed_for(analysed_result)[0]
    earliest = predict_first_order(_geometry(), "A", speed)[0]
    result = _with(
        analysed_result,
        distance=d,
        mic_height=1.5,
        temperature=20.0,
        reflections=(earliest.delay_ms,),
        bound=d + 1,
    )
    checks = consistency_checks(result, _geometry(), "A")
    assert all(check.status == "ok" for check in checks)
    for check in checks:
        lowered = check.text.lower()
        assert "wall is" not in lowered and "located" not in lowered
        assert "wall at" not in lowered


def test_checks_do_not_mutate_inputs(analysed_result: AnalysisResult) -> None:
    geometry = _geometry()
    before = geometry.to_dict()
    consistency_checks(analysed_result, geometry, "A")
    assert geometry.to_dict() == before
