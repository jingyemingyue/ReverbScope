"""The workbench: no demo entry, straight into the charts, several
measurements at once with independent selection / visibility / baseline,
diagnostics that locate their evidence, a real take with Stop, save and
reopen, export, theme and small windows, and the thread lifecycle.
"""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QModelIndex, Qt
from PySide6.QtWidgets import QApplication, QMessageBox

from reverbscope.core.pipeline import Reference, analyze, synthetic_recording
from reverbscope.io.session_store import load_session, save_measurement
from reverbscope.models.configuration import SweepSettings
from reverbscope.models.result import AnalysisResult
from reverbscope.models.session import MeasurementSession
from reverbscope.ui.document import Measurement
from reverbscope.ui.workbench import WorkbenchWindow
from tests.conftest import make_rir

pytestmark = pytest.mark.gui


@pytest.fixture(scope="module")
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.fixture
def fake_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REVERBSCOPE_AUDIO_BACKEND", "fake")


def _settle(app: QApplication, *threads: object, rounds: int = 10) -> None:
    for thread in threads:
        if thread is not None:
            thread.wait()  # type: ignore[attr-defined]
    for _ in range(rounds):
        app.processEvents()
        time.sleep(0.01)


def _result(short_sweep: SweepSettings, rt60_s: float = 0.35, seed: int = 1) -> AnalysisResult:
    rate = short_sweep.sample_rate
    take = synthetic_recording(
        short_sweep,
        make_rir(rate, rt60_s=rt60_s, reflections=[(0.018, 0.35)], seed=seed),
        noise_rms=1e-5,
    )
    return analyze(take, Reference.from_settings(short_sweep))


def _measurement(
    short_sweep: SweepSettings, room: str = "Booth", position: str = "A", rt60_s: float = 0.35
) -> Measurement:
    session = MeasurementSession(
        room_name=room, measurement_position=position, mode="universal_daw"
    )
    return Measurement(session=session, result=_result(short_sweep, rt60_s), profile="generic")


def _saved(tmp_path: Path, short_sweep: SweepSettings, name: str, rt60_s: float = 0.35) -> Path:
    session = MeasurementSession(room_name="Booth", measurement_position=name, mode="universal_daw")
    save_measurement(tmp_path / name, session, _result(short_sweep, rt60_s), copy_recording=False)
    return tmp_path / name


def _lines(window: WorkbenchWindow, panel: int = 0) -> list[object]:
    figure = window.panels[panel].figure
    return [line for ax in figure.get_axes() for line in ax.get_lines()]


def _menu_texts(window: WorkbenchWindow) -> list[str]:
    texts: list[str] = []
    for top in window.menuBar().actions():
        menu = top.menu()
        if menu is None:
            continue
        for action in menu.actions():
            texts.append(action.text())
            sub = action.menu()
            if sub is not None:
                texts.extend(a.text() for a in sub.actions())
    return texts


# --- 1. no demo entry in the product --------------------------------------------------


def test_the_product_has_no_demo_entry(app: QApplication) -> None:
    import importlib

    window = WorkbenchWindow()
    window.show()
    app.processEvents()
    texts = _menu_texts(window) + [a.text() for a in window.toolbar.actions()]
    assert not any("demo" in text.lower() for text in texts), texts
    assert not hasattr(window, "show_mode")
    for name in ("home_page", "main_window", "workspace", "standalone_page", "daw_page"):
        with pytest.raises(ModuleNotFoundError):
            importlib.import_module(f"reverbscope.ui.{name}")
    window.close()


# --- 2. straight into the workbench; a result draws its curves ---------------------------


def test_the_window_opens_on_the_empty_workbench_and_a_session_draws_curves(
    app: QApplication, tmp_path: Path, short_sweep: SweepSettings
) -> None:
    window = WorkbenchWindow()
    window.show()
    app.processEvents()
    assert window.centralWidget() is window.splitter
    assert len(window.document) == 0
    assert window.statusBar().currentMessage() == "No measurement loaded."
    assert window.list_dock.isVisible() and not window.inspector_dock.isVisible()
    assert [panel.kind() for panel in window.panels] == ["frequency", "decay"]
    assert window.panels[0].isVisible() and window.panels[1].isVisible()
    # The empty chart says so instead of drawing axes.
    empty_texts = [t.get_text() for ax in window.panels[0].figure.get_axes() for t in ax.texts]
    assert any("No measurement" in text for text in empty_texts)

    folder = _saved(tmp_path, short_sweep, "A")
    measurement = window.controller.open_session(folder)
    _settle(app)
    assert measurement is not None and window.document.selected() is measurement
    assert _lines(window, 0) and _lines(window, 1)
    assert measurement.name() in window.windowTitle()
    # The chart area keeps at least 70 % of the workspace width.
    chart = window.splitter.width()
    assert chart >= 0.7 * (chart + window.list_dock.width()), (chart, window.list_dock.width())
    window.close()


# --- 3. two measurements: select, hide and baseline independently ------------------------


def test_two_measurements_are_drawn_and_selected_hidden_and_baselined_independently(
    app: QApplication, tmp_path: Path, short_sweep: SweepSettings
) -> None:
    window = WorkbenchWindow()
    window.show()
    first = window.document.add(_measurement(short_sweep, position="A", rt60_s=0.3))
    second = window.document.add(_measurement(short_sweep, position="B", rt60_s=0.8))
    _settle(app)
    document = window.document
    assert document.selected_id() == second
    colours = {line.get_color() for line in _lines(window, 1)}
    assert document.get(first).colour in colours and document.get(second).colour in colours
    assert document.get(first).colour != document.get(second).colour

    # Selecting the first keeps the second drawn.
    document.set_selected(first)
    _settle(app)
    assert document.visible() == [document.get(first), document.get(second)]
    assert document.get(second).colour in {line.get_color() for line in _lines(window, 1)}
    # The selected curve is the thick one.
    widths = {line.get_color(): line.get_linewidth() for line in _lines(window, 1)}
    assert widths[document.get(first).colour] > widths[document.get(second).colour]

    # Hiding the second through the list model removes its curve only.
    model = window.list_model
    index = model.index_for(second)
    assert index.isValid()
    assert model.data(index, Qt.ItemDataRole.CheckStateRole) == Qt.CheckState.Checked
    assert model.setData(index, Qt.CheckState.Unchecked, Qt.ItemDataRole.CheckStateRole)
    _settle(app)
    assert not document.is_visible(second) and document.is_visible(first)
    assert document.get(second).colour not in {line.get_color() for line in _lines(window, 1)}
    assert document.selected_id() == first
    document.set_visible(second, True)

    # The baseline is a third state: the first stays selected.
    document.set_baseline(second)
    _settle(app)
    assert document.baseline_id() == second and document.selected_id() == first
    assert document.candidate() is document.get(first)
    role = model.data(model.index_for(second).siblingAtColumn(2), Qt.ItemDataRole.DisplayRole)
    assert "baseline" in str(role)
    assert window.controller.comparison() is not None
    assert window.inspector.tabs.isTabEnabled(window.inspector.tab_index("comparison"))
    # The difference view draws the delta under the two responses.
    window.panels[0].difference_button.setChecked(True)
    _settle(app)
    assert len(window.panels[0].figure.get_axes()) >= 2
    window.panels[0].difference_button.setChecked(False)

    # Closing the baseline clears the role and keeps the other measurement.
    window.controller.close_measurement(second)
    _settle(app)
    assert document.baseline_id() is None and len(document) == 1
    assert document.selected_id() == first
    window.close()


def test_a_position_groups_its_measurements_in_the_list(
    app: QApplication, short_sweep: SweepSettings
) -> None:
    window = WorkbenchWindow()
    window.show()
    window.document.add(_measurement(short_sweep, position="A"))
    window.document.add(_measurement(short_sweep, position="A", rt60_s=0.5))
    window.document.add(_measurement(short_sweep, position="B"))
    _settle(app)
    model = window.list_model
    assert model.rowCount(QModelIndex()) == 2
    assert model.rowCount(model.index(0, 0, QModelIndex())) == 2
    assert model.rowCount(model.index(1, 0, QModelIndex())) == 1
    window.close()


# --- 4. diagnostics locate their evidence; the inspector folds without a selection --------


def test_diagnostics_locate_the_chart_and_the_inspector_folds_without_a_selection(
    app: QApplication, short_sweep: SweepSettings
) -> None:
    window = WorkbenchWindow()
    window.show()
    identifier = window.document.add(_measurement(short_sweep))
    _settle(app)
    assert not window.inspector_dock.isVisible()
    window.set_inspector_visible(True)
    _settle(app)
    assert window.inspector_dock.isVisible()
    assert window.inspector.tabs.isVisible()
    measurement = window.document.get(identifier)
    assert measurement is not None and measurement.health is not None
    assert window.quality_button.isEnabled()
    assert window.inspector.diagnostics_model.rowCount() == len(measurement.findings)
    # Locating a reflection shows that chart in a panel and highlights it.
    window.locate("reflections", 0)
    _settle(app)
    kinds = [panel.kind() for panel in window.panels if panel.isVisible()]
    assert "reflections" in kinds
    panel = next(p for p in window.panels if p.kind() == "reflections")
    assert panel.highlight().get("reflection") == 0
    # The inspector folds when the selection goes and comes back with it.
    window.document.set_selected(None)
    _settle(app)
    assert not window.inspector_dock.isVisible()
    window.document.set_selected(identifier)
    _settle(app)
    assert window.inspector_dock.isVisible()
    window.controller.close_measurement(identifier)
    _settle(app)
    assert not window.inspector_dock.isVisible()
    assert not window.quality_button.isEnabled()
    window.close()


# --- 5. a real take on the fake interface: stop, finish, save, reopen, export --------------


@pytest.fixture
def held_take(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    """The fake interface plays until the test releases it (or Stop is pressed)."""
    from PySide6.QtCore import QThread

    from reverbscope.audio.fake import FakeBackend
    from reverbscope.errors import MeasurementCancelledError

    release = threading.Event()
    real = FakeBackend.play_and_record
    takes: list[tuple[QThread, threading.Event | None]] = []

    def held(self, *args, cancel=None, **kwargs):  # type: ignore[no-untyped-def]
        takes.append((QThread.currentThread(), cancel))
        while not release.wait(0.01):
            if cancel is not None and cancel.is_set():
                raise MeasurementCancelledError("stopped")
        return real(self, *args, cancel=cancel, **kwargs)

    monkeypatch.setattr(FakeBackend, "play_and_record", held)
    yield release
    for thread, cancel in takes:
        if cancel is not None:
            cancel.set()
        else:
            release.set()
        thread.wait()


def _take_request(window: WorkbenchWindow, short_sweep: SweepSettings):  # type: ignore[no-untyped-def]
    from reverbscope.ui.measure_dialog import StandaloneMeasureDialog

    dialog = StandaloneMeasureDialog(
        window, profile="generic", backend="fake", room="Booth", position="A"
    )
    dialog.sample_rate.setCurrentIndex(dialog.sample_rate.findData(short_sweep.sample_rate))
    dialog.duration.setValue(short_sweep.duration_s)
    dialog.run_button.click()
    request = dialog.request()
    dialog.close()
    assert request is not None
    return request


def test_a_take_runs_with_stop_in_the_status_line_and_adds_a_measurement(
    app: QApplication, fake_backend: None, held_take: threading.Event, short_sweep: SweepSettings
) -> None:
    window = WorkbenchWindow()
    window.show()
    request = _take_request(window, short_sweep)
    assert window.measurements.start_take(request)
    _settle(app, rounds=5)
    assert window.run_status.isVisible() and window.run_status.stop_button.isVisible()
    assert window.stop_action.isEnabled()
    assert not window.measure_action.isEnabled()
    # Stop from the status line ends the take; nothing is added.
    window.run_status.stop_button.click()
    _settle(app, window.measurements.take_worker)
    assert len(window.document) == 0
    assert not window.run_status.stop_button.isVisible()
    assert window.measure_action.isEnabled()
    # A second take runs to the end and joins the list, selected and drawn.
    assert window.measurements.start_take(_take_request(window, short_sweep))
    held_take.set()
    _settle(app, window.measurements.take_worker)
    _settle(app, window.measurements.analysis_worker, rounds=20)
    assert len(window.document) == 1
    measurement = window.document.selected()
    assert measurement is not None
    assert measurement.synthetic and not measurement.unsaved_take
    assert measurement.session.mode == "synthetic_demo"
    assert _lines(window, 0)
    window.close()


def test_a_live_take_is_protected_saved_and_reopened(
    app: QApplication,
    tmp_path: Path,
    short_sweep: SweepSettings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window = WorkbenchWindow()
    window.show()
    recording = synthetic_recording(short_sweep, make_rir(short_sweep.sample_rate, rt60_s=0.3))
    result = analyze(recording, Reference.from_settings(short_sweep))
    live = Measurement(
        session=MeasurementSession(room_name="Booth", measurement_position="A", mode="standalone"),
        result=result,
        recording=recording,
        unsaved_take=True,
    )
    identifier = window.document.add(live)
    _settle(app)
    assert "*" in window.windowTitle()
    # Closing asks; Cancel keeps the window and the take.
    asked: list[str] = []

    def cancel(self: QMessageBox) -> int:  # type: ignore[override]
        asked.append("cancel")
        return 0

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(QMessageBox, "exec", cancel)
        window.close()
        app.processEvents()
    assert asked == ["cancel"] and window.isVisible()
    assert len(window.document) == 1

    # Saving writes the recording with the session; the take is then on disk.
    target = tmp_path / "booth-a"
    assert window.controller.save_to(identifier, target)
    saved = window.document.get(identifier)
    assert saved is not None and saved.path == target and not saved.unsaved_take
    assert (target / "recording.wav").exists()
    assert load_session(target).recording_path
    assert "*" not in window.windowTitle()
    window.close()

    reopened = WorkbenchWindow()
    reopened.show()
    measurement = reopened.controller.open_session(target)
    _settle(app)
    assert measurement is not None and measurement.name() == "Booth / A"
    assert measurement.result.decay.broadband.rt60_estimate_s == pytest.approx(
        result.decay.broadband.rt60_estimate_s
    )
    # Opening it again selects the open one instead of adding a copy.
    assert reopened.controller.open_session(target) is measurement
    assert len(reopened.document) == 1
    reopened.close()


def test_export_writes_csv_and_png(
    app: QApplication, tmp_path: Path, short_sweep: SweepSettings, monkeypatch: pytest.MonkeyPatch
) -> None:
    from PySide6.QtWidgets import QFileDialog

    from reverbscope.ui import export as export_module

    window = WorkbenchWindow()
    window.show()
    window.document.add(_measurement(short_sweep))
    _settle(app)
    out = tmp_path / "out"
    out.mkdir()
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **k: str(out))
    window.export_csv()
    assert list(out.glob("*.csv"))
    png = tmp_path / "chart.png"
    monkeypatch.setattr(export_module, "ask_save_path", lambda *a, **k: png)
    window.export_png()
    assert png.exists() and png.stat().st_size > 0
    window.close()


# --- 6. theme and small windows --------------------------------------------------------


def test_a_theme_switch_recolours_the_charts(
    app: QApplication, short_sweep: SweepSettings, monkeypatch: pytest.MonkeyPatch
) -> None:
    from reverbscope.ui.theme import DARK_TOKENS, LIGHT_TOKENS

    monkeypatch.setenv("REVERBSCOPE_COLOR_SCHEME", "light")
    window = WorkbenchWindow()
    window.show()
    window.document.add(_measurement(short_sweep))
    _settle(app)
    assert window.panels[0].figure.get_facecolor()[:3] == pytest.approx(
        _rgb(LIGHT_TOKENS["surface"]), abs=0.01
    )
    monkeypatch.setenv("REVERBSCOPE_COLOR_SCHEME", "dark")
    window.restyle()
    _settle(app)
    assert window.panels[0].figure.get_facecolor()[:3] == pytest.approx(
        _rgb(DARK_TOKENS["surface"]), abs=0.01
    )
    window.close()


def _rgb(colour: str) -> tuple[float, float, float]:
    value = colour.lstrip("#")
    return tuple(int(value[i : i + 2], 16) / 255.0 for i in (0, 2, 4))  # type: ignore[return-value]


def test_the_layout_works_at_the_minimum_size_and_resets(
    app: QApplication, short_sweep: SweepSettings
) -> None:
    window = WorkbenchWindow()
    window.resize(960, 640)
    window.show()
    window.document.add(_measurement(short_sweep))
    _settle(app)
    assert window.list_dock.isVisible()
    assert window.measure_action.isEnabled() and window.save_action.isEnabled()
    assert window.panels[0].width() > 0 and window.panels[0].canvas.width() >= 400
    window.set_dual(False)
    assert not window.panels[1].isVisible()
    window.panels[0].set_kind("noise")
    window.reset_layout()
    _settle(app)
    assert window.panels[1].isVisible()
    assert [panel.kind() for panel in window.panels] == ["frequency", "decay"]
    window.close()


# --- 7. lifecycle: late results, stale jobs, closing during a run ---------------------------


def test_a_result_after_the_window_closed_is_dropped(
    app: QApplication,
    fake_backend: None,
    held_take: threading.Event,
    short_sweep: SweepSettings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from reverbscope.ui.controller import WorkspaceController

    asked: list[int] = []
    monkeypatch.setattr(
        WorkspaceController, "ask_to_stop_running", lambda self: asked.append(1) or True
    )
    window = WorkbenchWindow()
    window.show()
    assert window.measurements.start_take(_take_request(window, short_sweep))
    _settle(app, rounds=3)
    # Closing asks about the running take, stops it and waits for the
    # thread: no abort, no other dialog.
    window.close()
    assert asked == [1]
    _settle(app, window.measurements.take_worker)
    assert len(window.document) == 0
    assert not window.isVisible()


def test_a_second_take_during_a_take_is_refused(
    app: QApplication, fake_backend: None, held_take: threading.Event, short_sweep: SweepSettings
) -> None:
    window = WorkbenchWindow()
    window.show()
    request = _take_request(window, short_sweep)
    assert window.measurements.start_take(request)
    assert not window.measurements.start_take(request)
    assert window.measurements.is_busy()
    window.measurements.stop()
    _settle(app, window.measurements.take_worker)
    assert not window.measurements.is_busy()
    window.close()


def test_a_synthetic_session_keeps_its_marker(
    app: QApplication, tmp_path: Path, short_sweep: SweepSettings
) -> None:
    from reverbscope.demo import DEMO_MODE

    session = MeasurementSession(
        mode=DEMO_MODE, room_name="Synthetic demo room", measurement_position="A"
    )
    save_measurement(tmp_path / "demo", session, _result(short_sweep), copy_recording=False)
    window = WorkbenchWindow()
    window.show()
    measurement = window.controller.open_session(tmp_path / "demo")
    _settle(app)
    assert measurement is not None and measurement.synthetic
    role = window.list_model.data(
        window.list_model.index_for(measurement.id).siblingAtColumn(2), Qt.ItemDataRole.DisplayRole
    )
    assert "synthetic" in str(role)
    window.set_inspector_visible(True)
    _settle(app)
    assert "synthetic" in window.inspector.header_text().lower()
    window.close()


# --- 8. projects and saving beside open measurements ----------------------------------


def test_a_session_opened_beside_a_project_is_not_a_member(
    app: QApplication, tmp_path: Path, short_sweep: SweepSettings
) -> None:
    """Only the sessions a project lists belong to it: one opened with Open
    Session while the project is open stays outside its overview."""
    from reverbscope.io.project_store import add_session, save_project
    from reverbscope.models.project import Project

    room = tmp_path / "room"
    listed = _saved(room, short_sweep, "A-1")
    save_project(room, Project(name="Room"))
    add_session(room, listed, position="A")
    foreign = _saved(tmp_path / "other", short_sweep, "hall", rt60_s=0.5)
    window = WorkbenchWindow()
    window.show()
    assert window.controller.open_project(room)
    member = window.document.find_by_path(listed)
    assert member is not None and member.project == room
    outside = window.controller.open_session(foreign)
    assert outside is not None and outside.project is None
    overview = window.controller.project_overview("generic")
    assert overview is not None
    assert [p.label for p in overview.positions] == ["A"]
    assert window.controller.position_labels() == ["A"]
    window.close()


def test_saving_over_the_folder_of_an_open_session_closes_the_stale_copy(
    app: QApplication, tmp_path: Path, short_sweep: SweepSettings
) -> None:
    """After a take is saved into a folder another open measurement came
    from, the folder has one owner: the stale in-memory copy is closed."""
    folder = _saved(tmp_path, short_sweep, "A")
    window = WorkbenchWindow()
    window.show()
    stale = window.controller.open_session(folder)
    assert stale is not None
    fresh_id = window.document.add(_measurement(short_sweep, position="A", rt60_s=0.5))
    assert window.controller.save_to(fresh_id, folder)
    assert window.document.get(stale.id) is None
    fresh = window.document.get(fresh_id)
    assert fresh is not None and fresh.path == folder and not fresh.unsaved
    assert window.document.find_by_path(folder) is fresh
    assert window.controller.open_session(folder) is fresh
    assert window.document.selected_id() == fresh_id
    window.close()
