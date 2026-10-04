"""Vertical geometry from the early reflections and one tape measurement.

What this module may and may not claim
--------------------------------------
A single omnidirectional microphone at a single position measures *path
lengths*, not directions, and the deconvolved impulse response has no absolute
time origin (its zero contains the interface round-trip latency). Writing the
image-source model of a first-order reflection off a plane perpendicular to
some axis, with ``s`` and ``r`` the perpendicular distances of loudspeaker and
microphone from that plane, ``d`` their straight-line separation, ``u = s + r``
and ``v = s - r``::

    L^2 - d^2 = u^2 - v^2 = 4*s*r

Four independent arrival equations constrain six unknowns. Without a measured
``d`` the deficit is three; with it, two. The residual freedom is exactly the
*direction* of the loudspeaker-to-microphone vector: every direction
reproduces the measured arrival times, so no coordinate, room length, room
width or wall distance can be derived. What survives that freedom is::

    P := s*r = c*delta*(2*d + c*delta) / 4          (exact, per reflection)

and, once the user supplies one perpendicular distance ``h``, the whole
axis perpendicular to that plane::

    s = P / h                                       (loudspeaker side)
    H = (u + sqrt(L_upper^2 - d^2 + v^2)) / 2       (the opposite plane)
    q = sqrt(d^2 - v^2)                             (horizontal separation)

Those are the only quantities this module reports. See
:data:`~roomscope.models.result.PLACEMENT_COORDINATES_WITHHELD`, which is
emitted verbatim in the JSON.

**Source.** The image-source construction for a plane reflector is standard
(Allen & Berkley 1979 is the canonical *forward* method); the identity
``L^2 - d^2 = 4*s*r`` used here is elementary algebra from it and is
implemented clean-room. RoomScope deliberately does *not* implement
room-shape-from-echoes / echo sorting (Dokmanic et al., PNAS 110(30), 2013,
and the echo-labelling work that follows it), which is the published route to
the full geometry and requires a microphone array or several positions; see
docs/MEASUREMENT_METHODOLOGY.md.

Tiers
-----
The single code path degrades explicitly as inputs are withheld:

* **0** -- temperature only: every candidate carries its excess path in metres.
* **1** -- and ``distance_m``: the per-candidate product of perpendicular
  distances, its bounds, and the specular level ceiling.
* **2** -- and ``mic_height_m``: the vertical axis is solved.

Thresholds and their justification
----------------------------------
Tier 1 (geometry, no free choice): the level ceiling ``20*log10(d/L)``.
Tier 2 (physical plausibility, wide by design): the height and ceiling ranges.
Tier 3 (RoomScope engineering choices, not standards):
:data:`MAX_SURFACE_ATTENUATION_DB`, :data:`SPECULAR_EXCESS_TOLERANCE_DB`,
:data:`HEIGHT_AGREEMENT_M`, :data:`CEILING_AGREEMENT_M`. The level gate is a
*tier 3* screen, not pure geometry: it assumes a point source radiating into a
free field, an infinite rigid plane, and that a broadband peak-held envelope
peak is comparable with an on-axis level. It is used to withhold an
attribution, never to assert what a candidate is.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, replace

from roomscope.i18n import diag
from roomscope.models.result import (
    SPEED_OF_SOUND_REFERENCE,
    BoundaryCandidate,
    PlacementLength,
    PlacementResult,
    Reflection,
    ReflectionsResult,
    Validity,
)

#: Air temperature assumed when the user states none. Never applied silently:
#: :attr:`PlacementResult.temperature_assumed` records it.
DEFAULT_TEMPERATURE_C = 20.0
#: 1-sigma allowed for an unstated temperature (~0.9 % of ``c``).
TEMPERATURE_SIGMA_C = 5.0
#: Assumed 1-sigma of a tape measurement of the loudspeaker-microphone distance.
DISTANCE_SIGMA_M = 0.02
#: Assumed 1-sigma of a tape measurement of the microphone height.
HEIGHT_SIGMA_M = 0.01
#: Half the 0.1 ms peak-hold of :mod:`roomscope.core.reflections`.
PEAK_LOCATION_SIGMA_MS = 0.05

#: How far above the specular ceiling a candidate may read and still be
#: considered (tier 3).
SPECULAR_EXCESS_TOLERANCE_DB = 2.0
#: How far below the specular ceiling a candidate may read and still be treated
#: as a discrete plane rather than diffuse energy (tier 3).
MAX_SURFACE_ATTENUATION_DB = 12.0

MIN_SOURCE_HEIGHT_M = 0.10
MAX_SOURCE_HEIGHT_M = 3.00
MIN_CEILING_M = 1.80
MAX_CEILING_M = 6.00
#: The opposite plane must clear both devices by at least this much.
MIN_CEILING_CLEARANCE_M = 0.30
#: Tape slack allowed when checking that the vertical separation of the two
#: devices does not exceed their straight-line distance.
DISTANCE_SLACK_M = 0.02
#: Minimum horizontal separation that is not numerically degenerate.
MIN_HORIZONTAL_SEPARATION_M = 0.05

#: Minimum separation the reflection search can resolve: two arrivals closer
#: than this become one envelope peak (``min_distance`` in
#: :mod:`roomscope.core.reflections`, plus its 0.1 ms peak-hold).
MERGE_RESOLUTION_MS = 0.3
#: Hypotheses closer together than this are the same answer (tier 3).
HEIGHT_AGREEMENT_M = 0.08
CEILING_AGREEMENT_M = 0.12
#: Only the earliest N candidates are considered as plane hypotheses.
MAX_HYPOTHESIS_CANDIDATES = 8

LOWER_PLANE = "lower_plane"
UPPER_PLANE = "upper_plane"

_NOT_COMPUTED = Validity.NOT_COMPUTED


def speed_of_sound_m_s(temperature_c: float) -> float:
    """``c = 331.3 * sqrt(1 + T/273.15)`` in m/s. 343.2 m/s at 20 C."""
    if temperature_c <= -273.15:
        raise ValueError("temperature must be above absolute zero")
    return 331.3 * math.sqrt(1.0 + temperature_c / 273.15)


def mirror_path_m(distance_m: float, delay_ms: float, speed_m_s: float) -> float:
    """``L = d + c*delta``: the image-source path length (m)."""
    return distance_m + speed_m_s * delay_ms / 1000.0


def boundary_product_m2(distance_m: float, delay_ms: float, speed_m_s: float) -> float:
    """``s*r = c*delta*(2d + c*delta)/4`` (m^2), exact for a flat reflector."""
    excess = speed_m_s * delay_ms / 1000.0
    return excess * (2.0 * distance_m + excess) / 4.0


def specular_ceiling_db(distance_m: float, path_m: float) -> float:
    """``20*log10(d/L)``: what a lossless point source mirrored in a rigid plane
    would read at that path length, in dB relative to the direct sound."""
    return 20.0 * math.log10(distance_m / path_m)


@dataclass(frozen=True)
class _Hypothesis:
    """One candidate read as a particular plane."""

    index: int
    delay_ms: float
    metres: float


def _propagate(
    fn: Callable[..., float],
    nominal: dict[str, float],
    sigmas: dict[str, float],
) -> float | None:
    """1-sigma of ``fn(**nominal)`` by a numeric Jacobian, combined in quadrature.

    Input uncertainty only; model error is excluded, and
    :data:`~roomscope.models.result.PLACEMENT_UNCERTAINTY_EXCLUDES` says so in
    the JSON beside every figure this produces.
    """
    try:
        base = float(fn(**nominal))
    except (ValueError, ZeroDivisionError):
        return None
    total = 0.0
    for name, sigma in sigmas.items():
        if sigma <= 0.0 or name not in nominal:
            continue
        step = max(abs(nominal[name]) * 1e-6, 1e-9)
        shifted = dict(nominal)
        shifted[name] = nominal[name] + step
        try:
            moved = float(fn(**shifted))
        except (ValueError, ZeroDivisionError):
            return None
        total += ((moved - base) / step * sigma) ** 2
    if not math.isfinite(total):
        return None
    return math.sqrt(total)


def _refused(reason: str, missing_input: str | None = None) -> PlacementLength:
    return PlacementLength(
        metres=None, validity=_NOT_COMPUTED, reason=reason, missing_input=missing_input
    )


def _resolve(
    hypotheses: list[_Hypothesis],
    agreement_m: float,
    *,
    empty_reason: str,
    uncertainty_m: float | None,
) -> tuple[PlacementLength, int | None]:
    """The unique-or-refuse rule: agree, or say which values competed.

    Returns the length and the index of the candidate it came from (``None``
    when nothing was resolved). There is deliberately no tie-break: picking the
    earliest is wrong exactly in the commonest setup (a desk edge arrives
    before the desk top) and picking the loudest is wrong whenever the lower
    plane is carpeted.
    """
    if not hypotheses:
        return _refused(empty_reason), None
    values = sorted(h.metres for h in hypotheses)
    if values[-1] - values[0] <= agreement_m:
        median = float(values[len(values) // 2])
        chosen = min(hypotheses, key=lambda h: abs(h.metres - median))
        return (
            PlacementLength(
                metres=median,
                validity=Validity.VALID,
                input_uncertainty_m=uncertainty_m,
            ),
            chosen.index,
        )
    listed = " or ".join(f"{v:.2f} m" for v in values)
    return (
        PlacementLength(
            metres=None,
            validity=_NOT_COMPUTED,
            reason=diag(
                "more than one reflection could be the surface the height was measured "
                "from, and they disagree by more than {agreement_cm:.0f} cm: {values}. "
                "RoomScope does not choose between them. This is the expected outcome when "
                "the microphone sits near the vertical midpoint of the room, where the "
                "arrival from the surface below and the one from the surface above are "
                "interchangeable; moving the microphone 20-30 cm up or down and measuring "
                "again separates them",
                agreement_cm=agreement_m * 100,
                values=listed,
            ),
            alternatives_m=tuple(values),
        ),
        None,
    )


def _tier0_candidate(reflection: Reflection, speed_m_s: float) -> BoundaryCandidate:
    return BoundaryCandidate(
        delay_ms=reflection.delay_ms,
        relative_db=reflection.relative_db,
        excess_path_m=speed_m_s * reflection.delay_ms / 1000.0,
    )


def _tier1_candidate(
    reflection: Reflection, speed_m_s: float, distance_m: float
) -> BoundaryCandidate:
    excess = speed_m_s * reflection.delay_ms / 1000.0
    path = distance_m + excess
    product = excess * (2.0 * distance_m + excess) / 4.0
    geometric_mean = math.sqrt(product)
    # 0 <= (s-r)^2 <= d^2 brackets the arithmetic mean exactly; its lower end
    # coincides with the geometric mean (AM >= GM) and its upper end is L/2.
    bracket = (geometric_mean, path / 2.0)
    return BoundaryCandidate(
        delay_ms=reflection.delay_ms,
        relative_db=reflection.relative_db,
        excess_path_m=excess,
        mirror_path_m=path,
        product_m2=product,
        geometric_mean_m=geometric_mean,
        mean_distance_bracket_m=bracket,
        specular_ceiling_db=specular_ceiling_db(distance_m, path),
    )


def _screen_level(
    candidate: BoundaryCandidate, max_attenuation_db: float
) -> tuple[bool, str | None, str | None]:
    """Tier-3 level screen. Returns (usable, reason_when_not, rejection_when_not).

    ``reason_when_not`` is stored on the candidate; ``rejection_when_not`` is
    the same statement with the candidate named, for the refusal reason.
    Never asserts what a candidate *is*; only whether it is treated as a
    first-order specular arrival from a flat plane.
    """
    ceiling = candidate.specular_ceiling_db
    assert ceiling is not None
    excess_db = candidate.relative_db - ceiling
    if excess_db > SPECULAR_EXCESS_TOLERANCE_DB:
        return (
            False,
            diag(
                "reads {excess:.1f} dB above what a lossless point source mirrored in a "
                "rigid plane would give at that path length, so it is not treated as a "
                "first-order specular arrival (it may be two arrivals merged by the envelope "
                "peak-hold, a comb-filter artefact or a peak of the dense early tail)",
                excess=excess_db,
            ),
            diag(
                "the {delay:.1f} ms candidate reads {excess:.1f} dB above what a lossless "
                "point source mirrored in a rigid plane would give at that path length, so it "
                "is not treated as a first-order specular arrival (it may be two arrivals "
                "merged by the envelope peak-hold, a comb-filter artefact or a peak of the "
                "dense early tail)",
                delay=candidate.delay_ms,
                excess=excess_db,
            ),
        )
    if excess_db < -max_attenuation_db:
        return (
            False,
            diag(
                "reads {attenuation:.1f} dB below that ceiling, more than the "
                "{limit:.0f} dB RoomScope treats as the limit for a discrete "
                "plane reflection, so it is not used to attribute a surface",
                attenuation=-excess_db,
                limit=max_attenuation_db,
            ),
            diag(
                "the {delay:.1f} ms candidate reads {attenuation:.1f} dB below that ceiling, "
                "more than the {limit:.0f} dB RoomScope treats as the limit for a discrete "
                "plane reflection, so it is not used to attribute a surface",
                delay=candidate.delay_ms,
                attenuation=-excess_db,
                limit=max_attenuation_db,
            ),
        )
    return True, None, None


def _no_geometry(
    *,
    candidates: tuple[BoundaryCandidate, ...],
    tier: int,
    speed_m_s: float,
    temperature_c: float,
    temperature_assumed: bool,
    distance_m: float | None,
    mic_height_m: float | None,
    reflections: ReflectionsResult,
    notes: list[str],
    reason: str,
    missing_input: str | None = None,
) -> PlacementResult:
    """A fully-formed result whose three lengths are all withheld."""
    refusal = _refused(reason, missing_input)
    return PlacementResult(
        tier=tier,
        candidates=candidates,
        source_height_m=refusal,
        ceiling_height_m=refusal,
        horizontal_separation_m=refusal,
        speed_of_sound_m_s=speed_m_s,
        temperature_c=temperature_c,
        temperature_assumed=temperature_assumed,
        distance_m=distance_m,
        mic_height_m=mic_height_m,
        analysed_window_ms=reflections.analysed_window_ms,
        window_truncated=reflections.window_truncated,
        notes=tuple(notes),
    )


def _inherited_notes(reflections: ReflectionsResult) -> list[str]:
    """Caveats the geometry inherits verbatim from the reflection search."""
    notes: list[str] = []
    for note in reflections.notes:
        if "statistical" in note or "20 strongest" in note or "too short" in note:
            notes.append(diag("inherited from the reflection search: {note}", note=note))
    if reflections.window_truncated and reflections.analysed_window_ms is not None:
        notes.append(
            diag(
                "the reflection search was cut short at {end:.1f} ms, and truncation does "
                "not drop arrivals at random: it drops the longest paths first, so any "
                "height derived from what remains is biased low",
                end=reflections.analysed_window_ms[1],
            )
        )
    return notes


def estimate_placement(
    reflections: ReflectionsResult,
    *,
    distance_m: float | None,
    mic_height_m: float | None,
    temperature_c: float | None,
    max_surface_attenuation_db: float = MAX_SURFACE_ATTENUATION_DB,
    height_agreement_m: float = HEIGHT_AGREEMENT_M,
    ceiling_agreement_m: float = CEILING_AGREEMENT_M,
) -> PlacementResult:
    """Vertical geometry from detected early reflections and the user's tape measure.

    ``mic_height_m`` is the microphone capsule above *the first solid
    horizontal surface below it* -- the desk top when the microphone is at a
    desk, otherwise the floor. Phrasing the question that way dissolves the
    desk-versus-floor ambiguity by definition; no acoustic evidence from one
    omnidirectional microphone could resolve it.
    """
    temperature_assumed = temperature_c is None
    temperature = DEFAULT_TEMPERATURE_C if temperature_c is None else temperature_c
    speed = speed_of_sound_m_s(temperature)
    notes = _inherited_notes(reflections)
    if temperature_assumed:
        notes.append(
            diag(
                "no air temperature was supplied, so {temperature:.0f} C ({speed:.1f} m/s) "
                "was assumed; a 5 C error moves every distance by about 0.9 %",
                temperature=DEFAULT_TEMPERATURE_C,
                speed=speed,
            )
        )

    # R1: every delay is relative to the detected direct sound. If that origin
    # was not established, no metre derived from it means anything.
    if reflections.direct_sound_confidence != "high":
        confidence = reflections.direct_sound_confidence
        if confidence == "low":
            origin_reason = diag(
                "direct-sound detection confidence is low, so the time origin every delay is "
                "measured from was not established and no distance derived from it is reported"
            )
        elif confidence == "medium":
            origin_reason = diag(
                "direct-sound detection confidence is medium, so the time origin every delay "
                "is measured from was not established and no distance derived from it is "
                "reported"
            )
        else:
            origin_reason = diag(
                "direct-sound detection confidence is {confidence}, so the time origin every "
                "delay is measured from was not established and no distance derived from it "
                "is reported",
                confidence=confidence,
            )
        return _no_geometry(
            candidates=(),
            tier=0,
            speed_m_s=speed,
            temperature_c=temperature,
            temperature_assumed=temperature_assumed,
            distance_m=distance_m,
            mic_height_m=mic_height_m,
            reflections=reflections,
            notes=notes,
            reason=origin_reason,
        )

    if distance_m is None:
        candidates = tuple(_tier0_candidate(r, speed) for r in reflections.reflections)
        return _no_geometry(
            candidates=candidates,
            tier=0,
            speed_m_s=speed,
            temperature_c=temperature,
            temperature_assumed=temperature_assumed,
            distance_m=None,
            mic_height_m=mic_height_m,
            reflections=reflections,
            notes=notes,
            reason=diag(
                "no loudspeaker-to-microphone distance was supplied; measure the straight "
                "line from the loudspeaker to the microphone capsule with a tape"
            ),
            missing_input="--speaker-distance",
        )

    tier1 = [_tier1_candidate(r, speed, distance_m) for r in reflections.reflections]

    if mic_height_m is None:
        return _no_geometry(
            candidates=tuple(tier1),
            tier=1,
            speed_m_s=speed,
            temperature_c=temperature,
            temperature_assumed=temperature_assumed,
            distance_m=distance_m,
            mic_height_m=None,
            reflections=reflections,
            notes=notes,
            reason=diag(
                "no microphone height was supplied, so no reflection can be attributed to "
                "a horizontal plane"
            ),
            missing_input="--mic-height",
        )

    # ---- Tier 2: the vertical solve -------------------------------------
    height = mic_height_m
    screened: list[BoundaryCandidate] = []
    lower: list[_Hypothesis] = []
    rejections: list[str] = []

    for index, candidate in enumerate(tier1):
        if index >= MAX_HYPOTHESIS_CANDIDATES:
            screened.append(candidate)
            continue
        usable, why, rejection = _screen_level(candidate, max_surface_attenuation_db)
        if not usable:
            assert rejection is not None
            screened.append(replace(candidate, interpretable_as_plane=False, excluded_reason=why))
            rejections.append(rejection)
            continue
        assert candidate.product_m2 is not None
        # Passing the level screen only says this may be a specular reflection
        # off some flat plane. Failing the gates below says it is not the plane
        # the height was measured from -- it stays a candidate for the one above.
        screened.append(replace(candidate, interpretable_as_plane=True))
        source_height = candidate.product_m2 / height
        separation = source_height - height
        if not MIN_SOURCE_HEIGHT_M <= source_height <= MAX_SOURCE_HEIGHT_M:
            rejections.append(
                diag(
                    "the {delay:.1f} ms candidate implies a loudspeaker {height:.2f} m above "
                    "the plane the height was measured from ({low:.2f}-{high:.2f} m is "
                    "treated as plausible)",
                    delay=candidate.delay_ms,
                    height=source_height,
                    low=MIN_SOURCE_HEIGHT_M,
                    high=MAX_SOURCE_HEIGHT_M,
                )
            )
        elif abs(separation) > distance_m + DISTANCE_SLACK_M:
            rejections.append(
                diag(
                    "the {delay:.1f} ms candidate implies a vertical separation of "
                    "{separation:.2f} m, which the {distance:.2f} m straight-line distance "
                    "cannot contain",
                    delay=candidate.delay_ms,
                    separation=abs(separation),
                    distance=distance_m,
                )
            )
        elif math.sqrt(max(distance_m**2 - separation**2, 0.0)) < MIN_HORIZONTAL_SEPARATION_M:
            rejections.append(
                diag(
                    "the {delay:.1f} ms candidate implies the loudspeaker is vertically above "
                    "the microphone, which leaves no horizontal separation",
                    delay=candidate.delay_ms,
                )
            )
        else:
            lower.append(
                _Hypothesis(index=index, delay_ms=candidate.delay_ms, metres=source_height)
            )

    if rejections:
        empty_reason = diag(
            "no detected reflection can be read as coming from the horizontal plane the "
            "microphone height was measured from: {rejections}",
            rejections="; ".join(rejections),
        )
    else:
        empty_reason = diag(
            "no detected reflection can be read as coming from the horizontal plane the "
            "microphone height was measured from; none was detected at all"
        )

    def _source_height(distance: float, delay: float, temperature_arg: float, mic: float) -> float:
        c = speed_of_sound_m_s(temperature_arg)
        return boundary_product_m2(distance, delay, c) / mic

    def _horizontal(distance: float, delay: float, temperature_arg: float, mic: float) -> float:
        lift = _source_height(distance, delay, temperature_arg, mic) - mic
        return math.sqrt(distance**2 - lift**2)

    def _upper_plane(
        distance: float, delay: float, upper_delay: float, temperature_arg: float, mic: float
    ) -> float:
        source = _source_height(distance, delay, temperature_arg, mic)
        mirror = distance + speed_of_sound_m_s(temperature_arg) * upper_delay / 1000.0
        return (source + mic + math.sqrt(mirror**2 - distance**2 + (source - mic) ** 2)) / 2.0

    input_sigmas = {
        "distance": DISTANCE_SIGMA_M,
        "delay": PEAK_LOCATION_SIGMA_MS,
        "upper_delay": PEAK_LOCATION_SIGMA_MS,
        "temperature_arg": TEMPERATURE_SIGMA_C if temperature_assumed else 1.0,
        "mic": HEIGHT_SIGMA_M,
    }

    source_length, source_index = _resolve(
        lower, height_agreement_m, empty_reason=empty_reason, uncertainty_m=None
    )

    ceiling_length = _refused(
        diag(
            "the plane the heights are measured from was not established, so nothing above "
            "it can be placed"
        )
    )
    horizontal_length = ceiling_length

    if source_length.validity is Validity.VALID and source_index is not None:
        source_height_value = source_length.metres
        assert source_height_value is not None
        u_z = source_height_value + height
        v_z = source_height_value - height
        horizontal = math.sqrt(max(distance_m**2 - v_z**2, 0.0))
        # Each length gets its own propagation: q and the upper plane depend on
        # the inputs differently from the loudspeaker height (q's sensitivity
        # to the height grows as the devices approach the vertical).
        source_nominal = {
            "distance": distance_m,
            "delay": tier1[source_index].delay_ms,
            "temperature_arg": temperature,
            "mic": height,
        }
        # At the arrival the reported height came from (the median of agreeing
        # hypotheses), not the earliest one.
        source_length = replace(
            source_length,
            input_uncertainty_m=_propagate(_source_height, source_nominal, input_sigmas),
        )
        horizontal_length = PlacementLength(
            metres=horizontal,
            validity=Validity.VALID,
            input_uncertainty_m=_propagate(_horizontal, source_nominal, input_sigmas),
        )
        upper: list[_Hypothesis] = []
        upper_rejections: list[str] = []
        for index, candidate in enumerate(screened):
            if index == source_index or candidate.interpretable_as_plane is not True:
                continue
            assert candidate.mirror_path_m is not None
            inner = candidate.mirror_path_m**2 - distance_m**2 + v_z**2
            if inner < 0.0:
                upper_rejections.append(
                    diag(
                        "the {delay:.1f} ms candidate has no real solution for a plane above "
                        "both devices",
                        delay=candidate.delay_ms,
                    )
                )
                continue
            upper_height = (u_z + math.sqrt(inner)) / 2.0
            if not MIN_CEILING_M <= upper_height <= MAX_CEILING_M:
                upper_rejections.append(
                    diag(
                        "the {delay:.1f} ms candidate implies an upper plane {height:.2f} m "
                        "above the lower one ({low:.1f}-{high:.1f} m is treated as plausible)",
                        delay=candidate.delay_ms,
                        height=upper_height,
                        low=MIN_CEILING_M,
                        high=MAX_CEILING_M,
                    )
                )
                continue
            if upper_height < max(source_height_value, height) + MIN_CEILING_CLEARANCE_M:
                upper_rejections.append(
                    diag(
                        "the {delay:.1f} ms candidate implies an upper plane {height:.2f} m up, "
                        "less than {clearance:.2f} m above the higher of the two devices",
                        delay=candidate.delay_ms,
                        height=upper_height,
                        clearance=MIN_CEILING_CLEARANCE_M,
                    )
                )
                continue
            upper.append(_Hypothesis(index=index, delay_ms=candidate.delay_ms, metres=upper_height))
        window = reflections.analysed_window_ms
        beyond_window: dict[str, float] | None = None
        if window is not None:
            # Image of the source in a plane at height H is at 2H - s_z, so the
            # arrival travels sqrt((2H - u_z)^2 + q^2) against the direct d.
            lowest_upper_delay = (
                (math.sqrt((2.0 * MIN_CEILING_M - u_z) ** 2 + horizontal**2) - distance_m)
                / speed
                * 1000.0
            )
            if lowest_upper_delay > window[1]:
                beyond_window = {
                    "lowest": MIN_CEILING_M,
                    "delay": lowest_upper_delay,
                    "start": window[0],
                    "end": window[1],
                }
        if upper_rejections and beyond_window is not None:
            upper_empty_reason = diag(
                "no detected reflection can be read as a plane above both devices: "
                "{rejections}; even the lowest plausible upper plane ({lowest:.1f} m) would "
                "arrive at about {delay:.1f} ms, beyond the {start:.1f}-{end:.1f} ms window "
                "that could be searched, so absence here is not evidence of absence",
                rejections="; ".join(upper_rejections),
                **beyond_window,
            )
        elif upper_rejections:
            upper_empty_reason = diag(
                "no detected reflection can be read as a plane above both devices: {rejections}",
                rejections="; ".join(upper_rejections),
            )
        elif beyond_window is not None:
            upper_empty_reason = diag(
                "no detected reflection can be read as a plane above both devices; even the "
                "lowest plausible upper plane ({lowest:.1f} m) would arrive at about "
                "{delay:.1f} ms, beyond the {start:.1f}-{end:.1f} ms window that could be "
                "searched, so absence here is not evidence of absence",
                **beyond_window,
            )
        else:
            upper_empty_reason = diag(
                "no detected reflection can be read as a plane above both devices"
            )
        ceiling_length, ceiling_index = _resolve(
            upper,
            ceiling_agreement_m,
            empty_reason=upper_empty_reason,
            uncertainty_m=None,
        )
        if ceiling_index is not None:
            ceiling_length = replace(
                ceiling_length,
                input_uncertainty_m=_propagate(
                    _upper_plane,
                    {**source_nominal, "upper_delay": tier1[ceiling_index].delay_ms},
                    input_sigmas,
                ),
            )
        # A height solved from a single arrival is only as good as that arrival
        # being ONE arrival. When no upper plane was established and a plausible
        # one would land within the detector's resolution of the arrival used
        # here, this reading may be two arrivals merged into one peak -- the
        # common case with a microphone near the vertical midpoint of a room.
        if ceiling_length.validity is not Validity.VALID and source_length.metres is not None:
            lowest_upper = max(
                MIN_CEILING_M, max(source_height_value, height) + MIN_CEILING_CLEARANCE_M
            )
            earliest_upper_ms = (
                (math.hypot(2.0 * lowest_upper - u_z, horizontal) - distance_m) / speed * 1000.0
            )
            used_delay = tier1[source_index].delay_ms
            if earliest_upper_ms <= used_delay + MERGE_RESOLUTION_MS:
                source_length = replace(
                    source_length,
                    validity=Validity.UNRELIABLE,
                    reason=diag(
                        "no separate arrival from a plane above the devices was found, and one "
                        "as low as {lowest:.2f} m would arrive at {earliest:.1f} ms -- within "
                        "the {resolution:.1f} ms the reflection search can resolve from the "
                        "{used:.1f} ms arrival this height was solved from. That arrival may "
                        "therefore be two arrivals merged into one peak, which would bias the "
                        "height. Moving the microphone 20-30 cm up or down and measuring again "
                        "separates them",
                        lowest=lowest_upper,
                        earliest=earliest_upper_ms,
                        resolution=MERGE_RESOLUTION_MS,
                        used=used_delay,
                    ),
                )
                horizontal_length = replace(
                    horizontal_length,
                    validity=Validity.UNRELIABLE,
                    reason=source_length.reason,
                )
        named: list[BoundaryCandidate] = []
        for index, candidate in enumerate(screened):
            surface = None
            if index == source_index:
                surface = LOWER_PLANE
            elif ceiling_index is not None and index == ceiling_index:
                surface = UPPER_PLANE
            named.append(replace(candidate, surface=surface) if surface else candidate)
        screened = named

    notes.append(
        diag(
            "only the two horizontal planes are ever named. No wall is identified: one "
            "omnidirectional microphone gives no bearing, so naming one would be a guess"
        )
    )
    return PlacementResult(
        tier=2,
        candidates=tuple(screened),
        source_height_m=source_length,
        ceiling_height_m=ceiling_length,
        horizontal_separation_m=horizontal_length,
        speed_of_sound_m_s=speed,
        temperature_c=temperature,
        temperature_assumed=temperature_assumed,
        distance_m=distance_m,
        mic_height_m=mic_height_m,
        analysed_window_ms=reflections.analysed_window_ms,
        window_truncated=reflections.window_truncated,
        notes=tuple(notes),
    )


__all__ = [
    "CEILING_AGREEMENT_M",
    "DEFAULT_TEMPERATURE_C",
    "HEIGHT_AGREEMENT_M",
    "LOWER_PLANE",
    "MAX_SURFACE_ATTENUATION_DB",
    "SPECULAR_EXCESS_TOLERANCE_DB",
    "SPEED_OF_SOUND_REFERENCE",
    "UPPER_PLANE",
    "boundary_product_m2",
    "estimate_placement",
    "mirror_path_m",
    "specular_ceiling_db",
    "speed_of_sound_m_s",
]
