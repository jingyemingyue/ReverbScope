"""The COMMON SLOPES card of the Project page: decay times shared by the
project's positions, computed on request in a worker thread."""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from reverbscope.models.configuration import SweepSettings
from reverbscope.ui.main_window import MainWindow
from tests.ui.test_gui_project import _booth

pytestmark = pytest.mark.gui


@pytest.fixture(scope="module")
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_common_slopes_card_runs_and_fills_the_table(
    app: QApplication, tmp_path: Path, short_sweep: SweepSettings
) -> None:
    project = _booth(tmp_path, short_sweep)
    window = MainWindow()
    window.show()
    window.show_project(project)
    assert window.model.wait_until_loaded()
    page = window.project
    page.redraw()
    app.processEvents()
    assert page.common_card.isVisibleTo(page)
    assert page.common_button.isEnabled()
    assert not page.common_table.isVisibleTo(page)
    assert len(page.common_responses()) == 3
    page.analyse_common_slopes()
    assert not page.common_button.isEnabled()  # one analysis at a time
    deadline = time.monotonic() + 120.0
    while page.common_result is None and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.02)
    for _ in range(20):
        app.processEvents()
    result = page.common_result
    assert result is not None, page.common_status.text()
    assert page.common_table.isVisibleTo(page)
    assert page.common_table.rowCount() == len(result.bands) > 0
    assert page.common_table.item(0, 3).text() == "3"
    assert "3 position(s)" in page.common_status.text()
    assert page.common_button.isEnabled()
    window.close()
