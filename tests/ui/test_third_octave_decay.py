"""The one-third-octave decay analysis in the desktop app.

The Decay view gets a Resolution list only for a measurement analysed in
one-third-octave bands; the inspector counts their two-slope bands; both
measurement pages offer the opt-in, off by default.
"""

from __future__ import annotations

import math
import os
from pathlib import Path
from typing import Any

import numpy as np
import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLabel

from reverbscope.core.pipeline import synthetic_recording
from reverbscope.i18n import _
from reverbscope.io.wav import write_wav
from reverbscope.models.configuration import AnalysisSettings, SweepSettings
from reverbscope.models.result import AnalysisResult
from tests.conftest import make_rir
from tests.ui.test_views import _model, _shown

pytestmark = pytest.mark.gui


@pytest.fixture(scope="module")
def app() -> Any:
    return QApplication.instance() or QApplication([])


def _coupled(third_octave: bool) -> AnalysisResult:
    from reverbscope.core.pipeline import analyze_impulse_response
    from reverbscope.models.audio import AudioSignal
    from tests.unit.test_multislope import LEAD, RATE, decay

    signal = decay(0.4, 1.6, -25.0, seed=8)
    signal[LEAD] = 4.0 * math.sqrt(float(np.sum(signal**2)))
    return analyze_impulse_response(
        AudioSignal(signal, RATE),
        AnalysisSettings(third_octave_decay=third_octave),
        excitation_band=(20.0, 20_000.0),
    )


def test_decay_view_switches_to_one_third_octave_bands(app: Any) -> None:
    from reverbscope.ui.views.decay import ALL_BANDS, OCTAVE, THIRD_OCTAVE, DecayView

    result = _coupled(True)
    thirds = result.decay.third_octave_bands
    assert thirds is not None
    view = _shown(DecayView(_model(result)), app)
    assert view.resolution.isVisible()
    assert view.resolution_value() == OCTAVE
    octave_labels = [view.band.itemData(i) for i in range(2, view.band.count())]
    assert octave_labels == [b.band_label for b in result.decay.bands]

    view.resolution.setCurrentIndex(view.resolution.findData(THIRD_OCTAVE))
    app.processEvents()
    view.redraw()
    assert view.resolution_value() == THIRD_OCTAVE
    labels = [view.band.itemData(i) for i in range(2, view.band.count())]
    assert labels == [b.band_label for b in thirds]
    # The band chart shows the thirds' T30 and says so.
    assert any("one-third-octave" in (s.processing or "") for s in view.bands_chart.series)
    assert "One-third-octave bands: two slopes in" in view.notes.text()

    # A one-third-octave band with two slopes gets the overlay.
    view.band.setCurrentIndex(view.band.findData("1 kHz"))
    view.redraw()
    names = [s.name for s in view.chart.series]
    assert _("Two-slope fit") in names
    assert "Two-slope fit: T1 = " in view.notes.text()

    # All bands: every third is a curve (each its own key).
    view.band.setCurrentIndex(view.band.findData(ALL_BANDS))
    view.redraw()
    keys = {s.key for s in view.chart.series}
    assert all(any(key.endswith("#" + b.band_label) for key in keys) for b in thirds)

    # Back to octaves: the octave list and the 1 kHz octave band.
    view.resolution.setCurrentIndex(view.resolution.findData(OCTAVE))
    app.processEvents()
    view.redraw()
    labels = [view.band.itemData(i) for i in range(2, view.band.count())]
    assert labels == [b.band_label for b in result.decay.bands]
    view.close()


def test_decay_view_hides_the_resolution_without_thirds(app: Any) -> None:
    from reverbscope.ui.views.decay import OCTAVE, THIRD_OCTAVE, DecayView

    view = _shown(DecayView(_model(_coupled(False))), app)
    assert not view.resolution.isVisible()
    # A choice left on one-third octave from another measurement falls back.
    view.resolution.setCurrentIndex(view.resolution.findData(THIRD_OCTAVE))
    view.redraw()
    assert view.resolution_value() == OCTAVE
    assert "One-third-octave" not in view.notes.text()
    view.close()


def _labels(widget: Any) -> list[str]:
    return [label.text() for label in widget.findChildren(QLabel)]


def test_the_opt_in_is_off_by_default_and_reaches_the_analysis(
    app: Any, tmp_path: Path, short_sweep: SweepSettings
) -> None:
    from reverbscope.ui.main_window import MainWindow

    window = MainWindow()
    window.show()
    assert not window.daw.third_octave.isChecked()
    assert not window.standalone.third_octave.isChecked()
    window.show_mode("universal_daw")
    page = window.daw
    rate = short_sweep.sample_rate
    page.sample_rate.setCurrentIndex(page.sample_rate.findData(rate))
    page.duration.setValue(short_sweep.duration_s)
    page.generate_sweep_to(tmp_path / "sweep.wav")
    take = synthetic_recording(short_sweep, make_rir(rate, rt60_s=0.3), noise_rms=1e-5)
    page.set_recording(write_wav(tmp_path / "take.wav", take.samples, rate, subtype="FLOAT"))
    page.third_octave.setChecked(True)
    page.start_analysis(blocking=True)
    app.processEvents()
    assert window.state.analysis_settings.third_octave_decay is True
    assert window.state.result is not None
    thirds = window.state.result.decay.third_octave_bands
    assert thirds is not None and len(thirds) == 24
    assert _("Slopes, 1/3 octave") in _labels(window.inspector.figures)
    window.close()
