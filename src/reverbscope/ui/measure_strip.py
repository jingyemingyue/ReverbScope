"""The measure strip: the controls of a take, always under the workspace.

Device, sample rate, channels, loopback, the position the take belongs to,
Start and Stop. The strip does not measure by itself: its lists and spin
boxes share their models and values with the Standalone page (which keeps
the device logic, the preflight and the workers), so the two never
disagree. Stop and ``Esc`` live here, which is why switching views no
longer stops a take (docs/design/GUI_2_ARCHITECTURE.md §2).
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QWidget,
)

from reverbscope.i18n import N_, _
from reverbscope.ui.pages import DawModePage, StandalonePage
from reverbscope.ui.widgets import label, primary, set_banner_text
from reverbscope.ui.workspace import WorkspaceModel

#: Strip modes, in the order of the mode list.
MODES = (
    ("standalone", N_("Audio interface")),
    ("demo", N_("Demo (no interface)")),
    ("universal_daw", N_("DAW recording")),
)


def _mirror_combo(strip: QComboBox, page: QComboBox) -> None:
    """``strip`` shows ``page``'s list and keeps the same row selected."""
    strip.setModel(page.model())
    strip.setCurrentIndex(page.currentIndex())

    def from_page(index: int) -> None:
        if strip.currentIndex() != index:
            strip.blockSignals(True)
            strip.setCurrentIndex(index)
            strip.blockSignals(False)

    def from_strip(index: int) -> None:
        if page.currentIndex() != index:
            page.setCurrentIndex(index)

    def resync() -> None:
        # The page refills its list with its own signals blocked and then
        # picks the system's default row: show that row, not row 0.
        strip.blockSignals(True)
        strip.setCurrentIndex(page.currentIndex())
        strip.blockSignals(False)

    def later(*_args: object) -> None:
        QTimer.singleShot(0, strip, resync)

    page.currentIndexChanged.connect(from_page)
    strip.currentIndexChanged.connect(from_strip)
    model = page.model()
    model.rowsInserted.connect(later)
    model.rowsRemoved.connect(later)
    model.modelReset.connect(later)


def _mirror_spin(strip: QSpinBox, page: QSpinBox) -> None:
    strip.setRange(page.minimum(), page.maximum())
    strip.setSpecialValueText(page.specialValueText())
    strip.setValue(page.value())

    def follow(target: QSpinBox) -> Callable[[int], None]:
        def set_value(value: int) -> None:
            if target.value() != value:
                target.setValue(value)

        return set_value

    page.valueChanged.connect(follow(strip))
    strip.valueChanged.connect(follow(page))


class MeasureStrip(QWidget):
    """One row of take controls under the three columns."""

    #: The strip's mode list changed: ``standalone``, ``demo`` or ``universal_daw``.
    mode_changed = Signal(str)
    #: Show the full set-up page of the strip's mode.
    setup_requested = Signal(str)
    #: Start: a take (interface, demo) or the DAW import page.
    start_requested = Signal(str)

    def __init__(
        self,
        model: WorkspaceModel,
        standalone: StandalonePage,
        daw: DawModePage,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.model = model
        self.standalone = standalone
        self.daw = daw
        self.setProperty("strip", True)
        self.setAutoFillBackground(True)
        row = QHBoxLayout(self)
        row.setContentsMargins(8, 4, 8, 4)
        row.setSpacing(6)

        self.mode = QComboBox()
        for value, text in MODES:
            self.mode.addItem(_(text), value)
        self.mode.setToolTip(_("How the next measurement is made."))
        self.mode.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.mode.currentIndexChanged.connect(self._mode_selected)
        row.addWidget(self.mode)

        self.device_widgets: list[QWidget] = []
        self.input_device = QComboBox()
        self.output_device = QComboBox()
        self.sample_rate = QComboBox()
        for combo, page_combo, tip in (
            (self.input_device, standalone.input_device, _("Input device")),
            (self.output_device, standalone.output_device, _("Output device")),
            (self.sample_rate, standalone.sample_rate, _("Sample rate")),
        ):
            _mirror_combo(combo, page_combo)
            combo.setToolTip(tip)
            combo.setSizeAdjustPolicy(
                QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
            )
            combo.setMinimumContentsLength(8)
            combo.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.input_channel = QSpinBox()
        _mirror_spin(self.input_channel, standalone.input_channel)
        self.input_channel.setToolTip(_("Input channel (mic)"))
        self.loopback_channel = QSpinBox()
        _mirror_spin(self.loopback_channel, standalone.loopback_channel)
        self.loopback_channel.setToolTip(_("Loopback channel (1-based)"))
        for caption, widget in (
            (_("In"), self.input_device),
            (_("Out"), self.output_device),
            (None, self.sample_rate),
            (_("Mic"), self.input_channel),
            (_("Loopback"), self.loopback_channel),
        ):
            if caption:
                caption_label = label(caption, "hint")
                row.addWidget(caption_label)
                self.device_widgets.append(caption_label)
            row.addWidget(widget, 1 if isinstance(widget, QComboBox) else 0)
            self.device_widgets.append(widget)

        self.position_label = label(_("Position"), "hint")
        row.addWidget(self.position_label)
        self.position = QComboBox()
        self.position.setEditable(True)
        self.position.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.position.setToolTip(
            _("The position this take belongs to; Save lists it under it in the project.")
        )
        self.position.setMinimumContentsLength(6)
        self.position.currentTextChanged.connect(self._position_edited)
        row.addWidget(self.position)

        self.setup_button = QPushButton(_("Set up..."))
        self.setup_button.setToolTip(
            _("All settings of this mode: level, sweep, profile, room and placement.")
        )
        self.setup_button.clicked.connect(
            lambda: self.setup_requested.emit(str(self.mode.currentData()))
        )
        row.addWidget(self.setup_button)
        self.start_button = primary(QPushButton(_("Start")))
        self.start_button.setShortcut("Ctrl+Return")
        self.start_button.clicked.connect(
            lambda: self.start_requested.emit(str(self.mode.currentData()))
        )
        row.addWidget(self.start_button)
        self.stop_button = QPushButton(_("Stop"))
        self.stop_button.setProperty("danger", True)
        self.stop_button.setEnabled(False)
        self.stop_button.setToolTip(_("Stop the take and silence the output (Esc)."))
        self.stop_button.clicked.connect(standalone.stop_measurement)
        row.addWidget(self.stop_button)
        # Esc stops a take from any view; a QShortcut on the strip, which is
        # always visible, so it never competes with a hidden page's button.
        self.stop_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        self.stop_shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
        self.stop_shortcut.activated.connect(self._escape)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setMaximumWidth(120)
        self.progress.setTextVisible(False)
        self.progress.hide()
        row.addWidget(self.progress)
        self.status = QLabel("")
        self.status.setProperty("role", "hint")
        self.status.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.status.setMinimumWidth(60)
        row.addWidget(self.status, 2)

        standalone.busy_changed.connect(self._busy)
        standalone.progress_changed.connect(self.progress.setValue)
        standalone.status_changed.connect(self._status)
        daw.busy_changed.connect(self._busy)
        daw.status_changed.connect(self._status)
        standalone.position.textChanged.connect(self._page_position)
        model.project_changed.connect(self._fill_positions)
        self._fill_positions()
        self._mode_selected()

    # --- mode -----------------------------------------------------------------------

    def set_mode(self, mode: str) -> None:
        index = self.mode.findData(mode)
        if index >= 0 and index != self.mode.currentIndex():
            self.mode.setCurrentIndex(index)

    def current_mode(self) -> str:
        return str(self.mode.currentData())

    def _mode_selected(self, _index: int = 0) -> None:
        mode = self.current_mode()
        live = mode in ("standalone", "demo")
        for widget in self.device_widgets:
            widget.setVisible(live)
        self.start_button.setText(_("Start") if live else _("Import recording..."))
        # In DAW mode Ctrl+Return belongs to the DAW page's Analyze: two
        # visible buttons with one shortcut would make Qt fire neither.
        self.start_button.setShortcut("Ctrl+Return" if live else "")
        self.start_button.setToolTip(
            _("Play the sweep and record it (Ctrl+Return).")
            if live
            else _("Open the DAW recording page to import the recorded WAV file.")
        )
        self.mode_changed.emit(mode)

    # --- position -------------------------------------------------------------------

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

    # --- following a take -----------------------------------------------------------

    def _busy(self, busy: bool) -> None:
        self.start_button.setEnabled(not busy)
        self.mode.setEnabled(not busy)
        self.position.setEnabled(not busy)
        # The page's Stop is on exactly while the sweep plays (the worker may
        # not have started yet when the busy signal arrives).
        running = busy and self.standalone.stop_button.isEnabled()
        self.stop_button.setEnabled(running)
        self.progress.setVisible(busy)
        if busy and not running:
            # The analysis has no progress of its own: a busy bar.
            self.progress.setRange(0, 0)
        else:
            self.progress.setRange(0, 100)

    def _status(self, text: str, tone: str) -> None:
        set_banner_text(self.status, text, tone)
        self.status.setToolTip(text)

    def _escape(self) -> None:
        if self.stop_button.isEnabled():
            self.standalone.stop_measurement()
