"""The centre column: grouped analysis views over the stack.

The bar groups the analysis so ten views are not one flat row
(docs/design/GUI_2_ARCHITECTURE.md §4):

Overview · Frequency · Time · Decay · Spectral · Compare · Report

Spectral keeps a second selector (spectrogram, waterfall, noise). Project
sits apart from the analysis groups. ``Ctrl+1`` … ``Ctrl+8`` open the
numbered views and ``Ctrl+0`` opens Compare; the 3D room view (formerly
``Ctrl+8``) was removed, so Project moved from ``Ctrl+9`` to ``Ctrl+8``.
Switching a view does not clear the measurement list and does not stop a
take.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QResizeEvent
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMenu,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from reverbscope.i18n import _
from reverbscope.ui import icons
from reverbscope.ui.state import MeasurementState
from reverbscope.ui.views.base import AnalysisView
from reverbscope.ui.widgets import label, native_shortcut
from reverbscope.ui.workspace import WorkspaceModel

#: View ids with a Ctrl+<n> shortcut, in order (Ctrl+1 … Ctrl+8).
NUMBERED_VIEWS = (
    "overview",
    "fr",
    "etc",
    "decay",
    "noise",
    "spectrogram",
    "waterfall",
    "project",
)

#: Analysis groups shown on the bar, in order. Project is not one of them.
VIEW_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("overview", ("overview",)),
    ("frequency", ("fr",)),
    ("time", ("etc",)),
    ("decay", ("decay",)),
    ("spectral", ("spectrogram", "waterfall", "noise")),
    ("compare", ("compare",)),
    ("report", ("report",)),
)


def group_label(group_id: str) -> str:
    """Short name of a bar group. Not the view's own title when that title is long."""
    labels = {
        "overview": _("Overview"),
        "frequency": _("Frequency"),
        "time": _("Time"),
        "decay": _("Decay"),
        "spectral": _("Spectral"),
        "compare": _("Compare"),
        "report": _("Report"),
    }
    return labels.get(group_id, group_id)


def group_of(view_id: str) -> str:
    """The bar group that contains ``view_id``, or ``""``."""
    for group_id, view_ids in VIEW_GROUPS:
        if view_id in view_ids:
            return group_id
    return ""


def _native(sequence: str) -> str:
    """``sequence`` as the platform shows it (Command on macOS, Ctrl elsewhere)."""
    return native_shortcut(sequence)


def _shortcut_for(view_id: str) -> str:
    if view_id in NUMBERED_VIEWS:
        return _native(f"Ctrl+{NUMBERED_VIEWS.index(view_id) + 1}")
    if view_id == "compare":
        return _native("Ctrl+0")
    return ""


def default_views(model: WorkspaceModel, state: MeasurementState) -> list[AnalysisView]:
    """Every analysis view, numbered ones first, then Compare and the report."""
    from reverbscope.ui.compare_view import ComparePage
    from reverbscope.ui.project_view import ProjectPage
    from reverbscope.ui.views.decay import DecayView
    from reverbscope.ui.views.frequency import FrequencyView
    from reverbscope.ui.views.impulse import ImpulseView
    from reverbscope.ui.views.noise import NoiseView
    from reverbscope.ui.views.overview import OverviewView
    from reverbscope.ui.views.report import ReportView
    from reverbscope.ui.views.timefreq import SpectrogramView, WaterfallView

    return [
        OverviewView(model),
        FrequencyView(model),
        ImpulseView(model),
        DecayView(model),
        NoiseView(model),
        SpectrogramView(model),
        WaterfallView(model),
        ProjectPage(state, model),
        ComparePage(model),
        ReportView(model),
    ]


class ElidingLabel(QLabel):
    """A one-line label that elides its text to its width and keeps the full
    text in the tooltip (the toolbar's title and subtitle)."""

    def __init__(self, role: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("role", role)
        self._full = ""
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)

    def set_full_text(self, text: str) -> None:
        self._full = text
        self._elide()

    def full_text(self) -> str:
        return self._full

    def _elide(self) -> None:
        width = max(8, self.width() - 2)
        shown = self.fontMetrics().elidedText(self._full, Qt.TextElideMode.ElideRight, width)
        self.setText(shown)
        self.setToolTip(self._full if shown != self._full else "")

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802 - Qt override
        super().resizeEvent(event)
        self._elide()


class AnalysisWorkspace(QWidget):
    """Grouped view bar over a stack; the stack is the window's ``stack``."""

    #: A view button or the secondary selector chose ``view_id``.
    view_chosen = Signal(str)
    #: The toolbar's Save button.
    save_requested = Signal()

    def __init__(self, views: list[AnalysisView], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumWidth(420)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        # One unified 52 px toolbar (docs/design/light-sidebar/SPEC.md §6):
        # sidebar switch, title and subtitle, the view groups as a segmented
        # control, then Save and the inspector switch. No second bar.
        bar = QWidget()
        bar.setProperty("viewbar", True)
        bar.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        bar.setFixedHeight(52)
        self.bar = bar
        self.bar_layout = QHBoxLayout(bar)
        self.bar_layout.setContentsMargins(10, 0, 10, 0)
        self.bar_layout.setSpacing(8)
        layout.addWidget(bar)
        # The groups scroll when the window is narrow, so a Chinese label is
        # not clipped. The side switches stay pinned.
        self.group_bar = QWidget()
        self.group_layout = QHBoxLayout(self.group_bar)
        self.group_layout.setContentsMargins(0, 0, 0, 0)
        self.group_layout.setSpacing(0)
        self.segment = QWidget()
        self.segment.setProperty("segmented", True)
        self.segment.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.segment_layout = QHBoxLayout(self.segment)
        self.segment_layout.setContentsMargins(2, 0, 2, 0)
        self.segment_layout.setSpacing(0)
        self.group_scroll = QScrollArea()
        self.group_scroll.setWidget(self.group_bar)
        self.group_scroll.setWidgetResizable(True)
        self.group_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.group_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.group_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.group_scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.group_scroll.setProperty("viewscroll", True)
        self.stack = QStackedWidget()
        layout.addWidget(self.stack, 1)

        self.navigator_button = self._icon_switch(
            "panel-left",
            _("List"),
            _("Show or hide the measurement list ({shortcut}).").format(
                shortcut=_native("Ctrl+Shift+Left")
            ),
        )
        self.bar_layout.addWidget(self.navigator_button)

        titles = QVBoxLayout()
        titles.setContentsMargins(0, 0, 0, 0)
        titles.setSpacing(0)
        self.title_label = ElidingLabel("toolbar-title")
        self.subtitle_label = ElidingLabel("toolbar-subtitle")
        for widget in (self.title_label, self.subtitle_label):
            widget.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
            titles.addWidget(widget)
        self.title_box = QWidget()
        self.title_box.setLayout(titles)
        self.title_box.setMinimumWidth(0)
        self.title_box.setMaximumWidth(220)
        self.bar_layout.addWidget(self.title_box, 0)
        self._title = ""
        self._subtitle = ""

        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.views: dict[str, AnalysisView] = {}
        self.buttons: dict[str, QToolButton] = {}
        self._last: dict[str, str] = {}
        for view in views:
            self.views[view.view_id] = view
            self.stack.addWidget(view)
        for group_id, view_ids in VIEW_GROUPS:
            self._last[group_id] = view_ids[0]
            button = QToolButton()
            button.setCheckable(True)
            button.setAutoRaise(True)
            button.setProperty("viewtab", True)
            button.setText(group_label(group_id))
            button.setToolTip(self._group_tip(group_id, view_ids))
            button.clicked.connect(lambda _checked=False, g=group_id: self._group_clicked(g))
            self.group.addButton(button)
            self.buttons[group_id] = button
            self.segment_layout.addWidget(button)
        self.subview = QComboBox()
        self.subview.setVisible(False)
        self.subview.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.subview.setToolTip(_("The chart inside this group."))
        self.subview.currentIndexChanged.connect(self._subview_chosen)
        # Secondary charts get their own row instead of widening the view bar.
        self.subview_bar = QWidget()
        self.subview_bar.setProperty("subviewbar", True)
        self.subview_bar.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        subview_layout = QHBoxLayout(self.subview_bar)
        subview_layout.setContentsMargins(16, 6, 16, 6)
        subview_layout.setSpacing(8)
        subview_layout.addWidget(label(_("View"), "caption"))
        subview_layout.addWidget(self.subview)
        subview_layout.addStretch(1)
        self.subview_bar.hide()
        layout.insertWidget(1, self.subview_bar)
        self.group_layout.addStretch(1)
        self.group_layout.addWidget(self.segment)

        self.project_button = QToolButton()
        self.project_button.setCheckable(True)
        self.project_button.setAutoRaise(True)
        self.project_button.setProperty("viewtab", True)
        self.project_button.setProperty("projecttab", True)
        self.project_button.setText(_("Project"))
        self.project_button.setIcon(icons.icon("folder-open", 14))
        self.project_button.setIconSize(icons.icon_size(14))
        self.project_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        project_key = _shortcut_for("project")
        self.project_button.setToolTip(
            _("The open project, apart from the analysis charts ({shortcut}).").format(
                shortcut=project_key
            )
            if project_key
            else _("The open project, apart from the analysis charts.")
        )
        self.project_button.clicked.connect(lambda _checked=False: self.view_chosen.emit("project"))
        self.group_layout.addWidget(self.project_button)
        self.group_layout.addStretch(1)
        self.bar_layout.addWidget(self.group_scroll, 1)
        # When the groups do not fit (960 px, SPEC §13), a menu lists them all.
        self.more_button = QToolButton()
        self.more_button.setProperty("panelswitch", True)
        self.more_button.setIcon(icons.icon("chevron-down", 16))
        self.more_button.setIconSize(icons.icon_size(16))
        self.more_button.setFixedSize(26, 30)
        self.more_button.setToolTip(_("All views"))
        self.more_button.setAccessibleName(_("All views"))
        self.more_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.more_menu = QMenu(self.more_button)
        self.more_button.setMenu(self.more_menu)
        self.more_menu.aboutToShow.connect(self._fill_more_menu)
        self.more_button.hide()
        self.bar_layout.addWidget(self.more_button)

        self.save_button = self._icon_switch(
            "save",
            _("Save Session..."),
            _("Save the measurement made in this window ({shortcut}).").format(
                shortcut=_native("Ctrl+S")
            ),
            checkable=False,
        )
        self.save_button.clicked.connect(self.save_requested.emit)
        self.bar_layout.addWidget(self.save_button)
        self.inspector_button = self._icon_switch(
            "panel-right",
            _("Inspector"),
            _("Show or hide the inspector ({shortcut}).").format(
                shortcut=_native("Ctrl+Shift+Right")
            ),
        )
        self.bar_layout.addWidget(self.inspector_button)
        bar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.group_scroll.setFixedHeight(40)
        self.stack.currentChanged.connect(self._sync_buttons)

    def _icon_switch(
        self, icon_name: str, text: str, tip: str, *, checkable: bool = True
    ) -> QToolButton:
        """An 18 px icon button with a 30 x 30 hit area; its text is its accessible name."""
        button = QToolButton()
        button.setCheckable(checkable)
        button.setChecked(checkable)
        button.setAutoRaise(True)
        button.setProperty("panelswitch", True)
        button.setProperty("icon_name", icon_name)
        button.setText(text)
        button.setAccessibleName(text)
        button.setToolTip(tip)
        button.setIcon(icons.icon(icon_name, 18))
        button.setIconSize(icons.icon_size(18))
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        button.setFixedSize(30, 30)
        return button

    def _fill_more_menu(self) -> None:
        self.more_menu.clear()
        current = self.current_view_id()
        for group_id, view_ids in VIEW_GROUPS:
            for view_id in view_ids:
                action = self.more_menu.addAction(self.views[view_id].title())
                action.setCheckable(True)
                action.setChecked(view_id == current)
                action.triggered.connect(lambda _checked=False, v=view_id: self.view_chosen.emit(v))
            if group_id == "spectral":
                self.more_menu.addSeparator()
        if "project" in self.views:
            self.more_menu.addSeparator()
            action = self.more_menu.addAction(self.views["project"].title())
            action.triggered.connect(lambda _checked=False: self.view_chosen.emit("project"))

    def _fit_title(self, width: int) -> None:
        """Show the title only where the groups still fit beside it unscrolled."""
        fixed = sum(
            button.width()
            for button in (self.navigator_button, self.save_button, self.inspector_button)
        )
        room = width - fixed - 40 - self.group_bar.sizeHint().width()
        self.more_button.setVisible(room < 0)
        self.title_box.setVisible(room >= 120)
        self.title_box.setFixedWidth(max(0, min(220, room)))

    def set_place(self, title: str, subtitle: str = "") -> None:
        """The toolbar's title and subtitle (what is shown, and of which measurement)."""
        self._title = title
        self._subtitle = subtitle
        self._elide_titles()

    def _elide_titles(self) -> None:
        self.title_label.set_full_text(self._title)
        self.subtitle_label.set_full_text(self._subtitle)
        self.subtitle_label.setVisible(bool(self._subtitle))

    def restyle_icons(self) -> None:
        self.more_button.setIcon(icons.icon("chevron-down", 16))
        for button in (self.navigator_button, self.save_button, self.inspector_button):
            name = button.property("icon_name")
            if isinstance(name, str):
                button.setIcon(icons.icon(name, 18))
        self.project_button.setIcon(icons.icon("folder-open", 14))

    def _group_tip(self, group_id: str, view_ids: tuple[str, ...]) -> str:
        names = ", ".join(self.views[view_id].title() for view_id in view_ids)
        keys = ", ".join(key for view_id in view_ids if (key := _shortcut_for(view_id)))
        label = group_label(group_id)
        if keys:
            return _("{group}: {names} ({keys}).").format(group=label, names=names, keys=keys)
        return _("{group}: {names}.").format(group=label, names=names)

    def _group_clicked(self, group_id: str) -> None:
        view_ids = dict(VIEW_GROUPS)[group_id]
        current = self.current_view_id()
        if current in view_ids:
            return
        self.view_chosen.emit(self._last.get(group_id, view_ids[0]))

    def _subview_chosen(self, index: int) -> None:
        if index < 0:
            return
        view_id = str(self.subview.itemData(index))
        if view_id and view_id != self.current_view_id():
            self.view_chosen.emit(view_id)

    def add_page(self, page: QWidget) -> None:
        """A page that is not a view (start panel, set-up pages)."""
        self.stack.addWidget(page)

    def show_view(self, view_id: str) -> AnalysisView:
        view = self.views[view_id]
        self.stack.setCurrentWidget(view)
        return view

    def current_view_id(self) -> str:
        widget = self.stack.currentWidget()
        return widget.view_id if isinstance(widget, AnalysisView) else ""

    def _sync_buttons(self, _index: int) -> None:
        view_id = self.current_view_id()
        group_id = group_of(view_id)
        self.project_button.setChecked(view_id == "project")
        QTimer.singleShot(0, self, self._reveal_active_view)
        if not group_id:
            self.group.setExclusive(False)
            for button in self.buttons.values():
                button.setChecked(False)
            self.group.setExclusive(True)
            self.subview.setVisible(False)
            self.subview_bar.hide()
            return
        self._last[group_id] = view_id
        self.buttons[group_id].setChecked(True)
        view_ids = dict(VIEW_GROUPS)[group_id]
        self.subview.blockSignals(True)
        self.subview.clear()
        if len(view_ids) > 1:
            for item_id in view_ids:
                self.subview.addItem(self.views[item_id].title(), item_id)
            self.subview.setCurrentIndex(max(self.subview.findData(view_id), 0))
            self.subview.setVisible(True)
            self.subview_bar.show()
        else:
            self.subview.setVisible(False)
            self.subview_bar.hide()
        self.subview.blockSignals(False)

    def _reveal_active_view(self) -> None:
        """Menu and keyboard navigation keep the selected tab in the viewport."""
        view_id = self.current_view_id()
        button = (
            self.project_button if view_id == "project" else self.buttons.get(group_of(view_id))
        )
        if button is not None:
            self.group_scroll.ensureWidgetVisible(button, 4, 0)

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802 - Qt override
        super().resizeEvent(event)
        # A narrow centre column gives the toolbar title's room to the groups.
        self._fit_title(event.size().width())
        # QScrollArea needs the new viewport geometry before it scrolls.
        QTimer.singleShot(0, self, self._reveal_active_view)

    def retitle(self) -> None:
        for group_id, button in self.buttons.items():
            button.setText(group_label(group_id))
            view_ids = dict(VIEW_GROUPS)[group_id]
            button.setToolTip(self._group_tip(group_id, view_ids))
        if "project" in self.views:
            self.project_button.setText(self.views["project"].title())
        self._sync_buttons(self.stack.currentIndex())

    def view_title(self, view_id: str) -> str:
        view = self.views.get(view_id)
        return view.title() if view is not None else _("Start")
