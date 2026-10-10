"""Main window: the workspace frame around the pages.

Left, the navigation (pages, the open project's positions and sessions,
recent sessions); top, the context bar with the page's title and its main
actions; centre, the page; right, the details pane; bottom, the status
line with the real take progress and Stop. Pages keep their widgets and
their data when another page is shown: only New Measurement and Open
Session reset the measurement state.
"""

from __future__ import annotations

import sys
import weakref
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QAction, QCloseEvent, QDesktopServices, QGuiApplication, QResizeEvent
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QMainWindow,
    QMessageBox,
    QSplitter,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from reverbscope import __version__
from reverbscope.errors import ReverbScopeError
from reverbscope.i18n import _, localize
from reverbscope.interpretation import available_profiles
from reverbscope.io.recent import remember_session
from reverbscope.io.session_store import load_measurement
from reverbscope.settings import load_settings
from reverbscope.ui.compare_view import ComparePage
from reverbscope.ui.daw_page import STEP_ANALYSE, DawModePage
from reverbscope.ui.home_page import HomePage
from reverbscope.ui.project_view import ProjectPage
from reverbscope.ui.results_page import ResultsPage
from reverbscope.ui.standalone_page import STEP_DIMENSIONS, StandalonePage
from reverbscope.ui.state import MeasurementState
from reverbscope.ui.theme import apply_application_chrome, color_scheme
from reverbscope.ui.widgets import app_icon
from reverbscope.ui.workspace import (
    NAV_COMPARE,
    NAV_DAW,
    NAV_DEMO,
    NAV_HOME,
    NAV_PROJECT,
    NAV_RESULTS,
    NAV_STANDALONE,
    ContextBar,
    DetailPane,
    NavigationPane,
    RunStatusBar,
)

#: Below this window width the details pane folds away by itself (it comes
#: back with the View menu); the navigation stays.
NARROW_WIDTH = 1180


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


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"ReverbScope {__version__}")
        self.setWindowIcon(app_icon())
        self.setMinimumSize(960, 640)
        self.resize(1280, 800)
        self.state = MeasurementState()
        # The default profile chosen in Settings, as the CLI reads it.
        default_profile = load_settings().default_profile
        if default_profile in available_profiles():
            self.state.profile = default_profile

        # --- the frame ------------------------------------------------------------
        self.nav = NavigationPane()
        self.context_bar = ContextBar()
        self.details = DetailPane()
        self.stack = QStackedWidget()
        centre = QWidget()
        centre_layout = QVBoxLayout(centre)
        centre_layout.setContentsMargins(0, 0, 0, 0)
        centre_layout.setSpacing(0)
        centre_layout.addWidget(self.context_bar)
        centre_layout.addWidget(self.stack, 1)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.addWidget(self.nav)
        self.splitter.addWidget(centre)
        self.splitter.addWidget(self.details)
        self.splitter.setCollapsible(0, True)
        self.splitter.setCollapsible(1, False)
        self.splitter.setCollapsible(2, True)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setStretchFactor(2, 0)
        self.splitter.setSizes([230, 760, 290])
        self.setCentralWidget(self.splitter)
        self._details_wanted = True
        self._details_auto_hidden = False

        # --- the pages ------------------------------------------------------------
        self.home = HomePage()
        self.daw = DawModePage(self.state)
        self.standalone = StandalonePage(self.state)
        self.results = ResultsPage(self.state)
        self.compare = ComparePage()
        self.project = ProjectPage(self.state)
        for page in (
            self.home,
            self.daw,
            self.standalone,
            self.results,
            self.compare,
            self.project,
        ):
            self.stack.addWidget(page)
        for page in (self.daw, self.standalone, self.results, self.compare, self.project):
            self.context_bar.add_actions(page.context_actions)
            self.details.add_detail(page.detail)

        self.home.choose_mode.connect(self.show_mode)
        self.home.open_session.connect(self.choose_session)
        self.home.open_recent.connect(self.open_session_path)
        self.home.compare_requested.connect(self.show_compare)
        self.home.open_project.connect(self.choose_project)
        self.home.open_project_path.connect(self.show_project)
        self.project.back.connect(self.show_start)
        self.project.measure_requested.connect(self._measure_position)
        self.project.open_session.connect(self.open_session_path)
        self.project.compare_requested.connect(self._compare_from_project)
        self.project.changed.connect(self._update_project_nav)
        self.results.project_requested.connect(self.show_project)
        self.results.compare_requested.connect(self._compare_current)
        self.results.settings_requested.connect(self._back_to_dimensions)
        self.results.context_changed.connect(self._results_context)
        self.results.report_toggled.connect(self._report_toggled)
        self.daw.analysis_finished.connect(self.show_results)
        self.standalone.analysis_finished.connect(self.show_results)
        self.daw.back.connect(self.show_start)
        self.standalone.back.connect(self.show_start)
        self.daw.activity_changed.connect(self._on_activity)
        self.standalone.activity_changed.connect(self._on_activity)
        self.daw.step_changed.connect(self._step_changed)
        self.standalone.step_changed.connect(self._step_changed)
        self.results.new_measurement.connect(self.show_home)
        self.compare.back.connect(self._leave_compare)
        self.compare.open_session.connect(self.open_session_path)
        self.compare.context_changed.connect(self._compare_context)
        self.nav.page_requested.connect(self._navigate)
        self.nav.session_requested.connect(self.open_session_path)
        self.nav.position_requested.connect(self._show_position)
        self.details.closed.connect(self._hide_details)

        # --- the status line ------------------------------------------------------
        self._status = QStatusBar()
        self.setStatusBar(self._status)
        self.run_status = RunStatusBar()
        self.run_status.stop_requested.connect(self.standalone.stop_measurement)
        self._status.addPermanentWidget(self.run_status)
        self._place = ""

        self._build_menus()
        # The page Compare was opened from, and its status-bar place: Back
        # returns there. Going Home instead reset the state, so an unsaved
        # result (the only copy of a live take) was gone.
        self._before_compare: tuple[QWidget, str] = (self.home, "")
        # The colour scheme the window was last drawn in.
        self._scheme = color_scheme()
        # "Follow the system": macOS (Auto appearance) or Windows can turn
        # dark while ReverbScope runs. Widgets drawn after that took the dark
        # colours while the window kept the light style sheet.
        QGuiApplication.styleHints().colorSchemeChanged.connect(self._follow_system_scheme)
        self._following_system = True
        self._go_home()

    # --- menus ------------------------------------------------------------------------

    def _build_menus(self) -> None:
        file_menu = self.menuBar().addMenu(_("&File"))
        new_action = QAction(_("&New Measurement"), self)
        new_action.setShortcut("Ctrl+N")
        new_action.triggered.connect(self.show_home)
        open_action = QAction(_("&Open Session..."), self)
        open_action.setShortcut("Ctrl+O")
        open_action.triggered.connect(self.choose_session)
        compare_action = QAction(_("&Compare Sessions..."), self)
        compare_action.setShortcut("Ctrl+Shift+C")
        compare_action.triggered.connect(self.show_compare)
        project_action = QAction(_("Open &Project..."), self)
        project_action.setShortcut("Ctrl+Shift+O")
        project_action.triggered.connect(self.choose_project)
        settings_action = QAction(_("&Settings..."), self)
        settings_action.setShortcut("Ctrl+,")
        settings_action.triggered.connect(self.show_settings)
        quit_action = QAction(_("&Quit"), self)
        quit_action.setShortcut("Ctrl+Q")
        quit_action.triggered.connect(self.close)
        file_menu.addAction(new_action)
        file_menu.addAction(open_action)
        file_menu.addAction(compare_action)
        file_menu.addAction(project_action)
        file_menu.addSeparator()
        file_menu.addAction(settings_action)
        file_menu.addSeparator()
        file_menu.addAction(quit_action)

        measure_menu = self.menuBar().addMenu(_("&Measure"))
        daw_action = QAction(_("Universal DAW Mode"), self)
        daw_action.setShortcut("Ctrl+1")
        daw_action.triggered.connect(self._show_mode_action("universal_daw"))
        standalone_action = QAction(_("Standalone Mode"), self)
        standalone_action.setShortcut("Ctrl+2")
        standalone_action.triggered.connect(self._show_mode_action("standalone"))
        demo_action = QAction(_("Demo (no interface)"), self)
        demo_action.setShortcut("Ctrl+3")
        demo_action.triggered.connect(self._show_mode_action("demo"))
        measure_menu.addAction(daw_action)
        measure_menu.addAction(standalone_action)
        measure_menu.addAction(demo_action)

        view_menu = self.menuBar().addMenu(_("&View"))
        self.nav_action = QAction(_("&Navigation pane"), self)
        self.nav_action.setCheckable(True)
        self.nav_action.setChecked(True)
        self.nav_action.setShortcut("F9")
        self.nav_action.toggled.connect(self.nav.setVisible)
        self.details_action = QAction(_("&Details pane"), self)
        self.details_action.setCheckable(True)
        self.details_action.setChecked(True)
        self.details_action.setShortcut("F10")
        self.details_action.toggled.connect(self.set_details_visible)
        results_action = QAction(_("&Results"), self)
        results_action.setShortcut("Ctrl+4")
        results_action.triggered.connect(self._show_results_from_menu)
        view_menu.addAction(self.nav_action)
        view_menu.addAction(self.details_action)
        view_menu.addSeparator()
        view_menu.addAction(results_action)

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

    # --- the frame ------------------------------------------------------------------

    def _hide_details(self) -> None:
        self.set_details_visible(False)

    def _show_results_from_menu(self) -> None:
        self._navigate(NAV_RESULTS)

    def _step_changed(self, _index: int) -> None:
        self._mode_context()

    def set_details_visible(self, visible: bool) -> None:
        self._details_wanted = visible
        self._details_auto_hidden = False
        self.details.setVisible(visible)
        if self.details_action.isChecked() != visible:
            self.details_action.blockSignals(True)
            self.details_action.setChecked(visible)
            self.details_action.blockSignals(False)

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802 - Qt override
        super().resizeEvent(event)
        narrow = event.size().width() < NARROW_WIDTH
        # ``isHidden`` rather than ``isVisible``: the first resize comes before
        # the window is shown, and a window opened small must open folded.
        if narrow and self._details_wanted and not self.details.isHidden():
            self.details.hide()
            self._details_auto_hidden = True
        elif not narrow and self._details_auto_hidden and self._details_wanted:
            self.details.show()
            self._details_auto_hidden = False

    def _show_page(self, page: QWidget, place: str, nav_key: str | None) -> None:
        self.stack.setCurrentWidget(page)
        self._set_place(place)
        self.context_bar.show_actions(getattr(page, "context_actions", None))
        self.details.show_detail(getattr(page, "detail", None))
        # Enable the Results entry before selecting it: a disabled item cannot
        # become current, and the highlight would stay on the previous page.
        self._update_nav_state()
        if nav_key is not None:
            self.nav.set_current_page(nav_key)

    def _set_place(self, place: str) -> None:
        self._place = place
        self._status.showMessage(
            _("ReverbScope {version}  ·  {place}").format(version=__version__, place=place)
        )

    def _update_nav_state(self) -> None:
        session = self.state.session
        from reverbscope.demo import localize_demo_name

        title = localize_demo_name(session.mode, session.room_name) if self.state.result else ""
        self.nav.set_result_available(self.state.result is not None, title)

    def _update_project_nav(self) -> None:
        overview = self.project.overview
        if overview is None or self.project.path is None:
            self.nav.set_project(None)
            return
        positions = [
            (
                position.label,
                [(Path(take.directory).name, take.directory) for take in position.sessions],
            )
            for position in overview.positions
        ]
        if overview.unlisted:
            positions.append(
                ("", [(Path(take.directory).name, take.directory) for take in overview.unlisted])
            )
        self.nav.set_project(
            overview.name or self.project.path.name, positions, self.project.current_position()
        )

    def _navigate(self, key: str) -> None:
        if key == NAV_HOME:
            self.show_start()
        elif key in (NAV_DAW, NAV_STANDALONE, NAV_DEMO):
            self.show_mode(key)
        elif key == NAV_RESULTS:
            if self.state.result is not None:
                self.show_results()
        elif key == NAV_COMPARE:
            self.show_compare()
        elif key == NAV_PROJECT:
            if self.project.path is not None:
                self.show_project()
            else:
                self.choose_project()

    def _on_activity(self, busy: bool, text: str, fraction: object, stoppable: bool) -> None:
        if busy:
            self.run_status.set_running(
                text, fraction if isinstance(fraction, float) else None, stoppable=stoppable
            )
        else:
            self.run_status.set_idle(text)

    def _mode_context(self) -> None:
        current = self.stack.currentWidget()
        if current is self.daw:
            index = self.daw.steps.current()
            self.context_bar.set_context(
                _("Universal DAW Mode"),
                _("Step {n} of {total}: {title}").format(
                    n=index + 1,
                    total=len(self.daw.steps.buttons),
                    title=self.daw.steps.title(index),
                ),
            )
        elif current is self.standalone:
            index = self.standalone.steps.current()
            self.context_bar.set_context(
                _("Demo (no interface)") if self.standalone.demo_mode else _("Standalone Mode"),
                _("Step {n} of {total}: {title}").format(
                    n=index + 1,
                    total=len(self.standalone.steps.buttons),
                    title=self.standalone.steps.title(index),
                ),
            )

    def _compare_context(self, title: str, subtitle: str) -> None:
        if self.stack.currentWidget() is self.compare:
            self.context_bar.set_context(title, subtitle)

    def _report_toggled(self, open: bool) -> None:
        """The text report needs a wide pane: widen the details while it is open."""
        sizes = self.splitter.sizes()
        if len(sizes) != 3:
            return
        if open:
            self._details_before_report = sizes
            if not self.details.isVisible():
                self.set_details_visible(True)
            wanted = min(560, max(sizes[2], self.width() // 2))
            self.details.setMaximumWidth(wanted)
            self.splitter.setSizes([sizes[0], sizes[1] - (wanted - sizes[2]), wanted])
        else:
            self.details.setMaximumWidth(460)
            before = getattr(self, "_details_before_report", None)
            if before is not None:
                self.splitter.setSizes(before)

    def _results_context(self, title: str, subtitle: str) -> None:
        if self.stack.currentWidget() is self.results:
            self.context_bar.set_context(title, subtitle)

    # --- lifecycle ------------------------------------------------------------------

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 - Qt override
        if not self._leave_take():
            event.ignore()
            return
        # The colour-scheme signal belongs to the application and outlives this
        # window: a closed window that stays connected still restyles the whole
        # application on every system change (the chrome and every chart are
        # redrawn), and each further closed window makes that slower. Closing
        # twice is legal, and disconnecting what is no longer connected warns.
        if self._following_system:
            self._following_system = False
            QGuiApplication.styleHints().colorSchemeChanged.disconnect(self._follow_system_scheme)
        # A QThread destroyed while it runs aborts the process (Ctrl+Q during a
        # take or an analysis): stop the take and let the workers finish.
        self.standalone.shutdown_workers()
        self.daw.shutdown_workers()
        super().closeEvent(event)

    def _leave_take(self) -> bool:
        """True when the window may drop the result on screen.

        A live Standalone take is the only copy of its recording until the
        session is saved; New Measurement, Open Session and closing the window
        used to drop it without a word.
        """
        if not (self.state.unsaved_take and self.state.result is not None):
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
            self.results.save_button.click()
            return not self.state.unsaved_take
        return clicked is discard

    # --- pages ----------------------------------------------------------------------

    def show_start(self) -> None:
        """The start page without dropping anything: the result, the imported
        recording and the device choices stay where they are."""
        self.home.refresh_recent()
        self.nav.refresh_recent()
        self.home.show_walkthrough(not load_settings().walkthrough_dismissed)
        self.context_bar.set_context(
            "ReverbScope", _("Start a measurement, open a project or a saved session.")
        )
        self._show_page(self.home, _("Home"), NAV_HOME)

    def show_home(self) -> None:
        """New Measurement: Home with a fresh state; asks first when a live
        take is unsaved."""
        if self._leave_take():
            self._go_home()

    def _go_home(self) -> None:
        self.state.reset()
        # Home is a fresh start: the next measurement belongs to no project
        # until the Project page starts one.
        self.state.leave_project()
        self.daw.clear_recording()
        # Home's environment report and device inspector describe the real
        # interface, not the demo's fake one.
        self.standalone.demo_mode = False
        self.run_status.set_idle()
        self.show_start()

    def choose_session(self) -> None:
        path, _filter = QFileDialog.getOpenFileName(
            self,
            _("Open session"),
            "",
            _("Session files (session.json);;JSON files (*.json);;All files (*)"),
        )
        if path:
            self.open_session_path(path)

    def open_session_path(self, path: str | Path) -> None:
        try:
            loaded = load_measurement(path)
        except ReverbScopeError as exc:
            QMessageBox.critical(self, _("Cannot open session"), localize(str(exc)))
            return
        if not self._leave_take():
            return
        # Drop the previous take: saving the opened session must not write
        # that recording into it. An opened session belongs to no project
        # workflow either: Save would otherwise list a copy of it there.
        self.state.reset()
        self.state.leave_project()
        self.daw.clear_recording()
        self.state.session = loaded.session
        self.state.result = loaded.result
        self.state.mode = loaded.session.mode
        self.state.saved_path = loaded.directory
        profile = loaded.session.recording_profile or "generic"
        if profile not in available_profiles():
            # A profile this install does not have (a plugin, a newer version).
            profile = "generic"
        from reverbscope.ui.measure_flow import safe_findings

        findings, problem = safe_findings(loaded.result, profile)
        self.state.profile = profile
        self.state.findings = findings
        self.state.findings_problem = problem
        remember_session(loaded.directory)
        self.nav.refresh_recent()
        self.show_results()

    def show_mode(self, mode: str) -> None:
        if mode in ("demo", "standalone") and self.standalone.is_busy():
            # Ctrl+2 / Ctrl+3 while a take or its analysis runs on the
            # Standalone page, from that page or from another: switching the
            # backend under it would show the demo banner over a real sweep (or
            # the reverse) and list devices over a running progress bar. The
            # page is shown as it is; leaving it for Home stops the take.
            self._show_page(
                self.standalone,
                _("Demo (no interface)") if self.standalone.demo_mode else _("Standalone Mode"),
                NAV_DEMO if self.standalone.demo_mode else NAV_STANDALONE,
            )
            self._mode_context()
            return
        if mode == "demo":
            self.state.mode = "standalone"
            self.standalone.demo_mode = True
            self.standalone.refresh_devices()
            self._show_page(self.standalone, _("Demo (no interface)"), NAV_DEMO)
            self._mode_context()
            return
        self.state.mode = mode
        self.standalone.demo_mode = False
        if mode == "standalone":
            self.standalone.refresh_devices()
            self._show_page(self.standalone, _("Standalone Mode"), NAV_STANDALONE)
        else:
            self._show_page(self.daw, _("Universal DAW Mode"), NAV_DAW)
        self._mode_context()

    def _back_to_dimensions(self) -> None:
        """The Results page asks for a missing placement input: the mode page
        the result came from, on its dimensions step, with everything kept."""
        if self.state.mode == "universal_daw":
            self.daw.show_step(STEP_ANALYSE)
            self.daw.placement_section.set_open(True)
            self._show_page(self.daw, _("Universal DAW Mode"), NAV_DAW)
        else:
            self.standalone.show_step(STEP_DIMENSIONS)
            self._show_page(
                self.standalone,
                _("Demo (no interface)") if self.standalone.demo_mode else _("Standalone Mode"),
                NAV_DEMO if self.standalone.demo_mode else NAV_STANDALONE,
            )
        self._mode_context()

    def show_getting_started(self) -> None:
        """Home with the first-measurement card, and the card stays from now on."""
        import contextlib
        from dataclasses import replace

        from reverbscope.settings import save_settings

        with contextlib.suppress(ReverbScopeError, OSError):
            save_settings(replace(load_settings(), walkthrough_dismissed=False))
        self.show_home()
        self.home.restore_walkthrough()

    def choose_project(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, _("Open project folder"))
        if directory:
            self.show_project(Path(directory))

    def show_project(self, path: str | Path | None = None) -> None:
        """The Project page: for ``path`` (opened, or offered to be made), or
        the project it already shows, read again."""
        if path is not None:
            if not self.project.open_path(Path(path)):
                return
        else:
            self.project.reload()
        self.context_bar.set_context(*self.project.context_text())
        self._show_page(self.project, _("Project"), NAV_PROJECT)
        self._update_project_nav()

    def _show_position(self, position: str) -> None:
        if self.project.path is None:
            return
        self.show_project()
        self.project.select_position(position)

    def _measure_position(self, position: str, mode: str) -> None:
        """Measure ``position`` of the project on the Project page with ``mode``:
        the save on the Results page then adds the session to the project."""
        self.state.project_path = self.project.path
        self.state.project_position = position
        self.show_mode(mode)
        name = "" if self.project.overview is None else self.project.overview.name
        for page in (self.daw, self.standalone):
            page.position.setText(position)
            if name and not page.room.text():
                page.room.setText(name)

    def _compare_from_project(self, baseline: str, candidate: str) -> None:
        self.show_compare()
        self.compare.set_paths(Path(baseline), Path(candidate))

    def _compare_current(self) -> None:
        """Compare the result on screen: a saved one is the baseline already."""
        self.show_compare()
        saved = self.state.saved_path
        if saved is not None and not self.compare.baseline_path.text().strip():
            self.compare.baseline_path.setText(str(saved))
        elif saved is None:
            self.compare.status.setText(
                _("Save this session first to compare it; a comparison reads sessions from disk.")
            )

    def show_results(self) -> None:
        self.results.refresh()
        self.context_bar.set_context(*self.results.context_text())
        self._show_page(self.results, _("Results"), NAV_RESULTS)

    def show_compare(self) -> None:
        current = self.stack.currentWidget()
        if current is not None and current is not self.compare:
            self._before_compare = (current, self._place)
        self.compare.browser.refresh_recent()
        selected = self.home.browser.selected_pair()
        if selected is not None:
            self.compare.set_paths(*selected)
        self.context_bar.set_context(*self.compare.context_text())
        self._show_page(self.compare, _("Compare"), NAV_COMPARE)

    def _leave_compare(self) -> None:
        """Back: to the page Compare was opened from, with its measurement kept."""
        page, place = self._before_compare
        if page is self.home:
            # Nothing to keep there; Home lists the sessions saved meanwhile.
            self.show_start()
            return
        if page is self.results:
            self.show_results()
            return
        if page is self.project:
            self.show_project()
            return
        self._show_page(page, place, None)

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
        self.results.restyle()
        self.compare.restyle()
        self.project.restyle()
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
