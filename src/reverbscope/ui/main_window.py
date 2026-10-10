"""Main window: the workstation (docs/design/GUI_2_ARCHITECTURE.md §2).

Navigator | view bar and views | inspector, in one splitter, with the
measure strip under it. The window wires the workspace model to the
panels, the measurement pages to the model, and owns the actions that
cross them: open, save, the unsaved-take prompt and closing.
"""

from __future__ import annotations

import sys
import weakref
from collections.abc import Callable
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QAction, QCloseEvent, QDesktopServices, QGuiApplication, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QInputDialog,
    QMainWindow,
    QMessageBox,
    QSplitter,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from reverbscope import __version__
from reverbscope.errors import ReverbScopeError
from reverbscope.i18n import _, localize
from reverbscope.interpretation import available_profiles
from reverbscope.io.recent import remember_session
from reverbscope.io.session_store import SESSION_FILE, load_measurement, save_measurement
from reverbscope.settings import load_settings
from reverbscope.ui import ui_state
from reverbscope.ui.analysis_workspace import NUMBERED_VIEWS, AnalysisWorkspace, default_views
from reverbscope.ui.compare_view import ComparePage
from reverbscope.ui.inspector import Inspector
from reverbscope.ui.measure_strip import MeasureStrip
from reverbscope.ui.navigator import Navigator
from reverbscope.ui.pages import DawModePage, StandalonePage
from reverbscope.ui.plotkit import dispose_charts
from reverbscope.ui.project_view import ProjectPage
from reverbscope.ui.start_panel import StartPanel
from reverbscope.ui.state import MeasurementState
from reverbscope.ui.theme import apply_application_chrome, color_scheme
from reverbscope.ui.widgets import app_icon
from reverbscope.ui.workspace import WorkspaceModel, folder_key, usable_profile


def about_html() -> str:
    """About box body, translated when it is shown (not when this module loads)."""
    return _(
        "<b>ReverbScope {version}</b><br>"
        "An open-source, DAW-independent recording environment analyzer.<br><br>"
        "Licensed under the Apache License, Version 2.0.<br>"
        "This program uses Qt and PySide6 (Copyright The Qt Company Ltd. and contributors) "
        "under the GNU Lesser General Public License v3; the Qt libraries are loaded as "
        "separate shared libraries and may be replaced by interface-compatible versions. "
        "NumPy, SciPy, matplotlib, soundfile (libsndfile, LGPL-2.1) and sounddevice "
        "(PortAudio) are used under their respective licenses. Charts are drawn with "
        "pyqtgraph (MIT License, © 2012 University of North Carolina at Chapel Hill, "
        "Luke Campagnola).<br><br>"
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


def replace_session_box(parent: QWidget, directory: str) -> QMessageBox:
    """The chosen folder already holds a session. The safe button is the default: keep it."""
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Warning)
    box.setWindowTitle(_("Replace session?"))
    box.setText(_("{path} already holds a saved session. Replace it?").format(path=directory))
    box.addButton(_("Replace"), QMessageBox.ButtonRole.AcceptRole)
    cancel = box.addButton(_("Cancel"), QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(cancel)
    box.setEscapeButton(cancel)
    return box


def ask_replace_session(parent: QWidget, directory: str) -> bool:
    box = replace_session_box(parent, directory)
    box.exec()
    clicked = box.clickedButton()
    # By role, not by label, as in pages.ask_separate_clocks.
    return clicked is not None and box.buttonRole(clicked) == QMessageBox.ButtonRole.AcceptRole


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"ReverbScope {__version__}")
        self.setWindowIcon(app_icon())
        self.setMinimumSize(960, 640)
        self.resize(1366, 820)
        self.state = MeasurementState()
        # The default profile chosen in Settings, as the CLI reads it.
        default_profile = load_settings().default_profile
        if default_profile in available_profiles():
            self.state.profile = default_profile
        self.model = WorkspaceModel(self)

        self.home = StartPanel()
        self.daw = DawModePage(self.state)
        self.standalone = StandalonePage(self.state)
        views = default_views(self.model, self.state)
        self.workspace = AnalysisWorkspace(views)
        #: The workspace's stack: start panel, set-up pages, every view.
        self.stack = self.workspace.stack
        for page in (self.home, self.daw, self.standalone):
            self.workspace.add_page(page)
        self.views = self.workspace.views
        compare = self.views["compare"]
        project = self.views["project"]
        assert isinstance(compare, ComparePage) and isinstance(project, ProjectPage)
        self.compare = compare
        self.project = project
        self.navigator = Navigator(self.model)
        self.inspector = Inspector(self.model)
        self.strip = MeasureStrip(self.model, self.standalone, self.daw)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.addWidget(self.navigator)
        self.splitter.addWidget(self.workspace)
        self.splitter.addWidget(self.inspector)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setStretchFactor(2, 0)
        self.splitter.setSizes([230, 820, 300])
        central = QWidget()
        column = QVBoxLayout(central)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        column.addWidget(self.splitter, 1)
        column.addWidget(self.strip)
        self.setCentralWidget(central)

        self.home.choose_mode.connect(self.show_mode)
        self.home.open_session.connect(self.choose_session)
        self.home.open_recent.connect(self.open_session_path)
        self.home.compare_requested.connect(self.show_compare)
        self.home.open_project.connect(self.choose_project)
        self.navigator.open_session_requested.connect(self.choose_session)
        self.navigator.open_project_requested.connect(self.choose_project)
        self.navigator.measure_position_requested.connect(self._measure_at)
        self.navigator.remove_requested.connect(self.remove_entry)
        self.navigator.save_requested.connect(self._weak(lambda window, _key: window.save_take()))
        self.inspector.compare_requested.connect(self.show_compare)
        self.inspector.same_gain.toggled.connect(self.compare.same_gain.setChecked)
        self.compare.same_gain.toggled.connect(self.inspector.same_gain.setChecked)
        self.compare.open_pair.connect(self._open_pair)
        room: Any = self.views["room"]  # a RoomView
        room.checks_changed.connect(self.inspector.set_room_checks)
        self.project.measure_requested.connect(self._measure_position)
        self.project.open_session.connect(self._show_session)
        self.project.compare_requested.connect(self._compare_from_project)
        self.daw.analysis_finished.connect(self._take_finished)
        self.standalone.analysis_finished.connect(self._take_finished)
        self.daw.back.connect(self._leave_setup)
        self.standalone.back.connect(self._leave_setup)
        for page in (self.daw, self.standalone):
            page.before_take = self._weak(lambda window: window._before_take(), default=True)
        self.strip.mode_changed.connect(self._strip_mode)
        self.strip.setup_requested.connect(self.show_mode)
        self.strip.start_requested.connect(self._strip_start)
        self.workspace.view_chosen.connect(self.show_view)
        self.model.project_failed.connect(self._project_failed)
        self.model.current_changed.connect(self._current_changed)

        self._build_menus()
        self._status = QStatusBar()
        self.setStatusBar(self._status)
        self._place = ""
        #: The view shown when the first measurement opens (ui.ini).
        self._preferred_view = ui_state.read_text("workspace/view", "overview")
        if self._preferred_view not in self.views:
            self._preferred_view = "overview"
        self._restore_layout()
        # The colour scheme the window was last drawn in.
        self._scheme = color_scheme()
        # "Follow the system": macOS (Auto appearance) or Windows can turn
        # dark while ReverbScope runs. Widgets drawn after that took the dark
        # colours while the window kept the light style sheet.
        QGuiApplication.styleHints().colorSchemeChanged.connect(self._follow_system_scheme)
        self._following_system = True
        self._closed = False
        self._go_home()

    # --- menus ---------------------------------------------------------------------------

    def _build_menus(self) -> None:
        file_menu = self.menuBar().addMenu(_("&File"))
        new_action = QAction(_("&New Measurement"), self)
        new_action.setShortcut("Ctrl+N")
        new_action.triggered.connect(self.show_home)
        open_action = QAction(_("&Open Session..."), self)
        open_action.setShortcut("Ctrl+O")
        open_action.triggered.connect(self.choose_session)
        project_action = QAction(_("Open &Project..."), self)
        project_action.setShortcut("Ctrl+Shift+O")
        project_action.triggered.connect(self.choose_project)
        self.close_project_action = QAction(_("Close Project"), self)
        self.close_project_action.triggered.connect(self.close_project)
        self.save_action = QAction(_("&Save Session..."), self)
        self.save_action.setShortcut("Ctrl+S")
        self.save_action.triggered.connect(self.save_take)
        compare_action = QAction(_("&Compare Sessions..."), self)
        compare_action.setShortcut("Ctrl+Shift+C")
        compare_action.triggered.connect(self.show_compare)
        settings_action = QAction(_("&Settings..."), self)
        settings_action.setShortcut("Ctrl+,")
        settings_action.triggered.connect(self.show_settings)
        quit_action = QAction(_("&Quit"), self)
        quit_action.setShortcut("Ctrl+Q")
        quit_action.triggered.connect(self.close)
        for action in (new_action, open_action, project_action, self.close_project_action):
            file_menu.addAction(action)
        file_menu.addSeparator()
        file_menu.addAction(self.save_action)
        file_menu.addAction(compare_action)
        file_menu.addSeparator()
        file_menu.addAction(settings_action)
        file_menu.addSeparator()
        file_menu.addAction(quit_action)

        view_menu = self.menuBar().addMenu(_("&View"))
        self.view_actions: dict[str, QAction] = {}
        for view_id, view in self.views.items():
            action = QAction(view.title(), self)
            if view_id in NUMBERED_VIEWS:
                action.setShortcut(QKeySequence(f"Ctrl+{NUMBERED_VIEWS.index(view_id) + 1}"))
            elif view_id == "compare":
                action.setShortcut(QKeySequence("Ctrl+0"))
            action.triggered.connect(self._show_view_action(view_id))
            view_menu.addAction(action)
            self.view_actions[view_id] = action
        view_menu.addSeparator()
        start_action = QAction(_("Start panel"), self)
        start_action.triggered.connect(self._show_start)
        view_menu.addAction(start_action)
        reset_layout = QAction(_("Reset the layout"), self)
        reset_layout.triggered.connect(self.reset_layout)
        view_menu.addAction(reset_layout)

        measure_menu = self.menuBar().addMenu(_("&Measure"))
        daw_action = QAction(_("Universal DAW Mode"), self)
        daw_action.setShortcut("Ctrl+Shift+1")
        daw_action.triggered.connect(self._show_mode_action("universal_daw"))
        standalone_action = QAction(_("Standalone Mode"), self)
        standalone_action.setShortcut("Ctrl+Shift+2")
        standalone_action.triggered.connect(self._show_mode_action("standalone"))
        demo_action = QAction(_("Demo (no interface)"), self)
        demo_action.setShortcut("Ctrl+Shift+3")
        demo_action.triggered.connect(self._show_mode_action("demo"))
        measure_menu.addAction(daw_action)
        measure_menu.addAction(standalone_action)
        measure_menu.addAction(demo_action)

        from reverbscope.edition import is_developer

        self.developer_menu = None
        if is_developer():
            self.developer_menu = self.menuBar().addMenu(_("&Developer"))
            inspector_action = QAction(_("Audio Device &Inspector..."), self)
            inspector_action.setShortcut("Ctrl+Shift+D")
            inspector_action.triggered.connect(self.show_device_inspector)
            folder_action = QAction(_("Open &Data Folder"), self)
            folder_action.triggered.connect(self._open_data_folder)
            for action in (inspector_action, folder_action):
                self.developer_menu.addAction(action)

        help_menu = self.menuBar().addMenu(_("&Help"))
        self.getting_started_action = QAction(_("&Getting started"), self)
        self.getting_started_action.triggered.connect(self.show_getting_started)
        help_menu.addAction(self.getting_started_action)
        about_action = QAction(_("&About ReverbScope"), self)
        about_action.triggered.connect(self._about)
        licenses_action = QAction(_("&Third-party licenses..."), self)
        licenses_action.triggered.connect(self._open_licenses)
        self.report_action = QAction(_("&Environment Report for Bug Reports..."), self)
        self.report_action.triggered.connect(self.show_environment_report)
        help_menu.addAction(self.report_action)
        help_menu.addSeparator()
        help_menu.addAction(about_action)
        help_menu.addAction(licenses_action)

    def _weak(self, call: Callable[..., Any], default: Any = None) -> Callable[..., Any]:
        """``call(window, *args)`` holding the window by a weak reference only.

        A lambda or bound method of the window kept by its own children (a Qt
        connection, a page's hook) keeps a closed window alive for good.
        """
        window = weakref.ref(self)

        def run(*args: Any) -> Any:
            target = window()
            return default if target is None else call(target, *args)

        return run

    def _show_mode_action(self, mode: str) -> Callable[[], None]:
        """What a Measure-menu action runs: open ``mode``.

        A lambda capturing ``self`` made the window reachable from the menu
        action it owns, so it was never freed after closing: every closed
        window stayed alive, and each one made the application's style sheet
        slower to apply. This holds the window by a weak reference only.
        """
        window = weakref.ref(self)

        def show() -> None:
            target = window()
            if target is not None:
                target.show_mode(mode)

        return show

    def _show_view_action(self, view_id: str) -> Callable[[], None]:
        window = weakref.ref(self)

        def show() -> None:
            target = window()
            if target is not None:
                target.show_view(view_id)

        return show

    # --- layout state --------------------------------------------------------------------

    def _restore_layout(self) -> None:
        geometry = ui_state.read_bytes("window/geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)
        splitter = ui_state.read_bytes("window/splitter")
        if splitter is not None:
            self.splitter.restoreState(splitter)

    def _save_layout(self) -> None:
        ui_state.write("window/geometry", self.saveGeometry())
        ui_state.write("window/splitter", self.splitter.saveState())
        view = self.workspace.current_view_id() or self._preferred_view
        ui_state.write("workspace/view", view)
        self._save_selection()

    def _save_selection(self) -> None:
        if self.model.project_path is not None:
            ui_state.write_selection(self.model.project_path, self.model.selection_state())

    def reset_layout(self) -> None:
        self.splitter.setSizes([230, max(400, self.width() - 560), 300])

    # --- closing -------------------------------------------------------------------------

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 - Qt override
        if not self._closed and not self._leave_take():
            event.ignore()
            return
        if not self._closed:
            self._save_layout()
        self._closed = True
        # The colour-scheme signal belongs to the application and outlives this
        # window: a closed window that stays connected still restyles the whole
        # application on every system change (the chrome and every chart are
        # redrawn), and each further closed window makes that slower. Closing
        # twice is legal, and disconnecting what is no longer connected warns.
        if self._following_system:
            self._following_system = False
            QGuiApplication.styleHints().colorSchemeChanged.disconnect(self._follow_system_scheme)
        # A QThread destroyed while it runs aborts the process (Ctrl+Q during a
        # take, an analysis, a project load or a spectrogram): stop the take,
        # interrupt the rest and let every worker finish.
        self.standalone.shutdown_workers()
        self.daw.shutdown_workers()
        self.model.shutdown()
        for view in self.views.values():
            view.shutdown()
        dispose_charts(self)
        super().closeEvent(event)

    def _set_place(self, place: str) -> None:
        self._place = place
        self._status.showMessage(
            _("ReverbScope {version}  ·  {place}").format(version=__version__, place=place)
        )

    # --- the unsaved take ------------------------------------------------------------------

    def _unsaved_take_key(self) -> str:
        for entry in self.model.unsaved_entries():
            if entry.is_take:
                return entry.key
        return ""

    def _leave_take(self) -> bool:
        """True when the window may drop the unsaved take.

        A live Standalone take is the only copy of its recording until the
        session is saved; a new take, New Measurement, removing it from the
        list and closing the window ask first.
        """
        if not self._unsaved_take_key():
            return True
        return self._ask_about_unsaved_take()

    def _ask_about_unsaved_take(self) -> bool:
        box = QMessageBox(
            QMessageBox.Icon.Question,
            _("Unsaved measurement"),
            _(
                "This measurement has not been saved. Its recording exists only in "
                "memory and is lost if you continue."
            ),
            parent=self,
        )
        save = box.addButton(_("Save Session..."), QMessageBox.ButtonRole.AcceptRole)
        discard = box.addButton(_("Discard"), QMessageBox.ButtonRole.DestructiveRole)
        cancel = box.addButton(_("Cancel"), QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(save)
        box.setEscapeButton(cancel)
        box.exec()
        clicked = box.clickedButton()
        if clicked is save:
            # The folder chooser may be cancelled or the save may fail: the
            # take is let go only once it is on disk.
            self.save_take()
            return not self._unsaved_take_key()
        if clicked is discard:
            self._discard_take()
            return True
        return False

    def _discard_take(self) -> None:
        key = self._unsaved_take_key()
        if key:
            self.model.remove(key)
        self.state.unsaved_take = False

    def _before_take(self) -> bool:
        """A new take or analysis is about to replace the take on screen."""
        return self._leave_take()

    # --- starting over -------------------------------------------------------------------

    def show_home(self) -> None:
        """New Measurement: the start panel; asks first when a live take is unsaved."""
        if self._leave_take():
            self._go_home()

    def _go_home(self) -> None:
        if self.standalone.is_busy():
            # The page stays alive behind the start panel: stop the sweep, as
            # leaving the page always did.
            self.standalone.stop_measurement()
        for entry in self.model.entries():
            if entry.is_take:
                self.model.remove(entry.key)
        self.state.reset()
        self.daw.clear_recording()
        self._show_start()

    def _show_start(self) -> None:
        self.home.refresh_recent()
        self.home.show_walkthrough(not load_settings().walkthrough_dismissed)
        self.stack.setCurrentWidget(self.home)
        self._set_place(_("Start"))

    # --- views ---------------------------------------------------------------------------

    def show_view(self, view_id: str) -> None:
        view = self.workspace.show_view(view_id)
        self._preferred_view = view_id
        self._set_place(view.title())

    def current_view_id(self) -> str:
        return self.workspace.current_view_id()

    def _current_changed(self, key: str) -> None:
        """A measurement became current: leave the start panel for the views."""
        if key and self.stack.currentWidget() is self.home:
            self.show_view(self._preferred_view)

    def show_results(self) -> None:
        """The view the user last read, for the current measurement."""
        self.show_view(self._preferred_view)

    # --- opening ---------------------------------------------------------------------------

    def choose_session(self) -> None:
        path, _filter = QFileDialog.getOpenFileName(
            self,
            _("Open session"),
            "",
            _("Session files (session.json);;JSON files (*.json);;All files (*)"),
        )
        if path:
            self.open_session_path(path)

    def open_session_path(self, path: str | Path) -> bool:
        """Open a saved session into the list and make it current.

        It is added, not swapped in: the take and everything else open stay.
        """
        try:
            loaded = load_measurement(path)
        except ReverbScopeError as exc:
            QMessageBox.critical(self, _("Cannot open session"), localize(str(exc)))
            return False
        profile = usable_profile(loaded.session)
        self.model.add_session(
            loaded.directory,
            loaded.session,
            loaded.result,
            profile=profile,
        )
        remember_session(loaded.directory)
        self.show_view(
            self._preferred_view
            if self.stack.currentWidget() in (self.home, self.daw, self.standalone)
            else (self.current_view_id() or self._preferred_view)
        )
        return True

    def _show_session(self, path: str) -> None:
        """A row of the project view: select it, or open it when it is not in the list."""
        key = folder_key(path)
        if self.model.entry(key) is not None:
            self.model.set_current(key)
            self.show_view("overview")
            return
        self.open_session_path(path)

    def _open_pair(self, baseline: str, candidate: str) -> None:
        """Two sessions picked in Compare: open both, compare them."""
        if not (self.open_session_path(baseline) and self.open_session_path(candidate)):
            return
        self.model.set_baseline(folder_key(baseline))
        self.model.set_current(folder_key(candidate))
        self.show_view("compare")

    def choose_project(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, _("Open project folder"))
        if directory:
            self.show_project(Path(directory))

    def show_project(self, path: str | Path | None = None) -> None:
        """The project view: for ``path`` (opened, or offered to be made), or
        the project already open, read again."""
        if path is not None:
            self._save_selection()
            if not self.project.open_path(Path(path)):
                return
        elif self.model.project_path is not None:
            self._save_selection()
            self.project.reload()
        self.show_view("project")

    def close_project(self) -> None:
        self._save_selection()
        self.model.close_project()

    def _project_failed(self, message: str) -> None:
        QMessageBox.critical(self, _("Cannot open project"), message)

    def _measure_position(self, position: str, mode: str) -> None:
        """Measure ``position`` of the open project with ``mode``."""
        self._prepare_position(position)
        self.show_mode(mode)

    def _measure_at(self, position: str) -> None:
        """A position row's menu: measure there with the strip's mode."""
        self._prepare_position(position)
        self.model.add_position(position)
        self.show_mode(self.strip.current_mode())

    def _prepare_position(self, position: str) -> None:
        """The next take is of ``position`` in the open project, in its room."""
        self.strip.set_position(position)
        project = self.model.project
        name = project.name if project is not None else ""
        for page in (self.daw, self.standalone):
            page.position.setText(position)
            if name and not page.room.text():
                page.room.setText(name)

    def _compare_from_project(self, baseline: str, candidate: str) -> None:
        self.model.set_baseline(folder_key(baseline))
        self.model.set_current(folder_key(candidate))
        self.show_compare()

    def show_compare(self) -> None:
        selected = self.home.browser.selected_pair()
        if selected is not None:
            self.compare.set_paths(*selected)
        self.compare.browser.refresh_recent()
        self.show_view("compare")

    # --- measuring -----------------------------------------------------------------------

    def show_mode(self, mode: str) -> None:
        if mode in ("demo", "standalone") and self.standalone.is_busy():
            # Ctrl+Shift+2 / 3 while a take or its analysis runs: switching the
            # backend under it would show the demo banner over a real sweep (or
            # the reverse). The page is shown as it is.
            self.stack.setCurrentWidget(self.standalone)
            self._set_place(
                _("Demo (no interface)") if self.standalone.demo_mode else _("Standalone Mode")
            )
            return
        self.strip.set_mode(mode)
        self._apply_mode(mode)
        if mode == "universal_daw":
            self.stack.setCurrentWidget(self.daw)
            self._set_place(_("Universal DAW Mode"))
        else:
            self.stack.setCurrentWidget(self.standalone)
            self._set_place(_("Demo (no interface)") if mode == "demo" else _("Standalone Mode"))

    def _apply_mode(self, mode: str) -> None:
        if mode == "universal_daw":
            self.state.mode = mode
            return
        self.state.mode = "standalone"
        demo = mode == "demo"
        if self.standalone.demo_mode != demo or not self.standalone.input_device.count():
            self.standalone.demo_mode = demo
            self.standalone.refresh_devices()

    def _strip_mode(self, mode: str) -> None:
        if not self.standalone.is_busy():
            self._apply_mode(mode)

    def _strip_start(self, mode: str) -> None:
        if mode == "universal_daw":
            self.show_mode(mode)
            return
        self._apply_mode(mode)
        self.standalone.start_measurement()

    def _leave_setup(self) -> None:
        """Back on a set-up page: the view the user came from, or the start panel."""
        if self.model.current() is not None:
            self.show_view(self._preferred_view)
        else:
            self._show_start()

    def _take_finished(self) -> None:
        """A take or a DAW analysis is done: it joins the list as the current entry."""
        result = self.state.result
        if result is None:
            return
        session = self.state.session
        # The position the take was started at, not what the strip shows now.
        position = session.measurement_position.strip() or self.strip.position.currentText().strip()
        self.model.add_take(
            session,
            result,
            list(self.state.findings),
            self.state.findings_problem,
            self.state.profile,
            unsaved=self.state.unsaved_take,
            synthetic=session.mode == "demo",
            position=position,
        )
        if self.model.project_path is not None and position:
            self.model.add_position(position)
        if self.stack.currentWidget() in (self.home, self.daw, self.standalone):
            self.show_view("overview")

    # --- saving --------------------------------------------------------------------------

    def _take_entry_key(self) -> str:
        current = self.model.current()
        if current is not None and current.is_take:
            return current.key
        for entry in self.model.entries():
            if entry.is_take:
                return entry.key
        return ""

    def save_take(self) -> bool:
        """Save the take (the measurement made in this window) as a session.

        Into the open project, in a folder named after its position, which
        lists it under that position; otherwise into a folder the user picks.
        """
        key = self._take_entry_key()
        entry = self.model.entry(key) if key else None
        if entry is None or entry.result is None or self.state.result is not entry.result:
            QMessageBox.information(
                self,
                _("Save Session"),
                _(
                    "Only a measurement made in this window can be saved; opened sessions "
                    "are already on disk."
                ),
            )
            return False
        project = self.model.project_path
        position = entry.position or self.state.session.measurement_position.strip()
        if project is not None:
            name, ok = QInputDialog.getText(
                self,
                _("Save into the project"),
                _("Folder name inside {project}").format(project=project),
                text=suggested_folder(project, position),
            )
            if not ok or not name.strip():
                return False
            target = project / name.strip()
            if (target / SESSION_FILE).exists() and not ask_replace_session(self, str(target)):
                return False
        else:
            directory = QFileDialog.getExistingDirectory(
                self, _("Choose a folder for the session"), load_settings().output_dir
            )
            if not directory:
                return False
            target = Path(directory)
            # The dialog opens at the default output folder: accepting it twice
            # as offered would replace the first session without a word.
            if (target / SESSION_FILE).exists() and not ask_replace_session(self, directory):
                return False
        return self.save_to(target, key=key)

    def save_to(self, directory: Path, *, key: str = "") -> bool:
        key = key or self._take_entry_key()
        result = self.state.result
        if result is None or not key:
            return False
        try:
            # A live take has no file yet: it is written with the rest of the
            # session, so a failed save cannot overwrite the previous take.
            unsaved = self.state.recording if self.state.recording_path is None else None
            session_path = save_measurement(
                directory, self.state.session, result, recording=unsaved
            )
            if unsaved is not None:
                self.state.session.recording_path = str(directory / "recording.wav")
        except (ReverbScopeError, OSError) as exc:
            QMessageBox.critical(self, _("Cannot save session"), localize(str(exc)))
            return False
        remember_session(directory)
        self.state.unsaved_take = False
        entry = self.model.entry(key)
        position = entry.position if entry is not None else ""
        self.model.mark_saved(key, directory, position=position)
        self._status.showMessage(_("Session saved to {path}").format(path=session_path.parent))
        project = self.model.project_path
        if project is not None:
            self._add_to_project(project, directory, position or "A")
        return True

    def _add_to_project(self, project: Path, directory: Path, position: str) -> None:
        from reverbscope.io.project_store import add_session

        try:
            listed = add_session(project, directory, position=position)
        except (ReverbScopeError, OSError) as exc:
            QMessageBox.warning(
                self,
                _("Saved, but not added to the project"),
                _(
                    "The session is saved in {path}, but could not be listed in the project: "
                    "{error}"
                ).format(path=directory, error=localize(str(exc))),
            )
            return
        self._status.showMessage(
            _(
                "Session saved to {path} and listed in project {project} under position {label}"
            ).format(path=directory, project=listed.name or project.name, label=position)
        )
        self._save_selection()
        self.model.reload_project()

    def remove_entry(self, key: str) -> None:
        entry = self.model.entry(key)
        if entry is None:
            return
        if entry.unsaved and not self._leave_take():
            return
        self.model.remove(key)

    def show_getting_started(self) -> None:
        """The start panel with the first-measurement card, and the card stays from now on."""
        import contextlib
        from dataclasses import replace

        from reverbscope.settings import save_settings

        with contextlib.suppress(ReverbScopeError, OSError):
            save_settings(replace(load_settings(), walkthrough_dismissed=False))
        self._show_start()
        self.home.restore_walkthrough()

    def show_settings(self) -> None:
        from reverbscope.ui.settings_dialog import SettingsDialog

        before = load_settings()
        if not SettingsDialog(self).exec():
            return
        if color_scheme() != self._scheme:
            self.restyle()
        settings = load_settings()
        profile = settings.default_profile
        if profile != before.default_profile and profile in available_profiles():
            # A new default profile applies now, as the output folder does.
            # Only the combos: a running take keeps the profile it started with.
            for combo in (self.daw.profile, self.standalone.profile):
                combo.setCurrentIndex(max(combo.findData(profile), 0))
        if settings.audio_backend != before.audio_backend and not self.standalone.is_busy():
            # The Standalone page lists the new backend's devices: a take
            # would otherwise open that backend's device of the number
            # chosen from the old list. A running take keeps its list, and
            # the page makes it again before the next one.
            self.standalone.refresh_devices()

    def restyle(self) -> None:
        """Apply the colour scheme now in force to the whole window.

        The application style sheet and palette reach every widget; the
        finding cards, chips, table colours and charts keep the colours they
        were drawn with, so they are drawn again. Without that a switch to
        Dark left pale cards under light text, and white charts.
        """
        app = QApplication.instance()
        if app is not None:
            apply_application_chrome(app)
        self._scheme = color_scheme()
        for view in self.views.values():
            view.restyle()
        self.navigator.rebuild()
        self.inspector.refresh()
        for page in (self.daw, self.standalone):
            page.placement.redraw()

    def _follow_system_scheme(self, *_scheme: object) -> None:
        # A theme chosen in Settings (or REVERBSCOPE_COLOR_SCHEME) does not
        # follow the system, and its scheme does not change here.
        if color_scheme() != self._scheme:
            self.restyle()

    def _tools_backend(self) -> str | None:
        """The backend the device inspector and the environment report describe.

        The fake one only on the Demo page itself: the page keeps its demo
        flag after a take, and a bug report sent from Results or Compare
        must describe the user's real interface.
        """
        on_demo = self.stack.currentWidget() is self.standalone and self.standalone.demo_mode
        return "fake" if on_demo else None

    def show_device_inspector(self) -> None:
        from reverbscope.ui.dev_tools import DeviceInspector

        DeviceInspector(self._tools_backend(), self).exec()

    def show_environment_report(self) -> None:
        from reverbscope.ui.dev_tools import EnvironmentReport

        EnvironmentReport(self._tools_backend(), self).exec()

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


def suggested_folder(project: Path, position: str) -> str:
    """``<position>-<n>``: the next free folder name for the position."""
    stem = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in position) or "take"
    n = 1
    while (project / f"{stem}-{n}").exists():
        n += 1
    return f"{stem}-{n}"


def license_notice_path() -> Path | None:
    """Directory or file the About/Help menus should open for third-party texts."""
    candidates: list[Path] = []
    if getattr(sys, "frozen", False):
        exe = Path(sys.executable).resolve().parent
        candidates.extend(
            [
                exe / "THIRD_PARTY_LICENSES",
                exe.parent / "Resources" / "THIRD_PARTY_LICENSES",
            ]
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
