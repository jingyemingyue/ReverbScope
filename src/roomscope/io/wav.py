"""WAV reading/writing via ``soundfile`` (libsndfile) and sweep sidecar files.

The sweep WAV that RoomScope generates is accompanied by
``<name>.roomscope-sweep.json`` containing the exact :class:`SweepSettings`.
With the sidecar the analysis regenerates the reference sweep analytically at
any sample rate; without it, the WAV itself is used as the reference signal.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np

from roomscope import __version__
from roomscope.core.pipeline import Reference
from roomscope.core.sweep import measurement_signal
from roomscope.errors import ConfigurationError, InvalidAudioError, SessionError
from roomscope.i18n import _
from roomscope.io.jsonutil import read_json_object, write_text_atomic
from roomscope.models.audio import AudioSignal, FloatArray
from roomscope.models.configuration import SweepSettings
from roomscope.models.loadutil import read_schema_version

SIDECAR_SUFFIX = ".roomscope-sweep.json"
SIDECAR_KEY = "roomscope_sweep"
SIDECAR_SCHEMA_VERSION = 1


def _soundfile() -> Any:
    try:
        import soundfile
    except ImportError as exc:  # pragma: no cover - depends on the environment
        raise InvalidAudioError(
            _("the 'soundfile' package (libsndfile) is required for WAV I/O")
        ) from exc
    return soundfile


def read_wav(path: str | Path) -> AudioSignal:
    """Read an audio file as float64. Multi-channel files keep their channels."""
    sf = _soundfile()
    file_path = Path(path)
    if not file_path.is_file():
        raise InvalidAudioError(_("audio file not found: {path}").format(path=file_path))
    try:
        data, sample_rate = sf.read(str(file_path), dtype="float64", always_2d=True)
    except Exception as exc:  # libsndfile raises RuntimeError / soundfile.LibsndfileError
        raise InvalidAudioError(
            _("cannot read audio file {name}: {error}").format(name=file_path.name, error=exc)
        ) from exc
    samples = np.asarray(data, dtype=np.float64)
    if samples.shape[0] == 0:
        raise InvalidAudioError(_("audio file is empty: {name}").format(name=file_path.name))
    if samples.shape[1] == 1:
        samples = np.ascontiguousarray(samples[:, 0])
    return AudioSignal(samples=samples, sample_rate=int(sample_rate), source=str(file_path))


def write_wav(
    path: str | Path,
    samples: FloatArray,
    sample_rate: int,
    *,
    subtype: str = "PCM_24",
) -> Path:
    """Write ``samples`` (mono or ``(n, channels)``) as WAV.

    PCM subtypes require ``|x| <= 1``; use ``subtype="FLOAT"`` for impulse
    responses, which may exceed full scale.
    """
    sf = _soundfile()
    file_path = Path(path)
    data = np.asarray(samples, dtype=np.float64)
    if data.ndim not in (1, 2) or data.shape[0] == 0:
        raise InvalidAudioError(_("samples must be a non-empty 1-D or 2-D array"))
    if not np.all(np.isfinite(data)):
        # NaN passes the full-scale test below and is written as a -1.0 click.
        raise InvalidAudioError(_("signal contains NaN or infinite samples"))
    if subtype.startswith("PCM") and float(np.max(np.abs(data))) > 1.0:
        raise ConfigurationError(
            _("signal exceeds full scale; use subtype='FLOAT' or lower the level")
        )
    file_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        sf.write(str(file_path), data, sample_rate, subtype=subtype)
    except Exception as exc:
        raise InvalidAudioError(
            _("cannot write audio file {path}: {error}").format(path=file_path, error=exc)
        ) from exc
    return file_path


def sidecar_path(wav_path: str | Path) -> Path:
    p = Path(wav_path)
    return p.with_name(p.stem + SIDECAR_SUFFIX)


def _sha256(samples: FloatArray) -> str:
    return hashlib.sha256(np.ascontiguousarray(samples, dtype=np.float32).tobytes()).hexdigest()


def write_sweep_file(settings: SweepSettings, path: str | Path) -> tuple[Path, Path]:
    """Write the measurement signal (silence + sweep + silence) and its sidecar."""
    signal = measurement_signal(settings)
    wav_path = write_wav(path, signal, settings.sample_rate, subtype="PCM_24")
    payload = {
        "schema_version": SIDECAR_SCHEMA_VERSION,
        SIDECAR_KEY: settings.to_dict(),
        "roomscope_version": __version__,
        "wav_file": wav_path.name,
        "signal_sha256_float32": _sha256(signal),
        "note": (
            "Keep this file next to the WAV. RoomScope uses it to regenerate the exact "
            "reference sweep when analysing a recording."
        ),
    }
    side = sidecar_path(wav_path)
    write_text_atomic(side, json.dumps(payload, indent=2))
    return wav_path, side


def read_sweep_sidecar(path: str | Path) -> SweepSettings | None:
    """Return the sweep settings stored next to ``path`` (a WAV or the JSON itself)."""
    p = Path(path)
    side = p if p.suffix == ".json" else sidecar_path(p)
    if not side.is_file():
        return None
    try:
        if side.stat().st_size > 1_000_000:
            raise ConfigurationError(
                _("{name} is larger than 1 MB; a sweep sidecar cannot be that large").format(
                    name=side.name
                )
            )
        payload = read_json_object(side, kind="sweep sidecar")
        read_schema_version(payload, SIDECAR_SCHEMA_VERSION, "sweep sidecar")
    except (OSError, SessionError) as exc:
        raise ConfigurationError(
            _("cannot read sweep sidecar {name}: {error}").format(name=side.name, error=exc)
        ) from exc
    if SIDECAR_KEY not in payload:
        raise ConfigurationError(
            _("{name} is not a RoomScope sweep sidecar").format(name=side.name)
        )
    return SweepSettings.from_dict(payload[SIDECAR_KEY])


def load_reference(path: str | Path) -> Reference:
    """Build a :class:`Reference` from a sweep WAV (preferring its sidecar) or a
    sidecar JSON file."""
    settings = read_sweep_sidecar(path)
    if settings is not None:
        return Reference.from_settings(settings)
    p = Path(path)
    if p.suffix == ".json":
        raise ConfigurationError(
            _("{name} does not contain a sweep definition").format(name=p.name)
        )
    signal = read_wav(p)
    return Reference.from_signal(signal.samples, signal.sample_rate)
