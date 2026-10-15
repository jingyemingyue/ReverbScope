"""GUI and plot chrome that follows the system colour scheme.

ARCHITECTURE_V1.md §5.8 asks for system dark mode and for plots that stay
readable when colour is not available. Matplotlib does not follow Qt on its
own; these helpers restyle figures after they are drawn. ``REVERBSCOPE_COLOR_SCHEME``
overrides the system for tests (``dark`` or ``light``).
"""

from __future__ import annotations

import functools
import os
from typing import Any

from matplotlib.figure import Figure

ENV_COLOR_SCHEME = "REVERBSCOPE_COLOR_SCHEME"

#: Design tokens. One accent (a measured "scope" teal), neutral surfaces, and
#: one tone per validity / severity so a number's trust level reads at a glance.
#: ``plot_bg`` is the "screen" of a graph: darker (or whiter) than the panel
#: around it, as on a measurement instrument, so the trace is what the eye
#: lands on. Both schemes keep body text above WCAG AA contrast on their surfaces.
LIGHT_TOKENS: dict[str, str] = {
    "bg": "#e9edf1",
    "surface": "#f8fafb",
    "surface_alt": "#eef2f5",
    "border": "#d3dae1",
    "border_strong": "#b9c3cd",
    "nav": "#dde3e9",
    "text": "#18212b",
    "muted": "#56626f",
    "accent": "#0f7a87",
    "accent_hover": "#0b636e",
    "accent_text": "#ffffff",
    "accent_soft": "#d9eef1",
    "good": "#2a7a30",
    "good_soft": "#e1f1e3",
    "warn": "#9a5600",
    "warn_soft": "#fbeed7",
    "bad": "#c02626",
    "bad_soft": "#f9e1e1",
    "info": "#1d5ba3",
    "info_soft": "#e0ebf8",
    "grid": "#cdd5dd",
    "plot_bg": "#ffffff",
}
DARK_TOKENS: dict[str, str] = {
    "bg": "#0d1014",
    "surface": "#14181e",
    "surface_alt": "#1a2027",
    "border": "#262d36",
    "border_strong": "#38424e",
    "nav": "#0a0c10",
    "text": "#dde3ea",
    "muted": "#8996a5",
    "accent": "#3fbccb",
    "accent_hover": "#63cdda",
    "accent_text": "#041014",
    "accent_soft": "#11303a",
    "good": "#62cf83",
    "good_soft": "#16301f",
    "warn": "#f0b050",
    "warn_soft": "#352a14",
    "bad": "#f26e6e",
    "bad_soft": "#38191b",
    "info": "#78acee",
    "info_soft": "#16273b",
    "grid": "#222a33",
    "plot_bg": "#090b0f",
}
#: Series colours for plots, in drawing order; distinct in both schemes and
#: paired with line styles so they survive greyscale printing.
PLOT_SERIES = ("#17a2b4", "#e8892f", "#8d6ee0", "#3fa653", "#d24b86", "#8a929c")
#: The same series lifted for the dark screen (a 1.5 px trace needs more light
#: on near-black than on white to keep its contrast).
PLOT_SERIES_DARK = ("#3fd0e2", "#f5a04e", "#b095f5", "#6fd88a", "#ee74a8", "#a2acb8")

_DARK = {
    "bg": DARK_TOKENS["surface"],
    "screen": DARK_TOKENS["plot_bg"],
    "fg": DARK_TOKENS["text"],
    "grid": DARK_TOKENS["grid"],
    "muted": DARK_TOKENS["muted"],
}
_LIGHT = {
    "bg": LIGHT_TOKENS["surface"],
    "screen": LIGHT_TOKENS["plot_bg"],
    "fg": LIGHT_TOKENS["text"],
    "grid": LIGHT_TOKENS["grid"],
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


def series_colors() -> tuple[str, ...]:
    """Trace colours for the colour scheme in force (lifted on the dark screen)."""
    return PLOT_SERIES_DARK if color_scheme() == "dark" else PLOT_SERIES


def style_figure(fig: Figure) -> None:
    """Recolour a drawn figure as a measurement screen.

    The figure itself takes the panel colour; every axes becomes a "screen"
    (``plot_bg``) with a hairline frame, a quiet grid and small muted ticks.
    The title is left-aligned and quiet, so the trace carries the eye.
    """
    colors = plot_colors()
    panel, screen = colors["bg"], colors["screen"]
    fg, grid, muted = colors["fg"], colors["grid"], colors["muted"]
    fig.patch.set_facecolor(panel)
    for ax in fig.get_axes():
        ax.set_facecolor(screen)
        ax.tick_params(colors=muted, which="both", labelcolor=muted, length=3, width=0.6)
        ax.xaxis.label.set_color(muted)
        ax.yaxis.label.set_color(muted)
        for name in ("title", "_left_title", "_right_title"):
            title = getattr(ax, name, None)
            if title is not None:
                title.set_color(fg)
        for spine in ax.spines.values():
            spine.set_color(grid)
            spine.set_linewidth(0.8)
        for line in (*ax.get_xgridlines(), *ax.get_ygridlines()):
            line.set_color(grid)
            line.set_alpha(0.9)
        # Minor grid lines (log-frequency axes) keep matplotlib's light grey
        # unless they are recoloured too; they stay fainter than the major ones.
        for axis in (ax.xaxis, ax.yaxis):
            for tick in axis.get_minor_ticks():
                tick.gridline.set_color(grid)
                tick.gridline.set_alpha(0.4)
        for text in ax.texts:
            text.set_color(fg)
        zaxis = getattr(ax, "zaxis", None)
        if zaxis is not None:
            ax.set_facecolor(panel)
            zaxis.label.set_color(fg)
            zaxis.set_tick_params(colors=fg)
            for name in ("xaxis", "yaxis", "zaxis"):
                pane = getattr(getattr(ax, name), "pane", None)
                if pane is not None:
                    pane.set_facecolor(panel)
                    pane.set_edgecolor(muted)
        legend = ax.get_legend()
        if legend is not None:
            frame = legend.get_frame()
            frame.set_facecolor(panel)
            frame.set_edgecolor(grid)
            frame.set_alpha(0.92)
            for text in legend.get_texts():
                text.set_color(fg)


def tokens() -> dict[str, str]:
    """The design tokens of the current colour scheme."""
    return dict(DARK_TOKENS if color_scheme() == "dark" else LIGHT_TOKENS)


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

    rcParams["axes.prop_cycle"] = cycler(color=list(series_colors()))
    rcParams["axes.spines.top"] = False
    rcParams["axes.spines.right"] = False
    rcParams["axes.titlesize"] = 10
    rcParams["axes.titleweight"] = "bold"
    rcParams["axes.titlelocation"] = "left"
    rcParams["axes.titlepad"] = 8
    rcParams["axes.labelsize"] = 9
    rcParams["axes.axisbelow"] = True
    rcParams["xtick.labelsize"] = 8.5
    rcParams["ytick.labelsize"] = 8.5
    rcParams["legend.fontsize"] = 8.5
    rcParams["legend.frameon"] = True
    rcParams["legend.fancybox"] = False
    rcParams["grid.linewidth"] = 0.6
    rcParams["lines.linewidth"] = 1.4
    rcParams["lines.solid_capstyle"] = "round"
    rcParams["figure.facecolor"] = plot_colors()["bg"]


def stylesheet(t: dict[str, str] | None = None) -> str:
    """The Qt style sheet for the tokens ``t`` (default: the current scheme).

    Widgets opt into roles with dynamic properties: ``role`` on labels
    (``title``, ``subtitle``, ``section``, ``kpi-value``, ``kpi-label``,
    ``hint``), ``card`` and ``panel`` on frames, ``primary`` on buttons,
    ``nav`` on the navigation rail's buttons, ``tone`` on chips.
    """
    t = t or tokens()
    images = _arrow_images(t["muted"])
    arrow_up = f'image: url("{images[0]}");' if images else ""
    arrow_down = f'image: url("{images[1]}");' if images else ""
    return f"""
QWidget {{ color: {t["text"]}; font-size: 12px; }}
QMainWindow, QStackedWidget, QScrollArea, QScrollArea > QWidget > QWidget,
QWidget[page="true"] {{ background: {t["bg"]}; }}
QMenuBar {{ background: {t["surface"]}; border-bottom: 1px solid {t["border"]}; padding: 1px 4px; }}
QMenuBar::item {{ padding: 4px 10px; background: transparent; border-radius: 3px; }}
QMenuBar::item:selected {{ background: {t["accent_soft"]}; }}
QMenu {{ background: {t["surface"]}; border: 1px solid {t["border_strong"]}; padding: 4px; }}
QMenu::item {{ padding: 5px 24px 5px 14px; border-radius: 3px; }}
QMenu::item:selected {{ background: {t["accent_soft"]}; color: {t["text"]}; }}
QMenu::item:disabled {{ color: {t["muted"]}; }}
QMenu::separator {{ height: 1px; background: {t["border"]}; margin: 4px 6px; }}
QStatusBar {{ background: {t["nav"]}; color: {t["muted"]}; border-top: 1px solid {t["border"]};
    font-size: 11px; }}
QStatusBar::item {{ border: none; }}
QStatusBar QLabel {{ color: {t["muted"]}; font-size: 11px; padding: 0 8px; }}
QToolTip {{ background: {t["surface_alt"]}; color: {t["text"]}; border: 1px solid {t["border_strong"]};
    padding: 4px 6px; }}

QLabel[role="title"] {{ font-size: 22px; font-weight: 700; }}
QLabel[role="page-title"] {{ font-size: 16px; font-weight: 700; }}
QLabel[role="subtitle"] {{ color: {t["muted"]}; font-size: 12px; }}
QLabel[role="section"] {{ color: {t["muted"]}; font-size: 10px; font-weight: 700; }}
QLabel[role="hint"] {{ color: {t["muted"]}; }}
QLabel[role="kpi-label"] {{ color: {t["muted"]}; font-size: 10px; font-weight: 700; }}
QLabel[role="kpi-value"] {{ font-size: 22px; font-weight: 700; }}
QLabel[role="kpi-sub"] {{ color: {t["muted"]}; font-size: 11px; }}
QLabel[role="card-title"] {{ font-size: 14px; font-weight: 700; }}
QLabel[role="readout"] {{ color: {t["text"]}; font-size: 12px; }}
QLabel[role="readout-key"] {{ color: {t["muted"]}; font-size: 11px; }}
QLabel[role="badge"] {{ background: {t["accent"]}; color: {t["accent_text"]};
    border-radius: 3px; min-width: 22px; min-height: 22px; max-height: 22px;
    padding: 0 6px; font-size: 11px; font-weight: 700;
    qproperty-alignment: AlignCenter; }}
QLabel[role="pill"] {{ background: {t["accent_soft"]}; color: {t["text"]};
    border: 1px solid {t["accent_soft"]}; border-radius: 3px; padding: 2px 8px;
    font-size: 11px; }}

QFrame[card="true"], QGroupBox {{ background: {t["surface"]}; border: 1px solid {t["border"]};
    border-radius: 6px; }}
QFrame[card="true"][hover="true"]:hover {{ border: 1px solid {t["accent"]};
    background: {t["accent_soft"]}; }}
QFrame[panel="true"] {{ background: {t["surface"]}; border: 1px solid {t["border"]};
    border-radius: 0; }}
QFrame[panelHeader="true"] {{ background: {t["surface_alt"]}; border: none;
    border-bottom: 1px solid {t["border"]}; border-radius: 0; }}
QFrame[toolbar="true"] {{ background: {t["surface"]}; border: none;
    border-bottom: 1px solid {t["border"]}; border-radius: 0; }}
QFrame[readout="true"] {{ background: {t["surface_alt"]}; border: none;
    border-top: 1px solid {t["border"]}; border-radius: 0; }}
QLabel[banner="warn"] {{ background: {t["warn_soft"]}; border: 1px solid {t["warn"]};
    border-radius: 4px; padding: 6px 10px; }}
QLabel[banner="info"] {{ background: {t["info_soft"]}; border: 1px solid {t["info"]};
    border-radius: 4px; padding: 6px 10px; }}
QGroupBox {{ margin-top: 12px; padding: 14px 12px 10px 12px; font-weight: 600; }}
QGroupBox::title {{ subcontrol-origin: margin; subcontrol-position: top left; left: 10px;
    top: 0px; padding: 0 6px; color: {t["muted"]}; background: transparent;
    font-size: 11px; font-weight: 700; }}
QGroupBox QGroupBox {{ background: {t["surface_alt"]}; border-radius: 4px; }}

QFrame#navRail {{ background: {t["nav"]}; border: none; border-right: 1px solid {t["border"]}; }}
QToolButton[nav="true"] {{ background: transparent; color: {t["muted"]}; border: none;
    border-left: 3px solid transparent; border-radius: 0; padding: 9px 2px 7px 2px;
    font-size: 10px; font-weight: 600; min-width: 64px; }}
QToolButton[nav="true"]:hover {{ color: {t["text"]}; background: {t["surface_alt"]}; }}
QToolButton[nav="true"]:checked {{ color: {t["text"]}; background: {t["surface"]};
    border-left: 3px solid {t["accent"]}; }}
QToolButton[nav="true"]:disabled {{ color: {t["border_strong"]}; }}
QToolButton[plotTool="true"] {{ background: transparent; color: {t["muted"]}; border: 1px solid transparent;
    border-radius: 3px; padding: 3px 7px; font-size: 11px; font-weight: 600; }}
QToolButton[plotTool="true"]:hover {{ color: {t["text"]}; border-color: {t["border_strong"]};
    background: {t["surface_alt"]}; }}
QToolButton[plotTool="true"]:checked {{ color: {t["accent"]}; border-color: {t["accent"]};
    background: {t["accent_soft"]}; }}

QPushButton {{ background: {t["surface_alt"]}; border: 1px solid {t["border_strong"]};
    border-radius: 4px; padding: 4px 12px; min-height: 18px; }}
QPushButton:hover {{ border-color: {t["accent"]}; background: {t["accent_soft"]}; }}
QPushButton:pressed {{ background: {t["surface"]}; }}
QPushButton:focus {{ border-color: {t["accent"]}; }}
QPushButton:disabled {{ color: {t["muted"]}; background: {t["surface"]}; border-color: {t["border"]}; }}
QPushButton[primary="true"] {{ background: {t["accent"]}; color: {t["accent_text"]};
    border: 1px solid {t["accent"]}; font-weight: 700; }}
QPushButton[primary="true"]:hover {{ background: {t["accent_hover"]};
    border-color: {t["accent_hover"]}; }}
QPushButton[primary="true"]:disabled {{ background: {t["border"]}; border-color: {t["border"]};
    color: {t["muted"]}; }}
QPushButton[danger="true"] {{ color: {t["bad"]}; border-color: {t["bad"]}; }}
QPushButton[segment="true"] {{ border-radius: 0; margin: 0 0 0 -1px; padding: 4px 12px;
    background: {t["surface_alt"]}; color: {t["muted"]}; font-weight: 600; }}
QPushButton[segment="true"]:hover {{ color: {t["text"]}; border-color: {t["border_strong"]};
    background: {t["surface"]}; }}
QPushButton[segment="true"]:checked {{ background: {t["accent_soft"]}; color: {t["accent"]};
    border-color: {t["accent"]}; }}
QPushButton[flat="true"] {{ background: transparent; border: 1px solid transparent; color: {t["muted"]}; }}
QPushButton[flat="true"]:hover {{ color: {t["text"]}; border-color: {t["border_strong"]};
    background: {t["surface_alt"]}; }}

QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QPlainTextEdit, QTextEdit {{
    background: {t["plot_bg"]}; border: 1px solid {t["border_strong"]}; border-radius: 3px;
    padding: 3px 7px; selection-background-color: {t["accent"]};
    selection-color: {t["accent_text"]}; }}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus,
QPlainTextEdit:focus {{ border: 1px solid {t["accent"]}; }}
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled {{
    color: {t["muted"]}; background: {t["surface_alt"]}; border-color: {t["border"]}; }}
QAbstractSpinBox {{ padding-right: 18px; }}
QAbstractSpinBox::up-button, QAbstractSpinBox::down-button {{ subcontrol-origin: border;
    width: 16px; border: none; background: transparent; }}
QAbstractSpinBox::up-button {{ subcontrol-position: top right; }}
QAbstractSpinBox::down-button {{ subcontrol-position: bottom right; }}
QAbstractSpinBox::up-arrow {{ {arrow_up} width: 8px; height: 8px; }}
QAbstractSpinBox::down-arrow {{ {arrow_down} width: 8px; height: 8px; }}
QComboBox {{ padding-right: 22px; }}
QComboBox::drop-down {{ subcontrol-origin: padding; subcontrol-position: center right;
    width: 20px; border: none; background: transparent; }}
QComboBox::down-arrow {{ {arrow_down} width: 9px; height: 9px; }}
QComboBox QAbstractItemView {{ background: {t["surface"]}; border: 1px solid {t["border_strong"]};
    selection-background-color: {t["accent_soft"]}; selection-color: {t["text"]}; outline: none; }}
QPlainTextEdit[report="true"] {{ background: {t["plot_bg"]}; }}
QCheckBox {{ spacing: 7px; }}
QCheckBox::indicator {{ width: 14px; height: 14px; border: 1px solid {t["border_strong"]};
    border-radius: 3px; background: {t["plot_bg"]}; }}
QCheckBox::indicator:checked {{ background: {t["accent"]}; border: 1px solid {t["accent"]};
    border-radius: 3px; }}

QTabWidget::pane {{ background: {t["surface"]}; border: 1px solid {t["border"]};
    border-radius: 0; top: -1px; }}
QTabBar {{ background: transparent; }}
QTabBar::tab {{ background: transparent; color: {t["muted"]}; padding: 7px 14px;
    border: none; border-bottom: 2px solid transparent; margin-right: 0; font-weight: 600; }}
QTabBar::tab:selected {{ color: {t["text"]}; border-bottom: 2px solid {t["accent"]}; }}
QTabBar::tab:hover:!selected {{ color: {t["text"]}; background: {t["surface_alt"]}; }}

QSplitter::handle {{ background: {t["border"]}; }}
QSplitter::handle:horizontal {{ width: 1px; }}
QSplitter::handle:vertical {{ height: 1px; }}
QSplitter::handle:hover {{ background: {t["accent"]}; }}

QTableWidget, QTableView, QListWidget {{ background: {t["surface"]};
    alternate-background-color: {t["surface_alt"]}; border: 1px solid {t["border"]};
    border-radius: 0; gridline-color: {t["border"]};
    selection-background-color: {t["accent_soft"]}; selection-color: {t["text"]}; outline: none; }}
QTableWidget::item {{ padding: 2px 6px; }}
QHeaderView::section {{ background: {t["surface_alt"]}; color: {t["muted"]};
    font-size: 10px; font-weight: 700; border: none; border-bottom: 1px solid {t["border_strong"]};
    padding: 5px 8px; }}
QListWidget::item {{ padding: 6px 10px; border-bottom: 1px solid {t["border"]}; }}
QListWidget::item:selected {{ background: {t["accent_soft"]}; color: {t["text"]}; }}
QListWidget::item:hover {{ background: {t["surface_alt"]}; }}

QProgressBar {{ background: {t["surface_alt"]}; border: none; border-radius: 2px;
    min-height: 6px; max-height: 6px; text-align: center; }}
QProgressBar::chunk {{ background: {t["accent"]}; border-radius: 2px; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {t["border_strong"]}; border-radius: 3px; min-height: 30px;
    margin: 1px 2px; }}
QScrollBar::handle:vertical:hover {{ background: {t["muted"]}; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 0; }}
QScrollBar::handle:horizontal {{ background: {t["border_strong"]}; border-radius: 3px; min-width: 30px;
    margin: 2px 1px; }}
QScrollBar::handle:horizontal:hover {{ background: {t["muted"]}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QDialog {{ background: {t["bg"]}; }}
"""


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
    for name in CJK_FALLBACK_FONTS:
        if name in installed and name not in families:
            families.append(name)
    if len(families) > 1:
        font.setFamilies(families)
        app.setFont(font)


def mono_families() -> list[str]:
    """The installed monospace faces, then Chinese faces for the glyphs they lack."""
    from PySide6.QtGui import QFontDatabase

    installed = set(QFontDatabase.families())
    cjk_mono = (
        "Sarasa Mono SC",
        "Noto Sans Mono CJK SC",
        "Noto Sans Mono CJK JP",
        "Source Han Mono SC",
    )
    latin_mono = (
        "SF Mono",
        "Cascadia Mono",
        "Menlo",
        "Consolas",
        "DejaVu Sans Mono",
        "Liberation Mono",
    )
    families = [name for name in (*cjk_mono, *latin_mono) if name in installed]
    families.extend(
        name for name in CJK_FALLBACK_FONTS if name in installed and name not in families
    )
    return families


def apply_mono_font(widget: Any, *, pixel_size: int = 12, bold: bool = False) -> None:
    """Monospace digits for a readout or a figure: columns of numbers line up.

    Set on the widget (not from the style sheet) so a glyph the Latin face
    lacks, such as a Chinese unit, falls back to a Chinese face instead of
    being drawn as an empty box.
    """
    from PySide6.QtGui import QFont

    font = QFont()
    font.setStyleHint(QFont.StyleHint.Monospace)
    families = mono_families()
    if families:
        font.setFamilies(families)
    font.setPixelSize(pixel_size)
    font.setBold(bold)
    widget.setFont(font)


def apply_report_font(widget: Any) -> None:
    """Monospace for a report, with a Chinese face for the glyphs it lacks.

    A style sheet ``font-family`` picks one face for the whole widget, so a
    Latin monospace font draws Chinese as empty boxes. Set the families on
    the widget instead, and do not override them from the style sheet.
    """
    apply_mono_font(widget, pixel_size=13)


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
