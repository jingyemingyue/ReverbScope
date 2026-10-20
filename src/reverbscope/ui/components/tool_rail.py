"""Canvas tools (cursor, pan, box zoom, fit) with translated names.

The icons come from :mod:`reverbscope.ui.components.icons`; each tooltip
names the tool and says what a drag does, so the rail is discoverable
without reading the manual.
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QButtonGroup, QFrame, QToolButton, QVBoxLayout, QWidget

from reverbscope.i18n import _
from reverbscope.ui.components.icons import icon
from reverbscope.ui.design.tokens import SPACE, TOOL_RAIL_WIDTH


def tool_icon(name: str) -> QIcon:
    """The canvas tool ``name`` from the desktop's one icon family."""
    return icon(name, accent=True)


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
        for name, title, hint in (
            ("cursor", _("Cursor"), _("Read values under the pointer")),
            ("pan", _("Pan"), _("Drag to move, scroll to zoom")),
            ("zoom", _("Box zoom"), _("Drag a box to zoom into it")),
            ("fit", _("Fit chart"), _("Show all data")),
        ):
            if name == "fit":
                rule = QFrame()
                rule.setProperty("rule", True)
                rule.setFixedHeight(1)
                layout.addWidget(rule)
            button = QToolButton()
            button.setIcon(tool_icon(name))
            button.setIconSize(QSize(20, 20))
            button.setToolTip(f"<b>{title}</b><br>{hint}")
            button.setAccessibleName(title)
            button.setProperty("tool", True)
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
