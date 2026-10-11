"""The run status line: what runs now, how far it is, and Stop.

Fed by the measurement controller; the Stop button stays visible for the
whole take whatever the window shows. A run whose progress is unknown
(the analysis) shows a busy bar, never a percentage, and no level meter
is drawn because the audio backend reports no level.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QProgressBar, QPushButton, QWidget

from reverbscope.i18n import _


class RunStatusBar(QWidget):
    stop_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        self.activity = QLabel("")
        self.activity.setProperty("role", "hint")
        row.addWidget(self.activity)
        self.progress = QProgressBar()
        self.progress.setFixedWidth(160)
        self.progress.setTextVisible(False)
        self.progress.hide()
        row.addWidget(self.progress)
        self.stop_button = QPushButton(_("Stop"))
        self.stop_button.setProperty("danger", True)
        self.stop_button.setToolTip(_("Stop the take that is playing (Esc)."))
        self.stop_button.clicked.connect(self.stop_requested.emit)
        self.stop_button.hide()
        row.addWidget(self.stop_button)
        self._running = False

    def set_running(self, text: str, fraction: float | None, *, stoppable: bool) -> None:
        self._running = True
        self.activity.setText(text)
        self.progress.show()
        if fraction is None:
            self.progress.setRange(0, 0)
        else:
            self.progress.setRange(0, 100)
            self.progress.setValue(int(max(0.0, min(1.0, fraction)) * 100.0))
        self.stop_button.setVisible(stoppable)
        self.stop_button.setEnabled(stoppable)

    def set_idle(self, text: str = "") -> None:
        self._running = False
        self.activity.setText(text)
        self.progress.hide()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.stop_button.hide()

    def is_running(self) -> bool:
        return self._running
