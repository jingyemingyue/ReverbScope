"""Write a common-slope analysis: ``common-slope.json`` and two CSV tables.

* ``common-slope.json``: :meth:`CommonSlopeResult.to_dict`, valid against
  ``reverbscope schema common-slope``.
* ``common-slope-bands.csv``: one row per band (selected slope count, common
  decay times, BIC differences, supporting positions, RMS errors).
* ``common-slope-positions.csv``: one row per band, position and slope
  (amplitude in dB, noise, RMS error of the common model and of the
  per-response fit).

Numbers are written with ``repr`` precision; an absent value is an empty cell.
"""

from __future__ import annotations

import csv
import io
import json
import statistics
from pathlib import Path

from reverbscope.core.common_slope import MAX_COMMON_SLOPES, CommonSlopeResult
from reverbscope.io.jsonutil import write_text_atomic

COMMON_SLOPE_FILE = "common-slope.json"
BANDS_CSV = "common-slope-bands.csv"
POSITIONS_CSV = "common-slope-positions.csv"

BAND_COLUMNS = (
    "band",
    "center_hz",
    "fraction",
    "validity",
    "selected_slopes",
    *(f"t{k}_s" for k in range(1, MAX_COMMON_SLOPES + 1)),
    *(f"edc_t{k}_s" for k in range(1, MAX_COMMON_SLOPES + 1)),
    "delta_bic",
    "supporting_positions",
    "positions",
    "excluded_positions",
    "median_rms_common_db",
    "median_rms_single_db",
    "estimator",
    "amplitude_method",
    "reason",
    "notes",
)
POSITION_COLUMNS = (
    "band",
    "center_hz",
    "position",
    "slope",
    "t_s",
    "amplitude",
    "amplitude_db",
    "noise_term",
    "noise_db",
    "rms_common_db",
    "single_slopes",
    "single_decay_times_s",
    "rms_single_db",
)


def _cell(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, tuple | list):
        return " ".join(_cell(v) for v in value)
    return str(value)


def _median(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


def bands_csv(result: CommonSlopeResult) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(BAND_COLUMNS)
    for band in result.bands:
        times = list(band.decay_times_s) + [None] * (MAX_COMMON_SLOPES - len(band.decay_times_s))
        edc = list(band.edc_decay_times_s) + [None] * (
            MAX_COMMON_SLOPES - len(band.edc_decay_times_s)
        )
        singles = [
            p.single_rms_residual_db for p in band.positions if p.single_rms_residual_db is not None
        ]
        writer.writerow(
            [
                _cell(v)
                for v in (
                    band.band_label,
                    band.center_hz,
                    band.fraction,
                    str(band.validity),
                    band.selected_slopes,
                    *times,
                    *edc,
                    band.delta_bic,
                    band.supporting_positions,
                    len(band.positions),
                    len(band.excluded),
                    _median([p.rms_residual_db for p in band.positions]),
                    _median(singles),
                    result.estimator,
                    result.amplitude_method,
                    band.reason,
                    "; ".join(band.notes),
                )
            ]
        )
    return buffer.getvalue()


def positions_csv(result: CommonSlopeResult) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(POSITION_COLUMNS)
    for band in result.bands:
        for position in band.positions:
            for k, decay in enumerate(band.decay_times_s):
                writer.writerow(
                    [
                        _cell(v)
                        for v in (
                            band.band_label,
                            band.center_hz,
                            position.position,
                            k + 1,
                            decay,
                            position.amplitudes[k],
                            position.amplitudes_db[k],
                            position.noise_term,
                            position.noise_db,
                            position.rms_residual_db,
                            position.single_slopes,
                            position.single_decay_times_s,
                            position.single_rms_residual_db,
                        )
                    ]
                )
    return buffer.getvalue()


def save_common_slope(directory: str | Path, result: CommonSlopeResult) -> list[Path]:
    """Write the three files into ``directory`` (created); returns their paths."""
    base = Path(directory)
    base.mkdir(parents=True, exist_ok=True)
    written = []
    for name, text in (
        (COMMON_SLOPE_FILE, json.dumps(result.to_dict(), indent=1, allow_nan=False) + "\n"),
        (BANDS_CSV, bands_csv(result)),
        (POSITIONS_CSV, positions_csv(result)),
    ):
        path = base / name
        write_text_atomic(path, text)
        written.append(path)
    return written
