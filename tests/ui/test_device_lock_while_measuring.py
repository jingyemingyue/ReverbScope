"""C8: device and sweep controls stay locked while a take is sounding.

Guidelines §4 C8: while measuring, the operator must not change device
settings. Esc/Stop remain the live controls. This is independent of the
Esc-through-modal work in PR #101.
"""

from __future__ import annotations

import os
import threading

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QThread
from PySide6.QtWidgets import QApplication

from reverbscope.ui.main_window import MainWindow

pytestmark = pytest.mark.gui


@pytest.fixture(scope="module")
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.fixture
def held_take(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
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


def _settle(app: QApplication, worker: QThread | None, timeout_ms: int = 5000) -> None:
    if worker is None:
        return
    elapsed = 0
    while worker.isRunning() and elapsed < timeout_ms:
        app.processEvents()
        worker.wait(20)
        elapsed += 20
    app.processEvents()


def test_device_and_sweep_controls_lock_while_a_take_plays(app: QApplication, held_take) -> None:
    """Regression: host/input/output/rate/channel/level stayed editable during
    a sounding take, contradicting C8 even though the worker had already
    captured the indices."""
    window = MainWindow()
    window.show()
    window.show_mode("demo")
    app.processEvents()
    page = window.standalone
    strip = window.strip
    page.duration.setValue(1.0)
    locked = [
        page.host_api,
        page.input_device,
        page.output_device,
        page.sample_rate,
        page.input_channel,
        page.loopback_channel,
        page.output_channel,
        page.duration,
        page.level,
        page.profile,
        page.latency,
        page.refresh_button,
        page.run_button,
        page.back_button,
    ]
    try:
        page.run_button.click()
        assert page.is_busy()
        for widget in locked:
            assert not widget.isEnabled(), widget.objectName() or widget.__class__.__name__
        for widget in strip.device_widgets:
            assert not widget.isEnabled(), widget
        assert page.stop_button.isEnabled()
        assert strip.stop_button.isEnabled()
        assert not page.acknowledge.isEnabled()
    finally:
        held_take.set()
        _settle(app, page._measure_worker)
        _settle(app, page._analysis_worker)
    for widget in (
        page.host_api,
        page.input_device,
        page.sample_rate,
        page.duration,
        page.level,
        page.refresh_button,
    ):
        assert widget.isEnabled()
    window.close()
