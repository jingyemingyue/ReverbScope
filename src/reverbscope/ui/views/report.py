"""Report view: the text report ``reverbscope analyze`` prints, for the current entry.

Under the report, the command lines for what only the CLI does yet (CSV
export, the bug-report bundle, analysing an impulse response from another
tool, the synthetic demo), filled in with the current session's folder and
ready to copy (SPEC §19 "report and export": GUI and CLI shown apart).
"""

from __future__ import annotations

import shlex
import sys
from pathlib import Path

from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QHBoxLayout, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget

from reverbscope.cli.render import REPORT_CONSOLE, render_analysis
from reverbscope.i18n import _
from reverbscope.ui import icons
from reverbscope.ui.theme import apply_report_font
from reverbscope.ui.views.base import AnalysisView
from reverbscope.ui.widgets import label
from reverbscope.ui.workspace import WorkspaceModel

#: Stands for the session folder while the measurement is not saved yet.
SESSION_PLACEHOLDER = "SESSION"


def shell_quote(text: str, *, windows: bool | None = None) -> str:
    """``text`` as one shell word: double quotes on Windows, POSIX quoting elsewhere."""
    if windows is None:
        windows = sys.platform == "win32"
    if windows:
        return f'"{text}"' if any(c in text for c in ' \t&()^%!;,"') else text
    return shlex.quote(text)


def cli_commands(session: Path | None, *, windows: bool | None = None) -> list[str]:
    """The CLI-only features as command lines, for ``session`` (or a placeholder)."""
    folder = shell_quote(str(session), windows=windows) if session else SESSION_PLACEHOLDER
    return [
        f"reverbscope export {folder} --format csv",
        f"reverbscope session bundle {folder}",
        "reverbscope analyze-ir --ir IMPULSE.wav --band 20 20000",
        "reverbscope demo",
    ]


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

        # What only the command line does yet, so it can be found from here.
        # The commands are literal (never translated) and name this session.
        layout.addWidget(label(_("Command line only"), "section"))
        cli_row = QHBoxLayout()
        self.commands_hint = label("", "hint", wrap=True)
        cli_row.addWidget(self.commands_hint, 1)
        self.copy_commands_button = QPushButton(_("Copy commands"))
        self.copy_commands_button.setIcon(icons.icon("copy", 16))
        self.copy_commands_button.setToolTip(_("Copy these command lines to the clipboard."))
        self.copy_commands_button.clicked.connect(self.copy_commands)
        cli_row.addWidget(self.copy_commands_button)
        layout.addLayout(cli_row)
        self.commands = QPlainTextEdit()
        self.commands.setReadOnly(True)
        self.commands.setProperty("commands", True)
        self.commands.setAccessibleName(_("Command-line equivalents"))
        self.commands.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        apply_report_font(self.commands)
        lines = len(cli_commands(None))
        self.commands.setFixedHeight(lines * self.commands.fontMetrics().lineSpacing() + 24)
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

    def session_folder(self) -> Path | None:
        """The current measurement's saved folder, or ``None`` while unsaved."""
        entry = self.model.current()
        return entry.directory if entry is not None and entry.directory else None

    def command_lines(self) -> str:
        return "\n".join(cli_commands(self.session_folder()))

    def _commands_hint(self) -> str:
        hint = _(
            "Not in the desktop yet: CSV export, a zip for a bug report, an impulse "
            "response from another tool (set --band to its sweep's band), the demo."
        )
        if self.session_folder() is None:
            hint += " " + _("Save the session first: {placeholder} stands for its folder.").format(
                placeholder=SESSION_PLACEHOLDER
            )
        return hint

    def redraw(self) -> None:
        self.text.setPlainText(self.report_text())
        self.commands.setPlainText(self.command_lines())
        self.commands_hint.setText(self._commands_hint())
        self.status.setText("")

    def restyle(self) -> None:
        self.copy_commands_button.setIcon(icons.icon("copy", 16))
        super().restyle()

    def copy(self) -> None:
        text = self.report_text()
        if not text.strip():
            self.status.setText(_("Nothing to copy yet."))
            return
        QGuiApplication.clipboard().setText(text)
        self.status.setText(_("Report copied to the clipboard."))

    def copy_commands(self) -> None:
        QGuiApplication.clipboard().setText(self.command_lines() + "\n")
        self.status.setText(_("Commands copied to the clipboard."))
