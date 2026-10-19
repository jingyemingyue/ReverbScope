"""The live input monitor of "Signal and level": lifecycle, errors and readings, offscreen.

Every source here is synthetic or a fake; nothing opens a sound card. Real
latency and device behaviour need the hardware test in
docs/design/LIVE_INPUT_MONITOR.md.
"""

from __future__ import annotations

import os
import time
from collections.abc import Iterator

import numpy as np
import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from reverbscope.display.live import CLIP_DBFS
from reverbscope.ui.live_input import (
    ERROR_BUSY,
    ERROR_NO_DEVICE,
    ERROR_OTHER,
    ERROR_PERMISSION,
    ERROR_UNAVAILABLE,
    LiveInputError,
    RingBuffer,
    SyntheticInput,
    classify_error,
)

pytestmark = pytest.mark.gui


@pytest.fixture(scope="module")
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


class SpySource:
    """A synthetic source that counts start and stop and is fed by the test."""

    synthetic = True

    def __init__(self, sample_rate: int = 48000, channels: int = 1) -> None:
        self.inner = SyntheticInput(sample_rate, channels, threaded=False)
        self.sample_rate = sample_rate
        self.channels = channels
        self.starts = 0
        self.stops = 0
        self.fail: LiveInputError | None = None

    def start(self, ring: RingBuffer) -> None:
        self.starts += 1
        self.inner.start(ring)

    def stop(self) -> None:
        self.stops += 1
        self.inner.stop()

    def failure(self) -> LiveInputError | None:
        return self.fail

    def pump(self, frames: int) -> None:
        self.inner.pump(frames)


@pytest.fixture
def panel(app: QApplication) -> Iterator[object]:
    from reverbscope.ui.live_monitor import LiveMonitorPanel

    widget = LiveMonitorPanel()
    widget.resize(900, 420)
    widget.show()
    app.processEvents()
    yield widget
    widget.shutdown()
    widget.close()
    widget.deleteLater()
    app.processEvents()


# --- capture plumbing ------------------------------------------------------------


def test_ring_buffer_wraps_and_returns_the_newest_frames() -> None:
    ring = RingBuffer(8, 1)
    ring.write(np.arange(5, dtype=np.float32)[:, None])
    ring.write(np.arange(5, 11, dtype=np.float32)[:, None])
    assert ring.written == 11
    assert ring.latest(4)[:, 0].tolist() == [7.0, 8.0, 9.0, 10.0]
    # More than was ever written: zeros in front.
    fresh = RingBuffer(8, 2)
    fresh.write(np.ones((3, 2), dtype=np.float32))
    assert fresh.latest(5)[:, 0].tolist() == [0.0, 0.0, 1.0, 1.0, 1.0]
    # A block larger than the buffer keeps its tail.
    ring.write(np.arange(20, dtype=np.float32)[:, None])
    assert ring.latest(3)[:, 0].tolist() == [17.0, 18.0, 19.0]


@pytest.mark.parametrize(
    ("message", "kind"),
    [
        ("Error opening InputStream: Device unavailable [PaErrorCode -9985]", ERROR_BUSY),
        ("Error querying device -1", ERROR_NO_DEVICE),
        ("Invalid number of channels [PaErrorCode -9998]", ERROR_NO_DEVICE),
        ("Unanticipated host error: permission denied", ERROR_PERMISSION),
        ("something else entirely", ERROR_OTHER),
    ],
)
def test_portaudio_errors_are_sorted(message: str, kind: str) -> None:
    assert classify_error(RuntimeError(message)) == kind


def test_backend_unavailable_is_its_own_kind() -> None:
    from reverbscope.errors import AudioBackendUnavailableError

    assert classify_error(AudioBackendUnavailableError("no portaudio")) == ERROR_UNAVAILABLE


def test_synthetic_input_levels() -> None:
    source = SyntheticInput(48000, 2, threaded=False, tones=((1000.0, -6.0),), noise_rms_dbfs=-80)
    block = source.generate(48000)
    peak = 20 * np.log10(np.max(np.abs(block), axis=0))
    assert peak[0] == pytest.approx(-6.0, abs=0.1)
    assert peak[1] == pytest.approx(-12.0, abs=0.1)


# --- the panel -------------------------------------------------------------------


def test_start_read_stop_with_a_fake_source(panel: object, app: QApplication) -> None:
    from reverbscope.ui.live_monitor import LiveMonitorPanel

    assert isinstance(panel, LiveMonitorPanel)
    spy = SpySource()
    spy.inner.tones = ((1000.0, -6.0),)
    spy.inner.noise_rms_dbfs = -90.0
    panel.source_factory = lambda: spy
    assert panel.start()
    assert panel.running and spy.starts == 1
    assert panel.timer.isActive()
    assert panel.synthetic_badge.isVisibleTo(panel)
    panel.averaging.setCurrentIndex(panel.averaging.findData(0.0))
    for _ in range(10):
        spy.pump(4800)
        panel.tick(0.1)
    channel = panel.meter.channels[0]
    assert channel.peak.hold == pytest.approx(-6.0, abs=0.2)
    assert channel.last_rms_dbfs == pytest.approx(-9.0, abs=0.3)
    assert not channel.clipped
    peak = int(np.argmax(panel.spectrum.level_db))
    assert panel.spectrum.frequencies[peak] == pytest.approx(1000.0, rel=0.03)
    assert panel.spectrum.level_db[peak] == pytest.approx(-6.0, abs=1.5)
    # The curve is drawn, at about one point per 1.5 px of plot width.
    x, _y = panel.chart.level_curve.getData()
    assert x is not None and 64 <= len(x) <= panel.chart.plot.width()
    # Starting twice opens nothing new.
    assert panel.start() and spy.starts == 1
    panel.stop()
    assert not panel.running and spy.stops == 1
    assert not panel.timer.isActive()
    panel.tick(0.1)  # a late timer tick after stop does nothing


def test_clip_latches_and_a_click_clears_it(panel: object, app: QApplication) -> None:
    from reverbscope.ui.live_monitor import LiveMonitorPanel

    assert isinstance(panel, LiveMonitorPanel)
    spy = SpySource()
    panel.source_factory = lambda: spy
    panel.start()
    assert panel.ring is not None
    panel.ring.write(np.full((256, 1), 10 ** (CLIP_DBFS / 20) + 1e-3, dtype=np.float32))
    panel.tick(0.03)
    assert panel.meter.clipped
    for _ in range(20):
        spy.pump(1440)
        panel.tick(0.03)
    assert panel.meter.clipped  # latched
    QTest.mouseClick(panel.meter, Qt.MouseButton.LeftButton, pos=QPoint(10, 10))
    assert not panel.meter.clipped


def test_freeze_holds_the_spectrum_but_not_the_meter(panel: object, app: QApplication) -> None:
    from reverbscope.ui.live_monitor import LiveMonitorPanel

    assert isinstance(panel, LiveMonitorPanel)
    spy = SpySource()
    panel.source_factory = lambda: spy
    panel.start()
    spy.pump(9000)
    panel.tick(0.03)
    panel.freeze_button.setChecked(True)
    held = panel.spectrum.level_db.copy()
    spy.inner.tones = ((5000.0, -3.0),)
    spy.pump(9000)
    panel.tick(0.03)
    assert np.array_equal(panel.spectrum.level_db, held)
    assert panel.meter.channels[0].peak.hold > -6.0
    panel.freeze_button.setChecked(False)
    spy.pump(9000)
    panel.tick(0.03)
    assert not np.array_equal(panel.spectrum.level_db, held)


@pytest.mark.parametrize(
    ("kind", "needle"),
    [
        (ERROR_NO_DEVICE, "No input device"),
        (ERROR_PERMISSION, "microphone access"),
        (ERROR_BUSY, "busy"),
        (ERROR_UNAVAILABLE, "not available"),
    ],
)
def test_open_errors_are_shown_inline(
    panel: object, app: QApplication, kind: str, needle: str
) -> None:
    from reverbscope.ui.live_monitor import LiveMonitorPanel

    assert isinstance(panel, LiveMonitorPanel)

    def refuse() -> SpySource:
        raise LiveInputError(kind, "PortAudio said no")

    panel.source_factory = refuse
    assert not panel.start()
    assert not panel.running
    assert panel.error.isVisibleTo(panel)
    assert needle in panel.error.text()
    assert panel.chart.message.text()
    assert panel.state_label.text() == "Not listening"


def test_an_unexpected_exception_does_not_escape(panel: object, app: QApplication) -> None:
    from reverbscope.ui.live_monitor import LiveMonitorPanel

    assert isinstance(panel, LiveMonitorPanel)

    def broken() -> SpySource:
        raise OSError("driver exploded")

    panel.source_factory = broken
    assert not panel.start()
    assert "driver exploded" in panel.error.text()


def test_a_stream_that_dies_is_reported(panel: object, app: QApplication) -> None:
    from reverbscope.ui.live_monitor import LiveMonitorPanel

    assert isinstance(panel, LiveMonitorPanel)
    spy = SpySource()
    panel.source_factory = lambda: spy
    panel.start()
    spy.fail = LiveInputError(ERROR_OTHER, "unplugged")
    panel.tick(0.03)
    assert not panel.running and spy.stops == 1
    assert "unplugged" in panel.error.text()


def test_digital_silence_earns_a_hint(panel: object, app: QApplication) -> None:
    from reverbscope.ui.live_monitor import SILENT_HINT_S, LiveMonitorPanel

    assert isinstance(panel, LiveMonitorPanel)
    spy = SpySource()
    panel.source_factory = lambda: spy
    panel.start()
    assert panel.ring is not None
    for _ in range(int(SILENT_HINT_S / 0.25) + 1):
        panel.ring.write(np.zeros((12000, 1), dtype=np.float32))
        panel.tick(0.25)
    assert panel.silence_hint.isVisibleTo(panel)
    spy.pump(4800)
    panel.tick(0.1)
    assert not panel.silence_hint.isVisibleTo(panel)


def test_pause_wins_until_resume(panel: object, app: QApplication) -> None:
    from reverbscope.ui.live_monitor import LiveMonitorPanel

    assert isinstance(panel, LiveMonitorPanel)
    spy = SpySource()
    panel.source_factory = lambda: spy
    panel.start()
    panel.pause()
    assert not panel.running and spy.stops == 1
    assert not panel.start()  # the page asking again does not reopen it
    assert panel.pause_button.text() == "Resume"
    panel.pause_button.click()
    assert panel.running and spy.starts == 2


def test_threaded_synthetic_input_reaches_the_display(panel: object, app: QApplication) -> None:
    from reverbscope.ui.live_monitor import LiveMonitorPanel

    assert isinstance(panel, LiveMonitorPanel)
    panel.source_factory = lambda: SyntheticInput(48000, 1)
    assert panel.start()
    end = time.monotonic() + 0.6
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.005)
    stats = panel.stats()
    assert stats["frames"] >= 5
    assert panel.meter.channels[0].peak.hold > -40.0
    panel.stop()


def test_horizontal_meter_draws(app: QApplication) -> None:
    from reverbscope.ui.components.level_meter import LevelMeter

    meter = LevelMeter(["L", "R"], orientation=Qt.Orientation.Horizontal)
    meter.resize(meter.sizeHint())
    meter.update_levels([-6.0, -0.05], [-12.0, -3.0], 0.03)
    assert meter.clipped
    assert not meter.grab().isNull()
    assert "peak" in meter.readout_text()
    meter.close()
    meter.deleteLater()


# --- on the Standalone page ------------------------------------------------------


@pytest.fixture
def window(app: QApplication, monkeypatch: pytest.MonkeyPatch) -> Iterator[object]:
    monkeypatch.setenv("REVERBSCOPE_AUDIO_BACKEND", "fake")
    from reverbscope.ui.main_window import MainWindow

    win = MainWindow()
    win.resize(1280, 800)
    win.show()
    app.processEvents()
    win.show_mode("standalone")
    app.processEvents()
    yield win
    win.close()
    win.deleteLater()
    app.processEvents()


def _settle(app: QApplication) -> None:
    for _ in range(4):
        app.processEvents()


def test_the_monitor_listens_only_on_its_step(window: object, app: QApplication) -> None:
    from reverbscope.ui.main_window import MainWindow

    assert isinstance(window, MainWindow)
    page = window.standalone
    spies: list[SpySource] = []

    def factory() -> SpySource:
        spies.append(SpySource())
        return spies[-1]

    page.live.source_factory = factory
    assert page.flow.stack.currentIndex() == 0
    _settle(app)
    assert not page.live.running
    page.flow.set_step(1)
    _settle(app)
    assert page.live.running
    page.flow.set_step(2)
    _settle(app)
    assert not page.live.running and spies[0].stops == 1
    page.flow.set_step(1)
    _settle(app)
    assert page.live.running and len(spies) == 2
    # Another task hides the page: the input closes.
    window.show_view("overview")
    _settle(app)
    assert not page.live.running and spies[1].stops == 1
    window.show_mode("standalone")
    _settle(app)
    assert page.live.running and len(spies) == 3


def test_a_device_change_reopens_the_input(window: object, app: QApplication) -> None:
    from reverbscope.ui.main_window import MainWindow

    assert isinstance(window, MainWindow)
    page = window.standalone
    spies: list[SpySource] = []
    page.live.source_factory = lambda: spies.append(SpySource()) or spies[-1]
    page.flow.set_step(1)
    _settle(app)
    page.loopback_channel.setValue(2)
    _settle(app)
    assert len(spies) == 2 and spies[0].stops == 1 and page.live.running


def test_the_page_feeds_the_chosen_channels(window: object, app: QApplication) -> None:
    from reverbscope.ui.main_window import MainWindow

    assert isinstance(window, MainWindow)
    page = window.standalone
    page.input_channel.setValue(1)
    page.loopback_channel.setValue(2)
    assert page.live_channels() == [1, 2]
    source = page._live_source()  # the fake backend: synthetic input
    assert isinstance(source, SyntheticInput) and source.channels == 2
    assert page.live.meter.names == ["Mic 1", "Loopback 2"]


def test_a_take_esc_and_closing_stop_the_input(
    window: object, app: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    from reverbscope.ui.main_window import MainWindow

    assert isinstance(window, MainWindow)
    page = window.standalone
    spy = SpySource()
    page.live.source_factory = lambda: spy
    page.flow.set_step(1)
    _settle(app)
    assert page.live.running
    # Starting a take lets go of the device before the preflight touches it.
    monkeypatch.setattr(page, "_preflight", lambda *_a, **_k: None)
    page.start_measurement()
    assert not page.live.running and spy.stops == 1
    # Busy (a take or an analysis) keeps it closed.
    with monkeypatch.context() as patch:
        patch.setattr(page, "is_busy", lambda: True)
        page._sync_live()
        assert not page.live.running
    page._sync_live()
    assert page.live.running
    # Esc with no take running pauses the monitor until Resume.
    window.strip._escape()
    assert not page.live.running and page.live.user_paused
    page._sync_live()
    assert not page.live.running
    page.live.resume()
    assert page.live.running
    window.close()
    assert not page.live.running


# --- nothing plays by itself -----------------------------------------------------


class _FakeSoundDevice:
    """Records which stream types are opened; no real audio."""

    def __init__(self) -> None:
        self.opened: list[str] = []

    def InputStream(self, **kwargs: object) -> object:  # noqa: N802 - sounddevice's name
        self.opened.append("InputStream")
        assert "callback" in kwargs

        class Stream:
            active = True

            def start(self) -> None: ...

            def abort(self) -> None: ...

            def close(self) -> None: ...

        return Stream()

    def Stream(self, **_kwargs: object) -> object:  # noqa: N802
        self.opened.append("Stream")
        raise AssertionError("the live monitor must not open an output")

    def OutputStream(self, **_kwargs: object) -> object:  # noqa: N802
        self.opened.append("OutputStream")
        raise AssertionError("the live monitor must not open an output")

    def play(self, *_args: object, **_kwargs: object) -> None:
        self.opened.append("play")
        raise AssertionError("the live monitor must not play")


def test_the_device_input_is_input_only(monkeypatch: pytest.MonkeyPatch) -> None:
    import reverbscope.audio.devices as devices
    from reverbscope.ui.live_input import SoundDeviceInput

    fake = _FakeSoundDevice()
    monkeypatch.setattr(devices, "sounddevice_module", lambda: fake)
    source = SoundDeviceInput(3, [1, 2], 48000)
    source.start(RingBuffer(48000, 2))
    source.stop()
    assert fake.opened == ["InputStream"]


def test_entering_the_level_step_plays_nothing(
    window: object, app: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    import reverbscope.ui.workers as workers
    from reverbscope.ui.main_window import MainWindow

    assert isinstance(window, MainWindow)
    played: list[object] = []
    monkeypatch.setattr(
        workers.MeasureWorker, "start", lambda self: played.append(self), raising=True
    )
    page = window.standalone
    for step in (0, 1, 0, 1):
        page.flow.set_step(step)
        _settle(app)
    assert played == []
    assert not page.is_busy()


def test_a_sweep_needs_an_output_the_user_chose(
    window: object, app: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    import reverbscope.ui.pages as pages
    from reverbscope.ui.main_window import MainWindow

    assert isinstance(window, MainWindow)
    page = window.standalone
    warnings: list[str] = []
    monkeypatch.setattr(
        pages.QMessageBox, "warning", lambda _parent, _title, text: warnings.append(text)
    )
    # On a real backend (not the fake one), a preselected or default output is refused.
    page._explicit_output = None
    assert page.output_block_reason("portaudio")
    reached: list[bool] = []
    monkeypatch.setattr(page, "_preflight", lambda *_a, **_k: reached.append(True))
    monkeypatch.setattr(
        pages, "plan_input_channels", pages.plan_input_channels
    )  # unchanged; the guard comes first

    class RealBackend:
        name = "portaudio"

    import reverbscope.audio.backend as backend_module

    monkeypatch.setattr(backend_module, "get_backend", lambda _name=None: RealBackend())
    page.start_measurement()
    assert warnings and "Choose the output of your audio interface" in warnings[0]
    assert reached == []  # nothing reached the device checks, nothing played
    # "System default" is never accepted, even when picked by hand.
    row = page.output_device.findData(None)
    if row >= 0:
        page.output_device.setCurrentIndex(row)
        page._output_chosen(row)
        assert "system default output" in page.output_block_reason("portaudio")
    # An interface output picked by hand is accepted.
    index = next(
        page.output_device.itemData(r)
        for r in range(page.output_device.count())
        if page.output_device.itemData(r) is not None
    )
    assert page.choose_output(int(index))
    assert page.output_block_reason("portaudio") == ""
    # The fake backend plays nothing and is not limited.
    page._explicit_output = None
    assert page.output_block_reason("fake") == ""
