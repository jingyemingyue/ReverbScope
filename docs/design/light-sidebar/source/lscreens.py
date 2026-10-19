# ruff: noqa
# Design-phase mockup renderer (docs only, not product code).
"""Screens for the light-sidebar baseline."""

from __future__ import annotations

import json
import math

import numpy as np

import lk
import lshell as sh
from lcharts import Plot, colorbar, legend, mnum, ramp
from lk import C, L, Canvas, tw

DEMO = np.load(lk.HERE / "demo.npz")
import os

CLI = os.environ.get("RS_DEMO_DIR", "/workspace/work/reverbscope-design/cli/demo")
RES = {p: json.load(open(f"{CLI}/position-{p}/result.json")) for p in "ab"}
CMP = json.load(open(f"{CLI}/comparison.json"))
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
    lk.chip(
        cv,
        W - 20 - tw(L("合成演示数据", "Synthetic demo data"), "callout") - 38,
        14,
        L("合成演示数据", "Synthetic demo data"),
        icon="flask-conical",
    )
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
        L("拖入录音文件，或选择一种方式开始", "Drop a recording, or choose how to start"),
        "body",
        "text3",
        h=22,
        w=cw - 40,
    )
    # path options as a segmented control with icons (one choice)
    by = y + ch - 48
    opts = [
        ("audio-lines", L("用音频接口", "Audio interface")),
        ("music", L("用 DAW", "With a DAW")),
        ("file-audio", L("导入脉冲响应", "Import IR")),
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
        ("folder-open", L("打开示例项目", "Open sample project")),
        ("folder", L("打开…", "Open…")),
        ("layers", L("打开项目…", "Open Project…")),
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
        ("⌘K", L("搜索", "Search")),
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
        "解释方式：通俗 + 术语（音乐人）· 可在 设置 ▸ 通用 修改",
        "Wording: plain + terms (Musician) · change in Settings ▸ General",
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
        lab = L("测量中 · 6.2 s", "Measuring · 6.2 s")
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
                (L("设备", "Device"), None, pop("ReverbScope fake interface")),
                (L("声道", "Channel"), None, pop(L("输出 1 → 扬声器", "Out 1 → speaker"))),
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
                (L("设备", "Device"), None, pop("ReverbScope fake interface")),
                (L("声道", "Channel"), None, pop(L("输入 1 ← 话筒", "In 1 ← mic"))),
                (
                    L("采样率", "Sample rate"),
                    L("两端一致", "Both ends match"),
                    lambda xr, yy, h: cv.text(
                        xr - 200, yy, "48 kHz", "mono", "text1", w=200, h=h, align="r"
                    ),
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
            ("ok", L("输出设备已连接", "Output connected"), None, False),
            ("ok", L("输入设备已连接", "Input connected"), None, False),
            ("ok", L("采样率一致", "Sample rates match"), "48 kHz", False),
            ("todo", L("电平确认（下一步）", "Level check (next step)"), None, False),
            ("todo", L("输入预检", "Input pre-check"), None, True),
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
                L("扫频时长", "Sweep length"),
                None,
                lambda xr, yy, h: _seg_right(
                    cv,
                    xr,
                    yy,
                    h,
                    [
                        L("短 5 s", "Short 5 s"),
                        L("标准 10 s", "Std 10 s"),
                        L("长 20 s", "Long 20 s"),
                        L("自定义", "Custom"),
                    ],
                    1,
                ),
            ),
            (
                L("录音配置", "Profile"),
                L("决定解读关注什么", "Decides what the reading focuses on"),
                lambda xr, yy, h: lk.popup(
                    cv, xr - 200, yy + (h - 28) / 2, 200, L("人声", "Vocals")
                ),
                52,
            ),
            (
                L("房间与摆位（可选）", "Room & placement (optional)"),
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
            ("ok", L("设备已连接", "Devices connected"), None, False),
            ("ok", L("采样率一致", "Sample rates match"), "48 kHz", False),
            ("warn", L("电平需确认", "Level needs confirming"), "−9.0 dBFS", False),
            ("todo", L("输入预检", "Input pre-check"), None, True),
        ],
    )
    if cw:
        y2 = TB + 84 + 36 + 4 * 32 + 20
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
        L("先勾选“我已调低监听音量”才能继续", "Tick “I have turned monitoring down” to continue"),
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
    # progress
    cv.text(fx, y, L("第 1 遍", "Pass 1"), "calloutm", "text2", h=18)
    cv.text(fx, y, "6.2 / 10.0 s", "mono", "text1", w=fw, h=18, align="r")
    y += 26
    cv.rect(fx, y, fw, 6, fill="sunken", r=3)
    cv.rect(fx, y, fw * 0.62, 6, fill="accent", r=3)
    y += 28
    # live recording trace (illustrative)
    ph = max(150, cv.H - 64 - 24 - 74 - y - 20)
    cv.rect(fx, y, fw, ph, fill="plot.bg", stroke="sep", r=10)
    cv.text(
        fx + 14,
        y + 10,
        L("输入 · 话筒（实时，示意）", "Input · mic (live, illustrative)"),
        "caption",
        "text3",
        h=16,
    )
    mid = y + ph / 2 + 8
    pts = []
    n = 520
    for i in range(n):
        t = i / n
        if t > 0.62:
            break
        f = 3 + 140 * t**2
        env = 0.35 + 0.25 * math.sin(t * 9) ** 2
        pts.append(
            (fx + 14 + t * (fw - 28), mid + math.sin(2 * math.pi * f * t) * env * (ph * 0.32))
        )
    cv.path(pts, "cur", sw=1.0)
    cv.hline(fx + 14, fx + fw - 14, mid, "grid.major")
    y += ph + 20
    # meter
    cv.text(fx, y, L("输入电平", "Input level"), "calloutm", "text2", h=18)
    cv.text(
        fx,
        y,
        L("峰值 −18.4 dBFS · 余量充足", "Peak −18.4 dBFS · headroom OK"),
        "mono",
        "text1",
        w=fw,
        h=18,
        align="r",
    )
    y += 26
    mw = fw

    def X(v):
        return fx + (v + 60) / 60 * mw

    cv.rect(fx, y, mw, 10, fill="sunken", r=5)
    cv.rect(fx, y, X(-24) - fx, 10, fill="good", r=5)
    cv.rect(X(-24) - 5, y, X(-18.4) - X(-24) + 5, 10, fill="good")
    cv.line(X(-18.4), y - 3, X(-18.4), y + 13, "text1", 1.5)
    cv.line(X(-6), y - 3, X(-6), y + 13, "warn", 1, dash=[2, 2])
    for v in (-60, -48, -36, -24, -12, -6, 0):
        cv.text(X(v) - 18, y + 14, mnum(v, 0), "monos", "text3", w=36, h=14, align="c")
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
            L("路径与用户类型切换", "Path & user-type switch"),
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


# ------------------------------------------------------------ analysis
VIEWS = [
    ("总览", "Overview"),
    ("频响", "Freq."),
    ("时域", "Time"),
    ("衰变", "Decay"),
    ("噪声", "Noise"),
    ("时频", "Time-freq."),
    ("房间", "Room"),
    ("报告", "Report"),
]


def _analysis_frame(cv, view, inspector=False, title=None, sel="b1", compare=False):
    W, H = cv.W, cv.H
    nar = narrow()
    if not nar:
        sh.sidebar(cv, sel=sel)
    x0 = 0 if nar else SB
    sub = (
        L("A-1 基准 ↔ B-1 当前", "A-1 baseline ↔ B-1 current")
        if compare
        else L("合成演示房间 · 位置 B", "Synthetic demo room · Pos. B")
    )
    end = sh.toolbar(cv, x0, title or "B-1", sub, traffic=nar)
    labels = [L(z, e) for z, e in VIEWS]
    if compare:
        labels = [L("总览", "Overview"), L("频响", "Freq."), L("衰变", "Decay"), L("噪声", "Noise")]
    if nar and not compare:
        keep = [0, 1, 3, 5]
        labels = [labels[i] for i in keep] + ["⋯"]
        selv = keep.index(view) if view in keep else 4
    else:
        selv = view
    segw = sum(tw(s, "calloutm") + 20 for s in labels) + 4
    rx = W - 16
    icons = [("panel-right", inspector), ("download", False), ("git-compare", compare)]
    for name, act in icons:
        rx -= 32
        sh.tool_icon(cv, rx, 11, name, active=act)
    sx = max(end + 24, min(x0 + (W - x0) / 2 - segw / 2, rx - 16 - segw))
    lk.segmented(cv, sx, 12, labels, selv, pad=10)
    return x0


def _fr_controls(cv, x, y, w):
    seg = [L("叠加", "Overlay"), L("差值", "Difference"), L("叠加 + 差值", "Both")]
    sw_ = lk.segmented(cv, x, y, seg, 2, pad=10)
    xx = x + sw_ + 16
    cv.text(xx, y, L("平滑", "Smoothing"), "callout", "text2", h=28)
    xx += tw(L("平滑", "Smoothing"), "callout") + 8
    lk.popup(cv, xx, y, 104, "1/6 oct", role="callout")
    xx += 104 + 16
    for lab, on in ((L("原始曲线", "Raw"), False), (L("电平对齐", "Align level"), False)):
        if xx + 24 + tw(lab, "callout") > x + w - 160:
            break
        lk.checkbox(cv, xx, y + 6, checked=on)
        xx += 24 + cv.text(xx + 24, y, lab, "callout", "text1", h=28) + 16
    # chart tools (right)
    rx = x + w
    fit = L("适配", "Fit")
    fw = tw(fit, "callout") + 12 + lk.kbd.__defaults__[0] if False else tw(fit, "callout") + 34
    rx -= fw
    cv.text(rx, y, fit, "callout", "accent.text", h=28)
    lk.kbd(cv, rx + tw(fit, "callout") + 6, y + 5, "F")
    rx -= 12
    for name, act in (("zoom-in", False), ("move", False), ("crosshair", True)):
        rx -= 28
        sh.tool_icon(cv, rx, y, name, active=act, size=16, box=28)


def _readout(cv, x, y, w, parts, hint):
    cv.rect(x, y, w, 28, fill="readout", r=6)
    xx = x + 12
    for i, (txt, color) in enumerate(parts):
        if i:
            cv.vline(xx, y + 7, y + 21, "border")
            xx += 10
        xx += cv.text(xx, y, txt, "mono", color, h=28) + 10
    hw = tw(hint, "caption")
    if xx + hw + 16 < x + w:
        cv.text(x + w - hw - 12, y, hint, "caption", "text3", h=28)


def analysis_fr(cv: Canvas):
    W, H = cv.W, cv.H
    insp = W >= 1440
    x0 = _analysis_frame(cv, 1, inspector=insp)
    iw = 288 if insp else 0
    pad = 24 if narrow() else 32
    x, xr = x0 + pad, W - pad - (iw + 0 if insp else 0)
    if insp:
        xr = W - iw - 24
    y = TB + 20
    cv.text(x, y, L("频率响应", "Frequency response"), "title1", "text1", h=28)
    meta = L(
        "B-1 当前 · A-1 基准 · 1/6 倍频程平滑 · 电平未对齐",
        "B-1 current · A-1 baseline · 1/6-oct smoothing · level not aligned",
    )
    tx = x + tw(L("频率响应", "Frequency response"), "title1") + 14
    cv.text(tx, y + 6, meta, "callout", "text3", w=xr - tx - (0 if narrow() else 140), h=20)
    if not narrow():
        lab = L("合成演示数据", "Synthetic demo")
        lk.chip(cv, xr - tw(lab, "callout") - 38, y + 2, lab, icon="flask-conical")
    y += 44
    _fr_controls(cv, x, y, xr - x)
    y += 44
    # legend
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
    mh = int(avail * 0.68)
    f = DEMO["fr_f"]
    a, b = DEMO["fr_a"], DEMO["fr_b"]
    lo, hi = 30.6, 19725.6
    p = Plot(
        cv,
        x,
        y,
        xr - x,
        mh,
        ylabel=L("电平（dB，相对）", "Level (dB, relative)"),
        yr=(-30, 30),
        show_xlabels=False,
        yminor=2,
    )
    p.frame()
    p.hatch(18, lo, None)
    p.hatch(hi, 21000, None)
    p.curve(f, a, "base", 1.5, dash=[5, 3])
    p.curve(f, b, "cur", 2.0)
    fa = float(np.interp(math.log10(109.7), np.log10(f), a))
    fb = float(np.interp(math.log10(109.7), np.log10(f), b))
    p.cursor(109.7, dots=[(fb, "cur", True), (fa, "base", False)])
    cv.text(p.px + 6, p.py + 4, L("扫频范围外", "Outside sweep"), "caption", "text3", h=14)
    # difference
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
    q.curve(f, b - a, "delta", 1.5)
    q.cursor(109.7, dots=[(fb - fa, "delta", True)], flag="109.7 Hz")
    yr_ = H - 16 - 28 - 18
    cv.text(
        x + 46,
        yr_ - 2,
        L(
            "斜线：扫频范围（31 Hz–19.7 kHz）之外，不是测量值。",
            "Hatched: outside the sweep (31 Hz–19.7 kHz); not measured.",
        ),
        "caption",
        "text3",
        h=16,
        w=xr - x - 46,
    )
    _readout(
        cv,
        x,
        H - 16 - 28,
        xr - x,
        [
            ("109.7 Hz", "text1"),
            (f"B-1 {mnum(fb, 1, True)} dB", "cur"),
            (f"A-1 {mnum(fa, 1, True)} dB", "base"),
            (f"Δ {mnum(fb - fa, 1, True)} dB", "delta"),
        ],
        L("滚轮缩放 · 拖动平移 · 双击 / F 适配", "Wheel zoom · drag pan · double-click / F fit"),
    )
    if insp:
        inspector_fr(cv, W - iw, TB, iw, H - TB, fa, fb)


def inspector_fr(cv, x, y, w, h, fa, fb):
    cv.rect(x, y, w, h, fill="sidebar")
    cv.vline(x, y, y + h, "sep")
    lk.segmented(
        cv,
        x + 16,
        y + 14,
        [L("检查", "Inspect"), L("显示", "Display"), L("解读", "Reading")],
        0,
        widths=[(w - 36) / 3] * 3,
    )
    yy = y + 60
    cv.text(x + 16, yy, L("曲线", "Curves"), "captionm", "text3", h=16)
    yy += 22
    for lab, role, col, dash, eye in (
        ("B-1", L("当前", "current"), "cur", None, True),
        ("A-1", L("基准", "baseline"), "base", [5, 3], True),
    ):
        cv.line(x + 16, yy + 14, x + 34, yy + 14, col, 2 if not dash else 1.5, dash=dash)
        adv = cv.text(x + 42, yy, lab, "bodym", "text1", h=28)
        cv.text(x + 46 + adv, yy, role, "callout", "text3", h=28)
        cv.icon("eye", x + w - 34, yy + 6, 16, "text2")
        yy += 30
    b = L("设为基准", "Set as baseline")
    bw = lk.button(cv, x + 16, yy + 4, b, "secondary", shortcut="⌘B", h=26, role="callout")
    lk.chip(
        cv, x + 16 + bw + 8, yy + 8, L("未实现", "Not impl."), h=18, tone="planned", role="caption"
    )
    yy += 48
    cv.hline(x + 16, x + w - 16, yy, "sep")
    yy += 14
    cv.text(x + 16, yy, L("光标处", "At cursor"), "captionm", "text3", h=16)
    yy += 22
    rows = [
        (L("频率", "Frequency"), "109.7 Hz", "text1"),
        ("B-1", f"{mnum(fb, 1, True)} dB", "cur"),
        ("A-1", f"{mnum(fa, 1, True)} dB", "base"),
        ("Δ", f"{mnum(fb - fa, 1, True)} dB", "delta"),
    ]
    for k, v, c in rows:
        cv.text(x + 16, yy, k, "callout", "text2", h=24)
        cv.text(x + 16, yy, v, "mono", c, w=w - 32, h=24, align="r")
        yy += 24
    yy += 12
    cv.hline(x + 16, x + w - 16, yy, "sep")
    yy += 14
    cv.text(x + 16, yy, L("检测到", "Detected"), "captionm", "text3", h=16)
    yy += 22
    cv.icon("info", x + 16, yy + 2, 16, "info")
    cv.text(
        x + 40, yy, L("共振候选 109.7 Hz", "Resonance candidate 109.7 Hz"), "bodym", "text1", h=20
    )
    dt = L(
        "高出基线 +10.7 dB · 20 dB 衰减 278 ms（滤波器余振 21 ms，可区分）",
        "+10.7 dB above baseline · 20 dB decay 278 ms (filter ringing 21 ms)",
    )
    dh_ = cv.wrap_h(dt, "callout", w - 56)
    cv.text(x + 40, yy + 22, dt, "callout", "text2", w=w - 56, h=dh_ + 2, wrap=True, valign="t")
    yy += 22 + dh_ + 10
    cv.text(
        x + 40,
        yy,
        L(
            "再测一两个位置，看它跟着房间还是位置走。",
            "Measure one or two more spots: room or position?",
        ),
        "callout",
        "text3",
        w=w - 56,
        h=40,
        wrap=True,
        valign="t",
    )


# ------------------------------------------------------------ decay
def analysis_decay(cv: Canvas):
    W, H = cv.W, cv.H
    x0 = _analysis_frame(cv, 3)
    x, xr = x0 + 32, W - 32
    y = TB + 20
    cv.text(x, y, L("衰变与频带指标", "Decay and band metrics"), "title1", "text1", h=28)
    cv.text(
        x + tw(L("衰变与频带指标", "Decay and band metrics"), "title1") + 14,
        y + 6,
        L(
            "ISO 3382-1 · Schroeder 反向积分 · B-1 当前 · A-1 基准",
            "ISO 3382-1 · Schroeder backward integration",
        ),
        "callout",
        "text3",
        h=20,
        w=420,
    )
    y += 48
    bb = RES["b"]["decay"]["broadband"]
    # metric strip — no boxes, hairline separators
    mets = [
        (
            L("RT60（T30）", "RT60 (T30)"),
            f"{bb['t30']['seconds']:.2f}",
            "s",
            f"A-1 {RES['a']['decay']['broadband']['t30']['seconds']:.2f} s",
        ),
        ("EDT", f"{bb['edt']['seconds']:.2f}", "s", f"T20 {bb['t20']['seconds']:.2f} s"),
        (
            "C50",
            mnum(bb["c50"]["value"], 1, True),
            "dB",
            f"C80 {mnum(bb['c80']['value'], 1, True)} dB",
        ),
        ("D50", f"{bb['d50']['value']:.0f}", "%", f"Ts {bb['centre_time']['value'] * 1000:.1f} ms"),
    ]
    mw = (xr - x) / 4
    for i, (k, v, u, sub) in enumerate(mets):
        mx = x + i * mw
        if i:
            cv.vline(mx - 1, y + 4, y + 60, "sep")
        ix = mx + (16 if i else 0)
        cv.text(ix, y, k, "callout", "text2", h=18)
        adv = cv.text(ix, y + 18, v, "num", "text1", h=32)
        cv.text(ix + adv + 4, y + 30, u, "callout", "text2", h=18)
        cv.text(ix, y + 50, sub, "monos", "text3", h=16)
    y += 84
    table_w = 330
    cw = xr - x - table_w - 32
    # schroeder
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
    bottom = H - 24
    avail = bottom - y
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
        ylabel=L("能量衰变（dB）", "Energy decay (dB)"),
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
    t30 = bb["t30"]["seconds"]
    # fit: -60 dB per t30, through -5 dB at onset of range
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
        xlabel=L("倍频程中心（Hz）", "Octave centre (Hz)"),
        yfmt=lambda v: f"{v:.1f}",
    )
    # custom grid at band centres
    bands = RES["b"]["decay"]["bands"]
    centers = [63, 125, 250, 500, 1000, 2000, 4000, 8000]
    import lcharts

    old = lcharts.FREQ_MAJOR
    lcharts.FREQ_MAJOR = tuple(centers)
    q.frame()
    lcharts.FREQ_MAJOR = old
    q.cv.line(q.px, q.Y(t30), q.px + q.pw, q.Y(t30), C("cur", 0.6), 1, dash=[3, 3])
    lab = L(f"宽带 T30 {t30:.2f} s", f"Broadband T30 {t30:.2f} s")
    cv.text(
        q.px + q.pw - tw(lab, "caption") - 6, q.Y(t30) - 16, lab, "caption", "accent.text", h=14
    )
    for key, col, dash, sw_ in (
        ("t30", "cur", None, 2.0),
        ("t20", "d7", [5, 3], 1.5),
        ("edt", "d2", [1.5, 2.5], 1.5),
    ):
        prev = None
        for c, bd in zip(centers, bands):
            m = bd[key]
            v = m["seconds"]
            ok = m["validity"] == "valid"
            X, Y = q.X(c), q.Y(v)
            if ok and prev:
                cv.path([prev, (X, Y)], col, sw=sw_, dash=dash)
            if ok:
                cv.circle(X, Y, 3.2, fill=col)
                prev = (X, Y)
            else:
                cv.circle(X, Y, 3.6, fill="plot.bg", stroke=col, sw=1.5)
                cv.text(X + 5, Y - 16, "?", "captionm", "warn", h=14)
                prev = None
    legend(
        cv,
        q.px + 10,
        q.py + 6,
        [("T30", None, "cur", None), ("T20", None, "d7", [5, 3]), ("EDT", None, "d2", [1.5, 2.5])],
    )
    # table
    tx = xr - table_w
    cv.text(tx, y - 22, L("分频带 · B-1", "Per band · B-1"), "headline", "text1", h=18)
    cols = [L("频带", "Band"), "EDT", "T20", "T30", "C50"]
    cwid = [70, 64, 64, 64, 68]
    ty = y + 2
    cv.hline(tx, xr, ty + 26, "sep")
    cx_ = tx
    for c, w in zip(cols, cwid):
        cv.text(cx_, ty, c, "captionm", "text3", w=w - 8, h=26, align="l" if c == cols[0] else "r")
        cx_ += w
    ty += 28
    rows = [("宽带" if lk.zh() else "Broadband", bb)] + [(bd["band_label"], bd) for bd in bands]
    for i, (lab, bd) in enumerate(rows):
        rh = 30
        if i % 2 == 1:
            cv.rect(tx - 6, ty, table_w + 6, rh, fill=C("sunken", 0.7), r=4)
        cx_ = tx
        cv.text(cx_, ty, lab, "callout" if i else "calloutm", "text1", w=cwid[0], h=rh)
        cx_ += cwid[0]
        for key, w in zip(("edt", "t20", "t30"), cwid[1:4]):
            m = bd[key]
            ok = m["validity"] == "valid"
            s = f"{m['seconds']:.2f}" if ok else f"({m['seconds']:.2f})?"
            cv.text(
                cx_,
                ty,
                s,
                "mono" if ok else "mono",
                "text1" if ok else "warn",
                w=w - 8,
                h=rh,
                align="r",
            )
            cx_ += w
        cv.text(
            cx_,
            ty,
            mnum(bd["c50"]["value"], 1, True),
            "mono",
            "text1",
            w=cwid[4] - 8,
            h=rh,
            align="r",
        )
        ty += rh
    ty += 10
    cv.icon("triangle-alert", tx, ty + 2, 14, "warn")
    cv.text(
        tx + 20,
        ty,
        L(
            "(…)? 不可靠：63 Hz、250 Hz 的 EDT 主要反映直达声。悬停看原因。",
            "(…)? unreliable: EDT at 63 Hz and 250 Hz mostly describes the direct sound.",
        ),
        "caption",
        "text2",
        w=table_w - 20,
        h=34,
        wrap=True,
        valign="t",
    )


# ------------------------------------------------------------ waterfall
def analysis_waterfall(cv: Canvas):
    W, H = cv.W, cv.H
    x0 = _analysis_frame(cv, 5)
    x, xr = x0 + 32, W - 32
    y = TB + 20
    cv.text(x, y, L("瀑布图", "Waterfall"), "title1", "text1", h=28)
    cv.text(
        x + tw(L("瀑布图", "Waterfall"), "title1") + 14,
        y + 6,
        L(
            "累积频谱衰减 · B-1 · 显示平滑 1/6 oct · 切片起点相对直达声",
            "Cumulative spectral decay · B-1 · 1/6-oct display smoothing",
        ),
        "callout",
        "text3",
        h=20,
        w=520,
    )
    y += 44
    sw_ = lk.segmented(cv, x, y, [L("瀑布", "Waterfall"), L("声谱", "Spectrogram")], 0, pad=12)
    xx = x + sw_ + 20
    for lab, val, w in ((L("底限", "Floor"), "−60 dB", 92), (L("时间", "Time"), "0–290 ms", 112)):
        xx += cv.text(xx, y, lab, "callout", "text2", h=28) + 8
        lk.popup(cv, xx, y, w, val, role="callout")
        xx += w + 16
    lk.toggle(cv, xx, y + 5, on=False)
    cv.text(xx + 40, y, L("透视", "Perspective"), "callout", "text1", h=28)
    colorbar(cv, xr - 150, y + 11, 120, "0", f"{DEMO['wf_times_ms'][-1]:.0f}", "ms")
    y += 48
    f = DEMO["wf_freqs_hz"]
    t = DEMO["wf_times_ms"]
    lv = DEMO["wf_levels_db"]
    lf = np.log2(f)
    sm = np.empty_like(lv)
    for j in range(len(f)):
        msk = np.abs(lf - lf[j]) <= 1 / 12
        sm[:, j] = 10 * np.log10(np.mean(10 ** (lv[:, msk] / 10), axis=1))
    lv = sm
    top = np.nanmax(lv)
    bottom = H - 16 - 28 - 12
    p = Plot(
        cv,
        x,
        y,
        xr - x,
        bottom - y,
        xr=(20, 20000),
        yr=(-60, 0),
        ystep=10,
        yminor=5,
        ylabel=L("电平（dB，相对最大值）", "Level (dB re max)"),
        xlabel=L("频率（Hz）", "Frequency (Hz)"),
    )
    p.frame()
    n = len(t)
    sel = int(np.argmin(np.abs(t - 100))) if t[-1] > 100 else n // 3
    for i in range(n - 1, -1, -1):
        col = ramp(i / max(1, n - 1))
        col.setAlphaF(0.9)
        p.curve(f, np.maximum(lv[i] - top, -61), col, 1.1)
    p.curve(f, np.maximum(lv[sel] - top, -61), "cursor", 2.4)
    p.hatch(18, 30.6)
    p.hatch(19725.6, 21000)
    v = float(np.interp(math.log10(109.7), np.log10(f), lv[sel] - top))
    p.cursor(109.7, dots=[(v, "cursor", True)], flag="109.7 Hz")
    _readout(
        cv,
        x,
        H - 16 - 28,
        xr - x,
        [
            (L(f"切片 {t[sel]:.0f} ms", f"Slice {t[sel]:.0f} ms"), "text1"),
            ("109.7 Hz", "text1"),
            (f"{mnum(v, 1)} dB", "text1"),
            (
                L(
                    "共振候选：衰减明显慢于周围",
                    "Resonance candidate: decays slower than its surroundings",
                ),
                "text2",
            ),
        ],
        L("↑↓ 换切片 · 滚轮缩放", "↑↓ slice · wheel zoom"),
    )


# ------------------------------------------------------------ compare
def compare(cv: Canvas):
    W, H = cv.W, cv.H
    x0 = _analysis_frame(cv, 0, title=L("对比", "Compare"), sel="b1", compare=True)
    # override segmented highlight: compare is its own mode -> draw a compare header instead
    x, xr = x0 + 32, W - 32
    y = TB + 20
    cv.text(x, y, L("对比", "Compare"), "title1", "text1", h=28)
    ax = x + tw(L("对比", "Compare"), "title1") + 16
    ax += lk.chip(cv, ax, y + 2, L("A-1 · 基准", "A-1 · baseline"), tone="neutral") + 8
    cv.icon("arrow-right", ax, y + 6, 16, "text3")
    ax += 24
    ax += lk.chip(cv, ax, y + 2, L("B-1 · 当前", "B-1 · current"), tone="accent") + 12
    cv.text(
        ax,
        y + 2,
        L(
            "可比 · 共同频带 31 Hz–19.7 kHz · 未做电平对齐",
            "Comparable · common band 31 Hz–19.7 kHz",
        ),
        "callout",
        "text3",
        h=24,
        w=xr - ax - 110,
    )
    lk.button(
        cv, xr - 92, y, L("交换", "Swap"), "secondary", icon="refresh-cw", h=28, role="callout"
    )
    y += 48
    gap = 32
    cw = (xr - x - gap) / 2
    ch = 280
    cv.text(x, y, L("频响差值 B − A", "Response difference B − A"), "headline", "text1", h=18)
    cv.text(x + cw + gap, y, L("分频带 T30", "T30 by band"), "headline", "text1", h=18)
    y += 26
    f = DEMO["fr_f"]
    p = Plot(
        cv,
        x,
        y,
        cw,
        ch,
        yr=(-15, 15),
        ystep=5,
        yminor=0,
        ylabel="Δ dB",
        xlabel=L("频率（Hz）", "Frequency (Hz)"),
    )
    p.frame()
    p.hatch(18, 30.6)
    p.hatch(19725.6, 21000)
    p.curve(f, DEMO["fr_b"] - DEMO["fr_a"], "delta", 1.5)
    centers = [63, 125, 250, 500, 1000, 2000, 4000, 8000]
    import lcharts

    q = Plot(
        cv,
        x + cw + gap,
        y,
        cw,
        ch,
        xr=(44, 11300),
        yr=(0, 1.0),
        ystep=0.2,
        yminor=0,
        ylabel=L("T30（s）", "T30 (s)"),
        xlabel=L("倍频程中心（Hz）", "Octave centre (Hz)"),
        yfmt=lambda v: f"{v:.1f}",
    )
    old = lcharts.FREQ_MAJOR
    lcharts.FREQ_MAJOR = tuple(centers)
    q.frame()
    lcharts.FREQ_MAJOR = old
    for pos, col, dash, sw_ in (("a", "base", [5, 3], 1.5), ("b", "cur", None, 2.0)):
        pts = [
            (q.X(c), q.Y(bd["t30"]["seconds"]))
            for c, bd in zip(centers, RES[pos]["decay"]["bands"])
        ]
        cv.path(pts, col, sw=sw_, dash=dash)
        for X, Y in pts:
            cv.circle(X, Y, 3, fill=col if pos == "b" else "plot.bg", stroke=col, sw=1.5)
    legend(
        cv,
        q.px + 10,
        q.py + 6,
        [
            ("A-1", L("基准", "baseline"), "base", [5, 3]),
            ("B-1", L("当前", "current"), "cur", None),
        ],
    )
    y += ch + 24
    # table
    cv.text(x, y, L("指标", "Metrics"), "headline", "text1", h=18)
    y += 26
    cols = [
        (L("指标", "Metric"), 220, "l"),
        (L("A-1 基准", "A-1 baseline"), 130, "r"),
        (L("B-1 当前", "B-1 current"), 130, "r"),
        ("Δ", 130, "r"),
        (L("变化", "Change"), 0, "l"),
    ]
    total_fixed = sum(c[1] for c in cols)
    cols[-1] = (cols[-1][0], xr - x - total_fixed, "l")
    cv.hline(x, xr, y + 26, "sep")
    cx_ = x
    for lab, w, al in cols:
        cv.text(
            cx_ + (12 if al == "l" and cx_ > x else 0),
            y,
            lab,
            "captionm",
            "text3",
            w=w - 12,
            h=26,
            align=al,
        )
        cx_ += w
    y += 28

    def row(name):
        for g in ("decay", "noise"):
            for r in CMP[g]:
                if r["name"] == name:
                    return r

    items = [
        ("broadband.t30", L("RT60（T30）", "RT60 (T30)"), 2, 1, "s"),
        ("broadband.edt", "EDT", 2, 1, "s"),
        ("broadband.c50", "C50", 1, 1, "dB"),
        ("broadband.c80", "C80", 1, 1, "dB"),
        ("broadband.d50", "D50", 1, 1, "%"),
        ("noise.rms_dbfs", L("本底噪声 RMS（未校准）", "Noise RMS (uncal.)"), 1, 1, "dBFS"),
        ("band.63 Hz.edt", L("63 Hz EDT", "63 Hz EDT"), 2, 1, "s"),
    ]
    rh = 32
    for i, (key, lab, d, _, unit) in enumerate(items):
        r = row(key)
        if y + rh > H - 12:
            break
        if i % 2 == 1:
            cv.rect(x - 8, y, xr - x + 16, rh, fill=C("sunken", 0.7), r=4)
        cx_ = x
        cv.text(cx_, y, lab, "body", "text1", w=cols[0][1], h=rh)
        cx_ += cols[0][1]
        sign = unit == "dB"
        u = " " + unit if unit != "%" else " %"
        du = {"dBFS": " dB", "%": " pp"}.get(unit, u)
        cv.text(
            cx_,
            y,
            mnum(r["baseline"], d, sign) + u,
            "mono",
            "text2",
            w=cols[1][1] - 12,
            h=rh,
            align="r",
        )
        cx_ += cols[1][1]
        cv.text(
            cx_,
            y,
            mnum(r["candidate"], d, sign) + u,
            "mono",
            "text1",
            w=cols[2][1] - 12,
            h=rh,
            align="r",
        )
        cx_ += cols[2][1]
        if r["validity"] != "valid":
            cv.text(
                cx_,
                y,
                L("不可比", "Not comparable"),
                "callout",
                "warn",
                w=cols[3][1] - 12,
                h=rh,
                align="r",
            )
            cx_ += cols[3][1]
            cv.icon("triangle-alert", cx_ + 12, y + 9, 14, "warn")
            cv.text(
                cx_ + 32,
                y,
                L(
                    "B-1 的 EDT 不可靠：衰变曲线在直达声处下降 5.8 dB",
                    "B-1 EDT unreliable: 5.8 dB drop across the direct sound",
                ),
                "callout",
                "text2",
                w=cols[4][1] - 40,
                h=rh,
            )
        else:
            dv = r["delta"]
            ds = mnum(dv, d, True) + du
            if r.get("delta_percent") is not None:
                ds += f"  {mnum(r['delta_percent'], 0, True)} %"
            cv.text(cx_, y, ds, "monom", "text1", w=cols[3][1] - 12, h=rh, align="r")
            cx_ += cols[3][1]
            # centred diverging bar
            bw = cols[4][1] - 24
            mid = cx_ + 12 + bw / 2
            scale = {"s": 0.3, "dB": 20, "%": 5, "dBFS": 20}[unit]
            L_ = max(-1, min(1, dv / scale)) * (bw / 2)
            cv.vline(mid, y + 8, y + rh - 8, "border")
            cv.rect(min(mid, mid + L_), y + 12, abs(L_), 8, fill=C("delta", 0.85), r=2)
        y += rh


# ------------------------------------------------------------ settings
def settings(cv: Canvas):
    W, H = cv.W, cv.H
    analysis_fr(cv)
    cv.rect(0, 0, W, H, fill=C("scrim", 0.28 if lk.MODE["theme"] == "light" else 0.5))
    sw_, shh = 780, 600
    sx, sy = (W - sw_) / 2, (H - shh) / 2
    cv.shadow(sx, sy, sw_, shh, r=12, depth=30, alpha=0.30, dy=16)
    cv.rect(sx, sy, sw_, shh, fill="window", stroke=C("shadow", 0.15), r=12)
    nav_w = 200
    p = cv.p
    p.save()
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QPainterPath

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
        ("flask-conical", L("高级", "Advanced")),
        (None, None),
        ("info", L("关于", "About")),
    ]
    yy = sy + 52
    for i, (ic, lab) in enumerate(items):
        if ic is None:
            cv.hline(sx + 16, sx + nav_w - 16, yy + 6, "sep")
            yy += 12
            continue
        if i == 0:
            cv.rect(sx + 8, yy, nav_w - 16, 30, fill="sel.sidebar", r=6)
        cv.icon(ic, sx + 18, yy + 7, 16, "accent.text" if i == 0 else "text2")
        cv.text(sx + 44, yy, lab, "bodym" if i == 0 else "body", "text1", h=30)
        yy += 32
    cv.text(sx + 18, sy + shh - 34, "ReverbScope 0.5.0b3", "caption", "text3", h=20)
    cx, cw = sx + nav_w + 28, sw_ - nav_w - 56
    cy = sy + 18
    cv.text(cx, cy, L("通用", "General"), "title2", "text1", h=24)
    cv.icon("x", sx + sw_ - 34, sy + 18, 16, "text3")
    cy += 40

    def pop(label, w=180):
        return lambda xr, yy, h: lk.popup(cv, xr - w, yy + (h - 28) / 2, w, label, role="callout")

    cy += (
        sh.group(
            cv,
            cx,
            cy,
            cw,
            [
                (
                    L("语言", "Language"),
                    L("重启后完全生效", "Fully applies after restart"),
                    pop(L("简体中文", "English")),
                    52,
                ),
                (
                    L("外观", "Appearance"),
                    None,
                    lambda xr, yy, h: _seg_right(
                        cv,
                        xr,
                        yy,
                        h,
                        [L("跟随系统", "System"), L("浅色", "Light"), L("深色", "Dark")],
                        0,
                    ),
                ),
                (
                    L("减少动态效果", "Reduce motion"),
                    None,
                    lambda xr, yy, h: lk.toggle(cv, xr - 32, yy + (h - 18) / 2, False),
                ),
            ],
        )
        + 20
    )
    cv.text(cx, cy, L("结果怎么解释", "How results are explained"), "captionm", "text3", h=18)
    cy += 24
    # user type tiles
    modes = [
        ("house", L("普通用户", "Everyday"), L("通俗", "Plain")),
        ("music", L("音乐人 · 录音爱好者", "Musician"), L("通俗 + 术语", "Plain + terms")),
        ("sliders-vertical", L("专业人士", "Professional"), L("专业", "Pro")),
    ]
    tw_ = (cw - 16) / 3
    for i, (ic, lab, sub) in enumerate(modes):
        tx = cx + i * (tw_ + 8)
        sel = i == 1
        cv.rect(
            tx,
            cy,
            tw_,
            76,
            fill="accent.soft" if sel else "surface",
            stroke="accent" if sel else "sep",
            r=10,
            sw=1.5 if sel else 1,
        )
        cv.icon(ic, tx + 14, cy + 14, 20, "accent.text" if sel else "text2")
        if sel:
            cv.icon("circle-check", tx + tw_ - 30, cy + 14, 16, "accent")
        cv.text(tx + 14, cy + 40, lab, "bodym", "text1", w=tw_ - 20, h=18)
        cv.text(tx + 14, cy + 56, sub, "caption", "text2", w=tw_ - 20, h=14)
    cy += 92
    cy += (
        sh.group(
            cv,
            cx,
            cy,
            cw,
            [
                (
                    L("解释方式", "Wording"),
                    None,
                    lambda xr, yy, h: _seg_right(
                        cv,
                        xr,
                        yy,
                        h,
                        [L("通俗", "Plain"), L("通俗 + 术语", "Plain + terms"), L("专业", "Pro")],
                        1,
                    ),
                ),
                (
                    L("默认细节", "Default detail"),
                    None,
                    lambda xr, yy, h: _seg_right(
                        cv,
                        xr,
                        yy,
                        h,
                        [L("精简", "Brief"), L("标准", "Standard"), L("详细", "Full")],
                        1,
                    ),
                ),
            ],
        )
        + 16
    )
    cv.rect(cx, cy, cw, 60, fill="sunken", r=10)
    cv.text(
        cx + 14,
        cy + 8,
        L("预览 · 同一条解读，数字不变", "Preview · same reading, same numbers"),
        "caption",
        "text3",
        h=16,
    )
    cv.icon("info", cx + 14, cy + 30, 16, "info")
    cv.text(
        cx + 38,
        cy + 26,
        L(
            "低频 · 低频比中频散得慢（T30 0.82 s 对 0.45 s），人声会发闷。",
            "Low end · Bass decays slower than mids (T30 0.82 s vs 0.45 s); vocals turn boxy.",
        ),
        "callout",
        "text1",
        w=cw - 52,
        h=40,
        wrap=True,
        valign="t",
    )


# ------------------------------------------------------------ icon sheet
ICON_SPEC = [
    ("plus", "新测量 New Measurement ⌘N", 16, "侧栏"),
    ("search", "搜索测量 ⌘K", 16, "侧栏"),
    ("folder-open", "项目 / 打开示例项目", 16, "侧栏、首页"),
    ("folder", "打开… ⌘O", 16, "首页"),
    ("layers", "打开项目… ⇧⌘O", 16, "首页"),
    ("history", "最近", 14, "侧栏"),
    ("settings", "设置 ⌘,", 16, "侧栏底、设置导航"),
    ("circle-help", "帮助", 16, "侧栏底"),
    ("message-square", "反馈", 16, "侧栏底"),
    ("panel-left", "显示/隐藏侧栏 ⌥⌘S", 16, "标题栏"),
    ("panel-right", "检查器 ⌥⌘I", 18, "工具栏"),
    ("download", "导出 ⌘E（未实现）", 18, "工具栏"),
    ("git-compare", "对比 ⌘0", 18, "工具栏"),
    ("save", "保存 ⌘S", 18, "测量工具栏"),
    ("audio-lines", "音频接口路径", 16, "首页、设置·音频"),
    ("music", "DAW 路径 / 音乐人", 16, "首页、用户类型"),
    ("file-audio", "导入脉冲响应", 16, "首页"),
    ("mic", "录音配置 / 设置·测量", 14, "首页、设置"),
    ("arrow-right", "开始（composer）", 20, "首页"),
    ("chevron-left", "上一步", 16, "操作栏"),
    ("square-stop", "停止 Esc", 16, "操作栏（发声时）"),
    ("lock", "测量中锁定", 14, "侧栏、步骤、工具栏"),
    ("activity", "运行中 / 测量中条目", 14, "步骤、侧栏"),
    ("circle-check", "检查通过 / 已选", 16, "就绪检查"),
    ("triangle-alert", "警告 / 需确认", 16, "就绪检查、操作栏、列表"),
    ("circle-dashed", "待完成", 16, "就绪检查"),
    ("info", "提示 / 信息", 16, "解读、检查器"),
    ("crosshair", "光标工具 V", 16, "图表工具"),
    ("move", "平移 H", 16, "图表工具"),
    ("zoom-in", "框选缩放 Z", 16, "图表工具"),
    ("eye", "显示/隐藏曲线", 16, "检查器"),
    ("flask-conical", "合成演示数据 / 高级", 14, "标签、设置"),
    ("refresh-cw", "交换基准", 16, "对比"),
    ("house", "普通用户", 20, "用户类型"),
    ("sliders-vertical", "专业人士", 20, "用户类型"),
    ("cable", "连接", 20, "首页说明"),
    ("chevron-down", "下拉", 14, "弹出按钮"),
    ("chevron-right", "展开 / 进入", 16, "分组行"),
    ("x", "关闭", 16, "设置窗口"),
    ("check", "复选 / 完成步骤", 14, "复选框、步骤"),
]


def icon_sheet(cv: Canvas):
    W, H = cv.W, cv.H
    cv.text(
        32,
        24,
        L(
            "图标规格 · Lucide 1.59.0（ISC）· 线宽 1.5 px",
            "Icon spec · Lucide 1.59.0 (ISC) · 1.5 px stroke",
        ),
        "title2",
        "text1",
        h=26,
    )
    cv.text(
        32,
        52,
        L(
            "同一家族、同一线宽；16 px 用于侧栏/按钮/行内，18 px 工具栏，20 px 首页与用户类型，14 px 标签与小控件。",
            "One family, one stroke; 16 px sidebar/buttons/inline, 18 px toolbar, 20 px home & user type, 14 px chips.",
        ),
        "callout",
        "text2",
        h=18,
        w=W - 64,
    )
    cols = 4
    cw_ = (W - 64) / cols
    y0 = 92
    rh = 40
    for i, (name, fn, size, where) in enumerate(ICON_SPEC):
        c, r = i % cols, i // cols
        x, y = 32 + c * cw_, y0 + r * rh
        cv.rect(x, y + 4, 32, 32, fill="surface", stroke="sep", r=7)
        cv.icon(name, x + 16 - size / 2, y + 20 - size / 2, size, "text1")
        cv.text(x + 42, y + 4, fn, "callout", "text1", w=cw_ - 50, h=16)
        cv.text(x + 42, y + 20, f"{name} · {size} · {where}", "caption", "text3", w=cw_ - 50, h=16)
    y = y0 + math.ceil(len(ICON_SPEC) / cols) * rh + 16
    cv.hline(32, W - 32, y, "sep")
    y += 16
    cv.text(32, y, L("状态", "States"), "headline", "text1", h=18)
    y += 28
    states = [
        (L("默认", "Default"), "text2", None),
        (L("悬停", "Hover"), "text1", "hover"),
        (L("激活", "Active"), "accent.text", "accent.soft"),
        (L("禁用", "Disabled"), "disabled", None),
        (L("危险", "Danger"), "on.crit", "crit"),
    ]
    x = 32
    for lab, col, bg in states:
        if bg:
            cv.rect(x, y, 30, 30, fill=bg, r=7)
        cv.icon("crosshair" if lab != L("危险", "Danger") else "square-stop", x + 6, y + 6, 18, col)
        cv.text(x + 40, y, lab, "callout", "text2", h=30)
        x += 140
    x += 20
    cv.text(
        x,
        y,
        L(
            "图标 + 文字：间距 6–8 px，图标中心对齐文字 x 高度中线；不单用颜色表达状态。",
            "Icon + label: 6–8 px gap, icon centred on the text x-height; state never by colour alone.",
        ),
        "callout",
        "text2",
        w=W - x - 32,
        h=30,
    )
