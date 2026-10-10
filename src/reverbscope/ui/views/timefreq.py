"""Spectrogram and waterfall views, computed from the stored impulse response.

The transforms (``display.timefreq``) run in a worker thread with a
generation token, so a long response never blocks the window and a result
for an entry or parameters no longer shown is dropped. Results are cached
per entry and parameters in the workspace model. See
docs/design/GUI_2_ARCHITECTURE.md §5.3.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

import numpy as np
from PySide6.QtCore import QRectF, QThread, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from reverbscope.display import DisplayDataError
from reverbscope.display.timefreq import (
    SpectrogramParams,
    TimeFrequencyResult,
    TransformCancelledError,
    WaterfallParams,
    cumulative_spectral_decay,
    spectrogram,
)
from reverbscope.i18n import _
from reverbscope.ui.pg import colormap
from reverbscope.ui.plotkit import X_FREQUENCY, X_TIME_MS, ChartPanel, format_frequency, pg
from reverbscope.ui.theme import tokens
from reverbscope.ui.views.base import AnalysisView
from reverbscope.ui.workers import unexpected_error_text
from reverbscope.ui.workspace import Entry, WorkspaceModel, entry_label

log = logging.getLogger(__name__)


class TransformWorker(QThread):
    """Runs one time-frequency transform; ``cancelled`` is the thread's interruption flag."""

    succeeded = Signal(int, str, object, object)
    failed = Signal(int, str)

    def __init__(
        self,
        generation: int,
        key: str,
        params: object,
        function: Callable[..., TimeFrequencyResult],
        samples: Any,
        sample_rate: int,
        direct_index: int,
    ) -> None:
        super().__init__()
        self.generation = generation
        self.key = key
        self.params = params
        self._function = function
        self._args = (samples, sample_rate, direct_index)

    def run(self) -> None:
        try:
            result = self._function(
                *self._args, self.params, cancelled=self.isInterruptionRequested
            )
        except TransformCancelledError:
            return
        except DisplayDataError as exc:
            self.failed.emit(self.generation, exc.text())
        except MemoryError:
            from reverbscope.ui.workers import out_of_memory_text

            self.failed.emit(self.generation, out_of_memory_text())
        except Exception:
            log.exception("time-frequency transform failed unexpectedly")
            self.failed.emit(self.generation, unexpected_error_text())
        else:
            self.succeeded.emit(self.generation, self.key, self.params, result)


def note_lines(result: TimeFrequencyResult) -> list[str]:
    lines = []
    for template, params in result.notes:
        text = _(template)
        lines.append(text.format(**params) if params else text)
    return lines


class _TimeFrequencyView(AnalysisView):
    """What the spectrogram and the waterfall share: the worker, the cache, the notes."""

    kind = ""

    def __init__(self, model: WorkspaceModel, parent: QWidget | None = None) -> None:
        super().__init__(model, parent)
        self._generation = 0
        self._worker: TransformWorker | None = None
        self._old_workers: list[TransformWorker] = []
        # The result the running transform reads: a late answer for an entry
        # that was replaced meanwhile (saved over, project read again) is dropped.
        self._source: object = None
        self._shown_key = ""
        self.result: TimeFrequencyResult | None = None
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(250)
        self._debounce.timeout.connect(self.refresh)
        self.root = QVBoxLayout(self)
        self.root.setContentsMargins(10, 8, 10, 8)
        self.root.setSpacing(6)
        self.controls = QHBoxLayout()
        self.controls.setSpacing(6)
        self.root.addLayout(self.controls)
        self.status = QLabel("")
        self.status.setProperty("role", "hint")
        self.status.setWordWrap(True)
        self.notes = QLabel("")
        self.notes.setProperty("role", "hint")
        self.notes.setWordWrap(True)
        for signal in (model.current_changed, model.entries_changed):
            signal.connect(self.refresh)

    def _spin(
        self, low: float, high: float, value: float, suffix: str, decimals: int = 1
    ) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(low, high)
        spin.setDecimals(decimals)
        spin.setValue(value)
        spin.setSuffix(suffix)
        spin.valueChanged.connect(lambda _v: self._debounce.start())
        return spin

    def params(self) -> object:
        raise NotImplementedError

    def transform(self) -> Callable[..., TimeFrequencyResult]:
        raise NotImplementedError

    def draw_result(self, entry: Entry, result: TimeFrequencyResult) -> None:
        raise NotImplementedError

    def clear_chart(self) -> None:
        raise NotImplementedError

    def redraw(self) -> None:
        entry = self.model.current()
        self.result = None
        if entry is None or entry.result is None:
            self.clear_chart()
            self.status.setText(_("Choose a measurement in the list."))
            self.notes.setText("")
            return
        try:
            params = self.params()
        except DisplayDataError as exc:
            self.clear_chart()
            self.status.setText(exc.text())
            return
        cached = self.model.cache_get(entry.key, (self.kind, params))
        if isinstance(cached, TimeFrequencyResult):
            self._show(entry, cached)
            return
        self._start(entry, params)

    def _start(self, entry: Entry, params: object) -> None:
        assert entry.result is not None
        self._cancel_running()
        self._generation += 1
        self._source = entry.result
        if self._shown_key != entry.key:
            # Not the previous measurement's picture under this one's name.
            self.clear_chart()
            self.notes.setText("")
            self._shown_key = ""
        ir = entry.result.impulse_response
        worker = TransformWorker(
            self._generation,
            entry.key,
            params,
            self.transform(),
            ir.samples,
            ir.sample_rate,
            ir.direct_sound_index,
        )
        worker.succeeded.connect(self._on_done)
        worker.failed.connect(self._on_failed)
        worker.finished.connect(self._on_finished)
        self._worker = worker
        self.status.setText(_("Computing for {name}...").format(name=entry_label(entry)))
        worker.start()

    def _cancel_running(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            self._worker.requestInterruption()
            self._old_workers.append(self._worker)
        self._worker = None

    def _on_done(self, generation: int, key: str, params: object, result: object) -> None:
        if generation != self._generation or not isinstance(result, TimeFrequencyResult):
            return
        source = self.model.entry(key)
        if source is None or source.result is not self._source:
            return
        self.model.cache_put(key, (self.kind, params), result)
        entry = self.model.current()
        if entry is not None and entry.key == key:
            self._show(entry, result)

    def _on_failed(self, generation: int, message: str) -> None:
        if generation != self._generation:
            return
        self.clear_chart()
        self.status.setText(message)
        self.notes.setText("")

    def _on_finished(self) -> None:
        worker = self.sender()
        if worker is self._worker:
            self._worker = None
        if isinstance(worker, TransformWorker) and worker in self._old_workers:
            self._old_workers.remove(worker)

    def _show(self, entry: Entry, result: TimeFrequencyResult) -> None:
        self.result = result
        self._shown_key = entry.key
        self.status.setText(
            _("{name}: {unit}").format(name=entry_label(entry), unit=_(result.unit))
        )
        self.notes.setText("  ".join(note_lines(result)))
        self.draw_result(entry, result)

    def is_computing(self) -> bool:
        return self._worker is not None and self._worker.isRunning()

    def shutdown(self) -> None:
        workers = [*self._old_workers, *([self._worker] if self._worker is not None else [])]
        for worker in workers:
            worker.requestInterruption()
        for worker in workers:
            worker.wait()
        self._old_workers.clear()
        self._worker = None


class SpectrogramView(_TimeFrequencyView):
    view_id = "spectrogram"
    kind = "spectrogram"

    def __init__(self, model: WorkspaceModel, parent: QWidget | None = None) -> None:
        super().__init__(model, parent)
        c = self.controls
        c.addWidget(QLabel(_("Window")))
        self.window_ms = self._spin(1.0, 500.0, 20.0, " ms")
        c.addWidget(self.window_ms)
        c.addWidget(QLabel(_("Step")))
        self.hop_ms = self._spin(0.1, 100.0, 2.0, " ms")
        c.addWidget(self.hop_ms)
        c.addWidget(QLabel(_("Time")))
        self.end_ms = self._spin(10.0, 5000.0, 500.0, " ms", 0)
        c.addWidget(self.end_ms)
        c.addWidget(QLabel(_("Frequency")))
        self.fmin = self._spin(1.0, 20_000.0, 20.0, " Hz", 0)
        self.fmax = self._spin(100.0, 96_000.0, 20_000.0, " Hz", 0)
        c.addWidget(self.fmin)
        c.addWidget(self.fmax)
        c.addWidget(QLabel(_("Levels")))
        self.normalization = QComboBox()
        self.normalization.addItem(_("re peak"), "peak")
        self.normalization.addItem(_("re direct sound"), "direct")
        self.normalization.addItem(_("re full scale"), "none")
        self.normalization.currentIndexChanged.connect(lambda _i: self._debounce.start())
        c.addWidget(self.normalization)
        self.floor = self._spin(-160.0, -10.0, -80.0, " dB", 0)
        c.addWidget(self.floor)
        c.addStretch(1)
        self.chart = ChartPanel(
            X_TIME_MS,
            x_label=_("Time after direct sound (ms)"),
            y_label=_("Frequency (Hz)"),
            title=_("Spectrogram"),
            y_frequency=True,
        )
        self.chart.export_name = "spectrogram"
        self.chart.csv_action.setVisible(False)  # an image: no curves to list
        self.chart.readout_hook = self._readout
        self.image = pg.ImageItem(axisOrder="col-major")
        self.chart.plot_item.addItem(self.image)
        self.colorbar = pg.ColorBarItem(
            values=(-80.0, 0.0), colorMap=colormap("inferno"), interactive=False, width=14
        )
        self.colorbar.setImageItem(self.image, insert_in=self.chart.plot_item)
        self.root.addWidget(self.chart, 1)
        self.root.addWidget(self.status)
        self.root.addWidget(self.notes)

    def title(self) -> str:
        return _("Spectrogram")

    def params(self) -> SpectrogramParams:
        fmax = self.fmax.value()
        entry = self.model.current()
        if entry is not None and entry.result is not None:
            fmax = min(fmax, entry.result.sample_rate / 2.0)
        return SpectrogramParams(
            window_ms=self.window_ms.value(),
            hop_ms=self.hop_ms.value(),
            freq_range_hz=(self.fmin.value(), fmax),
            time_range_ms=(-5.0, self.end_ms.value()),
            normalization=str(self.normalization.currentData()),
            floor_db=self.floor.value(),
            points_per_octave=24,
        )

    def transform(self) -> Callable[..., TimeFrequencyResult]:
        return spectrogram

    def clear_chart(self) -> None:
        self.image.clear()
        self.chart.set_title("")

    def draw_result(self, entry: Entry, result: TimeFrequencyResult) -> None:
        levels = np.asarray(result.levels_db, dtype=np.float64)
        times = result.times_ms
        logf = np.log10(result.freqs_hz)
        self.image.setImage(levels, autoLevels=False)
        floor = float(np.nanmin(levels)) if levels.size else -80.0
        top = float(np.nanmax(levels)) if levels.size else 0.0
        self.colorbar.setLevels((floor, top))
        dt = float(times[1] - times[0]) if times.size > 1 else 1.0
        df = float(logf[1] - logf[0]) if logf.size > 1 else 0.01
        rect = QRectF(
            float(times[0]) - dt / 2.0, float(logf[0]) - df / 2.0, dt * times.size, df * logf.size
        )
        self.image.setRect(rect)
        self.chart.set_default_range((rect.left(), rect.right()), (rect.top(), rect.bottom()))
        self.chart.set_title(_("Spectrogram: {name}").format(name=entry_label(entry)))

    def _readout(self, plot_x: float, plot_y: float) -> str | None:
        result = self.result
        if result is None or result.times_ms.size == 0:
            return None
        ti = int(np.argmin(np.abs(result.times_ms - plot_x)))
        fi = int(np.argmin(np.abs(np.log10(result.freqs_hz) - plot_y)))
        level = float(result.levels_db[ti, fi])
        return _("{time:.1f} ms   {freq}   {level:.1f} {unit}").format(
            time=float(result.times_ms[ti]),
            freq=format_frequency(float(result.freqs_hz[fi])),
            level=level,
            unit=_(result.unit),
        )

    def restyle(self) -> None:
        self.chart.restyle()
        self.refresh()


class WaterfallView(_TimeFrequencyView):
    view_id = "waterfall"
    kind = "waterfall"

    def __init__(self, model: WorkspaceModel, parent: QWidget | None = None) -> None:
        super().__init__(model, parent)
        c = self.controls
        c.addWidget(QLabel(_("Window")))
        self.window_ms = self._spin(5.0, 2000.0, 300.0, " ms", 0)
        c.addWidget(self.window_ms)
        c.addWidget(QLabel(_("Rise")))
        self.rise_ms = self._spin(0.0, 50.0, 0.5, " ms")
        c.addWidget(self.rise_ms)
        c.addWidget(QLabel(_("Step")))
        self.step_ms = self._spin(0.1, 200.0, 10.0, " ms")
        c.addWidget(self.step_ms)
        c.addWidget(QLabel(_("Slices")))
        self.slices = QSpinBox()
        self.slices.setRange(2, 120)
        self.slices.setValue(30)
        self.slices.valueChanged.connect(lambda _v: self._debounce.start())
        c.addWidget(self.slices)
        c.addWidget(QLabel(_("Frequency")))
        self.fmin = self._spin(1.0, 20_000.0, 20.0, " Hz", 0)
        self.fmax = self._spin(100.0, 96_000.0, 20_000.0, " Hz", 0)
        c.addWidget(self.fmin)
        c.addWidget(self.fmax)
        self.smoothing = QComboBox()
        for fraction in (0, 24, 12, 6, 3):
            text = (
                _("no smoothing")
                if fraction == 0
                else _("1/{fraction} octave").format(fraction=fraction)
            )
            self.smoothing.addItem(text, fraction)
        self.smoothing.setCurrentIndex(2)
        self.smoothing.currentIndexChanged.connect(lambda _i: self._debounce.start())
        c.addWidget(self.smoothing)
        self.perspective = QCheckBox(_("Perspective"))
        self.perspective.setToolTip(
            _("Offset later slices up and to the right, as a three-dimensional waterfall.")
        )
        self.perspective.setChecked(True)
        self.perspective.toggled.connect(self.refresh)
        c.addWidget(self.perspective)
        c.addStretch(1)
        self.chart = ChartPanel(
            X_FREQUENCY,
            x_label=_("Frequency (Hz)"),
            y_label=_("Level (dB re first slice peak)"),
            title=_("Waterfall"),
        )
        self.chart.export_name = "waterfall"
        self.chart.readout_hook = self._readout
        self.root.addWidget(self.chart, 1)
        slice_row = QHBoxLayout()
        slice_row.addWidget(QLabel(_("Slice")))
        self.slice = QSlider()
        self.slice.setOrientation(pg.QtCore.Qt.Orientation.Horizontal)
        self.slice.valueChanged.connect(self._slice_moved)
        slice_row.addWidget(self.slice, 1)
        self.slice_label = QLabel("")
        self.slice_label.setMinimumWidth(240)
        slice_row.addWidget(self.slice_label)
        self.root.addLayout(slice_row)
        self.root.addWidget(self.status)
        self.root.addWidget(self.notes)
        self._entry_key = ""

    def title(self) -> str:
        return _("Waterfall")

    def params(self) -> WaterfallParams:
        fmax = self.fmax.value()
        entry = self.model.current()
        if entry is not None and entry.result is not None:
            fmax = min(fmax, entry.result.sample_rate / 2.0)
        return WaterfallParams(
            window_ms=self.window_ms.value(),
            rise_ms=self.rise_ms.value(),
            step_ms=self.step_ms.value(),
            slices=self.slices.value(),
            freq_range_hz=(self.fmin.value(), fmax),
            smoothing=int(self.smoothing.currentData()),
            points_per_octave=48,
        )

    def transform(self) -> Callable[..., TimeFrequencyResult]:
        return cumulative_spectral_decay

    def clear_chart(self) -> None:
        self.chart.clear()
        self.chart.set_title("")
        self.slice_label.setText("")

    def offsets(self, index: int, count: int) -> tuple[float, float]:
        """Perspective shift of slice ``index``: (log10 Hz, dB)."""
        if not self.perspective.isChecked() or count <= 1:
            return 0.0, 0.0
        return 0.35 * index / (count - 1), 25.0 * index / (count - 1)

    def draw_result(self, entry: Entry, result: TimeFrequencyResult) -> None:
        self._entry_key = entry.key
        self.chart.clear()
        cmap = colormap("viridis")
        count = result.times_ms.size
        self.slice.blockSignals(True)
        self.slice.setRange(0, max(count - 1, 0))
        self.slice.setValue(min(self.slice.value(), max(count - 1, 0)))
        self.slice.blockSignals(False)
        chosen = self.slice.value()
        # Back to front: the first slice is drawn last, on top.
        for index in range(count - 1, -1, -1):
            dx, dy = self.offsets(index, count)
            color = cmap.map(index / max(count - 1, 1), mode="qcolor").name()
            freqs = result.freqs_hz * 10.0**dx
            selected = index == chosen
            self.chart.add_curve(
                _("{time:.1f} ms").format(time=float(result.times_ms[index])),
                freqs,
                result.levels_db[index] + dy,
                color=tokens()["warn"] if selected else color,
                width=2.4 if selected else 1.0,
                readout=selected,
                legend=index in (0, count - 1) or selected,
                z=100 if selected else count - index,
                shift=(10.0**dx, dy),
            )
        top_dx, top_dy = self.offsets(count - 1, count)
        fmin = float(result.freqs_hz[0])
        fmax = float(result.freqs_hz[-1]) * 10.0**top_dx
        floor = float(np.nanmin(result.levels_db)) if result.levels_db.size else -60.0
        self.chart.set_default_range((fmin, fmax), (floor - 3.0, 5.0 + top_dy))
        self.chart.set_title(_("Waterfall: {name}").format(name=entry_label(entry)))
        self._update_slice_label()

    def _slice_moved(self, _value: int) -> None:
        entry = self.model.current()
        if self.result is not None and entry is not None:
            self.draw_result(entry, self.result)

    def _update_slice_label(self) -> None:
        if self.result is None or self.result.times_ms.size == 0:
            self.slice_label.setText("")
            return
        index = self.slice.value()
        levels = self.result.levels_db[index]
        peak = int(np.nanargmax(levels))
        self.slice_label.setText(
            _("{time:.1f} ms: peak {level:.1f} dB at {freq}").format(
                time=float(self.result.times_ms[index]),
                level=float(levels[peak]),
                freq=format_frequency(float(self.result.freqs_hz[peak])),
            )
        )

    def _readout(self, plot_x: float, _plot_y: float) -> str | None:
        """Time, frequency and level of the selected slice under the cursor."""
        result = self.result
        if result is None or result.times_ms.size == 0:
            return None
        index = self.slice.value()
        dx, _dy = self.offsets(index, result.times_ms.size)
        logf = np.log10(result.freqs_hz) + dx
        fi = int(np.argmin(np.abs(logf - plot_x)))
        return _("{time:.1f} ms   {freq}   {level:.1f} dB").format(
            time=float(result.times_ms[index]),
            freq=format_frequency(float(result.freqs_hz[fi])),
            level=float(result.levels_db[index, fi]),
        )

    def restyle(self) -> None:
        self.chart.restyle()
        self.refresh()
