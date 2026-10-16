"""Compare: the current measurement against the baseline.

The pair comes from the workspace model (the navigator's baseline and the
current entry), so measuring a new position and selecting it gives its
verdict straight away. Two saved sessions can still be picked from the
list or by path; they are opened into the workspace and compared there.
The difference curve is an interactive chart like every other.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from reverbscope.cli.render import (
    REFLECTIONS_NOT_COMPARED,
    REPORT_CONSOLE,
    RESONANCES_NARROWED,
    RESONANCES_NOT_COMPARED,
    render_comparison,
)
from reverbscope.errors import ReverbScopeError
from reverbscope.i18n import _, localize
from reverbscope.interpretation.interpreter import Finding
from reverbscope.interpretation.profiles import profile_title
from reverbscope.interpretation.verdicts import ComparisonVerdict, verdict_chip
from reverbscope.io.session_store import save_comparison
from reverbscope.labels import metric_label, signed_number, status_text, validity_word
from reverbscope.models.comparison import ComparisonResult, ResonanceMatch
from reverbscope.ui.browser import SessionBrowser
from reverbscope.ui.comparison import EntryComparison, current_comparison
from reverbscope.ui.plotkit import X_FREQUENCY, ChartPanel
from reverbscope.ui.theme import apply_report_font, tokens
from reverbscope.ui.views.base import AnalysisView
from reverbscope.ui.widgets import Card, FindingCard, ask_save_path, label, primary
from reverbscope.ui.workspace import WorkspaceModel, entry_label


def _decay_flags(match: ResonanceMatch) -> str:
    def _flag(value: bool | None) -> str:
        if value is None:
            return "—"
        return _("yes") if value else _("no")

    return f"{_flag(match.baseline_decay_distinguishable)} / {_flag(match.candidate_decay_distinguishable)}"


def _with_note(table: QTableWidget, note: QLabel) -> QWidget:
    """A tab page: ``table`` with a line of explanation (``note``) under it."""
    page = QWidget()
    box = QVBoxLayout(page)
    box.setContentsMargins(0, 0, 0, 0)
    box.addWidget(table, 1)
    box.addWidget(note)
    return page


def _notes_starting(comparison: ComparisonResult, *prefixes: str) -> str:
    """The comparison's notes that start with one of ``prefixes``, in the language shown."""
    return "\n".join(localize(note) for note in comparison.notes if note.startswith(prefixes))


class ComparePage(AnalysisView):
    """The compare view (``compare``): verdict, metrics, difference, report."""

    view_id = "compare"
    #: Open the two sessions at these paths into the workspace and compare them
    #: (the window loads them; ``(baseline, candidate)``).
    open_pair = Signal(str, str)

    def __init__(self, model: WorkspaceModel, parent: QWidget | None = None) -> None:
        super().__init__(model, parent)
        self._comparison: ComparisonResult | None = None
        self._shown: EntryComparison | None = None
        # The verdict card and the tabs do not both fit a short window: the
        # body scrolls, and the tabs never shrink below a usable height.
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body = QWidget()
        body.setProperty("page", True)
        scroll.setWidget(body)
        outer.addWidget(scroll)
        layout = QVBoxLayout(body)
        layout.setContentsMargins(14, 10, 14, 8)
        layout.setSpacing(8)

        top = QHBoxLayout()
        self.pair = label("", "section")
        self.pair.setWordWrap(True)
        top.addWidget(self.pair, 1)
        self.swap_button = QPushButton(_("Swap"))
        self.swap_button.setToolTip(_("Make the current measurement the baseline and back."))
        self.swap_button.clicked.connect(self.swap)
        top.addWidget(self.swap_button)
        self.same_gain = QCheckBox(_("Input gain unchanged"))
        self.same_gain.setToolTip(
            _(
                "Required for a VALID noise delta. Leave unchecked if the preamp gain "
                "may have changed."
            )
        )
        self.same_gain.toggled.connect(self.refresh)
        top.addWidget(self.same_gain)
        save = QPushButton(_("Save comparison.json..."))
        save.clicked.connect(self._save)
        top.addWidget(save)
        copy = QPushButton(_("Copy report"))
        copy.clicked.connect(self._copy)
        top.addWidget(copy)
        layout.addLayout(top)
        self.hint = label(
            _(
                "Every difference carries a validity: ReverbScope says when two takes cannot "
                "be compared rather than printing a delta."
            ),
            "hint",
            wrap=True,
        )
        layout.addWidget(self.hint)

        # Two saved sessions from the list or by path, for a pair not open yet.
        self.picker = Card()
        picker_head = QHBoxLayout()
        picker_head.addWidget(
            label(
                _("Compare two sessions. Select two rows, or pick each path."), "hint", wrap=True
            ),
            1,
        )
        self.picker_toggle = QPushButton(_("Hide"))
        self.picker_toggle.setCheckable(True)
        self.picker_toggle.toggled.connect(self._toggle_picker)
        self.picker_toggle.clicked.connect(lambda: setattr(self, "_picker_touched", True))
        #: The user opened or closed the picker: it stays as they left it.
        self._picker_touched = False
        picker_head.addWidget(self.picker_toggle)
        self.picker.body.addLayout(picker_head)
        self.picker_body = QWidget()
        picker_layout = QVBoxLayout(self.picker_body)
        picker_layout.setContentsMargins(0, 0, 0, 0)
        self.browser = SessionBrowser(multi_select=True)
        self.browser.list.setMinimumHeight(90)
        self.browser.open_session.connect(self._fill_next_path)
        picker_layout.addWidget(self.browser, 1)
        paths = QHBoxLayout()
        self.baseline_path = QLineEdit()
        self.baseline_path.setPlaceholderText(_("Baseline session"))
        self.candidate_path = QLineEdit()
        self.candidate_path.setPlaceholderText(_("Candidate session"))
        pick_a = QPushButton(_("Baseline..."))
        pick_b = QPushButton(_("Candidate..."))
        pick_a.clicked.connect(lambda: self._pick_into(self.baseline_path))
        pick_b.clicked.connect(lambda: self._pick_into(self.candidate_path))
        paths.addWidget(self.baseline_path)
        paths.addWidget(pick_a)
        paths.addWidget(self.candidate_path)
        paths.addWidget(pick_b)
        self.run_button = primary(QPushButton(_("Compare")))
        self.run_button.clicked.connect(self.run_compare)
        paths.addWidget(self.run_button)
        picker_layout.addLayout(paths)
        self.picker.body.addWidget(self.picker_body)
        layout.addWidget(self.picker)

        # Did moving help: one row per aspect under the candidate's profile.
        verdict_card = Card()
        self.verdict_title = label("", "section")
        verdict_card.body.addWidget(self.verdict_title)
        self.verdict_headline = label("", "hint", wrap=True)
        verdict_card.body.addWidget(self.verdict_headline)
        self.verdict_rows = QVBoxLayout()
        self.verdict_rows.setSpacing(6)
        verdict_card.body.addLayout(self.verdict_rows)
        self.verdict_conditions = label("", "hint", wrap=True)
        verdict_card.body.addWidget(self.verdict_conditions)
        verdict_card.hide()
        self.verdict_card = verdict_card
        layout.addWidget(verdict_card)

        def table(columns: list[str]) -> QTableWidget:
            widget = QTableWidget(0, len(columns))
            widget.setHorizontalHeaderLabels(columns)
            widget.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
            widget.verticalHeader().setVisible(False)
            widget.setAlternatingRowColors(True)
            widget.setShowGrid(False)
            widget.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
            return widget

        self.tabs = QTabWidget()
        self.table = table(
            [_("Metric"), _("Baseline"), _("Candidate"), _("Delta"), "%", _("Validity")]
        )
        self.reflections = table(
            [
                _("Status"),
                _("Baseline (ms / dB)"),
                _("Candidate (ms / dB)"),
                _("Δ level (dB)"),
            ]
        )
        self.resonances = table(
            [
                _("Status"),
                _("Baseline (Hz)"),
                _("Candidate (Hz)"),
                _("Decay distinguishable"),
            ]
        )
        chart = QWidget()
        chart_layout = QVBoxLayout(chart)
        chart_layout.setContentsMargins(0, 4, 0, 0)
        self.diff_chart = ChartPanel(
            X_FREQUENCY,
            x_label=_("Frequency (Hz)"),
            y_label="Δ dB",
            title=_("Frequency-response difference (candidate − baseline)"),
        )
        self.diff_chart.export_name = "comparison-difference"
        chart_layout.addWidget(self.diff_chart, 1)
        self.band_mad = label("", "hint", wrap=True)
        chart_layout.addWidget(self.band_mad)
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setProperty("report", True)
        apply_report_font(self.text)
        # A table with no rows reads as "nothing found". When a topic was not
        # compared (or only in part) the note says so under the table, as the
        # report does, instead of leaving the tab blank.
        self.reflections_note = label("", "hint", wrap=True)
        self.resonances_note = label("", "hint", wrap=True)
        self.tabs.addTab(self.table, _("Metrics"))
        self.tabs.addTab(chart, _("Frequency response difference"))
        self.tabs.addTab(
            _with_note(self.reflections, self.reflections_note), _("Early Reflections")
        )
        self.tabs.addTab(_with_note(self.resonances, self.resonances_note), _("Resonances"))
        self.tabs.addTab(self.text, _("Full report"))
        self.tabs.setMinimumHeight(340)
        layout.addWidget(self.tabs, 2)
        self.status = label("", "hint", wrap=True)
        layout.addWidget(self.status)
        for signal in (
            model.current_changed,
            model.baseline_changed,
            model.entries_changed,
        ):
            signal.connect(self.refresh)

    def title(self) -> str:
        return _("Compare")

    # --- the pair ---------------------------------------------------------------------

    def set_paths(self, baseline: Path, candidate: Path) -> None:
        self.baseline_path.setText(str(baseline))
        self.candidate_path.setText(str(candidate))

    def run_compare(self) -> None:
        """Open the picked pair into the workspace; the comparison follows."""
        baseline = self.baseline_path.text().strip()
        candidate = self.candidate_path.text().strip()
        selected = self.browser.selected_pair() if not baseline or not candidate else None
        if selected is not None:
            baseline, candidate = str(selected[0]), str(selected[1])
            self.set_paths(*selected)
        if not baseline or not candidate:
            QMessageBox.information(self, _("Compare"), _("Choose two sessions first."))
            return
        self.open_pair.emit(baseline, candidate)
        self.refresh()

    def swap(self) -> None:
        baseline = self.model.baseline_key
        current = self.model.current_key
        if baseline and current and baseline != current:
            self.model.set_baseline(current)
            self.model.set_current(baseline)

    def _toggle_picker(self, hidden: bool) -> None:
        self.picker_body.setVisible(not hidden)
        self.picker_toggle.setText(_("Show") if hidden else _("Hide"))

    # --- drawing ----------------------------------------------------------------------

    def redraw(self) -> None:
        baseline = self.model.baseline()
        current = self.model.current()
        self.swap_button.setEnabled(baseline is not None and current is not None)
        try:
            compared = current_comparison(self.model, same_gain=self.same_gain.isChecked())
        except ReverbScopeError as exc:
            compared = None
            self.status.setText(_("Cannot compare: {error}").format(error=localize(str(exc))))
        else:
            self.status.setText("")
        if compared is None:
            self._comparison = None
            self._shown = None
            if baseline is None:
                self.pair.setText(_("No baseline chosen"))
                self.hint.setText(
                    _(
                        "Right-click a measurement in the list and choose Use as baseline, then "
                        "select the measurement to compare with it. Or pick two saved sessions "
                        "below."
                    )
                )
            elif current is None or current.key == baseline.key:
                self.pair.setText(_("Baseline: {name}").format(name=entry_label(baseline)))
                self.hint.setText(_("Select another measurement in the list to compare it."))
            else:
                self.pair.setText(_("Waiting for both measurements to load."))
            self.verdict_card.hide()
            self._clear_tables()
            return
        self.pair.setText(
            _("{candidate}  against the baseline  {baseline}").format(
                candidate=entry_label(compared.candidate), baseline=entry_label(compared.baseline)
            )
        )
        self.hint.setText(
            _(
                "Every difference carries a validity: ReverbScope says when two takes cannot "
                "be compared rather than printing a delta."
            )
        )
        self._comparison = compared.comparison
        self._shown = compared
        if not self._picker_touched:
            self.picker_toggle.setChecked(True)
        self._show(compared.comparison, compared.findings, compared.profile, compared.verdict)

    def _clear_tables(self) -> None:
        for widget in (self.table, self.reflections, self.resonances):
            widget.setRowCount(0)
        self.reflections_note.setText("")
        self.resonances_note.setText("")
        self.text.setPlainText("")
        self.diff_chart.clear()
        self.diff_chart.set_message(_("No difference curve"))
        self.band_mad.setText("")

    def restyle(self) -> None:
        self.diff_chart.restyle()
        self.refresh()

    def _show(
        self,
        comparison: ComparisonResult,
        findings: list[Finding],
        profile: str,
        verdict: ComparisonVerdict,
    ) -> None:
        self._show_verdict(verdict)
        rows = (
            list(comparison.decay)
            + list(comparison.noise)
            + list(comparison.placement)
            + list(comparison.loopback)
        )
        self.table.setRowCount(len(rows))
        for r, item in enumerate(rows):
            values = [
                metric_label(item.name, item.unit),
                "" if item.baseline is None else f"{item.baseline:.3f}",
                "" if item.candidate is None else f"{item.candidate:.3f}",
                "" if item.delta is None else signed_number(item.delta, 3),
                "" if item.delta_percent is None else signed_number(item.delta_percent, 1),
                validity_word(item.validity),
            ]
            for c, value in enumerate(values):
                cell = QTableWidgetItem(value)
                cell.setFlags(cell.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if c == 0:
                    cell.setToolTip(item.name)
                if c == len(values) - 1 and item.reason:
                    # Why a delta is missing (core diagnostics, English).
                    cell.setToolTip(localize(item.reason))
                self.table.setItem(r, c, cell)
        self.table.resizeColumnsToContents()
        self.reflections.setRowCount(len(comparison.reflections))
        self.reflections_note.setText(_notes_starting(comparison, REFLECTIONS_NOT_COMPARED))

        def _pair(delay_ms: float | None, level_db: float | None) -> str:
            if delay_ms is None:
                return ""
            if level_db is None:
                return f"{delay_ms:.2f}"
            return f"{delay_ms:.2f} / {level_db:.1f}"

        for r, match in enumerate(comparison.reflections):
            baseline = _pair(match.baseline_delay_ms, match.baseline_relative_db)
            candidate = _pair(match.candidate_delay_ms, match.candidate_relative_db)
            delta = "" if match.level_delta_db is None else signed_number(match.level_delta_db, 1)
            for c, value in enumerate((status_text(match.status), baseline, candidate, delta)):
                cell = QTableWidgetItem(value)
                cell.setFlags(cell.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.reflections.setItem(r, c, cell)
        self.reflections.resizeColumnsToContents()
        self.resonances.setRowCount(len(comparison.resonances))
        self.resonances_note.setText(
            _notes_starting(comparison, RESONANCES_NOT_COMPARED, RESONANCES_NARROWED)
        )
        for r, resonance in enumerate(comparison.resonances):
            baseline_hz = "" if resonance.baseline_hz is None else f"{resonance.baseline_hz:.1f}"
            candidate_hz = "" if resonance.candidate_hz is None else f"{resonance.candidate_hz:.1f}"
            resonance_row = (
                status_text(resonance.status),
                baseline_hz,
                candidate_hz,
                _decay_flags(resonance),
            )
            for c, value in enumerate(resonance_row):
                cell = QTableWidgetItem(value)
                cell.setFlags(cell.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.resonances.setItem(r, c, cell)
        self.resonances.resizeColumnsToContents()
        self.text.setPlainText(
            render_comparison(REPORT_CONSOLE, comparison, findings, profile, verdict)
        )
        self._draw_difference(comparison)

    def _draw_difference(self, comparison: ComparisonResult) -> None:
        chart = self.diff_chart
        chart.clear()
        fr = comparison.frequency_response
        if fr is None or not fr.frequencies_hz.size:
            chart.set_message(_("No difference curve"))
            self.band_mad.setText("")
            return
        t = tokens()
        candidate = self._shown.candidate if self._shown is not None else None
        chart.add_curve(
            _("candidate − baseline"),
            fr.frequencies_hz,
            fr.difference_db,
            color=candidate.color if candidate is not None else t["accent"],
            width=1.6,
            processing=_("as computed by reverbscope compare"),
            readout=True,
        )
        chart.add_hline(0.0, color=t["muted"])
        chart.set_default_range(
            (
                max(20.0, float(fr.frequencies_hz[fr.frequencies_hz > 0].min(initial=20.0))),
                float(fr.frequencies_hz.max()),
            ),
            None,
        )
        if fr.band_mad_db:
            bits = ", ".join(f"{name} {mad:.2f} dB" for name, mad in fr.band_mad_db)
            self.band_mad.setText(
                _("Mean absolute difference per octave: {bits}").format(bits=bits)
            )
        else:
            self.band_mad.setText("")

    def _copy(self) -> None:
        text = self.text.toPlainText()
        if not text.strip():
            self.status.setText(_("Nothing to copy yet."))
            return
        QGuiApplication.clipboard().setText(text)
        self.status.setText(_("Report copied to the clipboard."))

    def _show_verdict(self, verdict: ComparisonVerdict) -> None:
        """The verdict card: the headline, one row per aspect, the conditions."""
        self.verdict_title.setText(
            _("VERDICT ({profile} PROFILE)").format(profile=profile_title(verdict.profile).upper())
        )
        self.verdict_headline.setText(verdict.headline())
        while self.verdict_rows.count():
            entry = self.verdict_rows.takeAt(0)
            widget = entry.widget() if entry is not None else None
            if widget is not None:
                widget.deleteLater()
        for aspect in verdict.aspects:
            self.verdict_rows.addWidget(
                FindingCard(
                    str(aspect.verdict),
                    aspect.title,
                    aspect.reason,
                    severity_label=verdict_chip(aspect.verdict),
                )
            )
        self.verdict_conditions.setText("\n".join(verdict.conditions))
        self.verdict_card.setVisible(bool(verdict.aspects))

    def _save(self) -> None:
        if self._comparison is None:
            QMessageBox.information(
                self, _("Save comparison"), _("Choose a baseline and a measurement to compare.")
            )
            return
        target = ask_save_path(
            self, _("Save comparison.json"), "comparison.json", _("JSON files (*.json)")
        )
        if target is None:
            return
        try:
            # Always a .json name: save_comparison takes any other for a folder.
            written = save_comparison(target, self._comparison)
        except ReverbScopeError as exc:
            QMessageBox.critical(self, _("Cannot save"), localize(str(exc)))
            return
        self.status.setText(_("Wrote {path}").format(path=written))

    def _pick_into(self, field: QLineEdit) -> None:
        path, _filter = QFileDialog.getOpenFileName(
            self,
            _("Open session"),
            "",
            _("Session files (session.json);;JSON files (*.json);;All files (*)"),
        )
        if path:
            field.setText(path)

    def _fill_next_path(self, path: str) -> None:
        if not self.baseline_path.text().strip():
            self.baseline_path.setText(path)
        else:
            self.candidate_path.setText(path)
