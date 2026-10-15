"""An interactive graph: the instrument's screen with its controls and readout.

``PlotView`` wraps a matplotlib figure the way a measurement tool wraps its
graphs. A crosshair follows the pointer and the readout under the graph names
the value of every trace at that x; the wheel zooms around the pointer, a drag
pans (or draws a zoom box), a double click fits the view again, and the graph
can be copied or saved as an image. Nothing here changes a number: the plot
functions in :mod:`reverbscope.ui.plots` draw, this class only looks.
"""

from __future__ import annotations

import contextlib
import math
import re
from collections.abc import Callable, Sequence
from html import escape
from typing import Any

import numpy as np

from reverbscope.ui.qt import ensure_pyside6

ensure_pyside6()

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from reverbscope.i18n import _, pgettext
from reverbscope.ui.theme import apply_mono_font, plot_colors
from reverbscope.ui.widgets import ask_save_path, error_box

#: What a unit symbol looks like (``Hz``, ``dB re FS^2/Hz``, ``%``); words in other scripts are not.
_UNIT = re.compile(r"[A-Za-z%°µ/^0-9 .\-]+")

#: Most traces the readout lists at once; more would not fit on a line anyway.
MAX_READOUT_TRACES = 9
#: A drag shorter than this many pixels is a click, not a zoom box.
MIN_BOX_PIXELS = 6
#: Wheel zoom: the fraction of the visible range kept per notch.
WHEEL_STEP = 0.82
#: Notches of one wheel event that count; more would jump past the whole graph.
MAX_WHEEL_NOTCHES = 6
#: The tightest range a zoom may reach, as a fraction of the home range.
MIN_SPAN_FRACTION = 1e-4


def split_axis_label(text: str) -> tuple[str, str]:
    """``("Frequency", "Hz")`` from ``"Frequency (Hz)"`` (full-width brackets of
    the Chinese catalog too). The unit is the first item of the last bracket;
    a word such as ``relative`` is not a unit, and neither is any text that
    is not a unit symbol."""
    match = re.search(r"[(（]([^)）]*)[)）]\s*$", text)
    if match is None:
        return text.strip(), ""
    name = text[: match.start()].strip()
    unit = re.split(r"[,，]", match.group(1))[0].strip()
    if not _UNIT.fullmatch(unit) or unit.lower() == "relative":
        unit = ""
    return name, unit


def format_value(value: float, unit: str) -> str:
    """A readout number with its unit: kilohertz above 1 kHz, no clutter otherwise."""
    if not math.isfinite(value):
        return "-"
    if unit == "Hz":
        return f"{value / 1000.0:.3f} kHz" if abs(value) >= 1000.0 else f"{value:.1f} Hz"
    if unit in {"s", "ms"}:
        return f"{value:.3f} {unit}" if abs(value) < 10 else f"{value:.2f} {unit}"
    if unit == "dB" or unit.startswith("dB "):
        return f"{value:.1f} {unit}"
    text = f"{value:.4g}"
    return f"{text} {unit}".strip()


def _to_scale(value: float, scale: str) -> float:
    return math.log10(value) if scale == "log" else value


def _from_scale(value: float, scale: str) -> float:
    return 10.0**value if scale == "log" else value


def zoomed_limits(
    limits: tuple[float, float], anchor: float, factor: float, scale: str
) -> tuple[float, float]:
    """``limits`` scaled by ``factor`` about ``anchor`` (data units; log-aware)."""
    low, high = limits
    if scale == "log" and (low <= 0 or high <= 0 or anchor <= 0):
        return limits
    a = _to_scale(anchor, scale)
    lo, hi = _to_scale(low, scale), _to_scale(high, scale)
    return _from_scale(a + (lo - a) * factor, scale), _from_scale(a + (hi - a) * factor, scale)


def clamped_limits(
    limits: tuple[float, float], home: tuple[float, float], scale: str
) -> tuple[float, float]:
    """``limits`` moved (and narrowed if need be) to lie within ``home``."""
    if scale == "log" and (min(limits) <= 0 or min(home) <= 0):
        return limits
    lo, hi = sorted((_to_scale(limits[0], scale), _to_scale(limits[1], scale)))
    h_lo, h_hi = sorted((_to_scale(home[0], scale), _to_scale(home[1], scale)))
    span = min(hi - lo, h_hi - h_lo)
    span = max(span, (h_hi - h_lo) * MIN_SPAN_FRACTION)
    if lo < h_lo:
        lo = h_lo
    if lo + span > h_hi:
        lo = h_hi - span
    new = (_from_scale(lo, scale), _from_scale(lo + span, scale))
    # Keep the orientation the axis had (a reversed axis stays reversed).
    return new if limits[0] <= limits[1] else (new[1], new[0])


class PlotView(QFrame):
    """A graph with its toolbar and a readout line."""

    def __init__(self, parent: QWidget | None = None, *, figsize: tuple[float, float] = (7, 4.5)):
        super().__init__(parent)
        self.setProperty("panel", True)
        self.figure = Figure(figsize=figsize, dpi=100)
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.canvas.setMinimumHeight(220)
        self.canvas.setCursor(Qt.CursorShape.CrossCursor)
        self.canvas.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self._build_toolbar())
        outer.addWidget(self.canvas, 1)
        outer.addWidget(self._build_readout())

        #: ``"pan"`` or ``"zoom"``: what a left-button drag does.
        self.mode = "pan"
        self._home: dict[int, tuple[tuple[float, float], tuple[float, float]]] | None = None
        self._background: Any = None
        self._artists: dict[int, tuple[Line2D, Line2D, list[Line2D]]] = {}
        self._axes_key: tuple[int, ...] = ()
        self._drag: dict[str, Any] | None = None
        self._box: Rectangle | None = None
        self._sorted_cache: dict[tuple[int, int], bool] = {}
        for name, handler in (
            ("draw_event", self._on_draw),
            ("motion_notify_event", self._on_motion),
            ("button_press_event", self._on_press),
            ("button_release_event", self._on_release),
            ("scroll_event", self._on_scroll),
            ("figure_leave_event", self._on_leave),
            ("axes_leave_event", self._on_leave),
        ):
            connect: Any = self.canvas.mpl_connect  # one call for event names of several types
            connect(name, self._guarded(handler))

    @staticmethod
    def _guarded(handler: Callable[[Any], None]) -> Callable[[Any], None]:
        """``handler`` that ignores an event arriving after Qt deleted the widget.

        A closing window still sends leave and draw events to a canvas that Qt
        is taking apart; there is nothing left to draw on, and matplotlib would
        print a traceback for each one.
        """

        def call(event: Any) -> None:
            try:
                handler(event)
            except RuntimeError as exc:
                if "already deleted" not in str(exc):
                    raise

        return call

    # --- construction ----------------------------------------------------------
    def _build_toolbar(self) -> QFrame:
        bar = QFrame()
        bar.setProperty("toolbar", True)
        row = QHBoxLayout(bar)
        row.setContentsMargins(8, 4, 8, 4)
        row.setSpacing(4)
        self.pan_button = self._tool(_("Pan"), _("Drag to move the view. Wheel: zoom."), True)
        self.zoom_button = self._tool(_("Zoom"), _("Drag a box to zoom into it."), True)
        group = QButtonGroup(self)
        group.setExclusive(True)
        for button in (self.pan_button, self.zoom_button):
            group.addButton(button)
        self.pan_button.setChecked(True)
        self.pan_button.clicked.connect(lambda: self.set_mode("pan"))
        self.zoom_button.clicked.connect(lambda: self.set_mode("zoom"))
        self.fit_button = self._tool(
            pgettext("graph view", "Fit"), _("Show the whole graph again (double-click).")
        )
        self.fit_button.clicked.connect(self.reset_view)
        self.copy_button = self._tool(_("Copy image"), _("Copy the graph as an image."))
        self.copy_button.clicked.connect(self.copy_image)
        self.save_button = self._tool(_("Save image..."), _("Save the graph as a PNG file."))
        self.save_button.clicked.connect(self.save_image)
        row.addWidget(self.pan_button)
        row.addWidget(self.zoom_button)
        row.addWidget(self.fit_button)
        row.addStretch(1)
        row.addWidget(self.copy_button)
        row.addWidget(self.save_button)
        return bar

    def _tool(self, text: str, tip: str, checkable: bool = False) -> QToolButton:
        button = QToolButton()
        button.setText(text)
        button.setToolTip(tip)
        button.setCheckable(checkable)
        button.setProperty("plotTool", True)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        return button

    def _build_readout(self) -> QFrame:
        bar = QFrame()
        bar.setProperty("readout", True)
        row = QHBoxLayout(bar)
        row.setContentsMargins(10, 5, 10, 5)
        row.setSpacing(12)
        self.position = QLabel("")
        self.position.setProperty("role", "readout")
        apply_mono_font(self.position)
        self.position.setMinimumWidth(330)
        self.values = QLabel("")
        self.values.setProperty("role", "readout")
        self.values.setTextFormat(Qt.TextFormat.RichText)
        self.values.setWordWrap(True)
        self.values.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        apply_mono_font(self.values, pixel_size=11)
        self.hint = QLabel(_("Wheel: zoom  ·  Drag: pan  ·  Double-click: fit"))
        self.hint.setProperty("role", "readout-key")
        self.hint.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(self.position)
        row.addWidget(self.values, 1)
        row.addWidget(self.hint)
        bar.setMinimumHeight(34)
        self._idle_readout()
        return bar

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt override
        return QSize(720, 460)

    # --- drawing ---------------------------------------------------------------
    def redraw(self) -> None:
        """Draw the figure again after a plot function rebuilt it.

        The plot functions lay the figure out once, for the size it has then;
        the tight layout engine repeats that at every draw, so the axis labels
        still fit once the tab is shown or the window is resized. The view the
        figure is drawn with becomes the one Fit returns to.
        """
        self.figure.set_layout_engine("tight")
        self._home = None
        self._background = None
        self._drop_crosshair()
        self._artists = {}
        self._axes_key = ()
        self._sorted_cache = {}
        self._idle_readout()
        self.canvas.draw_idle()

    def _drop_crosshair(self) -> None:
        """Take the crosshair artists off the axes (a figure drawn again keeps its axes)."""
        for v, h, markers in self._artists.values():
            for artist in (v, h, *markers):
                with contextlib.suppress(ValueError, NotImplementedError, AttributeError):
                    artist.remove()
        self._artists = {}
        self._axes_key = ()

    def data_axes(self) -> list[Any]:
        """The axes that hold a graph (not an empty placeholder or a 3-D picture)."""
        return [
            ax
            for ax in self.figure.get_axes()
            if ax.axison and getattr(ax, "name", "rectilinear") == "rectilinear"
        ]

    def _ensure_home(self) -> dict[int, tuple[tuple[float, float], tuple[float, float]]]:
        """The limits the graph was drawn with, taken the first time they are needed."""
        if self._home is None:
            self._home = {
                id(ax): (tuple(ax.get_xlim()), tuple(ax.get_ylim())) for ax in self.data_axes()
            }
        return self._home

    def _on_draw(self, _event: object) -> None:
        self._ensure_home()
        self._background = self.canvas.copy_from_bbox(self.figure.bbox)

    # --- view control ----------------------------------------------------------
    def set_mode(self, mode: str) -> None:
        self.mode = "zoom" if mode == "zoom" else "pan"
        self.pan_button.setChecked(self.mode == "pan")
        self.zoom_button.setChecked(self.mode == "zoom")

    def reset_view(self) -> None:
        """Back to the view the graph was drawn with."""
        for ax in self.data_axes():
            home = self._ensure_home().get(id(ax))
            if home is not None:
                ax.set_xlim(*home[0])
                ax.set_ylim(*home[1])
        self.canvas.draw_idle()

    def _limits(self, ax: Any, axis: str) -> tuple[float, float]:
        low, high = ax.get_xlim() if axis == "x" else ax.get_ylim()
        return float(low), float(high)

    def _home_limits(self, ax: Any, axis: str) -> tuple[float, float] | None:
        home = self._ensure_home().get(id(ax))
        if home is None:
            return None
        return home[0] if axis == "x" else home[1]

    def _apply(self, ax: Any, axis: str, limits: tuple[float, float]) -> None:
        scale = ax.get_xscale() if axis == "x" else ax.get_yscale()
        home = self._home_limits(ax, axis)
        if home is not None:
            limits = clamped_limits(limits, home, scale)
        if axis == "x":
            ax.set_xlim(*limits)
        else:
            ax.set_ylim(*limits)

    def zoom(self, ax: Any, x: float, y: float, factor: float, axes: str = "xy") -> None:
        """Scale the view of ``ax`` by ``factor`` about the data point (x, y)."""
        if "x" in axes:
            self._apply(ax, "x", zoomed_limits(self._limits(ax, "x"), x, factor, ax.get_xscale()))
        if "y" in axes:
            self._apply(ax, "y", zoomed_limits(self._limits(ax, "y"), y, factor, ax.get_yscale()))
        self.canvas.draw_idle()

    def _on_scroll(self, event: Any) -> None:
        ax = event.inaxes
        if ax is None or event.xdata is None or event.ydata is None:
            return
        # A fast wheel reports several notches at once; a few are plenty.
        factor = WHEEL_STEP ** max(-MAX_WHEEL_NOTCHES, min(MAX_WHEEL_NOTCHES, float(event.step)))
        keys = str(event.key or "")
        axes = "y" if "shift" in keys else "xy" if ("control" in keys or "ctrl" in keys) else "x"
        self.zoom(ax, float(event.xdata), float(event.ydata), factor, axes)

    def _on_press(self, event: Any) -> None:
        ax = event.inaxes
        if ax is None or event.button != 1 or ax not in self.data_axes():
            return
        if event.dblclick:
            self.reset_view()
            return
        self._drag = {
            "ax": ax,
            "x": float(event.x),
            "y": float(event.y),
            "xlim": self._limits(ax, "x"),
            "ylim": self._limits(ax, "y"),
            "mode": self.mode,
        }
        if self.mode == "zoom":
            self._box = Rectangle(
                (0, 0), 0, 0, fill=True, alpha=0.18, animated=True,
                facecolor=plot_colors()["muted"], edgecolor=plot_colors()["fg"], linewidth=0.8,
            )  # fmt: skip
            ax.add_patch(self._box)

    def _on_release(self, event: Any) -> None:
        drag, self._drag = self._drag, None
        box, self._box = self._box, None
        if drag is None:
            return
        ax = drag["ax"]
        if box is not None:
            box.remove()
            moved = max(abs(float(event.x) - drag["x"]), abs(float(event.y) - drag["y"]))
            if moved >= MIN_BOX_PIXELS and event.x is not None:
                inverse = ax.transData.inverted()
                (x0, y0) = inverse.transform((drag["x"], drag["y"]))
                (x1, y1) = inverse.transform((float(event.x), float(event.y)))
                self._apply(ax, "x", self._ordered(ax, "x", float(x0), float(x1)))
                self._apply(ax, "y", self._ordered(ax, "y", float(y0), float(y1)))
            self.canvas.draw_idle()

    @staticmethod
    def _ordered(ax: Any, axis: str, a: float, b: float) -> tuple[float, float]:
        current = ax.get_xlim() if axis == "x" else ax.get_ylim()
        low, high = sorted((a, b))
        return (low, high) if current[0] <= current[1] else (high, low)

    def _pan(self, event: Any) -> None:
        drag = self._drag
        assert drag is not None
        ax = drag["ax"]
        width = float(ax.bbox.width) or 1.0
        height = float(ax.bbox.height) or 1.0
        for axis, delta in (
            ("x", (float(event.x) - drag["x"]) / width),
            ("y", (float(event.y) - drag["y"]) / height),
        ):
            start = drag["xlim"] if axis == "x" else drag["ylim"]
            scale = ax.get_xscale() if axis == "x" else ax.get_yscale()
            if scale == "log" and min(start) <= 0:
                continue
            lo, hi = _to_scale(start[0], scale), _to_scale(start[1], scale)
            shift = (hi - lo) * delta
            self._apply(ax, axis, (_from_scale(lo - shift, scale), _from_scale(hi - shift, scale)))

    # --- crosshair and readout -------------------------------------------------
    def _traces(self, ax: Any) -> list[Line2D]:
        lines = [
            line
            for line in ax.get_lines()
            if not str(line.get_label()).startswith("_") and len(line.get_xdata()) > 1
        ]
        return lines[:MAX_READOUT_TRACES]

    def _ensure_artists(self) -> None:
        axes = self.data_axes()
        key = tuple(id(ax) for ax in axes)
        if key == self._axes_key and self._artists:
            return
        self._artists = {}
        colors = plot_colors()
        for ax in axes:
            v = ax.axvline(float(np.mean(ax.get_xlim())), color=colors["fg"], linewidth=0.7)
            h = ax.axhline(float(np.mean(ax.get_ylim())), color=colors["fg"], linewidth=0.7)
            for line in (v, h):
                line.set_animated(True)
                line.set_alpha(0.55)
                line.set_visible(False)
                line.set_label("_crosshair")
            markers = []
            for trace in self._traces(ax):
                marker = Line2D(
                    [], [], marker="o", markersize=5.5, linestyle="none",
                    markerfacecolor=trace.get_color(), markeredgecolor=colors["bg"],
                    markeredgewidth=0.8, animated=True, visible=False,
                )  # fmt: skip
                marker.set_label("_marker")
                ax.add_line(marker)
                markers.append(marker)
            self._artists[id(ax)] = (v, h, markers)
        self._axes_key = key

    def _is_sorted(self, line: Line2D) -> bool:
        xs = np.asarray(line.get_xdata(), dtype=float)
        key = (id(line), int(xs.shape[0]))
        if key not in self._sorted_cache:
            self._sorted_cache[key] = bool(np.all(np.diff(xs) >= 0))
        return self._sorted_cache[key]

    def _on_motion(self, event: Any) -> None:
        if self._drag is not None and event.x is not None:
            drag = self._drag
            if drag["mode"] == "zoom":
                self._draw_box(event)
            else:
                self._pan(event)
                self.canvas.draw_idle()
            return
        ax = event.inaxes
        if ax is None or event.xdata is None or ax not in self.data_axes():
            self._hide_crosshair()
            return
        self._show_crosshair(ax, float(event.xdata), float(event.ydata))

    def _draw_box(self, event: Any) -> None:
        drag = self._drag
        box = self._box
        if drag is None or box is None or self._background is None:
            return
        ax = drag["ax"]
        inverse = ax.transData.inverted()
        x0, y0 = inverse.transform((drag["x"], drag["y"]))
        x1, y1 = inverse.transform((float(event.x), float(event.y)))
        box.set_xy((min(x0, x1), min(y0, y1)))
        box.set_width(abs(x1 - x0))
        box.set_height(abs(y1 - y0))
        self.canvas.restore_region(self._background)
        ax.draw_artist(box)
        self.canvas.blit(self.figure.bbox)

    def _show_crosshair(self, ax: Any, x: float, y: float) -> None:
        if self._background is None:
            return
        self._ensure_artists()
        entries: list[tuple[Line2D, float]] = []
        for key, (v, h, markers) in self._artists.items():
            active = key == id(ax)
            v.set_visible(active)
            h.set_visible(active)
            for marker in markers:
                marker.set_visible(False)
            if not active:
                continue
            v.set_xdata([x, x])
            h.set_ydata([y, y])
            for trace, marker in zip(self._traces(ax), markers, strict=False):
                value = self._value_at(trace, x)
                if value is None:
                    continue
                marker.set_data([x], [value])
                marker.set_visible(True)
                entries.append((trace, value))
        self._write_readout(ax, x, y, entries)
        self.canvas.restore_region(self._background)
        for key, (v, h, markers) in self._artists.items():
            target = next((a for a in self.data_axes() if id(a) == key), None)
            if target is None or not v.get_visible():
                continue
            target.draw_artist(v)
            target.draw_artist(h)
            for marker in markers:
                if marker.get_visible():
                    target.draw_artist(marker)
        self.canvas.blit(self.figure.bbox)

    def _hide_crosshair(self) -> None:
        if self._background is None or not self._artists:
            return
        shown = False
        for v, h, markers in self._artists.values():
            shown = shown or v.get_visible()
            v.set_visible(False)
            h.set_visible(False)
            for marker in markers:
                marker.set_visible(False)
        if shown:
            self.canvas.restore_region(self._background)
            self.canvas.blit(self.figure.bbox)
        self._idle_readout()

    def _on_leave(self, _event: object) -> None:
        if self._drag is None:
            self._hide_crosshair()

    def _value_at(self, line: Line2D, x: float) -> float | None:
        """The trace's y at ``x``, linearly interpolated; ``None`` outside it."""
        xs = np.asarray(line.get_xdata(), dtype=float)
        ys = np.asarray(line.get_ydata(), dtype=float)
        if xs.size < 2 or not self._is_sorted(line) or x < xs[0] or x > xs[-1]:
            return None
        value = float(np.interp(x, xs, ys))
        return value if math.isfinite(value) else None

    def _idle_readout(self) -> None:
        self.position.setText("")
        self.values.setText("")
        self.hint.setVisible(True)

    def _write_readout(
        self, ax: Any, x: float, y: float, entries: Sequence[tuple[Line2D, float]]
    ) -> None:
        x_name, x_unit = split_axis_label(str(ax.get_xlabel()))
        _y_name, y_unit = split_axis_label(str(ax.get_ylabel()))
        self.position.setText(
            f"{x_name or 'x'}  {format_value(x, x_unit)}   {format_value(y, y_unit)}"
        )
        parts = []
        for trace, value in entries:
            # "63 Hz  RT60~0.83 s": the name is what comes before the double space.
            label = str(trace.get_label()).split("  ")[0]
            swatch = escape(str(trace.get_color()))
            parts.append(
                f'<span style="color:{swatch}">●</span> {escape(label)} '
                f"<b>{escape(format_value(value, y_unit))}</b>"
            )
        self.values.setText("&nbsp;&nbsp;&nbsp;".join(parts))
        self.hint.setVisible(False)

    # --- export ----------------------------------------------------------------
    def copy_image(self) -> None:
        QGuiApplication.clipboard().setImage(self.canvas.grab().toImage())

    def save_image(self) -> None:
        path = ask_save_path(
            self, _("Save image"), "reverbscope-graph.png", _("PNG images (*.png)")
        )
        if path is None:
            return
        try:
            self.figure.savefig(path, dpi=200, facecolor=self.figure.get_facecolor())
        except (OSError, ValueError) as exc:
            error_box(self, _("Cannot save image"), str(exc))


class SweepPreview(PlotView):
    """The planned test signal, redrawn whenever the settings change."""

    def show_settings(self, settings: Any) -> None:
        from reverbscope.ui.plots import plot_sweep_plan

        plot_sweep_plan(self.figure, settings)
        self.redraw()
