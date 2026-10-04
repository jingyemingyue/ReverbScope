"""Results page: Overview, Impulse Response, Frequency Response, Decay, Noise, Early Reflections."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from roomscope.ui.qt import ensure_pyside6

ensure_pyside6()

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QGuiApplication
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
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

from roomscope.cli.render import REPORT_CONSOLE, render_analysis
from roomscope.errors import RoomScopeError
from roomscope.i18n import _, localize
from roomscope.io.recent import remember_session
from roomscope.io.session_store import SESSION_FILE, save_measurement
from roomscope.labels import severity_text, surface_text, topic_text, validity_word
from roomscope.interpretation import Finding
from roomscope.interpretation.profiles import (
    confidence_text,
    noise_segment_text,
    profile_title,
)
from roomscope.models.result import AnalysisResult, PlacementResult, Validity
from roomscope.settings import load_settings
from roomscope.ui.plots import (
    decay_table_rows,
    energy_table_rows,
    plot_decay,
    plot_frequency_response,
    plot_impulse_response,
    plot_noise,
    plot_placement_result,
    plot_reflections,
)
from roomscope.ui.state import MeasurementState
from roomscope.ui.theme import apply_report_font, tokens
from roomscope.ui.widgets import Card, FindingCard, PageHeader, StatTile, label, primary

#: Display word and chip tone of a metric validity.
VALIDITY_DISPLAY = {
    Validity.VALID: ("valid", "good"),
    Validity.UNRELIABLE: ("unreliable", "warn"),
    Validity.INSUFFICIENT_RANGE: ("insufficient range", "warn"),
    Validity.NOT_COMPUTED: ("not computed", "neutral"),
    Validity.OUTSIDE_EXCITATION: ("outside the sweep's range", "neutral"),
    Validity.NOT_COMPARABLE: ("not comparable", "warn"),
}
CONFIDENCE_TONE = {"high": "good", "medium": "info", "low": "bad"}


class _PlacementTab(QWidget):
    """S5: vertical-axis figures from the tape measure and early reflections."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        self.summary = QLabel("")
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        self.figure = Figure(figsize=(7.2, 3.6), dpi=100)
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.canvas.setMinimumHeight(260)
        self.scene_hint = QLabel("")
        self.scene_hint.setWordWrap(True)
        layout.addWidget(self.canvas, 2)
        layout.addWidget(self.scene_hint)
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
            self.scene_hint.setText(plot_placement_result(self.figure, None))
            self.canvas.draw_idle()
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
        for index, (caption, length) in enumerate(rows):
            if length.metres is None:
                value = _("not determined")
                if length.missing_input:
                    # The core names the CLI option; here, the field to fill in.
                    fields = {
                        "--speaker-distance": _("Loudspeaker distance"),
                        "--mic-height": _("Microphone height"),
                    }
                    value += f" ({fields.get(length.missing_input, length.missing_input)})"
            else:
                value = f"{length.metres:.2f} m"
                if length.input_uncertainty_m is not None:
                    value += f" +/-{length.input_uncertainty_m:.2f}"
            note = localize(length.reason or "")
            for column, text in enumerate((caption, value, validity_word(length.validity), note)):
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
                surface_text(candidate.surface),
                plane,
            ]
            for column, text in enumerate(values):
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.candidates.setItem(index, column, item)
        self.candidates.resizeColumnsToContents()
        notes = [localize(note) for note in placement.notes]
        if placement.coordinates_withheld:
            notes.append(localize(placement.coordinates_withheld))
        self.notes.setPlainText("\n".join(notes))
        self.scene_hint.setText(plot_placement_result(self.figure, placement))
        self.canvas.draw_idle()


class _PlotTab(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.figure = Figure(figsize=(7.0, 4.5), dpi=100)
        self.canvas = FigureCanvasQTAgg(self.figure)
        layout = QVBoxLayout(self)
        layout.addWidget(self.canvas)

    def redraw(self) -> None:
        # The plot functions lay the figure out once, for the size it has then;
        # the tight layout engine repeats that at every draw, so the axis labels
        # still fit once the tab is shown or the window is resized.
        self.figure.set_layout_engine("tight")
        self.canvas.draw_idle()


def validity_text(validity: Validity) -> tuple[str, str]:
    """The translated word and colour tone shown for a validity."""
    return _validity_text(validity)


def _validity_text(validity: Validity) -> tuple[str, str]:
    _word, tone = VALIDITY_DISPLAY.get(validity, (str(validity), "neutral"))
    return validity_word(validity), tone


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
    # By role, not by label, as in pages.ask_separate_clocks.
    return clicked is not None and box.buttonRole(clicked) == QMessageBox.ButtonRole.AcceptRole


class _Overview(QWidget):
    """Key figures with their trust level, the findings, and the decay table."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("page", True)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        body = QWidget()
        body.setProperty("page", True)
        layout = QVBoxLayout(body)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)
        scroll.setWidget(body)
        outer.addWidget(scroll)

        tiles = QHBoxLayout()
        tiles.setSpacing(10)
        self.rt60 = StatTile(_("Reverberation (RT60)"))
        self.noise = StatTile(_("Background noise"))
        self.reflections = StatTile(_("Early reflections"))
        self.direct = StatTile(_("Direct sound"))
        for tile in (self.rt60, self.noise, self.reflections, self.direct):
            tiles.addWidget(tile)
        layout.addLayout(tiles)

        self.findings_title = label("", "section")
        layout.addWidget(self.findings_title)
        self.findings = QVBoxLayout()
        self.findings.setSpacing(6)
        layout.addLayout(self.findings)

        decay = Card()
        decay.body.addWidget(label(_("REVERBERATION BY BAND"), "section"))
        decay.body.addWidget(
            label(
                _(
                    "Reverberation (extrapolated to 60 dB). 'insufficient range' means "
                    "the decay is not clean enough for that metric."
                ),
                "hint",
                wrap=True,
            )
        )
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels([_("Band"), "EDT", "T20", "T30", _("RT60 estimate")])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        decay.body.addWidget(self.table)
        layout.addWidget(decay)

        energy = Card()
        energy.body.addWidget(label(_("EARLY AND LATE ENERGY"), "section"))
        energy.body.addWidget(
            label(
                _(
                    "C50 is early energy over late energy at 50 ms (speech). C80 is the same "
                    "at 80 ms (music). D50 is the share of energy in the first 50 ms. Centre "
                    "time is the energy-weighted average time. Time zero is the detected "
                    "direct sound. A ratio is reported only when the decay range is at least "
                    "20 dB, and it is not a room score."
                ),
                "hint",
                wrap=True,
            )
        )
        self.energy_table = QTableWidget(0, 5)
        self.energy_table.setHorizontalHeaderLabels(
            [_("Band"), "C50", "C80", "D50", _("Centre time")]
        )
        self.energy_table.horizontalHeader().setStretchLastSection(True)
        self.energy_table.verticalHeader().setVisible(False)
        self.energy_table.setAlternatingRowColors(True)
        self.energy_table.setShowGrid(False)
        self.energy_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.energy_table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.energy_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        energy.body.addWidget(self.energy_table)
        layout.addWidget(energy)
        layout.addStretch(1)

    def show_result(self, result: AnalysisResult, findings: list[Finding], profile: str) -> None:
        broadband = result.decay.broadband
        if broadband.rt60_estimate_s is not None:
            word, tone = _validity_text(broadband.t30.validity)
            if broadband.rt60_basis and broadband.rt60_basis != "T30":
                word, tone = _validity_text(
                    broadband.t20.validity
                    if broadband.rt60_basis == "T20"
                    else broadband.edt.validity
                )
            self.rt60.show_value(
                f"{broadband.rt60_estimate_s:.2f} s",
                _("broadband, estimated from {basis}").format(basis=broadband.rt60_basis),
                word,
                tone,
            )
        else:
            word, tone = _validity_text(broadband.t30.validity)
            self.rt60.show_value("-", _("no reverberation time could be reported"), word, tone)

        noise = result.noise
        if noise.rms_dbfs is not None:
            hum = next((h for h in noise.hum if h.detected), None)
            chip, tone = (
                (_("hum {base:g} Hz").format(base=hum.base_hz), "warn")
                if hum is not None
                else (_("no hum"), "good")
            )
            self.noise.show_value(
                f"{noise.rms_dbfs:.1f} dBFS",
                _("RMS, {segment} segment, uncalibrated").format(
                    segment=noise_segment_text(noise.segment_source)
                ),
                chip,
                tone,
            )
        else:
            self.noise.show_value("-", _("no quiet segment to measure"), _("not computed"))

        refl = result.reflections
        if refl.reflections:
            strongest = max(refl.reflections, key=lambda r: r.relative_db)
            self.reflections.show_value(
                str(len(refl.reflections)),
                _("strongest at {delay:.1f} ms, {level:.1f} dB").format(
                    delay=strongest.delay_ms, level=strongest.relative_db
                ),
                _("above {threshold:g} dB").format(threshold=refl.threshold_db),
                "info",
            )
        else:
            self.reflections.show_value(
                "0",
                _("none above {threshold:g} dB").format(threshold=refl.threshold_db),
                _("clean"),
                "good",
            )

        ir = result.impulse_response
        margin = (
            _("pre-peak margin {margin:.1f} dB").format(margin=ir.pre_peak_margin_db)
            if ir.pre_peak_margin_db is not None
            else _("pre-peak margin not checkable")
        )
        if ir.playback_speed is not None:
            self.direct.show_value(
                confidence_text(ir.direct_sound_confidence),
                _("sweep played at {percent:.1f} % speed").format(
                    percent=ir.playback_speed.speed_ratio * 100.0
                ),
                _("wrong speed"),
                "bad",
            )
        else:
            confidence = ir.direct_sound_confidence
            self.direct.show_value(
                confidence_text(confidence),
                margin,
                _("confidence"),
                CONFIDENCE_TONE.get(confidence, "neutral"),
            )

        while self.findings.count():
            entry = self.findings.takeAt(0)
            widget = entry.widget() if entry is not None else None
            if widget is not None:
                widget.deleteLater()
        self.findings_title.setText(
            _("INTERPRETATION ({profile} PROFILE)").format(profile=profile_title(profile).upper())
        )
        for finding in findings:
            self.findings.addWidget(
                FindingCard(
                    str(finding.severity),
                    topic_text(finding.topic),
                    finding.message,
                    severity_label=severity_text(str(finding.severity)),
                )
            )
        if not findings:
            self.findings.addWidget(label(_("No findings."), "hint"))

        rows = decay_table_rows(result)
        self._fill_metric_table(self.table, rows)
        self._fill_metric_table(self.energy_table, energy_table_rows(result))

    def _fill_metric_table(self, table: QTableWidget, rows: Sequence[tuple[str, ...]]) -> None:
        colours = tokens()
        table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, value in enumerate(row):
                item = QTableWidgetItem(value)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if c > 0 and (value.startswith("(") or value == _("insufficient range")):
                    item.setForeground(QColor(colours["warn"]))
                elif c > 0 and value in {_("n/a"), "-"}:
                    item.setForeground(QColor(colours["muted"]))
                if r == 0:
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)
                table.setItem(r, c, item)
        table.resizeRowsToContents()
        height = table.horizontalHeader().height() + 2 * table.frameWidth()
        height += sum(table.rowHeight(r) for r in range(table.rowCount()))
        table.setFixedHeight(height + 2)


class ResultsPage(QWidget):
    new_measurement = Signal()

    def __init__(self, state: MeasurementState, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.state = state
        self.setProperty("page", True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 20, 28, 14)
        layout.setSpacing(10)

        self.header = PageHeader(_("Results"))
        self.new_button = QPushButton(_("New Measurement"))
        self.new_button.clicked.connect(self.new_measurement.emit)
        self.copy_button = QPushButton(_("Copy report"))
        self.copy_button.setToolTip(_("Copy the full text report to the clipboard."))
        self.copy_button.clicked.connect(self._copy_report)
        self.save_button = primary(QPushButton(_("Save Session...")))
        self.save_button.setShortcut("Ctrl+S")
        self.save_button.clicked.connect(self._choose_save_directory)
        self.header.action_row.addWidget(self.new_button)
        self.header.action_row.addWidget(self.copy_button)
        self.header.action_row.addWidget(self.save_button)
        layout.addWidget(self.header)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(False)
        self.overview = _Overview()
        self.table = self.overview.table
        self.tabs.addTab(self.overview, _("Overview"))

        report = QWidget()
        report_layout = QVBoxLayout(report)
        report_layout.setContentsMargins(14, 14, 14, 14)
        self.diagnostics_heading = label(
            _("The same report that roomscope analyze prints; warnings are at the end."),
            "hint",
            wrap=True,
        )
        report_layout.addWidget(self.diagnostics_heading)
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setProperty("report", True)
        apply_report_font(self.text)
        report_layout.addWidget(self.text, 1)
        self.tabs.addTab(report, _("Full report"))

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

        self.status = label("", "hint", wrap=True)
        layout.addWidget(self.status)

    def _copy_report(self) -> None:
        text = self.text.toPlainText().strip()
        if not text:
            self.status.setText(_("Nothing to copy yet."))
            return
        clipboard = QGuiApplication.clipboard()
        clipboard.setText(self.text.toPlainText())
        self.status.setText(_("Report copied to the clipboard."))

    def refresh(self) -> None:
        result = self.state.result
        if result is None:
            return
        session = self.state.session
        parts = [
            part
            for part in (session.room_name, session.measurement_position, session.microphone_name)
            if part
        ]
        parts.append(_("{profile} profile").format(profile=profile_title(self.state.profile)))
        parts.append(f"{result.sample_rate} Hz")
        self.header.subtitle.setText("  ·  ".join(parts))
        self.header.subtitle.setVisible(True)
        self.overview.show_result(result, list(self.state.findings), self.state.profile)
        self.text.setPlainText(
            render_analysis(REPORT_CONSOLE, result, self.state.findings, self.state.profile)
        )
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
        except RoomScopeError as exc:
            QMessageBox.critical(self, _("Cannot save session"), localize(str(exc)))
            return
        remember_session(directory)
        self.status.setText(_("Session saved to {path}").format(path=session_path.parent))
