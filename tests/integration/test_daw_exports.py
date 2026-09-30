"""Recordings in the containers and sample formats mainstream DAWs export.

Pro Tools writes Broadcast WAV with ``bext`` / ``iXML`` / ``JUNK`` chunks,
Logic Pro records CAF and exports AIFF or WAV, Cubase / Nuendo, REAPER and
Studio One can write RF64 or Wave64 for long takes, and every DAW offers
16- / 24-bit PCM and 32-bit float. Each one must give the same analysis as a
plain WAV.
"""

from __future__ import annotations

import struct
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from roomscope.core.pipeline import Reference, analyze, synthetic_recording
from roomscope.io.wav import read_wav
from roomscope.models.configuration import SweepSettings
from tests.conftest import make_rir

#: (file name, soundfile format, subtype)
DAW_FORMATS = [
    ("take_pcm16.wav", "WAV", "PCM_16"),
    ("take_pcm24.wav", "WAV", "PCM_24"),
    ("take_pcm32.wav", "WAV", "PCM_32"),
    ("take_float.wav", "WAV", "FLOAT"),
    ("take_extensible.wav", "WAVEX", "PCM_24"),
    ("take_rf64.wav", "RF64", "PCM_24"),
    ("take.w64", "W64", "FLOAT"),
    ("take.aif", "AIFF", "PCM_24"),
    ("take.caf", "CAF", "PCM_24"),
    ("take.flac", "FLAC", "PCM_24"),
]


@pytest.fixture(scope="module")
def take(short_sweep: SweepSettings) -> np.ndarray:
    ir = make_rir(short_sweep.sample_rate, rt60_s=0.5, diffuse_level=0.02, length_s=1.0, seed=7)
    samples = synthetic_recording(short_sweep, ir, noise_rms=2e-4, gain=0.3, seed=7).samples
    return np.clip(samples, -0.99, 0.99)


@pytest.fixture(scope="module")
def reference_t30(take: np.ndarray, short_sweep: SweepSettings) -> float:
    from roomscope.models.audio import AudioSignal

    result = analyze(
        AudioSignal(take, short_sweep.sample_rate), Reference.from_settings(short_sweep)
    )
    t30 = result.decay.broadband.t30.seconds
    assert t30 is not None
    return t30


def _chunk(tag: bytes, payload: bytes) -> bytes:
    pad = b"\0" if len(payload) % 2 else b""
    return tag + struct.pack("<I", len(payload)) + payload + pad


def _broadcast_wav(path: Path, samples: np.ndarray, sample_rate: int) -> None:
    """A Pro Tools-style BWF: ``JUNK`` before ``fmt``, ``bext`` and ``iXML``
    between ``fmt`` and ``data``."""
    plain = path.with_suffix(".plain.wav")
    sf.write(plain, samples, sample_rate, subtype="PCM_24", format="WAV")
    raw = plain.read_bytes()
    assert raw[:4] == b"RIFF" and raw[8:12] == b"WAVE"
    chunks: dict[bytes, bytes] = {}
    offset = 12
    while offset < len(raw):
        tag = raw[offset : offset + 4]
        size = struct.unpack("<I", raw[offset + 4 : offset + 8])[0]
        chunks[tag] = raw[offset + 8 : offset + 8 + size]
        offset += 8 + size + (size % 2)
    bext = (
        b"RoomScope test take".ljust(256, b"\0")  # Description
        + b"Pro Tools".ljust(32, b"\0")  # Originator
        + b"".ljust(32, b"\0")  # OriginatorReference
        + b"2026-09-24"  # OriginationDate
        + b"12:00:00"  # OriginationTime
        + struct.pack("<II", 0, 0)  # TimeReference
        + struct.pack("<H", 1)  # Version
        + b"\0" * 64  # UMID
        + b"\0" * 190  # loudness fields + reserved
    )
    ixml = b'<?xml version="1.0"?><BWFXML><PROJECT>RoomScope</PROJECT></BWFXML>'
    body = (
        _chunk(b"JUNK", b"\0" * 28)
        + _chunk(b"fmt ", chunks[b"fmt "])
        + _chunk(b"bext", bext)
        + _chunk(b"iXML", ixml)
        + _chunk(b"data", chunks[b"data"])
    )
    path.write_bytes(b"RIFF" + struct.pack("<I", 4 + len(body)) + b"WAVE" + body)
    plain.unlink()


@pytest.mark.parametrize(("name", "container", "subtype"), DAW_FORMATS)
def test_daw_export_formats_give_the_same_analysis(
    tmp_path: Path,
    take: np.ndarray,
    short_sweep: SweepSettings,
    reference_t30: float,
    name: str,
    container: str,
    subtype: str,
) -> None:
    path = tmp_path / name
    sf.write(path, take, short_sweep.sample_rate, subtype=subtype, format=container)
    recording = read_wav(path)
    assert recording.sample_rate == short_sweep.sample_rate
    result = analyze(recording, Reference.from_settings(short_sweep))
    assert result.impulse_response.direct_sound_confidence == "high"
    assert result.decay.broadband.t30.seconds == pytest.approx(reference_t30, rel=0.02)


def test_broadcast_wav_with_metadata_chunks(
    tmp_path: Path, take: np.ndarray, short_sweep: SweepSettings, reference_t30: float
) -> None:
    path = tmp_path / "Audio 1_01.wav"
    _broadcast_wav(path, take, short_sweep.sample_rate)
    recording = read_wav(path)
    np.testing.assert_allclose(recording.samples, take, atol=2.0**-22)
    result = analyze(recording, Reference.from_settings(short_sweep))
    assert result.decay.broadband.t30.seconds == pytest.approx(reference_t30, rel=0.02)


def test_stereo_export_of_a_mono_microphone(
    tmp_path: Path, take: np.ndarray, short_sweep: SweepSettings
) -> None:
    """A stereo bounce of a mono microphone track: both channels identical,
    or the microphone on one side and silence on the other."""
    for pair in (np.column_stack([take, take]), np.column_stack([np.zeros_like(take), take])):
        path = tmp_path / "stereo_bounce.wav"
        sf.write(path, pair, short_sweep.sample_rate, subtype="PCM_24")
        result = analyze(read_wav(path), Reference.from_settings(short_sweep))
        assert result.impulse_response.direct_sound_confidence == "high"
