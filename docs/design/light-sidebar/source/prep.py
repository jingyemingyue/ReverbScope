# ruff: noqa
"""Precompute the mockup data from ReverbScope's OWN algorithms (main ab3da19).

Nothing here is hand-drawn. Steps:

1. ``reverbscope demo --out $RS_DEMO_DIR`` (synthetic room, positions A/B, 5 s sweep).
2. ``PYTHONPATH=src python prep.py`` reads those sessions with
   ``io.session_store.load_measurement`` and calls the same src APIs the GUI on
   main calls: ``display.curves`` (smoothing, level offset, difference),
   ``display.etc`` (ETC + reflection markers), ``display.timefreq``
   (spectrogram + cumulative spectral decay with default params),
   ``health.assess``, ``interpretation.interpret`` / ``judge_comparison`` /
   ``summarize_project`` / ``explain_all``, ``core.averaging.average_decay``,
   ``geometry.room.example_room`` + ``geometry.paths`` (predicted first-order
   paths, reflection constraints, consistency checks).
3. Arrays go to ``demo.npz``; texts (both interface languages) to ``demo.json``.
"""

import dataclasses, json, math, os
import numpy as np, soundfile as sf

from reverbscope import i18n
from reverbscope.io.session_store import load_measurement, load_comparison
from reverbscope.display.curves import smooth_fractional_octave, level_offset, difference
from reverbscope.display.etc import etc_curve, marker_points
from reverbscope.display.timefreq import (
    SpectrogramParams,
    WaterfallParams,
    spectrogram,
    cumulative_spectral_decay,
)

HERE = os.path.dirname(os.path.abspath(__file__))
D = os.environ.get("RS_DEMO_DIR", "/workspace/work/light-sidebar/demo-main")
npz: dict = {}
js: dict = {"source": "reverbscope demo (main ab3da19), computed by src APIs", "lang": {}}

g = np.logspace(math.log10(18), math.log10(21000), 1400)
npz["fr_f"] = g
M = {p: load_measurement(f"{D}/position-{p}") for p in "ab"}


def on_grid(f, m):
    keep = (f >= 15) & (f <= 22000) & np.isfinite(m)
    return np.interp(np.log10(g), np.log10(f[keep]), m[keep])


def peak_on_grid(f, m):
    keep = (f >= 15) & (f <= 22000) & np.isfinite(m)
    ff, mm = f[keep], m[keep]
    idx = np.searchsorted(ff, g)
    lo, o = 0, []
    for hi in idx:
        seg = mm[lo : max(hi, lo + 1)]
        o.append(seg[np.argmax(np.abs(seg - np.median(seg)))] if seg.size else np.nan)
        lo = hi
    return np.array(o)


num: dict = {}


def dc(o):
    if o is None:
        return None
    if dataclasses.is_dataclass(o) and not isinstance(o, type):
        try:
            return dataclasses.asdict(o)
        except Exception:
            pass
    if hasattr(o, "to_dict"):
        return o.to_dict()
    if isinstance(o, dict):
        return o
    return str(o)


for p, m in M.items():
    r = m.result
    fr = r.frequency_response
    f = np.asarray(fr.frequencies_hz, float)
    raw = np.asarray(fr.magnitude_db_raw, float)
    sm = np.asarray(fr.magnitude_db_smoothed, float)
    npz[f"fr_{p}"] = on_grid(f, sm)
    npz[f"frraw_{p}"] = peak_on_grid(f, raw)
    # display smoothing 1/3 octave (FrequencyView SMOOTHING_CHOICES) from the raw curve
    sel = (f > 15) & (f < 24000)
    npz[f"fr3_{p}"] = on_grid(f[sel], smooth_fractional_octave(f[sel], raw[sel], 3))
    off = level_offset(f, sm, (500.0, 2000.0))
    num[f"align_offset_{p}_db"] = None if off is None else float(off)
    bb = r.decay.broadband
    npz[f"edc_t_{p}"] = np.asarray(bb.edc_time_s, float)
    npz[f"edc_db_{p}"] = np.asarray(bb.edc_db, float)
    bands = []
    for band in r.decay.bands:
        row = {"band": band.band_label, "hz": band.center_hz}
        for k in ("edt", "t20", "t30"):
            mt = getattr(band, k)
            row[k] = (mt.seconds, str(mt.validity), mt.reason)
        for k in ("c50", "c80", "d50", "centre_time"):
            mt = getattr(band, k)
            row[k] = (mt.value, str(mt.validity), mt.reason)
        row["rt60"] = band.rt60_estimate_s
        row["basis"] = band.rt60_basis
        bands.append(row)
        if band.edc_time_s is not None and len(band.edc_time_s):
            npz[f"bedc_t_{p}_{int(band.center_hz)}"] = np.asarray(band.edc_time_s, float)
            npz[f"bedc_db_{p}_{int(band.center_hz)}"] = np.asarray(band.edc_db, float)
    bbd = {}
    for k in ("edt", "t20", "t30"):
        mt = getattr(bb, k)
        bbd[k] = (mt.seconds, str(mt.validity), list(mt.evaluation_range_db or []))
    for k in ("c50", "c80", "d50", "centre_time"):
        mt = getattr(bb, k)
        bbd[k] = (mt.value, str(mt.validity))
    bbd.update(
        rt60=bb.rt60_estimate_s,
        basis=bb.rt60_basis,
        curvature_percent=bb.curvature_percent,
        noise_floor_db=bb.noise_floor_db,
        truncation_time_s=bb.truncation_time_s,
    )
    num[f"bands_{p}"] = bands
    num[f"broadband_{p}"] = bbd
    # ETC + reflection markers (display.etc), first 120 ms
    x, sr = sf.read(f"{D}/position-{p}/impulse_response.wav")
    x = np.asarray(x, float)
    if x.ndim > 1:
        x = x[:, 0]
    di = r.impulse_response.direct_sound_index
    curve = etc_curve(x, sr, di)
    t = np.asarray(curve.time_ms)
    keep = (t >= -5) & (t <= 160)
    npz[f"etc_t_{p}"] = t[keep]
    npz[f"etc_db_{p}"] = np.asarray(curve.level_db)[keep]
    refl = r.reflections.reflections
    npz[f"refl_{p}"] = marker_points(curve, refl) if refl else np.zeros((0, 2))
    num[f"reflections_{p}"] = [(q.delay_ms, q.relative_db) for q in refl]
    num[f"reflection_window_ms_{p}"] = list(r.reflections.window_ms)
    num[f"reflection_threshold_db_{p}"] = r.reflections.threshold_db
    num[f"direct_confidence_{p}"] = str(r.impulse_response.direct_sound_confidence)
    num[f"pre_peak_margin_db_{p}"] = r.impulse_response.pre_peak_margin_db
    # waveform excerpt
    seg = x[max(0, di - int(0.005 * sr)) : di + int(0.160 * sr)]
    npz[f"wave_{p}"] = seg[:: max(1, len(seg) // 4000)] / (np.max(np.abs(seg)) or 1)
    # noise
    n = r.noise
    npz[f"psd_f_{p}"] = np.asarray(n.psd_frequencies_hz, float)
    npz[f"psd_db_{p}"] = np.asarray(n.psd_db, float)
    num[f"noise_{p}"] = {
        "rms_dbfs": n.rms_dbfs,
        "peak_dbfs": n.peak_dbfs,
        "segment": str(n.segment_source),
        "segment_start_s": n.segment_start_s,
        "segment_duration_s": n.segment_duration_s,
        "bands": [(float(b), float(v)) for b, v in n.band_levels_dbfs],
        "hum": [
            {
                "base_hz": h.base_hz,
                "detected": bool(getattr(h, "detected", False)),
                "harmonics": [(float(a), float(b)) for a, b in h.harmonics],
            }
            for h in n.hum
        ],
        "calibration": n.calibration,
    }
    # resonance candidates
    num[f"resonances_{p}"] = [dc(c) for c in r.resonances.candidates]
    num[f"excitation_{p}"] = (fr.excitation_band.low_hz, fr.excitation_band.high_hz)
    num[f"smoothing_fraction_{p}"] = fr.smoothing_fraction
    num[f"harmonics_{p}"] = [
        (h.order, h.level_db, h.floor_db) for h in r.impulse_response.harmonic_distortion
    ]
    num[f"clipping_{p}"] = {"peak_dbfs": r.clipping.peak_dbfs, "clipped": r.clipping.clipped}
    num[f"placement_tier_{p}"] = r.placement.tier
    num[f"sweep_{p}"] = dc(r.sweep_settings) if r.sweep_settings else None

# FR difference B - A (display.curves.difference) on the stored smoothed curves
fa = np.asarray(M["a"].result.frequency_response.frequencies_hz, float)
fb = np.asarray(M["b"].result.frequency_response.frequencies_hz, float)
df, dd = difference(
    fa,
    np.asarray(M["a"].result.frequency_response.magnitude_db_smoothed, float),
    fb,
    np.asarray(M["b"].result.frequency_response.magnitude_db_smoothed, float),
)
npz["diff_ba"] = on_grid(np.asarray(df), np.asarray(dd))

# spectrogram + waterfall of B (default params, as the GUI views)
xb, sr = sf.read(f"{D}/position-b/impulse_response.wav")
xb = np.asarray(xb, float)
dib = M["b"].result.impulse_response.direct_sound_index
sp = spectrogram(xb, sr, dib, SpectrogramParams())
wf = cumulative_spectral_decay(xb, sr, dib, WaterfallParams())
for pre, obj in (("sg_", sp), ("wf_", wf)):
    for a in dir(obj):
        if a.startswith("_"):
            continue
        v = getattr(obj, a)
        if isinstance(v, np.ndarray):
            npz[pre + a] = v
num["spectrogram_params"] = dc(SpectrogramParams())
num["waterfall_params"] = dc(WaterfallParams())

# comparison (comparison.json written by `reverbscope demo`)
cmp = load_comparison(f"{D}/comparison.json")
num["comparison_comparable"] = cmp.comparable
num["comparison_common_band"] = list(cmp.common_band) if cmp.common_band else None
deltas = []
for grp in ("decay", "noise"):
    for d in getattr(cmp, grp) or []:
        dd_ = dc(d)
        dd_["group"] = grp
        deltas.append(dd_)
num["comparison_deltas"] = deltas
num["comparison_fr"] = dc(cmp.frequency_response) if cmp.frequency_response is not None else None
num["comparison_reflections"] = [dc(m) for m in (cmp.reflections or [])]
num["comparison_resonances"] = [dc(m) for m in (cmp.resonances or [])]

js["num"] = num

# texts in both languages
from reverbscope import health
from reverbscope.interpretation.interpreter import interpret
from reverbscope.interpretation.verdicts import judge_comparison
from reverbscope.interpretation.explain import explain_all
from reverbscope.interpretation.overview import ProjectEntry, summarize_project
from reverbscope.core.averaging import average_decay
from reverbscope.geometry.room import example_room, with_microphone, Point
from reverbscope.geometry import paths as gp

for lang in ("en", "zh_CN"):
    i18n.activate(lang)
    T: dict = {}
    for p, m in M.items():
        rep = health.assess(m.result)
        T[f"health_{p}"] = [
            {
                "id": c.id,
                "status": str(c.status),
                "title": c.title,
                "reason": c.reason,
                "fix": list(c.fix),
                "affects": list(c.affects),
            }
            for c in rep.checks
        ]
        T[f"health_{p}_status_word"] = health.status_word(rep.overall)
        for prof in ("vocal", "voiceover", "generic"):
            T[f"findings_{p}_{prof}"] = [
                {"topic": f.topic, "severity": str(f.severity), "message": f.message}
                for f in interpret(m.result, prof)
            ]
    v = judge_comparison(cmp, "vocal", baseline=M["a"].result, candidate=M["b"].result)
    T["verdicts"] = [
        {"aspect": a.aspect, "verdict": str(a.verdict), "title": a.title, "reason": a.reason}
        for a in v.aspects
    ]
    T["verdict_conditions"] = list(v.conditions)
    T["profiles"] = [
        {"name": e.name, "title": e.title, "description": e.description, "wants": list(e.wants)}
        for e in explain_all()
    ]
    ent = [
        ProjectEntry(lbl, str(M[p].directory), M[p].session, M[p].result)
        for lbl, p in (("A", "a"), ("B", "b"))
    ]
    ov = summarize_project(ent, "vocal", project_name="Demo room")

    def _ss(ps):
        r_ = ps.sessions[ps.representative] if ps.sessions else None
        if r_ is None:
            return {"label": ps.label}
        return {
            "label": ps.label,
            "verdict_text": ps.verdict_text,
            "rt60": r_.rt60_s,
            "rt60_basis": r_.rt60_basis,
            "clarity": (r_.clarity_metric, r_.clarity_db),
            "noise": r_.noise_rms_dbfs,
            "reflection": (r_.reflection_ms, r_.reflection_db),
            "fit": str(r_.fit),
            "fit_reason": r_.fit_reason,
            "health": str(r_.health),
            "health_problems": list(r_.health_problems),
            "n_takes": len(ps.sessions),
        }

    T["overview_positions"] = [_ss(ps) for ps in ov.positions]
    T["overview_next_steps"] = list(ov.next_steps)
    av = average_decay([M["a"].result, M["b"].result], session_labels=["A", "B"])
    T["average"] = {
        "iso_class": str(av.iso_3382_2_class),
        "n_mic": av.n_microphone_positions,
        "n_src": av.n_source_positions,
        "bands": [
            {
                "band": bd.band_label,
                "t30": (bd.t30.seconds, bd.t30.spread_s, bd.t30.count, str(bd.t30.validity)),
                "edt": (bd.edt.seconds, bd.edt.spread_s, bd.edt.count, str(bd.edt.validity)),
            }
            for bd in av.bands
        ],
    }
    geo = example_room()
    T["room_box"] = dc(geo.room) if geo.room else None
    T["room_source"] = dc(geo.source) if geo.source else None
    T["room_mics"] = {k: dc(v) for k, v in dict(geo.microphones).items()}
    pos = list(dict(geo.microphones))[0]
    speed = gp.speed_for(M["a"].result)[0]
    pred = gp.predict_first_order(geo, pos, speed)
    T["room_predicted"] = [
        {
            "face": str(q.face),
            "delay_ms": q.delay_ms,
            "path_m": q.path_length_m,
            "point": dc(q.point),
        }
        for q in pred
    ]
    T["room_position"] = pos
    T["room_checks"] = [
        {"name": c.name, "status": str(c.status), "text": c.text}
        for c in gp.consistency_checks(M["a"].result, geo, pos)
    ]
    dd0 = gp.direct_distance(geo, pos)
    T["room_direct_m"] = dd0
    T["room_constraints"] = [
        dc(gp.constraint_for(dl, dd0, speed)) for dl, _ in num["reflections_a"]
    ]
    T["overlay_refusal_a"] = gp.overlay_refusal(M["a"].result)
    js["lang"]["zh" if lang.startswith("zh") else "en"] = T

np.savez_compressed(os.path.join(HERE, "demo.npz"), **npz)
with open(os.path.join(HERE, "demo.json"), "w") as fh:
    json.dump(js, fh, ensure_ascii=False, indent=1, default=str)
print("npz keys", len(npz), "json ok")

# ---- texts the GUI shows verbatim: the report, DAW steps and per-DAW notes
from reverbscope.cli.report import format_report
from reverbscope.ui.pages import DAW_INSTRUCTIONS
import reverbscope.health as _h

js2 = json.load(open(os.path.join(HERE, "demo.json")))
for lang in ("en", "zh_CN"):
    i18n.activate(lang)
    key = "zh" if lang.startswith("zh") else "en"
    T = js2["lang"][key]
    T["report_b"] = format_report(M["b"].result, interpret(M["b"].result, "vocal"), "vocal")
    T["daw_instructions"] = i18n._(DAW_INSTRUCTIONS)
    for name in dir(_h):
        if name.startswith("DAW_") and isinstance(getattr(_h, name), tuple):
            T[name.lower()] = [(d, i18n._(s)) for d, s in getattr(_h, name)]
with open(os.path.join(HERE, "demo.json"), "w") as fh:
    json.dump(js2, fh, ensure_ascii=False, indent=1, default=str)
print("texts ok")
