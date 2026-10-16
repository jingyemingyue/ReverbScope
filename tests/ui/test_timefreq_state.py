"""Spectrogram and waterfall: visibility and late worker results.

The completion order is controlled with events. Nothing here waits in the
hope that a thread loses a race. Both views share the worker, so each case
is run on the spectrogram and on the waterfall.
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
from reverbscope.display.timefreq import SpectrogramParams, TimeFrequencyResult, WaterfallParams
from reverbscope.i18n import N_
from reverbscope.models.configuration import SweepSettings
from reverbscope.models.result import AnalysisResult
from reverbscope.models.session import MeasurementSession
from tests.conftest import make_rir

pytestmark = pytest.mark.gui

_KINDS = ("spectrogram", "waterfall")


@pytest.fixture(scope="module")
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.fixture(scope="module")
def result() -> AnalysisResult:
    sweep = SweepSettings(duration_s=0.5, pre_silence_s=0.05, post_silence_s=0.2, level_dbfs=-12.0)
    ir = make_rir(sweep.sample_rate, rt60_s=0.2, reflections=[(0.012, 0.4)])
    return analyze(synthetic_recording(sweep, ir, noise_rms=1e-5), Reference.from_settings(sweep))


def _model(result: AnalysisResult, folder: Path, positions: tuple[str, ...] = ("A",)) -> Any:
    from reverbscope.ui.workspace import WorkspaceModel

    model = WorkspaceModel()
    for index, position in enumerate(positions):
        model.add_session(
            folder / position,
            MeasurementSession(measurement_position=position),
            result,
            position=position,
            make_current=index == 0,
            visible=True,
        )
    return model


def _view(kind: str, model: Any) -> Any:
    from reverbscope.ui.views.timefreq import SpectrogramView, WaterfallView

    view = SpectrogramView(model) if kind == "spectrogram" else WaterfallView(model)
    view.resize(800, 500)
    return view


def _tiny(kind: str, params: object, mark: float) -> TimeFrequencyResult:
    assert isinstance(params, SpectrogramParams | WaterfallParams)
    return TimeFrequencyResult(
        kind=kind,
        times_ms=np.array([0.0, 10.0]),
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


def _wait(view: Any) -> None:
    for worker in (*view._old_workers, *([view._worker] if view._worker is not None else [])):
        assert worker.wait(5000)


def _illegal(view: Any) -> None:
    """Parameters the view rejects. Signals stay blocked so only redraw() runs."""
    if view.kind == "spectrogram":
        view.hop_ms.blockSignals(True)
        view.hop_ms.setValue(80.0)  # longer than the 20 ms window
        view.hop_ms.blockSignals(False)
        return
    view.window_ms.blockSignals(True)
    view.window_ms.setValue(5.0)
    view.window_ms.blockSignals(False)
    view.rise_ms.blockSignals(True)
    view.rise_ms.setValue(40.0)  # rise plus the taper no longer fit the window
    view.rise_ms.blockSignals(False)


def _nudge(view: Any) -> None:
    """A legal parameter change that must not be covered by the previous worker."""
    if view.kind == "spectrogram":
        view.hop_ms.blockSignals(True)
        view.hop_ms.setValue(4.0)
        view.hop_ms.blockSignals(False)
        return
    view.step_ms.blockSignals(True)
    view.step_ms.setValue(20.0)
    view.step_ms.blockSignals(False)


@pytest.mark.parametrize("kind", _KINDS)
@pytest.mark.parametrize("action", ("hide", "switch", "remove", "illegal"))
@pytest.mark.parametrize("outcome", ("success", "failure"))
def test_a_late_callback_does_not_redraw(
    app: QApplication,
    result: AnalysisResult,
    tmp_path: Path,
    kind: str,
    action: str,
    outcome: str,
) -> None:
    """Hide, switch, remove and illegal parameters, then a late success or failure.

    The first worker is released only after the view has already moved on.
    """
    positions = ("A", "B") if action == "switch" else ("A",)
    model = _model(result, tmp_path / f"{kind}-{action}-{outcome}", positions)
    view = _view(kind, model)
    first_in = threading.Event()
    second_in = threading.Event()
    first_go = threading.Event()
    second_go = threading.Event()
    seen: dict[str, object] = {}
    counter = {"n": 0}
    lock = threading.Lock()

    def gated(
        samples: object,
        sample_rate: int,
        direct_index: int,
        params: object,
        cancelled: object = None,
    ) -> TimeFrequencyResult:
        del samples, sample_rate, direct_index, cancelled
        with lock:
            number = counter["n"]
            counter["n"] += 1
        if number == 0:
            seen["params"] = params
            first_in.set()
            assert first_go.wait(5)
            if outcome == "failure":
                raise DisplayDataError(N_("The impulse response is empty."))
            return _tiny(kind, params, -10.0)
        second_in.set()
        assert second_go.wait(5)
        return _tiny(kind, params, -20.0)

    view.transform = lambda: gated  # type: ignore[method-assign]
    try:
        view.show()
        assert first_in.wait(5)
        key = view.model.current_key
        if action == "hide":
            view.model.set_overlay(key, False)
        elif action == "switch":
            other = next(entry.key for entry in view.model.entries() if entry.key != key)
            view.model.set_current(other)
            assert second_in.wait(5)
        elif action == "remove":
            view.model.remove(key)
        else:
            _illegal(view)
            with pytest.raises(DisplayDataError):
                view.params()
            view.redraw()
        _deliver(app)
        assert view.result is None
        status = view.status.text()
        assert status
        if action == "hide":
            assert "hidden" in status.lower()
        first_go.set()
        for worker in list(view._old_workers):
            assert worker.wait(5000)
        if action != "switch" and view._worker is not None:
            assert view._worker.wait(5000)
        _deliver(app)
        assert view.result is None
        assert view.status.text() == status
        cached = view.model.cache_get(key, (kind, seen["params"]))
        if outcome == "success" and action in ("hide", "switch", "illegal"):
            assert isinstance(cached, TimeFrequencyResult)
            assert float(cached.levels_db[0, 0]) == pytest.approx(-10.0)
        else:
            assert cached is None
        if action == "switch":
            second_go.set()
            assert view._worker is not None and view._worker.wait(5000)
            _deliver(app)
            assert view.result is not None
            assert float(view.result.levels_db[0, 0]) == pytest.approx(-20.0)
    finally:
        first_go.set()
        second_go.set()
        view.shutdown()
        view.close()


@pytest.mark.parametrize("kind", _KINDS)
def test_an_older_result_cannot_cover_a_newer_one(
    app: QApplication, result: AnalysisResult, tmp_path: Path, kind: str
) -> None:
    """The first worker finishes after the second has already drawn."""
    view = _view(kind, _model(result, tmp_path / f"{kind}-order"))
    first_in = threading.Event()
    first_go = threading.Event()
    second_in = threading.Event()
    second_go = threading.Event()
    which = {"n": 0}
    lock = threading.Lock()

    def gated(
        samples: object,
        sample_rate: int,
        direct_index: int,
        params: object,
        cancelled: object = None,
    ) -> TimeFrequencyResult:
        del samples, sample_rate, direct_index, cancelled
        with lock:
            which["n"] += 1
            number = which["n"]
        if number == 1:
            first_in.set()
            assert first_go.wait(5)
            return _tiny(kind, params, -10.0)
        second_in.set()
        assert second_go.wait(5)
        return _tiny(kind, params, -20.0)

    view.transform = lambda: gated  # type: ignore[method-assign]
    try:
        view.show()
        assert first_in.wait(5)
        _nudge(view)
        view.redraw()
        assert second_in.wait(5)
        second_go.set()
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

    One modest spectrogram is measured below. Several of those fit in the
    8 MiB budget; the oldest are the ones that go.
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


def test_one_display_result_may_exceed_the_budget(
    app: QApplication, result: AnalysisResult, tmp_path: Path
) -> None:
    """The 8 MiB figure is a budget. A single picture larger than it is kept.

    Adding another picture drops the oldest until one remains, so two pictures
    are not both kept once their total is over the budget.
    """
    del app
    from reverbscope.ui.workspace import DISPLAY_CACHE_BUDGET, WorkspaceModel

    model = WorkspaceModel()
    entry = model.add_session(
        tmp_path / "over",
        MeasurementSession(measurement_position="A"),
        result,
        position="A",
    )
    huge = np.zeros(DISPLAY_CACHE_BUDGET // 8 + 4096, dtype=np.float64)
    assert huge.nbytes > DISPLAY_CACHE_BUDGET
    model.cache_put(entry.key, "huge", huge)
    assert model.cache_get(entry.key, "huge") is huge
    assert model.display_cache_bytes() > DISPLAY_CACHE_BUDGET
    small = np.ones(4, dtype=np.float64)
    model.cache_put(entry.key, "small", small)
    assert model.cache_get(entry.key, "huge") is None
    assert model.cache_get(entry.key, "small") is small
    assert model.display_cache_bytes() <= DISPLAY_CACHE_BUDGET
    model.cache_put(entry.key, "huge", huge)
    assert model.cache_get(entry.key, "small") is None
    assert model.cache_get(entry.key, "huge") is huge
    assert model.display_cache_bytes() > DISPLAY_CACHE_BUDGET
