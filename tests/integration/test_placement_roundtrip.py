"""Placement through the whole chain: synthesised sweep -> analyse -> geometry.

No real room is used as evidence anywhere here; every arrival is placed by the
image-source construction so that the answer is known before the analysis runs.
"""

from __future__ import annotations

import math

import pytest

from reverbscope.core.pipeline import Reference, analyze, synthetic_recording
from reverbscope.core.placement import DEFAULT_TEMPERATURE_C, speed_of_sound_m_s
from reverbscope.models.configuration import AnalysisSettings, SweepSettings
from reverbscope.models.result import Validity
from tests.conftest import make_rir

C20 = speed_of_sound_m_s(DEFAULT_TEMPERATURE_C)


def _plane(distance_m: float, near: float, far: float, horizontal: float) -> tuple[float, float]:
    """``(delay_s, linear gain)`` of a first-order arrival off one plane.

    The gain is the free-field spreading ratio ``d/L`` times an absorption
    coefficient, which is what a real surface roughly does and, importantly,
    keeps the arrival *below* the specular ceiling the analysis screens on.
    """
    path = math.hypot(near + far, horizontal)
    return (path - distance_m) / C20, 0.7 * distance_m / path


def _measure(
    sample_rate: int,
    short_sweep: SweepSettings,
    arrivals: list[tuple[float, float]],
    settings: AnalysisSettings,
):  # type: ignore[no-untyped-def]
    ir = make_rir(sample_rate, rt60_s=0.35, reflections=arrivals, diffuse_level=0.004, length_s=0.6)
    recording = synthetic_recording(short_sweep, ir, noise_rms=1e-4)
    return analyze(recording, Reference.from_settings(short_sweep), settings)


def test_vertical_geometry_survives_the_whole_chain(
    sample_rate: int, short_sweep: SweepSettings
) -> None:
    source_height, mic_height, horizontal, ceiling = 1.20, 0.40, 1.44, 3.20
    distance = math.hypot(source_height - mic_height, horizontal)
    result = _measure(
        sample_rate,
        short_sweep,
        [
            _plane(distance, source_height, mic_height, horizontal),
            _plane(distance, ceiling - source_height, ceiling - mic_height, horizontal),
        ],
        AnalysisSettings(
            placement_distance_m=distance,
            placement_mic_height_m=mic_height,
            placement_temperature_c=DEFAULT_TEMPERATURE_C,
        ),
    )
    placement = result.placement
    assert placement is not None
    assert placement.tier == 2
    # Tolerance is set by the reflection detector's peak location (0.1 ms
    # peak-hold), not by the geometry, which is exact.
    assert placement.source_height_m.metres == pytest.approx(source_height, abs=0.05)
    assert placement.ceiling_height_m.metres == pytest.approx(ceiling, abs=0.05)
    assert placement.horizontal_separation_m.metres == pytest.approx(horizontal, abs=0.05)


def test_two_planes_that_the_detector_merges_do_not_become_a_confident_answer(
    sample_rate: int, short_sweep: SweepSettings
) -> None:
    """Floor and ceiling 0.25 ms apart are one envelope peak, not two.

    The reflection search holds peaks for 0.1 ms and keeps them 0.3 ms apart,
    so a microphone near the vertical midpoint of a room produces a single
    merged candidate. What must never happen is a confident height derived
    from an arrival that is two arrivals.
    """
    source_height, mic_height, horizontal, ceiling = 1.20, 1.25, 1.44, 2.50
    distance = math.hypot(source_height - mic_height, horizontal)
    lower = _plane(distance, source_height, mic_height, horizontal)
    upper = _plane(distance, ceiling - source_height, ceiling - mic_height, horizontal)
    assert abs(upper[0] - lower[0]) * 1000.0 < 0.3  # closer than the detector can separate

    result = _measure(
        sample_rate,
        short_sweep,
        [lower, upper],
        AnalysisSettings(
            placement_distance_m=distance,
            placement_mic_height_m=mic_height,
            placement_temperature_c=DEFAULT_TEMPERATURE_C,
        ),
    )
    placement = result.placement
    assert placement is not None
    merged = [c for c in placement.candidates if c.delay_ms < 6.0]
    assert len(merged) == 1, "the two arrivals should merge into one candidate"
    # The ceiling cannot be established from a single merged arrival.
    assert placement.ceiling_height_m.validity is Validity.NOT_COMPUTED
    # The height solved from the merged peak happens to be close here, but the
    # merge is undetectable from one arrival, so it must not read as trustworthy.
    assert placement.source_height_m.validity is Validity.UNRELIABLE
    assert "may therefore be two arrivals merged" in (placement.source_height_m.reason or "")
    assert placement.horizontal_separation_m.validity is Validity.UNRELIABLE
    if placement.source_height_m.metres is not None:
        assert 1.15 <= placement.source_height_m.metres <= 1.35


def test_without_placement_inputs_the_block_is_present_and_says_what_is_missing(
    sample_rate: int, short_sweep: SweepSettings
) -> None:
    result = _measure(
        sample_rate,
        short_sweep,
        [(0.006, 10 ** (-9 / 20))],
        AnalysisSettings(),
    )
    placement = result.placement
    assert placement is not None
    assert placement.tier == 0
    assert placement.temperature_assumed is True
    assert placement.source_height_m.missing_input == "--speaker-distance"
    payload = result.to_dict(include_curves=False)["placement"]
    assert payload["tier"] == 0
    assert payload["candidates"][0]["excess_path_m"] == pytest.approx(C20 * 0.006, abs=0.05)
    assert payload["candidates"][0]["product_m2"] is None
    assert "no coordinate" in payload["coordinates_withheld"].lower()
