# ruff: noqa: ARG001, N802
# Design-phase mockup renderer (docs only, not product code).
"""Pro-desktop design kit: tokens, fonts, QSS and small widgets (design phase only).

Not product code. Renders 1440x900 mockups offscreen with PySide6 + pyqtgraph,
the same stack main uses (ui/pg.py, ui/plotkit.py). Token keys extend
src/reverbscope/ui/theme.py LIGHT_TOKENS / DARK_TOKENS (19 keys) and are the
values proposed in docs/design/pro/DESIGN_SYSTEM.md.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QByteArray, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QPainter, QPen, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

# Re-exported for the screen modules (pk.QLineEdit, pk.QProgressBar).
REEXPORT = (QLineEdit, QProgressBar)

HERE = Path(__file__).resolve().parent
PROTO = HERE.parent
DESIGN = PROTO.parent
# Asset locations. Defaults fit the design workspace; inside the repository
# (docs/design/pro/prototype/) set them with environment variables:
#   RS_MAIN       the repository's src/ (ReverbScope's own display code)
#   RS_ICONS      a folder of Lucide SVGs (lucide-static 0.460.0, ISC)
#   RS_FONT_DIR   IBM Plex Sans / Mono and Source Han Sans CN files (OFL 1.1)
#   RS_DEMO_DIR   the folder `reverbscope demo --out DIR` wrote
#   RS_OUT        where PNGs go
_in_repo = HERE.parts[-3:] == ("design", "pro", "prototype")
_repo_src = HERE.parents[3] / "src" if _in_repo else Path("/workspace/work/rs-main/src")
RS_MAIN = Path(os.environ.get("RS_MAIN", str(_repo_src)))
sys.path.insert(0, str(RS_MAIN))
ICONS = Path(os.environ.get("RS_ICONS", str(PROTO / "icons")))
FONT_DIR = Path(os.environ.get("RS_FONT_DIR", str(DESIGN / "fonts" / "use")))
DEMO_DIR = Path(os.environ.get("RS_DEMO_DIR", str(DESIGN / "cli" / "demo")))
OUT_DIR = Path(os.environ.get("RS_OUT", str(DESIGN / "out" / "pro" / "screens")))

# ------------------------------------------------------------------ tokens
# Base: the 19 keys of main's theme.py, unchanged. New keys below are additions.
MAIN_LIGHT = {
    "bg": "#f1f1f0",
    "surface": "#ffffff",
    "surface_alt": "#e9e9e7",
    "border": "#cececb",
    "text": "#242526",
    "muted": "#545659",
    "accent": "#177e89",
    "accent_hover": "#12656e",
    "accent_text": "#ffffff",
    "accent_soft": "#e6eeee",
    "good": "#1e6b24",
    "good_soft": "#e5f3e7",
    "warn": "#8a4e00",
    "warn_soft": "#fdf0dc",
    "bad": "#c62828",
    "bad_soft": "#fbe7e7",
    "info": "#1f5fa8",
    "info_soft": "#e4eefa",
    "grid": "#d5dbe2",
}
MAIN_DARK = {
    "bg": "#1b1c1e",
    "surface": "#222325",
    "surface_alt": "#2b2c2f",
    "border": "#404145",
    "text": "#ededeb",
    "muted": "#b6b7bb",
    "accent": "#71b7bc",
    "accent_hover": "#8dc8cc",
    "accent_text": "#0d1216",
    "accent_soft": "#293c3e",
    "good": "#6cc070",
    "good_soft": "#1d3322",
    "warn": "#f0b35a",
    "warn_soft": "#3a2e1a",
    "bad": "#f08a8a",
    "bad_soft": "#3d2020",
    "info": "#7fb2ee",
    "info_soft": "#1c2c40",
    "grid": "#67696d",
}
NEW_LIGHT = {
    "toolbar": "#e8e8e6",  # unified title/toolbar band
    "sidebar": "#f1f1f0",  # = bg; the measurement list
    "panel": "#f7f7f6",  # right inspector
    "hover": "#e2e2df",
    "pressed": "#d6d6d3",
    "selected": "#d9e8e9",  # selected list row (accent tint)
    "text_disabled": "#9a9c9f",
    "faint": "#5f6266",  # tertiary text >= 4.5:1 on every light surface
    "border_strong": "#8c8f93",  # input/checkbox outline, >= 3:1 (WCAG 1.4.11)
    "focus": "#177e89",
    "accent_fg": "#136a73",
    "accent_pressed": "#0e5158",  # accent used as text on tinted surfaces
    "plot_bg": "#ffffff",
    "plot_grid_major": "#d9dce0",
    "plot_grid_minor": "#eef0f2",
    "plot_axis": "#8c8f93",
    "plot_text": "#545659",
    "plot_zero": "#a9adb2",
    "plot_excluded": "#c9ccd0",  # hatch outside the excitation band / not analysed
    "cursor": "#242526",
    "cursor_flag_text": "#ffffff",
    "readout_bg": "#f4f5f6",
    "planned": "#5b4bc4",
    "planned_soft": "#eeebfb",
    # GUIDELINES §13.2 data colours, unchanged (each >= 3:1 on plot_bg)
    "series_1": "#177e89",
    "series_2": "#d9731f",
    "series_3": "#6b5bd2",
    "series_4": "#2f9e57",
    "series_5": "#c2417e",
    "series_6": "#8c6d1f",
    "series_7": "#3b82c4",
    "series_8": "#6b7280",
    # octave-band ramp 63 Hz -> 8 kHz: viridis 0-0.92, darkened until >= 3:1 on plot_bg
    "band_1": "#440154",
    "band_2": "#472f7d",
    "band_3": "#39558c",
    "band_4": "#2a778e",
    "band_5": "#1f968b",
    "band_6": "#2da670",
    "band_7": "#4ba62e",
    "band_8": "#899a15",
}
NEW_DARK = {
    "toolbar": "#2a2b2e",
    "sidebar": "#1f2022",
    "panel": "#1f2022",
    "hover": "#323337",
    "pressed": "#3b3d41",
    "selected": "#24393b",
    "text_disabled": "#6c6e73",
    "faint": "#a3a5aa",
    "border_strong": "#7a7d83",
    "focus": "#71b7bc",
    "accent_fg": "#7cc2c7",
    "accent_pressed": "#5a9ea3",
    "plot_bg": "#161719",
    "plot_grid_major": "#33353a",
    "plot_grid_minor": "#232528",
    "plot_axis": "#6c6e73",
    "plot_text": "#b6b7bb",
    "plot_zero": "#5c5f64",
    "plot_excluded": "#3a3c40",
    "cursor": "#ededeb",
    "cursor_flag_text": "#161719",
    "readout_bg": "#1d1e21",
    "planned": "#a99cf0",
    "planned_soft": "#2a2640",
    "series_1": "#4fb6c3",
    "series_2": "#f29a52",
    "series_3": "#9c8fea",
    "series_4": "#5bc07f",
    "series_5": "#e07aaa",
    "series_6": "#c7a34a",
    "series_7": "#79aee3",
    "series_8": "#9ca3af",
    # viridis 0.22-1.0, lightened until >= 3:1 on plot_bg
    "band_1": "#505eb0",
    "band_2": "#326a92",
    "band_3": "#26828e",
    "band_4": "#1e9d89",
    "band_5": "#35b779",
    "band_6": "#6ccd5a",
    "band_7": "#b4de2c",
    "band_8": "#fde725",
}
LIGHT = {**MAIN_LIGHT, **NEW_LIGHT}
DARK = {**MAIN_DARK, **NEW_DARK}

# spacing (4-pt grid), sizes
SP = {0: 0, 1: 2, 2: 4, 3: 6, 4: 8, 5: 12, 6: 16, 7: 24}
SIZE = {
    "toolbar_h": 52,
    "chartbar_h": 34,
    "control_bar_h": 44,
    "readout_h": 24,
    "list_w": 220,
    "list_min": 200,
    "rail_w": 48,
    "panel_w": 288,
    "panel_min": 264,
    "row_h": 24,
    "table_row_h": 22,
    "control_h": 24,
    "tool_h": 26,
}


class State:
    lang = "zh"
    theme = "light"
    W = 1440
    H = 900
    T: dict[str, str] = LIGHT
    mode = "pro"
    tmp = Path(tempfile.mkdtemp(prefix="rs-pro-"))


S = State()


def set_mode(lang: str, theme: str, w: int = 1440, h: int = 900, mode: str = "pro") -> None:
    S.lang, S.theme, S.W, S.H, S.mode = lang, theme, w, h, mode
    S.T = LIGHT if theme == "light" else DARK


def L(zh: str, en: str) -> str:
    return zh if S.lang == "zh" else en


def C(token: str) -> str:
    return S.T[token]


def rgba(token: str, a: float) -> str:
    c = QColor(C(token))
    return f"rgba({c.red()},{c.green()},{c.blue()},{a})"


# ------------------------------------------------------------------ fonts
SANS = ["IBM Plex Sans", "Source Han Sans CN"]
MONO = ["IBM Plex Mono", "Source Han Sans CN"]
FONT_FILES = [
    "IBMPlexSans-Regular.ttf",
    "IBMPlexSans-Medium.ttf",
    "IBMPlexSans-SemiBold.ttf",
    "SourceHanSansCN-Regular.otf",
    "SourceHanSansCN-Medium.otf",
    "SourceHanSansCN-Bold.otf",
    "IBMPlexMono-Regular.ttf",
    "IBMPlexMono-Medium.ttf",
    "IBMPlexMono-SemiBold.ttf",
]
_loaded = False

# type scale: role -> (px, weight, family)
TYPE = {
    "window_title": (13, 600, "sans"),
    "heading": (13, 600, "sans"),  # panel / section heading
    "body": (13, 400, "sans"),
    "control": (12, 400, "sans"),  # buttons, combos, list rows, tabs
    "control_strong": (12, 600, "sans"),
    "label": (11, 500, "sans"),  # section labels, column headers, badges
    "caption": (11, 400, "sans"),  # footnotes
    "num": (12, 400, "mono"),  # table numbers, list values
    "num_strong": (12, 600, "mono"),
    "num_lg": (15, 500, "mono"),  # inspector key figures
    "readout": (12, 400, "mono"),  # cursor readout bar
    "tick": (11, 400, "mono"),  # axis ticks
}


def ensure_fonts() -> None:
    global _loaded
    if _loaded:
        return
    for fn in FONT_FILES:
        if QFontDatabase.addApplicationFont(str(FONT_DIR / fn)) < 0:
            raise RuntimeError(f"font {fn} missing")
    _loaded = True


def font(role: str = "body", size: int | None = None, weight: int | None = None) -> QFont:
    px, w, fam = TYPE[role]
    f = QFont()
    f.setFamilies(MONO if fam == "mono" else SANS)
    f.setPixelSize(size or px)
    f.setWeight(QFont.Weight(weight or w))
    f.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    return f


# ------------------------------------------------------------------ icons
def ipix(name: str, size: int = 16, color: str = "muted", stroke: float = 1.75) -> QPixmap:
    col = C(color) if color in S.T else color
    svg = (ICONS / f"{name}.svg").read_text()
    svg = svg.replace("currentColor", col)
    svg = svg.replace('stroke-width="2"', f'stroke-width="{stroke}"')
    r = QSvgRenderer(QByteArray(svg.encode()))
    dpr = 2
    pm = QPixmap(size * dpr, size * dpr)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    r.render(p, QRectF(0, 0, size * dpr, size * dpr))
    p.end()
    pm.setDevicePixelRatio(dpr)
    return pm


def icon_file(name: str, color: str, stroke: float = 2.0) -> str:
    col = C(color) if color in S.T else color
    path = S.tmp / f"{name}-{col.strip('#')}-{stroke}.svg"
    if not path.exists():
        svg = (ICONS / f"{name}.svg").read_text().replace("currentColor", col)
        path.write_text(svg.replace('stroke-width="2"', f'stroke-width="{stroke}"'))
    return path.as_posix()


def ico(name: str, size: int = 16, color: str = "muted") -> QLabel:
    lab = QLabel()
    lab.setPixmap(ipix(name, size, color))
    lab.setFixedSize(size, size)
    lab.setStyleSheet("background:transparent;")
    return lab


# ------------------------------------------------------------------ QSS
def qss() -> str:
    t = S.T
    icon_file("chevron-down", "muted", 2.0)
    check = icon_file("check", "accent_text", 3.0)
    return f"""
* {{ outline: none; }}
QWidget {{ color: {t["text"]}; background: transparent; }}
QWidget#window {{ background: {t["bg"]}; }}
QLabel {{ background: transparent; }}
QFrame[role="toolbar"] {{ background: {t["toolbar"]}; border-bottom: 1px solid {t["border"]}; }}
QFrame[role="sidebar"] {{ background: {t["sidebar"]}; border-right: 1px solid {t["border"]}; }}
QFrame[role="panel"] {{ background: {t["panel"]}; border-left: 1px solid {t["border"]}; }}
QFrame[role="center"] {{ background: {t["plot_bg"]}; }}
QFrame[role="chartbar"] {{ background: {t["surface"]}; border-bottom: 1px solid {t["border"]}; }}
QFrame[role="controlbar"] {{ background: {t["toolbar"]}; border-top: 1px solid {t["border"]}; }}
QFrame[role="controlbar"][measuring="true"] {{ border-top: 2px solid {t["accent"]}; }}
QFrame[role="readout"] {{ background: {t["readout_bg"]}; border-top: 1px solid {t["border"]}; }}
QFrame[role="hline"] {{ background: {t["border"]}; max-height: 1px; min-height: 1px; }}
QFrame[role="vline"] {{ background: {t["border"]}; max-width: 1px; min-width: 1px; }}
QFrame[role="row"] {{ border-radius: 4px; }}
QFrame[role="row"][sel="true"] {{ background: {t["selected"]}; }}
QFrame[role="row"][hover="true"] {{ background: {t["hover"]}; }}
QFrame[role="banner"] {{ background: {t["accent_soft"]}; border: 1px solid {rgba("accent", 0.45)}; border-radius: 4px; }}
QFrame[role="banner"][tone="warn"] {{ background: {t["warn_soft"]}; border: 1px solid {rgba("warn", 0.45)}; }}
QFrame[role="banner"][tone="bad"] {{ background: {t["bad_soft"]}; border: 1px solid {rgba("bad", 0.5)}; }}
QFrame[role="badge"] {{ border-radius: 3px; background: {t["surface_alt"]}; }}
QFrame[role="badge"][tone="planned"] {{ background: {t["planned_soft"]}; border: 1px solid {rgba("planned", 0.55)}; }}
QFrame[role="badge"][tone="synthetic"] {{ background: {t["info_soft"]}; border: 1px solid {rgba("info", 0.45)}; }}
QFrame[role="popover"] {{ background: {t["surface"]}; border: 1px solid {t["border"]}; border-radius: 6px; }}
QFrame[role="seg"] {{ background: {t["surface_alt"]}; border-radius: 5px; }}
QToolButton, QPushButton {{ font-size: 12px; }}
QToolButton[role="tool"] {{ border: 1px solid transparent; border-radius: 4px; padding: 2px 6px; color: {t["text"]}; }}
QToolButton[role="tool"][state="hover"] {{ background: {t["hover"]}; }}
QToolButton[role="tool"][state="pressed"] {{ background: {t["pressed"]}; }}
QToolButton[role="tool"][state="on"] {{ background: {t["accent_soft"]}; color: {t["accent_fg"]}; border: 1px solid {rgba("accent", 0.5)}; }}
QToolButton[role="tool"][state="focus"] {{ border: 2px solid {t["focus"]}; }}
QToolButton[role="tool"][state="disabled"] {{ color: {t["text_disabled"]}; }}
QToolButton[role="segbtn"] {{ border: none; border-radius: 4px; padding: 2px 10px; color: {t["muted"]}; }}
QToolButton[role="segbtn"][icononly="true"] {{ padding: 0px; }}
QToolButton[role="segbtn"][on="true"] {{ background: {t["surface"]}; color: {t["text"]}; font-weight: 600; border: 1px solid {t["border"]}; }}
QPushButton[role="btn"] {{ background: {t["surface"]}; border: 1px solid {t["border_strong"]}; border-radius: 4px; padding: 3px 10px; min-height: 16px; }}
QPushButton[role="btn"][state="hover"] {{ background: {t["hover"]}; }}
QPushButton[role="btn"][state="pressed"] {{ background: {t["pressed"]}; }}
QPushButton[role="btn"][state="disabled"] {{ color: {t["text_disabled"]}; border-color: {t["border"]}; background: {t["surface"]}; }}
QPushButton[role="btn"][state="focus"] {{ border: 2px solid {t["focus"]}; padding: 2px 9px; }}
QPushButton[role="btn"][state="on"] {{ background: {t["accent_soft"]}; color: {t["accent_fg"]}; border-color: {t["accent"]}; }}
QPushButton[role="primary"] {{ background: {t["accent"]}; color: {t["accent_text"]}; border: 1px solid {t["accent"]}; border-radius: 4px; padding: 3px 12px; font-weight: 600; min-height: 16px; }}
QPushButton[role="primary"][state="hover"] {{ background: {t["accent_hover"]}; border-color: {t["accent_hover"]}; }}
QPushButton[role="primary"][state="pressed"] {{ background: {t["accent_pressed"]}; border-color: {t["accent_pressed"]}; }}
QPushButton[role="primary"][state="disabled"] {{ background: {t["surface_alt"]}; color: {t["text_disabled"]}; border-color: {t["border"]}; }}
QPushButton[role="primary"][state="focus"] {{ border: 2px solid {t["text"]}; }}
QPushButton[role="danger"] {{ background: {t["bad"]}; color: {"#ffffff" if S.theme == "light" else "#1b1c1e"}; border: 1px solid {t["bad"]}; border-radius: 4px; padding: 3px 12px; font-weight: 600; min-height: 16px; }}
QPushButton[role="combo"] {{ background: {t["surface"]}; border: 1px solid {t["border"]}; border-radius: 4px; padding: 2px 20px 2px 7px; text-align: left; min-height: 16px; }}
QPushButton[role="combo"][flat="true"] {{ background: transparent; border: 1px solid transparent; }}
QLineEdit {{ background: {t["surface"]}; border: 1px solid {t["border_strong"]}; border-radius: 4px; padding: 2px 6px; font-size: 12px; selection-background-color: {t["accent_soft"]}; }}
QCheckBox {{ spacing: 6px; font-size: 12px; }}
QCheckBox::indicator {{ width: 13px; height: 13px; border: 1px solid {t["border_strong"]}; border-radius: 3px; background: {t["surface"]}; }}
QCheckBox::indicator:checked {{ background: {t["accent"]}; border-color: {t["accent"]}; image: url({check}); }}
QProgressBar {{ background: {t["surface_alt"]}; border: none; border-radius: 2px; }}
QProgressBar::chunk {{ background: {t["accent"]}; border-radius: 2px; }}
QTableWidget {{ background: {t["surface"]}; border: none; gridline-color: transparent; font-size: 12px; }}
QHeaderView::section {{ background: {t["surface"]}; color: {t["muted"]}; border: none; border-bottom: 1px solid {t["border"]}; padding: 0 6px; font-size: 11px; font-weight: 600; }}
"""


# ------------------------------------------------------------------ widgets
def lab(
    text: str,
    role: str = "body",
    color: str = "text",
    wrap: bool = False,
    align=None,
    width: int | None = None,
    size: int | None = None,
    weight: int | None = None,
) -> QLabel:
    w = QLabel(text)
    w.setFont(font(role, size, weight))
    w.setStyleSheet(f"color:{C(color) if color in S.T else color}; background:transparent;")
    w.setWordWrap(wrap)
    if align is not None:
        w.setAlignment(align)
    if width:
        w.setFixedWidth(width)
    return w


def num(
    text: str,
    color: str = "text",
    strong: bool = False,
    align_right: bool = True,
    width: int | None = None,
    size: int | None = None,
) -> QLabel:
    w = lab(text, "num_strong" if strong else "num", color, size=size)
    if align_right:
        w.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    if width:
        w.setFixedWidth(width)
    return w


def _add(lay, it) -> None:
    if it is None:
        return
    if it == "stretch":
        lay.addStretch(1)
    elif isinstance(it, int):
        lay.addSpacing(it)
    else:
        lay.addWidget(it)


def hbox(*items, spacing: int = 6, margins=(0, 0, 0, 0), role: str | None = None) -> QWidget:
    w = QFrame() if role else QWidget()
    if role:
        w.setProperty("role", role)
    lay = QHBoxLayout(w)
    lay.setContentsMargins(*margins)
    lay.setSpacing(spacing)
    for it in items:
        _add(lay, it)
    return w


def vbox(*items, spacing: int = 6, margins=(0, 0, 0, 0), role: str | None = None) -> QWidget:
    w = QFrame() if role else QWidget()
    if role:
        w.setProperty("role", role)
    lay = QVBoxLayout(w)
    lay.setContentsMargins(*margins)
    lay.setSpacing(spacing)
    for it in items:
        _add(lay, it)
    return w


def frame(role: str, **props) -> QFrame:
    f = QFrame()
    f.setProperty("role", role)
    for k, v in props.items():
        f.setProperty(k, v)
    return f


def hline() -> QFrame:
    return frame("hline")


def vline(h: int | None = 18) -> QFrame:
    f = frame("vline")
    if h:
        f.setFixedHeight(h)
    return f


def tool(
    icon: str | None = None,
    text: str = "",
    state: str = "",
    tip_key: str | None = None,
    icon_color: str | None = None,
    size: int = 16,
) -> QToolButton:
    b = QToolButton()
    b.setProperty("role", "tool")
    if state:
        b.setProperty("state", state)
    if icon:
        col = icon_color or (
            "accent_fg" if state == "on" else "text_disabled" if state == "disabled" else "text"
        )
        b.setIcon(ipix(icon, size, col))
        b.setIconSize(QSize(size, size))
    if text:
        b.setText(text)
        b.setFont(font("control"))
        if icon:
            b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
    b.setFixedHeight(SIZE["tool_h"])
    return b


def btn(
    text: str,
    kind: str = "btn",
    state: str = "",
    icon: str | None = None,
    icon_color: str | None = None,
) -> QPushButton:
    b = QPushButton(text)
    b.setProperty("role", kind)
    if state:
        b.setProperty("state", state)
    b.setFont(font("control_strong" if kind in ("primary", "danger") else "control"))
    if icon:
        col = icon_color or ("accent_text" if kind == "primary" else "text")
        if kind == "danger":
            col = "#ffffff" if S.theme == "light" else "#1b1c1e"
        if state == "disabled":
            col = "text_disabled"
        b.setIcon(ipix(icon, 14, col))
        b.setIconSize(QSize(14, 14))
    b.setFixedHeight(SIZE["control_h"])
    return b


def combo(
    text: str, width: int | None = None, flat: bool = False, mono: bool = False
) -> QPushButton:
    b = QPushButton(text)
    b.setProperty("role", "combo")
    if flat:
        b.setProperty("flat", "true")
    b.setFont(font("num" if mono else "control"))
    b.setFixedHeight(SIZE["control_h"])
    if width:
        b.setFixedWidth(width)
        avail = width - 30
        b.setText(b.fontMetrics().elidedText(text, Qt.TextElideMode.ElideRight, avail))
    arrow = QLabel(b)
    arrow.setPixmap(ipix("chevron-down", 12, "muted"))
    arrow.setFixedSize(12, 12)
    arrow.setStyleSheet("background:transparent;")

    def place(ev=None, b=b, arrow=arrow):
        arrow.move(b.width() - 17, (b.height() - 12) // 2)

    b.resizeEvent = place  # type: ignore[assignment]
    return b


def labelled(label: str, widget: QWidget, spacing: int = 4) -> QWidget:
    return hbox(lab(label, "control", "muted"), widget, spacing=spacing)


def seg(
    options: list[str],
    selected: int,
    icons: list[str | None] | None = None,
    planned: set[int] | None = None,
) -> QFrame:
    f = frame("seg")
    lay = QHBoxLayout(f)
    lay.setContentsMargins(2, 2, 2, 2)
    lay.setSpacing(0)
    for i, o in enumerate(options):
        b = QToolButton()
        b.setProperty("role", "segbtn")
        b.setProperty("on", "true" if i == selected else "false")
        b.setText(o)
        b.setFont(font("control_strong" if i == selected else "control"))
        if icons and icons[i]:
            b.setIcon(ipix(icons[i], 14, "text" if i == selected else "muted"))
            b.setIconSize(QSize(14, 14))
            b.setToolButtonStyle(
                Qt.ToolButtonStyle.ToolButtonTextBesideIcon
                if o
                else Qt.ToolButtonStyle.ToolButtonIconOnly
            )
            if not o:
                b.setProperty("icononly", "true")
        b.setFixedHeight(22)
        lay.addWidget(b)
        if planned and i in planned:
            dot = QLabel(b)
            dot.setFixedSize(6, 6)
            dot.setStyleSheet(f"background:{C('planned')}; border-radius:3px;")
            dot.move(2, 2)
    return f


def check(text: str, on: bool = False) -> QCheckBox:
    c = QCheckBox(text)
    c.setChecked(on)
    c.setFont(font("control"))
    return c


def badge(text: str, tone: str = "planned", icon: str | None = None) -> QFrame:
    f = frame("badge", tone=tone)
    lay = QHBoxLayout(f)
    lay.setContentsMargins(5, 1, 6, 1)
    lay.setSpacing(3)
    col = {"planned": "planned", "synthetic": "info"}.get(tone, "muted")
    if icon:
        lay.addWidget(ico(icon, 11, col))
    lay.addWidget(lab(text, "label", col, size=10 if tone == "planned" else 11))
    f.setFixedHeight(18)
    return f


def planned_badge(text: str | None = None) -> QFrame:
    return badge(text or L("未实现", "Planned"), "planned", "circle-dashed")


def synthetic_badge() -> QFrame:
    return badge(L("合成演示数据", "Synthetic demo data"), "synthetic", "flask-conical")


def swatch(color: str, dashed: bool = False, w: int = 14) -> QLabel:
    pm = QPixmap(w * 2, 8 * 2)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(C(color) if color in S.T else color), 2.4 * 2)
    if dashed:
        pen.setStyle(Qt.PenStyle.DashLine)
        pen.setDashPattern([2.2, 1.4])
    p.setPen(pen)
    p.drawLine(1, 8, w * 2 - 1, 8)
    p.end()
    pm.setDevicePixelRatio(2)
    lb = QLabel()
    lb.setPixmap(pm)
    lb.setFixedSize(w, 8)
    return lb


def dot(color: str, size: int = 8) -> QLabel:
    d = QLabel()
    d.setFixedSize(size, size)
    d.setStyleSheet(
        f"background:{C(color) if color in S.T else color}; border-radius:{size // 2}px;"
    )
    return d


def status_icon(tone: str, size: int = 13) -> QLabel:
    name = {
        "good": "circle-check",
        "warn": "triangle-alert",
        "bad": "circle-x",
        "info": "info",
        "neutral": "circle",
        "unknown": "circle-help",
    }[tone]
    color = {"neutral": "muted", "unknown": "muted"}.get(tone, tone)
    return ico(name, size, color)


def kbd(text: str) -> QLabel:
    k = lab(text, "caption", "faint")
    return k


def spacer_w(w: int) -> QWidget:
    s = QWidget()
    s.setFixedWidth(w)
    return s


def expanding(w: QWidget) -> QWidget:
    w.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
    return w


def traffic_lights() -> QWidget:
    w = QWidget()
    w.setFixedSize(58, 14)
    cols = ("#ff5f57", "#febc2e", "#28c840")

    def paint(ev, w=w):
        p = QPainter(w)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        for i, c in enumerate(cols):
            p.setBrush(QColor(c))
            p.setPen(QPen(QColor(0, 0, 0, 40), 0.5))
            p.drawEllipse(QRectF(i * 20 + 0.5, 0.5, 12, 12))
        p.end()

    w.paintEvent = paint  # type: ignore[assignment]
    return w


def app() -> QApplication:
    a = QApplication.instance() or QApplication(sys.argv)
    ensure_fonts()
    return a
