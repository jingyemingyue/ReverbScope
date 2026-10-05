"""Saving and loading measurement sessions.

A session directory contains::

    session.json            metadata + analysis summary (MeasurementSession)
    result.json             full AnalysisResult (metrics and curves)
    impulse_response.wav    raw impulse response, 32-bit float
    sweep.reverbscope-sweep.json   always copied when a sidecar is available
    recording.wav           copied when copy_recording is on (GUI default);
                            an AIFF, CAF or FLAC take is converted to WAV

Raw sweep and recording files are never modified in place.
"""

from __future__ import annotations

import json
import logging
import math
import os
import shutil
import stat
import zipfile
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from reverbscope.models.comparison import ComparisonResult

from reverbscope.errors import ReverbScopeError, SessionError
from reverbscope.i18n import _
from reverbscope.io.jsonutil import (
    MAX_JSON_BYTES,
    MAX_RESULT_JSON_BYTES,
    discard,
    keep_beside,
    keep_mode,
    temporary_beside,
    write_text_atomic,
)
from reverbscope.io.wav import _soundfile, read_wav, write_wav
from reverbscope.models.audio import AudioSignal
from reverbscope.models.result import AnalysisResult, Validity
from reverbscope.models.session import MeasurementSession

log = logging.getLogger(__name__)

SESSION_FILE = "session.json"
RESULT_FILE = "result.json"
COMPARISON_FILE = "comparison.json"
IR_FILE = "impulse_response.wav"
RECORDING_FILE = "recording.wav"
SWEEP_SIDECAR_NAME = "sweep.reverbscope-sweep.json"
#: Left out of a ``--no-audio`` bundle: every container a DAW export or a
#: recorder may have put into the folder.
AUDIO_SUFFIXES = {".wav", ".flac", ".aiff", ".aif", ".aifc", ".caf", ".ogg", ".w64", ".rf64"}


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
    recording: AudioSignal | None = None,
) -> Path:
    """Write session.json, result.json and impulse_response.wav into ``directory``.

    The sweep sidecar is always copied when one can be found. The raw recording
    is copied when ``copy_recording`` is true, or when it is omitted and the
    user settings default to copying (the GUI default). ``recording`` is a take
    that has no file yet (a live GUI take): it is written as recording.wav.

    Nothing in ``directory`` is replaced until every file has been written,
    and a rename that fails puts back the members already replaced, so a
    failed save keeps the session that was there whole.
    """
    base = Path(directory)
    base.mkdir(parents=True, exist_ok=True)
    if copy_recording is None:
        from reverbscope.settings import load_settings

        copy_recording = load_settings().copy_recording
    # The paths below are rewritten relative to ``base``. Rewrite a copy: the
    # caller's session keeps paths that still resolve, so saving it again into
    # another folder (the GUI's Save button, twice) still finds the recording.
    session = replace(session)
    original_sweep = session.sweep_path
    original_recording = session.recording_path
    # Every member is written under a temporary name first and only renamed
    # into place once all of them have been written: a full disk half-way
    # through keeps the previous take whole instead of mixing two takes.
    staged: list[tuple[Path, Path]] = []

    def stage(name: str) -> Path:
        final = base / name
        # A fresh name, created here: a link planted under a guessable name
        # in a folder from someone else is never written through. The real
        # suffix stays last: soundfile picks the format from it.
        try:
            temporary = temporary_beside(final, f".saving{final.suffix}")
        except OSError as exc:
            raise SessionError(
                _("cannot write {path}: {error}").format(path=final, error=exc)
            ) from exc
        staged.append((temporary, final))
        return temporary

    ir_path = base / IR_FILE
    result_path = base / RESULT_FILE
    session_path = base / SESSION_FILE
    try:
        if recording is not None:
            write_wav(
                stage(RECORDING_FILE), recording.samples, recording.sample_rate, subtype="FLOAT"
            )
            session.recording_path = str(base / RECORDING_FILE)
        write_wav(
            stage(IR_FILE), result.impulse_response.samples, result.sample_rate, subtype="FLOAT"
        )
        _write_staged_text(
            stage(RESULT_FILE), result_path, json.dumps(result.to_dict(include_curves), indent=1)
        )
        _copy_sidecar(original_sweep, base, stage=stage)
        if copy_recording and recording is None:
            copied = _copy_recording(original_recording, base, stage=stage)
            if copied is not None:
                session.recording_path = str(copied)
        session.sample_rate = result.sample_rate
        session.impulse_response_path = _relative(ir_path, base)
        session.result_path = _relative(result_path, base)
        session.sweep_path = _relative(session.sweep_path, base)
        session.recording_path = _relative(session.recording_path, base)
        session.analysis_summary = result_summary(result)
        # session.json is renamed last, after the files it describes.
        _write_staged_text(
            stage(SESSION_FILE), session_path, json.dumps(session.to_dict(), indent=2)
        )
        _replace_members(staged)
    finally:
        for temporary, _final in staged:
            discard(temporary)
    return session_path


def _replace_members(staged: list[tuple[Path, Path]]) -> None:
    """Rename every staged member into place, or leave every member as it was.

    Each member a save replaces is kept under a second name until all the
    renames have succeeded. When one fails (Windows refuses to replace a file
    another program has open), the members already replaced are put back, so
    the folder never holds one take's recording beside another's analysis.
    """
    replaced: list[tuple[Path, Path | None]] = []
    kept: list[Path] = []
    try:
        for temporary, final in staged:
            try:
                previous = _keep_previous(final)
                if previous is not None:
                    kept.append(previous)
                keep_mode(temporary, final)
                os.replace(temporary, final)
            except OSError as exc:
                for done, earlier in reversed(replaced):
                    if not _put_back(done, earlier) and earlier is not None:
                        kept.remove(earlier)  # its only copy now: never deleted
                raise SessionError(
                    _("cannot write {path}: {error}").format(path=final, error=exc)
                ) from exc
            replaced.append((final, previous))
    finally:
        for name in kept:
            discard(name)


def _keep_previous(final: Path) -> Path | None:
    """The member at ``final`` under a second name; None when there is none.

    A link planted under a member's name is replaced like any file, but never
    kept: it is not part of a take.
    """
    try:
        status = os.lstat(final)
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(status.st_mode):
        return None
    return keep_beside(final, f".previous{final.suffix}")


def _put_back(final: Path, previous: Path | None) -> bool:
    """Undo one rename of a failed save: the previous member, or none."""
    try:
        if previous is None:
            final.unlink(missing_ok=True)
        else:
            os.replace(previous, final)
    except OSError as exc:
        log.warning("cannot restore %s after a failed save: %s", final, exc)
        return False
    return True


def _write_staged_text(temporary: Path, final: Path, text: str) -> None:
    try:
        with temporary.open("w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
    except (OSError, TypeError, ValueError) as exc:
        raise SessionError(_("cannot write {path}: {error}").format(path=final, error=exc)) from exc


def bundle_session(
    directory: str | Path,
    dest: str | Path | None = None,
    *,
    include_audio: bool = True,
) -> Path:
    """Zip a session folder for a bug report. ``include_audio=False`` drops WAVs.

    Paths under the home folder in its JSON files are written as ``~/…``.
    """
    session_file = _session_file(directory)
    # Absolute, so that "." (bundling the folder you are in) has a name; not
    # resolved, so that a linked folder keeps its own name for the zip.
    base = Path(os.path.abspath(session_file.parent))
    # A folder at a drive or volume root (a recorder's USB stick) has no name.
    name = base.name or "session"
    target = Path(dest) if dest is not None else base.parent / f"{name}.zip"
    # Like ``compare --out``: anything that is not a .zip file is a folder,
    # also when it does not exist yet ("--out bundles/" loses its slash).
    if target.is_dir() or target.suffix.lower() != ".zip":
        target = target / f"{name}.zip"
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
    inside = base.resolve()
    temporary: Path | None = None
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        # Written beside the target and renamed over it once complete: a
        # failure half-way (a full disk) keeps an earlier bundle there whole.
        temporary = temporary_beside(target, ".zip")
        # strict_timestamps=False: a file dated before 1980 (a recorder whose
        # clock was never set) is stored as 1980 instead of failing the zip.
        with zipfile.ZipFile(
            temporary, "w", zipfile.ZIP_DEFLATED, strict_timestamps=False
        ) as archive:
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
                name = path.relative_to(base).as_posix()
                redacted = _without_home(path)
                if redacted is None:
                    archive.write(path, name)
                else:
                    info = zipfile.ZipInfo.from_file(path, name, strict_timestamps=False)
                    archive.writestr(info, redacted, compress_type=zipfile.ZIP_DEFLATED)
        os.replace(temporary, target)
    except (OSError, ValueError) as exc:
        raise SessionError(
            _("cannot write bundle {path}: {error}").format(path=target, error=exc)
        ) from exc
    finally:
        if temporary is not None:
            discard(temporary)
    return target


def _without_home(path: Path) -> bytes | None:
    """A JSON member as it goes into a bundle, or None to bundle it unchanged.

    session.json keeps the absolute path of a sweep or recording outside the
    folder, and comparison.json the session paths as typed: the user's home
    folder there would publish the account name with a bug report. It is
    shown as ``~``, as in the doctor report. result.json names no files.
    """
    if path.suffix.lower() != ".json" or path.name == RESULT_FILE:
        return None
    try:
        data = _read_json(path, kind="JSON")
    except SessionError:
        return None  # not ReverbScope's JSON: bundled as it is
    shown = _redact_strings(data)
    if shown == data:
        return None
    return (json.dumps(shown, indent=2) + "\n").encode("utf-8")


def _redact_strings(value: Any) -> Any:
    from reverbscope.diagnostics import redact_home

    if isinstance(value, str):
        return redact_home(value)
    if isinstance(value, list):
        return [_redact_strings(item) for item in value]
    if isinstance(value, dict):
        return {key: _redact_strings(item) for key, item in value.items()}
    return value


def _copy_into(src: Path, dest: Path, *, stage: Callable[[str], Path] | None = None) -> Path | None:
    if not src.is_file():
        return None
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        # samefile also matches on case-insensitive file systems (macOS, Windows)
        # where Recording.wav and recording.wav are one file.
        if dest.exists() and os.path.samefile(src, dest):
            return dest
        shutil.copy2(src, dest if stage is None else stage(dest.name))
    except OSError as exc:
        raise SessionError(
            _("cannot copy {source} to {target}: {error}").format(
                source=src, target=dest, error=exc
            )
        ) from exc
    return dest


def _sidecar_source(sweep_path: str | Path) -> Path | None:
    """The sweep sidecar that belongs to ``sweep_path`` (a sidecar or a sweep WAV)."""
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
            return candidate
    return None


def _copy_sidecar(
    sweep_path: str | None, base: Path, *, stage: Callable[[str], Path] | None = None
) -> Path | None:
    if not sweep_path:
        return None
    source = _sidecar_source(sweep_path)
    if source is None:
        return None
    return _copy_into(source, base / SWEEP_SIDECAR_NAME, stage=stage)


def _copy_recording(
    recording_path: str | None, base: Path, *, stage: Callable[[str], Path] | None = None
) -> Path | None:
    if not recording_path:
        return None
    src = Path(recording_path)
    if not src.is_file() and not src.is_absolute():
        src = base / src
    dest = base / RECORDING_FILE
    subtype = _wav_subtype(src)
    if subtype is None:
        return _copy_into(src, dest, stage=stage)
    # An AIFF, CAF or FLAC export copied byte for byte under the name
    # recording.wav is a "corrupt WAV" to every program that goes by the
    # name; it is converted, with a sample format that keeps every sample.
    signal = read_wav(src)
    write_wav(
        dest if stage is None else stage(dest.name),
        signal.samples,
        signal.sample_rate,
        subtype=subtype,
    )
    return dest


def _wav_subtype(src: Path) -> str | None:
    """None when ``src`` is a WAV file (or cannot be inspected): it is copied
    as it is. Otherwise the WAV sample format that holds its samples exactly."""
    if not src.is_file():
        return None
    sf = _soundfile()
    try:
        info = sf.info(str(src))
    except Exception:  # libsndfile raises RuntimeError / soundfile.LibsndfileError
        return None
    if info.format in ("WAV", "WAVEX"):
        return None
    return info.subtype if sf.check_format("WAV", info.subtype) else "FLOAT"


def load_session(path: str | Path) -> MeasurementSession:
    """Load a session from ``session.json`` or from its directory."""
    return MeasurementSession.from_dict(_read_json(_session_file(path)))


def load_result(path: str | Path) -> AnalysisResult:
    """Load an :class:`AnalysisResult` from ``result.json``."""
    # Every frequency-response bin is stored: a 192 kHz take is larger than
    # the cap on the other JSON files.
    return AnalysisResult.from_dict(
        _read_json(Path(path), kind="result", max_bytes=MAX_RESULT_JSON_BYTES)
    )


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
        rt60 = _finite(self.session.analysis_summary.get("broadband_rt60_estimate_s"))
        rt60_text = (
            _("RT60 {seconds:.2f} s").format(seconds=rt60) if rt60 is not None else _("RT60 n/a")
        )
        return f"{room}  ·  {created}  ·  {rt60_text}"


def _finite(value: object) -> float | None:
    """A number from session.json, or None (a crafted 400-digit integer too)."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    try:
        number = float(value)
    except OverflowError:
        return None
    return number if math.isfinite(number) else None


def load_measurement(path: str | Path) -> LoadedMeasurement:
    """Load session metadata, ``result.json`` and the IR WAV from a directory."""
    session_file = _session_file(path)
    directory = session_file.parent
    session = MeasurementSession.from_dict(_read_json(session_file))
    _anchor_copied_files(session, directory)
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


def _anchor_copied_files(session: MeasurementSession, directory: Path) -> None:
    """Point the sweep and recording paths of an opened session into its folder.

    Saving the opened session into another folder (the GUI's Save button)
    copies the sweep sidecar and the recording named here. Only files inside
    the session folder are kept: a session from someone else must not make
    ReverbScope copy one of your files (``../../.ssh/id_rsa``, or an absolute
    path) into a new session, and from there into a bug-report bundle. A path
    outside, such as the working sweep WAV, is dropped, and the folder's own
    copy of the sweep sidecar takes its place.
    """
    recording = _inside(directory, session.recording_path)
    session.recording_path = None if recording is None else str(recording)
    sweep = _inside(directory, session.sweep_path)
    sidecar = None if sweep is None else _sidecar_source(sweep)
    if sidecar is not None and not _contains(directory.resolve(), sidecar.resolve()):
        # A link next to the sweep that leads out of the folder.
        sweep = sidecar = None
    if sidecar is None:
        own = _inside(directory, SWEEP_SIDECAR_NAME)
        if own is not None and own.is_file():
            sweep = own
    session.sweep_path = None if sweep is None else str(sweep)


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
        except ReverbScopeError:
            # Unreadable, or settings this version refuses (ConfigurationError):
            # one bad folder must not hide the others.
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


def _read_json(
    path: Path, *, kind: str = "session", max_bytes: int = MAX_JSON_BYTES
) -> dict[str, Any]:
    from reverbscope.io.jsonutil import read_json_object

    return read_json_object(path, kind=kind, max_bytes=max_bytes)


def _resolve_member(directory: Path, stored: str | None, default_name: str) -> Path:
    """Resolve a file named in ``session.json`` inside the session directory.

    ``result.json`` and ``impulse_response.wav`` are always written inside the
    session folder, so a stored path that is absolute or leads out of it
    (``../..``, or a symlink pointing elsewhere) can only come from an edited
    or crafted file, e.g. a received bug-report bundle. It is refused rather
    than read (#11).
    """
    # The default name is checked too: it can itself be a link out of the folder.
    candidate = Path(stored or default_name)
    if candidate.is_absolute() or candidate.drive or candidate.root:
        raise SessionError(
            _(
                "session.json names {name} at an absolute path ({path}); "
                "session files must stay inside the session folder"
            ).format(name=default_name, path=candidate)
        )
    resolved = _inside(directory, candidate)
    if resolved is None:
        raise SessionError(
            _(
                "session.json names {name} outside the session folder ({path}); "
                "session files must stay inside the session folder"
            ).format(name=default_name, path=candidate)
        )
    return resolved


def _inside(directory: Path, stored: str | Path | None) -> Path | None:
    """``stored`` resolved inside ``directory``, or None when it is not there.

    The rule of :func:`_resolve_member` without the error: an absolute path,
    one that leads out of the folder (``..``, or a link to elsewhere), or
    one that cannot be resolved (a NUL byte, a link loop) gives None.
    """
    if not stored:
        return None
    candidate = Path(stored)
    if candidate.is_absolute() or candidate.drive or candidate.root:
        return None
    base = directory.resolve()
    try:
        resolved = (base / candidate).resolve()
    except (OSError, RuntimeError, ValueError):
        return None
    return resolved if _contains(base, resolved) else None


def _contains(base: Path, resolved: Path) -> bool:
    return resolved == base or base in resolved.parents


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
        write_text_atomic(target, json.dumps(comparison.to_dict(), indent=1))
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
