"""Universal DAW Mode must work when no audio devices are listed."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from reverbscope.audio import backend as backend_module
from reverbscope.audio.backend import DeviceInfo
from reverbscope.core.pipeline import synthetic_recording
from reverbscope.io.wav import write_wav
from reverbscope.models.configuration import SweepSettings
from reverbscope.ui.main_window import MainWindow
from tests.conftest import make_rir

pytestmark = pytest.mark.gui


@pytest.fixture(scope="module")
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


class _EmptyBackend:
    name = "empty"

    def list_devices(self) -> list[DeviceInfo]:
        return []

    def check_sample_rate(self, *_args: object, **_kwargs: object) -> None:
        return None


def test_daw_analyze_works_with_no_audio_devices(
    app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("REVERBSCOPE_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(backend_module, "get_backend", lambda name=None: _EmptyBackend())
    window = MainWindow()
    window.show()
    window.show_mode("universal_daw")
    page = window.daw
    settings = SweepSettings(sample_rate=48000, duration_s=0.5, level_dbfs=-20.0)
    page.sample_rate.setCurrentIndex(page.sample_rate.findData(settings.sample_rate))
    page.duration.setValue(settings.duration_s)
    page.generate_sweep_to(tmp_path / "sweep.wav")
    take = synthetic_recording(settings, make_rir(settings.sample_rate, rt60_s=0.3))
    page.set_recording(
        write_wav(tmp_path / "take.wav", take.samples, take.sample_rate, subtype="FLOAT")
    )
    page.start_analysis(blocking=True)
    app.processEvents()
    assert window.state.result is not None
    assert window.stack.currentWidget() is window.views["overview"]
    window.close()
