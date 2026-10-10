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
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from reverbscope.i18n import _
from reverbscope.ui.theme import LIGHT_TOKENS, tokens, tone_color

#: A glyph per tone, so a status reads without its colour (ARCHITECTURE_V1 §5.8).
TONE_GLYPH = {"good": "✓", "warn": "!", "bad": "✕", "info": "i", "neutral": "–"}


def set_banner_text(widget: QLabel, text: str, tone: str = "") -> None:
    """Show ``text`` on a label, as a ``warn``, ``info``, ``bad`` or ``good``
    banner when ``tone`` is set.

    A dynamic property is read when the style is polished, so changing it
    after the widget is shown does nothing until the style is reapplied.
    """
    widget.setText(text)
    widget.setProperty("banner", tone)
    widget.style().unpolish(widget)
    widget.style().polish(widget)


def error_box(parent: QWidget | None, title: str, message: str) -> None:
    """A critical dialog: selectable text, and a button we translate ourselves."""
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
            # By role, not by label: some desktops insert "&" accelerators.
            if clicked is None or box.buttonRole(clicked) != QMessageBox.ButtonRole.AcceptRole:
                return None
    return path


def scroll_body(
    page: QWidget, *, margins: tuple[int, int, int, int] = (0, 0, 8, 8)
) -> tuple[QVBoxLayout, QScrollArea]:
    """Give ``page`` a scrolling body; return the body layout and the scroll area.

    The page's own layout is created here with no margins when it has none.
    """
    page.setProperty("page", True)
    existing = page.layout()
    if isinstance(existing, QVBoxLayout):
        outer = existing
    else:
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QScrollArea.Shape.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    body = QWidget()
    body.setProperty("page", True)
    layout = QVBoxLayout(body)
    layout.setContentsMargins(*margins)
    layout.setSpacing(10)
    scroll.setWidget(body)
    outer.addWidget(scroll, 1)
    return layout, scroll


def scroll_page(page: QWidget, header: QWidget | None = None) -> QVBoxLayout:
    """A page with an optional fixed ``header`` and a scrolling body."""
    page.setProperty("page", True)
    outer = QVBoxLayout(page)
    outer.setContentsMargins(20, 14, 20, 10)
    outer.setSpacing(8)
    if header is not None:
        outer.addWidget(header)
    layout, _scroll = scroll_body(page)
    return layout


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


def flat(button: QPushButton) -> QPushButton:
    """A link-like button for a secondary action (``Show all``, ``Back to settings``)."""
    button.setProperty("flat", True)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    return button


class Card(QFrame):
    """A bordered surface with padding; children go into :attr:`body`."""

    def __init__(self, parent: QWidget | None = None, *, spacing: int = 8) -> None:
        super().__init__(parent)
        self.setProperty("card", True)
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(14, 12, 14, 12)
        self.body.setSpacing(spacing)


class PageHeader(QWidget):
    """Page title, one-line explanation and optional actions on the right."""

    def __init__(self, title: str, subtitle: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 2)
        text = QVBoxLayout()
        text.setSpacing(2)
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
    """A clickable card that starts a workflow."""

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
        self.setMinimumWidth(200)
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
        description.setMinimumHeight(40)
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
    """A small tag coloured by tone: good, warn, bad, info or neutral.

    The glyph of the tone goes before the text when ``glyph`` is set, so a
    status reads in greyscale too.
    """

    def __init__(
        self,
        text: str = "",
        tone: str = "neutral",
        parent: QWidget | None = None,
        *,
        glyph: bool = False,
    ):
        super().__init__(text, parent)
        self._glyph = glyph
        self._text = text
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.set_tone(tone)

    def setText(self, text: str) -> None:  # noqa: N802 - Qt override
        self._text = text
        super().setText(self._decorated(text))

    def _decorated(self, text: str) -> str:
        if self._glyph and text:
            return f"{TONE_GLYPH.get(self._tone, '')} {text}".strip()
        return text

    def set_tone(self, tone: str) -> None:
        self._tone = tone
        fg, bg = tone_color(tone)
        self.setStyleSheet(
            f"background: {bg}; color: {fg}; border: 1px solid {fg}; border-radius: 3px;"
            " padding: 1px 7px; font-size: 11px; font-weight: 700;"
        )
        super().setText(self._decorated(self._text))


class StatTile(Card):
    """One key figure: caption, value, a qualifier line and a trust chip.

    Clicking it emits :attr:`activated`: the page opens the chart behind it.
    """

    activated = Signal()

    def __init__(self, caption: str, parent: QWidget | None = None) -> None:
        super().__init__(parent, spacing=2)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setProperty("hover", True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
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

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt override
        if event.button() == Qt.MouseButton.LeftButton:
            self.activated.emit()
        super().mouseReleaseEvent(event)


#: Finding severities, measurement-health statuses, fits and verdicts to a chip tone.
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
    """One interpretation finding with a coloured severity edge.

    Clicking the card emits :attr:`activated`; a page uses it to open the
    chart the finding points at and to show its evidence.
    """

    activated = Signal()

    def __init__(
        self,
        severity: str,
        topic: str,
        message: str,
        parent: QWidget | None = None,
        *,
        severity_label: str | None = None,
        clickable: bool = False,
    ) -> None:
        super().__init__(parent)
        self.tone = SEVERITY_TONE.get(severity, "neutral")
        fg, bg = tone_color(self.tone)
        self.setObjectName("finding")
        self._style = (
            f"QFrame#finding {{ background: {bg}; border: 1px solid {bg};"
            f" border-left: 4px solid {fg}; border-radius: 3px; }}"
        )
        self._selected_style = (
            f"QFrame#finding {{ background: {bg}; border: 1px solid {fg};"
            f" border-left: 4px solid {fg}; border-radius: 3px; }}"
        )
        self.setStyleSheet(self._style)
        self._clickable = clickable
        if clickable:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        row = QHBoxLayout(self)
        row.setContentsMargins(10, 7, 10, 7)
        row.setSpacing(10)
        self.chip = Chip((severity_label or severity).upper(), self.tone, glyph=True)
        # A fixed width cut "NOT COMPARABLE" short; the column stays aligned
        # for the usual one-word labels.
        self.chip.setMinimumWidth(82)
        row.addWidget(self.chip, 0, Qt.AlignmentFlag.AlignTop)
        text = QVBoxLayout()
        text.setSpacing(1)
        self.topic = label(topic, "kpi-label")
        text.addWidget(self.topic)
        self.message = label(message, wrap=True)
        self.message.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        text.addWidget(self.message)
        row.addLayout(text, 1)

    def set_selected(self, selected: bool) -> None:
        self.setStyleSheet(self._selected_style if selected else self._style)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt override
        if self._clickable and event.button() == Qt.MouseButton.LeftButton:
            self.activated.emit()
        super().mouseReleaseEvent(event)


class CollapsibleSection(QWidget):
    """A heading that opens and closes the content under it (help, advanced options)."""

    toggled = Signal(bool)

    def __init__(
        self, title: str, content: QWidget, parent: QWidget | None = None, *, open: bool = False
    ) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self.button = QToolButton()
        self.button.setText(title)
        self.button.setCheckable(True)
        self.button.setChecked(open)
        self.button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.button.setArrowType(Qt.ArrowType.DownArrow if open else Qt.ArrowType.RightArrow)
        self.button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.button.toggled.connect(self._toggle)
        layout.addWidget(self.button, 0, Qt.AlignmentFlag.AlignLeft)
        self.content = content
        self.content.setVisible(open)
        layout.addWidget(self.content)

    def _toggle(self, checked: bool) -> None:
        self.content.setVisible(checked)
        self.button.setArrowType(Qt.ArrowType.DownArrow if checked else Qt.ArrowType.RightArrow)
        self.toggled.emit(checked)

    def set_open(self, open: bool) -> None:
        self.button.setChecked(open)


class StepBar(QFrame):
    """The numbered steps of a workflow; the current one is marked, done ones ticked.

    Every step stays clickable so the user can go back and change an earlier
    choice; the page decides what a step needs before it is *done*.
    """

    step_chosen = Signal(int)

    def __init__(self, titles: Sequence[str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("stepbar", True)
        row = QHBoxLayout(self)
        row.setContentsMargins(6, 4, 6, 4)
        row.setSpacing(4)
        self.buttons: list[QToolButton] = []
        self._done: list[bool] = [False] * len(titles)
        for index, title in enumerate(titles):
            button = QToolButton()
            button.setProperty("step", True)
            button.setCheckable(True)
            button.setAutoExclusive(True)
            button.setText(f"{index + 1}  {title}")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _checked=False, i=index: self.step_chosen.emit(i))
            row.addWidget(button)
            self.buttons.append(button)
            if index + 1 < len(titles):
                arrow = label("›", "hint")
                row.addWidget(arrow)
        row.addStretch(1)
        self._titles = list(titles)
        if self.buttons:
            self.buttons[0].setChecked(True)

    def set_current(self, index: int) -> None:
        if 0 <= index < len(self.buttons):
            self.buttons[index].setChecked(True)

    def current(self) -> int:
        return next((i for i, b in enumerate(self.buttons) if b.isChecked()), 0)

    def set_done(self, index: int, done: bool) -> None:
        if not 0 <= index < len(self.buttons):
            return
        self._done[index] = done
        button = self.buttons[index]
        mark = "✓ " if done else ""
        button.setText(f"{mark}{index + 1}  {self._titles[index]}")
        button.setProperty("done", done)
        button.style().unpolish(button)
        button.style().polish(button)

    def is_done(self, index: int) -> bool:
        return self._done[index]

    def title(self, index: int) -> str:
        return self._titles[index] if 0 <= index < len(self._titles) else ""


class KeyValueList(QWidget):
    """Rows of ``name: value`` for the details pane (a metric's evidence, a
    candidate's numbers); every row selectable so it can be copied."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(3)

    def set_rows(self, rows: Sequence[tuple[str, str]]) -> None:
        clear_layout(self._layout)
        for name, value in rows:
            row = QWidget()
            box = QHBoxLayout(row)
            box.setContentsMargins(0, 0, 0, 0)
            box.setSpacing(8)
            key = label(name, "kpi-label", wrap=True)
            key.setMinimumWidth(110)
            key.setMaximumWidth(160)
            key.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
            box.addWidget(key)
            text = label(value, wrap=True)
            text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            box.addWidget(text, 1)
            self._layout.addWidget(row)


def clear_layout(layout: QVBoxLayout | QHBoxLayout) -> None:
    """Delete every widget (and nested layout) a layout holds.

    A widget is hidden at once: ``deleteLater`` waits for the event loop, and
    until then a removed row still painted over the new one.
    """
    while layout.count():
        entry = layout.takeAt(0)
        if entry is None:
            continue
        widget = entry.widget()
        if widget is not None:
            widget.hide()
            widget.setParent(None)
            widget.deleteLater()
            continue
        nested = entry.layout()
        if nested is not None:
            clear_layout(nested)  # type: ignore[arg-type]


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
