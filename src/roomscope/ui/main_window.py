"""Main window: a stacked layout of Home -> Mode page -> Results."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QAction, QCloseEvent, QDesktopServices
from PySide6.QtWidgets import (
    QFileDialog,
    QMainWindow,
    QMessageBox,
    QStackedWidget,
    QStatusBar,
    QWidget,
)

from roomscope import __version__
from roomscope.errors import RoomScopeError
from roomscope.i18n import _, localize
from roomscope.interpretation import available_profiles, interpret
from roomscope.io.recent import remember_session
from roomscope.io.session_store import load_measurement
from roomscope.settings import load_settings
from roomscope.ui.compare_view import ComparePage
from roomscope.ui.pages import DawModePage, HomePage, StandalonePage
from roomscope.ui.results import ResultsPage
from roomscope.ui.state import MeasurementState
from roomscope.ui.widgets import app_icon


def about_html() -> str:
    """About box body, translated when it is shown (not when this module loads)."""
    return _(
        "<b>RoomScope {version}</b><br>"
        "An open-source, DAW-independent recording environment analyzer.<br><br>"
        "Licensed under the Apache License, Version 2.0.<br>"
        "This program uses Qt and PySide6 (Copyright The Qt Company Ltd. and contributors) "
        "under the GNU Lesser General Public License v3; the Qt libraries are loaded as "
        "separate shared libraries and may be replaced by interface-compatible versions. "
        "NumPy, SciPy, matplotlib, soundfile (libsndfile, LGPL-2.1) and sounddevice "
        "(PortAudio) are used under their respective licenses.<br><br>"
        "A desktop bundle ships a <code>THIRD_PARTY_LICENSES/</code> directory next to the "
        "executable (and inside <code>RoomScope.app</code> on macOS). From a source checkout "
        "see docs/DEPENDENCIES.md. Levels are digital (dBFS) unless a calibration is provided; "
        "RoomScope never reports dB SPL."
    ).format(version=__version__)


def about_box(parent: QWidget | None = None) -> QMessageBox:
    """The About dialog. The button is ours, so it does not depend on Qt's catalog."""
    box = QMessageBox(parent)
    box.setWindowTitle(_("About RoomScope"))
    box.setWindowIcon(app_icon())
    box.setIconPixmap(app_icon().pixmap(64, 64))
    box.setTextFormat(Qt.TextFormat.RichText)
    box.setText(about_html())
    box.addButton(_("OK"), QMessageBox.ButtonRole.AcceptRole)
    return box


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"RoomScope {__version__}")
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
        self.compare.back.connect(self.show_home)

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
        daw_action.triggered.connect(lambda: self.show_mode("universal_daw"))
        standalone_action = QAction(_("Standalone Mode"), self)
        standalone_action.setShortcut("Ctrl+2")
        standalone_action.triggered.connect(lambda: self.show_mode("standalone"))
        demo_action = QAction(_("Demo (no interface)"), self)
        demo_action.setShortcut("Ctrl+3")
        demo_action.triggered.connect(lambda: self.show_mode("demo"))
        measure_menu.addAction(daw_action)
        measure_menu.addAction(standalone_action)
        measure_menu.addAction(demo_action)

        from roomscope.edition import is_developer

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
        about_action = QAction(_("&About RoomScope"), self)
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
        self.show_home()

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 - Qt override
        # A QThread destroyed while it runs aborts the process (Ctrl+Q during a
        # take or an analysis): stop the take and let the workers finish.
        self.standalone.shutdown_workers()
        self.daw.shutdown_workers()
        super().closeEvent(event)

    def _set_place(self, place: str) -> None:
        self._status.showMessage(
            _("RoomScope {version}  ·  {place}").format(version=__version__, place=place)
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
        except RoomScopeError as exc:
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
        try:
            findings = interpret(loaded.result, profile)
        except RoomScopeError:
            profile = "generic"
            findings = interpret(loaded.result, profile)
        self.state.profile = profile
        self.state.findings = findings
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
        self.compare.browser.refresh_recent()
        selected = self.home.browser.selected_pair()
        if selected is not None:
            self.compare.set_paths(*selected)
        self.stack.setCurrentWidget(self.compare)
        self._set_place(_("Compare"))

    def show_settings(self) -> None:
        from roomscope.ui.settings_dialog import SettingsDialog

        before = load_settings().default_profile
        if not SettingsDialog(self).exec():
            return
        profile = load_settings().default_profile
        if profile != before and profile in available_profiles():
            # A new default profile applies now, as the output folder does.
            # Only the combos: a running take keeps the profile it started with.
            for combo in (self.daw.profile, self.standalone.profile):
                combo.setCurrentIndex(max(combo.findData(profile), 0))

    def show_device_inspector(self) -> None:
        from roomscope.ui.dev_tools import DeviceInspector

        backend = "fake" if self.standalone.demo_mode else None
        DeviceInspector(backend, self).exec()

    def show_environment_report(self) -> None:
        from roomscope.ui.dev_tools import EnvironmentReport

        backend = "fake" if self.standalone.demo_mode else None
        EnvironmentReport(backend, self).exec()

    def _open_data_folder(self) -> None:
        from roomscope.io.recent import roomscope_home

        home = roomscope_home()
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
