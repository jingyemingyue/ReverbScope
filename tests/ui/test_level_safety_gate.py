"""SAFE-01: level acknowledgement gates Start before any dialog."""

from __future__ import annotations

import os

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMessageBox

from reverbscope.audio.backend import SAFE_MAX_LEVEL_DBFS
from reverbscope.i18n import _
from reverbscope.ui.main_window import MainWindow

pytestmark = pytest.mark.gui


@pytest.fixture
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_level_gate_disables_start_without_dialog(
    app: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    warnings: list[str] = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda *args, **kwargs: warnings.append("warned") or QMessageBox.StandardButton.Ok,
    )

    window = MainWindow()
    window.show()
    window.show_mode("standalone")
    app.processEvents()
    page = window.standalone

    reason = _("Check “I have set the monitor level low” first")

    # ① Above the safe ceiling, unchecked: Start disabled, reason shown, no dialog.
    page.level.setValue(-9.0)
    page.acknowledge.setChecked(False)
    app.processEvents()
    assert not page.level_acknowledged()
    assert not page.run_button.isEnabled()
    assert page.level_gate_reason() == reason
    page.start_measurement()
    assert warnings == []

    # ② Acknowledged: Start may enable (devices permitting) and no dialog path.
    page.acknowledge.setChecked(True)
    app.processEvents()
    assert page.level_acknowledged()
    assert page.level_gate_reason() == ""
    # Devices may be absent offscreen; gate itself must be clear.
    assert page._level_blocks_start() is False

    # ④ Below the ceiling: acknowledgement not required.
    page.level.setValue(-20.0)
    app.processEvents()
    assert page.level_acknowledged()
    assert not page.acknowledge.isEnabled()
    assert SAFE_MAX_LEVEL_DBFS == -12.0
    assert page._level_blocks_start() is False

    # Crossing back above the ceiling clears a prior tick.
    page.level.setValue(-9.0)
    app.processEvents()
    assert not page.acknowledge.isChecked()
    assert page._level_blocks_start() is True

    # ③ After a finished take the acknowledgement resets.
    page.acknowledge.setChecked(True)
    page._reset_level_acknowledgement()
    assert not page.acknowledge.isChecked()

    window.close()
