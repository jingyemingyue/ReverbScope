"""Small styled building blocks shared by the RoomScope pages.

They only set object properties (``card``, ``role``, ``tone``, ``primary``)
that :func:`roomscope.ui.theme.stylesheet` styles, so the look stays in one
place and follows the light / dark scheme.
"""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QMouseEvent, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from roomscope.ui.theme import LIGHT_TOKENS, tokens, tone_color


def label(text: str, role: str | None = None, *, wrap: bool = False) -> QLabel:
    """A label with a style role (``title``, ``subtitle``, ``section``, ...)."""
    widget = QLabel(text)
    if role:
        widget.setProperty("role", role)
    widget.setWordWrap(wrap)
    return widget


def primary(button: QPushButton) -> QPushButton:
    """Mark ``button`` as the page's main action."""
    button.setProperty("primary", True)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    return button


class Card(QFrame):
    """A rounded surface with padding; children go into :attr:`body`."""

    def __init__(self, parent: QWidget | None = None, *, spacing: int = 8) -> None:
        super().__init__(parent)
        self.setProperty("card", True)
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(16, 14, 16, 14)
        self.body.setSpacing(spacing)


class PageHeader(QWidget):
    """Page title, one-line explanation and optional actions on the right."""

    def __init__(self, title: str, subtitle: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 4)
        text = QVBoxLayout()
        text.setSpacing(2)
        self.title = label(title, "page-title")
        text.addWidget(self.title)
        self.subtitle = label(subtitle, "subtitle", wrap=True)
        self.subtitle.setVisible(bool(subtitle))
        text.addWidget(self.subtitle)
        row.addLayout(text, 1)
        self.action_row = QHBoxLayout()
        self.action_row.setSpacing(8)
        row.addLayout(self.action_row)


class ModeCard(Card):
    """A large clickable card that starts a workflow."""

    clicked = Signal()

    def __init__(
        self, glyph: str, title: str, text: str, action: str, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent, spacing=6)
        self.setProperty("hover", True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setMinimumWidth(220)
        top = QHBoxLayout()
        icon = label(glyph, "pill")
        top.addWidget(icon)
        top.addStretch(1)
        self.body.addLayout(top)
        self.body.addWidget(label(title, "card-title", wrap=True))
        description = label(text, "hint", wrap=True)
        description.setMinimumHeight(48)
        self.body.addWidget(description, 1)
        self.button = primary(QPushButton(action))
        self.button.clicked.connect(self.clicked.emit)
        self.body.addWidget(self.button)
        self.setToolTip(text)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt override
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)


class Chip(QLabel):
    """A small rounded tag coloured by tone: good, warn, bad, info or neutral."""

    def __init__(self, text: str = "", tone: str = "neutral", parent: QWidget | None = None):
        super().__init__(text, parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.set_tone(tone)

    def set_tone(self, tone: str) -> None:
        fg, bg = tone_color(tone)
        self.setStyleSheet(
            f"background: {bg}; color: {fg}; border: 1px solid {bg}; border-radius: 9px;"
            " padding: 2px 9px;"
            "font-size: 11px; font-weight: 700;"
        )


class StatTile(Card):
    """One key figure: caption, value, a qualifier line and a trust chip."""

    def __init__(self, caption: str, parent: QWidget | None = None) -> None:
        super().__init__(parent, spacing=2)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        top = QHBoxLayout()
        self.caption = label(caption, "kpi-label")
        top.addWidget(self.caption)
        top.addStretch(1)
        self.chip = Chip()
        top.addWidget(self.chip)
        self.body.addLayout(top)
        self.value = label("-", "kpi-value")
        self.body.addWidget(self.value)
        self.sub = label("", "kpi-sub", wrap=True)
        self.body.addWidget(self.sub)

    def show_value(self, value: str, sub: str = "", chip: str = "", tone: str = "neutral") -> None:
        self.value.setText(value)
        self.sub.setText(sub)
        self.chip.setText(chip)
        self.chip.set_tone(tone)
        self.chip.setVisible(bool(chip))


#: Chip tone of an interpretation severity.
SEVERITY_TONE = {"warning": "warn", "notice": "info", "info": "good"}


class FindingCard(QFrame):
    """One interpretation finding with a coloured severity edge."""

    def __init__(
        self,
        severity: str,
        topic: str,
        message: str,
        parent: QWidget | None = None,
        *,
        severity_label: str | None = None,
    ) -> None:
        super().__init__(parent)
        tone = SEVERITY_TONE.get(severity, "neutral")
        fg, bg = tone_color(tone)
        self.setObjectName("finding")
        self.setStyleSheet(
            f"QFrame#finding {{ background: {bg}; border-left: 4px solid {fg};"
            " border-radius: 6px; }"
        )
        row = QHBoxLayout(self)
        row.setContentsMargins(12, 8, 12, 8)
        row.setSpacing(10)
        chip = Chip((severity_label or severity).upper(), tone)
        chip.setFixedWidth(82)
        row.addWidget(chip, 0, Qt.AlignmentFlag.AlignTop)
        text = QVBoxLayout()
        text.setSpacing(1)
        text.addWidget(label(topic, "kpi-label"))
        self.message = label(message, wrap=True)
        self.message.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        text.addWidget(self.message)
        row.addLayout(text, 1)


def separator() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    line.setStyleSheet(f"color: {tokens()['border']};")
    return line


def app_icon() -> QIcon:
    """RoomScope's icon, drawn at runtime (no binary asset to package):
    a rounded accent tile with a scope ring and a decaying sine."""
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(_icon_pixmap(size))
    return icon


def _icon_pixmap(size: int) -> QPixmap:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    s = float(size)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(LIGHT_TOKENS["accent"]))
    painter.drawRoundedRect(QRectF(0, 0, s, s), s * 0.22, s * 0.22)
    white = QColor("#ffffff")
    ring = QPen(white, max(1.0, s * 0.06))
    painter.setPen(ring)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    margin = s * 0.16
    painter.drawEllipse(QRectF(margin, margin, s - 2 * margin, s - 2 * margin))
    wave = QPainterPath()
    left, right = s * 0.24, s * 0.76
    mid = s * 0.5
    steps = 48
    for i in range(steps + 1):
        x = left + (right - left) * i / steps
        phase = i / steps
        y = mid - math.sin(phase * 5.0 * math.pi) * s * 0.17 * math.exp(-2.6 * phase)
        if i == 0:
            wave.moveTo(QPointF(x, y))
        else:
            wave.lineTo(QPointF(x, y))
    stroke = QPen(white, max(1.0, s * 0.055))
    stroke.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(stroke)
    painter.drawPath(wave)
    painter.end()
    return pixmap
