"""Results page: Overview, Impulse Response, Frequency Response, Decay, Noise, Early Reflections."""

from __future__ import annotations

from pathlib import Path

from roomscope.ui.qt import ensure_pyside6

ensure_pyside6()

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from roomscope.cli.report import format_report
from roomscope.errors import RoomScopeError
from roomscope.i18n import _
from roomscope.io.recent import remember_session
from roomscope.io.session_store import save_measurement
from roomscope.io.wav import write_wav
from roomscope.models.result import PlacementResult
from roomscope.ui.plots import (
    decay_table_rows,
    plot_decay,
    plot_frequency_response,
    plot_impulse_response,
    plot_noise,
    plot_reflections,
)
from roomscope.ui.state import MeasurementState


class _PlacementTab(QWidget):
    """S5: vertical-axis figures from the tape measure and early reflections."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        self.summary = QLabel("")
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels([_("Figure"), _("Value"), _("Validity"), _("Note")])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table, 1)
        self.candidates = QTableWidget(0, 5)
        self.candidates.setHorizontalHeaderLabels(
            [
                _("Delay (ms)"),
                _("Level (dB)"),
                _("Excess path (m)"),
                _("Surface"),
                _("Plane?"),
            ]
        )
        self.candidates.horizontalHeader().setStretchLastSection(True)
        self.candidates.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.candidates, 1)
        self.notes = QPlainTextEdit()
        self.notes.setReadOnly(True)
        layout.addWidget(self.notes, 1)

    def show_placement(self, placement: PlacementResult | None) -> None:
        if placement is None:
            self.summary.setText(
                _("No placement result. Add a loudspeaker distance to raise the tier.")
            )
            self.table.setRowCount(0)
            self.candidates.setRowCount(0)
            self.notes.setPlainText("")
            return
        assumed = _(" (assumed)") if placement.temperature_assumed else ""
        self.summary.setText(
            _(
                "Placement tier {tier}. No coordinates, room length, room width or "
                "named wall are derived. Speed of sound {speed:.1f} m/s at "
                "{temp:.0f} C{assumed}."
            ).format(
                tier=placement.tier,
                speed=placement.speed_of_sound_m_s,
                temp=placement.temperature_c,
                assumed=assumed,
            )
        )
        rows = [
            (_("Loudspeaker height"), placement.source_height_m),
            (_("Plane above the devices"), placement.ceiling_height_m),
            (_("Horizontal separation"), placement.horizontal_separation_m),
        ]
        self.table.setRowCount(len(rows))
        for index, (label, length) in enumerate(rows):
            if length.metres is None:
                value = _("not determined")
                if length.missing_input:
                    value += f" ({length.missing_input})"
            else:
                value = f"{length.metres:.2f} m"
                if length.input_uncertainty_m is not None:
                    value += f" +/-{length.input_uncertainty_m:.2f}"
            note = length.reason or ""
            for column, text in enumerate((label, value, str(length.validity), note)):
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(index, column, item)
        self.table.resizeColumnsToContents()
        self.candidates.setRowCount(len(placement.candidates))
        for index, candidate in enumerate(placement.candidates):
            plane = _("yes") if candidate.interpretable_as_plane else _("no")
            if candidate.interpretable_as_plane is None:
                plane = _("untested")
            values = [
                f"{candidate.delay_ms:.2f}",
                f"{candidate.relative_db:.1f}",
                f"{candidate.excess_path_m:.2f}",
                candidate.surface or "",
                plane,
            ]
            for column, text in enumerate(values):
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.candidates.setItem(index, column, item)
        self.candidates.resizeColumnsToContents()
        notes = list(placement.notes)
        if placement.coordinates_withheld:
            notes.append(placement.coordinates_withheld)
        self.notes.setPlainText("\n".join(notes))


class _PlotTab(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.figure = Figure(figsize=(7.0, 4.5), dpi=100)
        self.canvas = FigureCanvasQTAgg(self.figure)
        layout = QVBoxLayout(self)
        layout.addWidget(self.canvas)

    def redraw(self) -> None:
        self.canvas.draw_idle()


class ResultsPage(QWidget):
    new_measurement = Signal()

    def __init__(self, state: MeasurementState, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.state = state
        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()

        overview = QWidget()
        ov_layout = QVBoxLayout(overview)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels([_("Band"), "EDT", "T20", "T30", _("RT60 estimate")])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        # The report is a column layout: a proportional font breaks its tables.
        self.text.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        ov_layout.addWidget(
            QLabel(
                _(
                    "Reverberation (extrapolated to 60 dB). 'insufficient range' means "
                    "the decay is not clean enough for that metric."
                )
            )
        )
        ov_layout.addWidget(self.table, 1)
        self.diagnostics_heading = QLabel(
            _("Full report (the core diagnostics in it are always in English):")
        )
        self.diagnostics_heading.setWordWrap(True)
        ov_layout.addWidget(self.diagnostics_heading)
        ov_layout.addWidget(self.text, 2)
        self.tabs.addTab(overview, _("Overview"))

        self.ir_tab = _PlotTab()
        self.fr_tab = _PlotTab()
        self.decay_tab = _PlotTab()
        self.noise_tab = _PlotTab()
        self.refl_tab = _PlotTab()
        self.place_tab = _PlacementTab()
        self.tabs.addTab(self.ir_tab, _("Impulse Response"))
        self.tabs.addTab(self.fr_tab, _("Frequency Response"))
        self.tabs.addTab(self.decay_tab, _("Decay"))
        self.tabs.addTab(self.noise_tab, _("Noise"))
        self.tabs.addTab(self.refl_tab, _("Early Reflections"))
        self.tabs.addTab(self.place_tab, _("Placement"))
        layout.addWidget(self.tabs, 1)

        row = QHBoxLayout()
        self.new_button = QPushButton(_("New Measurement"))
        self.new_button.clicked.connect(self.new_measurement.emit)
        self.save_button = QPushButton(_("Save Session..."))
        self.save_button.setShortcut("Ctrl+S")
        self.save_button.clicked.connect(self._choose_save_directory)
        row.addWidget(self.new_button)
        row.addStretch(1)
        row.addWidget(self.save_button)
        layout.addLayout(row)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

    def refresh(self) -> None:
        result = self.state.result
        if result is None:
            return
        rows = decay_table_rows(result)
        self.table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, value in enumerate(row):
                item = QTableWidgetItem(value)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(r, c, item)
        self.table.resizeColumnsToContents()
        self.text.setPlainText(format_report(result, self.state.findings, self.state.profile))
        plot_impulse_response(self.ir_tab.figure, result)
        plot_frequency_response(self.fr_tab.figure, result)
        plot_decay(self.decay_tab.figure, result)
        plot_noise(self.noise_tab.figure, result)
        plot_reflections(self.refl_tab.figure, result)
        self.place_tab.show_placement(result.placement)
        for tab in (self.ir_tab, self.fr_tab, self.decay_tab, self.noise_tab, self.refl_tab):
            tab.redraw()
        self.status.setText("")

    def _choose_save_directory(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, _("Choose a folder for the session"))
        if directory:
            self.save_to(Path(directory))

    def save_to(self, directory: Path) -> None:
        result = self.state.result
        if result is None:
            return
        try:
            if self.state.recording is not None and self.state.recording_path is None:
                path = write_wav(
                    directory / "recording.wav",
                    self.state.recording.samples,
                    result.sample_rate,
                    subtype="FLOAT",
                )
                self.state.session.recording_path = str(path)
            session_path = save_measurement(directory, self.state.session, result)
        except RoomScopeError as exc:
            QMessageBox.critical(self, _("Cannot save session"), str(exc))
            return
        remember_session(directory)
        self.status.setText(_("Session saved to {path}").format(path=session_path.parent))
