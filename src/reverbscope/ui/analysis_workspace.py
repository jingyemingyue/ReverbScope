"""The centre column: grouped analysis views over the stack.

The bar groups the analysis so eleven views are not one flat row
(docs/design/GUI_2_ARCHITECTURE.md §4):

Overview · Frequency · Time · Decay · Spectral · Room · Compare · Report

Spectral keeps a second selector (spectrogram, waterfall, noise). Project
sits apart from the analysis groups. ``Ctrl+1`` … ``Ctrl+9`` and ``Ctrl+0``
still open the same views as before. Switching a view does not clear the
measurement list and does not stop a take.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from reverbscope.i18n import _
from reverbscope.ui.state import MeasurementState
from reverbscope.ui.views.base import AnalysisView
from reverbscope.ui.widgets import native_shortcut
from reverbscope.ui.workspace import WorkspaceModel

#: View ids with a Ctrl+<n> shortcut, in order (Ctrl+1 … Ctrl+9).
NUMBERED_VIEWS = (
    "overview",
    "fr",
    "etc",
    "decay",
    "noise",
    "spectrogram",
    "waterfall",
    "room",
    "project",
)

#: Analysis groups shown on the bar, in order. Project is not one of them.
VIEW_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("overview", ("overview",)),
    ("frequency", ("fr",)),
    ("time", ("etc",)),
    ("decay", ("decay",)),
    ("spectral", ("spectrogram", "waterfall", "noise")),
    ("room", ("room",)),
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
        "room": _("Room"),
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
    from reverbscope.ui.room.view import RoomView
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
        RoomView(model),
        ProjectPage(state, model),
        ComparePage(model),
        ReportView(model),
    ]


class AnalysisWorkspace(QWidget):
    """Grouped view bar over a stack; the stack is the window's ``stack``."""

    #: A view button or the secondary selector chose ``view_id``.
    view_chosen = Signal(str)

    def __init__(self, views: list[AnalysisView], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumWidth(420)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        bar = QWidget()
        bar.setProperty("viewbar", True)
        self.bar_layout = QHBoxLayout(bar)
        self.bar_layout.setContentsMargins(4, 2, 4, 0)
        self.bar_layout.setSpacing(0)
        layout.addWidget(bar)
        # The groups scroll when the window is narrow, so a Chinese label is
        # not clipped. List and Inspector stay pinned.
        self.group_bar = QWidget()
        self.group_layout = QHBoxLayout(self.group_bar)
        self.group_layout.setContentsMargins(0, 0, 0, 0)
        self.group_layout.setSpacing(0)
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

        self.navigator_button = QToolButton()
        self.navigator_button.setCheckable(True)
        self.navigator_button.setChecked(True)
        self.navigator_button.setAutoRaise(True)
        self.navigator_button.setProperty("panelswitch", True)
        self.navigator_button.setText(_("List"))
        self.navigator_button.setToolTip(
            _("Show or hide the measurement list ({shortcut}).").format(
                shortcut=_native("Ctrl+Shift+Left")
            )
        )
        self.bar_layout.addWidget(self.navigator_button)

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
            self.group_layout.addWidget(button)
        self.subview = QComboBox()
        self.subview.setVisible(False)
        self.subview.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.subview.setToolTip(_("The chart inside this group."))
        self.subview.currentIndexChanged.connect(self._subview_chosen)
        # Secondary charts get their own row instead of widening the view bar.
        self.subview_bar = QWidget()
        self.subview_bar.setProperty("subviewbar", True)
        subview_layout = QHBoxLayout(self.subview_bar)
        subview_layout.setContentsMargins(8, 3, 8, 3)
        subview_layout.setSpacing(6)
        subview_layout.addWidget(QLabel(_("View")))
        subview_layout.addWidget(self.subview)
        subview_layout.addStretch(1)
        self.subview_bar.hide()
        layout.insertWidget(1, self.subview_bar)
        self.group_layout.addStretch(1)

        self.project_button = QToolButton()
        self.project_button.setCheckable(True)
        self.project_button.setAutoRaise(True)
        self.project_button.setProperty("viewtab", True)
        self.project_button.setProperty("projecttab", True)
        self.project_button.setText(_("Project"))
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
        self.bar_layout.addWidget(self.group_scroll, 1)

        self.inspector_button = QToolButton()
        self.inspector_button.setCheckable(True)
        self.inspector_button.setChecked(True)
        self.inspector_button.setAutoRaise(True)
        self.inspector_button.setProperty("panelswitch", True)
        self.inspector_button.setText(_("Inspector"))
        self.inspector_button.setToolTip(
            _("Show or hide the inspector ({shortcut}).").format(
                shortcut=_native("Ctrl+Shift+Right")
            )
        )
        self.bar_layout.addWidget(self.inspector_button)
        bar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.group_scroll.setFixedHeight(self.navigator_button.sizeHint().height() + 10)
        self.stack.currentChanged.connect(self._sync_buttons)

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
