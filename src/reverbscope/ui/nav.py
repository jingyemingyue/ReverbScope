"""The navigation rail: where the window's pages are, always one click away.

Icons are drawn at run time from the colour tokens (no binary assets to
package) and drawn again when the colour scheme changes.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QButtonGroup, QFrame, QSizePolicy, QToolButton, QVBoxLayout, QWidget

from reverbscope.i18n import _
from reverbscope.ui.theme import tokens

ICON_SIZE = 24


def _pen(color: QColor, width: float) -> QPen:
    pen = QPen(color, width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return pen


def _draw_home(p: QPainter) -> None:
    path = QPainterPath()
    path.moveTo(3.5, 11.5)
    path.lineTo(12, 4)
    path.lineTo(20.5, 11.5)
    p.drawPath(path)
    body = QPainterPath()
    body.moveTo(6, 10)
    body.lineTo(6, 19.5)
    body.lineTo(10.2, 19.5)
    body.lineTo(10.2, 14.2)
    body.lineTo(13.8, 14.2)
    body.lineTo(13.8, 19.5)
    body.lineTo(18, 19.5)
    body.lineTo(18, 10)
    p.drawPath(body)


def _draw_measure(p: QPainter) -> None:
    """A decaying sine on a baseline: the sweep and the room's answer."""
    import math

    wave = QPainterPath()
    steps = 40
    for i in range(steps + 1):
        phase = i / steps
        x = 3 + 18 * phase
        y = 12 - math.sin(phase * 4.2 * math.pi) * 7.5 * math.exp(-1.7 * phase)
        if i == 0:
            wave.moveTo(QPointF(x, y))
        else:
            wave.lineTo(QPointF(x, y))
    p.drawPath(wave)
    p.drawLine(QPointF(3, 12), QPointF(21, 12))


def _draw_results(p: QPainter) -> None:
    p.drawLine(QPointF(4, 4), QPointF(4, 20))
    p.drawLine(QPointF(4, 20), QPointF(21, 20))
    line = QPainterPath()
    line.moveTo(7, 15)
    line.lineTo(11, 9.5)
    line.lineTo(14.5, 13)
    line.lineTo(20, 6)
    p.drawPath(line)


def _draw_project(p: QPainter) -> None:
    path = QPainterPath()
    path.moveTo(3.5, 7)
    path.lineTo(3.5, 18.5)
    path.lineTo(20.5, 18.5)
    path.lineTo(20.5, 9)
    path.lineTo(12, 9)
    path.lineTo(10, 6)
    path.lineTo(3.5, 6)
    path.closeSubpath()
    p.drawPath(path)


def _draw_compare(p: QPainter) -> None:
    p.drawEllipse(QRectF(3.5, 6.5, 11, 11))
    p.drawEllipse(QRectF(9.5, 6.5, 11, 11))


def _draw_settings(p: QPainter) -> None:
    for y, knob in ((7, 8.5), (12, 15.5), (17, 10.5)):
        p.drawLine(QPointF(4, y), QPointF(20, y))
        p.setBrush(p.pen().color())
        p.drawEllipse(QPointF(knob, y), 2.0, 2.0)
        p.setBrush(Qt.BrushStyle.NoBrush)


_GLYPHS: dict[str, Callable[[QPainter], None]] = {
    "home": _draw_home,
    "measure": _draw_measure,
    "results": _draw_results,
    "project": _draw_project,
    "compare": _draw_compare,
    "settings": _draw_settings,
}


def nav_icon(name: str, color: str, active: str | None = None) -> QIcon:
    """The icon ``name`` drawn with ``color`` (``active`` when its button is checked),
    at two pixel densities."""
    icon = QIcon()
    draw = _GLYPHS[name]
    for state, tint in ((QIcon.State.Off, color), (QIcon.State.On, active or color)):
        for scale in (1, 2):
            size = ICON_SIZE * scale
            pixmap = QPixmap(size, size)
            pixmap.fill(Qt.GlobalColor.transparent)
            pixmap.setDevicePixelRatio(float(scale))
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setPen(_pen(QColor(tint), 1.7))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            draw(painter)
            painter.end()
            icon.addPixmap(pixmap, QIcon.Mode.Normal, state)
    return icon


class NavRail(QFrame):
    """A column of page buttons down the left edge of the window."""

    requested = Signal(str)

    #: key, caption, tooltip; the captions are translated when the rail is built.
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("navRail")
        self.setFixedWidth(72)
        self._buttons: dict[str, QToolButton] = {}
        column = QVBoxLayout(self)
        column.setContentsMargins(0, 6, 0, 6)
        column.setSpacing(2)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        for key, caption, tip in (
            ("home", _("Home"), _("Home: start a new measurement or open a saved one")),
            ("measure", _("Measure"), _("Measure a room: Universal DAW, Standalone or Demo")),
            ("results", _("Results"), _("The result on screen")),
            ("project", _("Project"), _("One room, several microphone positions")),
            ("compare", _("Compare"), _("Compare two saved sessions")),
        ):
            column.addWidget(self._add(key, caption, tip, checkable=True))
        column.addStretch(1)
        column.addWidget(self._add("settings", _("Settings"), _("Settings"), checkable=False))
        self.restyle()

    def _add(self, key: str, caption: str, tip: str, *, checkable: bool) -> QToolButton:
        button = QToolButton()
        button.setText(caption)
        button.setToolTip(tip)
        button.setProperty("nav", True)
        button.setCheckable(checkable)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        button.setIconSize(QSize(ICON_SIZE, ICON_SIZE))
        button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        button.setFixedWidth(72)
        button.clicked.connect(lambda _checked=False, k=key: self.requested.emit(k))
        if checkable:
            self._group.addButton(button)
        self._buttons[key] = button
        return button

    def button(self, key: str) -> QToolButton:
        return self._buttons[key]

    def set_current(self, key: str | None) -> None:
        """Mark the page ``key`` as the one shown (``None``: none of the rail's)."""
        if key is None:
            self._group.setExclusive(False)
            for button in self._group.buttons():
                button.setChecked(False)
            self._group.setExclusive(True)
        elif key in self._buttons and self._buttons[key].isCheckable():
            self._buttons[key].setChecked(True)

    def set_available(self, key: str, available: bool) -> None:
        self._buttons[key].setEnabled(available)

    def restyle(self) -> None:
        """Draw the icons again in the colours of the scheme now in force."""
        t = tokens()
        for key, button in self._buttons.items():
            button.setIcon(nav_icon(key, t["muted"], t["accent"]))
