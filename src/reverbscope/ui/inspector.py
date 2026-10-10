"""The inspector: what the current measurement is and how far to trust it.

The right column of the workstation. For the current entry it shows the
measurement health, the key figures each with its validity, the conditions
it was measured under, the comparison verdict against the baseline, the
selected early reflection and the room view's consistency checks. Every
number is one the analysis computed; nothing here is a score.
"""

from __future__ import annotations

import html
from collections.abc import Sequence

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QGridLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from reverbscope.errors import ReverbScopeError
from reverbscope.geometry.paths import ConsistencyCheck, speed_for
from reverbscope.health import assess, status_word
from reverbscope.i18n import _, localize
from reverbscope.interpretation.profiles import confidence_text, profile_title
from reverbscope.interpretation.verdicts import verdict_chip
from reverbscope.labels import validity_word
from reverbscope.models.result import AnalysisResult, DecayMetric, EnergyMetric, Validity
from reverbscope.ui.comparison import current_comparison
from reverbscope.ui.theme import tone_color
from reverbscope.ui.views.overview import CONFIDENCE_TONE, HEALTH_TONE, VALIDITY_DISPLAY
from reverbscope.ui.widgets import label, separator
from reverbscope.ui.workspace import Entry, WorkspaceModel, entry_label

#: Chip tone of a room consistency check.
CHECK_TONE = {"ok": "good", "warn": "warn", "unknown": "neutral"}
VERDICT_TONE = {
    "meaningful_improvement": "good",
    "meaningful_degradation": "bad",
    "probably_insignificant": "info",
    "not_comparable": "warn",
    "insufficient_evidence": "neutral",
}


def _tone(validity: Validity) -> str:
    return VALIDITY_DISPLAY.get(validity, ("", "neutral"))[1]


def decay_text(metric: DecayMetric) -> str:
    if metric.seconds is None:
        return "-"
    text = f"{metric.seconds:.2f} s"
    return text if metric.validity is Validity.VALID else f"({text})"


def energy_text(metric: EnergyMetric) -> str:
    if metric.value is None:
        return "-"
    if metric.unit == "dB":
        text = f"{metric.value:+.1f} dB"
    elif metric.unit == "%":
        text = f"{metric.value:.0f} %"
    else:
        text = f"{metric.value * 1000:.0f} ms"
    return text if metric.validity is Validity.VALID else f"({text})"


class _Section(QWidget):
    """A titled block of rows: caption, value, chip."""

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(4)
        self.title = label(title.upper(), "section")
        layout.addWidget(self.title)
        self.note = label("", "hint", wrap=True)
        self.note.hide()
        layout.addWidget(self.note)
        self.grid = QGridLayout()
        self.grid.setHorizontalSpacing(8)
        self.grid.setVerticalSpacing(3)
        self.grid.setColumnStretch(0, 2)
        self.grid.setColumnStretch(1, 3)
        layout.addLayout(self.grid)
        self.extra = QVBoxLayout()
        self.extra.setSpacing(4)
        layout.addLayout(self.extra)
        self.rows = 0

    def clear(self) -> None:
        for layout in (self.grid, self.extra):
            while layout.count():
                item = layout.takeAt(0)
                widget = item.widget() if item is not None else None
                if widget is not None:
                    # Hidden at once: deleteLater alone left the old rows
                    # painted under the new ones until the event loop ran.
                    widget.hide()
                    widget.setParent(None)
                    widget.deleteLater()
        self.rows = 0
        self.set_note("")

    def set_note(self, text: str) -> None:
        self.note.setText(text)
        self.note.setVisible(bool(text))

    def add_row(self, caption: str, value: str, chip: str = "", tone: str = "neutral") -> None:
        """``caption`` over two columns: the value, then the chip word in its tone.

        The chip is inline text rather than a pill so a narrow inspector wraps
        instead of cutting it off.
        """
        name = label(caption, "hint")
        name.setWordWrap(True)
        name.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        shown = QLabel()
        shown.setWordWrap(True)
        shown.setTextFormat(Qt.TextFormat.RichText)
        shown.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        text = html.escape(value)
        if chip:
            color, _soft = tone_color(tone)
            text += f' <span style="color:{color}; font-weight:600">· {html.escape(chip)}</span>'
        shown.setText(text)
        shown.setToolTip(f"{value}  {chip}".strip())
        self.grid.addWidget(name, self.rows, 0, Qt.AlignmentFlag.AlignTop)
        self.grid.addWidget(shown, self.rows, 1, Qt.AlignmentFlag.AlignTop)
        self.rows += 1

    def add_text(self, text: str, role: str | None = "hint") -> QLabel:
        widget = label(text, role, wrap=True)
        widget.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.extra.addWidget(widget)
        return widget

    def add_widget(self, widget: QWidget) -> None:
        self.extra.addWidget(widget)
        # A reused widget was parked while the section was cleared, hidden.
        widget.show()


class Inspector(QWidget):
    """The right column."""

    #: Open the compare view (the verdict's "Details" button).
    compare_requested = Signal()

    def __init__(self, model: WorkspaceModel, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.model = model
        self.setMinimumWidth(220)
        # Holds the reused buttons while their section is rebuilt, so they
        # are never parentless (and never outlive the window).
        self._parking = QWidget(self)
        self._parking.hide()
        self._room_checks: list[ConsistencyCheck] = []
        self._room_note = ""
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body = QWidget()
        body.setProperty("page", True)
        scroll.setWidget(body)
        outer.addWidget(scroll)
        layout = QVBoxLayout(body)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)
        self.heading = label(_("Nothing selected"), "section")
        self.heading.setWordWrap(True)
        layout.addWidget(self.heading)
        self.subtitle = label("", "hint", wrap=True)
        layout.addWidget(self.subtitle)

        self.health = _Section(_("Measurement health"))
        self.figures = _Section(_("Key figures"))
        self.figures.set_note("")
        self.conditions = _Section(_("Conditions"))
        self.comparison = _Section(_("Comparison"))
        self.same_gain = QCheckBox(_("Input gain unchanged"))
        self.same_gain.setToolTip(
            _(
                "Required for a VALID noise delta. Leave unchecked if the preamp gain "
                "may have changed."
            )
        )
        self.same_gain.toggled.connect(self._draw_comparison)
        self.details_button = QPushButton(_("Open the comparison"))
        self.details_button.clicked.connect(self.compare_requested.emit)
        self.profile_button = QPushButton(_("About this profile..."))
        self.profile_button.clicked.connect(self.show_profile_help)
        self.reflection = _Section(_("Selected reflection"))
        self.room = _Section(_("Room checks"))
        for section in (
            self.health,
            self.figures,
            self.conditions,
            self.comparison,
            self.reflection,
            self.room,
        ):
            layout.addWidget(separator())
            layout.addWidget(section)
        layout.addStretch(1)

        for signal in (model.current_changed, model.entries_changed):
            signal.connect(self.refresh)
        model.entry_updated.connect(self._entry_updated)
        model.baseline_changed.connect(self._draw_comparison)
        model.reflection_changed.connect(lambda *_a: self._draw_reflection())
        self.refresh()

    # --- following the model --------------------------------------------------------

    def _entry_updated(self, key: str) -> None:
        if key in (self.model.current_key, self.model.baseline_key):
            self.refresh()

    def refresh(self) -> None:
        entry = self.model.current()
        if entry is None:
            self.heading.setText(_("Nothing selected"))
            self.subtitle.setText(
                _("Open a project or a session, or measure with the strip below.")
            )
        else:
            self.heading.setText(entry_label(entry))
            self.subtitle.setText(entry.error or self._subtitle(entry))
        has = entry is not None and entry.result is not None
        for section in (self.health, self.figures, self.conditions):
            section.setVisible(has)
        if entry is not None and entry.result is not None:
            self._draw_health(entry.result)
            self._draw_figures(entry.result)
            self._draw_conditions(entry)
        self._draw_comparison()
        self._draw_reflection()
        self._draw_room()

    def _subtitle(self, entry: Entry) -> str:
        """Room, position, microphone, profile and rate, as the old Results header read."""
        from reverbscope.demo import localize_demo_name

        bits: list[str] = []
        session = entry.session
        if session is not None:
            bits.extend(
                localize_demo_name(session.mode, part)
                for part in (
                    session.room_name,
                    session.measurement_position,
                    session.microphone_name,
                )
                if part
            )
        if entry.result is not None:
            bits.append(_("{profile} profile").format(profile=profile_title(entry.profile)))
            bits.append(f"{entry.result.sample_rate} Hz")
        if entry.unsaved:
            bits.append(_("not saved yet"))
        if entry.synthetic:
            bits.append(_("synthetic demo, not a room"))
        if entry.directory is not None:
            bits.append(str(entry.directory))
        return "  ·  ".join(bits)

    # --- sections ---------------------------------------------------------------------

    def _draw_health(self, result: AnalysisResult) -> None:
        section = self.health
        section.clear()
        report = assess(result)
        section.add_row(
            _("Overall"),
            _("{good} of {total} checks good").format(
                good=len(report.good), total=len(report.checks)
            ),
            status_word(report.overall),
            HEALTH_TONE[report.overall],
        )
        for check in report.problems:
            section.add_row(check.title, check.reason, status_word(check.status), "warn")

    def _draw_figures(self, result: AnalysisResult) -> None:
        section = self.figures
        section.clear()
        broadband = result.decay.broadband
        if broadband.rt60_estimate_s is not None:
            section.add_row(
                _("RT60 estimate"),
                _("{value:.2f} s from {basis}").format(
                    value=broadband.rt60_estimate_s, basis=broadband.rt60_basis
                ),
            )
        for name, metric in (
            ("EDT", broadband.edt),
            ("T20", broadband.t20),
            ("T30", broadband.t30),
        ):
            section.add_row(
                name, decay_text(metric), validity_word(metric.validity), _tone(metric.validity)
            )
        for name, energy in (
            ("C50", broadband.c50),
            ("C80", broadband.c80),
            ("D50", broadband.d50),
        ):
            section.add_row(
                name, energy_text(energy), validity_word(energy.validity), _tone(energy.validity)
            )
        noise = result.noise
        section.add_row(
            _("Noise floor"),
            _("{rms:.1f} dBFS RMS, uncalibrated").format(rms=noise.rms_dbfs)
            if noise.rms_dbfs is not None
            else _("not computed"),
        )
        ir = result.impulse_response
        confidence = ir.direct_sound_confidence
        section.add_row(
            _("Direct sound"),
            confidence_text(confidence),
            _("confidence"),
            CONFIDENCE_TONE.get(confidence, "neutral"),
        )
        section.add_row(
            _("Early reflections"),
            str(len(result.reflections.reflections)),
            _("above {threshold:g} dB").format(threshold=result.reflections.threshold_db),
            "info",
        )
        section.set_note(_("Values in brackets are shown, not trusted (not VALID)."))

    def _draw_conditions(self, entry: Entry) -> None:
        from reverbscope.demo import localize_demo_name

        assert entry.result is not None
        section = self.conditions
        # The button is reused; take it out before clearing.
        self.profile_button.setParent(self._parking)
        section.clear()
        result = entry.result
        session = entry.session
        if session is not None:
            for caption, value in (
                (_("Room"), session.room_name),
                (_("Position"), entry.position or session.measurement_position),
                (_("Microphone"), session.microphone_name),
                (_("Audio interface"), session.audio_interface),
            ):
                if value:
                    section.add_row(caption, localize_demo_name(session.mode, value))
            sweep = session.sweep_settings
            section.add_row(
                _("Sweep"),
                _("{duration:g} s, {low:g} Hz to {high:g} Hz, {level:g} dBFS").format(
                    duration=sweep.duration_s,
                    low=sweep.start_hz,
                    high=sweep.end_hz,
                    level=sweep.level_dbfs,
                ),
            )
            if session.input_channel is not None:
                section.add_row(_("Microphone input"), str(session.input_channel))
            section.add_row(
                _("Loopback"),
                str(session.loopback_channel) if session.loopback_channel else _("unused"),
            )
            if session.created_at:
                section.add_row(_("Recorded"), session.created_at.replace("T", " ")[:19])
        section.add_row(_("Sample rate"), f"{result.sample_rate} Hz")
        section.add_row(_("Profile"), profile_title(entry.profile))
        section.add_widget(self.profile_button)
        loopback = result.impulse_response.loopback
        if loopback is not None and loopback.path_delay_ms is not None:
            section.add_row(_("Acoustic path delay"), f"{loopback.path_delay_ms:.2f} ms")

    def show_profile_help(self) -> QWidget | None:
        """What the current measurement's recording profile watches for."""
        from reverbscope.ui.profile_dialog import show_profile_help

        entry = self.model.current()
        if entry is None:
            return None
        return show_profile_help(entry.profile, self)

    def _draw_comparison(self, *_args: object) -> None:
        section = self.comparison
        # The check box and the button are reused; take them out before clearing.
        for widget in (self.same_gain, self.details_button):
            widget.setParent(self._parking)
        section.clear()
        baseline = self.model.baseline()
        current = self.model.current()
        if baseline is None:
            section.set_note(
                _("Right-click a measurement in the list and choose Use as baseline to compare.")
            )
            return
        if current is None or current.key == baseline.key:
            section.set_note(
                _("{name} is the baseline. Select another measurement to compare it.").format(
                    name=entry_label(baseline)
                )
            )
            return
        try:
            compared = current_comparison(self.model, same_gain=self.same_gain.isChecked())
        except ReverbScopeError as exc:
            section.set_note(_("Cannot compare: {error}").format(error=localize(str(exc))))
            return
        if compared is None:
            section.set_note(_("Waiting for both measurements to load."))
            return
        verdict = compared.verdict
        section.set_note(
            _("{candidate} against the baseline {baseline}.").format(
                candidate=entry_label(current), baseline=entry_label(baseline)
            )
        )
        section.add_text(verdict.headline(), None)
        for aspect in verdict.aspects:
            section.add_row(
                aspect.title,
                aspect.reason,
                verdict_chip(aspect.verdict),
                VERDICT_TONE.get(str(aspect.verdict), "neutral"),
            )
        section.add_widget(self.same_gain)
        section.add_widget(self.details_button)

    def _draw_reflection(self) -> None:
        section = self.reflection
        section.clear()
        key, index = self.model.selected_reflection()
        entry = self.model.entry(key) if key else None
        if (
            entry is None
            or entry.result is None
            or not 0 <= index < len(entry.result.reflections.reflections)
        ):
            section.set_note(
                _("Click a reflection marker in the impulse response or the room view.")
            )
            return
        reflection = entry.result.reflections.reflections[index]
        speed, temperature, assumed = speed_for(entry.result)
        excess = reflection.delay_ms / 1000.0 * speed
        section.add_row(_("Delay"), f"{reflection.delay_ms:.2f} ms")
        section.add_row(_("Level"), f"{reflection.relative_db:.1f} dB")
        section.add_row(
            _("Excess path"),
            _("{metres:.2f} m at {speed:.1f} m/s").format(metres=excess, speed=speed),
        )
        if assumed:
            section.set_note(
                _("No temperature entered; {temperature:.0f} °C is assumed.").format(
                    temperature=temperature
                )
            )

    # --- room checks (pushed by the room view) ----------------------------------------

    def set_room_checks(self, checks: Sequence[ConsistencyCheck], note: str = "") -> None:
        self._room_checks = list(checks)
        self._room_note = note
        self._draw_room()

    def _draw_room(self) -> None:
        section = self.room
        section.clear()
        if not self._room_checks:
            section.set_note(
                self._room_note
                or _("Enter the room and the device positions in the Room view to check them.")
            )
            return
        section.set_note(self._room_note)
        status_words = {
            "ok": _("consistent"),
            "warn": _("check this"),
            "unknown": _("not checkable"),
        }
        for check in self._room_checks:
            section.add_row(status_words[check.status], check.text, "", CHECK_TONE[check.status])
