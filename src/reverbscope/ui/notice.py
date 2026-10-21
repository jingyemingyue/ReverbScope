"""A short notice ("Session saved to …") that does not depend on the status bar.

SPEC §6 (docs/design/light-sidebar) puts a transient notice in the toolbar's
subtitle slot for four seconds. When the toolbar is too narrow to show its
title (a 960 px window with the inspector open), the same words float under
the toolbar, over the top of the canvas, instead. Neither takes the keyboard
focus or blocks the window; the status bar keeps its copy as well.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy, QToolButton, QWidget

from reverbscope.i18n import _
from reverbscope.ui import icons

#: How long a notice stays, in milliseconds (SPEC §6: four seconds).
NOTICE_MS = 4000
#: Widest the floating notice grows before its text wraps.
NOTICE_MAX_WIDTH = 560
#: Tones a notice can take, and the Lucide icon that marks each.
NOTICE_ICONS = {
    "good": "circle-check",
    "info": "info",
    "warn": "triangle-alert",
    "bad": "circle-x",
}


def notice_tone(tone: str) -> str:
    """``tone`` if a notice knows it, else ``info``."""
    return tone if tone in NOTICE_ICONS else "info"


class FloatingNotice(QFrame):
    """The notice over the top of the canvas, centred, under ``top`` px."""

    def __init__(self, host: QWidget) -> None:
        super().__init__(host)
        self.setProperty("notice", True)
        self.setProperty("tone", "good")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.top = 0
        row = QHBoxLayout(self)
        row.setContentsMargins(12, 8, 6, 8)
        row.setSpacing(8)
        self.mark = QLabel()
        self.mark.setFixedSize(16, 16)
        row.addWidget(self.mark, 0, Qt.AlignmentFlag.AlignTop)
        self.text = QLabel()
        self.text.setWordWrap(True)
        self.text.setTextFormat(Qt.TextFormat.PlainText)
        self.text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.text.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        row.addWidget(self.text, 1)
        self.close_button = QToolButton()
        self.close_button.setAutoRaise(True)
        self.close_button.setProperty("panelswitch", True)
        self.close_button.setIcon(icons.icon("x", 14))
        self.close_button.setIconSize(icons.icon_size(14))
        self.close_button.setFixedSize(22, 22)
        self.close_button.setToolTip(_("Dismiss"))
        self.close_button.setAccessibleName(_("Dismiss"))
        self.close_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.close_button.clicked.connect(self.hide)
        row.addWidget(self.close_button, 0, Qt.AlignmentFlag.AlignTop)
        self._tone = "good"
        host.installEventFilter(self)
        self.hide()

    def show_message(self, text: str, tone: str = "good") -> None:
        tone = notice_tone(tone)
        self._tone = tone
        if self.property("tone") != tone:
            self.setProperty("tone", tone)
            self.style().unpolish(self)
            self.style().polish(self)
        self.restyle_icons()
        self.text.setText(text)
        self.text.setAccessibleName(text)
        self.setToolTip(text)
        self.show()
        self.place()
        self.raise_()

    def message(self) -> str:
        """The words on screen, or ``""`` while hidden."""
        return self.text.text() if not self.isHidden() else ""

    def restyle_icons(self) -> None:
        self.mark.setPixmap(icons.icon(NOTICE_ICONS[self._tone], 16, tone=self._tone).pixmap(16))
        self.close_button.setIcon(icons.icon("x", 14))

    def place(self) -> None:
        host = self.parentWidget()
        if host is None:
            return
        width = max(0, min(NOTICE_MAX_WIDTH, host.width() - 32))
        layout = self.layout()
        assert layout is not None
        height = layout.heightForWidth(width) if layout.hasHeightForWidth() else -1
        height = max(height, layout.minimumSize().height())
        self.setGeometry((host.width() - width) // 2, self.top + 8, width, height)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802 - Qt override
        resized = watched is self.parentWidget() and event.type() == QEvent.Type.Resize
        if resized and not self.isHidden():
            self.place()
        handled: bool = super().eventFilter(watched, event)
        return handled
