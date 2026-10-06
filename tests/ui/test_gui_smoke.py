"""Offscreen smoke test of the GUI: build the window, run a DAW-mode analysis, save a session."""

from __future__ import annotations

import math
import os
from pathlib import Path

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


def test_pyside6_version_is_visible_to_matplotlib() -> None:
    from reverbscope.ui.qt import ensure_pyside6

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
    assert (tmp_path / "sweep.reverbscope-sweep.json").is_file()
    assert page._reference is not None

    ir = make_rir(
        short_sweep.sample_rate, rt60_s=0.35, reflections=[(0.018, 0.35)], diffuse_level=0.01
    )
    recording = synthetic_recording(page.current_sweep_settings(), ir, noise_rms=1e-5)
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
    assert "ReverbScope analysis" in window.results.text.toPlainText()
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
    monkeypatch.setenv("REVERBSCOPE_HOME", str(tmp_path / "home"))
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
    recording = synthetic_recording(page.current_sweep_settings(), ir, noise_rms=1e-5)
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
    assert "ReverbScope analysis" in window.results.text.toPlainText()
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

    from reverbscope.ui.widgets import shortcut_badge

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
    monkeypatch.setenv("REVERBSCOPE_HOME", str(tmp_path / "home"))
    from reverbscope.settings import load_settings
    from reverbscope.ui.settings_dialog import SettingsDialog

    window = MainWindow()
    window.show()
    dialog = SettingsDialog(window)
    dialog.language.setCurrentIndex(dialog.language.findData("zh_CN"))
    dialog.copy_recording.setChecked(False)
    dialog.accept()
    loaded = load_settings()
    assert loaded.language == "zh_CN"
    assert loaded.copy_recording is False
    from reverbscope.i18n import activate

    activate("en")
    window.close()


def test_placement_tab_uses_tape_measurements(
    app: QApplication, tmp_path: Path, short_sweep: SweepSettings
) -> None:
    from reverbscope.core.placement import DEFAULT_TEMPERATURE_C, speed_of_sound_m_s

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
    recording = synthetic_recording(page.current_sweep_settings(), ir, noise_rms=1e-4)
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
    monkeypatch.setenv("REVERBSCOPE_HOME", str(tmp_path / "home"))
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
    recording = synthetic_recording(page.current_sweep_settings(), ir, noise_rms=1e-5)
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
    assert "ReverbScope comparison" in window.compare.text.toPlainText()
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
    # The same pre-flight as reverbscope measure: resolved devices, real channels.
    # "System default" stays selected: PortAudio's default devices are used.
    assert page._preflight([1], 48000) == (None, None)
    window.close()


def test_help_licenses_and_report_heading(app: QApplication) -> None:
    from reverbscope.ui.main_window import license_notice_path

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
    assert "reverbscope analyze" in window.results.diagnostics_heading.text()
    window.close()


def test_gui_smoke_flag_constructs_and_exits(app: QApplication) -> None:
    from reverbscope.cli.main import main
    from reverbscope.ui.app import run_app

    assert run_app(smoke=True) == 0
    assert main(["gui", "--smoke"]) == 0


def test_developer_menu_and_device_inspector(
    app: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("REVERBSCOPE_EDITION", "developer")
    from reverbscope.ui.dev_tools import DeviceInspector, EnvironmentReport

    window = MainWindow()
    assert window.developer_menu is not None
    assert not window.standalone.advanced.isHidden() or not window.isVisible()
    inspector = DeviceInspector("fake", window)
    assert inspector.table.rowCount() == 1
    inspector.refresh(probe=True)
    assert "48000" in inspector.table.item(0, 6).text()
    inspector.copy_json()
    report = EnvironmentReport("fake", window)
    assert "ReverbScope" in report.text.toPlainText()
    assert "not probed" in report.text.toPlainText()
    report.refresh(probe=True)
    assert "record 44100, 48000" in report.text.toPlainText()
    window.close()


def test_the_inspector_reads_unknown_for_a_device_that_could_not_be_opened(
    app: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Review finding: a busy device's rate cells were empty, as if it accepted
    none, next to a note saying its rates are unknown."""
    from dataclasses import replace

    from reverbscope.i18n import activate
    from reverbscope.ui.dev_tools import DeviceInspector

    inspector = DeviceInspector("fake")
    inspector.refresh(probe=True)
    assert inspector.inventory is not None
    device = inspector.inventory.devices[0]
    assert inspector.table.item(0, 6).text() == "44100, 48000, 88200, 96000, 176400, 192000"
    busy = replace(
        device,
        input_rates=(),
        output_rates=(),
        input_rates_known=False,
        output_rates_known=False,
    )
    inspector.inventory = replace(inspector.inventory, devices=(busy,))
    inspector._fill()
    assert [inspector.table.item(0, column).text() for column in (6, 7)] == ["unknown"] * 2
    activate("zh_CN")
    try:
        inspector._fill()
        assert [inspector.table.item(0, column).text() for column in (6, 7)] == ["未知"] * 2
    finally:
        activate("en")
    inspector.close()


def test_user_edition_hides_developer_tools(
    app: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("REVERBSCOPE_EDITION", "user")
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
    from reverbscope.audio import backend as backend_module
    from reverbscope.audio import inventory as inventory_module
    from reverbscope.audio.backend import DeviceInfo

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

    from reverbscope.ui.theme import CJK_FALLBACK_FONTS, configure_matplotlib, font_families

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
    from reverbscope.models.result import Validity
    from reverbscope.ui.compare_view import metric_label, status_text
    from reverbscope.ui.results import validity_text

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
    monkeypatch.setenv("REVERBSCOPE_HOME", str(tmp_path / "home"))
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

    from reverbscope.core.pipeline import Reference, analyze
    from reverbscope.io.session_store import save_measurement
    from reverbscope.models.audio import AudioSignal
    from reverbscope.models.session import MeasurementSession

    monkeypatch.setenv("REVERBSCOPE_HOME", str(tmp_path / "home"))
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
    from reverbscope.core.pipeline import Reference, analyze
    from reverbscope.io.session_store import RECORDING_FILE, load_session
    from reverbscope.io.wav import read_wav
    from reverbscope.ui import results

    monkeypatch.setenv("REVERBSCOPE_HOME", str(tmp_path / "home"))
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

    from reverbscope.settings import UserSettings, save_settings

    monkeypatch.setenv("REVERBSCOPE_HOME", str(tmp_path / "home"))
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

    from reverbscope.ui import workers

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
    from reverbscope.core.pipeline import Reference, analyze
    from reverbscope.io.session_store import save_measurement
    from reverbscope.models.session import MeasurementSession

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
    take = synthetic_recording(page.current_sweep_settings(), make_rir(rate, rt60_s=0.3))
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

    from reverbscope.demo import DEMO_MODE

    if mode == "standalone":
        # The backend Settings or REVERBSCOPE_AUDIO_BACKEND chose: no demo banner.
        monkeypatch.setenv("REVERBSCOPE_AUDIO_BACKEND", "fake")
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


def test_the_demo_cable_is_on_the_loopback_channel_the_box_says(
    app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Review finding: the Demo's "Loopback channel" box accepted 0-64 but the
    fake interface wired its cable to input 2 whatever was typed there, so a
    loopback on input 3 was refused as "a room" and a microphone on input 2
    analysed the cable."""
    monkeypatch.setenv("REVERBSCOPE_HOME", str(tmp_path / "home"))
    window = MainWindow()
    window.show()
    window.show_mode("demo")
    app.processEvents()
    page = window.standalone
    page.duration.setValue(1.0)

    def take() -> object:
        page.run_button.click()
        _settle(app, page._measure_worker)
        _settle(app, page._analysis_worker)
        assert window.stack.currentWidget() is window.results
        assert window.state.result is not None
        return window.state.result

    page.input_channel.setValue(1)
    page.loopback_channel.setValue(3)
    wired = take().impulse_response.loopback  # type: ignore[attr-defined]
    assert wired is not None and wired.compensation_applied
    assert window.state.session is not None and window.state.session.loopback_channel == 3

    window.show_mode("demo")
    app.processEvents()
    page.input_channel.setValue(2)
    page.loopback_channel.setValue(0)  # "unused": nothing is wired to input 2
    result = take()
    assert result.impulse_response.loopback is None  # type: ignore[attr-defined]
    # The synthetic room (RT60 0.4 s), not a cable (0.07 s).
    assert result.decay.broadband.rt60_estimate_s == pytest.approx(0.4, abs=0.1)  # type: ignore[attr-defined]
    window.close()


def test_the_lang_option_reaches_the_gui(
    app: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """run_app resolved the language again from settings, REVERBSCOPE_LANG and
    the system, so `reverbscope --lang zh_CN gui` opened in English."""
    from reverbscope.cli.main import main
    from reverbscope.i18n import current_locale
    from reverbscope.ui import app as app_module
    from reverbscope.ui import main_window

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
    the mode pages kept the old one until ReverbScope restarted."""
    from PySide6.QtWidgets import QDialog

    from reverbscope.ui import settings_dialog

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
    from reverbscope.core.pipeline import Reference, analyze
    from reverbscope.io.recent import remember_session
    from reverbscope.io.session_store import save_measurement
    from reverbscope.models.session import MeasurementSession

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


#: The latest scripted save dialog. A call that asks no question leaves its
#: 100 ms timer behind; it must not cancel the dialog of the next call.
_dialog_script: list[object] = []


def _type_name_and_refuse_to_replace(
    app: QApplication, folder: Path, name: str, *, replace: bool = False
) -> list[str]:
    """Drive the next save dialog: type ``name`` in ``folder``, answer No to
    a replace question (Replace when ``replace``), then cancel. Returns the
    questions asked."""
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QFileDialog, QLineEdit, QMessageBox

    questions: list[str] = []
    script = object()
    _dialog_script[:] = [script]

    def visible(kind: type) -> list:  # type: ignore[type-arg]
        return [w for w in app.topLevelWidgets() if isinstance(w, kind) and w.isVisible()]

    def answer() -> None:
        if _dialog_script != [script]:
            return
        boxes = visible(QMessageBox)
        if boxes:
            questions.append(boxes[0].text())
            accepting = [
                button
                for button in boxes[0].buttons()
                if boxes[0].buttonRole(button) == QMessageBox.ButtonRole.AcceptRole
            ]
            if replace and accepting:
                accepting[0].click()
            else:
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
    "reverbscope_sweep" silently replaced reverbscope_sweep.wav (and its
    sidecar), and "comparison" an existing comparison.json."""
    from reverbscope.core.compare import compare
    from reverbscope.core.pipeline import Reference, analyze

    window = MainWindow()
    window.show()
    window.show_mode("universal_daw")
    page = window.daw
    page.generate_sweep_to(tmp_path / "reverbscope_sweep.wav")
    sweep = (tmp_path / "reverbscope_sweep.wav").read_bytes()
    page.duration.setValue(3.0)
    questions = _type_name_and_refuse_to_replace(app, tmp_path, "reverbscope_sweep")
    page._choose_sweep_target()
    assert questions and "reverbscope_sweep.wav" in questions[0]
    assert (tmp_path / "reverbscope_sweep.wav").read_bytes() == sweep

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

    from reverbscope.core.pipeline import Reference, analyze
    from reverbscope.interpretation import interpret
    from reverbscope.models.session import MeasurementSession

    folder = tmp_path / "ReverbScope Sessions"
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


def _demo_take(app: QApplication, window: MainWindow, seconds: float = 1.0) -> None:
    """Run a take on the Demo page and wait until Results shows it."""
    window.show_mode("demo")
    app.processEvents()
    page = window.standalone
    page.duration.setValue(seconds)
    page.run_button.click()
    _settle(app, page._measure_worker)
    _settle(app, page._analysis_worker)
    assert window.stack.currentWidget() is window.results


def test_daw_mode_analyses_only_the_recording_it_shows(
    app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, short_sweep: SweepSettings
) -> None:
    """After a Demo take, Ctrl+1 showed "No recording selected." but Analyze
    ran on the demo's synthetic take and saved it as a Universal DAW session.
    With a recording imported first, its name stayed on the page while the
    demo take was analysed."""
    import json

    from reverbscope.io.wav import read_wav
    from reverbscope.ui import pages

    monkeypatch.setenv("REVERBSCOPE_HOME", str(tmp_path / "home"))
    refused: list[str] = []
    monkeypatch.setattr(
        pages.QMessageBox, "warning", staticmethod(lambda _p, title, _m: refused.append(title))
    )
    window = MainWindow()
    window.show()
    _demo_take(app, window)
    window.show_mode("universal_daw")  # Ctrl+1 from Results
    daw = window.daw
    assert daw.recording_label.text() == "No recording selected."
    daw.start_analysis(blocking=True)
    assert refused == ["No recording"]
    assert window.stack.currentWidget() is daw

    rate = short_sweep.sample_rate
    daw.sample_rate.setCurrentIndex(daw.sample_rate.findData(rate))
    daw.duration.setValue(short_sweep.duration_s)
    daw.generate_sweep_to(tmp_path / "sweep.wav")
    take = synthetic_recording(daw.current_sweep_settings(), make_rir(rate, rt60_s=0.3))
    take_path = write_wav(tmp_path / "daw_take.wav", take.samples, rate, subtype="FLOAT")
    daw.set_recording(take_path)
    _demo_take(app, window)
    window.show_mode("universal_daw")
    assert daw.recording_label.text().startswith("daw_take.wav")
    daw.start_analysis(blocking=True)
    assert window.stack.currentWidget() is window.results
    assert window.state.recording_path == take_path
    window.results.save_to(tmp_path / "session")
    saved = json.loads((tmp_path / "session" / "session.json").read_text(encoding="utf-8"))
    assert saved["mode"] == "universal_daw"
    copied = read_wav(tmp_path / "session" / saved["recording_path"])
    assert len(copied.samples) == len(take.samples)
    window.close()


def test_a_standalone_take_never_replaces_the_daw_reference(
    app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, short_sweep: SweepSettings
) -> None:
    """Every Standalone or Demo Run, even a refused one, replaced the shared
    reference: the Universal DAW page, still showing its Step 1 sweep, then
    deconvolved its recording with the take's shorter sweep, reported a
    time-stretched sweep and marked every decay metric unreliable."""
    import json

    from reverbscope.ui import pages

    monkeypatch.setenv("REVERBSCOPE_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(pages.QMessageBox, "critical", staticmethod(lambda *_a: None))
    rate = short_sweep.sample_rate
    window = MainWindow()
    window.show()
    window.show_mode("universal_daw")
    daw = window.daw
    daw.sample_rate.setCurrentIndex(daw.sample_rate.findData(rate))
    daw.duration.setValue(short_sweep.duration_s)
    daw.generate_sweep_to(tmp_path / "daw_sweep.wav")
    take = synthetic_recording(
        daw.current_sweep_settings(), make_rir(rate, rt60_s=0.4), noise_rms=1e-5
    )
    daw.set_recording(write_wav(tmp_path / "daw_take.wav", take.samples, rate, subtype="FLOAT"))

    window.show_mode("demo")
    window.standalone.input_channel.setValue(40)  # refused: the fake interface has 8 inputs
    window.standalone.duration.setValue(1.5)
    window.standalone.run_button.click()
    assert window.standalone._measure_worker is None
    window.standalone.input_channel.setValue(1)
    _demo_take(app, window, seconds=1.5)
    window.show_mode("universal_daw")
    assert daw.reference_label.text() == "Reference: daw_sweep.wav"
    daw.start_analysis(blocking=True)
    result = window.state.result
    assert result is not None
    assert result.sweep_settings["duration_s"] == short_sweep.duration_s
    assert result.decay.broadband.rt60_estimate_s == pytest.approx(0.4, rel=0.1)
    window.results.save_to(tmp_path / "session")
    saved = json.loads((tmp_path / "session" / "session.json").read_text(encoding="utf-8"))
    assert saved["sweep_settings"]["duration_s"] == short_sweep.duration_s
    window.close()


def test_standalone_keeps_the_chosen_devices_when_it_lists_them_again(
    app: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ctrl+2, Refresh devices or coming back from Results listed the devices
    again on "System default": the next take played and recorded through
    the computer's default devices instead of the interface chosen."""
    from reverbscope.audio import backend as backend_module
    from reverbscope.audio import inventory as inventory_module
    from reverbscope.audio.backend import DeviceInfo

    devices = [
        DeviceInfo(0, "BlackHole 2ch", "Core Audio", 2, 2, 48000.0, False, False),
        DeviceInfo(1, "MacBook Pro Microphone", "Core Audio", 1, 0, 48000.0, True, False),
        DeviceInfo(2, "Scarlett 2i2", "Core Audio", 2, 2, 48000.0, False, False),
        DeviceInfo(3, "MacBook Pro Speakers", "Core Audio", 0, 2, 48000.0, False, True),
    ]

    class Mac:
        name = "test"

        def list_devices(self) -> list[DeviceInfo]:
            return list(devices)

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
    window.show_mode("standalone")
    page = window.standalone

    def chosen() -> tuple[object, object, object]:
        return (
            page.host_api.currentData(),
            page.input_device.currentData(),
            page.output_device.currentData(),
        )

    page.host_api.setCurrentIndex(page.host_api.findData("Core Audio"))
    page.input_device.setCurrentIndex(page.input_device.findData(2))
    page.output_device.setCurrentIndex(page.output_device.findData(2))
    window.show_results()
    window.show_mode("standalone")  # Ctrl+2 from Results
    assert chosen() == ("Core Audio", 2, 2)
    page.refresh_button.click()
    assert chosen() == ("Core Audio", 2, 2)
    # Unplugged, its index taken by another device: the system's defaults.
    devices[2] = DeviceInfo(2, "USB Headset", "Core Audio", 1, 2, 48000.0, False, False)
    page.refresh_button.click()
    assert chosen() == ("Core Audio", 1, 3)
    window.close()


def test_a_new_audio_backend_in_settings_reaches_the_standalone_page(
    app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Settings changed the audio backend but the Standalone page kept the
    old backend's list: the take opened the new backend's device with the
    number chosen from the old list ("input device 0 does not support
    48000 Hz"), or a real device, while the fake interface was shown."""
    from PySide6.QtWidgets import QDialog

    from reverbscope.audio import backend as backend_module
    from reverbscope.audio import inventory as inventory_module
    from reverbscope.audio.backend import DeviceInfo
    from reverbscope.audio.fake import FakeBackend
    from reverbscope.settings import UserSettings, load_settings, save_settings
    from reverbscope.ui import pages, settings_dialog

    class Interface:
        name = "test"

        def list_devices(self) -> list[DeviceInfo]:
            return [DeviceInfo(0, "Scarlett 2i2", "Core Audio", 2, 2, 48000.0, True, True)]

        def check_sample_rate(self, *args: object, **kwargs: object) -> None:
            return None

    def backend_for(name: str | None = None) -> object:
        chosen = name or load_settings().audio_backend
        return FakeBackend() if chosen == "fake" else Interface()

    real_build = inventory_module.build_inventory
    monkeypatch.setenv("REVERBSCOPE_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("REVERBSCOPE_AUDIO_BACKEND", raising=False)
    monkeypatch.setattr(backend_module, "get_backend", backend_for)
    monkeypatch.setattr(
        inventory_module,
        "build_inventory",
        lambda backend, **kwargs: real_build(backend, probe_rates=False, platform="darwin"),
    )
    warned: list[str] = []
    monkeypatch.setattr(
        pages.QMessageBox, "warning", staticmethod(lambda _p, title, _m: warned.append(title))
    )

    def accept_with_backend(self: settings_dialog.SettingsDialog) -> int:
        self.backend.setCurrentIndex(self.backend.findData(""))
        self.accept()
        return QDialog.DialogCode.Accepted.value

    monkeypatch.setattr(settings_dialog.SettingsDialog, "exec", accept_with_backend)
    save_settings(UserSettings(audio_backend="fake"))
    window = MainWindow()
    window.show_mode("standalone")
    page = window.standalone

    def listed() -> str:
        return " ".join(page.input_device.itemText(i) for i in range(page.input_device.count()))

    assert "ReverbScope fake interface" in listed()
    window.show_settings()
    assert "Scarlett 2i2" in listed() and "fake" not in listed()

    # Changed while a take ran, the list stays until Run makes it again.
    save_settings(UserSettings(audio_backend="fake"))
    page.run_button.click()
    assert warned == ["Audio backend changed"]
    assert page._measure_worker is None
    assert "ReverbScope fake interface" in listed()
    window.close()


def test_standalone_without_any_audio_device_says_so_and_does_not_run(
    app: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With no audio device Run stayed enabled under "0 audio device(s)
    found.", and the take failed with PortAudio's English "Error querying
    device -1", also in the Chinese interface."""
    from reverbscope.audio import backend as backend_module
    from reverbscope.audio.backend import DeviceInfo

    class Silent:
        name = "test"

        def list_devices(self) -> list[DeviceInfo]:
            return []

        def check_sample_rate(self, *args: object, **kwargs: object) -> None:
            return None

    monkeypatch.setattr(backend_module, "get_backend", lambda name=None: Silent())
    window = MainWindow()
    window.show_mode("standalone")
    page = window.standalone
    assert not page.run_button.isEnabled()
    assert page.status.text() == "No audio device found; Universal DAW Mode still works."
    assert page.status.property("banner") == "warn"
    assert page.refresh_button.isEnabled()
    window.close()


def test_the_environment_report_describes_the_fake_backend_only_on_the_demo_page(
    app: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """After a Demo take, Help > Environment Report (and the device
    inspector) from Results or Compare described the fake interface
    instead of the user's hardware."""
    from reverbscope.ui import dev_tools

    described: list[str | None] = []

    class Recorder:
        def __init__(self, backend: str | None, parent: object = None) -> None:
            described.append(backend)

        def exec(self) -> int:
            return 0

    monkeypatch.setattr(dev_tools, "EnvironmentReport", Recorder)
    monkeypatch.setattr(dev_tools, "DeviceInspector", Recorder)
    window = MainWindow()
    window.show()
    window.show_mode("demo")
    window.show_environment_report()
    _demo_take(app, window)
    window.show_environment_report()
    window.show_device_inspector()
    window.show_compare()
    window.show_environment_report()
    assert described == ["fake", None, None, None]
    window.close()


def test_a_comparison_saved_from_the_app_names_its_sessions(
    app: QApplication,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    short_sweep: SweepSettings,
) -> None:
    """The desktop app saved comparison.json without baseline_session and
    candidate_session: `reverbscope show` listed neither session and read the
    report with the General profile instead of the candidate's."""
    from reverbscope.cli.main import main
    from reverbscope.core.pipeline import Reference, analyze
    from reverbscope.io.session_store import load_comparison, save_measurement
    from reverbscope.models.session import MeasurementSession
    from reverbscope.ui import compare_view

    monkeypatch.setenv("REVERBSCOPE_HOME", str(tmp_path / "home"))
    result = analyze(
        synthetic_recording(short_sweep, make_rir(48000, rt60_s=0.3), noise_rms=1e-5),
        Reference.from_settings(short_sweep),
    )
    for name in ("base", "cand"):
        session = MeasurementSession(room_name=name, recording_profile="vocal")
        save_measurement(tmp_path / name, session, result, copy_recording=False)
    target = tmp_path / "gui_comparison.json"
    monkeypatch.setattr(compare_view, "ask_save_path", lambda *_a, **_k: target)
    window = MainWindow()
    page = window.compare
    page.set_paths(tmp_path / "base", tmp_path / "cand")
    page.run_compare()
    page._save()
    saved = load_comparison(target)
    assert saved.baseline_session == str(tmp_path / "base")
    assert saved.candidate_session == str(tmp_path / "cand")
    capsys.readouterr()
    assert main(["show", str(target)]) == 0
    shown = capsys.readouterr().out
    assert str(tmp_path / "cand") in shown
    assert "Interpretation (Vocals profile)" in shown
    window.close()


def test_back_from_compare_returns_to_the_unsaved_result(
    app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Compare's Back went Home and reset the state: a take checked against
    an old session before it was saved (Results, Ctrl+Shift+C, Back) was
    gone, recording and all."""
    monkeypatch.setenv("REVERBSCOPE_HOME", str(tmp_path / "home"))
    window = MainWindow()
    window.show()
    _demo_take(app, window)
    result, recording = window.state.result, window.state.recording
    assert recording is not None and window.state.recording_path is None
    window.show_compare()
    window.compare.back.emit()
    assert window.stack.currentWidget() is window.results
    assert window.state.result is result
    assert window.state.recording is recording
    assert window.statusBar().currentMessage().endswith("Results")
    window.results.save_to(tmp_path / "take")
    assert (tmp_path / "take" / "recording.wav").is_file()

    window.show_home()
    window.show_compare()
    window.compare.back.emit()
    assert window.stack.currentWidget() is window.home
    window.close()


def test_saving_a_name_with_a_dot_asks_before_replacing_the_file_written(
    app: QApplication, tmp_path: Path, short_sweep: SweepSettings
) -> None:
    """Qt's dialog adds the extension only to a name that has none: "sweep
    2026.10.05" and "studio v1.2" were checked as typed, and the .wav or
    .json added after the dialog closed replaced an existing file (and the
    sweep's sidecar) without a question."""
    from reverbscope.core.compare import compare
    from reverbscope.core.pipeline import Reference, analyze

    window = MainWindow()
    window.show()
    window.show_mode("universal_daw")
    page = window.daw
    page.generate_sweep_to(tmp_path / "sweep 2026.10.05.wav")
    sweep = (tmp_path / "sweep 2026.10.05.wav").read_bytes()
    page.duration.setValue(3.0)
    questions = _type_name_and_refuse_to_replace(app, tmp_path, "sweep 2026.10.05")
    page._choose_sweep_target()
    assert questions == ["sweep 2026.10.05.wav already exists. Replace it?"]
    assert (tmp_path / "sweep 2026.10.05.wav").read_bytes() == sweep

    result = analyze(
        synthetic_recording(short_sweep, make_rir(48000, rt60_s=0.3), noise_rms=1e-5),
        Reference.from_settings(short_sweep),
    )
    (tmp_path / "studio v1.2.json").write_text('{"keep": true}', encoding="utf-8")
    window.compare._comparison = compare(result, result)
    questions = _type_name_and_refuse_to_replace(app, tmp_path, "studio v1.2")
    window.compare._save()
    assert questions == ["studio v1.2.json already exists. Replace it?"]
    assert (tmp_path / "studio v1.2.json").read_text(encoding="utf-8") == '{"keep": true}'

    # A new name with a dot gets the extension without a question.
    questions = _type_name_and_refuse_to_replace(app, tmp_path, "take.v2")
    page._choose_sweep_target()
    assert questions == []
    assert (tmp_path / "take.v2.wav").is_file()
    assert (tmp_path / "take.v2.reverbscope-sweep.json").is_file()
    window.close()


def test_a_confirmed_replace_writes_the_file_a_dotted_name_names(
    app: QApplication, tmp_path: Path
) -> None:
    """The question asked for "sweep 2026.10.05.wav" is a real one: Replace
    writes the sweep (and its sidecar) over the old file, as the Qt dialog's
    own question does for a name typed with its extension."""
    window = MainWindow()
    window.show()
    window.show_mode("universal_daw")
    page = window.daw
    page.generate_sweep_to(tmp_path / "sweep 2026.10.05.wav")
    old = (tmp_path / "sweep 2026.10.05.wav").read_bytes()
    page.duration.setValue(3.0)
    questions = _type_name_and_refuse_to_replace(app, tmp_path, "sweep 2026.10.05", replace=True)
    page._choose_sweep_target()
    assert questions == ["sweep 2026.10.05.wav already exists. Replace it?"]
    assert (tmp_path / "sweep 2026.10.05.wav").read_bytes() != old
    assert page.sweep_label.text().startswith("Written: sweep 2026.10.05.wav")
    window.close()


@pytest.fixture
def restore_chrome(app: QApplication):  # type: ignore[no-untyped-def]
    """Put the application's style sheet and palette back after a theme test."""
    sheet, palette = app.styleSheet(), app.palette()
    yield
    app.setStyleSheet(sheet)
    app.setPalette(palette)


def _theme_colours(window: MainWindow) -> dict[str, str]:
    """The colours each part of the window was last drawn with."""
    from matplotlib.colors import to_hex

    from reverbscope.ui.widgets import FindingCard

    cards = window.results.findChildren(FindingCard)
    assert cards
    return {
        "results chart": to_hex(window.results.ir_tab.figure.get_facecolor()),
        "compare chart": to_hex(window.compare.figure.get_facecolor()),
        "placement picture": to_hex(window.daw.placement.figure.get_facecolor()),
        "finding card": cards[-1].styleSheet(),
        "chip": window.results.overview.rt60.chip.styleSheet(),
    }


def test_a_new_theme_in_settings_redraws_cards_and_charts(
    app: QApplication,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    short_sweep: SweepSettings,
    restore_chrome: None,
) -> None:
    """Settings switched the application style sheet only: finding cards,
    chips, table colours and charts kept the old scheme, so after Light to
    Dark the findings were light text on pale cards and the charts white."""
    from PySide6.QtWidgets import QDialog

    from reverbscope.core.compare import compare
    from reverbscope.core.pipeline import Reference, analyze
    from reverbscope.interpretation import interpret
    from reverbscope.settings import UserSettings, save_settings
    from reverbscope.ui import settings_dialog
    from reverbscope.ui.theme import DARK_TOKENS, LIGHT_TOKENS, apply_application_chrome

    monkeypatch.setenv("REVERBSCOPE_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("REVERBSCOPE_COLOR_SCHEME", raising=False)
    save_settings(UserSettings(theme="light"))
    apply_application_chrome(app)

    def accept_with_theme(self: settings_dialog.SettingsDialog) -> int:
        self.theme.setCurrentIndex(self.theme.findData("dark"))
        self.accept()
        return QDialog.DialogCode.Accepted.value

    monkeypatch.setattr(settings_dialog.SettingsDialog, "exec", accept_with_theme)
    result = analyze(
        synthetic_recording(short_sweep, make_rir(48000, rt60_s=0.3), noise_rms=1e-5),
        Reference.from_settings(short_sweep),
    )
    window = MainWindow()
    window.state.result = result
    window.state.findings = interpret(result, "generic")
    window.show_results()
    window.compare._show(compare(result, result), [], "generic")
    before = _theme_colours(window)
    assert before["results chart"] == LIGHT_TOKENS["surface"]
    window.show_settings()
    after = _theme_colours(window)
    assert DARK_TOKENS["bg"] in app.styleSheet()
    for part in ("results chart", "compare chart", "placement picture"):
        assert after[part] == DARK_TOKENS["surface"], part
    assert any(DARK_TOKENS[f"{tone}_soft"] in after["finding card"] for tone in ("info", "good"))
    assert after["chip"] != before["chip"]
    window.close()


def test_following_the_system_redraws_the_window_when_the_system_turns_dark(
    app: QApplication,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    short_sweep: SweepSettings,
    restore_chrome: None,
) -> None:
    """The theme "Follow the system" was applied once at startup: when the
    system turned dark while ReverbScope ran, cards and charts drawn after
    that were dark on the still light window (dark text on dark cards)."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QGuiApplication

    from reverbscope.core.compare import compare
    from reverbscope.core.pipeline import Reference, analyze
    from reverbscope.interpretation import interpret
    from reverbscope.ui.theme import DARK_TOKENS, ENV_COLOR_SCHEME, apply_application_chrome

    monkeypatch.setenv("REVERBSCOPE_HOME", str(tmp_path / "home"))
    monkeypatch.setenv(ENV_COLOR_SCHEME, "light")
    apply_application_chrome(app)
    result = analyze(
        synthetic_recording(short_sweep, make_rir(48000, rt60_s=0.3), noise_rms=1e-5),
        Reference.from_settings(short_sweep),
    )
    window = MainWindow()
    window.state.result = result
    window.state.findings = interpret(result, "generic")
    window.show_results()
    window.compare._show(compare(result, result), [], "generic")
    # The offscreen platform cannot change its scheme: the variable stands
    # in for the system's answer, and the signal is the one Qt sends.
    monkeypatch.setenv(ENV_COLOR_SCHEME, "dark")
    QGuiApplication.styleHints().colorSchemeChanged.emit(Qt.ColorScheme.Dark)
    colours = _theme_colours(window)
    assert DARK_TOKENS["bg"] in app.styleSheet()
    for part in ("results chart", "compare chart", "placement picture"):
        assert colours[part] == DARK_TOKENS["surface"], part
    window.close()


def test_a_closed_window_stops_following_the_system(
    app: QApplication,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    restore_chrome: None,
) -> None:
    """The colour-scheme signal belongs to the application. A window that was
    closed but stayed connected still restyled the whole application on every
    system change, and each closed window made the next change slower (a test
    run with 40 of them needed over ten minutes for one signal)."""
    import warnings

    from PySide6.QtCore import Qt
    from PySide6.QtGui import QGuiApplication

    from reverbscope.ui.theme import ENV_COLOR_SCHEME, apply_application_chrome

    monkeypatch.setenv("REVERBSCOPE_HOME", str(tmp_path / "home"))
    monkeypatch.setenv(ENV_COLOR_SCHEME, "light")
    apply_application_chrome(app)
    window = MainWindow()
    restyled: list[int] = []
    monkeypatch.setattr(window, "restyle", lambda: restyled.append(1))
    monkeypatch.setenv(ENV_COLOR_SCHEME, "dark")
    # An open window follows (and the stand-in never records the new scheme,
    # so a second change would be answered again).
    QGuiApplication.styleHints().colorSchemeChanged.emit(Qt.ColorScheme.Dark)
    assert restyled == [1]
    window.close()
    QGuiApplication.styleHints().colorSchemeChanged.emit(Qt.ColorScheme.Dark)
    assert restyled == [1]
    # Closing again must not try to disconnect what is already disconnected.
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        window.close()


def test_the_measure_menu_opens_each_mode(app: QApplication) -> None:
    from PySide6.QtGui import QAction

    window = MainWindow()
    by_shortcut = {
        action.shortcut().toString(): action
        for action in window.findChildren(QAction)
        if not action.shortcut().isEmpty()
    }
    by_shortcut["Ctrl+2"].trigger()
    assert window.stack.currentWidget() is window.standalone
    assert not window.standalone.demo_mode
    by_shortcut["Ctrl+3"].trigger()
    assert window.stack.currentWidget() is window.standalone
    assert window.standalone.demo_mode
    by_shortcut["Ctrl+1"].trigger()
    assert window.stack.currentWidget() is window.daw
    window.close()


def test_a_closed_window_is_freed(app: QApplication) -> None:
    """A Measure-menu action held its window through a lambda, so a closed
    window was never freed: they piled up, and every one of them was repolished
    whenever the application's style sheet changed (about half a second each;
    a full run of this file spent most of its time on that)."""
    import gc
    import weakref

    window = MainWindow()
    window.show_mode("universal_daw")
    window.close()
    freed = weakref.ref(window)
    del window
    gc.collect()
    assert freed() is None
