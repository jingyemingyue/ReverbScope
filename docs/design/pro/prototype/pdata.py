# Design-phase mockup renderer (docs only, not product code).
"""Demo data for the pro mockups. Nothing acoustic is computed here.

Scalars and stored curves come from result.json / comparison.json written by
`reverbscope demo` (0.5.0b3, main 01291d8; see ../../cli/demo). The ETC and
the waterfall are computed by main's own display code
(reverbscope.display.etc.etc_curve, reverbscope.display.timefreq
.cumulative_spectral_decay) from the stored impulse_response.wav, the same
calls ui/views/impulse.py and ui/views/timefreq.py make.
"""

from __future__ import annotations

import json
import math
from functools import cache

import numpy as np
import pk

CLI = pk.DEMO_DIR


@cache
def result(pos: str) -> dict:
    return json.loads((CLI / f"position-{pos}" / "result.json").read_text())


@cache
def comparison() -> dict:
    return json.loads((CLI / "comparison.json").read_text())


def fr(pos: str, smoothed: bool = True, n: int = 1600) -> tuple[np.ndarray, np.ndarray]:
    d = result(pos)["frequency_response"]
    f = np.asarray(d["frequencies_hz"], float)
    m = np.asarray(d["magnitude_db_smoothed" if smoothed else "magnitude_db_raw"], float)
    keep = (f >= 15) & (f <= 22000) & np.isfinite(m)
    f, m = f[keep], m[keep]
    g = np.logspace(math.log10(18), math.log10(21000), n)
    if smoothed:
        return g, np.interp(np.log10(g), np.log10(f), m)
    # raw: peak-preserving subset per log bin (display only)
    idx = np.searchsorted(f, g)
    out = []
    lo = 0
    for hi in idx:
        seg = m[lo : max(hi, lo + 1)]
        out.append(seg[np.argmax(np.abs(seg - np.median(seg)))] if seg.size else np.nan)
        lo = hi
    return g, np.asarray(out)


def fr_at(pos: str, hz: float) -> float:
    g, m = fr(pos)
    return float(np.interp(math.log10(hz), np.log10(g), m))


def diff() -> tuple[np.ndarray, np.ndarray]:
    d = comparison()["frequency_response"]
    return np.asarray(d["frequencies_hz"], float), np.asarray(d["difference_db"], float)


def excitation(pos: str = "b") -> tuple[float, float]:
    b = result(pos)["impulse_response"]["excitation_band"]
    return float(b["low_hz"]), float(b["high_hz"])


def broadband(pos: str) -> dict:
    return result(pos)["decay"]["broadband"]


def bands(pos: str) -> list[dict]:
    return result(pos)["decay"]["bands"]


@cache
def ir(pos: str):
    import soundfile as sf

    x, sr = sf.read(CLI / f"position-{pos}" / "impulse_response.wav")
    return np.asarray(x, float), int(sr), int(result(pos)["impulse_response"]["direct_sound_index"])


@cache
def etc(pos: str):
    from reverbscope.display.etc import etc_curve

    x, sr, d = ir(pos)
    return etc_curve(x, sr, d)


@cache
def waterfall(pos: str = "b"):
    from reverbscope.display.timefreq import WaterfallParams, cumulative_spectral_decay

    x, sr, d = ir(pos)
    return cumulative_spectral_decay(x, sr, d, WaterfallParams())


def speed_of_sound(pos: str = "b") -> float:
    return float(result(pos)["placement"]["speed_of_sound_m_s"])


def cmp_row(name: str) -> dict:
    c = comparison()
    for g in ("decay", "noise"):
        for r in c[g]:
            if r["name"] == name:
                return r
    raise KeyError(name)


def fmt_s(v: float | None) -> str:
    return "—" if v is None else f"{v:.2f}"


def signed(v: float, digits: int = 1) -> str:
    s = f"{v:+.{digits}f}"
    return s.replace("-", "\u2212")


def neg(v: float, digits: int = 1) -> str:
    return f"{v:.{digits}f}".replace("-", "\u2212")
