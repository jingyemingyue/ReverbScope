"""Saving and loading measurement sessions.

A session directory contains::

    session.json            metadata + analysis summary (MeasurementSession)
    result.json             full AnalysisResult (metrics and curves)
    impulse_response.wav    raw impulse response, 32-bit float
    sweep.reverbscope-sweep.json   always copied when a sidecar is available
    recording.wav           copied when copy_recording is on (GUI default)

Raw sweep and recording files are never modified in place.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import zipfile
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from reverbscope.models.comparison import ComparisonResult

from reverbscope.errors import SessionError
from reverbscope.i18n import _
from reverbscope.io.wav import read_wav, write_wav
from reverbscope.models.result import AnalysisResult, Validity
from reverbscope.models.session import MeasurementSession

log = logging.getLogger(__name__)

SESSION_FILE = "session.json"
RESULT_FILE = "result.json"
COMPARISON_FILE = "comparison.json"
IR_FILE = "impulse_response.wav"
RECORDING_FILE = "recording.wav"
SWEEP_SIDECAR_NAME = "sweep.reverbscope-sweep.json"
AUDIO_SUFFIXES = {".wav", ".flac", ".aiff", ".aif", ".ogg"}


def _relative(path: str | Path | None, base: Path) -> str | None:
    if path is None:
        return None
    p = Path(path).resolve()
    try:
        return str(p.relative_to(base.resolve()))
    except ValueError:
        return str(p)


def _metric_value(metric: dict[str, Any]) -> float | None:
    return metric["seconds"] if metric.get("validity") == str(Validity.VALID) else None


def result_summary(result: AnalysisResult) -> dict[str, Any]:
    """Scalar summary of a result for listings and the session file."""
    broadband = result.decay.broadband
    bands = {
        band.band_label: {
            "rt60_estimate_s": band.rt60_estimate_s,
            "rt60_basis": band.rt60_basis,
            "t20_s": band.t20.seconds if band.t20.validity is Validity.VALID else None,
            "t30_s": band.t30.seconds if band.t30.validity is Validity.VALID else None,
            "edt_s": band.edt.seconds if band.edt.validity is Validity.VALID else None,
        }
        for band in result.decay.bands
    }
    return {
        "created_at": result.created_at,
        "sample_rate": result.sample_rate,
        "broadband_rt60_estimate_s": broadband.rt60_estimate_s,
        "broadband_rt60_basis": broadband.rt60_basis,
        "broadband_edt_s": broadband.edt.seconds
        if broadband.edt.validity is Validity.VALID
        else None,
        "broadband_peak_to_noise_db": broadband.peak_to_noise_db,
        "bands": bands,
        "noise_rms_dbfs": result.noise.rms_dbfs,
        "hum_detected": [h.base_hz for h in result.noise.hum if h.detected],
        "early_reflections": [r.to_dict() for r in result.reflections.reflections[:5]],
        "resonance_candidates_hz": [c.frequency_hz for c in result.resonances.candidates],
        "direct_sound_confidence": result.impulse_response.direct_sound_confidence,
        "warnings": list(result.warnings),
    }


def save_measurement(
    directory: str | Path,
    session: MeasurementSession,
    result: AnalysisResult,
    *,
    include_curves: bool = True,
    copy_recording: bool | None = None,
) -> Path:
    """Write session.json, result.json and impulse_response.wav into ``directory``.

    The sweep sidecar is always copied when one can be found. The raw recording
    is copied when ``copy_recording`` is true, or when it is omitted and the
    user settings default to copying (the GUI default).
    """
    base = Path(directory)
    base.mkdir(parents=True, exist_ok=True)
    if copy_recording is None:
        from reverbscope.settings import load_settings

        copy_recording = load_settings().copy_recording
    original_sweep = session.sweep_path
    original_recording = session.recording_path
    ir_path = write_wav(
        base / IR_FILE, result.impulse_response.samples, result.sample_rate, subtype="FLOAT"
    )
    result_path = base / RESULT_FILE
    try:
        result_path.write_text(
            json.dumps(result.to_dict(include_curves), indent=1), encoding="utf-8"
        )
    except (OSError, TypeError, ValueError) as exc:
        raise SessionError(
            _("cannot write {path}: {error}").format(path=result_path, error=exc)
        ) from exc
    _copy_sidecar(original_sweep, base)
    if copy_recording:
        copied = _copy_recording(original_recording, base)
        if copied is not None:
            session.recording_path = str(copied)
    session.sample_rate = result.sample_rate
    session.impulse_response_path = _relative(ir_path, base)
    session.result_path = _relative(result_path, base)
    session.sweep_path = _relative(session.sweep_path, base)
    session.recording_path = _relative(session.recording_path, base)
    session.analysis_summary = result_summary(result)
    session_path = base / SESSION_FILE
    try:
        session_path.write_text(json.dumps(session.to_dict(), indent=2), encoding="utf-8")
    except (OSError, TypeError, ValueError) as exc:
        raise SessionError(
            _("cannot write {path}: {error}").format(path=session_path, error=exc)
        ) from exc
    return session_path


def bundle_session(
    directory: str | Path,
    dest: str | Path | None = None,
    *,
    include_audio: bool = True,
) -> Path:
    """Zip a session folder for a bug report. ``include_audio=False`` drops WAVs."""
    session_file = _session_file(directory)
    base = session_file.parent
    target = Path(dest) if dest is not None else base.with_name(base.name + ".zip")
    if target.is_dir():
        target = target / f"{base.name}.zip"
    try:
        target.resolve().relative_to(base.resolve())
    except ValueError:
        pass
    else:
        # The archive would contain itself and grow without end.
        raise SessionError(
            _("write the bundle outside the session folder (it would be inside {folder})").format(
                folder=base
            )
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    inside = base.resolve()
    try:
        with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(base.rglob("*")):
                if not path.is_file():
                    continue
                if not include_audio and path.suffix.lower() in AUDIO_SUFFIXES:
                    continue
                if not path.resolve().is_relative_to(inside):
                    # A link out of the folder (a session from someone else)
                    # must not put one of your files into a public report.
                    log.warning("not bundling %s: it links outside the session folder", path)
                    continue
                archive.write(path, path.relative_to(base).as_posix())
    except OSError as exc:
        raise SessionError(
            _("cannot write bundle {path}: {error}").format(path=target, error=exc)
        ) from exc
    return target


def _copy_into(src: Path, dest: Path) -> Path | None:
    if not src.is_file():
        return None
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        # samefile also matches on case-insensitive file systems (macOS, Windows)
        # where Recording.wav and recording.wav are one file.
        if dest.exists() and os.path.samefile(src, dest):
            return dest
        shutil.copy2(src, dest)
    except OSError as exc:
        raise SessionError(
            _("cannot copy {source} to {target}: {error}").format(
                source=src, target=dest, error=exc
            )
        ) from exc
    return dest


def _copy_sidecar(sweep_path: str | None, base: Path) -> Path | None:
    if not sweep_path:
        return None
    from reverbscope.io.wav import SIDECAR_SUFFIX, sidecar_path

    src = Path(sweep_path)
    candidates = []
    if src.suffix == ".json" or src.name.endswith(SIDECAR_SUFFIX):
        candidates.append(src)
    else:
        candidates.append(sidecar_path(src))
        candidates.append(src.with_name(SWEEP_SIDECAR_NAME))
    for candidate in candidates:
        if candidate.is_file():
            return _copy_into(candidate, base / SWEEP_SIDECAR_NAME)
    return None


def _copy_recording(recording_path: str | None, base: Path) -> Path | None:
    if not recording_path:
        return None
    src = Path(recording_path)
    if not src.is_file() and not src.is_absolute():
        src = base / src
    return _copy_into(src, base / RECORDING_FILE)


def load_session(path: str | Path) -> MeasurementSession:
    """Load a session from ``session.json`` or from its directory."""
    return MeasurementSession.from_dict(_read_json(_session_file(path)))


def load_result(path: str | Path) -> AnalysisResult:
    """Load an :class:`AnalysisResult` from ``result.json``."""
    return AnalysisResult.from_dict(_read_json(Path(path), kind="result"))


@dataclass(frozen=True)
class LoadedMeasurement:
    """A session directory after :func:`load_measurement`."""

    directory: Path
    session: MeasurementSession
    result: AnalysisResult


@dataclass(frozen=True)
class SessionListing:
    """One ``session.json`` found by :func:`list_sessions``."""

    path: Path
    session: MeasurementSession

    @property
    def label(self) -> str:
        room = self.session.room_name or _("(unnamed room)")
        created = self.session.created_at
        rt60 = self.session.analysis_summary.get("broadband_rt60_estimate_s")
        rt60_text = (
            _("RT60 {seconds:.2f} s").format(seconds=rt60)
            if isinstance(rt60, (int, float))
            else _("RT60 n/a")
        )
        return f"{room}  ·  {created}  ·  {rt60_text}"


def load_measurement(path: str | Path) -> LoadedMeasurement:
    """Load session metadata, ``result.json`` and the IR WAV from a directory."""
    session_file = _session_file(path)
    directory = session_file.parent
    session = MeasurementSession.from_dict(_read_json(session_file))
    result_path = _resolve_member(directory, session.result_path, RESULT_FILE)
    if not result_path.is_file():
        raise SessionError(_("result.json not found next to {path}").format(path=session_file))
    result = load_result(result_path)
    ir_path = _resolve_member(directory, session.impulse_response_path, IR_FILE)
    if ir_path.is_file():
        ir = read_wav(ir_path)
        samples = ir.samples if ir.samples.ndim == 1 else ir.samples[:, 0]
        result = replace(
            result,
            impulse_response=replace(
                result.impulse_response, samples=samples, sample_rate=ir.sample_rate
            ),
        )
    elif result.impulse_response.samples.size == 0:
        raise SessionError(
            _(
                "impulse_response.wav not found next to {path} and result.json has no IR samples"
            ).format(path=session_file)
        )
    return LoadedMeasurement(directory=directory, session=session, result=result)


def list_sessions(root: str | Path, *, max_depth: int = 2) -> list[SessionListing]:
    """Find ``session.json`` files under ``root``, newest ``created_at`` first."""
    base = Path(root)
    if not base.is_dir():
        raise SessionError(_("not a directory: {path}").format(path=base))
    found: list[SessionListing] = []
    for candidate in base.rglob(SESSION_FILE):
        try:
            rel = candidate.relative_to(base)
        except ValueError:
            continue
        if len(rel.parts) - 1 > max_depth:
            continue
        if any(part.startswith(".") for part in rel.parts[:-1]):
            continue
        try:
            found.append(SessionListing(path=candidate.parent, session=load_session(candidate)))
        except SessionError:
            continue
    found.sort(key=lambda item: item.session.created_at, reverse=True)
    return found


def _session_file(path: str | Path) -> Path:
    p = Path(path)
    if p.is_dir():
        p = p / SESSION_FILE
    if not p.is_file():
        raise SessionError(_("session file not found: {path}").format(path=p))
    return p


def _read_json(path: Path, *, kind: str = "session") -> dict[str, Any]:
    from reverbscope.io.jsonutil import read_json_object

    return read_json_object(path, kind=kind)


def _resolve_member(directory: Path, stored: str | None, default_name: str) -> Path:
    """Resolve a file named in ``session.json`` inside the session directory.

    ``result.json`` and ``impulse_response.wav`` are always written inside the
    session folder, so a stored path that is absolute or leads out of it
    (``../..``, or a symlink pointing elsewhere) can only come from an edited
    or crafted file, e.g. a received bug-report bundle. It is refused rather
    than read (#11).
    """
    if not stored:
        return directory / default_name
    candidate = Path(stored)
    if candidate.is_absolute() or candidate.drive or candidate.root:
        raise SessionError(
            _(
                "session.json names {name} at an absolute path ({path}); "
                "session files must stay inside the session folder"
            ).format(name=default_name, path=stored)
        )
    base = directory.resolve()
    resolved = (base / candidate).resolve()
    if resolved != base and base not in resolved.parents:
        raise SessionError(
            _(
                "session.json names {name} outside the session folder ({path}); "
                "session files must stay inside the session folder"
            ).format(name=default_name, path=stored)
        )
    return resolved


def save_comparison(path: str | Path, comparison: object) -> Path:
    """Write ``comparison.json`` to ``path`` (a file or a directory)."""
    from reverbscope.models.comparison import ComparisonResult

    if not isinstance(comparison, ComparisonResult):
        raise SessionError(_("save_comparison expects a ComparisonResult"))
    target = Path(path)
    if target.suffix.lower() != ".json":
        target = target / COMPARISON_FILE
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        target.write_text(json.dumps(comparison.to_dict(), indent=1), encoding="utf-8")
    except (OSError, TypeError, ValueError) as exc:
        raise SessionError(
            _("cannot write {path}: {error}").format(path=target, error=exc)
        ) from exc
    return target


def load_comparison(path: str | Path) -> ComparisonResult:
    """Read ``comparison.json``. Findings are not stored; re-derive them on load."""
    from reverbscope.models.comparison import ComparisonResult

    target = Path(path)
    if target.is_dir():
        target = target / COMPARISON_FILE
    if not target.is_file():
        raise SessionError(_("comparison file not found: {path}").format(path=target))
    return ComparisonResult.from_dict(_read_json(target, kind="comparison"))
