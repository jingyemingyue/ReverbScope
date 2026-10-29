"""Edge paths for comparison helpers and impulse-response serialization."""

from __future__ import annotations

import numpy as np
import pytest

from reverbscope.core.pipeline import Reference, analyze, synthetic_recording
from reverbscope.errors import SessionError
from reverbscope.models.comparison import CompareSettings, _array_to_list, _curve
from reverbscope.models.configuration import SweepSettings
from reverbscope.models.result import Validity, _not_computed_energy
from tests.conftest import make_rir


def test_array_to_list_and_curve_helpers() -> None:
    assert _array_to_list(None) is None
    assert _array_to_list(np.array([1.23456, 2.0])) == [1.2346, 2.0]
    with pytest.raises(TypeError, match="list of numbers"):
        _curve(1.0)


def test_compare_settings_reject_non_positive_thresholds() -> None:
    with pytest.raises(ValueError, match="min_common_band_octaves"):
        CompareSettings(min_common_band_octaves=0.0)
    with pytest.raises(ValueError, match="reflection_match_ms"):
        CompareSettings(reflection_match_ms=0.0)
    with pytest.raises(ValueError, match="resonance_match_octaves"):
        CompareSettings(resonance_match_octaves=0.0)
    with pytest.raises(ValueError, match="log_grid_points_per_octave"):
        CompareSettings(log_grid_points_per_octave=0)
    settings = CompareSettings()
    assert CompareSettings.from_dict(settings.to_dict()) == settings
    with pytest.raises(SessionError):
        CompareSettings.from_dict([])  # type: ignore[arg-type]


def test_not_computed_energy_and_ir_to_dict_without_curves(
    short_sweep: SweepSettings,
) -> None:
    metric = _not_computed_energy("legacy.c50", "dB")
    assert metric.validity is Validity.NOT_COMPUTED
    assert metric.value is None
    result = analyze(
        synthetic_recording(
            short_sweep,
            make_rir(short_sweep.sample_rate, rt60_s=0.3, diffuse_level=0.02),
            noise_rms=1e-5,
        ),
        Reference.from_settings(short_sweep),
    )
    payload = result.impulse_response.to_dict(include_curves=False)
    assert "samples" not in payload
    assert payload["loopback"] is None or "samples" not in (payload["loopback"] or {})
