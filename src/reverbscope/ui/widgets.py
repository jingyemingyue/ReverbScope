"""Small styled building blocks shared by the ReverbScope pages.

They only set object properties (``card``, ``role``, ``tone``, ``primary``)
that :func:`reverbscope.ui.theme.stylesheet` styles, so the look stays in one
place and follows the light / dark scheme.
"""

from __future__ import annotations

import math
import sys
from collections.abc import Sequence
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QIcon,
    QKeySequence,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from reverbscope.i18n import _
from reverbscope.ui.theme import LIGHT_TOKENS, apply_mono_font, tokens, tone_color


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


def scroll_page(page: QWidget, header: PageHeader) -> QVBoxLayout:
    """Give ``page`` a header strip across the top and a scrolling body; return the body layout."""
    page.setProperty("page", True)
    outer = QVBoxLayout(page)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.setSpacing(0)
    outer.addWidget(header)
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QScrollArea.Shape.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    body = QWidget()
    body.setProperty("page", True)
    layout = QVBoxLayout(body)
    layout.setContentsMargins(20, 16, 20, 16)
    layout.setSpacing(12)
    scroll.setWidget(body)
    outer.addWidget(scroll, 1)
    return layout


def split_page(
    page: QWidget, header: PageHeader, *, left_width: int = 440
) -> tuple[QVBoxLayout, QVBoxLayout]:
    """Give ``page`` a header strip over two panes; return the layouts of the (left, right) pane.

    The left pane holds the settings and scrolls on its own; the right pane
    is the working area (a graph, the run controls, the status) and takes the
    rest of the width. A form never has to be scrolled past to reach Run.
    """
    page.setProperty("page", True)
    outer = QVBoxLayout(page)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.setSpacing(0)
    outer.addWidget(header)
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QScrollArea.Shape.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    scroll.setMinimumWidth(380)
    left = QWidget()
    left.setProperty("page", True)
    left_layout = QVBoxLayout(left)
    left_layout.setContentsMargins(16, 14, 12, 14)
    left_layout.setSpacing(12)
    scroll.setWidget(left)
    right = QWidget()
    right.setProperty("page", True)
    right_layout = QVBoxLayout(right)
    right_layout.setContentsMargins(12, 14, 16, 14)
    right_layout.setSpacing(10)
    splitter = QSplitter(Qt.Orientation.Horizontal)
    splitter.setChildrenCollapsible(False)
    splitter.addWidget(scroll)
    splitter.addWidget(right)
    splitter.setStretchFactor(0, 0)
    splitter.setStretchFactor(1, 1)
    splitter.setSizes([left_width, 900])
    outer.addWidget(splitter, 1)
    return left_layout, right_layout


class ModeSwitch(QWidget):
    """The three ways to measure as a segmented control: one click to change mode."""

    chosen = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        self._buttons: dict[str, QPushButton] = {}
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        modes = (
            ("universal_daw", _("Universal DAW Mode")),
            ("standalone", _("Standalone Mode")),
            ("demo", _("Demo (no interface)")),
        )
        for mode, caption in modes:
            button = QPushButton(caption)
            button.setCheckable(True)
            button.setProperty("segment", True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _checked=False, m=mode: self.chosen.emit(m))
            self._group.addButton(button)
            self._buttons[mode] = button
            row.addWidget(button)

    def set_mode(self, mode: str) -> None:
        button = self._buttons.get(mode)
        if button is not None:
            button.setChecked(True)


def label(text: str, role: str | None = None, *, wrap: bool = False) -> QLabel:
    """A label with a style role (``title``, ``subtitle``, ``section``, ...)."""
    widget = QLabel(text)
    if role:
        widget.setProperty("role", role)
    widget.setWordWrap(wrap)
    return widget


def shortcut_badge(sequence: str) -> str:
    """Key mark for a card: ``⌃1``, or ``⌘1`` on macOS.

    The word ``Ctrl`` is English, and the Chinese interface rejects it.
    ``sequence`` is a Qt shortcut such as ``Ctrl+1``.
    """
    key = sequence.rsplit("+", 1)[-1]
    if sys.platform == "darwin":
        native = QKeySequence(sequence).toString(QKeySequence.SequenceFormat.NativeText)
        if native and "Ctrl" not in native:
            return native
        return f"⌘{key}"
    return f"⌃{key}"


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


class PageHeader(QFrame):
    """A strip across the top of a page: title, one-line explanation, actions on the right."""

    def __init__(self, title: str, subtitle: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("toolbar", True)
        row = QHBoxLayout(self)
        row.setContentsMargins(20, 10, 20, 10)
        text = QVBoxLayout()
        text.setSpacing(1)
        self.title = label(title, "page-title")
        text.addWidget(self.title)
        self.subtitle = label(subtitle, "subtitle", wrap=True)
        self.subtitle.setVisible(bool(subtitle))
        text.addWidget(self.subtitle)
        row.addLayout(text, 1)
        self.action_row = QHBoxLayout()
        self.action_row.setSpacing(6)
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
        self.body.setContentsMargins(14, 12, 14, 12)
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
        self.body.addWidget(description, 1)
        self.button = QPushButton(action)
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
            f"background: {bg}; color: {fg}; border: 1px solid {fg}; border-radius: 3px;"
            " padding: 1px 7px;"
            "font-size: 10px; font-weight: 700;"
        )


class StatTile(Card):
    """One key figure: caption, value, a qualifier line and a trust chip."""

    def __init__(self, caption: str, parent: QWidget | None = None) -> None:
        super().__init__(parent, spacing=2)
        self.body.setContentsMargins(12, 9, 12, 9)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        top = QHBoxLayout()
        self.caption = label(caption, "kpi-label")
        top.addWidget(self.caption)
        top.addStretch(1)
        self.chip = Chip()
        top.addWidget(self.chip)
        self.body.addLayout(top)
        self.value = label("-", "kpi-value")
        apply_mono_font(self.value, pixel_size=22, bold=True)
        self.body.addWidget(self.value)
        self.sub = label("", "kpi-sub", wrap=True)
        self.body.addWidget(self.sub)

    def show_value(self, value: str, sub: str = "", chip: str = "", tone: str = "neutral") -> None:
        self.value.setText(value)
        self.sub.setText(sub)
        self.chip.setText(chip)
        self.chip.set_tone(tone)
        self.chip.setVisible(bool(chip))


class KeyValueList(QWidget):
    """Captions on the left, monospace values on the right: a property sheet."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setHorizontalSpacing(12)
        self._grid.setVerticalSpacing(4)
        self._grid.setColumnStretch(1, 1)
        self._rows: list[tuple[QLabel, QLabel]] = []

    def set_rows(self, rows: Sequence[tuple[str, str]]) -> None:
        """Show ``rows`` (caption, value); a row with no value is left out."""
        shown = [(key, value) for key, value in rows if value]
        while len(self._rows) < len(shown):
            key_label = label("", "kpi-label")
            value_label = label("", wrap=True)
            apply_mono_font(value_label, pixel_size=11)
            value_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            row = len(self._rows)
            self._grid.addWidget(key_label, row, 0, Qt.AlignmentFlag.AlignTop)
            self._grid.addWidget(value_label, row, 1)
            self._rows.append((key_label, value_label))
        for index, (key_label, value_label) in enumerate(self._rows):
            if index < len(shown):
                key_label.setText(shown[index][0])
                value_label.setText(shown[index][1])
            key_label.setVisible(index < len(shown))
            value_label.setVisible(index < len(shown))


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
        fg, bg = tone_color(tone)
        self.setObjectName("finding")
        self.setStyleSheet(
            f"QFrame#finding {{ background: {bg}; border-left: 3px solid {fg};"
            " border-radius: 3px; }"
        )
        row = QHBoxLayout(self)
        row.setContentsMargins(10, 7, 12, 7)
        row.setSpacing(10)
        chip = Chip((severity_label or severity).upper(), tone)
        # A fixed width cut "NOT COMPARABLE" short; the column stays aligned
        # for the usual one-word labels.
        chip.setMinimumWidth(82)
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
