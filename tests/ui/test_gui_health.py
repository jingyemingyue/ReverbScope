"""The Measurement health card on the Results page."""

from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from reverbscope.core.pipeline import Reference, analyze, synthetic_recording
from reverbscope.io.wav import write_wav
from reverbscope.models.configuration import SweepSettings
from reverbscope.ui.main_window import MainWindow
from reverbscope.ui.results import _Overview
from reverbscope.ui.theme import tone_color
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


def test_a_cut_short_reflection_window_is_not_shown_as_a_clean_room(
    app: QApplication, short_sweep: SweepSettings
) -> None:
    """An empty reflection list from a response that ended before the search
    window did is an incomplete search, not "clean" (the command line's
    At-a-glance row says the same)."""
    rate = short_sweep.sample_rate
    take = synthetic_recording(short_sweep, make_rir(rate, rt60_s=0.3), noise_rms=1e-5)
    result = analyze(take, Reference.from_settings(short_sweep))
    cut_short = replace(
        result,
        reflections=replace(
            result.reflections,
            reflections=(),
            window_truncated=True,
            analysed_window_ms=(0.8, 12.0),
        ),
    )
    overview = _Overview()
    overview.show_result(cut_short, [], "generic")
    assert overview.reflections.value.text() == "0"
    assert "12.0 ms that could be searched" in overview.reflections.sub.text()
    assert overview.reflections.chip.text() == "incomplete window"
    assert tone_color("warn")[0] in overview.reflections.chip.styleSheet()
    # A complete window with nothing above the threshold is still clean.
    clean = replace(cut_short, reflections=replace(cut_short.reflections, window_truncated=False))
    overview.show_result(clean, [], "generic")
    assert overview.reflections.chip.text() == "clean"
    assert tone_color("good")[0] in overview.reflections.chip.styleSheet()
    overview.close()
