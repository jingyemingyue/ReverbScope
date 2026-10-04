"""Application entry point for the GUI."""

from __future__ import annotations

import logging
import os
import sys
from collections.abc import Callable
from types import TracebackType
from typing import TYPE_CHECKING

from roomscope.i18n import N_

if TYPE_CHECKING:
    from PySide6.QtCore import QCoreApplication


#: Shown instead of a traceback when PySide6 cannot be imported: the wheel
#: without the ``gui`` extra, or a Linux system without the Qt system libraries.
GUI_UNAVAILABLE = N_(
    "The desktop GUI cannot start because PySide6 could not be loaded ({error}). "
    'Install it in this Python environment with: pip install "PySide6_Essentials>=6.6". '
    "On Linux the OpenGL/EGL and XCB system libraries are also needed; see "
    "docs/INSTALLATION.md. The command-line tool works without it."
)


def pyside6_import_error() -> str | None:
    """Why PySide6 cannot be imported, or ``None`` when the GUI can start."""
    try:
        import PySide6.QtWidgets  # noqa: F401
    except ImportError as exc:
        return str(exc)
    return None


def run_app(argv: list[str] | None = None, *, smoke: bool = False, lang: str | None = None) -> int:
    """Start the desktop app; ``lang`` is ``roomscope --lang`` (else settings, then the system)."""
    from PySide6.QtCore import QLocale, Qt
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtWidgets import QApplication

    from roomscope.i18n import activate
    from roomscope.logging_config import configure_logging
    from roomscope.ui.main_window import MainWindow
    from roomscope.ui.theme import apply_application_chrome

    # Warnings and unexpected failures go to $ROOMSCOPE_HOME/roomscope.log.
    # The desktop launcher does not pass through the command line, which is
    # where logging would otherwise be configured.
    configure_logging(logging.WARNING)
    if smoke:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication.instance() or QApplication(argv if argv is not None else sys.argv)
    # --lang, settings and ROOMSCOPE_LANG first; then the locale variables, and
    # the desktop's UI languages when none is set (a Finder launch on macOS).
    activate(lang or None, system_languages=QLocale.system().uiLanguages())
    install_qt_translations(app)
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
    previous = sys.excepthook
    sys.excepthook = _gui_excepthook(previous)
    try:
        return int(app.exec())
    finally:
        sys.excepthook = previous


_Hook = Callable[[type[BaseException], BaseException, TracebackType | None], object]


def _gui_excepthook(previous: _Hook) -> _Hook:
    """Show one dialog for a bug on the GUI thread, and keep the traceback in the log.

    Installed only while ``run_app`` is in its event loop, so a test that
    builds a window never gets a modal dialog from an assertion.
    """
    showing = False

    def hook(
        exc_type: type[BaseException],
        exc: BaseException,
        tb: TracebackType | None,
    ) -> None:
        nonlocal showing
        if issubclass(exc_type, (KeyboardInterrupt, SystemExit)):
            previous(exc_type, exc, tb)
            return
        logging.getLogger("roomscope.ui").error("unhandled exception", exc_info=(exc_type, exc, tb))
        if showing:
            return
        showing = True
        try:
            from PySide6.QtWidgets import QApplication

            from roomscope.ui.widgets import error_box
            from roomscope.ui.workers import gui_failure_text

            error_box(QApplication.activeWindow(), "RoomScope", gui_failure_text(exc))
        except Exception:
            previous(exc_type, exc, tb)
        finally:
            showing = False

    return hook


def install_qt_translations(app: QCoreApplication) -> None:
    """Qt's own texts (standard buttons, file and message dialogs) in the
    active language, from the ``qtbase`` catalog that ships with Qt."""
    from PySide6.QtCore import QLibraryInfo, QLocale, QTranslator

    from roomscope.i18n import DEFAULT_LANG, current_locale

    lang = current_locale()
    if lang == DEFAULT_LANG:
        return
    translator = QTranslator(app)
    folder = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    if translator.load(QLocale(lang), "qtbase", "_", folder):
        app.installTranslator(translator)


def main() -> None:
    """``roomscope-gui`` entry point of a pip install."""
    error = pyside6_import_error()
    if error is not None:
        from roomscope.i18n import _, activate

        activate(None)
        sys.stderr.write(_(GUI_UNAVAILABLE).format(error=error) + "\n")
        raise SystemExit(2)
    raise SystemExit(run_app())
