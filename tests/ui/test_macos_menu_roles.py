"""macOS App menu roles for Settings / About / Quit (guidelines §18.1)."""

from __future__ import annotations

import os
import sys

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QAction
from PySide6.QtWidgets import QApplication

from reverbscope.ui.main_window import MainWindow

pytestmark = pytest.mark.gui


@pytest.fixture(scope="module")
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_settings_about_and_quit_use_mac_menu_roles(app: QApplication) -> None:
    window = MainWindow()
    roles = {
        action.menuRole(): action
        for action in window.findChildren(QAction)
        if action.menuRole()
        in {
            QAction.MenuRole.PreferencesRole,
            QAction.MenuRole.AboutRole,
            QAction.MenuRole.QuitRole,
        }
    }
    assert QAction.MenuRole.PreferencesRole in roles
    assert QAction.MenuRole.AboutRole in roles
    assert QAction.MenuRole.QuitRole in roles
    assert "Settings" in roles[QAction.MenuRole.PreferencesRole].text().replace("&", "")
    assert "About" in roles[QAction.MenuRole.AboutRole].text().replace("&", "")
    assert "Quit" in roles[QAction.MenuRole.QuitRole].text().replace("&", "")
    if sys.platform == "darwin":
        for action in window.findChildren(QAction):
            assert "&" not in action.text(), action.text()
    window.close()
