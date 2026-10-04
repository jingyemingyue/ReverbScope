"""Compare two saved sessions: side-by-side deltas and a difference curve."""

from __future__ import annotations

from pathlib import Path

from roomscope.ui.qt import ensure_pyside6

ensure_pyside6()

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from roomscope.cli.render import REPORT_CONSOLE, render_comparison
from roomscope.core.compare import compare
from roomscope.errors import RoomScopeError
from roomscope.i18n import _, localize
from roomscope.interpretation import interpret_comparison
from roomscope.interpretation.interpreter import Finding
from roomscope.io.session_store import load_measurement, save_comparison
from roomscope.models.comparison import CompareSettings, ComparisonResult, ResonanceMatch
from roomscope.ui.browser import SessionBrowser
from roomscope.labels import metric_label, signed_number, status_text, validity_word
from roomscope.ui.theme import apply_report_font, ensure_plot_fonts, style_figure
from roomscope.ui.widgets import Card, PageHeader, ask_save_path, label, primary


def _decay_flags(match: ResonanceMatch) -> str:
    def _flag(value: bool | None) -> str:
        if value is None:
            return "—"
        return _("yes") if value else _("no")

    return f"{_flag(match.baseline_decay_distinguishable)} / {_flag(match.candidate_decay_distinguishable)}"


class ComparePage(QWidget):
    back = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._comparison: ComparisonResult | None = None
        self.setProperty("page", True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 20, 28, 14)
        layout.setSpacing(10)

        header = PageHeader(
            _("Compare two sessions"),
            _(
                "Every difference carries a validity: RoomScope says when two takes cannot "
                "be compared rather than printing a delta."
            ),
        )
        back = QPushButton(_("Back"))
        back.clicked.connect(self.back.emit)
        header.action_row.addWidget(back)
        layout.addWidget(header)

        picker = Card()
        picker.body.addWidget(
            label(_("Compare two sessions. Select two rows, or pick each path."), "hint", wrap=True)
        )
        self.browser = SessionBrowser(multi_select=True)
        self.browser.list.setMinimumHeight(90)
        self.browser.open_session.connect(self._fill_next_path)
        picker.body.addWidget(self.browser, 1)
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
        picker.body.addLayout(paths)
        buttons = QHBoxLayout()
        self.same_gain = QCheckBox(_("Input gain unchanged"))
        self.same_gain.setToolTip(
            _(
                "Required for a VALID noise delta. Leave unchecked if the preamp gain "
                "may have changed."
            )
        )
        buttons.addWidget(self.same_gain)
        buttons.addStretch(1)
        save = QPushButton(_("Save comparison.json..."))
        save.clicked.connect(self._save)
        run = primary(QPushButton(_("Compare")))
        run.setShortcut("Ctrl+Return")
        run.clicked.connect(self.run_compare)
        buttons.addWidget(save)
        buttons.addWidget(run)
        picker.body.addLayout(buttons)
        layout.addWidget(picker)

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
        # Laid out again at every draw: the chart is drawn while its tab is
        # hidden, at a size it does not keep.
        self.figure = Figure(figsize=(7.0, 3.2), dpi=100, layout="tight")
        self.canvas = FigureCanvasQTAgg(self.figure)
        style_figure(self.figure)
        chart_layout.addWidget(self.canvas, 1)
        self.band_mad = label("", "hint", wrap=True)
        chart_layout.addWidget(self.band_mad)
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setProperty("report", True)
        apply_report_font(self.text)
        self.tabs.addTab(self.table, _("Metrics"))
        self.tabs.addTab(chart, _("Frequency response difference"))
        self.tabs.addTab(self.reflections, _("Early Reflections"))
        self.tabs.addTab(self.resonances, _("Resonances"))
        self.tabs.addTab(self.text, _("Full report"))
        layout.addWidget(self.tabs, 2)
        self.status = label("", "hint", wrap=True)
        layout.addWidget(self.status)

    def set_paths(self, baseline: Path, candidate: Path) -> None:
        self.baseline_path.setText(str(baseline))
        self.candidate_path.setText(str(candidate))

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
            comparison = compare(
                left.result,
                right.result,
                settings=CompareSettings(same_input_gain=self.same_gain.isChecked()),
            )
        except RoomScopeError as exc:
            QMessageBox.critical(self, _("Cannot compare"), localize(str(exc)))
            return
        profile = right.session.recording_profile or "generic"
        try:
            findings = interpret_comparison(comparison, profile)
        except RoomScopeError:
            findings = interpret_comparison(comparison, "generic")
            profile = "generic"
        self._comparison = comparison
        self._show(comparison, findings, profile)
        self.status.setText(f"{left.directory}  vs  {right.directory}")

    def _show(self, comparison: ComparisonResult, findings: list[Finding], profile: str) -> None:
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
        self.text.setPlainText(render_comparison(REPORT_CONSOLE, comparison, findings, profile))
        self.figure.clear()
        ensure_plot_fonts()
        axes = self.figure.add_subplot(111)
        fr = comparison.frequency_response
        if fr is not None and fr.frequencies_hz.size:
            axes.semilogx(fr.frequencies_hz, fr.difference_db, linestyle="-")
            axes.set_xlabel(_("Frequency (Hz)"))
            axes.set_ylabel("Δ dB")
            axes.set_title(_("Frequency-response difference (candidate − baseline)"))
            axes.grid(True, which="both", alpha=0.3)
            if fr.band_mad_db:
                bits = ", ".join(f"{name} {mad:.2f} dB" for name, mad in fr.band_mad_db)
                self.band_mad.setText(
                    _("Mean absolute difference per octave: {bits}").format(bits=bits)
                )
            else:
                self.band_mad.setText("")
        else:
            axes.text(0.5, 0.5, _("No difference curve"), ha="center", va="center")
            axes.set_axis_off()
            self.band_mad.setText("")
        style_figure(self.figure)
        self.canvas.draw_idle()

    def _save(self) -> None:
        if self._comparison is None:
            QMessageBox.information(self, _("Save comparison"), _("Run a comparison first."))
            return
        target = ask_save_path(
            self, _("Save comparison.json"), "comparison.json", _("JSON files (*.json)")
        )
        if target is None:
            return
        path = str(target)
        if not path.lower().endswith(".json"):
            # Without the extension save_comparison takes the name for a folder.
            path += ".json"
        try:
            written = save_comparison(path, self._comparison)
        except RoomScopeError as exc:
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
