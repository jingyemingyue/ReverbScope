"""One family of line icons for the desktop, drawn in code.

Every glyph is drawn on the same 24 x 24 grid with the same 1.6 px round
stroke, so the task bar, the canvas tools, the panel switches and the chart
actions read as one set. They are original drawings (no icon font or image
files are shipped); the shapes follow the common line-icon conventions of
open sets such as Lucide (ISC), whose adoption is still an open decision.

A :class:`QIcon` carries the muted colour for its normal state and the text
colour when it is checked or hovered, so an icon tracks its button's state
the way its label does.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap

from reverbscope.ui.theme import tokens

#: Device pixel ratio the icons are drawn at; Qt scales them down crisply.
_SCALE = 2
_GRID = 24

Draw = Callable[[QPainter], None]


def _lines(painter: QPainter, *points: tuple[float, float]) -> None:
    painter.drawPolyline([QPointF(x, y) for x, y in points])


def _folder(p: QPainter) -> None:
    path = QPainterPath()
    path.moveTo(3, 7)
    path.lineTo(3, 18.5)
    path.quadTo(3, 20, 4.5, 20)
    path.lineTo(19.5, 20)
    path.quadTo(21, 20, 21, 18.5)
    path.lineTo(21, 9.5)
    path.quadTo(21, 8, 19.5, 8)
    path.lineTo(12, 8)
    path.lineTo(10, 5)
    path.lineTo(4.5, 5)
    path.quadTo(3, 5, 3, 6.5)
    path.closeSubpath()
    p.drawPath(path)


def _waveform(p: QPainter) -> None:
    for x, half in ((3, 1.5), (6.6, 4.5), (10.2, 8), (13.8, 5.5), (17.4, 3), (21, 1.5)):
        p.drawLine(QPointF(x, 12 - half), QPointF(x, 12 + half))


def _chart(p: QPainter) -> None:
    _lines(p, (3, 3), (3, 21), (21, 21))
    _lines(p, (6.5, 15.5), (10, 10.5), (13.5, 13.5), (19.5, 6))


def _compare(p: QPainter) -> None:
    _lines(p, (3, 21), (21, 21))
    _lines(p, (3, 14), (7.5, 9), (12, 12), (21, 5))
    pen = QPen(p.pen())
    pen.setDashPattern([1.6, 1.8])
    p.setPen(pen)
    _lines(p, (3, 17), (7.5, 14), (12, 16.5), (21, 11))


def _save(p: QPainter) -> None:
    path = QPainterPath()
    path.moveTo(5, 3.5)
    path.lineTo(16.5, 3.5)
    path.lineTo(20.5, 7.5)
    path.lineTo(20.5, 19)
    path.quadTo(20.5, 20.5, 19, 20.5)
    path.lineTo(5, 20.5)
    path.quadTo(3.5, 20.5, 3.5, 19)
    path.lineTo(3.5, 5)
    path.quadTo(3.5, 3.5, 5, 3.5)
    p.drawPath(path)
    _lines(p, (7.5, 3.5), (7.5, 8), (15, 8), (15, 3.5))
    p.drawRect(QRectF(7, 13.5, 10, 7))


def _sliders(p: QPainter) -> None:
    for y, knob in ((6, 15), (12, 8), (18, 13)):
        p.drawLine(QPointF(3, y), QPointF(knob - 2.2, y))
        p.drawLine(QPointF(knob + 2.2, y), QPointF(21, y))
        p.drawEllipse(QPointF(knob, y), 2.2, 2.2)


def _list(p: QPainter) -> None:
    for y in (6, 12, 18):
        p.drawPoint(QPointF(4, y))
        p.drawLine(QPointF(8, y), QPointF(21, y))


def _panel_right(p: QPainter) -> None:
    p.drawRoundedRect(QRectF(3, 4, 18, 16), 2, 2)
    p.drawLine(QPointF(14.5, 4), QPointF(14.5, 20))
    for y in (8.5, 12, 15.5):
        p.drawLine(QPointF(17, y), QPointF(18.8, y))


def _crosshair(p: QPainter) -> None:
    p.drawEllipse(QPointF(12, 12), 6.5, 6.5)
    for a, b in (
        ((12, 2.5), (12, 7)),
        ((12, 17), (12, 21.5)),
        ((2.5, 12), (7, 12)),
        ((17, 12), (21.5, 12)),
    ):
        p.drawLine(QPointF(*a), QPointF(*b))


def _move(p: QPainter) -> None:
    p.drawLine(QPointF(12, 3), QPointF(12, 21))
    p.drawLine(QPointF(3, 12), QPointF(21, 12))
    _lines(p, (9, 6), (12, 3), (15, 6))
    _lines(p, (9, 18), (12, 21), (15, 18))
    _lines(p, (6, 9), (3, 12), (6, 15))
    _lines(p, (18, 9), (21, 12), (18, 15))


def _zoom(p: QPainter) -> None:
    p.drawEllipse(QPointF(10.5, 10.5), 6.5, 6.5)
    p.drawLine(QPointF(15.3, 15.3), QPointF(20.5, 20.5))
    p.drawLine(QPointF(7.5, 10.5), QPointF(13.5, 10.5))
    p.drawLine(QPointF(10.5, 7.5), QPointF(10.5, 13.5))


def _fit(p: QPainter) -> None:
    for (x, y), (dx, dy) in (
        ((3, 3), (1, 1)),
        ((21, 3), (-1, 1)),
        ((3, 21), (1, -1)),
        ((21, 21), (-1, -1)),
    ):
        _lines(p, (x, y + 5 * dy), (x, y), (x + 5 * dx, y))


def _download(p: QPainter) -> None:
    p.drawLine(QPointF(12, 3.5), QPointF(12, 15))
    _lines(p, (7.5, 10.5), (12, 15), (16.5, 10.5))
    _lines(p, (4, 15.5), (4, 19), (20, 19), (20, 15.5))


def _report(p: QPainter) -> None:
    _lines(p, (14, 3), (5.5, 3), (5.5, 21), (18.5, 21), (18.5, 7.5), (14, 3))
    _lines(p, (14, 3), (14, 7.5), (18.5, 7.5))
    for y in (12, 15, 18):
        p.drawLine(QPointF(8.5, y), QPointF(15.5, y))


def _play(p: QPainter) -> None:
    path = QPainterPath()
    path.moveTo(7, 4.5)
    path.lineTo(19, 12)
    path.lineTo(7, 19.5)
    path.closeSubpath()
    p.drawPath(path)


def _stop(p: QPainter) -> None:
    p.drawRoundedRect(QRectF(5.5, 5.5, 13, 13), 1.5, 1.5)


def _plus(p: QPainter) -> None:
    p.drawLine(QPointF(12, 5), QPointF(12, 19))
    p.drawLine(QPointF(5, 12), QPointF(19, 12))


def _open(p: QPainter) -> None:
    _folder(p)
    p.drawLine(QPointF(12, 11), QPointF(12, 17))
    _lines(p, (9.5, 13.5), (12, 11), (14.5, 13.5))


def _layers(p: QPainter) -> None:
    _lines(p, (12, 3.5), (21, 8), (12, 12.5), (3, 8), (12, 3.5))
    _lines(p, (3, 12), (12, 16.5), (21, 12))
    _lines(p, (3, 16), (12, 20.5), (21, 16))


def _help(p: QPainter) -> None:
    p.drawEllipse(QPointF(12, 12), 9, 9)
    path = QPainterPath()
    path.moveTo(9.4, 9.5)
    path.cubicTo(9.4, 6.4, 14.8, 6.4, 14.8, 9.6)
    path.cubicTo(14.8, 11.6, 12, 11.8, 12, 13.8)
    p.drawPath(path)
    p.drawPoint(QPointF(12, 17))


_GLYPHS: dict[str, Draw] = {
    "project": _folder,
    "measure": _waveform,
    "analysis": _chart,
    "compare": _compare,
    "save": _save,
    "settings": _sliders,
    "list": _list,
    "properties": _panel_right,
    "cursor": _crosshair,
    "pan": _move,
    "zoom": _zoom,
    "fit": _fit,
    "export": _download,
    "report": _report,
    "play": _play,
    "stop": _stop,
    "new": _plus,
    "open": _open,
    "layers": _layers,
    "help": _help,
}

#: Every icon name, for tests and the design notes.
ICON_NAMES = tuple(_GLYPHS)


def icon_pixmap(name: str, color: str, size: int = _GRID) -> QPixmap:
    """``name`` drawn in ``color`` at ``size`` logical pixels."""
    pixmap = QPixmap(size * _SCALE, size * _SCALE)
    pixmap.setDevicePixelRatio(_SCALE)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.scale(size / _GRID, size / _GRID)
    pen = QPen(QColor(color), 1.6)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    _GLYPHS[name](painter)
    painter.end()
    return pixmap


def icon(name: str, *, accent: bool = False) -> QIcon:
    """A themed icon: muted at rest, text colour when checked or hovered.

    ``accent`` draws the checked state in the accent colour (task bar, tools).
    """
    t = tokens()
    result = QIcon()
    rest = icon_pixmap(name, t["muted"])
    lit = icon_pixmap(name, t["accent"] if accent else t["text"])
    result.addPixmap(rest, QIcon.Mode.Normal, QIcon.State.Off)
    result.addPixmap(icon_pixmap(name, t["text"]), QIcon.Mode.Active, QIcon.State.Off)
    result.addPixmap(lit, QIcon.Mode.Normal, QIcon.State.On)
    result.addPixmap(lit, QIcon.Mode.Active, QIcon.State.On)
    result.addPixmap(icon_pixmap(name, t["border"]), QIcon.Mode.Disabled, QIcon.State.Off)
    return result
