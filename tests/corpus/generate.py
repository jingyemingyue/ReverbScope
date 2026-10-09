"""Generate the synthetic part of the regression corpus (tests/corpus/README.md).

Every file written here is small, synthetic and deterministic. Run it from
the repository root after a format change::

    python tests/corpus/generate.py

The manifest (``tests/corpus/manifest.json``) is kept by hand: it says why
each file exists and what ReverbScope must do with it. A file that came from
a community report is minimised by hand, not generated here, and listed in
the manifest with its issue.
"""

from __future__ import annotations

import json
import os
import shutil
import struct
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent / "files"
RATE = 48000


def _tone(frames: int, channels: int = 1) -> np.ndarray:
    """A 1 kHz tone at -12 dBFS, ``frames`` long, as float64."""
    t = np.arange(frames) / RATE
    mono = 0.25 * np.sin(2 * np.pi * 1000.0 * t)
    return mono if channels == 1 else np.stack([mono, 0.5 * mono], axis=1)


def _riff(
    *,
    frames: int = 100,
    channels: int = 1,
    rate: int = RATE,
    bits: int = 16,
    fmt_tag: int = 1,
    fmt_first: bool = True,
    data_size: int | None = None,
    list_chunk: bool = False,
    pad_list: bool = True,
    riff_size: int | None = None,
    data_chunk: bool = True,
) -> bytes:
    """A RIFF/WAVE file assembled by hand, so that every field can be wrong."""
    block = channels * bits // 8
    if bits == 16:
        pcm = (_tone(frames, channels) * 32767.0).astype("<i2").tobytes()
    else:
        pcm = _tone(frames, channels).astype("<f4").tobytes()
    fmt = struct.pack("<HHIIHH", fmt_tag, channels, rate, rate * block, block, bits)
    fmt_chunk = b"fmt " + struct.pack("<I", len(fmt)) + fmt
    size = len(pcm) if data_size is None else data_size
    data = (b"data" + struct.pack("<I", size) + pcm) if data_chunk else b""
    body = fmt_chunk + data if fmt_first else data + fmt_chunk
    if list_chunk:
        body = b"LIST" + struct.pack("<I", 5) + b"abcde" + (b"\x00" if pad_list else b"") + body
    total = 4 + len(body) if riff_size is None else riff_size
    return b"RIFF" + struct.pack("<I", total) + b"WAVE" + body


def _write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def wav_structures() -> None:
    base = ROOT / "wav"
    _write(base / "pcm16_mono_100.wav", _riff())
    _write(base / "float32_stereo_100.wav", _riff(channels=2, bits=32, fmt_tag=3))
    _write(base / "list_before_fmt_padded.wav", _riff(list_chunk=True))
    _write(base / "list_before_fmt_unpadded.wav", _riff(list_chunk=True, pad_list=False))
    _write(base / "data_before_fmt.wav", _riff(fmt_first=False))
    _write(base / "data_size_streaming.wav", _riff(data_size=0xFFFFFFFF))
    _write(base / "data_size_beyond_file.wav", _riff(data_size=10 * 96000))
    _write(base / "data_size_zero.wav", _riff(data_size=0))
    _write(base / "data_size_odd.wav", _riff(data_size=199))
    _write(base / "zero_channels.wav", _riff(channels=0))
    _write(base / "zero_sample_rate.wav", _riff(rate=0))
    _write(base / "extensible_without_extension.wav", _riff(fmt_tag=0xFFFE))
    _write(base / "mp3_format_tag.wav", _riff(fmt_tag=0x55))
    _write(base / "riff_size_zero.wav", _riff(riff_size=0))
    _write(base / "only_header.wav", _riff(data_chunk=False))
    _write(base / "one_frame.wav", _riff(frames=1))
    nan = _tone(100).astype("<f4")
    nan[10] = np.nan
    fmt = struct.pack("<HHIIHH", 3, 1, RATE, RATE * 4, 4, 32)
    body = b"fmt " + struct.pack("<I", 16) + fmt + b"data" + struct.pack("<I", 400) + nan.tobytes()
    _write(
        base / "float32_with_nan.wav", b"RIFF" + struct.pack("<I", 4 + len(body)) + b"WAVE" + body
    )


def containers() -> None:
    import soundfile as sf

    base = ROOT / "containers"
    base.mkdir(parents=True, exist_ok=True)
    tone = _tone(100)
    for name, fmt, subtype in (
        ("minimal.aiff", "AIFF", "PCM_24"),
        ("minimal.caf", "CAF", "PCM_24"),
        ("minimal.flac", "FLAC", "PCM_24"),
        ("minimal.w64", "W64", "PCM_24"),
        ("minimal.rf64", "RF64", "PCM_24"),
        ("minimal_float.aiff", "AIFF", "FLOAT"),
    ):
        sf.write(str(base / name), tone, RATE, format=fmt, subtype=subtype)


def sidecars() -> None:
    from reverbscope.io.wav import write_sweep_file
    from reverbscope.models.configuration import SweepSettings

    base = ROOT / "sidecar"
    base.mkdir(parents=True, exist_ok=True)
    settings = SweepSettings(
        sample_rate=RATE, duration_s=0.5, pre_silence_s=0.1, post_silence_s=0.1
    )
    wav, side = write_sweep_file(settings, base / "scratch.wav")
    text = side.read_text(encoding="utf-8")
    payload = json.loads(text)
    wav.unlink()
    side.unlink()
    (base / "bom_crlf.reverbscope-sweep.json").write_bytes(
        b"\xef\xbb\xbf" + text.replace("\n", "\r\n").encode("utf-8")
    )
    (base / "trailing_garbage.reverbscope-sweep.json").write_text(text + "\n}\n", encoding="utf-8")
    edited = json.loads(text)
    edited["reverbscope_sweep"]["sample_rate"] = "48000"
    (base / "sample_rate_as_text.reverbscope-sweep.json").write_text(json.dumps(edited), "utf-8")
    edited = json.loads(text)
    edited["reverbscope_sweep"]["duration_s"] = float("nan")
    (base / "duration_nan.reverbscope-sweep.json").write_text(json.dumps(edited), "utf-8")
    edited = json.loads(text)
    edited["schema_version"] = 99
    (base / "newer_schema.reverbscope-sweep.json").write_text(json.dumps(edited), "utf-8")
    (base / "not_an_object.reverbscope-sweep.json").write_text("[]", encoding="utf-8")
    (base / "missing_definition.reverbscope-sweep.json").write_text(
        json.dumps({"schema_version": 1, "note": payload["note"]}), encoding="utf-8"
    )


def sessions() -> None:
    """A session saved by this version, then every way its files can go wrong.

    A second of silence before the sweep and 1.5 s after it (the noise floor
    needs a verified quiet segment; the health check wants a second of decay)
    make the baseline good on every check; the derived folders keep
    its files and change one thing each.
    """
    from reverbscope.audio.fake import make_rir
    from reverbscope.core.pipeline import Reference, analyze, synthetic_recording
    from reverbscope.io.session_store import save_measurement
    from reverbscope.io.wav import read_wav, write_wav
    from reverbscope.models.configuration import AnalysisSettings, SweepSettings
    from reverbscope.models.session import MeasurementSession

    base = ROOT / "session"
    if base.exists():
        shutil.rmtree(base)
    settings = SweepSettings(
        sample_rate=RATE, duration_s=0.5, pre_silence_s=1.0, post_silence_s=1.5
    )
    recording = synthetic_recording(
        settings, make_rir(RATE, rt60_s=0.2, length_s=0.3), noise_rms=1e-5
    )
    result = analyze(
        recording, Reference.from_settings(settings), AnalysisSettings(ir_max_length_s=0.2)
    )
    session = MeasurementSession(
        session_id="corpus-base",
        created_at="2026-10-07T00:00:00+00:00",
        room_name="Corpus",
        sweep_settings=settings,
        analysis_settings=AnalysisSettings(ir_max_length_s=0.2),
        recording_profile="generic",
        platform="corpus",
        reverbscope_version="0.5.0b2",
    )
    save_measurement(base / "base", session, result, include_curves=False, copy_recording=False)
    # The loader needs the direct sound only; a 300-sample response keeps the
    # corpus small (every derived folder carries its own copy).
    ir = read_wav(base / "base" / "impulse_response.wav")
    write_wav(base / "base" / "impulse_response.wav", ir.samples[:300], RATE, subtype="FLOAT")

    def derive(name: str) -> Path:
        folder = base / name
        shutil.copytree(base / "base", folder)
        return folder

    def rewrite(folder: Path, member: str, edit) -> None:  # type: ignore[no-untyped-def]
        path = folder / member
        data = json.loads(path.read_text(encoding="utf-8"))
        edit(data)
        path.write_text(json.dumps(data, indent=1), encoding="utf-8")

    def legacy(data: dict) -> None:
        for key in ("placement", "clipping", "dropouts"):
            data[key] = None
        data["impulse_response"].pop("direct_level_dbfs", None)
        data["impulse_response"].pop("playback_speed", None)
        for band in [data["decay"]["broadband"], *data["decay"]["bands"]]:
            for key in ("c50", "c80", "d50", "centre_time", "onset_time_s", "mid_band_hz"):
                band.pop(key, None)

    rewrite(derive("legacy-fields-missing"), "result.json", legacy)

    def older(data: dict) -> None:
        data["schema_version"] = 0
        data["future_field"] = {"from": "a later ReverbScope", "values": [1, 2, 3]}

    rewrite(derive("schema-0-unknown-fields"), "session.json", older)
    folder = derive("bom-crlf")
    for member in ("session.json", "result.json"):
        raw = (folder / member).read_text(encoding="utf-8")
        (folder / member).write_bytes(b"\xef\xbb\xbf" + raw.replace("\n", "\r\n").encode("utf-8"))
    folder = derive("utf16")
    (folder / "session.json").write_bytes(
        (folder / "session.json").read_text("utf-8").encode("utf-16")
    )
    folder = derive("half-written-result")
    raw = (folder / "result.json").read_bytes()
    (folder / "result.json").write_bytes(raw[: len(raw) // 2])
    rewrite(
        derive("newer-result-schema"), "result.json", lambda d: d.__setitem__("schema_version", 2)
    )
    folder = derive("ir-cut-before-direct")
    write_wav(folder / "impulse_response.wav", np.array([0.0, 1.0, 0.0]), RATE, subtype="FLOAT")
    folder = derive("ir-other-rate")
    write_wav(folder / "impulse_response.wav", ir.samples[:300], 44100, subtype="FLOAT")
    rewrite(
        derive("member-outside"),
        "session.json",
        lambda d: d.__setitem__("result_path", "../base/result.json"),
    )
    folder = derive("nan-infinity-tokens")
    text = (folder / "result.json").read_text(encoding="utf-8")
    data = json.loads(text)
    data["decay"]["broadband"]["rt60_estimate_s"] = float("nan")
    data["noise"]["rms_dbfs"] = float("inf")
    (folder / "result.json").write_text(json.dumps(data, indent=1), encoding="utf-8")
    (base / "empty-session-json").mkdir()
    (base / "empty-session-json" / "session.json").write_bytes(b"")
    shutil.copy2(base / "base" / "result.json", base / "empty-session-json" / "result.json")


def projects_and_comparisons() -> None:
    base = ROOT / "project"
    base.mkdir(parents=True, exist_ok=True)
    (base / "session_dirs_as_text.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "name": "Room",
                "positions": [{"label": "desk", "session_dirs": "abc"}],
            }
        ),
        encoding="utf-8",
    )
    (base / "positions_as_number.json").write_text(
        json.dumps({"schema_version": 1, "name": "Room", "positions": 5}), encoding="utf-8"
    )
    base = ROOT / "comparison"
    base.mkdir(parents=True, exist_ok=True)
    (base / "comparable_as_text.json").write_text(
        json.dumps({"comparable": "false", "common_band": None}), encoding="utf-8"
    )
    (base / "delta_name_missing.json").write_text(
        json.dumps({"comparable": True, "common_band": None, "decay": [{"validity": "valid"}]}),
        encoding="utf-8",
    )
    (base / "frequency_huge_integer.json").write_text(
        '{"comparable": true, "common_band": null, "frequency_response": {"frequencies_hz": [1'
        + "0" * 400
        + "]}}",
        encoding="utf-8",
    )


def main() -> int:
    os.environ.setdefault("REVERBSCOPE_HOME", str(ROOT.parent / ".home"))
    wav_structures()
    containers()
    sidecars()
    sessions()
    projects_and_comparisons()
    shutil.rmtree(ROOT.parent / ".home", ignore_errors=True)
    total = sum(p.stat().st_size for p in ROOT.rglob("*") if p.is_file())
    print(f"{sum(1 for p in ROOT.rglob('*') if p.is_file())} files, {total / 1024:.0f} KB")  # noqa: T201
    return 0


if __name__ == "__main__":
    sys.exit(main())
