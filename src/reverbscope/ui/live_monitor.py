"""Live input monitor for the "Signal and level" step: level meter and live spectrum.

A display while the level is set, never a measurement: nothing shown here
is stored, exported or analysed, and the panel says so. The page decides
when it may listen (its step is visible, no take or analysis is running,
the window is open); Esc and Pause stop it until Resume is pressed.

Frames are drawn from a ``QTimer`` (about 30 per second) that reads the
ring buffer the input source fills; the audio callback never touches Qt
(see :mod:`reverbscope.ui.live_input`).
"""

from __future__ import annotations

import collections
import logging
import time
from collections.abc import Callable

import numpy as np
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QWidget,
)

from reverbscope.display.live import (
    AVERAGING_TIMES_S,
    DEFAULT_AVERAGING_S,
    DEFAULT_FFT_SIZE,
    DEFAULT_SMOOTHING,
    FFT_SIZES,
    RMS_WINDOW_S,
    SILENCE_DBFS,
    SMOOTHING_FRACTIONS,
    LiveSpectrum,
    block_peak_dbfs,
    block_rms_dbfs,
)
from reverbscope.i18n import _
from reverbscope.ui.components.level_meter import LevelMeter
from reverbscope.ui.components.live_spectrum import LiveSpectrumChart
from reverbscope.ui.design.tokens import SPACE
from reverbscope.ui.live_input import InputSource, LiveInputError, RingBuffer
from reverbscope.ui.widgets import Card, label, set_banner_text

log = logging.getLogger(__name__)

#: Frame period of the display timer (ms): about 33 frames per second.
FRAME_MS = 30
#: The ring buffer keeps at least this much input (s), and two of the largest frames.
RING_SECONDS = 1.0
#: Exact digital silence for this long (s) earns a hint: on macOS a missing
#: microphone permission gives zeros, not an error.
SILENT_HINT_S = 2.0


class LiveMonitorPanel(Card):
    """Meter, spectrum, their options, and the reason when the input cannot be shown."""

    #: ``True`` while an input stream is open.
    running_changed = Signal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        #: Builds the input source when listening starts; set by the page.
        self.source_factory: Callable[[], InputSource] | None = None
        self.source: InputSource | None = None
        self.ring: RingBuffer | None = None
        #: Esc or Pause: stay quiet until Resume, whatever the page asks.
        self.user_paused = False
        self.frozen = False
        self._read_upto = 0
        self._last_tick: float | None = None
        self._silent_s = 0.0
        #: Reused by :meth:`tick` so each frame does one ring copy, not three.
        self._scratch: np.ndarray | None = None
        #: Wall time of each drawn frame's work (s), for the performance note.
        self.frame_seconds: collections.deque[float] = collections.deque(maxlen=300)
        self.frame_stamps: collections.deque[float] = collections.deque(maxlen=300)

        header = QHBoxLayout()
        header.setSpacing(SPACE)
        # Section role already styles the caption; do not force Latin all-caps
        # (guidelines: no all-caps titles; Chinese must not gain letter-spacing).
        header.addWidget(label(_("Live input"), "section"))
        self.state_label = label("", "hint")
        header.addWidget(self.state_label)
        header.addStretch(1)
        self.synthetic_badge = QLabel(_("Synthetic demo data"))
        self.synthetic_badge.setProperty("banner", "info")
        self.synthetic_badge.hide()
        header.addWidget(self.synthetic_badge)
        self.pause_button = QPushButton(_("Pause"))
        self.pause_button.setToolTip(_("Stop listening to the input (Esc)."))
        self.pause_button.clicked.connect(self._toggle_pause)
        header.addWidget(self.pause_button)
        self.body.addLayout(header)

        options = QHBoxLayout()
        options.setSpacing(SPACE)
        self.fft_size = QComboBox()
        self.fft_size.setAccessibleName(_("Analysis length"))
        self.fft_size.setToolTip(
            _("Longer analysis resolves lower frequencies more finely and reacts more slowly.")
        )
        for size in FFT_SIZES:
            self.fft_size.addItem(_("{points} points").format(points=size), size)
        self.fft_size.setCurrentIndex(FFT_SIZES.index(DEFAULT_FFT_SIZE))
        self.averaging = QComboBox()
        self.averaging.setAccessibleName(_("Averaging"))
        for seconds in AVERAGING_TIMES_S:
            self.averaging.addItem(
                _("No averaging")
                if seconds <= 0
                else _("Average {seconds:g} s").format(seconds=seconds),
                seconds,
            )
        self.averaging.setCurrentIndex(AVERAGING_TIMES_S.index(DEFAULT_AVERAGING_S))
        self.smoothing = QComboBox()
        self.smoothing.setAccessibleName(_("Display smoothing"))
        for fraction in SMOOTHING_FRACTIONS:
            self.smoothing.addItem(
                _("No smoothing")
                if fraction == 0
                else _("1/{fraction} octave").format(fraction=fraction),
                fraction,
            )
        self.smoothing.setCurrentIndex(SMOOTHING_FRACTIONS.index(DEFAULT_SMOOTHING))
        self.peak_hold = QCheckBox(_("Peak hold"))
        self.peak_hold.setChecked(True)
        self.freeze_button = QPushButton(_("Freeze"))
        self.freeze_button.setCheckable(True)
        self.freeze_button.setToolTip(_("Hold the spectrum still; the meter keeps running."))
        self.freeze_button.toggled.connect(self._set_frozen)
        for widget in (self.fft_size, self.averaging, self.smoothing):
            widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
            options.addWidget(widget)
        options.addWidget(self.peak_hold)
        options.addStretch(1)
        options.addWidget(self.freeze_button)
        self.body.addLayout(options)

        charts = QHBoxLayout()
        charts.setSpacing(SPACE * 2)
        self.meter = LevelMeter()
        charts.addWidget(self.meter)
        self.chart = LiveSpectrumChart()
        charts.addWidget(self.chart, 1)
        self.body.addLayout(charts, 1)

        self.error = label("", None, wrap=True)
        self.error.hide()
        self.body.addWidget(self.error)
        self.silence_hint = label(
            _(
                "The input is digitally silent. Check the input channel and the interface's "
                "gain; on macOS, also check that ReverbScope may use the microphone."
            ),
            "hint",
            wrap=True,
        )
        self.silence_hint.hide()
        self.body.addWidget(self.silence_hint)
        self.note = label("", "hint", wrap=True)
        self.body.addWidget(self.note)

        self.spectrum = LiveSpectrum(sample_rate=48000)
        self.fft_size.currentIndexChanged.connect(self._options_changed)
        self.averaging.currentIndexChanged.connect(self._options_changed)
        self.smoothing.currentIndexChanged.connect(self._options_changed)
        self.peak_hold.toggled.connect(self._peak_hold_toggled)
        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.setInterval(FRAME_MS)
        self.timer.timeout.connect(self.tick)
        self._update_state()
        self._update_note()

    # --- lifecycle --------------------------------------------------------------

    @property
    def running(self) -> bool:
        return self.source is not None

    def start(self) -> bool:
        """Open the input unless paused by the user; ``True`` when it is open."""
        if self.running:
            return True
        if self.user_paused or self.source_factory is None:
            self._update_state()
            return False
        self._show_error("")
        try:
            source = self.source_factory()
            ring = RingBuffer(
                max(int(RING_SECONDS * source.sample_rate), 2 * max(FFT_SIZES)), source.channels
            )
            source.start(ring)
        except LiveInputError as exc:
            log.info("live input unavailable: %s", exc)
            self._show_error(exc.text())
            self._update_state()
            return False
        except Exception as exc:  # a broken driver must not take the page down
            log.warning("live input failed to start", exc_info=True)
            self._show_error(LiveInputError("other", str(exc)).text())
            self._update_state()
            return False
        self.source, self.ring = source, ring
        self._read_upto = 0
        self._last_tick = None
        self._silent_s = 0.0
        self.silence_hint.hide()
        self.meter.reset()
        self.spectrum.configure(sample_rate=source.sample_rate, points=self.chart.wanted_points())
        self._apply_options()
        self.chart.set_nyquist(source.sample_rate)
        self.chart.clear()
        self.chart.set_message("")
        self.synthetic_badge.setVisible(bool(getattr(source, "synthetic", False)))
        self.timer.start()
        self._update_state()
        self._update_note()
        self.running_changed.emit(True)
        return True

    def stop(self) -> None:
        """Close the input (leaving the step, a take starting, the window closing)."""
        self.timer.stop()
        source, self.source = self.source, None
        self.ring = None
        if source is not None:
            try:
                source.stop()
            except Exception:
                log.debug("live input: stop failed", exc_info=True)
            self.running_changed.emit(False)
        self._update_state()

    def pause(self) -> None:
        """Esc / Pause: stop, and stay stopped until Resume."""
        self.user_paused = True
        self.stop()

    def resume(self) -> bool:
        self.user_paused = False
        return self.start()

    def _toggle_pause(self) -> None:
        if self.running:
            self.pause()
        else:
            self.resume()

    # --- options ----------------------------------------------------------------

    def _apply_options(self) -> None:
        self.spectrum.averaging_s = float(self.averaging.currentData())
        self.spectrum.smoothing = int(self.smoothing.currentData())
        size = int(self.fft_size.currentData())
        if size != self.spectrum.fft_size:
            self.spectrum.configure(fft_size=size)
        self.chart.show_peak = self.peak_hold.isChecked()

    def _options_changed(self, _index: int = 0) -> None:
        self._apply_options()
        self._update_note()

    def _peak_hold_toggled(self, checked: bool) -> None:
        self.chart.show_peak = checked
        self.spectrum.reset_peaks()

    def _set_frozen(self, frozen: bool) -> None:
        self.frozen = frozen
        self.freeze_button.setText(_("Unfreeze") if frozen else _("Freeze"))
        self._update_state()

    # --- frames -----------------------------------------------------------------

    def _ensure_scratch(self, frames: int, channels: int) -> np.ndarray:
        scratch = self._scratch
        if (
            scratch is None
            or scratch.shape[0] < frames
            or scratch.shape[1] != channels
            or scratch.dtype != np.float32
        ):
            scratch = np.zeros((max(frames, 1), channels), dtype=np.float32)
            self._scratch = scratch
        return scratch

    def tick(self, dt_s: float | None = None) -> None:
        """Draw one frame from the newest input (the timer; tests pass ``dt_s``)."""
        source, ring = self.source, self.ring
        if source is None or ring is None:
            return
        started = time.perf_counter()
        failure = source.failure()
        if failure is not None:
            self.stop()
            self._show_error(failure.text())
            return
        now = time.monotonic()
        if dt_s is None:
            dt_s = 0.0 if self._last_tick is None else now - self._last_tick
        self._last_tick = now
        upto = ring.written
        fresh = min(upto - self._read_upto, ring.capacity)
        self._read_upto = upto
        rate = source.sample_rate
        rms_n = int(RMS_WINDOW_S * rate)
        fft_n = 0 if self.frozen else self.spectrum.fft_size
        need = max(fresh, rms_n, fft_n)
        if need > 0:
            scratch = self._ensure_scratch(need, ring.channels)
            block = ring.latest(need, upto=upto, out=scratch[:need])
        else:
            block = np.zeros((0, ring.channels), dtype=np.float32)
        peaks = block_peak_dbfs(block[-fresh:]) if fresh > 0 else [SILENCE_DBFS] * ring.channels
        rms = block_rms_dbfs(block[-rms_n:] if rms_n else block)
        self.meter.update_levels(peaks, rms, dt_s)
        if fresh > 0:
            silent = max(peaks) <= SILENCE_DBFS
            self._silent_s = self._silent_s + dt_s if silent else 0.0
            self.silence_hint.setVisible(self._silent_s >= SILENT_HINT_S)
        if not self.frozen and fresh > 0 and fft_n > 0:
            points = self.chart.wanted_points()
            if points != self.spectrum.points:
                self.spectrum.configure(points=points)
                self._apply_options()
            self.spectrum.update(block[-fft_n:, 0], dt_s)
            self.chart.draw(self.spectrum)
        self.frame_seconds.append(time.perf_counter() - started)
        self.frame_stamps.append(now)

    def stats(self) -> dict[str, float]:
        """Mean frame work (ms) and frames per second over the recent frames."""
        work = list(self.frame_seconds)
        stamps = list(self.frame_stamps)
        fps = 0.0
        if len(stamps) >= 2 and stamps[-1] > stamps[0]:
            fps = (len(stamps) - 1) / (stamps[-1] - stamps[0])
        return {
            "frames": float(len(work)),
            "mean_ms": 1000.0 * float(np.mean(work)) if work else 0.0,
            "p95_ms": 1000.0 * float(np.percentile(work, 95)) if work else 0.0,
            "fps": fps,
        }

    # --- text -------------------------------------------------------------------

    def _show_error(self, text: str) -> None:
        set_banner_text(self.error, text, "warn" if text else "")
        self.error.setVisible(bool(text))
        self.chart.set_message(text and _("No live input."))

    def _update_state(self) -> None:
        if self.running:
            state = _("Listening · spectrum frozen") if self.frozen else _("Listening")
        elif self.user_paused:
            state = _("Paused")
        else:
            state = _("Not listening")
        self.state_label.setText(state)
        self.pause_button.setText(_("Pause") if self.running else _("Resume"))
        self.pause_button.setEnabled(self.source_factory is not None)

    def _update_note(self) -> None:
        rate = self.source.sample_rate if self.source is not None else self.spectrum.sample_rate
        size = int(self.fft_size.currentData())
        averaging = float(self.averaging.currentData())
        fraction = int(self.smoothing.currentData())
        parts = [
            _("Hann window, {points} points ({resolution:.1f} Hz)").format(
                points=size, resolution=rate / size
            ),
            _("averaging {seconds:g} s").format(seconds=averaging)
            if averaging > 0
            else _("no averaging"),
            _("display smoothing 1/{fraction} octave").format(fraction=fraction)
            if fraction
            else _("no display smoothing"),
            _("uncalibrated dBFS"),
        ]
        self.note.setText(
            _("For setting the level only: nothing here is stored or analysed. {details}.").format(
                details=" · ".join(parts)
            )
        )

    def restyle(self) -> None:
        self.chart.restyle()
        self.meter.restyle()

    def shutdown(self) -> None:
        """The window is closing: close the input and release the chart."""
        self.stop()
        self._scratch = None
        self.chart.dispose()
