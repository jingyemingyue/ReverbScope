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
from PySide6.QtGui import QKeySequence, QResizeEvent, QShortcut
from PySide6.QtWidgets import (
    QBoxLayout,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from reverbscope.i18n import N_, _
from reverbscope.ui import icons
from reverbscope.ui.pages import DawModePage, StandalonePage
from reverbscope.ui.widgets import ElidedComboBox, label, native_shortcut, primary, set_banner_text
from reverbscope.ui.workspace import WorkspaceModel

#: Strip modes, in the order of the mode list. The product has no demo mode;
#: synthetic takes stay a command-line and test facility.
MODES = (
    ("standalone", N_("Audio interface")),
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

    #: The strip's mode list changed: ``standalone`` or ``universal_daw``.
    mode_changed = Signal(str)
    #: Show the full set-up page of the strip's mode.
    setup_requested = Signal(str)
    #: Start: a take on the interface, or the DAW import page.
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
        outer = QVBoxLayout(self)
        self.outer_layout = outer
        outer.setContentsMargins(8, 3, 8, 3)
        outer.setSpacing(2)
        self.control_layout = QBoxLayout(QBoxLayout.Direction.TopToBottom)
        self.control_layout.setSpacing(6)
        outer.addLayout(self.control_layout)
        self.settings_bar = QWidget()
        row = QHBoxLayout(self.settings_bar)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        self.control_layout.addWidget(self.settings_bar, 1)

        self.mode = QComboBox()
        for value, text in MODES:
            self.mode.addItem(_(text), value)
        self.mode.setToolTip(_("How the next measurement is made."))
        self.mode.setAccessibleName(_("Mode"))
        self.mode.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.mode.currentIndexChanged.connect(self._mode_selected)
        row.addWidget(self.mode)

        self.device_widgets: list[QWidget] = []
        self.advanced_widgets: list[QWidget] = []
        self.input_device = ElidedComboBox()
        self.output_device = ElidedComboBox()
        self.sample_rate = QComboBox()
        for combo, page_combo, tip in (
            (self.input_device, standalone.input_device, _("Input device")),
            (self.output_device, standalone.output_device, _("Output device")),
            (self.sample_rate, standalone.sample_rate, _("Sample rate")),
        ):
            _mirror_combo(combo, page_combo)
            combo.setAccessibleName(tip)
            combo.setToolTip(f"{tip}: {combo.currentText()}")
            combo.currentTextChanged.connect(
                lambda text, c=combo, caption=tip: c.setToolTip(f"{caption}: {text}")
            )
            combo.setSizeAdjustPolicy(
                QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
            )
            combo.setMinimumContentsLength(8)
            combo.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.input_channel = QSpinBox()
        _mirror_spin(self.input_channel, standalone.input_channel)
        self.input_channel.setToolTip(_("Input channel (mic)"))
        self.input_channel.setMaximumWidth(64)
        self.sample_rate.setMaximumWidth(130)
        self.loopback_channel = QSpinBox()
        _mirror_spin(self.loopback_channel, standalone.loopback_channel)
        self.loopback_channel.setToolTip(_("Loopback channel (1-based)"))
        # The output stays on the main row: the sweep plays only on an output
        # the user picked here or on the set-up page (OUT-2, OUT-4).
        for caption, widget in (
            (_("In"), self.input_device),
            (_("Out"), self.output_device),
            (None, self.sample_rate),
            (_("Mic"), self.input_channel),
        ):
            if caption:
                caption_label = label(caption, "hint")
                row.addWidget(caption_label)
                self.device_widgets.append(caption_label)
            # The output gets the room first: it is the one Start waits for.
            stretch = {self.input_device: 1, self.output_device: 2}.get(widget, 0)
            row.addWidget(widget, stretch)
            self.device_widgets.append(widget)

        self.advanced_bar = QWidget()
        advanced = QHBoxLayout(self.advanced_bar)
        advanced.setContentsMargins(0, 0, 0, 0)
        advanced.setSpacing(6)
        for caption, widget in ((_("Loopback"), self.loopback_channel),):
            caption_label = label(caption, "hint")
            advanced.addWidget(caption_label)
            advanced.addWidget(widget)
            self.device_widgets.append(caption_label)
            self.device_widgets.append(widget)
            self.advanced_widgets.append(caption_label)
            self.advanced_widgets.append(widget)
        advanced.addStretch(1)
        self.advanced_bar.hide()
        outer.addWidget(self.advanced_bar)

        self.position_label = label(_("Position"), "hint")
        row.addWidget(self.position_label)
        self.position = QComboBox()
        self.position.setEditable(True)
        self.position.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.position.setToolTip(
            _("The position this take belongs to; Save lists it under it in the project.")
        )
        self.position.setMinimumContentsLength(6)
        self.position.setMaximumWidth(140)
        self.position.currentTextChanged.connect(self._position_edited)
        row.addWidget(self.position)

        self.transport_bar = QWidget()
        row = QHBoxLayout(self.transport_bar)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        self.transport_layout = row
        row.addStretch(1)
        self.control_layout.addWidget(self.transport_bar)
        self.advanced_button = QToolButton()
        self.advanced_button.setCheckable(True)
        self.advanced_button.setAutoRaise(True)
        self.advanced_button.setText(_("Advanced"))
        self.advanced_button.setToolTip(_("Loopback channel."))
        self.advanced_button.toggled.connect(self.advanced_bar.setVisible)
        row.addWidget(self.advanced_button)

        self.setup_button = QPushButton(_("Set up..."))
        self.setup_button.setIcon(icons.icon("sliders-vertical", 16))
        self.setup_button.setToolTip(
            _("All settings of this mode: level, sweep, profile, room and placement.")
        )
        self.setup_button.clicked.connect(
            lambda: self.setup_requested.emit(str(self.mode.currentData()))
        )
        row.addWidget(self.setup_button)
        self.start_button = primary(QPushButton(_("Start")))
        self.start_button.setShortcut(QKeySequence("Ctrl+Return"))
        self.start_button.clicked.connect(
            lambda: self.start_requested.emit(str(self.mode.currentData()))
        )
        row.addWidget(self.start_button)
        self.stop_button = QPushButton(_("Stop"))
        self.stop_button.setProperty("danger", True)
        self.stop_button.setIcon(icons.icon("square-stop", 16, tone="on_bad"))
        self.stop_button.setEnabled(False)
        self.stop_button.setToolTip(_("Stop the take and silence the output (Esc)."))
        self.stop_button.clicked.connect(standalone.stop_measurement)
        row.addWidget(self.stop_button)
        self.phase = QLabel(_("Ready"))
        self.phase.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.phase.setMinimumWidth(72)
        self.phase.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        row.addWidget(self.phase, 0, Qt.AlignmentFlag.AlignVCenter)
        # Esc stops a take from any view; a QShortcut on the strip, which is
        # always visible, so it never competes with a hidden page's button.
        self.stop_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        self.stop_shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
        self.stop_shortcut.activated.connect(self._escape)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setMaximumWidth(160)
        self.progress.setFormat("%p%")
        self.progress.setTextVisible(False)
        self.progress.hide()
        self.status = QLabel("")
        self.status.setProperty("role", "hint")
        self.status.setWordWrap(True)
        self.status.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.status.setMinimumWidth(80)
        self.detail = QWidget()
        detail = QHBoxLayout(self.detail)
        detail.setContentsMargins(0, 0, 0, 0)
        detail.setSpacing(8)
        detail.addWidget(self.progress)
        detail.addWidget(self.status, 1)
        self.detail_layout = detail
        self._wrapped = False
        self.detail.hide()
        outer.addWidget(self.detail)

        self._ready, self._reason = standalone._ready
        standalone.readiness_changed.connect(self._readiness)
        standalone.busy_changed.connect(self._busy)
        standalone.progress_changed.connect(self.progress.setValue)
        standalone.status_changed.connect(
            lambda text, tone: self._status_if("standalone", text, tone)
        )
        daw.busy_changed.connect(self._busy)
        daw.status_changed.connect(lambda text, tone: self._status_if("universal_daw", text, tone))
        standalone.position.textChanged.connect(self._page_position)
        model.project_changed.connect(self._fill_positions)
        self._fill_positions()
        self._mode_selected()
        self._set_phase("idle")
        self._sync_start()

    def restyle_icons(self) -> None:
        self.setup_button.setIcon(icons.icon("sliders-vertical", 16))
        self.stop_button.setIcon(icons.icon("square-stop", 16, tone="on_bad"))

    def _readiness(self, ready: bool, reason: str) -> None:
        self._ready, self._reason = ready, reason
        self._sync_start()
        if self.current_mode() == "standalone" and not self.standalone.is_busy():
            if reason:
                self._status(reason, "warn")
            else:
                self._show_page_status()

    def _sync_start(self) -> None:
        """Start is off with the reason beside it while no output is chosen or
        the level is not acknowledged (OUT-4, SAFE)."""
        busy = self.standalone.is_busy() or self.stop_button.isEnabled()
        live = self.current_mode() == "standalone"
        allowed = not busy and (not live or self._ready)
        self.start_button.setEnabled(allowed)
        if live and not busy and self._reason:
            self.start_button.setToolTip(self._reason)

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802 - Qt override
        super().resizeEvent(event)
        self._reflow(event.size().width())

    def _reflow(self, width: int) -> None:
        # Use the current platform's font/style metrics, including the wider
        # DAW import caption. Start and Stop never join a scrolling area.
        margin = self.outer_layout.contentsMargins()
        required = (
            self.settings_bar.minimumSizeHint().width()
            + self.transport_bar.minimumSizeHint().width()
            + self.control_layout.spacing()
            + margin.left()
            + margin.right()
        )
        wrapped = width < required
        self.control_layout.setDirection(
            QBoxLayout.Direction.TopToBottom if wrapped else QBoxLayout.Direction.LeftToRight
        )
        # Wrapped (narrow window): the status line sits left of the buttons
        # on the transport row instead of taking a third row from the chart.
        host = self.transport_layout if wrapped else self.detail_layout
        if self.status.parentWidget() is not (self.transport_bar if wrapped else self.detail):
            self.status.setParent(None)
            if wrapped:
                host.insertWidget(0, self.status, 1)
            else:
                host.addWidget(self.status, 1)
        self._wrapped = wrapped
        self._sync_detail()

    # --- mode -----------------------------------------------------------------------

    def set_mode(self, mode: str) -> None:
        index = self.mode.findData(mode)
        if index >= 0 and index != self.mode.currentIndex():
            self.mode.setCurrentIndex(index)

    def current_mode(self) -> str:
        return str(self.mode.currentData())

    def _mode_selected(self, _index: int = 0) -> None:
        mode = self.current_mode()
        live = mode == "standalone"
        for widget in self.device_widgets:
            widget.setVisible(live)
        self.advanced_button.setVisible(live)
        self.advanced_bar.setVisible(live and self.advanced_button.isChecked())
        self.start_button.setText(_("Start") if live else _("Import recording..."))
        # In DAW mode Ctrl+Return belongs to the DAW page's Analyze: two
        # visible buttons with one shortcut would make Qt fire neither.
        shortcut = QKeySequence("Ctrl+Return") if live else QKeySequence()
        self.start_button.setShortcut(shortcut)
        native = native_shortcut("Ctrl+Return") if live else ""
        self.start_button.setToolTip(
            _("Play the sweep and record it ({shortcut}).").format(shortcut=native)
            if live
            else _("Open the DAW recording page to import the recorded WAV file.")
        )
        self.mode_changed.emit(mode)
        self._show_page_status()
        if hasattr(self, "_ready"):
            self._sync_start()
            if live and self._reason and not self.standalone.is_busy():
                self._status(self._reason, "warn")
        self._reflow(self.width())

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
        self.start_button.setEnabled(
            not busy and (self.current_mode() != "standalone" or self._ready)
        )
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
            self._set_phase("analyze")
        elif running:
            self.progress.setRange(0, 100)
            self._set_phase("measure")
        else:
            self.progress.setRange(0, 100)
            self._set_phase("idle")
        self._sync_detail()

    def _set_phase(self, phase: str) -> None:
        """``idle``, ``measure`` (sweep playing) or ``analyze``."""
        texts = {
            "idle": (_("Ready"), _("Not measuring.")),
            "measure": (
                _("Measuring"),
                _("The sweep is playing. Stop ends it and silences the output."),
            ),
            "analyze": (
                _("Analyzing"),
                _("The recording is being analyzed. Playback has already finished."),
            ),
        }
        caption, tip = texts[phase]
        self.phase.setText(caption)
        self.phase.setToolTip(tip)
        self.phase.setProperty("phase", phase)
        self.phase.style().unpolish(self.phase)
        self.phase.style().polish(self.phase)
        measuring = phase != "idle"
        if bool(self.property("measuring")) != measuring:
            self.setProperty("measuring", measuring)
            self.style().unpolish(self)
            self.style().polish(self)
        self.progress.setProperty("phase", "measure" if phase == "measure" else "")
        self.progress.setTextVisible(phase == "measure")
        self.progress.style().unpolish(self.progress)
        self.progress.style().polish(self.progress)

    def _show_page_status(self) -> None:
        page = self.standalone if self.current_mode() == "standalone" else self.daw
        banner = page.status.property("banner")
        self._status(page.status.text(), banner if isinstance(banner, str) else "")

    def _status_if(self, mode: str, text: str, tone: str) -> None:
        if mode == self.current_mode():
            self._status(text, tone)

    def _status(self, text: str, tone: str) -> None:
        set_banner_text(self.status, text, tone)
        self.status.setToolTip(text)
        self._sync_detail()

    def _sync_detail(self) -> None:
        in_detail = self.status.parentWidget() is self.detail
        self.detail.setVisible(
            (in_detail and bool(self.status.text())) or not self.progress.isHidden()
        )
        self.status.setVisible(bool(self.status.text()))

    def _escape(self) -> None:
        if self.stop_button.isEnabled():
            self.standalone.stop_measurement()
