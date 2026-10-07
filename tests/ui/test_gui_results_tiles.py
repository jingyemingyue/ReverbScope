"""The key-figure tiles of the Results overview."""

from __future__ import annotations

import os
from dataclasses import replace

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from reverbscope.core.pipeline import Reference, analyze, synthetic_recording
from reverbscope.models.configuration import SweepSettings
from reverbscope.ui.results import _Overview
from reverbscope.ui.theme import tone_color
from tests.conftest import make_rir

pytestmark = pytest.mark.gui


@pytest.fixture(scope="module")
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


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
            result.reflections, reflections=(), window_truncated=True, analysed_window_ms=(0.8, 12.0)
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
