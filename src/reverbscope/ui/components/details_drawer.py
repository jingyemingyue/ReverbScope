"""An optional panel that covers the edge of the canvas without resizing it."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QToolButton, QVBoxLayout, QWidget

from reverbscope.i18n import _
from reverbscope.ui.design.tokens import DRAWER_WIDTH, SPACE


class DetailsDrawer(QFrame):
    dismissed = Signal()

    def __init__(
        self, title: str, content: QWidget, parent: QWidget, *, left: bool = False
    ) -> None:
        super().__init__(parent)
        self.left = left
        self.setProperty("drawer", True)
        self.setAutoFillBackground(True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACE, SPACE, SPACE, SPACE)
        header = QHBoxLayout()
        caption = QLabel(title)
        caption.setProperty("role", "section")
        header.addWidget(caption)
        header.addStretch()
        close = QToolButton()
        close.setText("×")
        close.setToolTip(_("Close panel"))
        close.setAccessibleName(_("Close panel"))
        close.clicked.connect(self.dismissed.emit)
        header.addWidget(close)
        layout.addLayout(header)
        content.setMinimumWidth(0)
        layout.addWidget(content, 1)
        parent.installEventFilter(self)
        self.hide()

    def set_open(self, open_: bool) -> None:
        self._place()
        self.setVisible(open_)
        if open_:
            self.raise_()

    def _place(self) -> None:
        parent = self.parentWidget()
        if parent is not None:
            width = min(DRAWER_WIDTH, max(0, parent.width() - 2 * SPACE))
            self.setGeometry(0 if self.left else parent.width() - width, 0, width, parent.height())

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if watched is self.parentWidget() and event.type() == QEvent.Type.Resize:
            self._place()
        handled: bool = super().eventFilter(watched, event)
        return handled
