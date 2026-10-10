"""The overview of a result: is it trustworthy, what is wrong, what next.

The measurement health comes first and says whether the take failed, is
limited or is good; the findings of the recording profile follow, the most
important first; the next steps point at the chart or the fix behind each.
Every card can be clicked to open its chart and its evidence.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtGui import QResizeEvent
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QPushButton, QVBoxLayout, QWidget

from reverbscope.health import HealthCheck, HealthReport, HealthStatus, assess, status_word
from reverbscope.i18n import _
from reverbscope.interpretation import Finding
from reverbscope.interpretation.profiles import profile_title
from reverbscope.labels import severity_text, topic_text
from reverbscope.models.result import AnalysisResult
from reverbscope.ui.results_presenter import (
    HEALTH_TONE,
    TOP_FINDINGS,
    check_group,
    check_message,
    finding_group,
    group_title,
    health_summary,
    key_figures,
    main_problems,
    next_steps,
    ranked_checks,
    ranked_findings,
    trust_text,
)
from reverbscope.ui.widgets import (
    Card,
    Chip,
    FindingCard,
    StatTile,
    clear_layout,
    flat,
    label,
    scroll_body,
    set_banner_text,
)


class Overview(QWidget):
    """Key figures with their trust level, the health, the findings, the next steps."""

    #: An analysis group to open (a key of :data:`results_presenter.GROUPS`).
    group_requested = Signal(str)
    #: A finding (its index in the state's list) was clicked.
    finding_selected = Signal(int)
    #: A health check was clicked.
    check_selected = Signal(object)

    def __init__(self, parent: QWidget | None = None, *, with_tiles: bool = True) -> None:
        super().__init__(parent)
        layout, self.scroll_area = scroll_body(self, margins=(10, 8, 10, 8))
        layout.setSpacing(8)
        self._with_tiles = with_tiles
        self._report: HealthReport | None = None
        self._findings: list[Finding] = []
        self._show_all = False

        trust = Card()
        self.trust_banner = label("", wrap=True)
        trust.body.addWidget(label(_("Is this measurement trustworthy?").upper(), "section"))
        trust.body.addWidget(self.trust_banner)
        health_header = QHBoxLayout()
        health_header.addWidget(label(_("MEASUREMENT HEALTH"), "section"))
        self.health_chip = Chip("", "neutral", glyph=True)
        health_header.addWidget(self.health_chip)
        health_header.addStretch(1)
        trust.body.addLayout(health_header)
        self.health_rows = QVBoxLayout()
        self.health_rows.setSpacing(6)
        trust.body.addLayout(self.health_rows)
        self.health_summary = label("", "hint", wrap=True)
        trust.body.addWidget(self.health_summary)
        layout.addWidget(trust)

        self.tiles_grid = QGridLayout()
        self.tiles_grid.setSpacing(8)
        self.rt60 = StatTile(_("Reverberation (RT60)"))
        self.noise = StatTile(_("Background noise"))
        self.reflections = StatTile(_("Early reflections"))
        self.direct = StatTile(_("Direct sound"))
        self.tiles = {
            "rt60": self.rt60,
            "noise": self.noise,
            "reflections": self.reflections,
            "direct": self.direct,
        }
        self._tile_groups: dict[str, str] = {}
        self._tile_columns = 0
        for key, tile in self.tiles.items():
            tile.activated.connect(lambda k=key: self._tile_clicked(k))
        if with_tiles:
            self._lay_out_tiles(4)
            layout.addLayout(self.tiles_grid)

        problems = Card()
        problems.body.addWidget(label(_("What are the main problems?").upper(), "section"))
        self.findings_title = label("", "hint", wrap=True)
        problems.body.addWidget(self.findings_title)
        # The page puts its "About this profile..." button here, under the title.
        self.profile_row = QHBoxLayout()
        self.profile_row.addStretch(1)
        problems.body.addLayout(self.profile_row)
        self.findings = QVBoxLayout()
        self.findings.setSpacing(6)
        problems.body.addLayout(self.findings)
        more = QHBoxLayout()
        self.show_all_button = flat(QPushButton(""))
        self.show_all_button.clicked.connect(self._toggle_all)
        self.show_all_button.hide()
        more.addWidget(self.show_all_button)
        more.addStretch(1)
        problems.body.addLayout(more)
        layout.addWidget(problems)

        steps = Card()
        steps.body.addWidget(label(_("What next?").upper(), "section"))
        self.next_steps = QVBoxLayout()
        self.next_steps.setSpacing(4)
        steps.body.addLayout(self.next_steps)
        layout.addWidget(steps)
        layout.addStretch(1)

    def _lay_out_tiles(self, columns: int) -> None:
        """Four tiles in a row where they fit, two by two where they do not."""
        if columns == self._tile_columns:
            return
        self._tile_columns = columns
        for tile in self.tiles.values():
            self.tiles_grid.removeWidget(tile)
        for index, tile in enumerate(self.tiles.values()):
            self.tiles_grid.addWidget(tile, index // columns, index % columns)

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802 - Qt override
        super().resizeEvent(event)
        if not self._with_tiles:
            return
        needed = sum(tile.minimumSizeHint().width() for tile in self.tiles.values()) + 3 * 8 + 40
        self._lay_out_tiles(4 if self.scroll_area.viewport().width() >= needed else 2)

    def show_result(
        self, result: AnalysisResult, findings: list[Finding], profile: str, problem: str = ""
    ) -> None:
        """``problem`` says why there are no findings (the profile failed)."""
        for key, figure in key_figures(result).items():
            tile = self.tiles[key]
            tile.show_value(figure.value, figure.sub, figure.chip, figure.tone)
            tile.setToolTip(_("Open {chart}").format(chart=group_title(figure.group)))
            self._tile_groups[key] = figure.group
        report = assess(result)
        self._report = report
        self._findings = list(findings)
        self._show_health(report)
        self.findings_title.setText(main_problems(findings, problem, profile_title(profile)))
        self._show_findings()
        clear_layout(self.next_steps)
        for sentence, group in next_steps(report, findings):
            row = QHBoxLayout()
            row.setSpacing(6)
            row.addWidget(label(f"→  {sentence}", wrap=True), 1)
            if group is not None:
                button = flat(QPushButton(_("Open")))
                button.clicked.connect(lambda _checked=False, g=group: self.group_requested.emit(g))
                row.addWidget(button)
            self.next_steps.addLayout(row)
        if not self.next_steps.count():
            self.next_steps.addWidget(
                label(_("Nothing to do: save the session or compare it."), "hint")
            )

    def _show_health(self, report: HealthReport) -> None:
        """The trust sentence, the checks that are not good (worst first,
        each with what to do), and the names of those that are."""
        sentence, tone = trust_text(report)
        set_banner_text(self.trust_banner, sentence, tone)
        self.health_chip.setText(status_word(report.overall).upper())
        self.health_chip.set_tone(HEALTH_TONE[report.overall])
        self.health_summary.setText(health_summary(report))
        clear_layout(self.health_rows)
        for check in ranked_checks(report):
            card = FindingCard(
                str(check.status),
                check.title,
                check_message(check),
                severity_label=status_word(check.status),
                clickable=True,
            )
            card.activated.connect(lambda c=check: self._check_clicked(c))
            self.health_rows.addWidget(card)

    def _check_clicked(self, check: HealthCheck) -> None:
        self.check_selected.emit(check)
        group = check_group(check)
        if group is not None and check.status is not HealthStatus.INVALID:
            self.group_requested.emit(group)

    def _show_findings(self) -> None:
        clear_layout(self.findings)
        ranked = ranked_findings(self._findings)
        shown = ranked if self._show_all else ranked[:TOP_FINDINGS]
        for index, finding in shown:
            card = FindingCard(
                str(finding.severity),
                topic_text(finding.topic),
                finding.message,
                severity_label=severity_text(str(finding.severity)),
                clickable=True,
            )
            card.activated.connect(lambda i=index: self._finding_clicked(i))
            self.findings.addWidget(card)
        if not self._findings:
            self.findings.addWidget(label(_("No findings."), "hint"))
        hidden = len(ranked) - len(shown)
        if hidden > 0:
            self.show_all_button.setText(_("Show all {n} findings").format(n=len(ranked)))
            self.show_all_button.show()
        elif self._show_all and len(ranked) > TOP_FINDINGS:
            self.show_all_button.setText(_("Show the most important only"))
            self.show_all_button.show()
        else:
            self.show_all_button.hide()

    def _tile_clicked(self, key: str) -> None:
        group = self._tile_groups.get(key)
        if group is not None:
            self.group_requested.emit(group)

    def _toggle_all(self) -> None:
        self._show_all = not self._show_all
        self._show_findings()

    def _finding_clicked(self, index: int) -> None:
        self.finding_selected.emit(index)
        if 0 <= index < len(self._findings):
            group = finding_group(self._findings[index])
            if group is not None:
                self.group_requested.emit(group)
