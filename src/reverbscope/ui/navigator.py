"""The navigator: the project, its positions and every open measurement.

One row per entry of the workspace model, grouped by position. The check
box draws the entry with the current one (overlay), the swatch is the
colour its curves have in every chart, and the baseline is marked. Clicking
a row makes it current. See docs/design/GUI_2_ARCHITECTURE.md §2 and §3.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPoint, Qt, QUrl, Signal
from PySide6.QtGui import QAction, QDesktopServices, QFont
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QMenu,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from reverbscope.i18n import N_, _, pgettext
from reverbscope.ui.plotkit import DASHES, swatch_icon
from reverbscope.ui.widgets import label
from reverbscope.ui.workspace import Entry, WorkspaceModel, entry_label

KEY_ROLE = Qt.ItemDataRole.UserRole
#: A position row carries its label under this role (entries carry their key).
POSITION_ROLE = Qt.ItemDataRole.UserRole + 1

NO_POSITION = N_("Not in the project")
TAKES = N_("This session's take")


class Navigator(QWidget):
    """The left column: project header, the entry tree, open buttons."""

    open_session_requested = Signal()
    open_project_requested = Signal()
    close_project_requested = Signal()
    #: Measure at this position (the strip takes it and shows Start).
    measure_position_requested = Signal(str)
    #: The user asked to remove ``key``; the window asks first for an unsaved take.
    remove_requested = Signal(str)
    #: Save the take (only offered on an unsaved take's row).
    save_requested = Signal(str)

    def __init__(self, model: WorkspaceModel, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.model = model
        self.setMinimumWidth(180)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 4, 6)
        layout.setSpacing(6)
        self.project_title = label(_("No project open"), "section")
        self.project_title.setWordWrap(True)
        layout.addWidget(self.project_title)
        self.project_hint = label("", "hint", wrap=True)
        layout.addWidget(self.project_hint)

        buttons = QHBoxLayout()
        buttons.setSpacing(4)
        self.open_project_button = QPushButton(_("Project..."))
        self.open_project_button.setToolTip(
            _("One room, several microphone positions: open or make a project folder.")
        )
        self.open_project_button.clicked.connect(self.open_project_requested.emit)
        self.open_session_button = QPushButton(_("Session..."))
        self.open_session_button.setToolTip(
            _("Add a saved session to the list (session.json or its folder).")
        )
        self.open_session_button.clicked.connect(self.open_session_requested.emit)
        buttons.addWidget(self.open_project_button)
        buttons.addWidget(self.open_session_button)
        layout.addLayout(buttons)

        self.tree = QTreeWidget()
        self.tree.setColumnCount(2)
        self.tree.setHeaderHidden(True)
        self.tree.setRootIsDecorated(False)
        self.tree.setIndentation(10)
        self.tree.setUniformRowHeights(True)
        self.tree.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        header = self.tree.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.tree.setToolTip(
            _(
                "Click a measurement to show it. Tick it to draw it with the current one. "
                "Right-click for the baseline and more."
            )
        )
        self.tree.currentItemChanged.connect(self._row_selected)
        self.tree.itemChanged.connect(self._item_changed)
        self.tree.customContextMenuRequested.connect(self._context_menu)
        layout.addWidget(self.tree, 1)
        self.loading = label("", "hint", wrap=True)
        layout.addWidget(self.loading)
        self._filling = False
        self._items: dict[str, QTreeWidgetItem] = {}

        model.entries_changed.connect(self.rebuild)
        model.project_changed.connect(self.rebuild)
        model.entry_updated.connect(self._update_entry)
        model.current_changed.connect(self._select_current)
        model.overlay_changed.connect(self._sync_checks)
        model.baseline_changed.connect(self._sync_baseline)
        model.loading_changed.connect(self._loading)
        self.rebuild()

    # --- building -----------------------------------------------------------------

    def rebuild(self) -> None:
        self._filling = True
        self.tree.clear()
        self._items.clear()
        model = self.model
        if model.project_path is not None:
            name = model.project.name if model.project is not None and model.project.name else ""
            self.project_title.setText(name or model.project_path.name)
            self.project_hint.setText(str(model.project_path))
            self.project_hint.setVisible(True)
        else:
            self.project_title.setText(_("No project open"))
            self.project_hint.setVisible(False)
        groups: dict[str, QTreeWidgetItem] = {}
        bold = QFont(self.font())
        bold.setBold(True)

        def group(title: str, position: str = "") -> QTreeWidgetItem:
            if title in groups:
                return groups[title]
            item = QTreeWidgetItem([title, ""])
            item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            item.setFont(0, bold)
            item.setData(0, POSITION_ROLE, position)
            self.tree.addTopLevelItem(item)
            item.setExpanded(True)
            groups[title] = item
            return item

        for position in model.positions:
            group(position, position)
        for entry in model.entries():
            if entry.is_take:
                parent = group(_(TAKES))
            elif entry.position and model.project_path is not None:
                parent = group(entry.position, entry.position)
            elif model.project_path is not None:
                parent = group(_(NO_POSITION))
            else:
                parent = self.tree.invisibleRootItem()
            item = QTreeWidgetItem()
            item.setData(0, KEY_ROLE, entry.key)
            self._fill_item(item, entry)
            parent.addChild(item)
            self._items[entry.key] = item
        for title, item in groups.items():
            if item.childCount() == 0 and item.data(0, POSITION_ROLE):
                hint = QTreeWidgetItem([_("no measurement yet"), ""])
                hint.setFlags(Qt.ItemFlag.ItemIsEnabled)
                hint.setForeground(0, self.palette().placeholderText())
                hint.setData(0, POSITION_ROLE, title)
                item.addChild(hint)
        self._filling = False
        self._select_current(model.current_key)

    def _fill_item(self, item: QTreeWidgetItem, entry: Entry) -> None:
        was = self._filling
        self._filling = True
        flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        text = entry_label(entry)
        if entry.loading:
            text = _("{name} (loading)").format(name=text)
        elif entry.error:
            text = _("{name} (cannot be read)").format(name=text)
            item.setToolTip(0, entry.error)
        else:
            flags |= Qt.ItemFlag.ItemIsUserCheckable
            item.setToolTip(0, str(entry.directory) if entry.directory else text)
        item.setFlags(flags)
        item.setText(0, text)
        item.setIcon(0, swatch_icon(entry.color, DASHES[entry.color_index % len(DASHES)]))
        if entry.result is not None:
            item.setCheckState(
                0,
                Qt.CheckState.Checked
                if self.model.is_overlaid(entry.key)
                else Qt.CheckState.Unchecked,
            )
        item.setText(1, self._marks(entry))
        self._filling = was

    def _marks(self, entry: Entry) -> str:
        marks = []
        if entry.key == self.model.baseline_key:
            marks.append(pgettext("workspace", "Baseline"))
        if entry.unsaved:
            marks.append(_("unsaved"))
        if entry.synthetic:
            marks.append(_("demo"))
        return "  ".join(marks)

    # --- following the model --------------------------------------------------------

    def _update_entry(self, key: str) -> None:
        item = self._items.get(key)
        entry = self.model.entry(key)
        if item is not None and entry is not None:
            self._fill_item(item, entry)

    def _select_current(self, key: str) -> None:
        item = self._items.get(key)
        self._filling = True
        if item is None:
            self.tree.clearSelection()
        else:
            self.tree.setCurrentItem(item)
        self._filling = False

    def _sync_checks(self) -> None:
        self._filling = True
        for key, item in self._items.items():
            entry = self.model.entry(key)
            if entry is not None and entry.result is not None:
                item.setCheckState(
                    0,
                    Qt.CheckState.Checked
                    if self.model.is_overlaid(key)
                    else Qt.CheckState.Unchecked,
                )
        self._filling = False

    def _sync_baseline(self) -> None:
        for key, item in self._items.items():
            entry = self.model.entry(key)
            if entry is not None:
                item.setText(1, self._marks(entry))

    def _loading(self, busy: bool) -> None:
        self.loading.setText(_("Reading the project's sessions...") if busy else "")

    # --- user actions ----------------------------------------------------------------

    def _row_selected(self, item: QTreeWidgetItem | None, _previous: object = None) -> None:
        if self._filling or item is None:
            return
        key = item.data(0, KEY_ROLE)
        if key:
            self.model.set_current(str(key))

    def _item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        if self._filling or column != 0:
            return
        key = item.data(0, KEY_ROLE)
        if key:
            self.model.set_overlay(str(key), item.checkState(0) == Qt.CheckState.Checked)

    def select(self, key: str) -> None:
        """Make ``key`` current as a click on its row would."""
        self.model.set_current(key)

    def _context_menu(self, point: QPoint) -> None:
        item = self.tree.itemAt(point)
        if item is None:
            return
        menu = self.context_menu(item)
        if menu is not None:
            menu.exec(self.tree.viewport().mapToGlobal(point))
            menu.deleteLater()

    def context_menu(self, item: QTreeWidgetItem) -> QMenu | None:
        """The menu of a row (built separately so tests can read it)."""
        menu = QMenu(self)
        key = item.data(0, KEY_ROLE)
        position = item.data(0, POSITION_ROLE)
        if not key:
            if position:
                measure = QAction(_("Measure at {position}").format(position=position), menu)
                measure.triggered.connect(
                    lambda _checked=False, p=str(position): self.measure_position_requested.emit(p)
                )
                menu.addAction(measure)
                return menu
            return None
        key = str(key)
        entry = self.model.entry(key)
        if entry is None:
            return None
        if entry.result is not None:
            if key == self.model.baseline_key:
                clear = QAction(_("Clear the baseline"), menu)
                clear.triggered.connect(lambda: self.model.set_baseline(""))
                menu.addAction(clear)
            else:
                base = QAction(_("Use as baseline"), menu)
                base.setToolTip(_("Comparisons and difference panes compare against it."))
                base.triggered.connect(lambda _checked=False, k=key: self.model.set_baseline(k))
                menu.addAction(base)
        if entry.unsaved:
            save = QAction(_("Save Session..."), menu)
            save.triggered.connect(lambda _checked=False, k=key: self.save_requested.emit(k))
            menu.addAction(save)
        if entry.directory is not None:
            folder = QAction(_("Show folder"), menu)
            folder.triggered.connect(
                lambda _checked=False, d=entry.directory: _open_folder(Path(d))
            )
            menu.addAction(folder)
        if entry.position and self.model.project_path is not None:
            again = QAction(_("Measure at {position}").format(position=entry.position), menu)
            again.triggered.connect(
                lambda _checked=False, p=entry.position: self.measure_position_requested.emit(p)
            )
            menu.addAction(again)
        menu.addSeparator()
        remove = QAction(_("Remove from the list"), menu)
        remove.setToolTip(_("Nothing is deleted on disk."))
        remove.triggered.connect(lambda _checked=False, k=key: self.remove_requested.emit(k))
        menu.addAction(remove)
        return menu


def _open_folder(directory: Path) -> None:
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(directory)))
