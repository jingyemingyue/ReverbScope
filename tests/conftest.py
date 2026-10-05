"""Shared fixtures: synthetic rooms and short sweeps so the suite runs fast."""

from __future__ import annotations

from collections.abc import Iterator

import numpy as np
import pytest
from scipy.signal import resample_poly

from reverbscope.audio.fake import make_rir
from reverbscope.core.sweep import normalisation_band_hz

# Re-export the synthetic room used throughout the suite.
__all__ = ["make_rir"]
from reverbscope.models.audio import FloatArray
from reverbscope.models.configuration import SweepSettings
from reverbscope.models.result import AnalysisResult


@pytest.fixture(autouse=True)
def isolate_reverbscope_home(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Keep recent-session writes out of the real ``~/.reverbscope``."""
    monkeypatch.setenv("REVERBSCOPE_HOME", str(tmp_path_factory.mktemp("reverbscope_home")))


@pytest.fixture(autouse=True)
def pin_language(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Run every test in English regardless of the developer's locale (#14).

    ``REVERBSCOPE_LANG`` and the POSIX locale variables would otherwise pick
    the CLI / GUI language; a test that wants Chinese passes ``--lang`` or
    calls ``activate("zh_CN")``. English is re-activated afterwards so a
    failing test cannot leak its catalog into the next one.
    """
    from reverbscope.i18n import activate

    for name in ("REVERBSCOPE_LANG", "LC_ALL", "LC_MESSAGES", "LANGUAGE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("LANG", "C.UTF-8")
    activate("en")
    yield
    activate("en")


DECAY_CONSTANT = 3.0 * np.log(10.0) * 2.0  # 60 dB in natural-log units: ln(10^6) = 13.8155


def exponential_decay_ir(
    sample_rate: int, rt60_s: float, length_s: float, seed: int = 1
) -> FloatArray:
    """Gaussian noise with an exactly exponential energy envelope (no direct sound)."""
    n = int(length_s * sample_rate)
    t = np.arange(n) / sample_rate
    rng = np.random.default_rng(seed)
    return np.asarray(
        rng.normal(0.0, 1.0, n) * np.exp(-DECAY_CONSTANT * t / (2.0 * rt60_s)), dtype=np.float64
    )


def alias_free_distortion(
    signal: FloatArray,
    amplitude: float,
    *,
    h2: float = 0.0,
    h3: float = 0.0,
    factor: int = 4,
) -> FloatArray:
    """Memoryless distortion with the given harmonic levels re the fundamental.

    Computed at ``factor`` times the sample rate and resampled back, so that
    harmonics above the Nyquist frequency are removed instead of folding back:
    a loudspeaker distorts in the analogue domain, where nothing aliases.
    Digital clipping is the opposite case and is built without oversampling.
    """
    up = np.asarray(resample_poly(signal, factor, 1), dtype=np.float64)
    distorted = up + (2.0 * h2 / amplitude) * up**2 + (4.0 * h3 / amplitude**2) * up**3
    return np.asarray(resample_poly(distorted, 1, factor), dtype=np.float64)


def fr_median_db(result: AnalysisResult) -> float:
    """Median raw frequency response (dB) over the normalisation band of the
    result's excitation band (the level a flat response should show)."""
    band = result.impulse_response.excitation_band
    assert band is not None
    lo, hi = normalisation_band_hz(band.low_hz, band.high_hz)
    fr = result.frequency_response
    select = (fr.frequencies_hz >= lo) & (fr.frequencies_hz <= hi)
    return float(np.median(fr.magnitude_db_raw[select]))


@pytest.fixture(scope="session")
def sample_rate() -> int:
    return 48000


@pytest.fixture(scope="session")
def short_sweep(sample_rate: int) -> SweepSettings:
    """A 2 s sweep keeps the whole suite fast while staying realistic."""
    return SweepSettings(
        sample_rate=sample_rate,
        duration_s=2.0,
        pre_silence_s=1.0,
        post_silence_s=1.5,
        level_dbfs=-12.0,
    )
