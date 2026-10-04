"""Offscreen smoke test of the GUI: build the window, run a DAW-mode analysis, save a session."""

from __future__ import annotations

import math
import os
from pathlib import Path

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from roomscope.core.pipeline import synthetic_recording
from roomscope.io.wav import write_wav
from roomscope.models.configuration import SweepSettings
from roomscope.ui.main_window import MainWindow
from tests.conftest import make_rir

pytestmark = pytest.mark.gui


def test_pyside6_version_is_visible_to_matplotlib() -> None:
    from roomscope.ui.qt import ensure_pyside6

    ensure_pyside6()
    import PySide6

    assert PySide6.__version__
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg

    assert FigureCanvasQTAgg is not None


@pytest.fixture(scope="module")
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_daw_mode_end_to_end(app: QApplication, tmp_path: Path, short_sweep: SweepSettings) -> None:
    window = MainWindow()
    window.show()
    window.show_mode("universal_daw")
    assert window.stack.currentWidget() is window.daw

    page = window.daw
    page.sample_rate.setCurrentIndex(page.sample_rate.findData(short_sweep.sample_rate))
    page.duration.setValue(short_sweep.duration_s)
    page.generate_sweep_to(tmp_path / "sweep.wav")
    assert (tmp_path / "sweep.roomscope-sweep.json").is_file()
    assert window.state.reference is not None

    ir = make_rir(
        short_sweep.sample_rate, rt60_s=0.35, reflections=[(0.018, 0.35)], diffuse_level=0.01
    )
    recording = synthetic_recording(window.state.sweep_settings, ir, noise_rms=1e-5)
    rec_path = write_wav(
        tmp_path / "recording.wav", recording.samples, recording.sample_rate, subtype="FLOAT"
    )
    page.set_recording(rec_path)
    assert page.channel.count() == 2
    page.room.setText("Booth A")

    page.start_analysis(blocking=True)
    app.processEvents()
    assert window.state.result is not None
    assert window.stack.currentWidget() is window.results
    assert "RoomScope analysis" in window.results.text.toPlainText()
    assert window.results.table.rowCount() == 1 + len(window.state.result.decay.bands)
    assert window.state.findings

    out = tmp_path / "session"
    window.results.save_to(out)
    assert (out / "session.json").is_file()
    assert (out / "impulse_response.wav").is_file()
    assert "saved" in window.results.status.text()

    window.show_home()
    assert window.state.result is None
    window.close()


def test_reopen_saved_session(
    app: QApplication, tmp_path: Path, short_sweep: SweepSettings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ROOMSCOPE_HOME", str(tmp_path / "home"))
    window = MainWindow()
    window.show()
    window.show_mode("universal_daw")
    page = window.daw
    page.sample_rate.setCurrentIndex(page.sample_rate.findData(short_sweep.sample_rate))
    page.duration.setValue(short_sweep.duration_s)
    page.generate_sweep_to(tmp_path / "sweep.wav")
    ir = make_rir(
        short_sweep.sample_rate, rt60_s=0.35, reflections=[(0.018, 0.35)], diffuse_level=0.01
    )
    recording = synthetic_recording(window.state.sweep_settings, ir, noise_rms=1e-5)
    rec_path = write_wav(
        tmp_path / "recording.wav", recording.samples, recording.sample_rate, subtype="FLOAT"
    )
    page.set_recording(rec_path)
    page.room.setText("Booth A")
    page.profile.setCurrentIndex(page.profile.findData("vocal"))
    assert page.profile.currentText() == "Vocals"
    page.start_analysis(blocking=True)
    app.processEvents()
    out = tmp_path / "session"
    window.results.save_to(out)
    saved_rt60 = window.state.result.decay.broadband.rt60_estimate_s
    assert window.state.session.recording_profile == "vocal"

    window.show_home()
    assert window.state.result is None
    window.home.refresh_recent()
    assert window.home.recent.count() == 1
    assert "Booth A" in window.home.recent.item(0).text()

    window.home.list_folder(tmp_path)
    assert window.home.recent.count() == 1
    assert "Booth A" in window.home.recent.item(0).text()

    window.open_session_path(out)
    app.processEvents()
    assert window.stack.currentWidget() is window.results
    assert window.state.result is not None
    assert window.state.session.room_name == "Booth A"
    assert window.state.profile == "vocal"
    assert window.state.result.decay.broadband.rt60_estimate_s == saved_rt60
    assert window.state.result.impulse_response.samples.size > 0
    assert "RoomScope analysis" in window.results.text.toPlainText()
    assert "Interpretation (Vocals profile)" in window.results.text.toPlainText()
    window.results._copy_report()
    assert app.clipboard().text() == window.results.text.toPlainText()
    assert window.results.status.text()
    window.close()


def test_main_window_actions_have_shortcuts(app: QApplication) -> None:
    from PySide6.QtGui import QAction

    window = MainWindow()
    shortcuts = {
        action.shortcut().toString()
        for action in window.findChildren(QAction)
        if not action.shortcut().isEmpty()
    }
    for needed in ("Ctrl+N", "Ctrl+O", "Ctrl+Shift+C", "Ctrl+,", "Ctrl+1", "Ctrl+2", "Ctrl+3"):
        assert needed in shortcuts, shortcuts
    from PySide6.QtWidgets import QLabel

    from roomscope.ui.widgets import shortcut_badge

    badges = sorted(
        child.text()
        for child in window.home.findChildren(QLabel)
        if child.property("role") == "badge"
    )
    expected = sorted(shortcut_badge(sequence) for sequence in ("Ctrl+1", "Ctrl+2", "Ctrl+3"))
    assert badges == expected
    assert "Home" in window.statusBar().currentMessage()
    assert window.daw.analyze_button.shortcut().toString() == "Ctrl+Return"
    assert window.standalone.stop_button.shortcut().toString() == "Esc"
    assert window.results.save_button.shortcut().toString() == "Ctrl+S"
    window.close()


def test_standalone_page_builds(app: QApplication) -> None:
    window = MainWindow()
    window.show_mode("standalone")
    assert window.stack.currentWidget() is window.standalone
    # Either devices were listed or the backend is reported unavailable; both are acceptable.
    assert window.standalone.status.text()
    window.close()


def test_demo_mode_uses_fake_backend(app: QApplication) -> None:
    window = MainWindow()
    window.show()
    window.show_mode("demo")
    app.processEvents()
    assert window.stack.currentWidget() is window.standalone
    assert window.standalone.demo_mode is True
    assert not window.standalone.demo_banner.isHidden()
    assert window.standalone.stop_button is not None
    assert "fake" in window.standalone.status.text().lower()
    window.close()


def test_settings_dialog_saves(
    app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ROOMSCOPE_HOME", str(tmp_path / "home"))
    from roomscope.settings import load_settings
    from roomscope.ui.settings_dialog import SettingsDialog

    window = MainWindow()
    window.show()
    dialog = SettingsDialog(window)
    dialog.language.setCurrentIndex(dialog.language.findData("zh_CN"))
    dialog.copy_recording.setChecked(False)
    dialog.accept()
    loaded = load_settings()
    assert loaded.language == "zh_CN"
    assert loaded.copy_recording is False
    from roomscope.i18n import activate

    activate("en")
    window.close()


def test_placement_tab_uses_tape_measurements(
    app: QApplication, tmp_path: Path, short_sweep: SweepSettings
) -> None:
    from roomscope.core.placement import DEFAULT_TEMPERATURE_C, speed_of_sound_m_s

    source_height, mic_height, horizontal, ceiling = 1.20, 0.40, 1.44, 3.20
    speed = speed_of_sound_m_s(DEFAULT_TEMPERATURE_C)
    distance = math.hypot(source_height - mic_height, horizontal)

    def plane(near: float, far: float) -> tuple[float, float]:
        path = math.hypot(near + far, horizontal)
        return (path - distance) / speed, 0.7 * distance / path

    window = MainWindow()
    window.show()
    window.show_mode("universal_daw")
    page = window.daw
    page.sample_rate.setCurrentIndex(page.sample_rate.findData(short_sweep.sample_rate))
    page.duration.setValue(short_sweep.duration_s)
    page.generate_sweep_to(tmp_path / "sweep.wav")
    page.placement.distance.setValue(distance)
    page.placement.mic_height.setValue(mic_height)
    page.placement.temperature_measured.setChecked(True)
    page.placement.temperature.setValue(DEFAULT_TEMPERATURE_C)
    ir = make_rir(
        short_sweep.sample_rate,
        rt60_s=0.35,
        reflections=[
            plane(source_height, mic_height),
            plane(ceiling - source_height, ceiling - mic_height),
        ],
        diffuse_level=0.004,
        length_s=0.6,
    )
    recording = synthetic_recording(window.state.sweep_settings, ir, noise_rms=1e-4)
    rec_path = write_wav(
        tmp_path / "recording.wav", recording.samples, recording.sample_rate, subtype="FLOAT"
    )
    page.set_recording(rec_path)
    page.start_analysis(blocking=True)
    app.processEvents()
    assert window.state.result is not None
    placement = window.state.result.placement
    assert placement is not None
    assert placement.tier == 2
    assert window.results.tabs.tabText(window.results.tabs.count() - 1) == "Placement"
    summary = window.results.place_tab.summary.text()
    assert "tier 2" in summary.lower()
    assert window.results.place_tab.table.rowCount() == 3
    height_item = window.results.place_tab.table.item(0, 1)
    assert height_item is not None
    assert "m" in height_item.text()
    assert window.state.analysis_settings.placement_distance_m == pytest.approx(distance, abs=0.01)
    window.close()


def test_compare_two_saved_sessions(
    app: QApplication, tmp_path: Path, short_sweep: SweepSettings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ROOMSCOPE_HOME", str(tmp_path / "home"))
    window = MainWindow()
    window.show()
    window.show_mode("universal_daw")
    page = window.daw
    page.sample_rate.setCurrentIndex(page.sample_rate.findData(short_sweep.sample_rate))
    page.duration.setValue(short_sweep.duration_s)
    page.generate_sweep_to(tmp_path / "sweep.wav")
    ir = make_rir(
        short_sweep.sample_rate, rt60_s=0.35, reflections=[(0.018, 0.35)], diffuse_level=0.01
    )
    recording = synthetic_recording(window.state.sweep_settings, ir, noise_rms=1e-5)
    rec_path = write_wav(
        tmp_path / "recording.wav", recording.samples, recording.sample_rate, subtype="FLOAT"
    )
    page.set_recording(rec_path)
    page.start_analysis(blocking=True)
    app.processEvents()
    first = tmp_path / "session-a"
    window.results.save_to(first)
    window.show_home()
    window.show_mode("universal_daw")
    page = window.daw
    page.sample_rate.setCurrentIndex(page.sample_rate.findData(short_sweep.sample_rate))
    page.duration.setValue(short_sweep.duration_s)
    page.generate_sweep_to(tmp_path / "sweep2.wav")
    page.set_recording(rec_path)
    page.start_analysis(blocking=True)
    app.processEvents()
    second = tmp_path / "session-b"
    window.results.save_to(second)

    window.show_compare()
    assert window.stack.currentWidget() is window.compare
    window.compare.set_paths(first, second)
    window.compare.same_gain.setChecked(True)
    window.compare.run_compare()
    app.processEvents()
    assert "RoomScope comparison" in window.compare.text.toPlainText()
    assert window.compare.table.rowCount() > 0
    assert window.compare.reflections.columnCount() == 4
    assert window.compare.resonances.columnCount() == 4
    assert window.compare.resonances.horizontalHeaderItem(3).text()
    assert window.compare._comparison is not None
    assert window.compare.resonances.rowCount() == len(window.compare._comparison.resonances)
    assert all(item.validity is not None for item in window.compare._comparison.decay)
    window.close()


def test_standalone_shows_requested_and_device_rate(app: QApplication) -> None:
    window = MainWindow()
    window.show_mode("demo")
    app.processEvents()
    page = window.standalone
    assert "48000" in page.device_rate.text()
    page.sample_rate.setCurrentIndex(page.sample_rate.findData(44100))
    app.processEvents()
    label = page.device_rate.text()
    assert "44100" in label
    assert "48000" in label
    assert "requested" in label
    # The same pre-flight as roomscope measure: resolved devices, real channels.
    # "System default" stays selected: PortAudio's default devices are used.
    assert page._preflight([1], 48000) == (None, None)
    window.close()


def test_help_licenses_and_report_heading(app: QApplication) -> None:
    from roomscope.ui.main_window import license_notice_path

    notice = license_notice_path()
    assert notice is not None
    assert notice.name in {"DEPENDENCIES.md", "THIRD_PARTY_LICENSES"}
    window = MainWindow()
    texts = [
        action.text()
        for menu in (action.menu() for action in window.menuBar().actions() if action.menu())
        for action in menu.actions()
    ]
    assert any("license" in text.lower() or "许可" in text for text in texts)
    # Diagnostics are shown in the interface language now; the heading names
    # the CLI command that prints the same report.
    assert "roomscope analyze" in window.results.diagnostics_heading.text()
    window.close()


def test_gui_smoke_flag_constructs_and_exits(app: QApplication) -> None:
    from roomscope.cli.main import main
    from roomscope.ui.app import run_app

    assert run_app(smoke=True) == 0
    assert main(["gui", "--smoke"]) == 0


def test_developer_menu_and_device_inspector(
    app: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ROOMSCOPE_EDITION", "developer")
    from roomscope.ui.dev_tools import DeviceInspector, EnvironmentReport

    window = MainWindow()
    assert window.developer_menu is not None
    assert not window.standalone.advanced.isHidden() or not window.isVisible()
    inspector = DeviceInspector("fake", window)
    assert inspector.table.rowCount() == 1
    inspector.refresh(probe=True)
    assert "48000" in inspector.table.item(0, 6).text()
    inspector.copy_json()
    report = EnvironmentReport("fake", window)
    assert "RoomScope" in report.text.toPlainText()
    assert "not probed" in report.text.toPlainText()
    report.refresh(probe=True)
    assert "record 44100, 48000" in report.text.toPlainText()
    window.close()


def test_user_edition_hides_developer_tools(
    app: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ROOMSCOPE_EDITION", "user")
    window = MainWindow()
    assert window.developer_menu is None
    assert window.standalone.advanced.isHidden()
    # The environment report is for everyone who files a bug.
    assert window.report_action.isEnabled()
    window.close()


def test_standalone_host_api_filter_and_options(app: QApplication) -> None:
    window = MainWindow()
    window.show_mode("demo")
    page = window.standalone
    assert page.host_api.count() >= 1
    # The fake interface is the recommended input and output.
    assert page.input_device.currentText().startswith("★") or page.host_api.currentData() is None
    options = page.stream_options()
    assert options.is_default
    window.close()


def test_standalone_preselects_the_system_default_devices(
    app: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Review finding: on a Mac every Core Audio device is its own starred
    entry, so the page preselected the lowest index, a virtual BlackHole
    device, instead of the microphone and speakers the system uses."""
    from roomscope.audio import backend as backend_module
    from roomscope.audio import inventory as inventory_module
    from roomscope.audio.backend import DeviceInfo

    devices = [
        DeviceInfo(0, "BlackHole 2ch", "Core Audio", 2, 2, 48000.0, False, False),
        DeviceInfo(1, "MacBook Pro Microphone", "Core Audio", 1, 0, 48000.0, True, False),
        DeviceInfo(2, "MacBook Pro Speakers", "Core Audio", 0, 2, 48000.0, False, True),
    ]

    class Mac:
        name = "test"

        def list_devices(self) -> list[DeviceInfo]:
            return devices

        def check_sample_rate(self, *args: object, **kwargs: object) -> None:
            return None

    real_build = inventory_module.build_inventory
    monkeypatch.setattr(backend_module, "get_backend", lambda name=None: Mac())
    monkeypatch.setattr(
        inventory_module,
        "build_inventory",
        lambda backend, **kwargs: real_build(backend, probe_rates=False, platform="darwin"),
    )
    window = MainWindow()
    page = window.standalone
    page.refresh_devices()
    assert page.host_api.currentData() is None
    assert page.input_device.currentData() is None
    assert page.output_device.currentData() is None
    # Choosing the host API preselects its default devices, not the first star.
    page.host_api.setCurrentIndex(page.host_api.findData("Core Audio"))
    assert page.input_device.currentData() == 1
    assert page.output_device.currentData() == 2
    window.close()


def test_charts_draw_chinese_text_with_an_installed_cjk_font() -> None:
    """Chart titles are translated; DejaVu Sans alone has no Chinese glyphs
    and matplotlib drew them as empty boxes (seen in the zh-CN compare page)."""
    import warnings

    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure

    from roomscope.ui.theme import CJK_FALLBACK_FONTS, configure_matplotlib, font_families

    families = font_families()
    assert families[0] == "DejaVu Sans"
    if len(families) == 1:
        pytest.skip(f"none of {CJK_FALLBACK_FONTS} is installed on this machine")
    configure_matplotlib()
    figure = Figure()
    FigureCanvasAgg(figure)  # a bare Figure's canvas does not render
    figure.add_subplot(111).set_title("频率响应差异（候选 − 基线）")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        figure.canvas.draw()
    assert not [w for w in caught if "missing from font" in str(w.message)]


def test_compare_metrics_have_readable_names() -> None:
    """The compare table showed ids such as ``band.63 Hz.t20`` and ``not_comparable``."""
    from roomscope.models.result import Validity
    from roomscope.ui.compare_view import metric_label, status_text
    from roomscope.ui.results import validity_text

    assert metric_label("broadband.t30", "s") == "Broadband T30 (s)"
    assert metric_label("band.63 Hz.rt60_estimate", "s") == "63 Hz RT60 estimate (s)"
    assert metric_label("band.63 Hz") == "63 Hz"
    assert metric_label("noise.rms_dbfs", "dBFS") == "Background noise, RMS (dBFS)"
    assert metric_label("loopback.path_delay_ms", "ms") == "Loopback path delay (ms)"
    assert metric_label("something.new") == "something.new"
    assert status_text("appeared") == "appeared"
    assert validity_text(Validity.NOT_COMPARABLE) == ("not comparable", "warn")
    assert validity_text(Validity.OUTSIDE_EXCITATION)[0] == "outside the sweep's range"


@pytest.fixture
def held_take(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    """The fake interface plays until the test releases it (or Stop is pressed)."""
    import threading

    from PySide6.QtCore import QThread

    from roomscope.audio.fake import FakeBackend
    from roomscope.errors import MeasurementCancelledError

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
    # A test that fails mid-take never reaches window.close(): stop the take
    # and wait for it, or Qt aborts the whole run on a QThread destroyed
    # while it is still running.
    for thread, cancel in takes:
        if cancel is not None:
            cancel.set()
        else:
            release.set()
        thread.wait()


def test_a_running_take_cannot_be_replaced_and_closing_waits_for_it(
    app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, held_take
) -> None:
    """Refresh devices (button, Ctrl+2, Back -> Demo) re-enabled Run during a
    take; a second Run dropped the only reference to the running QThread and
    the process aborted. Closing the window mid-take aborted it too."""
    monkeypatch.setenv("ROOMSCOPE_HOME", str(tmp_path / "home"))
    window = MainWindow()
    window.show()
    window.show_mode("demo")
    app.processEvents()
    page = window.standalone
    page.duration.setValue(1.0)
    page.run_button.click()
    first = page._measure_worker
    assert first is not None and first.isRunning()
    assert not page.back_button.isEnabled()
    page.refresh_devices()
    assert not page.run_button.isEnabled()
    page.start_measurement()  # the Run shortcut while busy
    assert page._measure_worker is first
    window.close()
    assert not first.isRunning()


def test_opening_a_session_forgets_the_previous_take(
    app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, short_sweep: SweepSettings
) -> None:
    """Saving the opened session wrote the earlier take as its recording.wav."""
    import numpy as np

    from roomscope.core.pipeline import Reference, analyze
    from roomscope.io.session_store import save_measurement
    from roomscope.models.audio import AudioSignal
    from roomscope.models.session import MeasurementSession

    monkeypatch.setenv("ROOMSCOPE_HOME", str(tmp_path / "home"))
    recording = synthetic_recording(short_sweep, make_rir(48000, rt60_s=0.3), noise_rms=1e-5)
    result = analyze(recording, Reference.from_settings(short_sweep))
    folder = tmp_path / "studio-a"
    save_measurement(folder, MeasurementSession(room_name="Studio A"), result, copy_recording=False)
    window = MainWindow()
    window.show()
    window.state.recording = AudioSignal(np.full(4800, 0.1), 48000)
    window.open_session_path(folder)
    assert window.state.recording is None
    assert window.state.session.room_name == "Studio A"
    window.close()


def test_a_live_take_is_saved_with_its_session(
    app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, short_sweep: SweepSettings
) -> None:
    """The live take was written to recording.wav before the rest of the
    session: a save that then failed (a full disk) had already replaced the
    recording of the session in that folder."""
    from roomscope.core.pipeline import Reference, analyze
    from roomscope.io.session_store import RECORDING_FILE, load_session
    from roomscope.io.wav import read_wav
    from roomscope.ui import results

    monkeypatch.setenv("ROOMSCOPE_HOME", str(tmp_path / "home"))
    errors: list[str] = []
    monkeypatch.setattr(
        results.QMessageBox, "critical", lambda _parent, _title, text: errors.append(text)
    )
    rate = short_sweep.sample_rate
    window = MainWindow()
    window.show()
    takes = []
    for rt60 in (0.3, 0.8):
        recording = synthetic_recording(short_sweep, make_rir(rate, rt60_s=rt60), noise_rms=1e-5)
        takes.append((recording, analyze(recording, Reference.from_settings(short_sweep))))

    folder = tmp_path / "studio"
    window.state.recording, window.state.result = takes[0]
    window.state.recording_path = None
    window.results.save_to(folder)
    assert load_session(folder).recording_path == RECORDING_FILE
    before = (folder / RECORDING_FILE).read_bytes()

    def disk_full(_fd: int) -> None:
        raise OSError(28, "No space left on device")

    window.state.recording, window.state.result = takes[1]
    monkeypatch.setattr(os, "fsync", disk_full)
    window.results.save_to(folder)
    monkeypatch.undo()
    assert errors and "No space left" in errors[0]
    assert (folder / RECORDING_FILE).read_bytes() == before

    elsewhere = tmp_path / "elsewhere"
    window.results.save_to(elsewhere)
    assert len(read_wav(elsewhere / RECORDING_FILE).samples) == len(takes[1][0].samples)
    window.close()


def test_home_selects_two_sessions_for_compare_and_settings_reach_the_gui(
    app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from PySide6.QtWidgets import QAbstractItemView

    from roomscope.settings import UserSettings, save_settings

    monkeypatch.setenv("ROOMSCOPE_HOME", str(tmp_path / "home"))
    save_settings(UserSettings(default_profile="vocal"))
    window = MainWindow()
    assert (
        window.home.browser.list.selectionMode()
        is QAbstractItemView.SelectionMode.ExtendedSelection
    )
    assert window.daw.profile.currentData() == "vocal"
    assert window.standalone.profile.currentData() == "vocal"
    window.close()


def _settle(app: QApplication, *workers: object) -> None:
    """Wait for the workers, then deliver their queued signals."""
    import time

    for worker in workers:
        if worker is not None:
            worker.wait()  # type: ignore[attr-defined]
    for _ in range(10):
        app.processEvents()
        time.sleep(0.01)


@pytest.fixture
def held_analysis(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    """The GUI's analysis waits until the test releases it."""
    import threading

    from roomscope.ui import workers

    gate = threading.Event()
    real = workers.analyze

    def held(*args, **kwargs):  # type: ignore[no-untyped-def]
        gate.wait(30)
        return real(*args, **kwargs)

    monkeypatch.setattr(workers, "analyze", held)
    yield gate
    gate.set()


def test_a_late_analysis_never_joins_a_session_opened_meanwhile(
    app: QApplication, tmp_path: Path, short_sweep: SweepSettings, held_analysis
) -> None:
    """The page only checked that it was visible when the result arrived.
    Ctrl+O then Ctrl+1 to wait for the analysis put the new take's result
    under the opened session's room, settings and recording."""
    from roomscope.core.pipeline import Reference, analyze
    from roomscope.io.session_store import save_measurement
    from roomscope.models.session import MeasurementSession

    rate = short_sweep.sample_rate
    opened = analyze(
        synthetic_recording(short_sweep, make_rir(rate, rt60_s=0.8), noise_rms=1e-5),
        Reference.from_settings(short_sweep),
    )
    folder = tmp_path / "studio-x"
    save_measurement(folder, MeasurementSession(room_name="Studio X"), opened, copy_recording=False)
    window = MainWindow()
    window.show()
    window.show_mode("universal_daw")
    page = window.daw
    page.sample_rate.setCurrentIndex(page.sample_rate.findData(rate))
    page.duration.setValue(short_sweep.duration_s)
    page.generate_sweep_to(tmp_path / "sweep.wav")
    take = synthetic_recording(window.state.sweep_settings, make_rir(rate, rt60_s=0.3))
    page.set_recording(
        write_wav(tmp_path / "take.wav", take.samples, take.sample_rate, subtype="FLOAT")
    )
    page.room.setText("Booth A")
    try:
        page.start_analysis()
        window.open_session_path(folder)  # Ctrl+O while it runs
        studio_x = window.state.result
        window.show_mode("universal_daw")  # back to the page to wait for it
    finally:
        held_analysis.set()
        _settle(app, page._worker)
    assert window.stack.currentWidget() is page
    assert window.state.session.room_name == "Studio X"
    assert window.state.result is studio_x
    assert "discarded" in page.status.text()
    assert page.analyze_button.isEnabled()
    window.close()


def test_a_late_standalone_analysis_is_not_shown_after_new_measurement(
    app: QApplication, held_analysis
) -> None:
    """Ctrl+N then Ctrl+3 during the analysis showed the take under a blank
    session without its recording, so Save wrote no recording.wav."""
    window = MainWindow()
    window.show()
    window.show_mode("demo")
    app.processEvents()
    page = window.standalone
    page.duration.setValue(1.0)
    page.room.setText("Live room")
    try:
        page.run_button.click()
        _settle(app, page._measure_worker)
        assert page._analysis_worker is not None and page._analysis_worker.isRunning()
        window.show_home()  # Ctrl+N
        window.show_mode("demo")  # Ctrl+3: back to wait for it
    finally:
        held_analysis.set()
        _settle(app, page._analysis_worker)
    assert window.stack.currentWidget() is page
    assert window.state.result is None
    assert "discarded" in page.status.text()
    assert page.run_button.isEnabled()
    window.close()


def test_the_measure_menu_does_not_switch_backend_under_a_running_take(
    app: QApplication, held_take
) -> None:
    """Ctrl+2 / Ctrl+3 on the page of a running take re-listed the devices
    and put the demo banner over a real sweep (or the reverse); the output
    channel edited during the take was saved as the one it used."""
    window = MainWindow()
    window.show()
    window.show_mode("demo")
    app.processEvents()
    page = window.standalone
    page.duration.setValue(1.0)
    page.output_channel.setValue(1)
    try:
        page.run_button.click()
        assert page.is_busy()
        window.show_mode("standalone")  # Ctrl+2 during the demo take
        assert page.demo_mode is True
        assert page.status.text() == "Playing the sweep and recording..."
        assert not page.run_button.isEnabled()
        page.output_channel.setValue(2)  # edited while the sweep plays
    finally:
        held_take.set()
        _settle(app, page._measure_worker)
        _settle(app, page._analysis_worker)
    assert window.stack.currentWidget() is window.results
    assert window.state.session.output_channel == 1
    window.close()


@pytest.mark.parametrize("mode", ["demo", "standalone"])
def test_a_take_on_the_fake_backend_is_saved_as_a_synthetic_demo(
    app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    """The desktop Demo (or Standalone Mode with the fake backend chosen in
    Settings) saved an ordinary Standalone session: nothing in its files
    said that no audio hardware was used."""
    import json

    from roomscope.demo import DEMO_MODE

    if mode == "standalone":
        # The backend Settings or ROOMSCOPE_AUDIO_BACKEND chose: no demo banner.
        monkeypatch.setenv("ROOMSCOPE_AUDIO_BACKEND", "fake")
    window = MainWindow()
    window.show()
    window.show_mode(mode)
    app.processEvents()
    page = window.standalone
    page.duration.setValue(1.0)
    page.run_button.click()
    _settle(app, page._measure_worker)
    _settle(app, page._analysis_worker)
    assert window.stack.currentWidget() is window.results
    window.results.save_to(tmp_path / "take")
    saved = json.loads((tmp_path / "take" / "session.json").read_text(encoding="utf-8"))
    assert saved["mode"] == DEMO_MODE
    assert saved["notes"].startswith("SYNTHETIC DEMO")
    window.close()


def test_the_lang_option_reaches_the_gui(
    app: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """run_app resolved the language again from settings, ROOMSCOPE_LANG and
    the system, so `roomscope --lang zh_CN gui` opened in English."""
    from roomscope.cli.main import main
    from roomscope.i18n import current_locale
    from roomscope.ui import app as app_module
    from roomscope.ui import main_window

    seen: list[str] = []

    class Spy(main_window.MainWindow):
        def __init__(self) -> None:
            super().__init__()
            seen.append(current_locale())

    monkeypatch.setattr(main_window, "MainWindow", Spy)
    # Qt's own catalog would stay installed for the tests that follow.
    monkeypatch.setattr(app_module, "install_qt_translations", lambda _app: None)
    assert main(["--lang", "zh_CN", "gui", "--smoke"]) == 0
    assert seen == ["zh_CN"]


def test_a_new_default_profile_applies_without_a_restart(
    app: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """MainWindow read the default profile once at startup: after Settings
    the mode pages kept the old one until RoomScope restarted."""
    from PySide6.QtWidgets import QDialog

    from roomscope.ui import settings_dialog

    def accept_with_profile(self: settings_dialog.SettingsDialog) -> int:
        self.profile.setCurrentIndex(self.profile.findData("vocal"))
        self.accept()
        return QDialog.DialogCode.Accepted.value

    monkeypatch.setattr(settings_dialog.SettingsDialog, "exec", accept_with_profile)
    window = MainWindow()
    assert window.daw.profile.currentData() == "generic"
    window.show_settings()
    assert window.daw.profile.currentData() == "vocal"
    assert window.standalone.profile.currentData() == "vocal"
    # Settings accepted again without a new default keep this measurement's choice.
    window.daw.profile.setCurrentIndex(window.daw.profile.findData("generic"))
    window.show_settings()
    assert window.daw.profile.currentData() == "generic"
    window.close()


def test_two_selected_sessions_compare_oldest_first(
    app: QApplication, tmp_path: Path, short_sweep: SweepSettings
) -> None:
    """The selection came in click order and the recent list is newest
    first: top row then shift-click the next made the later take the
    baseline, so every delta had the wrong sign."""
    from roomscope.core.pipeline import Reference, analyze
    from roomscope.io.recent import remember_session
    from roomscope.io.session_store import save_measurement
    from roomscope.models.session import MeasurementSession

    result = analyze(
        synthetic_recording(short_sweep, make_rir(48000, rt60_s=0.3), noise_rms=1e-5),
        Reference.from_settings(short_sweep),
    )
    # One date without a zone: it cannot be compared with an aware one as is.
    for room, created in (("before", "2026-01-01T00:00:00+00:00"), ("after", "2026-02-01")):
        session = MeasurementSession(room_name=room, created_at=created)
        save_measurement(tmp_path / room, session, result, copy_recording=False)
        remember_session(tmp_path / room)
    window = MainWindow()
    home = window.home.recent
    assert "after" in home.item(0).text() and "before" in home.item(1).text()
    home.item(0).setSelected(True)
    home.item(1).setSelected(True)
    window.show_compare()
    assert Path(window.compare.baseline_path.text()).name == "before"
    assert Path(window.compare.candidate_path.text()).name == "after"

    # The Compare page's own list, with both path fields empty.
    page = window.compare
    page.baseline_path.clear()
    page.candidate_path.clear()
    page.browser.list.item(0).setSelected(True)
    page.browser.list.item(1).setSelected(True)
    page.run_compare()
    assert Path(page.baseline_path.text()).name == "before"
    assert Path(page.candidate_path.text()).name == "after"
    window.close()


def _type_name_and_refuse_to_replace(app: QApplication, folder: Path, name: str) -> list[str]:
    """Drive the next save dialog: type ``name`` in ``folder``, answer No to
    a replace question, then cancel. Returns the questions asked."""
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QFileDialog, QLineEdit, QMessageBox

    questions: list[str] = []

    def visible(kind: type) -> list:  # type: ignore[type-arg]
        return [w for w in app.topLevelWidgets() if isinstance(w, kind) and w.isVisible()]

    def answer() -> None:
        boxes = visible(QMessageBox)
        if boxes:
            questions.append(boxes[0].text())
            boxes[0].done(QMessageBox.StandardButton.No)
        for dialog in visible(QFileDialog):
            dialog.reject()

    def type_name(attempts: int = 250) -> None:
        dialogs = visible(QFileDialog)
        if not dialogs:
            if attempts:
                QTimer.singleShot(20, lambda: type_name(attempts - 1))
            return
        dialogs[0].setDirectory(str(folder))
        dialogs[0].findChild(QLineEdit, "fileNameEdit").setText(name)
        QTimer.singleShot(100, answer)
        dialogs[0].accept()

    QTimer.singleShot(20, type_name)
    return questions


def test_saving_a_file_asks_before_replacing_it_when_the_extension_is_added(
    app: QApplication, tmp_path: Path, short_sweep: SweepSettings
) -> None:
    """The extension was added after the save dialog closed: typing
    "roomscope_sweep" silently replaced roomscope_sweep.wav (and its
    sidecar), and "comparison" an existing comparison.json."""
    from roomscope.core.compare import compare
    from roomscope.core.pipeline import Reference, analyze

    window = MainWindow()
    window.show()
    window.show_mode("universal_daw")
    page = window.daw
    page.generate_sweep_to(tmp_path / "roomscope_sweep.wav")
    sweep = (tmp_path / "roomscope_sweep.wav").read_bytes()
    page.duration.setValue(3.0)
    questions = _type_name_and_refuse_to_replace(app, tmp_path, "roomscope_sweep")
    page._choose_sweep_target()
    assert questions and "roomscope_sweep.wav" in questions[0]
    assert (tmp_path / "roomscope_sweep.wav").read_bytes() == sweep

    result = analyze(
        synthetic_recording(short_sweep, make_rir(48000, rt60_s=0.3), noise_rms=1e-5),
        Reference.from_settings(short_sweep),
    )
    (tmp_path / "comparison.json").write_text("{}", encoding="utf-8")
    window.compare._comparison = compare(result, result)
    questions = _type_name_and_refuse_to_replace(app, tmp_path, "comparison")
    window.compare._save()
    assert questions and "comparison.json" in questions[0]
    assert (tmp_path / "comparison.json").read_text(encoding="utf-8") == "{}"
    window.close()


def test_saving_over_a_saved_session_asks_first(
    app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, short_sweep: SweepSettings
) -> None:
    """Save Session opens at the default output folder; accepting it twice
    as offered replaced the first session's files without a word."""
    import json

    from PySide6.QtWidgets import QFileDialog, QMessageBox

    from roomscope.core.pipeline import Reference, analyze
    from roomscope.interpretation import interpret
    from roomscope.models.session import MeasurementSession

    folder = tmp_path / "RoomScope Sessions"
    monkeypatch.setattr(
        QFileDialog, "getExistingDirectory", staticmethod(lambda *_a, **_k: str(folder))
    )
    asked: list[str] = []
    answer = {"replace": False}

    def exec_(box: QMessageBox) -> int:
        asked.append(box.text())
        if answer["replace"]:
            next(
                button
                for button in box.buttons()
                if box.buttonRole(button) == QMessageBox.ButtonRole.AcceptRole
            ).click()
        return 0

    monkeypatch.setattr(QMessageBox, "exec", exec_)
    result = analyze(
        synthetic_recording(short_sweep, make_rir(48000, rt60_s=0.3), noise_rms=1e-5),
        Reference.from_settings(short_sweep),
    )
    window = MainWindow()

    def save(room: str) -> str:
        window.state.session = MeasurementSession(room_name=room)
        window.state.result = result
        window.state.findings = interpret(result, "generic")
        window.show_results()
        window.results._choose_save_directory()
        saved = json.loads((folder / "session.json").read_text(encoding="utf-8"))
        return str(saved["room_name"])

    assert save("Room A") == "Room A"
    assert asked == []
    assert save("Room B") == "Room A"
    assert len(asked) == 1 and str(folder) in asked[0]
    answer["replace"] = True
    assert save("Room C") == "Room C"
    window.close()
