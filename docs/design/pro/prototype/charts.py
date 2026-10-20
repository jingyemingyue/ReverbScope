# ruff: noqa: N802
# Design-phase mockup renderer (docs only, not product code).
"""Chart style for the pro mockups, on pyqtgraph 0.14 like main's ui/plotkit.py.

Frequency axes are drawn in log10(Hz) coordinates (as ChartPanel does) with a
two-level grid: major lines at 1-2-5 per decade, minor lines at the other
integers. dB axes: major every 10 dB, minor every 2 or 5 dB, a heavier 0 dB
line. Every colour comes from a pk token.
"""

from __future__ import annotations

import math

import numpy as np
import pk
import pyqtgraph as pg
from pk import C
from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QPen
from PySide6.QtWidgets import QFrame, QVBoxLayout, QWidget

pg.setConfigOptions(antialias=True, useOpenGL=False, background=None)

FREQ_MAJOR = (20, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000)


def fmt_hz(f: float) -> str:
    if f >= 1000:
        v = f / 1000
        return f"{v:g}k"
    return f"{f:g}"


class Chart(QWidget):
    def __init__(
        self,
        xkind: str = "freq",
        xlabel: str = "",
        ylabel: str = "",
        left_w: int = 46,
        bottom_h: int | None = None,
        show_x_label: bool = True,
    ) -> None:
        super().__init__()
        self.xkind = xkind
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.pw = pg.PlotWidget(background=C("plot_bg"))
        self.pw.setFrameShape(QFrame.Shape.NoFrame)
        self.pw.setStyleSheet("border:none;")
        lay.addWidget(self.pw)
        pi = self.pi = self.pw.getPlotItem()
        pi.hideButtons()
        pi.setMenuEnabled(False)
        pi.layout.setContentsMargins(2, 8, 12, 2)
        for name in ("left", "bottom"):
            ax = pi.getAxis(name)
            ax.setPen(pg.mkPen(C("plot_axis"), width=1))
            ax.setTextPen(pg.mkPen(C("plot_text")))
            ax.setTickFont(pk.font("tick"))
            ax.setStyle(tickLength=-4, tickTextOffset=4, autoExpandTextSpace=False)
        pi.getAxis("left").setWidth(left_w)
        pi.getAxis("bottom").setHeight(bottom_h or (34 if show_x_label else 20))
        ls = {"color": C("plot_text"), "font-size": "11px"}
        if xlabel and show_x_label:
            pi.setLabel("bottom", xlabel, **ls)
            pi.getAxis("bottom").label.setFont(pk.font("caption"))
        if ylabel:
            pi.setLabel("left", ylabel, **ls)
            pi.getAxis("left").label.setFont(pk.font("caption"))
        pi.showAxis("top")
        pi.showAxis("right")
        for name in ("top", "right"):
            ax = pi.getAxis(name)
            ax.setPen(pg.mkPen(C("plot_axis"), width=1))
            ax.setStyle(showValues=False, tickLength=0)
            ax.setHeight(1) if name == "top" else ax.setWidth(1)
        self.vb = pi.getViewBox()
        self.vb.setMouseEnabled(False, False)
        self.vb.disableAutoRange()
        self.flags: list = []

    # -------------------------------------------------- coordinates
    def X(self, x):
        if self.xkind == "freq":
            return np.log10(np.asarray(x, float)) if np.ndim(x) else math.log10(x)
        return x

    def _vlines(self, values, token, width=1.0, z=-20):
        for v in values:
            ln = pg.InfiniteLine(pos=v, angle=90, pen=pg.mkPen(C(token), width=width))
            ln.setZValue(z)
            self.pi.addItem(ln, ignoreBounds=True)

    def _hlines(self, values, token, width=1.0, z=-20):
        for v in values:
            ln = pg.InfiniteLine(pos=v, angle=0, pen=pg.mkPen(C(token), width=width))
            ln.setZValue(z)
            self.pi.addItem(ln, ignoreBounds=True)

    def x_freq(self, lo: float = 20, hi: float = 20000, sparse: bool = False) -> None:
        self.pi.setXRange(math.log10(lo), math.log10(hi), padding=0)
        major, minor = [], []
        for dec in range(6):
            for k in range(1, 10):
                f = k * 10**dec
                if lo <= f <= hi:
                    (major if f in FREQ_MAJOR else minor).append(f)
        labels = [f for f in major if not sparse or f in (20, 100, 1000, 10000, 20000)]
        self.pi.getAxis("bottom").setTicks(
            [[(math.log10(f), fmt_hz(f)) for f in labels], [(math.log10(f), "") for f in minor]]
        )
        self._vlines([math.log10(f) for f in minor], "plot_grid_minor", z=-30)
        self._vlines([math.log10(f) for f in major], "plot_grid_major", z=-25)

    def x_lin(
        self,
        lo: float,
        hi: float,
        major: float,
        minor: float,
        fmt=lambda v: f"{v:g}",
        label_every: int = 1,
    ) -> None:
        self.pi.setXRange(lo, hi, padding=0)
        maj = list(np.arange(math.ceil(lo / major) * major, hi + 1e-9, major))
        mnr = [
            v
            for v in np.arange(math.ceil(lo / minor) * minor, hi + 1e-9, minor)
            if min(abs(v - m) for m in maj) > 1e-9
        ]
        self.pi.getAxis("bottom").setTicks(
            [
                [(v, fmt(v)) for i, v in enumerate(maj) if i % label_every == 0],
                [(v, "") for v in mnr],
            ]
        )
        self._vlines(mnr, "plot_grid_minor", z=-30)
        self._vlines(maj, "plot_grid_major", z=-25)

    def y_lin(
        self, lo: float, hi: float, major: float, minor: float, fmt=None, zero: bool = True
    ) -> None:
        fmt = fmt or (lambda v: f"{v:g}".replace("-", "\u2212"))
        self.pi.setYRange(lo, hi, padding=0)
        maj = list(np.arange(math.ceil(lo / major) * major, hi + 1e-9, major))
        mnr = [
            v
            for v in np.arange(math.ceil(lo / minor) * minor, hi + 1e-9, minor)
            if min(abs(v - m) for m in maj) > 1e-9
        ]
        self.pi.getAxis("left").setTicks([[(v, fmt(v)) for v in maj], [(v, "") for v in mnr]])
        self._hlines(mnr, "plot_grid_minor", z=-30)
        self._hlines(maj, "plot_grid_major", z=-25)
        if zero and lo < 0 < hi:
            self._hlines([0.0], "plot_zero", width=1.2, z=-22)

    # -------------------------------------------------- items
    def curve(
        self,
        x,
        y,
        color: str,
        width: float = 1.6,
        dash: bool | list = False,
        alpha: float = 1.0,
        z: int = 0,
        fill_to: float | None = None,
        fill_token: str = "plot_bg",
    ):
        col = QColor(C(color) if color in pk.S.T else color)
        col.setAlphaF(alpha)
        pen = QPen(col, width)
        pen.setCosmetic(True)
        if dash:
            pen.setStyle(Qt.PenStyle.CustomDashLine)
            pen.setDashPattern(dash if isinstance(dash, list) else [5, 3])
        kw = {}
        if fill_to is not None:
            kw = {"fillLevel": fill_to, "brush": pg.mkBrush(C(fill_token))}
        item = pg.PlotDataItem(self.X(x), y, pen=pen, connect="finite", **kw)
        item.setZValue(z)
        self.pi.addItem(item)
        return item

    def shade(
        self,
        x0: float,
        x1: float,
        token: str = "plot_excluded",
        hatch: bool = True,
        alpha: int = 255,
    ) -> None:
        col = QColor(C(token))
        col.setAlpha(alpha)
        br = QBrush(col, Qt.BrushStyle.BDiagPattern if hatch else Qt.BrushStyle.SolidPattern)
        reg = pg.LinearRegionItem(
            values=(self.X(x0), self.X(x1)), movable=False, brush=br, pen=pg.mkPen(None)
        )
        reg.setZValue(-40)
        self.pi.addItem(reg, ignoreBounds=True)

    def band(self, x0: float, x1: float, token: str = "accent", alpha: int = 22) -> None:
        self.shade(x0, x1, token, hatch=False, alpha=alpha)

    def hline(self, y: float, token: str, dash: bool = True, width: float = 1.0) -> None:
        pen = pg.mkPen(
            C(token), width=width, style=Qt.PenStyle.DashLine if dash else Qt.PenStyle.SolidLine
        )
        ln = pg.InfiniteLine(pos=y, angle=0, pen=pen)
        ln.setZValue(-5)
        self.pi.addItem(ln, ignoreBounds=True)

    def text(
        self,
        s: str,
        x: float,
        y: float,
        color: str = "plot_text",
        anchor=(0, 1),
        role: str = "tick",
        fill: str | None = None,
        border: str | None = None,
    ) -> None:
        t = pg.TextItem(
            s,
            color=C(color) if color in pk.S.T else color,
            anchor=anchor,
            fill=pg.mkBrush(C(fill)) if fill else None,
            border=pg.mkPen(C(border)) if border else None,
        )
        t.setFont(pk.font(role))
        t.setPos(self.X(x) if self.xkind == "freq" else x, y)
        t.setZValue(60)
        self.pi.addItem(t, ignoreBounds=True)

    def marker(
        self,
        x: float,
        y: float,
        color: str,
        size: int = 7,
        hollow: bool = False,
        symbol: str = "o",
        z: int = 50,
    ) -> None:
        col = C(color) if color in pk.S.T else color
        sp = pg.ScatterPlotItem(
            [self.X(x) if self.xkind == "freq" else x],
            [y],
            size=size,
            symbol=symbol,
            pen=pg.mkPen(col, width=1.5),
            brush=pg.mkBrush(C("plot_bg") if hollow else col),
        )
        sp.setZValue(z)
        self.pi.addItem(sp)

    def cursor(
        self,
        x: float,
        name: str,
        y: float | None = None,
        dashed: bool = False,
        ytop: float | None = None,
    ) -> None:
        """Placed measurement cursor: a vertical line, a flag with its name, a dot on the curve."""
        xx = self.X(x) if self.xkind == "freq" else x
        pen = pg.mkPen(
            C("cursor"), width=1.2, style=Qt.PenStyle.DashLine if dashed else Qt.PenStyle.SolidLine
        )
        ln = pg.InfiniteLine(pos=xx, angle=90, pen=pen)
        ln.setZValue(70)
        self.pi.addItem(ln, ignoreBounds=True)
        top = ytop if ytop is not None else self.vb.viewRange()[1][1]
        t = pg.TextItem(
            f" {name} ", color=C("cursor_flag_text"), anchor=(0, 0), fill=pg.mkBrush(C("cursor"))
        )
        t.setFont(pk.font("num_strong", size=11))
        t.setPos(xx, top)
        t.setZValue(80)
        self.pi.addItem(t, ignoreBounds=True)
        if y is not None:
            self.marker(x, y, "cursor", size=7, hollow=True, z=85)

    def crosshair(self, x: float, y: float | None = None) -> None:
        """Hover crosshair (implemented in plotkit: show_cursor)."""
        xx = self.X(x) if self.xkind == "freq" else x
        col = QColor(C("muted"))
        col.setAlpha(160)
        pen = QPen(col, 1)
        pen.setStyle(Qt.PenStyle.DotLine)
        pen.setCosmetic(True)
        ln = pg.InfiniteLine(pos=xx, angle=90, pen=pen)
        ln.setZValue(65)
        self.pi.addItem(ln, ignoreBounds=True)
        if y is not None:
            ln2 = pg.InfiniteLine(pos=y, angle=0, pen=pen)
            ln2.setZValue(65)
            self.pi.addItem(ln2, ignoreBounds=True)


def overlay(
    chart: QWidget, widget: QWidget, corner: str = "tr", dx: int = 14, dy: int = 12
) -> None:
    """Pin a child widget (cursor readout, empty state, callout) to a chart corner."""
    widget.setParent(chart)
    widget.adjustSize()
    old = chart.resizeEvent

    def place(ev=None):
        if ev is not None:
            old(ev)
        w, h = widget.sizeHint().width(), widget.sizeHint().height()
        widget.resize(w, h)
        x = chart.width() - w - dx if "r" in corner else dx
        y = dy if "t" in corner else chart.height() - h - dy
        if corner == "c":
            x, y = (chart.width() - w) // 2, (chart.height() - h) // 2
        widget.move(x, y)
        widget.raise_()

    chart.resizeEvent = place  # type: ignore[assignment]
    place()
