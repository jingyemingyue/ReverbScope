# ruff: noqa
"""Precompute demo data (from `reverbscope demo` outputs) for the light-sidebar mockups."""

import json, math, os, numpy as np, soundfile as sf, sys

# needs reverbscope importable (PYTHONPATH=src) for the waterfall display helper
D = os.environ.get("RS_DEMO_DIR", "/workspace/work/reverbscope-design/cli/demo")
out = {}
for p in "ab":
    r = json.load(open(f"{D}/position-{p}/result.json"))
    fr = r["frequency_response"]
    f = np.asarray(fr["frequencies_hz"])
    g = np.logspace(math.log10(18), math.log10(21000), 1400)
    for k in ("smoothed", "raw"):
        m = np.asarray(fr["magnitude_db_" + k], float)
        keep = (f >= 15) & (f <= 22000) & np.isfinite(m)
        if k == "smoothed":
            out[f"fr_{p}"] = np.interp(np.log10(g), np.log10(f[keep]), m[keep])
        else:
            ff, mm = f[keep], m[keep]
            idx = np.searchsorted(ff, g)
            lo = 0
            o = []
            for hi in idx:
                seg = mm[lo : max(hi, lo + 1)]
                o.append(seg[np.argmax(np.abs(seg - np.median(seg)))] if seg.size else np.nan)
                lo = hi
            out[f"frraw_{p}"] = np.array(o)
    bb = r["decay"]["broadband"]
    out[f"edc_t_{p}"] = np.array(bb["edc_time_s"])
    out[f"edc_db_{p}"] = np.array(bb["edc_db"])
    out[f"psd_f_{p}"] = np.array(r["noise"]["psd_frequencies_hz"])
    out[f"psd_db_{p}"] = np.array(r["noise"]["psd_db"])
out["fr_f"] = g
print(list(r["decay"]["bands"][0].keys()))
from reverbscope.display.timefreq import WaterfallParams, cumulative_spectral_decay

x, sr = sf.read(f"{D}/position-b/impulse_response.wav")
x = np.asarray(x, float)
d = json.load(open(f"{D}/position-b/result.json"))["impulse_response"]["direct_sound_index"]
w = cumulative_spectral_decay(x, sr, d, WaterfallParams())
print(type(w), [a for a in dir(w) if not a.startswith("_")])
for a in dir(w):
    if not a.startswith("_"):
        v = getattr(w, a)
        if isinstance(v, np.ndarray):
            out["wf_" + a] = v
            print(a, v.shape)
        elif isinstance(v, (int, float)):
            print(a, v)
np.savez_compressed(os.path.join(os.path.dirname(os.path.abspath(__file__)), "demo.npz"), **out)
