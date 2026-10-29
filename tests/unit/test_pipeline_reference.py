"""Boundary coverage for :class:`~reverbscope.core.pipeline.Reference` and
the public ``analyze`` entry when the reference cannot be used."""

from __future__ import annotations

import numpy as np
import pytest

from reverbscope.core.pipeline import Reference, analyze, synthetic_recording
from reverbscope.errors import ConfigurationError, InvalidAudioError, SampleRateMismatchError
from reverbscope.models.audio import AudioSignal
from reverbscope.models.configuration import SweepSettings
from tests.conftest import make_rir


def test_reference_requires_settings_or_signal() -> None:
    with pytest.raises(ConfigurationError, match="sweep settings or a reference signal"):
        Reference()


def test_reference_signal_requires_its_sample_rate() -> None:
    with pytest.raises(ConfigurationError, match="sample rate"):
        Reference(signal=np.zeros(32, dtype=np.float64))


def test_from_signal_keeps_the_first_channel_of_a_stereo_array() -> None:
    stereo = np.column_stack([np.linspace(0.0, 1.0, 64), np.linspace(1.0, 0.0, 64)]).astype(
        np.float64
    )
    reference = Reference.from_signal(stereo, 48000)
    assert reference.signal is not None
    assert reference.signal.ndim == 1
    assert reference.signal[0] == pytest.approx(0.0)
    assert reference.sample_rate == 48000


def test_analyze_rejects_a_sweep_that_cannot_be_regenerated_at_the_recording_rate(
    short_sweep: SweepSettings,
) -> None:
    # A non-silent recording at a rate the sweep settings refuse.
    rng = np.random.default_rng(0)
    samples = rng.normal(0.0, 0.05, size=(22050, 2)).astype(np.float64)
    recording = AudioSignal(samples, sample_rate=22050)
    with pytest.raises(SampleRateMismatchError):
        analyze(recording, Reference.from_settings(short_sweep))


def test_analyze_rejects_an_all_silent_reference_signal(short_sweep: SweepSettings) -> None:
    silent = np.zeros(int(short_sweep.sample_rate * short_sweep.duration_s), dtype=np.float64)
    recording = synthetic_recording(
        short_sweep, make_rir(short_sweep.sample_rate, rt60_s=0.3), noise_rms=1e-5
    )
    with pytest.raises(InvalidAudioError, match="reference signal cannot be used"):
        analyze(recording, Reference.from_signal(silent, short_sweep.sample_rate))
