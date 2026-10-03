from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from roomscope.core.sweep import measurement_signal
from roomscope.errors import ConfigurationError, InvalidAudioError
from roomscope.io.wav import (
    load_reference,
    read_sweep_sidecar,
    read_wav,
    sidecar_path,
    write_sweep_file,
    write_wav,
)
from roomscope.models.configuration import SweepSettings


def test_float_round_trip_mono_and_stereo(tmp_path: Path, sample_rate: int) -> None:
    mono = np.linspace(-1.5, 1.5, 1000)
    path = write_wav(tmp_path / "mono.wav", mono, sample_rate, subtype="FLOAT")
    back = read_wav(path)
    assert back.n_channels == 1 and back.sample_rate == sample_rate
    assert np.allclose(back.samples, mono, atol=1e-6)
    stereo = np.stack([mono * 0.5, mono * 0.25], axis=1)
    path2 = write_wav(tmp_path / "stereo.wav", stereo, sample_rate, subtype="FLOAT")
    back2 = read_wav(path2)
    assert back2.n_channels == 2
    assert np.allclose(back2.samples, stereo, atol=1e-6)


def test_pcm24_round_trip_is_close(tmp_path: Path, sample_rate: int) -> None:
    x = 0.9 * np.sin(np.linspace(0, 40 * np.pi, 4000))
    path = write_wav(tmp_path / "pcm.wav", x, sample_rate, subtype="PCM_24")
    back = read_wav(path)
    assert np.allclose(back.samples, x, atol=2e-7)


def test_pcm_clipping_rejected(tmp_path: Path, sample_rate: int) -> None:
    with pytest.raises(ConfigurationError):
        write_wav(tmp_path / "clip.wav", np.array([0.0, 1.5]), sample_rate, subtype="PCM_24")


def test_missing_and_invalid_files(tmp_path: Path) -> None:
    with pytest.raises(InvalidAudioError):
        read_wav(tmp_path / "nope.wav")
    bad = tmp_path / "bad.wav"
    bad.write_text("this is not audio")
    with pytest.raises(InvalidAudioError):
        read_wav(bad)


def test_sweep_file_and_sidecar(tmp_path: Path, short_sweep: SweepSettings) -> None:
    wav, side = write_sweep_file(short_sweep, tmp_path / "sweep.wav")
    assert wav.is_file() and side.is_file()
    assert side == sidecar_path(wav) == tmp_path / "sweep.roomscope-sweep.json"
    assert read_sweep_sidecar(wav) == short_sweep
    assert read_sweep_sidecar(side) == short_sweep
    signal = read_wav(wav)
    assert signal.n_samples == short_sweep.total_samples
    assert np.allclose(signal.samples, measurement_signal(short_sweep), atol=2e-7)
    ref = load_reference(wav)
    assert ref.settings == short_sweep and ref.signal is None
    ref2 = load_reference(side)
    assert ref2.settings == short_sweep


def test_reference_from_plain_wav(tmp_path: Path, short_sweep: SweepSettings) -> None:
    path = write_wav(
        tmp_path / "plain.wav", measurement_signal(short_sweep), short_sweep.sample_rate
    )
    assert read_sweep_sidecar(path) is None
    ref = load_reference(path)
    assert ref.settings is None and ref.signal is not None
    assert ref.sample_rate == short_sweep.sample_rate


def test_bad_sidecar_rejected(tmp_path: Path) -> None:
    side = tmp_path / "x.roomscope-sweep.json"
    side.write_text("{}")
    with pytest.raises(ConfigurationError):
        read_sweep_sidecar(side)
    with pytest.raises(ConfigurationError):
        load_reference(tmp_path / "other.json")


@pytest.mark.parametrize("subtype", ["PCM_24", "FLOAT"])
def test_write_wav_refuses_non_finite_samples(tmp_path: Path, subtype: str) -> None:
    """NaN passed the full-scale check and was written as a -1.0 click (PCM)
    or as a file read_wav then refused (FLOAT)."""
    with pytest.raises(InvalidAudioError, match="NaN"):
        write_wav(tmp_path / "x.wav", np.array([0.0, np.nan, 0.5]), 48000, subtype=subtype)
    assert not (tmp_path / "x.wav").exists()
