"""Additional edge paths for :mod:`reverbscope.core.resonance`."""

from __future__ import annotations

import numpy as np

from reverbscope.core.resonance import (
    _decay_20db_s,
    band_decay_20db_s,
    filter_ringing_20db_s,
    notch_band,
)


def test_decay_20db_returns_none_without_a_drop() -> None:
    assert _decay_20db_s(np.ones(48_000), 48_000, 0.01) is None


def test_band_helpers_return_none_or_passthrough_when_band_does_not_fit() -> None:
    impulse = np.zeros(1_000)
    impulse[100] = 1.0
    assert band_decay_20db_s(impulse, 8_000, 4_000.0) is None
    assert filter_ringing_20db_s(8_000, 4_000.0) is None
    passthrough = notch_band(np.full(100, 0.5), 8_000, 4_000.0)
    assert np.allclose(passthrough, 0.5)
