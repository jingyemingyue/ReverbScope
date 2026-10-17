"""The focused desktop's widget styling, independent of measurement data."""

from __future__ import annotations


def desktop_styles(t: dict[str, str]) -> str:
    return f"""
QWidget {{ font-size: 14px; }}
QMainWindow, QWidget[page="true"] {{ background: {t["bg"]}; }}
QLabel[role="title"] {{ font-size: 23px; font-weight: 600; }}
QLabel[role="page-title"] {{ font-size: 18px; font-weight: 600; }}
QLabel[role="section"], QLabel[role="panel-title"] {{ font-size: 13px; font-weight: 600; }}
QLabel[role="subtitle"], QLabel[role="hint"], QLabel[role="kpi-sub"] {{ font-size: 12px; }}
QLabel[role="kpi-value"] {{ font-size: 30px; font-weight: 500; }}
QLabel[role="kpi-label"] {{ font-size: 13px; font-weight: 400; }}
QLabel[role="brand"] {{ font-size: 15px; font-weight: 600; }}
QPushButton, QToolButton {{ border-radius: 3px; padding: 5px 12px; min-height: 20px; }}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{ min-height: 22px; padding: 4px 8px; }}
QComboBox {{ padding-right: 26px; }}
QPushButton[primary="true"] {{ border-radius: 3px; }}
QToolButton[task="true"] {{ border: none; border-bottom: 2px solid transparent;
    border-radius: 0; background: transparent; color: {t["muted"]}; padding: 12px 20px; }}
QToolButton[task="true"]:checked {{ border-bottom: 2px solid {t["accent"]};
    color: {t["text"]}; background: {t["surface_alt"]}; }}
QWidget[taskbar="true"] {{ background: {t["surface"]}; border-bottom: 1px solid {t["border"]}; }}
QWidget[contextbar="true"] {{ background: {t["bg"]}; border-bottom: 1px solid {t["border"]}; }}
QWidget[toolrail="true"] {{ background: {t["surface"]}; border-right: 1px solid {t["border"]}; }}
QWidget[toolrail="true"] QToolButton {{ padding: 2px; }}
QFrame[drawer="true"] {{ background: {t["surface"]}; border: 1px solid {t["border"]}; }}
QFrame[drawer="true"] QWidget[panel="true"] {{ background: {t["surface"]}; }}
QGroupBox {{ border: none; border-top: 1px solid {t["border"]}; border-radius: 0;
    margin-top: 22px; padding: 22px 0 8px 0; background: transparent; }}
QGroupBox::title {{ left: 0; padding: 0 10px 0 0; color: {t["text"]}; }}
QGroupBox QGroupBox {{ background: transparent; border: none; }}
QFrame[card="true"] {{ border: none; border-radius: 0; background: transparent; }}
QWidget[options="true"] {{ background: {t["surface"]}; border-bottom: 1px solid {t["border"]}; }}
QWidget[options="true"] QToolButton {{ padding: 4px 8px; }}
QToolButton[legend="true"], QToolButton[legend="true"]:checked {{
    background: transparent; border: 1px solid transparent; padding: 4px 8px;
    color: {t["text"]}; }}
QToolButton[legend="true"]:!checked {{ color: {t["muted"]}; }}
QToolButton[legend="true"]:hover {{ background: {t["surface_alt"]};
    border-color: {t["border"]}; }}
QToolButton[legend="true"]:focus {{ background: {t["surface_alt"]};
    border-color: {t["accent"]}; }}
QTableWidget, QTableView, QListWidget, QTreeWidget {{ border: none; border-radius: 0; }}
QHeaderView::section {{ padding: 10px 12px; font-size: 12px; font-weight: 500; }}
QTreeWidget[measurements="true"]::item {{ min-height: 28px; padding: 6px 4px; }}
QTableWidget::item {{ padding: 5px; }}
QTabWidget::pane {{ border: none; background: transparent; }}
QTabBar::tab {{ padding: 10px 18px; }}
QWidget[strip="true"] {{ background: {t["surface"]}; border-top: 1px solid {t["border"]}; }}
QPlainTextEdit[report="true"] {{ background: {t.get("canvas", t["bg"])}; border: none;
    padding: 24px; }}
QStatusBar {{ font-size: 12px; min-height: 22px; }}
QScrollArea {{ border: none; }}
"""
