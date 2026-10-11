"""One chart panel of the workbench: a kind of chart, the measurements it
overlays, and the mouse that zooms, pans and picks in it.

The panel reads the :class:`~reverbscope.ui.document.WorkspaceDocument`
(which measurements are visible, selected, the baseline) and draws what it
holds; it computes no metric. Every visible measurement is drawn in its own
colour and line style, the selected one thicker and on top. Kinds that
show one measurement (impulse response, early reflections, placement) draw
the selected one and say so in the title.

Zooming changes the view only: the curves are what the result stored,
whatever the limits. Panels that share an axis key (frequency, seconds,
milliseconds) follow each other's x limits through a :class:`ZoomLink`; a
frequency axis is never tied to a time axis.
"""

from __future__ import annotations

import contextlib
import csv
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from typing import Any, cast

import numpy as np
from matplotlib.axes import Axes
from matplotlib.backend_bases import MouseButton, MouseEvent, PickEvent
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QShowEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMenu,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from reverbscope.i18n import _
from reverbscope.interpretation.profiles import noise_segment_text
from reverbscope.models.comparison import ComparisonResult
from reverbscope.models.result import AnalysisResult
from reverbscope.ui import plots
from reverbscope.ui.document import Measurement, WorkspaceDocument
from reverbscope.ui.export import export_figure_png
from reverbscope.ui.plot_data import (
    AXIS_NONE,
    PLOT_KINDS,
    Curve,
    PlotKind,
    decay_curves,
    frequency_curves,
    noise_curve,
    plot_kind,
)
from reverbscope.ui.qt import ensure_pyside6
from reverbscope.ui.theme import ensure_plot_fonts, plot_colors, style_figure
from reverbscope.ui.widgets import ask_save_path, error_box

#: Scope combo values: which measurements a multi-measurement kind overlays.
SCOPE_ALL = "all"
SCOPE_SELECTED = "selected"
SCOPE_BASELINE = "baseline"

#: Mouse-wheel zoom per notch, and how close (points) a click must come to
#: a marker or curve to pick it.
ZOOM_FACTOR = 1.25
PICK_RADIUS = 6

_WIDTH_SELECTED = 2.2
_WIDTH_OTHER = 1.2
_ALPHA_OTHER = 0.6
_ALPHA_DIMMED = 0.4

#: Cursor readout formats per axis: (x unit, x format, y unit, y format).
AxisUnits = tuple[str, str, str, str]
UNITS_FREQUENCY: AxisUnits = ("Hz", "{:.0f}", "dB", "{:.1f}")
UNITS_SECONDS: AxisUnits = ("s", "{:.2f}", "dB", "{:.1f}")
UNITS_MILLISECONDS: AxisUnits = ("ms", "{:.1f}", "dB", "{:.1f}")
UNITS_AMPLITUDE: AxisUnits = ("ms", "{:.1f}", "", "{:.3f}")
UNITS_METRES: AxisUnits = ("m", "{:.2f}", "m", "{:.2f}")


def _make_canvas(figure: Figure) -> Any:
    """matplotlib's Qt canvas, imported once PySide6 carries a version."""
    ensure_pyside6()
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg

    return cast(Any, FigureCanvasQTAgg)(figure)


@dataclass
class PlotContext:
    """What one draw works from: the measurements to overlay, the selected
    one (drawn on top), the baseline, the comparison in difference mode and
    the item the inspector asked to highlight."""

    visible: list[Measurement]
    selected: Measurement | None
    baseline: Measurement | None
    comparison: ComparisonResult | None = None
    highlight: dict[str, int] = field(default_factory=dict)


@dataclass
class _View:
    """The user's zoom of one kind: x limits, and y limits once touched."""

    xlim: tuple[float, float]
    ylim: tuple[float, float] | None = None


class ZoomLink(QObject):
    """Shares x limits between the panels of one window.

    Only panels whose current kind has the same axis key follow each other:
    two frequency axes, or two axes in seconds. ``enabled`` switches the
    linking off without forgetting the panels.
    """

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.enabled = True
        self._panels: list[PlotPanel] = []
        self._busy = False

    def register(self, panel: PlotPanel) -> None:
        if panel not in self._panels:
            self._panels.append(panel)

    def unregister(self, panel: PlotPanel) -> None:
        if panel in self._panels:
            self._panels.remove(panel)

    def panels(self) -> list[PlotPanel]:
        return list(self._panels)

    def propagate(self, origin: PlotPanel, axis_key: str, xlim: tuple[float, float]) -> None:
        """``origin`` changed its x limits: every other panel on ``axis_key`` follows."""
        if not self.enabled or axis_key == AXIS_NONE or self._busy:
            return
        self._busy = True
        try:
            for panel in list(self._panels):
                if panel is origin:
                    continue
                try:
                    panel.set_xlim_from_link(axis_key, xlim)
                except RuntimeError:
                    # The Qt widget is gone; the Python wrapper outlived it.
                    self._panels.remove(panel)
        finally:
            self._busy = False


def _zoomed(
    lo: float, hi: float, centre: float | None, factor: float, log: bool
) -> tuple[float, float]:
    """``(lo, hi)`` shrunk by ``factor`` (> 1 zooms in) around ``centre``."""
    if log:
        if lo <= 0.0 or hi <= 0.0 or (centre is not None and centre <= 0.0):
            return lo, hi
        lo, hi = float(np.log10(lo)), float(np.log10(hi))
        centre = (lo + hi) / 2.0 if centre is None else float(np.log10(centre))
    elif centre is None:
        centre = (lo + hi) / 2.0
    new_lo = centre - (centre - lo) / factor
    new_hi = centre + (hi - centre) / factor
    if log:
        return float(10.0**new_lo), float(10.0**new_hi)
    return new_lo, new_hi


def _shifted(
    limits: tuple[float, float], anchor: float, current: float, log: bool
) -> tuple[float, float]:
    """``limits`` moved so that the point now at ``current`` returns to ``anchor``."""
    lo, hi = limits
    if log:
        if anchor <= 0.0 or current <= 0.0 or lo <= 0.0 or hi <= 0.0:
            return limits
        ratio = anchor / current
        return lo * ratio, hi * ratio
    delta = anchor - current
    return lo + delta, hi + delta


class PlotPanel(QWidget):
    """A chart with its compact control bar.

    Signals: ``kind_changed(key)`` when the chart kind changes;
    ``item_selected(name, index)`` when a resonance marker, reflection
    marker or decay band of the selected measurement is clicked;
    ``status_message(text)`` with the outcome of an export started from the
    panel's own menu.
    """

    kind_changed = Signal(str)
    item_selected = Signal(str, int)
    status_message = Signal(str)

    def __init__(
        self,
        document: WorkspaceDocument,
        link: ZoomLink,
        parent: QWidget | None = None,
        *,
        kind: str = "frequency",
    ) -> None:
        super().__init__(parent)
        self._document = document
        self._link = link
        self._kind = plot_kind(kind)
        self._dirty = True
        self._highlight: dict[str, int] = {}
        self._comparison_provider: (
            Callable[[Measurement, Measurement], ComparisonResult | None] | None
        ) = None
        self._views: dict[str, _View] = {}
        self._data_limits: list[tuple[Axes, tuple[float, float], tuple[float, float]]] = []
        self._linked_axes: list[Axes] = []
        self._zoomable: list[Axes] = []
        self._axes_units: dict[int, AxisUnits] = {}
        self._pickable: list[tuple[Line2D, tuple[str, int]]] = []
        self._pan: tuple[Axes, float, float] | None = None
        self._pan_moved = False
        #: The click last answered with a pick: one click hits one item only,
        #: whatever number of artists lie under it. The event itself is kept
        #: (not its id, which CPython hands to a later event once freed).
        self._last_pick: MouseEvent | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        bar = QHBoxLayout()
        bar.setContentsMargins(4, 2, 4, 0)
        bar.setSpacing(6)
        self.kind_combo = QComboBox()
        self.kind_combo.setToolTip(_("Chart"))
        for plot in PLOT_KINDS:
            self.kind_combo.addItem(plot.title(), plot.key)
        self.kind_combo.currentIndexChanged.connect(self._kind_combo_changed)
        bar.addWidget(self.kind_combo)
        self.scope_combo = QComboBox()
        self.scope_combo.setToolTip(_("Measurements shown"))
        for title, key in (
            (_("All visible measurements"), SCOPE_ALL),
            (_("Selected only"), SCOPE_SELECTED),
            (_("Baseline and selected"), SCOPE_BASELINE),
        ):
            self.scope_combo.addItem(title, key)
        self.scope_combo.currentIndexChanged.connect(lambda _index: self.refresh())
        bar.addWidget(self.scope_combo)
        self.raw_check = QCheckBox(_("Raw curve"))
        self.raw_check.setToolTip(_("Also draw the unsmoothed response"))
        self.raw_check.toggled.connect(lambda _checked: self.refresh())
        bar.addWidget(self.raw_check)
        self.bands_check = QCheckBox(_("Octave bands"))
        self.bands_check.setToolTip(
            _("Also draw the octave-band decays of the selected measurement")
        )
        self.bands_check.toggled.connect(lambda _checked: self.refresh())
        bar.addWidget(self.bands_check)
        self.difference_button = QToolButton()
        self.difference_button.setText(_("Difference"))
        self.difference_button.setCheckable(True)
        self.difference_button.setToolTip(_("Candidate minus baseline"))
        self.difference_button.toggled.connect(lambda _checked: self.refresh())
        bar.addWidget(self.difference_button)
        self.reset_button = QToolButton()
        self.reset_button.setText(_("Reset zoom"))
        self.reset_button.setToolTip(_("Back to the full range (double-click does the same)"))
        self.reset_button.clicked.connect(self.reset_zoom)
        bar.addWidget(self.reset_button)
        bar.addStretch(1)
        self.readout = QLabel("")
        self.readout.setProperty("role", "hint")
        self.readout.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.readout.setMinimumWidth(140)
        self.readout.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        bar.addWidget(self.readout)
        self.export_button = QToolButton()
        self.export_button.setText(_("Export"))
        self.export_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.export_menu = QMenu(self.export_button)
        self.export_png_action = self.export_menu.addAction(_("Chart as PNG..."))
        self.export_png_action.triggered.connect(lambda _checked=False: self.export_png())
        self.export_csv_action = self.export_menu.addAction(_("Curves as CSV..."))
        self.export_csv_action.triggered.connect(lambda _checked=False: self.export_csv())
        self.export_button.setMenu(self.export_menu)
        bar.addWidget(self.export_button)
        layout.addLayout(bar)

        self.figure = Figure(figsize=(7.0, 4.0), dpi=100)
        self.canvas = _make_canvas(self.figure)
        self.canvas.setMinimumHeight(180)
        self.canvas.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(self.canvas, 1)
        self.canvas.mpl_connect("scroll_event", self._on_scroll)
        self.canvas.mpl_connect("button_press_event", self._on_press)
        self.canvas.mpl_connect("motion_notify_event", self._on_motion)
        self.canvas.mpl_connect("button_release_event", self._on_release)
        self.canvas.mpl_connect("pick_event", self._on_pick)

        link.register(self)
        document.measurement_added.connect(self._on_document_changed)
        document.measurement_removed.connect(self._on_document_changed)
        document.measurement_changed.connect(self._on_document_changed)
        document.visibility_changed.connect(self._on_document_changed)
        document.selection_changed.connect(self._on_selection_changed)
        document.baseline_changed.connect(self._on_baseline_changed)
        self._sync_kind_combo()
        self._update_controls()

    # --- kind, scope, highlight -----------------------------------------------------

    def kind(self) -> str:
        return self._kind.key

    def plot_kind(self) -> PlotKind:
        return self._kind

    def set_kind(self, key: str) -> None:
        new = plot_kind(key)
        if new.key == self._kind.key:
            self._sync_kind_combo()
            return
        self._kind = new
        self._pan = None
        self._sync_kind_combo()
        self._update_controls()
        self.kind_changed.emit(new.key)
        self.refresh()

    def scope(self) -> str:
        return str(self.scope_combo.currentData())

    def set_scope(self, key: str) -> None:
        index = self.scope_combo.findData(key)
        if index >= 0:
            self.scope_combo.setCurrentIndex(index)

    def set_highlight(self, name: str, index: int | None) -> None:
        """Emphasise one item of the selected measurement: a resonance or
        reflection marker (filled) or a decay band (the others dimmed)."""
        new = {} if index is None else {name: index}
        if new == self._highlight:
            return
        self._highlight = new
        self.refresh()

    def highlight(self) -> dict[str, int]:
        return dict(self._highlight)

    def set_comparison_provider(
        self, provider: Callable[[Measurement, Measurement], ComparisonResult | None] | None
    ) -> None:
        """``provider(baseline, candidate)`` gives the comparison drawn in
        difference mode; it is called only then."""
        self._comparison_provider = provider
        if self.difference_active():
            self.refresh()

    def difference_active(self) -> bool:
        return (
            self._kind.difference
            and self.difference_button.isEnabled()
            and self.difference_button.isChecked()
        )

    def save_state(self) -> dict[str, Any]:
        """The view choices (not the data) for the window's layout settings."""
        return {
            "kind": self._kind.key,
            "scope": self.scope(),
            "raw": self.raw_check.isChecked(),
            "bands": self.bands_check.isChecked(),
            "difference": self.difference_button.isChecked(),
        }

    def restore_state(self, state: dict[str, Any]) -> None:
        kind = state.get("kind")
        if isinstance(kind, str):
            with contextlib.suppress(KeyError):
                self.set_kind(kind)
        scope = state.get("scope")
        if isinstance(scope, str):
            self.set_scope(scope)
        self.raw_check.setChecked(bool(state.get("raw", False)))
        self.bands_check.setChecked(bool(state.get("bands", False)))
        self.difference_button.setChecked(bool(state.get("difference", False)))

    def _sync_kind_combo(self) -> None:
        index = self.kind_combo.findData(self._kind.key)
        if index >= 0 and index != self.kind_combo.currentIndex():
            self.kind_combo.blockSignals(True)
            self.kind_combo.setCurrentIndex(index)
            self.kind_combo.blockSignals(False)

    def _kind_combo_changed(self, index: int) -> None:
        key = self.kind_combo.itemData(index)
        if isinstance(key, str):
            self.set_kind(key)

    def _update_controls(self) -> None:
        kind = self._kind
        self.scope_combo.setVisible(kind.multi)
        self.raw_check.setVisible(kind.key == "frequency")
        self.bands_check.setVisible(kind.key == "decay")
        comparable = (
            kind.difference
            and self._document.baseline() is not None
            and self._document.candidate() is not None
        )
        self.difference_button.setVisible(kind.difference)
        self.difference_button.setEnabled(comparable)

    # --- document -------------------------------------------------------------------

    def _on_document_changed(self, *_args: object) -> None:
        self._update_controls()
        self.refresh()

    def _on_selection_changed(self, _id: object) -> None:
        self._highlight = {}
        self._update_controls()
        self.refresh()

    def _on_baseline_changed(self, _id: object) -> None:
        self._update_controls()
        self.refresh()

    def _scope_measurements(self) -> list[Measurement]:
        document = self._document
        selected = document.selected()
        if not self._kind.multi:
            return [selected] if selected is not None else []
        scope = self.scope()
        if scope == SCOPE_SELECTED:
            return [selected] if selected is not None else []
        if scope == SCOPE_BASELINE:
            chosen: list[Measurement] = []
            for measurement in (document.baseline(), selected):
                if measurement is not None and all(m.id != measurement.id for m in chosen):
                    chosen.append(measurement)
            return chosen
        return document.visible()

    def context(self) -> PlotContext:
        """What the next draw works from, built from the document."""
        document = self._document
        baseline = document.baseline()
        comparison: ComparisonResult | None = None
        if self.difference_active():
            candidate = document.candidate()
            if self._comparison_provider is not None and baseline is not None and candidate:
                comparison = self._comparison_provider(baseline, candidate)
        return PlotContext(
            visible=self._scope_measurements(),
            selected=document.selected(),
            baseline=baseline,
            comparison=comparison,
            highlight=dict(self._highlight),
        )

    # --- lifecycle ------------------------------------------------------------------

    def refresh(self) -> None:
        """Draw again now when the panel is on screen; otherwise when it is shown."""
        self._dirty = True
        if self.isVisible():
            self._draw()

    def restyle(self) -> None:
        self.refresh()

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802 - Qt override
        super().showEvent(event)
        if self._dirty:
            self._draw()

    def is_dirty(self) -> bool:
        return self._dirty

    # --- drawing --------------------------------------------------------------------

    def _draw(self) -> None:
        self._dirty = False
        self._pan = None
        self._pickable = []
        self._axes_units = {}
        self._linked_axes = []
        self._zoomable = []
        fig = self.figure
        fig.clear()
        ensure_plot_fonts()
        self.canvas.setToolTip("")
        context = self.context()
        kind = self._kind
        if kind.multi:
            if not context.visible:
                self._empty(
                    _("No measurement loaded")
                    if len(self._document) == 0
                    else _("No visible measurement")
                )
            elif kind.key == "frequency":
                if self.difference_active() and self._document.candidate() is not None:
                    self._draw_frequency_difference(context)
                else:
                    self._draw_frequency(context)
            elif kind.key == "decay":
                if self.difference_active() and self._document.candidate() is not None:
                    self._draw_decay_difference(context)
                else:
                    self._draw_decay(context)
            else:
                self._draw_noise(context)
        elif context.selected is None:
            self._empty(_("No measurement selected"))
        else:
            self._draw_single(context, context.selected)
        self._apply_view()
        fig.set_layout_engine("tight")
        style_figure(fig)
        self.canvas.draw_idle()

    def _empty(self, text: str) -> None:
        ax = self.figure.add_subplot(1, 1, 1)
        ax.text(
            0.5,
            0.5,
            text,
            ha="center",
            va="center",
            transform=ax.transAxes,
            color=plot_colors()["muted"],
        )
        ax.set_axis_off()

    def _not_stored(self, ax: Axes, text: str) -> None:
        ax.text(0.5, 0.5, text, ha="center", va="center", transform=ax.transAxes)
        ax.set_axis_off()

    def _register_axes(self, ax: Axes, units: AxisUnits, *, linked: bool) -> None:
        self._zoomable.append(ax)
        self._axes_units[id(ax)] = units
        if linked and self._kind.axis != AXIS_NONE:
            self._linked_axes.append(ax)

    @staticmethod
    def _ordered(context: PlotContext) -> list[Measurement]:
        """The measurements to draw, the selected one last (on top)."""
        selected = context.selected
        others = [m for m in context.visible if selected is None or m.id != selected.id]
        if selected is not None and any(m.id == selected.id for m in context.visible):
            others.append(selected)
        return others

    @staticmethod
    def _is_selected(measurement: Measurement, context: PlotContext) -> bool:
        return context.selected is not None and measurement.id == context.selected.id

    @staticmethod
    def _legend_label(label: str, measurement: Measurement, context: PlotContext) -> str:
        if context.baseline is not None and measurement.id == context.baseline.id:
            return _("{name} (baseline)").format(name=label)
        return label

    def _plot_curve(
        self,
        ax: Axes,
        curve: Curve,
        *,
        selected: bool,
        label: str,
        log_x: bool = False,
        pick: bool = False,
    ) -> Line2D:
        width = _WIDTH_SELECTED if selected else _WIDTH_OTHER
        alpha = 1.0 if selected else _ALPHA_OTHER
        if curve.secondary:
            width *= 0.5
            alpha *= 0.7
        if curve.emphasis:
            width = _WIDTH_SELECTED + 1.0
            alpha = 1.0
        kwargs: dict[str, Any] = {
            "color": curve.colour,
            "linestyle": curve.style,
            "linewidth": width,
            "alpha": alpha,
            "label": label,
        }
        if pick:
            kwargs["picker"] = True
            kwargs["pickradius"] = PICK_RADIUS
        (line,) = ax.plot(curve.x, curve.y, **kwargs)
        if log_x:
            ax.set_xscale("log")
        if pick and curve.item is not None:
            self._pickable.append((line, curve.item))
        return line

    def _pick_markers(
        self,
        ax: Axes,
        xs: Sequence[float],
        ys: Sequence[float],
        name: str,
        *,
        colour: str,
        highlight: int | None,
    ) -> None:
        """Invisible pick targets over the markers a plot function drew, and
        a filled marker on the highlighted one."""
        for index, (x, y) in enumerate(zip(xs, ys, strict=True)):
            if not (np.isfinite(x) and np.isfinite(y)):
                continue
            (line,) = ax.plot(
                [x],
                [y],
                "o",
                markersize=9,
                alpha=0.0,
                label="_nolegend_",
                picker=True,
                pickradius=PICK_RADIUS,
            )
            self._pickable.append((line, (name, index)))
        if highlight is not None and 0 <= highlight < len(xs):
            ax.plot(
                [xs[highlight]],
                [ys[highlight]],
                "o",
                markersize=9,
                markerfacecolor=colour,
                markeredgecolor=colour,
                alpha=0.9,
                label="_nolegend_",
            )

    def _selected_title(self, measurement: Measurement) -> None:
        self.figure.suptitle(
            _("{name} (selected measurement only)").format(name=measurement.name()),
            fontsize=10,
            color=plot_colors()["fg"],
        )

    # frequency

    def _draw_frequency(self, context: PlotContext) -> None:
        ax = self.figure.add_subplot(1, 1, 1)
        ordered = self._ordered(context)
        raw = self.raw_check.isChecked()
        finite: list[float] = []
        top_hz = 20.0
        drawn = 0
        for measurement in ordered:
            selected = self._is_selected(measurement, context)
            for curve in frequency_curves(measurement, raw=raw):
                self._plot_curve(
                    ax,
                    curve,
                    selected=selected,
                    label=self._legend_label(curve.label, measurement, context),
                    log_x=True,
                )
                drawn += 1
                if not curve.secondary:
                    finite.extend(float(v) for v in curve.y[np.isfinite(curve.y)])
            top_hz = max(top_hz, measurement.result.sample_rate / 2.0)
        if drawn == 0:
            self._not_stored(ax, _("No frequency response stored with this session"))
            return
        selected_m = context.selected
        if selected_m is not None and any(m.id == selected_m.id for m in ordered):
            self._mark_resonances(ax, selected_m, context.highlight.get("resonance"))
        ax.set_xlim(20.0, top_hz)
        if finite:
            top = float(np.percentile(finite, 99.5))
            ax.set_ylim(top - 60.0, top + 10.0)
        ax.set_xlabel(_("Frequency (Hz)"))
        ax.set_ylabel(_("Magnitude (dB, relative)"))
        if len(ordered) == 1:
            ax.set_title(
                _("Frequency response ({window:.2f} s window)").format(
                    window=ordered[0].result.frequency_response.window_s
                )
            )
        else:
            ax.set_title(_("Frequency response, {n} measurements").format(n=len(ordered)))
        ax.grid(True, which="both", alpha=0.3)
        ax.legend(loc="lower left", fontsize="small")
        self._register_axes(ax, UNITS_FREQUENCY, linked=True)

    def _mark_resonances(self, ax: Axes, measurement: Measurement, highlight: int | None) -> None:
        result = measurement.result
        fr = result.frequency_response
        curve = (
            fr.magnitude_db_smoothed
            if fr.magnitude_db_smoothed is not None
            else fr.magnitude_db_raw
        )
        if curve.size == 0 or not result.resonances.candidates:
            return
        plots._mark_resonances(ax, result, highlight)
        xs: list[float] = []
        ys: list[float] = []
        for candidate in result.resonances.candidates:
            position = int(np.argmin(np.abs(fr.frequencies_hz - candidate.frequency_hz)))
            xs.append(candidate.frequency_hz)
            ys.append(float(curve[position]))
        # The plot function fills the chosen marker itself; here only the
        # pick targets are added (highlight=None keeps a second marker away).
        self._pick_markers(ax, xs, ys, "resonance", colour=measurement.colour, highlight=None)

    def _draw_frequency_difference(self, context: PlotContext) -> None:
        baseline = context.baseline
        candidate = self._document.candidate()
        assert baseline is not None and candidate is not None
        fig = self.figure
        ax_curves = fig.add_subplot(2, 1, 1)
        ax_diff = fig.add_subplot(2, 1, 2, sharex=ax_curves)
        raw = self.raw_check.isChecked()
        finite: list[float] = []
        top_hz = 20.0
        drawn = 0
        for measurement, suffix in (
            (baseline, _("{name} (baseline)")),
            (candidate, _("{name} (candidate)")),
        ):
            selected = measurement.id == candidate.id
            for curve in frequency_curves(measurement, raw=raw):
                self._plot_curve(
                    ax_curves,
                    curve,
                    selected=selected,
                    label=suffix.format(name=curve.label),
                    log_x=True,
                )
                drawn += 1
                if not curve.secondary:
                    finite.extend(float(v) for v in curve.y[np.isfinite(curve.y)])
            top_hz = max(top_hz, measurement.result.sample_rate / 2.0)
        if drawn == 0:
            ax_curves.text(
                0.5,
                0.5,
                _("No frequency response stored with this session"),
                ha="center",
                va="center",
                transform=ax_curves.transAxes,
            )
        else:
            ax_curves.legend(loc="lower left", fontsize="small")
        if finite:
            top = float(np.percentile(finite, 99.5))
            ax_curves.set_ylim(top - 50.0, top + 8.0)
        ax_curves.set_ylabel(_("Magnitude (dB, relative)"))
        ax_curves.set_title(_("Frequency response: one scale for both takes"))
        ax_curves.grid(True, which="both", alpha=0.3)
        ax_curves.tick_params(labelbottom=False)
        self._register_axes(ax_curves, UNITS_FREQUENCY, linked=True)
        delta = context.comparison.frequency_response if context.comparison is not None else None
        if delta is not None and delta.frequencies_hz.size:
            ax_diff.semilogx(
                delta.frequencies_hz,
                delta.difference_db,
                color=candidate.colour,
                linestyle="-",
                linewidth=1.4,
                label=_("{name} (candidate)").format(name=candidate.name()),
            )
            ax_diff.axhline(0.0, color=plot_colors()["muted"], linewidth=0.8)
            ax_diff.set_ylabel("Δ dB")
            ax_diff.set_title(_("Frequency-response difference (candidate − baseline)"))
            ax_diff.grid(True, which="both", alpha=0.3)
            self._register_axes(ax_diff, UNITS_FREQUENCY, linked=True)
        else:
            ax_diff.text(
                0.5,
                0.5,
                _("No difference curve"),
                ha="center",
                va="center",
                transform=ax_diff.transAxes,
            )
            ax_diff.set_axis_off()
        ax_curves.set_xlim(20.0, top_hz)
        ax_diff.set_xlabel(_("Frequency (Hz)"))

    # decay

    def _draw_decay(self, context: PlotContext) -> None:
        ax = self.figure.add_subplot(1, 1, 1)
        ordered = self._ordered(context)
        bands = self.bands_check.isChecked()
        highlight = context.highlight.get("band")
        drawn = 0
        for measurement in ordered:
            selected = self._is_selected(measurement, context)
            # The octave bands of one measurement only, the selected one (or
            # the single one shown): with two measurements the other one's
            # bands would be eight more dashed lines and legend rows.
            with_bands = bands and (selected or len(ordered) == 1)
            for curve in decay_curves(measurement, bands=with_bands):
                emphasis = selected and highlight is not None and curve.item == ("band", highlight)
                line = self._plot_curve(
                    ax,
                    replace(curve, emphasis=emphasis),
                    selected=selected,
                    label=self._legend_label(curve.label, measurement, context),
                    pick=selected,
                )
                if selected and highlight is not None and not emphasis:
                    line.set_alpha(_ALPHA_DIMMED)
                drawn += 1
        if drawn == 0:
            self._not_stored(ax, _("No decay curves stored with this session"))
            return
        ax.set_ylim(-70.0, 5.0)
        ax.set_xlabel(_("Time (s)"))
        ax.set_ylabel(_("Schroeder decay (dB, relative)"))
        ax.set_title(_("Energy decay curves (Lundeby-truncated)"))
        ax.grid(True, alpha=0.3)
        ax.legend(loc="upper right", fontsize="small")
        self._register_axes(ax, UNITS_SECONDS, linked=True)

    def _draw_decay_difference(self, context: PlotContext) -> None:
        baseline = context.baseline
        candidate = self._document.candidate()
        assert baseline is not None and candidate is not None
        ax = self.figure.add_subplot(1, 1, 1)
        drawn = 0
        for measurement, suffix in (
            (baseline, _("{name} (baseline)")),
            (candidate, _("{name} (candidate)")),
        ):
            for curve in decay_curves(measurement, bands=False):
                self._plot_curve(
                    ax,
                    curve,
                    selected=measurement.id == candidate.id,
                    label=suffix.format(name=curve.label),
                )
                drawn += 1
        if drawn == 0:
            self._not_stored(ax, _("No decay curves stored with this session"))
            return
        ax.set_ylim(-70.0, 5.0)
        ax.set_xlabel(_("Time (s)"))
        ax.set_ylabel(_("Schroeder decay (dB, relative)"))
        ax.set_title(_("Broadband decay: baseline and candidate"))
        ax.grid(True, alpha=0.3)
        ax.legend(loc="upper right", fontsize="small")
        self._register_axes(ax, UNITS_SECONDS, linked=True)

    # noise

    def _draw_noise(self, context: PlotContext) -> None:
        ax = self.figure.add_subplot(1, 1, 1)
        ordered = self._ordered(context)
        top_hz = 20.0
        drawn = 0
        for measurement in ordered:
            curve = noise_curve(measurement)
            top_hz = max(top_hz, measurement.result.sample_rate / 2.0)
            if curve is None:
                continue
            self._plot_curve(
                ax,
                curve,
                selected=self._is_selected(measurement, context),
                label=self._legend_label(curve.label, measurement, context),
                log_x=True,
            )
            drawn += 1
        if drawn == 0:
            selected = context.selected
            noise = selected.result.noise if selected is not None else None
            self._not_stored(
                ax,
                _("No quiet segment available")
                if noise is not None and noise.rms_dbfs is None
                else _("No noise spectrum stored with this session"),
            )
            return
        selected = context.selected
        if selected is not None and any(m.id == selected.id for m in ordered):
            self._mark_hum(ax, selected)
        ax.set_xlim(10.0, top_hz)
        ax.set_xlabel(_("Frequency (Hz)"))
        ax.set_ylabel(_("PSD (dB re FS^2/Hz)"))
        if len(ordered) == 1 and ordered[0].result.noise.rms_dbfs is not None:
            noise = ordered[0].result.noise
            ax.set_title(
                _("Background noise: {rms:.1f} dBFS RMS ({segment}), uncalibrated").format(
                    rms=noise.rms_dbfs, segment=noise_segment_text(noise.segment_source)
                )
            )
        else:
            ax.set_title(_("Background noise (dBFS, uncalibrated)"))
        ax.grid(True, which="both", alpha=0.3)
        ax.legend(loc="upper right", fontsize="small")
        self._register_axes(ax, UNITS_FREQUENCY, linked=True)

    @staticmethod
    def _mark_hum(ax: Axes, measurement: Measurement) -> None:
        noise = measurement.result.noise
        f = noise.psd_frequencies_hz
        psd = noise.psd_db
        if f is None or psd is None:
            return
        for hum in noise.hum:
            if not hum.detected:
                continue
            for freq, prominence in hum.harmonics:
                idx = int(np.argmin(np.abs(f - freq)))
                ax.plot(
                    [freq],
                    [psd[idx]],
                    "v",
                    color=measurement.colour,
                    markerfacecolor="none",
                    label="_nolegend_",
                )
                ax.annotate(
                    f"{freq:.0f} Hz +{prominence:.0f} dB",
                    (freq, float(psd[idx])),
                    fontsize="x-small",
                    color=plot_colors()["fg"],
                )

    # single-measurement kinds

    def _draw_single(self, context: PlotContext, measurement: Measurement) -> None:
        fig = self.figure
        result: AnalysisResult = measurement.result
        key = self._kind.key
        if key == "impulse":
            plots.plot_impulse_response(fig, result)
            axes = fig.get_axes()
            if len(axes) >= 2:
                self._register_axes(axes[0], UNITS_AMPLITUDE, linked=False)
                self._register_axes(axes[1], UNITS_SECONDS, linked=False)
        elif key == "reflections":
            plots.plot_reflections(fig, result)
            axes = fig.get_axes()
            if axes:
                self._add_reflection_targets(
                    axes[0], measurement, context.highlight.get("reflection")
                )
                self._register_axes(axes[0], UNITS_MILLISECONDS, linked=True)
        else:
            hint = plots.plot_placement_overview(
                fig, result, candidate_index=context.highlight.get("reflection")
            )
            self.canvas.setToolTip(hint)
            axes = fig.get_axes()
            if len(axes) >= 2:
                self._register_axes(axes[0], UNITS_METRES, linked=False)
                # The overview fills the chosen marker itself.
                self._add_reflection_targets(axes[1], measurement, None)
                self._register_axes(axes[1], UNITS_MILLISECONDS, linked=False)
        self._selected_title(measurement)

    def _add_reflection_targets(
        self, ax: Axes, measurement: Measurement, highlight: int | None
    ) -> None:
        reflections = measurement.result.reflections.reflections
        if not reflections:
            return
        self._pick_markers(
            ax,
            [r.delay_ms for r in reflections],
            [r.relative_db for r in reflections],
            "reflection",
            colour=measurement.colour,
            highlight=highlight,
        )

    # --- view: zoom, pan, link ------------------------------------------------------

    def _apply_view(self) -> None:
        self._data_limits = [(ax, ax.get_xlim(), ax.get_ylim()) for ax in self._zoomable]
        view = self._views.get(self._kind.key)
        if view is None or not self._linked_axes:
            return
        for ax in self._linked_axes:
            ax.set_xlim(view.xlim)
        if view.ylim is not None:
            self._linked_axes[0].set_ylim(view.ylim)

    def _store_view(self, *, y_changed: bool = False) -> None:
        if not self._linked_axes:
            return
        ax = self._linked_axes[0]
        previous = self._views.get(self._kind.key)
        ylim = ax.get_ylim() if y_changed else (previous.ylim if previous is not None else None)
        self._views[self._kind.key] = _View(ax.get_xlim(), ylim)

    def linked_xlim(self) -> tuple[float, float] | None:
        """The x limits the panel shares on its axis key, once drawn."""
        if not self._linked_axes:
            return None
        return self._linked_axes[0].get_xlim()

    def set_xlim_from_link(self, axis_key: str, xlim: tuple[float, float]) -> None:
        """Another panel on the same axis zoomed: follow its x limits."""
        if axis_key == AXIS_NONE or axis_key != self._kind.axis:
            return
        previous = self._views.get(self._kind.key)
        self._views[self._kind.key] = _View(
            (float(xlim[0]), float(xlim[1])), previous.ylim if previous is not None else None
        )
        if self._dirty or not self._linked_axes:
            return
        for ax in self._linked_axes:
            ax.set_xlim(xlim)
        if self.isVisible():
            self.canvas.draw_idle()

    def reset_zoom(self) -> None:
        """Back to the limits the data gave, and tell the linked panels."""
        self._views.pop(self._kind.key, None)
        if self._dirty:
            return
        for ax, xlim, ylim in self._data_limits:
            ax.set_xlim(xlim)
            ax.set_ylim(ylim)
        self.canvas.draw_idle()
        if self._linked_axes:
            self._link.propagate(self, self._kind.axis, self._linked_axes[0].get_xlim())

    def _view_changed(self, ax: Axes, *, y_changed: bool, propagate: bool) -> None:
        self._store_view(y_changed=y_changed)
        self.canvas.draw_idle()
        if propagate and ax in self._linked_axes:
            self._link.propagate(self, self._kind.axis, ax.get_xlim())

    def _on_scroll(self, event: MouseEvent) -> None:
        ax = event.inaxes
        if ax is None or ax not in self._zoomable or not event.step:
            return
        factor = ZOOM_FACTOR ** float(event.step)
        shift = "shift" in (event.modifiers or ()) or event.key == "shift"
        if shift:
            lo, hi = ax.get_ylim()
            ax.set_ylim(_zoomed(lo, hi, event.ydata, factor, ax.get_yscale() == "log"))
        else:
            lo, hi = ax.get_xlim()
            ax.set_xlim(_zoomed(lo, hi, event.xdata, factor, ax.get_xscale() == "log"))
        self._view_changed(ax, y_changed=shift, propagate=not shift)

    def _on_press(self, event: MouseEvent) -> None:
        if event.button != MouseButton.LEFT:
            return
        ax = event.inaxes
        if ax is None or ax not in self._zoomable:
            return
        if event.dblclick:
            self._pan = None
            self.reset_zoom()
            return
        if event.xdata is None or event.ydata is None:
            return
        self._pan = (ax, float(event.xdata), float(event.ydata))
        self._pan_moved = False

    def _on_motion(self, event: MouseEvent) -> None:
        self._update_readout(event)
        if self._pan is None or event.button != MouseButton.LEFT:
            return
        ax, x0, y0 = self._pan
        if event.inaxes is ax and event.xdata is not None and event.ydata is not None:
            x, y = float(event.xdata), float(event.ydata)
        else:
            point = ax.transData.inverted().transform((event.x, event.y))
            x, y = float(point[0]), float(point[1])
        if not (np.isfinite(x) and np.isfinite(y)):
            return
        ax.set_xlim(_shifted(ax.get_xlim(), x0, x, ax.get_xscale() == "log"))
        ax.set_ylim(_shifted(ax.get_ylim(), y0, y, ax.get_yscale() == "log"))
        self._pan_moved = True
        self._store_view(y_changed=True)
        self.canvas.draw_idle()

    def _on_release(self, _event: MouseEvent) -> None:
        if self._pan is None:
            return
        ax, _x0, _y0 = self._pan
        self._pan = None
        if self._pan_moved and ax in self._linked_axes:
            self._link.propagate(self, self._kind.axis, ax.get_xlim())

    def _update_readout(self, event: MouseEvent) -> None:
        ax = event.inaxes
        units = self._axes_units.get(id(ax)) if ax is not None else None
        if units is None or event.xdata is None or event.ydata is None:
            self.readout.setText("")
            return
        x_unit, x_format, y_unit, y_format = units
        x = x_format.format(event.xdata)
        y = y_format.format(event.ydata)
        self.readout.setText(f"{x} {x_unit}, {y} {y_unit}".replace(" ,", ",").rstrip())

    # --- picking --------------------------------------------------------------------

    def pick_items(self) -> list[tuple[Line2D, tuple[str, int]]]:
        """The pick targets of the current drawing: ``(artist, (name, index))``."""
        return list(self._pickable)

    def _on_pick(self, event: PickEvent) -> None:
        mouse = event.mouseevent
        if mouse.button != MouseButton.LEFT or mouse.dblclick:
            return
        if mouse is self._last_pick:
            return
        for artist, item in self._pickable:
            if artist is event.artist:
                self._last_pick = mouse
                name, index = item
                self.set_highlight(name, index)
                self.item_selected.emit(name, index)
                return

    # --- export ---------------------------------------------------------------------

    def _export_stem(self) -> str:
        selected = self._document.selected()
        stem = f"reverbscope-{self._kind.key}"
        if selected is not None and selected.path is not None:
            stem = f"{selected.path.name}-{self._kind.key}"
        return stem

    def export_png(self) -> str:
        """Save the chart as it is on screen; returns the status sentence."""
        if self._dirty and self.isVisible():
            self._draw()
        message = export_figure_png(self, self.figure, self._export_stem())
        if message:
            self.status_message.emit(message)
        return message

    def csv_columns(self) -> list[tuple[str, str, list[float], list[float]]]:
        """``(x header, y header, x, y)`` for every curve on the chart."""
        columns: list[tuple[str, str, list[float], list[float]]] = []
        for ax in self.figure.get_axes():
            x_label = ax.get_xlabel()
            y_label = ax.get_ylabel()
            for line in ax.get_lines():
                label = str(line.get_label())
                if label.startswith("_") or line.get_linestyle() in ("None", "none", ""):
                    continue
                xs = np.asarray(line.get_xdata(), dtype=np.float64)
                ys = np.asarray(line.get_ydata(), dtype=np.float64)
                if xs.size < 2:
                    continue
                columns.append(
                    (
                        f"{label}: {x_label}" if x_label else label,
                        f"{label}: {y_label}" if y_label else label,
                        [float(v) for v in xs],
                        [float(v) for v in ys],
                    )
                )
        return columns

    def export_csv(self) -> str:
        """Write the curves shown (x and y per measurement) to a CSV file the
        user picks; returns the status sentence."""
        if self._dirty and self.isVisible():
            self._draw()
        columns = self.csv_columns()
        if not columns:
            message = _("No curves to export")
            self.status_message.emit(message)
            return message
        target = ask_save_path(
            self, _("Save curves as CSV"), f"{self._export_stem()}.csv", _("CSV files (*.csv)")
        )
        if target is None:
            return ""
        rows = max(len(column[2]) for column in columns)
        try:
            with target.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.writer(handle)
                header: list[str] = []
                for x_header, y_header, _xs, _ys in columns:
                    header.extend((x_header, y_header))
                writer.writerow(header)
                for row in range(rows):
                    cells: list[str] = []
                    for _xh, _yh, xs, ys in columns:
                        if row < len(xs):
                            cells.extend((f"{xs[row]:.6g}", f"{ys[row]:.6g}"))
                        else:
                            cells.extend(("", ""))
                    writer.writerow(cells)
        except OSError as exc:
            message = _("The CSV file could not be written: {error}").format(error=str(exc))
            error_box(self, _("Cannot export"), message)
            return message
        message = _("Wrote {path}").format(path=target)
        self.status_message.emit(message)
        return message


__all__ = [
    "PICK_RADIUS",
    "SCOPE_ALL",
    "SCOPE_BASELINE",
    "SCOPE_SELECTED",
    "ZOOM_FACTOR",
    "PlotContext",
    "PlotPanel",
    "ZoomLink",
]
