"""Home and New Measurement pages.

New Measurement holds both routes, Universal DAW Mode and Standalone Mode, on
one page: the same four numbered steps, the same footer with the action, and
one place for the position and the analysis. Only step 2 differs by route.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, cast

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QHideEvent
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
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
from reverbscope.i18n import N_, _, localize
from reverbscope.interpretation import Finding, available_profiles, interpret
from reverbscope.interpretation.profiles import profile_title
from reverbscope.io.wav import load_reference, read_wav, write_sweep_file
from reverbscope.models.audio import AudioSignal
from reverbscope.models.configuration import SUPPORTED_SAMPLE_RATES, AnalysisSettings, SweepSettings
from reverbscope.models.result import AnalysisResult
from reverbscope.models.session import MeasurementSession
from reverbscope.ui.browser import SessionBrowser
from reverbscope.ui.state import MeasurementState
from reverbscope.ui.widgets import (
    Card,
    ModeCard,
    PageHeader,
    StepCard,
    ask_save_path,
    error_box,
    label,
    primary,
    scroll_page,
    set_banner_text,
)
from reverbscope.ui.workers import AnalysisWorker, MeasureWorker, unexpected_error_text

log = logging.getLogger(__name__)

#: The two routes of New Measurement. The values are the session modes.
ROUTE_DAW = "universal_daw"
ROUTE_STANDALONE = "standalone"


def separate_clocks_box(parent: QWidget, warning: str) -> QMessageBox:
    """Two devices, two clocks. The safe button is the default: do not measure."""
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Warning)
    box.setWindowTitle(_("Two devices, two clocks"))
    box.setText(localize(warning))
    box.setInformativeText(_("Measure anyway?"))
    box.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    box.addButton(_("Measure anyway"), QMessageBox.ButtonRole.AcceptRole)
    cancel = box.addButton(_("Cancel"), QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(cancel)
    box.setEscapeButton(cancel)
    return box


def ask_separate_clocks(parent: QWidget, warning: str) -> bool:
    box = separate_clocks_box(parent, warning)
    box.exec()
    clicked = box.clickedButton()
    # By role, not by label: some desktops insert "&" accelerators into it.
    return clicked is not None and box.buttonRole(clicked) == QMessageBox.ButtonRole.AcceptRole


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


def _find_data(combo: QComboBox, value: object) -> int:
    """The first row of ``combo`` whose data is ``value`` (``None`` included)."""
    return next((row for row in range(combo.count()) if combo.itemData(row) == value), -1)


def late_result_text() -> str:
    """Shown on the New Measurement page whose take or analysis ended after the
    user moved on.

    Not after any page switch: a visit to Compare or Settings keeps the result,
    which then opens Results. Only a reset (New Measurement, Open Session) or a
    measurement another page started meanwhile makes the result late.
    """
    return _(
        "The result was discarded: a new measurement or another session replaced it "
        "before it was ready."
    )


def safe_findings(result: AnalysisResult, profile: str) -> tuple[list[Finding], str]:
    """The findings for ``result``, or none and the reason why.

    A recording profile that fails (a third-party one from an entry point)
    must not stop the result from being shown: the page stayed busy for good
    and the measurement was never seen.
    """
    try:
        return interpret(result, profile), ""
    except ReverbScopeError as exc:
        return [], localize(str(exc))
    except Exception:
        log.exception("recording profile %r failed to interpret the result", profile)
        return [], unexpected_error_text()


class WalkthroughCard(Card):
    """The first-run hint on Home. The demo card below is the way in; this says
    what it is for and where the guide is."""

    dismissed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent, spacing=10)
        self.body.addWidget(label(_("Your first measurement").upper(), "section"))
        self.body.addWidget(
            label(
                _(
                    "Run the demo first: it walks the whole workflow on a synthetic room, "
                    "and nothing is played."
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

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("page", True)
        # A window shorter than the page (a 1366x768 laptop, or the 960x640
        # minimum) scrolls it; without the scroll area the first-measurement
        # card was squeezed until its buttons overlapped and were cut off.
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
        layout.setContentsMargins(28, 22, 28, 22)
        layout.setSpacing(14)

        layout.addWidget(label("ReverbScope", "title"))
        layout.addWidget(
            label(
                _("An open-source, DAW-independent recording environment analyzer"),
                "subtitle",
                wrap=True,
            )
        )
        pills = QHBoxLayout()
        pills.setSpacing(8)
        for text in (
            _("A validity flag on every number"),
            _("Any DAW: WAV in, WAV out"),
            _("No room score, no invented figures"),
        ):
            pills.addWidget(label(text, "pill"))
        pills.addStretch(1)
        layout.addLayout(pills)
        layout.addSpacing(6)

        # Shown until dismissed (a setting); Help ▸ Getting started brings it back.
        self.walkthrough = WalkthroughCard()
        self.walkthrough.dismissed.connect(self.dismiss_walkthrough)
        #: "Don't show this again" was clicked in this run: the card stays
        #: hidden even where the settings file could not record it.
        self._walkthrough_dismissed = False
        layout.addWidget(self.walkthrough)

        layout.addWidget(label(_("New Measurement").upper(), "section"))
        cards = QHBoxLayout()
        cards.setSpacing(12)
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
            _("Start with my interface"),
            shortcut="Ctrl+2",
        )
        # The demo is the Standalone route on the fake backend: a trial of the
        # same page, so its card is the secondary one.
        demo = ModeCard(
            _("DEMO"),
            _("Demo (no interface)"),
            _("Run Standalone Mode on the fake backend. Nothing is sent to a loudspeaker."),
            _("Try the demo"),
            shortcut="Ctrl+3",
            emphasis=False,
        )
        daw.clicked.connect(lambda: self.choose_mode.emit("universal_daw"))
        standalone.clicked.connect(lambda: self.choose_mode.emit("standalone"))
        demo.clicked.connect(lambda: self.choose_mode.emit("demo"))
        self.mode_cards = (daw, standalone, demo)
        for card in self.mode_cards:
            cards.addWidget(card)
        layout.addLayout(cards)
        layout.addSpacing(6)

        sessions = Card()
        header = QHBoxLayout()
        header.addWidget(label(_("Saved sessions").upper(), "section"))
        header.addStretch(1)
        open_button = QPushButton(_("Open Session..."))
        open_button.setToolTip(_("Open a session.json or a folder that contains one."))
        open_button.clicked.connect(self.open_session.emit)
        compare_button = QPushButton(_("Compare two sessions..."))
        compare_button.setToolTip(_("Pick two saved sessions and compare their metrics."))
        compare_button.clicked.connect(self.compare_requested.emit)
        project_button = QPushButton(_("Open Project..."))
        project_button.setToolTip(
            _("One room, several microphone positions: open or make a project folder.")
        )
        project_button.clicked.connect(self.open_project.emit)
        header.addWidget(open_button)
        header.addWidget(project_button)
        header.addWidget(compare_button)
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


def _profile_combo(state: MeasurementState) -> QComboBox:
    from reverbscope.interpretation.explain import profile_description

    combo = QComboBox()
    for index, name in enumerate(available_profiles()):
        combo.addItem(profile_title(name), name)
        combo.setItemData(index, profile_description(name), Qt.ItemDataRole.ToolTipRole)
    combo.setCurrentIndex(max(combo.findData(state.profile), 0))

    def describe(_index: int) -> None:
        combo.setToolTip(profile_description(str(combo.currentData() or "")))

    combo.currentIndexChanged.connect(describe)
    describe(combo.currentIndex())
    return combo


def _profile_row(combo: QComboBox, page: QWidget) -> tuple[QHBoxLayout, QPushButton]:
    """The profile selector with the button that says what the profile wants.

    Returns the row and the button; the page keeps the button as its
    ``profile_help`` attribute (declared on the page, not set from here, so
    the type checker sees it whether or not PySide6's stubs are installed).
    """
    from reverbscope.ui.profile_dialog import profile_of, show_profile_help

    row = QHBoxLayout()
    row.setSpacing(8)
    row.addWidget(combo, 1)
    button = QPushButton(_("What does it want?"))
    button.setToolTip(_("What this profile watches for, and what it does not judge."))
    button.clicked.connect(lambda: show_profile_help(profile_of(combo), page))
    row.addWidget(button)
    return row, button


class PlacementInputs(QWidget):
    """Optional tape measurements that raise the placement tier (S5)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(6)
        outer.addWidget(label(_("Tape measurements (optional)").upper(), "section"))
        row = QHBoxLayout()
        outer.addLayout(row)
        form = QFormLayout()
        self.distance = QDoubleSpinBox()
        self.distance.setRange(0.0, 15.0)
        self.distance.setDecimals(2)
        self.distance.setSingleStep(0.01)
        self.distance.setSuffix(" m")
        self.distance.setSpecialValueText(_("not measured"))
        self.distance.setValue(0.0)
        self.distance.setToolTip(_("Straight line from the loudspeaker to the microphone capsule."))
        self.mic_height = QDoubleSpinBox()
        self.mic_height.setRange(0.0, 5.0)
        self.mic_height.setDecimals(2)
        self.mic_height.setSingleStep(0.01)
        self.mic_height.setSuffix(" m")
        self.mic_height.setSpecialValueText(_("not measured"))
        self.mic_height.setValue(0.0)
        self.mic_height.setEnabled(False)
        self.mic_height.setToolTip(
            _("Capsule above the first solid horizontal surface below it. Needs the distance.")
        )
        self.temperature = QDoubleSpinBox()
        self.temperature.setRange(-20.0, 50.0)
        self.temperature.setDecimals(1)
        self.temperature.setValue(20.0)
        self.temperature.setSuffix(" C")
        self.temperature.setEnabled(False)
        self.temperature_measured = QCheckBox(_("air temperature measured"))
        self.temperature_measured.toggled.connect(self.temperature.setEnabled)
        self.distance.valueChanged.connect(self._sync_height)
        self.distance.valueChanged.connect(self._redraw_scene)
        self.mic_height.valueChanged.connect(self._redraw_scene)
        form.addRow(_("Loudspeaker distance"), self.distance)
        form.addRow(_("Microphone height"), self.mic_height)
        form.addRow(self.temperature_measured, self.temperature)
        row.addLayout(form, 1)
        scene = QVBoxLayout()
        self.figure = Figure(figsize=(5.6, 3.3), dpi=100)
        self.canvas: Any = cast(Any, FigureCanvasQTAgg)(self.figure)
        self.canvas.setMinimumHeight(240)
        self.scene_hint = QLabel("")
        self.scene_hint.setWordWrap(True)
        self.scene_hint.setProperty("role", "hint")
        scene.addWidget(self.canvas, 1)
        scene.addWidget(self.scene_hint)
        row.addLayout(scene, 2)
        self._redraw_scene()

    def _sync_height(self, value: float) -> None:
        allowed = value >= 0.20
        self.mic_height.setEnabled(allowed)
        if not allowed:
            self.mic_height.setValue(0.0)

    def redraw(self) -> None:
        """Draw the picture again (in a new colour scheme)."""
        self._redraw_scene()

    def _redraw_scene(self, _value: float | None = None) -> None:
        from reverbscope.ui.plots import plot_placement_illustration

        distance = self.distance.value()
        height = self.mic_height.value()
        hint = plot_placement_illustration(
            self.figure,
            distance_m=distance if distance >= 0.20 else None,
            mic_height_m=height if self.mic_height.isEnabled() and height >= 0.02 else None,
        )
        self.scene_hint.setText(hint)
        self.canvas.draw_idle()

    def analysis_kwargs(self) -> dict[str, float | None]:
        distance = self.distance.value()
        height = self.mic_height.value()
        distance_m = distance if distance >= 0.20 else None
        mic_height_m = height if distance_m is not None and height >= 0.02 else None
        temperature_c = self.temperature.value() if self.temperature_measured.isChecked() else None
        return {
            "placement_distance_m": distance_m,
            "placement_mic_height_m": mic_height_m,
            "placement_temperature_c": temperature_c,
        }


class MeasurePage(QWidget):
    """New Measurement: Universal DAW Mode and Standalone Mode on one page.

    Both routes share the test signal, the position and the analysis; only
    step 2 differs (the interface's devices and channels, or the export and
    import of a DAW take). The footer holds the one action of the route, so
    the Run or Analyze button stays in view however long the page is. A take
    or an analysis locks the route switch, so no measurement is replaced
    while it runs.
    """

    analysis_finished = Signal()
    back = Signal()

    def __init__(self, state: MeasurementState, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.state = state
        #: The Demo: the Standalone route on the fake backend.
        self.demo_mode = False
        self.route = state.mode if state.mode in (ROUTE_DAW, ROUTE_STANDALONE) else ROUTE_DAW
        # Standalone route: the devices of the interface, the take and its workers.
        self._devices: list[DeviceInfo] = []
        self._inventory: DeviceInventory | None = None
        # The backend that listed :attr:`_inventory`: device indices of
        # another one (the Demo's fake interface) name other devices.
        self._inventory_backend: str | None = None
        self._measure_worker: MeasureWorker | None = None
        self._analysis_worker: AnalysisWorker | None = None
        #: A take is playing or recording; an analysis is running. Set by the
        #: page, cleared by the worker's own signal (a finished thread may
        #: still report itself as running for a moment).
        self._taking = False
        self._analysing = False
        #: The route the running (or last) take or analysis belongs to.
        self._analysis_route = self.route
        self._channel_plan: ChannelPlan | None = None
        # The output channel the take plays on: the spin box stays editable.
        self._take_output_channel = 1
        # The take runs on the fake backend: its session is a synthetic demo.
        self._take_synthetic = False
        # The take's sweep, analysis settings and profile. They join the
        # shared state with its recording, not before: a refused or stopped
        # Run replaced the reference the Universal DAW analysis used.
        self._take_settings = state.sweep_settings
        self._take_reference: Reference | None = None
        self._take_analysis_settings = AnalysisSettings()
        self._take_profile = state.profile
        # Universal DAW Mode: the recording imported, and the sweep of step 1
        # (or the reference file chosen), kept here until an analysis starts.
        # A take on the Standalone route replaces the shared state, not these.
        self._recording: AudioSignal | None = None
        self._recording_path: Path | None = None
        self._reference: Reference | None = None
        self._sweep_settings = state.sweep_settings
        self._sweep_path: Path | None = None
        # The state generation the running take or analysis belongs to.
        self._generation = -1

        header = PageHeader(_("New Measurement"))
        self._header = header
        # The route switch sits where the page's actions are, as on Results.
        self.route_buttons: dict[str, QPushButton] = {}
        self._route_group = QButtonGroup(self)
        self._route_group.setExclusive(True)
        for route, caption, edge in (
            (ROUTE_DAW, _("Universal DAW Mode"), "left"),
            (ROUTE_STANDALONE, _("Standalone Mode"), "right"),
        ):
            button = QPushButton(caption)
            button.setCheckable(True)
            button.setProperty("segment", edge)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _checked=False, r=route: self._choose_route(r))
            self._route_group.addButton(button)
            header.action_row.addWidget(button)
            self.route_buttons[route] = button

        footer = self._build_footer()
        layout = scroll_page(self, header, footer=footer)

        self.demo_bar = QWidget()
        demo_row = QHBoxLayout(self.demo_bar)
        demo_row.setContentsMargins(0, 0, 0, 0)
        demo_row.setSpacing(10)
        self.demo_banner = label(
            _("Demo mode: the fake backend synthesises a room. Nothing is sent to a loudspeaker."),
            wrap=True,
        )
        self.demo_banner.setProperty("banner", "info")
        demo_row.addWidget(self.demo_banner, 1)
        self.leave_demo_button = QPushButton(_("Use my audio interface"))
        self.leave_demo_button.clicked.connect(lambda: self.leave_demo())
        demo_row.addWidget(self.leave_demo_button)
        self.demo_bar.hide()
        layout.addWidget(self.demo_bar)

        layout.addWidget(self._build_test_signal_step())
        layout.addWidget(self._build_capture_step())
        layout.addWidget(self._build_position_step())
        layout.addWidget(self._build_analysis_step())
        layout.addStretch(1)

        self.refresh_devices()
        self.set_route(self.route)

    # --- layout -----------------------------------------------------------------

    def _build_footer(self) -> QFrame:
        footer = QFrame()
        footer.setProperty("footer", True)
        bar = QVBoxLayout(footer)
        bar.setContentsMargins(16, 10, 16, 10)
        bar.setSpacing(8)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(6)
        self.progress.hide()
        bar.addWidget(self.progress)
        row = QHBoxLayout()
        row.setSpacing(10)
        self.back_button = QPushButton(_("Back"))
        self.back_button.clicked.connect(self.back.emit)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        self.stop_button = QPushButton(_("Stop"))
        self.stop_button.setProperty("danger", True)
        self.stop_button.setShortcut("Esc")
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self.stop_measurement)
        self.run_button = primary(QPushButton(_("Run Measurement")))
        self.run_button.setShortcut("Ctrl+Return")
        self.run_button.clicked.connect(self._run)
        row.addWidget(self.back_button)
        row.addWidget(self.status, 1)
        row.addWidget(self.stop_button)
        row.addWidget(self.run_button)
        bar.addLayout(row)
        return footer

    def _build_test_signal_step(self) -> StepCard:
        """Step 1: the sweep. Its level belongs to the route: the DAW's peak
        level of the file it writes, or the playback level of the interface
        (which starts low: the safety rule of the Standalone route)."""
        step = StepCard(1)
        self.sample_rate = QComboBox()
        for sr in SUPPORTED_SAMPLE_RATES:
            self.sample_rate.addItem(f"{sr} Hz", sr)
        self.sample_rate.setCurrentIndex(
            list(SUPPORTED_SAMPLE_RATES).index(self.state.sweep_settings.sample_rate)
        )
        self.duration = QDoubleSpinBox()
        self.duration.setRange(1.0, 60.0)
        self.duration.setValue(self.state.sweep_settings.duration_s)
        self.duration.setSuffix(" s")
        self.level = QDoubleSpinBox()
        self.level.setRange(-40.0, 0.0)
        self.level.setValue(self.state.sweep_settings.level_dbfs)
        self.level.setSuffix(" dBFS")
        self.playback_level = QDoubleSpinBox()
        self.playback_level.setRange(-40.0, 0.0)
        self.playback_level.setValue(DEFAULT_STANDALONE_LEVEL_DBFS)
        self.playback_level.setSuffix(" dBFS")
        self.safety = label(_(SAFETY_MESSAGE), wrap=True)
        self.safety.setProperty("banner", "warn")
        self.acknowledge = QCheckBox(
            _("I have set the monitor level low (required above {level:g} dBFS)").format(
                level=SAFE_MAX_LEVEL_DBFS
            )
        )
        self.save_sweep_button = primary(QPushButton(_("Save Test Signal WAV...")))
        self.save_sweep_button.clicked.connect(self._choose_sweep_target)
        self.sweep_label = QLabel(_("No test signal written yet."))
        self.sweep_label.setWordWrap(True)
        self._signal_form = QFormLayout()
        self._signal_form.addRow(_("Sample rate"), self.sample_rate)
        self._signal_form.addRow(_("Sweep duration"), self.duration)
        self._signal_form.addRow(_("Peak level"), self.level)
        self._signal_form.addRow(_("Playback level"), self.playback_level)
        self.step1 = step
        step.body.addWidget(self.safety)
        step.body.addLayout(self._signal_form)
        step.body.addWidget(self.acknowledge)
        step.body.addWidget(self.save_sweep_button)
        step.body.addWidget(self.sweep_label)
        self.sample_rate.currentIndexChanged.connect(self._update_device_rate)
        return step

    def _build_capture_step(self) -> StepCard:
        """Step 2, by route: the devices and channels of the interface, or the
        DAW's instructions, the recording and the reference to import."""
        step = StepCard(2)
        self.capture_step = step

        self.devices_panel = QWidget()
        devices = QFormLayout(self.devices_panel)
        devices.setContentsMargins(0, 0, 0, 0)
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
        self.device_rate = QLabel(_("Device rate: unknown"))
        self.device_rate.setWordWrap(True)
        self.input_device.currentIndexChanged.connect(self._update_device_rate)
        self.output_device.currentIndexChanged.connect(self._update_device_rate)
        self.input_channel = QSpinBox()
        self.input_channel.setRange(1, 64)
        self.loopback_channel = QSpinBox()
        self.loopback_channel.setRange(0, 64)
        self.loopback_channel.setSpecialValueText(_("unused"))
        self.output_channel = QSpinBox()
        self.output_channel.setRange(1, 64)
        devices.addRow(_("Audio system (host API)"), self.host_api)
        devices.addRow(_("Input device"), self.input_device)
        devices.addRow(_("Output device"), self.output_device)
        devices.addRow(self.refresh_button)
        devices.addRow(self.device_rate)
        devices.addRow(_("Input channel (mic)"), self.input_channel)
        devices.addRow(_("Loopback channel (1-based)"), self.loopback_channel)
        devices.addRow(_("Output channel (speaker)"), self.output_channel)

        from reverbscope.edition import is_developer

        self.advanced = QWidget()
        adv_layout = QVBoxLayout(self.advanced)
        adv_layout.setContentsMargins(0, 8, 0, 0)
        adv_layout.setSpacing(6)
        adv_layout.addWidget(
            label(_("Advanced audio options (developer edition)").upper(), "section")
        )
        adv = QFormLayout()
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
        adv_layout.addLayout(adv)
        self.advanced.setVisible(is_developer())
        devices.addRow(self.advanced)

        self.recording_panel = QWidget()
        recording = QVBoxLayout(self.recording_panel)
        recording.setContentsMargins(0, 0, 0, 0)
        recording.setSpacing(10)
        instructions = QLabel(_(DAW_INSTRUCTIONS))
        instructions.setWordWrap(True)
        instructions.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        recording.addWidget(instructions)
        self.recording_button = QPushButton(_("Choose Recording..."))
        self.recording_button.clicked.connect(self._choose_recording)
        self.recording_label = QLabel(_("No recording selected."))
        self.recording_label.setWordWrap(True)
        self.reference_button = QPushButton(_("Choose Reference Sweep..."))
        self.reference_button.clicked.connect(self._choose_reference)
        self.reference_label = QLabel(
            _("Reference: the test signal from Step 1 (or choose a file).")
        )
        self.reference_label.setWordWrap(True)
        self.channel = QComboBox()
        self.recording_loopback = QComboBox()
        self._reset_channel_lists()
        import_form = QFormLayout()
        import_form.addRow(self.recording_button, self.recording_label)
        import_form.addRow(self.reference_button, self.reference_label)
        import_form.addRow(_("Microphone channel"), self.channel)
        import_form.addRow(_("Loopback channel"), self.recording_loopback)
        recording.addLayout(import_form)

        step.body.addWidget(self.devices_panel)
        step.body.addWidget(self.recording_panel)
        return step

    def _build_position_step(self) -> StepCard:
        step = StepCard(3)
        step.set_text(
            _("Position (optional)"),
            _(
                "Where the loudspeaker and the microphone stood. The names are saved with the session."
            ),
        )
        meta = QFormLayout()
        self.room = QLineEdit(self.state.session.room_name)
        self.position = QLineEdit(self.state.session.measurement_position)
        self.mic = QLineEdit(self.state.session.microphone_name)
        meta.addRow(_("Room"), self.room)
        meta.addRow(_("Position"), self.position)
        meta.addRow(_("Microphone"), self.mic)
        self.placement = PlacementInputs()
        step.body.addLayout(meta)
        step.body.addWidget(self.placement)
        return step

    def _build_analysis_step(self) -> StepCard:
        step = StepCard(4)
        step.set_text(
            _("Analysis"),
            _(
                "The recording profile says what the room is judged for. Every number "
                "still carries its own validity."
            ),
        )
        form = QFormLayout()
        self.profile = _profile_combo(self.state)
        profile_row, self.profile_help = _profile_row(self.profile, self)
        form.addRow(_("Recording profile"), profile_row)
        step.body.addLayout(form)
        return step

    # --- route and state --------------------------------------------------------

    def set_route(self, route: str) -> None:
        """Show ``route``: the step texts, the step 2 panel, the action and the
        controls that belong to it. A route the page is not on loses the Demo."""
        self.route = route
        interface = route == ROUTE_STANDALONE
        if not interface:
            self.demo_mode = False
        self.demo_bar.setVisible(self.demo_mode)
        for name, button in self.route_buttons.items():
            button.setChecked(name == route)
        self._header.subtitle.setText(
            _(
                "ReverbScope plays the sweep and records the microphone through your audio "
                "interface, then runs the same analysis as Universal DAW Mode."
            )
            if interface
            else _(
                "Four steps: generate the test signal, play and record it in your DAW, "
                "import the recording, analyse. ReverbScope never talks to the DAW."
            )
        )
        self._header.subtitle.setVisible(True)
        self._signal_form.setRowVisible(self.level, not interface)
        self._signal_form.setRowVisible(self.playback_level, interface)
        self.safety.setVisible(interface)
        self.acknowledge.setVisible(interface)
        self.save_sweep_button.setVisible(not interface)
        self.sweep_label.setVisible(not interface)
        self.devices_panel.setVisible(interface)
        self.recording_panel.setVisible(not interface)
        if interface:
            self.capture_step.set_text(
                _("Play and record through your interface"),
                _(
                    "ReverbScope plays the test signal and records the microphone when you run the measurement."
                ),
            )
            self.step1.set_text(
                _("Test signal"),
                _("The sweep ReverbScope plays through your interface, at the level below."),
            )
        else:
            self.capture_step.set_text(
                _("Record in your DAW, then import the take"),
                _(
                    "Play the test signal in your DAW and record it. ReverbScope never talks to the DAW."
                ),
            )
            self.step1.set_text(
                _("Test signal"),
                _("The sweep ReverbScope writes as a WAV file for your DAW, at the level below."),
            )
        self.run_button.setText(_("Run Measurement") if interface else _("Analyze"))
        # Changing the text of a button drops its shortcut: the key is set again.
        self.run_button.setShortcut("Ctrl+Return")
        if not interface and not self.is_busy():
            set_banner_text(self.status, "")
        self.refresh_controls()

    def open_route(self, route: str, *, demo: bool = False) -> None:
        """Show New Measurement on ``route`` (the menu, the cards, a project's
        position). ``demo`` is the Standalone route on the fake backend."""
        demo = demo and route == ROUTE_STANDALONE
        changed = demo != self.demo_mode
        self.demo_mode = demo
        self.set_route(route)
        if route == ROUTE_STANDALONE or changed:
            self.refresh_devices()

    def leave_demo(self) -> None:
        """The Demo off: the same route on the interface (not while it runs)."""
        if self.demo_mode and not self.is_busy():
            self.open_route(ROUTE_STANDALONE)

    def _choose_route(self, route: str) -> None:
        if route == self.route or self.is_busy():
            # Keep the button of the route on the page checked.
            self.route_buttons[self.route].setChecked(True)
            return
        self.open_route(route)

    def _run(self) -> None:
        if self.route == ROUTE_STANDALONE:
            self.start_measurement()
        else:
            self.start_analysis()

    def current_sweep_settings(self) -> SweepSettings:
        """The sweep of the route the page shows."""
        if self.route == ROUTE_STANDALONE:
            return self._sweep_at(self.playback_level.value())
        return self._sweep_at(self.level.value())

    def _sweep_at(self, level_dbfs: float) -> SweepSettings:
        return SweepSettings(
            sample_rate=int(self.sample_rate.currentData()),
            duration_s=float(self.duration.value()),
            level_dbfs=float(level_dbfs),
        )

    def refresh_controls(self) -> None:
        """Enable what the page's state allows. A take or an analysis locks
        the route switch, Back, the demo and the devices until it ends."""
        busy = self.is_busy()
        interface = self.route == ROUTE_STANDALONE
        self.run_button.setEnabled(not busy and (not interface or bool(self._devices)))
        self.stop_button.setVisible(interface)
        self.stop_button.setEnabled(self._taking)
        self.back_button.setEnabled(not busy)
        self.leave_demo_button.setEnabled(not busy)
        for button in self.route_buttons.values():
            button.setEnabled(not busy)
        self.refresh_button.setEnabled(not busy)
        self.progress.setVisible(busy)

    def _set_busy(self, busy: bool, text: str = "", *, tone: str = "") -> None:
        set_banner_text(self.status, text, tone)
        if not busy:
            self.progress.setValue(0)
        self.refresh_controls()

    def is_busy(self) -> bool:
        """A take or its analysis is still running."""
        return self._taking or self._analysing

    def shutdown_workers(self) -> None:
        """Stop a take (silencing the output) and let both workers finish."""
        if self._measure_worker is not None:
            self._measure_worker.request_stop()
        for worker in (self._measure_worker, self._analysis_worker):
            if worker is not None:
                worker.wait()

    def hideEvent(self, event: QHideEvent) -> None:  # noqa: N802 - Qt override
        # Leaving the page (not minimising the window) stops a take: Stop and
        # Esc live on this page, so the sweep must not go on playing unseen.
        if not event.spontaneous() and self._measure_worker is not None:
            self._measure_worker.request_stop()
        super().hideEvent(event)

    def _stale(self) -> bool:
        """The result that arrives now belongs to a session that is gone.

        The shared state was reset (New Measurement, Open Session) or taken by
        a measurement another page started since this one began, or the
        window is closed. A visit to Compare or Settings meanwhile is not
        that: the result is kept and opens Results.
        """
        return self._generation != self.state.generation or not self.window().isVisible()

    def _may_replace_unsaved_take(self) -> bool:
        """A new take or analysis replaces the live take that is not saved yet.

        Its recording exists only in memory, so the page asks first, as New
        Measurement, Open Session and closing the window do.
        """
        if not (self.state.unsaved_take and self.state.result is not None):
            return True
        box = QMessageBox(
            QMessageBox.Icon.Question,
            _("Unsaved measurement"),
            _(
                "This measurement has not been saved. Its recording exists only in "
                "memory and is lost if you continue."
            ),
            parent=self,
        )
        discard = box.addButton(_("Discard"), QMessageBox.ButtonRole.DestructiveRole)
        cancel = box.addButton(_("Cancel"), QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(cancel)
        box.setEscapeButton(cancel)
        box.exec()
        return box.clickedButton() is discard

    def clear_recording(self) -> None:
        """Forget the imported take (New Measurement, Open Session)."""
        self._recording = None
        self._recording_path = None
        self.recording_label.setText(_("No recording selected."))
        self._reset_channel_lists()

    # --- step 1: the test signal (Universal DAW Mode) ---------------------------

    def _choose_sweep_target(self) -> None:
        target = ask_save_path(
            self, _("Save test signal"), "reverbscope_sweep.wav", _("WAV files (*.wav)")
        )
        if target is not None:
            self.generate_sweep_to(target)

    def generate_sweep_to(self, path: Path) -> None:
        try:
            settings = self._sweep_at(self.level.value())
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
        self.reference_label.setText(_("Reference: {name}").format(name=wav_path.name))

    # --- step 2: the recording (Universal DAW Mode) -----------------------------

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
        try:
            recording = read_wav(path)
        except ReverbScopeError as exc:
            QMessageBox.critical(self, _("Cannot read recording"), localize(str(exc)))
            return
        self._recording = recording
        self._recording_path = path
        self._reset_channel_lists()
        for index in range(recording.n_channels):
            label_text = _("Channel {n}").format(n=index + 1)
            self.channel.addItem(label_text, index)
            self.recording_loopback.addItem(label_text, index)
        self.recording_label.setText(
            _("{name}: {seconds:.1f} s, {rate} Hz, {channels} channel(s)").format(
                name=path.name,
                seconds=recording.duration_s,
                rate=recording.sample_rate,
                channels=recording.n_channels,
            )
        )

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
        try:
            reference = load_reference(path)
        except ReverbScopeError as exc:
            QMessageBox.critical(self, _("Cannot read reference sweep"), localize(str(exc)))
            return
        self._reference = reference
        self._sweep_path = path
        if reference.settings is not None:
            self._sweep_settings = reference.settings
        self.reference_label.setText(_("Reference: {name}").format(name=path.name))

    def _reset_channel_lists(self) -> None:
        self.channel.clear()
        self.channel.addItem(_("Auto (highest level)"), None)
        self.recording_loopback.clear()
        self.recording_loopback.addItem(_("None"), None)

    # --- analysis of a DAW recording ---------------------------------------------

    def start_analysis(self, *, blocking: bool = False) -> None:
        if self.is_busy():
            # Analyze while busy: a second worker would drop the only
            # reference to the running one, and Qt aborts the process when a
            # QThread is destroyed while it runs.
            return
        if self._recording is None:
            QMessageBox.warning(
                self, _("No recording"), _("Choose the recorded WAV file first (Step 2).")
            )
            return
        if self._reference is None:
            QMessageBox.warning(
                self,
                _("No reference"),
                _("Generate the test signal (Step 1) or choose the sweep file."),
            )
            return
        if not self._may_replace_unsaved_take():
            return
        channel = self.channel.currentData()
        loopback = self.recording_loopback.currentData()
        self.state.profile = str(self.profile.currentData())
        place = self.placement.analysis_kwargs()
        self.state.analysis_settings = AnalysisSettings(
            channel=None if channel is None else int(channel),
            loopback_channel=None if loopback is None else int(loopback),
            placement_distance_m=place["placement_distance_m"],
            placement_mic_height_m=place["placement_mic_height_m"],
            placement_temperature_c=place["placement_temperature_c"],
        )
        # The imported take and its sweep become the shared session's, which
        # Save writes; a take or analysis another page still runs is now late.
        self._generation = self.state.claim()
        self.state.recording = self._recording
        self.state.recording_path = self._recording_path
        self.state.reference = self._reference
        self.state.sweep_settings = self._sweep_settings
        self.state.sweep_path = self._sweep_path
        self.state.session = MeasurementSession(
            mode=ROUTE_DAW,
            room_name=self.room.text(),
            measurement_position=self.position.text(),
            microphone_name=self.mic.text(),
            sweep_settings=self._sweep_settings,
            analysis_settings=self.state.analysis_settings,
            sweep_path=str(self._sweep_path) if self._sweep_path else None,
            recording_path=str(self._recording_path) if self._recording_path else None,
            recording_profile=self.state.profile,
        )
        self._analysing = True
        self._analysis_route = ROUTE_DAW
        self.progress.setRange(0, 0)
        self._set_busy(True, _("Analyzing..."))
        self._analysis_worker = AnalysisWorker(
            self._recording, self._reference, self.state.analysis_settings
        )
        self._analysis_worker.succeeded.connect(self._on_success)
        self._analysis_worker.failed.connect(self._on_failure)
        if blocking:
            self._analysis_worker.run()
        else:
            self._analysis_worker.start()

    # --- step 2: devices and the take (Standalone Mode) -------------------------

    def refresh_devices(self) -> None:
        from reverbscope.audio.backend import get_backend
        from reverbscope.audio.inventory import build_inventory

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
            self._device_status(
                _("Audio backend unavailable: {error}").format(error=localize(str(exc))),
                "warn",
            )
            self.refresh_controls()
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
        self.refresh_controls()
        if self.demo_mode:
            self._device_status(_("Demo mode: fake backend, no loudspeaker."))
        elif not self._devices:
            self._device_status(_("No audio device found; Universal DAW Mode still works."), "warn")
        else:
            self._device_status(_("{n} audio device(s) found.").format(n=len(self._devices)))

    def _device_status(self, text: str, tone: str = "") -> None:
        """The footer's line about the devices: the Standalone route's, so the
        DAW route never shows an interface's status."""
        if self.route == ROUTE_STANDALONE:
            set_banner_text(self.status, text, tone)

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
            label_text = f"[{d.index}] {d.name} ({d.host_api})"
            if d.is_input:
                star = "★ " if probe.recommended_input else ""
                self.input_device.addItem(
                    _("{name} - {count} in").format(
                        name=f"{star}{label_text}", count=d.max_input_channels
                    ),
                    d.index,
                )
            if d.is_output:
                star = "★ " if probe.recommended_output else ""
                self.output_device.addItem(
                    _("{name} - {count} out").format(
                        name=f"{star}{label_text}", count=d.max_output_channels
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
        device_txt = ", ".join(parts) if parts else _("unknown")
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

    def start_measurement(self) -> None:
        from reverbscope.audio.backend import get_backend

        if self.is_busy():
            return
        try:
            settings = self._sweep_at(self.playback_level.value())
        except ReverbScopeError as exc:
            QMessageBox.critical(self, _("Invalid settings"), localize(str(exc)))
            return
        if settings.level_dbfs > SAFE_MAX_LEVEL_DBFS and not self.acknowledge.isChecked():
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
        if not self._may_replace_unsaved_take():
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
        self._taking = True
        self._analysis_route = ROUTE_STANDALONE
        self.progress.setRange(0, 100)
        self._set_busy(True, _("Playing the sweep and recording..."))
        self._generation = self.state.generation
        self._measure_worker = MeasureWorker(
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
        self._measure_worker.succeeded.connect(self._on_recorded)
        self._measure_worker.failed.connect(self._on_failure)
        self._measure_worker.progress.connect(self._on_progress)
        self._measure_worker.stopped.connect(self._on_stopped)
        self._measure_worker.start()

    def stop_measurement(self) -> None:
        if self._measure_worker is not None:
            self._measure_worker.request_stop()

    def _on_progress(self, fraction: float) -> None:
        self.progress.setValue(int(fraction * 100.0))

    def _on_stopped(self) -> None:
        self._taking = False
        self._set_busy(False, _("Stopped."))

    def _on_recorded(self, recording: AudioSignal) -> None:
        self._taking = False
        if self._stale():
            self._set_busy(False, late_result_text(), tone="warn")
            return
        plan = self._channel_plan
        reference = self._take_reference
        assert plan is not None and reference is not None
        # The take takes the shared state: an analysis another page started
        # meanwhile is late from here on.
        self._generation = self.state.claim()
        self.state.mode = ROUTE_STANDALONE
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
            mode=DEMO_MODE if self._take_synthetic else ROUTE_STANDALONE,
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
        self._analysing = True
        self.progress.setRange(0, 0)
        self._set_busy(True, _("Recorded. Analyzing..."))
        self._analysis_worker = AnalysisWorker(recording, reference, self._take_analysis_settings)
        self._analysis_worker.succeeded.connect(self._on_success)
        self._analysis_worker.failed.connect(self._on_failure)
        self._analysis_worker.start()

    def _on_success(self, result: AnalysisResult) -> None:
        self._analysing = False
        if self._stale():
            self._set_busy(False, late_result_text(), tone="warn")
            return
        findings, problem = safe_findings(result, self.state.profile)
        self.state.result = result
        self.state.findings = findings
        self.state.findings_problem = problem
        # A live take that is not a demo has no file until it is saved: New
        # Measurement and Open Session ask first. A DAW recording is a file.
        self.state.unsaved_take = (
            not self.demo_mode
            and self.state.recording is not None
            and self.state.recording_path is None
        )
        self._set_busy(False, _("Done."))
        self.analysis_finished.emit()

    def _on_failure(self, message: str) -> None:
        self._taking = False
        self._analysing = False
        if self._analysis_route == ROUTE_DAW:
            text = _("Analysis failed: {message}").format(message=message)
            title = _("Analysis failed")
        else:
            text = _("Measurement failed: {message}").format(message=message)
            title = _("Measurement failed")
        self._set_busy(False, text, tone="warn")
        if not self._stale():
            # An analysis the user abandoned (New Measurement meanwhile) keeps
            # its failure on this page; no dialog over the page they are on.
            error_box(self, title, message)
