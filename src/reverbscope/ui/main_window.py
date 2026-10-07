"""Main window: a stacked layout of Home -> Mode page -> Results."""

from __future__ import annotations

import sys
import weakref
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QAction, QCloseEvent, QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QMainWindow,
    QMessageBox,
    QStackedWidget,
    QStatusBar,
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
from reverbscope.ui.pages import DawModePage, HomePage, StandalonePage, safe_findings
from reverbscope.ui.results import ResultsPage
from reverbscope.ui.state import MeasurementState
from reverbscope.ui.theme import apply_application_chrome, color_scheme
from reverbscope.ui.widgets import app_icon


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
        self.resize(1180, 800)
        self.state = MeasurementState()
        # The default profile chosen in Settings, as the CLI reads it.
        default_profile = load_settings().default_profile
        if default_profile in available_profiles():
            self.state.profile = default_profile
        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)

        self.home = HomePage()
        self.daw = DawModePage(self.state)
        self.standalone = StandalonePage(self.state)
        self.results = ResultsPage(self.state)
        self.compare = ComparePage()
        for page in (self.home, self.daw, self.standalone, self.results, self.compare):
            self.stack.addWidget(page)

        self.home.choose_mode.connect(self.show_mode)
        self.home.open_session.connect(self.choose_session)
        self.home.open_recent.connect(self.open_session_path)
        self.home.compare_requested.connect(self.show_compare)
        self.daw.analysis_finished.connect(self.show_results)
        self.standalone.analysis_finished.connect(self.show_results)
        self.daw.back.connect(self.show_home)
        self.standalone.back.connect(self.show_home)
        self.results.new_measurement.connect(self.show_home)
        self.compare.back.connect(self._leave_compare)

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
        settings_action = QAction(_("&Settings..."), self)
        settings_action.setShortcut("Ctrl+,")
        settings_action.triggered.connect(self.show_settings)
        quit_action = QAction(_("&Quit"), self)
        quit_action.setShortcut("Ctrl+Q")
        quit_action.triggered.connect(self.close)
        file_menu.addAction(new_action)
        file_menu.addAction(open_action)
        file_menu.addAction(compare_action)
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
        self._status = QStatusBar()
        self.setStatusBar(self._status)
        self._place = ""
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
        self.show_home()

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

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 - Qt override
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

    def _set_place(self, place: str) -> None:
        self._place = place
        self._status.showMessage(
            _("ReverbScope {version}  ·  {place}").format(version=__version__, place=place)
        )

    def show_home(self) -> None:
        self.state.reset()
        self.daw.clear_recording()
        # Home's environment report and device inspector describe the real
        # interface, not the demo's fake one.
        self.standalone.demo_mode = False
        self.home.refresh_recent()
        self.stack.setCurrentWidget(self.home)
        self._set_place(_("Home"))

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
        # Drop the previous take: saving the opened session must not write
        # that recording into it.
        self.state.reset()
        self.daw.clear_recording()
        self.state.session = loaded.session
        self.state.result = loaded.result
        self.state.mode = loaded.session.mode
        profile = loaded.session.recording_profile or "generic"
        if profile not in available_profiles():
            # A profile this install does not have (a plugin, a newer version).
            profile = "generic"
        findings, problem = safe_findings(loaded.result, profile)
        self.state.profile = profile
        self.state.findings = findings
        self.state.findings_problem = problem
        remember_session(loaded.directory)
        self.show_results()

    def show_mode(self, mode: str) -> None:
        if (
            mode in ("demo", "standalone")
            and self.stack.currentWidget() is self.standalone
            and self.standalone.is_busy()
        ):
            # Ctrl+2 / Ctrl+3 on the page of a running take: switching the
            # backend under it would show the demo banner over a real sweep
            # (or the reverse). Leaving the page (Ctrl+1, Home) stops the take.
            return
        if mode == "demo":
            self.state.mode = "standalone"
            self.standalone.demo_mode = True
            self.standalone.refresh_devices()
            self.stack.setCurrentWidget(self.standalone)
            self._set_place(_("Demo (no interface)"))
            return
        self.state.mode = mode
        self.standalone.demo_mode = False
        if mode == "standalone":
            self.standalone.refresh_devices()
            self.stack.setCurrentWidget(self.standalone)
            self._set_place(_("Standalone Mode"))
        else:
            self.stack.setCurrentWidget(self.daw)
            self._set_place(_("Universal DAW Mode"))

    def show_results(self) -> None:
        self.results.refresh()
        self.stack.setCurrentWidget(self.results)
        self._set_place(_("Results"))

    def show_compare(self) -> None:
        current = self.stack.currentWidget()
        if current is not None and current is not self.compare:
            self._before_compare = (current, self._place)
        self.compare.browser.refresh_recent()
        selected = self.home.browser.selected_pair()
        if selected is not None:
            self.compare.set_paths(*selected)
        self.stack.setCurrentWidget(self.compare)
        self._set_place(_("Compare"))

    def _leave_compare(self) -> None:
        """Back: to the page Compare was opened from, with its measurement kept."""
        page, place = self._before_compare
        if page is self.home:
            # Nothing to keep there; Home lists the sessions saved meanwhile.
            self.show_home()
            return
        self.stack.setCurrentWidget(page)
        self._set_place(place)

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
        home.mkdir(parents=True, exist_ok=True)
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
