"""The centre column: the view bar and the stack of views and pages.

``default_views()`` builds the analysis views in shortcut order
(docs/design/GUI_2_ARCHITECTURE.md §4). The stack also holds the start
panel and the two measurement set-up pages; showing one of those leaves no
view button checked.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
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
    """View bar over a stack; the stack is the window's ``stack``."""

    #: A view button was clicked (``view_id``).
    view_chosen = Signal(str)

    def __init__(self, views: list[AnalysisView], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        bar = QWidget()
        bar.setProperty("viewbar", True)
        self.bar_layout = QHBoxLayout(bar)
        self.bar_layout.setContentsMargins(6, 4, 6, 4)
        self.bar_layout.setSpacing(2)
        scroll = QScrollArea()
        scroll.setWidget(bar)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        scroll.setFixedHeight(40)
        self.bar_scroll = scroll
        layout.addWidget(scroll)
        self.stack = QStackedWidget()
        layout.addWidget(self.stack, 1)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.views: dict[str, AnalysisView] = {}
        self.buttons: dict[str, QToolButton] = {}
        for view in views:
            self._add_view(view)
        self.bar_layout.addStretch(1)
        self.stack.currentChanged.connect(self._sync_buttons)

    def _add_view(self, view: AnalysisView) -> None:
        self.views[view.view_id] = view
        self.stack.addWidget(view)
        button = QToolButton()
        button.setCheckable(True)
        button.setAutoRaise(True)
        button.setProperty("viewtab", True)
        button.setText(view.title())
        if view.view_id in NUMBERED_VIEWS:
            number = NUMBERED_VIEWS.index(view.view_id) + 1
            button.setToolTip(f"{view.title()}  (Ctrl+{number})")
        elif view.view_id == "compare":
            button.setToolTip(f"{view.title()}  (Ctrl+0)")
        button.clicked.connect(lambda _checked=False, v=view.view_id: self.view_chosen.emit(v))
        self.group.addButton(button)
        self.buttons[view.view_id] = button
        self.bar_layout.addWidget(button)

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
        if view_id:
            self.buttons[view_id].setChecked(True)
            return
        # A page that is not a view: no button stays checked.
        self.group.setExclusive(False)
        for button in self.buttons.values():
            button.setChecked(False)
        self.group.setExclusive(True)

    def retitle(self) -> None:
        for view_id, view in self.views.items():
            self.buttons[view_id].setText(view.title())

    def view_title(self, view_id: str) -> str:
        view = self.views.get(view_id)
        return view.title() if view is not None else _("Start")
