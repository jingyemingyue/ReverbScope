"""Original monochrome canvas tools, with translated accessible names."""

from __future__ import annotations

from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QButtonGroup, QToolButton, QVBoxLayout, QWidget

from reverbscope.i18n import _
from reverbscope.ui.design.tokens import SPACE, TOOL_RAIL_WIDTH
from reverbscope.ui.theme import tokens


def tool_icon(name: str) -> QIcon:
    pixmap = QPixmap(24, 24)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QPen(QColor(tokens()["muted"]), 1.4))
    if name == "zoom":
        painter.drawRect(5, 5, 12, 12)
        painter.drawLine(17, 17, 21, 21)
    elif name == "fit":
        for x, y, dx, dy in ((4, 4, 1, 1), (20, 4, -1, 1), (4, 20, 1, -1), (20, 20, -1, -1)):
            painter.drawLine(x, y, x + 5 * dx, y)
            painter.drawLine(x, y, x, y + 5 * dy)
    elif name == "cursor":
        painter.drawLine(12, 3, 12, 21)
        painter.drawLine(3, 12, 21, 12)
        painter.drawEllipse(QPointF(12, 12), 3, 3)
    else:
        painter.drawLine(4, 12, 20, 12)
        painter.drawLine(12, 4, 12, 20)
        for x, y, dx, dy in ((4, 12, 1, 0), (20, 12, -1, 0), (12, 4, 0, 1), (12, 20, 0, -1)):
            painter.drawLine(x, y, x + 3 * dx + 3 * dy, y + 3 * dy + 3 * dx)
            painter.drawLine(x, y, x + 3 * dx - 3 * dy, y + 3 * dy - 3 * dx)
    painter.end()
    return QIcon(pixmap)


class ToolRail(QWidget):
    chosen = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.setProperty("toolrail", True)
        self.setFixedWidth(TOOL_RAIL_WIDTH)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACE // 2, SPACE, SPACE // 2, SPACE)
        layout.setSpacing(SPACE)
        group = QButtonGroup(self)
        group.setExclusive(True)
        self.buttons: dict[str, QToolButton] = {}
        for name, title in (
            ("cursor", _("Cursor")),
            ("pan", _("Pan")),
            ("zoom", _("Box zoom")),
            ("fit", _("Fit chart")),
        ):
            button = QToolButton()
            button.setIcon(tool_icon(name))
            button.setToolTip(title)
            button.setAccessibleName(title)
            button.setFixedSize(4 * SPACE, 4 * SPACE)
            button.setCheckable(name != "fit")
            if name != "fit":
                group.addButton(button)
            button.clicked.connect(lambda _checked=False, key=name: self.chosen.emit(key))
            layout.addWidget(button)
            self.buttons[name] = button
        self.buttons["pan"].setChecked(True)
        layout.addStretch()

    def restyle(self) -> None:
        for name, button in self.buttons.items():
            button.setIcon(tool_icon(name))
