from __future__ import annotations

import math
from dataclasses import replace

import numpy as np
import pytest

from reverbscope.core.placement import (
    DEFAULT_TEMPERATURE_C,
    LOWER_PLANE,
    MAX_HYPOTHESIS_CANDIDATES,
    MAX_SURFACE_ATTENUATION_DB,
    UPPER_PLANE,
    _propagate,
    boundary_product_m2,
    estimate_placement,
    mirror_path_m,
    specular_ceiling_db,
    speed_for_result,
    speed_of_sound_m_s,
)
from reverbscope.models.result import (
    AnalysisResult,
    PlacementLength,
    Reflection,
    ReflectionsResult,
    Validity,
)

C20 = speed_of_sound_m_s(DEFAULT_TEMPERATURE_C)


def _reflections(
    arrivals: list[tuple[float, float]],
    *,
    confidence: str = "high",
    window_ms: tuple[float, float] = (0.8, 80.0),
    analysed_ms: tuple[float, float] | None = None,
    truncated: bool = False,
    notes: tuple[str, ...] = (),
) -> ReflectionsResult:
    """A ReflectionsResult built directly, so the geometry is tested alone."""
    return ReflectionsResult(
        direct_sound_time_s=0.0,
        direct_sound_confidence=confidence,
        window_ms=window_ms,
        threshold_db=-20.0,
        reflections=tuple(Reflection(delay_ms=d, relative_db=lvl) for d, lvl in arrivals),
        notes=notes,
        analysed_window_ms=analysed_ms or window_ms,
        window_truncated=truncated,
    )


def _plane_arrival(distance_m: float, near: float, far: float, horizontal: float) -> float:
    """Delay (ms) of the first-order arrival off a plane, from the two
    perpendicular distances and the horizontal separation."""
    path = math.hypot(near + far, horizontal)
    return (path - distance_m) / C20 * 1000.0


def _lossy(distance_m: float, delay_ms: float, attenuation_db: float = 3.0) -> float:
    """A level that sits a realistic few dB under the specular ceiling."""
    return (
        specular_ceiling_db(distance_m, mirror_path_m(distance_m, delay_ms, C20)) - attenuation_db
    )


# --------------------------------------------------------------------------
# The exact identities the module is built on
# --------------------------------------------------------------------------


def test_speed_of_sound_matches_the_iso_form() -> None:
    assert speed_of_sound_m_s(20.0) == pytest.approx(343.2, abs=0.05)
    for t in (-10.0, 0.0, 20.0, 35.0):
        iso = 343.2 * math.sqrt((t + 273.15) / 293.15)
        assert speed_of_sound_m_s(t) == pytest.approx(iso, rel=1e-4)


def test_boundary_product_equals_the_product_of_perpendicular_distances() -> None:
    """``s*r = c*delta*(2d + c*delta)/4`` against a brute-force image source."""
    rng = np.random.default_rng(11)
    for _ in range(2000):
        s, r = rng.uniform(0.2, 3.0, 2)
        horizontal = float(rng.uniform(0.1, 6.0))
        distance = math.hypot(s - r, horizontal)
        delay_ms = _plane_arrival(distance, float(s), float(r), horizontal)
        assert boundary_product_m2(distance, delay_ms, C20) == pytest.approx(s * r, rel=1e-9)


def test_mean_distance_bracket_is_exact_and_brackets_the_truth() -> None:
    """The bracket on (s+r)/2 is a consequence of 0 <= (s-r)^2 <= d^2, not an estimate."""
    rng = np.random.default_rng(12)
    for _ in range(500):
        s, r = rng.uniform(0.2, 3.0, 2)
        horizontal = float(rng.uniform(0.1, 6.0))
        distance = math.hypot(s - r, horizontal)
        delay_ms = _plane_arrival(distance, float(s), float(r), horizontal)
        result = estimate_placement(
            _reflections([(delay_ms, _lossy(distance, delay_ms))]),
            distance_m=distance,
            mic_height_m=None,
            temperature_c=DEFAULT_TEMPERATURE_C,
        )
        candidate = result.candidates[0]
        assert candidate.mean_distance_bracket_m is not None
        low, high = candidate.mean_distance_bracket_m
        assert candidate.geometric_mean_m == pytest.approx(math.sqrt(s * r), rel=1e-9)
        assert low == pytest.approx(candidate.geometric_mean_m, rel=1e-12)
        assert high == pytest.approx(candidate.mirror_path_m / 2.0, rel=1e-12)
        assert low - 1e-9 <= (s + r) / 2.0 <= high + 1e-9


def test_single_position_identifiability_is_what_the_docstring_claims() -> None:
    """Rank of the observation map: deficit 3 without a measured d, 2 with it.

    This is the claim the whole module's refusal policy rests on, so it is
    asserted rather than only written down.
    """

    def paths(p: np.ndarray) -> np.ndarray:
        source, receiver, room = p[0:3], p[3:6], p[6:9]
        out = [float(np.linalg.norm(source - receiver))]
        for axis in range(3):
            for near in (True, False):
                image = source.copy()
                image[axis] = -source[axis] if near else 2.0 * room[axis] - source[axis]
                out.append(float(np.linalg.norm(image - receiver)))
        return np.asarray(out)

    def jacobian(fn, p: np.ndarray) -> np.ndarray:  # type: ignore[no-untyped-def]
        base = fn(p)
        cols = []
        for i in range(p.size):
            q = p.copy()
            q[i] += 1e-6
            cols.append((fn(q) - base) / 1e-6)
        return np.stack(cols, axis=1)

    rng = np.random.default_rng(13)
    for _ in range(25):
        room = rng.uniform(2.5, 7.0, 3)
        p = np.concatenate(
            [rng.uniform(0.15, 0.85, 3) * room, rng.uniform(0.15, 0.85, 3) * room, room]
        )
        relative = jacobian(lambda q: paths(q)[1:] - paths(q)[0], p)
        with_distance = jacobian(lambda q: np.append(paths(q)[1:] - paths(q)[0], paths(q)[0]), p)
        assert np.linalg.matrix_rank(relative, tol=1e-5) == 6  # 9 unknowns - 6 = deficit 3
        assert np.linalg.matrix_rank(with_distance, tol=1e-5) == 7  # deficit 2


# --------------------------------------------------------------------------
# The vertical solve
# --------------------------------------------------------------------------


def test_vertical_axis_is_recovered_from_two_arrivals() -> None:
    # Deliberately NOT near-symmetric: a microphone close to the vertical
    # midpoint makes the two planes interchangeable (see the test below).
    source_height, mic_height, horizontal, ceiling = 1.20, 0.40, 1.44, 3.20
    distance = math.hypot(source_height - mic_height, horizontal)
    lower_ms = _plane_arrival(distance, source_height, mic_height, horizontal)
    upper_ms = _plane_arrival(distance, ceiling - source_height, ceiling - mic_height, horizontal)
    result = estimate_placement(
        _reflections(
            [(lower_ms, _lossy(distance, lower_ms)), (upper_ms, _lossy(distance, upper_ms))]
        ),
        distance_m=distance,
        mic_height_m=mic_height,
        temperature_c=DEFAULT_TEMPERATURE_C,
    )
    assert result.tier == 2
    assert result.source_height_m.validity is Validity.VALID
    assert result.source_height_m.metres == pytest.approx(source_height, abs=0.005)
    assert result.ceiling_height_m.validity is Validity.VALID
    assert result.ceiling_height_m.metres == pytest.approx(ceiling, abs=0.005)
    assert result.horizontal_separation_m.metres == pytest.approx(horizontal, abs=0.005)
    named = {c.surface for c in result.candidates if c.surface}
    assert named == {LOWER_PLANE, UPPER_PLANE}
    # A distinct upper-plane arrival was found, so the merge safeguard must not fire.
    assert result.source_height_m.reason is None


def test_a_microphone_near_the_vertical_midpoint_is_refused_with_both_readings() -> None:
    """Floor and ceiling become interchangeable, and that is a refusal, not a guess."""
    source_height, mic_height, horizontal, ceiling = 1.20, 1.25, 1.44, 2.50
    distance = math.hypot(source_height - mic_height, horizontal)
    lower_ms = _plane_arrival(distance, source_height, mic_height, horizontal)
    upper_ms = _plane_arrival(distance, ceiling - source_height, ceiling - mic_height, horizontal)
    result = estimate_placement(
        _reflections(
            [(lower_ms, _lossy(distance, lower_ms)), (upper_ms, _lossy(distance, upper_ms))]
        ),
        distance_m=distance,
        mic_height_m=mic_height,
        temperature_c=DEFAULT_TEMPERATURE_C,
    )
    assert result.source_height_m.metres is None
    assert result.source_height_m.alternatives_m == pytest.approx((1.20, 1.30), abs=0.01)
    assert "vertical midpoint" in (result.source_height_m.reason or "")
    assert "moving the microphone" in (result.source_height_m.reason or "")
    assert all(c.surface is None for c in result.candidates)


def test_competing_upper_planes_are_refused_as_the_plane_above() -> None:
    """Two ceiling readings were refused as "the surface the height was
    measured from", with the vertical-midpoint advice, although the lower
    plane had been found and only the plane above was in doubt."""
    source_height, mic_height, horizontal = 0.90, 0.40, 1.0
    distance = math.hypot(source_height - mic_height, horizontal)
    lower_ms = _plane_arrival(distance, source_height, mic_height, horizontal)
    arrivals = [(lower_ms, _lossy(distance, lower_ms))]
    for ceiling in (2.5, 3.2):
        upper_ms = _plane_arrival(
            distance, ceiling - source_height, ceiling - mic_height, horizontal
        )
        arrivals.append((upper_ms, _lossy(distance, upper_ms)))
    result = estimate_placement(
        _reflections(arrivals),
        distance_m=distance,
        mic_height_m=mic_height,
        temperature_c=DEFAULT_TEMPERATURE_C,
    )
    assert result.source_height_m.validity is Validity.VALID
    assert result.source_height_m.metres == pytest.approx(source_height, abs=0.005)
    ceiling_length = result.ceiling_height_m
    assert ceiling_length.metres is None
    assert ceiling_length.alternatives_m == pytest.approx((2.5, 3.2), abs=0.005)
    assert ceiling_length.reason == (
        "more than one reflection could be the plane above the devices, and they disagree by "
        "more than 12 cm: 2.50 m or 3.20 m. ReverbScope does not choose between them"
    )
    from reverbscope.i18n import activate, localize

    activate("zh_CN")
    try:
        assert localize(ceiling_length.reason) == (
            "有不止一个反射可能来自设备上方平面，且它们之间相差超过 12 cm："
            "2.50 m 或 3.20 m。ReverbScope 不会在其中做选择"
        )
    finally:
        activate("en")


def test_reported_uncertainty_is_labelled_as_input_only() -> None:
    source_height, mic_height, horizontal = 1.20, 1.25, 1.44
    distance = math.hypot(source_height - mic_height, horizontal)
    lower_ms = _plane_arrival(distance, source_height, mic_height, horizontal)
    result = estimate_placement(
        _reflections([(lower_ms, _lossy(distance, lower_ms))]),
        distance_m=distance,
        mic_height_m=mic_height,
        temperature_c=DEFAULT_TEMPERATURE_C,
    )
    length = result.source_height_m.to_dict()
    assert length["input_uncertainty_m"] is not None
    assert 0.0 < length["input_uncertainty_m"] < 0.2
    assert "excludes model error" in length["uncertainty_excludes"]


def test_temperature_is_assumed_but_never_silently() -> None:
    result = estimate_placement(
        _reflections([(4.0, -10.0)]), distance_m=1.5, mic_height_m=None, temperature_c=None
    )
    assert result.temperature_assumed is True
    assert result.temperature_c == DEFAULT_TEMPERATURE_C
    assert any("no air temperature was supplied" in n for n in result.notes)


# --------------------------------------------------------------------------
# Refusals: every one of these must withhold a number, not invent one
# --------------------------------------------------------------------------


@pytest.mark.parametrize("confidence", ["low", "medium"])
def test_refuses_everything_when_the_time_origin_is_not_established(confidence: str) -> None:
    result = estimate_placement(
        _reflections([(4.0, -10.0)], confidence=confidence),
        distance_m=1.5,
        mic_height_m=1.2,
        temperature_c=20.0,
    )
    assert result.tier == 0
    assert result.candidates == ()
    for length in (
        result.source_height_m,
        result.ceiling_height_m,
        result.horizontal_separation_m,
    ):
        assert length.metres is None
        assert length.validity is Validity.NOT_COMPUTED
        assert confidence in (length.reason or "")


def test_without_a_distance_only_excess_path_is_reported() -> None:
    result = estimate_placement(
        _reflections([(4.0, -10.0)]), distance_m=None, mic_height_m=None, temperature_c=20.0
    )
    assert result.tier == 0
    assert result.candidates[0].excess_path_m == pytest.approx(C20 * 0.004, rel=1e-9)
    assert result.candidates[0].product_m2 is None
    assert result.candidates[0].interpretable_as_plane is None
    assert result.source_height_m.missing_input == "--speaker-distance"


def test_without_a_mic_height_no_surface_is_named() -> None:
    result = estimate_placement(
        _reflections([(4.0, -10.0)]), distance_m=1.5, mic_height_m=None, temperature_c=20.0
    )
    assert result.tier == 1
    assert result.candidates[0].product_m2 is not None
    assert all(c.surface is None for c in result.candidates)
    assert result.source_height_m.missing_input == "--mic-height"


def test_refuses_and_names_the_gate_when_no_arrival_fits_the_plane() -> None:
    # 60 ms of excess path at 1.5 m implies a loudspeaker far above any room.
    result = estimate_placement(
        _reflections([(60.0, _lossy(1.5, 60.0))]),
        distance_m=1.5,
        mic_height_m=1.2,
        temperature_c=20.0,
    )
    assert result.source_height_m.validity is Validity.NOT_COMPUTED
    assert "implies a loudspeaker" in (result.source_height_m.reason or "")
    # Failing the lower-plane gate is not the same as failing the level screen:
    # the arrival may still be a specular reflection off some other plane, so it
    # keeps interpretable_as_plane and is simply never named.
    assert result.candidates[0].interpretable_as_plane is True
    assert result.candidates[0].surface is None


def test_ambiguity_lists_every_candidate_and_picks_none() -> None:
    mic_height, horizontal = 1.25, 1.44
    distance = math.hypot(1.20 - mic_height, horizontal)
    first = _plane_arrival(distance, 1.20, mic_height, horizontal)
    second = _plane_arrival(distance, 1.90, mic_height, horizontal)
    result = estimate_placement(
        _reflections([(first, _lossy(distance, first)), (second, _lossy(distance, second))]),
        distance_m=distance,
        mic_height_m=mic_height,
        temperature_c=DEFAULT_TEMPERATURE_C,
    )
    assert result.source_height_m.metres is None
    assert result.source_height_m.validity is Validity.NOT_COMPUTED
    assert len(result.source_height_m.alternatives_m) == 2
    expected = sorted(
        boundary_product_m2(distance, delay, C20) / mic_height for delay in (first, second)
    )
    assert result.source_height_m.alternatives_m == pytest.approx(tuple(expected), abs=1e-9)
    assert "does not choose" in (result.source_height_m.reason or "")


def test_a_candidate_louder_than_a_lossless_mirror_is_excluded_not_explained_away() -> None:
    distance, delay = 1.5, 4.0
    too_loud = specular_ceiling_db(distance, mirror_path_m(distance, delay, C20)) + 6.0
    result = estimate_placement(
        _reflections([(delay, too_loud)]),
        distance_m=distance,
        mic_height_m=1.2,
        temperature_c=20.0,
    )
    candidate = result.candidates[0]
    assert candidate.interpretable_as_plane is False
    assert "above what a lossless point source" in (candidate.excluded_reason or "")
    # It says what the arrival is NOT treated as, never what it IS.
    assert "is not treated as" in (candidate.excluded_reason or "")


def test_truncated_window_reports_the_bias_not_just_the_window() -> None:
    result = estimate_placement(
        _reflections([(4.0, -10.0)], analysed_ms=(0.8, 25.0), truncated=True),
        distance_m=1.5,
        mic_height_m=None,
        temperature_c=20.0,
    )
    assert result.window_truncated is True
    assert result.analysed_window_ms == (0.8, 25.0)
    assert any("biased low" in n for n in result.notes)


def test_reflection_search_caveats_are_inherited_verbatim() -> None:
    caveat = "only the 20 strongest reflections are listed"
    result = estimate_placement(
        _reflections([(4.0, -10.0)], notes=(caveat,)),
        distance_m=1.5,
        mic_height_m=None,
        temperature_c=20.0,
    )
    assert any(caveat in n for n in result.notes)


# --------------------------------------------------------------------------
# The export carries its own defence
# --------------------------------------------------------------------------


def test_export_never_contains_a_horizontal_claim() -> None:
    source_height, mic_height, horizontal, ceiling = 1.20, 0.40, 1.44, 3.20
    distance = math.hypot(source_height - mic_height, horizontal)
    lower_ms = _plane_arrival(distance, source_height, mic_height, horizontal)
    upper_ms = _plane_arrival(distance, ceiling - source_height, ceiling - mic_height, horizontal)
    payload = estimate_placement(
        _reflections(
            [(lower_ms, _lossy(distance, lower_ms)), (upper_ms, _lossy(distance, upper_ms))]
        ),
        distance_m=distance,
        mic_height_m=mic_height,
        temperature_c=DEFAULT_TEMPERATURE_C,
    ).to_dict()

    def keys(node: object) -> list[str]:
        if isinstance(node, dict):
            return [k for key, value in node.items() for k in [key, *keys(value)]]
        if isinstance(node, list):
            return [k for item in node for k in keys(item)]
        return []

    forbidden = ("room_length", "room_width", "wall_distance", "position", "coordinate_")
    assert not [k for k in keys(payload) if k.startswith(forbidden)]
    assert "no coordinate, room length, room width or wall distance" in (
        payload["coordinates_withheld"].lower()
    )
    assert "underdetermined by two" not in payload["coordinates_withheld"]  # it says the counts
    assert "deficit of three" in payload["coordinates_withheld"]


def test_a_steep_but_possible_geometry_is_not_refused() -> None:
    """The tape slack was subtracted instead of allowed: with d = 1.5 m every
    geometry under ~0.24 m horizontal separation was refused as impossible."""
    source_height, mic_height, horizontal, ceiling = 1.8866, 0.40, 0.20, 3.0
    distance = math.hypot(source_height - mic_height, horizontal)
    lower_ms = _plane_arrival(distance, source_height, mic_height, horizontal)
    upper_ms = _plane_arrival(distance, ceiling - source_height, ceiling - mic_height, horizontal)
    result = estimate_placement(
        _reflections(
            [(lower_ms, _lossy(distance, lower_ms)), (upper_ms, _lossy(distance, upper_ms))]
        ),
        distance_m=distance,
        mic_height_m=mic_height,
        temperature_c=DEFAULT_TEMPERATURE_C,
    )
    assert result.source_height_m.validity is Validity.VALID
    assert result.source_height_m.metres == pytest.approx(source_height, abs=0.005)
    assert result.horizontal_separation_m.metres == pytest.approx(horizontal, abs=0.005)


@pytest.mark.parametrize(
    ("source_height", "mic_height", "horizontal", "ceiling"),
    [(1.20, 0.40, 1.44, 3.20), (1.80, 0.30, 0.45, 3.20), (1.60, 0.40, 0.50, 3.00)],
)
def test_each_length_carries_its_own_input_uncertainty(
    source_height: float, mic_height: float, horizontal: float, ceiling: float
) -> None:
    """Ceiling and horizontal separation reported the loudspeaker height's
    sigma; the horizontal one was understated up to 3.5 times."""
    from reverbscope.core.placement import (
        DISTANCE_SIGMA_M,
        HEIGHT_SIGMA_M,
        PEAK_LOCATION_SIGMA_MS,
    )

    distance = math.hypot(source_height - mic_height, horizontal)
    lower_ms = _plane_arrival(distance, source_height, mic_height, horizontal)
    upper_ms = _plane_arrival(distance, ceiling - source_height, ceiling - mic_height, horizontal)
    result = estimate_placement(
        _reflections(
            [(lower_ms, _lossy(distance, lower_ms)), (upper_ms, _lossy(distance, upper_ms))]
        ),
        distance_m=distance,
        mic_height_m=mic_height,
        temperature_c=DEFAULT_TEMPERATURE_C,
    )

    def lengths(
        d: float, low: float, up: float, temperature: float, h: float
    ) -> tuple[float, float]:
        speed = speed_of_sound_m_s(temperature)
        s = boundary_product_m2(d, low, speed) / h
        mirror = d + speed * up / 1000.0
        return math.sqrt(d**2 - (s - h) ** 2), (
            s + h + math.sqrt(mirror**2 - d**2 + (s - h) ** 2)
        ) / 2

    nominal = (distance, lower_ms, upper_ms, DEFAULT_TEMPERATURE_C, mic_height)
    sigmas = (DISTANCE_SIGMA_M, PEAK_LOCATION_SIGMA_MS, PEAK_LOCATION_SIGMA_MS, 1.0, HEIGHT_SIGMA_M)
    variance = np.zeros(2)
    for index, sigma in enumerate(sigmas):
        step = max(abs(nominal[index]) * 1e-6, 1e-9)
        moved = list(nominal)
        moved[index] += step
        slope = (np.array(lengths(*moved)) - np.array(lengths(*nominal))) / step
        variance += (slope * sigma) ** 2
    expected = np.sqrt(variance)
    assert result.horizontal_separation_m.input_uncertainty_m == pytest.approx(
        expected[0], rel=0.01
    )
    assert result.ceiling_height_m.input_uncertainty_m == pytest.approx(expected[1], rel=0.01)


def test_height_uncertainty_is_taken_at_the_arrival_the_height_came_from() -> None:
    """Agreeing lower-plane arrivals report their median, but the height's
    input uncertainty was propagated at the earliest of them: detecting
    other agreeing arrivals moved the sigma of the same reported height."""
    h, d = 0.40, math.hypot(0.8, 1.0)

    def delay(source: float) -> float:
        # s * h = c * delta * (2 d + c * delta) / 4, solved for delta.
        return (-d + math.sqrt(d * d + 4 * source * h)) / C20 * 1000.0

    ceiling = _plane_arrival(d, 2.5 - 1.21, 2.5 - h, math.sqrt(d * d - (1.21 - h) ** 2))

    def source_height(sources: tuple[float, ...]) -> PlacementLength:
        arrivals = sorted([delay(s) for s in sources] + [ceiling])
        reflections = _reflections([(a, _lossy(d, a)) for a in arrivals])
        return estimate_placement(
            reflections, distance_m=d, mic_height_m=h, temperature_c=20.0
        ).source_height_m

    alone = source_height((1.21,))
    agreed = source_height((1.18, 1.21, 1.25))
    assert alone.validity is Validity.VALID and agreed.validity is Validity.VALID
    assert agreed.metres == pytest.approx(alone.metres)
    assert agreed.input_uncertainty_m == pytest.approx(alone.input_uncertainty_m, rel=1e-9)


@pytest.mark.parametrize(
    ("source_height", "mic_height", "horizontal", "expected"),
    [
        (
            1.5,
            1.2,
            1.0,
            "and a plane 2.70 m up (plausible heights start at 1.80 m) would arrive at the "
            "same 5.3 ms as the arrival this height was solved from",
        ),
        (
            1.0,
            0.9,
            3.0,
            "and one as low as 1.80 m would arrive at 1.3 ms -- within the 0.3 ms the "
            "reflection search can resolve from the 1.6 ms arrival this height was solved from",
        ),
    ],
    ids=["lowest plane arrives well before", "lowest plane within the resolution"],
)
def test_a_possible_merge_names_the_plane_that_would_merge(
    source_height: float, mic_height: float, horizontal: float, expected: str
) -> None:
    """With the devices straddling mid-height, the lowest plausible plane above
    arrives long before the lower plane's arrival, yet the reason said it
    arrived "at 0.9 ms -- within the 0.3 ms ... from the 5.3 ms arrival". The
    plane that would really merge is the one at u_z = s + h above the lower
    plane, whose mirror path equals the lower plane's."""
    distance = math.hypot(source_height - mic_height, horizontal)
    lower_ms = _plane_arrival(distance, source_height, mic_height, horizontal)
    result = estimate_placement(
        _reflections([(lower_ms, _lossy(distance, lower_ms))]),
        distance_m=distance,
        mic_height_m=mic_height,
        temperature_c=DEFAULT_TEMPERATURE_C,
    )
    assert result.source_height_m.validity is Validity.UNRELIABLE
    assert result.source_height_m.metres == pytest.approx(source_height, abs=0.005)
    reason = result.source_height_m.reason or ""
    assert expected in reason
    assert "may therefore be two arrivals merged into one peak" in reason
    assert result.horizontal_separation_m.validity is Validity.UNRELIABLE
    assert result.horizontal_separation_m.reason == reason


# --- speed_for_result (moved from the removed geometry/paths.py) -------------------


def test_speed_for_result_assumes_20_c_without_placement(analysed_result: AnalysisResult) -> None:
    speed, temperature, assumed = speed_for_result(replace(analysed_result, placement=None))
    assert (temperature, assumed) == (DEFAULT_TEMPERATURE_C, True)
    assert speed == pytest.approx(343.2, abs=0.05)


def test_speed_for_result_uses_the_entered_temperature(analysed_result: AnalysisResult) -> None:
    placement = estimate_placement(
        _reflections([(3.0, -6.0)]), distance_m=2.0, mic_height_m=1.2, temperature_c=25.0
    )
    result = replace(analysed_result, placement=placement)
    speed, temperature, assumed = speed_for_result(result)
    assert (temperature, assumed) == (25.0, False)
    assert speed == pytest.approx(speed_of_sound_m_s(25.0))
    # A non-finite stored temperature falls back to the assumed one.
    broken = replace(result, placement=replace(placement, temperature_c=float("nan")))
    assert speed_for_result(broken)[1:] == (DEFAULT_TEMPERATURE_C, True)


# --------------------------------------------------------------------------
# Edges that the happy-path suite never walks (coverage fallthrough)
# --------------------------------------------------------------------------


def test_speed_of_sound_rejects_absolute_zero_and_below() -> None:
    with pytest.raises(ValueError, match="absolute zero"):
        speed_of_sound_m_s(-273.15)
    with pytest.raises(ValueError, match="absolute zero"):
        speed_of_sound_m_s(-300.0)


def test_propagate_returns_none_when_the_model_or_jacobian_raises() -> None:
    def boom(**_: float) -> float:
        raise ValueError("nope")

    assert _propagate(boom, {"a": 1.0}, {"a": 0.1}) is None

    def zero_div(**_: float) -> float:
        return 1.0 / 0.0

    assert _propagate(zero_div, {"a": 1.0}, {"a": 0.1}) is None

    def shift_raises(*, a: float) -> float:
        if a > 1.0:
            raise ValueError("shifted")
        return a * 2.0

    assert _propagate(shift_raises, {"a": 1.0}, {"a": 0.1}) is None

    def nan_on_shift(*, a: float) -> float:
        return float("nan") if a != 1.0 else 1.0

    assert _propagate(nan_on_shift, {"a": 1.0}, {"a": 0.1}) is None


def test_a_candidate_far_below_the_specular_ceiling_is_excluded() -> None:
    distance, delay = 1.5, 4.0
    too_quiet = specular_ceiling_db(distance, mirror_path_m(distance, delay, C20)) - (
        MAX_SURFACE_ATTENUATION_DB + 5.0
    )
    result = estimate_placement(
        _reflections([(delay, too_quiet)]),
        distance_m=distance,
        mic_height_m=1.2,
        temperature_c=20.0,
    )
    candidate = result.candidates[0]
    assert candidate.interpretable_as_plane is False
    reason = candidate.excluded_reason or ""
    assert "below that ceiling" in reason
    assert f"{MAX_SURFACE_ATTENUATION_DB:.0f} dB" in reason


def test_unknown_direct_sound_confidence_is_named_in_the_refusal() -> None:
    result = estimate_placement(
        _reflections([(4.0, -10.0)], confidence="unknown"),
        distance_m=1.5,
        mic_height_m=1.2,
        temperature_c=20.0,
    )
    assert result.tier == 0
    assert result.candidates == ()
    assert "confidence is unknown" in (result.source_height_m.reason or "")


def test_candidates_past_the_hypothesis_cap_are_kept_but_not_attributed() -> None:
    """Only the earliest N arrivals are plane hypotheses; later ones stay unnamed."""
    source_height, mic_height, horizontal = 1.20, 0.40, 1.44
    distance = math.hypot(source_height - mic_height, horizontal)
    lower_ms = _plane_arrival(distance, source_height, mic_height, horizontal)
    pads = [
        (
            1.0 + 0.2 * i,
            specular_ceiling_db(distance, mirror_path_m(distance, 1.0 + 0.2 * i, C20)) + 6.0,
        )
        for i in range(MAX_HYPOTHESIS_CANDIDATES)
    ]
    arrivals = [*pads, (lower_ms, _lossy(distance, lower_ms))]
    result = estimate_placement(
        _reflections(arrivals),
        distance_m=distance,
        mic_height_m=mic_height,
        temperature_c=DEFAULT_TEMPERATURE_C,
    )
    assert len(result.candidates) == MAX_HYPOTHESIS_CANDIDATES + 1
    assert result.source_height_m.metres is None
    assert all(c.surface is None for c in result.candidates)


def _delay_for_product(distance_m: float, product_m2: float) -> float:
    excess = -distance_m + math.sqrt(distance_m * distance_m + 4.0 * product_m2)
    return excess / C20 * 1000.0


def test_a_vertical_separation_the_tape_cannot_contain_is_refused() -> None:
    mic_height, source_height, distance = 0.5, 2.5, 1.5
    delay = _delay_for_product(distance, source_height * mic_height)
    result = estimate_placement(
        _reflections([(delay, _lossy(distance, delay))]),
        distance_m=distance,
        mic_height_m=mic_height,
        temperature_c=20.0,
    )
    reason = result.source_height_m.reason or ""
    assert "vertical separation" in reason
    assert "cannot contain" in reason


def test_a_near_vertical_stack_is_refused_as_no_horizontal_separation() -> None:
    mic_height, source_height, distance = 1.0, 1.5, 0.50
    delay = _delay_for_product(distance, source_height * mic_height)
    result = estimate_placement(
        _reflections([(delay, _lossy(distance, delay))]),
        distance_m=distance,
        mic_height_m=mic_height,
        temperature_c=20.0,
    )
    assert "vertically above the microphone" in (result.source_height_m.reason or "")


def test_an_upper_plane_that_clears_the_devices_by_too_little_is_rejected() -> None:
    source_height, mic_height, horizontal = 2.0, 1.9, 1.5
    distance = math.hypot(source_height - mic_height, horizontal)
    lower_ms = _plane_arrival(distance, source_height, mic_height, horizontal)
    # Target an upper plane only 5 cm above the taller device (clearance needs 30 cm).
    target_upper = 2.05
    u_z = source_height + mic_height
    v_z = source_height - mic_height
    mirror = math.sqrt((2.0 * target_upper - u_z) ** 2 + distance * distance - v_z * v_z)
    upper_ms = (mirror - distance) / C20 * 1000.0
    result = estimate_placement(
        _reflections(
            [
                (lower_ms, _lossy(distance, lower_ms)),
                (upper_ms, _lossy(distance, upper_ms)),
            ]
        ),
        distance_m=distance,
        mic_height_m=mic_height,
        temperature_c=DEFAULT_TEMPERATURE_C,
    )
    reason = result.ceiling_height_m.reason or ""
    assert "less than" in reason and "above the higher of the two devices" in reason


def test_a_window_too_short_for_any_upper_plane_says_so() -> None:
    source_height, mic_height, horizontal = 1.2, 0.4, 3.0
    distance = math.hypot(source_height - mic_height, horizontal)
    lower_ms = _plane_arrival(distance, source_height, mic_height, horizontal)
    window = (0.8, 1.2)
    result = estimate_placement(
        _reflections(
            [(lower_ms, _lossy(distance, lower_ms))],
            window_ms=window,
            analysed_ms=window,
        ),
        distance_m=distance,
        mic_height_m=mic_height,
        temperature_c=DEFAULT_TEMPERATURE_C,
    )
    assert result.source_height_m.validity is Validity.VALID
    reason = result.ceiling_height_m.reason or ""
    assert "beyond the" in reason and "window that could be searched" in reason
    assert "not evidence of absence" in reason


def test_a_rejected_upper_candidate_and_a_short_window_are_both_named() -> None:
    source_height, mic_height, horizontal = 1.2, 0.4, 3.0
    distance = math.hypot(source_height - mic_height, horizontal)
    lower_ms = _plane_arrival(distance, source_height, mic_height, horizontal)
    too_high = 7.0
    upper_ms = _plane_arrival(distance, too_high - source_height, too_high - mic_height, horizontal)
    window = (0.8, 1.2)
    result = estimate_placement(
        _reflections(
            [
                (lower_ms, _lossy(distance, lower_ms)),
                (upper_ms, _lossy(distance, upper_ms)),
            ],
            window_ms=window,
            analysed_ms=window,
        ),
        distance_m=distance,
        mic_height_m=mic_height,
        temperature_c=DEFAULT_TEMPERATURE_C,
    )
    reason = result.ceiling_height_m.reason or ""
    assert "1.8-6.0 m is treated as plausible" in reason
    assert "beyond the" in reason and "not evidence of absence" in reason


def test_statistical_and_too_short_caveats_are_inherited() -> None:
    notes = (
        "peaks are statistical under the threshold",
        "recording too short for late arrivals",
        "only the 20 strongest reflections are listed",
    )
    result = estimate_placement(
        _reflections([(4.0, -10.0)], notes=notes),
        distance_m=1.5,
        mic_height_m=None,
        temperature_c=20.0,
    )
    inherited = [n for n in result.notes if n.startswith("inherited from the reflection search:")]
    assert len(inherited) == 3
    for note in notes:
        assert any(note in n for n in inherited)


def test_unrelated_notes_are_not_inherited_and_a_missing_window_skips_beyond_check() -> None:
    """Notes without the search keywords stay local; no analysed window means no
    'beyond the window' claim even when every upper candidate is rejected."""
    source_height, mic_height, horizontal = 1.2, 0.4, 1.5
    distance = math.hypot(source_height - mic_height, horizontal)
    lower_ms = _plane_arrival(distance, source_height, mic_height, horizontal)
    too_high = 7.0
    upper_ms = _plane_arrival(distance, too_high - source_height, too_high - mic_height, horizontal)
    reflections = ReflectionsResult(
        direct_sound_time_s=0.0,
        direct_sound_confidence="high",
        window_ms=(0.8, 80.0),
        threshold_db=-20.0,
        reflections=(
            Reflection(delay_ms=lower_ms, relative_db=_lossy(distance, lower_ms)),
            Reflection(delay_ms=upper_ms, relative_db=_lossy(distance, upper_ms)),
        ),
        notes=("unrelated note that should not be inherited",),
        analysed_window_ms=None,
        window_truncated=False,
    )
    result = estimate_placement(
        reflections,
        distance_m=distance,
        mic_height_m=mic_height,
        temperature_c=DEFAULT_TEMPERATURE_C,
    )
    assert not any("inherited from the reflection search" in n for n in result.notes)
    assert result.source_height_m.validity is Validity.VALID
    reason = result.ceiling_height_m.reason or ""
    assert "1.8-6.0 m is treated as plausible" in reason
    assert "beyond the" not in reason
