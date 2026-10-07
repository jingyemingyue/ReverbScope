"""The Measurement health card on the Results page."""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from reverbscope.core.pipeline import synthetic_recording
from reverbscope.io.wav import write_wav
from reverbscope.models.configuration import SweepSettings
from reverbscope.ui.main_window import MainWindow
from tests.conftest import make_rir

pytestmark = pytest.mark.gui


@pytest.fixture(scope="module")
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _analyse_file(
    app: QApplication, tmp_path: Path, short_sweep: SweepSettings, samples
) -> MainWindow:  # type: ignore[no-untyped-def]
    window = MainWindow()
    window.show()
    window.show_mode("universal_daw")
    page = window.daw
    rate = short_sweep.sample_rate
    page.sample_rate.setCurrentIndex(page.sample_rate.findData(rate))
    page.duration.setValue(short_sweep.duration_s)
    page.generate_sweep_to(tmp_path / "sweep.wav")
    page.set_recording(write_wav(tmp_path / "take.wav", samples, rate, subtype="FLOAT"))
    page.start_analysis(blocking=True)
    app.processEvents()
    assert window.stack.currentWidget() is window.results
    return window


def test_the_results_page_shows_the_health_card(
    app: QApplication, tmp_path: Path, short_sweep: SweepSettings
) -> None:
    rate = short_sweep.sample_rate
    take = synthetic_recording(short_sweep, make_rir(rate, rt60_s=0.3), noise_rms=1e-5)
    window = _analyse_file(app, tmp_path, short_sweep, take.samples)
    overview = window.results.overview
    assert overview.health_chip.text() == "GOOD"
    assert "10 of 10 checks good" in overview.health_summary.text()
    assert overview.health_rows.count() == 0
    assert "Measurement health" in window.results.text.toPlainText()
    window.close()

    clipped = np.clip(take.samples * 4.0, -0.3, 0.3)
    window = _analyse_file(app, tmp_path, short_sweep, clipped)
    overview = window.results.overview
    assert overview.health_chip.text() == "INVALID"
    assert overview.health_rows.count() >= 1
    cards = [overview.health_rows.itemAt(i).widget() for i in range(overview.health_rows.count())]
    texts = [card.message.text() for card in cards]
    assert any("flat-topped" in text and "Affects:" in text for text in texts)
    window.close()
