"""Fake backend must honour cancel before the expensive room convolution."""

from __future__ import annotations

import threading

import numpy as np
import pytest

from reverbscope.audio.backend import CALLBACK_BLOCK
from reverbscope.audio.fake import FakeBackend
from reverbscope.core.sweep import measurement_signal
from reverbscope.errors import MeasurementCancelledError
from reverbscope.models.configuration import SweepSettings


def test_fake_cancel_before_convolve_skips_fftconvolve(monkeypatch: pytest.MonkeyPatch) -> None:
    import reverbscope.audio.fake as fake_mod

    calls: list[str] = []

    def tracked(*_args: object, **_kwargs: object) -> np.ndarray:
        calls.append("fftconvolve")
        return np.zeros(8)

    monkeypatch.setattr(fake_mod, "fftconvolve", tracked)
    backend = FakeBackend()
    cancel = threading.Event()
    cancel.set()
    settings = SweepSettings(sample_rate=48000, duration_s=0.5, level_dbfs=-20.0)
    with pytest.raises(MeasurementCancelledError):
        backend.play_and_record(
            measurement_signal(settings),
            settings.sample_rate,
            input_device=None,
            output_device=None,
            input_channels=[1],
            output_channel=1,
            level_dbfs=-20.0,
            cancel=cancel,
        )
    assert calls == []
    assert backend.cancelled is True
    assert backend.last_output_block.shape[0] == CALLBACK_BLOCK
