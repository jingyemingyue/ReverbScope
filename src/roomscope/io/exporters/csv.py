"""CSV exporter for every curve and table in an :class:`AnalysisResult` (S4)."""

from __future__ import annotations

import csv
from pathlib import Path

from roomscope.errors import SessionError
from roomscope.i18n import _
from roomscope.models.result import AnalysisResult, BandDecay


class CsvExporter:
    name = "csv"

    def export(self, result: AnalysisResult, directory: Path) -> list[Path]:
        base = Path(directory)
        base.mkdir(parents=True, exist_ok=True)
        written = [
            _write_decay_metrics(base / "decay_metrics.csv", result),
            _write_energy_metrics(base / "energy_metrics.csv", result),
            _write_decay_edc(base / "decay_edc.csv", result),
            _write_frequency_response(base / "frequency_response.csv", result),
            _write_spectrum(base / "spectrum.csv", result),
            _write_noise_psd(base / "noise_psd.csv", result),
            _write_reflections(base / "reflections.csv", result),
            _write_resonances(base / "resonances.csv", result),
        ]
        return [path for path in written if path is not None]


def export_csv(result: AnalysisResult, directory: str | Path) -> list[Path]:
    return CsvExporter().export(result, Path(directory))


def _write(path: Path, header: list[str], rows: list[list[object]]) -> Path:
    try:
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(header)
            writer.writerows(rows)
    except OSError as exc:
        raise SessionError(_("cannot write {path}: {error}").format(path=path, error=exc)) from exc
    return path


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


def _write_spectrum(path: Path, result: AnalysisResult) -> Path | None:
    spectrum = result.spectrum
    if spectrum is None or spectrum.frequencies_hz.size == 0:
        return None
    rows: list[list[object]] = [
        [float(freq), float(level)]
        for freq, level in zip(spectrum.frequencies_hz, spectrum.level_db, strict=False)
    ]
    return _write(path, ["frequency_hz", "level_db"], rows)


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
        ],
        rows,
    )
