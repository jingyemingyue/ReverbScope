"""DAW import: Sample rate combo, recording label and warnings stay honest."""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from reverbscope.core.pipeline import synthetic_recording
from reverbscope.io.wav import write_sweep_file, write_wav
from reverbscope.models.configuration import SweepSettings
from reverbscope.ui.main_window import MainWindow
from tests.conftest import make_rir

pytestmark = pytest.mark.gui


@pytest.fixture(scope="module")
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_loading_a_reference_syncs_the_sample_rate_combo(app: QApplication, tmp_path: Path) -> None:
    window = MainWindow()
    window.show()
    window.show_mode("universal_daw")
    page = window.daw
    page.sample_rate.setCurrentIndex(page.sample_rate.findData(48000))
    settings = SweepSettings(sample_rate=44100, duration_s=0.5, level_dbfs=-20.0)
    wav_path, _sidecar = write_sweep_file(settings, tmp_path / "ref.wav")
    page.set_reference(wav_path)
    assert page.sample_rate.currentData() == 44100
    assert page._sweep_settings.sample_rate == 44100
    window.close()


def test_save_and_reopen_keeps_sweep_sample_rate(
    app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """After Analyze + Save + Open, the session's sweep_settings.sample_rate
    must still match the combo that generated the sweep."""
    import json

    monkeypatch.setenv("REVERBSCOPE_HOME", str(tmp_path / "home"))
    window = MainWindow()
    window.show()
    window.show_mode("universal_daw")
    page = window.daw
    page.sample_rate.setCurrentIndex(page.sample_rate.findData(44100))
    page.duration.setValue(0.5)
    page.generate_sweep_to(tmp_path / "sweep.wav")
    take = synthetic_recording(
        page.current_sweep_settings(),
        make_rir(44100, rt60_s=0.25),
    )
    page.set_recording(
        write_wav(tmp_path / "take.wav", take.samples, take.sample_rate, subtype="FLOAT")
    )
    page.start_analysis(blocking=True)
    app.processEvents()
    out = tmp_path / "session"
    assert window.save_to(out)
    saved = json.loads((out / "session.json").read_text(encoding="utf-8"))
    assert saved["sweep_settings"]["sample_rate"] == 44100
    assert saved["sample_rate"] == 44100
    result = json.loads((out / "result.json").read_text(encoding="utf-8"))
    assert result["sample_rate"] == 44100
    window.show_home()
    assert window.open_session_path(out)
    app.processEvents()
    opened = window.model.current()
    assert opened is not None and opened.session is not None
    assert opened.session.sweep_settings.sample_rate == 44100
    assert opened.session.sample_rate == 44100
    window.close()


def test_a_rate_mismatch_between_take_and_sweep_is_warned(
    app: QApplication, tmp_path: Path
) -> None:
    window = MainWindow()
    window.show()
    window.show_mode("universal_daw")
    page = window.daw
    page.sample_rate.setCurrentIndex(page.sample_rate.findData(48000))
    page.duration.setValue(0.5)
    page.generate_sweep_to(tmp_path / "sweep.wav")
    take = synthetic_recording(
        SweepSettings(sample_rate=44100, duration_s=0.5, level_dbfs=-20.0),
        make_rir(44100, rt60_s=0.25),
    )
    audio = np.asarray(take.samples, dtype=np.float64)
    rec = write_wav(tmp_path / "take44100.wav", audio, 44100, subtype="FLOAT")
    page.set_recording(rec)
    assert "44100" in page.recording_label.text()
    text = page.status.text().lower()
    assert "44100" in page.status.text() and "48000" in page.status.text()
    assert "differ" in text or page.status.property("banner") == "warn"
    window.close()
