"""Ctrl+Return must belong to exactly one primary action per mode."""

from __future__ import annotations

import os

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QApplication

from reverbscope.ui.main_window import MainWindow

pytestmark = pytest.mark.gui


@pytest.fixture(scope="module")
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _seq(widget) -> str:  # type: ignore[no-untyped-def]
    return widget.shortcut().toString()


def test_ctrl_return_belongs_to_start_in_standalone(app: QApplication) -> None:
    window = MainWindow()
    window.show()
    window.show_mode("standalone")
    app.processEvents()
    enter = QKeySequence("Ctrl+Return").toString()
    assert _seq(window.strip.start_button) == enter
    assert _seq(window.daw.analyze_button) == ""
    window.close()


def test_ctrl_return_belongs_to_analyze_in_daw(app: QApplication) -> None:
    window = MainWindow()
    window.show()
    window.show_mode("universal_daw")
    app.processEvents()
    enter = QKeySequence("Ctrl+Return").toString()
    assert _seq(window.strip.start_button) == ""
    assert _seq(window.daw.analyze_button) == enter
    window.show_mode("standalone")
    app.processEvents()
    assert _seq(window.strip.start_button) == enter
    assert _seq(window.daw.analyze_button) == ""
    window.close()
