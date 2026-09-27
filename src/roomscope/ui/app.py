"""Application entry point for the GUI."""

from __future__ import annotations

import os
import sys


def run_app(argv: list[str] | None = None, *, smoke: bool = False) -> int:
    from PySide6.QtCore import QLocale, Qt
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtWidgets import QApplication

    from roomscope.i18n import activate
    from roomscope.ui.main_window import MainWindow
    from roomscope.ui.theme import apply_application_chrome

    if smoke:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication.instance() or QApplication(argv if argv is not None else sys.argv)
    # --lang, settings and ROOMSCOPE_LANG first; then the locale variables, and
    # the desktop's UI languages when none is set (a Finder launch on macOS).
    activate(None, system_languages=QLocale.system().uiLanguages())
    QGuiApplication.setDesktopFileName("roomscope")
    apply_application_chrome(app)
    from roomscope.ui.widgets import app_icon

    QApplication.setWindowIcon(app_icon())
    window = MainWindow()
    window.show()
    if smoke:
        app.processEvents()
        window.close()
        return 0
    return int(app.exec())


def main() -> None:
    raise SystemExit(run_app())
