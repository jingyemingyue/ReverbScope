"""The live spectrum chart: a filled curve, a peak-hold trace and a cursor readout.

Drawn with pyqtgraph in ``log10(Hz)`` coordinates like the other frequency
charts (:class:`reverbscope.ui.plotkit.LogFrequencyAxis`), styled from the
design tokens. The numbers come from :class:`reverbscope.display.live.LiveSpectrum`;
this widget only draws them and reads them back under the cursor.
"""

from __future__ import annotations

import contextlib
import math
from typing import Any

import numpy as np
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QBrush, QColor, QGradient, QLinearGradient
from PySide6.QtWidgets import QLabel, QSizePolicy, QVBoxLayout, QWidget

from reverbscope.display.live import (
    SILENCE_DBFS,
    SPECTRUM_DB_RANGE,
    SPECTRUM_MAX_HZ,
    SPECTRUM_MIN_HZ,
    LiveSpectrum,
    note_name,
)
from reverbscope.i18n import _
from reverbscope.ui.design.tokens import MIN_PLOT_HEIGHT
from reverbscope.ui.pg import close_plot_widget, disable_menus, plot_widget, pyqtgraph
from reverbscope.ui.plotkit import LogFrequencyAxis, format_frequency
from reverbscope.ui.theme import tokens

#: Display points per logical pixel of plot width (1 point per ~1.5 px).
POINTS_PER_PX = 1.0 / 1.5


def readout_text(hz: float, db: float | None) -> str:
    """``1 kHz · −23.4 dBFS · B5`` (the note when the frequency has one)."""
    level = "-" if db is None else f"{db:.1f}".replace("-", "−")
    note = note_name(hz)
    text = _("{frequency} · {level} dBFS").format(frequency=format_frequency(hz), level=level)
    return f"{text} · {note}" if note else text


class LiveSpectrumChart(QWidget):
    """A live, non-interactive (except the cursor) spectrum chart."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        pg: Any = pyqtgraph()
        self.spectrum: LiveSpectrum | None = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        self.plot = plot_widget(axisItems={"bottom": LogFrequencyAxis(orientation="bottom")})
        # Room for the sweep settings under it on a 800 px window.
        self.plot.setMinimumHeight(MIN_PLOT_HEIGHT - 60)
        self.plot.setMaximumHeight(MIN_PLOT_HEIGHT + 40)
        self.plot.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.plot_item = self.plot.getPlotItem()
        disable_menus(self.plot_item)
        self.view_box = self.plot_item.getViewBox()
        # Live: the axes stay where they are; the cursor reads values.
        self.view_box.setMouseEnabled(x=False, y=False)
        self.plot_item.enableAutoRange(x=False, y=False)
        self.plot_item.setXRange(
            math.log10(SPECTRUM_MIN_HZ), math.log10(SPECTRUM_MAX_HZ), padding=0
        )
        self.plot_item.setYRange(*SPECTRUM_DB_RANGE, padding=0)
        self.plot_item.getAxis("left").setTickSpacing(major=20.0, minor=10.0)
        self.peak_curve = pg.PlotCurveItem()
        self.peak_curve.setZValue(10)
        self.level_curve = pg.PlotCurveItem(fillLevel=SILENCE_DBFS)
        self.level_curve.setZValue(20)
        self.plot_item.addItem(self.peak_curve)
        self.plot_item.addItem(self.level_curve)
        self.cursor_line = pg.InfiniteLine(angle=90, movable=False)
        self.cursor_line.setZValue(30)
        self.cursor_line.hide()
        self.plot_item.addItem(self.cursor_line, ignoreBounds=True)
        layout.addWidget(self.plot, 1)
        self.readout = QLabel("")
        self.readout.setProperty("role", "hint")
        self.readout.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self.readout)
        self.message = QLabel(self.plot)
        self.message.setProperty("role", "hint")
        self.message.setWordWrap(True)
        self.message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.message.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.message.hide()
        self._cursor_hz: float | None = None
        self.show_peak = True
        self._disposed = False
        self.plot.scene().sigMouseMoved.connect(self._mouse_moved)
        self.plot.setAccessibleName(_("Live input spectrum"))
        self.set_labels()
        self.restyle()

    # --- appearance -------------------------------------------------------------

    def set_labels(self) -> None:
        t = tokens()
        self.plot_item.setLabel("bottom", _("Frequency (Hz)"), color=t["text"])
        self.plot_item.setLabel("left", _("Level (dBFS)"), color=t["text"])

    def restyle(self) -> None:
        if self._disposed:
            return
        pg: Any = pyqtgraph()
        t = tokens()
        self.plot.setBackground(QColor(t["canvas"]))
        for name in ("bottom", "left"):
            axis = self.plot_item.getAxis(name)
            axis.setPen(pg.mkPen(QColor(t["grid"])))
            axis.setTextPen(pg.mkPen(QColor(t["text"])))
        self.plot_item.showGrid(x=True, y=True, alpha=0.18)
        accent = QColor(t["accent"])
        self.level_curve.setPen(pg.mkPen(accent, width=1.5))
        # A soft vertical gradient under the curve, strongest at the curve.
        # In data coordinates (dB), so it does not depend on how pyqtgraph
        # splits the fill path: strong at the top of the scale, faint at the floor.
        low, high = SPECTRUM_DB_RANGE
        gradient = QLinearGradient(QPointF(0.0, high), QPointF(0.0, low))
        gradient.setCoordinateMode(QGradient.CoordinateMode.LogicalMode)
        top, bottom = QColor(accent), QColor(accent)
        top.setAlpha(150)
        bottom.setAlpha(18)
        gradient.setColorAt(0.0, top)
        gradient.setColorAt(1.0, bottom)
        self.level_curve.setBrush(QBrush(gradient))
        peak = QColor(t["muted"])
        peak.setAlpha(200)
        self.peak_curve.setPen(pg.mkPen(peak, width=1))
        self.cursor_line.setPen(pg.mkPen(QColor(t["muted"]), width=1, style=Qt.PenStyle.DashLine))
        self.set_labels()

    def set_message(self, text: str) -> None:
        self.message.setText(text)
        self.message.setVisible(bool(text))
        self.message.setGeometry(self.plot.rect().adjusted(48, 16, -16, -40))

    def resizeEvent(self, event: Any) -> None:  # noqa: N802 - Qt override
        super().resizeEvent(event)
        self.message.setGeometry(self.plot.rect().adjusted(48, 16, -16, -40))

    def wanted_points(self) -> int:
        """Display points for the current plot width (about one per 1.5 px)."""
        width = self.view_box.width() if self.view_box.width() > 0 else self.plot.width()
        return max(64, int(width * POINTS_PER_PX))

    def set_nyquist(self, sample_rate: int) -> None:
        top = min(SPECTRUM_MAX_HZ, 0.5 * sample_rate)
        self.plot_item.setXRange(math.log10(SPECTRUM_MIN_HZ), math.log10(top), padding=0)

    # --- data -------------------------------------------------------------------

    def draw(self, spectrum: LiveSpectrum) -> None:
        self.spectrum = spectrum
        x = np.log10(spectrum.frequencies)
        self.level_curve.setData(x, spectrum.level_db)
        if self.show_peak:
            self.peak_curve.setData(x, spectrum.peak_db)
            self.peak_curve.show()
        else:
            self.peak_curve.hide()
        if self._cursor_hz is not None:
            self._show_readout(self._cursor_hz)

    def clear(self) -> None:
        self.level_curve.setData([], [])
        self.peak_curve.setData([], [])
        self.readout.setText("")

    def _mouse_moved(self, position: Any) -> None:
        if not self.plot_item.sceneBoundingRect().contains(position):
            return
        point = self.view_box.mapSceneToView(position)
        hz = 10.0 ** float(point.x())
        self._cursor_hz = hz
        self.cursor_line.setPos(point.x())
        self.cursor_line.show()
        self._show_readout(hz)

    def _show_readout(self, hz: float) -> None:
        db = self.spectrum.value_at(hz) if self.spectrum is not None else None
        self.readout.setText(readout_text(hz, db))

    def leaveEvent(self, event: Any) -> None:  # noqa: N802 - Qt override
        self._cursor_hz = None
        self.cursor_line.hide()
        super().leaveEvent(event)

    def dispose(self) -> None:
        if self._disposed:
            return
        self._disposed = True
        with contextlib.suppress(RuntimeError, TypeError):
            self.plot.scene().sigMouseMoved.disconnect(self._mouse_moved)
        close_plot_widget(self.plot)
