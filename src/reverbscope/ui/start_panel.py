"""The project landing page: saved sessions and measurement entry points.

The first-measurement guide expands on demand and can be dismissed.
A double click adds a saved session to the persistent workspace model."""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from reverbscope.errors import ReverbScopeError
from reverbscope.i18n import _
from reverbscope.ui.browser import SessionBrowser
from reverbscope.ui.pages import WalkthroughCard
from reverbscope.ui.widgets import PageHeader, label, native_shortcut

log = logging.getLogger(__name__)


def key_marks(sequence: str) -> str:
    """``Ctrl+Shift+2`` as key marks (``⌃⇧2``; ``⌘⇧2`` on macOS).

    Marks, not the words: "Ctrl" and "Shift" are English, and a mark is what
    the menus of macOS show anyway.
    """
    import sys

    marks = {"Ctrl": "⌘" if sys.platform == "darwin" else "⌃", "Shift": "⇧", "Alt": "⌥"}
    return "".join(marks.get(part, part) for part in sequence.split("+"))


class ActionTile(QFrame):
    """One way in: an icon, a name, what it does and its shortcut.

    The whole tile is a button (click, or Space / Enter when focused); the
    primary tile carries the accent.
    """

    clicked = Signal()

    def __init__(
        self,
        glyph: str,
        title: str,
        text: str,
        shortcut: str = "",
        *,
        primary: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        from reverbscope.ui.components.icons import icon_pixmap
        from reverbscope.ui.theme import tokens

        super().__init__(parent)
        self.setProperty("tile", True)
        self.setProperty("primary", primary)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName(title)
        self.setToolTip(text)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(12)
        mark = QLabel()
        mark.setPixmap(icon_pixmap(glyph, tokens()["accent" if primary else "muted"], 22))
        mark.setFixedSize(QSize(24, 24))
        layout.addWidget(mark, 0, Qt.AlignmentFlag.AlignTop)
        words = QVBoxLayout()
        words.setSpacing(2)
        top = QHBoxLayout()
        top.setSpacing(8)
        self.title = label(title, "tile-title")
        top.addWidget(self.title)
        top.addStretch(1)
        if shortcut:
            badge = label(key_marks(shortcut), "shortcut")
            badge.setToolTip(native_shortcut(shortcut))
            top.addWidget(badge)
        words.addLayout(top)
        self.text = label(text, "hint", wrap=True)
        words.addWidget(self.text)
        layout.addLayout(words, 1)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt override
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(
            event.position().toPoint()
        ):
            self.clicked.emit()
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event: object) -> None:  # noqa: N802 - Qt override
        from PySide6.QtGui import QKeyEvent

        assert isinstance(event, QKeyEvent)
        if event.key() in (Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.clicked.emit()
            return
        super().keyPressEvent(event)


class StartPanel(QWidget):
    choose_mode = Signal(str)
    open_session = Signal()
    open_recent = Signal(str)
    compare_requested = Signal()
    open_project = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("page", True)
        # A short window (1366x768, or the minimum size) scrolls the panel
        # rather than squeezing the card until its buttons overlap.
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body = QWidget()
        body.setProperty("page", True)
        self.scroll_area.setWidget(body)
        outer.addWidget(self.scroll_area)
        body.setMaximumWidth(1080)
        self.scroll_area.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        layout = QVBoxLayout(body)
        layout.setContentsMargins(32, 24, 32, 20)
        layout.setSpacing(20)
        layout.addWidget(
            PageHeader(
                _("Projects and measurements"), _("Open a room project or start a new measurement.")
            )
        )
        # Every way in is on screen with its shortcut (the menus repeat them).
        tiles = QGridLayout()
        tiles.setHorizontalSpacing(12)
        tiles.setVerticalSpacing(12)
        interface = ActionTile(
            "measure",
            _("New interface measurement"),
            _("Play a sweep through your audio interface and record the microphone."),
            "Ctrl+Shift+2",
            primary=True,
        )
        interface.clicked.connect(lambda: self.choose_mode.emit("standalone"))
        daw = ActionTile(
            "analysis",
            _("Analyze a DAW recording"),
            _("Make the test signal, record it in any DAW, then import the take."),
            "Ctrl+Shift+1",
        )
        daw.clicked.connect(lambda: self.choose_mode.emit("universal_daw"))
        project_tile = ActionTile(
            "project",
            _("Open Project..."),
            _("One room, several microphone positions: open or make a project folder."),
            "Ctrl+Shift+O",
        )
        project_tile.clicked.connect(self.open_project.emit)
        compare_tile = ActionTile(
            "compare",
            _("Compare two sessions..."),
            _("Before and after a change: every difference with its validity."),
            "Ctrl+Shift+C",
        )
        compare_tile.clicked.connect(self.compare_requested.emit)
        self.tiles = (interface, daw, project_tile, compare_tile)
        for index, tile in enumerate(self.tiles):
            tiles.addWidget(tile, index // 2, index % 2)
        layout.addLayout(tiles)

        # Shown until dismissed (a setting); Help ▸ Getting started brings it back.
        self.walkthrough = WalkthroughCard()
        self.walkthrough.choose_mode.connect(self.choose_mode.emit)
        self.walkthrough.dismissed.connect(self.dismiss_walkthrough)
        #: "Don't show this again" was clicked in this run: the card stays
        #: hidden even where the settings file could not record it.
        self._walkthrough_dismissed = False
        self.guide_button = QToolButton()
        self.guide_button.setText(_("Getting started"))
        self.guide_button.setCheckable(True)
        self.guide_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.guide_button.setArrowType(Qt.ArrowType.RightArrow)
        self.guide_button.toggled.connect(self.walkthrough.setVisible)
        self.guide_button.toggled.connect(
            lambda opened: self.guide_button.setArrowType(
                Qt.ArrowType.DownArrow if opened else Qt.ArrowType.RightArrow
            )
        )
        self.walkthrough.hide()

        sessions = QWidget()
        sessions_layout = QVBoxLayout(sessions)
        sessions_layout.setContentsMargins(0, 0, 0, 0)
        sessions_layout.setSpacing(6)
        header = QHBoxLayout()
        header.addWidget(label(_("Saved sessions"), "panel-title"))
        header.addStretch(1)
        open_button = QPushButton(_("Open Session..."))
        open_button.setToolTip(_("Open a session.json or a folder that contains one."))
        open_button.clicked.connect(self.open_session.emit)
        compare_button = QPushButton(_("Compare selected"))
        compare_button.setToolTip(_("Select two rows below, then compare them."))
        compare_button.clicked.connect(self.compare_requested.emit)
        # Open Project... is a tile above.
        header.addWidget(open_button)
        sessions_layout.addLayout(header)
        # Two selected rows go straight into Compare (MainWindow.show_compare).
        self.browser = SessionBrowser(multi_select=True)
        self.browser.open_session.connect(self.open_recent.emit)
        self.recent = self.browser.list
        sessions_layout.addWidget(self.browser, 1)
        layout.addWidget(sessions, 1)
        footer = QHBoxLayout()
        footer.addWidget(compare_button)
        footer.addStretch(1)
        footer.addWidget(self.guide_button)
        layout.addLayout(footer)
        layout.addWidget(self.walkthrough)

    def refresh_recent(self) -> None:
        self.browser.refresh_recent()

    def list_folder(self, root: Path) -> None:
        self.browser.list_folder(root)

    def show_walkthrough(self, visible: bool) -> None:
        enabled = visible and not self._walkthrough_dismissed
        self.guide_button.setVisible(enabled)
        self.walkthrough.setVisible(enabled and self.guide_button.isChecked())

    def restore_walkthrough(self) -> None:
        """Help > Getting started: the card is back, also after a dismissal."""
        self._walkthrough_dismissed = False
        self.guide_button.show()
        self.guide_button.setChecked(True)
        self.walkthrough.show()

    def dismiss_walkthrough(self) -> None:
        """Hide the card and remember it; a settings file that cannot be
        written still hides it for this run."""
        from dataclasses import replace

        from reverbscope.settings import load_settings, save_settings

        self._walkthrough_dismissed = True
        self.guide_button.setChecked(False)
        self.guide_button.hide()
        self.walkthrough.hide()
        try:
            save_settings(replace(load_settings(), walkthrough_dismissed=True))
        except (ReverbScopeError, OSError) as exc:
            log.info("the walkthrough stays for the next start: %s", exc)
