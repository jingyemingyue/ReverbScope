"""Edge paths of :mod:`reverbscope.core.playback_speed`."""

from __future__ import annotations

from unittest import mock

import numpy as np
import pytest

from reverbscope.core.playback_speed import measure_sweep_speed
from reverbscope.core.sweep import generate_ess
from reverbscope.models.configuration import SweepSettings


@pytest.fixture
def settings() -> SweepSettings:
    return SweepSettings(duration_s=2.0)


@pytest.fixture
def padded_sweep(settings: SweepSettings) -> np.ndarray:
    return np.concatenate([np.zeros(48_000), generate_ess(settings), np.zeros(48_000)])


def test_measure_sweep_speed_rejects_short_or_multichannel(
    settings: SweepSettings,
) -> None:
    assert measure_sweep_speed(np.zeros((100, 2)), 48_000, settings) is None
    assert measure_sweep_speed(np.zeros(100), 48_000, settings) is None


def test_measure_sweep_speed_needs_enough_stft_frames(
    settings: SweepSettings, padded_sweep: np.ndarray
) -> None:
    import reverbscope.core.playback_speed as ps

    real_stft = ps.stft

    def short_stft(*args: object, **kwargs: object):  # type: ignore[no-untyped-def]
        freqs, times, spec = real_stft(*args, **kwargs)
        return freqs, times[:2], spec[:, :2]

    with mock.patch.object(ps, "stft", short_stft):
        assert measure_sweep_speed(padded_sweep, 48_000, settings) is None


def test_measure_sweep_speed_needs_frequency_bins_in_search_band(
    settings: SweepSettings, padded_sweep: np.ndarray
) -> None:
    import reverbscope.core.playback_speed as ps

    with mock.patch.object(ps, "SEARCH_LOW_HZ", 20_000.0):
        assert measure_sweep_speed(padded_sweep, 48_000, settings) is None


def test_measure_sweep_speed_rejects_non_positive_fitted_rate(
    settings: SweepSettings, padded_sweep: np.ndarray
) -> None:
    import reverbscope.core.playback_speed as ps

    with mock.patch.object(ps, "theilslopes", return_value=(-1.0, 0.0, None, None)):
        assert measure_sweep_speed(padded_sweep, 48_000, settings) is None
    with mock.patch.object(ps, "theilslopes", return_value=(float("nan"), 0.0, None, None)):
        assert measure_sweep_speed(padded_sweep, 48_000, settings) is None
