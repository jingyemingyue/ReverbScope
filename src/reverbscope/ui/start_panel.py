"""The start panel: what the workspace shows before anything is open.

It replaces the 0.5 home page. The marketing pills and the three large mode
cards are gone (the measure strip under the workspace starts a take); the
first-measurement card stays until it is dismissed, and Help ▸ Getting
started brings it back. The saved-session list opens a session into the
workspace with a double click.
"""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QScrollArea, QVBoxLayout, QWidget

from reverbscope.errors import ReverbScopeError
from reverbscope.i18n import _
from reverbscope.ui.browser import SessionBrowser
from reverbscope.ui.pages import WalkthroughCard
from reverbscope.ui.widgets import Card, label

log = logging.getLogger(__name__)


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
        layout = QVBoxLayout(body)
        layout.setContentsMargins(20, 14, 20, 14)
        layout.setSpacing(10)
        layout.addWidget(label(_("Start"), "title"))
        layout.addWidget(
            label(
                _(
                    "Open a project or a session, or measure with the strip at the bottom of "
                    "the window. Measurements open in the list on the left."
                ),
                "hint",
                wrap=True,
            )
        )

        # Shown until dismissed (a setting); Help ▸ Getting started brings it back.
        self.walkthrough = WalkthroughCard()
        self.walkthrough.choose_mode.connect(self.choose_mode.emit)
        self.walkthrough.dismissed.connect(self.dismiss_walkthrough)
        #: "Don't show this again" was clicked in this run: the card stays
        #: hidden even where the settings file could not record it.
        self._walkthrough_dismissed = False
        layout.addWidget(self.walkthrough)

        sessions = Card()
        header = QHBoxLayout()
        header.addWidget(label(_("Saved sessions").upper(), "section"))
        header.addStretch(1)
        open_button = QPushButton(_("Open Session..."))
        open_button.setToolTip(_("Open a session.json or a folder that contains one."))
        open_button.clicked.connect(self.open_session.emit)
        project_button = QPushButton(_("Open Project..."))
        project_button.setToolTip(
            _("One room, several microphone positions: open or make a project folder.")
        )
        project_button.clicked.connect(self.open_project.emit)
        compare_button = QPushButton(_("Compare two sessions..."))
        compare_button.setToolTip(_("Select two rows below, then compare them."))
        compare_button.clicked.connect(self.compare_requested.emit)
        for button in (open_button, project_button, compare_button):
            header.addWidget(button)
        sessions.body.addLayout(header)
        # Two selected rows go straight into Compare (MainWindow.show_compare).
        self.browser = SessionBrowser(multi_select=True)
        self.browser.open_session.connect(self.open_recent.emit)
        self.recent = self.browser.list
        sessions.body.addWidget(self.browser, 1)
        layout.addWidget(sessions, 1)

    def refresh_recent(self) -> None:
        self.browser.refresh_recent()

    def list_folder(self, root: Path) -> None:
        self.browser.list_folder(root)

    def show_walkthrough(self, visible: bool) -> None:
        self.walkthrough.setVisible(visible and not self._walkthrough_dismissed)

    def restore_walkthrough(self) -> None:
        """Help > Getting started: the card is back, also after a dismissal."""
        self._walkthrough_dismissed = False
        self.walkthrough.show()

    def dismiss_walkthrough(self) -> None:
        """Hide the card and remember it; a settings file that cannot be
        written still hides it for this run."""
        from dataclasses import replace

        from reverbscope.settings import load_settings, save_settings

        self._walkthrough_dismissed = True
        self.walkthrough.hide()
        try:
            save_settings(replace(load_settings(), walkthrough_dismissed=True))
        except (ReverbScopeError, OSError) as exc:
            log.info("the walkthrough stays for the next start: %s", exc)
