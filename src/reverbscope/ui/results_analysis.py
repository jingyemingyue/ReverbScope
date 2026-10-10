"""The analysis workspace of a result: one chart group at a time.

Five groups (frequency and low end, decay, noise, impulse and early
reflections, placement geometry), chosen on the left; each draws its chart
when it is first shown, not when the result arrives, and its table selects
what the details pane explains.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, cast

from reverbscope.ui.qt import ensure_pyside6

ensure_pyside6()

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QSplitter,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from reverbscope.i18n import _
from reverbscope.models.result import AnalysisResult
from reverbscope.ui.placement_view import PlacementView
from reverbscope.ui.plots import (
    decay_table_rows,
    energy_table_rows,
    plot_decay,
    plot_frequency_response,
    plot_impulse_response,
    plot_noise,
    plot_reflections,
)
from reverbscope.ui.results_presenter import (
    GROUP_DECAY,
    GROUP_FREQUENCY,
    GROUP_IMPULSE,
    GROUP_NOISE,
    GROUP_PLACEMENT,
    GROUPS,
    band_detail_rows,
    group_title,
    impulse_detail_rows,
    noise_band_rows,
    noise_detail_rows,
    reflection_rows,
    resonance_detail_rows,
    resonance_note,
    resonance_rows,
)
from reverbscope.ui.theme import tokens
from reverbscope.ui.widgets import label


def _table(columns: Sequence[str], *, stretch_last: bool = True) -> QTableWidget:
    table = QTableWidget(0, len(columns))
    table.setHorizontalHeaderLabels(list(columns))
    table.horizontalHeader().setStretchLastSection(stretch_last)
    table.verticalHeader().setVisible(False)
    table.setAlternatingRowColors(True)
    table.setShowGrid(False)
    table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    return table


def fill_metric_table(table: QTableWidget, rows: Sequence[tuple[str, ...]]) -> None:
    """Rows of figures; a withheld or unreliable value is coloured and a
    missing one muted, so a blank never reads as zero."""
    colours = tokens()
    table.blockSignals(True)
    table.setRowCount(len(rows))
    for r, row in enumerate(rows):
        for c, value in enumerate(row):
            item = QTableWidgetItem(value)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            if c > 0 and (value.startswith("(") or value == _("insufficient range")):
                item.setForeground(QColor(colours["warn"]))
            elif c > 0 and value in {_("n/a"), "-"}:
                item.setForeground(QColor(colours["muted"]))
            if r == 0:
                font = item.font()
                font.setBold(True)
                item.setFont(font)
            table.setItem(r, c, item)
    table.resizeRowsToContents()
    table.blockSignals(False)


class GroupView(QWidget):
    """One chart with the table that belongs to it; drawn when shown."""

    #: ``(title, rows, note)`` for the details pane.
    detail_changed = Signal(str, object, str)

    def __init__(self, key: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.key = key
        self._result: AnalysisResult | None = None
        self._dirty = False
        self._highlight: int | None = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.note = QLabel("")
        self.note.setWordWrap(True)
        self.note.setProperty("role", "hint")
        self.note.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.note)
        self.splitter = QSplitter(Qt.Orientation.Vertical)
        self.figure = Figure(figsize=(7.0, 4.2), dpi=100)
        self.canvas: Any = cast(Any, FigureCanvasQTAgg)(self.figure)
        self.canvas.setMinimumHeight(240)
        self.splitter.addWidget(self.canvas)
        self.tables = QWidget()
        self.tables_layout = QVBoxLayout(self.tables)
        self.tables_layout.setContentsMargins(0, 0, 0, 0)
        self.tables_layout.setSpacing(4)
        self.splitter.addWidget(self.tables)
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 2)
        layout.addWidget(self.splitter, 1)

    # --- lifecycle --------------------------------------------------------------------

    def set_result(self, result: AnalysisResult) -> None:
        self._result = result
        self._highlight = None
        self._dirty = True
        self.fill_tables(result)
        if self.isVisible():
            self.ensure_drawn()

    def restyle(self) -> None:
        self._dirty = True
        if self._result is not None:
            self.fill_tables(self._result)
        if self.isVisible():
            self.ensure_drawn()

    def ensure_drawn(self) -> None:
        if self._dirty and self._result is not None:
            self.draw(self._result)
            # The plot functions lay the figure out once, for the size it has
            # then; the tight layout engine repeats that at every draw, so the
            # axis labels still fit once the group is shown or the window resized.
            self.figure.set_layout_engine("tight")
            self.canvas.draw_idle()
            self._dirty = False

    def showEvent(self, event: Any) -> None:  # noqa: N802 - Qt override
        super().showEvent(event)
        self.ensure_drawn()

    def redraw(self) -> None:
        """Draw again now (a selection changed what is highlighted)."""
        self._dirty = True
        self.ensure_drawn()

    # --- what a group defines ---------------------------------------------------------

    def draw(self, result: AnalysisResult) -> None:
        raise NotImplementedError

    def fill_tables(self, result: AnalysisResult) -> None:
        raise NotImplementedError

    def show_overview_detail(self) -> None:
        """The details of the group as a whole (nothing selected)."""


class FrequencyGroup(GroupView):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(GROUP_FREQUENCY, parent)
        self.tables_layout.addWidget(label(_("Low-frequency resonance candidates"), "section"))
        self.resonances = _table(
            [_("Frequency (Hz)"), _("Above baseline (dB)"), _("Decay 20 dB"), _("Distinguishable")]
        )
        self.resonances.itemSelectionChanged.connect(self._select)
        self.tables_layout.addWidget(self.resonances, 1)

    def draw(self, result: AnalysisResult) -> None:
        plot_frequency_response(self.figure, result, selected_resonance=self._highlight)

    def fill_tables(self, result: AnalysisResult) -> None:
        fill_metric_table(self.resonances, resonance_rows(result))
        self.note.setText(resonance_note(result))

    def show_overview_detail(self) -> None:
        if self._result is None:
            return
        fr = self._result.frequency_response
        rows = [
            (_("Window"), f"{fr.window_s:.2f} s"),
            (_("Smoothing"), _("1/{fraction} octave").format(fraction=fr.smoothing_fraction)),
            (_("Candidates"), str(len(self._result.resonances.candidates))),
        ]
        band = self._result.excitation_band
        if band is not None:
            rows.append((_("Excitation band"), f"{band.low_hz:.0f}–{band.high_hz:.0f} Hz"))
        self.detail_changed.emit(group_title(self.key), rows, resonance_note(self._result))

    def _select(self) -> None:
        rows = {index.row() for index in self.resonances.selectedIndexes()}
        if self._result is None or len(rows) != 1:
            return
        row = rows.pop()
        if not 0 <= row < len(self._result.resonances.candidates):
            return
        self._highlight = row
        self.detail_changed.emit(
            _("Resonance candidate {hz:.1f} Hz").format(
                hz=self._result.resonances.candidates[row].frequency_hz
            ),
            resonance_detail_rows(self._result, row),
            _(
                "A candidate is a resonance only when its decay is clearly longer than "
                "both the filter ringing and the surroundings."
            ),
        )
        self.redraw()


class DecayGroup(GroupView):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(GROUP_DECAY, parent)
        self.tables_layout.addWidget(label(_("Reverberation by band"), "section"))
        self.table = _table([_("Band"), "EDT", "T20", "T30", _("RT60 estimate")])
        self.table.setToolTip(
            _(
                "Reverberation (extrapolated to 60 dB). 'insufficient range' means "
                "the decay is not clean enough for that metric."
            )
        )
        self.table.itemSelectionChanged.connect(lambda: self._select(self.table))
        self.tables_layout.addWidget(self.table, 1)
        self.tables_layout.addWidget(label(_("Early and late energy"), "section"))
        self.energy_table = _table([_("Band"), "C50", "C80", "D50", _("Centre time")])
        self.energy_table.setToolTip(
            _(
                "C50 is early energy over late energy at 50 ms (speech). C80 is the same "
                "at 80 ms (music). D50 is the share of energy in the first 50 ms. Centre "
                "time is the energy-weighted average time. Time zero is the detected "
                "direct sound. A ratio is reported only when the decay range is at least "
                "20 dB, and it is not a room score."
            )
        )
        self.energy_table.itemSelectionChanged.connect(lambda: self._select(self.energy_table))
        self.tables_layout.addWidget(self.energy_table, 1)

    def draw(self, result: AnalysisResult) -> None:
        plot_decay(self.figure, result, highlight=self._highlight)

    def fill_tables(self, result: AnalysisResult) -> None:
        fill_metric_table(self.table, decay_table_rows(result))
        fill_metric_table(self.energy_table, energy_table_rows(result))
        self.note.setText(
            _(
                "A value in brackets is unreliable; 'insufficient range' means the decay "
                "could not be evaluated over the range that metric needs. Select a band "
                "for the reasons."
            )
        )

    def show_overview_detail(self) -> None:
        if self._result is not None:
            self.detail_changed.emit(
                group_title(self.key), band_detail_rows(self._result, 0), _("Broadband")
            )

    def _select(self, table: QTableWidget) -> None:
        rows = {index.row() for index in table.selectedIndexes()}
        if self._result is None or len(rows) != 1:
            return
        row = rows.pop()
        bands = (self._result.decay.broadband, *self._result.decay.bands)
        if not 0 <= row < len(bands):
            return
        self._highlight = row
        from reverbscope.interpretation.profiles import band_text

        self.detail_changed.emit(
            band_text(bands[row].band_label),
            band_detail_rows(self._result, row),
            _("Every metric with its validity and, when it is not valid, the reason."),
        )
        self.redraw()


class NoiseGroup(GroupView):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(GROUP_NOISE, parent)
        self.tables_layout.addWidget(label(_("Octave-band levels (dBFS)"), "section"))
        self.bands = _table([_("Band"), _("Level (dBFS)")])
        self.bands.itemSelectionChanged.connect(self._select)
        self.tables_layout.addWidget(self.bands, 1)

    def draw(self, result: AnalysisResult) -> None:
        plot_noise(self.figure, result)

    def fill_tables(self, result: AnalysisResult) -> None:
        fill_metric_table(self.bands, noise_band_rows(result))
        noise = result.noise
        if noise.rms_dbfs is None:
            self.note.setText(
                _("No quiet segment could be verified, so no level is reported.")
                + " "
                + " ".join(_localized(note) for note in noise.notes)
            )
        else:
            self.note.setText(_("Levels are digital (dBFS), not dB SPL: uncalibrated."))

    def show_overview_detail(self) -> None:
        if self._result is not None:
            self.detail_changed.emit(
                group_title(self.key), noise_detail_rows(self._result), self.note.text()
            )

    def _select(self) -> None:
        self.show_overview_detail()


class ImpulseGroup(GroupView):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(GROUP_IMPULSE, parent)
        row = QHBoxLayout()
        self.chart_buttons: dict[str, Any] = {}
        from PySide6.QtWidgets import QToolButton

        for key, title in (
            ("impulse", _("Impulse response")),
            ("reflections", _("Early reflections")),
        ):
            button = QToolButton()
            button.setText(title)
            button.setCheckable(True)
            button.setAutoExclusive(True)
            button.clicked.connect(lambda _checked=False, k=key: self._show_chart(k))
            row.addWidget(button)
            self.chart_buttons[key] = button
        row.addStretch(1)
        self.chart_buttons["reflections"].setChecked(True)
        self._chart = "reflections"
        self.tables_layout.addLayout(row)
        self.tables_layout.addWidget(label(_("Early reflections"), "section"))
        self.reflections = _table([_("Delay (ms)"), _("Level re direct (dB)")])
        self.reflections.itemSelectionChanged.connect(self._select)
        self.tables_layout.addWidget(self.reflections, 1)

    def _show_chart(self, key: str) -> None:
        self._chart = key
        self.redraw()

    def draw(self, result: AnalysisResult) -> None:
        if self._chart == "impulse":
            plot_impulse_response(self.figure, result)
        else:
            plot_reflections(self.figure, result)

    def fill_tables(self, result: AnalysisResult) -> None:
        fill_metric_table(self.reflections, reflection_rows(result))
        refl = result.reflections
        if refl.window_truncated and refl.analysed_window_ms is not None:
            self.note.setText(
                _(
                    "The response ended at {end:.1f} ms, before the {window:.0f} ms window: "
                    "later arrivals could not be seen."
                ).format(end=refl.analysed_window_ms[1], window=refl.window_ms[1])
            )
        else:
            self.note.setText(
                _("Arrivals above {threshold:g} dB re the direct sound inside the window.").format(
                    threshold=refl.threshold_db
                )
            )

    def show_overview_detail(self) -> None:
        if self._result is not None:
            self.detail_changed.emit(
                group_title(self.key), impulse_detail_rows(self._result), self.note.text()
            )

    def _select(self) -> None:
        rows = {index.row() for index in self.reflections.selectedIndexes()}
        if self._result is None or len(rows) != 1:
            return
        row = rows.pop()
        reflections = self._result.reflections.reflections
        if not 0 <= row < len(reflections):
            return
        reflection = reflections[row]
        detail = [
            (_("Delay"), f"{reflection.delay_ms:.2f} ms"),
            (_("Level re direct"), f"{reflection.relative_db:.1f} dB"),
        ]
        placement = self._result.placement
        if placement is not None and row < len(placement.candidates):
            candidate = placement.candidates[row]
            detail.append((_("Excess path"), f"{candidate.excess_path_m:.2f} m"))
        self.detail_changed.emit(
            _("Reflection at {delay:.1f} ms").format(delay=reflection.delay_ms),
            detail,
            _("The placement geometry group says what this arrival may be."),
        )


def _localized(note: str) -> str:
    from reverbscope.i18n import localize

    return localize(note)


class AnalysisWorkspace(QWidget):
    """The group list on the left and the group shown on the right."""

    detail_changed = Signal(str, object, str)
    settings_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.list = QListWidget()
        self.list.setFixedWidth(190)
        self.list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.list.currentRowChanged.connect(self._row_changed)
        layout.addWidget(self.list)
        self.stack = QStackedWidget()
        layout.addWidget(self.stack, 1)
        self.groups: dict[str, GroupView | PlacementView] = {}
        self.placement = PlacementView()
        self.placement.settings_requested.connect(self.settings_requested.emit)
        for view in (FrequencyGroup(), DecayGroup(), NoiseGroup(), ImpulseGroup(), self.placement):
            self.groups[view.key] = view
            view.detail_changed.connect(self.detail_changed.emit)
            page = QWidget()
            page_layout = QVBoxLayout(page)
            page_layout.setContentsMargins(12, 10, 12, 10)
            page_layout.addWidget(view)
            self.stack.addWidget(page)
            item = QListWidgetItem(group_title(view.key))
            item.setData(Qt.ItemDataRole.UserRole, view.key)
            self.list.addItem(item)
        self.list.setCurrentRow(0)

    def set_result(self, result: AnalysisResult) -> None:
        for view in self.groups.values():
            view.set_result(result)

    def restyle(self) -> None:
        """Every group draws again when next shown; the current one now."""
        for view in self.groups.values():
            view.restyle()
        self.groups[self.current_group()].ensure_drawn()

    def current_group(self) -> str:
        item = self.list.currentItem()
        return str(item.data(Qt.ItemDataRole.UserRole)) if item is not None else GROUPS[0]

    def current_figure(self) -> Figure:
        return self.groups[self.current_group()].figure

    def show_group(self, key: str) -> None:
        for row in range(self.list.count()):
            if self.list.item(row).data(Qt.ItemDataRole.UserRole) == key:
                self.list.setCurrentRow(row)
                return

    def _row_changed(self, row: int) -> None:
        if row < 0:
            return
        self.stack.setCurrentIndex(row)
        view = self.groups[str(self.list.item(row).data(Qt.ItemDataRole.UserRole))]
        view.ensure_drawn()
        if isinstance(view, GroupView):
            view.show_overview_detail()

    def ensure_current_drawn(self) -> None:
        self.groups[self.current_group()].ensure_drawn()


__all__ = [
    "GROUP_DECAY",
    "GROUP_FREQUENCY",
    "GROUP_IMPULSE",
    "GROUP_NOISE",
    "GROUP_PLACEMENT",
    "AnalysisWorkspace",
    "GroupView",
    "fill_metric_table",
]
