"""960×640: the main analysis plot must keep a measurable share of the window."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from reverbscope.models.result import AnalysisResult
from reverbscope.models.session import MeasurementSession
from reverbscope.ui.main_window import MainWindow
from reverbscope.ui.plotkit import ChartPanel

pytestmark = pytest.mark.gui

# REVIEW.md §3.1 recorded ~220 px (34 %) on e39185c BEFORE. Minimal chrome
# recovery targets at least half the window height for the primary plot.
_MIN_PLOT_FRACTION = 0.50


@pytest.fixture
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_plot_height_at_960x640_measured(
    app: QApplication, analysed_result: AnalysisResult, tmp_path: Path
) -> None:
    window = MainWindow()
    window.resize(960, 640)
    window.show()
    window.model.add_session(tmp_path / "take", MeasurementSession(), analysed_result)
    window.show_view("fr")
    app.processEvents()
    window.resize(960, 640)
    for _ in range(5):
        app.processEvents()

    view = window.views["fr"]
    charts = [c for c in view.findChildren(ChartPanel) if c.isVisible()]
    assert charts, "frequency view should show a chart"
    primary = max(charts, key=lambda chart: chart.plot.height())
    plot_h = primary.plot.height()
    fraction = plot_h / window.height()
    # Recorded for the PR; do not treat the design-mock 338 px as a claim.
    assert plot_h >= int(window.height() * _MIN_PLOT_FRACTION), (
        f"primary plot {plot_h}px is {fraction:.0%} of {window.height()}px "
        f"(need ≥ {_MIN_PLOT_FRACTION:.0%}); tools_visible={window.workspace.tools.isVisible()} "
        f"context={window.workspace.context.height()} status_bar={window.statusBar() is not None}"
    )
    window.close()
