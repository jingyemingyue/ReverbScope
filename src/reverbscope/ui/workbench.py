"""The workbench window: menus, toolbar, the chart area, the measurement
list, the inspector and the run status line.

The window manages measurements and views, not pages: every measurement
opened or taken stays in the list with its colour; the charts draw the
visible ones, the inspector explains the selected one, and a job that runs
(a take, an analysis) reports to the status line with Stop in reach.
Layout and window state are saved with QSettings and can be reset.
"""

from __future__ import annotations

import contextlib
import sys
from pathlib import Path

from PySide6.QtCore import QByteArray, QEvent, QObject, QSettings, Qt, QUrl
from PySide6.QtGui import (
    QAction,
    QActionGroup,
    QCloseEvent,
    QDesktopServices,
    QGuiApplication,
    QKeySequence,
)
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDockWidget,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QStatusBar,
    QToolBar,
    QToolButton,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from reverbscope import __version__
from reverbscope.errors import ReverbScopeError
from reverbscope.health import status_word
from reverbscope.i18n import _
from reverbscope.interpretation import available_profiles
from reverbscope.settings import load_settings
from reverbscope.ui.controller import WorkspaceController, suggest_label
from reverbscope.ui.document import Measurement, WorkspaceDocument
from reverbscope.ui.inspector import InspectorPanel
from reverbscope.ui.measure_dialog import DawAnalysisDialog, StandaloneMeasureDialog
from reverbscope.ui.measurement_controller import MeasurementController
from reverbscope.ui.measurement_model import MeasurementListModel, connect_selection, style_tree
from reverbscope.ui.plot_data import PLOT_KINDS
from reverbscope.ui.plot_panel import PlotPanel, ZoomLink
from reverbscope.ui.results_presenter import HEALTH_TONE, health_summary
from reverbscope.ui.status_line import RunStatusBar
from reverbscope.ui.theme import (
    apply_application_chrome,
    apply_report_font,
    color_scheme,
    tone_color,
)
from reverbscope.ui.widgets import TONE_GLYPH, app_icon, error_box

#: QSettings keys of the window layout.
_SETTINGS_GEOMETRY = "workbench/geometry"
_SETTINGS_STATE = "workbench/state"
_SETTINGS_SPLIT = "workbench/split"
_SETTINGS_KINDS = "workbench/kinds"
_SETTINGS_DUAL = "workbench/dual"
_SETTINGS_INSPECTOR = "workbench/inspector"

#: The chart kinds the two panels open on: the response and the decay.
DEFAULT_KINDS = ("frequency", "decay")


def about_html() -> str:
    """About box body, translated when it is shown (not when this module loads)."""
    return _(
        "<b>ReverbScope {version}</b><br>"
        "An open-source, DAW-independent recording environment analyzer.<br>"
        "A validity flag on every number · any DAW: WAV in, WAV out · "
        "no room score, no invented figures.<br><br>"
        "Licensed under the Apache License, Version 2.0.<br>"
        "This program uses Qt and PySide6 (Copyright The Qt Company Ltd. and contributors) "
        "under the GNU Lesser General Public License v3; the Qt libraries are loaded as "
        "separate shared libraries and may be replaced by interface-compatible versions. "
        "NumPy, SciPy, matplotlib, soundfile (libsndfile, LGPL-2.1) and sounddevice "
        "(PortAudio) are used under their respective licenses.<br><br>"
        "A desktop bundle ships a <code>THIRD_PARTY_LICENSES/</code> directory next to the "
        "executable (and inside <code>ReverbScope.app</code> on macOS). From a source checkout "
        "see docs/DEPENDENCIES.md. Levels are digital (dBFS) unless a calibration is provided; "
        "ReverbScope never reports dB SPL."
    ).format(version=__version__)


def about_box(parent: QWidget | None = None) -> QMessageBox:
    """The About dialog. The button is ours, so it does not depend on Qt's catalog."""
    box = QMessageBox(parent)
    box.setWindowTitle(_("About ReverbScope"))
    box.setWindowIcon(app_icon())
    box.setIconPixmap(app_icon().pixmap(64, 64))
    box.setTextFormat(Qt.TextFormat.RichText)
    box.setText(about_html())
    box.addButton(_("OK"), QMessageBox.ButtonRole.AcceptRole)
    return box


def license_notice_path() -> Path | None:
    """Directory or file the About/Help menus should open for third-party texts."""
    candidates: list[Path] = []
    if getattr(sys, "frozen", False):
        exe = Path(sys.executable).resolve().parent
        candidates.extend(
            [exe / "THIRD_PARTY_LICENSES", exe.parent / "Resources" / "THIRD_PARTY_LICENSES"]
        )
    source_root: Path | None = None
    for parent in Path(__file__).resolve().parents:
        if (parent / "docs" / "DEPENDENCIES.md").is_file():
            source_root = parent
            break
    if source_root is not None:
        candidates.append(source_root / "THIRD_PARTY_LICENSES")
    for path in candidates:
        if path.is_dir():
            return path
    if source_root is not None:
        return source_root / "docs" / "DEPENDENCIES.md"
    return None


class QualityButton(QToolButton):
    """The selected measurement's quality, in the toolbar: a glyph and the
    status word in the tone's colour. Clicking it opens the inspector."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.set_status(None)

    def set_status(self, measurement: Measurement | None) -> None:
        if measurement is None:
            self.setText(_("No measurement selected"))
            self.setToolTip("")
            self.setStyleSheet("")
            self.setEnabled(False)
            return
        tone = HEALTH_TONE[measurement.status]
        fg, bg = tone_color(tone)
        self.setText(
            _("Quality: {glyph} {status}").format(
                glyph=TONE_GLYPH.get(tone, ""), status=status_word(measurement.status)
            )
        )
        assert measurement.health is not None
        self.setToolTip(health_summary(measurement.health))
        self.setStyleSheet(
            f"QToolButton {{ color: {fg}; background: {bg}; border: 1px solid {fg};"
            " border-radius: 3px; padding: 3px 8px; font-weight: 600; }"
        )
        self.setEnabled(True)


class OverviewDialog(QDialog):
    """The project overview as text (positions, spatial average, next steps)."""

    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(_("Project overview"))
        self.resize(760, 560)
        layout = QVBoxLayout(self)
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setPlainText(text)
        apply_report_font(self.text)
        layout.addWidget(self.text, 1)
        row = QHBoxLayout()
        row.addStretch(1)
        copy = QPushButton(_("Copy overview"))
        copy.clicked.connect(self._copy)
        row.addWidget(copy)
        close = QPushButton(_("Close"))
        close.clicked.connect(self.accept)
        row.addWidget(close)
        layout.addLayout(row)

    def _copy(self) -> None:
        QGuiApplication.clipboard().setText(self.text.toPlainText())


class WorkbenchWindow(QMainWindow):
    """One window: charts in the middle, measurements on the right, the
    inspector at the bottom on demand, the run status line below."""

    def __init__(self, *, restore_layout: bool = False) -> None:
        super().__init__()
        self.setWindowTitle(f"ReverbScope {__version__}")
        self.setWindowIcon(app_icon())
        self.setMinimumSize(960, 640)
        self.resize(1280, 800)
        self.setDockOptions(
            QMainWindow.DockOption.AnimatedDocks | QMainWindow.DockOption.AllowTabbedDocks
        )
        self._restore_layout = restore_layout
        self._settings = QSettings("ReverbScope", "ReverbScope")
        self._default_state: QByteArray | None = None

        self.document = WorkspaceDocument(self)
        self.controller = WorkspaceController(self.document, self)
        self.measurements = MeasurementController(self.document, self)
        self.link = ZoomLink(self)

        # --- the chart area -------------------------------------------------------
        self.splitter = QSplitter(Qt.Orientation.Vertical)
        self.splitter.setChildrenCollapsible(False)
        self.panels: list[PlotPanel] = []
        for kind in DEFAULT_KINDS:
            panel = PlotPanel(self.document, self.link, kind=kind)
            panel.set_comparison_provider(self.controller.comparison_result)
            panel.item_selected.connect(self._chart_item_selected)
            panel.status_message.connect(self._show_message)
            panel.canvas.installEventFilter(self)
            self.panels.append(panel)
            self.splitter.addWidget(panel)
        self._active_panel = 0
        self.setCentralWidget(self.splitter)

        # --- the measurement list -------------------------------------------------
        self.list_model = MeasurementListModel(self.document, self)
        self.tree = QTreeView()
        self.tree.setModel(self.list_model)
        style_tree(self.tree)
        self.tree.setSelectionMode(QTreeView.SelectionMode.SingleSelection)
        self.tree.doubleClicked.connect(self._tree_double_clicked)
        connect_selection(self.tree, self.document)
        list_widget = QWidget()
        list_layout = QVBoxLayout(list_widget)
        list_layout.setContentsMargins(4, 4, 4, 4)
        list_layout.setSpacing(4)
        list_layout.addWidget(self.tree, 1)
        self.list_hint = QLabel(_("No measurement loaded."))
        self.list_hint.setProperty("role", "hint")
        self.list_hint.setWordWrap(True)
        list_layout.addWidget(self.list_hint)
        list_buttons = QHBoxLayout()
        list_buttons.setSpacing(4)
        self.baseline_button = QToolButton()
        self.baseline_button.setText(_("Set as baseline"))
        self.baseline_button.setCheckable(True)
        self.baseline_button.clicked.connect(self.toggle_baseline)
        self.close_button = QToolButton()
        self.close_button.setText(_("Close"))
        self.close_button.clicked.connect(self.close_selected)
        list_buttons.addWidget(self.baseline_button)
        list_buttons.addWidget(self.close_button)
        list_buttons.addStretch(1)
        list_layout.addLayout(list_buttons)
        self.list_dock = QDockWidget(_("Measurements"), self)
        self.list_dock.setObjectName("measurements")
        self.list_dock.setWidget(list_widget)
        self.list_dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetClosable
        )
        self.list_dock.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea
        )
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.list_dock)

        # --- the inspector --------------------------------------------------------
        self.inspector = InspectorPanel()
        self.inspector.locate_requested.connect(self.locate)
        self.inspector.comparison_settings_changed.connect(self._same_gain_changed)
        self.inspector_dock = QDockWidget(_("Properties and diagnostics"), self)
        self.inspector_dock.setObjectName("inspector")
        self.inspector_dock.setWidget(self.inspector)
        self.inspector_dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetClosable
        )
        self.inspector_dock.setAllowedAreas(
            Qt.DockWidgetArea.BottomDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea
        )
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.inspector_dock)
        self.inspector_dock.hide()
        self._inspector_wanted = False
        self.inspector_dock.visibilityChanged.connect(self._inspector_visibility)

        # --- the status line ------------------------------------------------------
        self._status = QStatusBar()
        self.setStatusBar(self._status)
        self.run_status = RunStatusBar()
        self.run_status.stop_requested.connect(self.measurements.stop)
        self._status.addPermanentWidget(self.run_status)

        self._build_actions()
        self._build_menus()
        self._build_toolbar()

        # --- wiring ---------------------------------------------------------------
        self.document.selection_changed.connect(self._selection_changed)
        self.document.baseline_changed.connect(self._baseline_changed)
        self.document.measurement_added.connect(self._list_changed)
        self.document.measurement_removed.connect(self._list_changed)
        self.document.measurement_changed.connect(self._measurement_changed)
        self.document.project_changed.connect(self._project_changed)
        self.controller.message.connect(self._show_message)
        self.measurements.status_changed.connect(self._activity)
        self.measurements.failed.connect(self._job_failed)
        self.measurements.measurement_ready.connect(self._measurement_ready)

        # The colour scheme the window was last drawn in; "follow the system"
        # restyles when macOS or Windows switch to dark while it runs.
        self._scheme = color_scheme()
        QGuiApplication.styleHints().colorSchemeChanged.connect(self._follow_system_scheme)
        self._following_system = True

        self.resizeDocks([self.list_dock], [300], Qt.Orientation.Horizontal)
        self.resizeDocks([self.inspector_dock], [260], Qt.Orientation.Vertical)
        self._default_state = self.saveState()
        self._selection_changed(None)
        self._list_changed("")
        self._show_message(_("No measurement loaded."))
        if restore_layout:
            self._restore()

    # --- actions, menus, toolbar --------------------------------------------------

    def _build_actions(self) -> None:
        self.measure_action = QAction(_("&Measure..."), self)
        self.measure_action.setShortcut("Ctrl+M")
        self.measure_action.setToolTip(_("Play the sweep through an audio interface and record"))
        self.measure_action.triggered.connect(self.measure)
        self.import_action = QAction(_("&Import DAW Recording..."), self)
        self.import_action.setShortcut("Ctrl+I")
        self.import_action.setToolTip(_("Analyse a recording exported from a DAW"))
        self.import_action.triggered.connect(self.import_recording)
        self.open_action = QAction(_("&Open Session..."), self)
        self.open_action.setShortcut(QKeySequence.StandardKey.Open)
        self.open_action.triggered.connect(self.controller.choose_session)
        self.open_project_action = QAction(_("Open &Project..."), self)
        self.open_project_action.setShortcut("Ctrl+Shift+O")
        self.open_project_action.triggered.connect(self.controller.choose_project)
        self.new_project_action = QAction(_("&New Project..."), self)
        self.new_project_action.triggered.connect(self.controller.new_project)
        self.add_session_action = QAction(_("&Add Saved Session to Project..."), self)
        self.add_session_action.triggered.connect(self.controller.add_session_to_project)
        self.overview_action = QAction(_("Project &Overview..."), self)
        self.overview_action.triggered.connect(self.show_project_overview)
        self.measure_position_action = QAction(_("Measure a New &Position..."), self)
        self.measure_position_action.triggered.connect(self.measure_new_position)
        self.save_action = QAction(_("&Save Session..."), self)
        self.save_action.setShortcut(QKeySequence.StandardKey.Save)
        self.save_action.triggered.connect(self.save_selected)
        self.close_action = QAction(_("&Close Measurement"), self)
        self.close_action.setShortcut("Ctrl+W")
        self.close_action.triggered.connect(self.close_selected)
        self.export_csv_action = QAction(_("CSV &Tables..."), self)
        self.export_csv_action.triggered.connect(self.export_csv)
        self.export_png_action = QAction(_("Current Chart as &PNG..."), self)
        self.export_png_action.triggered.connect(self.export_png)
        self.copy_report_action = QAction(_("Copy &Report"), self)
        self.copy_report_action.triggered.connect(self.inspector.copy_report)
        self.save_comparison_action = QAction(_("Save &comparison.json..."), self)
        self.save_comparison_action.triggered.connect(self.save_comparison)
        self.settings_action = QAction(_("Se&ttings..."), self)
        self.settings_action.setShortcut("Ctrl+,")
        self.settings_action.triggered.connect(self.show_settings)
        self.quit_action = QAction(_("&Quit"), self)
        self.quit_action.setShortcut(QKeySequence.StandardKey.Quit)
        self.quit_action.triggered.connect(self.close)

        self.stop_action = QAction(_("&Stop Take"), self)
        self.stop_action.setShortcut("Esc")
        self.stop_action.setEnabled(False)
        self.stop_action.triggered.connect(self.measurements.stop)
        self.baseline_action = QAction(_("Set as &Baseline"), self)
        self.baseline_action.setShortcut("Ctrl+B")
        self.baseline_action.setCheckable(True)
        self.baseline_action.triggered.connect(self.toggle_baseline)

        self.single_action = QAction(_("&One chart"), self)
        self.single_action.setShortcut("Ctrl+1")
        self.single_action.setCheckable(True)
        self.dual_action = QAction(_("&Two charts"), self)
        self.dual_action.setShortcut("Ctrl+2")
        self.dual_action.setCheckable(True)
        layout_group = QActionGroup(self)
        layout_group.addAction(self.single_action)
        layout_group.addAction(self.dual_action)
        self.dual_action.setChecked(True)
        self.single_action.triggered.connect(self._single_chart)
        self.dual_action.triggered.connect(self._dual_chart)
        self.list_action = self.list_dock.toggleViewAction()
        self.list_action.setText(_("&Measurement list"))
        self.list_action.setShortcut("F9")
        self.inspector_action = QAction(_("&Properties and diagnostics"), self)
        self.inspector_action.setShortcut("F10")
        self.inspector_action.setCheckable(True)
        self.inspector_action.toggled.connect(self.set_inspector_visible)
        self.link_action = QAction(_("&Linked zoom"), self)
        self.link_action.setCheckable(True)
        self.link_action.setChecked(True)
        self.link_action.toggled.connect(self._set_linked)
        self.reset_layout_action = QAction(_("&Reset layout"), self)
        self.reset_layout_action.triggered.connect(self.reset_layout)

        self.guide_action = QAction(_("&User guide"), self)
        self.guide_action.triggered.connect(self._open_guide)
        self.report_action = QAction(_("&Environment Report for Bug Reports..."), self)
        self.report_action.triggered.connect(self.show_environment_report)
        self.about_action = QAction(_("&About ReverbScope"), self)
        self.about_action.triggered.connect(self._about)
        self.licenses_action = QAction(_("&Third-party licenses..."), self)
        self.licenses_action.triggered.connect(self._open_licenses)

    def _build_menus(self) -> None:
        bar = self.menuBar()
        file_menu = bar.addMenu(_("&File"))
        file_menu.addAction(self.measure_action)
        file_menu.addAction(self.import_action)
        file_menu.addSeparator()
        file_menu.addAction(self.open_action)
        self.recent_menu = file_menu.addMenu(_("Recent &Sessions"))
        self.recent_menu.aboutToShow.connect(self._fill_recent_sessions)
        file_menu.addAction(self.open_project_action)
        self.recent_projects_menu = file_menu.addMenu(_("Recent Pro&jects"))
        self.recent_projects_menu.aboutToShow.connect(self._fill_recent_projects)
        file_menu.addSeparator()
        file_menu.addAction(self.save_action)
        file_menu.addAction(self.close_action)
        export_menu = file_menu.addMenu(_("&Export"))
        export_menu.addAction(self.export_csv_action)
        export_menu.addAction(self.export_png_action)
        export_menu.addAction(self.copy_report_action)
        export_menu.addAction(self.save_comparison_action)
        file_menu.addSeparator()
        file_menu.addAction(self.settings_action)
        file_menu.addSeparator()
        file_menu.addAction(self.quit_action)

        measure_menu = bar.addMenu(_("&Measure"))
        measure_menu.addAction(self.measure_action)
        measure_menu.addAction(self.import_action)
        measure_menu.addSeparator()
        measure_menu.addAction(self.stop_action)
        measure_menu.addSeparator()
        measure_menu.addAction(self.baseline_action)

        project_menu = bar.addMenu(_("&Project"))
        project_menu.addAction(self.open_project_action)
        project_menu.addAction(self.new_project_action)
        project_menu.addSeparator()
        project_menu.addAction(self.measure_position_action)
        project_menu.addAction(self.add_session_action)
        project_menu.addAction(self.overview_action)

        view_menu = bar.addMenu(_("&View"))
        view_menu.addAction(self.single_action)
        view_menu.addAction(self.dual_action)
        view_menu.addSeparator()
        view_menu.addAction(self.list_action)
        view_menu.addAction(self.inspector_action)
        view_menu.addAction(self.link_action)
        view_menu.addSeparator()
        view_menu.addAction(self.reset_layout_action)

        from reverbscope.edition import is_developer

        self.developer_menu: QMenu | None = None
        if is_developer():
            self.developer_menu = bar.addMenu(_("&Developer"))
            inspector_action = QAction(_("Audio Device &Inspector..."), self)
            inspector_action.setShortcut("Ctrl+Shift+D")
            inspector_action.triggered.connect(self.show_device_inspector)
            folder_action = QAction(_("Open &Data Folder"), self)
            folder_action.triggered.connect(self._open_data_folder)
            self.developer_menu.addAction(inspector_action)
            self.developer_menu.addAction(folder_action)

        help_menu = bar.addMenu(_("&Help"))
        help_menu.addAction(self.guide_action)
        help_menu.addAction(self.report_action)
        help_menu.addSeparator()
        help_menu.addAction(self.about_action)
        help_menu.addAction(self.licenses_action)

    def _build_toolbar(self) -> None:
        self.toolbar = QToolBar(_("Main toolbar"))
        self.toolbar.setObjectName("main_toolbar")
        self.toolbar.setMovable(False)
        self.toolbar.setFloatable(False)
        self.toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.toolbar.setIconSize(self.toolbar.iconSize() * 0.75)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self.toolbar)
        self.toolbar.addAction(self.measure_action)
        self.toolbar.addAction(self.import_action)
        self.toolbar.addAction(self.open_action)
        self.toolbar.addAction(self.open_project_action)
        self.toolbar.addAction(self.save_action)
        self.toolbar.addSeparator()
        self.toolbar.addAction(self.baseline_action)
        self.toolbar.addSeparator()
        self.toolbar.addAction(self.single_action)
        self.toolbar.addAction(self.dual_action)
        spacer = QWidget()
        spacer.setSizePolicy(
            spacer.sizePolicy().horizontalPolicy().Expanding, spacer.sizePolicy().verticalPolicy()
        )
        self.toolbar.addWidget(spacer)
        self.quality_button = QualityButton()
        self.quality_button.clicked.connect(self._show_quality)
        self.toolbar.addWidget(self.quality_button)
        self.toolbar.addAction(self.inspector_action)
        # Shortcuts are listed in the menus; the toolbar keeps its text short.
        self.measure_action.setIconText(_("Measure"))
        self.import_action.setIconText(_("Import DAW recording"))
        self.open_action.setIconText(_("Open session"))
        self.save_action.setIconText(_("Save session"))
        self.open_project_action.setIconText(_("Project"))
        self.baseline_action.setIconText(_("Baseline"))
        self.single_action.setIconText(_("1 chart"))
        self.dual_action.setIconText(_("2 charts"))
        self.inspector_action.setIconText(_("Inspector"))

    # --- the chart area ------------------------------------------------------------

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802 - Qt override
        if event.type() == QEvent.Type.MouseButtonPress:
            for index, panel in enumerate(self.panels):
                if watched is panel.canvas:
                    self._active_panel = index
        return super().eventFilter(watched, event)

    def active_panel(self) -> PlotPanel:
        """The panel the user last clicked (the first one until then), among
        the visible panels."""
        panel = self.panels[self._active_panel]
        if panel.isVisible() or not self.panels[0].isVisible():
            return panel
        return self.panels[0]

    def _single_chart(self) -> None:
        self.set_dual(False)

    def _dual_chart(self) -> None:
        self.set_dual(True)

    def set_dual(self, dual: bool) -> None:
        self.panels[1].setVisible(dual)
        (self.dual_action if dual else self.single_action).setChecked(True)
        if not dual:
            self._active_panel = 0

    def is_dual(self) -> bool:
        return not self.panels[1].isHidden()

    def _set_linked(self, enabled: bool) -> None:
        self.link.enabled = enabled

    def locate(self, kind: str, target: object) -> None:
        """Show chart ``kind`` (in the panel that has it, else the active one)
        and highlight ``target`` (an index of the kind's items, or ``None``)."""
        keys = {plot_kind.key for plot_kind in PLOT_KINDS}
        if kind not in keys:
            return
        panel = next((p for p in self.panels if p.isVisible() and p.kind() == kind), None)
        if panel is None:
            panel = self.active_panel()
            panel.set_kind(kind)
        index = target if isinstance(target, int) else None
        panel.set_highlight(_highlight_name(kind), index)
        panel.raise_()

    def _chart_item_selected(self, name: str, index: int) -> None:
        kind = {"resonance": "frequency", "reflection": "reflections", "band": "decay"}.get(name)
        if kind is None:
            return
        for panel in self.panels:
            if panel.kind() == kind:
                panel.set_highlight(name, index)
        if self.document.selected() is not None:
            self.set_inspector_visible(True)
            self.inspector.show_item(kind, index)

    # --- the inspector --------------------------------------------------------------

    def set_inspector_visible(self, visible: bool) -> None:
        """The inspector shows when it is wanted and a measurement is selected."""
        self._inspector_wanted = visible
        shown = visible and self.document.selected() is not None
        if self.inspector_dock.isVisible() != shown:
            self.inspector_dock.setVisible(shown)
        self._sync_inspector_action()

    def _inspector_visibility(self, visible: bool) -> None:
        # The dock's own close button: the user does not want it any more.
        if not visible and self._inspector_wanted and self.document.selected() is not None:
            self._inspector_wanted = False
        self._sync_inspector_action()

    def _sync_inspector_action(self) -> None:
        checked = self._inspector_wanted
        if self.inspector_action.isChecked() != checked:
            self.inspector_action.blockSignals(True)
            self.inspector_action.setChecked(checked)
            self.inspector_action.blockSignals(False)

    def _show_quality(self) -> None:
        self.set_inspector_visible(True)
        self.inspector.show_tab("quality")

    def _tree_double_clicked(self, _index: object) -> None:
        if self.document.selected() is not None:
            self.set_inspector_visible(True)

    # --- document changes ----------------------------------------------------------

    def _selection_changed(self, measurement_id: object) -> None:
        measurement = self.document.get(measurement_id if isinstance(measurement_id, str) else None)
        self.quality_button.set_status(measurement)
        self.inspector.set_measurement(measurement)
        self._update_comparison()
        has = measurement is not None
        for action in (
            self.save_action,
            self.close_action,
            self.export_csv_action,
            self.copy_report_action,
            self.baseline_action,
        ):
            action.setEnabled(has)
        self.baseline_button.setEnabled(has)
        self.close_button.setEnabled(has)
        is_baseline = has and self.document.baseline_id() == measurement_id
        for toggle in (self.baseline_action, self.baseline_button):
            toggle.blockSignals(True)
            toggle.setChecked(is_baseline)
            toggle.blockSignals(False)
        if not has:
            if self.inspector_dock.isVisible():
                self.inspector_dock.hide()
        elif self._inspector_wanted and not self.inspector_dock.isVisible():
            self.inspector_dock.show()
        self._sync_inspector_action()
        self._update_title()

    def _baseline_changed(self, _measurement_id: object) -> None:
        self._selection_changed(self.document.selected_id())
        self._list_changed("")

    def _list_changed(self, _measurement_id: str) -> None:
        empty = len(self.document) == 0
        self.list_hint.setVisible(empty)
        self.export_png_action.setEnabled(not empty)
        self.save_comparison_action.setEnabled(self.controller.comparison() is not None)
        if empty:
            self._show_message(_("No measurement loaded."))
        else:
            self._show_message(_("{n} measurement(s) open.").format(n=len(self.document)))
        self._update_title()

    def _measurement_changed(self, measurement_id: str) -> None:
        if measurement_id == self.document.selected_id():
            self.inspector.set_measurement(self.document.get(measurement_id))
            self.quality_button.set_status(self.document.get(measurement_id))
        self._update_title()

    def _project_changed(self, path: object) -> None:
        has = path is not None
        self.add_session_action.setEnabled(has)
        self.overview_action.setEnabled(has)
        self._update_title()

    def _update_title(self) -> None:
        parts = [f"ReverbScope {__version__}"]
        if self.document.project is not None:
            parts.append(self.document.project_name or self.document.project.name)
        selected = self.document.selected()
        if selected is not None:
            name = selected.name()
            if selected.unsaved:
                name += " *"
            parts.append(name)
        self.setWindowTitle("  ·  ".join(parts))

    def _update_comparison(self) -> None:
        comparison = self.controller.comparison()
        baseline = self.document.baseline()
        candidate = self.document.candidate()
        self.inspector.set_comparison(
            baseline,
            candidate,
            None if comparison is None else comparison.result,
            None if comparison is None else comparison.verdict,
        )
        self.save_comparison_action.setEnabled(comparison is not None)
        for panel in self.panels:
            panel.refresh()

    def _same_gain_changed(self, same_gain: bool) -> None:
        self.controller.set_same_gain(same_gain)
        self._update_comparison()

    def toggle_baseline(self, *_args: object) -> None:
        selected = self.document.selected()
        if selected is None:
            return
        if self.document.baseline_id() == selected.id:
            self.document.set_baseline(None)
        else:
            self.document.set_baseline(selected.id)

    def close_selected(self) -> None:
        selected = self.document.selected()
        if selected is not None:
            self.controller.close_measurement(selected.id)

    def save_selected(self) -> None:
        self.controller.save()

    # --- jobs -----------------------------------------------------------------------

    def _activity(self, busy: bool, text: str, fraction: object, stoppable: bool) -> None:
        if busy:
            self.run_status.set_running(
                text, fraction if isinstance(fraction, float) else None, stoppable=stoppable
            )
        else:
            self.run_status.set_idle(text)
        self.stop_action.setEnabled(busy and stoppable)
        self.measure_action.setEnabled(not busy)
        self.import_action.setEnabled(not busy)
        self.measure_position_action.setEnabled(not busy)
        self._show_message(text)

    def _job_failed(self, message: str) -> None:
        error_box(self, _("Measurement failed"), message)

    def _measurement_ready(self, measurement_id: str) -> None:
        measurement = self.document.get(measurement_id)
        if measurement is None:
            return
        self._show_message(_("{name}: analysed.").format(name=measurement.name()))

    def measure(self) -> None:
        """The Standalone measurement dialog; its request starts a take."""
        if self.measurements.is_busy():
            return
        dialog = StandaloneMeasureDialog(
            self, profile=self._default_profile(), **self._position_defaults()
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        request = dialog.request()
        if request is not None:
            self.measurements.start_take(request)

    def import_recording(self) -> None:
        """The Universal DAW dialog; its request starts an analysis."""
        if self.measurements.is_busy():
            return
        dialog = DawAnalysisDialog(
            self, profile=self._default_profile(), **self._position_defaults()
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        request = dialog.request()
        if request is not None:
            self.measurements.start_analysis(request)

    def measure_new_position(self) -> None:
        if self.document.project is None:
            QMessageBox.information(
                self, _("Measure a new position"), _("Open or make a project first.")
            )
            return
        self.measure()

    def _default_profile(self) -> str:
        selected = self.document.selected()
        if selected is not None:
            return selected.profile
        profile = load_settings().default_profile
        return profile if profile in available_profiles() else "generic"

    def _position_defaults(self) -> dict[str, str]:
        """Room and position for the next take: the project's name and the next
        free label when a project is open, else the selected measurement's room."""
        project = self.document.project
        if project is not None:
            return {
                "room": self.document.project_name or project.name,
                "position": suggest_label(self.controller.position_labels()),
            }
        selected = self.document.selected()
        if selected is not None:
            return {"room": selected.session.room_name, "position": ""}
        return {}

    # --- export -----------------------------------------------------------------------

    def export_csv(self) -> None:
        from reverbscope.ui.export import export_csv_tables

        selected = self.document.selected()
        if selected is None:
            self._show_message(_("No measurement selected."))
            return
        start = str(selected.project or load_settings().output_dir or "")
        message = export_csv_tables(self, selected.result, start)
        if message:
            self._show_message(message)

    def export_png(self) -> None:
        message = self.active_panel().export_png()
        if message:
            self._show_message(message)

    def save_comparison(self) -> None:
        from reverbscope.io.session_store import save_comparison
        from reverbscope.ui.widgets import ask_save_path

        comparison = self.controller.comparison()
        if comparison is None:
            QMessageBox.information(
                self,
                _("Save comparison"),
                _("Set a baseline and select another measurement first."),
            )
            return
        target = ask_save_path(
            self, _("Save comparison.json"), "comparison.json", _("JSON files (*.json)")
        )
        if target is None:
            return
        try:
            written = save_comparison(target, comparison.result)
        except ReverbScopeError as exc:
            from reverbscope.i18n import localize

            QMessageBox.critical(self, _("Cannot save"), localize(str(exc)))
            return
        self._show_message(_("Wrote {path}").format(path=written))

    def show_project_overview(self) -> None:
        from reverbscope.cli.render import REPORT_CONSOLE, render_overview

        overview = self.controller.project_overview(self._default_profile())
        if overview is None:
            QMessageBox.information(self, _("Project overview"), _("Open or make a project first."))
            return
        OverviewDialog(render_overview(REPORT_CONSOLE, overview), self).exec()

    # --- recent ----------------------------------------------------------------------

    def _fill_recent_sessions(self) -> None:
        from reverbscope.io.recent import recent_session_paths

        self.recent_menu.clear()
        paths = recent_session_paths()
        if not paths:
            empty = self.recent_menu.addAction(_("No recent sessions yet."))
            empty.setEnabled(False)
            return
        for path in paths:
            action = self.recent_menu.addAction(str(path))
            action.setData(str(path))
            action.triggered.connect(self._open_recent)

    def _fill_recent_projects(self) -> None:
        from reverbscope.io.project_store import is_project
        from reverbscope.io.recent import recent_session_paths

        self.recent_projects_menu.clear()
        seen: list[Path] = []
        for path in recent_session_paths():
            parent = path.parent
            if is_project(parent) and parent not in seen:
                seen.append(parent)
        if not seen:
            empty = self.recent_projects_menu.addAction(_("No recent projects yet."))
            empty.setEnabled(False)
            return
        for project in seen:
            action = self.recent_projects_menu.addAction(str(project))
            action.setData(str(project))
            action.triggered.connect(self._open_recent_project)

    def _open_recent(self) -> None:
        action = self.sender()
        if isinstance(action, QAction) and action.data():
            self.controller.open_session(str(action.data()))

    def _open_recent_project(self) -> None:
        action = self.sender()
        if isinstance(action, QAction) and action.data():
            self.controller.open_project(Path(str(action.data())))

    # --- layout ---------------------------------------------------------------------

    def reset_layout(self) -> None:
        """The default arrangement: two charts, the list on the right, the
        inspector folded, the default window size."""
        if self._default_state is not None:
            self.restoreState(self._default_state)
        self.list_dock.show()
        self.inspector_dock.hide()
        self._inspector_wanted = False
        self._sync_inspector_action()
        self.set_dual(True)
        for panel, kind in zip(self.panels, DEFAULT_KINDS, strict=True):
            panel.set_kind(kind)
            panel.reset_zoom()
        self.splitter.setSizes([1, 1])
        self.resizeDocks([self.list_dock], [300], Qt.Orientation.Horizontal)
        self.resize(1280, 800)

    def _restore(self) -> None:
        geometry = self._settings.value(_SETTINGS_GEOMETRY)
        if isinstance(geometry, QByteArray) and not geometry.isEmpty():
            self.restoreGeometry(geometry)
        state = self._settings.value(_SETTINGS_STATE)
        if isinstance(state, QByteArray) and not state.isEmpty():
            self.restoreState(state)
        kinds = self._settings.value(_SETTINGS_KINDS)
        if isinstance(kinds, list):
            keys = {plot_kind.key for plot_kind in PLOT_KINDS}
            for panel, kind in zip(self.panels, kinds, strict=False):
                if isinstance(kind, str) and kind in keys:
                    panel.set_kind(kind)
        dual = self._settings.value(_SETTINGS_DUAL)
        if dual is not None:
            self.set_dual(str(dual).lower() in {"true", "1"})
        split = self._settings.value(_SETTINGS_SPLIT)
        if isinstance(split, list) and len(split) == 2:
            with contextlib.suppress(TypeError, ValueError):
                self.splitter.setSizes([int(v) for v in split])
        wanted = self._settings.value(_SETTINGS_INSPECTOR)
        self._inspector_wanted = str(wanted).lower() in {"true", "1"}
        # Docks are restored by restoreState; the inspector only shows with a selection.
        self.inspector_dock.hide()
        self._sync_inspector_action()

    def _save_layout(self) -> None:
        self._settings.setValue(_SETTINGS_GEOMETRY, self.saveGeometry())
        self._settings.setValue(_SETTINGS_STATE, self.saveState())
        self._settings.setValue(_SETTINGS_KINDS, [panel.kind() for panel in self.panels])
        self._settings.setValue(_SETTINGS_DUAL, self.is_dual())
        self._settings.setValue(_SETTINGS_SPLIT, self.splitter.sizes())
        self._settings.setValue(_SETTINGS_INSPECTOR, self._inspector_wanted)

    # --- lifecycle ----------------------------------------------------------------

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 - Qt override
        if not self.controller.ask_about_unsaved(self.document.unsaved_takes()):
            event.ignore()
            return
        if self._following_system:
            self._following_system = False
            QGuiApplication.styleHints().colorSchemeChanged.disconnect(self._follow_system_scheme)
        # A QThread destroyed while it runs aborts the process (Ctrl+Q during a
        # take or an analysis): stop the take and let the workers finish.
        self.measurements.shutdown()
        if self._restore_layout:
            self._save_layout()
        super().closeEvent(event)

    def restyle(self) -> None:
        """Apply the colour scheme now in force to the whole window."""
        app = QApplication.instance()
        if app is not None:
            apply_application_chrome(app)
        self._scheme = color_scheme()
        for panel in self.panels:
            panel.restyle()
        self.inspector.restyle()
        self.quality_button.set_status(self.document.selected())
        self.list_model.restyle()

    def _follow_system_scheme(self, *_scheme: object) -> None:
        if color_scheme() != self._scheme:
            self.restyle()

    def show_settings(self) -> None:
        from reverbscope.ui.settings_dialog import SettingsDialog

        if not SettingsDialog(self).exec():
            return
        if color_scheme() != self._scheme:
            self.restyle()

    def _show_message(self, text: str) -> None:
        self._status.showMessage(text)

    # --- help --------------------------------------------------------------------

    def show_device_inspector(self) -> None:
        from reverbscope.ui.dev_tools import DeviceInspector

        DeviceInspector(None, self).exec()

    def show_environment_report(self) -> None:
        from reverbscope.ui.dev_tools import EnvironmentReport

        EnvironmentReport(None, self).exec()

    def _open_guide(self) -> None:
        from reverbscope.edition import user_guide_url
        from reverbscope.i18n import current_locale

        QDesktopServices.openUrl(QUrl(user_guide_url(current_locale())))

    def _open_data_folder(self) -> None:
        from reverbscope.io.recent import reverbscope_home

        home = reverbscope_home()
        try:
            home.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            QMessageBox.warning(
                self,
                _("Cannot open the data folder"),
                _("cannot create folder {path}: {error}").format(
                    path=home, error=exc.strerror or str(exc)
                ),
            )
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(home)))

    def _about(self) -> None:
        about_box(self).exec()

    def _open_licenses(self) -> None:
        target = license_notice_path()
        if target is None:
            QMessageBox.information(
                self,
                _("Third-party licenses"),
                _(
                    "No THIRD_PARTY_LICENSES directory was found next to this "
                    "executable. See docs/DEPENDENCIES.md in the source tree."
                ),
            )
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))


def _highlight_name(kind: str) -> str:
    """The item a chart kind can highlight: a resonance marker, a reflection
    (also on the placement timeline) or a decay band."""
    return {
        "frequency": "resonance",
        "reflections": "reflection",
        "placement": "reflection",
        "decay": "band",
    }.get(kind, kind)
