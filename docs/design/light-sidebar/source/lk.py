# ruff: noqa
# Design-phase mockup renderer (docs only, not product code).
"""Light-sidebar baseline kit: tokens, fonts, icons and QPainter helpers.

Everything is drawn with QPainter on a QImage (2x). No product code is imported;
chart data comes from `reverbscope demo` outputs pre-baked into demo.npz.
"""

from __future__ import annotations

import math
import re
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt, QByteArray
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontDatabase,
    QFontMetricsF,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtSvg import QSvgRenderer

HERE = Path(__file__).resolve().parent
import os

# Fonts are not committed (OFL files are large); point RS_FONT_DIR at IBM Plex Sans/Mono,
# Source Han Sans CN, Source Serif 4 and LXGW WenKai. Icons: ../icons (Lucide subset, ISC).
FONT_DIR = Path(os.environ.get("RS_FONT_DIR", "/workspace/work/reverbscope-design/fonts/use"))
ICON_DIR = Path(os.environ.get("RS_ICON_DIR", str(HERE.parent / "icons")))

# ---------------------------------------------------------------- tokens
LIGHT = {
    "window": "#FBFAF8",
    "sidebar.top": "#F3F1EC",
    "sidebar.bot": "#ECE9E3",
    "sidebar": "#F0EEE9",
    "toolbar": "#FBFAF8",
    "surface": "#FFFFFF",
    "sunken": "#F3F1ED",
    "hover": "#E8E5DF",
    "pressed": "#DEDAD3",
    "sel.sidebar": "#DDEAEA",
    "sep": "#E5E2DB",
    "border": "#D6D2CA",
    "control": "#8A857B",
    "text1": "#1D1B18",
    "text2": "#57534C",
    "text3": "#68645D",
    "disabled": "#A9A49B",
    "accent": "#177E89",
    "accent.hover": "#12656E",
    "accent.soft": "#E3F1F2",
    "accent.text": "#136C76",
    "on.accent": "#FFFFFF",
    "focus": "#177E89",
    "good": "#2D7B31",
    "good.soft": "#E8F4E9",
    "warn": "#9A5B00",
    "warn.soft": "#FDF1DE",
    "warn.border": "#E9C48A",
    "crit": "#C62828",
    "crit.soft": "#FBE9E9",
    "on.crit": "#FFFFFF",
    "info": "#1F5FA8",
    "info.soft": "#E6EEF9",
    "planned": "#5A4AC2",
    "planned.soft": "#EEEBFB",
    "plot.bg": "#FFFFFF",
    "grid.major": "#E3E0DA",
    "grid.minor": "#F2F0EC",
    "axis": "#8A857B",
    "plot.text": "#57534C",
    "zero": "#B5B0A6",
    "excluded": "#E3E0DA",
    "cur": "#177E89",
    "base": "#4F4B45",
    "delta": "#6B5BD2",
    "cursor": "#1D1B18",
    "cursor.on": "#FFFFFF",
    "d2": "#D9731F",
    "d3": "#6B5BD2",
    "d4": "#2F9E57",
    "d5": "#C2417E",
    "d7": "#3B82C4",
    "readout": "#F6F4F0",
    "scrim": "#1D1B18",
    "shadow": "#000000",
    "tl.red": "#FF5F57",
    "tl.yel": "#FEBC2E",
    "tl.grn": "#28C840",
}
DARK = {
    "window": "#1E1D1B",
    "sidebar.top": "#2B2A27",
    "sidebar.bot": "#262522",
    "sidebar": "#282724",
    "toolbar": "#1E1D1B",
    "surface": "#2C2B28",
    "sunken": "#181715",
    "hover": "#34322F",
    "pressed": "#3D3B37",
    "sel.sidebar": "#21393B",
    "sep": "#3A3834",
    "border": "#4A4741",
    "control": "#7D786F",
    "text1": "#ECEAE4",
    "text2": "#B5B0A6",
    "text3": "#9C978E",
    "disabled": "#6A665F",
    "accent": "#4FB6C3",
    "accent.hover": "#6CC6D1",
    "accent.soft": "#183A3F",
    "accent.text": "#5CC0CC",
    "on.accent": "#0B1114",
    "focus": "#4FB6C3",
    "good": "#6CC070",
    "good.soft": "#1B2E1E",
    "warn": "#F0B35A",
    "warn.soft": "#352915",
    "warn.border": "#6A4E22",
    "crit": "#EF6A6A",
    "crit.soft": "#3A1D1D",
    "on.crit": "#1A0B0B",
    "info": "#7FB2EE",
    "info.soft": "#1A2A3D",
    "planned": "#9C8FEA",
    "planned.soft": "#27233F",
    "plot.bg": "#181715",
    "grid.major": "#34322F",
    "grid.minor": "#242320",
    "axis": "#7D786F",
    "plot.text": "#B5B0A6",
    "zero": "#5E5A54",
    "excluded": "#2E2C29",
    "cur": "#4FB6C3",
    "base": "#C9C4BA",
    "delta": "#9C8FEA",
    "cursor": "#ECEAE4",
    "cursor.on": "#181715",
    "d2": "#F29A52",
    "d3": "#9C8FEA",
    "d4": "#5BC07F",
    "d5": "#E07AAA",
    "d7": "#79AEE3",
    "readout": "#232220",
    "scrim": "#000000",
    "shadow": "#000000",
    "tl.red": "#FF5F57",
    "tl.yel": "#FEBC2E",
    "tl.grn": "#28C840",
}
T = dict(LIGHT)
MODE = {"lang": "zh", "theme": "light", "W": 1280, "H": 800}
OVERFLOWS: list[str] = []
SIDEBAR_W = 260
FOOT = 26
TOOLBAR_H = 52


def set_mode(lang: str, theme: str, W: int = 1280, H: int = 800) -> None:
    MODE.update(lang=lang, theme=theme, W=W, H=H)
    T.clear()
    T.update(LIGHT if theme == "light" else DARK)


def C(name: str, alpha: float | None = None) -> QColor:
    c = QColor(T[name] if name in T else name)
    if alpha is not None:
        c.setAlphaF(alpha)
    return c


def zh() -> bool:
    return MODE["lang"] == "zh"


def L(zh_s: str, en_s: str) -> str:
    return zh_s if zh() else en_s


_TR: dict = {}


def tr(msgid: str) -> str:
    """The product's own translation of ``msgid`` (src/reverbscope/locale, main ab3da19).

    Needs ``PYTHONPATH=<repo>/src``. Used for view, control and section names so the
    mockups carry the exact words the GUI on main already ships."""
    lang = "zh_CN" if zh() else "en"
    if lang not in _TR:
        from reverbscope.i18n import translator

        _TR[lang] = translator(lang)
    return _TR[lang](msgid)


# ---------------------------------------------------------------- fonts
_FAM: dict[str, str] = {}


def load_fonts() -> None:
    for f in [
        "IBMPlexSans-Regular.ttf",
        "IBMPlexSans-Medium.ttf",
        "IBMPlexSans-SemiBold.ttf",
        "IBMPlexMono-Regular.ttf",
        "IBMPlexMono-Medium.ttf",
        "IBMPlexMono-SemiBold.ttf",
        "SourceHanSansCN-Regular.otf",
        "SourceHanSansCN-Medium.otf",
        "SourceHanSansCN-Bold.otf",
        "SourceSerif4-Semibold.otf",
        "LXGWWenKai-Medium.ttf",
    ]:
        fid = QFontDatabase.addApplicationFont(str(FONT_DIR / f))
        if fid < 0:
            raise RuntimeError(f)
        _FAM[f] = QFontDatabase.applicationFontFamilies(fid)[0]


# role: (px, weight, family-kind, letter-spacing%)
ROLES = {
    "display": (30, 600, "serif"),
    "largetitle": (26, 600, "sans"),
    "title1": (20, 600, "sans"),
    "title2": (17, 600, "sans"),
    "title3": (15, 600, "sans"),
    "headline": (13, 600, "sans"),
    "body": (13, 400, "sans"),
    "bodym": (13, 500, "sans"),
    "callout": (12, 400, "sans"),
    "calloutm": (12, 500, "sans"),
    "caption": (11, 400, "sans"),
    "captionm": (11, 600, "sans"),
    "mono": (12, 400, "mono"),
    "monom": (12, 500, "mono"),
    "monos": (11, 400, "mono"),
    "num": (24, 500, "sans"),
    "numl": (34, 500, "sans"),
    "kbd": (10.5, 500, "sans"),
}


def font(role: str) -> QFont:
    px, w, kind = ROLES[role]
    f = QFont()
    if kind == "serif":
        f.setFamilies(["Source Serif 4", "LXGW WenKai"])
    elif kind == "mono":
        f.setFamilies(["IBM Plex Mono", "Source Han Sans CN"])
    else:
        f.setFamilies(["IBM Plex Sans", "Source Han Sans CN"])
    f.setPixelSize(int(round(px))) if px == int(px) else f.setPointSizeF(px * 0.75)
    f.setWeight(QFont.Weight(w))
    f.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    if kind == "sans" and px >= 20:
        f.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 99)
    return f


def tw(s: str, role: str) -> float:
    return QFontMetricsF(font(role)).horizontalAdvance(s)


# ---------------------------------------------------------------- icons
_SVG: dict[str, str] = {}


def _svg(name: str) -> str:
    if name not in _SVG:
        _SVG[name] = (ICON_DIR / f"{name}.svg").read_text()
    return _SVG[name]


USED_ICONS: dict[str, set] = {}


class Canvas:
    def __init__(
        self,
        W: int | None = None,
        H: int | None = None,
        scale: float = 2.0,
        name: str = "",
        footer: bool = True,
    ):
        self.W, self.H = W or MODE["W"], H or MODE["H"]
        self.name = name
        self.foot = FOOT if footer else 0
        self.img = QImage(
            int(self.W * scale),
            int((self.H + self.foot) * scale),
            QImage.Format.Format_ARGB32_Premultiplied,
        )
        self.img.fill(C("window"))
        p = self.p = QPainter(self.img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.scale(scale, scale)

    # -- primitives
    def rect(self, x, y, w, h, fill=None, stroke=None, r=0, sw=1.0, dash=None):
        p = self.p
        p.save()
        p.setBrush(
            QBrush(C(fill) if isinstance(fill, str) else fill)
            if fill is not None
            else Qt.BrushStyle.NoBrush
        )
        if stroke is not None:
            pen = QPen(C(stroke) if isinstance(stroke, str) else stroke, sw)
            if dash:
                pen.setDashPattern(dash)
            p.setPen(pen)
            o = sw / 2
            rr = QRectF(x + o, y + o, w - sw, h - sw)
        else:
            p.setPen(Qt.PenStyle.NoPen)
            rr = QRectF(x, y, w, h)
        if r:
            p.drawRoundedRect(rr, r, r)
        else:
            p.drawRect(rr)
        p.restore()

    def circle(self, cx, cy, rad, fill=None, stroke=None, sw=1.0):
        p = self.p
        p.save()
        p.setBrush(
            C(fill)
            if isinstance(fill, str)
            else (fill if fill is not None else Qt.BrushStyle.NoBrush)
        )
        p.setPen(
            QPen(C(stroke) if isinstance(stroke, str) else stroke, sw)
            if stroke is not None
            else Qt.PenStyle.NoPen
        )
        p.drawEllipse(QPointF(cx, cy), rad, rad)
        p.restore()

    def line(self, x1, y1, x2, y2, color="sep", sw=1.0, dash=None, cap=Qt.PenCapStyle.FlatCap):
        p = self.p
        p.save()
        pen = QPen(C(color) if isinstance(color, str) else color, sw)
        pen.setCapStyle(cap)
        if dash:
            pen.setDashPattern(dash)
        p.setPen(pen)
        p.drawLine(QPointF(x1, y1), QPointF(x2, y2))
        p.restore()

    def hline(self, x1, x2, y, color="sep"):
        self.rect(x1, y, x2 - x1, 1, fill=color)

    def vline(self, x, y1, y2, color="sep"):
        self.rect(x, y1, 1, y2 - y1, fill=color)

    def path(self, pts, color, sw=1.5, dash=None, alpha=None, fill=None):
        if len(pts) < 2:
            return
        p = self.p
        p.save()
        pp = QPainterPath(QPointF(*pts[0]))
        for q in pts[1:]:
            pp.lineTo(QPointF(*q))
        col = C(color, alpha) if isinstance(color, str) else color
        pen = QPen(col, sw)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap if not dash else Qt.PenCapStyle.FlatCap)
        if dash:
            pen.setDashPattern(dash)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(pp)
        p.restore()

    def shadow(self, x, y, w, h, r=12, depth=18, alpha=0.10, dy=8):
        p = self.p
        p.save()
        p.setPen(Qt.PenStyle.NoPen)
        a = alpha / depth * 2.2
        for i in range(depth, 0, -1):
            c = C("shadow")
            c.setAlphaF(min(1.0, a * (1 - i / depth) ** 1.6 * 1.6))
            p.setBrush(c)
            p.drawRoundedRect(QRectF(x - i, y - i + dy, w + 2 * i, h + 2 * i), r + i, r + i)
        p.restore()

    def gradient_v(self, x, y, w, h, top, bot):
        g = QLinearGradient(x, y, x, y + h)
        g.setColorAt(0, C(top))
        g.setColorAt(1, C(bot))
        self.p.fillRect(QRectF(x, y, w, h), QBrush(g))

    # -- text
    def text(
        self,
        x,
        y,
        s,
        role="body",
        color="text1",
        w=None,
        h=None,
        align="l",
        valign="c",
        wrap=False,
        check=True,
    ):
        """Single line (y = box top, h default = line box). Returns advance width."""
        f = font(role)
        fm = QFontMetricsF(f)
        adv = fm.horizontalAdvance(s)
        lh = h if h is not None else math.ceil(fm.height())
        if w is None:
            w = adv + 1
        if check and not wrap and adv > w + 0.6:
            OVERFLOWS.append(f"{self.name}: '{s}' {adv:.0f}>{w:.0f} ({role})")
        fl = {
            "l": Qt.AlignmentFlag.AlignLeft,
            "c": Qt.AlignmentFlag.AlignHCenter,
            "r": Qt.AlignmentFlag.AlignRight,
        }[align]
        fl |= {
            "c": Qt.AlignmentFlag.AlignVCenter,
            "t": Qt.AlignmentFlag.AlignTop,
            "b": Qt.AlignmentFlag.AlignBottom,
        }[valign]
        if wrap:
            fl |= Qt.TextFlag.TextWordWrap
            br = fm.boundingRect(QRectF(0, 0, w, 10000), int(fl), s)
            if check and h is not None and br.height() > h + 0.6:
                OVERFLOWS.append(f"{self.name}: wrap '{s[:30]}' {br.height():.0f}>{h:.0f}")
        p = self.p
        p.save()
        p.setFont(f)
        p.setPen(C(color) if isinstance(color, str) else color)
        p.drawText(QRectF(x, y, w, lh), int(fl), s)
        p.restore()
        return adv

    def wrap_h(self, s, role, w):
        fm = QFontMetricsF(font(role))
        return fm.boundingRect(QRectF(0, 0, w, 10000), int(Qt.TextFlag.TextWordWrap), s).height()

    # -- icons
    def icon(self, name, x, y, size=16, color="text2", stroke=1.5):
        USED_ICONS.setdefault(name, set()).add(size)
        svg = _svg(name)
        swv = stroke * 24.0 / size
        col = C(color) if isinstance(color, str) else color
        svg = re.sub(r'stroke-width="[0-9.]+"', f'stroke-width="{swv:.3f}"', svg)
        svg = svg.replace("currentColor", col.name())
        r = QSvgRenderer(QByteArray(svg.encode()))
        self.p.save()
        if col.alphaF() < 1:
            self.p.setOpacity(col.alphaF())
        r.render(self.p, QRectF(x, y, size, size))
        self.p.restore()

    def save(self, path):
        self.p.end()
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.img.save(str(path))


# ---------------------------------------------------------------- components
def kbd(cv: Canvas, x, y, label, h=18, dim=False):
    """Keycap. Returns width."""
    w = max(h, tw(label, "kbd") + 10)
    cv.rect(x, y, w, h, fill="surface", stroke="border", r=4)
    cv.rect(x + 1, y + h - 2, w - 2, 1, fill="sep")
    cv.text(x, y, label, "kbd", "text3" if not dim else "disabled", w=w, h=h - 1, align="c")
    return w


def button(
    cv,
    x,
    y,
    label,
    kind="secondary",
    w=None,
    h=28,
    icon=None,
    shortcut=None,
    disabled=False,
    role="bodym",
):
    pad = 12
    iw = 16 + 6 if icon else 0
    sw_ = (tw(shortcut, "callout") + 8) if shortcut else 0
    tw_ = tw(label, role)
    if w is None:
        w = pad * 2 + iw + tw_ + sw_
    if kind == "primary":
        fill, fg, stroke = (
            ("accent", "on.accent", None) if not disabled else ("sunken", "disabled", "sep")
        )
    elif kind == "danger":
        fill, fg, stroke = "crit", "on.crit", None
    elif kind == "plain":
        fill, fg, stroke = None, ("accent.text" if not disabled else "disabled"), None
    else:
        fill, fg, stroke = (
            ("surface", "text1", "border") if not disabled else ("sunken", "disabled", "sep")
        )
    if kind in ("primary", "secondary") and not disabled:
        cv.rect(
            x,
            y + 1,
            w,
            h,
            fill=C("shadow", 0.05 if T is LIGHT or MODE["theme"] == "light" else 0.25),
            r=7,
        )
    cv.rect(x, y, w, h, fill=fill, stroke=stroke, r=7)
    cx = x + (w - (iw + tw_ + sw_)) / 2
    if icon:
        cv.icon(icon, cx, y + (h - 16) / 2, 16, fg)
        cx += iw
    cv.text(cx, y, label, role, fg, w=tw_ + 1, h=h)
    if shortcut:
        col = C(fg)
        col.setAlphaF(0.75)
        cv.text(cx + tw_ + 8, y, shortcut, "callout", col, w=sw_, h=h)
    return w


def segmented(cv, x, y, items, sel, h=28, role="calloutm", pad=12, widths=None, disabled=()):
    ws = widths or [tw(s, role) + pad * 2 for s in items]
    W = sum(ws) + 4
    cv.rect(x, y, W, h, fill="sunken", stroke="sep", r=8)
    cx = x + 2
    for i, (s, w) in enumerate(zip(items, ws)):
        if i == sel:
            cv.rect(cx, y + 2 + 1, w, h - 4, fill=C("shadow", 0.07), r=6)
            cv.rect(cx, y + 2, w, h - 4, fill="surface", r=6)
        elif i > 0 and i - 1 != sel:
            cv.vline(cx, y + 8, y + h - 8, "border")
        col = "text1" if i == sel else ("disabled" if i in disabled else "text2")
        cv.text(
            cx,
            y,
            s,
            role if i != sel else role.rstrip("m") + "m" if role.endswith("m") else role,
            col,
            w=w,
            h=h,
            align="c",
        )
        cx += w
    return W


def chip(cv, x, y, label, icon=None, h=24, tone="neutral", role="callout"):
    fills = {
        "neutral": ("sunken", "text2", "sep"),
        "accent": ("accent.soft", "accent.text", None),
        "warn": ("warn.soft", "warn", None),
        "crit": ("crit.soft", "crit", None),
        "planned": ("planned.soft", "planned", None),
        "good": ("good.soft", "good", None),
    }
    fill, fg, st = fills[tone]
    w = tw(label, role) + 20 + (18 if icon else 0)
    cv.rect(x, y, w, h, fill=fill, stroke=st, r=h / 2)
    cx = x + 10
    if icon:
        cv.icon(icon, cx, y + (h - 14) / 2, 14, fg)
        cx += 18
    cv.text(cx, y, label, role, fg, w=w - (cx - x) - 8, h=h)
    return w


def checkbox(cv, x, y, checked=False, disabled=False, focus=False, size=16):
    if focus:
        cv.rect(x - 3, y - 3, size + 6, size + 6, stroke=C("focus", 0.55), r=7, sw=2.5)
    if checked:
        cv.rect(x, y, size, size, fill="accent" if not disabled else "disabled", r=4)
        cv.icon("check", x + 2, y + 2, size - 4, "on.accent", stroke=2.0)
    else:
        cv.rect(
            x, y, size, size, fill="surface", stroke="control" if not disabled else "border", r=4
        )


def toggle(cv, x, y, on=False):
    cv.rect(x, y, 32, 18, fill="accent" if on else "border", r=9)
    cv.circle(x + (23 if on else 9), y + 9, 7, fill="#FFFFFF")


def popup(cv, x, y, w, label, h=28, disabled=False, role="body"):
    cv.rect(x, y + 1, w, h, fill=C("shadow", 0.04), r=7)
    cv.rect(x, y, w, h, fill="surface" if not disabled else "sunken", stroke="border", r=7)
    cv.text(x + 10, y, label, role, "text1" if not disabled else "disabled", w=w - 34, h=h)
    cv.icon(
        "chevron-down", x + w - 22, y + (h - 14) / 2, 14, "text3" if not disabled else "disabled"
    )


def traffic_lights(cv, x=20, y=20, dim=False):
    for i, k in enumerate(("tl.red", "tl.yel", "tl.grn")):
        c = C(k) if not dim else C("border")
        cv.circle(x + 6 + i * 20, y + 6, 6, fill=c, stroke=C("shadow", 0.12), sw=0.5)


def app_icon(cv, x, y, s=20):
    cv.rect(x, y, s, s, fill="#177E89", r=s * 0.26)
    cv.circle(x + s / 2, y + s / 2, s * 0.34, stroke="#FFFFFF", sw=max(1.2, s / 14))
    pts = []
    for i in range(29):
        t = i / 28
        xx = x + s * 0.25 + t * s * 0.5
        yy = y + s / 2 + math.sin(t * math.pi * 4) * s * 0.12 * math.sin(t * math.pi)
        pts.append((xx, yy))
    cv.path(pts, "#FFFFFF", sw=max(1.1, s / 16))


def mock_label(cv, text=None):
    """Footer strip under the window marking the image as a design mockup."""
    if not cv.foot:
        return
    y = cv.H
    cv.p.fillRect(QRectF(0, y, cv.W, cv.foot), QColor("#2A2926"))
    s = text or L(
        "设计稿 DESIGN MOCKUP · 非交互验证 · 合成演示数据",
        "DESIGN MOCKUP · not interaction-verified · synthetic demo data",
    )
    cv.text(12, y, s, "caption", QColor("#F3F1EC"), w=cv.W * 0.7, h=cv.foot)
    meta = f"{cv.name} · {MODE['W']}×{MODE['H']} · {MODE['lang']}-{MODE['theme']}"
    cv.text(
        cv.W * 0.5, y, meta, "caption", QColor("#C9C4BA"), w=cv.W * 0.5 - 12, h=cv.foot, align="r"
    )
