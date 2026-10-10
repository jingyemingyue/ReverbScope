"""Overview view: key figures with their trust level, the health, the findings, the tables.

The content of the 0.5 Results page's Overview tab, drawn from the
workspace model's current entry.
"""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from reverbscope.health import HealthStatus, affects_text, assess, status_word
from reverbscope.i18n import _
from reverbscope.interpretation import Finding
from reverbscope.interpretation.profiles import confidence_text, noise_segment_text, profile_title
from reverbscope.labels import severity_text, topic_text, validity_word
from reverbscope.models.result import AnalysisResult, Validity
from reverbscope.ui.tables import decay_table_rows, energy_table_rows
from reverbscope.ui.theme import tokens
from reverbscope.ui.views.base import AnalysisView
from reverbscope.ui.widgets import Card, Chip, FindingCard, PageHeader, StatTile, label
from reverbscope.ui.workspace import WorkspaceModel, entry_label

#: Display word and chip tone of a metric validity.
VALIDITY_DISPLAY = {
    Validity.VALID: ("valid", "good"),
    Validity.UNRELIABLE: ("unreliable", "warn"),
    Validity.INSUFFICIENT_RANGE: ("insufficient range", "warn"),
    Validity.NOT_COMPUTED: ("not computed", "neutral"),
    Validity.OUTSIDE_EXCITATION: ("outside the excitation range", "neutral"),
    Validity.NOT_COMPARABLE: ("not comparable", "warn"),
}
CONFIDENCE_TONE = {"high": "good", "medium": "info", "low": "bad"}
HEALTH_TONE = {
    HealthStatus.GOOD: "good",
    HealthStatus.WARNING: "warn",
    HealthStatus.INVALID: "bad",
    HealthStatus.UNKNOWN: "neutral",
}


def validity_text(validity: Validity) -> tuple[str, str]:
    """The translated word and colour tone shown for a validity."""
    return _validity_text(validity)


def _validity_text(validity: Validity) -> tuple[str, str]:
    _word, tone = VALIDITY_DISPLAY.get(validity, (str(validity), "neutral"))
    return validity_word(validity), tone


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

        health = Card()
        health_header = QHBoxLayout()
        health_header.addWidget(label(_("MEASUREMENT HEALTH"), "section"))
        self.health_chip = Chip("", "neutral")
        health_header.addWidget(self.health_chip)
        health_header.addStretch(1)
        health.body.addLayout(health_header)
        self.health_summary = label("", "hint", wrap=True)
        health.body.addWidget(self.health_summary)
        self.health_rows = QVBoxLayout()
        self.health_rows.setSpacing(6)
        health.body.addLayout(self.health_rows)
        layout.addWidget(health)

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

    def show_result(
        self, result: AnalysisResult, findings: list[Finding], profile: str, problem: str = ""
    ) -> None:
        """``problem`` says why there are no findings (the profile failed)."""
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
        elif refl.window_truncated and refl.analysed_window_ms is not None:
            # The response ended before the window did: later arrivals were
            # not seen, so an empty list is not a clean room (the command line
            # says the same in its At-a-glance row).
            self.reflections.show_value(
                "0",
                _(
                    "none above {threshold:.0f} dB in the {end:.1f} ms that could be searched"
                ).format(threshold=refl.threshold_db, end=refl.analysed_window_ms[1]),
                _("incomplete window"),
                "warn",
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

        self._show_health(result)
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
        if not findings and problem:
            self.findings.addWidget(
                label(
                    _("The {profile} profile could not interpret this result: {error}").format(
                        profile=profile_title(profile), error=problem
                    ),
                    "hint",
                    wrap=True,
                )
            )
        elif not findings:
            self.findings.addWidget(label(_("No findings."), "hint"))

        rows = decay_table_rows(result)
        self._fill_metric_table(self.table, rows)
        self._fill_metric_table(self.energy_table, energy_table_rows(result))

    def _show_health(self, result: AnalysisResult) -> None:
        """The measurement-health card: the overall status, the checks that
        are not good with what to do, and the names of those that are."""
        report = assess(result)
        self.health_chip.setText(status_word(report.overall).upper())
        self.health_chip.set_tone(HEALTH_TONE[report.overall])
        summary = _("{good} of {total} checks good.").format(
            good=len(report.good), total=len(report.checks)
        )
        if report.unavailable:
            summary += " " + _("Not reported: {groups}.").format(
                groups=affects_text(report.unavailable)
            )
        if report.good:
            summary += " " + _("Good: {titles}.").format(
                titles=", ".join(check.title for check in report.good)
            )
        self.health_summary.setText(summary)
        while self.health_rows.count():
            entry = self.health_rows.takeAt(0)
            widget = entry.widget() if entry is not None else None
            if widget is not None:
                widget.deleteLater()
        for check in report.problems:
            parts = [check.reason]
            if check.affects:
                parts.append(_("Affects: {groups}").format(groups=affects_text(check.affects)))
            parts.extend(check.fix)
            parts.extend(check.details)
            self.health_rows.addWidget(
                FindingCard(
                    str(check.status),
                    check.title,
                    "\n".join(parts),
                    severity_label=status_word(check.status),
                )
            )

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


class OverviewView(AnalysisView):
    view_id = "overview"

    def __init__(self, model: WorkspaceModel, parent: QWidget | None = None) -> None:
        super().__init__(model, parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 6)
        layout.setSpacing(6)
        self.header = PageHeader(_("Overview"))
        layout.addWidget(self.header)
        self.empty = label(
            _(
                "No measurement selected. Open a project or a session, or measure with the strip below."
            ),
            "hint",
            wrap=True,
        )
        layout.addWidget(self.empty)
        self.overview = _Overview()
        self.table = self.overview.table
        layout.addWidget(self.overview, 1)
        for signal in (model.current_changed, model.entries_changed):
            signal.connect(self.refresh)
        model.entry_updated.connect(self._entry_updated)

    def title(self) -> str:
        return _("Overview")

    def _entry_updated(self, key: str) -> None:
        if key == self.model.current_key:
            self.refresh()

    def redraw(self) -> None:
        entry = self.model.current()
        has = entry is not None and entry.result is not None
        self.empty.setVisible(not has)
        self.overview.setVisible(has)
        if entry is None or entry.result is None:
            self.header.title.setText(_("Overview"))
            self.header.subtitle.setText(entry.error if entry is not None else "")
            self.header.subtitle.setVisible(entry is not None and bool(entry.error))
            return
        self.header.title.setText(entry_label(entry))
        self.header.subtitle.setText(subtitle_text(entry))
        self.header.subtitle.setVisible(True)
        self.overview.show_result(
            entry.result, list(entry.findings), entry.profile, entry.findings_problem
        )


def subtitle_text(entry: object) -> str:
    """Room · position · microphone · profile · sample rate, as the 0.5 Results header."""
    from reverbscope.demo import localize_demo_name
    from reverbscope.ui.workspace import Entry

    assert isinstance(entry, Entry) and entry.result is not None
    session = entry.session
    parts: list[str] = []
    if session is not None:
        parts = [
            localize_demo_name(session.mode, part)
            for part in (session.room_name, session.measurement_position, session.microphone_name)
            if part
        ]
    parts.append(_("{profile} profile").format(profile=profile_title(entry.profile)))
    parts.append(f"{entry.result.sample_rate} Hz")
    return "  ·  ".join(parts)
