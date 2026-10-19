"""ESC-01: application-level Escape stops a take before popups consume it."""

from __future__ import annotations

import os

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication, QComboBox

from reverbscope.i18n import _
from reverbscope.ui.main_window import MainWindow

pytestmark = pytest.mark.gui


@pytest.fixture
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _press_escape(target: object) -> None:
    event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(target, event)


def test_escape_stops_while_popup_focused(
    app: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    window = MainWindow()
    window.show()
    window.show_mode("standalone")
    app.processEvents()

    stopped: list[bool] = []
    monkeypatch.setattr(window.standalone, "stop_measurement", lambda: stopped.append(True) or None)

    window.standalone.stop_button.setEnabled(True)
    window.standalone.busy_changed.emit(True)
    app.processEvents()
    assert window.strip.stop_button.isEnabled()

    combo = window.standalone.sample_rate
    assert isinstance(combo, QComboBox)
    combo.setFocus()
    combo.showPopup()
    app.processEvents()
    popup = QApplication.activePopupWidget()
    assert popup is not None

    _press_escape(popup)
    app.processEvents()
    assert stopped == [True]
    window.close()


def test_escape_closes_overlay_drawer_when_idle(app: QApplication) -> None:
    window = MainWindow()
    window.show()
    app.processEvents()
    window.set_inspector_open(True)
    app.processEvents()
    assert window.properties_drawer.is_overlay()
    assert window.properties_drawer.isVisible()

    _press_escape(window)
    app.processEvents()
    assert not window.properties_drawer.isVisible()
    window.close()


def test_escape_shows_uncancellable_during_analysis(app: QApplication) -> None:
    window = MainWindow()
    window.show()
    app.processEvents()

    window.standalone.stop_button.setEnabled(False)
    window.standalone.busy_changed.emit(True)
    app.processEvents()
    assert window.strip.phase.property("phase") == "analyze"

    _press_escape(window)
    app.processEvents()
    assert window.strip.status.text() == _("Analysis cannot be cancelled")
    window.close()
