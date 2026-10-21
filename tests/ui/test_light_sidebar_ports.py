"""Ideas from the dark polish draft (#96), re-implemented for the light sidebar
(docs/design/light-sidebar): notices that do not need the status bar, a
visible "Use as baseline", the CLI-only commands on the report, the middle
elision of the measurement name, the Run reason pinned in view, the monospace
readout, and a view bar that never draws a tab cut in half."""

from __future__ import annotations

import os
import time
from pathlib import Path, PurePosixPath, PureWindowsPath

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QApplication

from reverbscope.audio import backend as backend_module
from reverbscope.audio import inventory as inventory_module
from reverbscope.audio.backend import DeviceInfo
from reverbscope.core.pipeline import Reference, analyze, synthetic_recording
from reverbscope.io.session_store import save_measurement
from reverbscope.models.configuration import SweepSettings
from reverbscope.models.result import AnalysisResult
from reverbscope.models.session import MeasurementSession
from reverbscope.ui import theme
from reverbscope.ui.analysis_workspace import VIEW_GROUPS
from reverbscope.ui.main_window import MainWindow
from reverbscope.ui.views.report import SESSION_PLACEHOLDER, ReportView, cli_commands, shell_quote
from tests.conftest import make_rir
from tests.ui._metrics import wide_offscreen_latin

pytestmark = pytest.mark.gui


@pytest.fixture(scope="module")
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _pump(app: QApplication, seconds: float = 0.0) -> None:
    end = time.monotonic() + seconds
    while True:
        app.processEvents()
        if time.monotonic() >= end:
            return
        time.sleep(0.01)


class _Interface:
    name = "test"

    def list_devices(self) -> list[DeviceInfo]:
        return [
            DeviceInfo(0, "MacBook Pro Speakers", "Core Audio", 0, 2, 48000.0, False, True),
            DeviceInfo(1, "MacBook Pro Microphone", "Core Audio", 1, 0, 48000.0, True, False),
            DeviceInfo(2, "Studio Interface 2x2", "Core Audio", 2, 2, 48000.0, False, False),
        ]

    def check_sample_rate(self, *_args: object, **_kwargs: object) -> None:
        return None


@pytest.fixture
def interface(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("REVERBSCOPE_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("REVERBSCOPE_AUDIO_BACKEND", raising=False)
    real_build = inventory_module.build_inventory
    monkeypatch.setattr(backend_module, "get_backend", lambda name=None: _Interface())
    monkeypatch.setattr(
        inventory_module,
        "build_inventory",
        lambda backend, **kw: real_build(backend, probe_rates=False, platform="darwin"),
    )


def _saved_session(root: Path, result: AnalysisResult, name: str = "B-1") -> Path:
    folder = root / "sessions with space" / name
    session = MeasurementSession(room_name="Booth", measurement_position="B")
    save_measurement(folder, session, result, copy_recording=False)
    return folder


# --- 1. notices -------------------------------------------------------------------


def test_a_notice_takes_the_subtitle_slot_then_gives_it_back(
    app: QApplication, interface: None
) -> None:
    """SPEC §6: the notice sits in the toolbar's subtitle for a few seconds and
    the status bar keeps a copy; nothing takes the focus."""
    window = MainWindow()
    window.resize(1280, 800)
    window.show()
    window.show_view("overview")
    window.set_inspector_open(False)
    _pump(app)
    bar = window.workspace
    if wide_offscreen_latin():
        window.close()
        pytest.skip("whether the title fits needs desktop Latin font metrics")
    assert bar.title_box.isVisible()
    focus = QApplication.focusWidget()
    window.statusBar().hide()  # a layout without a status bar still shows it
    bar.show_notice("Session saved to /tmp/x", timeout_ms=150)
    _pump(app)
    assert bar.subtitle_label.full_text() == "Session saved to /tmp/x"
    assert bar.subtitle_label.isVisible()
    assert bar.subtitle_label.property("notice") == "good"
    assert bar.floating_notice.isHidden()
    assert QApplication.focusWidget() is focus
    _pump(app, 0.4)
    assert bar.notice_text() == ""
    assert bar.subtitle_label.full_text() != "Session saved to /tmp/x"
    assert not bar.subtitle_label.property("notice")
    window.close()


def test_notify_reaches_the_status_bar_and_a_floating_notice_when_narrow(
    app: QApplication, interface: None
) -> None:
    window = MainWindow()
    window.resize(960, 640)
    window.show()
    window.show_view("overview")
    window.set_inspector_open(True)
    _pump(app, 0.1)
    bar = window.workspace
    assert not bar.title_box.isVisible(), "the 960 px bar has no room for the title"
    window.notify("Session saved to /tmp/narrow", "good")
    _pump(app)
    notice = bar.floating_notice
    assert notice.isVisible() and notice.message() == "Session saved to /tmp/narrow"
    assert window.statusBar().currentMessage() == "Session saved to /tmp/narrow"
    assert notice.focusPolicy() == Qt.FocusPolicy.NoFocus
    # Under the toolbar, inside the centre column, not over the sidebar.
    assert notice.geometry().top() >= bar.bar.height()
    assert bar.rect().contains(notice.geometry())
    notice.close_button.click()
    assert notice.isHidden()
    window.close()


def test_saving_says_so_through_notify(
    app: QApplication,
    interface: None,
    tmp_path: Path,
    short_sweep: SweepSettings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Save Session ends in a notice, not only in the status bar."""
    window = MainWindow()
    window.show()
    said: list[str] = []
    monkeypatch.setattr(window, "notify", lambda text, tone="good": said.append(text))
    recording = synthetic_recording(short_sweep, make_rir(short_sweep.sample_rate, rt60_s=0.3))
    result = analyze(recording, Reference.from_settings(short_sweep))
    page = window.standalone
    page.demo_mode = False
    window.state.recording = recording
    window.state.recording_path = None
    page._stale = lambda: False  # type: ignore[method-assign]
    page._on_success(result)
    window.show_results()
    assert window.save_to(tmp_path / "saved")
    assert said and str(tmp_path / "saved") in said[-1]
    window.close()


# --- 2. Use as baseline in the inspector ------------------------------------------


def test_the_inspector_offers_use_as_baseline(
    app: QApplication, interface: None, tmp_path: Path, analysed_result: AnalysisResult
) -> None:
    folder = _saved_session(tmp_path, analysed_result)
    window = MainWindow()
    window.resize(1440, 900)
    window.show()
    assert window.open_session_path(folder)
    assert window.model.wait_until_loaded()
    _pump(app)
    inspector = window.inspector
    assert window.model.baseline() is None
    assert inspector.comparison.isVisibleTo(inspector)
    assert inspector.baseline_button.isVisibleTo(inspector)
    inspector.baseline_button.click()
    current = window.model.current()
    assert current is not None and window.model.baseline_key == current.key
    _pump(app)
    assert not inspector.baseline_button.isVisibleTo(inspector)
    window.close()


# --- 3. the CLI-only commands on the report ---------------------------------------


def test_cli_commands_name_the_session_and_quote_it_per_shell() -> None:
    lines = cli_commands(PurePosixPath("/data/my room/B-1"), windows=False)
    assert lines[0] == "reverbscope export '/data/my room/B-1' --format csv"
    assert lines[1] == "reverbscope session bundle '/data/my room/B-1'"
    assert lines[2].startswith("reverbscope analyze-ir --ir ")
    assert lines[3] == "reverbscope demo"
    windows = cli_commands(PureWindowsPath(r"C:\Users\me\my room"), windows=True)
    assert windows[1] == r'reverbscope session bundle "C:\Users\me\my room"'
    assert shell_quote(r"C:\Users\me\my room", windows=True) == r'"C:\Users\me\my room"'
    assert shell_quote(r"C:\data\B-1", windows=True) == r"C:\data\B-1"
    unsaved = cli_commands(None)
    assert all(SESSION_PLACEHOLDER in line for line in unsaved[:2])


def test_every_listed_command_is_a_real_cli_command() -> None:
    """The report must not advertise a command the CLI does not have."""
    from reverbscope.cli.main import build_parser

    parser = build_parser()
    for line in cli_commands(Path("/tmp/s")):
        try:
            parser.parse_args(line.split()[1:])
        except SystemExit as exc:  # pragma: no cover - a failure is the finding
            raise AssertionError(f"not a valid command line: {line}") from exc


def test_the_report_shows_copyable_commands_for_the_current_session(
    app: QApplication, interface: None, tmp_path: Path, analysed_result: AnalysisResult
) -> None:
    folder = _saved_session(tmp_path, analysed_result)
    window = MainWindow()
    window.resize(1280, 800)
    window.show()
    assert window.open_session_path(folder)
    assert window.model.wait_until_loaded()
    window.show_view("report")
    _pump(app)
    view = window.views["report"]
    assert isinstance(view, ReportView)
    text = view.commands.toPlainText()
    assert str(folder) in text and "reverbscope demo" in text
    assert view.commands.isReadOnly() and view.commands.isVisible()
    view.copy_commands_button.click()
    assert QApplication.clipboard().text().strip() == text
    assert SESSION_PLACEHOLDER not in view.commands_hint.text()
    window.close()


# --- 4. the measurement name elides in the middle ---------------------------------


def test_the_measurement_name_elides_in_the_middle(app: QApplication, interface: None) -> None:
    from reverbscope.ui.analysis_workspace import ElidingLabel

    window = MainWindow()
    window.show()
    bar = window.workspace
    assert bar.subtitle_label.elide_mode() == Qt.TextElideMode.ElideMiddle
    assert bar.title_label.elide_mode() == Qt.TextElideMode.ElideRight
    # The same label on its own, at a width the layout cannot override.
    probe = ElidingLabel("toolbar-subtitle", mode=bar.subtitle_label.elide_mode())
    probe.resize(120, 20)
    name = "Position B · B-12 · a long room name · synthetic demo data"
    probe.set_full_text(name)
    shown = probe.text()
    assert "…" in shown
    assert shown.startswith("Pos") and shown.endswith("ta")
    assert probe.toolTip() == name
    # The sidebar list keeps its middle elision too.
    assert window.navigator.tree.textElideMode() == Qt.TextElideMode.ElideMiddle
    window.close()


# --- 5. the Run reason stays in view ----------------------------------------------


@pytest.mark.parametrize("language", ["en", "zh_CN"])
def test_the_run_reason_is_in_view_at_960_by_640(
    app: QApplication, interface: None, language: str
) -> None:
    """SPEC §8.1: the action bar is outside the scroll area, so Run, Stop and
    the reason Run is off are inside the window whatever the form holds."""
    from reverbscope.i18n import activate
    from reverbscope.ui.theme import apply_application_chrome

    activate(language)
    try:
        apply_application_chrome(app)
        window = MainWindow()
        window.resize(960, 640)
        window.show()
        window.show_mode("standalone")
        _pump(app, 0.1)
        page = window.standalone
        assert page.readiness_reason()
        if wide_offscreen_latin() and language == "en":
            return  # the pixel fit below needs desktop Latin font metrics
        visible = window.rect()
        for widget in (page.readiness, page.run_button, page.stop_button, page.back_button):
            assert widget.isVisible(), widget
            rect = widget.rect().translated(widget.mapTo(window, QPoint()))
            assert visible.contains(rect), (widget, rect, visible)
        assert page.readiness.text() == page.readiness_reason()
        # Too little room beside the buttons: the reason moves above them.
        page.action_bar.resize(360, page.action_bar.height())
        page._place_reason()
        assert page.reason_above_buttons()
        page.action_bar.resize(900, page.action_bar.height())
        page._place_reason()
        assert not page.reason_above_buttons()
        window.close()
    finally:
        activate("en")


# --- 6. monospace figures ----------------------------------------------------------


def test_readouts_use_an_installed_monospace_face(app: QApplication) -> None:
    from reverbscope.ui.plotkit import ChartPanel

    families = theme.mono_families()
    panel = ChartPanel(x_label="Frequency (Hz)", y_label="Level (dB)")
    try:
        if not families:
            assert theme.mono_font() is None
            assert not panel.readout.property("mono")
            return
        assert set(families) <= set(theme.MONO_FONTS)
        assert panel.readout.property("mono") is True
        assert panel.readout.font().families()[0] == families[0]
        tick = panel.plot_item.getAxis("bottom").style["tickFont"]
        assert tick is not None and tick.families()[0] == families[0]
        assert tick.pixelSize() == 11
    finally:
        panel.dispose()


def test_no_monospace_face_keeps_the_ui_face(
    app: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    from PySide6.QtWidgets import QLabel

    monkeypatch.setattr(theme, "mono_families", list)
    widget = QLabel("0.51 s")
    assert theme.mono_font() is None
    assert theme.apply_mono_font(widget) is False
    assert not widget.property("mono")


# --- 7. no tab is drawn cut in half -------------------------------------------------


def _cut_tabs(window: MainWindow) -> list[str]:
    bar = window.workspace
    viewport = bar.group_scroll.viewport()
    cut = []
    for button in [*bar.buttons.values(), bar.project_button]:
        if not button.isVisible():
            continue
        rect = button.rect().translated(button.mapTo(viewport, QPoint()))
        if not viewport.rect().contains(rect):
            cut.append(button.text())
    return cut


@pytest.mark.parametrize("language", ["en", "zh_CN"])
@pytest.mark.parametrize("width", [960, 1100, 1280])
def test_no_view_tab_is_cut_whichever_view_is_current(
    app: QApplication, interface: None, language: str, width: int
) -> None:
    """#97's leftover: Project current in a narrow window scrolled the bar and
    cut the leftmost group. Groups that do not fit go into "All views"."""
    from reverbscope.i18n import activate
    from reverbscope.ui.theme import apply_application_chrome

    if wide_offscreen_latin() and language == "en":
        pytest.skip("the pixel fit needs desktop Latin font metrics")
    activate(language)
    try:
        apply_application_chrome(app)
        window = MainWindow()
        window.resize(width, 640)
        window.show()
        for inspector in (False, True):
            window.set_inspector_open(inspector)
            for view_id in ("project", "report", "overview", "waterfall"):
                window.show_view(view_id)
                _pump(app)
                bar = window.workspace
                assert bar.group_scroll.horizontalScrollBar().value() == 0, view_id
                assert _cut_tabs(window) == [], (view_id, inspector)
                current = bar.project_button if view_id == "project" else None
                if current is None:
                    group = next(g for g, ids in VIEW_GROUPS if view_id in ids)
                    current = bar.buttons[group]
                assert current.isVisible() and current.isChecked(), view_id
                if bar.hidden_groups():
                    assert bar.more_button.isVisible()
        window.close()
    finally:
        activate("en")
