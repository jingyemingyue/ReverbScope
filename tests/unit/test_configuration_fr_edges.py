"""Edge paths for analysis settings loading and FR tapering."""

from __future__ import annotations

import numpy as np
import pytest

from reverbscope.core.frequency_response import _taper_end
from reverbscope.errors import ConfigurationError
from reverbscope.models.calibration import CalibrationRecord
from reverbscope.models.configuration import AnalysisSettings, SweepSettings


def test_taper_end_skips_fade_when_window_is_one_sample_or_less() -> None:
    samples = np.ones(8, dtype=np.float64)
    assert np.array_equal(_taper_end(samples, 48_000, 0.0), samples)
    assert np.array_equal(_taper_end(samples, 48_000, 1e-6), samples)


def test_analysis_settings_from_dict_rejects_bad_octave_bands() -> None:
    with pytest.raises(ConfigurationError, match="octave_bands_hz"):
        AnalysisSettings.from_dict({"octave_bands_hz": "nope"})
    with pytest.raises(ConfigurationError, match="could not convert"):
        AnalysisSettings.from_dict({"octave_bands_hz": [125.0, "x"]})


def test_analysis_settings_round_trips_calibration() -> None:
    settings = AnalysisSettings.from_dict(
        {"calibration": {"reference_dbfs": -20.0, "reference_db_spl": 94.0}}
    )
    assert settings.calibration == CalibrationRecord(reference_dbfs=-20.0, reference_db_spl=94.0)
    assert settings.to_dict()["calibration"]["reference_db_spl"] == 94.0


def test_sweep_settings_with_sample_rate_and_from_dict() -> None:
    base = SweepSettings(sample_rate=48_000, duration_s=1.0)
    other = base.with_sample_rate(44_100)
    assert other.sample_rate == 44_100
    assert other.duration_s == base.duration_s
    assert SweepSettings.from_dict(base.to_dict()) == base


def test_analysis_settings_rejects_negative_loopback_channel() -> None:
    with pytest.raises(ConfigurationError, match="loopback_channel"):
        AnalysisSettings(loopback_channel=-1)
