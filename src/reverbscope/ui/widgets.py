"""Small styled building blocks shared by the ReverbScope pages.

They only set object properties (``card``, ``role``, ``tone``, ``primary``)
that :func:`reverbscope.ui.theme.stylesheet` styles, so the look stays in one
place and follows the light / dark scheme.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QIcon,
    QKeySequence,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QResizeEvent,
)
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from reverbscope.i18n import _
from reverbscope.ui.theme import LIGHT_TOKENS, tokens, tone_color


class PathLabel(QLabel):
    """One line with a preserved filename; the complete path stays in a tooltip."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.full_path = ""
        self.setProperty("role", "hint")
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)

    def setText(self, text: str) -> None:  # noqa: N802 - Qt override
        self.full_path = text
        self.setToolTip(text)
        self.setAccessibleName(text)
        self._elide_path()

    def _elide_path(self) -> None:
        super().setText(
            self.fontMetrics().elidedText(
                self.full_path, Qt.TextElideMode.ElideMiddle, max(1, self.contentsRect().width())
            )
        )

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802 - Qt override
        super().resizeEvent(event)
        self._elide_path()


class PlotBody(QWidget):
    """Scrollable plot content whose wrapped notes reserve only required height.

    A QGraphicsView's preferred size follows its current viewport. Feeding
    that preferred height back into QScrollArea's height-for-width calculation
    makes the chart grow on every layout pass. Minimum height is stable.
    """

    def heightForWidth(self, width: int) -> int:  # noqa: N802 - Qt override
        layout = self.layout()
        if layout is None:
            return int(super().heightForWidth(width))
        height = layout.minimumHeightForWidth(width)
        return int(max(layout.minimumSize().height(), height))


def set_banner_text(widget: QLabel, text: str, tone: str = "") -> None:
    """Show ``text`` on a label, as a ``warn`` or ``info`` banner when ``tone`` is set.

    A dynamic property is read when the style is polished, so changing it
    after the widget is shown does nothing until the style is reapplied.
    """
    widget.setText(text)
    widget.setProperty("banner", tone)
    widget.style().unpolish(widget)
    widget.style().polish(widget)


def error_box(parent: QWidget | None, title: str, message: str) -> None:
    """A critical dialog: selectable text, and a button we translate ourselves."""
    from PySide6.QtWidgets import QMessageBox

    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Critical)
    box.setWindowTitle(title)
    box.setText(message)
    box.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    box.addButton(_("OK"), QMessageBox.ButtonRole.AcceptRole)
    box.exec()


def replace_file_box(parent: QWidget | None, path: Path) -> QMessageBox:
    """``path`` already exists. The safe button is the default: keep it."""
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Warning)
    box.setWindowTitle(_("Replace file?"))
    box.setText(_("{name} already exists. Replace it?").format(name=path.name))
    box.addButton(_("Replace"), QMessageBox.ButtonRole.AcceptRole)
    cancel = box.addButton(_("Cancel"), QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(cancel)
    box.setEscapeButton(cancel)
    return box


def ask_save_path(parent: QWidget, title: str, name: str, file_filter: str) -> Path | None:
    """Ask where to save ``name``; ``None`` when the user cancels.

    The path returned always ends in ``name``'s extension, and the user was
    asked before it replaces a file. The dialog adds the extension to a
    name typed without one before it asks about replacing a file; the
    static ``getSaveFileName`` has no such default. Qt adds it only when
    the name has no extension at all, so "sweep 2026.10.05" or "studio
    v1.2" is checked as typed: the extension is added here, and here the
    user is asked when that file exists.
    """
    from PySide6.QtWidgets import QFileDialog

    suffix = Path(name).suffix
    dialog = QFileDialog(parent, title, "", file_filter)
    dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
    dialog.setDefaultSuffix(suffix.lstrip("."))
    dialog.selectFile(name)
    try:
        if not dialog.exec():
            return None
        chosen = dialog.selectedFiles()
    finally:
        dialog.deleteLater()
    if not chosen:
        return None
    path = Path(chosen[0])
    if suffix and path.suffix.lower() != suffix.lower():
        path = path.with_name(path.name + suffix)
        if path.exists():
            box = replace_file_box(parent, path)
            box.exec()
            clicked = box.clickedButton()
            # By role, not by label, as in pages.ask_separate_clocks.
            if clicked is None or box.buttonRole(clicked) != QMessageBox.ButtonRole.AcceptRole:
                return None
    return path


#: Widest a set-up page's column grows (form and readiness side by side).
PAGE_COLUMN_WIDTH = 760


def scroll_page(
    page: QWidget, header: PageHeader, *, max_width: int = PAGE_COLUMN_WIDTH
) -> QVBoxLayout:
    """Give ``page`` a fixed header and a scrolling body; return the body layout.

    Header and body share one column, centred and at most ``max_width``
    wide (SPEC R2): the eye does not cross the whole screen.
    """
    page.setProperty("page", True)
    row = QHBoxLayout(page)
    row.setContentsMargins(28, 20, 20, 12)
    row.setSpacing(0)
    column = QWidget()
    column.setProperty("page", True)
    column.setMaximumWidth(max_width)
    column.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
    row.addStretch(1)
    row.addWidget(column, 100)
    row.addStretch(1)
    outer = QVBoxLayout(column)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.setSpacing(8)
    outer.addWidget(header)
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QScrollArea.Shape.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    body = QWidget()
    body.setProperty("page", True)
    layout = QVBoxLayout(body)
    layout.setContentsMargins(0, 0, 8, 8)
    layout.setSpacing(12)
    scroll.setWidget(body)
    outer.addWidget(scroll, 1)
    return layout


def label(text: str, role: str | None = None, *, wrap: bool = False) -> QLabel:
    """A label with a style role (``title``, ``subtitle``, ``section``, ...)."""
    widget = QLabel(text)
    if role:
        widget.setProperty("role", role)
    widget.setWordWrap(wrap)
    return widget


def native_shortcut(sequence: str) -> str:
    """How the platform shows ``sequence`` (Command on macOS, Ctrl elsewhere).

    ``QKeySequence.toString`` returns a Python ``str``. The lint job does not
    install PySide6, so the stub is missing and mypy sees ``Any``. ``str()``
    is the value the method actually produces.
    """
    shown = QKeySequence(sequence).toString(QKeySequence.SequenceFormat.NativeText)
    return str(shown)


def shortcut_badge(sequence: str) -> str:
    """Key mark for a card: ``⌃1``, or ``⌘1`` on macOS.

    The word ``Ctrl`` is English, and the Chinese interface rejects it.
    ``sequence`` is a Qt shortcut such as ``Ctrl+1``.
    """
    key = sequence.rsplit("+", 1)[-1]
    mark = "⌃"
    if sys.platform == "darwin":
        mark = "⌘"
        native = native_shortcut(sequence)
        if native and "Ctrl" not in native:
            return native
    return f"{mark}{key}"


def key_marks(sequence: str) -> str:
    """Every key of ``sequence`` as a mark: ``⇧⌃O`` (``⇧⌘O`` on macOS).

    For key hints a Chinese interface can show (the word ``Ctrl`` fails its
    gate); modifiers come first in the Apple order.
    """
    parts = sequence.split("+")
    key = parts[-1]
    command = "⌘" if sys.platform == "darwin" else "⌃"
    marks = {"Shift": "⇧", "Alt": "⌥", "Ctrl": command, "Meta": "⌃"}
    order = ("Meta", "Alt", "Shift", "Ctrl")
    shown = "".join(marks[name] for name in order if name in parts[:-1])
    return f"{shown}{'↩' if key == 'Return' else key}"


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
        self.body.setContentsMargins(12, 10, 12, 10)
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
        self,
        glyph: str,
        title: str,
        text: str,
        action: str,
        parent: QWidget | None = None,
        *,
        shortcut: str = "",
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
        if shortcut:
            # Same keys as the Measure menu. A control mark, not the word
            # "Ctrl": that word fails the Chinese-interface gate.
            top.addWidget(label(shortcut_badge(shortcut), "badge"))
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
        fg, _bg = tone_color(tone)
        self.setStyleSheet(
            f"background: transparent; color: {fg}; border: none;"
            " padding: 0 3px; font-size: 11px; font-weight: 600;"
        )


class StatTile(QWidget):
    """One key figure: caption, value, a qualifier line and a trust chip.

    Not a card. The four figures sit in one row, like a parameter strip.
    """

    def __init__(self, caption: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 10, 0)
        layout.setSpacing(1)
        # The caption wraps on its own line. Sharing the row with the chip
        # clipped Chinese captions once the tile got narrow.
        self.caption = label(caption, "kpi-label", wrap=True)
        layout.addWidget(self.caption)
        row = QHBoxLayout()
        self.value = label("-", "kpi-value")
        row.addWidget(self.value, 1)
        self.chip = Chip()
        layout.addLayout(row)
        layout.addWidget(self.chip, 0, Qt.AlignmentFlag.AlignLeft)
        self.sub = label("", "kpi-sub", wrap=True)
        layout.addWidget(self.sub)

    def show_value(self, value: str, sub: str = "", chip: str = "", tone: str = "neutral") -> None:
        self.value.setText(value)
        self.sub.setText(sub)
        self.chip.setText(chip)
        self.chip.set_tone(tone)
        self.chip.setVisible(bool(chip))


#: Chip tone of an interpretation severity.
#: Finding severities and measurement-health statuses to a chip tone.
SEVERITY_TONE = {
    "warning": "warn",
    "notice": "info",
    "info": "good",
    "invalid": "bad",
    "unknown": "neutral",
    "good": "good",
    "meaningful_improvement": "good",
    "meaningful_degradation": "bad",
    "probably_insignificant": "neutral",
    "not_comparable": "warn",
    "insufficient_evidence": "info",
    "fits": "good",
    "warnings": "warn",
}


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
        self.setObjectName("finding")
        self.setStyleSheet(
            f"QFrame#finding {{ background: {tokens()['surface']}; "
            f"border: none; border-bottom: 1px solid {tokens()['border']}; }}"
        )
        row = QHBoxLayout(self)
        row.setContentsMargins(6, 4, 6, 4)
        row.setSpacing(6)
        chip = Chip((severity_label or severity).upper(), tone)
        # A fixed width cut "NOT COMPARABLE" short; the column stays aligned
        # for the usual one-word labels.
        chip.setMinimumWidth(48)
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
    """ReverbScope's icon, drawn at runtime (no binary asset to package):
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


def step_mark(state: str, number: int, size: int = 22) -> QPixmap:
    """The round node of a step: ``done``, ``current``, ``todo``, ``locked``
    or ``running`` (docs/design/light-sidebar/SPEC.md §8.1)."""
    from reverbscope.ui import icons

    t = tokens()
    ratio = 2.0
    image = QPixmap(round(size * ratio), round(size * ratio))
    image.setDevicePixelRatio(ratio)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    box = QRectF(1.0, 1.0, size - 2.0, size - 2.0)
    fill, ring, ink = {
        "done": (t["accent"], t["accent"], t["accent_text"]),
        "current": (t["accent"], t["accent"], t["accent_text"]),
        "running": (t["accent_soft"], t["accent"], t["accent_ink"]),
        "locked": (t["surface_alt"], t["sep"], t["disabled"]),
    }.get(state, (t["surface"], t["control"], t["muted"]))
    painter.setPen(QPen(QColor(ring), 1.2))
    painter.setBrush(QColor(fill))
    painter.drawEllipse(box)
    glyph = {"done": "check", "locked": "lock", "running": "activity"}.get(state)
    if glyph:
        inner = 12 if glyph != "check" else 13
        mark = icons.pixmap(glyph, ink, inner, ratio)
        offset = (size - inner) / 2.0
        painter.drawPixmap(QPointF(offset, offset), mark)
    else:
        font = painter.font()
        font.setPixelSize(11)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor(ink))
        painter.drawText(box, Qt.AlignmentFlag.AlignCenter, str(number))
    painter.end()
    return image


class StepIndicator(QWidget):
    """A horizontal step bar: numbered nodes joined by lines.

    It shows progress through one page's sections; a click on a step asks
    the page to reveal that section. Steps that are not reachable yet are
    drawn locked and say why in their tooltip.
    """

    step_clicked = Signal(int)

    def __init__(self, titles: tuple[str, ...], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        from PySide6.QtWidgets import QToolButton

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 4, 0, 8)
        row.setSpacing(8)
        row.addStretch(1)
        self.nodes: list[QToolButton] = []
        self.lines: list[QFrame] = []
        self.states: tuple[str, ...] = tuple("todo" for _title in titles)
        for index, title in enumerate(titles):
            if index:
                line = QFrame()
                line.setProperty("stepline", True)
                line.setFixedHeight(2)
                line.setMinimumWidth(16)
                line.setMaximumWidth(72)
                line.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
                row.addWidget(line, 1)
                self.lines.append(line)
            node = QToolButton()
            node.setText(title)
            node.setAutoRaise(True)
            node.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            node.setIconSize(QPixmap(22, 22).size())
            node.clicked.connect(lambda _checked=False, i=index: self.step_clicked.emit(i))
            row.addWidget(node)
            self.nodes.append(node)
        row.addStretch(1)
        self.set_states(self.states)

    def set_states(self, states: tuple[str, ...]) -> None:
        self.states = states
        for index, (node, state) in enumerate(zip(self.nodes, states, strict=False)):
            node.setIcon(QIcon(step_mark(state, index + 1)))
            node.setProperty("step", state)
            weight = "600" if state in ("current", "running", "done") else "400"
            colour = tokens()["disabled" if state == "locked" else "text"]
            node.setStyleSheet(f"QToolButton {{ font-weight: {weight}; color: {colour}; }}")
            node.setAccessibleDescription(state)
        self._fit(self.width())
        for index, line in enumerate(self.lines):
            done = index < len(states) and states[index] == "done"
            if bool(line.property("done")) != done:
                line.setProperty("done", done)
                line.style().unpolish(line)
                line.style().polish(line)

    def restyle(self) -> None:
        self.set_states(self.states)

    def minimumSizeHint(self) -> QSize:  # noqa: N802 - Qt override
        # Narrow pages keep the nodes and drop the other steps' words.
        return QSize(
            len(self.nodes) * 34 + len(self.lines) * 16, super().minimumSizeHint().height()
        )

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802 - Qt override
        super().resizeEvent(event)
        self._fit(event.size().width())

    def _fit(self, width: int) -> None:
        full = (
            sum(node.fontMetrics().horizontalAdvance(node.text()) + 40 for node in self.nodes)
            + len(self.lines) * 40
        )
        compact = width < full
        for node, state in zip(self.nodes, self.states, strict=False):
            words = not compact or state in ("current", "running")
            node.setToolButtonStyle(
                Qt.ToolButtonStyle.ToolButtonTextBesideIcon
                if words
                else Qt.ToolButtonStyle.ToolButtonIconOnly
            )
            node.setToolTip(node.text())
