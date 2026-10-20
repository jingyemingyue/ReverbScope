"""GUI and plot chrome that follows the system colour scheme.

ARCHITECTURE_V1.md §5.8 asks for system dark mode and for plots that stay
readable when colour is not available. Matplotlib does not follow Qt on its
own; these helpers restyle figures after they are drawn. ``REVERBSCOPE_COLOR_SCHEME``
overrides the system for tests (``dark`` or ``light``).
"""

from __future__ import annotations

import functools
import os
import sys
from typing import Any

from matplotlib.figure import Figure

ENV_COLOR_SCHEME = "REVERBSCOPE_COLOR_SCHEME"

#: Design tokens: the light, warm "sidebar" look of docs/design/light-sidebar
#: (SPEC §2) and its dark twin. One accent (a measured "scope" teal), warm
#: neutral surfaces and one tone per validity / severity, so a number's trust
#: level reads at a glance. Body text stays above WCAG AA on every surface
#: (tests/unit/test_theme_contrast.py). The first block keeps the names the
#: views have always used; the second adds the sidebar, toolbar and plot roles.
LIGHT_TOKENS: dict[str, str] = {
    "bg": "#fbfaf8",
    "surface": "#ffffff",
    "surface_alt": "#f3f1ed",
    "border": "#d6d2ca",
    "text": "#1d1b18",
    "muted": "#57534c",
    "accent": "#177e89",
    "accent_hover": "#136c76",
    "accent_text": "#ffffff",
    "accent_soft": "#e3f1f2",
    "good": "#2d7b31",
    "good_soft": "#e7f3e5",
    "warn": "#9a5b00",
    "warn_soft": "#fdf1de",
    "bad": "#c62828",
    "bad_soft": "#fbe9e9",
    "info": "#1f5fa8",
    "info_soft": "#e6eef9",
    "grid": "#8a857b",
    # sidebar, toolbar, controls
    "sidebar_top": "#f3f1ec",
    "sidebar_bot": "#ece9e3",
    "hover": "#e8e5df",
    "sel_sidebar": "#ddeaea",
    "sep": "#e5e2db",
    "control": "#8a857b",
    "text3": "#68645d",
    "disabled": "#a9a49b",
    "accent_ink": "#136c76",
    "on_bad": "#ffffff",
    "readout": "#f6f4f0",
    "axis": "#8a857b",
}
DARK_TOKENS: dict[str, str] = {
    "bg": "#1e1d1b",
    "surface": "#2c2b28",
    "surface_alt": "#232220",
    "border": "#4a4741",
    "text": "#eceae4",
    "muted": "#b5b0a6",
    "accent": "#4fb6c3",
    "accent_hover": "#5cc0cc",
    "accent_text": "#0b1114",
    "accent_soft": "#183a3f",
    "good": "#6cc070",
    "good_soft": "#1d3322",
    "warn": "#f0b35a",
    "warn_soft": "#352915",
    "bad": "#ef6a6a",
    "bad_soft": "#3a1d1d",
    "info": "#7fb2ee",
    "info_soft": "#1c2c40",
    "grid": "#7d786f",
    "sidebar_top": "#2b2a27",
    "sidebar_bot": "#262522",
    "hover": "#34322f",
    "sel_sidebar": "#21393b",
    "sep": "#3a3834",
    "control": "#7d786f",
    "text3": "#9c978e",
    "disabled": "#6a665f",
    "accent_ink": "#5cc0cc",
    "on_bad": "#1a0b0b",
    "readout": "#232220",
    "axis": "#7d786f",
}
#: Series colours for plots, in drawing order; distinct in both schemes and
#: paired with line styles so they survive greyscale printing.
PLOT_SERIES = ("#177e89", "#e07a2e", "#7a5cc7", "#3f9c4a", "#c2437a", "#8a8f98")

_DARK = {
    "bg": DARK_TOKENS["surface"],
    "fg": DARK_TOKENS["text"],
    "grid": "#45423d",
    "muted": DARK_TOKENS["muted"],
}
_LIGHT = {
    "bg": LIGHT_TOKENS["surface"],
    "fg": LIGHT_TOKENS["text"],
    "grid": "#e3e0da",
    "muted": LIGHT_TOKENS["muted"],
}


def color_scheme() -> str:
    """Return ``dark`` or ``light``."""
    forced = os.environ.get(ENV_COLOR_SCHEME, "").strip().lower()
    if forced in {"dark", "light"}:
        return forced
    try:
        from reverbscope.settings import load_settings

        chosen = load_settings().theme
    except Exception:
        chosen = ""
    if chosen in {"dark", "light"}:
        return chosen
    try:
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QGuiApplication
        from PySide6.QtWidgets import QApplication

        if QApplication.instance() is not None:
            # styleHints() is static on QGuiApplication (typed stubs of
            # PySide6 >= 6.9 see instance() as a QCoreApplication).
            scheme = QGuiApplication.styleHints().colorScheme()
            if scheme == Qt.ColorScheme.Dark:
                return "dark"
    except Exception:
        pass
    return "light"


def plot_colors() -> dict[str, str]:
    return dict(_DARK if color_scheme() == "dark" else _LIGHT)


def style_figure(fig: Figure) -> None:
    """Recolour a drawn figure so axes stay readable on a dark or light canvas."""
    colors = plot_colors()
    bg, fg, grid, muted = colors["bg"], colors["fg"], colors["grid"], colors["muted"]
    fig.patch.set_facecolor(bg)
    for ax in fig.get_axes():
        ax.set_facecolor(bg)
        ax.tick_params(colors=fg)
        ax.xaxis.label.set_color(fg)
        ax.yaxis.label.set_color(fg)
        ax.title.set_color(fg)
        for spine in ax.spines.values():
            spine.set_color(muted)
        for line in (*ax.get_xgridlines(), *ax.get_ygridlines()):
            line.set_color(grid)
        # Minor grid lines (log-frequency axes) keep matplotlib's light grey
        # unless they are recoloured too; they stay fainter than the major ones.
        for axis in (ax.xaxis, ax.yaxis):
            for tick in axis.get_minor_ticks():
                tick.gridline.set_color(grid)
                tick.gridline.set_alpha(0.45)
        for text in ax.texts:
            text.set_color(fg)
        zaxis = getattr(ax, "zaxis", None)
        if zaxis is not None:
            zaxis.label.set_color(fg)
            zaxis.set_tick_params(colors=fg)
            for name in ("xaxis", "yaxis", "zaxis"):
                pane = getattr(getattr(ax, name), "pane", None)
                if pane is not None:
                    pane.set_facecolor(bg)
                    pane.set_edgecolor(muted)
        legend = ax.get_legend()
        if legend is not None:
            legend.get_frame().set_facecolor(bg)
            legend.get_frame().set_edgecolor(muted)
            for text in legend.get_texts():
                text.set_color(fg)


def tokens() -> dict[str, str]:
    """The design tokens of the current colour scheme."""
    return dict(DARK_TOKENS if color_scheme() == "dark" else LIGHT_TOKENS)


def _srgb_channel(hex_color: str, index: int) -> float:
    value = int(hex_color[1 + 2 * index : 3 + 2 * index], 16) / 255.0
    if value <= 0.04045:
        return value / 12.92
    # ``float ** float`` is typed as ``Any`` (a negative base can be complex).
    return float(((value + 0.055) / 1.055) ** 2.4)


def relative_luminance(hex_color: str) -> float:
    """WCAG relative luminance of ``#rrggbb``."""
    red = _srgb_channel(hex_color, 0)
    green = _srgb_channel(hex_color, 1)
    blue = _srgb_channel(hex_color, 2)
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def contrast_ratio(foreground: str, background: str) -> float:
    """WCAG 2 contrast of two ``#rrggbb`` colours."""
    lighter = max(relative_luminance(foreground), relative_luminance(background))
    darker = min(relative_luminance(foreground), relative_luminance(background))
    return (lighter + 0.05) / (darker + 0.05)


def tone_color(tone: str) -> tuple[str, str]:
    """``(foreground, soft background)`` for ``good``, ``warn``, ``bad``, ``info``
    or ``neutral``."""
    t = tokens()
    if tone in {"good", "warn", "bad", "info"}:
        return t[tone], t[f"{tone}_soft"]
    return t["muted"], t["surface_alt"]


#: Fonts with Chinese glyphs that ship with macOS, Windows or common Linux
#: distributions. matplotlib (>= 3.6) takes a glyph missing from the first
#: family in ``font.family`` from the next one, so chart titles and labels in
#: the zh-CN catalog are not drawn as empty boxes by DejaVu Sans.
CJK_FALLBACK_FONTS = (
    "PingFang SC",
    "Hiragino Sans GB",
    "Arial Unicode MS",
    "Microsoft YaHei",
    "SimHei",
    "Noto Sans CJK SC",
    "Source Han Sans SC",
    "WenQuanYi Zen Hei",
    "Droid Sans Fallback",
)


#: Linux UI faces tried before the desktop default (installed ones only).
LINUX_UI_FONTS = (
    "Inter",
    "IBM Plex Sans",
    "Noto Sans CJK SC",
    "Source Han Sans SC",
    "Source Han Sans CN",
    "Noto Sans",
)


def font_families() -> list[str]:
    """DejaVu Sans, then the installed fonts of :data:`CJK_FALLBACK_FONTS`."""
    from matplotlib import font_manager

    installed = {entry.name for entry in font_manager.fontManager.ttflist}
    return ["DejaVu Sans", *(name for name in CJK_FALLBACK_FONTS if name in installed)]


def ensure_plot_fonts() -> None:
    """Use :func:`font_families` for text drawn from now on.

    Every ReverbScope chart calls this before it writes a title, so Chinese
    text never falls back to DejaVu Sans alone (empty boxes), even when a
    chart is drawn before :func:`configure_matplotlib` ran (a script, a test,
    an embedding application).
    """
    from matplotlib import rcParams

    families = _cached_font_families()
    if list(rcParams["font.family"]) != families:
        rcParams["font.family"] = families


@functools.cache
def _cached_font_families() -> list[str]:
    return font_families()


def configure_matplotlib() -> None:
    """Series colours, quiet spines and readable sizes for every ReverbScope plot."""
    from cycler import cycler
    from matplotlib import rcParams

    rcParams["font.family"] = font_families()

    rcParams["axes.prop_cycle"] = cycler(color=list(PLOT_SERIES))
    rcParams["axes.spines.top"] = False
    rcParams["axes.spines.right"] = False
    rcParams["axes.titlesize"] = 11
    rcParams["axes.titleweight"] = "bold"
    rcParams["axes.labelsize"] = 9.5
    rcParams["xtick.labelsize"] = 8.5
    rcParams["ytick.labelsize"] = 8.5
    rcParams["legend.fontsize"] = 8.5
    rcParams["legend.frameon"] = True
    rcParams["grid.linewidth"] = 0.6
    rcParams["lines.linewidth"] = 1.4


def stylesheet(t: dict[str, str] | None = None) -> str:
    """The Qt style sheet for the tokens ``t`` (default: the current scheme).

    Widgets opt into roles with dynamic properties: ``role`` on labels
    (``title``, ``subtitle``, ``section``, ``kpi-value``, ``kpi-label``,
    ``hint``, ``display``, ``sidebar-section``), ``card`` on frames,
    ``primary`` / ``danger`` on buttons, ``tone`` on chips, ``sidebar`` on the
    left column, ``viewbar`` on the unified toolbar, ``segmented`` on the view
    switcher and ``toolicon`` on icon-only tool buttons. The measures follow
    the 4/8 pt rhythm of docs/design/light-sidebar/SPEC.md §4: controls 28 px,
    radius 7 (controls), 8 (segment groove), 10 (grouped lists).
    """
    t = t or tokens()
    images = _arrow_images(t["muted"])
    arrow_up = f'image: url("{images[0]}");' if images else ""
    arrow_down = f'image: url("{images[1]}");' if images else ""
    check = _check_image(t["accent_text"])
    check_image = f'image: url("{check}");' if check else ""
    sidebar = (
        f"qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {t['sidebar_top']}, "
        f"stop:1 {t['sidebar_bot']})"
    )
    return f"""
QWidget {{ color: {t["text"]}; font-size: 13px; }}
QMainWindow, QStackedWidget, QScrollArea, QScrollArea > QWidget > QWidget,
QWidget[page="true"] {{ background: {t["bg"]}; }}
QMenuBar {{ background: {t["bg"]}; border-bottom: 1px solid {t["sep"]}; }}
QMenuBar::item {{ padding: 4px 10px; background: transparent; border-radius: 6px; }}
QMenuBar::item:selected {{ background: {t["hover"]}; }}
QMenu {{ background: {t["surface"]}; border: 1px solid {t["border"]}; border-radius: 8px;
    padding: 4px; }}
QMenu::item {{ padding: 5px 22px 5px 12px; border-radius: 5px; }}
QMenu::item:selected {{ background: {t["accent"]}; color: {t["accent_text"]}; }}
QMenu::item:disabled {{ color: {t["disabled"]}; }}
QMenu::separator {{ height: 1px; background: {t["sep"]}; margin: 4px 8px; }}
QToolTip {{ background: {t["surface"]}; color: {t["text"]}; border: 1px solid {t["border"]};
    border-radius: 6px; padding: 4px 8px; }}

QLabel[role="display"] {{ font-size: 30px; font-weight: 600; }}
QLabel[role="title"] {{ font-size: 20px; font-weight: 600; }}
QLabel[role="page-title"] {{ font-size: 20px; font-weight: 600; }}
QLabel[role="toolbar-title"] {{ font-size: 13px; font-weight: 600; }}
QLabel[role="toolbar-subtitle"] {{ color: {t["text3"]}; font-size: 11px; }}
QLabel[role="subtitle"] {{ color: {t["muted"]}; font-size: 13px; }}
QLabel[role="section"] {{ color: {t["text3"]}; font-size: 11px; font-weight: 600; }}
QLabel[role="sidebar-section"] {{ color: {t["text3"]}; font-size: 11px; font-weight: 600;
    padding: 0 8px; }}
QLabel[role="hint"] {{ color: {t["muted"]}; }}
QLabel[role="caption"] {{ color: {t["text3"]}; font-size: 11px; }}
QLabel[role="kpi-label"] {{ color: {t["text3"]}; font-size: 11px; font-weight: 600; }}
QLabel[role="kpi-value"] {{ font-size: 24px; font-weight: 500; }}
QLabel[role="kpi-sub"] {{ color: {t["muted"]}; font-size: 11px; }}
QLabel[role="card-title"] {{ font-size: 15px; font-weight: 600; }}
QLabel[role="badge"] {{ background: {t["surface_alt"]}; color: {t["muted"]};
    border: 1px solid {t["sep"]}; border-radius: 6px; min-width: 22px; min-height: 22px;
    max-height: 22px; padding: 0 6px; font-size: 11px; font-weight: 600;
    qproperty-alignment: AlignCenter; }}
QLabel[role="pill"] {{ background: {t["accent_soft"]}; color: {t["accent_ink"]};
    border: 1px solid {t["accent_soft"]}; border-radius: 11px; padding: 3px 10px;
    font-size: 12px; }}
QLabel[role="demo-tag"] {{ background: {t["info_soft"]}; color: {t["info"]};
    border-radius: 10px; padding: 2px 8px; font-size: 11px; font-weight: 600; }}

QFrame[card="true"], QGroupBox {{ background: {t["surface"]}; border: 1px solid {t["sep"]};
    border-radius: 10px; }}
QFrame[card="true"][hover="true"]:hover {{ border: 1px solid {t["accent"]};
    background: {t["accent_soft"]}; }}
QFrame[composer="true"] {{ background: {t["surface"]}; border: 1px solid {t["border"]};
    border-radius: 18px; }}
QFrame[safeband="true"] {{ background: {t["warn_soft"]}; border: none;
    border-radius: 8px; }}
QFrame[readiness="true"] {{ background: {t["surface"]}; border: 1px solid {t["sep"]};
    border-radius: 10px; }}
QLabel[banner="warn"] {{ background: {t["warn_soft"]}; color: {t["text"]}; border: none;
    border-radius: 8px; padding: 8px 12px; }}
QLabel[banner="info"] {{ background: {t["info_soft"]}; color: {t["text"]}; border: none;
    border-radius: 8px; padding: 8px 12px; }}
QLabel[banner="bad"] {{ background: {t["bad_soft"]}; color: {t["text"]}; border: none;
    border-radius: 8px; padding: 8px 12px; }}
QLabel[banner="good"] {{ background: {t["good_soft"]}; color: {t["text"]}; border: none;
    border-radius: 8px; padding: 8px 12px; }}
QGroupBox {{ margin-top: 24px; padding: 12px 12px 8px 12px; font-weight: 600; }}
QGroupBox::title {{ subcontrol-origin: margin; subcontrol-position: top left; left: 4px;
    top: 4px; padding: 0 4px; color: {t["text3"]}; background: transparent;
    font-size: 11px; }}
QGroupBox QGroupBox {{ background: {t["surface_alt"]}; border-radius: 8px; }}

QPushButton {{ background: {t["surface"]}; border: 1px solid {t["border"]}; border-radius: 7px;
    padding: 4px 12px; min-height: 18px; }}
QPushButton:hover {{ background: {t["hover"]}; }}
QPushButton:pressed {{ background: {t["surface_alt"]}; }}
QPushButton:disabled {{ color: {t["disabled"]}; background: {t["surface_alt"]};
    border-color: {t["sep"]}; }}
QPushButton[primary="true"] {{ background: {t["accent"]}; color: {t["accent_text"]};
    border: 1px solid {t["accent"]}; font-weight: 600; }}
QPushButton[primary="true"]:hover {{ background: {t["accent_hover"]};
    border-color: {t["accent_hover"]}; }}
QPushButton[primary="true"]:disabled {{ background: {t["surface_alt"]};
    border-color: {t["sep"]}; color: {t["disabled"]}; }}
QPushButton[danger="true"] {{ background: {t["bad"]}; color: {t["on_bad"]};
    border-color: {t["bad"]}; font-weight: 600; }}
QPushButton[danger="true"]:disabled {{ color: {t["disabled"]}; border-color: {t["sep"]};
    background: {t["surface_alt"]}; font-weight: 400; }}
QPushButton[pathcard="true"] {{ text-align: left; padding: 10px 14px; border-radius: 10px;
    background: {t["surface_alt"]}; border: 1px solid {t["sep"]}; font-weight: 600; }}
QPushButton[pathcard="true"]:hover {{ background: {t["accent_soft"]};
    border-color: {t["accent"]}; }}

QToolButton {{ background: transparent; border: 1px solid transparent;
    border-radius: 7px; padding: 3px 6px; min-height: 18px; }}
QToolButton:hover {{ background: {t["hover"]}; }}
QToolButton:checked {{ background: {t["accent_soft"]}; color: {t["accent_ink"]}; }}
QToolButton:disabled {{ color: {t["disabled"]}; }}
QToolButton::menu-indicator {{ subcontrol-position: bottom right; }}
QToolButton[toolicon="true"] {{ min-width: 22px; min-height: 22px; padding: 3px;
    border-radius: 7px; }}
QPushButton:focus, QToolButton:focus {{ border: 1px solid {t["accent"]}; }}
QWidget[panel="true"] {{ background: {t["surface_alt"]}; }}
QWidget[sidebar="true"] {{ background: {sidebar}; }}
QWidget[sidebar="true"] QLabel {{ background: transparent; }}
QToolButton[sidebarrow="true"] {{ text-align: left; padding: 5px 8px; border-radius: 6px;
    color: {t["text"]}; }}
QToolButton[sidebarrow="true"]:hover, QToolButton[sidebarrow="true"]:focus {{
    background: {t["hover"]}; border: 1px solid transparent; }}
QToolButton[sidebarrow="true"][accent="true"] {{ font-weight: 600; }}
QWidget[subviewbar="true"] {{ background: {t["bg"]}; border-bottom: 1px solid {t["sep"]}; }}
QLabel[role="panel-title"] {{ font-size: 13px; font-weight: 600; }}
QTreeWidget[measurements="true"], QListWidget[sidebarlist="true"] {{ border: none;
    border-radius: 0; background: transparent; }}
QTreeWidget[measurements="true"]::item {{ min-height: 26px; padding: 2px 4px;
    border-radius: 0; }}
QTreeWidget[measurements="true"]::item:first {{ border-top-left-radius: 6px;
    border-bottom-left-radius: 6px; }}
QTreeWidget[measurements="true"]::item:last {{ border-top-right-radius: 6px;
    border-bottom-right-radius: 6px; }}
QTreeWidget[measurements="true"]::item:only-one {{ border-radius: 6px; }}
QTreeWidget[measurements="true"]::item:hover {{ background: {t["hover"]}; }}
QTreeWidget[measurements="true"]::item:selected {{ background: {t["sel_sidebar"]};
    color: {t["text"]}; }}
QListWidget[sidebarlist="true"]::item {{ padding: 4px 8px; border: none; border-radius: 6px; }}
QListWidget[sidebarlist="true"]::item:hover {{ background: {t["hover"]}; }}
QListWidget[sidebarlist="true"]::item:selected {{ background: {t["sel_sidebar"]};
    color: {t["text"]}; }}
QLabel[role="count"] {{ color: {t["text3"]}; font-size: 11px; }}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QPlainTextEdit, QTextEdit {{
    background: {t["surface"]}; border: 1px solid {t["border"]}; border-radius: 6px;
    padding: 3px 8px; min-height: 20px; selection-background-color: {t["accent"]};
    selection-color: {t["accent_text"]}; }}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus,
QPlainTextEdit:focus {{ border: 1px solid {t["accent"]}; }}
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled {{
    color: {t["disabled"]}; background: {t["surface_alt"]}; }}
QComboBox[missing="true"] {{ border: 1px solid {t["warn"]}; }}
QAbstractSpinBox {{ padding-right: 20px; }}
QAbstractSpinBox::up-button, QAbstractSpinBox::down-button {{ subcontrol-origin: border;
    width: 18px; border: none; background: transparent; }}
QAbstractSpinBox::up-button {{ subcontrol-position: top right; }}
QAbstractSpinBox::down-button {{ subcontrol-position: bottom right; }}
QAbstractSpinBox::up-arrow {{ {arrow_up} width: 9px; height: 9px; }}
QAbstractSpinBox::down-arrow {{ {arrow_down} width: 9px; height: 9px; }}
QComboBox {{ padding-right: 24px; }}
QComboBox::drop-down {{ subcontrol-origin: padding; subcontrol-position: center right;
    width: 22px; border: none; background: transparent; }}
QComboBox::down-arrow {{ {arrow_down} width: 10px; height: 10px; }}
QComboBox QAbstractItemView {{ background: {t["surface"]}; border: 1px solid {t["border"]};
    border-radius: 6px; selection-background-color: {t["accent"]};
    selection-color: {t["accent_text"]}; }}
QPlainTextEdit[report="true"] {{ background: {t["surface"]}; border: 1px solid {t["sep"]};
    border-radius: 10px; padding: 8px 12px; }}
QCheckBox {{ spacing: 6px; }}
QCheckBox:disabled {{ color: {t["disabled"]}; }}
QCheckBox::indicator, QTreeView::indicator, QListView::indicator {{ width: 14px;
    height: 14px; border: 1px solid {t["control"]}; border-radius: 4px;
    background: {t["surface"]}; }}
QCheckBox::indicator:checked, QTreeView::indicator:checked,
QListView::indicator:checked {{ background: {t["accent"]}; border-color: {t["accent"]};
    {check_image} }}
QCheckBox::indicator:disabled {{ background: {t["surface_alt"]}; border-color: {t["sep"]}; }}

QTabWidget::pane {{ background: {t["surface"]}; border: 1px solid {t["sep"]};
    border-radius: 10px; top: -1px; }}
QTabBar::tab {{ background: transparent; color: {t["muted"]}; padding: 6px 12px;
    border: none; border-bottom: 2px solid transparent; margin-right: 2px; }}
QTabBar::tab:selected {{ color: {t["text"]}; border-bottom: 2px solid {t["accent"]};
    font-weight: 600; }}
QTabBar::tab:hover:!selected {{ color: {t["text"]}; }}

QTableWidget, QTableView, QListWidget, QTreeWidget {{ background: {t["surface"]};
    alternate-background-color: {t["readout"]}; border: 1px solid {t["sep"]};
    border-radius: 8px; gridline-color: {t["sep"]};
    selection-background-color: {t["accent_soft"]}; selection-color: {t["text"]}; }}
QHeaderView::section {{ background: {t["surface"]}; color: {t["text3"]};
    font-weight: 600; font-size: 11px; border: none; border-bottom: 1px solid {t["sep"]};
    padding: 5px 8px; }}
QListWidget::item {{ padding: 8px 10px; border-bottom: 1px solid {t["sep"]}; }}
QListWidget::item:selected {{ background: {t["accent_soft"]}; color: {t["text"]}; }}
QListWidget::item:hover {{ background: {t["hover"]}; }}

QProgressBar {{ background: {t["surface_alt"]}; border: none; border-radius: 4px;
    min-height: 8px; max-height: 8px; text-align: center; color: {t["text"]}; }}
QProgressBar[phase="measure"] {{ min-height: 16px; max-height: 16px; border-radius: 8px; }}
QProgressBar::chunk {{ background: {t["accent"]}; border-radius: 4px; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {t["border"]}; border-radius: 3px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {t["control"]}; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {t["border"]}; border-radius: 3px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QStatusBar {{ background: {t["bg"]}; border-top: 1px solid {t["sep"]};
    color: {t["text3"]}; font-size: 11px; }}
QStatusBar::item {{ border: none; }}

QWidget[viewbar="true"] {{ background: {t["bg"]}; border-bottom: 1px solid {t["sep"]}; }}
QWidget[segmented="true"] {{ background: {t["surface_alt"]}; border-radius: 8px; }}
QScrollArea[viewscroll="true"], QScrollArea[viewscroll="true"] > QWidget > QWidget {{
    background: transparent; border: none; }}
QScrollArea[viewscroll="true"] QScrollBar:horizontal {{ height: 4px; margin: 0; }}
QWidget[strip="true"] {{ background: {t["surface"]}; border-top: 1px solid {t["sep"]}; }}
QWidget[strip="true"][measuring="true"] {{ border-top: 2px solid {t["bad"]}; }}
QWidget[actionbar="true"] {{ background: {t["bg"]}; border-top: 1px solid {t["sep"]}; }}
QLabel[phase="idle"] {{ color: {t["muted"]}; background: {t["surface_alt"]};
    border: 1px solid {t["sep"]}; border-radius: 10px; padding: 2px 10px; font-weight: 600; }}
QLabel[phase="measure"] {{ color: {t["on_bad"]}; background: {t["bad"]};
    border: 1px solid {t["bad"]}; border-radius: 10px; padding: 2px 10px; font-weight: 600; }}
QLabel[phase="analyze"] {{ color: {t["text"]}; background: {t["warn_soft"]};
    border: 1px solid {t["warn"]}; border-radius: 10px; padding: 2px 10px; font-weight: 600; }}
QLabel[step="done"], QLabel[step="current"] {{ color: {t["text"]}; font-weight: 600; }}
QLabel[step="todo"] {{ color: {t["muted"]}; }}
QLabel[step="locked"] {{ color: {t["disabled"]}; }}
QFrame[stepline="true"] {{ background: {t["sep"]}; border: none; }}
QFrame[stepline="true"][done="true"] {{ background: {t["accent"]}; }}
QToolButton[viewtab="true"] {{ background: transparent; color: {t["muted"]}; border: none;
    border-radius: 6px; padding: 3px 7px; margin: 2px 1px; font-size: 12px;
    font-weight: 500; }}
QToolButton[viewtab="true"]:hover {{ color: {t["text"]}; background: {t["hover"]}; }}
QToolButton[viewtab="true"]:checked {{ color: {t["text"]}; font-weight: 600;
    background: {t["surface"]}; border: 1px solid {t["sep"]}; }}
QToolButton[panelswitch="true"] {{ background: transparent; border: none;
    padding: 4px; color: {t["muted"]}; border-radius: 7px; }}
QToolButton[panelswitch="true"]:hover {{ background: {t["hover"]}; }}
QToolButton[panelswitch="true"]:checked {{ color: {t["accent_ink"]};
    background: {t["accent_soft"]}; }}
QToolButton[projecttab="true"] {{ margin-left: 4px; }}
QToolButton[panelswitch="true"]::menu-indicator {{ image: none; width: 0; }}
QSplitter::handle {{ background: {t["sep"]}; }}
QSplitter::handle:horizontal {{ width: 1px; }}
QSplitter::handle:vertical {{ height: 1px; }}
QSplitter::handle:hover {{ background: {t["accent"]}; }}
"""


def _check_image(color: str) -> str | None:
    """A Lucide check mark in ``color`` for ticked check boxes, as a PNG file
    (style sheets take indicator images only as files)."""
    import tempfile
    from pathlib import Path

    try:
        from PySide6.QtGui import QGuiApplication
    except ImportError:
        return None
    if QGuiApplication.instance() is None:
        return None
    from reverbscope.ui.icons import pixmap

    folder = Path(tempfile.gettempdir()) / "reverbscope-theme"
    path = folder / f"check-{color.lstrip('#')}.png"
    if not path.is_file():
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except OSError:
            return None
        image = pixmap("check", color, 14, 4.0)
        if not image.save(str(path), "PNG"):
            return None
    return path.as_posix()


def _arrow_images(color: str) -> tuple[str, str] | None:
    """Up / down chevrons in ``color`` for spin and combo boxes, as PNG files.

    Qt style sheets take arrow images only as files (no CSS triangles), so
    they are drawn once per colour into the temporary directory. Without a
    running QGuiApplication the style keeps its own arrows.
    """
    import tempfile
    from pathlib import Path

    try:
        from PySide6.QtCore import QPointF, Qt
        from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPen, QPixmap
    except ImportError:
        return None
    if QGuiApplication.instance() is None:
        return None
    folder = Path(tempfile.gettempdir()) / "reverbscope-theme"
    try:
        folder.mkdir(parents=True, exist_ok=True)
    except OSError:
        return None
    paths: list[str] = []
    for direction in ("up", "down"):
        path = folder / f"chevron-{direction}-{color.lstrip('#')}.png"
        if not path.is_file():
            size = 36  # drawn at 4x and scaled down by the style for crisp edges
            pixmap = QPixmap(size, size)
            pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            pen = QPen(QColor(color), 4.5)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            top, bottom = (24.0, 12.0) if direction == "up" else (12.0, 24.0)
            painter.drawPolyline([QPointF(8.0, top), QPointF(18.0, bottom), QPointF(28.0, top)])
            painter.end()
            if not pixmap.save(str(path), "PNG"):
                return None
        paths.append(path.as_posix())
    return paths[0], paths[1]


def install_cjk_ui_font(app: Any) -> None:
    """Keep the platform UI font, and fall back per glyph to a Chinese face.

    Qt's fontconfig fallback usually does this already. A style sheet that
    names one family, or a machine whose fallback list has no Chinese, does
    not: labels then draw empty boxes. ``QFont.setFamilies`` asks for the
    next face only for a glyph the first one lacks.
    """
    from PySide6.QtGui import QFontDatabase

    font = app.font()
    installed = set(QFontDatabase.families())
    primary = font.family()
    families = [primary] if primary else []
    if sys.platform.startswith("linux"):
        # macOS and Windows keep their system UI font (SF Pro, Segoe UI); a
        # Linux desktop often defaults to DejaVu Sans, so a humanist face
        # with Chinese glyphs goes first when one is installed (SPEC §3,
        # nothing is bundled).
        preferred = [name for name in LINUX_UI_FONTS if name in installed]
        if preferred:
            families = [*preferred[:1], *(f for f in families if f != preferred[0])]
    for name in CJK_FALLBACK_FONTS:
        if name in installed and name not in families:
            families.append(name)
    if len(families) > 1:
        font.setFamilies(families)
    font.setPixelSize(13)
    app.setFont(font)


def apply_report_font(widget: Any) -> None:
    """Monospace for a report, with a Chinese face for the glyphs it lacks.

    A style sheet ``font-family`` picks one face for the whole widget, so a
    Latin monospace font draws Chinese as empty boxes. Set the families on
    the widget instead, and do not override them from the style sheet.
    """
    from PySide6.QtGui import QFont, QFontDatabase

    installed = set(QFontDatabase.families())
    cjk_mono = (
        "Sarasa Mono SC",
        "Noto Sans Mono CJK SC",
        "Noto Sans Mono CJK JP",
        "Source Han Mono SC",
    )
    latin_mono = ("DejaVu Sans Mono", "Menlo", "Consolas", "Liberation Mono")
    families = [name for name in (*cjk_mono, *latin_mono) if name in installed]
    families.extend(
        name for name in CJK_FALLBACK_FONTS if name in installed and name not in families
    )
    font = QFont()
    font.setStyleHint(QFont.StyleHint.Monospace)
    if families:
        font.setFamilies(families)
    font.setPixelSize(13)
    widget.setFont(font)


def apply_application_chrome(app: Any) -> None:
    """Give the whole application ReverbScope's look in the current colour scheme.

    Fusion is used on every platform so that the style sheet renders the same
    on Windows, macOS and Linux; the palette carries the tokens for the parts
    a style sheet does not reach (native dialogs keep the system look).
    """
    from PySide6.QtGui import QColor, QPalette
    from PySide6.QtWidgets import QStyleFactory

    styles = QStyleFactory.keys()
    if "Fusion" in styles:
        app.setStyle("Fusion")
    t = tokens()
    palette = QPalette()
    roles = QPalette.ColorRole
    palette.setColor(roles.Window, QColor(t["bg"]))
    palette.setColor(roles.WindowText, QColor(t["text"]))
    palette.setColor(roles.Base, QColor(t["surface"]))
    palette.setColor(roles.AlternateBase, QColor(t["surface_alt"]))
    palette.setColor(roles.Text, QColor(t["text"]))
    palette.setColor(roles.Button, QColor(t["surface"]))
    palette.setColor(roles.ButtonText, QColor(t["text"]))
    palette.setColor(roles.ToolTipBase, QColor(t["surface"]))
    palette.setColor(roles.ToolTipText, QColor(t["text"]))
    palette.setColor(roles.Highlight, QColor(t["accent"]))
    palette.setColor(roles.HighlightedText, QColor(t["accent_text"]))
    palette.setColor(roles.PlaceholderText, QColor(t["muted"]))
    palette.setColor(roles.Link, QColor(t["accent"]))
    app.setPalette(palette)
    app.setStyleSheet(stylesheet(t))
    install_cjk_ui_font(app)
    configure_matplotlib()
