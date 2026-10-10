"""The placement geometry of a result: a side view of what the two tape
measures and the reflections allow, a reflection timeline, and a
three-dimensional view as an auxiliary picture.

Measured lengths, model-derived lengths and example lengths are drawn in
different line styles and said to be so. Every alternative the model keeps
is shown; nothing picks one. A missing input names the field to fill in
and offers the way back to the measurement page.
"""

from __future__ import annotations

from typing import Any, cast

from reverbscope.ui.qt import ensure_pyside6

ensure_pyside6()

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from reverbscope.i18n import _, list_join
from reverbscope.models.result import AnalysisResult
from reverbscope.ui.plots import plot_placement_3d, plot_placement_result, plot_reflection_timeline
from reverbscope.ui.results_presenter import (
    candidate_detail_rows,
    candidate_rows,
    placement_length_rows,
    placement_missing,
    placement_notes,
    placement_summary,
)
from reverbscope.ui.widgets import flat, label, set_banner_text

VIEW_SIDE = "side"
VIEW_TIMELINE = "timeline"
VIEW_3D = "3d"


def _item(text: str) -> QTableWidgetItem:
    item = QTableWidgetItem(text)
    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
    return item


class PlacementView(QWidget):
    """S5: vertical-axis figures from the tape measure and early reflections."""

    #: ``(title, rows, note)`` for the details pane.
    detail_changed = Signal(str, object, str)
    #: The user wants the measurement page to fill in a missing input.
    settings_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.key = "placement"
        self._result: AnalysisResult | None = None
        self._dirty = False
        self._view = VIEW_SIDE
        self._selected: int | None = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.summary = QLabel("")
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        self.missing = QLabel("")
        self.missing.setWordWrap(True)
        self.missing.hide()
        missing_row = QHBoxLayout()
        missing_row.addWidget(self.missing, 1)
        self.settings_button = flat(QPushButton(_("Back to the measurement settings")))
        self.settings_button.clicked.connect(self.settings_requested.emit)
        self.settings_button.hide()
        missing_row.addWidget(self.settings_button)
        layout.addLayout(missing_row)

        bar = QHBoxLayout()
        bar.setSpacing(4)
        self.view_buttons: dict[str, QToolButton] = {}
        for key, title in (
            (VIEW_SIDE, _("Side view")),
            (VIEW_TIMELINE, _("Reflection timeline")),
            (VIEW_3D, _("3D (auxiliary)")),
        ):
            button = QToolButton()
            button.setText(title)
            button.setCheckable(True)
            button.setAutoExclusive(True)
            button.clicked.connect(lambda _checked=False, k=key: self.show_view(k))
            bar.addWidget(button)
            self.view_buttons[key] = button
        self.view_buttons[VIEW_SIDE].setChecked(True)
        bar.addStretch(1)
        self.reset_button = QPushButton(_("Reset view"))
        self.reset_button.setToolTip(_("Back to the fixed viewpoint of the 3D picture."))
        self.reset_button.clicked.connect(self._redraw)
        self.reset_button.hide()
        bar.addWidget(self.reset_button)
        layout.addLayout(bar)

        splitter = QSplitter(Qt.Orientation.Vertical)
        chart = QWidget()
        chart_layout = QVBoxLayout(chart)
        chart_layout.setContentsMargins(0, 0, 0, 0)
        self.figure = Figure(figsize=(7.2, 3.6), dpi=100)
        self.canvas: Any = cast(Any, FigureCanvasQTAgg)(self.figure)
        self.canvas.setMinimumHeight(220)
        chart_layout.addWidget(self.canvas, 1)
        self.scene_hint = QLabel("")
        self.scene_hint.setWordWrap(True)
        self.scene_hint.setProperty("role", "hint")
        chart_layout.addWidget(self.scene_hint)
        splitter.addWidget(chart)

        tables = QWidget()
        tables_layout = QVBoxLayout(tables)
        tables_layout.setContentsMargins(0, 0, 0, 0)
        tables_layout.setSpacing(4)
        tables_layout.addWidget(label(_("Solved lengths"), "section"))
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels([_("Figure"), _("Value"), _("Validity"), _("Note")])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setMaximumHeight(130)
        self.table.itemSelectionChanged.connect(self._length_selected)
        tables_layout.addWidget(self.table)
        tables_layout.addWidget(label(_("Reflection candidates"), "section"))
        self.candidates = QTableWidget(0, 5)
        self.candidates.setHorizontalHeaderLabels(
            [_("Delay (ms)"), _("Level (dB)"), _("Excess path (m)"), _("Surface"), _("Plane?")]
        )
        self.candidates.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.candidates.verticalHeader().setVisible(False)
        self.candidates.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.candidates.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.candidates.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.candidates.itemSelectionChanged.connect(self._candidate_selected)
        tables_layout.addWidget(self.candidates, 1)
        self.notes = QLabel("")
        self.notes.setWordWrap(True)
        self.notes.setProperty("role", "hint")
        self.notes.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        tables_layout.addWidget(self.notes)
        splitter.addWidget(tables)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter, 1)

    # --- data -----------------------------------------------------------------------

    def set_result(self, result: AnalysisResult) -> None:
        self._result = result
        self._selected = None
        self._dirty = True
        self._fill_tables()
        if self.isVisible():
            self.ensure_drawn()

    def show_placement(self, result: AnalysisResult) -> None:
        """Show ``result``'s placement now (tables and picture)."""
        self.set_result(result)
        self.ensure_drawn()

    def restyle(self) -> None:
        self._dirty = True
        if self.isVisible():
            self.ensure_drawn()

    def ensure_drawn(self) -> None:
        if self._dirty:
            self._redraw()
            self._dirty = False

    def showEvent(self, event: Any) -> None:  # noqa: N802 - Qt override
        super().showEvent(event)
        self.ensure_drawn()

    def show_view(self, key: str) -> None:
        self._view = key
        self.view_buttons[key].setChecked(True)
        self.reset_button.setVisible(key == VIEW_3D)
        self._redraw()

    def _redraw(self) -> None:
        result = self._result
        placement = result.placement if result is not None else None
        if self._view == VIEW_TIMELINE and result is not None:
            plot_reflection_timeline(self.figure, result, candidate_index=self._selected)
            self.scene_hint.setText(
                _(
                    "Every arrival above the threshold inside the analysed window; the "
                    "hatched part was not searched. Colour and marker say whether the "
                    "model attributed the arrival to a plane; a cross is an arrival it "
                    "refused."
                )
            )
        elif self._view == VIEW_3D:
            self.scene_hint.setText(plot_placement_3d(self.figure, placement))
        else:
            self.scene_hint.setText(plot_placement_result(self.figure, placement))
        # The two-dimensional pictures are laid out again at every draw (the
        # size changes with the splitter); the 3D view keeps its own margins.
        self.figure.set_layout_engine("tight" if self._view != VIEW_3D else "none")
        self.canvas.draw_idle()

    def _fill_tables(self) -> None:
        result = self._result
        placement = result.placement if result is not None else None
        self.summary.setText(placement_summary(placement))
        missing = placement_missing(placement)
        if missing:
            set_banner_text(
                self.missing,
                _("To go further, fill in: {fields}.").format(fields=list_join(missing)),
                "info",
            )
            self.missing.show()
            self.settings_button.show()
        else:
            self.missing.hide()
            self.settings_button.hide()
        if placement is None:
            self.table.setRowCount(0)
            self.candidates.setRowCount(0)
            self.notes.setText("")
            self.detail_changed.emit(_("Placement geometry"), [], placement_summary(None))
            return
        rows = placement_length_rows(placement)
        self.table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, text in enumerate(row):
                self.table.setItem(r, c, _item(text))
        self.candidates.blockSignals(True)
        candidates = candidate_rows(placement)
        self.candidates.setRowCount(len(candidates))
        for r, candidate_row in enumerate(candidates):
            for c, text in enumerate(candidate_row):
                self.candidates.setItem(r, c, _item(text))
        self.candidates.blockSignals(False)
        self.notes.setText("\n".join(placement_notes(placement)))
        self.detail_changed.emit(
            _("Placement geometry"),
            [(caption, f"{value} ({validity})") for caption, value, validity, _note in rows],
            placement_summary(placement),
        )

    # --- selection ------------------------------------------------------------------

    def _length_selected(self) -> None:
        result = self._result
        rows = {index.row() for index in self.table.selectedIndexes()}
        if result is None or result.placement is None or len(rows) != 1:
            return
        row = rows.pop()
        lengths = placement_length_rows(result.placement)
        if not 0 <= row < len(lengths):
            return
        caption, value, validity, note = lengths[row]
        detail = [(_("Value"), value), (_("Validity"), validity)]
        if note:
            detail.append((_("Note"), note))
        self.detail_changed.emit(
            caption,
            detail,
            _(
                "± is propagated from the stated tape-measure, temperature and "
                "peak-location uncertainties only; it excludes model error."
            ),
        )

    def _candidate_selected(self) -> None:
        result = self._result
        rows = {index.row() for index in self.candidates.selectedIndexes()}
        if result is None or result.placement is None or len(rows) != 1:
            self._selected = None
            return
        row = rows.pop()
        candidates = result.placement.candidates
        if not 0 <= row < len(candidates):
            return
        self._selected = row
        candidate = candidates[row]
        self.detail_changed.emit(
            _("Reflection at {delay:.1f} ms").format(delay=candidate.delay_ms),
            candidate_detail_rows(candidate),
            _(
                "The geometric fields describe a flat first-order reflector; read "
                '"Plane reflection?" first.'
            ),
        )
        if self._view == VIEW_TIMELINE:
            self._redraw()

    def select_candidate(self, index: int) -> None:
        if 0 <= index < self.candidates.rowCount():
            self.candidates.selectRow(index)
