"""What a measurement can say about the entered room, and what it cannot.

Three layers are kept apart (GUI_2_ARCHITECTURE.md §6.4):

* *entered*: the box and positions in :mod:`reverbscope.geometry.room`;
* *measured constraint*: what one reflection supports on its own, an
  ellipsoid of possible reflection points (:func:`constraint_for`);
* *geometric assumption*: first-order specular paths computed from the
  entered box (:func:`predict_first_order`).

A single microphone cannot locate a wall: one reflection delay fixes the
sum of two distances, which is an ellipsoid, not a point. Nothing here
claims otherwise; a match between a reflection and a predicted path says
the two *agree*, not that the wall is where the box says.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

from reverbscope.core.placement import speed_of_sound_m_s
from reverbscope.geometry.room import GeometryError, Point, RoomBox, RoomGeometry
from reverbscope.i18n import N_, _, list_join
from reverbscope.models.result import AnalysisResult

Face = Literal["x0", "x1", "y0", "y1", "z0", "z1"]
FACES: tuple[Face, ...] = ("x0", "x1", "y0", "y1", "z0", "z1")

#: How far an entered position may be from the true one (m) when nothing
#: better is known: a tape measure to a loudspeaker's acoustic centre and a
#: microphone capsule is good to a few centimetres.
DEFAULT_POSITION_UNCERTAINTY_M = 0.05
#: Temperature assumed when the measurement carries none (as in placement).
ASSUMED_TEMPERATURE_C = 20.0

#: Shown next to every reflection overlay.
SINGLE_MICROPHONE_NOTE = N_(
    "one microphone cannot locate a wall: one reflection fixes an ellipsoid of possible "
    "reflection points, not a point"
)

CheckStatus = Literal["ok", "warn", "unknown"]
MatchKind = Literal["none", "single", "ambiguous"]

_AXIS = {"x": 0, "y": 1, "z": 2}


def _face_axis(face: str) -> tuple[int, bool]:
    """``(axis index, at the far side)`` of a face name."""
    if face not in FACES:
        raise GeometryError(_("unknown face '{face}'").format(face=face))
    return _AXIS[face[0]], face[1] == "1"


def _plane(face: str, box: RoomBox) -> tuple[int, float]:
    axis, far = _face_axis(face)
    return axis, box.dimensions[axis] if far else 0.0


def face_label(face: str) -> str:
    """The face named by its coordinate when the box size is not at hand."""
    axis, far = _face_axis(face)
    name = face[0]
    if not far:
        return _("the face at {axis} = 0").format(axis=name)
    if axis == 0:
        return _("the face at x = the room's length")
    if axis == 1:
        return _("the face at y = the room's width")
    return _("the face at z = the room's height")


def face_text(face: str, box: RoomBox) -> str:
    """The face named by its coordinate: "the face at x = 5.00 m".

    Never "front wall": the program does not know which way the user faces,
    and a coordinate can be checked against the plan view.
    """
    _axis, value = _plane(face, box)
    return _("the face at {axis} = {value:.2f} m").format(axis=face[0], value=value)


def direct_distance(geometry: RoomGeometry, position: str) -> float | None:
    """Entered loudspeaker-to-microphone distance (m), or None without both."""
    microphone = geometry.microphone(position)
    if geometry.source is None or microphone is None:
        return None
    return geometry.source.distance_to(microphone)


@dataclass(frozen=True)
class ReflectionConstraint:
    """What one reflection delay supports by itself.

    The excess path ``c * delay`` is always known. With the direct distance
    ``d`` the total path ``L = d + excess`` is known too, and every point
    whose distances to the loudspeaker and to the microphone add up to ``L``
    could have reflected it: an ellipsoid with the two as foci and semi-major
    axis ``L / 2``. By the triangle inequality the reflection point is
    between ``(L - d) / 2`` and ``(L + d) / 2`` from the microphone.
    """

    delay_ms: float
    speed_m_s: float
    excess_path_m: float
    direct_distance_m: float | None
    total_path_m: float | None
    semi_major_m: float | None
    semi_minor_m: float | None
    distance_from_microphone_m: tuple[float, float] | None
    #: True when the direct distance is unknown, so only the excess path is.
    excess_only: bool
    text: str


def constraint_for(
    delay_ms: float, direct_distance_m: float | None, speed_m_s: float
) -> ReflectionConstraint:
    """The ellipsoid (or, without ``d``, only the excess path) of one reflection."""
    if not math.isfinite(delay_ms) or delay_ms < 0.0:
        raise GeometryError(_("a reflection delay must be a finite number of ms, 0 or more"))
    if not math.isfinite(speed_m_s) or speed_m_s <= 0.0:
        raise GeometryError(_("the speed of sound must be a positive number"))
    excess = speed_m_s * delay_ms / 1000.0
    if direct_distance_m is None:
        return ReflectionConstraint(
            delay_ms=delay_ms,
            speed_m_s=speed_m_s,
            excess_path_m=excess,
            direct_distance_m=None,
            total_path_m=None,
            semi_major_m=None,
            semi_minor_m=None,
            distance_from_microphone_m=None,
            excess_only=True,
            text=_(
                "the reflected sound travelled {excess:.2f} m further than the direct sound; "
                "without the loudspeaker-to-microphone distance nothing more is known"
            ).format(excess=excess),
        )
    if not math.isfinite(direct_distance_m) or direct_distance_m < 0.0:
        raise GeometryError(_("the direct distance must be a finite number of m, 0 or more"))
    d = direct_distance_m
    total = d + excess
    semi_major = total / 2.0
    semi_minor = math.sqrt(max(0.0, semi_major**2 - (d / 2.0) ** 2))
    low, high = (total - d) / 2.0, (total + d) / 2.0
    return ReflectionConstraint(
        delay_ms=delay_ms,
        speed_m_s=speed_m_s,
        excess_path_m=excess,
        direct_distance_m=d,
        total_path_m=total,
        semi_major_m=semi_major,
        semi_minor_m=semi_minor,
        distance_from_microphone_m=(low, high),
        excess_only=False,
        text=_(
            "reflected path {total:.2f} m ({excess:.2f} m longer than the direct sound): the "
            "reflection point lies on an ellipsoid around the loudspeaker and the microphone, "
            "{low:.2f} to {high:.2f} m from the microphone"
        ).format(total=total, excess=excess, low=low, high=high),
    )


def _reflections_searched(result: AnalysisResult) -> bool:
    """False when no stretch of the impulse response was searched for reflections."""
    window = result.reflections.analysed_window_ms or result.reflections.window_ms
    return window[1] > window[0]


def overlay_refusal(result: AnalysisResult) -> str | None:
    """Why the measured overlays must not be drawn for ``result``, or None.

    Reflection delays are times after the direct sound. If the direct sound
    is in doubt, so is every delay, and an ellipsoid drawn from them would
    look exact while being wrong.
    """
    ir = result.impulse_response
    if ir.samples.size == 0:
        return _("no impulse response is stored with this result, so nothing measured is drawn")
    if ir.playback_speed is not None:
        return _(
            "the sweep was played at the wrong speed, so the delays in this result are not "
            "reliable and nothing measured is drawn"
        )
    if ir.direct_sound_confidence == "low" or result.reflections.direct_sound_confidence == "low":
        return _(
            "the direct sound was not detected with confidence, so the reflection delays may "
            "be measured from the wrong peak and nothing measured is drawn"
        )
    if not _reflections_searched(result):
        return _("no reflections were searched in this result, so nothing measured is drawn")
    return None


def mirror_point(point: Point, face: str, box: RoomBox) -> Point:
    """``point`` mirrored in the plane of ``face``: the image source."""
    axis, plane = _plane(face, box)
    values = list(point.as_tuple())
    values[axis] = 2.0 * plane - values[axis]
    return Point(*values)


def specular_point(source: Point, mic: Point, face: str, box: RoomBox) -> Point | None:
    """Where the first-order specular path off ``face`` meets it, or None.

    The path runs straight from the image source to the microphone; it meets
    the plane where that line crosses it. None when the line does not cross
    the plane between the two (a position on or beyond the face) or crosses
    it outside the face's rectangle.
    """
    axis, plane = _plane(face, box)
    image = mirror_point(source, face, box).as_tuple()
    target = mic.as_tuple()
    span = target[axis] - image[axis]
    if span == 0.0:
        return None
    t = (plane - image[axis]) / span
    if not 0.0 <= t <= 1.0:
        return None
    if (source.as_tuple()[axis] - plane) * (target[axis] - plane) <= 0.0:
        # On the face, or on opposite sides of it: no reflection off it.
        return None
    hit = [image[i] + t * (target[i] - image[i]) for i in range(3)]
    hit[axis] = plane
    eps = 1e-9
    for i, size in enumerate(box.dimensions):
        if i != axis and not -eps <= hit[i] <= size + eps:
            return None
    return Point(*hit)


@dataclass(frozen=True)
class PredictedPath:
    """A first-order specular path of the entered box: an assumption, not a measurement."""

    face: Face
    point: Point
    path_length_m: float
    #: Arrival after the direct sound (ms).
    delay_ms: float


def predict_first_order(
    geometry: RoomGeometry, position: str, speed_m_s: float
) -> list[PredictedPath]:
    """The six first-order paths (fewer when one misses its face), earliest first.

    Empty when the box, the loudspeaker or the microphone was not entered.
    """
    microphone = geometry.microphone(position)
    if geometry.room is None or geometry.source is None or microphone is None:
        return []
    if not math.isfinite(speed_m_s) or speed_m_s <= 0.0:
        raise GeometryError(_("the speed of sound must be a positive number"))
    box, source = geometry.room, geometry.source
    direct = source.distance_to(microphone)
    paths: list[PredictedPath] = []
    for face in FACES:
        point = specular_point(source, microphone, face, box)
        if point is None:
            continue
        length = mirror_point(source, face, box).distance_to(microphone)
        paths.append(
            PredictedPath(
                face=face,
                point=point,
                path_length_m=length,
                delay_ms=(length - direct) / speed_m_s * 1000.0,
            )
        )
    paths.sort(key=lambda path: path.delay_ms)
    return paths


def tolerance_ms(
    sample_rate: int,
    speed_m_s: float,
    position_uncertainty_m: float = DEFAULT_POSITION_UNCERTAINTY_M,
) -> float:
    """How far a detected delay may be from a predicted one and still agree (ms).

    One sample period, because a detected reflection sits on a sample, plus
    ``2 * uncertainty / c``: an entered position that is off by ``u`` moves
    the reflected and the direct path by up to ``u`` each, so their
    difference, which is what the delay measures, by up to ``2 u``.
    """
    if sample_rate <= 0:
        raise GeometryError(_("the sample rate must be a positive number"))
    if not math.isfinite(speed_m_s) or speed_m_s <= 0.0:
        raise GeometryError(_("the speed of sound must be a positive number"))
    if not math.isfinite(position_uncertainty_m) or position_uncertainty_m < 0.0:
        raise GeometryError(_("the position uncertainty must be 0 m or more"))
    return 1000.0 / sample_rate + 2.0 * position_uncertainty_m / speed_m_s * 1000.0


@dataclass(frozen=True)
class ReflectionMatch:
    """A detected reflection against the predicted first-order paths.

    ``candidates`` pairs each path within the tolerance with its residual
    (detected minus predicted, ms), smallest residual first.
    """

    kind: MatchKind
    delay_ms: float
    candidates: tuple[tuple[PredictedPath, float], ...]
    tolerance_ms: float

    def text(self, box: RoomBox) -> str:
        """One sentence for the inspector, faces named by their coordinates."""
        if self.kind == "none":
            return _(
                "no first-order path of the entered room arrives within ±{tolerance:.2f} ms "
                "of {delay:.2f} ms"
            ).format(tolerance=self.tolerance_ms, delay=self.delay_ms)
        if self.kind == "single":
            path, residual = self.candidates[0]
            return _(
                "agrees with the first-order path off {face} (residual {residual:+.2f} ms); "
                "this is the entered room's prediction, not a located wall"
            ).format(face=face_text(path.face, box), residual=residual)
        items = [
            _("{face} ({residual:+.2f} ms)").format(
                face=face_text(path.face, box), residual=residual
            )
            for path, residual in self.candidates
        ]
        return _(
            "ambiguous: {count} first-order paths arrive within ±{tolerance:.2f} ms: {paths}"
        ).format(count=len(items), tolerance=self.tolerance_ms, paths=list_join(items))


def match_reflection(
    delay_ms: float, predictions: list[PredictedPath], tolerance_ms: float
) -> ReflectionMatch:
    """Every prediction within ``tolerance_ms`` of ``delay_ms`` is a candidate.

    Two faces predicted close together cannot be told apart by one delay, so
    both are kept and the match is ambiguous rather than the nearer one
    being picked.
    """
    found = [
        (path, delay_ms - path.delay_ms)
        for path in predictions
        if abs(delay_ms - path.delay_ms) <= tolerance_ms
    ]
    found.sort(key=lambda item: (abs(item[1]), FACES.index(item[0].face)))
    kind: MatchKind = "none" if not found else "single" if len(found) == 1 else "ambiguous"
    return ReflectionMatch(
        kind=kind, delay_ms=delay_ms, candidates=tuple(found), tolerance_ms=tolerance_ms
    )


@dataclass(frozen=True)
class ConsistencyCheck:
    name: str
    status: CheckStatus
    text: str


def speed_for(result: AnalysisResult) -> tuple[float, float, bool]:
    """``(speed m/s, temperature °C, assumed)`` for ``result``.

    The temperature comes from the placement inputs; without them 20 °C is
    assumed, as the placement analysis does, and the caller says so.
    """
    placement = result.placement
    if placement is not None and math.isfinite(placement.temperature_c):
        temperature = placement.temperature_c
        return speed_of_sound_m_s(temperature), temperature, placement.temperature_assumed
    return speed_of_sound_m_s(ASSUMED_TEMPERATURE_C), ASSUMED_TEMPERATURE_C, True


def _speed_check(speed: float, temperature: float, assumed: bool) -> ConsistencyCheck:
    if assumed:
        return ConsistencyCheck(
            "speed_of_sound",
            "unknown",
            _(
                "no temperature was entered for this measurement; {temperature:.0f} °C "
                "({speed:.1f} m/s) is assumed"
            ).format(temperature=temperature, speed=speed),
        )
    return ConsistencyCheck(
        "speed_of_sound",
        "ok",
        _("speed of sound {speed:.1f} m/s for the entered {temperature:.1f} °C").format(
            speed=speed, temperature=temperature
        ),
    )


def _inside_check(
    name: str, box: RoomBox | None, point: Point | None, inside: str, outside: str, missing: str
) -> ConsistencyCheck:
    if box is None or point is None:
        return ConsistencyCheck(name, "unknown", missing)
    if box.contains(point):
        return ConsistencyCheck(name, "ok", inside)
    return ConsistencyCheck(name, "warn", outside)


def _distance_check(entered: float | None, taped: float | None, limit: float) -> ConsistencyCheck:
    if entered is None:
        return ConsistencyCheck(
            "direct_distance",
            "unknown",
            _(
                "the loudspeaker or the microphone position is not entered, so the direct "
                "distance cannot be compared"
            ),
        )
    if taped is None:
        return ConsistencyCheck(
            "direct_distance",
            "unknown",
            _(
                "the entered positions are {entered:.2f} m apart; no measured distance was "
                "stored with this result to compare it with"
            ).format(entered=entered),
        )
    difference = entered - taped
    if abs(difference) <= limit:
        return ConsistencyCheck(
            "direct_distance",
            "ok",
            _(
                "the entered positions are {entered:.2f} m apart, as the {taped:.2f} m "
                "measured for this result"
            ).format(entered=entered, taped=taped),
        )
    return ConsistencyCheck(
        "direct_distance",
        "warn",
        _(
            "the entered positions are {entered:.2f} m apart, but {taped:.2f} m was measured "
            "for this result ({difference:+.2f} m); check the positions"
        ).format(entered=entered, taped=taped, difference=difference),
    )


def _height_check(mic: Point | None, measured: float | None, limit: float) -> ConsistencyCheck:
    if mic is None:
        return ConsistencyCheck(
            "microphone_height",
            "unknown",
            _("the microphone position is not entered, so its height cannot be compared"),
        )
    if measured is None:
        return ConsistencyCheck(
            "microphone_height",
            "unknown",
            _(
                "the microphone is entered at z = {entered:.2f} m; no microphone height was "
                "stored with this result to compare it with"
            ).format(entered=mic.z),
        )
    difference = mic.z - measured
    if abs(difference) <= limit:
        return ConsistencyCheck(
            "microphone_height",
            "ok",
            _(
                "the microphone is entered at z = {entered:.2f} m, as the {measured:.2f} m "
                "height measured for this result"
            ).format(entered=mic.z, measured=measured),
        )
    return ConsistencyCheck(
        "microphone_height",
        "warn",
        _(
            "the microphone is entered at z = {entered:.2f} m, but a height of {measured:.2f} m "
            "was measured for this result ({difference:+.2f} m)"
        ).format(entered=mic.z, measured=measured, difference=difference),
    )


def _loopback_check(
    result: AnalysisResult, entered: float | None, limit: float
) -> ConsistencyCheck:
    loopback = result.impulse_response.loopback
    bound = loopback.distance_upper_bound_m if loopback is not None else None
    if bound is None:
        return ConsistencyCheck(
            "loopback_bound",
            "unknown",
            _("this result has no loopback distance bound to compare the entered distance with"),
        )
    if entered is None:
        return ConsistencyCheck(
            "loopback_bound",
            "unknown",
            _(
                "the loopback allows at most {bound:.2f} m; the loudspeaker or the microphone "
                "position is not entered"
            ).format(bound=bound),
        )
    if entered <= bound + limit:
        return ConsistencyCheck(
            "loopback_bound",
            "ok",
            _(
                "the entered distance of {entered:.2f} m is within the {bound:.2f} m the "
                "loopback allows"
            ).format(entered=entered, bound=bound),
        )
    return ConsistencyCheck(
        "loopback_bound",
        "warn",
        _(
            "the entered distance of {entered:.2f} m is more than the {bound:.2f} m the "
            "loopback allows: sound cannot arrive before it was sent, so a position is wrong"
        ).format(entered=entered, bound=bound),
    )


def _earliest_check(
    result: AnalysisResult, geometry: RoomGeometry, position: str, speed: float
) -> ConsistencyCheck:
    name = "earliest_reflection"
    refusal = overlay_refusal(result)
    if refusal is not None:
        return ConsistencyCheck(name, "unknown", refusal)
    predictions = predict_first_order(geometry, position, speed)
    if not predictions:
        return ConsistencyCheck(
            name,
            "unknown",
            _(
                "the room box, the loudspeaker or the microphone is not entered, so no "
                "first-order path can be predicted"
            ),
        )
    window = result.reflections.analysed_window_ms or result.reflections.window_ms
    searched = [path for path in predictions if window[0] <= path.delay_ms <= window[1]]
    if not searched:
        return ConsistencyCheck(
            name,
            "unknown",
            _(
                "no predicted first-order path falls in the searched window of "
                "{start:.1f} to {stop:.1f} ms"
            ).format(start=window[0], stop=window[1]),
        )
    if not result.reflections.reflections:
        return ConsistencyCheck(
            name,
            "unknown",
            _("no reflection was detected, so the predicted paths cannot be compared"),
        )
    detected = min(reflection.delay_ms for reflection in result.reflections.reflections)
    predicted = searched[0]
    tolerance = tolerance_ms(result.sample_rate, speed)
    residual = detected - predicted.delay_ms
    box = geometry.room
    assert box is not None  # predictions exist only with a box
    if abs(residual) <= tolerance:
        return ConsistencyCheck(
            name,
            "ok",
            _(
                "the earliest detected reflection ({detected:.2f} ms) agrees with the earliest "
                "predicted path, off {face} ({predicted:.2f} ms, residual {residual:+.2f} ms)"
            ).format(
                detected=detected,
                face=face_text(predicted.face, box),
                predicted=predicted.delay_ms,
                residual=residual,
            ),
        )
    if residual < 0.0:
        return ConsistencyCheck(
            name,
            "warn",
            _(
                "the earliest detected reflection ({detected:.2f} ms) arrives before the "
                "earliest predicted path ({predicted:.2f} ms): something nearer than the room's "
                "faces (a desk, a stand) reflects, or an entered position is off"
            ).format(detected=detected, predicted=predicted.delay_ms),
        )
    return ConsistencyCheck(
        name,
        "warn",
        _(
            "the earliest detected reflection ({detected:.2f} ms) arrives after the earliest "
            "predicted path ({predicted:.2f} ms): that face may absorb, or an entered position "
            "is off"
        ).format(detected=detected, predicted=predicted.delay_ms),
    )


def consistency_checks(
    result: AnalysisResult, geometry: RoomGeometry, position: str
) -> list[ConsistencyCheck]:
    """The entered geometry against what ``result`` stored, one check per line.

    Every check that lacks an input says so (``unknown``) instead of passing.
    The checks compare numbers; none of them, and no combination of them,
    locates a wall.
    """
    speed, temperature, assumed = speed_for(result)
    mic = geometry.microphone(position)
    box = geometry.room
    limit = 2.0 * DEFAULT_POSITION_UNCERTAINTY_M
    entered = direct_distance(geometry, position)
    placement = result.placement
    return [
        _speed_check(speed, temperature, assumed),
        _inside_check(
            "source_inside",
            box,
            geometry.source,
            _("the loudspeaker is inside the entered room box"),
            _("the loudspeaker is outside the entered room box"),
            _("the room box or the loudspeaker position is not entered"),
        ),
        _inside_check(
            "microphone_inside",
            box,
            mic,
            _("the microphone is inside the entered room box"),
            _("the microphone is outside the entered room box"),
            _("the room box or the microphone position is not entered"),
        ),
        _distance_check(entered, placement.distance_m if placement else None, limit),
        _height_check(mic, placement.mic_height_m if placement else None, limit),
        _loopback_check(result, entered, limit),
        _earliest_check(result, geometry, position, speed),
    ]
