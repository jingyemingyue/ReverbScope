"""Small, offline regressions for imported-data resource and log boundaries."""

from __future__ import annotations

import io
import logging
import os
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import soundfile as sf

from reverbscope.errors import InvalidAudioError, SessionError
from reverbscope.io import jsonutil, wav
from reverbscope.logging_config import configure_logging


@pytest.mark.parametrize("format_name", ["FLAC", "WAV"])
def test_audio_decode_budget_is_based_on_float64_samples_not_encoded_size(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, format_name: str
) -> None:
    path = tmp_path / ("quiet." + format_name.lower())
    sf.write(str(path), np.zeros(10_000), 48000, format=format_name, subtype="PCM_16")
    monkeypatch.setattr(wav, "MAX_DECODED_AUDIO_BYTES", 8192, raising=False)
    with pytest.raises(InvalidAudioError, match="decoded"):
        wav.read_wav(path)


def test_decode_budget_counts_channels_and_accepts_the_exact_boundary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "stereo.wav"
    sf.write(str(path), np.zeros((100, 2)), 48000, subtype="PCM_16")
    monkeypatch.setattr(wav, "MAX_DECODED_AUDIO_BYTES", 100 * 2 * 8, raising=False)
    assert wav.read_wav(path).samples.nbytes == 1600
    monkeypatch.setattr(wav, "MAX_DECODED_AUDIO_BYTES", 1599)
    with pytest.raises(InvalidAudioError, match="decoded"):
        wav.read_wav(path)


def test_actual_decode_remains_bounded_when_metadata_understates_the_frames(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "changing.wav"
    path.write_bytes(b"fixture")
    reads = []

    class ChangingFile:
        frames = 1
        channels = 2
        samplerate = 48000

        def __enter__(self) -> ChangingFile:
            return self

        def __exit__(self, *args: object) -> None:
            pass

        def read(self, *, frames: int, dtype: str, always_2d: bool) -> np.ndarray:
            reads.append(frames)
            return np.zeros((frames, self.channels), dtype=dtype)

    monkeypatch.setattr(
        wav, "_soundfile", lambda: SimpleNamespace(SoundFile=lambda _: ChangingFile())
    )
    monkeypatch.setattr(wav, "MAX_DECODED_AUDIO_BYTES", 64)
    with pytest.raises(InvalidAudioError, match="decoded"):
        wav.read_wav(path)
    assert reads == [5]  # four stereo float64 frames plus one over-budget sentinel


def test_json_growth_after_the_size_check_still_obeys_the_byte_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "session.json"
    path.write_text("{}", encoding="utf-8")
    real_stat = Path.stat

    def stat_then_grow(self: Path, *, follow_symlinks: bool = True) -> os.stat_result:
        result = real_stat(self, follow_symlinks=follow_symlinks)
        if self == path:
            path.write_text('{"padding": "' + "x" * 128 + '"}', encoding="utf-8")
        return result

    monkeypatch.setattr(Path, "stat", stat_then_grow)
    with pytest.raises(SessionError, match="refused"):
        jsonutil.read_json_object(path, max_bytes=64)


def test_import_warning_text_cannot_emit_terminal_controls_or_forge_log_rows() -> None:
    stream = io.StringIO()
    logger = configure_logging(
        logging.WARNING, stream, fmt="%(levelname)s %(message)s", log_file=False
    )
    try:
        logger.warning("not bundling %s", "received\x1b[31m\a\r\nWARNING forged")
        logger.warning("next record")
        text = stream.getvalue()
        assert "\x1b" not in text and "\a" not in text and "\r" not in text
        assert text.count("\n") == 2
        assert "\\x1b" in text and "\\nWARNING forged" in text
    finally:
        for handler in list(logger.handlers):
            logger.removeHandler(handler)
            handler.close()


def test_safe_logging_keeps_tracebacks_and_does_not_mutate_shared_records() -> None:
    stream = io.StringIO()
    logger = configure_logging(logging.WARNING, stream, fmt="%(message)s", log_file=False)
    observed = []

    class Observer(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            observed.append(record.getMessage())

    logger.addHandler(Observer())
    payload = "received\x1b[31m\nname"
    try:
        logger.warning("%s", payload)
        try:
            raise ValueError("invalid input\x1b[31m")
        except ValueError:
            logger.exception("read failed")
        text = stream.getvalue()
        assert "\x1b" not in text
        assert "Traceback (most recent call last):\n" in text
        assert "ValueError:" in text
        assert observed[0] == payload
    finally:
        for handler in list(logger.handlers):
            logger.removeHandler(handler)
            handler.close()
