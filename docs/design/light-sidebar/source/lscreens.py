# ruff: noqa
# Design-phase mockup renderer (docs only, not product code).
"""Home and measurement-flow screens (round 2: only controls that exist in code)."""

from __future__ import annotations

import json
import math

import numpy as np

import lk
import lshell as sh
from lcharts import Plot, colorbar, legend, mnum, ramp
from lk import C, L, Canvas, tw

DEMO = np.load(lk.HERE / "demo.npz")
SB = lk.SIDEBAR_W
TB = lk.TOOLBAR_H


def narrow():
    return lk.MODE["W"] < 1100


# ------------------------------------------------------------ home / empty
def home(cv: Canvas):
    W, H = cv.W, cv.H
    sh.sidebar(cv, empty=True)
    x0 = SB
    cx = x0 + (W - x0) / 2
    # toolbar: no title, only right affordances
    cw = 640
    top = int((H - 520) / 2) + 8
    lk.app_icon(cv, cx - 22, top, 44)
    t = L("测一测你的录音位置", "Measure where you record")
    cv.text(cx - 300, top + 60, t, "display", "text1", w=600, h=40, align="c")
    st = L(
        "播放一段扫频，录下房间的回应，再用你习惯的说法解释结果。",
        "Play a sweep, record how the room answers, and read the result in words that suit you.",
    )
    cv.text(cx - 320, top + 104, st, "body", "text2", w=640, h=20, align="c")
    # composer
    y = top + 148
    ch = 112
    cv.shadow(cx - cw / 2, y, cw, ch, r=18, depth=22, alpha=0.10, dy=10)
    cv.rect(cx - cw / 2, y, cw, ch, fill="surface", stroke="sep", r=18)
    px = cx - cw / 2 + 20
    cv.text(
        px,
        y + 16,
        L("选择测量方式，再开始", "Choose how to measure, then start"),
        "body",
        "text3",
        h=22,
        w=cw - 40,
    )
    # path options as a segmented control with icons (one choice)
    by = y + ch - 48
    opts = [
        ("audio-lines", lk.tr("Audio interface")),
        ("music", lk.tr("DAW recording")),
    ]
    bx = px
    for i, (ic, lab) in enumerate(opts):
        w = tw(lab, "calloutm") + 44
        sel = i == 0
        cv.rect(
            bx,
            by,
            w,
            32,
            fill="accent.soft" if sel else "surface",
            stroke="accent" if sel else "border",
            r=16,
            sw=1.0,
        )
        cv.icon(ic, bx + 12, by + 8, 16, "accent.text" if sel else "text2")
        cv.text(bx + 32, by, lab, "calloutm", "accent.text" if sel else "text1", h=32)
        bx += w + 8
    # profile + go
    gx = cx + cw / 2 - 20 - 36
    cv.circle(gx + 18, by + 16, 18, fill="accent")
    cv.icon("arrow-right", gx + 8, by + 6, 20, "on.accent", stroke=1.75)
    prof = L("人声配置", "Vocals profile")
    pw = tw(prof, "callout") + 56
    cv.rect(gx - 12 - pw, by + 2, pw, 28, fill="sunken", r=14)
    cv.icon("mic", gx - 12 - pw + 10, by + 9, 14, "text2")
    cv.text(gx - 12 - pw + 30, by + 2, prof, "callout", "text1", h=28)
    cv.icon("chevron-down", gx - 12 - 22, by + 10, 12, "text3", stroke=1.25)
    # secondary
    y2 = y + ch + 28
    sec = [
        ("folder", lk.tr("Open Session...")),
        ("layers", lk.tr("Open Project...")),
        ("git-compare", lk.tr("Compare two sessions...")),
    ]
    widths = [tw(s, "callout") + 44 for _, s in sec]
    sx = cx - (sum(widths) + 8 * (len(sec) - 1)) / 2
    for (ic, lab), w in zip(sec, widths):
        cv.rect(sx, y2, w, 30, stroke="border", r=15)
        cv.icon(ic, sx + 12, y2 + 7, 16, "text2")
        cv.text(sx + 32, y2, lab, "callout", "text1", h=30)
        sx += w + 8
    # keyboard hints
    y3 = y2 + 54
    hints = [
        ("⌘N", L("新测量", "New")),
        ("⌘O", L("打开", "Open")),
        ("⇧⌘O", L("打开项目", "Project")),
        ("⌘,", L("设置", "Settings")),
    ]
    tot = sum(max(18, tw(k, "kbd") + 10) + 6 + tw(v, "caption") + 18 for k, v in hints) - 18
    hx = cx - tot / 2
    for k, v in hints:
        hx += lk.kbd(cv, hx, y3, k) + 6
        hx += cv.text(hx, y3, v, "caption", "text3", h=18) + 18
    # how it works strip
    y4 = y3 + 76
    steps = [
        ("cable", L("连接接口或 DAW", "Connect an interface or DAW")),
        ("audio-waveform", L("播放扫频并录音", "Play the sweep and record")),
        ("chart-spline", L("读懂频响与余音", "Read response and decay")),
    ]
    sw_ = 220
    sx = cx - sw_ * 1.5
    for i, (ic, lab) in enumerate(steps):
        x = sx + i * sw_
        cv.icon(ic, x + sw_ / 2 - 10, y4, 20, "text3")
        cv.text(x, y4 + 28, lab, "callout", "text3", w=sw_, h=18, align="c")
        if i:
            cv.hline(x - 40, x + 20, y4 + 10, "border")
    mode = L(
        "录音配置决定解读关注什么，数字不变 · 默认配置在 设置 ▸ 通用",
        "The recording profile decides what the reading watches; numbers stay · default in Settings",
    )
    cv.text(cx - 320, y4 + 58, mode, "caption", "text3", w=640, h=16, align="c")


# ------------------------------------------------------------ measurement flow
def _measure_frame(cv, step, busy=False, path_sel=0, steps=None, done=(), locked=(), running=None):
    W, H = cv.W, cv.H
    nar = narrow()
    if not nar:
        sh.sidebar(
            cv,
            tree=sh.project_tree(busy_item=busy),
            sel="new" if busy else None,
            busy=busy,
            hover_settings_tip=busy and not nar,
        )
    x0 = 0 if nar else SB
    end = sh.toolbar(
        cv,
        x0,
        L("新测量", "New Measurement"),
        L("合成演示房间 · 位置 B", "Synthetic demo room · Position B"),
        traffic=nar,
    )
    # centre: path segmented
    items = [L("音频接口", "Audio interface"), "DAW"]
    segw = sum(tw(s, "calloutm") + 24 for s in items) + 4
    sx = max(end + 24, x0 + (W - x0) / 2 - segw / 2)
    lk.segmented(cv, sx, 12, items, path_sel, disabled=(0, 1) if busy else ())
    if busy:
        cv.icon("lock", sx + segw + 8, 19, 14, "text3")
    # right side: status / chips
    rx = W - 16
    if busy:
        lab = L("测量中 · 62 %", "Measuring · 62 %")
        w = tw(lab, "calloutm") + 34
        rx -= w
        cv.rect(rx, 14, w, 24, fill="crit.soft", r=12)
        cv.circle(rx + 13, 26, 4, fill="crit")
        cv.text(rx + 24, 14, lab, "calloutm", "crit", h=24)
        rx -= 8
    rx -= sh.tool_icon(cv, rx - 30, 11, "save", disabled=busy)
    if not nar:
        lab = L("合成演示数据", "Synthetic demo data")
        rx -= tw(lab, "callout") + 38 + 8
        lk.chip(cv, rx, 14, lab, icon="flask-conical")
    elif step == 1:
        lab = L("就绪 2/3 · 电平需确认", "Ready 2/3 · level to confirm")
        rx -= tw(lab, "callout") + 38 + 8
        lk.chip(cv, rx, 14, lab, icon="triangle-alert", tone="warn")
    # layout columns
    pad = 32 if nar else 48
    chk_w = 0 if nar else 280
    gap = 0 if nar else 48
    form_w = min(600, W - x0 - 2 * pad - chk_w - gap)
    total = form_w + gap + chk_w
    fx = x0 + (W - x0 - total) / 2
    steps = steps or [
        L("连接设备", "Connect"),
        L("信号与电平", "Signal & level"),
        L("测量", "Measure"),
    ]
    sh.stepper(cv, fx, TB + 24, form_w, steps, step, locked=locked, running=running, done=done)
    return fx, form_w, fx + form_w + gap, chk_w


def measure_connect(cv: Canvas):
    fx, fw, cx, cw = _measure_frame(cv, 0)
    y = TB + 84
    cv.text(fx, y, L("连接设备", "Connect devices"), "title1", "text1", h=28)
    cv.text(
        fx,
        y + 32,
        L(
            "ReverbScope 通过音频接口播放扫频，同时录下话筒。两端采样率需要一致。",
            "ReverbScope plays the sweep through your interface and records the mic at the same time.",
        ),
        "callout",
        "text2",
        w=fw,
        h=18,
    )
    y += 72

    def pop(label, w=260):
        return lambda xr, yy, h: lk.popup(cv, xr - w, yy + (h - 28) / 2, w, label)

    cv.text(fx, y, L("输出 · 播放扫频", "Output · plays the sweep"), "captionm", "text3", h=18)
    y += 22
    y += (
        sh.group(
            cv,
            fx,
            y,
            fw,
            [
                (lk.tr("Output device"), None, pop("ReverbScope fake interface")),
                (lk.tr("Output channel (speaker)"), None, pop("1")),
            ],
        )
        + 20
    )
    cv.text(fx, y, L("输入 · 录下话筒", "Input · records the mic"), "captionm", "text3", h=18)
    y += 22
    y += (
        sh.group(
            cv,
            fx,
            y,
            fw,
            [
                (lk.tr("Input device"), None, pop("ReverbScope fake interface")),
                (lk.tr("Input channel (mic)"), None, pop("1")),
                (
                    lk.tr("Loopback channel (1-based)"),
                    L("可选：电气回采，补偿接口延迟与频响", "Optional: electrical loopback"),
                    pop(L("未使用", "unused")),
                    52,
                ),
                (
                    lk.tr("Sample rate"),
                    L("设备采样率：48000 Hz", "Device rate: 48000 Hz"),
                    pop("48000 Hz", 160),
                    52,
                ),
            ],
        )
        + 16
    )
    _checks(
        cv,
        cx,
        cw,
        [
            ("ok", L("输出设备已选择", "Output chosen"), None, False),
            ("ok", L("输入设备已选择", "Input chosen"), None, False),
            ("ok", L("同一设备，一个时钟", "One device, one clock"), "48 kHz", False),
            ("todo", L("电平确认（下一步）", "Level check (next step)"), None, False),
        ],
    )
    sh.action_bar(
        cv,
        fx,
        fx + fw + (cw + 48 if cw else 0),
        (L("上一步", "Back"), True),
        L("设备就绪，可以继续", "Devices ready"),
        "good",
        lambda y: _primary_right(
            cv, fx + fw + (cw + 48 if cw else 0), y, L("继续", "Continue"), False
        ),
    )


def _primary_right(cv, xr, y, label, disabled):
    w = tw(label, "bodym") + 24 + tw("⌘↩", "callout") + 8
    lk.button(cv, xr - w, y, label, "primary", w=w, shortcut="⌘↩", disabled=disabled)
    return w


def _checks(cv, x, w, rows, title=None):
    if not w:
        return
    y = TB + 84
    cv.text(x, y + 4, title or L("就绪检查", "Readiness"), "headline", "text1", h=20)
    y += 36
    for st, lab, val, planned in rows:
        sh.check_row(cv, x, y, w, st, lab, val, planned)
        y += 32
    return y


def level_slider(cv, x, y, w, val=-9.0, thr=-12.0, lo=-40, hi=0):
    def X(v):
        return x + (v - lo) / (hi - lo) * w

    cv.rect(x, y + 6, w, 6, fill="sunken", stroke="sep", r=3)
    cv.rect(x, y + 6, X(thr) - x, 6, fill=C("accent", 0.22), r=3)
    cv.rect(x, y + 6, X(val) - x, 6, fill="accent", r=3)
    cv.rect(X(thr), y + 6, X(val) - X(thr), 6, fill="warn", r=0)
    cv.line(X(thr), y - 2, X(thr), y + 20, "warn", 1.5, dash=[2, 2])
    cv.circle(X(val), y + 9, 10, fill="surface", stroke="control", sw=1)
    cv.circle(X(val), y + 9, 3, fill="warn")
    for v in range(lo, hi + 1, 10):
        if abs(v - thr) < 5:
            continue
        cv.text(X(v) - 20, y + 24, mnum(v, 0), "monos", "text3", w=40, h=14, align="c")
    cv.text(X(thr) - 20, y + 24, mnum(thr, 0), "monos", "warn", w=40, h=14, align="c")
    cv.text(
        x,
        y + 40,
        L("安全区 ≤ −12 dBFS", "Safe zone ≤ −12 dBFS"),
        "caption",
        "accent.text",
        w=X(thr) - x,
        h=14,
        align="c",
    )


def measure_signal(cv: Canvas):
    fx, fw, cx, cw = _measure_frame(cv, 1, done=(0,))
    y = TB + 84
    cv.text(fx, y, L("信号与电平", "Signal & level"), "title1", "text1", h=28)
    cv.text(
        fx,
        y + 32,
        L(
            "先把监听音箱或耳机音量调低。ReverbScope 用保守的数字电平播放扫频。",
            "Turn your monitors or headphones down first. The sweep plays at a conservative digital level.",
        ),
        "callout",
        "text2",
        w=fw,
        h=18,
    )
    y += 72
    # level block (single group)
    wtxt = L(
        "高于 −12 dBFS：先调低监听音量，再勾选确认。改电平、停止或新测量都会清除确认。",
        "Above −12 dBFS: turn monitoring down, then confirm. Changing the level, Stop or New Measurement clears it.",
    )
    wth = cv.wrap_h(wtxt, "callout", fw - 64)
    gh = 112 + 12 + wth + 44
    cv.rect(fx, y, fw, gh, fill="surface", stroke="sep", r=10)
    cv.text(fx + 16, y + 14, L("播放电平", "Playback level"), "body", "text1", h=20)
    val = "−9.0 dBFS"
    cv.text(fx + fw - 16 - 120, y + 12, val, "monom", "warn", w=120, h=24, align="r")
    level_slider(cv, fx + 16, y + 48, fw - 32)
    # warning + checkbox
    wy = y + 112
    cv.rect(fx + 1, wy, fw - 2, y + gh - wy - 1, fill="warn.soft", r=9)
    cv.rect(fx + 1, wy, fw - 2, 12, fill="warn.soft")
    cv.hline(fx + 1, fx + fw - 1, wy, "warn.border")
    cv.icon("triangle-alert", fx + 16, wy + 14, 16, "warn")
    cv.text(fx + 40, wy + 12, wtxt, "callout", "warn", w=fw - 64, h=wth + 2, wrap=True, valign="t")
    cby = wy + 12 + wth + 12
    lk.checkbox(cv, fx + 40, cby + 4, checked=False, focus=True)
    cv.text(
        fx + 66, cby, L("我已调低监听音量", "I have turned monitoring down"), "bodym", "text1", h=24
    )
    y += gh + 20
    y += sh.group(
        cv,
        fx,
        y,
        fw,
        [
            (
                lk.tr("Sweep duration"),
                L("1–60 s", "1–60 s"),
                lambda xr, yy, h: lk.popup(
                    cv, xr - 120, yy + (h - 28) / 2, 120, "10.0 s", role="callout"
                ),
                52,
            ),
            (
                lk.tr("Recording profile"),
                L("决定解读关注什么；数字不变", "Decides what the reading watches"),
                lambda xr, yy, h: lk.popup(
                    cv, xr - 200, yy + (h - 28) / 2, 200, L("人声", "Vocals")
                ),
                52,
            ),
            (
                lk.tr("Tape measurements (optional)"),
                None,
                lambda xr, yy, h: cv.icon("chevron-right", xr - 16, yy + (h - 16) / 2, 16, "text3"),
            ),
        ],
    )
    _checks(
        cv,
        cx,
        cw,
        [
            ("ok", L("设备已选择", "Devices chosen"), None, False),
            ("ok", L("同一设备，一个时钟", "One device, one clock"), "48 kHz", False),
            ("warn", L("电平需确认", "Level needs confirming"), "−9.0 dBFS", False),
        ],
    )
    if cw:
        y2 = TB + 84 + 36 + 3 * 32 + 20
        cv.hline(cx, cx + cw, y2, "sep")
        cv.text(cx, y2 + 14, L("本次将使用", "This take will use"), "captionm", "text3", h=16)
        rows = [
            (L("设备", "Device"), "fake interface"),
            (L("电平", "Level"), "−9.0 dBFS"),
            (L("时长", "Length"), "10 s"),
            (L("配置", "Profile"), L("人声", "Vocals")),
        ]
        for i, (k, v) in enumerate(rows):
            cv.text(cx, y2 + 36 + i * 24, k, "callout", "text2", h=24)
            cv.text(cx, y2 + 36 + i * 24, v, "mono", "text1", w=cw, h=24, align="r")
    xr = fx + fw + (cw + 48 if cw else 0)
    sh.action_bar(
        cv,
        fx,
        xr,
        (L("上一步", "Back"), False),
        L(
            "先勾选“我已调低监听音量”才能继续",
            "Tick “I have set the monitor level low” to continue",
        ),
        "warn",
        lambda y: _primary_right(cv, xr, y, L("继续", "Continue"), True),
    )
    if narrow():
        # readiness collapses into a one-line summary under the stepper
        pass


def _seg_right(cv, xr, yy, h, items, sel):
    w = sum(tw(s, "calloutm") + 20 for s in items) + 4
    lk.segmented(cv, xr - w, yy + (h - 28) / 2, items, sel, pad=10)


def measure_running(cv: Canvas):
    fx, fw, cx, cw = _measure_frame(cv, 2, busy=True, locked=(0, 1), running=2)
    y = TB + 84
    cv.text(fx, y, L("正在扫频", "Playing the sweep"), "title1", "text1", h=28)
    cv.text(
        fx,
        y + 32,
        L(
            "请保持安静。按一次 Esc 立即停止并静音——即使有菜单或弹层打开。",
            "Keep quiet. One Esc stops and mutes at once, even with a menu or popup open.",
        ),
        "callout",
        "text2",
        w=fw,
        h=18,
    )
    y += 76
    # progress (StandalonePage QProgressBar 0–100; the code has no live waveform or input meter)
    cv.text(fx, y, L("进度", "Progress"), "calloutm", "text2", h=18)
    cv.text(fx, y, "62 %", "mono", "text1", w=fw, h=18, align="r")
    y += 26
    cv.rect(fx, y, fw, 6, fill="sunken", r=3)
    cv.rect(fx, y, fw * 0.62, 6, fill="accent", r=3)
    y += 30
    phases = [
        ("check", L("播放扫频并同时录音", "Play the sweep and record"), "run"),
        (
            "circle-dashed",
            L(
                "分析：反卷积 → 脉冲响应 → 衰减 / 频响 / 噪声 / 反射",
                "Analyse: deconvolve → IR → decay / FR / noise / reflections",
            ),
            "todo",
        ),
        (
            "circle-dashed",
            L("测量健康（10 项检查）与解读", "Measurement health (10 checks) and reading"),
            "todo",
        ),
    ]
    gh = len(phases) * 44
    cv.rect(fx, y, fw, gh, fill="surface", stroke="sep", r=10)
    for i, (ic, lab, st) in enumerate(phases):
        yy = y + i * 44
        if i:
            cv.hline(fx + 44, fx + fw, yy, "sep")
        if st == "run":
            cv.icon("activity", fx + 16, yy + 14, 16, "accent")
        else:
            cv.icon("circle-dashed", fx + 16, yy + 14, 16, "text3")
        cv.text(
            fx + 44,
            yy,
            lab,
            "body" if st == "run" else "callout",
            "text1" if st == "run" else "text2",
            h=44,
            w=fw - 60,
        )
    y += gh + 16
    cv.rect(fx, y, fw, 52, fill="sunken", r=10)
    cv.icon("info", fx + 14, y + 10, 16, "info")
    cv.text(
        fx + 40,
        y + 6,
        L(
            "实时输入波形和输入电平表在代码里还没有（未实现），这里不画。录完后削波、余量与丢样由“测量健康”报告。",
            "No live waveform or input meter exists in code (not implemented), so none is drawn. Clipping, headroom and dropouts are reported by Measurement health afterwards.",
        ),
        "callout",
        "text2",
        w=fw - 54,
        h=42,
        wrap=True,
        valign="t",
    )
    # right column: this take
    if cw:
        yy = TB + 84
        cv.text(cx, yy + 4, L("本次设置", "This take"), "headline", "text1", h=20)
        rows = [
            (L("电平", "Level"), "−9.0 dBFS"),
            (L("确认", "Confirmed"), L("已调低监听", "Monitoring down")),
            (L("时长", "Length"), "10 s"),
            (L("配置", "Profile"), L("人声", "Vocals")),
            (L("设备", "Device"), "fake interface"),
        ]
        for i, (k, v) in enumerate(rows):
            cv.text(cx, yy + 36 + i * 28, k, "callout", "text2", h=28)
            cv.text(cx, yy + 36 + i * 28, v, "mono", "text1", w=cw, h=28, align="r")
        yy += 36 + len(rows) * 28 + 16
        cv.hline(cx, cx + cw, yy, "sep")
        cv.text(cx, yy + 14, L("测量中已锁定", "Locked while measuring"), "captionm", "text3", h=16)
        locked = [
            L("设置", "Settings"),
            L("打开 / 打开项目", "Open / Open Project"),
            L("新测量", "New Measurement"),
            L("保存", "Save"),
            L("路径切换（音频接口 / DAW）", "Path switch (interface / DAW)"),
        ]
        for i, k in enumerate(locked):
            cv.icon("lock", cx, yy + 40 + i * 26, 12, "text3", stroke=1.25)
            cv.text(cx + 20, yy + 34 + i * 26, k, "callout", "text2", h=24)
    xr = fx + fw + (cw + 48 if cw else 0)

    def stop(y):
        lab = L("停止", "Stop")
        w = tw(lab, "bodym") + 24 + 22 + tw("Esc", "callout") + 8
        lk.button(cv, xr - w, y, lab, "danger", w=w, icon="square-stop", shortcut="Esc")
        return w

    sh.action_bar(
        cv,
        fx,
        xr,
        (L("上一步", "Back"), True),
        L(
            "测量中 · 设置、打开、新测量、保存已锁定",
            "Measuring · Settings, Open, New, Save are locked",
        ),
        "busy",
        stop,
    )
