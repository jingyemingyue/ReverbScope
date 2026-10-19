"""Deliberately failing acceptance probes; run explicitly, outside testpaths.

These are evidence for deferred M2/M8 work, not xfails or suite exclusions.
Run: pytest docs/research/pr74_deferred_probes.py -q --tb=short
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from reverbscope.core.modal import estimate_modal_decays
from reverbscope.core.sweep import synchronized_settings
from reverbscope.models.configuration import SweepSettings


def test_m2_synchronized_phase_identity() -> None:
    settings = synchronized_settings(SweepSettings(duration_s=2.0))
    # phi(t + L ln(m)) - m phi(t) = 2 pi f1 L (m - 1).
    # Synchronization requires this to be an integer number of turns.
    phase_residual = np.angle(np.exp(2j * math.pi * settings.start_hz * settings.sweep_rate))
    assert abs(phase_residual) < 1e-8, f"phase residual: {phase_residual} rad"


@pytest.mark.parametrize("weight_beta", [0.9995, 0.99])
def test_m8_known_modal_decay_with_weighting(weight_beta: float) -> None:
    rate = 1000
    time = np.arange(2000) / rate
    signal = np.exp(-math.log(1000) * time / 0.8) * np.cos(2 * math.pi * 100 * time)
    modes = estimate_modal_decays(signal, rate, lp_order=2, weight_beta=weight_beta)
    assert modes, "no mode returned"
    closest = min(modes, key=lambda mode: abs(mode.frequency_hz - 100))
    assert closest.frequency_hz == pytest.approx(100, abs=1)
    assert closest.t60_s == pytest.approx(0.8, rel=0.05)
