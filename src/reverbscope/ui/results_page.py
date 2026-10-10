"""The Results page: overview, analysis workspace and the text report, with
the details pane fed by whatever is selected and the actions in the context
bar (save, export, copy, compare, project).
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QGuiApplication, QResizeEvent
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from reverbscope.cli.render import REPORT_CONSOLE, render_analysis
from reverbscope.demo import localize_demo_name
from reverbscope.errors import ReverbScopeError
from reverbscope.health import HealthCheck
from reverbscope.i18n import _, localize
from reverbscope.interpretation.profiles import profile_title
from reverbscope.io.recent import remember_session
from reverbscope.io.session_store import SESSION_FILE, save_measurement
from reverbscope.labels import topic_text
from reverbscope.models.result import AnalysisResult
from reverbscope.settings import load_settings
from reverbscope.ui.export import export_csv_tables, export_figure_png
from reverbscope.ui.results_analysis import AnalysisWorkspace
from reverbscope.ui.results_overview import Overview
from reverbscope.ui.results_presenter import (
    GROUPS,
    check_rows,
    finding_group,
    finding_rows,
    group_title,
    ranked_findings,
)
from reverbscope.ui.state import MeasurementState
from reverbscope.ui.theme import apply_report_font
from reverbscope.ui.widgets import Chip, KeyValueList, flat, label, primary
from reverbscope.ui.workspace import action_row


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
    # By role, not by label, as in measure_flow.ask_separate_clocks.
    return clicked is not None and box.buttonRole(clicked) == QMessageBox.ButtonRole.AcceptRole


# Below this page height the key-figure tiles fold so the chart keeps its room.
SHORT_PAGE_HEIGHT = 600


class ResultDetail(QWidget):
    """What the details pane shows for a result: the selected thing's rows,
    or the full text report."""

    open_chart = Signal(str)
    report_closed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 4, 12, 12)
        layout.setSpacing(8)
        head = QHBoxLayout()
        self.heading = label("", "card-title", wrap=True)
        head.addWidget(self.heading, 1)
        self.chip = Chip("", "neutral", glyph=True)
        self.chip.hide()
        head.addWidget(self.chip, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(head)
        self.message = label("", wrap=True)
        self.message.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.message)
        self.rows = KeyValueList()
        layout.addWidget(self.rows)
        self.note = label("", "hint", wrap=True)
        layout.addWidget(self.note)
        self.chart_button = flat(QPushButton(""))
        self.chart_button.hide()
        layout.addWidget(self.chart_button, 0, Qt.AlignmentFlag.AlignLeft)
        self._group: str | None = None
        self.chart_button.clicked.connect(self._open)
        # The full text report, shown instead of the selection on request.
        self.report_box = QWidget()
        report_layout = QVBoxLayout(self.report_box)
        report_layout.setContentsMargins(0, 0, 0, 0)
        report_layout.setSpacing(6)
        report_head = QHBoxLayout()
        report_head.addWidget(label(_("Full report"), "card-title"), 1)
        self.report_close = flat(QPushButton(_("Back to the selection")))
        self.report_close.clicked.connect(lambda: self.show_report(False))
        report_head.addWidget(self.report_close)
        report_layout.addLayout(report_head)
        self.report_heading = label(
            _("The same report that reverbscope analyze prints; warnings are at the end."),
            "hint",
            wrap=True,
        )
        report_layout.addWidget(self.report_heading)
        self.report = QPlainTextEdit()
        self.report.setReadOnly(True)
        self.report.setProperty("report", True)
        self.report.setMinimumHeight(420)
        self.report.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        apply_report_font(self.report)
        report_layout.addWidget(self.report, 1)
        self.report_box.hide()
        layout.addWidget(self.report_box, 1)
        self._selection = [
            self.heading,
            self.chip,
            self.message,
            self.rows,
            self.note,
            self.chart_button,
        ]
        layout.addStretch(1)

    def show_rows(
        self,
        heading: str,
        rows: list[tuple[str, str]],
        note: str = "",
        *,
        message: str = "",
        chip: tuple[str, str] | None = None,
        group: str | None = None,
    ) -> None:
        if self.report_box.isVisible():
            self.show_report(False)
        self.heading.setText(heading)
        self.message.setText(message)
        self.message.setVisible(bool(message))
        if chip is None:
            self.chip.hide()
        else:
            self.chip.setText(chip[0])
            self.chip.set_tone(chip[1])
            self.chip.show()
        self.rows.set_rows(rows)
        self.note.setText(note)
        self.note.setVisible(bool(note))
        self._group = group
        if group is None:
            self.chart_button.hide()
        else:
            from reverbscope.ui.results_presenter import group_title

            self.chart_button.setText(_("Open {chart}").format(chart=group_title(group)))
            self.chart_button.show()

    def _open(self) -> None:
        if self._group is not None:
            self.open_chart.emit(self._group)

    def show_report(self, visible: bool) -> None:
        """The text report instead of the selection (and back)."""
        self.report_box.setVisible(visible)
        self.heading.setVisible(not visible)
        self.message.setVisible(not visible and bool(self.message.text()))
        self.chip.setVisible(not visible and bool(self.chip.text()))
        self.rows.setVisible(not visible)
        self.note.setVisible(not visible and bool(self.note.text()))
        self.chart_button.setVisible(not visible and self._group is not None)
        if not visible:
            self.report_closed.emit()


class ResultsPage(QWidget):
    new_measurement = Signal()
    #: The user wants the Project page (the session was saved into a project).
    project_requested = Signal()
    #: Compare this result with another saved session.
    compare_requested = Signal()
    #: The placement group wants the measurement page's dimension fields.
    settings_requested = Signal()
    #: What the context bar should say for this page.
    context_changed = Signal(str, str)
    #: The full report was opened (True) or closed in the details pane: the
    #: window gives the pane more room while it is open.
    report_toggled = Signal(bool)

    def __init__(self, state: MeasurementState, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.state = state
        self.setProperty("page", True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 8)
        layout.setSpacing(8)

        self.new_button = QPushButton(_("New Measurement"))
        self.new_button.setToolTip(_("Back to the start page for another measurement (Ctrl+N)."))
        self.new_button.clicked.connect(self.new_measurement.emit)
        self.compare_button = QPushButton(_("Compare..."))
        self.compare_button.setToolTip(_("Compare this session with another saved one."))
        self.compare_button.clicked.connect(self.compare_requested.emit)
        self.export_button = QToolButton()
        self.export_button.setText(_("Export"))
        self.export_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.export_menu = QMenu(self.export_button)
        self.export_csv_action = self.export_menu.addAction(_("CSV tables..."))
        self.export_csv_action.triggered.connect(self.export_csv)
        self.export_png_action = self.export_menu.addAction(_("Current chart as PNG..."))
        self.export_png_action.triggered.connect(self.export_png)
        self.export_button.setMenu(self.export_menu)
        self.save_button = primary(QPushButton(_("Save Session...")))
        self.save_button.setShortcut("Ctrl+S")
        self.save_button.clicked.connect(self._choose_save_directory)
        self.profile_button = QPushButton(_("About this profile..."))
        self.profile_button.setToolTip(_("What the recording profile watches for."))
        self.profile_button.clicked.connect(self.show_profile_help)
        self.project_button = QPushButton(_("Project"))
        self.project_button.setToolTip(_("Back to the project this take belongs to."))
        self.project_button.clicked.connect(self.project_requested.emit)
        self.project_button.hide()
        self.copy_action = self.export_menu.addAction(_("Copy report"))
        self.copy_action.triggered.connect(self._copy_report)

        # The chart is the page: the groups and the overview stand beside it,
        # the details pane explains what is selected, the report is a detail.
        self.overview = Overview(with_tiles=False)
        self.overview.group_requested.connect(self.show_group)
        self.overview.finding_selected.connect(self._show_finding_detail)
        self.overview.check_selected.connect(self._show_check_detail)
        self.overview.profile_row.insertWidget(0, flat(self.profile_button))
        self.analysis = AnalysisWorkspace(with_list=False)
        self.analysis.detail_changed.connect(self._show_detail_rows)
        self.analysis.settings_requested.connect(self.settings_requested.emit)
        self.analysis.group_changed.connect(self._group_shown)
        self.groups = self.analysis.groups
        self.table = self.analysis.groups["decay"].table  # type: ignore[union-attr]

        # The four key figures stand over the chart; on a short window they
        # fold away so the chart keeps its height (they stay in the overview's
        # health card, the metric tables and the full report).
        self.tiles_row = QWidget()
        tiles = QHBoxLayout(self.tiles_row)
        tiles.setContentsMargins(0, 0, 0, 0)
        tiles.setSpacing(8)
        for tile in self.overview.tiles.values():
            tiles.addWidget(tile)
        layout.addWidget(self.tiles_row)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        sidebar = QWidget()
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(4)
        sidebar_layout.addWidget(label(_("Charts"), "section"))
        self.group_list = QListWidget()
        self.group_list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        for key in self.groups:
            item = QListWidgetItem(group_title(key))
            item.setData(Qt.ItemDataRole.UserRole, key)
            self.group_list.addItem(item)
        self.group_list.setFixedHeight(
            self.group_list.sizeHintForRow(0) * self.group_list.count() + 8
        )
        self.group_list.currentRowChanged.connect(self._group_row_changed)
        sidebar_layout.addWidget(self.group_list)
        sidebar_layout.addWidget(self.overview, 1)
        sidebar.setMinimumWidth(250)
        self.splitter.addWidget(sidebar)
        self.splitter.addWidget(self.analysis)
        self.splitter.setCollapsible(0, True)
        self.splitter.setCollapsible(1, False)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([330, 670])
        layout.addWidget(self.splitter, 1)

        self.status = QLabel("")
        self.status.setProperty("role", "hint")
        self.status.setWordWrap(True)
        self.status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.status)
        self.detail = ResultDetail()
        self.detail.open_chart.connect(self.show_group)
        # The full text report lives in the details pane and in Export.
        self.text = self.detail.report
        self.diagnostics_heading = self.detail.report_heading
        self.report_button = QPushButton(_("Full report"))
        self.report_button.setCheckable(True)
        self.report_button.setToolTip(
            _("Show the text report in the details pane (the same as reverbscope analyze).")
        )
        self.report_button.toggled.connect(self.detail.show_report)
        self.report_button.toggled.connect(self.report_toggled.emit)
        self.detail.report_closed.connect(self._report_closed)
        self.context_actions = action_row(
            self.new_button,
            self.project_button,
            self.report_button,
            self.compare_button,
            self.export_button,
            self.save_button,
        )

    # --- showing --------------------------------------------------------------------

    def _copy_report(self) -> None:
        text = self.text.toPlainText().strip()
        if not text:
            self.status.setText(_("Nothing to copy yet."))
            return
        clipboard = QGuiApplication.clipboard()
        clipboard.setText(self.text.toPlainText())
        self.status.setText(_("Report copied to the clipboard."))

    def context_text(self) -> tuple[str, str]:
        """The context bar's title and subtitle for this result."""
        result = self.state.result
        session = self.state.session
        if result is None:
            return _("Results"), ""
        title = localize_demo_name(session.mode, session.room_name) or _("Results")
        mode = {
            "universal_daw": _("Universal DAW Mode"),
            "standalone": _("Standalone Mode"),
            "synthetic_demo": _("Demo (no interface)"),
        }.get(session.mode, session.mode)
        parts = [
            localize_demo_name(session.mode, part)
            for part in (session.measurement_position, session.microphone_name)
            if part
        ]
        parts.append(_("{profile} profile").format(profile=profile_title(self.state.profile)))
        parts.append(f"{result.sample_rate} Hz")
        parts.append(mode)
        if self.state.unsaved_take:
            parts.append(_("unsaved"))
        return title, "  ·  ".join(parts)

    def refresh(self) -> None:
        result = self.state.result
        if result is None:
            return
        self.text.setPlainText(
            render_analysis(REPORT_CONSOLE, result, self.state.findings, self.state.profile)
        )
        self._draw(result)
        self.status.setText("")
        self.project_button.setVisible(self.state.project_path is not None)
        self.detail.show_rows(_("Results"), [], _("Click a figure, a finding or a table row."))
        self.show_group(self._first_group())
        self.context_changed.emit(*self.context_text())

    def restyle(self) -> None:
        """Draw the result again in the colour scheme now in force.

        The cards, the table colours and the charts take the scheme's colours
        when they are drawn; the application style sheet does not reach them.
        """
        if self.state.result is not None:
            self.overview.show_result(
                self.state.result,
                list(self.state.findings),
                self.state.profile,
                self.state.findings_problem,
            )
            self.analysis.restyle()

    def _draw(self, result: AnalysisResult) -> None:
        self.overview.show_result(
            result, list(self.state.findings), self.state.profile, self.state.findings_problem
        )
        # The charts are drawn when their group is shown, not all at once.
        self.analysis.set_result(result)

    def _first_group(self) -> str:
        """The chart a result opens on: the one behind its worst finding, else
        the first group."""
        for _index, finding in ranked_findings(self.state.findings):
            group = finding_group(finding)
            if group is not None:
                return group
        return GROUPS[0]

    def show_group(self, key: str) -> None:
        """Show the chart group ``key`` in the centre."""
        for row in range(self.group_list.count()):
            if self.group_list.item(row).data(Qt.ItemDataRole.UserRole) == key:
                if self.group_list.currentRow() != row:
                    self.group_list.setCurrentRow(row)
                else:
                    self.analysis.show_group(key)
                return

    def _group_row_changed(self, row: int) -> None:
        if row >= 0:
            self.analysis.show_group(str(self.group_list.item(row).data(Qt.ItemDataRole.UserRole)))

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802 - Qt override
        super().resizeEvent(event)
        self.tiles_row.setVisible(event.size().height() >= SHORT_PAGE_HEIGHT)

    def _group_shown(self, key: str) -> None:
        for row in range(self.group_list.count()):
            if self.group_list.item(row).data(Qt.ItemDataRole.UserRole) == key:
                self.group_list.blockSignals(True)
                self.group_list.setCurrentRow(row)
                self.group_list.blockSignals(False)

    def _report_closed(self) -> None:
        if self.report_button.isChecked():
            self.report_button.blockSignals(True)
            self.report_button.setChecked(False)
            self.report_button.blockSignals(False)
            self.report_toggled.emit(False)

    def session_line(self) -> str:
        """Room, position, microphone, profile and rate on one line."""
        title, subtitle = self.context_text()
        return f"{title}  ·  {subtitle}" if subtitle else title

    def _show_detail_rows(self, title: str, rows: object, note: str) -> None:
        listed = [tuple(row) for row in rows] if isinstance(rows, list) else []
        self.detail.show_rows(title, [(str(k), str(v)) for k, v in listed], note)

    def _show_finding_detail(self, index: int) -> None:
        findings = self.state.findings
        if not 0 <= index < len(findings):
            return
        finding = findings[index]
        from reverbscope.labels import severity_text
        from reverbscope.ui.widgets import SEVERITY_TONE

        self.detail.show_rows(
            topic_text(finding.topic),
            finding_rows(finding),
            _("Evidence: the measured values the sentence rests on."),
            message=finding.message,
            chip=(
                severity_text(str(finding.severity)),
                SEVERITY_TONE.get(str(finding.severity), "neutral"),
            ),
            group=finding_group(finding),
        )

    def _show_check_detail(self, check: HealthCheck) -> None:
        from reverbscope.health import status_word
        from reverbscope.ui.results_presenter import HEALTH_TONE, check_group

        self.detail.show_rows(
            check.title,
            check_rows(check),
            "",
            chip=(status_word(check.status), HEALTH_TONE[check.status]),
            group=check_group(check),
        )

    # --- export and save ------------------------------------------------------------

    def export_csv(self) -> None:
        result = self.state.result
        if result is None:
            self.status.setText(_("Nothing to export yet."))
            return
        start = str(self.state.project_path or load_settings().output_dir or "")
        message = export_csv_tables(self, result, start)
        if message:
            self.status.setText(message)

    def export_png(self) -> None:
        if self.state.result is None:
            self.status.setText(_("Nothing to export yet."))
            return
        self.analysis.ensure_current_drawn()
        group = self.analysis.current_group()
        stem = (
            "".join(ch if ch.isalnum() else "-" for ch in self.state.session.room_name)
            or "reverbscope"
        )
        message = export_figure_png(self, self.analysis.current_figure(), f"{stem}-{group}")
        if message:
            self.status.setText(message)

    def _choose_save_directory(self) -> None:
        project = self.state.project_path
        if project is not None:
            # Into the project, in a folder named after the position: the
            # session is then listed under it.
            name, ok = QInputDialog.getText(
                self,
                _("Save into the project"),
                _("Folder name inside {project}").format(project=project),
                text=self.suggested_project_folder(),
            )
            if not ok or not name.strip():
                return
            target = project / name.strip()
            if (target / SESSION_FILE).exists() and not ask_replace_session(self, str(target)):
                return
            self.save_to(target)
            return
        directory = QFileDialog.getExistingDirectory(
            self, _("Choose a folder for the session"), load_settings().output_dir
        )
        if not directory:
            return
        # The dialog opens at the default output folder: accepting it twice
        # as offered would replace the first session without a word.
        if (Path(directory) / SESSION_FILE).exists() and not ask_replace_session(self, directory):
            return
        self.save_to(Path(directory))

    def save_to(self, directory: Path) -> None:
        result = self.state.result
        if result is None:
            return
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
            return
        remember_session(directory)
        self.state.unsaved_take = False
        self.state.saved_path = session_path.parent
        self.status.setText(_("Session saved to {path}").format(path=session_path.parent))
        self.context_changed.emit(*self.context_text())
        project = self.state.project_path
        if project is not None:
            self._add_to_project(project, directory)

    def show_profile_help(self) -> QDialog:
        from reverbscope.ui.profile_dialog import show_profile_help

        return show_profile_help(self.state.profile, self)

    def suggested_project_folder(self) -> str:
        """``<position>-<n>``: the next free folder name for the position."""
        project = self.state.project_path
        position = self.project_position_label()
        stem = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in position) or "take"
        n = 1
        while project is not None and (project / f"{stem}-{n}").exists():
            n += 1
        return f"{stem}-{n}"

    def project_position_label(self) -> str:
        return self.state.project_position or self.state.session.measurement_position.strip() or "A"

    def _add_to_project(self, project: Path, directory: Path) -> None:
        from reverbscope.io.project_store import add_session

        position = self.project_position_label()
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
        self.status.setText(
            _(
                "Session saved to {path} and listed in project {project} under position {label}"
            ).format(path=directory, project=listed.name or project.name, label=position)
        )
        self.project_button.show()
