"""Report view: the text report ``reverbscope analyze`` prints, for the current entry."""

from __future__ import annotations

from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QHBoxLayout, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget

from reverbscope.cli.render import REPORT_CONSOLE, render_analysis
from reverbscope.i18n import _
from reverbscope.ui.theme import apply_report_font
from reverbscope.ui.views.base import AnalysisView
from reverbscope.ui.widgets import label
from reverbscope.ui.workspace import WorkspaceModel


class ReportView(AnalysisView):
    view_id = "report"

    def __init__(self, model: WorkspaceModel, parent: QWidget | None = None) -> None:
        super().__init__(model, parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        row = QHBoxLayout()
        row.addWidget(
            label(
                _("The same report that reverbscope analyze prints; warnings are at the end."),
                "hint",
                wrap=True,
            ),
            1,
        )
        self.copy_button = QPushButton(_("Copy report"))
        self.copy_button.setToolTip(_("Copy the full text report to the clipboard."))
        self.copy_button.clicked.connect(self.copy)
        row.addWidget(self.copy_button)
        layout.addLayout(row)
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setProperty("report", True)
        apply_report_font(self.text)
        layout.addWidget(self.text, 1)
        self.status = label("", "hint", wrap=True)
        layout.addWidget(self.status)
        for signal in (model.current_changed, model.entries_changed):
            signal.connect(self.refresh)

    def title(self) -> str:
        return _("Full report")

    def report_text(self) -> str:
        entry = self.model.current()
        if entry is None or entry.result is None:
            return ""
        return render_analysis(REPORT_CONSOLE, entry.result, entry.findings, entry.profile)

    def redraw(self) -> None:
        self.text.setPlainText(self.report_text())
        self.status.setText("")

    def copy(self) -> None:
        text = self.report_text()
        if not text.strip():
            self.status.setText(_("Nothing to copy yet."))
            return
        QGuiApplication.clipboard().setText(text)
        self.status.setText(_("Report copied to the clipboard."))
