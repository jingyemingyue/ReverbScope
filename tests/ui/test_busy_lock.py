"""BUSY-01: lock settings, open, and mode switches while a measurement is busy."""

from __future__ import annotations

import os

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from reverbscope.i18n import _
from reverbscope.ui.main_window import MainWindow

pytestmark = pytest.mark.gui


@pytest.fixture
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_busy_locks_settings_open_and_mode_while_sounding(
    app: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """While sounding, dangerous global entries stay disabled and open nothing."""
    window = MainWindow()
    window.show()
    app.processEvents()

    locked = (
        window.new_action,
        window.open_action,
        window.open_project_action,
        window.settings_action,
        window.daw_mode_action,
        window.standalone_mode_action,
    )
    for action in locked:
        assert action.isEnabled(), action.text()
    assert window.workspace.settings_button.isEnabled()

    settings_opened: list[bool] = []

    class _FakeSettings:
        def __init__(self, _parent: object) -> None:
            settings_opened.append(True)

        def exec(self) -> bool:
            return False

    monkeypatch.setattr("reverbscope.ui.settings_dialog.SettingsDialog", _FakeSettings)

    # Sounding: stop is armed, busy_changed reports the take (same path as the strip).
    window.standalone.stop_button.setEnabled(True)
    window.standalone.busy_changed.emit(True)
    app.processEvents()

    reason = _("Measurement in progress")
    for action in locked:
        assert not action.isEnabled(), action.text()
        assert action.toolTip() == reason
    assert not window.workspace.settings_button.isEnabled()
    assert window.workspace.settings_button.toolTip() == reason

    window.show_settings()
    assert settings_opened == []

    file_dialogs: list[str] = []
    monkeypatch.setattr(
        "reverbscope.ui.main_window.QFileDialog.getOpenFileName",
        lambda *args, **kwargs: file_dialogs.append("session") or ("", ""),
    )
    monkeypatch.setattr(
        "reverbscope.ui.main_window.QFileDialog.getExistingDirectory",
        lambda *args, **kwargs: file_dialogs.append("project") or "",
    )
    # Guards must return before any file dialog (modals would cover Stop).
    window.choose_session()
    window.choose_project()
    assert file_dialogs == []

    window.show_mode("universal_daw")
    app.processEvents()
    # Path switch is blocked: never leave the busy standalone path for DAW.
    assert window.stack.currentWidget() is not window.daw
    assert window.stack.currentWidget() is window.standalone

    window.standalone.busy_changed.emit(False)
    app.processEvents()
    for action in locked:
        assert action.isEnabled(), action.text()
    assert window.workspace.settings_button.isEnabled()

    window.show_settings()
    assert settings_opened == [True]
    window.close()
