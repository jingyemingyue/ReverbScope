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
from PySide6.QtWidgets import (
    QFrame,
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
from reverbscope.ui import icons
from reverbscope.ui.browser import SessionBrowser
from reverbscope.ui.pages import WalkthroughCard
from reverbscope.ui.theme import tokens
from reverbscope.ui.widgets import app_icon, key_marks, label

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
        layout.setContentsMargins(32, 24, 32, 16)
        layout.setSpacing(12)
        layout.addLayout(self._hero(), 0)

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
        header.addWidget(label(_("Saved sessions"), "section"))
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
        for button, icon_name in ((open_button, "folder"), (project_button, "layers")):
            button.setIcon(icons.icon(icon_name, 16))
            button.setProperty("icon_name", icon_name)
            header.addWidget(button)
        compare_button.setIcon(icons.icon("git-compare", 16))
        compare_button.setProperty("icon_name", "git-compare")
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

    def _hero(self) -> QVBoxLayout:
        """Icon, title, one sentence and the composer with the two real ways in
        (``measure_strip.MODES``), centred as one group (SPEC §7)."""
        hero = QVBoxLayout()
        hero.setSpacing(8)
        hero.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        mark = QLabel()
        mark.setPixmap(app_icon().pixmap(44, 44))
        mark.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        hero.addWidget(mark)
        title = label("ReverbScope", "display")
        title.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        hero.addWidget(title)
        lead = label(
            _(
                "Measure how a room sounds: through your audio interface, or from a "
                "recording made in your DAW."
            ),
            "subtitle",
            wrap=True,
        )
        lead.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        hero.addWidget(lead)

        self.composer = QFrame()
        self.composer.setProperty("composer", True)
        self.composer.setMaximumWidth(640)
        self.composer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        inner = QVBoxLayout(self.composer)
        inner.setContentsMargins(16, 16, 16, 12)
        inner.setSpacing(12)
        paths = QHBoxLayout()
        paths.setSpacing(12)
        self.path_buttons: dict[str, QPushButton] = {}
        for mode, icon_name, title_text, text in (
            (
                "standalone",
                "audio-lines",
                _("Audio interface"),
                _("Plays the sweep only on the output you choose, and records the microphone."),
            ),
            (
                "universal_daw",
                "music",
                _("DAW recording"),
                _("Write the test signal, record it in your DAW, then import the recording."),
            ),
        ):
            button = QPushButton()
            button.setProperty("pathcard", True)
            button.setProperty("icon_name", icon_name)
            button.setToolTip(text)
            button.setAccessibleName(title_text)
            button.setAccessibleDescription(text)
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            card = QHBoxLayout(button)
            card.setContentsMargins(14, 10, 14, 10)
            card.setSpacing(10)
            mark = QLabel()
            mark.setProperty("icon_name", icon_name)
            mark.setPixmap(icons.pixmap(icon_name, tokens()["accent_ink"], 20))
            mark.setAlignment(Qt.AlignmentFlag.AlignTop)
            words = QVBoxLayout()
            words.setSpacing(2)
            heading = label(title_text, "panel-title")
            detail = label(text, "caption", wrap=True)
            words.addWidget(heading)
            words.addWidget(detail)
            card.addWidget(mark)
            card.addLayout(words, 1)
            for part in (mark, heading, detail):
                part.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            button.setMinimumHeight(76)
            button.clicked.connect(lambda _checked=False, m=mode: self.choose_mode.emit(m))
            paths.addWidget(button, 1)
            self.path_buttons[mode] = button
        inner.addLayout(paths)
        note = QHBoxLayout()
        note.setSpacing(6)
        self.profile_mark = QLabel()
        self.profile_mark.setPixmap(icons.pixmap("mic", tokens()["text3"], 14))
        note.addWidget(self.profile_mark)
        note.addWidget(
            label(
                _(
                    "A recording profile changes only the wording and the thresholds, never the numbers."
                ),
                "caption",
                wrap=True,
            ),
            1,
        )
        inner.addLayout(note)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(self.composer, 4)
        row.addStretch(1)
        hero.addLayout(row)
        keys = label(
            _(
                "{new} new measurement · {open} open · {project} project · {settings} settings"
            ).format(
                new=key_marks("Ctrl+N"),
                open=key_marks("Ctrl+O"),
                project=key_marks("Ctrl+Shift+O"),
                settings=key_marks("Ctrl+,"),
            ),
            "caption",
        )
        keys.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        hero.addWidget(keys)
        return hero

    def restyle_icons(self) -> None:
        for widget in self.findChildren(QPushButton):
            name = widget.property("icon_name")
            if isinstance(name, str) and name and not widget.property("pathcard"):
                widget.setIcon(icons.icon(name, 16))
        for mark in self.findChildren(QLabel):
            name = mark.property("icon_name")
            if isinstance(name, str) and name:
                mark.setPixmap(icons.pixmap(name, tokens()["accent_ink"], 20))
        self.profile_mark.setPixmap(icons.pixmap("mic", tokens()["text3"], 14))

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
