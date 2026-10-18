"""CSV exporter for every curve and table in an :class:`AnalysisResult` (S4)."""

from __future__ import annotations

import csv
import logging
import os
from pathlib import Path

from reverbscope.errors import SessionError
from reverbscope.i18n import _
from reverbscope.io.jsonutil import (
    discard,
    keep_beside,
    keep_mode,
    make_folder,
    temporary_beside,
)
from reverbscope.models.result import AnalysisResult, BandDecay

log = logging.getLogger(__name__)


class CsvExporter:
    name = "csv"

    def export(self, result: AnalysisResult, directory: Path) -> list[Path]:
        base = Path(directory)
        make_folder(base)
        writers = {
            "decay_metrics.csv": _write_decay_metrics,
            "energy_metrics.csv": _write_energy_metrics,
            "decay_edc.csv": _write_decay_edc,
            "frequency_response.csv": _write_frequency_response,
            "interface_response.csv": _write_interface_response,
            "noise_psd.csv": _write_noise_psd,
            "reflections.csv": _write_reflections,
            "resonances.csv": _write_resonances,
        }
        # (temporary, final). A missing curve is ``None``: the file of that
        # name from an earlier export would otherwise read as this one's.
        # Nothing in the folder changes until every curve has been written.
        staged: list[tuple[Path | None, Path]] = []
        try:
            for name, write in writers.items():
                final = base / name
                staged.append((write(final, result), final))
            _publish(staged)
        except BaseException:
            for temporary, _final in staged:
                if temporary is not None:
                    discard(temporary)
            raise
        return [final for temporary, final in staged if temporary is not None]


def export_csv(result: AnalysisResult, directory: str | Path) -> list[Path]:
    return CsvExporter().export(result, Path(directory))


def _write(path: Path, header: list[str], rows: list[list[object]]) -> Path:
    """Write ``rows`` beside ``path`` and return that temporary file.

    The caller replaces ``path`` only after every curve has been written, so a
    full disk part-way through leaves the previous export whole.
    """
    try:
        temporary = temporary_beside(path, ".csv")
    except OSError as exc:
        raise SessionError(_("cannot write {path}: {error}").format(path=path, error=exc)) from exc
    try:
        with temporary.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(header)
            writer.writerows(rows)
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as exc:
        discard(temporary)
        raise SessionError(_("cannot write {path}: {error}").format(path=path, error=exc)) from exc
    except BaseException:
        discard(temporary)
        raise
    return temporary


def _publish(staged: list[tuple[Path | None, Path]]) -> None:
    """Put ``staged`` in place, or put back whatever this call already replaced.

    ``None`` means the curve is absent: that file, from an earlier export, is
    removed. A file this export did not mean to touch is left alone.
    """
    # (final, previous contents or None, True when this call created final)
    backups: list[tuple[Path, Path | None, bool]] = []
    try:
        for temporary, final in staged:
            if temporary is None:
                if final.is_file():
                    backups.append((final, keep_beside(final, ".csv"), False))
                    _remove(final)
                continue
            existed = final.is_file()
            backups.append((final, keep_beside(final, ".csv") if existed else None, not existed))
            if existed:
                keep_mode(temporary, final)
            os.replace(temporary, final)
    except (OSError, SessionError) as exc:
        _restore(backups)
        if isinstance(exc, SessionError):
            raise
        where = exc.filename
        if isinstance(where, bytes):
            where = os.fsdecode(where)
        raise SessionError(
            _("cannot write {path}: {error}").format(path=where or "", error=exc)
        ) from exc
    else:
        # The previous curves survived in these names. Drop them only after
        # every replacement has landed; a restore that itself fails must keep
        # the copy, which is then the only whole version left.
        for _final, backup, _created in backups:
            if backup is not None:
                discard(backup)
    finally:
        for temporary, _final in staged:
            if temporary is not None:
                discard(temporary)


def _restore(backups: list[tuple[Path, Path | None, bool]]) -> None:
    for final, backup, created in reversed(backups):
        try:
            if backup is not None:
                os.replace(backup, final)
                # A hard link of a file this call never replaced names the same
                # inode, so replace leaves the second name in place.
                discard(backup)
            elif created:
                final.unlink(missing_ok=True)
        except OSError:
            # The copy stays beside the folder. Removing it would leave no
            # whole version of that curve.
            log.warning("cannot restore %s after a failed export", final)


def _remove(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError as exc:
        raise SessionError(_("cannot write {path}: {error}").format(path=path, error=exc)) from exc


def _metric_row(
    band: BandDecay, name: str, seconds: float | None, validity: object
) -> list[object]:
    return [band.band_label, name, seconds if seconds is not None else "", str(validity)]


def _write_decay_metrics(path: Path, result: AnalysisResult) -> Path:
    rows: list[list[object]] = []
    for band in (result.decay.broadband, *result.decay.bands):
        rows.append(_metric_row(band, "EDT", band.edt.seconds, band.edt.validity))
        rows.append(_metric_row(band, "T20", band.t20.seconds, band.t20.validity))
        rows.append(_metric_row(band, "T30", band.t30.seconds, band.t30.validity))
        rows.append(
            [
                band.band_label,
                "RT60_estimate",
                band.rt60_estimate_s if band.rt60_estimate_s is not None else "",
                band.rt60_basis or "",
            ]
        )
    return _write(path, ["band", "metric", "seconds", "validity_or_basis"], rows)


def _write_energy_metrics(path: Path, result: AnalysisResult) -> Path:
    rows: list[list[object]] = []
    for band in (result.decay.broadband, *result.decay.bands):
        for metric in (band.c50, band.c80, band.d50, band.centre_time):
            rows.append(
                [
                    band.band_label,
                    metric.name,
                    "" if metric.value is None else metric.value,
                    metric.unit,
                    str(metric.validity),
                ]
            )
    return _write(path, ["band", "metric", "value", "unit", "validity"], rows)


def _write_decay_edc(path: Path, result: AnalysisResult) -> Path | None:
    rows: list[list[object]] = []
    for band in (result.decay.broadband, *result.decay.bands):
        if band.edc_time_s.size == 0:
            continue
        for time_s, level_db in zip(band.edc_time_s, band.edc_db, strict=False):
            rows.append([band.band_label, float(time_s), float(level_db)])
    if not rows:
        return None
    return _write(path, ["band", "time_s", "edc_db"], rows)


def _write_frequency_response(path: Path, result: AnalysisResult) -> Path | None:
    fr = result.frequency_response
    if fr.frequencies_hz.size == 0:
        return None
    smoothed = fr.magnitude_db_smoothed
    rows: list[list[object]] = []
    for index, freq in enumerate(fr.frequencies_hz):
        raw = float(fr.magnitude_db_raw[index]) if index < fr.magnitude_db_raw.size else ""
        sm = float(smoothed[index]) if smoothed is not None and index < smoothed.size else ""
        rows.append([float(freq), raw, sm])
    return _write(path, ["frequency_hz", "magnitude_db_raw", "magnitude_db_smoothed"], rows)


def _write_interface_response(path: Path, result: AnalysisResult) -> Path | None:
    """The interface response measured on the loopback (when one was used)."""
    loopback = result.impulse_response.loopback
    if (
        loopback is None
        or loopback.interface_response_hz is None
        or loopback.interface_response_db is None
        or loopback.interface_response_hz.size == 0
    ):
        return None
    rows: list[list[object]] = [
        [float(freq), float(level)]
        for freq, level in zip(
            loopback.interface_response_hz, loopback.interface_response_db, strict=False
        )
    ]
    return _write(path, ["frequency_hz", "magnitude_db"], rows)


def _write_noise_psd(path: Path, result: AnalysisResult) -> Path | None:
    noise = result.noise
    if noise.psd_frequencies_hz is None or noise.psd_db is None:
        return None
    rows: list[list[object]] = [
        [float(freq), float(level)]
        for freq, level in zip(noise.psd_frequencies_hz, noise.psd_db, strict=False)
    ]
    return _write(path, ["frequency_hz", "psd_db"], rows)


def _write_reflections(path: Path, result: AnalysisResult) -> Path:
    rows: list[list[object]] = [[r.delay_ms, r.relative_db] for r in result.reflections.reflections]
    return _write(path, ["delay_ms", "relative_db"], rows)


def _write_resonances(path: Path, result: AnalysisResult) -> Path:
    rows: list[list[object]] = [
        [
            c.frequency_hz,
            c.level_above_baseline_db,
            c.narrowband_decay_20db_s if c.narrowband_decay_20db_s is not None else "",
            c.decay_distinguishable,
            # Added after decay_distinguishable so existing columns keep their place.
            c.filter_ringing_20db_s if c.filter_ringing_20db_s is not None else "",
            c.surroundings_decay_20db_s if c.surroundings_decay_20db_s is not None else "",
        ]
        for c in result.resonances.candidates
    ]
    return _write(
        path,
        [
            "frequency_hz",
            "level_above_baseline_db",
            "narrowband_decay_20db_s",
            "decay_distinguishable",
            "filter_ringing_20db_s",
            "surroundings_decay_20db_s",
        ],
        rows,
    )
