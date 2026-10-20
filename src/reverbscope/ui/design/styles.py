"""The focused desktop's widget styling, independent of measurement data.

A restrained, dense measurement-tool look: chrome in two close greys, the
chart canvas darkest, one accent for selection and the primary action, and
tone colours only where a state is meant (valid, warning, invalid). Numbers
use an installed monospace face (:data:`~reverbscope.ui.design.tokens.MONO_FAMILIES`).
"""

from __future__ import annotations

from reverbscope.ui.design.tokens import MONO_FAMILIES


def _families(names: tuple[str, ...]) -> str:
    return ", ".join(f'"{name}"' for name in names)


def desktop_styles(t: dict[str, str]) -> str:
    mono = _families(MONO_FAMILIES)
    tones = "".join(
        f"""
QFrame[notice="true"][tone="{tone}"] {{ border-left: 3px solid {t[tone]}; }}
QFrame[notice="true"][tone="{tone}"] QLabel[role="notice-mark"] {{ color: {t[tone]}; }}"""
        for tone in ("good", "info", "warn", "bad")
    )
    return f"""
QWidget {{ font-size: 13px; }}
QMainWindow, QWidget[page="true"] {{ background: {t["bg"]}; }}
QMenuBar {{ font-size: 12px; padding: 1px 4px; }}
QMenuBar::item {{ padding: 3px 9px; }}
QLabel[role="title"] {{ font-size: 21px; font-weight: 600; }}
QLabel[role="page-title"] {{ font-size: 16px; font-weight: 600; }}
QLabel[role="section"], QLabel[role="panel-title"] {{ font-size: 12px; font-weight: 600;
    color: {t["muted"]}; }}
QLabel[role="subtitle"], QLabel[role="hint"], QLabel[role="kpi-sub"] {{ font-size: 12px; }}
QLabel[role="kpi-value"] {{ font-family: {mono}; font-size: 24px; font-weight: 500; }}
QLabel[role="kpi-label"] {{ font-size: 12px; font-weight: 500; color: {t["muted"]}; }}
QLabel[role="brand"] {{ font-size: 14px; font-weight: 600; }}
QLabel[role="mono"] {{ font-family: {mono}; }}
QLabel[role="tag"] {{ color: {t["warn"]}; background: {t["warn_soft"]};
    border: 1px solid {t["warn_soft"]}; border-radius: 3px; padding: 2px 8px;
    font-size: 12px; font-weight: 500; }}
QPushButton, QToolButton {{ border-radius: 4px; padding: 4px 12px; min-height: 20px; }}
QPushButton {{ background: {t["surface_alt"]}; border: 1px solid {t["border"]}; }}
QPushButton:hover {{ background: {t["accent_soft"]}; border-color: {t["accent"]}; }}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{ min-height: 20px; padding: 3px 8px;
    border-radius: 4px; }}
QComboBox {{ padding-right: 26px; }}
QPushButton[primary="true"] {{ border-radius: 4px; padding: 4px 16px; }}

QWidget[taskbar="true"] {{ background: {t["surface"]}; border-bottom: 1px solid {t["border"]}; }}
QToolButton[task="true"] {{ border: none; border-bottom: 2px solid transparent;
    border-radius: 0; background: transparent; color: {t["muted"]}; padding: 0 14px;
    min-height: 40px; max-height: 42px; font-weight: 500; }}
QToolButton[task="true"]:hover {{ color: {t["text"]}; }}
QToolButton[task="true"]:checked {{ border-bottom: 2px solid {t["accent"]};
    color: {t["text"]}; background: transparent; font-weight: 600; }}
QToolButton[taskaction="true"] {{ color: {t["muted"]}; padding: 4px 10px; }}
QToolButton[taskaction="true"]:hover {{ color: {t["text"]}; background: {t["surface_alt"]};
    border-color: transparent; }}

QWidget[contextbar="true"] {{ background: {t["bg"]}; border-bottom: 1px solid {t["border"]}; }}
QToolButton[viewtab="true"] {{ background: transparent; color: {t["muted"]}; border: none;
    border-bottom: 2px solid transparent; border-radius: 0; padding: 0 11px;
    min-height: 34px; max-height: 36px; font-weight: 500; }}
QToolButton[viewtab="true"]:hover {{ color: {t["text"]}; background: transparent; }}
QToolButton[viewtab="true"]:checked {{ color: {t["text"]}; font-weight: 600;
    border-bottom: 2px solid {t["accent"]}; background: transparent; }}
QToolButton[viewtab="true"]:focus {{ border: none; border-bottom: 2px solid {t["accent_hover"]}; }}
QFrame[vrule="true"] {{ background: {t["border"]}; border: none; }}
QFrame[rule="true"] {{ background: {t["border"]}; border: none; margin: 2px 4px; }}
QToolButton[panelswitch="true"] {{ background: transparent; border: 1px solid transparent;
    padding: 3px 9px; color: {t["muted"]}; }}
QToolButton[panelswitch="true"]:hover {{ color: {t["text"]}; background: {t["surface_alt"]}; }}
QToolButton[panelswitch="true"]:checked {{ color: {t["text"]}; background: {t["accent_soft"]};
    border-color: {t["accent_soft"]}; }}

QWidget[toolrail="true"] {{ background: {t["surface"]}; border-right: 1px solid {t["border"]}; }}
QWidget[toolrail="true"] QToolButton {{ padding: 2px; border: 1px solid transparent; }}
QWidget[toolrail="true"] QToolButton:hover {{ background: {t["surface_alt"]};
    border-color: transparent; }}
QWidget[toolrail="true"] QToolButton:checked {{ background: {t["accent_soft"]};
    border-color: {t["accent_soft"]}; }}

QFrame[drawer="true"] {{ background: {t["surface"]}; border: none;
    border-left: 1px solid {t["border"]}; border-right: 1px solid {t["border"]}; }}
QFrame[drawer="true"] QWidget[panel="true"] {{ background: {t["surface"]}; }}
QFrame[notice="true"] {{ background: {t["surface_alt"]}; border: 1px solid {t["border"]};
    border-radius: 4px; }}
QLabel[role="notice-mark"] {{ font-size: 12px; font-weight: 700; padding-top: 1px; }}
QFrame[notice="true"] QToolButton {{ padding: 0 6px; min-height: 18px; color: {t["muted"]}; }}
{tones}

QFrame[tile="true"] {{ background: {t["surface"]}; border: 1px solid {t["border"]};
    border-radius: 6px; }}
QFrame[tile="true"]:hover {{ border-color: {t["accent"]}; }}
QFrame[tile="true"]:focus {{ border-color: {t["accent_hover"]}; }}
QFrame[tile="true"][primary="true"] {{ background: {t["accent_soft"]};
    border-color: {t["accent_soft"]}; }}
QFrame[tile="true"][primary="true"]:hover {{ border-color: {t["accent"]}; }}
QLabel[role="tile-title"] {{ font-size: 14px; font-weight: 600; }}
QLabel[role="shortcut"] {{ color: {t["muted"]}; font-family: {mono}; font-size: 11px;
    border: 1px solid {t["border"]}; border-radius: 3px; padding: 0 5px; }}
QToolButton[chartaction="true"] {{ color: {t["muted"]}; padding: 2px 8px; }}
QToolButton[chartaction="true"]:hover {{ color: {t["text"]}; background: {t["surface_alt"]};
    border-color: transparent; }}
QLabel[readout="true"] {{ font-family: {mono}; font-size: 12px; }}
QLabel[role="reason"] {{ color: {t["warn"]}; font-size: 12px; }}

QGroupBox {{ border: none; border-top: 1px solid {t["border"]}; border-radius: 0;
    margin-top: 20px; padding: 18px 0 6px 0; background: transparent; }}
QGroupBox::title {{ left: 0; padding: 0 10px 0 0; color: {t["text"]}; }}
QGroupBox QGroupBox {{ background: transparent; border: none; }}
QFrame[card="true"] {{ border: none; border-radius: 0; background: transparent; }}
QWidget[options="true"] {{ background: {t["surface"]}; border-bottom: 1px solid {t["border"]}; }}
QWidget[options="true"] QToolButton {{ padding: 3px 8px; }}
QToolButton[legend="true"], QToolButton[legend="true"]:checked {{
    background: transparent; border: 1px solid transparent; padding: 3px 8px;
    color: {t["text"]}; }}
QToolButton[legend="true"]:!checked {{ color: {t["muted"]}; }}
QToolButton[legend="true"]:hover {{ background: {t["surface_alt"]};
    border-color: {t["border"]}; }}
QToolButton[legend="true"]:focus {{ background: {t["surface_alt"]};
    border-color: {t["accent"]}; }}
QTableWidget, QTableView, QListWidget, QTreeWidget {{ border: none; border-radius: 0; }}
QHeaderView::section {{ padding: 7px 10px; font-size: 12px; font-weight: 500; }}
QTreeWidget[measurements="true"]::item {{ min-height: 26px; padding: 4px 4px; }}
QTableWidget::item {{ padding: 4px; }}
QTabWidget::pane {{ border: none; background: transparent; }}
QTabBar::tab {{ padding: 8px 16px; }}
QWidget[strip="true"] {{ background: {t["surface"]}; border-top: 1px solid {t["border"]}; }}
QPlainTextEdit[report="true"] {{ background: {t.get("canvas", t["bg"])}; border: none;
    padding: 20px; }}
QPlainTextEdit[commands="true"] {{ background: {t.get("canvas", t["bg"])};
    border: 1px solid {t["border"]}; border-radius: 4px; padding: 4px 8px;
    color: {t["muted"]}; }}
QStatusBar {{ font-size: 11px; min-height: 20px; }}
QScrollArea {{ border: none; }}
"""
