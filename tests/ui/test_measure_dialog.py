"""The measurement dialogs: the Standalone take and the DAW analysis.

Both validate on accept exactly as the old pages did and hand the workbench
a request; they play, record and analyse nothing themselves. The fake
backend stands in for an interface (it is chosen through the environment
or the test hook, never through a widget).
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

from reverbscope.audio.backend import SAFE_MAX_LEVEL_DBFS
from reverbscope.core.pipeline import Reference, analyze, synthetic_recording
from reverbscope.demo import DEMO_MODE, FAKE_BACKEND_NOTES
from reverbscope.io.wav import write_wav
from reverbscope.models.audio import AudioSignal
from reverbscope.models.configuration import SweepSettings
from reverbscope.models.result import AnalysisResult
from reverbscope.ui.measure_dialog import (
    AnalysisRequest,
    DawAnalysisDialog,
    StandaloneMeasureDialog,
    TakeRequest,
)
from tests.conftest import make_rir

pytestmark = pytest.mark.gui


@pytest.fixture(scope="module")
def app() -> QApplication:
    instance = QApplication.instance()
    return instance if isinstance(instance, QApplication) else QApplication([])


@pytest.fixture
def fake_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REVERBSCOPE_AUDIO_BACKEND", "fake")


def _result(short_sweep: SweepSettings, rt60_s: float = 0.35, seed: int = 1) -> AnalysisResult:
    rate = short_sweep.sample_rate
    take = synthetic_recording(
        short_sweep,
        make_rir(rate, rt60_s=rt60_s, reflections=[(0.018, 0.35)], seed=seed),
        noise_rms=1e-5,
    )
    return analyze(take, Reference.from_settings(short_sweep))


def _take(settings: SweepSettings) -> AudioSignal:
    rate = settings.sample_rate
    return synthetic_recording(
        settings, make_rir(rate, rt60_s=0.35, reflections=[(0.018, 0.35)]), noise_rms=1e-5
    )


def _boxes(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    """Record every warning and critical box instead of showing it."""
    shown: list[tuple[str, str]] = []

    def warning(parent: object, title: str, text: str, *args: object) -> QMessageBox.StandardButton:
        shown.append(("warning", title))
        return QMessageBox.StandardButton.Ok

    def critical(
        parent: object, title: str, text: str, *args: object
    ) -> QMessageBox.StandardButton:
        shown.append(("critical", title))
        return QMessageBox.StandardButton.Ok

    monkeypatch.setattr(QMessageBox, "warning", warning)
    monkeypatch.setattr(QMessageBox, "critical", critical)
    return shown


def _standalone(short_sweep: SweepSettings, **kwargs: str) -> StandaloneMeasureDialog:
    dialog = StandaloneMeasureDialog(None, profile="generic", backend="fake", **kwargs)
    dialog.sample_rate.setCurrentIndex(dialog.sample_rate.findData(short_sweep.sample_rate))
    dialog.duration.setValue(short_sweep.duration_s)
    return dialog


# --- Standalone Mode ---------------------------------------------------------------


def test_the_standalone_dialog_lists_the_fake_devices_and_enables_run(
    app: QApplication, short_sweep: SweepSettings
) -> None:
    dialog = _standalone(short_sweep)
    dialog.show()
    assert dialog.run_button.isEnabled()
    inputs = [dialog.input_device.itemText(i) for i in range(dialog.input_device.count())]
    outputs = [dialog.output_device.itemText(i) for i in range(dialog.output_device.count())]
    assert inputs[0] == "System default" and outputs[0] == "System default"
    assert any("ReverbScope fake interface" in text and "8 in" in text for text in inputs)
    assert any("ReverbScope fake interface" in text and "2 out" in text for text in outputs)
    # The recommended entry is starred; the host API list names the fake one.
    assert any(text.startswith("★") for text in inputs[1:])
    assert dialog.host_api.itemText(0) == "System default"
    assert dialog.host_api.findData("fake") > 0
    assert dialog.device_hint.text() == "1 audio device(s) found."
    assert "48000" in dialog.device_rate.text()
    # The safety text is a banner, visible without scrolling the form.
    assert dialog.safety.property("banner") == "warn"
    assert dialog.safety.text().startswith("Start with your monitor")
    # Refresh keeps the device chosen.
    dialog.input_device.setCurrentIndex(1)
    dialog.refresh_devices()
    assert dialog.input_device.currentIndex() == 1
    assert dialog.run_button.isEnabled()
    assert dialog.width() <= 640 and dialog.height() <= 560
    dialog.close()


def test_without_a_device_run_is_disabled_and_the_hint_says_so(
    app: QApplication, short_sweep: SweepSettings, monkeypatch: pytest.MonkeyPatch
) -> None:
    from reverbscope.audio.fake import FakeBackend

    monkeypatch.setattr(FakeBackend, "list_devices", lambda self: [])
    dialog = _standalone(short_sweep)
    assert not dialog.run_button.isEnabled()
    assert dialog.device_hint.text() == "No audio device found; Universal DAW Mode still works."
    assert dialog.device_hint.property("banner") == "warn"
    assert dialog.input_device.count() == 1, "only System default is left to choose"
    dialog.close()


def test_accepting_with_defaults_yields_a_synthetic_take_request(
    app: QApplication, fake_backend: None, short_sweep: SweepSettings
) -> None:
    # The backend comes from the environment here, as in the product; the
    # dialog shows no switch for it.
    dialog = StandaloneMeasureDialog(None, profile="vocal", room="Booth", position="A")
    dialog.sample_rate.setCurrentIndex(dialog.sample_rate.findData(short_sweep.sample_rate))
    dialog.duration.setValue(short_sweep.duration_s)
    dialog.mic.setText("omni")
    dialog.show()
    assert dialog.request() is None
    dialog.run_button.click()
    assert dialog.result() == QDialog.DialogCode.Accepted
    assert not dialog.isVisible()
    request = dialog.request()
    assert isinstance(request, TakeRequest)
    assert request.synthetic and request.backend == "fake"
    assert request.session.mode == DEMO_MODE
    assert request.session.notes == FAKE_BACKEND_NOTES
    assert request.session.room_name == "Booth"
    assert request.session.measurement_position == "A"
    assert request.session.microphone_name == "omni"
    assert request.profile == "vocal" and request.session.recording_profile == "vocal"
    # 1-based interface channels in the session and the take, 0-based
    # recording columns for the analysis.
    assert request.input_channels == [1]
    assert request.loopback_channel is None
    assert request.output_channel == 1
    assert request.session.input_channel == 1 and request.session.output_channel == 1
    assert request.session.loopback_channel is None
    assert request.analysis_settings.channel == 0
    assert request.analysis_settings.loopback_channel is None
    assert request.input_device is None and request.output_device is None
    assert request.settings.sample_rate == short_sweep.sample_rate
    assert request.settings.duration_s == short_sweep.duration_s
    assert request.settings.level_dbfs == -20.0
    assert request.reference.settings == request.settings
    assert request.session.sweep_settings == request.settings
    assert request.options.is_default
    dialog.close()


def test_a_loopback_input_is_recorded_as_a_second_column(
    app: QApplication, short_sweep: SweepSettings
) -> None:
    dialog = _standalone(short_sweep)
    dialog.input_channel.setValue(3)
    dialog.loopback_channel.setValue(2)
    dialog.output_channel.setValue(2)
    dialog.placement.distance.setValue(1.25)
    dialog.run_button.click()
    request = dialog.request()
    assert request is not None
    assert request.input_channels == [3, 2]
    assert request.loopback_channel == 2
    assert request.session.input_channel == 3
    assert request.session.loopback_channel == 2
    assert request.session.output_channel == 2 and request.output_channel == 2
    assert request.analysis_settings.channel == 0
    assert request.analysis_settings.loopback_channel == 1
    assert request.analysis_settings.placement_distance_m == pytest.approx(1.25)
    assert request.session.analysis_settings == request.analysis_settings
    dialog.close()


def test_a_level_above_the_safe_maximum_needs_the_acknowledgement(
    app: QApplication, short_sweep: SweepSettings, monkeypatch: pytest.MonkeyPatch
) -> None:
    shown = _boxes(monkeypatch)
    dialog = _standalone(short_sweep)
    dialog.show()
    dialog.level.setValue(SAFE_MAX_LEVEL_DBFS + 3.0)
    dialog.run_button.click()
    assert shown == [("warning", "Level too high")]
    assert dialog.request() is None
    assert dialog.isVisible(), "the dialog stays open"
    assert dialog.result() != QDialog.DialogCode.Accepted
    # The acknowledgement lets the level through.
    dialog.acknowledge.setChecked(True)
    dialog.run_button.click()
    request = dialog.request()
    assert request is not None
    assert request.settings.level_dbfs == pytest.approx(SAFE_MAX_LEVEL_DBFS + 3.0)
    assert not dialog.isVisible()
    assert shown == [("warning", "Level too high")]
    dialog.close()


def test_a_channel_the_interface_lacks_is_refused_before_anything_plays(
    app: QApplication, short_sweep: SweepSettings, monkeypatch: pytest.MonkeyPatch
) -> None:
    shown = _boxes(monkeypatch)
    dialog = _standalone(short_sweep)
    dialog.show()
    # The same input as microphone and loopback: the channel plan refuses it.
    dialog.input_channel.setValue(2)
    dialog.loopback_channel.setValue(2)
    dialog.run_button.click()
    assert shown == [("critical", "Invalid settings")]
    assert dialog.request() is None and dialog.isVisible()
    # An output the fake interface (2 out) does not have: the preflight refuses it.
    dialog.loopback_channel.setValue(0)
    dialog.output_channel.setValue(5)
    dialog.run_button.click()
    assert shown[-1] == ("critical", "Invalid settings")
    assert dialog.request() is None and dialog.isVisible()
    dialog.close()


# --- Universal DAW Mode ------------------------------------------------------------


def test_the_daw_dialog_refuses_to_analyse_without_a_recording_or_reference(
    app: QApplication, tmp_path: Path, short_sweep: SweepSettings, monkeypatch: pytest.MonkeyPatch
) -> None:
    shown = _boxes(monkeypatch)
    dialog = DawAnalysisDialog(None, profile="generic")
    dialog.show()
    assert dialog.channel.count() == 1 and dialog.channel.currentData() is None
    assert not dialog.instructions.content.isVisible(), "the notes are closed by default"
    assert not dialog.placement_section.content.isVisible()
    dialog.analyze_button.click()
    assert shown == [("warning", "No recording")]
    assert dialog.request() is None and dialog.isVisible()
    rate = short_sweep.sample_rate
    take = _take(short_sweep)
    dialog.set_recording(write_wav(tmp_path / "take.wav", take.samples, rate, subtype="FLOAT"))
    assert dialog.recording_label.text().startswith("take.wav")
    assert dialog.channel.count() == 2
    dialog.analyze_button.click()
    assert shown == [("warning", "No recording"), ("warning", "No reference")]
    assert dialog.request() is None and dialog.isVisible()
    assert dialog.width() <= 640 and dialog.height() <= 560
    dialog.close()


def test_the_daw_dialog_builds_an_analysis_request(
    app: QApplication, tmp_path: Path, short_sweep: SweepSettings
) -> None:
    dialog = DawAnalysisDialog(None, profile="generic", room="Booth", position="B")
    dialog.show()
    rate = short_sweep.sample_rate
    dialog.sample_rate.setCurrentIndex(dialog.sample_rate.findData(rate))
    dialog.duration.setValue(short_sweep.duration_s)
    dialog.generate_sweep_to(tmp_path / "sweep.wav")
    assert (tmp_path / "sweep.wav").exists()
    assert dialog.sweep_label.text().startswith("Written: sweep.wav")
    assert dialog.reference_label.text() == "Reference: sweep.wav"
    # The microphone on the second channel of a stereo export.
    take = _take(dialog.current_sweep_settings())
    stereo = np.column_stack([np.zeros_like(take.samples), take.samples])
    recording_path = write_wav(tmp_path / "take.wav", stereo, rate, subtype="FLOAT")
    dialog.set_recording(recording_path)
    assert [dialog.channel.itemText(i) for i in range(dialog.channel.count())] == [
        "Auto (highest level)",
        "Channel 1",
        "Channel 2",
    ]
    assert not dialog.rate_hint.isVisible(), "the rates match"
    dialog.channel.setCurrentIndex(dialog.channel.findData(1))
    dialog.mic.setText("SDC")
    dialog.profile.setCurrentIndex(dialog.profile.findData("vocal"))
    dialog.placement.distance.setValue(1.5)
    dialog.placement.mic_height.setValue(0.9)
    dialog.analyze_button.click()
    assert dialog.result() == QDialog.DialogCode.Accepted
    request = dialog.request()
    assert isinstance(request, AnalysisRequest)
    assert request.session.mode == "universal_daw"
    assert request.session.room_name == "Booth"
    assert request.session.measurement_position == "B"
    assert request.session.microphone_name == "SDC"
    assert request.profile == "vocal" and request.session.recording_profile == "vocal"
    assert request.analysis_settings.channel == 1
    assert request.analysis_settings.loopback_channel is None
    assert request.analysis_settings.placement_distance_m == pytest.approx(1.5)
    assert request.analysis_settings.placement_mic_height_m == pytest.approx(0.9)
    assert request.session.analysis_settings == request.analysis_settings
    assert request.recording_path == recording_path
    assert request.session.recording_path == str(recording_path)
    assert request.sweep_path == tmp_path / "sweep.wav"
    assert request.session.sweep_path == str(tmp_path / "sweep.wav")
    assert request.settings.sample_rate == rate
    assert request.settings.duration_s == short_sweep.duration_s
    assert request.session.sweep_settings == request.settings
    assert request.recording.n_channels == 2
    # The request analyses as it is: the chosen column, the written sweep.
    result = analyze(request.recording, request.reference, request.analysis_settings)
    assert isinstance(result, AnalysisResult)
    assert result.decay.broadband.rt60_estimate_s == pytest.approx(
        _result(short_sweep).decay.broadband.rt60_estimate_s, rel=0.25
    )
    dialog.close()


def test_a_reference_file_and_a_rate_mismatch_are_reported(
    app: QApplication, tmp_path: Path, short_sweep: SweepSettings
) -> None:
    from reverbscope.io.wav import write_sweep_file

    other_rate = 44100
    sweep_path, _sidecar = write_sweep_file(
        short_sweep.with_sample_rate(other_rate), tmp_path / "ref.wav"
    )
    dialog = DawAnalysisDialog(None, profile="generic")
    dialog.show()
    dialog.set_reference(sweep_path)
    assert dialog.reference_label.text() == "Reference: ref.wav"
    assert dialog.current_sweep_settings().sample_rate != other_rate, (
        "the signal settings stay the user's; the reference keeps the sidecar's"
    )
    take = _take(short_sweep)
    dialog.set_recording(
        write_wav(tmp_path / "take.wav", take.samples, short_sweep.sample_rate, subtype="FLOAT")
    )
    assert dialog.rate_hint.isVisible()
    assert "44100" in dialog.rate_hint.text() and "48000" in dialog.rate_hint.text()
    dialog.analyze_button.click()
    request = dialog.request()
    assert request is not None
    assert request.settings.sample_rate == other_rate
    assert request.reference.settings is not None
    assert request.reference.settings.sample_rate == other_rate
    dialog.close()
