"""Data tables that read like a measurement tool's (GUIDELINES §13.9).

:func:`setup_data_table` gives a ``QTableWidget`` the shared behaviour:

- numbers right-aligned in tabular figures, so a column of seconds or
  decibels lines up on the decimal point; the header of a number column is
  right-aligned over it;
- a click on a header sorts by that column, by the number in the cell (a
  bracketed, not-trusted value sorts by its number too; a word such as
  "n/a" sorts after every number), and a third click goes back to the
  table's own order (bands low to high);
- Ctrl+C (⌘C) and the context menu copy the selected rows, or the whole
  table when nothing is selected, as tab-separated text with the header, so
  a spreadsheet pastes it into columns.

Display only: the cells keep exactly the text the views wrote into them.
"""

from __future__ import annotations

import contextlib
import math
import re
from collections.abc import Iterable

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QFont, QGuiApplication, QKeySequence
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QMenu, QTableWidget, QTableWidgetItem

from reverbscope.i18n import _

#: Row height of a data table in pixels (GUIDELINES §13.9).
ROW_HEIGHT = 28

#: Item data role holding the row's place in the table's own order.
ORDER_ROLE = int(Qt.ItemDataRole.UserRole) + 41

#: A number not glued to a metric name ("C80", "T30" are names, not values).
_NUMBER = re.compile(r"(?<![A-Za-z\d.])[-+\u2212]?\d+(?:[.,]\d+)?")
#: A kilo prefix right after the number: "1 kHz", "1.25k".
_KILO = re.compile(r"\s?k(?:Hz)?\b")


def number_in(text: str) -> float | None:
    """The first number written in ``text`` (``(0.69 s)`` → 0.69, ``−87.1`` → −87.1)."""
    match = _NUMBER.search(text)
    if match is None:
        return None
    raw = match.group(0).replace("\u2212", "-").replace(",", ".")
    try:
        value = float(raw)
    except ValueError:
        return None
    # "1 kHz" and "1.2 kHz" sort above "500 Hz".
    if _KILO.match(text, match.end()):
        value *= 1000.0
    return value if math.isfinite(value) else None


def tabular_font(base: QFont) -> QFont:
    """``base`` with tabular (equal-width) figures, where Qt can ask for them."""
    font = QFont(base)
    tag = getattr(QFont, "Tag", None)
    if tag is not None and hasattr(font, "setFeature"):
        with contextlib.suppress(TypeError, ValueError):  # older bindings
            font.setFeature(tag("tnum"), 1)
    return font


class DataItem(QTableWidgetItem):
    """A cell that sorts by the number it shows, then by the table's own order."""

    def __lt__(self, other: QTableWidgetItem) -> bool:  # type: ignore[override]
        mine, theirs = number_in(self.text()), number_in(other.text())
        if mine is not None and theirs is not None and mine != theirs:
            return mine < theirs
        if (mine is None) != (theirs is None):
            return mine is not None  # numbers before words such as "n/a"
        return int(self.data(ORDER_ROLE) or 0) < int(other.data(ORDER_ROLE) or 0)


def data_item(text: str, *, numeric: bool = False, row: int = 0) -> DataItem:
    """A read-only cell; ``numeric`` right-aligns it in tabular figures."""
    item = DataItem(text)
    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
    item.setData(ORDER_ROLE, row)
    if numeric:
        item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        item.setFont(tabular_font(item.font()))
    else:
        item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    return item


def begin_fill(table: QTableWidget) -> None:
    """Call before writing rows: a sorted table would move rows while they are filled."""
    table.setSortingEnabled(False)


def end_fill(table: QTableWidget) -> None:
    """Call after writing rows: sorting is offered again, in the order the user chose."""
    header = table.horizontalHeader()
    section = header.sortIndicatorSection()
    order = header.sortIndicatorOrder()
    sortable = bool(table.property("sortable"))
    table.setSortingEnabled(sortable)
    if sortable and 0 <= section < table.columnCount() and header.isSortIndicatorShown():
        table.sortItems(section, order)


def setup_data_table(
    table: QTableWidget,
    numeric_columns: Iterable[int] = (),
    *,
    sortable: bool = True,
) -> None:
    """Right-aligned number columns, header sorting and copy as TSV for ``table``."""
    numeric = sorted(set(numeric_columns))
    table.setProperty("numeric_columns", numeric)
    table.setProperty("sortable", sortable)
    header = table.horizontalHeader()
    header.setHighlightSections(False)
    header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    for column in numeric:
        item = table.horizontalHeaderItem(column)
        if item is not None:
            item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    if sortable:
        # Ascending, descending, then the table's own order again.
        header.setSortIndicatorClearable(True)
        header.setSortIndicator(-1, Qt.SortOrder.AscendingOrder)
        header.setSectionsClickable(True)
        header.setSortIndicatorShown(True)
        header.setToolTip(_("Click a column title to sort; a third click restores the order."))
        table.setSortingEnabled(True)
    if table.selectionMode() == QAbstractItemView.SelectionMode.NoSelection:
        table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
    copy = QAction(_("Copy"), table)
    copy.setShortcut(QKeySequence.StandardKey.Copy)
    copy.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
    copy.triggered.connect(lambda: copy_table(table, selected_only=True))
    table.addAction(copy)
    table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

    def menu_at(pos: object) -> None:
        menu = QMenu(table)
        menu.addAction(
            _("Copy selected rows"), lambda: copy_table(table, selected_only=True)
        ).setEnabled(bool(table.selectedItems()))
        menu.addAction(_("Copy table (tab-separated)"), lambda: copy_table(table))
        menu.exec(table.viewport().mapToGlobal(pos))  # type: ignore[arg-type]

    table.customContextMenuRequested.connect(menu_at)
    # Compact rows (GUIDELINES §13.9: 28–30 px), whatever the platform style asks.
    rows = table.verticalHeader()
    rows.setMinimumSectionSize(ROW_HEIGHT)
    rows.setDefaultSectionSize(ROW_HEIGHT)
    rows.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)


def table_tsv(table: QTableWidget, *, selected_only: bool = False) -> str:
    """The table (or its selected rows) as tab-separated text with a header line."""
    rows = range(table.rowCount())
    if selected_only and table.selectedItems():
        rows = sorted({item.row() for item in table.selectedItems()})  # type: ignore[assignment]
    columns = [c for c in range(table.columnCount()) if not table.isColumnHidden(c)]

    def head(column: int) -> str:
        item = table.horizontalHeaderItem(column)
        return item.text() if item is not None else ""

    lines = ["\t".join(head(c).replace("\n", " ") for c in columns)]
    for row in rows:
        cells = []
        for column in columns:
            item = table.item(row, column)
            cells.append("" if item is None else item.text().replace("\t", " ").replace("\n", " "))
        lines.append("\t".join(cells))
    return "\n".join(lines) + "\n"


def copy_table(table: QTableWidget, *, selected_only: bool = False) -> str:
    """Put :func:`table_tsv` on the clipboard and return it."""
    text = table_tsv(table, selected_only=selected_only)
    clipboard = QGuiApplication.clipboard()
    if clipboard is not None:
        clipboard.setText(text)
    return text
