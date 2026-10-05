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
