"""A short notice over the bottom of the canvas: "Session saved to …".

The status bar at the bottom edge is easy to miss, and a layout without one
(the focused desktop may drop it) loses saves silently. The notice floats
above the canvas, says what happened in words with a tone mark, stays for a
few seconds and can be dismissed. It never takes the keyboard focus.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Qt, QTimer
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QToolButton, QWidget

from reverbscope.i18n import _
from reverbscope.ui.design.tokens import SPACE

#: How long a notice stays, in milliseconds.
NOTICE_MS = 6000
#: Widest a notice grows before its text wraps.
NOTICE_MAX_WIDTH = 640


class Notice(QFrame):
    """A transient, dismissible message anchored to the bottom of ``host``."""

    def __init__(self, host: QWidget) -> None:
        super().__init__(host)
        self.setProperty("notice", True)
        self.setProperty("tone", "good")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        row = QHBoxLayout(self)
        row.setContentsMargins(2 * SPACE, SPACE, SPACE, SPACE)
        row.setSpacing(SPACE + SPACE // 2)
        self.mark = QLabel()
        self.mark.setProperty("role", "notice-mark")
        row.addWidget(self.mark, 0, Qt.AlignmentFlag.AlignVCenter)
        self.text = QLabel()
        self.text.setWordWrap(True)
        self.text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.text.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(self.text, 1)
        self.close_button = QToolButton()
        self.close_button.setText("×")
        self.close_button.setToolTip(_("Dismiss"))
        self.close_button.setAccessibleName(_("Dismiss"))
        self.close_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.close_button.clicked.connect(self.hide)
        row.addWidget(self.close_button, 0, Qt.AlignmentFlag.AlignVCenter)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)
        host.installEventFilter(self)
        self.hide()

    def show_message(self, text: str, tone: str = "good", *, timeout_ms: int = NOTICE_MS) -> None:
        """Show ``text`` (tone ``good``, ``info``, ``warn`` or ``bad``) for ``timeout_ms``."""
        marks = {"good": _("Done"), "info": _("Note"), "warn": _("Check"), "bad": _("Error")}
        self.setProperty("tone", tone if tone in marks else "info")
        self.mark.setText(marks.get(tone, marks["info"]))
        self.text.setText(text)
        self.setToolTip(text)
        for widget in (self, self.mark):
            widget.style().unpolish(widget)
            widget.style().polish(widget)
        self.show()
        self._place()
        self.raise_()
        self._timer.start(timeout_ms)

    def message(self) -> str:
        """The text on screen, or ``""`` when no notice is shown."""
        return self.text.text() if self.isVisible() else ""

    def _place(self) -> None:
        host = self.parentWidget()
        if host is None:
            return
        width = min(NOTICE_MAX_WIDTH, max(0, host.width() - 4 * SPACE))
        layout = self.layout()
        assert layout is not None
        height = layout.heightForWidth(width) if layout.hasHeightForWidth() else -1
        height = max(height, layout.minimumSize().height())
        self.setGeometry(
            (host.width() - width) // 2, host.height() - height - 2 * SPACE, width, height
        )

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        resized = watched is self.parentWidget() and event.type() == QEvent.Type.Resize
        if resized and self.isVisible():
            self._place()
        handled: bool = super().eventFilter(watched, event)
        return handled
