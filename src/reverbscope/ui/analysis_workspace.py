"""Task navigation and one persistent content canvas.

Project, measurement, analysis and comparison pages share state while their
controls remain local to the active task. Existing numbered view shortcuts
are retained. See docs/design/GUI_2_ARCHITECTURE.md.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
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
    """A task shell with one active canvas and optional edge panels.

    Measurement and analysis pages stay alive in one stack, so a navigation
    change never cancels a worker or loses a take.
    """

    view_chosen = Signal(str)
    task_chosen = Signal(str)

    def __init__(self, views: list[AnalysisView], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        from reverbscope.ui.components.context_bar import ContextBar
        from reverbscope.ui.components.tool_rail import ToolRail
        from reverbscope.ui.design.tokens import SPACE
        from reverbscope.ui.widgets import label

        self.views = {view.view_id: view for view in views}
        self.model = views[0].model
        self._pages: dict[QWidget, str] = {}
        self._analysis_view = "overview"
        self._tool = "pan"
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.taskbar = QWidget()
        self.taskbar.setProperty("taskbar", True)
        tasks = QHBoxLayout(self.taskbar)
        tasks.setContentsMargins(2 * SPACE, 0, 2 * SPACE, 0)
        tasks.setSpacing(0)
        tasks.addWidget(label("ReverbScope", "brand"))
        tasks.addSpacing(4 * SPACE)
        group = QButtonGroup(self)
        group.setExclusive(True)
        self.task_buttons: dict[str, QToolButton] = {}
        for key, title in (
            ("project", _("Project")),
            ("measure", _("Measure")),
            ("analysis", _("Analysis")),
            ("compare", _("Compare")),
        ):
            button = QToolButton()
            button.setText(title)
            button.setAccessibleName(title)
            button.setProperty("task", True)
            button.setCheckable(True)
            button.clicked.connect(lambda _checked=False, task=key: self.task_chosen.emit(task))
            group.addButton(button)
            self.task_buttons[key] = button
            tasks.addWidget(button)
        tasks.addStretch()
        self.save_button = QToolButton()
        self.save_button.setText(_("Save"))
        self.save_button.setAccessibleName(_("Save Session"))
        tasks.addWidget(self.save_button)
        self.settings_button = QToolButton()
        self.settings_button.setText(_("Settings"))
        self.settings_button.setAccessibleName(_("Settings"))
        tasks.addWidget(self.settings_button)
        layout.addWidget(self.taskbar)
        self.context = ContextBar(self.model)
        self.context.entry_chosen.connect(self.model.set_current)
        self.context.view.currentIndexChanged.connect(self._view_selected)
        layout.addWidget(self.context)
        self.navigator_button = self.context.list_button
        self.inspector_button = self.context.details_button
        self.body = QWidget()
        body = QHBoxLayout(self.body)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        self.tools = ToolRail()
        self.tools.chosen.connect(self._use_tool)
        body.addWidget(self.tools)
        self.stack = QStackedWidget()
        for view in views:
            self.stack.addWidget(view)
        body.addWidget(self.stack, 1)
        layout.addWidget(self.body, 1)
        self.stack.currentChanged.connect(self._sync_buttons)
        self.retitle()

    def _view_selected(self, index: int) -> None:
        view_id = self.context.view.itemData(index)
        if isinstance(view_id, str) and view_id != self.current_view_id():
            self.view_chosen.emit(view_id)

    def add_page(self, page: QWidget, task: str = "measure") -> None:
        self._pages[page] = task
        self.stack.addWidget(page)

    def show_view(self, view_id: str) -> AnalysisView:
        view = self.views[view_id]
        self.stack.setCurrentWidget(view)
        return view

    def current_view_id(self) -> str:
        widget = self.stack.currentWidget()
        return widget.view_id if isinstance(widget, AnalysisView) else ""

    def current_task(self) -> str:
        view_id = self.current_view_id()
        if view_id in {"project", "compare"}:
            return view_id
        if view_id:
            return "analysis"
        widget = self.stack.currentWidget()
        return self._pages.get(widget, "project") if widget is not None else "project"

    def _sync_buttons(self, _index: int = 0) -> None:
        task = self.current_task()
        view_id = self.current_view_id()
        self.task_buttons[task].setChecked(True)
        self.context.set_analysis(task == "analysis")
        self.context.measurement_controls.setVisible(task == "measure")
        self.context.title.setText(
            _("Project")
            if task == "project"
            else _("Compare")
            if task == "compare"
            else _("Measure")
        )
        self.tools.setVisible(
            view_id in {"fr", "etc", "decay", "noise", "spectrogram", "waterfall"}
        )
        self.context.view.blockSignals(True)
        self.context.view.setCurrentIndex(self.context.view.findData(view_id))
        self.context.view.blockSignals(False)
        if task == "analysis":
            self._analysis_view = view_id
            self._use_tool(self._tool)

    def _use_tool(self, tool: str) -> None:
        from reverbscope.ui.plotkit import ChartPanel

        view = self.stack.currentWidget()
        if view is None:
            return
        if tool != "fit":
            self._tool = tool
        for chart in view.findChildren(ChartPanel):
            if tool == "fit":
                chart.reset_view()
            else:
                chart.set_interaction(tool)
        if self.current_view_id() == "room" and tool == "fit":
            from reverbscope.ui.room.view import RoomView

            room = self.views["room"]
            assert isinstance(room, RoomView)
            room.canvas.fit()

    def retitle(self) -> None:
        self.context.view.blockSignals(True)
        self.context.view.clear()
        for view_id, view in self.views.items():
            if view_id not in {"project", "compare"}:
                self.context.view.addItem(view.title(), view_id)
        self.context.view.blockSignals(False)
        self._sync_buttons()

    def view_title(self, view_id: str) -> str:
        view = self.views.get(view_id)
        return view.title() if view is not None else _("Project")
