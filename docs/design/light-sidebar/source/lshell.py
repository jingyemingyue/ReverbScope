# ruff: noqa
# Design-phase mockup renderer (docs only, not product code).
"""Window chrome: vibrancy sidebar, unified toolbar, stepper, fixed action bar."""

from __future__ import annotations

from PySide6.QtGui import QColor

import lk
from lk import C, L, Canvas, kbd, tw

SB = lk.SIDEBAR_W
TB = lk.TOOLBAR_H


def project_tree(sel="b1", busy_item=None):
    """Rows for the demo project. kind: proj / pos / take."""
    return [
        ("proj", "folder-open", L("合成演示房间", "Synthetic demo room"), None, None),
        ("pos", None, L("A · 靠近桌面和侧墙", "A · Near desk and side wall"), None, None),
        ("take", "a1", "A-1", L("基准", "Baseline"), "warn"),
        ("pos", None, L("B · 从桌面向后移动 1 m", "B · 1 m back from desk"), None, None),
        ("take", "b1", "B-1", None, "warn"),
    ] + ([("take", "new", L("B-2 · 测量中", "B-2 · measuring"), None, "live")] if busy_item else [])


def sidebar(
    cv: Canvas, tree=None, sel=None, busy=False, recent=None, empty=False, hover_settings_tip=False
):
    H = cv.H
    cv.gradient_v(0, 0, SB, H, "sidebar.top", "sidebar.bot")
    cv.vline(SB - 1, 0, H, "sep")
    lk.traffic_lights(cv, 20, 20)
    cv.icon("panel-left", SB - 36, 18, 16, "text3")
    # app row
    lk.app_icon(cv, 20, 58, 20)
    cv.text(48, 56, "ReverbScope", "headline", "text1", h=24)
    y = 96
    for icon, lab, key, dis in (
        (("plus", L("新测量", "New Measurement"), "⌘N", busy)),
        (("search", L("搜索测量", "Search"), "⌘K", False)),
    ):
        col = "disabled" if dis else "text1"
        cv.icon(icon, 20, y + 8, 16, "disabled" if dis else "text2")
        cv.text(44, y, lab, "body", col, h=32, w=150)
        if dis:
            cv.icon("lock", SB - 34, y + 9, 14, "disabled")
        else:
            kbd(cv, SB - 20 - max(18, tw(key, "kbd") + 10), y + 7, key)
        y += 32
    y += 16
    if empty:
        cv.text(20, y, L("最近", "Recent"), "captionm", "text3", h=20)
        y += 24
        cv.text(
            20,
            y,
            L("还没有测量。保存后会出现在这里。", "No measurements yet."),
            "callout",
            "text3",
            w=SB - 40,
            h=40,
            wrap=True,
            valign="t",
        )
    else:
        cv.text(20, y, L("项目", "Project"), "captionm", "text3", h=20)
        y += 24
        for kind, key, lab, badge, flag in tree or project_tree():
            h = 30
            if kind == "take" and key == sel:
                cv.rect(10, y, SB - 20, h, fill="sel.sidebar", r=6)
            if kind == "proj":
                cv.icon(key, 20, y + 7, 16, "text2")
                cv.text(44, y, lab, "bodym", "text1", h=h, w=SB - 64)
            elif kind == "pos":
                cv.text(32, y, lab, "callout", "text2", h=h, w=SB - 52)
            else:
                x = 48
                if flag == "live":
                    cv.icon("activity", 30, y + 8, 14, "accent")
                adv = cv.text(x, y, lab, "bodym" if key == sel else "body", "text1", h=h)
                if badge:
                    lk.chip(cv, x + adv + 8, y + 6, badge, h=18, tone="neutral", role="caption")
                if flag == "warn":
                    cv.icon("triangle-alert", SB - 36, y + 8, 14, "warn")
            y += h
        y += 16
        cv.text(20, y, L("最近", "Recent"), "captionm", "text3", h=20)
        y += 24
        for lab in recent or [
            L("B-1 · 合成演示房间", "B-1 · Synthetic demo room"),
            L("A-1 · 合成演示房间", "A-1 · Synthetic demo room"),
        ]:
            cv.icon("history", 20, y + 8, 14, "text3")
            cv.text(42, y, lab, "callout", "text2", h=30, w=SB - 62)
            y += 30
    # bottom
    cv.hline(10, SB - 10, H - 48, "sep")
    x = 18
    for icon, lab in (("settings", L("设置", "Settings")), ("circle-help", L("帮助", "Help"))):
        dis = busy and icon == "settings"
        col = "disabled" if dis else "text2"
        cv.icon(icon, x, H - 32, 16, col)
        x += 22 + cv.text(x + 22, H - 40, lab, "callout", col, h=32) + 18
    fb = L("反馈", "Feedback")
    fw = tw(fb, "callout")
    cv.icon("message-square", SB - 20 - fw - 22, H - 32, 16, "text2")
    cv.text(SB - 20 - fw, H - 40, fb, "callout", "text2", h=32)
    if hover_settings_tip:
        tip = L("测量进行中 · 停止或结束后可用", "Measuring · available after Stop or finish")
        w = tw(tip, "callout") + 20
        cv.shadow(14, H - 82, w, 28, r=6, depth=8, alpha=0.18, dy=3)
        cv.rect(14, H - 82, w, 28, fill="surface", stroke="sep", r=6)
        cv.text(24, H - 82, tip, "callout", "text1", h=28)


def toolbar(cv: Canvas, x0, title, subtitle=None, sep=True, traffic=False):
    """Unified title/toolbar (52). Returns x after title block."""
    if traffic:
        lk.traffic_lights(cv, 20, 20)
        cv.icon("panel-left", 88, 18, 16, "text3")
        x0 = 120
    tx = x0 + 20
    if subtitle:
        cv.text(tx, 8, title, "headline", "text1", h=20)
        cv.text(tx, 26, subtitle, "caption", "text3", h=16)
        end = tx + max(tw(title, "headline"), tw(subtitle, "caption"))
    else:
        cv.text(tx, 0, title, "headline", "text1", h=TB)
        end = tx + tw(title, "headline")
    if sep:
        cv.hline(x0 if not traffic else 0, cv.W, TB - 1, "sep")
    return end


def tool_icon(cv, x, y, name, active=False, disabled=False, size=18, box=30):
    if active:
        cv.rect(x, y, box, box, fill="accent.soft", r=7)
    col = "accent.text" if active else ("disabled" if disabled else "text2")
    cv.icon(name, x + (box - size) / 2, y + (box - size) / 2, size, col)
    return box


def action_bar(cv: Canvas, x0, x1, left, status, status_tone, right_fn, H=None):
    """Fixed bottom bar (64): hairline top; content aligned to [x0, x1] (form column)."""
    H = H or cv.H
    y = H - 64
    cv.rect(lk.SIDEBAR_W if x0 > lk.SIDEBAR_W else 0, y, cv.W, 64, fill=C("window", 0.94))
    cv.hline(lk.SIDEBAR_W if x0 > lk.SIDEBAR_W else 0, cv.W, y, "sep")
    lw = 0
    if left:
        lab, dis = left
        lw = lk.button(cv, x0, y + 18, lab, "secondary", icon="chevron-left", disabled=dis)
    rw = right_fn(y + 18)
    if status:
        ic = {"warn": "triangle-alert", "info": "info", "busy": "lock", "good": "circle-check"}[
            status_tone
        ]
        col = {"warn": "warn", "info": "text3", "busy": "text3", "good": "good"}[status_tone]
        sx = x0 + lw + 16
        cv.icon(ic, sx, y + 24, 16, col)
        cv.text(
            sx + 22,
            y + 18,
            status,
            "callout",
            "text2" if status_tone != "warn" else "warn",
            w=x1 - rw - 16 - sx - 22,
            h=28,
        )
    return y


def stepper(cv: Canvas, x, y, w, steps, cur, locked=(), running=None, done=()):
    """Horizontal Apple-like stepper. steps: list of labels."""
    n = len(steps)
    seg = w / n
    for i, lab in enumerate(steps):
        cx = x + seg * i + 14
        state = (
            "run"
            if running == i
            else "lock"
            if i in locked
            else "done"
            if i in done
            else "cur"
            if i == cur
            else "todo"
        )
        if i < n - 1:
            lx0 = cx + 14 + tw(lab, "calloutm") + 14 + 8
            cv.hline(
                lx0,
                x + seg * (i + 1) + 14 - 14 - 8,
                y + 14,
                "border" if state not in ("done", "lock") else "accent",
            )
        if state == "done":
            cv.circle(cx, y + 14, 11, fill="accent")
            cv.icon("check", cx - 7, y + 7, 14, "on.accent", stroke=2)
        elif state == "cur":
            cv.circle(cx, y + 14, 11, fill="accent")
            cv.text(cx - 11, y + 3, str(i + 1), "captionm", "on.accent", w=22, h=22, align="c")
        elif state == "run":
            cv.circle(cx, y + 14, 11, fill="accent.soft", stroke="accent", sw=1.5)
            cv.icon("activity", cx - 7, y + 7, 14, "accent.text")
        elif state == "lock":
            cv.circle(cx, y + 14, 11, fill="sunken", stroke="border")
            cv.icon("lock", cx - 6, y + 8, 12, "text3", stroke=1.25)
        else:
            cv.circle(cx, y + 14, 11, fill="window", stroke="control", sw=1)
            cv.text(cx - 11, y + 3, str(i + 1), "captionm", "text3", w=22, h=22, align="c")
        col = "text1" if state in ("cur", "run") else ("text3" if state == "lock" else "text2")
        cv.text(
            cx + 20, y + 4, lab, "calloutm" if state in ("cur", "run") else "callout", col, h=20
        )


def check_row(cv, x, y, w, state, label, value=None, planned=False):
    ic = {
        "ok": ("circle-check", "good"),
        "warn": ("triangle-alert", "warn"),
        "todo": ("circle-dashed", "text3"),
        "bad": ("circle-x", "crit"),
    }[state]
    cv.icon(ic[0], x, y + 6, 16, ic[1])
    adv = cv.text(x + 24, y, label, "callout", "text1" if state != "todo" else "text2", h=28)
    if planned:
        lk.chip(
            cv,
            x + 24 + adv + 8,
            y + 5,
            L("未实现", "Not implemented"),
            h=18,
            tone="planned",
            role="caption",
        )
    if value:
        cv.text(x, y, value, "monos", "text3", w=w, h=28, align="r")


def group(cv, x, y, w, rows, row_h=44):
    """Inset grouped list (one level of box). rows: list of (label, sub, draw_fn(xr, yc) or None, h)."""
    total = sum(r[3] if len(r) > 3 and r[3] else row_h for r in rows)
    cv.rect(x, y, w, total, fill="surface", stroke="sep", r=10)
    yy = y
    for i, r in enumerate(rows):
        lab, sub, fn = r[0], r[1], r[2]
        h = r[3] if len(r) > 3 and r[3] else row_h
        if i:
            cv.hline(x + 16, x + w, yy, "sep")
        if sub:
            cv.text(x + 16, yy + h / 2 - 19, lab, "body", "text1", h=20)
            cv.text(x + 16, yy + h / 2 + 1, sub, "caption", "text3", h=16, w=w * 0.55)
        elif lab:
            cv.text(x + 16, yy, lab, "body", "text1", h=h)
        if fn:
            fn(x + w - 16, yy, h)
        yy += h
    return total
