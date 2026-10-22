# ruff: noqa
# Design-phase mockup renderer (docs only, not product code).
"""Round 2 screens: every view the code on main already has, drawn from real algorithm output.

Data: demo.npz / demo.json, written by prep.py from `reverbscope demo` sessions through the
src APIs (display.curves / display.etc / display.timefreq / health / interpretation /
core.averaging / geometry). Words for views, controls and sections come from the product's
own catalogue via lk.tr().
"""

from __future__ import annotations

import json
import math

import numpy as np

import lk
import lshell as sh
import lcharts
from lcharts import Plot, colorbar, legend, mnum, ramp
from lk import C, L, Canvas, tw, tr

DEMO = np.load(lk.HERE / "demo.npz")
DATA = json.load(open(lk.HERE / "demo.json"))
N = DATA["num"]
SB = lk.SIDEBAR_W
TB = lk.TOOLBAR_H
CENTERS = [63, 125, 250, 500, 1000, 2000, 4000, 8000]


def TX():
    return DATA["lang"]["zh" if lk.zh() else "en"]


def narrow():
    return lk.MODE["W"] < 1100


def mid_hz(v):
    return f"{v / 1000:g} kHz" if v >= 1000 else f"{v:g} Hz"


# ------------------------------------------------------------------ frame
#: ui/analysis_workspace.py VIEW_GROUPS (identical on main ab3da19 and PR #71 e39185c)
GROUPS = [
    ("overview", "Overview"),
    ("frequency", "Frequency"),
    ("time", "Time"),
    ("decay", "Decay"),
    ("spectral", "Spectral"),
    ("room", "Room"),
    ("compare", "Compare"),
    ("report", "Report"),
]
SPECTRAL = [("spectrogram", "Spectrogram"), ("waterfall", "Waterfall"), ("noise", "Noise")]


def frame(cv, group, inspector=False, title="B-1", sub=None, sel="b1", health_warn=True):
    """Sidebar + unified toolbar with the code's eight view groups. Returns content x0."""
    W = cv.W
    nar = narrow()
    if not nar:
        sh.sidebar(cv, sel=sel)
    x0 = 0 if nar else SB
    sub = sub or L("合成演示房间 · 位置 B", "Synthetic demo room · Position B")
    end = sh.toolbar(cv, x0, title, sub, traffic=nar)
    labels = [tr(e) for _, e in GROUPS]
    ids = [g for g, _ in GROUPS]
    selv = ids.index(group) if group in ids else -1
    rx = W - 16
    for name, act in (("panel-right", inspector), ("save", False)):
        rx -= 32
        sh.tool_icon(cv, rx, 11, name, active=act)
    pad = 10
    segw = sum(tw(s, "calloutm") + 2 * pad for s in labels) + 4
    if segw > rx - 16 - (end + 20):
        pad = 7
        segw = sum(tw(s, "calloutm") + 2 * pad for s in labels) + 4
    sx = max(end + 20, min(x0 + (W - x0) / 2 - segw / 2, rx - 12 - segw))
    lk.segmented(cv, sx, 12, labels, selv, pad=pad)
    return x0


def header(cv, x, xr, title, meta, y=None, demo=True):
    y = TB + 18 if y is None else y
    cv.text(x, y, title, "title1", "text1", h=28)
    tx = x + tw(title, "title1") + 14
    chipw = (tw(L("合成演示数据", "Synthetic demo"), "callout") + 38) if demo else 0
    if meta:
        cv.text(tx, y + 6, meta, "callout", "text3", w=max(40, xr - tx - chipw - 12), h=20)
    if demo:
        lab = L("合成演示数据", "Synthetic demo")
        lk.chip(cv, xr - chipw, y + 2, lab, icon="flask-conical")
    return y + 40


def label_popup(cv, x, y, lab, val, w, role="callout"):
    adv = cv.text(x, y, lab, "callout", "text2", h=28) + 6
    lk.popup(cv, x + adv, y, w, val, role=role)
    return adv + w + 14


def label_check(cv, x, y, lab, on=False):
    lk.checkbox(cv, x, y + 6, checked=on)
    return 24 + cv.text(x + 24, y, lab, "callout", "text1", h=28) + 14


def spin(cv, x, y, lab, val, w=None):
    adv = cv.text(x, y, lab, "callout", "text2", h=28) + 6
    w = w or tw(val, "mono") + 34
    cv.rect(x + adv, y, w, 28, fill="surface", stroke="border", r=7)
    cv.text(x + adv + 8, y, val, "mono", "text1", w=w - 26, h=28)
    cv.icon("chevron-down", x + adv + w - 18, y + 7, 12, "text3", stroke=1.25)
    return adv + w + 12


def chart_tools(cv, xr, y):
    """Right of a chart control row: Reset (R) and Export ▸ PNG / SVG / CSV (ChartPanel)."""
    exp = L("导出", "Export")
    w = tw(exp, "callout") + 52
    cv.rect(xr - w, y, w, 28, fill="surface", stroke="border", r=7)
    cv.icon("download", xr - w + 8, y + 6, 16, "text2")
    cv.text(xr - w + 30, y, exp, "callout", "text1", h=28)
    cv.icon("chevron-down", xr - 20, y + 8, 12, "text3", stroke=1.25)
    x = xr - w - 8
    rl = L("复位", "Reset")
    w2 = tw(rl, "callout") + 30 + 22
    cv.rect(x - w2, y, w2, 28, stroke="border", r=7)
    cv.icon("rotate-ccw", x - w2 + 8, y + 6, 16, "text2")
    cv.text(x - w2 + 30, y, rl, "callout", "text1", h=28)
    lk.kbd(cv, x - 22, y + 5, "R")
    return w + 8 + w2


HINT = None


def hint():
    return L(
        "滚轮缩放 · 拖动平移 · 右键拖动框选 · 双击 / R 复位",
        "Wheel zoom · drag pan · right-drag box zoom · double-click / R reset",
    )


def readout(cv, x, y, w, parts, h_=None):
    cv.rect(x, y, w, 28, fill="readout", r=6)
    xx = x + 12
    for i, (txt, color) in enumerate(parts):
        if i:
            cv.vline(xx, y + 7, y + 21, "border")
            xx += 10
        xx += cv.text(xx, y, txt, "mono", color, h=28) + 10
    hs = h_ if h_ is not None else hint()
    hw = tw(hs, "caption")
    if hs and xx + hw + 16 < x + w:
        cv.text(x + w - hw - 12, y, hs, "caption", "text3", h=28)


def octave_frame(q):
    old = lcharts.FREQ_MAJOR
    lcharts.FREQ_MAJOR = tuple(CENTERS)
    q.frame()
    lcharts.FREQ_MAJOR = old


def table(cv, x, y, cols, rows, rh=28, zebra=True, head_role="captionm", maxy=None):
    """cols: (label, width, align). rows: list of list of (text, color, role). Returns y."""
    cx = x
    tot = sum(c[1] for c in cols)
    for lab, w, al in cols:
        cv.text(cx + (0 if al == "l" else 0), y, lab, head_role, "text3", w=w - 8, h=24, align=al)
        cx += w
    y += 24
    cv.hline(x, x + tot, y, "sep")
    y += 2
    for i, r in enumerate(rows):
        if maxy and y + rh > maxy:
            break
        if zebra and i % 2 == 1:
            cv.rect(x - 6, y, tot + 6, rh, fill=C("sunken", 0.7), r=4)
        cx = x
        for (lab, w, al), cell in zip(cols, r):
            txt, col, role = (
                (cell + (None, None))[:3] if isinstance(cell, tuple) else (cell, None, None)
            )
            cv.text(
                cx,
                y,
                txt,
                role or ("mono" if al == "r" else "callout"),
                col or "text1",
                w=w - 8,
                h=rh,
                align=al,
            )
            cx += w
        y += rh
    return y


def val_text(v, validity, d=2, unit="", sign=False):
    if v is None:
        return ("–", "text3", "mono")
    s = mnum(v, d, sign) + (f" {unit}" if unit else "")
    if validity != "valid":
        return (f"({s})", "warn", "mono")
    return (s, "text1", "mono")


def section_title(cv, x, y, s, w=None):
    cv.text(x, y, s, "captionm", "text3", h=18, w=w)
    return y + 22


# ------------------------------------------------------------------ inspector (real sections)
def inspector(cv, x, y, w, h, sections=("health", "figures", "conditions", "comparison")):
    """ui/inspector.py: Measurement health · Key figures · Conditions · Comparison ·
    Selected reflection · Room checks (same sections, same order)."""
    cv.rect(x, y, w, h, fill="sidebar")
    cv.vline(x, y, y + h, "sep")
    t = TX()
    yy = y + 14
    cv.text(x + 16, yy, tr("Inspector"), "headline", "text1", h=20)
    yy += 24
    cv.text(x + 16, yy, "B-1", "bodym", "text1", h=18)
    cv.text(
        x + 16 + tw("B-1", "bodym") + 8,
        yy,
        L("人声配置 · 合成演示，不是真实房间", "Vocals profile · synthetic demo, not a room"),
        "caption",
        "text3",
        w=w - 48,
        h=18,
    )
    yy += 28
    pad = x + 16
    iw = w - 32

    def sec(title):
        nonlocal yy
        cv.hline(pad, pad + iw, yy, "sep")
        yy += 10
        cv.icon("chevron-down", pad, yy + 2, 12, "text3", stroke=1.25)
        cv.text(pad + 18, yy, title, "captionm", "text2", h=16)
        yy += 24

    def kv(k, v, col="text1", role="mono"):
        nonlocal yy
        cv.text(pad, yy, k, "callout", "text2", h=22, w=iw * 0.48)
        cv.text(pad + iw * 0.4, yy, v, role, col, w=iw * 0.6, h=22, align="r")
        yy += 22

    for s in sections:
        if yy > y + h - 40:
            break
        if s == "health":
            sec(tr("Measurement health"))
            checks = t["health_b"]
            good = sum(1 for c in checks if c["status"] == "good")
            cv.icon("triangle-alert", pad, yy + 3, 14, "warn")
            cv.text(
                pad + 20,
                yy,
                L(
                    f"{tr('Overall')}：{len(checks)} 项检查中 {good} 项良好",
                    f"Overall: {good} of {len(checks)} checks good",
                ),
                "callout",
                "text1",
                h=20,
                w=iw - 20,
            )
            yy += 24
            for c in checks:
                if c["status"] == "good":
                    continue
                cv.text(pad + 20, yy, c["title"], "calloutm", "warn", h=18)
                yy += 20
                rh_ = cv.wrap_h(c["reason"], "caption", iw - 20)
                cv.text(
                    pad + 20,
                    yy,
                    c["reason"],
                    "caption",
                    "text2",
                    w=iw - 20,
                    h=rh_ + 2,
                    wrap=True,
                    valign="t",
                )
                yy += rh_ + 4
                for f in c["fix"][:1]:
                    s_ = L("下一步：", "Next: ") + f
                    fh = cv.wrap_h(s_, "caption", iw - 20)
                    cv.text(
                        pad + 20,
                        yy,
                        s_,
                        "caption",
                        "text1",
                        w=iw - 20,
                        h=fh + 2,
                        wrap=True,
                        valign="t",
                    )
                    yy += fh + 6
            yy += 4
        elif s == "figures":
            sec(tr("Key figures"))
            bb = N["broadband_b"]
            kv(tr("RT60 estimate"), f"{bb['rt60']:.2f} s · {bb['basis']}")
            nb = N["noise_b"]
            kv(tr("Noise floor"), f"{mnum(nb['rms_dbfs'], 1)} dBFS")
            kv(
                tr("Direct sound"),
                L(
                    f"置信度 高 · {N['pre_peak_margin_db_b']:.1f} dB",
                    f"high · {N['pre_peak_margin_db_b']:.1f} dB",
                ),
            )
            r = N["reflections_b"]
            kv(tr("Early reflections"), L(f"{len(r)} 个 · 高于 −20 dB", f"{len(r)} above −20 dB"))
            cv.text(
                pad,
                yy + 2,
                tr("Values in brackets are shown, not trusted (not VALID)."),
                "caption",
                "text3",
                w=iw,
                h=30,
                wrap=True,
                valign="t",
            )
            yy += 34
        elif s == "conditions":
            sec(tr("Conditions"))
            sw_ = N["sweep_b"] or {}
            kv(tr("Position"), "B")
            kv(
                L("扫频", "Sweep"),
                f"{sw_.get('duration_s', 5):g} s · {mnum(sw_.get('level_dbfs', -12), 0)} dBFS",
            )
            kv(tr("Sample rate"), "48000 Hz")
            kv(tr("Profile"), L("人声", "Vocals"), role="callout")
        elif s == "comparison":
            sec(L("对比", "Comparison"))
            cv.text(
                pad,
                yy,
                L("B-1 对比基准 A-1。", "B-1 against the baseline A-1."),
                "callout",
                "text1",
                h=20,
                w=iw,
            )
            yy += 24
            lk.checkbox(cv, pad, yy + 4, checked=True)
            cv.text(pad + 24, yy, tr("Input gain unchanged"), "callout", "text1", h=24)
            yy += 30
            lk.button(cv, pad, yy, tr("Open the comparison"), "secondary", h=26, role="callout")
            yy += 34
        elif s == "reflection":
            sec(tr("Selected reflection"))
            d, lv = N["reflections_a"][0]
            kv(tr("Delay"), f"{d:.2f} ms")
            kv(tr("Level"), f"{mnum(lv, 1)} dB")
            kv(
                tr("Excess path"),
                L(f"{d * 0.3432:.2f} m · 343.2 m/s", f"{d * 0.3432:.2f} m at 343.2 m/s"),
            )
            cv.text(
                pad,
                yy + 2,
                L("未输入气温；按 20 °C 假定。", "No temperature entered; 20 °C is assumed."),
                "caption",
                "text3",
                w=iw,
                h=18,
            )
            yy += 24
        elif s == "room":
            sec(tr("Room checks"))
            for c in t["room_checks"][:5]:
                ic, col = {"ok": ("circle-check", "good"), "warn": ("triangle-alert", "warn")}.get(
                    c["status"], ("circle-dashed", "text3")
                )
                cv.icon(ic, pad, yy + 3, 14, col)
                th = cv.wrap_h(c["text"], "caption", iw - 22)
                cv.text(
                    pad + 22,
                    yy + 1,
                    c["text"],
                    "caption",
                    "text2",
                    w=iw - 22,
                    h=th + 2,
                    wrap=True,
                    valign="t",
                )
                yy += max(20, th + 6)


# ------------------------------------------------------------------ 13 overview
def overview(cv: Canvas):
    W, H = cv.W, cv.H
    insp = W >= 1440
    x0 = frame(cv, "overview", inspector=insp)
    iw = 300 if insp else 0
    pad = 24 if narrow() else 32
    x, xr = x0 + pad, W - pad - iw
    t = TX()
    bb = N["broadband_b"]
    y = header(
        cv,
        x,
        xr,
        tr("Overview"),
        L(
            "合成演示房间 · 位置 B · 人声配置 · 48000 Hz",
            "Synthetic demo room · Position B · Vocals profile · 48000 Hz",
        ),
    )
    # stat tiles (StatTile x4, hairline separated)
    nb = N["noise_b"]
    refl = N["reflections_b"]
    tiles = [
        (
            tr("Reverberation (RT60)"),
            f"{bb['rt60']:.2f}",
            "s",
            L(f"宽带，由 {bb['basis']} 估计", f"broadband, from {bb['basis']}"),
            "valid",
        ),
        (
            tr("Background noise"),
            mnum(nb["rms_dbfs"], 1),
            "dBFS",
            L("RMS · 扫频前 · 未校准 · 50 Hz 交流声", "RMS · pre-sweep · uncalibrated · hum 50 Hz"),
            "warn",
        ),
        (
            tr("Early reflections"),
            mnum(refl[0][1], 1) if refl else "–",
            "dB",
            L(
                f"最强，位于 {refl[0][0]:.1f} ms · {len(refl)} 个高于 −20 dB",
                f"strongest at {refl[0][0]:.1f} ms · {len(refl)} above −20 dB",
            ),
            "valid",
        ),
        (
            tr("Direct sound"),
            L("高", "high"),
            "",
            L(
                f"置信度 · 峰前余量 {N['pre_peak_margin_db_b']:.1f} dB",
                f"confidence · pre-peak margin {N['pre_peak_margin_db_b']:.1f} dB",
            ),
            "valid",
        ),
    ]
    mw = (xr - x) / 4
    for i, (k, v, u, sub, st) in enumerate(tiles):
        mx = x + i * mw
        if i:
            cv.vline(mx - 1, y + 4, y + 62, "sep")
        ix = mx + (16 if i else 0)
        cv.text(ix, y, k, "callout", "text2", h=18, w=mw - 20)
        adv = cv.text(ix, y + 18, v, "num", "text1", h=32)
        if u:
            cv.text(ix + adv + 4, y + 30, u, "callout", "text2", h=18)
        if st == "warn":
            cv.icon(
                "triangle-alert",
                ix + adv + 4 + (tw(u, "callout") + 8 if u else 0),
                y + 30,
                14,
                "warn",
            )
        cv.text(ix, y + 50, sub, "caption", "text3", h=16, w=mw - 22)
    y += 84
    gap = 28
    lw = (xr - x - gap) * 0.5
    rx0 = x + lw + gap
    # left: health + findings
    yl = y
    cv.text(x, yl, tr("MEASUREMENT HEALTH"), "captionm", "text3", h=18)
    hs = t["health_b_status_word"]
    lk.chip(cv, x + lw - tw(hs, "callout") - 38, yl - 3, hs, icon="triangle-alert", tone="warn")
    yl += 24
    checks = t["health_b"]
    cols = 2
    cwid = lw / cols
    for i, c in enumerate(checks):
        cx_ = x + (i % cols) * cwid
        cy_ = yl + (i // cols) * 24
        ic, col = {
            "good": ("circle-check", "good"),
            "warning": ("triangle-alert", "warn"),
            "invalid": ("circle-x", "crit"),
        }.get(c["status"], ("circle-dashed", "text3"))
        cv.icon(ic, cx_, cy_ + 4, 14, col)
        cv.text(
            cx_ + 20,
            cy_,
            c["title"],
            "callout",
            "text1" if c["status"] == "good" else "warn",
            h=22,
            w=cwid - 24,
        )
    yl += ((len(checks) + 1) // 2) * 24 + 6
    lvl = next(c for c in checks if c["status"] != "good")
    s1 = f"{lvl['title']} · {lvl['reason']}"
    s2 = L("下一步：", "Next: ") + lvl["fix"][0]
    h1 = cv.wrap_h(s1, "caption", lw - 24)
    h2 = cv.wrap_h(s2, "caption", lw - 24)
    cv.rect(x, yl, lw, h1 + h2 + 18, fill="warn.soft", r=8)
    cv.text(x + 12, yl + 6, s1, "caption", "warn", w=lw - 24, h=h1 + 2, wrap=True, valign="t")
    cv.text(
        x + 12, yl + 10 + h1, s2, "caption", "text1", w=lw - 24, h=h2 + 2, wrap=True, valign="t"
    )
    yl += h1 + h2 + 34
    cv.text(x, yl, L("解读 · 人声配置", "Reading · Vocals profile"), "captionm", "text3", h=18)
    yl += 24
    for f in t["findings_b_vocal"]:
        ic, col = {
            "warning": ("triangle-alert", "warn"),
            "notice": ("info", "info"),
            "info": ("info", "text3"),
        }[f["severity"]]
        mh = cv.wrap_h(f["message"], "callout", lw - 24)
        if yl + min(mh, 36) > H - 20:
            break
        cv.icon(ic, x, yl + 2, 16, col)
        show_h = min(mh, 36)
        cv.text(
            x + 24,
            yl,
            f["message"],
            "callout",
            "text1",
            w=lw - 24,
            h=show_h + 1,
            wrap=True,
            valign="t",
            check=False,
        )
        yl += show_h + 10
    # right: tables
    yr_ = y
    cv.text(rx0, yr_, tr("REVERBERATION BY BAND"), "captionm", "text3", h=18)
    yr_ += 20
    rw = xr - rx0
    cw5 = [rw * 0.22] + [rw * 0.195] * 4
    cols_ = [
        (tr("Band"), cw5[0], "l"),
        ("EDT", cw5[1], "r"),
        ("T20", cw5[2], "r"),
        ("T30", cw5[3], "r"),
        (tr("RT60 estimate"), cw5[4], "r"),
    ]
    rows = [
        [
            (L("宽带", "Broadband"), "text1", "calloutm"),
            val_text(bb["edt"][0], bb["edt"][1], 2, "s"),
            val_text(bb["t20"][0], bb["t20"][1], 2, "s"),
            val_text(bb["t30"][0], bb["t30"][1], 2, "s"),
            (f"{bb['rt60']:.2f} s", "text1", "monom"),
        ]
    ]
    for b in N["bands_b"]:
        rows.append(
            [
                (mid_hz(b["hz"]), "text1", "callout"),
                val_text(*b["edt"][:2], 2, "s"),
                val_text(*b["t20"][:2], 2, "s"),
                val_text(*b["t30"][:2], 2, "s"),
                (f"{b['rt60']:.2f} s", "text1", "mono"),
            ]
        )
    rh = 22 if H < 900 else 24
    yr_ = table(cv, rx0, yr_, cols_, rows, rh=rh)
    yr_ += 14
    cv.text(rx0, yr_, tr("EARLY AND LATE ENERGY"), "captionm", "text3", h=18)
    yr_ += 20
    cols_ = [
        (tr("Band"), cw5[0], "l"),
        ("C50", cw5[1], "r"),
        ("C80", cw5[2], "r"),
        ("D50", cw5[3], "r"),
        (tr("Centre time"), cw5[4], "r"),
    ]
    rows = [
        [
            (L("宽带", "Broadband"), "text1", "calloutm"),
            val_text(bb["c50"][0], bb["c50"][1], 1, "dB", True),
            val_text(bb["c80"][0], bb["c80"][1], 1, "dB", True),
            val_text(bb["d50"][0], bb["d50"][1], 0, "%"),
            val_text(bb["centre_time"][0] * 1000, bb["centre_time"][1], 0, "ms"),
        ]
    ]
    for b in N["bands_b"]:
        rows.append(
            [
                (mid_hz(b["hz"]), "text1", "callout"),
                val_text(*b["c50"][:2], 1, "dB", True),
                val_text(*b["c80"][:2], 1, "dB", True),
                val_text(*b["d50"][:2], 0, "%"),
                val_text(b["centre_time"][0] * 1000, b["centre_time"][1], 0, "ms"),
            ]
        )
    yr_ = table(cv, rx0, yr_, cols_, rows, rh=rh, maxy=H - 30)
    cv.text(
        rx0,
        min(yr_ + 4, H - 24),
        tr("Values in brackets are shown, not trusted (not VALID)."),
        "caption",
        "text3",
        h=16,
        w=rw,
    )
    if insp:
        inspector(cv, W - iw, TB, iw, H - TB)


# ------------------------------------------------------------------ 05 frequency (real controls)
def frequency(cv: Canvas):
    W, H = cv.W, cv.H
    insp = W >= 1440
    x0 = frame(cv, "frequency", inspector=insp)
    iw = 300 if insp else 0
    pad = 24 if narrow() else 32
    x, xr = x0 + pad, W - pad - iw
    y = header(
        cv,
        x,
        xr,
        tr("Frequency response"),
        L(
            "B-1 当前 · A-1 基准 · 分析平滑 1/6 倍频程 · 电平未对齐",
            "B-1 current · A-1 baseline · analysis smoothing 1/6 oct · levels not aligned",
        ),
        demo=not narrow(),
    )
    # FrequencyView controls: Smoothing combo, Align levels, Raw curve  (+ ChartPanel Reset / Export)
    xx = x
    smooth = L("分析平滑（1/6 倍频程）", "analysis smoothing (1/6 octave)")
    xx += label_popup(cv, xx, y, tr("Smoothing"), smooth, tw(smooth, "callout") + 40)
    xx += label_check(cv, xx, y, tr("Align levels"))
    xx += label_check(cv, xx, y, tr("Raw curve"))
    chart_tools(cv, xr, y)
    y += 40
    legend(
        cv,
        x + 46,
        y,
        [
            ("B-1", L("当前", "current"), "cur", None),
            ("A-1", L("基准", "baseline"), "base", [5, 3]),
            (L("B − A", "B − A"), L("差值", "difference"), "delta", None),
        ],
    )
    y += 22
    bottom = H - 16 - 28 - 10 - 18
    avail = bottom - y
    mh = int(avail * 0.72)
    f = DEMO["fr_f"]
    a, b = DEMO["fr_a"], DEMO["fr_b"]
    lo, hi = N["excitation_b"]
    p = Plot(
        cv,
        x,
        y,
        xr - x,
        mh,
        ylabel=tr("Magnitude (dB, relative)")
        if False
        else L("幅度（dB，相对）", "Magnitude (dB, relative)"),
        yr=(-30, 30),
        show_xlabels=False,
        yminor=2,
    )
    p.frame()
    p.hatch(18, lo)
    p.hatch(hi, 21000)
    p.curve(f, a, "base", 1.5, dash=[5, 3])
    p.curve(f, b, "cur", 2.0)
    fc = N["resonances_b"][0]["frequency_hz"]
    fa = float(np.interp(math.log10(fc), np.log10(f), a))
    fb = float(np.interp(math.log10(fc), np.log10(f), b))
    p.cursor(fc, dots=[(fb, "cur", True), (fa, "base", False)])
    cv.text(p.px + 6, p.py + 4, L("扫频范围外", "Outside sweep"), "caption", "text3", h=14)
    y2 = y + mh + 6
    dh = avail - mh - 6
    q = Plot(
        cv,
        x,
        y2,
        xr - x,
        dh,
        ylabel="Δ dB",
        yr=(-20, 20),
        ystep=10,
        yminor=5,
        xlabel=L("频率（Hz）", "Frequency (Hz)"),
    )
    q.frame()
    q.hatch(18, lo)
    q.hatch(hi, 21000)
    d = DEMO["diff_ba"]
    q.curve(f, d, "delta", 1.5)
    dv = float(np.interp(math.log10(fc), np.log10(f), d))
    q.cursor(fc, dots=[(dv, "delta", True)], flag=f"{fc:.1f} Hz")
    cv.text(
        q.px + 6,
        q.py + 2,
        L("差值（当前 − 基准）", "Difference (current − baseline)"),
        "caption",
        "text3",
        h=14,
    )
    cv.text(
        x + 46,
        H - 16 - 28 - 20,
        L(
            f"斜线：扫频范围（{lo:.0f} Hz–{hi / 1000:.1f} kHz）之外，不是测量值。差值来自 display.curves.difference。",
            f"Hatched: outside the sweep ({lo:.0f} Hz–{hi / 1000:.1f} kHz). Difference from display.curves.difference.",
        ),
        "caption",
        "text3",
        h=16,
        w=xr - x - 46,
    )
    readout(
        cv,
        x,
        H - 16 - 28,
        xr - x,
        [
            (f"{fc:.1f} Hz", "text1"),
            (f"B-1 {mnum(fb, 1, True)} dB", "cur"),
            (f"A-1 {mnum(fa, 1, True)} dB", "base"),
            (f"Δ {mnum(fb - fa, 1, True)} dB", "delta"),
        ],
    )
    if insp:
        inspector(cv, W - iw, TB, iw, H - TB, ("health", "figures", "comparison", "conditions"))


# ------------------------------------------------------------------ 14 time / ETC
def time_etc(cv: Canvas):
    W, H = cv.W, cv.H
    x0 = frame(cv, "time")
    x, xr = x0 + 32, W - 32
    y = header(
        cv,
        x,
        xr,
        tr("Impulse response"),
        L(
            "能量-时间曲线 · 反射检测器的包络，0.1 ms 峰值保持 · A-1",
            "Energy-time curve · reflection detector envelope, 0.1 ms peak hold · A-1",
        ),
    )
    xx = x
    xx += label_popup(
        cv, xx, y, tr("Show"), tr("Energy-time curve"), tw(tr("Energy-time curve"), "callout") + 40
    )
    span = L("前 100 ms", "first 100 ms")
    xx += label_popup(cv, xx, y, tr("Span"), span, tw(span, "callout") + 40)
    chart_tools(cv, xr, y)
    y += 40
    side = 300
    cw = xr - x - side - 28
    legend(
        cv,
        x + 46,
        y,
        [
            ("A-1", L("当前", "current"), "cur", None),
            (L("反射候选", "reflection candidate"), None, "d2", None),
        ],
    )
    y += 22
    ch = H - 16 - 28 - 12 - y
    p = Plot(
        cv,
        x,
        y,
        cw,
        ch,
        xkind="lin",
        xr=(-5, 100),
        yr=(-60, 0),
        ystep=10,
        yminor=5,
        xticks=[0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100],
        ylabel=L("相对直达声电平（dB）", "Level re direct sound (dB)"),
        xlabel=L("直达声之后的时间（ms）", "Time after direct sound (ms)"),
    )
    p.xtfmt = lambda v: f"{v:g}"
    p.frame()
    win = N["reflection_window_ms_a"]
    thr = N["reflection_threshold_db_a"]
    cv.rect(p.X(win[0]), p.py, p.X(win[1]) - p.X(win[0]), p.ph, fill=C("accent", 0.05))
    cv.line(p.px, p.Y(thr), p.px + p.pw, p.Y(thr), C("d2", 0.7), 1, dash=[4, 3])
    cv.text(
        p.px + p.pw - 230,
        p.Y(thr) - 16,
        L(
            f"检测阈值 {thr:g} dB · 窗口 {win[0]:g}–{win[1]:g} ms",
            f"threshold {thr:g} dB · window {win[0]:g}–{win[1]:g} ms",
        ),
        "caption",
        "text2",
        w=224,
        h=14,
        align="r",
    )
    p.curve(DEMO["etc_t_a"], DEMO["etc_db_a"], "cur", 1.25)
    sel = 0
    for i, (tm, lv) in enumerate(DEMO["refl_a"]):
        X, Y = p.X(tm), p.Y(lv)
        cv.line(X, Y, X, p.py + p.ph, C("d2", 0.5), 1)
        cv.circle(
            X, Y, 5 if i == sel else 4, fill="d2" if i == sel else "plot.bg", stroke="d2", sw=1.75
        )
        cv.text(X + 7, Y - 18, f"{tm:.2f} ms", "monos", "d2", h=14)
    # side: reflections table + selected reflection
    sx = xr - side
    cv.text(sx, y - 22, tr("Early reflections"), "headline", "text1", h=18)
    cols = [
        (tr("Delay (ms)") if False else L("延迟（ms）", "Delay (ms)"), 82, "r"),
        (L("电平（dB）", "Level (dB)"), 82, "r"),
        (L("超出路径（m）", "Excess (m)"), 96, "r"),
        ("", 40, "l"),
    ]
    rows = []
    for tm, lv in N["reflections_a"]:
        rows.append([f"{tm:.2f}", mnum(lv, 1), f"{tm * 0.34321:.2f}", ""])
    yy = table(cv, sx, y + 2, cols, rows, rh=30)
    cv.rect(sx - 6, y + 28, side + 6, 30, stroke="accent", r=4, sw=1.25)
    yy += 8
    note = L(
        "候选是高出局部扩散声级的包络峰；在密集的早期尾部，部分候选可能是统计起伏。点图上的标记选中反射。",
        "Candidates are envelope peaks above the local diffuse level; some may be statistical. Click a marker to select.",
    )
    nh = cv.wrap_h(note, "caption", side)
    cv.text(sx, yy, note, "caption", "text3", w=side, h=nh + 2, wrap=True, valign="t")
    yy += nh + 16
    cv.hline(sx, xr, yy, "sep")
    yy += 12
    cv.text(sx, yy, tr("Selected reflection"), "captionm", "text3", h=16)
    yy += 22
    d, lv = N["reflections_a"][0]
    for k, v in (
        (tr("Delay"), f"{d:.2f} ms"),
        (tr("Level"), f"{mnum(lv, 1)} dB"),
        (tr("Excess path"), f"{d * 0.34321:.2f} m · 343.2 m/s"),
    ):
        cv.text(sx, yy, k, "callout", "text2", h=22)
        cv.text(sx, yy, v, "mono", "text1", w=side, h=22, align="r")
        yy += 22
    c = TX()["room_constraints"][0]
    th = cv.wrap_h(c["text"], "caption", side)
    cv.text(sx, yy + 6, c["text"], "caption", "text2", w=side, h=th + 2, wrap=True, valign="t")
    yy += th + 14
    lk.button(
        cv,
        sx,
        yy,
        L("在房间视图中显示", "Show in Room view"),
        "secondary",
        icon="box",
        h=26,
        role="callout",
    )
    readout(
        cv,
        x,
        H - 16 - 28,
        xr - x,
        [
            (f"{d:.2f} ms", "text1"),
            (f"{mnum(lv, 1)} dB", "cur"),
            (L("早期反射候选 · 桌面反射（演示）", "early reflection candidate"), "text2"),
        ],
    )


# ------------------------------------------------------------------ 06 decay (real controls)
def decay(cv: Canvas):
    W, H = cv.W, cv.H
    x0 = frame(cv, "decay")
    x, xr = x0 + 32, W - 32
    y = header(
        cv,
        x,
        xr,
        tr("Decay"),
        L(
            "Schroeder 积分，Lundeby 截断 · ISO 3382-1 · B-1 当前 · A-1 基准",
            "Schroeder integral, Lundeby-truncated · ISO 3382-1 · B-1 vs A-1",
        ),
    )
    xx = x
    xx += label_popup(cv, xx, y, tr("Band"), tr("Broadband"), tw(tr("Broadband"), "callout") + 40)
    xx += label_popup(cv, xx, y, tr("Metric"), "T30", 70)
    chart_tools(cv, xr, y)
    y += 40
    bb = N["broadband_b"]
    ba = N["broadband_a"]
    mets = [
        (f"RT60 ({bb['basis']})", f"{bb['rt60']:.2f}", "s", f"A-1 {ba['rt60']:.2f} s"),
        ("EDT", f"{bb['edt'][0]:.2f}", "s", f"T20 {bb['t20'][0]:.2f} s"),
        ("C50", mnum(bb["c50"][0], 1, True), "dB", f"C80 {mnum(bb['c80'][0], 1, True)} dB"),
        ("D50", f"{bb['d50'][0]:.0f}", "%", f"Ts {bb['centre_time'][0] * 1000:.0f} ms"),
    ]
    mw = (xr - x) / 4
    for i, (k, v, u, sub) in enumerate(mets):
        mx = x + i * mw
        if i:
            cv.vline(mx - 1, y + 4, y + 58, "sep")
        ix = mx + (16 if i else 0)
        cv.text(ix, y, k, "callout", "text2", h=18)
        adv = cv.text(ix, y + 16, v, "num", "text1", h=32)
        cv.text(ix + adv + 4, y + 28, u, "callout", "text2", h=18)
        cv.text(ix, y + 48, sub, "monos", "text3", h=16)
    y += 78
    table_w = 330
    cw = xr - x - table_w - 32
    legend(
        cv,
        x + 46,
        y,
        [
            ("B-1", L("当前", "current"), "cur", None),
            ("A-1", L("基准", "baseline"), "base", [5, 3]),
            (L("T30 拟合", "T30 fit"), None, "d2", [4, 3]),
        ],
    )
    y += 22
    avail = H - 22 - y
    h1 = int(avail * 0.56)
    p = Plot(
        cv,
        x,
        y,
        cw,
        h1,
        xkind="lin",
        xr=(0, 1.2),
        yr=(-70, 0),
        ystep=10,
        yminor=0,
        xticks=[0, 0.2, 0.4, 0.6, 0.8, 1.0, 1.2],
        ylabel=L("Schroeder 衰减（dB）", "Schroeder decay (dB)"),
        xlabel=L("时间（s）", "Time (s)"),
    )
    p.xtfmt = lambda v: f"{v:.1f}"
    p.frame()
    p.yband(-35, -5, "accent", 0.07, None)
    cv.text(
        p.X(0.42),
        p.Y(-5) + 4,
        L("T30 评估区 −5…−35 dB", "T30 range −5…−35 dB"),
        "caption",
        "accent.text",
        h=14,
    )
    p.hatch(bb["truncation_time_s"], 1.2, None)
    tl = L("截断后 · 未参与分析 →", "After truncation · not analysed →")
    cv.text(
        p.X(bb["truncation_time_s"]) - tw(tl, "caption") - 6, p.Y(-40), tl, "caption", "text3", h=14
    )
    p.curve(DEMO["edc_t_a"], DEMO["edc_db_a"], "base", 1.5, dash=[5, 3])
    p.curve(DEMO["edc_t_b"], DEMO["edc_db_b"], "cur", 2.0)
    t30 = bb["t30"][0]
    t5 = float(np.interp(-5, DEMO["edc_db_b"][::-1], DEMO["edc_t_b"][::-1]))
    t35 = t5 + t30 * 30 / 60
    p.curve([t5, t5 + t30 * 65 / 60], [-5, -70], C("d2", 0.45), 1.0, dash=[4, 3])
    p.curve([t5, t35], [-5, -35], "d2", 1.5, dash=[4, 3])
    for tt, dd in ((t5, -5), (t35, -35)):
        cv.circle(p.X(tt), p.Y(dd), 3, fill="plot.bg", stroke="d2", sw=1.5)
    y2 = y + h1 + 14
    h2 = avail - h1 - 14
    q = Plot(
        cv,
        x,
        y2,
        cw,
        h2,
        xkind="log",
        xr=(44, 11300),
        yr=(0, 1.0),
        ystep=0.2,
        yminor=0.1,
        ylabel=L("混响时间（s）", "RT (s)"),
        xlabel=L("频带中心（Hz）", "Band centre (Hz)"),
        yfmt=lambda v: f"{v:.1f}",
    )
    octave_frame(q)
    for pos, col, dash, sw_ in (("a", "base", [5, 3], 1.5), ("b", "cur", None, 2.0)):
        prev = None
        for c, bd in zip(CENTERS, N[f"bands_{pos}"]):
            v, val = bd["t30"][:2]
            X, Y = q.X(c), q.Y(v)
            if val == "valid":
                if prev:
                    cv.path([prev, (X, Y)], col, sw=sw_, dash=dash)
                cv.circle(X, Y, 3.2, fill=col if pos == "b" else "plot.bg", stroke=col, sw=1.5)
                prev = (X, Y)
            else:
                cv.circle(X, Y, 3.6, fill="plot.bg", stroke=col, sw=1.5)
                prev = None
    cv.text(
        q.px + 8,
        q.py + 4,
        L(
            "T30 · 实心 = 有效，空心 = 非有效（显示但不可信）",
            "T30 · filled = VALID, hollow = not VALID",
        ),
        "caption",
        "text3",
        h=14,
    )
    tx = xr - table_w
    cv.text(tx, y - 22, L("分频带 · B-1", "Per band · B-1"), "headline", "text1", h=18)
    cols = [
        (tr("Band"), 70, "l"),
        ("EDT", 64, "r"),
        ("T20", 64, "r"),
        ("T30", 64, "r"),
        ("C50", 68, "r"),
    ]
    rows = [
        [
            (L("宽带", "Broadband"), "text1", "calloutm"),
            val_text(bb["edt"][0], bb["edt"][1]),
            val_text(bb["t20"][0], bb["t20"][1]),
            val_text(bb["t30"][0], bb["t30"][1]),
            val_text(bb["c50"][0], bb["c50"][1], 1, "", True),
        ]
    ]
    for b in N["bands_b"]:
        rows.append(
            [
                (mid_hz(b["hz"]), "text1", "callout"),
                val_text(*b["edt"][:2]),
                val_text(*b["t20"][:2]),
                val_text(*b["t30"][:2]),
                val_text(*b["c50"][:2], 1, "", True),
            ]
        )
    ty = table(cv, tx, y + 2, cols, rows, rh=29)
    ty += 10
    bad = [mid_hz(b["hz"]) for b in N["bands_b"] if b["edt"][1] != "valid"]
    reason = next(b["edt"][2] for b in N["bands_b"] if b["edt"][1] != "valid")
    cv.icon("triangle-alert", tx, ty + 2, 14, "warn")
    s = L(
        f"括号 = 显示但不可信。{'、'.join(bad)} 的 EDT：衰减曲线在直达声处下降超过 5 dB，EDT 描述的是直达声而非房间。",
        f"Brackets = shown, not trusted. EDT at {', '.join(bad)}: the curve drops >5 dB across the direct sound.",
    )
    sh_ = cv.wrap_h(s, "caption", table_w - 20)
    cv.text(tx + 20, ty, s, "caption", "text2", w=table_w - 20, h=sh_ + 2, wrap=True, valign="t")


# ------------------------------------------------------------------ 15 noise
def noise(cv: Canvas):
    W, H = cv.W, cv.H
    x0 = frame(cv, "spectral")
    x, xr = x0 + 32, W - 32
    nb = N["noise_b"]
    y = header(
        cv,
        x,
        xr,
        tr("Background noise"),
        L(
            f"Welch 功率谱密度 · 扫频前片段 {nb['segment_start_s']:.2f}–{nb['segment_start_s'] + nb['segment_duration_s']:.2f} s · B-1 当前 · A-1 基准",
            "Welch PSD of the quiet pre-sweep segment · B-1 vs A-1",
        ),
    )
    sub = [tr(e) for _, e in SPECTRAL]
    sw_ = lk.segmented(cv, x, y, sub, 2, pad=12)
    chart_tools(cv, xr, y)
    y += 40
    side = 280
    cw = xr - x - side - 28
    legend(
        cv,
        x + 46,
        y,
        [
            ("B-1", L("当前", "current"), "cur", None),
            ("A-1", L("基准", "baseline"), "base", [5, 3]),
            (L("交流声谐波", "hum harmonics"), "50 Hz", "d2", None),
        ],
    )
    y += 22
    ch = H - 16 - 28 - 12 - y
    p = Plot(
        cv,
        x,
        y,
        cw,
        ch,
        xr=(20, 20000),
        yr=(-170, -60),
        ystep=20,
        yminor=10,
        ylabel=L("PSD（dB re FS²/Hz）", "PSD (dB re FS²/Hz)"),
        xlabel=L("频率（Hz）", "Frequency (Hz)"),
    )
    p.frame()
    for pos, col, dash, sw_ in (("a", "base", [5, 3], 1.25), ("b", "cur", None, 1.5)):
        f = DEMO[f"psd_f_{pos}"]
        d = DEMO[f"psd_db_{pos}"]
        m = f >= 20
        fl, dl = f[m], d[m]
        # peak-preserving decimation onto a log grid (display.curves.peak_subset in the app)
        g = np.logspace(math.log10(20), math.log10(20000), 900)
        idx = np.searchsorted(fl, g)
        out, lo_ = [], 0
        for hi in idx:
            seg = dl[lo_ : max(hi, lo_ + 1)]
            out.append(seg.max() if seg.size else np.nan)
            lo_ = hi
        p.curve(g, np.array(out), col, sw_, dash=dash)
    for hz, prom in nb["hum"][0]["harmonics"]:
        f = DEMO["psd_f_b"]
        lvl = float(np.interp(hz, f, DEMO["psd_db_b"]))
        X, Y = p.X(hz), p.Y(lvl)
        cv.circle(X, Y, 4.5, fill="plot.bg", stroke="d2", sw=1.75)
        cv.text(X + 7, Y - 16, f"{hz:g} Hz · +{prom:.0f} dB", "monos", "d2", h=14)
    sx = xr - side
    yy = y - 22
    cv.text(sx, yy, L("电平 · B-1", "Levels · B-1"), "headline", "text1", h=18)
    yy += 28
    for k, v in (
        (L("RMS", "RMS"), f"{mnum(nb['rms_dbfs'], 1)} dBFS"),
        (L("峰值", "Peak"), f"{mnum(nb['peak_dbfs'], 1)} dBFS"),
        (
            L("片段", "Segment"),
            L(
                f"扫频前 · {nb['segment_duration_s']:.2f} s",
                f"pre-sweep · {nb['segment_duration_s']:.2f} s",
            ),
        ),
    ):
        cv.text(sx, yy, k, "callout", "text2", h=24)
        cv.text(sx, yy, v, "mono", "text1", w=side, h=24, align="r")
        yy += 24
    yy += 8
    cv.rect(sx, yy, side, 40, fill="sunken", r=8)
    cv.text(
        sx + 10,
        yy + 4,
        L("未校准：电平为 dBFS，不是 dB SPL。", "Uncalibrated: dBFS, not dB SPL."),
        "caption",
        "text2",
        w=side - 20,
        h=16,
    )
    cv.text(
        sx + 10,
        yy + 20,
        L("NC / NR / dB(A) 未实现。", "NC / NR / dB(A): not implemented."),
        "caption",
        "text3",
        w=side - 20,
        h=16,
    )
    yy += 54
    cv.text(sx, yy, L("倍频程电平（dBFS）", "Octave levels (dBFS)"), "captionm", "text3", h=16)
    yy += 20
    na = {b: v for b, v in N["noise_a"]["bands"]}
    rows = [[(mid_hz(b), "text1", "callout"), mnum(v, 1), mnum(na[b], 1)] for b, v in nb["bands"]]
    yy = table(cv, sx, yy, [(tr("Band"), 90, "l"), ("B-1", 95, "r"), ("A-1", 95, "r")], rows, rh=23)
    yy += 10
    cv.icon("triangle-alert", sx, yy + 2, 14, "warn")
    s = L(
        "50 Hz 倍频交流声（50/100/150 Hz）。先查接地、线材、调光器和电源。",
        "Mains hum at 50/100/150 Hz. Check grounding, cables, dimmers first.",
    )
    hh = cv.wrap_h(s, "caption", side - 20)
    cv.text(sx + 20, yy, s, "caption", "text2", w=side - 20, h=hh + 2, wrap=True, valign="t")
    hz0 = 50.0
    readout(
        cv,
        x,
        H - 16 - 28,
        xr - x,
        [
            ("50.0 Hz", "text1"),
            (f"B-1 {mnum(float(np.interp(hz0, DEMO['psd_f_b'], DEMO['psd_db_b'])), 1)} dB", "cur"),
            (f"A-1 {mnum(float(np.interp(hz0, DEMO['psd_f_a'], DEMO['psd_db_a'])), 1)} dB", "base"),
        ],
    )


# ------------------------------------------------------------------ 16 spectrogram
def spectrogram_view(cv: Canvas):
    W, H = cv.W, cv.H
    x0 = frame(cv, "spectral")
    x, xr = x0 + 32, W - 32
    y = header(
        cv,
        x,
        xr,
        L("时频谱：B-1", "Spectrogram: B-1"),
        L(
            "短时功率谱 · 1 kHz 对数网格，每倍频程 48 点 · 时间相对直达声",
            "Short-time power spectrum · 48 points/octave · time re direct sound",
        ),
    )
    sub = [tr(e) for _, e in SPECTRAL]
    sw_ = lk.segmented(cv, x, y, sub, 0, pad=12)
    chart_tools(cv, xr, y)
    y += 40
    xx = x
    for lab, v in (
        (tr("Window"), "20.0 ms"),
        (tr("Step"), "2.0 ms"),
        (tr("Time"), "500 ms"),
        (tr("Frequency"), "20 – 20000 Hz"),
        (tr("Levels"), tr("re peak")),
        (L("底限", "Floor"), "−80 dB"),
    ):
        if xx + tw(lab, "callout") + tw(v, "mono") + 60 > xr - 10:
            break
        xx += spin(cv, xx, y, lab, v)
    y += 44
    ch = H - 16 - 28 - 14 - y
    cbw = 60
    p = Plot(
        cv,
        x,
        y,
        xr - x - cbw,
        ch,
        xkind="lin",
        xr=(-4, 500),
        yr=(0, 1),
        ystep=1,
        yminor=0,
        xticks=[0, 50, 100, 150, 200, 250, 300, 350, 400, 450, 500],
        ylabel=L("频率（Hz）", "Frequency (Hz)"),
        xlabel=L("直达声之后的时间（ms）", "Time after direct sound (ms)"),
        yfmt=lambda v: "",
    )
    p.xtfmt = lambda v: f"{v:g}"
    p.frame()
    t = DEMO["sg_times_ms"]
    f = DEMO["sg_freqs_hz"]
    lv = DEMO["sg_levels_db"]
    m = t <= 500
    t, lv = t[m], lv[m]
    # draw as image (pixel per bin) clipped to plot
    from PySide6.QtGui import QImage
    from PySide6.QtCore import QRectF

    fm = (f >= 20) & (f <= 20000)
    ff, L2 = f[fm], lv[:, fm]
    img = QImage(len(t), len(ff), QImage.Format.Format_RGB32)
    floor = -80.0
    stops = (
        ["#FFFFFF", "#DDEFF0", "#9FD3D6", "#4FA9B3", "#177E89", "#0F4F60", "#1D1B18"]
        if lk.MODE["theme"] == "light"
        else ["#181715", "#1B3438", "#1F5A62", "#2F8C96", "#4FB6C3", "#A7E0E6", "#F4FBFC"]
    )
    for i in range(len(t)):
        for j in range(len(ff)):
            v = (max(L2[i, j], floor) - floor) / -floor
            img.setPixelColor(i, len(ff) - 1 - j, ramp(v, stops))
    yt = lambda hz: (
        p.py
        + p.ph
        - (math.log10(hz) - math.log10(20)) / (math.log10(20000) - math.log10(20)) * p.ph
    )
    x_a, x_b = p.X(t[0]), p.X(t[-1])
    cv.p.save()
    cv.p.setClipRect(QRectF(p.px, p.py, p.pw, p.ph))
    cv.p.drawImage(QRectF(x_a, p.py, x_b - x_a, p.ph), img)
    cv.p.restore()
    for hz in (20, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000):
        Y = yt(hz)
        cv.hline(p.px, p.px + 4, Y, "axis")
        cv.text(
            p.ox,
            Y - 8,
            lcharts.fmt_hz(hz),
            "monos",
            "plot.text",
            w=p.px - p.ox - 6,
            h=16,
            align="r",
        )
    cv.rect(p.px, p.py, p.pw, p.ph, stroke="grid.major")
    rc = N["resonances_b"][0]["frequency_hz"]
    cv.line(p.px, yt(rc), p.px + p.pw, yt(rc), C("d2", 0.9), 1, dash=[4, 3])
    cv.text(
        p.X(300),
        yt(rc) - 16,
        L(f"共振候选 {rc:.0f} Hz：衰减明显慢于周围", f"resonance candidate {rc:.0f} Hz"),
        "caption",
        "d2",
        h=14,
    )
    # colour bar (vertical)
    bx = xr - cbw + 20
    from PySide6.QtGui import QLinearGradient, QBrush, QColor

    g = QLinearGradient(0, p.py + p.ph, 0, p.py)
    for i, s in enumerate(stops):
        g.setColorAt(i / (len(stops) - 1), QColor(s))
    cv.p.fillRect(QRectF(bx, p.py, 10, p.ph), QBrush(g))
    cv.rect(bx, p.py, 10, p.ph, stroke="grid.major")
    cv.text(bx + 14, p.py - 4, "0", "monos", "plot.text", h=14)
    cv.text(bx + 14, p.py + p.ph - 10, "−80", "monos", "plot.text", h=14)
    cv.text(bx - 4, p.py + p.ph + 4, "dB", "monos", "plot.text", h=14)
    lvl = float(np.interp(math.log10(rc), np.log10(ff), L2[int(np.argmin(np.abs(t - 120)))]))
    readout(
        cv,
        x,
        H - 16 - 28,
        xr - x,
        [("120.0 ms", "text1"), (f"{rc:.1f} Hz", "text1"), (f"{mnum(lvl, 1)} dB", "text1")],
        L(
            "计算在后台线程，参数改动后重新计算 · 滚轮缩放",
            "Computed off the GUI thread; recomputed after a change",
        ),
    )


# ------------------------------------------------------------------ 07 waterfall (real controls)
def waterfall(cv: Canvas):
    W, H = cv.W, cv.H
    x0 = frame(cv, "spectral")
    x, xr = x0 + 32, W - 32
    y = header(
        cv,
        x,
        xr,
        L("瀑布图：B-1", "Waterfall: B-1"),
        L(
            "累积频谱衰减 · 各切片相对第一切片峰值 · 透视为显示效果，CSV 导出时去掉",
            "Cumulative spectral decay · dB re first slice peak · perspective is display-only",
        ),
    )
    sub = [tr(e) for _, e in SPECTRAL]
    lk.segmented(cv, x, y, sub, 1, pad=12)
    chart_tools(cv, xr, y)
    y += 40
    xx = x
    for lab, v in (
        (tr("Window"), "300 ms"),
        (tr("Rise"), "0.5 ms"),
        (tr("Step"), "10.0 ms"),
        (tr("Slices"), "30"),
        (tr("Frequency"), "20 – 20000 Hz"),
    ):
        xx += spin(cv, xx, y, lab, v)
    sm = L("1/12 倍频程", "1/12 octave")
    if xx + tw(sm, "callout") + 40 < xr - 140:
        lk.popup(cv, xx, y, tw(sm, "callout") + 40, sm, role="callout")
        xx += tw(sm, "callout") + 54
    if xx + 80 < xr - 140:
        xx += label_check(cv, xx, y, tr("Perspective"), on=True)
    colorbar(cv, xr - 140, y + 11, 110, "0", f"{DEMO['wf_times_ms'][-1]:.0f}", "ms")
    y += 44
    f = DEMO["wf_freqs_hz"]
    t = DEMO["wf_times_ms"]
    lv = DEMO["wf_levels_db"]
    lf = np.log2(f)
    sm_ = np.empty_like(lv)
    for j in range(len(f)):
        msk = np.abs(lf - lf[j]) <= 1 / 24
        sm_[:, j] = 10 * np.log10(np.mean(10 ** (lv[:, msk] / 10), axis=1))
    lv = sm_
    bottom = H - 16 - 28 - 40
    p = Plot(
        cv,
        x,
        y,
        xr - x,
        bottom - y,
        xr=(20, 20000),
        yr=(-60, 10),
        ystep=10,
        yminor=5,
        ylabel=L("电平（dB，相对第一切片峰值）", "Level (dB re first slice peak)"),
        xlabel=L("频率（Hz）", "Frequency (Hz)"),
    )
    p.frame()
    n = len(t)
    sel = int(np.argmin(np.abs(t - 100)))
    dx = (
        0.0045  # perspective: later slices shifted right (log10 decades) and up (dB) — display only
    )
    dyy = 0.25
    for i in range(n - 1, -1, -1):
        col = ramp(i / max(1, n - 1))
        col.setAlphaF(0.9)
        p.curve(f * 10 ** (dx * i), np.maximum(lv[i], -61) + dyy * i, col, 1.1)
    p.curve(f * 10 ** (dx * sel), np.maximum(lv[sel], -61) + dyy * sel, "cursor", 2.4)
    p.hatch(18, 30.6)
    p.hatch(19725.6, 21000)
    rc = N["resonances_b"][0]["frequency_hz"]
    v = float(np.interp(math.log10(rc), np.log10(f), lv[sel]))
    p.cursor(rc * 10 ** (dx * sel), dots=[(v + dyy * sel, "cursor", True)], flag=f"{rc:.1f} Hz")
    # slice selector (WaterfallView: Slice spin)
    ys = bottom + 6
    cv.text(x, ys, tr("Slice"), "callout", "text2", h=28)
    sx = x + tw(tr("Slice"), "callout") + 8
    cv.rect(sx, ys, 180, 28, fill="surface", stroke="border", r=7)
    cv.icon("chevron-left", sx + 6, ys + 6, 16, "text2")
    cv.text(
        sx + 24, ys, f"{sel + 1} / {n} · {t[sel]:.1f} ms", "mono", "text1", w=132, h=28, align="c"
    )
    cv.icon("chevron-right", sx + 158, ys + 6, 16, "text2")
    sx += 20
    pk = int(np.argmax(np.where((f > 30) & (f < 19000), lv[sel], -999)))
    cv.text(
        sx + 176,
        ys,
        L(
            f"{t[sel]:.1f} ms：峰值 {mnum(lv[sel][pk], 1)} dB，位于 {lcharts.fmt_hz(round(f[pk]))} Hz",
            f"{t[sel]:.1f} ms: peak {mnum(lv[sel][pk], 1)} dB at {lcharts.fmt_hz(round(f[pk]))} Hz",
        ),
        "callout",
        "text2",
        h=28,
        w=xr - sx - 180,
    )
    readout(
        cv,
        x,
        H - 16 - 28,
        xr - x,
        [
            (f"{t[sel]:.1f} ms", "text1"),
            (f"{rc:.1f} Hz", "text1"),
            (f"{mnum(v, 1)} dB", "text1"),
            (
                L(
                    "共振候选：窄带 20 dB 衰减 278 ms，周围 104 ms",
                    "Resonance candidate: 278 ms vs 104 ms around",
                ),
                "text2",
            ),
        ],
    )


# ------------------------------------------------------------------ 17 room (3D, as in ui/room)
def _proj(cam, pt):
    """Simple orbit projection (yaw, pitch, scale, centre)."""
    yaw, pitch, s, cx, cy, ctr = cam
    x, y, z = pt[0] - ctr[0], pt[1] - ctr[1], pt[2] - ctr[2]
    cyw, syw = math.cos(yaw), math.sin(yaw)
    x1, y1 = x * cyw - y * syw, x * syw + y * cyw
    cp, sp = math.cos(pitch), math.sin(pitch)
    y2, z2 = y1 * cp - z * sp, y1 * sp + z * cp
    return (cx + x1 * s, cy - z2 * s)


def room(cv: Canvas):
    W, H = cv.W, cv.H
    x0 = frame(
        cv,
        "room",
        sel="a1",
        title="A-1",
        sub=L("合成演示房间 · 位置 A", "Synthetic demo room · Position A"),
    )
    x, xr = x0 + 24, W - 24
    t = TX()
    y = header(
        cv,
        x,
        xr,
        tr("Room"),
        L(
            "输入的房间 · 测量约束 · 几何假设 —— 一支全指向话筒给不出坐标",
            "Entered room · measured constraint · geometric assumption — one omni mic gives no coordinates",
        ),
    )
    xx = x
    for i, lab in enumerate((tr("Plan view"), tr("Front"), tr("Side"))):
        w_ = tw(lab, "callout") + 22
        cv.rect(xx, y, w_, 28, stroke="border", r=7, fill="surface")
        cv.text(xx, y, lab, "callout", "text1", w=w_, h=28, align="c")
        xx += w_ + 6
    xx += 6
    for ic, lab, k in (("maximize", tr("Frame"), "F"), ("rotate-ccw", tr("Reset view"), "R")):
        w_ = tw(lab, "callout") + 30 + 26
        cv.rect(xx, y, w_, 28, stroke="border", r=7)
        cv.icon(ic, xx + 8, y + 6, 16, "text2")
        cv.text(xx + 30, y, lab, "callout", "text1", h=28)
        lk.kbd(cv, xx + w_ - 22, y + 5, k)
        xx += w_ + 8
    rp = tr("Room parameters")
    lk.button(
        cv,
        xr - tw(rp, "callout") - 50,
        y,
        rp,
        "secondary",
        icon="sliders-vertical",
        h=28,
        role="callout",
    )
    y += 38
    xx = x
    for lab, on in (
        (tr("Entered"), True),
        (tr("Measured constraint"), True),
        (tr("Geometric assumption"), True),
        (tr("All constraints"), False),
    ):
        xx += label_check(cv, xx, y, lab, on)
    ib = tr("Import scan...")
    eb = tr("Example room")
    wb = tw(eb, "callout") + 24
    lk.button(cv, xr - wb, y, eb, "secondary", h=28, role="callout")
    lk.button(
        cv,
        xr - wb - 8 - (tw(ib, "callout") + 46),
        y,
        ib,
        "secondary",
        icon="scan",
        h=28,
        role="callout",
    )
    y += 40
    side = 320
    cw = xr - x - side - 24
    ch = H - 14 - y
    cv.rect(x, y, cw, ch, fill="plot.bg", stroke="sep", r=10)
    box = t["room_box"]
    src = t["room_source"]
    mic = t["room_mics"]["A"]
    Lx, Wy, Hz = box["length_m"], box["width_m"], box["height_m"]
    s = min(cw, ch) / 8.8
    cam = (
        math.radians(-35),
        math.radians(62),
        s,
        x + cw / 2,
        y + ch / 2 + 6,
        (Lx / 2, Wy / 2, Hz / 2),
    )
    P = lambda q: _proj(cam, q)
    corners = [(a, b, c) for a in (0, Lx) for b in (0, Wy) for c in (0, Hz)]
    # floor grid
    for gx in np.arange(0, Lx + 0.01, 1.0):
        a, b = P((gx, 0, 0)), P((gx, Wy, 0))
        cv.line(*a, *b, "grid.minor", 1)
    for gy in np.arange(0, Wy + 0.01, 1.0):
        a, b = P((0, gy, 0)), P((Lx, gy, 0))
        cv.line(*a, *b, "grid.minor", 1)
    edges = [
        (i, j)
        for i in range(8)
        for j in range(i + 1, 8)
        if sum(1 for k in range(3) if corners[i][k] != corners[j][k]) == 1
    ]
    for i, j in edges:
        a, b = P(corners[i]), P(corners[j])
        cv.line(*a, *b, "text3", 1.25)  # entered layer: solid
    # assumption layer: predicted first-order paths (dashed)
    for k, pp in enumerate(t["room_predicted"]):
        pt = pp["point"]
        q = (pt["x"], pt["y"], pt["z"])
        a, b, c = P((src["x"], src["y"], src["z"])), P(q), P((mic["x"], mic["y"], mic["z"]))
        col = C("d3", 0.75)
        cv.line(*a, *b, col, 1, dash=[3, 3])
        cv.line(*b, *c, col, 1, dash=[3, 3])
        cv.circle(*b, 2.5, fill=col)
    # measured constraint: ellipsoid of the 2.40 ms reflection (foci source, mic)
    con = t["room_constraints"][0]
    a_ = con["semi_major_m"]
    b_ = con["semi_minor_m"]
    F1 = np.array([src["x"], src["y"], src["z"]])
    F2 = np.array([mic["x"], mic["y"], mic["z"]])
    ctr = (F1 + F2) / 2
    ax = (F2 - F1) / np.linalg.norm(F2 - F1)
    tmp = np.array([0, 0, 1.0])
    u = np.cross(ax, tmp)
    u /= np.linalg.norm(u)
    v = np.cross(ax, u)
    for k in range(6):
        th = k * math.pi / 6
        pts = []
        for i in range(73):
            ph = i * 2 * math.pi / 72
            q = (
                ctr
                + ax * a_ * math.cos(ph)
                + (u * math.cos(th) + v * math.sin(th)) * b_ * math.sin(ph)
            )
            pts.append(P(q))
        cv.path(pts, C("d2", 0.55), sw=1.0)
    pts = []
    for i in range(73):
        ph = i * 2 * math.pi / 72
        q = ctr + (u * math.cos(ph) + v * math.sin(ph)) * b_
        pts.append(P(q))
    cv.path(pts, C("d2", 0.8), sw=1.25)
    # devices
    sp = P((src["x"], src["y"], src["z"]))
    mp = P((mic["x"], mic["y"], mic["z"]))
    cv.line(*sp, *mp, C("text2", 0.6), 1)
    cv.rect(sp[0] - 7, sp[1] - 9, 14, 18, fill="cur", r=3)
    cv.text(sp[0] - 60, sp[1] + 12, tr("Loudspeaker"), "caption", "text2", w=120, h=14, align="c")
    cv.circle(*mp, 6, fill="surface", stroke="cur", sw=2)
    cv.text(
        mp[0] - 60,
        mp[1] + 10,
        L("话筒 A", "Microphone A"),
        "caption",
        "text2",
        w=120,
        h=14,
        align="c",
    )
    # legend
    lx, ly = x + 14, y + 12
    for lab, col, dash in (
        (tr("Entered"), "text3", None),
        (
            L("测量约束：2.40 ms 反射的椭球", "Measured: ellipsoid of the 2.40 ms reflection"),
            "d2",
            None,
        ),
        (L("几何假设：一阶镜面路径", "Assumption: first-order specular paths"), "d3", [3, 3]),
    ):
        cv.line(lx, ly + 8, lx + 18, ly + 8, col, 1.5, dash=dash)
        cv.text(lx + 24, ly, lab, "caption", "text2", h=16)
        ly += 18
    cv.text(
        x + 14,
        y + ch - 24,
        L(
            "左键拖动环绕 · 右键/中键平移 · 滚轮缩放 · F 取景 · R 复位（ui/room/canvas.py）",
            "Left-drag orbit · right/middle-drag pan · wheel zoom · F frame · R reset",
        ),
        "caption",
        "text3",
        h=16,
        w=cw - 28,
    )
    # side panel: room box, devices, reflections, placement, checks
    sx = xr - side
    yy = y
    cv.text(sx, yy, tr("Room box (inside, metres)"), "captionm", "text3", h=16)
    yy += 20
    for k, val in (
        (tr("Length (x)") if False else L("长（x）", "Length (x)"), f"{Lx:.2f} m"),
        (L("宽（y）", "Width (y)"), f"{Wy:.2f} m"),
        (L("高（z）", "Height (z)"), f"{Hz:.2f} m"),
    ):
        cv.text(sx, yy, k, "callout", "text2", h=22)
        cv.text(sx, yy, val, "mono", "text1", w=side, h=22, align="r")
        yy += 22
    cv.text(sx, yy, tr("Loudspeaker"), "callout", "text2", h=22)
    cv.text(
        sx,
        yy,
        f"({src['x']:.2f}, {src['y']:.2f}, {src['z']:.2f}) m",
        "mono",
        "text1",
        w=side,
        h=22,
        align="r",
    )
    yy += 22
    cv.text(sx, yy, L("话筒 A", "Microphone A"), "callout", "text2", h=22)
    cv.text(
        sx,
        yy,
        f"({mic['x']:.2f}, {mic['y']:.2f}, {mic['z']:.2f}) m",
        "mono",
        "text1",
        w=side,
        h=22,
        align="r",
    )
    yy += 30
    cv.text(
        sx,
        yy,
        tr("Early reflections").upper() if not lk.zh() else tr("Early reflections"),
        "captionm",
        "text3",
        h=16,
    )
    yy += 18
    rows = []
    for d, lv in N["reflections_a"]:
        rows.append(
            [
                f"{d:.2f}",
                mnum(lv, 1),
                (
                    L("早于预测", "earlier than predicted")
                    if d < t["room_predicted"][0]["delay_ms"] - 0.2
                    else L("可能：地面 / 顶面", "maybe floor/ceiling"),
                    "text2",
                    "caption",
                ),
            ]
        )
    yy = table(
        cv,
        sx,
        yy,
        [
            (L("延迟 ms", "Delay ms"), 70, "r"),
            (L("电平 dB", "Level dB"), 70, "r"),
            (L("匹配", "Match"), side - 140, "l"),
        ],
        rows,
        rh=26,
    )
    yy += 12
    cv.text(sx, yy, tr("Placement"), "captionm", "text3", h=16)
    yy += 18
    rows = [
        [
            (L("扬声器高度", "Loudspeaker height"), "text1", "callout"),
            "–",
            (L("未确定", "not determined"), "text3", "caption"),
        ],
        [
            (L("设备上方平面", "Plane above"), "text1", "callout"),
            "–",
            (L("未确定", "not determined"), "text3", "caption"),
        ],
    ]
    yy = table(
        cv,
        sx,
        yy,
        [
            (L("项", "Figure"), 130, "l"),
            (L("值", "Value"), 60, "r"),
            (L("有效性", "Validity"), side - 190, "l"),
        ],
        rows,
        rh=24,
        zebra=False,
    )
    s = L(
        "档位 0：添加扬声器距离（卷尺）可提高档位。",
        "Tier 0: add a loudspeaker distance to raise the tier.",
    )
    cv.text(sx, yy + 2, s, "caption", "text3", w=side, h=16)
    yy += 26
    cv.text(sx, yy, tr("Room checks"), "captionm", "text3", h=16)
    yy += 20
    for c in t["room_checks"][:6]:
        if yy > H - 40:
            break
        ic, col = {"ok": ("circle-check", "good"), "warn": ("triangle-alert", "warn")}.get(
            c["status"], ("circle-dashed", "text3")
        )
        th = min(cv.wrap_h(c["text"], "caption", side - 22), 30)
        cv.icon(ic, sx, yy + 2, 14, col)
        cv.text(
            sx + 22,
            yy,
            c["text"],
            "caption",
            "text2",
            w=side - 22,
            h=th + 2,
            wrap=True,
            valign="t",
            check=False,
        )
        yy += th + 6


# ------------------------------------------------------------------ 18 project
def project(cv: Canvas):
    W, H = cv.W, cv.H
    nar = narrow()
    if not nar:
        sh.sidebar(cv, sel=None)
        cv.rect(10, 96 + 32 + 16 + 24, SB - 20, 30, fill="sel.sidebar", r=6)
        cv.icon("folder-open", 20, 96 + 32 + 16 + 24 + 7, 16, "text2")
        cv.text(
            44, 96 + 32 + 16 + 24, L("合成演示房间", "Synthetic demo room"), "bodym", "text1", h=30
        )
    x0 = 0 if nar else SB
    sh.toolbar(
        cv,
        x0,
        tr("Project"),
        L("合成演示房间 · 2 个位置 · 2 个会话", "Synthetic demo room · 2 positions · 2 sessions"),
        traffic=nar,
    )
    rx = W - 16 - 32
    sh.tool_icon(cv, rx, 11, "panel-right")
    x, xr = x0 + 32, W - 32
    t = TX()
    y = header(
        cv,
        x,
        xr,
        L("合成演示房间", "Synthetic demo room"),
        L(
            "一个房间、多个话筒位置；会话仍是独立文件夹（project.json）",
            "One room, several mic positions; sessions stay folders (project.json)",
        ),
    )
    xx = x
    xx += label_popup(cv, xx, y, tr("Profile"), L("人声", "Vocals"), 100)
    xx += spin(cv, xx, y, tr("Source positions"), "1")
    for lab in (tr("Copy overview"), tr("Add Session..."), tr("Compare with first position")):
        xx += lk.button(cv, xx, y, lab, "secondary", h=28, role="callout") + 8
    mp = tr("Measure a new position...")
    lk.button(cv, xr - tw(mp, "calloutm") - 24, y, mp, "primary", h=28, role="calloutm")
    y += 44
    cv.text(x, y, tr("POSITIONS"), "captionm", "text3", h=18)
    y += 22
    pw = (xr - x - 16) / 2
    for i, ps in enumerate(t["overview_positions"]):
        px = x + i * (pw + 16)
        cv.rect(px, y, pw, 84, fill="surface", stroke="sep", r=10)
        cv.text(
            px + 14,
            y + 10,
            L(f"位置 {ps['label']}", f"Position {ps['label']}"),
            "headline",
            "text1",
            h=20,
        )
        fit = L("人声配置：有警告", "Vocals: warnings") if ps["fit"] == "warnings" else ps["fit"]
        lk.chip(
            cv,
            px + pw - tw(fit, "caption") - 34,
            y + 10,
            fit,
            icon="triangle-alert",
            tone="warn",
            h=20,
            role="caption",
        )
        cv.text(
            px + 14,
            y + 34,
            f"RT60 {ps['rt60']:.2f} s ({ps['rt60_basis']}) · C50 {mnum(ps['clarity'][1], 1, True)} dB · {mnum(ps['noise'], 1)} dBFS",
            "mono",
            "text1",
            h=18,
            w=pw - 28,
        )
        cv.text(px + 14, y + 56, ps["verdict_text"], "caption", "text2", h=18, w=pw - 28)
    y += 100
    cv.text(x, y, tr("TAKES"), "captionm", "text3", h=18)
    y += 20
    ww = xr - x
    cols = [
        (tr("Position"), ww * 0.08, "l"),
        (L("会话", "Session"), ww * 0.12, "l"),
        (L("时间", "When"), ww * 0.14, "l"),
        (tr("Health"), ww * 0.12, "l"),
        ("RT60", ww * 0.1, "r"),
        (tr("Clarity"), ww * 0.12, "r"),
        (tr("Noise"), ww * 0.12, "r"),
        (tr("Reflection"), ww * 0.12, "r"),
        (tr("Fit"), ww * 0.08, "l"),
    ]
    rows = []
    for ps in t["overview_positions"]:
        rows.append(
            [
                ps["label"],
                f"position-{ps['label'].lower()}",
                "2026-10-19 18:03",
                (L("警告 · 电平", "warning · level"), "warn", "callout"),
                f"{ps['rt60']:.2f} s",
                f"{mnum(ps['clarity'][1], 1, True)} dB",
                f"{mnum(ps['noise'], 1)} dBFS",
                f"{mnum(ps['reflection'][1], 1)} dB·{ps['reflection'][0]:.1f}ms",
                (L("警告", "warnings"), "warn", "callout"),
            ]
        )
    y = table(cv, x, y, cols, rows, rh=28)
    cv.text(
        x,
        y + 2,
        L(
            "双击一行打开该会话。健康和契合度在页面显示时判定。",
            "Double-click a take to open it. Health and fit are judged when the page is shown.",
        ),
        "caption",
        "text3",
        h=16,
    )
    y += 30
    lw = (xr - x - 28) * 0.55
    cv.text(x, y, tr("SPATIAL AVERAGE"), "captionm", "text3", h=18)
    av = t["average"]
    cls = L("ISO 3382-2：简易级（survey）", "ISO 3382-2: survey")
    lk.chip(cv, x + lw - tw(cls, "caption") - 20, y - 2, cls, h=20, role="caption")
    yy = y + 20
    cols = [
        (tr("Band"), lw * 0.2, "l"),
        ("EDT", lw * 0.2, "r"),
        ("T30", lw * 0.2, "r"),
        (L("T30 离散", "T30 spread"), lw * 0.24, "r"),
        ("n", lw * 0.16, "r"),
    ]
    rows = []
    for b in av["bands"][:6]:
        lab = (
            L("宽带", "Broadband")
            if b["band"] == "broadband"
            else b["band"].replace("1000 Hz", "1 kHz")
        )
        rows.append(
            [
                (lab, "text1", "callout"),
                f"{b['edt'][0]:.2f} s",
                f"{b['t30'][0]:.2f} s",
                f"±{b['t30'][1]:.2f} s",
                str(b["t30"][2]),
            ]
        )
    table(cv, x, yy, cols, rows, rh=24, maxy=H - 14)
    nx = x + lw + 28
    cv.text(nx, y, tr("NEXT"), "captionm", "text3", h=18)
    yy = y + 22
    for i, s in enumerate(t["overview_next_steps"]):
        hh = cv.wrap_h(s, "callout", xr - nx - 24)
        if yy + hh > H - 14:
            break
        cv.text(nx, yy, f"{i + 1}.", "callout", "text3", h=18)
        cv.text(nx + 20, yy, s, "callout", "text1", w=xr - nx - 24, h=hh + 2, wrap=True, valign="t")
        yy += hh + 10


# ------------------------------------------------------------------ 19 report + export
def report_export(cv: Canvas):
    W, H = cv.W, cv.H
    x0 = frame(cv, "report")
    x, xr = x0 + 32, W - 32
    t = TX()
    y = header(
        cv,
        x,
        xr,
        tr("Full report"),
        L(
            "与 reverbscope analyze 打印的报告相同；警告在末尾",
            "The same report reverbscope analyze prints; warnings at the end",
        ),
    )
    lk.button(cv, x, y, tr("Copy report"), "secondary", icon="copy", h=28, role="callout")
    y += 40
    side = 330
    tw_ = xr - x - side - 28
    cv.rect(x, y, tw_, H - 16 - y, fill="surface", stroke="sep", r=10)
    lines = t["report_b"].split("\n")
    yy = y + 12
    from PySide6.QtGui import QFontMetricsF

    for ln in lines:
        if yy > H - 34:
            break
        cv.text(
            x + 14,
            yy,
            ln,
            "monos",
            "text1" if not ln.startswith("  ") else "text2",
            w=tw_ - 28,
            h=16,
            check=False,
        )
        yy += 16
    sx = xr - side
    cv.text(sx, y, L("导出", "Export"), "headline", "text1", h=20)
    yy = y + 28
    items = [
        (
            "download",
            L("图表存为 PNG / SVG", "Chart as PNG / SVG"),
            L("每张图表 ▸ 导出", "Every chart ▸ Export"),
            "GUI",
        ),
        (
            "download",
            tr("Curves as CSV..."),
            L("所画曲线，注明所用平滑", "Drawn curves, smoothing noted"),
            "GUI",
        ),
        ("copy", tr("Copy report"), L("本页文字报告", "This text report"), "GUI"),
        (
            "save",
            L("保存会话…  ⌘S", "Save Session…  ⌘S"),
            "session.json · result.json · impulse_response.wav",
            "GUI",
        ),
        ("file-down", tr("Save comparison.json..."), L("在对比视图", "In Compare"), "GUI"),
        ("copy", tr("Copy overview"), L("在项目视图", "In Project"), "GUI"),
        (
            "file-text",
            "reverbscope export --format csv",
            L("结果中每条曲线和每张表", "Every curve and table of a result"),
            "CLI",
        ),
        (
            "file-down",
            "reverbscope session bundle [--no-audio]",
            L("会话打包为 zip，便于报告问题", "Zip a session for a bug report"),
            "CLI",
        ),
        (
            "stethoscope",
            "reverbscope doctor",
            L("环境报告（隐私：主目录已隐藏）", "Environment report (home folder redacted)"),
            "CLI",
        ),
    ]
    for ic, lab, sub, where in items:
        cv.icon(ic, sx, yy + 4, 16, "text2")
        cv.text(
            sx + 24, yy, lab, "callout" if where == "GUI" else "monos", "text1", h=18, w=side - 70
        )
        cv.text(sx + 24, yy + 18, sub, "caption", "text3", h=16, w=side - 70)
        lk.chip(
            cv,
            xr - (tw(where, "caption") + 20),
            yy + 4,
            where,
            h=18,
            tone="neutral" if where == "GUI" else "accent",
            role="caption",
        )
        yy += 42
    yy += 4
    cv.hline(sx, xr, yy, "sep")
    yy += 12
    cv.text(
        sx,
        yy,
        L("未实现（不画入口）", "Not implemented (no entry drawn)"),
        "captionm",
        "text3",
        h=16,
    )
    yy += 20
    s = L(
        "PDF / HTML 报告 · 一键“导出全部” · dB SPL 校准导出 · 在 GUI 里打包会话（目前仅 CLI）",
        "PDF / HTML report · one-click Export all · dB SPL calibrated export · session bundle from the GUI (CLI only today)",
    )
    hh = cv.wrap_h(s, "caption", side)
    cv.text(sx, yy, s, "caption", "text2", w=side, h=hh + 2, wrap=True, valign="t")


# ------------------------------------------------------------------ 20 health sheet
def health_sheet(cv: Canvas):
    W, H = cv.W, cv.H
    overview(cv)
    cv.rect(0, 0, W, H, fill=C("scrim", 0.28 if lk.MODE["theme"] == "light" else 0.5))
    t = TX()
    checks = t["health_b"]
    sw_ = min(720, W - 80)
    shh = min(620, H - 60)
    sx, sy = (W - sw_) / 2, (H - shh) / 2
    cv.shadow(sx, sy, sw_, shh, r=12, depth=30, alpha=0.30, dy=16)
    cv.rect(sx, sy, sw_, shh, fill="window", stroke=C("shadow", 0.15), r=12)
    cv.icon("heart-pulse", sx + 20, sy + 20, 20, "text2")
    cv.text(
        sx + 50, sy + 16, L("测量健康 · B-1", "Measurement health · B-1"), "title2", "text1", h=28
    )
    cv.icon("x", sx + sw_ - 36, sy + 22, 16, "text3")
    good = sum(1 for c in checks if c["status"] == "good")
    hs = t["health_b_status_word"]
    lk.chip(
        cv,
        sx + 20,
        sy + 54,
        f"{hs} · "
        + L(f"{len(checks)} 项检查中 {good} 项良好", f"{good} of {len(checks)} checks good"),
        icon="triangle-alert",
        tone="warn",
    )
    cv.text(
        sx + 20,
        sy + 84,
        L(
            "health.assess() 的检查，按代码顺序；问题检查给出原因、影响的指标和下一步。",
            "Checks from health.assess(), in code order; a problem check gives the reason, what it affects and the next step.",
        ),
        "caption",
        "text3",
        w=sw_ - 40,
        h=16,
    )
    yy = sy + 110
    cv.rect(sx + 20, yy, sw_ - 40, shh - (yy - sy) - 64, fill="surface", stroke="sep", r=10)
    yy += 4
    for i, c in enumerate(checks):
        ic, col = {
            "good": ("circle-check", "good"),
            "warning": ("triangle-alert", "warn"),
            "invalid": ("circle-x", "crit"),
        }.get(c["status"], ("circle-dashed", "text3"))
        rh = 38 if c["status"] == "good" else 96
        if i:
            cv.hline(sx + 36, sx + sw_ - 20, yy, "sep")
        if c["status"] != "good":
            cv.rect(sx + 21, yy + 1, sw_ - 42, rh - 2, fill="warn.soft")
        cv.icon(ic, sx + 36, yy + 11, 16, col)
        cv.text(sx + 62, yy + 2, c["title"], "bodym", "text1", h=34, w=150)
        cv.text(sx + 210, yy + 2, c["reason"], "callout", "text2", h=34, w=sw_ - 250, check=False)
        if c["status"] != "good":
            cv.text(
                sx + 62,
                yy + 36,
                L("下一步：", "Next: ") + c["fix"][0],
                "callout",
                "text1",
                w=sw_ - 110,
                h=20,
            )
            b = L("显示 总览", "Show Overview")
            cv.text(
                sx + 62,
                yy + 62,
                L(
                    "按钮“显示 <视图>”打开相关图表（ui/health_nav.py）；电平检查不对应某个图表时不显示按钮。",
                    "A “Show <view>” button opens the chart a check is about (ui/health_nav.py); none when no chart fits.",
                ),
                "caption",
                "text3",
                w=sw_ - 110,
                h=18,
            )
        yy += rh
        if yy > sy + shh - 80:
            break
    bw = tw(L("完成", "Done"), "bodym") + 32
    lk.button(cv, sx + sw_ - 20 - bw, sy + shh - 48, L("完成", "Done"), "primary", w=bw)
    lk.button(cv, sx + 20, sy + shh - 48, tr("Copy report"), "secondary", icon="copy")


# ------------------------------------------------------------------ 12 DAW path (4 steps)
def _daw_frame(cv, step, done=()):
    import lscreens as S0

    steps = [
        L("生成测试信号", "Test signal"),
        L("在 DAW 中录制", "Record in DAW"),
        L("导入录音", "Import"),
        L("分析", "Analyze"),
    ]
    return S0._measure_frame(cv, step, path_sel=1, steps=steps, done=done)


def _instruction_lines():
    return [ln for ln in TX()["daw_instructions"].split("\n") if ln.strip()]


def daw_signal(cv: Canvas):
    import lscreens as S0

    fx, fw, cx, cw = _daw_frame(cv, 0)
    y = TB + 84
    cv.text(
        fx,
        y,
        tr("Step 1 - Generate Test Signal").split(" - ")[-1].split("—")[-1].strip()
        if not lk.zh()
        else "生成测试信号",
        "title1",
        "text1",
        h=28,
    )
    cv.text(
        fx,
        y + 32,
        L(
            "按 DAW 工程的采样率生成扫频 WAV，旁边写一个 .reverbscope-sweep.json 说明文件。",
            "Write the sweep WAV at your DAW project's rate, with its .reverbscope-sweep.json sidecar.",
        ),
        "callout",
        "text2",
        w=fw,
        h=18,
    )
    y += 72

    def pop(label, w=200):
        return lambda xr, yy, h: lk.popup(cv, xr - w, yy + (h - 28) / 2, w, label)

    def num(v, w=120):
        def f(xr, yy, h):
            cv.rect(xr - w, yy + (h - 28) / 2, w, 28, fill="surface", stroke="border", r=7)
            cv.text(xr - w + 10, yy + (h - 28) / 2, v, "mono", "text1", w=w - 30, h=28)
            cv.icon("chevron-down", xr - 22, yy + (h - 28) / 2 + 8, 12, "text3", stroke=1.25)

        return f

    y += (
        sh.group(
            cv,
            fx,
            y,
            fw,
            [
                (
                    tr("Sample rate"),
                    L(
                        "与 DAW 工程一致：44.1 / 48 / 88.2 / 96 / 176.4 / 192 kHz",
                        "Match the DAW project: 44.1 … 192 kHz",
                    ),
                    pop("48000 Hz", 160),
                    52,
                ),
                (
                    tr("Sweep duration"),
                    L("1–60 s；越长信噪比越高", "1–60 s; longer = more S/N"),
                    num("10.0 s"),
                    52,
                ),
                (
                    tr("Peak level"),
                    L("−40…0 dBFS；默认 −12 dBFS", "−40…0 dBFS; default −12 dBFS"),
                    num("−12.0 dBFS", 140),
                    52,
                ),
            ],
        )
        + 20
    )
    lab = tr("Save Test Signal WAV...")
    lk.button(cv, fx, y, lab, "primary", icon="file-down")
    cv.text(
        fx + tw(lab, "bodym") + 60,
        y,
        L(
            "已写入 reverbscope_sweep.wav · 20 Hz–20 kHz · 1 s 前静音 + 3 s 后静音",
            "Wrote reverbscope_sweep.wav · 20 Hz–20 kHz · 1 s pre + 3 s post silence",
        ),
        "callout",
        "text3",
        h=28,
        w=fw - tw(lab, "bodym") - 60,
    )
    y += 48
    S0._checks(
        cv,
        cx,
        cw,
        [
            ("ok", L("测试信号已写入", "Test signal written"), "48 kHz", False),
            ("todo", L("在 DAW 中录制（下一步）", "Record in your DAW (next)"), None, False),
            ("todo", L("选择录音", "Choose the recording"), None, False),
        ],
    )
    if cw:
        y2 = TB + 84 + 36 + 3 * 32 + 20
        cv.hline(cx, cx + cw, y2, "sep")
        cv.text(
            cx,
            y2 + 14,
            L("扫频（来自 SweepSettings 默认值）", "Sweep (SweepSettings defaults)"),
            "captionm",
            "text3",
            h=16,
        )
        for i, (k, v) in enumerate(
            (
                (L("范围", "Range"), "20 Hz – 20 kHz"),
                (L("淡入 / 淡出", "Fade in/out"), "50 ms / 10 ms"),
                (L("前 / 后静音", "Pre / post silence"), "1.0 s / 3.0 s"),
            )
        ):
            cv.text(cx, y2 + 36 + i * 24, k, "callout", "text2", h=24)
            cv.text(cx, y2 + 36 + i * 24, v, "mono", "text1", w=cw, h=24, align="r")
    xr = fx + fw + (cw + 48 if cw else 0)
    sh.action_bar(
        cv,
        fx,
        xr,
        (L("上一步", "Back"), True),
        L("测试信号已写入，可以继续", "Test signal written"),
        "good",
        lambda y: S0._primary_right(cv, xr, y, L("继续", "Continue"), False),
    )


def daw_record(cv: Canvas):
    import lscreens as S0

    fx, fw, cx, cw = _daw_frame(cv, 1, done=(0,))
    y = TB + 84
    cv.text(fx, y, L("在 DAW 中录制", "Record through your DAW"), "title1", "text1", h=28)
    cv.text(
        fx,
        y + 32,
        L(
            "ReverbScope 不控制 DAW；按下面五步录一条轨，再回来导入。",
            "ReverbScope does not drive your DAW: record one track as below, then import it.",
        ),
        "callout",
        "text2",
        w=fw,
        h=18,
    )
    y += 64
    lines = _instruction_lines()
    steps = [ln for ln in lines if ln[:2] in ("1.", "2.", "3.", "4.", "5.")]
    extra = [ln.strip() for ln in lines if ln[:2] not in ("1.", "2.", "3.", "4.", "5.")]
    texts = []
    for i, s in enumerate(steps):
        txt = s[3:].strip()
        if i == 4 and extra:
            txt += " " + extra[0]
        texts.append(txt)
    hh = sum(cv.wrap_h(t_, "callout", fw - 64) + 18 for t_ in texts)
    cv.rect(fx, y, fw, hh + 8, fill="surface", stroke="sep", r=10)
    yy = y + 10
    for i, txt in enumerate(texts):
        th = cv.wrap_h(txt, "callout", fw - 64)
        if i:
            cv.hline(fx + 48, fx + fw, yy - 8, "sep")
        cv.circle(fx + 26, yy + 9, 11, fill="accent.soft")
        cv.text(fx + 15, yy - 2, str(i + 1), "captionm", "accent.text", w=22, h=22, align="c")
        cv.text(
            fx + 48,
            yy,
            txt,
            "callout",
            "text1",
            w=fw - 64,
            h=th + 2,
            wrap=True,
            valign="t",
            check=False,
        )
        yy += th + 18
    y += hh + 22
    cv.rect(fx, y, fw, 40, fill="warn.soft", r=8)
    cv.icon("triangle-alert", fx + 12, y + 12, 16, "warn")
    w_ = extra[1] if len(extra) > 1 else ""
    cv.text(fx + 36, y, w_, "callout", "warn", w=fw - 48, h=40)
    y += 54
    cv.text(
        fx,
        y,
        L(
            "各 DAW 关闭时间伸缩的位置（health.DAW_STRETCH_SETTINGS）",
            "Where each DAW turns time-stretch off (health.DAW_STRETCH_SETTINGS)",
        ),
        "captionm",
        "text3",
        h=16,
        w=fw,
    )
    y += 20
    seen = set()
    cv.hline(fx, fx + fw, y, "sep")
    maxy = lk.MODE["H"] - 72
    for d, s in TX()["daw_stretch_settings"]:
        if d in seen:
            continue
        seen.add(d)
        th = cv.wrap_h(s, "caption", fw - 140)
        if y + th + 8 > maxy:
            cv.text(
                fx,
                y + 4,
                L("…其余见用户指南（daw-setup.md）", "…the rest in the user guide (daw-setup.md)"),
                "caption",
                "text3",
                h=16,
            )
            break
        cv.text(fx, y + 4, d, "calloutm", "text1", h=18, w=130)
        cv.text(fx + 140, y + 5, s, "caption", "text2", w=fw - 140, h=th + 2, wrap=True, valign="t")
        y += th + 10
        cv.hline(fx, fx + fw, y - 2, "sep")
    S0._checks(
        cv,
        cx,
        cw,
        [
            ("ok", L("测试信号已写入", "Test signal written"), "48 kHz", False),
            ("todo", L("在 DAW 中录制", "Record in your DAW"), None, False),
            ("todo", L("选择录音（下一步）", "Choose the recording (next)"), None, False),
        ],
    )
    xr = fx + fw + (cw + 48 if cw else 0)
    sh.action_bar(
        cv,
        fx,
        xr,
        (L("上一步", "Back"), False),
        L("录好后继续，导入录音文件", "Continue once the track is recorded"),
        "info",
        lambda y: S0._primary_right(cv, xr, y, L("继续", "Continue"), False),
    )


def daw_import(cv: Canvas):
    import lscreens as S0

    fx, fw, cx, cw = _daw_frame(cv, 2, done=(0, 1))
    y = TB + 84
    cv.text(fx, y, L("导入录音并分析", "Import the recording and analyze"), "title1", "text1", h=28)
    cv.text(
        fx,
        y + 32,
        L(
            "WAV / AIFF / CAF / FLAC，任意长度、不用裁切；ReverbScope 自动找到扫频。",
            "WAV / AIFF / CAF / FLAC, any length, untrimmed; the sweep is found automatically.",
        ),
        "callout",
        "text2",
        w=fw,
        h=18,
    )
    y += 72

    def pop(label, w=200):
        return lambda xr, yy, h: lk.popup(cv, xr - w, yy + (h - 28) / 2, w, label)

    def btn(label):
        return lambda xr, yy, h: lk.button(
            cv,
            xr - tw(label, "callout") - 24,
            yy + (h - 26) / 2,
            label,
            "secondary",
            h=26,
            role="callout",
        )

    y += (
        sh.group(
            cv,
            fx,
            y,
            fw,
            [
                (
                    L("录音", "Recording"),
                    L(
                        "position-b.wav：9.5 s，48000 Hz，1 声道",
                        "position-b.wav: 9.5 s, 48000 Hz, 1 channel(s)",
                    ),
                    btn(tr("Choose Recording...")),
                    52,
                ),
                (
                    L("参考扫频", "Reference"),
                    L(
                        "参考：reverbscope_sweep.wav（步骤 1）",
                        "Reference: reverbscope_sweep.wav (Step 1)",
                    ),
                    btn(tr("Choose Reference Sweep...")),
                    52,
                ),
                (
                    tr("Microphone channel"),
                    None,
                    pop(L("自动（电平最高）", "Auto (highest level)")),
                ),
                (
                    tr("Loopback channel"),
                    L("可选：电气回采，补偿接口", "Optional: electrical loopback"),
                    pop(L("无", "None")),
                    52,
                ),
            ],
        )
        + 16
    )
    y += sh.group(
        cv,
        fx,
        y,
        fw,
        [
            (
                tr("Recording profile"),
                L(
                    "决定解读关注什么；数字不变",
                    "Decides what the reading watches; numbers unchanged",
                ),
                lambda xr, yy, h: (
                    lk.popup(cv, xr - 200 - 34, yy + (h - 28) / 2, 200, L("人声", "Vocals")),
                    cv.icon("circle-help", xr - 22, yy + (h - 16) / 2, 16, "text2"),
                ),
                52,
            ),
            (
                tr("Tape measurements (optional)"),
                L(
                    "扬声器距离 · 话筒高度 · 气温 —— 提高摆位档位",
                    "Distance · mic height · temperature — raises the placement tier",
                ),
                lambda xr, yy, h: cv.icon("chevron-right", xr - 16, yy + (h - 16) / 2, 16, "text3"),
                52,
            ),
            (
                tr("Measurement metadata (optional)"),
                L("房间 · 位置 · 话筒", "Room · position · microphone"),
                lambda xr, yy, h: cv.icon("chevron-right", xr - 16, yy + (h - 16) / 2, 16, "text3"),
                52,
            ),
        ],
    )
    S0._checks(
        cv,
        cx,
        cw,
        [
            ("ok", L("测试信号", "Test signal"), "48 kHz", False),
            ("ok", L("录音已选择", "Recording chosen"), "9.5 s", False),
            ("ok", L("参考扫频", "Reference sweep"), "sidecar", False),
            ("todo", L("分析（下一步）", "Analyze (next)"), None, False),
        ],
    )
    if cw:
        y2 = TB + 84 + 36 + 4 * 32 + 20
        cv.hline(cx, cx + cw, y2, "sep")
        cv.text(
            cx,
            y2 + 14,
            L("分析会检查（health.assess）", "Analysis checks (health.assess)"),
            "captionm",
            "text3",
            h=16,
        )
        names = [c["title"] for c in TX()["health_b"]]
        for i, nm in enumerate(names[:8]):
            cv.icon("circle-dashed", cx, y2 + 40 + i * 22, 12, "text3", stroke=1.25)
            cv.text(cx + 20, y2 + 34 + i * 22, nm, "callout", "text2", h=22)
    xr = fx + fw + (cw + 48 if cw else 0)
    sh.action_bar(
        cv,
        fx,
        xr,
        (L("上一步", "Back"), False),
        L("分析不可取消；通常几秒钟", "Analysis cannot be cancelled; usually a few seconds"),
        "info",
        lambda y: S0._primary_right(cv, xr, y, tr("Analyze"), False),
    )


# ------------------------------------------------------------------ 08 compare (real tabs)
def compare(cv: Canvas):
    W, H = cv.W, cv.H
    x0 = frame(
        cv,
        "compare",
        title=tr("Compare"),
        sub=L("A-1 基准 ↔ B-1 对比项", "A-1 baseline ↔ B-1 candidate"),
    )
    x, xr = x0 + 32, W - 32
    t = TX()
    y = TB + 18
    cv.text(x, y, tr("Compare"), "title1", "text1", h=28)
    ax = x + tw(tr("Compare"), "title1") + 16
    ax += lk.chip(cv, ax, y + 2, L("A-1 · 基准", "A-1 · baseline")) + 8
    cv.icon("arrow-right", ax, y + 6, 16, "text3")
    ax += 24
    ax += lk.chip(cv, ax, y + 2, L("B-1 · 对比项", "B-1 · candidate"), tone="accent") + 12
    cb = N["comparison_common_band"]
    cbt = (
        L(
            f"可比 · 共同频带 {cb[0]:.0f} Hz–{cb[1] / 1000:.1f} kHz",
            f"Comparable · common band {cb[0]:.0f} Hz–{cb[1] / 1000:.1f} kHz",
        )
        if cb
        else ""
    )
    bx = xr
    for lab, kind, ic in (
        (tr("Copy report"), "secondary", "copy"),
        (tr("Save comparison.json..."), "secondary", "file-down"),
        (tr("Swap"), "secondary", "arrow-left-right"),
    ):
        w = tw(lab, "callout") + 24 + 22
        bx -= w
        lk.button(cv, bx, y, lab, kind, icon=ic, h=28, role="callout")
        bx -= 8
    cv.text(ax, y + 2, cbt, "callout", "text3", h=24, w=bx - ax - 8)
    y += 40
    lk.checkbox(cv, x, y + 6, checked=True)
    cv.text(
        x + 24,
        y,
        tr("Input gain unchanged") + L("（噪声差值需要）", " (required for a VALID noise delta)"),
        "callout",
        "text1",
        h=28,
    )
    y += 38
    # verdicts (judge_comparison, vocal)
    cv.text(x, y, L("判定 · 人声配置", "Verdicts · Vocals profile"), "captionm", "text3", h=18)
    y += 22
    vs = t["verdicts"]
    vw = (xr - x - 8 * (len(vs) - 1)) / len(vs)
    word = {
        "meaningful_improvement": (L("改善", "Improved"), "good", "circle-check"),
        "probably_insignificant": (
            L("大概率无关紧要", "Probably insignificant"),
            "neutral",
            "circle-dashed",
        ),
        "meaningful_regression": (L("退化", "Worse"), "crit", "triangle-alert"),
        "insufficient_evidence": (
            L("证据不足", "Insufficient evidence"),
            "neutral",
            "circle-dashed",
        ),
        "not_comparable": (L("不可比", "Not comparable"), "warn", "triangle-alert"),
    }
    for i, v in enumerate(vs):
        vx = x + i * (vw + 8)
        wd, tone, ic = word.get(v["verdict"], (v["verdict"], "neutral", "info"))
        cv.rect(vx, y, vw, 132, fill="surface", stroke="sep", r=10)
        cv.text(vx + 12, y + 8, v["title"], "bodym", "text1", h=20, w=vw - 24)
        lk.chip(
            cv,
            vx + 12,
            y + 32,
            wd,
            icon=ic,
            tone=tone if tone != "neutral" else "neutral",
            h=20,
            role="caption",
        )
        rh_ = cv.wrap_h(v["reason"], "caption", vw - 24)
        cv.text(
            vx + 12,
            y + 58,
            v["reason"],
            "caption",
            "text2",
            w=vw - 24,
            h=min(rh_, 70) + 2,
            wrap=True,
            valign="t",
            check=rh_ <= 70,
        )
    y += 144
    cond = t["verdict_conditions"][-1]
    cv.icon("info", x, y + 2, 14, "info")
    cv.text(x + 20, y, cond, "caption", "text2", w=xr - x - 20, h=16)
    y += 28
    tabs = [
        tr("Metrics"),
        tr("Frequency response difference"),
        tr("Early Reflections"),
        tr("Resonances"),
        tr("Full report"),
    ]
    lk.segmented(cv, x, y, tabs, 0, pad=12)
    y += 40
    ww = xr - x
    cols = [
        (L("指标", "Metric"), ww * 0.26, "l"),
        (tr("Baseline"), ww * 0.14, "r"),
        (tr("Candidate"), ww * 0.14, "r"),
        (tr("Delta"), ww * 0.14, "r"),
        ("%", ww * 0.1, "r"),
        (tr("Validity"), ww * 0.22, "l"),
    ]
    names = {
        "broadband.t30": "RT60 (T30)",
        "broadband.t20": "T20",
        "broadband.edt": "EDT",
        "broadband.c50": "C50",
        "broadband.c80": "C80",
        "broadband.d50": "D50",
        "broadband.centre_time": "Ts",
        "noise.rms_dbfs": L("本底噪声 RMS", "Noise RMS"),
        "band.63 Hz.edt": "63 Hz EDT",
        "band.125 Hz.t30": "125 Hz T30",
    }
    rows = []
    D = {d["name"]: d for d in N["comparison_deltas"]}
    for key, lab in names.items():
        d = D.get(key)
        if not d:
            continue
        u = d.get("unit", "")
        dig = 2 if u == "s" else 1
        sign = u == "dB"
        ok = d["validity"] == "valid"
        fmt = lambda v: (
            (mnum(v * 1000, 0) + " ms")
            if key.endswith("centre_time")
            else (mnum(v, dig, sign) + (f" {u}" if u else ""))
        )
        dfmt = lambda v: (
            (mnum(v * 1000, 0, True) + " ms")
            if key.endswith("centre_time")
            else (mnum(v, dig, True) + {"dBFS": " dB", "%": " pp"}.get(u, f" {u}"))
        )
        rows.append(
            [
                (lab, "text1", "callout"),
                fmt(d["baseline"]) if d["baseline"] is not None else "–",
                fmt(d["candidate"]) if d["candidate"] is not None else "–",
                (
                    dfmt(d["delta"]) if (ok and d.get("delta") is not None) else "–",
                    "text1" if ok else "text3",
                    "monom",
                ),
                mnum(d["delta_percent"], 1, True)
                if (ok and d.get("delta_percent") is not None)
                else "–",
                (
                    L("有效", "valid")
                    if ok
                    else L("不可比：对比项 EDT 不可靠", "not comparable: candidate EDT unreliable"),
                    "text2" if ok else "warn",
                    "caption",
                ),
            ]
        )
    table(cv, x, y, cols, rows, rh=26, maxy=H - 12)


# ------------------------------------------------------------------ 09 settings (real rows)
def settings(cv: Canvas):
    import lscreens as S0

    W, H = cv.W, cv.H
    frequency(cv)
    cv.rect(0, 0, W, H, fill=C("scrim", 0.28 if lk.MODE["theme"] == "light" else 0.5))
    sw_, shh = 780, 620
    sx, sy = (W - sw_) / 2, (H - shh) / 2
    cv.shadow(sx, sy, sw_, shh, r=12, depth=30, alpha=0.30, dy=16)
    cv.rect(sx, sy, sw_, shh, fill="window", stroke=C("shadow", 0.15), r=12)
    nav_w = 200
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QPainterPath

    p = cv.p
    p.save()
    clip = QPainterPath()
    clip.addRoundedRect(QRectF(sx, sy, sw_, shh), 12, 12)
    p.setClipPath(clip)
    cv.gradient_v(sx, sy, nav_w, shh, "sidebar.top", "sidebar.bot")
    p.restore()
    cv.vline(sx + nav_w, sy, sy + shh, "sep")
    lk.traffic_lights(cv, sx + 16, sy + 16)
    items = [
        ("settings", L("通用", "General")),
        ("mic", L("测量", "Measurement")),
        ("audio-lines", L("音频", "Audio")),
        ("flask-conical", L("开发者", "Developer")),
    ]
    yy = sy + 52
    for i, (ic, lab) in enumerate(items):
        if i == 0:
            cv.rect(sx + 8, yy, nav_w - 16, 30, fill="sel.sidebar", r=6)
        cv.icon(ic, sx + 18, yy + 7, 16, "accent.text" if i == 0 else "text2")
        cv.text(sx + 44, yy, lab, "bodym" if i == 0 else "body", "text1", h=30)
        yy += 32
    cv.text(sx + 18, sy + shh - 34, "ReverbScope 0.5.0b4", "caption", "text3", h=20)
    cx, cw = sx + nav_w + 28, sw_ - nav_w - 56
    cy = sy + 18
    cv.text(cx, cy, L("通用", "General"), "title2", "text1", h=24)
    cv.icon("x", sx + sw_ - 34, sy + 18, 16, "text3")
    cy += 40

    def pop(label, w=200):
        return lambda xr, yy, h: lk.popup(cv, xr - w, yy + (h - 28) / 2, w, label, role="callout")

    cy += (
        sh.group(
            cv,
            cx,
            cy,
            cw,
            [
                (
                    tr("Language"),
                    L("重启后完全生效", "Fully applies after a restart"),
                    pop(tr("Follow the system")),
                    52,
                ),
                (
                    tr("Theme"),
                    None,
                    lambda xr, yy, h: S0._seg_right(
                        cv, xr, yy, h, [tr("Follow the system"), tr("Light"), tr("Dark")], 0
                    ),
                ),
                (
                    tr("Default profile"),
                    L(
                        "新测量用的录音配置；7 种，见“它看什么？”",
                        "Profile for new measurements; 7 built in",
                    ),
                    pop(L("通用", "Generic")),
                    52,
                ),
            ],
        )
        + 14
    )
    cv.text(cx, cy, L("测量与文件", "Measurement & files"), "captionm", "text3", h=18)
    cy += 22
    cy += (
        sh.group(
            cv,
            cx,
            cy,
            cw,
            [
                (
                    tr("Default output folder"),
                    "~/ReverbScope",
                    lambda xr, yy, h: lk.button(
                        cv,
                        xr - 80,
                        yy + (h - 26) / 2,
                        L("浏览…", "Browse…"),
                        "secondary",
                        h=26,
                        role="callout",
                    ),
                    52,
                ),
                (
                    tr("Copy the raw recording into every session"),
                    None,
                    lambda xr, yy, h: lk.toggle(cv, xr - 32, yy + (h - 18) / 2, True),
                ),
            ],
        )
        + 14
    )
    cv.text(
        cx,
        cy,
        L("结果怎么解释 · 用户类型", "How results are worded · user type"),
        "captionm",
        "text3",
        h=18,
    )
    lk.chip(
        cv,
        cx
        + tw(L("结果怎么解释 · 用户类型", "How results are worded · user type"), "captionm")
        + 10,
        cy - 2,
        L("未实现 · 提案", "Not implemented · proposal"),
        h=20,
        tone="planned",
        role="caption",
    )
    cy += 26
    modes = [
        ("house", L("普通用户", "Everyday"), L("通俗", "Plain")),
        ("music", L("音乐人 · 录音爱好者", "Musician"), L("通俗 + 术语", "Plain + terms")),
        (
            "sliders-vertical",
            L("专业人士", "Professional"),
            L("专业 · 全部指标", "Pro · every metric"),
        ),
    ]
    tw_ = (cw - 16) / 3
    for i, (ic, lab, sub) in enumerate(modes):
        tx = cx + i * (tw_ + 8)
        sel = i == 1
        cv.rect(
            tx,
            cy,
            tw_,
            72,
            fill="accent.soft" if sel else "surface",
            stroke="accent" if sel else "sep",
            r=10,
            sw=1.5 if sel else 1,
        )
        cv.icon(ic, tx + 14, cy + 12, 20, "accent.text" if sel else "text2")
        if sel:
            cv.icon("circle-check", tx + tw_ - 30, cy + 12, 16, "accent")
        cv.text(tx + 14, cy + 38, lab, "bodym", "text1", w=tw_ - 20, h=18)
        cv.text(tx + 14, cy + 54, sub, "caption", "text2", w=tw_ - 20, h=14)
    cy += 84
    cv.rect(cx, cy, cw, 64, fill="sunken", r=10)
    cv.text(
        cx + 14,
        cy + 6,
        L(
            "预览 · 同一条解读，数字不变（文字取自 interpret()，人声配置）",
            "Preview · same finding, same numbers (text from interpret(), Vocals)",
        ),
        "caption",
        "text3",
        h=16,
        w=cw - 28,
    )
    cv.icon("info", cx + 14, cy + 30, 16, "info")
    f = TX()["findings_b_vocal"][1]["message"]
    cv.text(
        cx + 38, cy + 26, f, "callout", "text1", w=cw - 52, h=34, wrap=True, valign="t", check=False
    )


# ------------------------------------------------------------------ icon sheet v2
ICON_SPEC = [
    ("plus", "新测量 ⌘N", "File ▸ New Measurement", "侧栏"),
    ("folder", "打开会话… ⌘O", "File ▸ Open Session...", "首页"),
    ("layers", "打开项目… ⇧⌘O", "File ▸ Open Project...", "首页"),
    ("folder-open", "项目行 → 项目视图（⌘9）", "ProjectPage", "侧栏"),
    ("git-compare", "对比两个会话…", "File ▸ Compare Sessions...", "首页"),
    ("history", "已保存的会话", "io.recent / StartPanel", "侧栏"),
    ("settings", "设置… ⌘,", "File ▸ Settings...", "侧栏底"),
    ("circle-help", "入门 / 用户指南", "Help ▸ Getting started", "侧栏底"),
    ("stethoscope", "环境报告（问题反馈）", "Help ▸ Environment Report", "侧栏底"),
    ("panel-left", "测量列表 显示/隐藏", "View ▸ Measurement list", "标题栏"),
    ("panel-right", "检查器 显示/隐藏", "View ▸ Inspector", "工具栏"),
    ("save", "保存会话… ⌘S", "File ▸ Save Session...", "工具栏"),
    ("download", "导出 ▸ PNG / SVG / CSV", "ChartPanel export", "图表行"),
    ("rotate-ccw", "复位 R / 双击", "ChartPanel reset", "图表行"),
    ("audio-lines", "音频接口（独立模式）", "Measure ▸ Standalone Mode", "首页、工具栏"),
    ("music", "DAW 录音（通用 DAW 模式）", "Measure ▸ Universal DAW Mode", "首页、工具栏"),
    (
        "file-down",
        "保存测试信号 WAV… / 保存 comparison.json…",
        "DawModePage / ComparePage",
        "DAW 步骤 1、对比",
    ),
    ("file-input", "选择录音…", "DawModePage step 3", "DAW 步骤 3"),
    ("mic", "录音配置", "profile combo", "首页"),
    ("arrow-right", "开始", "→ mode page", "首页"),
    ("chevron-left", "上一步", "wizard back", "操作栏"),
    ("square-stop", "停止 Esc", "Stop take", "操作栏"),
    ("lock", "测量中锁定", "BUSY", "侧栏、步骤、工具栏"),
    ("activity", "测量中 / 运行中", "take running", "步骤、侧栏"),
    ("circle-check", "良好 / 已完成", "HealthStatus.GOOD", "健康、就绪"),
    ("triangle-alert", "警告", "HealthStatus.WARNING", "健康、列表"),
    ("circle-x", "无效", "HealthStatus.INVALID", "健康"),
    ("circle-dashed", "未知 / 待完成", "HealthStatus.UNKNOWN", "健康、就绪"),
    ("heart-pulse", "测量健康", "health.assess", "健康面板"),
    ("info", "提示 / 解读", "Severity notice/info", "解读"),
    ("copy", "复制报告 / 复制总览", "ReportView / ProjectPage", "报告、项目"),
    ("arrow-left-right", "互换基准", "ComparePage Swap", "对比"),
    ("box", "在房间视图中显示", "RoomView", "时间、检查器"),
    ("scan", "导入扫描…（PLY / OBJ）", "ScanImportDialog", "房间"),
    ("maximize", "取景 F", "RoomCanvas frame", "房间"),
    ("sliders-vertical", "房间参数 / 专业人士", "RoomView parameters", "房间、用户类型"),
    ("flask-conical", "合成演示数据", "entry synthetic", "页头、侧栏"),
    ("house", "普通用户（提案）", "未实现", "用户类型"),
    ("chevron-down", "下拉", "popup", "控件"),
    ("chevron-right", "进入", "group row", "分组行"),
    ("x", "关闭", "dialog", "窗口"),
    ("check", "复选 / 完成步骤", "checkbox", "控件"),
]


def icon_sheet(cv: Canvas):
    W, H = cv.W, cv.H
    cv.text(
        32,
        22,
        L(
            "图标规格 · Lucide 1.59.0（ISC）· 线宽 1.5 px · 每个图标对应 main 上的真实功能",
            "Icon spec · Lucide 1.59.0 (ISC) · 1.5 px · every icon maps to a real function on main",
        ),
        "title2",
        "text1",
        h=26,
        w=W - 64,
    )
    cols = 3
    colw = (W - 64) / cols
    y0 = 64
    rh = 36
    per = math.ceil(len(ICON_SPEC) / cols)
    for i, (ic, zh_, code, where) in enumerate(ICON_SPEC):
        c, r = divmod(i, per)
        x = 32 + c * colw
        y = y0 + r * rh
        cv.rect(x, y + 2, 32, 32, fill="surface", stroke="sep", r=7)
        cv.icon(ic, x + 8, y + 10, 16, "text1")
        cv.text(x + 42, y + 1, zh_ if lk.zh() else code, "callout", "text1", h=18, w=colw - 52)
        cv.text(
            x + 42,
            y + 18,
            f"{ic} · {code if lk.zh() else where}",
            "caption",
            "text3",
            h=16,
            w=colw - 52,
        )
    yb = y0 + per * rh + 10
    cv.hline(32, W - 32, yb, "sep")
    cv.text(
        32,
        yb + 10,
        L(
            "已移除（代码里没有）：search ⌘K 搜索 · message-square 反馈 · crosshair / move / zoom-in 光标·平移·框选工具 · file-audio 导入脉冲响应（仅 CLI analyze-ir）· refresh-cw（换成 arrow-left-right）",
            "Removed (not in code): search ⌘K · message-square feedback · crosshair / move / zoom-in tool modes · file-audio import IR (CLI analyze-ir only) · refresh-cw (now arrow-left-right)",
        ),
        "caption",
        "text2",
        w=W - 64,
        h=34,
        wrap=True,
        valign="t",
    )
