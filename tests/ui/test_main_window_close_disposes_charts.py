"""Closing the main window must dispose pyqtgraph charts (resource release)."""

from __future__ import annotations

import os

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from reverbscope.ui import main_window as main_window_module
from reverbscope.ui.main_window import MainWindow

pytestmark = pytest.mark.gui


@pytest.fixture(scope="module")
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_close_disposes_charts_each_time(app: QApplication, monkeypatch: pytest.MonkeyPatch) -> None:
    """Regression: a closed window that skips dispose_charts leaves pyqtgraph
    objects alive until interpreter shutdown (conftest has to clean them up)."""
    calls: list[object] = []

    def tracking(widget: object) -> None:
        calls.append(widget)
        # Still run the real disposer so later tests are not left dirty.
        from reverbscope.ui.plotkit import dispose_charts as real

        real(widget)

    monkeypatch.setattr(main_window_module, "dispose_charts", tracking)
    for _ in range(3):
        window = MainWindow()
        window.show()
        app.processEvents()
        window.close()
        app.processEvents()
    assert len(calls) == 3
    assert all(call is not None for call in calls)
