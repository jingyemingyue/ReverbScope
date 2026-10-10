"""The workstation's chart panel: one pyqtgraph plot with ReverbScope's interaction.

Every chart view builds on :class:`ChartPanel`. It gives the same handling
everywhere (docs/design/GUI_2_ARCHITECTURE.md §6.2): wheel zoom about the
cursor, drag to pan, right-drag box zoom, double-click / ``R`` / Reset to
fit, a cursor readout with units, a legend whose chips match the
measurement list and hide or show their curve, and Export ▸ PNG, SVG, CSV.

Curves are handed over at full resolution and kept; what is drawn is a
peak-preserving subset of the visible part (:func:`display.curves.peak_subset`),
recomputed when the view range changes, so a zoom never re-runs an
analysis and a notch never gets shallower. Frequency charts draw in
``log10(Hz)`` coordinates (pyqtgraph's ``setLogMode`` converts curves only,
not regions, markers or the cursor) and label the axis in Hz themselves.
"""

from __future__ import annotations

import csv
import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from PySide6.QtCore import QPointF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QIcon, QKeyEvent, QPainter, QPixmap
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMenu,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from reverbscope.display.curves import peak_subset
from reverbscope.i18n import _
from reverbscope.ui.pg import (
    close_plot_widget,
    disable_menus,
    plot_widget,
    png_export,
    pyqtgraph,
    svg_export,
)
from reverbscope.ui.theme import tokens

pg: Any = pyqtgraph()

#: Points drawn per curve for the visible range; extremes are always kept.
DISPLAY_POINTS = 4000

#: Dash patterns by entry colour index, so overlays stay apart without colour.
DASHES: tuple[Qt.PenStyle, ...] = (
    Qt.PenStyle.SolidLine,
    Qt.PenStyle.DashLine,
    Qt.PenStyle.DotLine,
    Qt.PenStyle.DashDotLine,
    Qt.PenStyle.DashDotDotLine,
    Qt.PenStyle.SolidLine,
    Qt.PenStyle.DashLine,
    Qt.PenStyle.DotLine,
)

X_FREQUENCY = "frequency"
X_TIME_MS = "time_ms"
X_TIME_S = "time_s"
X_LINEAR = "linear"


def format_frequency(hz: float) -> str:
    if not math.isfinite(hz):
        return "-"
    if hz >= 1000.0:
        return f"{hz / 1000.0:.3g} kHz"
    return f"{hz:.3g} Hz"


def format_x(kind: str, value: float, unit: str = "") -> str:
    if kind == X_FREQUENCY:
        return format_frequency(value)
    if kind == X_TIME_MS:
        return f"{value:.2f} ms"
    if kind == X_TIME_S:
        return f"{value:.3f} s"
    return f"{value:.3g} {unit}".strip()


class LogFrequencyAxis(pg.AxisItem):
    """An axis in ``log10(Hz)`` that reads in Hz: 20, 50, 100, 200, 500, 1k, 2k ..."""

    def tickValues(self, minVal: float, maxVal: float, size: float) -> list[Any]:  # noqa: N802, N803
        lo = max(minVal, -1.0)
        hi = min(maxVal, 6.0)
        if hi <= lo:
            return []
        major: list[float] = []
        minor: list[float] = []
        for decade in range(math.floor(lo), math.ceil(hi) + 1):
            for step in range(1, 10):
                value = math.log10(step * 10.0**decade)
                if lo <= value <= hi:
                    (major if step in (1, 2, 5) else minor).append(value)
        # Sparse labels when the axis is short: decades only.
        if size < 260:
            major = [v for v in major if abs(v - round(v)) < 1e-9] or major
        return [(1.0, major), (0.5, minor)]

    def tickStrings(self, values: list[float], scale: float, spacing: float) -> list[str]:  # noqa: N802, ARG002
        out = []
        for value in values:
            hz = 10.0**value
            out.append(f"{hz / 1000.0:g}k" if hz >= 1000.0 else f"{hz:g}")
        return out


class ChartViewBox(pg.ViewBox):
    """Left drag pans, right drag draws a zoom box, a double click fits."""

    reset_requested = Signal()

    def __init__(self) -> None:
        super().__init__(enableMenu=False)
        self.setMouseMode(pg.ViewBox.PanMode)

    def mouseDragEvent(self, ev: Any, axis: Any = None) -> None:  # noqa: N802 - Qt override
        if ev.button() == Qt.MouseButton.RightButton and axis is None:
            ev.accept()
            if ev.isFinish():
                self.rbScaleBox.hide()
                start = ev.buttonDownPos(Qt.MouseButton.RightButton)
                rect = self.childGroup.mapRectFromParent(
                    pg.QtCore.QRectF(pg.Point(start), pg.Point(ev.pos())).normalized()
                )
                if rect.width() > 0 and rect.height() > 0:
                    self.showAxRect(rect)
            else:
                self.updateScaleBox(ev.buttonDownPos(Qt.MouseButton.RightButton), ev.pos())
            return
        super().mouseDragEvent(ev, axis)

    def mouseClickEvent(self, ev: Any) -> None:  # noqa: N802 - Qt override
        if ev.double() and ev.button() == Qt.MouseButton.LeftButton:
            ev.accept()
            self.reset_requested.emit()
            return
        super().mouseClickEvent(ev)


@dataclass
class Series:
    """One curve: the full stored data and how it is drawn."""

    name: str
    x: np.ndarray
    y: np.ndarray
    color: str
    item: Any
    key: str = ""
    processing: str = ""
    readout: bool = False
    legend: bool = True
    width: float = 1.4
    style: Qt.PenStyle = Qt.PenStyle.SolidLine
    #: x in plot coordinates (log10 for frequency charts), sorted.
    px: np.ndarray = field(default_factory=lambda: np.zeros(0))
    visible: bool = True
    dash: tuple[float, ...] | None = None


#: Dash patterns (in pen widths) for curves of one measurement that differ by
#: band: none is solid, so the broadband curve stays the only solid one.
BAND_DASHES: tuple[tuple[float, ...], ...] = (
    (5, 2),
    (1, 1.5),
    (6, 2, 1.5, 2),
    (3, 1, 1, 1, 1, 1),
    (9, 3),
    (2, 3),
    (8, 2, 1.5, 2, 1.5, 2),
    (4, 4),
    (1, 3),
    (12, 2, 3, 2),
)


def make_pen(
    color: QColor | str,
    width: float,
    style: Qt.PenStyle = Qt.PenStyle.SolidLine,
    dash: Sequence[float] | None = None,
) -> Any:
    if dash:
        return pg.mkPen(color, width=width, dash=list(dash))
    return pg.mkPen(color, width=width, style=style)


def swatch_icon(
    color: str,
    style: Qt.PenStyle = Qt.PenStyle.SolidLine,
    size: int = 14,
    dash: Sequence[float] | None = None,
) -> QIcon:
    """A small coloured line, as the curve is drawn, for lists and legends."""
    pixmap = QPixmap(QSize(size * 2, size))
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = make_pen(QColor(color), 2 if dash else 3, style, dash)
    painter.setPen(pen)
    painter.drawLine(QPointF(2, size / 2), QPointF(size * 2 - 2, size / 2))
    painter.end()
    return QIcon(pixmap)


def dispose_charts(widget: QWidget) -> None:
    """:meth:`ChartPanel.dispose` every chart inside ``widget`` (it is closing for good)."""
    for chart in widget.findChildren(ChartPanel):
        chart.dispose()


class ChartPanel(QWidget):
    """A plot, its legend, its readout and its export menu."""

    #: Emitted with the series key when its legend chip is toggled.
    visibility_changed = Signal(str, bool)

    def __init__(
        self,
        x_kind: str = X_LINEAR,
        *,
        x_label: str = "",
        y_label: str = "",
        y_unit: str = "dB",
        title: str = "",
        y_frequency: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.x_kind = x_kind
        #: The y axis is ``log10(Hz)`` (spectrogram); values are given in plot units.
        self.y_frequency = y_frequency
        #: ``(plot_x, plot_y) -> text`` that replaces the curve readout (images).
        self.readout_hook: Callable[[float, float], str | None] | None = None
        self.y_unit = y_unit
        self.series: list[Series] = []
        self._extra_items: list[Any] = []
        self._default_x: tuple[float, float] | None = None
        self._default_y: tuple[float, float] | None = None
        self.export_name = "chart"
        self.title_text = title
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        top = QHBoxLayout()
        top.setSpacing(6)
        self.title = QLabel(title)
        self.title.setProperty("role", "section")
        self.title.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        top.addWidget(self.title, 1)
        self.readout = QLabel("")
        self.readout.setProperty("role", "hint")
        self.readout.setMinimumWidth(180)
        self.readout.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.readout.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        top.addWidget(self.readout, 1)
        self.reset_button = QToolButton()
        self.reset_button.setText(_("Reset view"))
        self.reset_button.setToolTip(_("Fit the chart again (R or double-click)."))
        self.reset_button.clicked.connect(self.reset_view)
        top.addWidget(self.reset_button)
        self.export_button = QToolButton()
        self.export_button.setText(_("Export"))
        self.export_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(self.export_button)
        menu.addAction(_("Chart as PNG..."), lambda: self._ask_export("png"))
        menu.addAction(_("Chart as SVG..."), lambda: self._ask_export("svg"))
        menu.addAction(_("Curves as CSV..."), lambda: self._ask_export("csv"))
        self.export_menu = menu
        self.export_button.setMenu(menu)
        top.addWidget(self.export_button)
        layout.addLayout(top)
        # The legend scrolls sideways rather than widening the chart: ten
        # bands or eight overlays must not push the window past a laptop screen.
        legend_box = QWidget()
        self.legend_row = QHBoxLayout(legend_box)
        self.legend_row.setContentsMargins(0, 0, 0, 0)
        self.legend_row.setSpacing(2)
        self.legend_area = QScrollArea()
        self.legend_area.setWidget(legend_box)
        self.legend_area.setWidgetResizable(True)
        self.legend_area.setFrameShape(QScrollArea.Shape.NoFrame)
        self.legend_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.legend_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.legend_area.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.legend_area.setFixedHeight(30)
        layout.addWidget(self.legend_area)

        axis_items: dict[str, Any] = {}
        if x_kind == X_FREQUENCY:
            axis_items["bottom"] = LogFrequencyAxis(orientation="bottom")
        if y_frequency:
            axis_items["left"] = LogFrequencyAxis(orientation="left")
        self.view_box = ChartViewBox()
        self.view_box.reset_requested.connect(self.reset_view)
        self.plot = plot_widget(viewBox=self.view_box, axisItems=axis_items)
        self.plot.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.plot_item = self.plot.getPlotItem()
        disable_menus(self.plot_item)
        self.plot_item.showGrid(x=True, y=True, alpha=0.25)
        self.plot.setMinimumHeight(140)
        layout.addWidget(self.plot, 1)
        # Why the chart is empty (nothing stored, nothing selected), over the plot.
        self.message = QLabel(self.plot)
        self.message.setProperty("role", "hint")
        self.message.setWordWrap(True)
        self.message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.message.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.message.hide()
        self.set_labels(x_label, y_label)

        self.cursor_line = pg.InfiniteLine(angle=90, movable=False)
        self.cursor_line.setZValue(50)
        self.cursor_line.hide()
        self.plot_item.addItem(self.cursor_line, ignoreBounds=True)
        self.cursor_dot = pg.ScatterPlotItem(size=8)
        self.cursor_dot.setZValue(51)
        self.plot_item.addItem(self.cursor_dot, ignoreBounds=True)
        self._mouse_proxy = pg.SignalProxy(
            self.plot.scene().sigMouseMoved, rateLimit=60, slot=self._on_mouse_moved
        )
        self._decimate_timer = QTimer(self)
        self._decimate_timer.setSingleShot(True)
        self._decimate_timer.setInterval(30)
        self._decimate_timer.timeout.connect(self._redecimate)
        self.view_box.sigXRangeChanged.connect(lambda *_a: self._decimate_timer.start())
        self._disposed = False
        self.restyle()

    def dispose(self) -> None:
        """Tear the pyqtgraph plot down in pyqtgraph's own order (``PlotWidget.close``).

        Left to the destructors, the scene deleted its items in whatever order
        Python's collector had left them, and it crashed now and then. The
        window calls this when it closes for good; a chart shown as a window of
        its own (tests, the benchmark) does it when it is closed. Afterwards
        the chart draws nothing.
        """
        if self._disposed:
            return
        self._disposed = True
        self._decimate_timer.stop()
        self._mouse_proxy.disconnect()
        self.series = []
        self._extra_items = []
        close_plot_widget(self.plot)

    def closeEvent(self, event: Any) -> None:  # noqa: N802 - Qt override
        if self.isWindow():
            self.dispose()
        super().closeEvent(event)

    # --- appearance -------------------------------------------------------------

    def set_labels(self, x_label: str, y_label: str) -> None:
        self.x_label = x_label
        self.y_label = y_label
        self.plot_item.setLabel("bottom", x_label)
        self.plot_item.setLabel("left", y_label)

    def set_message(self, text: str) -> None:
        """Say in the middle of the plot why it is empty; ``""`` hides it."""
        self.message.setText(text)
        self.message.setVisible(bool(text))
        self._place_message()

    def _place_message(self) -> None:
        rect = self.plot.rect().adjusted(40, 20, -20, -40)
        self.message.setGeometry(rect)

    def resizeEvent(self, event: Any) -> None:  # noqa: N802 - Qt override
        super().resizeEvent(event)
        self._place_message()

    def set_title(self, text: str) -> None:
        self.title_text = text
        self.title.setText(text)

    def restyle(self) -> None:
        if self._disposed:
            return
        t = tokens()
        self.plot.setBackground(QColor(t["surface"]))
        for name in ("bottom", "left"):
            axis = self.plot_item.getAxis(name)
            axis.setPen(pg.mkPen(QColor(t["muted"])))
            axis.setTextPen(pg.mkPen(QColor(t["text"])))
        self.cursor_line.setPen(pg.mkPen(QColor(t["muted"]), width=1, style=Qt.PenStyle.DashLine))
        self.plot_item.setLabel("bottom", self.x_label, color=t["text"])
        self.plot_item.setLabel("left", self.y_label, color=t["text"])

    # --- content ----------------------------------------------------------------

    def to_plot_x(self, x: np.ndarray) -> np.ndarray:
        if self.x_kind == X_FREQUENCY:
            with np.errstate(divide="ignore", invalid="ignore"):
                return np.where(x > 0, np.log10(np.maximum(x, 1e-12)), np.nan)
        return np.asarray(x, dtype=np.float64)

    def from_plot_x(self, value: float) -> float:
        return float(10.0**value) if self.x_kind == X_FREQUENCY else float(value)

    def clear(self) -> None:
        if self._disposed:
            return
        for series in self.series:
            self.plot_item.removeItem(series.item)
        for item in self._extra_items:
            self.plot_item.removeItem(item)
        self.series = []
        self._extra_items = []
        self.cursor_dot.setData([], [])
        self.set_message("")
        self._rebuild_legend()

    def add_curve(
        self,
        name: str,
        x: Sequence[float] | np.ndarray,
        y: Sequence[float] | np.ndarray,
        *,
        color: str,
        width: float = 1.4,
        style: Qt.PenStyle = Qt.PenStyle.SolidLine,
        key: str = "",
        processing: str = "",
        readout: bool = False,
        legend: bool = True,
        z: float = 0.0,
        alpha: int = 255,
        dash: Sequence[float] | None = None,
    ) -> Series:
        xa = np.asarray(x, dtype=np.float64)
        ya = np.asarray(y, dtype=np.float64)
        px = self.to_plot_x(xa)
        order = np.argsort(px, kind="stable") if px.size and np.any(np.diff(px) < 0) else None
        if order is not None:
            xa, ya, px = xa[order], ya[order], px[order]
        qcolor = QColor(color)
        qcolor.setAlpha(alpha)
        item = pg.PlotCurveItem(pen=make_pen(qcolor, width, style, dash))
        item.setZValue(z)
        self.plot_item.addItem(item)
        series = Series(
            name=name,
            x=xa,
            y=ya,
            color=color,
            item=item,
            key=key,
            processing=processing,
            readout=readout,
            legend=legend,
            width=width,
            style=style,
            px=px,
            dash=tuple(dash) if dash else None,
        )
        self.series.append(series)
        self._draw_series(series, None)
        self._rebuild_legend()
        return series

    def add_item(self, item: Any, *, ignore_bounds: bool = True) -> Any:
        """Any other pyqtgraph item (markers, regions, lines); cleared with the curves."""
        self.plot_item.addItem(item, ignoreBounds=ignore_bounds)
        self._extra_items.append(item)
        return item

    def add_region(self, x0: float, x1: float, *, color: str, alpha: int = 40) -> Any:
        """A shaded x interval (natural units)."""
        lo, hi = (float(v) for v in self.to_plot_x(np.array([x0, x1], dtype=np.float64)))
        fill = QColor(color)
        fill.setAlpha(alpha)
        region = pg.LinearRegionItem(values=(lo, hi), movable=False, brush=fill)
        for line in region.lines:
            line.setPen(pg.mkPen(None))
        region.setZValue(-10)
        return self.add_item(region)

    def add_hline(self, y: float, *, color: str, style: Qt.PenStyle = Qt.PenStyle.DashLine) -> Any:
        line = pg.InfiniteLine(pos=y, angle=0, movable=False, pen=pg.mkPen(color, style=style))
        return self.add_item(line)

    def add_vline(self, x: float, *, color: str, style: Qt.PenStyle = Qt.PenStyle.DashLine) -> Any:
        pos = float(self.to_plot_x(np.array([x], dtype=np.float64))[0])
        line = pg.InfiniteLine(pos=pos, angle=90, movable=False, pen=pg.mkPen(color, style=style))
        return self.add_item(line)

    def add_text(self, text: str, x: float, y: float, *, color: str) -> Any:
        item = pg.TextItem(text, color=color, anchor=(0, 1))
        pos = float(self.to_plot_x(np.array([x], dtype=np.float64))[0])
        item.setPos(pos, y)
        return self.add_item(item)

    def add_markers(
        self,
        x: Sequence[float] | np.ndarray,
        y: Sequence[float] | np.ndarray,
        *,
        color: str,
        symbol: str = "o",
        size: float = 9.0,
        filled: bool = False,
        on_click: Callable[[int], None] | None = None,
        tips: Sequence[str] | None = None,
    ) -> Any:
        px = self.to_plot_x(np.asarray(x, dtype=np.float64))
        brush = pg.mkBrush(color) if filled else pg.mkBrush(None)
        spots = [
            {"pos": (float(a), float(b)), "data": i}
            for i, (a, b) in enumerate(zip(px, np.asarray(y, dtype=np.float64), strict=True))
        ]
        item = pg.ScatterPlotItem(
            spots=spots, symbol=symbol, size=size, pen=pg.mkPen(color, width=1.6), brush=brush
        )
        item.setZValue(20)
        if tips is not None:
            item.setToolTip("\n".join(tips))
        if on_click is not None:

            def clicked(_item: Any, points: Any, _ev: Any = None) -> None:
                if len(points):
                    on_click(int(points[0].data()))

            item.sigClicked.connect(clicked)
        return self.add_item(item, ignore_bounds=False)

    # --- ranges -----------------------------------------------------------------

    def set_default_range(
        self, x_range: tuple[float, float] | None, y_range: tuple[float, float] | None
    ) -> None:
        """The range Reset returns to (natural units); applied now."""
        if x_range is not None:
            lo, hi = (float(v) for v in self.to_plot_x(np.array(x_range, dtype=np.float64)))
            self._default_x = (lo, hi)
        else:
            self._default_x = None
        self._default_y = y_range
        self.reset_view()

    def reset_view(self) -> None:
        if self._disposed:
            return
        if self._default_x is None and self._default_y is None:
            self.view_box.autoRange(padding=0.02)
        else:
            if self._default_x is not None:
                self.view_box.setXRange(*self._default_x, padding=0.0)
            else:
                self.view_box.enableAutoRange(axis=pg.ViewBox.XAxis)
            if self._default_y is not None:
                self.view_box.setYRange(*self._default_y, padding=0.0)
            else:
                self.view_box.enableAutoRange(axis=pg.ViewBox.YAxis)
        self._redecimate()

    def visible_x_range(self) -> tuple[float, float]:
        (x0, x1), _y = self.view_box.viewRange()
        return self.from_plot_x(x0), self.from_plot_x(x1)

    # --- drawing ----------------------------------------------------------------

    def _draw_series(self, series: Series, x_range: tuple[float, float] | None) -> None:
        log = self.x_kind == X_FREQUENCY
        x, y = peak_subset(series.x, series.y, DISPLAY_POINTS, log_x=log, x_range=x_range)
        series.item.setData(self.to_plot_x(x), y, connect="finite")

    def _redecimate(self) -> None:
        if self._disposed:
            return
        if not self.series:
            return
        x_range = self.visible_x_range()
        for series in self.series:
            if series.x.shape[0] > DISPLAY_POINTS:
                self._draw_series(series, x_range)

    def _rebuild_legend(self) -> None:
        while self.legend_row.count():
            entry = self.legend_row.takeAt(0)
            widget = entry.widget() if entry is not None else None
            if widget is not None:
                widget.deleteLater()
        for series in self.series:
            if not series.legend:
                continue
            chip = QToolButton()
            chip.setCheckable(True)
            chip.setChecked(series.visible)
            chip.setAutoRaise(True)
            chip.setIcon(swatch_icon(series.color, series.style, dash=series.dash))
            chip.setText(series.name)
            chip.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            tip = series.name if not series.processing else f"{series.name}\n{series.processing}"
            chip.setToolTip(tip + "\n" + _("Click to hide or show this curve."))
            if series.readout:
                font = chip.font()
                font.setBold(True)
                chip.setFont(font)
            chip.toggled.connect(lambda on, s=series: self.set_series_visible(s, on))
            self.legend_row.addWidget(chip)
        self.legend_row.addStretch(1)
        self.legend_area.setVisible(any(s.legend for s in self.series))

    def set_series_visible(self, series: Series, visible: bool) -> None:
        series.visible = visible
        series.item.setVisible(visible)
        self.visibility_changed.emit(series.key, visible)

    # --- readout ----------------------------------------------------------------

    def readout_series(self) -> Series | None:
        visible = [s for s in self.series if s.visible and s.x.size]
        flagged = [s for s in visible if s.readout]
        chosen = flagged or visible
        return chosen[-1] if chosen else None

    def value_at(self, series: Series, plot_x: float) -> float | None:
        """The stored curve's value at ``plot_x`` (linear between stored points)."""
        px = series.px
        if px.size == 0 or not (px[0] <= plot_x <= px[-1]):
            return None
        index = int(np.searchsorted(px, plot_x))
        index = min(max(index, 1), px.shape[0] - 1)
        x0, x1 = px[index - 1], px[index]
        y0, y1 = series.y[index - 1], series.y[index]
        if not (math.isfinite(y0) and math.isfinite(y1)):
            return None
        if x1 == x0:
            return float(y1)
        return float(y0 + (y1 - y0) * (plot_x - x0) / (x1 - x0))

    def readout_text(self, plot_x: float, plot_y: float) -> str:
        if self.readout_hook is not None:
            hooked = self.readout_hook(plot_x, plot_y)
            if hooked is not None:
                return hooked
        x_text = format_x(self.x_kind, self.from_plot_x(plot_x))
        text = f"{x_text}   {plot_y:.1f} {self.y_unit}"
        series = self.readout_series()
        if series is not None:
            value = self.value_at(series, plot_x)
            if value is not None:
                text = f"{x_text}   {series.name}: {value:.1f} {self.y_unit}"
        return text

    def _on_mouse_moved(self, args: Any) -> None:
        if self._disposed:
            return
        pos = args[0]
        if not self.plot.sceneBoundingRect().contains(pos):
            return
        point = self.view_box.mapSceneToView(pos)
        x, y = float(point.x()), float(point.y())
        self.show_cursor(x, y)

    def show_cursor(self, plot_x: float, plot_y: float) -> None:
        if self._disposed:
            return
        self.cursor_line.setPos(plot_x)
        self.cursor_line.show()
        self.readout.setText(self.readout_text(plot_x, plot_y))
        series = self.readout_series()
        value = self.value_at(series, plot_x) if series is not None else None
        if series is not None and value is not None:
            self.cursor_dot.setData([plot_x], [value], brush=pg.mkBrush(series.color))
        else:
            self.cursor_dot.setData([], [])

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 - Qt override
        if event.key() == Qt.Key.Key_R and not event.modifiers():
            self.reset_view()
            return
        super().keyPressEvent(event)

    # --- export -----------------------------------------------------------------

    def _ask_export(self, kind: str) -> None:
        filters = {
            "png": _("PNG images (*.png)"),
            "svg": _("SVG images (*.svg)"),
            "csv": _("CSV files (*.csv)"),
        }
        path, _filter = QFileDialog.getSaveFileName(
            self, _("Export"), f"{self.export_name}.{kind}", filters[kind]
        )
        if not path:
            return
        target = Path(path)
        if target.suffix.lower() != f".{kind}":
            target = target.with_suffix(f".{kind}")
        self.export(kind, target)

    def export(self, kind: str, path: Path) -> Path:
        if kind == "png":
            png_export(self.plot, path)
        elif kind == "svg":
            svg_export(self.plot, path)
        else:
            self.export_csv(path)
        return path

    def export_csv(self, path: Path) -> Path:
        """Every visible curve at full stored resolution, in long form.

        The header says what each curve is and which display processing was
        applied to it, so an exported smoothed or aligned curve is never
        mistaken for the stored one.
        """
        with path.open("w", newline="", encoding="utf-8") as handle:
            handle.write(f"# ReverbScope {self.title_text}\n")
            handle.write(f"# x: {self.x_label}\n# y: {self.y_label}\n")
            visible = [s for s in self.series if s.visible]
            for series in visible:
                processing = series.processing or _("as stored")
                handle.write(f"# {series.name}: {processing}\n")
            writer = csv.writer(handle)
            writer.writerow(["curve", "x", "y"])
            for series in visible:
                for xv, yv in zip(series.x.tolist(), series.y.tolist(), strict=True):
                    if math.isfinite(xv) and math.isfinite(yv):
                        writer.writerow([series.name, f"{xv:.6g}", f"{yv:.6g}"])
        return path
