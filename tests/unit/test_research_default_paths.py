"""Pin the remaining research-branch default difference documented in ADR 0004."""

from __future__ import annotations

import numpy as np
import pytest

from reverbscope.core.deconvolution import locate_impulse_response


@pytest.mark.parametrize("sweep_rate_s", [None, 0.002])
def test_harmonic_suppression_changes_only_intersecting_windows(
    sweep_rate_s: float | None,
) -> None:
    # Short sweep: harmonic windows intersect the retained pre-roll. A long
    # sweep's windows normally lie outside it, so a loopback alone misses this.
    rate = 8000
    impulse = np.full(2000, 1e-6)
    impulse[1000] = 1
    before = impulse.copy()
    kwargs = {
        "recording_length": 3000,
        "reference_length": 1001,
        "sample_rate": rate,
        "pre_delay_ms": 5.0,
        "max_length_s": 0.1,
        "sweep_rate_s": sweep_rate_s,
    }
    raw = locate_impulse_response(impulse, suppress_harmonics=False, **kwargs)
    default = locate_impulse_response(impulse, **kwargs)
    explicit = locate_impulse_response(impulse, suppress_harmonics=True, **kwargs)
    np.testing.assert_array_equal(default.samples, explicit.samples)
    expected = raw.samples.copy()
    start = raw.peak_index - raw.pre_delay_samples
    mask = np.zeros(len(expected), dtype=bool)
    for window in raw.harmonic_windows:
        left, right = max(0, window.start - start), min(len(expected), window.stop - start)
        if right > left:
            mask[left:right] = True
    expected[mask] = 0
    np.testing.assert_array_equal(default.samples, expected)
    np.testing.assert_array_equal(impulse, before)
    assert default.peak_index == raw.peak_index
    assert default.pre_peak_margin_db == raw.pre_peak_margin_db
    if sweep_rate_s is None:
        assert not mask.any()
    else:
        assert mask.any()
        assert np.any(default.samples != raw.samples)
