"""Universal DAW Mode as four steps: generate the test signal, record it in
the DAW, import the recording and choose the channels, check and analyse.

Every step can be returned to; a later step shows what the earlier ones
settled (file, sample rate, channels) and a link back to change it. The
analysis itself runs through :class:`~reverbscope.ui.measure_flow.AnalysisRun`.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from reverbscope.core.pipeline import Reference
from reverbscope.errors import ReverbScopeError
from reverbscope.i18n import N_, _, localize
from reverbscope.io.wav import load_reference, read_wav, write_sweep_file
from reverbscope.models.audio import AudioSignal
from reverbscope.models.configuration import SUPPORTED_SAMPLE_RATES, AnalysisSettings, SweepSettings
from reverbscope.models.result import AnalysisResult
from reverbscope.models.session import MeasurementSession
from reverbscope.ui.measure_flow import AnalysisRun, accept_result, late_result_text
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
    ask_save_path,
    error_box,
    flat,
    label,
    primary,
)
from reverbscope.ui.workspace import action_row

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

STEP_GENERATE, STEP_RECORD, STEP_IMPORT, STEP_ANALYSE = range(4)


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


class DawModePage(QWidget):
    analysis_finished = Signal()
    back = Signal()
    #: ``(busy, text, fraction or None, stoppable)`` for the window's status bar.
    activity_changed = Signal(bool, str, object, bool)
    #: The step shown changed: the window updates the details pane.
    step_changed = Signal(int)

    def __init__(self, state: MeasurementState, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.state = state
        self.setProperty("page", True)
        self._run = AnalysisRun(state, self)
        self._run.succeeded.connect(self._on_success)
        self._run.failed.connect(self._on_failure)
        # The recording this page imported. The shared state holds the take
        # of the session on the Results page, which a Standalone or Demo take
        # replaces: analysing that one put a take the page never showed
        # (a synthetic demo among them) into a Universal DAW session.
        self._recording: AudioSignal | None = None
        self._recording_path: Path | None = None
        # The sweep of Step 1 (or the reference file chosen), kept here for
        # the same reason: a Standalone take used to replace it, and the
        # recording was deconvolved with a sweep the page did not show.
        self._reference: Reference | None = None
        self._sweep_settings = state.sweep_settings
        self._sweep_path: Path | None = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        top = QWidget()
        top_row = QHBoxLayout(top)
        top_row.setContentsMargins(20, 12, 20, 4)
        self.steps = StepBar(
            [
                _("Generate test signal"),
                _("Record in the DAW"),
                _("Import and choose channels"),
                _("Check and analyse"),
            ]
        )
        self.steps.step_chosen.connect(self.show_step)
        top_row.addWidget(self.steps)
        outer.addWidget(top)
        self.pages = QStackedWidget()
        outer.addWidget(self.pages, 1)
        self.action_area = ActionArea()
        outer.addWidget(self.action_area)

        self._build_generate()
        self._build_record()
        self._build_import()
        self._build_analyse()

        self.back_button = self.action_area.back_button
        self.back_button.clicked.connect(self.back.emit)
        self.action_area.prev_button.clicked.connect(
            lambda: self.show_step(self.steps.current() - 1)
        )
        self.action_area.next_button.clicked.connect(self._next)
        self.analyze_button = primary(QPushButton(_("Analyze")))
        self.analyze_button.setShortcut("Ctrl+Return")
        self.analyze_button.setToolTip(
            _("Deconvolve the recording and read the room (Ctrl+Return).")
        )
        self.analyze_button.clicked.connect(self.start_analysis)
        self.action_area.right.addWidget(self.analyze_button)
        self.progress = self.action_area.progress
        self.progress.setRange(0, 0)
        self.status = self.action_area.status
        # The context bar's actions for this page.
        self.context_actions = action_row()
        self.detail = StepHelp()
        self.show_step(STEP_GENERATE)

    # --- building ---------------------------------------------------------------

    def _build_generate(self) -> None:
        panel = StepPanel(
            _("Generate the test signal"),
            _(
                "Write the sine sweep as a WAV file at your DAW project's sample rate. "
                "A sidecar JSON next to it stores the sweep definition; keep both together."
            ),
        )
        form_box = QGroupBox(_("Test signal"))
        form1 = QFormLayout(form_box)
        self.sample_rate = QComboBox()
        for sr in SUPPORTED_SAMPLE_RATES:
            self.sample_rate.addItem(f"{sr} Hz", sr)
        self.sample_rate.setCurrentIndex(
            list(SUPPORTED_SAMPLE_RATES).index(self.state.sweep_settings.sample_rate)
        )
        self.sample_rate.setToolTip(_("Must equal the DAW project's sample rate."))
        self.duration = QDoubleSpinBox()
        self.duration.setRange(1.0, 60.0)
        self.duration.setValue(self.state.sweep_settings.duration_s)
        self.duration.setSuffix(" s")
        self.level = QDoubleSpinBox()
        self.level.setRange(-40.0, 0.0)
        self.level.setValue(self.state.sweep_settings.level_dbfs)
        self.level.setSuffix(" dBFS")
        form1.addRow(_("Sample rate"), self.sample_rate)
        form1.addRow(_("Sweep duration"), self.duration)
        form1.addRow(_("Peak level"), self.level)
        self.save_sweep_button = primary(QPushButton(_("Save Test Signal WAV...")))
        self.save_sweep_button.clicked.connect(self._choose_sweep_target)
        self.sweep_label = QLabel(_("No test signal written yet."))
        self.sweep_label.setWordWrap(True)
        form1.addRow(self.save_sweep_button)
        form1.addRow(self.sweep_label)
        panel.body.addWidget(form_box)
        existing = QGroupBox(_("Already have the test signal?"))
        existing_form = QFormLayout(existing)
        self.reference_button = QPushButton(_("Choose Reference Sweep..."))
        self.reference_button.clicked.connect(self._choose_reference)
        self.reference_label = QLabel(
            _("Reference: the test signal from Step 1 (or choose a file).")
        )
        self.reference_label.setWordWrap(True)
        existing_form.addRow(self.reference_button, self.reference_label)
        panel.body.addWidget(existing)
        self.pages.addWidget(_scrolled(panel))

    def _build_record(self) -> None:
        panel = StepPanel(
            _("Record it in your DAW"),
            _("ReverbScope never talks to the DAW: you play the file and record the room."),
        )
        keys = QGroupBox(_("What matters"))
        keys_layout = QVBoxLayout(keys)
        for text in (
            _(
                "Project sample rate = the test signal's sample rate; time-stretching off for the clip."
            ),
            _("No plug-ins on the sweep track or the master bus, room correction included."),
            _(
                "Play the sweep through the one loudspeaker under test; record the microphone on a second track."
            ),
            _("Export that track as WAV, AIFF, CAF or FLAC without normalising or trimming."),
            _("Keep the monitor level low: clearly audible, not loud."),
        ):
            keys_layout.addWidget(label(f"•  {text}", wrap=True))
        panel.body.addWidget(keys)
        instructions = QLabel(_(DAW_INSTRUCTIONS))
        instructions.setWordWrap(True)
        instructions.setProperty("role", "hint")
        self.instructions = CollapsibleSection(_("Step-by-step notes"), instructions)
        panel.body.addWidget(self.instructions)
        panel.body.addWidget(
            label(_("When the recording is exported, go on to the next step."), "hint", wrap=True)
        )
        self.pages.addWidget(_scrolled(panel))

    def _build_import(self) -> None:
        panel = StepPanel(
            _("Import the recording"),
            _(
                "Choose the exported track. ReverbScope finds the sweep in it; pick the "
                "microphone channel and, if one was recorded, the loopback channel."
            ),
        )
        form_box = QGroupBox(_("Recording"))
        form3 = QFormLayout(form_box)
        self.recording_button = primary(QPushButton(_("Choose Recording...")))
        self.recording_button.clicked.connect(self._choose_recording)
        self.recording_label = QLabel(_("No recording selected."))
        self.recording_label.setWordWrap(True)
        self.channel = QComboBox()
        self.channel.setToolTip(_("The channel with the measurement microphone."))
        self.loopback_channel = QComboBox()
        self.loopback_channel.setToolTip(
            _("The channel with the electrical loopback cable, if one was recorded.")
        )
        self._reset_channel_lists()
        form3.addRow(self.recording_button, self.recording_label)
        form3.addRow(_("Microphone channel"), self.channel)
        form3.addRow(_("Loopback channel"), self.loopback_channel)
        panel.body.addWidget(form_box)
        self.reference_summary = label("", "hint", wrap=True)
        panel.body.addWidget(self.reference_summary)
        self.pages.addWidget(_scrolled(panel))

    def _build_analyse(self) -> None:
        panel = StepPanel(
            _("Check the configuration and analyse"),
            _("What the analysis will use. Go back to a step to change it."),
        )
        summary_box = QGroupBox(_("Summary"))
        summary_layout = QVBoxLayout(summary_box)
        self.summary = KeyValueList()
        summary_layout.addWidget(self.summary)
        links = QHBoxLayout()
        change_signal = flat(QPushButton(_("Change test signal")))
        change_signal.clicked.connect(lambda: self.show_step(STEP_GENERATE))
        change_recording = flat(QPushButton(_("Change recording or channels")))
        change_recording.clicked.connect(lambda: self.show_step(STEP_IMPORT))
        links.addWidget(change_signal)
        links.addWidget(change_recording)
        links.addStretch(1)
        summary_layout.addLayout(links)
        panel.body.addWidget(summary_box)
        meta, self.room, self.position, self.mic = metadata_form(self.state)
        panel.body.addWidget(meta)
        profile_box = QGroupBox(_("Interpretation"))
        profile_form = QFormLayout(profile_box)
        self.profile = profile_combo(self.state)
        row, self.profile_help = profile_row(self.profile, self)
        profile_form.addRow(_("Recording profile"), row)
        panel.body.addWidget(profile_box)
        self.placement = PlacementInputs()
        self.placement_section = CollapsibleSection(
            _("Optional tape measurements (placement geometry)"), self.placement
        )
        panel.body.addWidget(self.placement_section)
        self.pages.addWidget(_scrolled(panel))

    # --- steps --------------------------------------------------------------------

    def show_step(self, index: int) -> None:
        index = max(0, min(index, self.pages.count() - 1))
        self.pages.setCurrentIndex(index)
        self.steps.set_current(index)
        self.action_area.set_step_buttons(index, self.pages.count())
        if index == STEP_ANALYSE:
            self._refresh_summary()
        heading, text = self._step_help(index)
        self.detail.show_step(heading, text)
        self.step_changed.emit(index)

    def _next(self) -> None:
        current = self.steps.current()
        if current == STEP_RECORD:
            # The DAW step has nothing to check: reading it is doing it.
            self.steps.set_summary(STEP_RECORD, _("recorded and exported"))
            self.steps.set_done(STEP_RECORD, True)
        self.show_step(current + 1)

    def _step_help(self, index: int) -> tuple[str, str]:
        helps = {
            STEP_GENERATE: (
                _("Generate test signal"),
                _(
                    "The sweep rises from 20 Hz to the Nyquist frequency at the sample rate "
                    "chosen. The peak level is digital (dBFS); -12 dBFS leaves headroom for "
                    "the DAW's monitoring. The sidecar JSON holds the exact definition the "
                    "analysis deconvolves with, so keep it next to the WAV."
                ),
            ),
            STEP_RECORD: (
                _("Record in the DAW"),
                _(
                    "A sweep played at another sample rate or through time-stretching arrives "
                    "at the wrong speed; the measurement health check then says so and lists "
                    "where each DAW keeps the setting."
                ),
            ),
            STEP_IMPORT: (
                _("Import and choose channels"),
                _(
                    '"Auto" picks the channel with the highest level. A loopback channel is '
                    "the interface output wired straight back to an input: it removes the "
                    "interface's own response and latency from the result."
                ),
            ),
            STEP_ANALYSE: (
                _("Check and analyse"),
                _(
                    "Room, position and microphone are stored with the session so a project "
                    "can list it. The recording profile decides which thresholds the findings "
                    "use; the numbers themselves do not depend on it."
                ),
            ),
        }
        return helps[index]

    def _refresh_summary(self) -> None:
        rows: list[tuple[str, str]] = []
        if self._reference is None:
            rows.append((_("Test signal"), _("none yet (Step 1)")))
        else:
            settings = self._sweep_settings
            name = self._sweep_path.name if self._sweep_path is not None else _("settings")
            rows.append(
                (
                    _("Test signal"),
                    _("{name}: {rate} Hz, {seconds:.1f} s, {level:g} dBFS").format(
                        name=name,
                        rate=settings.sample_rate,
                        seconds=settings.duration_s,
                        level=settings.level_dbfs,
                    ),
                )
            )
        if self._recording is None:
            rows.append((_("Recording"), _("none yet (Step 3)")))
        else:
            rec = self._recording
            name = self._recording_path.name if self._recording_path else _("recording")
            rows.append(
                (
                    _("Recording"),
                    _("{name}: {seconds:.1f} s, {rate} Hz, {channels} channel(s)").format(
                        name=name,
                        seconds=rec.duration_s,
                        rate=rec.sample_rate,
                        channels=rec.n_channels,
                    ),
                )
            )
            if (
                self._reference is not None
                and self._reference.settings is not None
                and self._reference.settings.sample_rate != rec.sample_rate
            ):
                rows.append(
                    (
                        _("Sample rate"),
                        _(
                            "the recording is at {recording} Hz but the test signal at "
                            "{sweep} Hz: the analysis will report the playback speed"
                        ).format(
                            recording=rec.sample_rate,
                            sweep=self._reference.settings.sample_rate,
                        ),
                    )
                )
        rows.append((_("Microphone channel"), self.channel.currentText()))
        rows.append((_("Loopback channel"), self.loopback_channel.currentText()))
        self.summary.set_rows(rows)

    # --- step 1 -----------------------------------------------------------------
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
        self.reference_label.setText(_("Reference: {name}").format(name=wav_path.name))
        self._reference_changed()

    def _reference_changed(self) -> None:
        self.steps.set_done(STEP_GENERATE, self._reference is not None)
        if self._reference is not None and self._sweep_path is not None:
            self.reference_summary.setText(
                _("Reference sweep: {name}").format(name=self._sweep_path.name)
            )
            settings = self._sweep_settings
            self.steps.set_summary(
                STEP_GENERATE,
                _("{name}: {rate} Hz, {seconds:.1f} s, {level:g} dBFS").format(
                    name=self._sweep_path.name,
                    rate=settings.sample_rate,
                    seconds=settings.duration_s,
                    level=settings.level_dbfs,
                ),
            )
        self.action_area.set_status("")

    # --- step 3 -----------------------------------------------------------------
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
        self.steps.set_summary(
            STEP_IMPORT,
            _("{name}: {seconds:.1f} s, {rate} Hz, {channels} channel(s)").format(
                name=path.name,
                seconds=recording.duration_s,
                rate=recording.sample_rate,
                channels=recording.n_channels,
            ),
        )
        self.steps.set_summary(STEP_RECORD, _("recorded and exported"))
        self.steps.set_done(STEP_IMPORT, True)
        self.steps.set_done(STEP_RECORD, True)
        self.action_area.set_status("")

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
        self._reference_changed()

    # --- step 4 -----------------------------------------------------------------
    @property
    def _worker(self) -> object:
        """The analysis thread (for the tests that wait for it)."""
        return self._run.worker

    def is_busy(self) -> bool:
        return self._run.is_running()

    def start_analysis(self, *, blocking: bool = False) -> None:
        if self._run.is_running():
            return
        if self._recording is None:
            self.show_step(STEP_IMPORT)
            QMessageBox.warning(
                self, _("No recording"), _("Choose the recorded WAV file first (Step 3).")
            )
            return
        if self._reference is None:
            self.show_step(STEP_GENERATE)
            QMessageBox.warning(
                self,
                _("No reference"),
                _("Generate the test signal (Step 1) or choose the sweep file."),
            )
            return
        channel = self.channel.currentData()
        loopback = self.loopback_channel.currentData()
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
        generation = self.state.claim()
        self.state.mode = "universal_daw"
        self.state.recording = self._recording
        self.state.recording_path = self._recording_path
        self.state.reference = self._reference
        self.state.sweep_settings = self._sweep_settings
        self.state.sweep_path = self._sweep_path
        self.state.session = MeasurementSession(
            mode="universal_daw",
            room_name=self.room.text(),
            measurement_position=self.position.text(),
            microphone_name=self.mic.text(),
            sweep_settings=self._sweep_settings,
            analysis_settings=self.state.analysis_settings,
            sweep_path=str(self._sweep_path) if self._sweep_path else None,
            recording_path=str(self._recording_path) if self._recording_path else None,
            recording_profile=self.state.profile,
        )
        self.show_step(STEP_ANALYSE)
        self._set_busy(True, _("Analyzing..."))
        self._run.start(
            self._recording,
            self._reference,
            self.state.analysis_settings,
            generation=generation,
            blocking=blocking,
        )

    def _reset_channel_lists(self) -> None:
        self.channel.clear()
        self.channel.addItem(_("Auto (highest level)"), None)
        self.loopback_channel.clear()
        self.loopback_channel.addItem(_("None"), None)

    def clear_recording(self) -> None:
        """Forget the imported take (New Measurement, Open Session)."""
        self._recording = None
        self._recording_path = None
        self.recording_label.setText(_("No recording selected."))
        self._reset_channel_lists()
        self.steps.set_summary(STEP_IMPORT, "")
        self.steps.set_done(STEP_IMPORT, False)
        self.steps.set_done(STEP_ANALYSE, False)

    def shutdown_workers(self) -> None:
        """Let a running analysis finish: a QThread destroyed while it runs aborts."""
        self._run.wait()

    def _set_busy(self, busy: bool, text: str = "", *, tone: str = "") -> None:
        self.analyze_button.setEnabled(not busy)
        # Leaving mid-analysis would let the late result replace another session.
        self.back_button.setEnabled(not busy)
        self.progress.setVisible(busy)
        self.action_area.set_status(text, tone)
        self.activity_changed.emit(busy, text, None, False)

    def _stale(self) -> bool:
        """The result that arrives now belongs to a session that is gone."""
        return self._run.stale()

    def _on_success(self, result: AnalysisResult) -> None:
        if self._stale():
            self._set_busy(False, late_result_text(), tone="warn")
            return
        accept_result(self.state, result)
        self.steps.set_summary(STEP_ANALYSE, _("analysed; the result is on the Results page"))
        self.steps.set_done(STEP_ANALYSE, True)
        self._set_busy(False, _("Done."))
        self.analysis_finished.emit()

    def _on_failure(self, message: str) -> None:
        self._set_busy(False, _("Analysis failed: {message}").format(message=message), tone="warn")
        if not self._stale():
            # An analysis the user abandoned (New Measurement meanwhile) keeps
            # its failure on this page; no dialog over the page they are on.
            error_box(self, _("Analysis failed"), message)
