"""FLOW-01: step gates and an action bar that stays outside the scroll area."""

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


def test_action_bar_visible_at_960x640_and_steps_gate(app: QApplication) -> None:
    window = MainWindow()
    window.resize(960, 640)
    window.show()
    window.show_mode("standalone")
    app.processEvents()
    page = window.standalone
    flow = page.flow

    assert hasattr(page, "action_bar")
    bar = page.action_bar
    assert bar.isVisible()
    # Pinned below the scroll area, not inside the scrolling body.
    scroll = page._scroll_area
    assert bar.geometry().top() >= scroll.geometry().bottom() - 1
    top_left = bar.mapTo(window, bar.rect().topLeft())
    bottom_right = bar.mapTo(window, bar.rect().bottomRight())
    assert 0 <= top_left.y() < window.height()
    assert bottom_right.y() <= window.height()
    assert bottom_right.x() <= window.width()
    assert page.stop_button.isVisible() or not page.is_busy()

    # Step 2/3 locked until connection looks complete enough to advance.
    flow.set_step(0)
    app.processEvents()
    # With no devices, connection is incomplete → later steps stay locked.
    if not page._devices and not page.demo_mode:
        assert not flow.buttons[1].isEnabled()
        assert not flow.buttons[2].isEnabled()
        tip = flow.buttons[1].toolTip()
        assert tip  # reason for the lock
    else:
        # Demo / fake backend: connection may already be complete.
        assert flow.step_complete(0)[0]

    # Loud level without ack blocks leaving the signal step.
    page.level.setValue(-9.0)
    page.acknowledge.setChecked(False)
    if flow.buttons[1].isEnabled():
        flow.set_step(1)
        app.processEvents()
        assert flow.step_complete(1)[0] is False
        assert (
            _("monitor level") in flow.step_complete(1)[1].lower() or flow.next.isEnabled() is False
        )

    # Review must not offer a second “Back” beside Previous.
    assert not hasattr(page, "back_button") or page.back_button.parentWidget() is None
    window.close()
