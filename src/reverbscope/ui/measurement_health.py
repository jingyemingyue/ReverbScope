"""Actionable, read-only health cards shared by Results presentations."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from reverbscope.cli.console import printable_fields
from reverbscope.i18n import _
from reverbscope.measurement_health import (
    HealthFinding,
    HealthStatus,
    MeasurementHealth,
    health_status_text,
    health_summary,
)
from reverbscope.ui.theme import tone_color
from reverbscope.ui.widgets import Card, Chip, label

HEALTH_TONE = {
    HealthStatus.GOOD: "good",
    HealthStatus.WARNING: "warn",
    HealthStatus.INVALID: "bad",
    HealthStatus.UNKNOWN: "neutral",
}


def _plain_label(text: str, role: str | None = None) -> QLabel:
    widget = label(text, role, wrap=True)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    widget.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return widget


class HealthFindingCard(QFrame):
    """Problem, why, evidence and fix; severity is a word as well as a colour."""

    def __init__(self, finding: HealthFinding, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        tone = HEALTH_TONE[finding.severity]
        self.setProperty("healthCode", finding.code)
        self.setProperty("tone", tone)
        self.setObjectName("healthFinding")
        fg, bg = tone_color(tone)
        self.setStyleSheet(
            f"QFrame#healthFinding {{ background: {bg}; border-left: 3px solid {fg}; "
            "border-radius: 6px; }"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(5)
        layout.addWidget(
            _plain_label(
                _("{severity}: {problem}").format(
                    severity=health_status_text(finding.severity), problem=finding.title
                ),
                "kpi-label",
            )
        )
        layout.addWidget(
            _plain_label(_("Why: {explanation}").format(explanation=finding.explanation))
        )
        self.evidence = _plain_label(
            _("Evidence: {evidence}").format(evidence="\n".join(finding.evidence)), "hint"
        )
        layout.addWidget(self.evidence)
        layout.addWidget(_plain_label(_("Next step: {step}").format(step=finding.next_step)))


class MeasurementHealthPanel(Card):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        top = QHBoxLayout()
        top.addWidget(_plain_label(_("Measurement Health"), "section"), 1)
        self.status = Chip()
        top.addWidget(self.status, 0, Qt.AlignmentFlag.AlignTop)
        self.body.addLayout(top)
        self.summary = _plain_label("", "hint")
        self.body.addWidget(self.summary)
        self.findings = QVBoxLayout()
        self.findings.setSpacing(8)
        self.body.addLayout(self.findings)
        self.cards: list[HealthFindingCard] = []

    def show_health(self, health: MeasurementHealth) -> None:
        health = printable_fields(health)
        self.status.setText(health_status_text(health.status))
        tone = HEALTH_TONE[health.status]
        self.status.setProperty("tone", tone)
        self.status.set_tone(tone)
        self.summary.setText(health_summary(health.status))
        while self.findings.count():
            item = self.findings.takeAt(0)
            widget = item.widget() if item is not None else None
            if widget is not None:
                widget.hide()
                widget.deleteLater()
        self.cards.clear()
        for finding in health.findings:
            card = HealthFindingCard(finding)
            self.cards.append(card)
            self.findings.addWidget(card)
