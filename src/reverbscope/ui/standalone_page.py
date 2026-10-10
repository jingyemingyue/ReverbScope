"""Standalone Mode as four steps: devices and channels, test signal, optional
dimensions, run. Run and Stop live in the fixed action area under the steps.

The page keeps the device checks of the command line (``inventory.preflight``),
the channel plan, the sample-rate check and the playback-level limit, and
feeds the real take progress to its own bar and to the window's status bar.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtGui import QHideEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from reverbscope.audio.backend import ChannelPlan, DeviceInfo, StreamOptions, plan_input_channels
from reverbscope.audio.inventory import DeviceInventory
from reverbscope.audio.playrec import (
    DEFAULT_STANDALONE_LEVEL_DBFS,
    SAFE_MAX_LEVEL_DBFS,
    SAFETY_MESSAGE,
)
from reverbscope.core.pipeline import Reference
from reverbscope.core.sweep import measurement_signal
from reverbscope.demo import DEMO_MODE, FAKE_BACKEND_NOTES
from reverbscope.errors import AudioDeviceError, ReverbScopeError
from reverbscope.i18n import _, list_join, localize
from reverbscope.models.audio import AudioSignal
from reverbscope.models.configuration import SUPPORTED_SAMPLE_RATES, AnalysisSettings, SweepSettings
from reverbscope.models.result import AnalysisResult
from reverbscope.models.session import MeasurementSession
from reverbscope.ui.measure_flow import (
    AnalysisRun,
    TakeRun,
    accept_result,
    ask_separate_clocks,
    late_result_text,
)
from reverbscope.ui.measure_widgets import (
    ActionArea,
    PlacementInputs,
    StepHelp,
    StepPanel,
    metadata_form,
    profile_combo,
    profile_row,
)
from reverbscope.ui.state import MeasurementState
from reverbscope.ui.widgets import (
    CollapsibleSection,
    KeyValueList,
    StepBar,
    error_box,
    label,
    primary,
)
from reverbscope.ui.workspace import action_row

STEP_DEVICES, STEP_SIGNAL, STEP_DIMENSIONS, STEP_RUN = range(4)


def _find_data(combo: QComboBox, value: object) -> int:
    """The first row of ``combo`` whose data is ``value`` (``None`` included)."""
    return next((row for row in range(combo.count()) if combo.itemData(row) == value), -1)


def _scrolled(panel: QWidget) -> QScrollArea:
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QScrollArea.Shape.NoFrame)
    body = QWidget()
    body.setProperty("page", True)
    layout = QVBoxLayout(body)
    layout.setContentsMargins(20, 12, 20, 12)
    layout.addWidget(panel)
    scroll.setWidget(body)
    return scroll


class StandalonePage(QWidget):
    analysis_finished = Signal()
    back = Signal()
    #: ``(busy, text, fraction or None, stoppable)`` for the window's status bar.
    activity_changed = Signal(bool, str, object, bool)
    step_changed = Signal(int)

    def __init__(self, state: MeasurementState, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.state = state
        self.setProperty("page", True)
        self.demo_mode = False
        self._devices: list[DeviceInfo] = []
        self._take = TakeRun(self)
        self._take.recorded.connect(self._on_recorded)
        self._take.failed.connect(self._on_failure)
        self._take.progress.connect(self._on_progress)
        self._take.stopped.connect(self._on_stopped)
        self._analysis = AnalysisRun(state, self)
        self._analysis.succeeded.connect(self._on_success)
        self._analysis.failed.connect(self._on_failure)
        self._channel_plan: ChannelPlan | None = None
        # The output channel the take plays on: the spin box stays editable.
        self._take_output_channel = 1
        # The take runs on the fake backend: its session is a synthetic demo.
        self._take_synthetic = False
        # The take's sweep, analysis settings and profile. They join the
        # shared state with its recording, not before: a refused or stopped
        # Run replaced the reference the Universal DAW page analyses with.
        self._take_settings = state.sweep_settings
        self._take_reference: Reference | None = None
        self._take_analysis_settings = AnalysisSettings()
        self._take_profile = state.profile
        self._inventory: DeviceInventory | None = None
        # The backend that listed :attr:`_inventory`: device indices of
        # another one (the Demo's fake interface) name other devices.
        self._inventory_backend: str | None = None
        # The state generation the running take belongs to.
        self._generation = -1

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        top = QWidget()
        top_layout = QVBoxLayout(top)
        top_layout.setContentsMargins(20, 12, 20, 4)
        top_layout.setSpacing(6)
        self.demo_banner = QLabel(
            _("Demo mode: the fake backend synthesises a room. Nothing is sent to a loudspeaker.")
        )
        self.demo_banner.setWordWrap(True)
        self.demo_banner.setProperty("banner", "info")
        self.demo_banner.hide()
        top_layout.addWidget(self.demo_banner)
        self.steps = StepBar(
            [
                _("Devices and channels"),
                _("Test signal"),
                _("Optional dimensions"),
                _("Run measurement"),
            ]
        )
        self.steps.step_chosen.connect(self.show_step)
        top_layout.addWidget(self.steps)
        outer.addWidget(top)
        self.pages = QStackedWidget()
        outer.addWidget(self.pages, 1)
        self.action_area = ActionArea()
        outer.addWidget(self.action_area)

        self._build_devices()
        self._build_signal()
        self._build_dimensions()
        self._build_run()

        self.back_button = self.action_area.back_button
        self.back_button.clicked.connect(self.back.emit)
        self.action_area.prev_button.clicked.connect(
            lambda: self.show_step(self.steps.current() - 1)
        )
        self.action_area.next_button.clicked.connect(
            lambda: self.show_step(self.steps.current() + 1)
        )
        self.stop_button = QPushButton(_("Stop"))
        self.stop_button.setProperty("danger", True)
        self.stop_button.setShortcut("Esc")
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self.stop_measurement)
        self.run_button = primary(QPushButton(_("Run Measurement")))
        self.run_button.setShortcut("Ctrl+Return")
        self.run_button.setToolTip(_("Play the sweep and record the microphone (Ctrl+Return)."))
        self.run_button.clicked.connect(self.start_measurement)
        self.action_area.right.addWidget(self.stop_button)
        self.action_area.right.addWidget(self.run_button)
        self.progress = self.action_area.progress
        self.status = self.action_area.status
        self.context_actions = action_row()
        self.detail = StepHelp()
        self.show_step(STEP_DEVICES)
        self.refresh_devices()

    # --- building ---------------------------------------------------------------

    def _build_devices(self) -> None:
        from reverbscope.edition import is_developer

        panel = StepPanel(
            _("Devices and channels"),
            _(
                "The interface that plays the sweep and records the microphone. Input and "
                "output must use the same audio system."
            ),
        )
        safety = QLabel(_(SAFETY_MESSAGE))
        safety.setWordWrap(True)
        safety.setProperty("banner", "warn")
        panel.body.addWidget(safety)
        devices = QGroupBox(_("Audio devices"))
        form = QFormLayout(devices)
        self.host_api = QComboBox()
        self.host_api.setToolTip(
            _(
                "How ReverbScope talks to your interface: WASAPI, ASIO, WDM-KS, DirectSound or "
                "MME on Windows, Core Audio on macOS, ALSA or JACK on Linux. Input and output "
                'must use the same one. "System default" uses the devices your system '
                "uses; a star marks the entry recommended for each device."
            )
        )
        self.host_api.currentIndexChanged.connect(self._fill_device_lists)
        self.input_device = QComboBox()
        self.output_device = QComboBox()
        self.refresh_button = QPushButton(_("Refresh devices"))
        self.refresh_button.clicked.connect(self.refresh_devices)
        self.sample_rate = QComboBox()
        for sr in SUPPORTED_SAMPLE_RATES:
            self.sample_rate.addItem(f"{sr} Hz", sr)
        self.sample_rate.setCurrentIndex(
            list(SUPPORTED_SAMPLE_RATES).index(self.state.sweep_settings.sample_rate)
        )
        self.device_rate = QLabel(_("Device rate: unknown"))
        self.device_rate.setWordWrap(True)
        self.device_rate.setProperty("role", "hint")
        self.input_device.currentIndexChanged.connect(self._update_device_rate)
        self.output_device.currentIndexChanged.connect(self._update_device_rate)
        self.sample_rate.currentIndexChanged.connect(self._update_device_rate)
        form.addRow(_("Audio system (host API)"), self.host_api)
        form.addRow(_("Input device"), self.input_device)
        form.addRow(_("Output device"), self.output_device)
        form.addRow("", self.refresh_button)
        form.addRow(_("Sample rate"), self.sample_rate)
        form.addRow("", self.device_rate)
        panel.body.addWidget(devices)
        channels = QGroupBox(_("Channels (1-based, as on the interface)"))
        channel_form = QFormLayout(channels)
        self.input_channel = QSpinBox()
        self.input_channel.setRange(1, 64)
        self.loopback_channel = QSpinBox()
        self.loopback_channel.setRange(0, 64)
        self.loopback_channel.setSpecialValueText(_("unused"))
        self.loopback_channel.setToolTip(
            _("The input the interface output is wired back into, if you use a loopback cable.")
        )
        self.output_channel = QSpinBox()
        self.output_channel.setRange(1, 64)
        channel_form.addRow(_("Input channel (mic)"), self.input_channel)
        channel_form.addRow(_("Loopback channel (1-based)"), self.loopback_channel)
        channel_form.addRow(_("Output channel (speaker)"), self.output_channel)
        panel.body.addWidget(channels)

        self.advanced = QGroupBox(_("Advanced audio options (developer edition)"))
        adv = QFormLayout(self.advanced)
        self.latency = QComboBox()
        self.latency.addItem(_("PortAudio default (high)"), None)
        self.latency.addItem(_("Low"), "low")
        self.latency.addItem(_("High"), "high")
        self.wasapi_exclusive = QCheckBox(
            _("WASAPI exclusive mode (bypasses the Windows audio engine)")
        )
        self.coreaudio_set_rate = QCheckBox(
            _("Core Audio: set the device to the requested rate, never convert")
        )
        adv.addRow(_("Latency"), self.latency)
        adv.addRow(self.wasapi_exclusive)
        adv.addRow(self.coreaudio_set_rate)
        self.advanced_section = CollapsibleSection(_("Advanced audio options"), self.advanced)
        self.advanced_section.setVisible(is_developer())
        self.advanced.setVisible(is_developer())
        if is_developer():
            # Closed by default; the group box is shown when the section opens.
            self.advanced.setVisible(False)
            self.advanced_section.toggled.connect(self.advanced.setVisible)
        panel.body.addWidget(self.advanced_section)
        self.pages.addWidget(_scrolled(panel))

    def _build_signal(self) -> None:
        panel = StepPanel(
            _("Test signal"),
            _("How long the sweep is, how loud it plays, and which profile reads the result."),
        )
        sweep = QGroupBox(_("Test signal"))
        form2 = QFormLayout(sweep)
        self.duration = QDoubleSpinBox()
        self.duration.setRange(1.0, 60.0)
        self.duration.setValue(self.state.sweep_settings.duration_s)
        self.duration.setSuffix(" s")
        self.duration.setToolTip(
            _("Longer sweeps give more signal above the noise floor; 10 s is a good start.")
        )
        self.level = QDoubleSpinBox()
        self.level.setRange(-40.0, 0.0)
        self.level.setValue(DEFAULT_STANDALONE_LEVEL_DBFS)
        self.level.setSuffix(" dBFS")
        self.acknowledge = QCheckBox(
            _("I have set the monitor level low (required above {level:g} dBFS)").format(
                level=SAFE_MAX_LEVEL_DBFS
            )
        )
        form2.addRow(_("Sweep duration"), self.duration)
        form2.addRow(_("Playback level"), self.level)
        form2.addRow(self.acknowledge)
        panel.body.addWidget(sweep)
        profile_box = QGroupBox(_("Interpretation"))
        profile_form = QFormLayout(profile_box)
        self.profile = profile_combo(self.state)
        row, self.profile_help = profile_row(self.profile, self)
        profile_form.addRow(_("Recording profile"), row)
        panel.body.addWidget(profile_box)
        self.pages.addWidget(_scrolled(panel))

    def _build_dimensions(self) -> None:
        panel = StepPanel(
            _("Optional dimensions and metadata"),
            _(
                "Name the room and the position so a project can list the take, and enter "
                "the tape measurements if you want the placement geometry."
            ),
        )
        meta, self.room, self.position, self.mic = metadata_form(self.state)
        panel.body.addWidget(meta)
        self.placement = PlacementInputs()
        panel.body.addWidget(self.placement)
        self.pages.addWidget(_scrolled(panel))

    def _build_run(self) -> None:
        panel = StepPanel(
            _("Run the measurement"),
            _(
                "ReverbScope plays the sweep once, records the microphone, then analyses the "
                "take. Stop ends the take at once and nothing is kept."
            ),
        )
        summary_box = QGroupBox(_("Summary"))
        summary_layout = QVBoxLayout(summary_box)
        self.summary = KeyValueList()
        summary_layout.addWidget(self.summary)
        panel.body.addWidget(summary_box)
        panel.body.addWidget(
            label(
                _(
                    "The result opens on the Results page. A take recorded through a real "
                    "interface exists only in memory until the session is saved."
                ),
                "hint",
                wrap=True,
            )
        )
        self.pages.addWidget(_scrolled(panel))

    # --- steps --------------------------------------------------------------------

    def show_step(self, index: int) -> None:
        index = max(0, min(index, self.pages.count() - 1))
        self.pages.setCurrentIndex(index)
        self.steps.set_current(index)
        self.action_area.set_step_buttons(index, self.pages.count())
        self._update_step_summaries()
        if index == STEP_RUN:
            self._refresh_summary()
        heading, text = self._step_help(index)
        self.detail.show_step(heading, text)
        self.step_changed.emit(index)

    def _step_help(self, index: int) -> tuple[str, str]:
        helps = {
            STEP_DEVICES: (
                _("Devices and channels"),
                _(
                    "Pick the interface the loudspeaker and the microphone are connected "
                    "to. The device rate under the sample rate says what the interface runs "
                    "at; a difference means the interface resamples. Two different devices "
                    "run on two clocks and ReverbScope asks before measuring across them."
                ),
            ),
            STEP_SIGNAL: (
                _("Test signal"),
                _(
                    "The playback level is digital. Above {level:g} dBFS ReverbScope asks "
                    "you to confirm that the monitor level is low; it never changes the "
                    "system volume."
                ).format(level=SAFE_MAX_LEVEL_DBFS),
            ),
            STEP_DIMENSIONS: (
                _("Optional dimensions"),
                _(
                    "Nothing here is required. With the loudspeaker distance every early "
                    "reflection gets a path length; with the microphone height too, the "
                    "vertical axis can be solved. No wall or room shape is ever derived."
                ),
            ),
            STEP_RUN: (
                _("Run measurement"),
                _(
                    "The progress bar follows the take. The analysis after it has no "
                    "percentage: the bar then shows that it is busy. Stop (or Esc) ends a "
                    "take; the analysis cannot be stopped and takes a few seconds."
                ),
            ),
        }
        return helps[index]

    def _update_step_summaries(self) -> None:
        """What the earlier steps settled, under the step bar."""
        if self._devices:
            self.steps.set_summary(
                STEP_DEVICES,
                _("{inp} → {out}, {rate}").format(
                    inp=self.input_device.currentText() or _("none"),
                    out=self.output_device.currentText() or _("none"),
                    rate=self.sample_rate.currentText(),
                ),
            )
        self.steps.set_summary(
            STEP_SIGNAL,
            _("{seconds:.1f} s at {level:g} dBFS, {profile}").format(
                seconds=self.duration.value(),
                level=self.level.value(),
                profile=self.profile.currentText(),
            ),
        )
        parts = [p for p in (self.room.text(), self.position.text()) if p]
        self.steps.set_summary(
            STEP_DIMENSIONS,
            list_join(parts) + ("; " if parts else "") + self.placement.summary(),
        )
        self.steps.set_done(
            STEP_SIGNAL, self.steps.current() > STEP_SIGNAL or self.steps.is_done(STEP_SIGNAL)
        )
        self.steps.set_done(
            STEP_DIMENSIONS,
            self.steps.current() > STEP_DIMENSIONS or self.steps.is_done(STEP_DIMENSIONS),
        )

    def _refresh_summary(self) -> None:
        rows: list[tuple[str, str]] = [
            (_("Audio system"), self.host_api.currentText() or _("unknown")),
            (_("Input device"), self.input_device.currentText() or _("none")),
            (_("Output device"), self.output_device.currentText() or _("none")),
            (_("Sample rate"), self.sample_rate.currentText()),
            (
                _("Channels"),
                _("mic in {mic}, loopback {loopback}, speaker out {out}").format(
                    mic=self.input_channel.value(),
                    loopback=self.loopback_channel.text(),
                    out=self.output_channel.value(),
                ),
            ),
            (
                _("Test signal"),
                _("{seconds:.1f} s at {level:g} dBFS").format(
                    seconds=self.duration.value(), level=self.level.value()
                ),
            ),
            (_("Recording profile"), self.profile.currentText()),
            (_("Tape measurements"), self.placement.summary()),
        ]
        parts = [p for p in (self.room.text(), self.position.text(), self.mic.text()) if p]
        rows.append((_("Metadata"), list_join(parts) if parts else _("none")))
        self.summary.set_rows(rows)

    # --- devices ------------------------------------------------------------------

    def refresh_devices(self) -> None:
        from reverbscope.audio.backend import get_backend
        from reverbscope.audio.inventory import build_inventory

        self.demo_banner.setVisible(self.demo_mode)
        chosen = self._chosen_devices()
        try:
            backend = get_backend("fake" if self.demo_mode else None)
            inventory = build_inventory(backend, probe_rates=False)
        except ReverbScopeError as exc:
            self._devices = []
            self._inventory = None
            self._inventory_backend = None
            self.host_api.clear()
            self._fill_device_lists()
            self.action_area.set_status(
                _("Audio backend unavailable: {error}").format(error=localize(str(exc))), "warn"
            )
            self.run_button.setEnabled(False)
            self.steps.set_done(STEP_DEVICES, False)
            return
        if backend.name != self._inventory_backend:
            chosen = None
        self._inventory = inventory
        self._inventory_backend = backend.name
        self._devices = [probe.device for probe in inventory.devices]
        self.host_api.blockSignals(True)
        self.host_api.clear()
        self.host_api.addItem(_("System default"), None)
        used = [api for api in inventory.host_apis if api.device_count > 0]
        for api in sorted(used, key=lambda a: (a.rank is None, a.rank or 0, a.index)):
            self.host_api.addItem(api.name, api.name)
        # Preselect the best-ranked host API that has devices (WASAPI before
        # MME on Windows); a single-API system keeps "System default".
        if len(used) > 1:
            self.host_api.setCurrentIndex(1)
        if chosen is not None and _find_data(self.host_api, chosen[0]) >= 0:
            self.host_api.setCurrentIndex(_find_data(self.host_api, chosen[0]))
        else:
            chosen = None
        self.host_api.blockSignals(False)
        self._fill_device_lists()
        if chosen is not None:
            # Refresh, Ctrl+2 and coming back from Results list the devices
            # again; the next take stays on the interface chosen, not on the
            # system's default devices, while it is still there.
            for combo, device in ((self.input_device, chosen[1]), (self.output_device, chosen[2])):
                row = self._row_of(combo, device)
                if row >= 0:
                    combo.setCurrentIndex(row)
        # Refresh (button, Ctrl+2, Back -> Demo) can run during a take; Run
        # must stay off then, or a second take replaces the running thread.
        # With no device at all a take would only end in PortAudio's own
        # English error ("Error querying device -1").
        self.run_button.setEnabled(not self.is_busy() and bool(self._devices))
        self.steps.set_done(STEP_DEVICES, bool(self._devices))
        if self.is_busy():
            return
        if self.demo_mode:
            self.action_area.set_status(_("Demo mode: fake backend, no loudspeaker."), "info")
        elif not self._devices:
            self.action_area.set_status(
                _("No audio device found; Universal DAW Mode still works."), "warn"
            )
        else:
            self.action_area.set_status(
                _("{n} audio device(s) found.").format(n=len(self._devices))
            )

    def _chosen_devices(
        self,
    ) -> tuple[object, tuple[int, str] | None, tuple[int, str] | None] | None:
        """The host API and the (index, name) of the devices chosen now.

        ``None`` before the first list. A device is kept by name too: an
        interface plugged in again can come back under another index.
        """
        if self._inventory is None or not self.host_api.count():
            return None

        def device(combo: QComboBox) -> tuple[int, str] | None:
            index = combo.currentData()
            name = next((d.name for d in self._devices if d.index == index), None)
            return None if index is None or name is None else (int(index), name)

        return self.host_api.currentData(), device(self.input_device), device(self.output_device)

    def _row_of(self, combo: QComboBox, device: tuple[int, str] | None) -> int:
        """The row of ``device`` in ``combo``: the same index and name, else the
        one device of that name (an interface plugged in again comes back under
        another index), else -1 (its index now names another device)."""
        if device is None:
            return _find_data(combo, None)
        index, name = device
        if any(d.index == index and d.name == name for d in self._devices):
            return _find_data(combo, index)
        same_name = [d.index for d in self._devices if d.name == name]
        if len(same_name) == 1:
            return _find_data(combo, same_name[0])
        return -1

    def _fill_device_lists(self) -> None:
        """Devices of the chosen host API; the recommended entries are starred.

        The preselection is the system's choice, not ReverbScope's: "System
        default" under "System default", else the host API's own default
        device, and the first starred entry only when the host API has none.
        A star is a hint (on macOS every Core Audio device, virtual ones
        included, is its own recommended entry).
        """
        api = self.host_api.currentData() if self.host_api.count() else None
        probes = self._inventory.devices if self._inventory is not None else ()
        for combo in (self.input_device, self.output_device):
            combo.blockSignals(True)
            combo.clear()
        if api is None:
            self.input_device.addItem(_("System default"), None)
            self.output_device.addItem(_("System default"), None)
        for probe in probes:
            d = probe.device
            if api is not None and d.host_api != api:
                continue
            name = f"[{d.index}] {d.name} ({d.host_api})"
            if d.is_input:
                star = "★ " if probe.recommended_input else ""
                self.input_device.addItem(
                    _("{name} - {count} in").format(
                        name=f"{star}{name}", count=d.max_input_channels
                    ),
                    d.index,
                )
            if d.is_output:
                star = "★ " if probe.recommended_output else ""
                self.output_device.addItem(
                    _("{name} - {count} out").format(
                        name=f"{star}{name}", count=d.max_output_channels
                    ),
                    d.index,
                )
        chosen = next(
            (a for a in (self._inventory.host_apis if self._inventory else ()) if a.name == api),
            None,
        )
        for combo, default, attr in (
            (self.input_device, chosen.default_input if chosen else None, "recommended_input"),
            (self.output_device, chosen.default_output if chosen else None, "recommended_output"),
        ):
            row = combo.findData(default) if default is not None else -1
            if row < 0 and api is not None:
                row = next(
                    (
                        r
                        for r in range(combo.count())
                        if any(
                            p.device.index == combo.itemData(r) and getattr(p, attr) for p in probes
                        )
                    ),
                    -1,
                )
            if row >= 0:
                combo.setCurrentIndex(row)
            combo.blockSignals(False)
        kind = next(
            (
                a.kind
                for a in (self._inventory.host_apis if self._inventory else ())
                if a.name == api
            ),
            "",
        )
        self.wasapi_exclusive.setEnabled(kind == "wasapi")
        self.coreaudio_set_rate.setEnabled(kind == "coreaudio")
        self._update_device_rate()

    def stream_options(self) -> StreamOptions:
        return StreamOptions(
            latency=self.latency.currentData(),
            wasapi_exclusive=self.wasapi_exclusive.isEnabled()
            and self.wasapi_exclusive.isChecked(),
            coreaudio_change_device_rate=self.coreaudio_set_rate.isEnabled()
            and self.coreaudio_set_rate.isChecked(),
        )

    def _preflight(
        self, input_channels: list[int], sample_rate: int
    ) -> tuple[int | None, int | None] | None:
        """The checks the CLI makes too (``inventory.preflight``), before playing."""
        from reverbscope.audio.backend import get_backend
        from reverbscope.audio.inventory import preflight

        if self._inventory is None:
            QMessageBox.critical(
                self,
                _("Audio backend unavailable"),
                _("No audio device list is available; Universal DAW Mode still works."),
            )
            return None
        try:
            backend = get_backend("fake" if self.demo_mode else None)
        except ReverbScopeError as exc:
            QMessageBox.critical(self, _("Invalid settings"), localize(str(exc)))
            return None
        if backend.name != self._inventory_backend:
            # Settings chose another backend while a take ran (the list is
            # made again at once otherwise): the numbers in the list name
            # that backend's devices, not this one's.
            self.refresh_devices()
            QMessageBox.warning(
                self,
                _("Audio backend changed"),
                _(
                    "The audio backend was changed in Settings, so the device list has been "
                    "made again. Check the devices, then start the measurement again."
                ),
            )
            return None
        try:
            plan = preflight(
                backend,
                self._inventory,
                input_device=self.input_device.currentData(),
                output_device=self.output_device.currentData(),
                input_channels=input_channels,
                output_channel=int(self.output_channel.value()),
                sample_rate=sample_rate,
                options=self.stream_options(),
            )
        except AudioDeviceError as exc:
            QMessageBox.critical(self, _("Sample rate not supported"), localize(str(exc)))
            return None
        except ReverbScopeError as exc:
            QMessageBox.critical(self, _("Invalid settings"), localize(str(exc)))
            return None
        if plan.clock_warning and not ask_separate_clocks(self, plan.clock_warning):
            return None
        return plan.input_device, plan.output_device

    def _device_for(self, combo: QComboBox, *, kind: str) -> DeviceInfo | None:
        index = combo.currentData()
        for device in self._devices:
            if index is None:
                if kind == "input" and device.is_default_input:
                    return device
                if kind == "output" and device.is_default_output:
                    return device
            elif device.index == index:
                return device
        return None

    def _update_device_rate(self) -> None:
        requested = self.sample_rate.currentData()
        requested_hz = int(requested) if requested is not None else 0
        inp = self._device_for(self.input_device, kind="input")
        out = self._device_for(self.output_device, kind="output")
        parts: list[str] = []
        if inp is not None:
            parts.append(_("in {rate:.0f} Hz").format(rate=inp.default_sample_rate))
        if out is not None and (
            inp is None
            or out.index != inp.index
            or abs(out.default_sample_rate - inp.default_sample_rate) > 0.5
        ):
            parts.append(_("out {rate:.0f} Hz").format(rate=out.default_sample_rate))
        device_txt = list_join(parts) if parts else _("unknown")
        text = _("Device rate: {device}  (requested {requested} Hz)").format(
            device=device_txt, requested=requested_hz
        )
        mismatch = False
        for device in (inp, out):
            if (
                device is not None
                and requested_hz
                and abs(device.default_sample_rate - requested_hz) > 1.0
            ):
                mismatch = True
        if mismatch:
            text += _(" — rates differ; the interface may resample")
        self.device_rate.setText(text)

    def current_sweep_settings(self) -> SweepSettings:
        return SweepSettings(
            sample_rate=int(self.sample_rate.currentData()),
            duration_s=float(self.duration.value()),
            level_dbfs=float(self.level.value()),
        )

    # --- the take -----------------------------------------------------------------

    @property
    def _measure_worker(self) -> object:
        return self._take.worker

    @property
    def _analysis_worker(self) -> object:
        return self._analysis.worker

    def is_busy(self) -> bool:
        """A take or its analysis is still running."""
        return self._take.is_running() or self._analysis.is_running()

    def shutdown_workers(self) -> None:
        """Stop a take (silencing the output) and let both workers finish."""
        self._take.request_stop()
        self._take.wait()
        self._analysis.wait()

    def hideEvent(self, event: QHideEvent) -> None:  # noqa: N802 - Qt override
        # Leaving the page (not minimising the window) stops a take: Stop and
        # Esc live on this page, so the sweep must not go on playing unseen.
        if not event.spontaneous() and self._take.worker is not None:
            self._take.request_stop()
        super().hideEvent(event)

    def start_measurement(self) -> None:
        from reverbscope.audio.backend import get_backend

        if self.is_busy():
            return
        try:
            settings = self.current_sweep_settings()
        except ReverbScopeError as exc:
            QMessageBox.critical(self, _("Invalid settings"), localize(str(exc)))
            return
        if settings.level_dbfs > SAFE_MAX_LEVEL_DBFS and not self.acknowledge.isChecked():
            self.show_step(STEP_SIGNAL)
            QMessageBox.warning(
                self,
                _("Level too high"),
                _(
                    "Levels above {level:g} dBFS need the acknowledgement checkbox. "
                    "Set the monitor level low first."
                ).format(level=SAFE_MAX_LEVEL_DBFS),
            )
            return
        hardware_loopback = int(self.loopback_channel.value())
        try:
            # 1-based interface inputs → 0-based recording columns, checked
            # before anything is played (#13).
            plan = plan_input_channels(
                [int(self.input_channel.value())],
                hardware_loopback if hardware_loopback > 0 else None,
            )
        except ReverbScopeError as exc:
            QMessageBox.critical(self, _("Invalid settings"), localize(str(exc)))
            return
        devices = self._preflight(list(plan.input_channels), settings.sample_rate)
        if devices is None:
            return
        input_device, output_device = devices
        # Resolved once, for the take and for its session: Settings or
        # REVERBSCOPE_AUDIO_BACKEND can choose the fake backend outside Demo too.
        backend = get_backend("fake" if self.demo_mode else None).name
        self._take_synthetic = backend == "fake"
        self._channel_plan = plan
        self._take_output_channel = int(self.output_channel.value())
        self._take_settings = settings
        self._take_reference = Reference.from_settings(settings)
        place = self.placement.analysis_kwargs()
        self._take_analysis_settings = AnalysisSettings(
            channel=plan.analysis_channel,
            loopback_channel=plan.analysis_loopback_channel,
            placement_distance_m=place["placement_distance_m"],
            placement_mic_height_m=place["placement_mic_height_m"],
            placement_temperature_c=place["placement_temperature_c"],
        )
        self._take_profile = str(self.profile.currentData())
        self.show_step(STEP_RUN)
        self._set_busy(True, _("Playing the sweep and recording..."), fraction=0.0)
        self._generation = self.state.generation
        self._take.start(
            measurement_signal(settings),
            settings.sample_rate,
            input_device=input_device,
            output_device=output_device,
            input_channels=list(plan.input_channels),
            output_channel=self._take_output_channel,
            level_dbfs=settings.level_dbfs,
            backend=backend,
            options=self.stream_options(),
            loopback_channel=plan.loopback_channel,
        )

    def stop_measurement(self) -> None:
        self._take.request_stop()

    def _on_progress(self, fraction: float) -> None:
        self.progress.setRange(0, 100)
        self.progress.setValue(int(fraction * 100.0))
        self.activity_changed.emit(True, self.status.text(), fraction, True)

    def _on_stopped(self) -> None:
        self._set_busy(False, _("Stopped."))

    def _stale(self) -> bool:
        """As :meth:`DawModePage._stale`."""
        return self._generation != self.state.generation or not self.window().isVisible()

    def _on_recorded(self, recording: AudioSignal) -> None:
        if self._stale():
            self._set_busy(False, late_result_text(), tone="warn")
            return
        plan = self._channel_plan
        reference = self._take_reference
        assert plan is not None and reference is not None
        # The take takes the shared state: an analysis another page started
        # meanwhile is late from here on.
        self._generation = self.state.claim()
        self.state.mode = "standalone"
        self.state.recording = recording
        self.state.recording_path = None
        self.state.reference = reference
        self.state.sweep_settings = self._take_settings
        self.state.sweep_path = None
        self.state.analysis_settings = self._take_analysis_settings
        self.state.profile = self._take_profile
        # The session stores the 1-based interface channels of the take. A
        # take on the fake backend is marked like `reverbscope demo`'s sessions,
        # so it is never mistaken for a measurement of a real room.
        self.state.session = MeasurementSession(
            mode=DEMO_MODE if self._take_synthetic else "standalone",
            room_name=self.room.text(),
            measurement_position=self.position.text(),
            microphone_name=self.mic.text(),
            notes=FAKE_BACKEND_NOTES if self._take_synthetic else "",
            input_channel=plan.microphone_channel,
            loopback_channel=plan.loopback_channel,
            output_channel=self._take_output_channel,
            sweep_settings=self._take_settings,
            analysis_settings=self._take_analysis_settings,
            recording_profile=self._take_profile,
        )
        # The take is over; Stop cannot cancel the analysis, and its progress
        # has no percentage: a busy bar, never a number.
        self.stop_button.setEnabled(False)
        self.progress.setRange(0, 0)
        self.action_area.set_status(_("Recorded. Analyzing..."))
        self.activity_changed.emit(True, _("Recorded. Analyzing..."), None, False)
        self._analysis.start(
            recording, reference, self._take_analysis_settings, generation=self._generation
        )

    def _set_busy(
        self, busy: bool, text: str = "", *, tone: str = "", fraction: float | None = None
    ) -> None:
        self.run_button.setEnabled(not busy and bool(self._devices))
        self.stop_button.setEnabled(busy)
        self.back_button.setEnabled(not busy)
        self.refresh_button.setEnabled(not busy)
        self.progress.setVisible(busy)
        if busy:
            if fraction is None:
                self.progress.setRange(0, 0)
            else:
                self.progress.setRange(0, 100)
                self.progress.setValue(int(fraction * 100.0))
        else:
            self.progress.setRange(0, 100)
            self.progress.setValue(0)
        self.action_area.set_status(text, tone)
        self.activity_changed.emit(busy, text, fraction, busy)

    def _on_success(self, result: AnalysisResult) -> None:
        if self._stale():
            self._set_busy(False, late_result_text(), tone="warn")
            return
        accept_result(self.state, result)
        self.state.unsaved_take = (
            not self.demo_mode
            and self.state.recording is not None
            and self.state.recording_path is None
        )
        self.steps.set_summary(STEP_RUN, _("analysed; the result is on the Results page"))
        self.steps.set_done(STEP_RUN, True)
        self._set_busy(False, _("Done."))
        self.analysis_finished.emit()

    def _on_failure(self, message: str) -> None:
        self._set_busy(
            False, _("Measurement failed: {message}").format(message=message), tone="warn"
        )
        if not self._stale():
            error_box(self, _("Measurement failed"), message)
