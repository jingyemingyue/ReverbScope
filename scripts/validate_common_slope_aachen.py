"""Validate the common-slope analysis on the open Aachen St. Nicholas Chapel data.

Data: M. Zerwas and S. Kayku, Zenodo, https://doi.org/10.5281/zenodo.20428705,
CC-BY 4.0 (see ``scripts/validate_aachen_nikolauskapelle.py`` for the files and
how to unpack them). The data are *not* part of this repository::

    python scripts/validate_common_slope_aachen.py --data ~/aachen \\
        --out docs/validation/aachen-nikolauskapelle-common-slope.csv

The W channel of every dodecahedron response (46 files, three sources) is one
position of :func:`reverbscope.core.common_slope.analyze_common_slopes`, with
the strongest sample as the direct sound (the import path's time zero) and the
declared excitation band 20 Hz-20 kHz, in octave bands 63 Hz-8 kHz, once with
the EDC estimator (LINEX amplitudes) and once with the experimental IS-NMF /
SAGE estimator. For comparison it prints, per band: the per-response fits
(selected slope counts, median single-slope T, median two-slope T1/T2),
DecayFitNet's per-position T1/T2 (63-500 Hz) and their k-means clusters (the
original common-slope procedure of Götz et al. 2023), the RMS dB error of the
common model and of the per-response fits against each EDC, and the run time.
Writes one CSV row per band and estimator (``--out``) and one per position,
band and slope (``--positions``).
"""

from __future__ import annotations

import argparse
import csv
import statistics
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from validate_aachen_nikolauskapelle import (
    DFN_BANDS_HZ,
    EXCITATION_HZ,
    OCTAVES_HZ,
    _w_channel,
    read_decayfitnet,
)

from reverbscope.core.common_slope import (
    ESTIMATOR_EDC,
    ESTIMATOR_SAGE,
    BandObservation,
    ExcludedPosition,
    ResponseInput,
    fit_common_slopes,
    kmeans_log,
    observe_response,
)
from reverbscope.models.configuration import AnalysisSettings
from reverbscope.models.result import EXCITATION_SOURCE_DECLARED, ExcitationBand

ATTRIBUTION = (
    "# Derived from Zerwas & Kayku, St. Nicholas Chapel Aachen, "
    "doi:10.5281/zenodo.20428705, CC-BY 4.0"
)


def _median(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


def _fmt(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.3f}"
    if isinstance(value, tuple | list):
        return "/".join(_fmt(v) for v in value)
    return str(value)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=None, help="per-band CSV")
    parser.add_argument("--positions", type=Path, default=None, help="per-position CSV")
    args = parser.parse_args(argv)

    dfn = read_decayfitnet(args.data / "decayfitnet_all_positions.csv")
    wavs = sorted((args.data / "irs").glob("Nikolauskapelle_Source*_BRIR/*.wav"))
    if not wavs:
        wavs = sorted(args.data.glob("Nikolauskapelle_Source*_BRIR/*.wav"))
    settings = AnalysisSettings(octave_bands_hz=OCTAVES_HZ)
    excitation = ExcitationBand(*EXCITATION_HZ, source=EXCITATION_SOURCE_DECLARED)

    started = time.perf_counter()
    per_band: dict[float, tuple[list[BandObservation], list[ExcludedPosition]]] = {
        f: ([], []) for f in OCTAVES_HZ
    }
    for wav in wavs:
        w, rate = _w_channel(wav)
        response = ResponseInput(wav.stem, w, rate, int(np.argmax(np.abs(w))), excitation)
        for nominal, item in zip(OCTAVES_HZ, observe_response(response, settings), strict=True):
            if isinstance(item, BandObservation):
                per_band[nominal][0].append(item)
            elif isinstance(item, ExcludedPosition):
                per_band[nominal][1].append(item)
    observe_s = time.perf_counter() - started
    print(f"{len(wavs)} responses observed in {observe_s:.1f} s")

    band_rows: list[dict[str, object]] = []
    position_rows: list[dict[str, object]] = []
    print(
        "| Band | positions | per-response 1/2 slopes | median T (1 slope) | "
        "median T1/T2 (2-slope fits) | DFN median T1/T2 | DFN k-means T1/T2 | "
        "common T (EDC) | K | ΔBIC | support | common T (SAGE) | RMS common / per-response "
        "(dB, median) | fit time EDC / SAGE (s) |"
    )
    print("|" + "---|" * 14)
    for nominal in OCTAVES_HZ:
        observations, excluded = per_band[nominal]
        band = observations[0] if observations else None
        label = band.band_label if band else f"{nominal:g} Hz"
        results = {}
        for estimator in (ESTIMATOR_EDC, ESTIMATOR_SAGE):
            results[estimator] = fit_common_slopes(
                observations,
                band_label=label,
                center_hz=nominal,
                bandwidth_hz=band.bandwidth_hz if band else 0.0,
                excluded=excluded,
                estimator=estimator,
            )
        edc, sage = results[ESTIMATOR_EDC], results[ESTIMATOR_SAGE]
        singles = [o.single_slopes for o in observations]
        one_t = [m[0] for o in observations for m in o.candidate_decay_times_s if len(m) == 1]
        two_t1 = [m[0] for o in observations for m in o.candidate_decay_times_s if len(m) == 2]
        two_t2 = [m[1] for o in observations for m in o.candidate_decay_times_s if len(m) == 2]
        dfn_rows = [row for (pos, f), row in dfn.items() if f == nominal]
        dfn_t1 = [row.t1_s for row in dfn_rows]
        dfn_t2 = [row.t2_s for row in dfn_rows]
        dfn_k = kmeans_log(dfn_t1 + dfn_t2, 2) if nominal in DFN_BANDS_HZ and dfn_rows else []
        rms_common = [p.rms_residual_db for p in edc.positions]
        rms_single = [
            p.single_rms_residual_db for p in edc.positions if p.single_rms_residual_db is not None
        ]
        row = {
            "band_hz": nominal,
            "positions": len(observations),
            "excluded": len(excluded),
            "single_1": singles.count(1),
            "single_2": singles.count(2),
            "median_single_t_s": _median(one_t),
            "median_two_t1_s": _median(two_t1),
            "median_two_t2_s": _median(two_t2),
            "dfn_median_t1_s": _median(dfn_t1),
            "dfn_median_t2_s": _median(dfn_t2),
            "dfn_kmeans_t_s": tuple(dfn_k),
            "edc_slopes": edc.selected_slopes,
            "edc_t_s": edc.decay_times_s,
            "edc_validity": str(edc.validity),
            "edc_delta_bic": edc.delta_bic,
            "edc_support": edc.supporting_positions,
            "edc_models_t_s": " | ".join(_fmt(m.decay_times_s) for m in edc.models),
            "edc_models_rms_db": tuple(m.rms_residual_db for m in edc.models),
            "sage_t_s": sage.decay_times_s,
            "median_rms_common_db": _median(rms_common),
            "median_rms_single_db": _median(rms_single),
            "edc_runtime_s": edc.runtime_s,
            "sage_runtime_s": sage.runtime_s,
            "notes": "; ".join(edc.notes),
        }
        band_rows.append(row)
        print(
            f"| {label} | {len(observations)} | {singles.count(1)}/{singles.count(2)} | "
            f"{_fmt(row['median_single_t_s'])} | {_fmt(row['median_two_t1_s'])}/"
            f"{_fmt(row['median_two_t2_s'])} | {_fmt(row['dfn_median_t1_s'])}/"
            f"{_fmt(row['dfn_median_t2_s'])} | {_fmt(row['dfn_kmeans_t_s'])} | "
            f"{_fmt(edc.decay_times_s)} | {edc.selected_slopes} | {_fmt(edc.delta_bic)} | "
            f"{_fmt(edc.supporting_positions)} | {_fmt(sage.decay_times_s)} | "
            f"{_fmt(row['median_rms_common_db'])} / {_fmt(row['median_rms_single_db'])} | "
            f"{edc.runtime_s:.1f} / {sage.runtime_s:.1f} |"
        )
        if edc.notes:
            print(f"|   notes: {'; '.join(edc.notes)} |")
        for p in edc.positions:
            for k, (t_k, a_k) in enumerate(zip(edc.decay_times_s, p.amplitudes_db, strict=True)):
                position_rows.append(
                    {
                        "position": p.position,
                        "band_hz": nominal,
                        "slope": k + 1,
                        "t_s": t_k,
                        "amplitude_db": a_k,
                        "noise_db": p.noise_db,
                        "rms_common_db": p.rms_residual_db,
                        "single_slopes": p.single_slopes,
                        "rms_single_db": p.single_rms_residual_db,
                    }
                )
    # The same analysis per source position: the decay times are a property of
    # the room, so each source's receivers should give about the same.
    print()
    print("| Band | " + " | ".join(f"S{n} common T (K)" for n in (1, 2, 3)) + " |")
    print("|---|---|---|---|")
    for nominal in OCTAVES_HZ:
        observations, _excluded = per_band[nominal]
        cells = []
        for source in ("S1", "S2", "S3"):
            subset = [o for o in observations if o.position.startswith(source + "-")]
            if not subset:
                cells.append("")
                continue
            fit = fit_common_slopes(
                subset,
                band_label=subset[0].band_label,
                center_hz=nominal,
                bandwidth_hz=subset[0].bandwidth_hz,
            )
            cells.append(f"{_fmt(fit.decay_times_s)} ({fit.selected_slopes}, n={len(subset)})")
        print(f"| {nominal:g} Hz | " + " | ".join(cells) + " |")
    total = time.perf_counter() - started
    print(f"total {total:.1f} s (observations {observe_s:.1f} s)")
    for path, rows in ((args.out, band_rows), (args.positions, position_rows)):
        if path is None or not rows:
            continue
        with path.open("w", newline="", encoding="utf-8") as handle:
            handle.write(ATTRIBUTION + "\n")
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            for item in rows:
                writer.writerow({k: _fmt(v) for k, v in item.items()})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
