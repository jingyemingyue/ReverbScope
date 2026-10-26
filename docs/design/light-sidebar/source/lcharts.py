# ruff: noqa
# Design-phase mockup renderer (docs only, not product code).
"""Professional chart drawing for the light-sidebar baseline (QPainter, no pyqtgraph).

Log frequency axis with 1-2-5 major grid and integer minor grid; dB axes with 10 dB
major / 2 or 5 dB minor and a heavier 0 dB line; role-based line styles:
current = solid 2 px, baseline = dashed [5,3] 1.5 px, overlay = 1.25 px, raw = 1 px 35 %.
"""

from __future__ import annotations

import math

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QLinearGradient, QPainterPath, QPen

import lk
from lk import C, L

FREQ_MAJOR = (20, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000)


def fmt_hz(f):
    return f"{f / 1000:g}k" if f >= 1000 else f"{f:g}"


def mnum(v, d=1, sign=False):
    s = f"{v:+.{d}f}" if sign else f"{v:.{d}f}"
    return s.replace("-", "\u2212")


VIRIDIS = [
    "#440154",
    "#482878",
    "#3E4989",
    "#31688E",
    "#26828E",
    "#1F9E89",
    "#35B779",
    "#6DCD59",
    "#B4DE2C",
    "#FDE725",
]


# theme-adjusted time ramps (every stop >= 3:1 against plot.bg; see contrast.md)
RAMP_LIGHT = [
    "#440154",
    "#482878",
    "#3E4989",
    "#31688E",
    "#26828E",
    "#1E8778",
    "#2A8A55",
    "#3D7F2E",
]
RAMP_DARK = [
    "#8A7FE0",
    "#5A68BA",
    "#3A7FB0",
    "#26828E",
    "#1F9E89",
    "#35B779",
    "#6DCD59",
    "#B4DE2C",
    "#FDE725",
]


def theme_ramp():
    return RAMP_LIGHT if lk.MODE["theme"] == "light" else RAMP_DARK


def ramp(t, stops=None):
    stops = stops or theme_ramp()
    t = min(max(t, 0), 1) * (len(stops) - 1)
    i = min(int(t), len(stops) - 2)
    a, b = QColor(stops[i]), QColor(stops[i + 1])
    f = t - i
    return QColor(
        int(a.red() + (b.red() - a.red()) * f),
        int(a.green() + (b.green() - a.green()) * f),
        int(a.blue() + (b.blue() - a.blue()) * f),
    )


class Plot:
    def __init__(
        self,
        cv,
        x,
        y,
        w,
        h,
        xkind="log",
        xr=(20, 20000),
        yr=(-30, 30),
        ylabel="",
        xlabel="",
        left=46,
        bottom=34,
        ystep=10,
        yminor=5,
        xticks=None,
        show_xlabels=True,
        yfmt=None,
        right=10,
    ):
        self.cv = cv
        self.ox, self.oy, self.ow, self.oh = x, y, w, h
        self.px, self.py = x + left, y + 6
        self.pw = w - left - right
        self.ph = h - 6 - (bottom if show_xlabels else 6)
        self.xkind, self.xr, self.yr = xkind, xr, yr
        self.ylabel, self.xlabel = ylabel, xlabel
        self.ystep, self.yminor = ystep, yminor
        self.xticks = xticks
        self.show_xlabels = show_xlabels
        self.yfmt = yfmt or (lambda v: mnum(v, 0))

    # mapping
    def X(self, v):
        if self.xkind == "log":
            a, b = math.log10(self.xr[0]), math.log10(self.xr[1])
            return self.px + (math.log10(max(v, 1e-9)) - a) / (b - a) * self.pw
        return self.px + (v - self.xr[0]) / (self.xr[1] - self.xr[0]) * self.pw

    def Y(self, v):
        return self.py + (self.yr[1] - v) / (self.yr[1] - self.yr[0]) * self.ph

    def clip_on(self):
        self.cv.p.save()
        self.cv.p.setClipRect(QRectF(self.px, self.py, self.pw, self.ph))

    def clip_off(self):
        self.cv.p.restore()

    def frame(self):
        cv = self.cv
        cv.rect(self.px, self.py, self.pw, self.ph, fill="plot.bg")
        # minor grid
        if self.xkind == "log":
            d = 10
            while d <= self.xr[1]:
                for k in range(1, 10):
                    f = d * k
                    if self.xr[0] < f < self.xr[1] and f not in FREQ_MAJOR:
                        cv.vline(self.X(f), self.py, self.py + self.ph, "grid.minor")
                d *= 10
            majors = [f for f in FREQ_MAJOR if self.xr[0] <= f <= self.xr[1]]
        else:
            majors = self.xticks or []
        if self.yminor:
            v = math.ceil(self.yr[0] / self.yminor) * self.yminor
            while v <= self.yr[1]:
                if v % self.ystep:
                    cv.hline(self.px, self.px + self.pw, self.Y(v), "grid.minor")
                v += self.yminor
        for f in majors:
            cv.vline(self.X(f), self.py, self.py + self.ph, "grid.major")
        v = math.ceil(self.yr[0] / self.ystep) * self.ystep
        while v <= self.yr[1] + 1e-9:
            cv.hline(
                self.px,
                self.px + self.pw,
                self.Y(v),
                "zero" if abs(v) < 1e-9 and self.yr[0] < 0 < self.yr[1] else "grid.major",
            )
            cv.text(
                self.ox,
                self.Y(v) - 8,
                self.yfmt(v),
                "monos",
                "plot.text",
                w=self.px - self.ox - 6,
                h=16,
                align="r",
            )
            v += self.ystep
        # x labels
        if self.show_xlabels:
            for f in majors:
                lab = (
                    fmt_hz(f)
                    if self.xkind == "log"
                    else (self.xtfmt(f) if hasattr(self, "xtfmt") else f"{f:g}")
                )
                cv.text(
                    self.X(f) - 24,
                    self.py + self.ph + 4,
                    lab,
                    "monos",
                    "plot.text",
                    w=48,
                    h=14,
                    align="c",
                )
            if self.xlabel:
                cv.text(
                    self.px,
                    self.py + self.ph + 18,
                    self.xlabel,
                    "caption",
                    "text3",
                    w=self.pw,
                    h=14,
                    align="c",
                )
        # frame hairline
        cv.rect(self.px, self.py, self.pw, self.ph, stroke="grid.major")
        cv.line(self.px, self.py + self.ph, self.px + self.pw, self.py + self.ph, "axis", 1)
        cv.line(self.px, self.py, self.px, self.py + self.ph, "axis", 1)
        if self.ylabel:
            p = cv.p
            p.save()
            p.translate(self.ox + 4, self.py + self.ph / 2)
            p.rotate(-90)
            cv.text(-self.ph / 2, -2, self.ylabel, "caption", "text3", w=self.ph, h=14, align="c")
            p.restore()

    def curve(self, xs, ys, color="cur", sw=2.0, dash=None, alpha=None):
        pts = [
            (self.X(a), self.Y(b))
            for a, b in zip(xs, ys)
            if np.isfinite(b) and self.xr[0] <= a <= self.xr[1]
        ]
        self.clip_on()
        self.cv.path(pts, color, sw=sw, dash=dash, alpha=alpha)
        self.clip_off()

    def hatch(self, x0, x1, label=None):
        cv = self.cv
        a, b = self.X(max(x0, self.xr[0])), self.X(min(x1, self.xr[1]))
        if b - a < 1:
            return
        p = cv.p
        p.save()
        p.setClipRect(QRectF(a, self.py, b - a, self.ph))
        p.fillRect(QRectF(a, self.py, b - a, self.ph), C("excluded", 0.35))
        pen = QPen(C("excluded"), 1)
        p.setPen(pen)
        s = -self.ph
        while s < (b - a) + self.ph:
            p.drawLine(QPointF(a + s, self.py + self.ph), QPointF(a + s + self.ph, self.py))
            s += 7
        p.restore()
        if label:
            cv.text(
                a + 4,
                self.py + 4,
                label,
                "caption",
                "text3",
                w=max(b - a - 6, lk.tw(label, "caption") + 2),
                h=14,
            )

    def yband(self, y0, y1, color="accent", alpha=0.08, label=None):
        cv = self.cv
        a, b = self.Y(y1), self.Y(y0)
        cv.rect(self.px, a, self.pw, b - a, fill=C(color, alpha))
        cv.line(self.px, a, self.px + self.pw, a, C(color, 0.45), 1, dash=[2, 3])
        cv.line(self.px, b, self.px + self.pw, b, C(color, 0.45), 1, dash=[2, 3])
        if label:
            cv.text(
                self.px + self.pw - lk.tw(label, "caption") - 8,
                a + 2,
                label,
                "caption",
                "accent.text",
            )

    def cursor(self, xv, dots=(), flag=None):
        cv = self.cv
        x = self.X(xv)
        cv.line(x, self.py, x, self.py + self.ph, "cursor", 1, dash=[1, 2])
        for i, (yv, color, solid) in enumerate(dots):
            y = self.Y(yv)
            if solid:
                cv.circle(x, y, 3.5, fill=color, stroke="plot.bg", sw=1.5)
            else:
                cv.circle(x, y, 3.2, fill="plot.bg", stroke=color, sw=1.5)
        if flag:
            w = lk.tw(flag, "monos") + 10
            cv.rect(x - w / 2, self.py + self.ph - 18, w, 16, fill="cursor", r=3)
            cv.text(
                x - w / 2, self.py + self.ph - 18, flag, "monos", "cursor.on", w=w, h=16, align="c"
            )


def legend(cv, x, y, items, role="callout"):
    """items: (label, role_label, color, dash). Draws swatch + label + muted role. Returns width."""
    cx = x
    for lab, rl, color, dash in items:
        cv.line(cx, y + 8, cx + 18, y + 8, color, 2.0 if not dash else 1.5, dash=dash)
        cx += 24
        cx += cv.text(cx, y, lab, "calloutm", "text1", h=16) + 4
        if rl:
            cx += cv.text(cx, y, rl, role, "text3", h=16)
        cx += 16
    return cx - x


def colorbar(cv, x, y, w, lo, hi, unit, stops=None):
    stops = stops or theme_ramp()
    g = QLinearGradient(x, 0, x + w, 0)
    for i, s in enumerate(stops):
        g.setColorAt(i / (len(stops) - 1), QColor(s))
    cv.p.fillRect(QRectF(x, y, w, 6), QBrush(g))
    cv.rect(x, y, w, 6, stroke="grid.major")
    cv.text(x - 60, y - 5, lo, "monos", "plot.text", w=56, h=16, align="r")
    cv.text(x + w + 6, y - 5, f"{hi} {unit}", "monos", "plot.text")
