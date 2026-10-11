"""The workspace controller: opening, saving, projects and comparisons.

It changes the :class:`~reverbscope.ui.document.WorkspaceDocument` and asks
the user through dialogs owned by the window; it never draws. File formats,
project listing and the comparison itself come from ``io`` and ``core``.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QFileDialog, QInputDialog, QMessageBox, QWidget

from reverbscope.core.compare import compare
from reverbscope.errors import ReverbScopeError
from reverbscope.i18n import _, list_join, localize
from reverbscope.interpretation import available_profiles, interpret_comparison
from reverbscope.interpretation.interpreter import Finding
from reverbscope.interpretation.overview import ProjectEntry, ProjectOverview, summarize_project
from reverbscope.interpretation.verdicts import ComparisonVerdict, judge_comparison
from reverbscope.io.project_store import (
    add_session,
    is_project,
    list_project_sessions,
    load_project,
    save_project,
)
from reverbscope.io.recent import remember_session
from reverbscope.io.session_store import SESSION_FILE, load_measurement, save_measurement
from reverbscope.models.comparison import CompareSettings, ComparisonResult
from reverbscope.models.project import Project
from reverbscope.settings import load_settings
from reverbscope.ui.document import Measurement, WorkspaceDocument
from reverbscope.ui.measure_flow import safe_findings


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


@dataclass(frozen=True)
class Comparison:
    """A comparison of the baseline and a candidate, with its findings and verdict."""

    baseline_id: str
    candidate_id: str
    same_gain: bool
    result: ComparisonResult
    findings: list[Finding]
    profile: str
    verdict: ComparisonVerdict


class WorkspaceController(QObject):
    """Open, save, list and compare measurements of a document."""

    #: A sentence for the status line.
    message = Signal(str)

    def __init__(self, document: WorkspaceDocument, parent: QWidget) -> None:
        super().__init__(parent)
        self.document = document
        self._parent = parent
        self._comparisons: dict[tuple[str, str, bool], Comparison] = {}
        self.same_gain = False
        document.measurement_removed.connect(self._forget_comparisons)
        document.measurement_changed.connect(self._forget_comparisons)

    # --- opening ----------------------------------------------------------------------

    def open_session(self, path: str | Path, *, select: bool = True) -> Measurement | None:
        """Open a saved session; one already open is selected instead."""
        existing = self.document.find_by_path(Path(path))
        if existing is not None:
            if select:
                self.document.set_selected(existing.id)
            return existing
        try:
            loaded = load_measurement(path)
        except ReverbScopeError as exc:
            QMessageBox.critical(self._parent, _("Cannot open session"), localize(str(exc)))
            return None
        existing = self.document.find_by_path(loaded.directory)
        if existing is not None:
            if select:
                self.document.set_selected(existing.id)
            return existing
        measurement = self._measurement_from(loaded.session, loaded.result, loaded.directory)
        self.document.add(measurement, select=select)
        remember_session(loaded.directory)
        return measurement

    def _measurement_from(
        self,
        session: object,
        result: object,
        directory: Path,
        *,
        position: str = "",
        project: Path | None = None,
    ) -> Measurement:
        from reverbscope.models.result import AnalysisResult
        from reverbscope.models.session import MeasurementSession

        assert isinstance(session, MeasurementSession) and isinstance(result, AnalysisResult)
        profile = session.recording_profile or "generic"
        if profile not in available_profiles():
            # A profile this install does not have (a plugin, a newer version).
            profile = "generic"
        findings, problem = safe_findings(result, profile)
        return Measurement(
            session=session,
            result=result,
            findings=findings,
            findings_problem=problem,
            profile=profile,
            path=directory,
            position=position or session.measurement_position.strip(),
            # Only a session the project lists (or one added to it) belongs
            # to the project; one opened on its own beside it does not.
            project=project,
        )

    def choose_session(self) -> None:
        path, _filter = QFileDialog.getOpenFileName(
            self._parent,
            _("Open session"),
            "",
            _("Session files (session.json);;JSON files (*.json);;All files (*)"),
        )
        if path:
            self.open_session(path)

    # --- projects ---------------------------------------------------------------------

    def choose_project(self) -> None:
        directory = QFileDialog.getExistingDirectory(self._parent, _("Open project folder"))
        if directory:
            self.open_project(Path(directory))

    def new_project(self) -> None:
        directory = QFileDialog.getExistingDirectory(
            self._parent, _("Choose a folder for the project")
        )
        if not directory:
            return
        if is_project(directory):
            self.open_project(Path(directory))
            return
        self.create_project(Path(directory))

    def create_project(self, directory: Path, name: str = "") -> bool:
        try:
            save_project(directory, Project(name=name or directory.name))
        except ReverbScopeError as exc:
            QMessageBox.critical(self._parent, _("Cannot create project"), localize(str(exc)))
            return False
        return self.open_project(directory)

    def open_project(self, path: Path) -> bool:
        """Open every session of the project at ``path`` into the list, grouped
        by position; offer to make a project of a plain folder."""
        if not is_project(path):
            box = QMessageBox(self._parent)
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
        try:
            project = load_project(path)
            items = list_project_sessions(path)
        except ReverbScopeError as exc:
            QMessageBox.critical(self._parent, _("Cannot open project"), localize(str(exc)))
            return False
        base = path if path.is_dir() else path.parent
        self.document.set_project(base, project.name or base.name)
        skipped: list[str] = []
        first: Measurement | None = None
        for position, folder in items:
            existing = self.document.find_by_path(folder)
            if existing is not None:
                existing.project = base
                if position:
                    existing.position = position
                self.document.touch(existing.id)
                first = first or existing
                continue
            try:
                loaded = load_measurement(folder)
            except ReverbScopeError as exc:
                skipped.append(
                    _("{session}: not read ({reason})").format(
                        session=folder.name, reason=localize(str(exc))
                    )
                )
                continue
            measurement = self._measurement_from(
                loaded.session, loaded.result, loaded.directory, position=position, project=base
            )
            self.document.add(measurement, select=False)
            first = first or measurement
        if first is not None and self.document.selected() is None:
            self.document.set_selected(first.id)
        self.message.emit(
            _("Project {name}: {n} session(s) listed.").format(
                name=project.name or base.name, n=len(items)
            )
            + (" " + " ".join(skipped) if skipped else "")
        )
        return True

    def project_overview(
        self, profile: str, *, n_source_positions: int = 1
    ) -> ProjectOverview | None:
        """The project overview (positions, spatial average, next steps) of the
        measurements that belong to the open project, as the Project page showed it."""
        project = self.document.project
        if project is None:
            return None
        entries = [
            ProjectEntry(m.position, str(m.path), m.session, m.result)
            for m in self.document.measurements
            if m.project == project and m.path is not None
        ]
        return summarize_project(
            entries,
            profile,
            project_name=self.document.project_name or project.name,
            n_source_positions=n_source_positions,
        )

    def position_labels(self) -> list[str]:
        project = self.document.project
        labels: list[str] = []
        for m in self.document.measurements:
            listed = project is None or m.project == project
            if listed and m.position and m.position not in labels:
                labels.append(m.position)
        return labels

    def add_session_to_project(self) -> None:
        """List a saved session under a position of the open project."""
        project = self.document.project
        if project is None:
            QMessageBox.information(
                self._parent, _("Add session"), _("Open or make a project first.")
            )
            return
        path, _filter = QFileDialog.getOpenFileName(
            self._parent,
            _("Add a saved session to the project"),
            str(project),
            _("Session files (session.json);;All files (*)"),
        )
        if not path:
            return
        try:
            loaded = load_measurement(path)
        except ReverbScopeError as exc:
            QMessageBox.critical(self._parent, _("Cannot add session"), localize(str(exc)))
            return
        name, ok = QInputDialog.getText(
            self._parent,
            _("Add session"),
            _("Position label"),
            text=loaded.session.measurement_position or suggest_label(self.position_labels()),
        )
        if not ok or not name.strip():
            return
        try:
            add_session(project, loaded.directory, position=name.strip())
        except ReverbScopeError as exc:
            QMessageBox.critical(self._parent, _("Cannot add session"), localize(str(exc)))
            return
        measurement = self.open_session(loaded.directory)
        if measurement is not None:
            measurement.project = project
            measurement.position = name.strip()
            self.document.touch(measurement.id)

    # --- saving -----------------------------------------------------------------------

    def save(self, measurement_id: str | None = None) -> bool:
        """Save the measurement (the selected one by default): into the open
        project under its position, else into a folder the user chooses."""
        measurement = self.document.get(measurement_id or self.document.selected_id())
        if measurement is None:
            self.message.emit(_("No measurement selected."))
            return False
        project = measurement.project
        if project is not None:
            name, ok = QInputDialog.getText(
                self._parent,
                _("Save into the project"),
                _("Folder name inside {project}").format(project=project),
                text=self.suggested_project_folder(measurement),
            )
            if not ok or not name.strip():
                return False
            target = project / name.strip()
            if (target / SESSION_FILE).exists() and not ask_replace_session(
                self._parent, str(target)
            ):
                return False
            return self.save_to(measurement.id, target)
        directory = QFileDialog.getExistingDirectory(
            self._parent, _("Choose a folder for the session"), load_settings().output_dir
        )
        if not directory:
            return False
        # The dialog opens at the default output folder: accepting it twice
        # as offered would replace the first session without a word.
        if (Path(directory) / SESSION_FILE).exists() and not ask_replace_session(
            self._parent, directory
        ):
            return False
        return self.save_to(measurement.id, Path(directory))

    def save_to(self, measurement_id: str, directory: Path) -> bool:
        measurement = self.document.get(measurement_id)
        if measurement is None:
            return False
        try:
            # A live take has no file yet: it is written with the rest of the
            # session, so a failed save cannot overwrite the previous take.
            unsaved = measurement.recording if measurement.unsaved_take else None
            session_path = save_measurement(
                directory, measurement.session, measurement.result, recording=unsaved
            )
            if unsaved is not None:
                measurement.session.recording_path = str(directory / "recording.wav")
        except (ReverbScopeError, OSError) as exc:
            QMessageBox.critical(self._parent, _("Cannot save session"), localize(str(exc)))
            return False
        remember_session(directory)
        self.document.mark_saved(measurement_id, session_path.parent)
        for other in self.document.at_path(session_path.parent):
            if other.id != measurement_id:
                # The folder now holds this take: a measurement opened from it
                # before no longer matches what is on disk, so it is closed.
                self.document.remove(other.id)
        self.message.emit(_("Session saved to {path}").format(path=session_path.parent))
        project = measurement.project
        if project is not None:
            self._add_to_project(measurement, project, directory)
        return True

    def suggested_project_folder(self, measurement: Measurement) -> str:
        """``<position>-<n>``: the next free folder name for the position."""
        project = measurement.project
        position = self.position_label(measurement)
        stem = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in position) or "take"
        n = 1
        while project is not None and (project / f"{stem}-{n}").exists():
            n += 1
        return f"{stem}-{n}"

    def position_label(self, measurement: Measurement) -> str:
        return measurement.position or measurement.session.measurement_position.strip() or "A"

    def _add_to_project(self, measurement: Measurement, project: Path, directory: Path) -> None:
        position = self.position_label(measurement)
        try:
            listed = add_session(project, directory, position=position)
        except (ReverbScopeError, OSError) as exc:
            QMessageBox.warning(
                self._parent,
                _("Saved, but not added to the project"),
                _(
                    "The session is saved in {path}, but could not be listed in the project: "
                    "{error}"
                ).format(path=directory, error=localize(str(exc))),
            )
            return
        measurement.position = position
        self.document.touch(measurement.id)
        self.message.emit(
            _(
                "Session saved to {path} and listed in project {project} under position {label}"
            ).format(path=directory, project=listed.name or project.name, label=position)
        )

    # --- closing ----------------------------------------------------------------------

    def close_measurement(self, measurement_id: str) -> bool:
        """Remove a measurement from the workbench; a live take asks first."""
        measurement = self.document.get(measurement_id)
        if measurement is None:
            return False
        if measurement.unsaved_take and not self.ask_about_unsaved([measurement]):
            return False
        self.document.remove(measurement_id)
        return True

    def ask_to_stop_running(self) -> bool:
        """True when the user lets a take or analysis that runs now be stopped
        and lost (closing the window)."""
        box = QMessageBox(
            QMessageBox.Icon.Question,
            _("Measurement running"),
            _(
                "A take is playing or being analyzed: its recording exists only in "
                "memory and is lost if you close now."
            ),
            parent=self._parent,
        )
        stop = box.addButton(_("Stop and Close"), QMessageBox.ButtonRole.DestructiveRole)
        cancel = box.addButton(_("Cancel"), QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(cancel)
        box.setEscapeButton(cancel)
        box.exec()
        return box.clickedButton() is stop

    def ask_about_unsaved(self, takes: list[Measurement]) -> bool:
        """True when the caller may drop these live takes (saved first, or discarded)."""
        if not takes:
            return True
        names = list_join(m.name() for m in takes)
        box = QMessageBox(
            QMessageBox.Icon.Question,
            _("Unsaved measurement"),
            _("{names}: the recording exists only in memory and is lost if you continue.").format(
                names=names
            ),
            parent=self._parent,
        )
        save = box.addButton(_("Save Session..."), QMessageBox.ButtonRole.AcceptRole)
        discard = box.addButton(_("Discard"), QMessageBox.ButtonRole.DestructiveRole)
        cancel = box.addButton(_("Cancel"), QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(save)
        box.setEscapeButton(cancel)
        box.exec()
        clicked = box.clickedButton()
        if clicked is save:
            # The folder chooser may be cancelled or the save may fail: a take
            # is let go only once it is on disk.
            for measurement in takes:
                if measurement.unsaved_take and not self.save(measurement.id):
                    return False
            return True
        return clicked is discard

    # --- comparing ---------------------------------------------------------------------

    def set_same_gain(self, same_gain: bool) -> None:
        self.same_gain = same_gain

    def comparison(self) -> Comparison | None:
        """The comparison of the baseline and the selected measurement, or ``None``."""
        baseline = self.document.baseline()
        candidate = self.document.candidate()
        if baseline is None or candidate is None:
            return None
        key = (baseline.id, candidate.id, self.same_gain)
        cached = self._comparisons.get(key)
        if cached is not None:
            return cached
        try:
            result = replace(
                compare(
                    baseline.result,
                    candidate.result,
                    settings=CompareSettings(same_input_gain=self.same_gain),
                ),
                baseline_session=str(baseline.path) if baseline.path else baseline.name(),
                candidate_session=str(candidate.path) if candidate.path else candidate.name(),
            )
        except ReverbScopeError as exc:
            self.message.emit(_("Cannot compare: {error}").format(error=localize(str(exc))))
            return None
        profile = candidate.profile
        try:
            findings = interpret_comparison(result, profile)
        except ReverbScopeError:
            findings = interpret_comparison(result, "generic")
            profile = "generic"
        verdict = judge_comparison(
            result, profile, baseline=baseline.result, candidate=candidate.result
        )
        comparison = Comparison(
            baseline.id, candidate.id, self.same_gain, result, findings, profile, verdict
        )
        self._comparisons[key] = comparison
        return comparison

    def comparison_result(
        self, baseline: Measurement, candidate: Measurement
    ) -> ComparisonResult | None:
        """The comparison result for two measurements (the charts' difference view)."""
        if (
            self.document.baseline_id() == baseline.id
            and self.document.selected_id() == candidate.id
        ):
            comparison = self.comparison()
            return None if comparison is None else comparison.result
        try:
            return compare(
                baseline.result,
                candidate.result,
                settings=CompareSettings(same_input_gain=self.same_gain),
            )
        except ReverbScopeError:
            return None

    def _forget_comparisons(self, measurement_id: str) -> None:
        self._comparisons = {
            key: value for key, value in self._comparisons.items() if measurement_id not in key[:2]
        }
