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

from PySide6.QtCore import QEvent, QObject, Qt, Signal
from PySide6.QtGui import QResizeEvent, QShowEvent
from PySide6.QtWidgets import (
    QBoxLayout,
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
        self.scroll_area.viewport().installEventFilter(self)
        body = QWidget()
        body.setProperty("page", True)
        body.setMinimumWidth(0)
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
        self.sessions_label = label(_("Saved sessions"), "section")
        header = QHBoxLayout()
        header.addWidget(self.sessions_label)
        header.addStretch(1)
        self.open_button = QPushButton(_("Open Session..."))
        self.open_button.setToolTip(_("Open a session.json or a folder that contains one."))
        self.open_button.clicked.connect(self.open_session.emit)
        self.project_button = QPushButton(_("Open Project..."))
        self.project_button.setToolTip(
            _("One room, several microphone positions: open or make a project folder.")
        )
        self.project_button.clicked.connect(self.open_project.emit)
        compare_button = QPushButton(_("Compare two sessions..."))
        compare_button.setToolTip(_("Select two rows below, then compare them."))
        compare_button.clicked.connect(self.compare_requested.emit)
        for button, icon_name in ((self.open_button, "folder"), (self.project_button, "layers")):
            button.setIcon(icons.icon(icon_name, 16))
            button.setProperty("icon_name", icon_name)
            header.addWidget(button)
        compare_button.setIcon(icons.icon("git-compare", 16))
        compare_button.setProperty("icon_name", "git-compare")
        self._sessions_layout = sessions_layout
        self._header_row = header
        self._button_row = QBoxLayout(QBoxLayout.Direction.LeftToRight)
        self._button_row.setSpacing(8)
        self._header_stacked: bool | None = None
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
        self.compare_button = compare_button
        self._body_layout = layout
        self._footer_row = footer
        self._footer_guide_row = QHBoxLayout()
        self._footer_stacked: bool | None = None
        self._paths_stacked: bool | None = None
        layout.addLayout(footer)
        layout.addWidget(self.walkthrough)
        self._place_responsive()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802 - Qt override
        if (
            hasattr(self, "scroll_area")
            and watched is self.scroll_area.viewport()
            and event.type() == QEvent.Type.Resize
        ):
            self._place_responsive()
        return bool(super().eventFilter(watched, event))

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802 - Qt override
        super().resizeEvent(event)
        self._place_responsive()

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802 - Qt override
        super().showEvent(event)
        self._place_responsive()

    def _place_responsive(self) -> None:
        if not hasattr(self, "_sessions_layout"):
            return
        viewport_w = self.scroll_area.viewport().width()
        if self.width() > 0 and (viewport_w <= 0 or viewport_w > self.width()):
            viewport_w = max(self.width() - 16, 320)
        widget = self.scroll_area.widget()
        layout = widget.layout() if widget is not None else None
        margins = layout.contentsMargins() if layout is not None else None
        left_right = (margins.left() + margins.right()) if margins is not None else 64
        available = (viewport_w if viewport_w > 0 else (self.width() - 16)) - left_right
        if available <= 0:
            return

        if hasattr(self, "_paths_layout") and hasattr(self, "composer"):
            b1 = self.path_buttons.get("standalone")
            b2 = self.path_buttons.get("universal_daw")
            if b1 is not None and b2 is not None:
                c_lay = self.composer.layout()
                c_margins = c_lay.contentsMargins() if c_lay is not None else None
                c_padding = (c_margins.left() + c_margins.right()) if c_margins is not None else 32
                c_avail = min(available, self.composer.maximumWidth()) - c_padding
                b1_lay = b1.layout()
                b2_lay = b2.layout()
                fm1 = b1.fontMetrics()
                fm2 = b2.fontMetrics()
                t1 = _("Standalone Mode")
                t2 = _("Universal DAW Mode")
                b1_w = max(
                    b1_lay.sizeHint().width() if b1_lay is not None else 0,
                    b1_lay.minimumSize().width() if b1_lay is not None else 0,
                    b1.sizeHint().width(),
                    fm1.horizontalAdvance(t1) + 62,
                    200,
                )
                b2_w = max(
                    b2_lay.sizeHint().width() if b2_lay is not None else 0,
                    b2_lay.minimumSize().width() if b2_lay is not None else 0,
                    b2.sizeHint().width(),
                    fm2.horizontalAdvance(t2) + 62,
                    200,
                )
                paths_needed = b1_w + b2_w + self._paths_layout.spacing()
                paths_stacked = paths_needed > c_avail
                if paths_stacked != self._paths_stacked:
                    self._paths_stacked = paths_stacked
                    new_dir = (
                        QBoxLayout.Direction.TopToBottom
                        if paths_stacked
                        else QBoxLayout.Direction.LeftToRight
                    )
                    self._paths_layout.setDirection(new_dir)
                    if hasattr(self, "_hero_row"):
                        if paths_stacked:
                            self._hero_row.setStretch(0, 0)
                            self._hero_row.setStretch(1, 1)
                            self._hero_row.setStretch(2, 0)
                        else:
                            self._hero_row.setStretch(0, 1)
                            self._hero_row.setStretch(1, 4)
                            self._hero_row.setStretch(2, 1)
                    self._paths_layout.invalidate()
                    if c_lay is not None:
                        c_lay.invalidate()

        needed = (
            self.sessions_label.sizeHint().width()
            + self.open_button.sizeHint().width()
            + self.project_button.sizeHint().width()
            + 24
        )
        stacked = needed > available
        if stacked != self._header_stacked:
            self._header_stacked = stacked
            if stacked:
                self._header_row.removeWidget(self.open_button)
                self._header_row.removeWidget(self.project_button)
                self._button_row.addWidget(self.open_button)
                self._button_row.addWidget(self.project_button)
                self._button_row.addStretch(1)
                self._sessions_layout.insertLayout(1, self._button_row)
            else:
                self._button_row.removeWidget(self.open_button)
                self._button_row.removeWidget(self.project_button)
                while self._button_row.count():
                    it = self._button_row.takeAt(0)
                    del it
                self._sessions_layout.removeItem(self._button_row)
                self._header_row.addWidget(self.open_button)
                self._header_row.addWidget(self.project_button)

        if self._header_stacked:
            btn_w = (
                self.open_button.sizeHint().width()
                + self.project_button.sizeHint().width()
                + self._button_row.spacing()
            )
            b_dir = (
                QBoxLayout.Direction.TopToBottom
                if btn_w > available
                else QBoxLayout.Direction.LeftToRight
            )
            if self._button_row.direction() != b_dir:
                self._button_row.setDirection(b_dir)
                self._button_row.invalidate()

        footer_needed = (
            self.compare_button.sizeHint().width() + self.guide_button.sizeHint().width() + 20
        )
        footer_stacked = footer_needed > available
        if footer_stacked != self._footer_stacked:
            self._footer_stacked = footer_stacked
            if footer_stacked:
                self._footer_row.removeWidget(self.guide_button)
                while self._footer_guide_row.count():
                    it = self._footer_guide_row.takeAt(0)
                    del it
                self._footer_guide_row.addStretch(1)
                self._footer_guide_row.addWidget(self.guide_button)
                # Walkthrough is the last widget, footer is before it
                idx = self._body_layout.indexOf(self.walkthrough)
                self._body_layout.insertLayout(idx, self._footer_guide_row)
            else:
                self._footer_guide_row.removeWidget(self.guide_button)
                while self._footer_guide_row.count():
                    it = self._footer_guide_row.takeAt(0)
                    del it
                self._body_layout.removeItem(self._footer_guide_row)
                self._footer_row.addWidget(self.guide_button)

        if widget is not None and viewport_w > 0:
            widget.updateGeometry()
            if widget.width() > viewport_w:
                widget.resize(viewport_w, widget.height())

    def _hero(self) -> QVBoxLayout:
        """Icon, title, one sentence and the composer with the two real ways in
        (``measure_strip.MODES``), centred as one group (SPEC §7)."""
        hero = QVBoxLayout()
        hero.setSpacing(8)
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
        lead.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        lead.setMinimumWidth(0)
        hero.addWidget(lead)

        self.composer = QFrame()
        self.composer.setProperty("composer", True)
        self.composer.setMaximumWidth(640)
        self.composer.setMinimumWidth(0)
        self.composer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        inner = QVBoxLayout(self.composer)
        inner.setContentsMargins(16, 16, 16, 12)
        inner.setSpacing(12)
        paths = QBoxLayout(QBoxLayout.Direction.LeftToRight)
        paths.setSpacing(12)
        self._paths_layout = paths
        self._paths_stacked = False
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
            button.setMinimumWidth(0)
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
            heading.setMinimumWidth(0)
            detail = label(text, "caption", wrap=True)
            detail.setMinimumWidth(0)
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
        note_text = label(
            _(
                "A recording profile changes only the wording and the thresholds, never the numbers."
            ),
            "caption",
            wrap=True,
        )
        note_text.setMinimumWidth(0)
        note_text.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        note.addWidget(note_text, 1)
        inner.addLayout(note)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addStretch(1)
        row.addWidget(self.composer, 4)
        row.addStretch(1)
        self._hero_row = row
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
            wrap=True,
        )
        keys.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        keys.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        keys.setMinimumWidth(0)
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
