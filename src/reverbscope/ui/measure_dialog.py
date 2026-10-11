"""The two measurement entries of the workbench: a Standalone take on an
audio interface, and the analysis of a recording made in a DAW.

Both are compact dialogs that validate on accept exactly as the command
line does and hand the workbench a request dataclass; nothing here plays,
records or analyses. The
:class:`~reverbscope.ui.measurement_controller.MeasurementController` runs
the request as a job of its own, so the dialog can be closed and reopened
while a take runs without touching that job.

Synthetic data: a take recorded on the fake backend (chosen in Settings or
through ``REVERBSCOPE_AUDIO_BACKEND``; the dialog has no switch for it) is
marked like ``reverbscope demo``'s sessions (:data:`~reverbscope.demo.DEMO_MODE`,
:data:`~reverbscope.demo.FAKE_BACKEND_NOTES`), so it is never mistaken for a
measurement of a real room.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from reverbscope.audio.backend import DeviceInfo, StreamOptions, plan_input_channels
from reverbscope.audio.inventory import DeviceInventory
from reverbscope.audio.playrec import (
    DEFAULT_STANDALONE_LEVEL_DBFS,
    SAFE_MAX_LEVEL_DBFS,
    SAFETY_MESSAGE,
)
from reverbscope.core.pipeline import Reference
from reverbscope.demo import DEMO_MODE, FAKE_BACKEND_NOTES
from reverbscope.errors import AudioDeviceError, ReverbScopeError
from reverbscope.i18n import N_, _, list_join, localize
from reverbscope.io.wav import load_reference, read_wav, write_sweep_file
from reverbscope.models.audio import AudioSignal
from reverbscope.models.configuration import SUPPORTED_SAMPLE_RATES, AnalysisSettings, SweepSettings
from reverbscope.models.session import MeasurementSession
from reverbscope.ui.measure_flow import ask_separate_clocks
from reverbscope.ui.measure_widgets import (
    PlacementInputs,
    metadata_form,
    profile_combo,
    profile_row,
)
from reverbscope.ui.widgets import (
    CollapsibleSection,
    ask_save_path,
    label,
    primary,
    set_banner_text,
)

#: How a DAW records the test signal, step by step. Long, so the dialog
#: keeps it in a section that is closed by default.
DAW_INSTRUCTIONS = N_(
    "1. Generate the test signal at your DAW project's sample rate (Step 1).\n"
    "2. Import it on a new track. Switch time-stretching off for that clip (Warp, Flex, Follow Tempo, elastic audio) and bypass plug-ins on its track and on the master bus, including room-correction plug-ins.\n"
    "3. Route that track to the one loudspeaker you want to test.\n"
    "4. Arm a second track with the measurement microphone (input monitoring off) and record while the test signal plays.\n"
    "5. Export the recorded track as WAV, AIFF, CAF or FLAC at the project sample rate, without normalising.\n"
    "   Do not trim it - ReverbScope finds the sweep automatically.\n"
    "Start with a low monitor level; the sweep should be clearly audible but not loud.\n"
    "The user guide has step-by-step notes for Pro Tools, Logic Pro, Cubase, Studio One, Ableton Live, REAPER, FL Studio and Bitwig Studio."
)

#: The dialogs' size: compact, and never wider than a small laptop's
#: workbench leaves beside the charts.
DIALOG_SIZE = (640, 560)
MIN_DIALOG_SIZE = (480, 360)


@dataclass
class TakeRequest:
    """Everything a Standalone take needs, validated; the controller plays it.

    ``input_channels`` and ``loopback_channel`` are the 1-based interface
    inputs to record (what the session stores); ``analysis_settings`` holds
    the 0-based recording columns (:func:`plan_input_channels`). ``backend``
    is the resolved backend's name, so the take opens the devices the list
    named. ``synthetic`` marks a take on the fake backend: nothing was played.
    """

    settings: SweepSettings
    analysis_settings: AnalysisSettings
    profile: str
    session: MeasurementSession
    input_device: int | None
    output_device: int | None
    input_channels: list[int]
    output_channel: int
    loopback_channel: int | None
    backend: str | None
    options: StreamOptions
    reference: Reference
    synthetic: bool


@dataclass
class AnalysisRequest:
    """A recording made in a DAW with the reference to deconvolve it with."""

    recording: AudioSignal
    recording_path: Path | None
    reference: Reference
    sweep_path: Path | None
    settings: SweepSettings
    analysis_settings: AnalysisSettings
    profile: str
    session: MeasurementSession


# --- shared pieces ------------------------------------------------------------------


def _find_data(combo: QComboBox, value: object) -> int:
    """The first row of ``combo`` whose data is ``value`` (``None`` included)."""
    return next((row for row in range(combo.count()) if combo.itemData(row) == value), -1)


def _form(box: QGroupBox) -> QFormLayout:
    """A compact form: labels left, fields that may grow take the width."""
    form = QFormLayout(box)
    form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
    form.setHorizontalSpacing(10)
    form.setVerticalSpacing(6)
    return form


def _wide(combo: QComboBox) -> QComboBox:
    """A combo that takes the row's width without widening the dialog for a
    long device name."""
    combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
    combo.setMinimumContentsLength(24)
    return combo


def _sample_rate_combo(sample_rate: int) -> QComboBox:
    combo = QComboBox()
    for sr in SUPPORTED_SAMPLE_RATES:
        combo.addItem(f"{sr} Hz", sr)
    combo.setCurrentIndex(max(combo.findData(sample_rate), 0))
    return combo


def _seconds(value: float) -> QDoubleSpinBox:
    box = QDoubleSpinBox()
    box.setRange(1.0, 60.0)
    box.setValue(value)
    box.setSuffix(" s")
    return box


def _dbfs(value: float) -> QDoubleSpinBox:
    box = QDoubleSpinBox()
    box.setRange(-40.0, 0.0)
    box.setValue(value)
    box.setSuffix(" dBFS")
    return box


class _MeasureDialog(QDialog):
    """What both dialogs share: the scrolling body, the button row, the
    interpretation, metadata and placement groups."""

    def __init__(
        self,
        parent: QWidget | None,
        title: str,
        *,
        profile: str,
        room: str,
        position: str,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setSizeGripEnabled(True)
        self.setMinimumSize(*MIN_DIALOG_SIZE)
        self.resize(*DIALOG_SIZE)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        page = QWidget()
        page.setProperty("page", True)
        self.body = QVBoxLayout(page)
        self.body.setContentsMargins(12, 10, 12, 10)
        self.body.setSpacing(8)
        scroll.setWidget(page)
        outer.addWidget(scroll, 1)
        footer = QWidget()
        self.buttons = QHBoxLayout(footer)
        self.buttons.setContentsMargins(12, 8, 12, 10)
        self.buttons.setSpacing(8)
        self.buttons.addStretch(1)
        self.cancel_button = QPushButton(_("Cancel"))
        self.cancel_button.setAutoDefault(False)
        self.cancel_button.clicked.connect(self.reject)
        outer.addWidget(footer)
        self._profile_default = profile
        self._room_default = room
        self._position_default = position

    def _add_interpretation(self) -> None:
        box = QGroupBox(_("Interpretation"))
        form = _form(box)
        self.profile = profile_combo(self._profile_default)
        row, self.profile_help = profile_row(self.profile, self)
        form.addRow(_("Recording profile"), row)
        self.body.addWidget(box)

    def _add_metadata(self) -> None:
        box, self.room, self.position, self.mic = metadata_form(
            self._room_default, self._position_default, ""
        )
        self.body.addWidget(box)

    def _add_placement(self) -> None:
        """The tape measurements, closed by default: nothing there is required."""
        self.placement = PlacementInputs()
        self.placement_section = CollapsibleSection(
            _("Optional tape measurements (placement geometry)"), self.placement
        )
        self.body.addWidget(self.placement_section)

    def _finish_buttons(self, main: QPushButton) -> None:
        """``main`` first (the default button, Ctrl+Return), then Cancel."""
        main.setDefault(True)
        main.setShortcut("Ctrl+Return")
        self.buttons.addWidget(main)
        self.buttons.addWidget(self.cancel_button)

    def _analysis_settings(self, channel: int | None, loopback: int | None) -> AnalysisSettings:
        distance_m, mic_height_m, temperature_c = self.placement.values()
        return AnalysisSettings(
            channel=channel,
            loopback_channel=loopback,
            placement_distance_m=distance_m,
            placement_mic_height_m=mic_height_m,
            placement_temperature_c=temperature_c,
        )


# --- Standalone Mode ---------------------------------------------------------------


class StandaloneMeasureDialog(_MeasureDialog):
    """Devices and channels, test signal, profile, metadata, placement; Run.

    Keeps the device checks of the command line (``inventory.preflight``),
    the channel plan, the sample-rate check and the playback-level limit.
    ``backend`` names the backend whose devices are listed (``None``:
    Settings, ``REVERBSCOPE_AUDIO_BACKEND`` or PortAudio); it is a hook for
    the tests, not a switch the dialog shows.
    """

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        profile: str = "generic",
        position: str = "",
        room: str = "",
        backend: str | None = None,
    ) -> None:
        super().__init__(
            parent, _("Standalone Mode"), profile=profile, room=room, position=position
        )
        self._backend = backend
        self._devices: list[DeviceInfo] = []
        self._inventory: DeviceInventory | None = None
        #: The backend that listed :attr:`_inventory`: device indices of
        #: another one name other devices.
        self._inventory_backend: str | None = None
        self._request: TakeRequest | None = None
        self.safety = QLabel()
        self.safety.setWordWrap(True)
        set_banner_text(self.safety, _(SAFETY_MESSAGE), "warn")
        self.body.addWidget(self.safety)
        self._build_devices()
        self._build_channels()
        self._build_advanced()
        self._build_signal()
        self._add_interpretation()
        self._add_metadata()
        self._add_placement()
        self.body.addStretch(1)
        self.run_button = primary(QPushButton(_("Run measurement")))
        self.run_button.setToolTip(_("Play the sweep and record the microphone (Ctrl+Return)."))
        self.run_button.clicked.connect(self._run)
        self._finish_buttons(self.run_button)
        self.refresh_devices()

    # --- building ---------------------------------------------------------------

    def _build_devices(self) -> None:
        box = QGroupBox(_("Audio devices"))
        form = _form(box)
        self.host_api = _wide(QComboBox())
        self.host_api.setToolTip(
            _(
                "How ReverbScope talks to your interface: WASAPI, ASIO, WDM-KS, DirectSound or "
                "MME on Windows, Core Audio on macOS, ALSA or JACK on Linux. Input and output "
                'must use the same one. "System default" uses the devices your system '
                "uses; a star marks the entry recommended for each device."
            )
        )
        self.host_api.currentIndexChanged.connect(self._fill_device_lists)
        self.input_device = _wide(QComboBox())
        self.output_device = _wide(QComboBox())
        self.refresh_button = QPushButton(_("Refresh devices"))
        self.refresh_button.setAutoDefault(False)
        self.refresh_button.clicked.connect(self.refresh_devices)
        self.device_hint = label("", "hint", wrap=True)
        refresh_row = QHBoxLayout()
        refresh_row.setSpacing(8)
        refresh_row.addWidget(self.refresh_button)
        refresh_row.addWidget(self.device_hint, 1)
        self.sample_rate = _sample_rate_combo(SweepSettings().sample_rate)
        self.device_rate = label(_("Device rate: unknown"), "hint", wrap=True)
        self.input_device.currentIndexChanged.connect(self._update_device_rate)
        self.output_device.currentIndexChanged.connect(self._update_device_rate)
        self.sample_rate.currentIndexChanged.connect(self._update_device_rate)
        form.addRow(_("Audio system (host API)"), self.host_api)
        form.addRow(_("Input device"), self.input_device)
        form.addRow(_("Output device"), self.output_device)
        form.addRow("", refresh_row)
        form.addRow(_("Sample rate"), self.sample_rate)
        form.addRow("", self.device_rate)
        self.body.addWidget(box)

    def _build_channels(self) -> None:
        box = QGroupBox(_("Channels (1-based, as on the interface)"))
        form = _form(box)
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
        form.addRow(_("Input channel (mic)"), self.input_channel)
        form.addRow(_("Loopback channel (1-based)"), self.loopback_channel)
        form.addRow(_("Output channel (speaker)"), self.output_channel)
        self.body.addWidget(box)

    def _build_advanced(self) -> None:
        """Host-API stream options; shown in the developer edition only."""
        from reverbscope.edition import is_developer

        self.advanced = QGroupBox(_("Advanced audio options (developer edition)"))
        form = _form(self.advanced)
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
        form.addRow(_("Latency"), self.latency)
        form.addRow(self.wasapi_exclusive)
        form.addRow(self.coreaudio_set_rate)
        self.advanced_section = CollapsibleSection(_("Advanced audio options"), self.advanced)
        self.advanced_section.setVisible(is_developer())
        self.body.addWidget(self.advanced_section)

    def _build_signal(self) -> None:
        box = QGroupBox(_("Test signal"))
        form = _form(box)
        self.duration = _seconds(SweepSettings().duration_s)
        self.duration.setToolTip(
            _("Longer sweeps give more signal above the noise floor; 10 s is a good start.")
        )
        self.level = _dbfs(DEFAULT_STANDALONE_LEVEL_DBFS)
        self.acknowledge = QCheckBox(
            _("I have set the monitor level low (required above {level:g} dBFS)").format(
                level=SAFE_MAX_LEVEL_DBFS
            )
        )
        form.addRow(_("Sweep duration"), self.duration)
        form.addRow(_("Playback level"), self.level)
        form.addRow(self.acknowledge)
        self.body.addWidget(box)

    # --- devices ------------------------------------------------------------------

    def refresh_devices(self) -> None:
        """List the devices again; the interface chosen stays chosen while it is there."""
        from reverbscope.audio.backend import get_backend
        from reverbscope.audio.inventory import build_inventory

        chosen = self._chosen_devices()
        try:
            backend = get_backend(self._backend)
            inventory = build_inventory(backend, probe_rates=False)
        except ReverbScopeError as exc:
            self._devices = []
            self._inventory = None
            self._inventory_backend = None
            self.host_api.clear()
            self._fill_device_lists()
            set_banner_text(
                self.device_hint,
                _("Audio backend unavailable: {error}").format(error=localize(str(exc))),
                "warn",
            )
            self.run_button.setEnabled(False)
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
            # A refresh keeps the interface chosen, not the system's default
            # devices, while it is still there.
            for combo, device in ((self.input_device, chosen[1]), (self.output_device, chosen[2])):
                row = self._row_of(combo, device)
                if row >= 0:
                    combo.setCurrentIndex(row)
        # With no device at all a take would only end in PortAudio's own
        # English error ("Error querying device -1").
        self.run_button.setEnabled(bool(self._devices))
        if not self._devices:
            set_banner_text(
                self.device_hint,
                _("No audio device found; Universal DAW Mode still works."),
                "warn",
            )
        else:
            set_banner_text(
                self.device_hint, _("{n} audio device(s) found.").format(n=len(self._devices))
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
        host_apis = self._inventory.host_apis if self._inventory is not None else ()
        chosen = next((a for a in host_apis if a.name == api), None)
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
        kind = chosen.kind if chosen is not None else ""
        self.wasapi_exclusive.setEnabled(kind == "wasapi")
        self.coreaudio_set_rate.setEnabled(kind == "coreaudio")
        self._update_device_rate()

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
        mismatch = any(
            device is not None
            and requested_hz
            and abs(device.default_sample_rate - requested_hz) > 1.0
            for device in (inp, out)
        )
        if mismatch:
            text += _(" — rates differ; the interface may resample")
        self.device_rate.setText(text)

    def stream_options(self) -> StreamOptions:
        return StreamOptions(
            latency=self.latency.currentData(),
            wasapi_exclusive=self.wasapi_exclusive.isEnabled()
            and self.wasapi_exclusive.isChecked(),
            coreaudio_change_device_rate=self.coreaudio_set_rate.isEnabled()
            and self.coreaudio_set_rate.isChecked(),
        )

    def current_sweep_settings(self) -> SweepSettings:
        return SweepSettings(
            sample_rate=int(self.sample_rate.currentData()),
            duration_s=float(self.duration.value()),
            level_dbfs=float(self.level.value()),
        )

    # --- validation and the request -------------------------------------------------

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
            backend = get_backend(self._backend)
        except ReverbScopeError as exc:
            QMessageBox.critical(self, _("Invalid settings"), localize(str(exc)))
            return None
        if backend.name != self._inventory_backend:
            # Settings chose another backend while the dialog was open: the
            # numbers in the list name that backend's devices, not this one's.
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

    def _build_request(self) -> TakeRequest | None:
        """Validate every setting as the old page did; ``None`` and a message otherwise."""
        from reverbscope.audio.backend import get_backend

        try:
            settings = self.current_sweep_settings()
        except ReverbScopeError as exc:
            QMessageBox.critical(self, _("Invalid settings"), localize(str(exc)))
            return None
        if settings.level_dbfs > SAFE_MAX_LEVEL_DBFS and not self.acknowledge.isChecked():
            QMessageBox.warning(
                self,
                _("Level too high"),
                _(
                    "Levels above {level:g} dBFS need the acknowledgement checkbox. "
                    "Set the monitor level low first."
                ).format(level=SAFE_MAX_LEVEL_DBFS),
            )
            self.acknowledge.setFocus()
            return None
        hardware_loopback = int(self.loopback_channel.value())
        try:
            # 1-based interface inputs → 0-based recording columns, checked
            # before anything is played (#13).
            plan = plan_input_channels(
                [int(self.input_channel.value())],
                hardware_loopback if hardware_loopback > 0 else None,
            )
            analysis_settings = self._analysis_settings(
                plan.analysis_channel, plan.analysis_loopback_channel
            )
        except ReverbScopeError as exc:
            QMessageBox.critical(self, _("Invalid settings"), localize(str(exc)))
            return None
        devices = self._preflight(list(plan.input_channels), settings.sample_rate)
        if devices is None:
            return None
        input_device, output_device = devices
        # Resolved once, for the take and for its session: Settings or
        # REVERBSCOPE_AUDIO_BACKEND can choose the fake backend.
        backend = get_backend(self._backend).name
        synthetic = backend == "fake"
        output_channel = int(self.output_channel.value())
        profile = str(self.profile.currentData())
        # The session stores the 1-based interface channels of the take. A
        # take on the fake backend is marked like `reverbscope demo`'s
        # sessions, so it is never mistaken for a measurement of a real room.
        session = MeasurementSession(
            mode=DEMO_MODE if synthetic else "standalone",
            room_name=self.room.text(),
            measurement_position=self.position.text(),
            microphone_name=self.mic.text(),
            notes=FAKE_BACKEND_NOTES if synthetic else "",
            input_channel=plan.microphone_channel,
            loopback_channel=plan.loopback_channel,
            output_channel=output_channel,
            sweep_settings=settings,
            analysis_settings=analysis_settings,
            recording_profile=profile,
        )
        return TakeRequest(
            settings=settings,
            analysis_settings=analysis_settings,
            profile=profile,
            session=session,
            input_device=input_device,
            output_device=output_device,
            input_channels=list(plan.input_channels),
            output_channel=output_channel,
            loopback_channel=plan.loopback_channel,
            backend=backend,
            options=self.stream_options(),
            reference=Reference.from_settings(settings),
            synthetic=synthetic,
        )

    def _run(self) -> None:
        request = self._build_request()
        if request is None:
            return
        self._request = request
        self.accept()

    def request(self) -> TakeRequest | None:
        """The validated take after the dialog was accepted; ``None`` before."""
        return self._request


# --- Universal DAW Mode ------------------------------------------------------------


class DawAnalysisDialog(_MeasureDialog):
    """Write the test signal, choose the reference and the exported recording,
    pick the channels, profile, metadata and placement; Analyze.

    ReverbScope never talks to the DAW: the user plays the file there and
    records the room. The step-by-step notes are a section closed by default.
    """

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        profile: str = "generic",
        position: str = "",
        room: str = "",
    ) -> None:
        super().__init__(
            parent, _("Universal DAW Mode"), profile=profile, room=room, position=position
        )
        self._recording: AudioSignal | None = None
        self._recording_path: Path | None = None
        self._reference: Reference | None = None
        self._sweep_settings = SweepSettings()
        self._sweep_path: Path | None = None
        self._request: AnalysisRequest | None = None
        self._build_signal()
        self._build_notes()
        self._build_recording()
        self._add_interpretation()
        self._add_metadata()
        self._add_placement()
        self.body.addStretch(1)
        self.analyze_button = primary(QPushButton(_("Analyze")))
        self.analyze_button.setToolTip(
            _("Deconvolve the recording and read the room (Ctrl+Return).")
        )
        self.analyze_button.clicked.connect(self._analyze)
        self._finish_buttons(self.analyze_button)

    # --- building ---------------------------------------------------------------

    def _build_signal(self) -> None:
        box = QGroupBox(_("Test signal"))
        form = _form(box)
        self.sample_rate = _sample_rate_combo(self._sweep_settings.sample_rate)
        self.sample_rate.setToolTip(_("Must equal the DAW project's sample rate."))
        self.duration = _seconds(self._sweep_settings.duration_s)
        self.level = _dbfs(self._sweep_settings.level_dbfs)
        self.save_sweep_button = QPushButton(_("Save Test Signal WAV..."))
        self.save_sweep_button.setAutoDefault(False)
        self.save_sweep_button.clicked.connect(self._choose_sweep_target)
        self.sweep_label = label(_("No test signal written yet."), wrap=True)
        self.reference_button = QPushButton(_("Choose Reference Sweep..."))
        self.reference_button.setAutoDefault(False)
        self.reference_button.clicked.connect(self._choose_reference)
        self.reference_label = label(_("No reference sweep yet."), wrap=True)
        form.addRow(_("Sample rate"), self.sample_rate)
        form.addRow(_("Sweep duration"), self.duration)
        form.addRow(_("Peak level"), self.level)
        form.addRow(self.save_sweep_button, self.sweep_label)
        form.addRow(self.reference_button, self.reference_label)
        self.body.addWidget(box)

    def _build_notes(self) -> None:
        instructions = label(_(DAW_INSTRUCTIONS), "hint", wrap=True)
        instructions.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.instructions = CollapsibleSection(_("Step-by-step notes"), instructions)
        self.body.addWidget(self.instructions)

    def _build_recording(self) -> None:
        box = QGroupBox(_("Recording"))
        form = _form(box)
        self.recording_button = QPushButton(_("Choose Recording..."))
        self.recording_button.setAutoDefault(False)
        self.recording_button.clicked.connect(self._choose_recording)
        self.recording_label = label(_("No recording selected."), wrap=True)
        self.channel = QComboBox()
        self.channel.setToolTip(_("The channel with the measurement microphone."))
        self.loopback_channel = QComboBox()
        self.loopback_channel.setToolTip(
            _("The channel with the electrical loopback cable, if one was recorded.")
        )
        self._reset_channel_lists()
        self.rate_hint = QLabel()
        self.rate_hint.setWordWrap(True)
        self.rate_hint.hide()
        form.addRow(self.recording_button, self.recording_label)
        form.addRow(_("Microphone channel"), self.channel)
        form.addRow(_("Loopback channel"), self.loopback_channel)
        form.addRow(self.rate_hint)
        self.body.addWidget(box)

    # --- the test signal and the reference ----------------------------------------

    def current_sweep_settings(self) -> SweepSettings:
        return SweepSettings(
            sample_rate=int(self.sample_rate.currentData()),
            duration_s=float(self.duration.value()),
            level_dbfs=float(self.level.value()),
        )

    def _choose_sweep_target(self) -> None:
        target = ask_save_path(
            self, _("Save test signal"), "reverbscope_sweep.wav", _("WAV files (*.wav)")
        )
        if target is not None:
            self.generate_sweep_to(target)

    def generate_sweep_to(self, path: Path) -> None:
        """Write the sweep WAV and its sidecar at ``path``; it becomes the reference."""
        try:
            settings = self.current_sweep_settings()
            wav_path, sidecar = write_sweep_file(settings, path)
        except (ReverbScopeError, OSError) as exc:
            QMessageBox.critical(self, _("Cannot write test signal"), localize(str(exc)))
            return
        self._sweep_settings = settings
        self._sweep_path = wav_path
        self._reference = Reference.from_settings(settings)
        self.sweep_label.setText(
            _("Written: {wav} (+ {sidecar}). Keep both files together.").format(
                wav=wav_path.name, sidecar=sidecar.name
            )
        )
        self._reference_changed()

    def _choose_reference(self) -> None:
        path, _filter = QFileDialog.getOpenFileName(
            self,
            _("Choose reference sweep"),
            "",
            _("Sweep files (*.wav *.json);;All files (*)"),
        )
        if path:
            self.set_reference(Path(path))

    def set_reference(self, path: Path) -> None:
        """Use a sweep WAV (its sidecar preferred) or a sidecar JSON as the reference."""
        try:
            reference = load_reference(path)
        except ReverbScopeError as exc:
            QMessageBox.critical(self, _("Cannot read reference sweep"), localize(str(exc)))
            return
        self._reference = reference
        self._sweep_path = path
        if reference.settings is not None:
            self._sweep_settings = reference.settings
        self._reference_changed()

    def _reference_changed(self) -> None:
        if self._sweep_path is not None:
            self.reference_label.setText(_("Reference: {name}").format(name=self._sweep_path.name))
        self._update_rate_hint()

    # --- the recording --------------------------------------------------------------

    def _choose_recording(self) -> None:
        path, _filter = QFileDialog.getOpenFileName(
            self,
            _("Choose recording"),
            "",
            # Every container libsndfile reads that a DAW exports: Broadcast WAV,
            # RF64 and Wave64 for long takes, AIFF(-C) from Logic Pro / Pro Tools,
            # CAF from Logic Pro's recordings, FLAC.
            _(
                "Audio files (*.wav *.wave *.bwf *.rf64 *.w64 *.aif *.aiff *.aifc *.caf *.flac);;"
                "All files (*)"
            ),
        )
        if path:
            self.set_recording(Path(path))

    def set_recording(self, path: Path) -> None:
        """Read the exported track and list its channels."""
        try:
            recording = read_wav(path)
        except ReverbScopeError as exc:
            QMessageBox.critical(self, _("Cannot read recording"), localize(str(exc)))
            return
        self._recording = recording
        self._recording_path = path
        self._reset_channel_lists()
        for index in range(recording.n_channels):
            name = _("Channel {n}").format(n=index + 1)
            self.channel.addItem(name, index)
            self.loopback_channel.addItem(name, index)
        self.recording_label.setText(
            _("{name}: {seconds:.1f} s, {rate} Hz, {channels} channel(s)").format(
                name=path.name,
                seconds=recording.duration_s,
                rate=recording.sample_rate,
                channels=recording.n_channels,
            )
        )
        self._update_rate_hint()

    def _reset_channel_lists(self) -> None:
        self.channel.clear()
        self.channel.addItem(_("Auto (highest level)"), None)
        self.loopback_channel.clear()
        self.loopback_channel.addItem(_("None"), None)

    def _update_rate_hint(self) -> None:
        """Say when the recording and the test signal are at different rates:
        the analysis then reports the playback speed (nothing is refused)."""
        recording = self._recording
        reference = self._reference
        if (
            recording is None
            or reference is None
            or reference.settings is None
            or reference.settings.sample_rate == recording.sample_rate
        ):
            self.rate_hint.hide()
            return
        text = _(
            "the recording is at {recording} Hz but the test signal at "
            "{sweep} Hz: the analysis will report the playback speed"
        ).format(recording=recording.sample_rate, sweep=reference.settings.sample_rate)
        set_banner_text(self.rate_hint, f"{_('Sample rate')}: {text}", "info")
        self.rate_hint.show()

    # --- validation and the request -------------------------------------------------

    def _build_request(self) -> AnalysisRequest | None:
        if self._recording is None:
            QMessageBox.warning(self, _("No recording"), _("Choose the recorded file first."))
            self.recording_button.setFocus()
            return None
        if self._reference is None:
            QMessageBox.warning(
                self,
                _("No reference"),
                _("Write the test signal or choose the sweep file first."),
            )
            self.save_sweep_button.setFocus()
            return None
        channel = self.channel.currentData()
        loopback = self.loopback_channel.currentData()
        try:
            analysis_settings = self._analysis_settings(
                None if channel is None else int(channel),
                None if loopback is None else int(loopback),
            )
        except ReverbScopeError as exc:
            QMessageBox.critical(self, _("Invalid settings"), localize(str(exc)))
            return None
        profile = str(self.profile.currentData())
        session = MeasurementSession(
            mode="universal_daw",
            room_name=self.room.text(),
            measurement_position=self.position.text(),
            microphone_name=self.mic.text(),
            sweep_settings=self._sweep_settings,
            analysis_settings=analysis_settings,
            sweep_path=str(self._sweep_path) if self._sweep_path else None,
            recording_path=str(self._recording_path) if self._recording_path else None,
            recording_profile=profile,
        )
        return AnalysisRequest(
            recording=self._recording,
            recording_path=self._recording_path,
            reference=self._reference,
            sweep_path=self._sweep_path,
            settings=self._sweep_settings,
            analysis_settings=analysis_settings,
            profile=profile,
            session=session,
        )

    def _analyze(self) -> None:
        request = self._build_request()
        if request is None:
            return
        self._request = request
        self.accept()

    def request(self) -> AnalysisRequest | None:
        """The validated analysis after the dialog was accepted; ``None`` before."""
        return self._request
