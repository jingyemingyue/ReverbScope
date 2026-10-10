"""The Project page: one room, several microphone positions.

Shows :func:`reverbscope.interpretation.overview.summarize_project` for a
project folder (every take with its health, headline numbers and fit; every
position's agreement and its verdict against the first; the spatial average
and the ISO 3382-2 class; what to measure next), and starts the next take:
*Measure a new position* names the position, opens the chosen mode, and the
save on the Results page adds the session to the project under that name.
A position can be measured again, a take opened, and a take compared with
the first position.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from reverbscope.cli.render import REPORT_CONSOLE, render_overview
from reverbscope.errors import ReverbScopeError
from reverbscope.health import HealthStatus, status_word
from reverbscope.i18n import _, list_join, localize
from reverbscope.interpretation import available_profiles
from reverbscope.interpretation.overview import (
    PositionSummary,
    ProjectEntry,
    ProjectOverview,
    SessionSummary,
    fit_word,
    summarize_project,
)
from reverbscope.interpretation.profiles import profile_title
from reverbscope.io.project_store import (
    add_session,
    is_project,
    list_project_sessions,
    load_project,
    save_project,
)
from reverbscope.io.session_store import load_measurement, load_session
from reverbscope.labels import accuracy_class_text
from reverbscope.models.project import Project
from reverbscope.ui.state import MeasurementState
from reverbscope.ui.widgets import (
    Card,
    FindingCard,
    KeyValueList,
    PageHeader,
    clear_layout,
    label,
    primary,
    scroll_body,
)
from reverbscope.ui.workspace import action_row


def suggest_label(taken: list[str] | tuple[str, ...]) -> str:
    """The next free single-letter position label: A, B, ... then A2, B2, ..."""
    used = {name.strip().upper() for name in taken}
    letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    for suffix in ("", "2", "3", "4"):
        for letter in letters:
            candidate = f"{letter}{suffix}"
            if candidate not in used:
                return candidate
    return f"P{len(used) + 1}"


class NewPositionDialog(QDialog):
    """Name the position and pick how to measure it."""

    def __init__(
        self, suggested: str, mode: str, parent: QWidget | None = None, *, again: bool = False
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(_("Measure again") if again else _("Measure a new position"))
        form = QFormLayout(self)
        self.label_edit = QLineEdit(suggested)
        self.label_edit.setToolTip(
            _("A short name for the microphone position: A, B, desk, corner.")
        )
        self.label_edit.setReadOnly(again)
        form.addRow(_("Position"), self.label_edit)
        self.mode = QComboBox()
        self.mode.addItem(_("Universal DAW Mode"), "universal_daw")
        self.mode.addItem(_("Standalone Mode"), "standalone")
        self.mode.addItem(_("Demo (no interface)"), "demo")
        self.mode.setCurrentIndex(max(self.mode.findData(mode), 0))
        form.addRow(_("Measure with"), self.mode)
        form.addRow(
            label(
                _(
                    "Keep the loudspeaker, its level and the input gain as they were for the "
                    "other positions; only the microphone moves."
                ),
                "hint",
                wrap=True,
            )
        )
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def values(self) -> tuple[str, str]:
        return self.label_edit.text().strip(), str(self.mode.currentData())


class PositionDetail(QWidget):
    """The details pane of the Project page: the selected position or take."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 4, 12, 12)
        layout.setSpacing(8)
        self.heading = label("", "card-title", wrap=True)
        layout.addWidget(self.heading)
        self.rows = KeyValueList()
        layout.addWidget(self.rows)
        self.note = label("", "hint", wrap=True)
        self.note.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.note)
        layout.addStretch(1)

    def show_rows(self, heading: str, rows: list[tuple[str, str]], note: str = "") -> None:
        self.heading.setText(heading)
        self.rows.set_rows(rows)
        self.note.setText(note)
        self.note.setVisible(bool(note))


class ProjectPage(QWidget):
    back = Signal()
    #: Position label and mode: the main window opens the mode page for it.
    measure_requested = Signal(str, str)
    #: A take's directory: the main window opens it on the Results page.
    open_session = Signal(str)
    #: Baseline and candidate directories: the main window opens Compare on them.
    compare_requested = Signal(str, str)
    #: The overview was read again (the navigation lists the positions).
    changed = Signal()

    def __init__(self, state: MeasurementState, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.state = state
        self.path: Path | None = None
        self.overview: ProjectOverview | None = None
        self._project: Project | None = None
        self._entries: list[ProjectEntry] = []
        self._skipped: list[tuple[str, str]] = []
        self._selected_position: str = ""
        #: The user picked a profile: a reload keeps it instead of the latest take's.
        self._profile_chosen = False
        self.setProperty("page", True)

        self.back_button = QPushButton(_("Home"))
        self.back_button.clicked.connect(self.back.emit)
        self.open_button = QPushButton(_("Open Project..."))
        self.open_button.clicked.connect(self.choose)
        self.new_button = QPushButton(_("New Project..."))
        self.new_button.clicked.connect(self._choose_new)
        self.copy_button = QPushButton(_("Copy overview"))
        self.copy_button.clicked.connect(self._copy)
        self.measure_button = primary(QPushButton(_("Measure a new position...")))
        self.measure_button.clicked.connect(self._choose_position)
        self.context_actions = action_row(
            self.back_button,
            self.open_button,
            self.new_button,
            self.copy_button,
            self.measure_button,
        )
        self.detail = PositionDetail()

        layout, self.scroll_area = scroll_body(self, margins=(16, 10, 16, 8))
        self.header = PageHeader("")
        self.header.title.hide()
        layout.addWidget(self.header)

        tools = Card()
        row = QHBoxLayout()
        row.setSpacing(10)
        row.addWidget(label(_("Profile")))
        self.profile = QComboBox()
        for name in available_profiles():
            self.profile.addItem(profile_title(name), name)
        self.profile.setCurrentIndex(max(self.profile.findData(state.profile), 0))
        self.profile.currentIndexChanged.connect(lambda _index: self.refresh())
        row.addWidget(self.profile)
        row.addWidget(label(_("Source positions")))
        self.sources = QSpinBox()
        self.sources.setRange(1, 9)
        self.sources.setToolTip(
            _("Loudspeaker positions the takes were measured from (ISO 3382-2 counts them).")
        )
        self.sources.valueChanged.connect(lambda _value: self.refresh())
        row.addWidget(self.sources)
        row.addStretch(1)
        self.add_button = QPushButton(_("Add Session..."))
        self.add_button.setToolTip(_("List a saved session under a position of this project."))
        self.add_button.clicked.connect(self._choose_existing)
        row.addWidget(self.add_button)
        tools.body.addLayout(row)
        self.status = label("", "hint", wrap=True)
        tools.body.addWidget(self.status)
        layout.addWidget(tools)

        self.empty = label(
            _(
                "Open a project folder, or make one: a project is a folder with a project.json "
                "that lists the sessions saved in it by position."
            ),
            "hint",
            wrap=True,
        )
        layout.addWidget(self.empty)

        positions = Card()
        positions.body.addWidget(label(_("POSITIONS"), "section"))
        self.positions_hint = label("", "hint", wrap=True)
        positions.body.addWidget(self.positions_hint)
        self.position_rows = QVBoxLayout()
        self.position_rows.setSpacing(6)
        positions.body.addLayout(self.position_rows)
        position_actions = QHBoxLayout()
        self.remeasure_button = QPushButton(_("Measure this position again..."))
        self.remeasure_button.setToolTip(
            _("Another take at the selected position, listed under the same label.")
        )
        self.remeasure_button.clicked.connect(self._remeasure)
        position_actions.addWidget(self.remeasure_button)
        position_actions.addStretch(1)
        positions.body.addLayout(position_actions)
        self.positions_card = positions
        layout.addWidget(positions)

        takes = Card()
        takes.body.addWidget(label(_("TAKES"), "section"))
        self.table = QTableWidget(0, 9)
        self.table.setHorizontalHeaderLabels(
            [
                _("Position"),
                _("Session"),
                _("When"),
                _("Health"),
                "RT60",
                _("Clarity"),
                _("Noise"),
                _("Reflection"),
                _("Fit"),
            ]
        )
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setMinimumHeight(160)
        self.table.itemDoubleClicked.connect(self._open_row)
        self.table.itemSelectionChanged.connect(self._take_selected)
        takes.body.addWidget(self.table)
        take_actions = QHBoxLayout()
        self.open_take_button = QPushButton(_("Open result"))
        self.open_take_button.setToolTip(_("Open the selected take on the Results page."))
        self.open_take_button.clicked.connect(self._open_selected)
        self.compare_button = QPushButton(_("Compare with first position"))
        self.compare_button.setToolTip(
            _(
                "Open Compare with the first position as baseline and the selected take as candidate."
            )
        )
        self.compare_button.clicked.connect(self._compare_selected)
        take_actions.addWidget(self.open_take_button)
        take_actions.addWidget(self.compare_button)
        take_actions.addStretch(1)
        takes.body.addLayout(take_actions)
        self.takes_hint = label(
            _("Double-click a take to open it. Health and fit are judged when the page is shown."),
            "hint",
            wrap=True,
        )
        takes.body.addWidget(self.takes_hint)
        self.skipped = label("", "hint", wrap=True)
        takes.body.addWidget(self.skipped)
        self.takes_card = takes
        layout.addWidget(takes)

        average = Card()
        average.body.addWidget(label(_("SPATIAL AVERAGE"), "section"))
        self.iso_line = label("", wrap=True)
        average.body.addWidget(self.iso_line)
        self.average_table = QTableWidget(0, 6)
        self.average_table.setHorizontalHeaderLabels([_("Band"), "EDT", "T20", "T30", "RT60", "n"])
        self.average_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.average_table.verticalHeader().setVisible(False)
        self.average_table.setShowGrid(False)
        self.average_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.average_table.setMinimumHeight(120)
        average.body.addWidget(self.average_table)
        self.spread = label("", "hint", wrap=True)
        average.body.addWidget(self.spread)
        self.average_card = average
        layout.addWidget(average)

        nxt = Card()
        nxt.body.addWidget(label(_("NEXT"), "section"))
        self.next_steps = label("", wrap=True)
        self.next_steps.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        nxt.body.addWidget(self.next_steps)
        self.next_card = nxt
        layout.addWidget(nxt)
        layout.addStretch(1)
        self._show(None)

    # --- loading -------------------------------------------------------------------

    def choose(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, _("Open project folder"))
        if directory:
            self.open_path(Path(directory))

    def open_path(self, path: Path) -> bool:
        """Open ``path`` as a project; offer to make one when it is a plain folder."""
        if not is_project(path):
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Icon.Question)
            box.setWindowTitle(_("New project"))
            box.setText(_("{path} has no project.json. Make it a project?").format(path=path))
            box.setInformativeText(
                _("Sessions already saved in the folder are listed, without a position.")
            )
            yes = box.addButton(_("Make project"), QMessageBox.ButtonRole.AcceptRole)
            box.addButton(QMessageBox.StandardButton.Cancel)
            box.exec()
            if box.clickedButton() is not yes:
                return False
            return self.create_project(path)
        return self.load(path)

    def create_project(self, directory: Path, name: str = "") -> bool:
        try:
            save_project(directory, Project(name=name or directory.name))
        except ReverbScopeError as exc:
            QMessageBox.critical(self, _("Cannot create project"), localize(str(exc)))
            return False
        return self.load(directory)

    def _choose_new(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, _("Choose a folder for the project"))
        if not directory:
            return
        if is_project(directory):
            self.load(Path(directory))
            return
        self.create_project(Path(directory))

    def load(self, path: Path) -> bool:
        """Read the project at ``path`` and show its overview."""
        try:
            project = load_project(path)
            items = list_project_sessions(path)
        except ReverbScopeError as exc:
            QMessageBox.critical(self, _("Cannot open project"), localize(str(exc)))
            return False
        base = path if path.is_dir() else path.parent
        if base != self.path:
            # Another project: its latest take's profile applies again.
            self._profile_chosen = False
            self._selected_position = ""
        entries: list[ProjectEntry] = []
        skipped: list[tuple[str, str]] = []
        for position, folder in items:
            try:
                loaded = load_measurement(folder)
            except ReverbScopeError as exc:
                skipped.append((str(folder), str(exc)))
                continue
            entries.append(ProjectEntry(position, str(folder), loaded.session, loaded.result))
        self.path = base
        self._entries = entries
        self._skipped = skipped
        self._project = project
        # The profile the latest take was interpreted with, unless the user chose one.
        latest = max(entries, key=lambda item: item.session.created_at, default=None)
        if latest is not None and not self._profile_chosen:
            index = self.profile.findData(latest.session.recording_profile)
            if index >= 0:
                self.profile.blockSignals(True)
                self.profile.setCurrentIndex(index)
                self.profile.blockSignals(False)
        self._summarize()
        return True

    def refresh(self) -> None:
        """Read the project again after the user changed the profile or the sources
        (the profile combo is theirs from now on)."""
        if self.path is None:
            return
        self._profile_chosen = True
        self.load(self.path)

    def reload(self) -> None:
        """Read the project again after a take was saved or added, keeping the
        rule for the profile combo: the latest take's profile unless the user
        chose one."""
        if self.path is not None:
            self.load(self.path)

    def restyle(self) -> None:
        """Draw the cards again in the colour scheme now in force (their colours
        are set when they are made, like the Results page's)."""
        if self.overview is not None:
            self._show(self.overview)

    def _summarize(self) -> None:
        assert self._project is not None and self.path is not None
        overview = summarize_project(
            self._entries,
            str(self.profile.currentData() or "generic"),
            project_name=self._project.name or self.path.name,
            n_source_positions=int(self.sources.value()),
            skipped=self._skipped,
        )
        self._show(overview)

    def context_text(self) -> tuple[str, str]:
        if self.overview is None or self.path is None:
            return _("Project"), _("One room, several microphone positions.")
        n_sessions = sum(len(p.sessions) for p in self.overview.positions) + len(
            self.overview.unlisted
        )
        return (
            self.overview.name or self.path.name,
            _("{path}  ·  {positions} position(s), {sessions} session(s)").format(
                path=self.path, positions=len(self.overview.positions), sessions=n_sessions
            ),
        )

    # --- the workflow --------------------------------------------------------------

    def labels(self) -> list[str]:
        return [] if self.overview is None else [p.label for p in self.overview.positions]

    def current_position(self) -> str:
        return self._selected_position

    def select_position(self, position: str) -> None:
        """Select ``position``: its card, its representative take and its details."""
        if self.overview is None:
            return
        summary = next((p for p in self.overview.positions if p.label == position), None)
        if summary is None:
            return
        self._selected_position = position
        self._mark_position_cards(position)
        take = summary.representative_session
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 1)
            if item is not None and item.data(Qt.ItemDataRole.UserRole) == take.directory:
                self.table.selectRow(row)
                break
        self._show_position_detail(summary)
        self.remeasure_button.setEnabled(True)

    def _mark_position_cards(self, position: str) -> None:
        for index in range(self.position_rows.count()):
            entry = self.position_rows.itemAt(index)
            widget = entry.widget() if entry is not None else None
            if isinstance(widget, FindingCard):
                widget.set_selected(widget.topic.text() == position)

    def _show_position_detail(self, summary: PositionSummary) -> None:
        take = summary.representative_session
        rows = [
            (_("Takes"), str(len(summary.sessions))),
            (_("Representative"), Path(take.directory).name),
            (_("Health"), status_word(HealthStatus(take.health))),
            (_("Fit"), f"{fit_word(take.fit)}: {take.fit_reason}"),
        ]
        if take.rt60_s is not None:
            rows.append((_("RT60"), f"{take.rt60_s:.2f} s ({take.rt60_basis})"))
        if take.clarity_db is not None:
            rows.append((take.clarity_metric or _("Clarity"), f"{take.clarity_db:+.1f} dB"))
        if take.noise_verified and take.noise_rms_dbfs is not None:
            rows.append((_("Noise"), f"{take.noise_rms_dbfs:.1f} dBFS"))
        if take.reflection_db is not None and take.reflection_ms is not None:
            rows.append(
                (_("Reflection"), f"{take.reflection_db:.0f} dB @ {take.reflection_ms:.1f} ms")
            )
        if summary.repeat_spread_percent is not None:
            rows.append((_("Repeat spread"), f"{summary.repeat_spread_percent:.1f} %"))
        self.detail.show_rows(
            _("Position {label}").format(label=summary.label), rows, summary.verdict_text
        )

    def _choose_position(self) -> None:
        if self.path is None:
            QMessageBox.information(
                self, _("Measure a new position"), _("Open or make a project first.")
            )
            return
        dialog = NewPositionDialog(suggest_label(self.labels()), self.state.mode, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        name, mode = dialog.values()
        if not name:
            return
        self.start_position(name, mode)

    def _remeasure(self) -> None:
        if self.path is None or not self._selected_position:
            QMessageBox.information(self, _("Measure again"), _("Select a position first."))
            return
        dialog = NewPositionDialog(self._selected_position, self.state.mode, self, again=True)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        name, mode = dialog.values()
        if name:
            self.start_position(name, mode)

    def start_position(self, name: str, mode: str) -> None:
        """Measure ``name`` with ``mode``: the main window takes over."""
        self.measure_requested.emit(name, mode)

    def _choose_existing(self) -> None:
        if self.path is None:
            QMessageBox.information(self, _("Add session"), _("Open or make a project first."))
            return
        path, _filter = QFileDialog.getOpenFileName(
            self,
            _("Add a saved session to the project"),
            str(self.path),
            _("Session files (session.json);;All files (*)"),
        )
        if not path:
            return
        try:
            stored = load_session(path).measurement_position
        except ReverbScopeError as exc:
            QMessageBox.critical(self, _("Cannot add session"), localize(str(exc)))
            return
        name, ok = QInputDialog.getText(
            self,
            _("Add session"),
            _("Position label"),
            text=stored or suggest_label(self.labels()),
        )
        if ok and name.strip():
            self.add_existing(Path(path), name.strip())

    def add_existing(self, session: Path, position: str) -> bool:
        if self.path is None:
            return False
        try:
            add_session(self.path, session, position=position)
        except ReverbScopeError as exc:
            QMessageBox.critical(self, _("Cannot add session"), localize(str(exc)))
            return False
        self.reload()
        return True

    def _selected_take(self) -> SessionSummary | None:
        rows = {index.row() for index in self.table.selectedIndexes()}
        if len(rows) != 1 or self.overview is None:
            return None
        row = rows.pop()
        item = self.table.item(row, 1)
        directory = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        for take in self._takes():
            if take.directory == directory:
                return take
        return None

    def _takes(self) -> list[SessionSummary]:
        if self.overview is None:
            return []
        takes = [take for p in self.overview.positions for take in p.sessions]
        return takes + list(self.overview.unlisted)

    def _take_selected(self) -> None:
        take = self._selected_take()
        first = self.overview.positions[0] if self.overview and self.overview.positions else None
        self.compare_button.setEnabled(
            take is not None and first is not None and take.position != first.label
        )
        self.open_take_button.setEnabled(take is not None)
        if take is None:
            return
        rows = [
            (_("Position"), take.position or _("(unlisted)")),
            (_("Folder"), take.directory),
            (_("When"), str(take.created_at)[:16].replace("T", " ")),
            (_("Health"), status_word(HealthStatus(take.health))),
            (_("Fit"), f"{fit_word(take.fit)}: {take.fit_reason}"),
        ]
        if take.health_problems:
            rows.append((_("Checks"), list_join(take.health_problems)))
        if take.warnings:
            rows.append((_("Warnings"), list_join(take.warnings)))
        self.detail.show_rows(Path(take.directory).name, rows)
        if take.position and take.position != self._selected_position:
            self._selected_position = take.position
            self._mark_position_cards(take.position)
            self.remeasure_button.setEnabled(True)

    def _open_selected(self) -> None:
        take = self._selected_take()
        if take is not None:
            self.open_session.emit(take.directory)

    def _compare_selected(self) -> None:
        take = self._selected_take()
        if take is None or self.overview is None or not self.overview.positions:
            return
        baseline = self.overview.positions[0].representative_session
        self.compare_requested.emit(baseline.directory, take.directory)

    def _open_row(self, item: QTableWidgetItem) -> None:
        cell = self.table.item(item.row(), 1)
        directory = cell.data(Qt.ItemDataRole.UserRole) if cell is not None else None
        if directory:
            self.open_session.emit(str(directory))

    def overview_text(self) -> str:
        if self.overview is None:
            return ""
        return render_overview(REPORT_CONSOLE, self.overview)

    def _copy(self) -> None:
        text = self.overview_text()
        if text:
            QApplication.clipboard().setText(text)
            self.status.setText(_("Overview copied to the clipboard."))

    # --- drawing -------------------------------------------------------------------

    def _show(self, overview: ProjectOverview | None) -> None:
        self.overview = overview
        has = overview is not None
        self.empty.setVisible(not has)
        for card in (self.positions_card, self.takes_card, self.average_card, self.next_card):
            card.setVisible(has)
        for button in (self.measure_button, self.add_button, self.copy_button):
            button.setEnabled(has)
        self.compare_button.setEnabled(False)
        self.open_take_button.setEnabled(False)
        self.remeasure_button.setEnabled(False)
        if overview is None or self.path is None:
            self.header.subtitle.setText(
                _(
                    "One room, several microphone positions. Every take keeps its own folder; "
                    "the project lists which position it was taken at."
                )
            )
            self.header.subtitle.setVisible(True)
            self.changed.emit()
            return
        n_sessions = sum(len(p.sessions) for p in overview.positions) + len(overview.unlisted)
        self.header.subtitle.setText(
            _("{name}  ·  {path}  ·  {positions} position(s), {sessions} session(s)").format(
                name=overview.name or self.path.name,
                path=self.path,
                positions=len(overview.positions),
                sessions=n_sessions,
            )
        )
        self.header.subtitle.setVisible(True)
        self.status.setText("")
        self._show_positions(overview)
        self._show_takes(overview)
        self._show_average(overview)
        self.next_steps.setText("\n".join(f"→  {step}" for step in overview.next_steps))
        if self._selected_position in self.labels():
            self.select_position(self._selected_position)
        self.changed.emit()

    def _show_positions(self, overview: ProjectOverview) -> None:
        clear_layout(self.position_rows)
        if not overview.positions:
            self.positions_hint.setText(
                _(
                    "No position yet. Measure a new position, or add a saved session under a "
                    "position label."
                )
            )
            return
        self.positions_hint.setText(
            _(
                "Fit is the absence of a warning under the {profile} profile; the page does "
                "not rank positions. Click a position to select it."
            ).format(profile=profile_title(overview.profile))
        )
        for position in overview.positions:
            take = position.representative_session
            if position.repeatable is None:
                agreement = (
                    _("one take")
                    if len(position.sessions) == 1
                    else _("{n} takes, no RT60 to compare").format(n=len(position.sessions))
                )
            elif position.repeatable:
                agreement = _("{n} takes agree ({spread:.1f} % apart in RT60)").format(
                    n=len(position.sessions), spread=position.repeat_spread_percent
                )
            else:
                agreement = _("{n} takes disagree ({spread:.0f} % apart in RT60)").format(
                    n=len(position.sessions), spread=position.repeat_spread_percent
                )
            card = FindingCard(
                str(take.fit),
                position.label,
                "\n".join([agreement, take.fit_reason, position.verdict_text]),
                severity_label=fit_word(take.fit),
                clickable=True,
            )
            card.activated.connect(lambda p=position.label: self.select_position(p))
            self.position_rows.addWidget(card)

    def _show_takes(self, overview: ProjectOverview) -> None:
        rows: list[tuple[str, SessionSummary]] = [
            (p.label, take) for p in overview.positions for take in p.sessions
        ]
        rows += [(_("(unlisted)"), take) for take in overview.unlisted]
        self.table.blockSignals(True)
        self.table.setRowCount(len(rows))
        dash = "-"
        for r, (position, take) in enumerate(rows):
            health = status_word(HealthStatus(take.health))
            if take.health_problems:
                health += f" ({list_join(take.health_problems)})"
            cells = [
                position,
                Path(take.directory).name,
                str(take.created_at)[:16].replace("T", " "),
                health,
                dash if take.rt60_s is None else f"{take.rt60_s:.2f} s",
                dash
                if take.clarity_db is None
                else f"{take.clarity_metric} {take.clarity_db:+.1f} dB",
                f"{take.noise_rms_dbfs:.1f} dBFS"
                if take.noise_verified and take.noise_rms_dbfs is not None
                else dash,
                dash
                if take.reflection_db is None
                else f"{take.reflection_db:.0f} dB @ {take.reflection_ms:.1f} ms",
                fit_word(take.fit),
            ]
            for c, text in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if c == 1:
                    item.setData(Qt.ItemDataRole.UserRole, take.directory)
                    item.setToolTip(take.directory)
                if c == 8:
                    item.setToolTip(take.fit_reason)
                self.table.setItem(r, c, item)
        self.table.resizeRowsToContents()
        self.table.blockSignals(False)
        if overview.skipped:
            self.skipped.setText(
                "\n".join(
                    _("{session}: not read ({reason})").format(
                        session=Path(name).name, reason=localize(reason)
                    )
                    for name, reason in overview.skipped
                )
            )
        self.skipped.setVisible(bool(overview.skipped))

    def _show_average(self, overview: ProjectOverview) -> None:
        averaged = overview.averaged
        if averaged is None:
            self.iso_line.setText(_("No session to average yet."))
            self.average_table.setRowCount(0)
            self.spread.setText("")
            return
        self.iso_line.setText(
            _(
                "ISO 3382-2 class: {klass} ({sources} source × {mics} mic, {combos} combinations). "
                "VALID T values only; decay curves are never averaged."
            ).format(
                klass=accuracy_class_text(averaged.iso_3382_2_class),
                sources=averaged.n_source_positions,
                mics=averaged.n_microphone_positions,
                combos=averaged.n_combinations,
            )
        )
        from reverbscope.interpretation.profiles import band_text

        self.average_table.setRowCount(len(averaged.bands))
        for r, band in enumerate(averaged.bands):
            metrics = (band.edt, band.t20, band.t30, band.rt60)
            n = max(metric.count for metric in metrics)
            cells = [band_text(band.band_label)]
            for metric in metrics:
                if metric.seconds is None:
                    cells.append("-")
                elif metric.count < n:
                    cells.append(f"{metric.seconds:.2f} s ({metric.count})")
                else:
                    cells.append(f"{metric.seconds:.2f} s")
            cells.append(str(n))
            for c, text in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.average_table.setItem(r, c, item)
        self.average_table.resizeRowsToContents()
        if overview.spatial_spread_percent is None:
            self.spread.setText("")
        else:
            self.spread.setText(
                _(
                    "The positions' RT60 differ by {spread:.0f} % across the room (largest "
                    "minus smallest, over the mean)."
                ).format(spread=overview.spatial_spread_percent)
            )
