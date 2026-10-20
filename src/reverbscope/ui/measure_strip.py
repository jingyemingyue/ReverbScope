"""Only a running take's transport is global; configuration lives on its page.

Mode and position are hosted in the measurement context bar. There is one
source of truth for devices and sweep parameters: the measurement pages.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QProgressBar, QPushButton, QWidget

from reverbscope.i18n import N_, _
from reverbscope.ui.design.tokens import SPACE
from reverbscope.ui.pages import DawModePage, StandalonePage
from reverbscope.ui.widgets import set_banner_text
from reverbscope.ui.workspace import WorkspaceModel

MODES = (("standalone", N_("Audio interface")), ("universal_daw", N_("DAW recording")))


class MeasureStrip(QWidget):
    """A transport shown while recording or analysis is active, on every task."""

    mode_changed = Signal(str)
    setup_requested = Signal(str)
    start_requested = Signal(str)

    def __init__(
        self,
        model: WorkspaceModel,
        standalone: StandalonePage,
        daw: DawModePage,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.model, self.standalone, self.daw = model, standalone, daw
        self.setProperty("strip", True)
        self.configuration = QWidget()
        config = QHBoxLayout(self.configuration)
        config.setContentsMargins(0, 0, 0, 0)
        config.setSpacing(SPACE)
        self.mode = QComboBox()
        self.mode.setAccessibleName(_("Measurement method"))
        for key, text in MODES:
            self.mode.addItem(_(text), key)
        self.mode.currentIndexChanged.connect(self._mode_selected)
        config.addWidget(self.mode)
        config.addWidget(QLabel(_("Position")))
        self.position = QComboBox()
        self.position.setEditable(True)
        self.position.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.position.setAccessibleName(_("Measurement position"))
        self.position.setMinimumContentsLength(6)
        self.position.currentTextChanged.connect(self._position_edited)
        config.addWidget(self.position)
        self.phase = QLabel(_("Ready"))
        self.status = QLabel("")
        self.status.setProperty("role", "hint")
        self.status.setWordWrap(True)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setMaximumWidth(20 * SPACE)
        self.setup_button = QPushButton(_("Show measurement"))
        self.setup_button.clicked.connect(lambda: self.setup_requested.emit(self.current_mode()))
        self.stop_button = QPushButton(_("Stop"))
        self.stop_button.setProperty("danger", True)
        self.stop_button.setToolTip(_("Stop the take and silence the output (Esc)."))
        self.stop_button.setAccessibleName(_("Stop measurement"))
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(standalone.stop_measurement)
        row = QHBoxLayout(self)
        row.setContentsMargins(2 * SPACE, SPACE, 2 * SPACE, SPACE)
        row.setSpacing(2 * SPACE)
        row.addWidget(self.phase)
        row.addWidget(self.progress)
        row.addWidget(self.status, 1)
        row.addWidget(self.setup_button)
        row.addWidget(self.stop_button)
        self.stop_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        self.stop_shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
        self.stop_shortcut.activated.connect(self._escape)
        standalone.busy_changed.connect(self._busy)
        daw.busy_changed.connect(self._busy)
        standalone.progress_changed.connect(self.progress.setValue)
        standalone.status_changed.connect(
            lambda text, tone: self._status_if("standalone", text, tone)
        )
        daw.status_changed.connect(lambda text, tone: self._status_if("universal_daw", text, tone))
        standalone.position.textChanged.connect(self._page_position)
        daw.position.textChanged.connect(self._page_position)
        model.project_changed.connect(self._fill_positions)
        self._fill_positions()
        self._set_phase("idle")
        self.hide()

    def set_mode(self, mode: str) -> None:
        index = self.mode.findData(mode)
        if index >= 0 and index != self.mode.currentIndex():
            self.mode.setCurrentIndex(index)

    def current_mode(self) -> str:
        return str(self.mode.currentData())

    def _mode_selected(self, _index: int = 0) -> None:
        self.mode_changed.emit(self.current_mode())

    def _fill_positions(self) -> None:
        text = self.position.currentText()
        self.position.blockSignals(True)
        self.position.clear()
        self.position.addItems(self.model.positions)
        self.position.setEditText(text)
        self.position.blockSignals(False)

    def set_position(self, position: str) -> None:
        self.position.setEditText(position)

    def _position_edited(self, text: str) -> None:
        for page in (self.standalone, self.daw):
            if page.position.text() != text:
                page.position.setText(text)

    def _page_position(self, text: str) -> None:
        if self.position.currentText() != text:
            self.position.blockSignals(True)
            self.position.setEditText(text)
            self.position.blockSignals(False)

    def _busy(self, busy: bool) -> None:
        self.mode.setEnabled(not busy)
        self.position.setEnabled(not busy)
        running = busy and self.standalone.stop_button.isEnabled()
        self.stop_button.setEnabled(running)
        self.progress.setVisible(busy)
        self.progress.setRange(0, 100 if running or not busy else 0)
        self._set_phase("measure" if running else "analyze" if busy else "idle")
        self.setVisible(busy)

    def _set_phase(self, phase: str) -> None:
        self.phase.setProperty("phase", phase)
        self.phase.setText(
            {"idle": _("Ready"), "measure": _("Measuring"), "analyze": _("Analyzing")}[phase]
        )
        self.progress.setProperty("phase", phase)
        self.phase.style().unpolish(self.phase)
        self.phase.style().polish(self.phase)
        self.progress.setTextVisible(phase == "measure")

    def _status_if(self, mode: str, text: str, tone: str) -> None:
        if mode == self.current_mode():
            set_banner_text(self.status, text, tone)
            self.status.setToolTip(text)

    def _escape(self) -> None:
        if self.stop_button.isEnabled():
            self.standalone.stop_measurement()
