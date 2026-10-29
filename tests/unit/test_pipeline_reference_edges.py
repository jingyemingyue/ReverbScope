"""Edge paths for :class:`~reverbscope.core.pipeline.Reference` preparation."""

from __future__ import annotations

import numpy as np
import pytest

from reverbscope.core.pipeline import Reference, _prepare_reference, analyze, synthetic_recording
from reverbscope.core.sweep import generate_ess
from reverbscope.errors import ConfigurationError, InvalidAudioError, SampleRateMismatchError
from reverbscope.models.audio import AudioSignal
from reverbscope.models.configuration import SweepSettings
from tests.conftest import make_rir


def test_reference_requires_settings_or_signal_with_rate() -> None:
    with pytest.raises(ConfigurationError, match="settings or a reference signal"):
        Reference()
    with pytest.raises(ConfigurationError, match="sample rate"):
        Reference(signal=np.ones(16))


def test_reference_from_signal_takes_first_channel_of_stereo() -> None:
    stereo = np.stack([np.full(32, 0.25), np.full(32, 0.75)], axis=1)
    ref = Reference.from_signal(stereo, 48_000)
    assert ref.signal is not None
    assert ref.signal.shape == (32,)
    assert float(np.mean(ref.signal)) == pytest.approx(0.25)


def test_prepare_reference_rejects_unsupported_regenerated_rate(
    short_sweep: SweepSettings,
) -> None:
    # 32000 Hz is not a supported SweepSettings rate.
    with pytest.raises(SampleRateMismatchError, match="cannot be regenerated"):
        _prepare_reference(Reference.from_settings(short_sweep), 32_000)


def test_prepare_reference_rejects_silent_signal_reference(
    short_sweep: SweepSettings,
) -> None:
    silent = Reference.from_signal(np.zeros(short_sweep.sweep_samples), short_sweep.sample_rate)
    with pytest.raises(InvalidAudioError, match="cannot be used"):
        _prepare_reference(silent, short_sweep.sample_rate)


def test_analyze_with_signal_reference_matches_settings_path(
    short_sweep: SweepSettings,
) -> None:
    ir = make_rir(short_sweep.sample_rate, rt60_s=0.3, diffuse_level=0.02)
    recording = synthetic_recording(short_sweep, ir, noise_rms=1e-5)
    from_settings = analyze(recording, Reference.from_settings(short_sweep))
    sweep = generate_ess(short_sweep)
    from_signal = analyze(recording, Reference.from_signal(sweep, short_sweep.sample_rate))
    assert from_signal.impulse_response.direct_sound_index >= 0
    assert from_settings.decay.broadband.band_label == from_signal.decay.broadband.band_label


def test_device_warnings_are_carried_into_analysis_warnings(
    short_sweep: SweepSettings,
) -> None:
    ir = make_rir(short_sweep.sample_rate, rt60_s=0.3, diffuse_level=0.02)
    base = synthetic_recording(short_sweep, ir, noise_rms=1e-5)
    recording = AudioSignal(base.samples, base.sample_rate, device_warnings=("buffer underrun",))
    result = analyze(recording, Reference.from_settings(short_sweep))
    joined = " ".join(result.warnings).lower()
    assert "underrun" in joined or "buffer" in joined
