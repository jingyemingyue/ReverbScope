"""Compare two saved sessions: the verdict per aspect, the deltas, and the
curves of both takes on one scale with their difference.

The baseline and the candidate are named and coloured the same way
everywhere (baseline solid, candidate dashed); nothing is normalised per
take. The comparison and the verdicts come from ``core.compare`` and
``interpretation.verdicts``; this page only shows them.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any, cast

from reverbscope.ui.qt import ensure_pyside6

ensure_pyside6()

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PySide6.QtCore import Qt, Signal
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
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QToolButton,
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
from reverbscope.core.compare import compare
from reverbscope.errors import ReverbScopeError
from reverbscope.i18n import _, list_join, localize
from reverbscope.interpretation import interpret_comparison
from reverbscope.interpretation.interpreter import Finding
from reverbscope.interpretation.profiles import profile_title
from reverbscope.interpretation.verdicts import (
    AspectVerdict,
    ComparisonVerdict,
    judge_comparison,
    verdict_chip,
)
from reverbscope.io.session_store import load_measurement, save_comparison
from reverbscope.labels import metric_label, signed_number, status_text, validity_word
from reverbscope.models.comparison import CompareSettings, ComparisonResult, ResonanceMatch
from reverbscope.models.result import AnalysisResult
from reverbscope.ui.browser import SessionBrowser
from reverbscope.ui.plots import plot_decay_overlay, plot_frequency_overlay
from reverbscope.ui.theme import apply_report_font, ensure_plot_fonts, style_figure
from reverbscope.ui.widgets import (
    Card,
    Chip,
    FindingCard,
    KeyValueList,
    ask_save_path,
    clear_layout,
    label,
    primary,
    scroll_body,
)
from reverbscope.ui.workspace import action_row

CURVE_VIEWS = ("both", "baseline", "candidate", "difference")


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


class CompareDetail(QWidget):
    """The details pane of the Compare page: the selected aspect or delta."""

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
        layout.addStretch(1)

    def show_rows(
        self,
        heading: str,
        rows: list[tuple[str, str]],
        note: str = "",
        *,
        message: str = "",
        chip: tuple[str, str] | None = None,
    ) -> None:
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


class ComparePage(QWidget):
    back = Signal()
    #: Open one of the two sessions on the Results page.
    open_session = Signal(str)
    #: What the context bar should say for this page.
    context_changed = Signal(str, str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._comparison: ComparisonResult | None = None
        # What the tabs show, to draw it again in another colour scheme.
        self._shown: tuple[ComparisonResult, list[Finding], str, ComparisonVerdict] | None = None
        self._results: tuple[AnalysisResult, AnalysisResult] | None = None
        self._curve_view = "both"
        self._curves_dirty = False
        self.setProperty("page", True)
        layout, self.scroll_area = scroll_body(self, margins=(16, 10, 16, 8))

        # The context bar's actions.
        self.back_button = QPushButton(_("Back"))
        self.back_button.clicked.connect(self.back.emit)
        self.save_button = QPushButton(_("Save comparison.json..."))
        self.save_button.clicked.connect(self._save)
        self.run_button = primary(QPushButton(_("Compare")))
        self.run_button.setShortcut("Ctrl+Return")
        self.run_button.clicked.connect(self.run_compare)
        self.context_actions = action_row(self.back_button, self.save_button, self.run_button)
        self.detail = CompareDetail()

        picker = Card()
        picker.body.addWidget(
            label(
                _(
                    "Baseline is the take you compare against; candidate is the new one. "
                    "Select two rows (the older becomes the baseline), or pick each path."
                ),
                "hint",
                wrap=True,
            )
        )
        self.browser = SessionBrowser(multi_select=True)
        self.browser.list.setMinimumHeight(90)
        self.browser.list.setMaximumHeight(160)
        self.browser.open_session.connect(self._fill_next_path)
        picker.body.addWidget(self.browser, 1)
        paths = QHBoxLayout()
        paths.setSpacing(6)
        baseline_tag = Chip(_("BASELINE"), "info")
        candidate_tag = Chip(_("CANDIDATE"), "warn")
        self.baseline_path = QLineEdit()
        self.baseline_path.setPlaceholderText(_("Baseline session"))
        self.candidate_path = QLineEdit()
        self.candidate_path.setPlaceholderText(_("Candidate session"))
        pick_a = QPushButton(_("Baseline..."))
        pick_b = QPushButton(_("Candidate..."))
        pick_a.clicked.connect(lambda: self._pick_into(self.baseline_path))
        pick_b.clicked.connect(lambda: self._pick_into(self.candidate_path))
        swap = QPushButton("⇄")
        swap.setToolTip(_("Swap baseline and candidate"))
        swap.clicked.connect(self._swap)
        paths.addWidget(baseline_tag)
        paths.addWidget(self.baseline_path, 1)
        paths.addWidget(pick_a)
        paths.addWidget(swap)
        paths.addWidget(candidate_tag)
        paths.addWidget(self.candidate_path, 1)
        paths.addWidget(pick_b)
        picker.body.addLayout(paths)
        conditions = QHBoxLayout()
        self.same_gain = QCheckBox(_("Input gain unchanged"))
        self.same_gain.setToolTip(
            _(
                "Required for a VALID noise delta. Leave unchecked if the preamp gain "
                "may have changed."
            )
        )
        conditions.addWidget(self.same_gain)
        conditions.addStretch(1)
        self.open_baseline = QPushButton(_("Open baseline"))
        self.open_baseline.clicked.connect(lambda: self._open(self.baseline_path))
        self.open_candidate = QPushButton(_("Open candidate"))
        self.open_candidate.clicked.connect(lambda: self._open(self.candidate_path))
        conditions.addWidget(self.open_baseline)
        conditions.addWidget(self.open_candidate)
        picker.body.addLayout(conditions)
        layout.addWidget(picker)

        # Did moving help: one row per aspect under the candidate's profile.
        verdict_card = Card()
        self.verdict_title = label("", "section")
        verdict_card.body.addWidget(self.verdict_title)
        self.verdict_headline = label("", wrap=True)
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
            widget.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
            widget.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
            widget.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
            return widget

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.table = table(
            [_("Metric"), _("Baseline"), _("Candidate"), _("Delta"), "%", _("Validity")]
        )
        self.table.itemSelectionChanged.connect(self._metric_selected)
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
        curves = QWidget()
        curves_layout = QVBoxLayout(curves)
        curves_layout.setContentsMargins(0, 6, 0, 0)
        view_row = QHBoxLayout()
        view_row.setSpacing(4)
        self.view_buttons: dict[str, QToolButton] = {}
        for key, title in (
            ("both", _("Baseline and candidate")),
            ("baseline", _("Baseline")),
            ("candidate", _("Candidate")),
            ("difference", _("Difference only")),
        ):
            button = QToolButton()
            button.setText(title)
            button.setCheckable(True)
            button.setAutoExclusive(True)
            button.clicked.connect(lambda _checked=False, k=key: self._set_curve_view(k))
            view_row.addWidget(button)
            self.view_buttons[key] = button
        self.view_buttons["both"].setChecked(True)
        view_row.addStretch(1)
        curves_layout.addLayout(view_row)
        # Laid out again at every draw: the chart is drawn while its tab is
        # hidden, at a size it does not keep.
        self.figure = Figure(figsize=(7.0, 4.6), dpi=100, layout="tight")
        self.canvas: Any = cast(Any, FigureCanvasQTAgg)(self.figure)
        self.canvas.setMinimumHeight(300)
        style_figure(self.figure)
        curves_layout.addWidget(self.canvas, 1)
        self.band_mad = label("", "hint", wrap=True)
        curves_layout.addWidget(self.band_mad)
        decay = QWidget()
        decay_layout = QVBoxLayout(decay)
        decay_layout.setContentsMargins(0, 6, 0, 0)
        self.decay_figure = Figure(figsize=(7.0, 4.0), dpi=100, layout="tight")
        self.decay_canvas: Any = cast(Any, FigureCanvasQTAgg)(self.decay_figure)
        self.decay_canvas.setMinimumHeight(280)
        style_figure(self.decay_figure)
        decay_layout.addWidget(self.decay_canvas, 1)
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
        self.tabs.addTab(curves, _("Frequency response"))
        self.tabs.addTab(decay, _("Decay"))
        self.tabs.addTab(
            _with_note(self.reflections, self.reflections_note), _("Early Reflections")
        )
        self.tabs.addTab(_with_note(self.resonances, self.resonances_note), _("Resonances"))
        self.tabs.addTab(self.text, _("Full report"))
        self.tabs.currentChanged.connect(lambda _i: self._ensure_curves())
        self.tabs.setMinimumHeight(360)
        layout.addWidget(self.tabs, 2)
        self.status = label("", "hint", wrap=True)
        self.status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.status)

    # --- paths -------------------------------------------------------------------------

    def set_paths(self, baseline: Path, candidate: Path) -> None:
        self.baseline_path.setText(str(baseline))
        self.candidate_path.setText(str(candidate))

    def context_text(self) -> tuple[str, str]:
        if self._comparison is None:
            return _("Compare two sessions"), _("Every difference carries a validity.")
        return (
            _("Compare"),
            _("{baseline}  vs  {candidate}").format(
                baseline=Path(self._comparison.baseline_session or "").name or "?",
                candidate=Path(self._comparison.candidate_session or "").name or "?",
            ),
        )

    def _swap(self) -> None:
        baseline, candidate = self.baseline_path.text(), self.candidate_path.text()
        self.baseline_path.setText(candidate)
        self.candidate_path.setText(baseline)

    def _open(self, field: QLineEdit) -> None:
        path = field.text().strip()
        if path:
            self.open_session.emit(path)

    def run_compare(self) -> None:
        baseline = self.baseline_path.text().strip()
        candidate = self.candidate_path.text().strip()
        selected = self.browser.selected_pair() if not baseline or not candidate else None
        if selected is not None:
            baseline, candidate = str(selected[0]), str(selected[1])
            self.set_paths(*selected)
        if not baseline or not candidate:
            QMessageBox.information(self, _("Compare"), _("Choose two sessions first."))
            return
        try:
            left = load_measurement(baseline)
            right = load_measurement(candidate)
            # Named as `reverbscope compare` names them: `reverbscope show` lists
            # the two sessions and reads the candidate's profile from them.
            comparison = replace(
                compare(
                    left.result,
                    right.result,
                    settings=CompareSettings(same_input_gain=self.same_gain.isChecked()),
                ),
                baseline_session=str(left.directory),
                candidate_session=str(right.directory),
            )
        except ReverbScopeError as exc:
            QMessageBox.critical(self, _("Cannot compare"), localize(str(exc)))
            return
        profile = right.session.recording_profile or "generic"
        try:
            findings = interpret_comparison(comparison, profile)
        except ReverbScopeError:
            findings = interpret_comparison(comparison, "generic")
            profile = "generic"
        # Judged with both results at hand: each side's measurement health counts.
        verdict = judge_comparison(
            comparison, profile, baseline=left.result, candidate=right.result
        )
        self._comparison = comparison
        self._results = (left.result, right.result)
        self._show(comparison, findings, profile, verdict)
        self.context_changed.emit(*self.context_text())
        self.status.setText(
            _("{baseline}  vs  {candidate}").format(
                baseline=left.directory, candidate=right.directory
            )
        )

    def restyle(self) -> None:
        """Draw the comparison again in the colour scheme now in force."""
        if self._shown is not None:
            self._show(*self._shown)
        else:
            style_figure(self.figure)
            self.canvas.draw_idle()
            style_figure(self.decay_figure)
            self.decay_canvas.draw_idle()

    def _show(
        self,
        comparison: ComparisonResult,
        findings: list[Finding],
        profile: str,
        verdict: ComparisonVerdict | None = None,
    ) -> None:
        # Without the two results at hand the verdict rests on the comparison alone.
        if verdict is None:
            verdict = judge_comparison(comparison, profile)
        self._shown = (comparison, findings, profile, verdict)
        self._show_verdict(verdict)
        rows = (
            list(comparison.decay)
            + list(comparison.noise)
            + list(comparison.placement)
            + list(comparison.loopback)
        )
        self.table.blockSignals(True)
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
        self.table.blockSignals(False)
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
        fr = comparison.frequency_response
        if fr is not None and fr.band_mad_db:
            bits = list_join(f"{name} {mad:.2f} dB" for name, mad in fr.band_mad_db)
            self.band_mad.setText(
                _("Mean absolute difference per octave: {bits}").format(bits=bits)
            )
        else:
            self.band_mad.setText("")
        self._curves_dirty = True
        self._ensure_curves()
        self.detail.show_rows(
            _("Comparison"),
            [
                (_("Baseline"), comparison.baseline_session or "?"),
                (_("Candidate"), comparison.candidate_session or "?"),
                (_("Profile"), profile_title(profile)),
            ],
            verdict.headline(),
        )

    def _ensure_curves(self) -> None:
        """Draw the curve tabs when one of them is shown (not every time)."""
        if not self._curves_dirty or self._shown is None:
            return
        index = self.tabs.currentIndex()
        if index not in (1, 2):
            # Not on a curve tab: only the colours are brought up to date (a
            # theme change), the curves themselves wait until the tab is shown.
            style_figure(self.figure)
            style_figure(self.decay_figure)
            return
        comparison = self._shown[0]
        self.figure.clear()
        self.decay_figure.clear()
        ensure_plot_fonts()
        if self._results is not None:
            baseline, candidate = self._results
            plot_frequency_overlay(
                self.figure,
                baseline,
                candidate,
                comparison.frequency_response,
                view=self._curve_view,
            )
            plot_decay_overlay(self.decay_figure, baseline, candidate)
        else:
            # Only the comparison at hand (restyle after the sessions went): the
            # difference curve alone.
            axes = self.figure.add_subplot(111)
            fr = comparison.frequency_response
            if fr is not None and fr.frequencies_hz.size:
                axes.semilogx(fr.frequencies_hz, fr.difference_db, linestyle="-")
                axes.set_xlabel(_("Frequency (Hz)"))
                axes.set_ylabel("Δ dB")
                axes.set_title(_("Frequency-response difference (candidate − baseline)"))
                axes.grid(True, which="both", alpha=0.3)
            else:
                axes.text(0.5, 0.5, _("No difference curve"), ha="center", va="center")
                axes.set_axis_off()
            style_figure(self.figure)
            decay_axes = self.decay_figure.add_subplot(111)
            decay_axes.text(
                0.5, 0.5, _("No decay curves stored with this session"), ha="center", va="center"
            )
            decay_axes.set_axis_off()
            style_figure(self.decay_figure)
        self.canvas.draw_idle()
        self.decay_canvas.draw_idle()
        self._curves_dirty = False

    def _set_curve_view(self, key: str) -> None:
        self._curve_view = key
        self._curves_dirty = True
        self._ensure_curves()

    def _show_verdict(self, verdict: ComparisonVerdict) -> None:
        """The verdict card: the headline, one row per aspect, the conditions."""
        self.verdict_title.setText(
            _("VERDICT ({profile} PROFILE)").format(profile=profile_title(verdict.profile).upper())
        )
        self.verdict_headline.setText(verdict.headline())
        clear_layout(self.verdict_rows)
        for aspect in verdict.aspects:
            card = FindingCard(
                str(aspect.verdict),
                aspect.title,
                aspect.reason,
                severity_label=verdict_chip(aspect.verdict),
                clickable=True,
            )
            card.activated.connect(lambda a=aspect: self._aspect_selected(a))
            self.verdict_rows.addWidget(card)
        self.verdict_conditions.setText("\n".join(verdict.conditions))
        self.verdict_card.setVisible(bool(verdict.aspects))

    def _aspect_selected(self, aspect: AspectVerdict) -> None:
        from reverbscope.ui.results_presenter import evidence_rows
        from reverbscope.ui.widgets import SEVERITY_TONE

        self.detail.show_rows(
            aspect.title,
            evidence_rows(aspect.evidence),
            _("Judged under the candidate's recording profile from the deltas above."),
            message=aspect.reason,
            chip=(verdict_chip(aspect.verdict), SEVERITY_TONE.get(str(aspect.verdict), "neutral")),
        )

    def _metric_selected(self) -> None:
        if self._shown is None:
            return
        rows = {index.row() for index in self.table.selectedIndexes()}
        if len(rows) != 1:
            return
        comparison = self._shown[0]
        deltas = (
            list(comparison.decay)
            + list(comparison.noise)
            + list(comparison.placement)
            + list(comparison.loopback)
        )
        row = rows.pop()
        if not 0 <= row < len(deltas):
            return
        item = deltas[row]
        detail = [
            (_("Baseline"), "" if item.baseline is None else f"{item.baseline:.3f} {item.unit}"),
            (_("Candidate"), "" if item.candidate is None else f"{item.candidate:.3f} {item.unit}"),
            (
                _("Delta"),
                "" if item.delta is None else f"{signed_number(item.delta, 3)} {item.unit}",
            ),
            (_("Validity"), validity_word(item.validity)),
        ]
        if item.reason:
            detail.append((_("Reason"), localize(item.reason)))
        self.detail.show_rows(metric_label(item.name, item.unit), detail)

    def _save(self) -> None:
        if self._comparison is None:
            QMessageBox.information(self, _("Save comparison"), _("Run a comparison first."))
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
