"""The frame around the pages: navigation on the left, the context bar on
top, the details pane on the right and the run status at the bottom.

None of these knows a measurement; the main window feeds them and routes
their signals to the pages, so a page never reaches into the frame.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from reverbscope.demo import localize_demo_name
from reverbscope.errors import ReverbScopeError
from reverbscope.i18n import _
from reverbscope.ui.widgets import label

#: Keys the navigation pane and the main window agree on.
NAV_HOME = "home"
NAV_DAW = "universal_daw"
NAV_STANDALONE = "standalone"
NAV_DEMO = "demo"
NAV_RESULTS = "results"
NAV_COMPARE = "compare"
NAV_PROJECT = "project"

_KIND = Qt.ItemDataRole.UserRole
_VALUE = Qt.ItemDataRole.UserRole + 1


class NavigationPane(QFrame):
    """Projects, positions and sessions on the left; the pages above them.

    Clicking a page item asks the window to show it (the window decides,
    so an unsaved take is protected); a session item opens that session;
    a position of the open project selects it on the Project page.
    """

    page_requested = Signal(str)
    session_requested = Signal(str)
    position_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("workspace", "left")
        self.setMinimumWidth(200)
        self.setMaximumWidth(340)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.tree = QTreeWidget()
        self.tree.setProperty("workspace", True)
        self.tree.setHeaderHidden(True)
        self.tree.setRootIsDecorated(False)
        self.tree.setIndentation(14)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tree.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.tree.itemClicked.connect(self._clicked)
        self.tree.itemActivated.connect(self._clicked)
        layout.addWidget(self.tree, 1)

        self._pages: dict[str, QTreeWidgetItem] = {}
        self._start = self._section(_("Start"))
        self._page_item(self._start, NAV_HOME, _("Home"))
        self._measure = self._section(_("Measure"))
        self._page_item(self._measure, NAV_DAW, _("Universal DAW Mode"))
        self._page_item(self._measure, NAV_STANDALONE, _("Standalone Mode"))
        self._page_item(self._measure, NAV_DEMO, _("Demo (no interface)"))
        self._current = self._section(_("Current measurement"))
        self._page_item(self._current, NAV_RESULTS, _("Results"))
        self._page_item(self._current, NAV_COMPARE, _("Compare"))
        self._project = self._section(_("Project"))
        self._page_item(self._project, NAV_PROJECT, _("No project open"))
        self._recent = self._section(_("Recent sessions"))
        self.set_result_available(False)
        self.tree.expandAll()

    # --- building ----------------------------------------------------------------

    def _section(self, title: str) -> QTreeWidgetItem:
        item = QTreeWidgetItem([title])
        item.setFlags(Qt.ItemFlag.ItemIsEnabled)
        font = item.font(0)
        font.setBold(True)
        font.setPointSizeF(max(font.pointSizeF() - 1.0, 8.0))
        item.setFont(0, font)
        item.setForeground(0, self.palette().placeholderText())
        self.tree.addTopLevelItem(item)
        return item

    def _page_item(self, parent: QTreeWidgetItem, key: str, title: str) -> QTreeWidgetItem:
        item = QTreeWidgetItem([title])
        item.setData(0, _KIND, "page")
        item.setData(0, _VALUE, key)
        parent.addChild(item)
        self._pages[key] = item
        return item

    # --- state -------------------------------------------------------------------

    def set_current_page(self, key: str) -> None:
        item = self._pages.get(key)
        self.tree.blockSignals(True)
        # A disabled entry keeps its selection through setCurrentItem: clear first.
        self.tree.clearSelection()
        if item is not None:
            self.tree.setCurrentItem(item)
            item.setSelected(True)
        self.tree.blockSignals(False)

    def set_result_available(self, available: bool, title: str = "") -> None:
        item = self._pages[NAV_RESULTS]
        item.setText(0, _("Results: {name}").format(name=title) if title else _("Results"))
        if not available and item.isSelected():
            # Drop the highlight while the entry can still be deselected.
            self.tree.blockSignals(True)
            item.setSelected(False)
            self.tree.blockSignals(False)
        flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        item.setFlags(flags if available else Qt.ItemFlag.ItemIsSelectable)
        item.setDisabled(not available)

    def set_project(
        self,
        name: str | None,
        positions: Sequence[tuple[str, Sequence[tuple[str, str]]]] = (),
        current_position: str = "",
    ) -> None:
        """List the open project's positions and their sessions (``(label,
        [(session title, directory), ...])``), or say no project is open."""
        item = self._pages[NAV_PROJECT]
        item.takeChildren()
        if name is None:
            item.setText(0, _("No project open"))
            return
        item.setText(0, name)
        for position, sessions in positions:
            child = QTreeWidgetItem([position or _("(unlisted)")])
            child.setData(0, _KIND, "position")
            child.setData(0, _VALUE, position)
            if position and position == current_position:
                font = child.font(0)
                font.setBold(True)
                child.setFont(0, font)
            item.addChild(child)
            for title, directory in sessions:
                leaf = QTreeWidgetItem([title])
                leaf.setData(0, _KIND, "session")
                leaf.setData(0, _VALUE, directory)
                leaf.setToolTip(0, directory)
                child.addChild(leaf)
        self.tree.expandItem(item)
        for index in range(item.childCount()):
            position_item = item.child(index)
            if position_item is not None:
                self.tree.expandItem(position_item)

    def refresh_recent(self) -> None:
        from reverbscope.io.recent import recent_session_paths
        from reverbscope.io.session_store import load_session

        self._recent.takeChildren()
        for path in recent_session_paths():
            try:
                session = load_session(path)
            except ReverbScopeError:
                title = path.name
            else:
                room = localize_demo_name(session.mode, session.room_name) or path.name
                position = localize_demo_name(session.mode, session.measurement_position)
                title = f"{room} · {position}" if position else room
            leaf = QTreeWidgetItem([title])
            leaf.setData(0, _KIND, "session")
            leaf.setData(0, _VALUE, str(path))
            leaf.setToolTip(0, str(path))
            self._recent.addChild(leaf)
        if self._recent.childCount() == 0:
            empty = QTreeWidgetItem([_("None yet")])
            empty.setFlags(Qt.ItemFlag.NoItemFlags)
            self._recent.addChild(empty)
        self.tree.expandItem(self._recent)

    def recent_paths(self) -> list[Path]:
        paths: list[Path] = []
        for i in range(self._recent.childCount()):
            child = self._recent.child(i)
            if child is not None and child.data(0, _KIND) == "session":
                paths.append(Path(str(child.data(0, _VALUE))))
        return paths

    # --- signals -----------------------------------------------------------------

    def _clicked(self, item: QTreeWidgetItem, _column: int = 0) -> None:
        kind = item.data(0, _KIND)
        value = item.data(0, _VALUE)
        if kind == "page":
            self.page_requested.emit(str(value))
        elif kind == "session":
            self.session_requested.emit(str(value))
        elif kind == "position":
            self.position_requested.emit(str(value))


class ContextBar(QFrame):
    """What the user is looking at, and the main actions of the page shown.

    Every page registers its action row once (:meth:`add_actions`); the
    window switches to the row of the page it shows. The buttons stay the
    page's own objects, so a page enables and disables them itself.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("workspace", "top")
        row = QHBoxLayout(self)
        row.setContentsMargins(16, 8, 16, 8)
        row.setSpacing(12)
        text = QVBoxLayout()
        text.setSpacing(1)
        self.title = label("", "page-title")
        self.subtitle = label("", "subtitle")
        self.subtitle.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        # The text gives way to the buttons: a long room name is clipped, a
        # button never is.
        for widget in (self.title, self.subtitle):
            widget.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        text.addWidget(self.title)
        text.addWidget(self.subtitle)
        row.addLayout(text, 1)
        self.action_stack = QStackedWidget()
        self.action_stack.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Preferred)
        self._blank = QWidget()
        self.action_stack.addWidget(self._blank)
        row.addWidget(
            self.action_stack, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )

    def add_actions(self, widget: QWidget) -> None:
        self.action_stack.addWidget(widget)

    def show_actions(self, widget: QWidget | None) -> None:
        current = widget if widget is not None else self._blank
        # A stack is as wide as its widest page unless the hidden ones are
        # ignored: the title would be clipped on pages with few actions.
        for index in range(self.action_stack.count()):
            page = self.action_stack.widget(index)
            if page is None:
                continue
            if page is current:
                page.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Preferred)
            else:
                page.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.action_stack.setCurrentWidget(current)
        self.action_stack.updateGeometry()

    def set_context(self, title: str, subtitle: str = "") -> None:
        self.title.setText(title)
        self.subtitle.setText(subtitle)
        self.subtitle.setVisible(bool(subtitle))


def action_row(*buttons: QWidget) -> QWidget:
    """A page's buttons for the context bar, right-aligned."""
    widget = QWidget()
    row = QHBoxLayout(widget)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(6)
    for button in buttons:
        row.addWidget(button)
    return widget


class DetailPane(QFrame):
    """The details of what is selected: a metric, a reflection, a check, a step.

    Pages register a detail widget each; the window shows the one of the
    page on screen. The pane folds away with its close button or the View
    menu and comes back with the same content.
    """

    closed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("workspace", "right")
        self.setMinimumWidth(240)
        self.setMaximumWidth(460)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        head = QWidget()
        head_row = QHBoxLayout(head)
        head_row.setContentsMargins(12, 8, 6, 6)
        self.title = label(_("Details"), "section")
        head_row.addWidget(self.title, 1)
        self.close_button = QToolButton()
        self.close_button.setText("×")
        self.close_button.setToolTip(_("Hide the details pane"))
        self.close_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_button.clicked.connect(self.closed.emit)
        head_row.addWidget(self.close_button)
        layout.addWidget(head)
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # A column, not a QStackedWidget: a stack takes the size of its largest
        # page, and word-wrapped rows then overlapped in the scroll area.
        self.column = QWidget()
        self.column.setProperty("page", True)
        self._column_layout = QVBoxLayout(self.column)
        self._column_layout.setContentsMargins(0, 0, 0, 0)
        self._column_layout.setSpacing(0)
        self._blank = label(
            _("Select a metric, a finding or a reflection to see its details."), "hint", wrap=True
        )
        self._blank.setContentsMargins(12, 4, 12, 12)
        self._blank.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._column_layout.addWidget(self._blank)
        self._column_layout.addStretch(1)
        self._details: list[QWidget] = []
        self.scroll_area.setWidget(self.column)
        layout.addWidget(self.scroll_area, 1)

    def add_detail(self, widget: QWidget) -> None:
        widget.hide()
        self._details.append(widget)
        self._column_layout.insertWidget(self._column_layout.count() - 1, widget)

    def show_detail(self, widget: QWidget | None, title: str = "") -> None:
        for detail in self._details:
            detail.setVisible(detail is widget)
        self._blank.setVisible(widget is None)
        self.title.setText(title or _("Details"))


class RunStatusBar(QWidget):
    """The bottom line: what runs now, how far it is, and Stop.

    Fed by the page that runs a take or an analysis; the Stop button stays
    visible for the whole run whatever page is shown. A run whose progress
    is unknown (the analysis) shows a busy bar, never a percentage.
    """

    stop_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        self.activity = QLabel("")
        self.activity.setProperty("role", "hint")
        row.addWidget(self.activity)
        self.progress = QProgressBar()
        self.progress.setFixedWidth(160)
        self.progress.setTextVisible(False)
        self.progress.hide()
        row.addWidget(self.progress)
        self.stop_button = QPushButton(_("Stop"))
        self.stop_button.setProperty("danger", True)
        self.stop_button.setToolTip(
            _("Stop the take that is playing (Esc on the measurement page).")
        )
        self.stop_button.clicked.connect(self.stop_requested.emit)
        self.stop_button.hide()
        row.addWidget(self.stop_button)
        self._running = False

    def set_running(self, text: str, fraction: float | None, *, stoppable: bool) -> None:
        self._running = True
        self.activity.setText(text)
        self.progress.show()
        if fraction is None:
            self.progress.setRange(0, 0)
        else:
            self.progress.setRange(0, 100)
            self.progress.setValue(int(max(0.0, min(1.0, fraction)) * 100.0))
        self.stop_button.setVisible(stoppable)
        self.stop_button.setEnabled(stoppable)

    def set_idle(self, text: str = "") -> None:
        self._running = False
        self.activity.setText(text)
        self.progress.hide()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.stop_button.hide()

    def is_running(self) -> bool:
        return self._running
