"""Impulse response view: the energy-time curve or the waveform, with clickable reflections."""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from reverbscope.core.placement import speed_of_sound_m_s
from reverbscope.display import DisplayDataError
from reverbscope.display.etc import EtcCurve, etc_curve, marker_points
from reverbscope.i18n import _
from reverbscope.interpretation.profiles import confidence_text
from reverbscope.ui.plotkit import DASHES, X_TIME_MS, ChartPanel
from reverbscope.ui.theme import tokens
from reverbscope.ui.views.base import AnalysisView
from reverbscope.ui.workspace import Entry, WorkspaceModel, entry_label

MODE_ETC = "etc"
MODE_WAVE = "wave"

#: Time spans offered (ms after the direct sound); 0 = all of it.
SPANS_MS = (100.0, 300.0, 1000.0, 0.0)


class ImpulseView(AnalysisView):
    view_id = "etc"

    def __init__(self, model: WorkspaceModel, parent: QWidget | None = None) -> None:
        super().__init__(model, parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)
        controls = QHBoxLayout()
        controls.addWidget(QLabel(_("Show")))
        self.mode = QComboBox()
        self.mode.addItem(_("Energy-time curve"), MODE_ETC)
        self.mode.addItem(_("Waveform"), MODE_WAVE)
        self.mode.currentIndexChanged.connect(self.refresh)
        controls.addWidget(self.mode)
        controls.addWidget(QLabel(_("Span")))
        self.span = QComboBox()
        for span in SPANS_MS:
            text = _("whole response") if span == 0 else _("first {ms:g} ms").format(ms=span)
            self.span.addItem(text, span)
        self.span.currentIndexChanged.connect(self.refresh)
        controls.addWidget(self.span)
        controls.addStretch(1)
        layout.addLayout(controls)

        splitter = QSplitter(Qt.Orientation.Vertical)
        self.chart = ChartPanel(
            X_TIME_MS,
            x_label=_("Time after direct sound (ms)"),
            y_label=_("Level re direct sound (dB)"),
            title=_("Energy-time curve"),
        )
        self.chart.export_name = "impulse-response"
        splitter.addWidget(self.chart)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(
            [_("Delay (ms)"), _("Level (dB)"), _("Excess path (m)"), _("Note")]
        )
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.itemSelectionChanged.connect(self._table_selected)
        splitter.addWidget(self.table)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter, 1)
        self.notes = QLabel("")
        self.notes.setProperty("role", "hint")
        self.notes.setWordWrap(True)
        layout.addWidget(self.notes)
        self._filling = False
        for signal in (model.current_changed, model.overlay_changed, model.entries_changed):
            signal.connect(self.refresh)
        model.reflection_changed.connect(self._reflection_changed)

    def title(self) -> str:
        return _("Impulse response")

    def curve(self, entry: Entry) -> EtcCurve:
        cached = self.model.cache_get(entry.key, "etc")
        if cached is None:
            assert entry.result is not None
            ir = entry.result.impulse_response
            cached = etc_curve(ir.samples, ir.sample_rate, ir.direct_sound_index)
            self.model.cache_put(entry.key, "etc", cached)
        assert isinstance(cached, EtcCurve)
        return cached

    def redraw(self) -> None:
        t = tokens()
        self.chart.clear()
        current = self.model.current()
        wave = self.mode.currentData() == MODE_WAVE
        if wave:
            self.chart.set_labels(_("Time after direct sound (ms)"), _("Amplitude (relative)"))
            self.chart.y_unit = ""
            self.chart.set_title(_("Impulse response waveform"))
        else:
            self.chart.set_labels(
                _("Time after direct sound (ms)"), _("Level re direct sound (dB)")
            )
            self.chart.y_unit = "dB"
            self.chart.set_title(_("Energy-time curve"))
        notes: list[str] = []
        end_ms = 0.0
        for entry in self.model.drawn():
            assert entry.result is not None
            is_current = current is not None and entry.key == current.key
            ir = entry.result.impulse_response
            try:
                curve = self.curve(entry)
            except DisplayDataError as exc:
                notes.append(f"{entry_label(entry)}: {exc.text()}")
                continue
            end_ms = max(end_ms, float(curve.time_ms[-1]))
            if wave:
                peak = float(np.max(np.abs(ir.samples))) or 1.0
                y = np.asarray(ir.samples, dtype=np.float64) / peak
                processing = _("scaled to the peak")
            else:
                y = curve.level_db
                processing = _("the reflection detector's envelope, 0.1 ms peak hold")
            self.chart.add_curve(
                entry_label(entry),
                curve.time_ms,
                y,
                color=entry.color,
                width=1.6 if is_current else 1.0,
                style=DASHES[entry.color_index % len(DASHES)],
                key=entry.key,
                processing=processing,
                readout=is_current,
                z=10 if is_current else 0,
            )
        span = float(self.span.currentData())
        if current is not None and current.result is not None and not wave:
            self._draw_reflections(current, notes)
        if current is not None and current.result is not None:
            refl = current.result.reflections
            if span == 0.0:
                stop = end_ms
            else:
                stop = max(span, refl.window_ms[1] + 10.0) if span <= 100.0 else span
            self.chart.set_default_range((-5.0, stop), None if wave else (-80.0, 5.0))
        else:
            self.chart.set_default_range(None, None)
        if not wave:
            self.chart.add_hline(0.0, color=t["muted"], style=Qt.PenStyle.DotLine)
        self.notes.setText("  ".join(notes))
        self._fill_table(current)

    def _draw_reflections(self, entry: Entry, notes: list[str]) -> None:
        assert entry.result is not None
        t = tokens()
        refl = entry.result.reflections
        curve = self.curve(entry)
        lo_ms, hi_ms = refl.analysed_window_ms or refl.window_ms
        self.chart.add_region(lo_ms, hi_ms, color=t["accent"], alpha=18)
        self.chart.add_hline(refl.threshold_db, color=t["muted"])
        notes.append(
            _(
                "Shaded: the searched window ({start:.1f} to {stop:.1f} ms). Dashed: the "
                "{threshold:.0f} dB threshold. Direct-sound confidence: {confidence}."
            ).format(
                start=lo_ms,
                stop=hi_ms,
                threshold=refl.threshold_db,
                confidence=confidence_text(refl.direct_sound_confidence),
            )
        )
        if not refl.reflections:
            return
        points = marker_points(curve, refl.reflections)
        tips = [
            _("{delay:.2f} ms, {level:.1f} dB").format(delay=r.delay_ms, level=r.relative_db)
            for r in refl.reflections
        ]
        self.chart.add_markers(
            points[:, 0],
            points[:, 1],
            color=entry.color,
            on_click=lambda index, key=entry.key: self.model.select_reflection(key, index),
            tips=tips,
        )
        key, index = self.model.selected_reflection()
        if key == entry.key and 0 <= index < len(refl.reflections):
            self.chart.add_markers(
                [points[index, 0]],
                [points[index, 1]],
                color=t["warn"],
                size=14,
                filled=True,
                symbol="d",
            )
            self.chart.add_vline(float(points[index, 0]), color=t["warn"])

    def _fill_table(self, entry: Entry | None) -> None:
        self._filling = True
        try:
            reflections = (
                entry.result.reflections.reflections
                if entry is not None and entry.result is not None
                else ()
            )
            speed = speed_of_sound_m_s(
                entry.result.placement.temperature_c
                if entry is not None
                and entry.result is not None
                and entry.result.placement is not None
                else 20.0
            )
            self.table.setRowCount(len(reflections))
            for row, reflection in enumerate(reflections):
                values = [
                    f"{reflection.delay_ms:.2f}",
                    f"{reflection.relative_db:.1f}",
                    f"{speed * reflection.delay_ms / 1000.0:.2f}",
                    _("candidate reflection"),
                ]
                for column, text in enumerate(values):
                    self.table.setItem(row, column, QTableWidgetItem(text))
            key, index = self.model.selected_reflection()
            if entry is not None and key == entry.key and 0 <= index < len(reflections):
                self.table.selectRow(index)
            else:
                self.table.clearSelection()
        finally:
            self._filling = False

    def _table_selected(self) -> None:
        if self._filling:
            return
        current = self.model.current()
        rows = {index.row() for index in self.table.selectedIndexes()}
        if current is None or len(rows) != 1:
            return
        self.model.select_reflection(current.key, rows.pop())

    def _reflection_changed(self, _key: str, _index: int) -> None:
        self.refresh()

    def restyle(self) -> None:
        self.chart.restyle()
        self.refresh()
