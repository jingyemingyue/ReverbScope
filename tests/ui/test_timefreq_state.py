"""Spectrogram and waterfall: visibility and late worker results.

The completion order is controlled with events. Nothing here waits in the
hope that a thread loses a race.
"""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Any

import numpy as np
import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from reverbscope.core.pipeline import Reference, analyze, synthetic_recording
from reverbscope.display import DisplayDataError
from reverbscope.display.timefreq import SpectrogramParams, TimeFrequencyResult
from reverbscope.i18n import N_
from reverbscope.models.configuration import SweepSettings
from reverbscope.models.result import AnalysisResult
from reverbscope.models.session import MeasurementSession
from tests.conftest import make_rir

pytestmark = pytest.mark.gui


@pytest.fixture(scope="module")
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.fixture(scope="module")
def result() -> AnalysisResult:
    sweep = SweepSettings(duration_s=0.5, pre_silence_s=0.05, post_silence_s=0.2, level_dbfs=-12.0)
    ir = make_rir(sweep.sample_rate, rt60_s=0.2, reflections=[(0.012, 0.4)])
    return analyze(synthetic_recording(sweep, ir, noise_rms=1e-5), Reference.from_settings(sweep))


def _view(result: AnalysisResult, folder: Path) -> Any:
    from reverbscope.ui.views.timefreq import SpectrogramView
    from reverbscope.ui.workspace import WorkspaceModel

    model = WorkspaceModel()
    model.add_session(folder, MeasurementSession(measurement_position="A"), result, position="A")
    view = SpectrogramView(model)
    view.resize(800, 500)
    view.show()
    return view


def _tiny(params: SpectrogramParams, mark: float) -> TimeFrequencyResult:
    return TimeFrequencyResult(
        kind="spectrogram",
        times_ms=np.array([0.0, 1.0]),
        freqs_hz=np.array([100.0, 200.0]),
        levels_db=np.array([[mark, mark - 6.0], [mark - 3.0, mark - 12.0]]),
        unit="dB",
        reference_db=0.0,
        params=params,
        notes=(),
    )


def _deliver(app: QApplication) -> None:
    for _ in range(20):
        app.processEvents()


def test_hiding_the_current_measurement_clears_the_spectrogram_at_once(
    app: QApplication, result: AnalysisResult, tmp_path: Path
) -> None:
    view = _view(result, tmp_path / "shown")
    view.redraw()
    worker = view._worker
    assert worker is not None
    assert worker.wait(5000)
    _deliver(app)
    assert view.result is not None
    key = view.model.current_key
    view.model.set_overlay(key, False)
    _deliver(app)
    assert view.result is None
    assert "hidden" in view.status.text().lower()
    view.shutdown()
    view.close()


def test_a_late_success_does_not_redraw_after_the_measurement_is_hidden(
    app: QApplication, result: AnalysisResult, tmp_path: Path
) -> None:
    """The worker is released only after the measurement is hidden."""
    view = _view(result, tmp_path / "late-hide")
    entered = threading.Event()
    release = threading.Event()
    seen: dict[str, SpectrogramParams] = {}

    def gated(
        samples: object,
        sample_rate: int,
        direct_index: int,
        params: object,
        cancelled: object = None,
    ) -> TimeFrequencyResult:
        del samples, sample_rate, direct_index, cancelled
        assert isinstance(params, SpectrogramParams)
        seen["params"] = params
        entered.set()
        assert release.wait(5)
        return _tiny(params, 1.0)

    view.transform = lambda: gated  # type: ignore[method-assign]
    try:
        view.redraw()
        assert entered.wait(5)
        key = view.model.current_key
        view.model.set_overlay(key, False)
        _deliver(app)
        assert view.result is None
        assert "hidden" in view.status.text().lower()
        release.set()
        for worker in (
            *view._old_workers,
            *([view._worker] if view._worker is not None else []),
        ):
            assert worker.wait(5000)
        _deliver(app)
        assert view.result is None
        assert "hidden" in view.status.text().lower()
        cached = view.model.cache_get(key, ("spectrogram", seen["params"]))
        assert isinstance(cached, TimeFrequencyResult)
    finally:
        release.set()
        view.shutdown()
        view.close()


def test_a_late_failure_does_not_replace_the_hidden_state(
    app: QApplication, result: AnalysisResult, tmp_path: Path
) -> None:
    view = _view(result, tmp_path / "late-fail")
    entered = threading.Event()
    release = threading.Event()

    def gated(
        samples: object,
        sample_rate: int,
        direct_index: int,
        params: object,
        cancelled: object = None,
    ) -> TimeFrequencyResult:
        del samples, sample_rate, direct_index, params, cancelled
        entered.set()
        assert release.wait(5)
        raise DisplayDataError(N_("The impulse response is empty."))

    view.transform = lambda: gated  # type: ignore[method-assign]
    try:
        view.redraw()
        assert entered.wait(5)
        view.model.set_overlay(view.model.current_key, False)
        _deliver(app)
        hidden = view.status.text()
        release.set()
        for worker in (
            *view._old_workers,
            *([view._worker] if view._worker is not None else []),
        ):
            assert worker.wait(5000)
        _deliver(app)
        assert view.status.text() == hidden
        assert view.result is None
    finally:
        release.set()
        view.shutdown()
        view.close()


def test_an_older_spectrogram_cannot_cover_a_newer_one(
    app: QApplication, result: AnalysisResult, tmp_path: Path
) -> None:
    """The first worker finishes after the second has already drawn."""
    view = _view(result, tmp_path / "order")
    first_in = threading.Event()
    first_go = threading.Event()
    second_in = threading.Event()
    second_go = threading.Event()
    which = {"n": 0}

    def gated(
        samples: object,
        sample_rate: int,
        direct_index: int,
        params: object,
        cancelled: object = None,
    ) -> TimeFrequencyResult:
        del samples, sample_rate, direct_index, cancelled
        assert isinstance(params, SpectrogramParams)
        which["n"] += 1
        if which["n"] == 1:
            first_in.set()
            assert first_go.wait(5)
            return _tiny(params, -10.0)
        second_in.set()
        assert second_go.wait(5)
        return _tiny(params, -20.0)

    view.transform = lambda: gated  # type: ignore[method-assign]
    try:
        view.redraw()
        assert first_in.wait(5)
        view.hop_ms.blockSignals(True)
        view.hop_ms.setValue(4.0)
        view.hop_ms.blockSignals(False)
        view.redraw()
        assert second_in.wait(5)
        second_go.set()
        # The second worker is view._worker; the first is in _old_workers.
        assert view._worker is not None and view._worker.wait(5000)
        _deliver(app)
        assert view.result is not None
        assert float(view.result.levels_db[0, 0]) == pytest.approx(-20.0)
        first_go.set()
        assert view._old_workers
        assert view._old_workers[0].wait(5000)
        _deliver(app)
        assert view.result is not None
        assert float(view.result.levels_db[0, 0]) == pytest.approx(-20.0)
    finally:
        first_go.set()
        second_go.set()
        view.shutdown()
        view.close()


def test_the_display_cache_is_bounded_and_follows_the_measurement(
    app: QApplication, result: AnalysisResult, tmp_path: Path
) -> None:
    """Repeated parameter changes must not keep every spectrogram.

    One modest spectrogram is measured below. The budget is what decides how
    many of those can stay; an oversized value is kept only while it is the
    newest one.
    """
    del app
    from reverbscope.display.timefreq import SpectrogramParams, spectrogram
    from reverbscope.ui.workspace import DISPLAY_CACHE_BUDGET, WorkspaceModel

    ir = result.impulse_response
    picture = spectrogram(
        ir.samples,
        ir.sample_rate,
        ir.direct_sound_index,
        SpectrogramParams(
            window_ms=20.0,
            hop_ms=5.0,
            time_range_ms=(-5.0, 80.0),
            points_per_octave=6,
            floor_db=-80.0,
        ),
    )
    one = int(picture.levels_db.nbytes + picture.times_ms.nbytes + picture.freqs_hz.nbytes)
    assert 1_000 < one < DISPLAY_CACHE_BUDGET, one
    model = WorkspaceModel()
    entry = model.add_session(
        tmp_path / "cache",
        MeasurementSession(measurement_position="A"),
        result,
        position="A",
    )
    blob = np.zeros(256 * 1024, dtype=np.float64)  # 2 MiB; four of them fill the 8 MiB budget
    for index in range(6):
        model.cache_put(entry.key, ("blob", index), blob)
    assert model.display_cache_bytes() <= DISPLAY_CACHE_BUDGET
    assert model.cache_get(entry.key, ("blob", 5)) is blob
    assert model.cache_get(entry.key, ("blob", 0)) is None
    curve = np.ones(8, dtype=np.float64)
    model.cache_put(entry.key, "curve", curve)
    saved = model.mark_saved(entry.key, tmp_path / "saved-session", position="A")
    assert model.cache_get(saved, "curve") is curve
    assert saved != entry.key or model.cache_get(entry.key, "curve") is curve
    model.add_session(
        tmp_path / "saved-session",
        MeasurementSession(measurement_position="A"),
        result,
        position="A",
    )
    assert model.cache_get(saved, "curve") is None
    model.cache_put(saved, "curve", curve)
    model.remove(saved)
    assert model.display_cache_bytes() == 0


def test_illegal_parameters_keep_a_late_picture_off_the_chart(
    app: QApplication, result: AnalysisResult, tmp_path: Path
) -> None:
    view = _view(result, tmp_path / "bad-params")
    entered = threading.Event()
    release = threading.Event()

    def gated(
        samples: object,
        sample_rate: int,
        direct_index: int,
        params: object,
        cancelled: object = None,
    ) -> TimeFrequencyResult:
        del samples, sample_rate, direct_index, cancelled
        assert isinstance(params, SpectrogramParams)
        entered.set()
        assert release.wait(5)
        return _tiny(params, 3.0)

    view.transform = lambda: gated  # type: ignore[method-assign]
    try:
        view.redraw()
        assert entered.wait(5)
        view.hop_ms.blockSignals(True)
        view.hop_ms.setValue(80.0)  # longer than the 20 ms window
        view.hop_ms.blockSignals(False)
        view.redraw()
        assert view.result is None
        assert view.status.text()
        release.set()
        for worker in (
            *view._old_workers,
            *([view._worker] if view._worker is not None else []),
        ):
            assert worker.wait(5000)
        _deliver(app)
        assert view.result is None
    finally:
        release.set()
        view.shutdown()
        view.close()
