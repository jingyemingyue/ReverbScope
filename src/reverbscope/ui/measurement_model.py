"""The measurement list: a two-level tree over a :class:`WorkspaceDocument`.

Top-level rows are position groups (:meth:`Measurement.group_label`, in the
order a position first appears; a group goes when its last measurement
goes); their children are the measurements, one row each, with the curve
swatch, the visibility checkbox, the quality word and the role tags
(baseline, synthetic data, unsaved).

The model never computes or judges anything: the name, colour, line style,
health status and tags all come from the measurement and the document. It
listens to every document signal that changes what it shows and emits the
precise insert / remove / move / dataChanged for it, never a full reset.

As in a chart workbench with a source list, three states stay apart: the
checkbox is *visible*, the view's current row is *selected*, and the
baseline is a tag. Checking a row never changes the selection, and
selecting a row never hides another curve.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from PySide6.QtCore import (
    QAbstractItemModel,
    QItemSelectionModel,
    QModelIndex,
    QObject,
    QPersistentModelIndex,
    Qt,
)
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QHeaderView, QTreeView

from reverbscope.cli.render import created_text
from reverbscope.health import status_word
from reverbscope.i18n import _, list_join
from reverbscope.ui.document import Measurement, WorkspaceDocument
from reverbscope.ui.results_presenter import HEALTH_TONE
from reverbscope.ui.theme import tone_color
from reverbscope.ui.widgets import TONE_GLYPH

COLUMN_NAME = 0
COLUMN_QUALITY = 1
COLUMN_ROLE = 2
COLUMN_COUNT = 3

#: ``internalId`` of a group row. A measurement row carries its measurement's
#: key (>= 1, never reused), so an index stays right when groups are removed
#: or a row moves to another group: Qt keeps the internal id through both.
_GROUP_ID = 0

_SWATCH_WIDTH = 18
_SWATCH_HEIGHT = 12
_SWATCH_LINE_WIDTH = 2
_PEN_STYLES = {
    "-": Qt.PenStyle.SolidLine,
    "--": Qt.PenStyle.DashLine,
    "-.": Qt.PenStyle.DashDotLine,
    ":": Qt.PenStyle.DotLine,
}

_Index = QModelIndex | QPersistentModelIndex
_Flag = QItemSelectionModel.SelectionFlag


@dataclass
class _Group:
    label: str
    ids: list[str] = field(default_factory=list)


def swatch(colour: str, style: str) -> QPixmap:
    """A short line in the measurement's colour and matplotlib line style
    on a transparent pixmap: the list shows the curve the chart draws."""
    pixmap = QPixmap(_SWATCH_WIDTH, _SWATCH_HEIGHT)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    pen = QPen(QColor(colour), _SWATCH_LINE_WIDTH)
    pen.setStyle(_PEN_STYLES.get(style, Qt.PenStyle.SolidLine))
    pen.setCapStyle(Qt.PenCapStyle.FlatCap)
    painter.setPen(pen)
    y = _SWATCH_HEIGHT / 2
    painter.drawLine(1, int(y), _SWATCH_WIDTH - 1, int(y))
    painter.end()
    return pixmap


class MeasurementListModel(QAbstractItemModel):
    """Position groups over the document's measurements, three columns."""

    def __init__(self, document: WorkspaceDocument, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._document = document
        self._groups: list[_Group] = []
        self._keys: dict[str, int] = {}
        self._ids: dict[int, str] = {}
        self._next_key = 1
        self._baseline_id: str | None = document.baseline_id()
        self._swatches: dict[tuple[str, str], QPixmap] = {}
        #: True between begin/end of an insert, remove or move: the view
        #: moves its current index on its own then, which is not a choice.
        self._structural = False
        for measurement in document.measurements:
            self._place(measurement)
        document.measurement_added.connect(self._measurement_added)
        document.measurement_removed.connect(self._measurement_removed)
        document.measurement_changed.connect(self._measurement_changed)
        document.visibility_changed.connect(self._visibility_changed)
        document.baseline_changed.connect(self._baseline_changed)
        document.selection_changed.connect(self._selection_changed)

    # --- lookups -----------------------------------------------------------------------

    @property
    def document(self) -> WorkspaceDocument:
        return self._document

    def group_labels(self) -> list[str]:
        """The position groups, top to bottom."""
        return [group.label for group in self._groups]

    def in_structural_change(self) -> bool:
        """Rows are being inserted, removed or moved right now."""
        return self._structural

    def is_group(self, index: _Index) -> bool:
        return index.isValid() and index.internalId() == _GROUP_ID

    def measurement_at(self, index: _Index) -> Measurement | None:
        """The measurement of a row, ``None`` for a group row or no row."""
        if not index.isValid() or index.internalId() == _GROUP_ID:
            return None
        measurement_id = self._ids.get(int(index.internalId()))
        if measurement_id is None or self._position(measurement_id) is None:
            return None
        return self._document.get(measurement_id)

    def index_for(self, measurement_id: str, column: int = COLUMN_NAME) -> QModelIndex:
        """The row of a measurement; an invalid index when it is not listed."""
        position = self._position(measurement_id)
        if position is None:
            return QModelIndex()
        _group_row, row = position
        return self.createIndex(row, column, self._key(measurement_id))

    def _key(self, measurement_id: str) -> int:
        """The measurement's ``internalId``, given once and kept."""
        key = self._keys.get(measurement_id)
        if key is None:
            key = self._next_key
            self._next_key += 1
            self._keys[measurement_id] = key
            self._ids[key] = measurement_id
        return key

    def group_index(self, label: str) -> QModelIndex:
        for row, group in enumerate(self._groups):
            if group.label == label:
                return self.createIndex(row, COLUMN_NAME, _GROUP_ID)
        return QModelIndex()

    def _position(self, measurement_id: str) -> tuple[int, int] | None:
        for group_row, group in enumerate(self._groups):
            try:
                return group_row, group.ids.index(measurement_id)
            except ValueError:
                continue
        return None

    def _group_row(self, label: str) -> int:
        return next((row for row, group in enumerate(self._groups) if group.label == label), -1)

    # --- QAbstractItemModel ------------------------------------------------------------

    def rowCount(self, parent: _Index | None = None) -> int:  # noqa: N802 - Qt override
        if parent is None or not parent.isValid():
            return len(self._groups)
        if parent.column() != COLUMN_NAME or parent.internalId() != _GROUP_ID:
            return 0
        if not 0 <= parent.row() < len(self._groups):
            return 0
        return len(self._groups[parent.row()].ids)

    def columnCount(self, _parent: _Index | None = None) -> int:  # noqa: N802 - Qt override
        return COLUMN_COUNT

    def index(self, row: int, column: int, parent: _Index | None = None) -> QModelIndex:
        root = parent is None or not parent.isValid()
        if column < 0 or column >= COLUMN_COUNT or row < 0:
            return QModelIndex()
        if root:
            if row >= len(self._groups):
                return QModelIndex()
            return self.createIndex(row, column, _GROUP_ID)
        assert parent is not None
        if parent.internalId() != _GROUP_ID or row >= self.rowCount(parent):
            return QModelIndex()
        return self.createIndex(row, column, self._key(self._groups[parent.row()].ids[row]))

    def parent(self, child: _Index | None = None) -> QModelIndex:  # type: ignore[override]
        if child is None or not child.isValid() or child.internalId() == _GROUP_ID:
            return QModelIndex()
        measurement_id = self._ids.get(int(child.internalId()))
        position = self._position(measurement_id) if measurement_id is not None else None
        if position is None:
            return QModelIndex()
        return self.createIndex(position[0], COLUMN_NAME, _GROUP_ID)

    def hasChildren(self, parent: _Index | None = None) -> bool:  # noqa: N802 - Qt override
        return self.rowCount(parent) > 0

    def flags(self, index: _Index) -> Qt.ItemFlag:
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        if index.internalId() == _GROUP_ID:
            # A position is a heading with a checkbox for all its curves,
            # not an object to inspect: it cannot take the selection.
            if index.column() == COLUMN_NAME:
                return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable
            return Qt.ItemFlag.ItemIsEnabled
        flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        if index.column() == COLUMN_NAME:
            flags |= Qt.ItemFlag.ItemIsUserCheckable
        return flags

    def headerData(  # noqa: N802 - Qt override
        self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole
    ) -> Any:
        if orientation != Qt.Orientation.Horizontal or role != Qt.ItemDataRole.DisplayRole:
            return None
        return {
            COLUMN_NAME: _("Measurement"),
            COLUMN_QUALITY: _("Quality"),
            COLUMN_ROLE: _("Role"),
        }.get(section)

    def data(self, index: _Index, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid():
            return None
        if index.internalId() == _GROUP_ID:
            return self._group_data(index.row(), index.column(), role)
        measurement = self.measurement_at(index)
        if measurement is None:
            return None
        column = index.column()
        if column == COLUMN_NAME:
            return self._name_data(measurement, role)
        if column == COLUMN_QUALITY:
            return self._quality_data(measurement, role)
        if column == COLUMN_ROLE and role == Qt.ItemDataRole.DisplayRole:
            return self.role_text(measurement)
        return None

    def setData(  # noqa: N802 - Qt override
        self, index: _Index, value: Any, role: int = Qt.ItemDataRole.EditRole
    ) -> bool:
        if (
            not index.isValid()
            or index.column() != COLUMN_NAME
            or role != Qt.ItemDataRole.CheckStateRole
        ):
            return False
        visible = Qt.CheckState(value) == Qt.CheckState.Checked
        if index.internalId() == _GROUP_ID:
            if not 0 <= index.row() < len(self._groups):
                return False
            for measurement_id in list(self._groups[index.row()].ids):
                self._document.set_visible(measurement_id, visible)
            return True
        measurement = self.measurement_at(index)
        if measurement is None:
            return False
        self._document.set_visible(measurement.id, visible)
        return True

    # --- the cells ----------------------------------------------------------------------

    def _group_data(self, row: int, column: int, role: int) -> Any:
        if not 0 <= row < len(self._groups) or column != COLUMN_NAME:
            return None
        group = self._groups[row]
        if role == Qt.ItemDataRole.DisplayRole:
            return group.label
        if role == Qt.ItemDataRole.CheckStateRole:
            shown = sum(
                1 for measurement_id in group.ids if self._document.is_visible(measurement_id)
            )
            if shown == 0:
                return Qt.CheckState.Unchecked
            if shown == len(group.ids):
                return Qt.CheckState.Checked
            return Qt.CheckState.PartiallyChecked
        return None

    def _name_data(self, measurement: Measurement, role: int) -> Any:
        if role == Qt.ItemDataRole.DisplayRole:
            return measurement.name()
        if role == Qt.ItemDataRole.CheckStateRole:
            if self._document.is_visible(measurement.id):
                return Qt.CheckState.Checked
            return Qt.CheckState.Unchecked
        if role == Qt.ItemDataRole.DecorationRole:
            return self._swatch(measurement)
        if role == Qt.ItemDataRole.ToolTipRole:
            return self.tooltip_text(measurement)
        return None

    def _quality_data(self, measurement: Measurement, role: int) -> Any:
        tone = HEALTH_TONE.get(measurement.status, "neutral")
        if role == Qt.ItemDataRole.DisplayRole:
            return f"{TONE_GLYPH.get(tone, '')} {status_word(measurement.status)}".strip()
        if role == Qt.ItemDataRole.ForegroundRole:
            return QColor(tone_color(tone)[0])
        if role == Qt.ItemDataRole.ToolTipRole:
            return status_word(measurement.status)
        return None

    def role_text(self, measurement: Measurement) -> str:
        """The tags of the Role column: baseline, synthetic data, unsaved."""
        tags: list[str] = []
        if measurement.id == self._baseline_id:
            tags.append(_("baseline"))
        if measurement.synthetic:
            tags.append(_("synthetic data"))
        if measurement.unsaved:
            tags.append(_("unsaved"))
        return list_join(tags)

    def tooltip_text(self, measurement: Measurement) -> str:
        where = str(measurement.path) if measurement.path is not None else _("not saved")
        created = _("{label}: {description}").format(
            label=_("Created"), description=created_text(measurement.session.created_at)
        )
        return f"{where}\n{created}"

    def _swatch(self, measurement: Measurement) -> QPixmap:
        key = (measurement.colour, measurement.style)
        pixmap = self._swatches.get(key)
        if pixmap is None:
            pixmap = self._swatches[key] = swatch(*key)
        return pixmap

    def restyle(self) -> None:
        """The colour scheme changed: tone colours and swatches are redrawn."""
        self._swatches.clear()
        self._emit_all_changed()

    def _emit_all_changed(self) -> None:
        for group_row, group in enumerate(self._groups):
            group_index = self.createIndex(group_row, COLUMN_NAME, _GROUP_ID)
            self.dataChanged.emit(group_index, group_index)
            if group.ids:
                first = self.createIndex(0, COLUMN_NAME, self._key(group.ids[0]))
                last = self.createIndex(
                    len(group.ids) - 1, COLUMN_COUNT - 1, self._key(group.ids[-1])
                )
                self.dataChanged.emit(first, last)

    def _emit_row_changed(
        self, measurement_id: str, first_column: int = COLUMN_NAME, last_column: int = COLUMN_ROLE
    ) -> None:
        position = self._position(measurement_id)
        if position is None:
            return
        _group_row, row = position
        key = self._key(measurement_id)
        first = self.createIndex(row, first_column, key)
        last = self.createIndex(row, last_column, key)
        self.dataChanged.emit(first, last)

    def _emit_group_changed(self, group_row: int) -> None:
        index = self.createIndex(group_row, COLUMN_NAME, _GROUP_ID)
        self.dataChanged.emit(index, index, [Qt.ItemDataRole.CheckStateRole])

    # --- following the document -----------------------------------------------------

    def _place(self, measurement: Measurement) -> None:
        """List ``measurement`` without signals (the constructor)."""
        label = measurement.group_label()
        row = self._group_row(label)
        if row < 0:
            self._groups.append(_Group(label))
            row = len(self._groups) - 1
        self._groups[row].ids.append(measurement.id)

    def _measurement_added(self, measurement_id: str) -> None:
        measurement = self._document.get(measurement_id)
        if measurement is None or self._position(measurement_id) is not None:
            return
        self._insert(measurement_id, measurement.group_label())

    def _insert(self, measurement_id: str, label: str) -> None:
        group_row = self._group_row(label)
        self._structural = True
        try:
            if group_row < 0:
                group_row = len(self._groups)
                self.beginInsertRows(QModelIndex(), group_row, group_row)
                self._groups.append(_Group(label))
                self.endInsertRows()
            group = self._groups[group_row]
            parent = self.createIndex(group_row, COLUMN_NAME, _GROUP_ID)
            self.beginInsertRows(parent, len(group.ids), len(group.ids))
            group.ids.append(measurement_id)
            self.endInsertRows()
        finally:
            self._structural = False
        self._emit_group_changed(group_row)

    def _measurement_removed(self, measurement_id: str) -> None:
        position = self._position(measurement_id)
        if position is None:
            return
        group_row, row = position
        self._structural = True
        try:
            parent = self.createIndex(group_row, COLUMN_NAME, _GROUP_ID)
            self.beginRemoveRows(parent, row, row)
            del self._groups[group_row].ids[row]
            self.endRemoveRows()
            if not self._groups[group_row].ids:
                self.beginRemoveRows(QModelIndex(), group_row, group_row)
                del self._groups[group_row]
                self.endRemoveRows()
                return
        finally:
            self._structural = False
        self._emit_group_changed(group_row)

    def _measurement_changed(self, measurement_id: str) -> None:
        measurement = self._document.get(measurement_id)
        position = self._position(measurement_id)
        if measurement is None or position is None:
            return
        group_row, row = position
        label = measurement.group_label()
        if self._groups[group_row].label != label:
            self._move(measurement_id, group_row, row, label)
        self._emit_row_changed(measurement_id)

    def _move(self, measurement_id: str, group_row: int, row: int, label: str) -> None:
        """The measurement's position changed: its row moves to that group,
        which is created when new; the old group goes when it is left empty."""
        self._structural = True
        try:
            target_row = self._group_row(label)
            if target_row < 0:
                target_row = len(self._groups)
                self.beginInsertRows(QModelIndex(), target_row, target_row)
                self._groups.append(_Group(label))
                self.endInsertRows()
            source = self.createIndex(group_row, COLUMN_NAME, _GROUP_ID)
            target = self.createIndex(target_row, COLUMN_NAME, _GROUP_ID)
            destination = len(self._groups[target_row].ids)
            self.beginMoveRows(source, row, row, target, destination)
            del self._groups[group_row].ids[row]
            self._groups[target_row].ids.append(measurement_id)
            self.endMoveRows()
            if not self._groups[group_row].ids:
                self.beginRemoveRows(QModelIndex(), group_row, group_row)
                del self._groups[group_row]
                self.endRemoveRows()
                if target_row > group_row:
                    target_row -= 1
        finally:
            self._structural = False
        self._emit_group_changed(target_row)
        if self._groups and group_row < len(self._groups):
            self._emit_group_changed(group_row)

    def _visibility_changed(self, measurement_id: str, _visible: bool) -> None:
        position = self._position(measurement_id)
        if position is None:
            return
        group_row, row = position
        index = self.createIndex(row, COLUMN_NAME, self._key(measurement_id))
        self.dataChanged.emit(index, index, [Qt.ItemDataRole.CheckStateRole])
        self._emit_group_changed(group_row)

    def _baseline_changed(self, measurement_id: object) -> None:
        previous = self._baseline_id
        self._baseline_id = measurement_id if isinstance(measurement_id, str) else None
        for changed in (previous, self._baseline_id):
            if changed is not None:
                self._emit_row_changed(changed, COLUMN_ROLE, COLUMN_ROLE)

    def _selection_changed(self, _measurement_id: object) -> None:
        # The selection is the view's current row, not a cell value: nothing
        # here changes. Connected so the model is complete, and cheap.
        return


# --- the view ------------------------------------------------------------------------------


class SelectionSync(QObject):
    """Keeps a tree view's current row and the document's selection the same.

    The view's current index names the selected measurement; the document's
    selection moves the view's current index. A group row (not selectable)
    takes the keyboard focus on the way through but never the selection, so
    the selected measurement's row stays highlighted while it is current.
    """

    def __init__(self, view: QTreeView, document: WorkspaceDocument) -> None:
        super().__init__(view)
        self._view = view
        self._document = document
        self._syncing = False
        model = view.model()
        if not isinstance(model, MeasurementListModel):
            raise TypeError("connect_selection needs a QTreeView on a MeasurementListModel")
        self._model = model
        selection_model = view.selectionModel()
        selection_model.currentChanged.connect(self._current_changed)
        selection_model.selectionChanged.connect(self._selection_changed)
        document.selection_changed.connect(self._document_selected)
        self._document_selected(document.selected_id())

    def _current_changed(self, current: QModelIndex, _previous: QModelIndex) -> None:
        if self._syncing or self._model.in_structural_change():
            return
        measurement = self._model.measurement_at(current)
        if measurement is None:
            return
        self._syncing = True
        try:
            self._document.set_selected(measurement.id)
        finally:
            self._syncing = False

    def _selection_changed(self, *_args: object) -> None:
        """A click on a group row cleared the highlight: put it back on the
        selected measurement's row (the current index stays on the group)."""
        if self._syncing or self._model.in_structural_change():
            return
        selected_id = self._document.selected_id()
        if selected_id is None:
            return
        index = self._model.index_for(selected_id)
        selection_model = self._view.selectionModel()
        if not index.isValid() or selection_model.isSelected(index):
            return
        self._syncing = True
        try:
            selection_model.select(
                index,
                _Flag.Select | _Flag.Rows,
            )
        finally:
            self._syncing = False

    def _document_selected(self, measurement_id: object) -> None:
        if self._syncing:
            return
        selection_model = self._view.selectionModel()
        self._syncing = True
        try:
            if not isinstance(measurement_id, str):
                selection_model.clearSelection()
                selection_model.setCurrentIndex(QModelIndex(), _Flag.NoUpdate)
                return
            index = self._model.index_for(measurement_id)
            if not index.isValid():
                return
            self._view.expand(index.parent())
            selection_model.setCurrentIndex(index, _Flag.ClearAndSelect | _Flag.Rows)
            self._view.scrollTo(index)
        finally:
            self._syncing = False


def connect_selection(view: QTreeView, document: WorkspaceDocument) -> SelectionSync:
    """Sync ``view``'s current row with ``document``'s selection both ways.

    Call it after :meth:`QTreeView.setModel` (the selection model is made
    then). The returned object lives as long as the view.
    """
    return SelectionSync(view, document)


def style_tree(view: QTreeView) -> None:
    """Compact rows, a stretching name column, every group open."""
    view.setUniformRowHeights(True)
    view.setRootIsDecorated(True)
    view.setItemsExpandable(True)
    view.setAllColumnsShowFocus(True)
    view.setAlternatingRowColors(False)
    view.setIndentation(14)
    view.setSelectionBehavior(QTreeView.SelectionBehavior.SelectRows)
    view.setEditTriggers(QTreeView.EditTrigger.NoEditTriggers)
    header = view.header()
    header.setStretchLastSection(False)
    header.setSectionResizeMode(COLUMN_NAME, QHeaderView.ResizeMode.Stretch)
    header.setSectionResizeMode(COLUMN_QUALITY, QHeaderView.ResizeMode.ResizeToContents)
    header.setSectionResizeMode(COLUMN_ROLE, QHeaderView.ResizeMode.ResizeToContents)
    header.setSectionsMovable(False)
    view.expandAll()
    model = view.model()
    if model is not None:

        def expand_new_groups(parent: QModelIndex, first: int, last: int) -> None:
            if parent.isValid():
                return
            for row in range(first, last + 1):
                view.expand(model.index(row, COLUMN_NAME))

        model.rowsInserted.connect(expand_new_groups)
