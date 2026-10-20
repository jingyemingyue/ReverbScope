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
        layout.setContentsMargins(24, 20, 24, 16)
        row = QHBoxLayout()
        row.addWidget(
            label(
                _("Full measurement report, including validity, conditions and warnings."),
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
        # What only the command line does yet, named here so it can be found:
        # the commands are literal (not translated), filled with this session.
        layout.addWidget(
            label(
                _(
                    "From the command line: every curve and table as CSV, the session "
                    "as a zip for a bug report, and an impulse response from another tool."
                ),
                "hint",
                wrap=True,
            )
        )
        self.commands = QPlainTextEdit()
        self.commands.setReadOnly(True)
        self.commands.setProperty("commands", True)
        self.commands.setAccessibleName(_("Command-line equivalents"))
        apply_report_font(self.commands)
        self.commands.setFixedHeight(4 * self.commands.fontMetrics().lineSpacing() + 18)
        layout.addWidget(self.commands)
        for signal in (model.current_changed, model.entries_changed):
            signal.connect(self.refresh)

    def title(self) -> str:
        return _("Full report")

    def report_text(self) -> str:
        entry = self.model.current()
        if entry is None or entry.result is None:
            return ""
        return render_analysis(REPORT_CONSOLE, entry.result, entry.findings, entry.profile)

    def command_lines(self) -> str:
        """The CLI commands for what the desktop does not do yet."""
        entry = self.model.current()
        folder = entry.directory if entry is not None and entry.directory else None
        session = str(folder) if folder is not None else "SESSION"
        if " " in session:
            # Double quotes work in every shell ReverbScope runs from.
            session = f'"{session}"'
        return "\n".join(
            (
                f"reverbscope export {session} --format csv",
                f"reverbscope session bundle {session}",
                "reverbscope analyze-ir --ir IMPULSE.wav --band 20 20000",
            )
        )

    def redraw(self) -> None:
        self.text.setPlainText(self.report_text())
        self.commands.setPlainText(self.command_lines())
        self.status.setText("")

    def copy(self) -> None:
        text = self.report_text()
        if not text.strip():
            self.status.setText(_("Nothing to copy yet."))
            return
        QGuiApplication.clipboard().setText(text)
        self.status.setText(_("Report copied to the clipboard."))
