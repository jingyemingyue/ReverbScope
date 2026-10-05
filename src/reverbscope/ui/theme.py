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
#: Both schemes keep body text above WCAG AA contrast on their surfaces.
LIGHT_TOKENS: dict[str, str] = {
    "bg": "#f3f5f8",
    "surface": "#ffffff",
    "surface_alt": "#eef2f6",
    "border": "#d9dfe6",
    "text": "#1b2430",
    "muted": "#5a6676",
    "accent": "#177e89",
    "accent_hover": "#12656e",
    "accent_text": "#ffffff",
    "accent_soft": "#e1f1f3",
    "good": "#2e7d32",
    "good_soft": "#e5f3e7",
    "warn": "#a35a00",
    "warn_soft": "#fdf0dc",
    "bad": "#c62828",
    "bad_soft": "#fbe7e7",
    "info": "#1f5fa8",
    "info_soft": "#e4eefa",
    "grid": "#d5dbe2",
}
DARK_TOKENS: dict[str, str] = {
    "bg": "#14181d",
    "surface": "#1c2229",
    "surface_alt": "#232a32",
    "border": "#313a45",
    "text": "#e6eaef",
    "muted": "#9aa6b4",
    "accent": "#4fb6c3",
    "accent_hover": "#6cc6d1",
    "accent_text": "#0d1216",
    "accent_soft": "#1b3a40",
    "good": "#6cc070",
    "good_soft": "#1d3322",
    "warn": "#f0b35a",
    "warn_soft": "#3a2e1a",
    "bad": "#ef6a6a",
    "bad_soft": "#3d2020",
    "info": "#7fb2ee",
    "info_soft": "#1c2c40",
    "grid": "#3a444f",
}
#: Series colours for plots, in drawing order; distinct in both schemes and
#: paired with line styles so they survive greyscale printing.
PLOT_SERIES = ("#177e89", "#e07a2e", "#7a5cc7", "#3f9c4a", "#c2437a", "#8a8f98")

_DARK = {
    "bg": DARK_TOKENS["surface"],
    "fg": DARK_TOKENS["text"],
    "grid": DARK_TOKENS["grid"],
    "muted": DARK_TOKENS["muted"],
}
_LIGHT = {
    "bg": LIGHT_TOKENS["surface"],
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
    ``hint``), ``card`` on frames, ``primary`` on buttons, ``tone`` on chips.
    """
    t = t or tokens()
    images = _arrow_images(t["muted"])
    arrow_up = f'image: url("{images[0]}");' if images else ""
    arrow_down = f'image: url("{images[1]}");' if images else ""
    return f"""
QWidget {{ color: {t["text"]}; }}
QMainWindow, QStackedWidget, QScrollArea, QScrollArea > QWidget > QWidget,
QWidget[page="true"] {{ background: {t["bg"]}; }}
QMenuBar {{ background: {t["surface"]}; border-bottom: 1px solid {t["border"]}; }}
QMenuBar::item {{ padding: 4px 10px; background: transparent; }}
QMenuBar::item:selected {{ background: {t["accent_soft"]}; border-radius: 4px; }}
QMenu {{ background: {t["surface"]}; border: 1px solid {t["border"]}; padding: 4px; }}
QMenu::item {{ padding: 5px 22px 5px 14px; border-radius: 4px; }}
QMenu::item:selected {{ background: {t["accent_soft"]}; color: {t["text"]}; }}
QStatusBar {{ background: {t["surface"]}; color: {t["muted"]}; border-top: 1px solid {t["border"]}; }}
QStatusBar::item {{ border: none; }}
QToolTip {{ background: {t["surface"]}; color: {t["text"]}; border: 1px solid {t["border"]};
    padding: 4px 6px; }}

QLabel[role="title"] {{ font-size: 24px; font-weight: 700; }}
QLabel[role="page-title"] {{ font-size: 19px; font-weight: 700; }}
QLabel[role="subtitle"] {{ color: {t["muted"]}; font-size: 13px; }}
QLabel[role="section"] {{ color: {t["muted"]}; font-size: 12px; font-weight: 700; }}
QLabel[role="hint"] {{ color: {t["muted"]}; }}
QLabel[role="kpi-label"] {{ color: {t["muted"]}; font-size: 11px; font-weight: 600; }}
QLabel[role="kpi-value"] {{ font-size: 22px; font-weight: 700; }}
QLabel[role="kpi-sub"] {{ color: {t["muted"]}; font-size: 11px; }}
QLabel[role="card-title"] {{ font-size: 15px; font-weight: 700; }}
QLabel[role="badge"] {{ background: {t["accent"]}; color: {t["accent_text"]};
    border-radius: 11px; min-width: 22px; min-height: 22px; max-height: 22px;
    padding: 0 7px; font-size: 12px; font-weight: 700;
    qproperty-alignment: AlignCenter; }}
QLabel[role="pill"] {{ background: {t["accent_soft"]}; color: {t["text"]};
    border: 1px solid {t["accent_soft"]}; border-radius: 11px; padding: 3px 10px;
    font-size: 12px; }}

QFrame[card="true"], QGroupBox {{ background: {t["surface"]}; border: 1px solid {t["border"]};
    border-radius: 10px; }}
QFrame[card="true"][hover="true"]:hover {{ border: 1px solid {t["accent"]};
    background: {t["accent_soft"]}; }}
QLabel[banner="warn"] {{ background: {t["warn_soft"]}; border: 1px solid {t["warn"]};
    border-radius: 8px; padding: 8px 12px; }}
QLabel[banner="info"] {{ background: {t["info_soft"]}; border: 1px solid {t["info"]};
    border-radius: 8px; padding: 8px 12px; }}
QGroupBox {{ margin-top: 14px; padding: 18px 14px 12px 14px; font-weight: 600; }}
QGroupBox::title {{ subcontrol-origin: margin; subcontrol-position: top left; left: 12px;
    top: 2px; padding: 0 6px; color: {t["text"]}; background: transparent; }}
QGroupBox QGroupBox {{ background: {t["surface_alt"]}; border-radius: 8px; }}

QPushButton {{ background: {t["surface"]}; border: 1px solid {t["border"]}; border-radius: 6px;
    padding: 6px 14px; min-height: 18px; }}
QPushButton:hover {{ border-color: {t["accent"]}; background: {t["accent_soft"]}; }}
QPushButton:pressed {{ background: {t["surface_alt"]}; }}
QPushButton:disabled {{ color: {t["muted"]}; background: {t["surface_alt"]}; }}
QPushButton[primary="true"] {{ background: {t["accent"]}; color: {t["accent_text"]};
    border: 1px solid {t["accent"]}; font-weight: 600; }}
QPushButton[primary="true"]:hover {{ background: {t["accent_hover"]};
    border-color: {t["accent_hover"]}; }}
QPushButton[primary="true"]:disabled {{ background: {t["border"]}; border-color: {t["border"]};
    color: {t["muted"]}; }}
QPushButton[danger="true"] {{ color: {t["bad"]}; border-color: {t["bad"]}; }}

QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QPlainTextEdit, QTextEdit {{
    background: {t["surface"]}; border: 1px solid {t["border"]}; border-radius: 6px;
    padding: 4px 8px; selection-background-color: {t["accent"]};
    selection-color: {t["accent_text"]}; }}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus,
QPlainTextEdit:focus {{ border: 1px solid {t["accent"]}; }}
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled {{
    color: {t["muted"]}; background: {t["surface_alt"]}; }}
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
    selection-background-color: {t["accent_soft"]}; selection-color: {t["text"]}; }}
QPlainTextEdit[report="true"] {{ background: {t["surface_alt"]}; }}
QCheckBox::indicator:checked {{ background: {t["accent"]}; border: 1px solid {t["accent"]};
    border-radius: 3px; }}

QTabWidget::pane {{ background: {t["surface"]}; border: 1px solid {t["border"]};
    border-radius: 10px; top: -1px; }}
QTabBar::tab {{ background: transparent; color: {t["muted"]}; padding: 8px 14px;
    border: none; border-bottom: 2px solid transparent; margin-right: 2px; }}
QTabBar::tab:selected {{ color: {t["text"]}; border-bottom: 2px solid {t["accent"]};
    font-weight: 600; }}
QTabBar::tab:hover:!selected {{ color: {t["text"]}; }}

QTableWidget, QTableView, QListWidget {{ background: {t["surface"]};
    alternate-background-color: {t["surface_alt"]}; border: 1px solid {t["border"]};
    border-radius: 8px; gridline-color: {t["border"]};
    selection-background-color: {t["accent_soft"]}; selection-color: {t["text"]}; }}
QHeaderView::section {{ background: {t["surface_alt"]}; color: {t["muted"]};
    font-weight: 600; border: none; border-bottom: 1px solid {t["border"]};
    padding: 6px 8px; }}
QListWidget::item {{ padding: 8px 10px; border-bottom: 1px solid {t["surface_alt"]}; }}
QListWidget::item:selected {{ background: {t["accent_soft"]}; color: {t["text"]}; }}
QListWidget::item:hover {{ background: {t["surface_alt"]}; }}

QProgressBar {{ background: {t["surface_alt"]}; border: none; border-radius: 4px;
    min-height: 8px; max-height: 8px; text-align: center; }}
QProgressBar::chunk {{ background: {t["accent"]}; border-radius: 4px; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {t["border"]}; border-radius: 4px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {t["muted"]}; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {t["border"]}; border-radius: 4px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QStatusBar {{ background: {t["surface"]}; border-top: 1px solid {t["border"]};
    color: {t["muted"]}; }}
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
