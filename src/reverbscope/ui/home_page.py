"""The start page: ways into a measurement, recent projects and sessions."""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QWidget

from reverbscope.errors import ReverbScopeError
from reverbscope.i18n import _
from reverbscope.ui.browser import SessionBrowser
from reverbscope.ui.widgets import Card, ModeCard, flat, label, scroll_body

log = logging.getLogger(__name__)


class WalkthroughCard(Card):
    """The first-measurement card: three ways in, and where to read more."""

    choose_mode = Signal(str)
    dismissed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.body.addWidget(label(_("Your first measurement").upper(), "section"))
        self.body.addWidget(
            label(
                _(
                    "ReverbScope plays a sweep, records it and reads the room from the "
                    "recording. Three ways in; the demo needs no hardware."
                ),
                "hint",
                wrap=True,
            )
        )
        steps = (
            (
                _("Try the demo first: a synthetic room, nothing is played."),
                _("Try the demo"),
                "demo",
            ),
            (
                _(
                    "In your DAW: write the test signal, play it and record it on a track, "
                    "then import the recording here."
                ),
                _("Universal DAW Mode"),
                "universal_daw",
            ),
            (
                _(
                    "With an audio interface: ReverbScope plays the sweep and records the "
                    "microphone itself."
                ),
                _("Standalone Mode"),
                "standalone",
            ),
        )
        self.buttons: list[QPushButton] = []
        for number, (text, caption, mode) in enumerate(steps, start=1):
            row = QHBoxLayout()
            row.setSpacing(10)
            row.addWidget(label(f"{number}.  {text}", wrap=True), 1)
            button = QPushButton(caption)
            button.clicked.connect(lambda _checked=False, m=mode: self.choose_mode.emit(m))
            row.addWidget(button)
            self.buttons.append(button)
            self.body.addLayout(row)
        self.body.addWidget(
            label(
                _(
                    "Choose the recording profile that matches what you record; its button says "
                    "what it watches for. Every number carries a validity, and a result opens "
                    "with its measurement health."
                ),
                "hint",
                wrap=True,
            )
        )
        bottom = QHBoxLayout()
        self.guide_button = QPushButton(_("Read the user guide"))
        self.guide_button.clicked.connect(self._open_guide)
        bottom.addWidget(self.guide_button)
        bottom.addStretch(1)
        self.dismiss_button = QPushButton(_("Don't show this again"))
        self.dismiss_button.clicked.connect(self.dismissed.emit)
        bottom.addWidget(self.dismiss_button)
        self.body.addLayout(bottom)

    def _open_guide(self) -> None:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        from reverbscope.edition import user_guide_url
        from reverbscope.i18n import current_locale

        QDesktopServices.openUrl(QUrl(user_guide_url(current_locale())))


class HomePage(QWidget):
    choose_mode = Signal(str)
    open_session = Signal()
    open_recent = Signal(str)
    compare_requested = Signal()
    open_project = Signal()
    #: A project folder listed among the recent sessions' parents.
    open_project_path = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        # A window shorter than the page (a 1366x768 laptop, or the 960x640
        # minimum) scrolls it; without the scroll area the first-measurement
        # card was squeezed until its buttons overlapped and were cut off.
        layout, self.scroll_area = scroll_body(self, margins=(20, 16, 20, 16))
        layout.setSpacing(12)

        # Shown until dismissed (a setting); Help ▸ Getting started brings it back.
        self.walkthrough = WalkthroughCard()
        self.walkthrough.choose_mode.connect(self.choose_mode.emit)
        self.walkthrough.dismissed.connect(self.dismiss_walkthrough)
        #: "Don't show this again" was clicked in this run: the card stays
        #: hidden even where the settings file could not record it.
        self._walkthrough_dismissed = False
        layout.addWidget(self.walkthrough)

        layout.addWidget(label(_("New Measurement").upper(), "section"))
        cards = QHBoxLayout()
        cards.setSpacing(10)
        daw = ModeCard(
            "DAW",
            _("Universal DAW Mode"),
            _("Generate a test signal, play and record it in any DAW, import the recording."),
            _("Start in my DAW"),
            shortcut="Ctrl+1",
        )
        standalone = ModeCard(
            "I/O",
            _("Standalone Mode"),
            _(
                "ReverbScope plays the sweep and records the microphone through your audio interface."
            ),
            _("Measure now"),
            shortcut="Ctrl+2",
        )
        demo = ModeCard(
            _("DEMO"),
            _("Demo (no interface)"),
            _("Run Standalone Mode on the fake backend. Nothing is sent to a loudspeaker."),
            _("Try the demo"),
            shortcut="Ctrl+3",
        )
        # The demo is the way to look around, not a measurement: a plain button.
        demo.button.setProperty("primary", False)
        daw.clicked.connect(lambda: self.choose_mode.emit("universal_daw"))
        standalone.clicked.connect(lambda: self.choose_mode.emit("standalone"))
        demo.clicked.connect(lambda: self.choose_mode.emit("demo"))
        self.mode_cards = (daw, standalone, demo)
        for card in self.mode_cards:
            cards.addWidget(card)
        layout.addLayout(cards)

        projects = Card()
        projects_header = QHBoxLayout()
        projects_header.addWidget(label(_("Recent projects").upper(), "section"))
        projects_header.addStretch(1)
        project_button = QPushButton(_("Open Project..."))
        project_button.setToolTip(
            _("One room, several microphone positions: open or make a project folder.")
        )
        project_button.clicked.connect(self.open_project.emit)
        projects_header.addWidget(project_button)
        projects.body.addLayout(projects_header)
        self.project_rows = QHBoxLayout()
        self.project_rows.setSpacing(6)
        projects.body.addLayout(self.project_rows)
        self.projects_hint = label(
            _("A project folder you saved a session into is listed here."), "hint", wrap=True
        )
        projects.body.addWidget(self.projects_hint)
        layout.addWidget(projects)

        sessions = Card()
        header = QHBoxLayout()
        header.addWidget(label(_("Recent sessions").upper(), "section"))
        header.addStretch(1)
        open_button = QPushButton(_("Open Session..."))
        open_button.setToolTip(_("Open a session.json or a folder that contains one."))
        open_button.clicked.connect(self.open_session.emit)
        compare_button = QPushButton(_("Compare two sessions..."))
        compare_button.setToolTip(_("Pick two saved sessions and compare their metrics."))
        compare_button.clicked.connect(self.compare_requested.emit)
        header.addWidget(open_button)
        header.addWidget(compare_button)
        sessions.body.addLayout(header)
        # Two selected rows go straight into Compare (MainWindow.show_compare).
        self.browser = SessionBrowser(multi_select=True)
        self.browser.open_session.connect(self.open_recent.emit)
        self.recent = self.browser.list
        sessions.body.addWidget(self.browser, 1)
        sessions.body.addWidget(
            label(_("Double-click a session to open it; select two and compare."), "hint")
        )
        layout.addWidget(sessions, 1)

    def refresh_recent(self) -> None:
        self.browser.refresh_recent()
        self._refresh_projects()

    def _refresh_projects(self) -> None:
        from reverbscope.io.project_store import is_project, load_project
        from reverbscope.io.recent import recent_session_paths
        from reverbscope.ui.widgets import clear_layout

        clear_layout(self.project_rows)
        seen: list[Path] = []
        for path in recent_session_paths():
            parent = path.parent
            if parent in seen or not is_project(parent):
                continue
            seen.append(parent)
            if len(seen) > 4:
                break
            try:
                name = load_project(parent).name or parent.name
            except ReverbScopeError:
                name = parent.name
            button = flat(QPushButton(name))
            button.setToolTip(str(parent))
            button.clicked.connect(
                lambda _checked=False, p=parent: self.open_project_path.emit(str(p))
            )
            self.project_rows.addWidget(button)
        self.project_rows.addStretch(1)
        self.projects_hint.setVisible(not seen)

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
