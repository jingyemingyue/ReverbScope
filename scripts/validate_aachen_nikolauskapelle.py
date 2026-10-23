"""Validate the decay analysis on the open Aachen St. Nicholas Chapel data set.

Data: M. Zerwas and S. Kayku, "Room acoustic measurement and decay analysis
data of the St. Nicholas Chapel, Aachen Cathedral", Zenodo,
https://doi.org/10.5281/zenodo.20428705, CC-BY 4.0. The data set accompanies
Zerwas & Kayku, Acta Acustica (forthcoming). It is *not* part of this
repository: download it yourself and pass the folder::

    python scripts/validate_aachen_nikolauskapelle.py --data ~/aachen \\
        --cache ~/aachen-cache --out aachen-results.csv

The folder must hold ``decayfitnet_all_positions.csv``, the three
``Nikolauskapelle*_Results_20260205.xlsx`` files and the unpacked
``impulse_responses.zip`` (``Nikolauskapelle_Source{1,2,3}_BRIR/*.wav``).

For each of the 46 dodecahedron responses the W (omnidirectional) channel of
the B-format file is analysed by ReverbScope as an imported impulse
response:

* octave bands (63 Hz-8 kHz) through
  :func:`reverbscope.core.pipeline.analyze_impulse_response`, giving the
  single/double-slope fit that is compared with DecayFitNet's T1, T2, A1, A2
  (63-500 Hz);
* one-third-octave bands (50 Hz-10 kHz) through the same per-band analysis
  (:func:`reverbscope.core.decay.analyze_band`), giving EDT, T20 and T30 to
  compare with the authors' ISO 3382-1 parameters in the xlsx files.

The xlsx files are read with the standard library (they are zip archives of
XML), so the script needs nothing beyond ReverbScope's own dependencies.
Writes one CSV row per position, band and quantity and prints the summary
tables used in ``docs/validation/aachen-nikolauskapelle.md``.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import statistics
import sys
import xml.etree.ElementTree as ET
import zipfile
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import soundfile as sf

from reverbscope.core.decay import (
    DIRECT_SOUND_MARGIN_S,
    analyze_band,
    analyze_decay,
    decay_lead_in_s,
    onset_search_window_s,
    pulse_spread_s,
)
from reverbscope.core.filters import apply_bandpass, band_fits, bandpass_sos, iec_band
from reverbscope.core.pipeline import analyze_impulse_response
from reverbscope.errors import AnalysisError
from reverbscope.models.audio import AudioSignal
from reverbscope.models.configuration import AnalysisSettings
from reverbscope.models.result import (
    EXCITATION_SOURCE_DECLARED,
    BandDecay,
    ExcitationBand,
    Validity,
)

#: Declared excitation range of the imported responses (the sweep is not in
#: the data set; the dodecahedron and subwoofer cover the octave bands used).
EXCITATION_HZ = (20.0, 20_000.0)
OCTAVES_HZ = (63.0, 125.0, 250.0, 500.0, 1000.0, 2000.0, 4000.0, 8000.0)
DFN_BANDS_HZ = (63.0, 125.0, 250.0, 500.0)
THIRDS_HZ = (
    50.0, 63.0, 80.0, 100.0, 125.0, 160.0, 200.0, 250.0, 315.0, 400.0, 500.0, 630.0,
    800.0, 1000.0, 1250.0, 1600.0, 2000.0, 2500.0, 3150.0, 4000.0, 5000.0, 6300.0,
    8000.0, 10000.0,
)  # fmt: skip
_NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
_POSITION = re.compile(r"^S(\d)-Do_R-?(\d+)$")


def _num(text: str) -> float | None:
    text = text.strip().replace(",", ".")
    if not text:
        return None
    try:
        value = float(text)
    except ValueError:
        return None
    return value if math.isfinite(value) else None


@dataclass(frozen=True)
class DfnRow:
    t1_s: float
    t2_s: float
    a1: float
    a2: float


def read_decayfitnet(path: Path) -> dict[tuple[str, float], DfnRow]:
    """``(position, band) -> DecayFitNet row``; semicolons and decimal commas."""
    rows: dict[tuple[str, float], DfnRow] = {}
    with path.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle, delimiter=";"):
            t1, t2 = _num(row["T1_s"]), _num(row["T2_s"])
            a1, a2 = _num(row["A1"]), _num(row["A2"])
            band = _num(row["band_hz"])
            if None in (t1, t2, a1, a2, band):
                continue
            assert t1 is not None and t2 is not None and a1 is not None and a2 is not None
            assert band is not None
            rows[(row["position"], band)] = DfnRow(t1, t2, a1, a2)
    return rows


def _column(ref: str) -> int:
    letters = re.match(r"[A-Z]+", ref)
    assert letters is not None
    index = 0
    for char in letters.group(0):
        index = index * 26 + (ord(char) - 64)
    return index


def read_xlsx_parameters(path: Path) -> dict[tuple[str, str, float], float]:
    """``(position, parameter, band) -> value`` from the ``Parameters`` sheet.

    Row 2 names each parameter at the first column of its block, row 3 holds
    the band of every column, the rows below one receiver each.
    """
    with zipfile.ZipFile(path) as archive:
        shared = [
            "".join(t.text or "" for t in item.iter(f"{{{_NS['m']}}}t"))
            for item in ET.fromstring(archive.read("xl/sharedStrings.xml")).findall("m:si", _NS)
        ]
        sheet = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
    table: dict[int, dict[int, str]] = {}
    for row in sheet.find("m:sheetData", _NS) or ():
        cells: dict[int, str] = {}
        for cell in row:
            value = cell.find("m:v", _NS)
            if value is None or value.text is None:
                continue
            text = shared[int(value.text)] if cell.get("t") == "s" else value.text
            cells[_column(cell.get("r", "A"))] = text
        table[int(row.get("r", "0"))] = cells
    names = sorted(table.get(2, {}).items())
    bands = table.get(3, {})
    out: dict[tuple[str, str, float], float] = {}
    for number, cells in table.items():
        if number <= 3:
            continue
        # Source 2's workbook writes "S2-Do_R-4" for the file S2-Do_R4.wav.
        match = _POSITION.match(cells.get(2, "").strip())
        if match is None:
            continue
        position = f"S{match.group(1)}-Do_R{match.group(2)}"
        for column, text in cells.items():
            band = _num(bands.get(column, ""))
            value = _num(text)
            owner = [name for start, name in names if start <= column]
            if band is None or value is None or not owner:
                continue
            out[(position, owner[-1].split(" (")[0], band)] = value
    return out


def _w_channel(path: Path) -> tuple[np.ndarray, int]:
    samples, rate = sf.read(path, dtype="float64", always_2d=True)
    return np.ascontiguousarray(samples[:, 0]), int(rate)


def third_octave_bands(w: np.ndarray, rate: int, direct: int) -> dict[float, BandDecay]:
    """ReverbScope's per-band analysis on IEC 61260-1 one-third-octave bands,
    with the same lead-in, onset window and direct-sound spread as
    :func:`reverbscope.core.decay.analyze_decay` uses for octave bands."""
    settings = AnalysisSettings(octave_bands_hz=(50.0,))
    lead = round(decay_lead_in_s(settings) * rate)
    pad = max(0, lead - direct)
    signal = np.concatenate([np.zeros(pad), w]) if pad else w
    origin = direct + pad
    spread = DIRECT_SOUND_MARGIN_S + pulse_spread_s(EXCITATION_HZ[1] - EXCITATION_HZ[0])
    out: dict[float, BandDecay] = {}
    for nominal in THIRDS_HZ:
        band = iec_band(nominal, 3)
        if not band_fits(band, rate):
            continue
        filtered = apply_bandpass(signal, bandpass_sos(band, rate), time_reversed=True)
        start = max(0, origin - round(onset_search_window_s(band.bandwidth_hz) * rate))
        out[nominal] = analyze_band(
            filtered,
            rate,
            band,
            noise_margin_db=settings.decay_noise_margin_db,
            direct_index=origin,
            time_origin_index=origin,
            onset_search_start=start,
            direct_spread_s=spread,
        )
    return out


def _share(amplitudes: tuple[float, ...]) -> float:
    return 100.0 * amplitudes[1] / sum(amplitudes)


def analyse_position(
    wav: Path,
    settings: AnalysisSettings,
    dfn: dict[tuple[str, float], DfnRow],
) -> list[dict[str, object]]:
    """The comparison rows of one response file."""
    rows: list[dict[str, object]] = []
    position = wav.stem
    w, rate = _w_channel(wav)
    # The import check of ``analyze-ir`` refuses a file whose strongest sample
    # is not 10 dB above everything before it; it is recorded, and every file
    # is then analysed by the same decay analysis with the strongest sample as
    # the direct sound (what the import path uses as time zero).
    refused = ""
    try:
        analyze_impulse_response(
            AudioSignal(w, rate, source=wav.name), settings, excitation_band=EXCITATION_HZ
        )
    except AnalysisError as exc:
        refused = str(exc).split(":")[0]
    direct = int(np.argmax(np.abs(w)))
    excitation = ExcitationBand(*EXCITATION_HZ, source=EXCITATION_SOURCE_DECLARED)
    decay = analyze_decay(w, rate, settings, direct_index=direct, excitation_band=excitation)
    for band in decay.bands:
        if band.center_hz is None:
            continue
        fit = band.multi_slope
        ref = dfn.get((position, band.center_hz))
        two = fit.model(2) if fit is not None else None
        one = fit.model(1) if fit is not None else None
        rows.append(
            {
                "position": position,
                "fraction": "octave",
                "band_hz": band.center_hz,
                "rs_validity": fit.validity.value if fit is not None else "",
                "rs_selected_slopes": fit.selected_slopes if fit is not None else "",
                "rs_delta_bic": fit.delta_bic if fit is not None else "",
                "rs_t30_s": band.t30.seconds if band.t30.validity is Validity.VALID else "",
                "rs1_t_s": one.decay_times_s[0] if one else "",
                "rs2_t1_s": two.decay_times_s[0] if two else "",
                "rs2_t2_s": two.decay_times_s[1] if two else "",
                "rs2_a2_share_pct": _share(two.amplitudes) if two else "",
                "rs_note": "; ".join(fit.notes) if fit is not None else "",
                "analyze_ir": "refused" if refused else "ok",
                "dfn_t1_s": ref.t1_s if ref else "",
                "dfn_t2_s": ref.t2_s if ref else "",
                "dfn_a2_share_pct": _share((ref.a1, ref.a2)) if ref else "",
            }
        )
    for nominal, band in third_octave_bands(w, rate, direct).items():
        for name, metric in (("EDT", band.edt), ("T20", band.t20), ("T30", band.t30)):
            rows.append(
                {
                    "position": position,
                    "fraction": "third",
                    "band_hz": nominal,
                    "metric": name,
                    "rs_seconds": metric.seconds if metric.seconds is not None else "",
                    "rs_validity": metric.validity.value,
                }
            )
    return rows


def run(data: Path, out: Path | None, cache: Path | None = None, limit: int | None = None) -> int:
    dfn = read_decayfitnet(data / "decayfitnet_all_positions.csv")
    iso: dict[tuple[str, str, float], float] = {}
    for workbook in sorted(data.glob("Nikolauskapelle*_Results_*.xlsx")):
        iso.update(read_xlsx_parameters(workbook))
    wavs = sorted(data.glob("**/S*-Do_R*.wav"), key=lambda p: (p.parent.name, len(p.stem), p.stem))
    if not wavs:
        print(f"no S*-Do_R*.wav under {data}", file=sys.stderr)
        return 2
    settings = AnalysisSettings(octave_bands_hz=OCTAVES_HZ)
    rows: list[dict[str, object]] = []
    computed = 0
    for wav in wavs:
        stored = cache / f"{wav.stem}.json" if cache is not None else None
        if stored is not None and stored.exists():
            rows.extend(json.loads(stored.read_text(encoding="utf-8")))
            continue
        if limit is not None and computed >= limit:
            print(f"{wav.stem}: skipped (--limit)", file=sys.stderr)
            continue
        position_rows = analyse_position(wav, settings, dfn)
        computed += 1
        if stored is not None:
            stored.parent.mkdir(parents=True, exist_ok=True)
            stored.write_text(json.dumps(position_rows), encoding="utf-8")
        rows.extend(position_rows)
        print(f"{wav.stem}: done", file=sys.stderr)
    for row in rows:
        if row["fraction"] == "third":
            key = (str(row["position"]), str(row["metric"]), float(str(row["band_hz"])))
            row["iso_seconds"] = iso.get(key, "")
    if out is not None:
        fields = sorted({key for row in rows for key in row}, key=_field_order)
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", encoding="utf-8", newline="") as handle:
            handle.write(
                "# Derived from Zerwas & Kayku, St. Nicholas Chapel data set, "
                "doi:10.5281/zenodo.20428705, CC-BY 4.0. Changes: ReverbScope analysis of the "
                "W channel; DecayFitNet and ISO values copied from the data set for comparison.\n"
            )
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for row in rows:
                writer.writerow({k: _fmt(v) for k, v in row.items()})
    summarize(rows)
    return 0


_ORDER = [
    "position",
    "fraction",
    "band_hz",
    "metric",
    "rs_seconds",
    "rs_validity",
    "iso_seconds",
    "rs_selected_slopes",
    "rs_delta_bic",
    "rs_t30_s",
    "rs1_t_s",
    "rs2_t1_s",
    "rs2_t2_s",
    "rs2_a2_share_pct",
    "dfn_t1_s",
    "dfn_t2_s",
    "dfn_a2_share_pct",
    "rs_note",
    "analyze_ir",
]


def _field_order(name: str) -> int:
    return _ORDER.index(name) if name in _ORDER else len(_ORDER)


def _fmt(value: object) -> object:
    if isinstance(value, float):
        return f"{value:.4g}"
    return value


def _quartiles(values: list[float]) -> tuple[float, float, float]:
    if len(values) < 2:
        v = values[0] if values else float("nan")
        return v, v, v
    q = statistics.quantiles(values, n=4, method="inclusive")
    return q[1], q[0], q[2]


def _pct(a: object, b: object) -> float | None:
    if a in ("", None) or b in ("", None):
        return None
    assert isinstance(a, float | int) and isinstance(b, float | int)
    return 100.0 * (float(a) / float(b) - 1.0)


def summarize(rows: list[dict[str, object]]) -> None:
    """Median and IQR of the relative differences, printed as Markdown."""
    print("\n## ReverbScope vs ISO 3382-1 parameters (xlsx), 1/3 octave, VALID only")
    print("| Band | n | EDT median [IQR] | T20 median [IQR] | T30 median [IQR] |")
    print("| --- | --- | --- | --- | --- |")
    by: dict[tuple[float, str], list[float]] = defaultdict(list)
    for row in rows:
        if row["fraction"] != "third" or row["rs_validity"] != "valid":
            continue
        diff = _pct(row["rs_seconds"], row["iso_seconds"])
        if diff is not None:
            by[(float(str(row["band_hz"])), str(row["metric"]))].append(diff)
    for nominal in THIRDS_HZ:
        cells = []
        count = 0
        for metric in ("EDT", "T20", "T30"):
            values = by.get((nominal, metric), [])
            count = max(count, len(values))
            if values:
                m, lo, hi = _quartiles(values)
                cells.append(f"{m:+.1f} % [{lo:+.1f}, {hi:+.1f}]")
            else:
                cells.append("–")
        print(f"| {nominal:g} Hz | {count} | " + " | ".join(cells) + " |")

    octave = [r for r in rows if r["fraction"] == "octave"]
    print("\n## Slope count (octave bands; DecayFitNet's file always gives two slopes)")
    print("| Band | n | 1 slope | 2 slopes | not VALID or no fit |")
    print("| --- | --- | --- | --- | --- |")
    for nominal in OCTAVES_HZ:
        sel = [r for r in octave if r["band_hz"] == nominal]
        valid = [r for r in sel if r["rs_validity"] == "valid"]
        one = sum(1 for r in valid if r["rs_selected_slopes"] == 1)
        two = sum(1 for r in valid if r["rs_selected_slopes"] == 2)
        print(f"| {nominal:g} Hz | {len(sel)} | {one} | {two} | {len(sel) - one - two} |")

    print("\n## ReverbScope vs DecayFitNet T1, T2 and late-energy share (63-500 Hz)")
    print(
        "| Band | n | RS slopes = 2 | RS T (1 slope) vs DFN T1 | RS T (1 slope) vs DFN T2 "
        "| forced 2-slope T1 vs DFN T1 | forced T2 vs DFN T2 | late share RS2 / DFN "
        "| degenerate 2-slope fits |"
    )
    print("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")

    def cell(values: list[float]) -> str:
        if not values:
            return "–"
        m, lo, hi = _quartiles(values)
        return f"{m:+.1f} % [{lo:+.1f}, {hi:+.1f}]"

    for nominal in DFN_BANDS_HZ:
        paired = [
            r
            for r in octave
            if r["band_hz"] == nominal and r["dfn_t1_s"] != "" and r["rs2_t1_s"] != ""
        ]
        if not paired:
            continue
        chosen = sum(1 for r in paired if r["rs_selected_slopes"] == 2)
        single = [r for r in paired if r["rs_selected_slopes"] == 1 and r["rs1_t_s"] != ""]
        s1 = [d for r in single if (d := _pct(r["rs1_t_s"], r["dfn_t1_s"])) is not None]
        s2 = [d for r in single if (d := _pct(r["rs1_t_s"], r["dfn_t2_s"])) is not None]
        t1 = [d for r in paired if (d := _pct(r["rs2_t1_s"], r["dfn_t1_s"])) is not None]
        t2 = [d for r in paired if (d := _pct(r["rs2_t2_s"], r["dfn_t2_s"])) is not None]
        rs_share = [float(str(r["rs2_a2_share_pct"])) for r in paired]
        dfn_share = [float(str(r["dfn_a2_share_pct"])) for r in paired]
        degenerate = sum(1 for r in paired if _degenerate(r))
        print(
            f"| {nominal:g} Hz | {len(paired)} | {chosen} | {cell(s1)} | {cell(s2)} "
            f"| {cell(t1)} | {cell(t2)} "
            f"| {statistics.median(rs_share):.1f} % / {statistics.median(dfn_share):.1f} % "
            f"| {degenerate} |"
        )
    refused = sorted({str(r["position"]) for r in octave if r.get("analyze_ir") == "refused"})
    print(f"\nanalyze-ir import check refused: {len(refused)} ({', '.join(refused) or 'none'})")


def _degenerate(row: dict[str, object]) -> bool:
    """A two-slope fit that does not describe two slopes: nearly equal times,
    a slow time at the fit bound (several times the record) or a late share
    below 1 %."""
    t1 = float(str(row["rs2_t1_s"]))
    t2 = float(str(row["rs2_t2_s"]))
    share = float(str(row["rs2_a2_share_pct"]))
    return t2 < 1.05 * t1 or t2 > 15.0 or share < 1.0 or share > 99.0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data", type=Path, required=True, help="folder of the data set")
    parser.add_argument("--out", type=Path, default=None, help="CSV of the comparison")
    parser.add_argument(
        "--cache", type=Path, default=None, help="folder for per-position results (resumable)"
    )
    parser.add_argument(
        "--limit", type=int, default=None, help="analyse at most this many new positions"
    )
    args = parser.parse_args(argv)
    return run(args.data, args.out, args.cache, args.limit)


if __name__ == "__main__":
    raise SystemExit(main())
