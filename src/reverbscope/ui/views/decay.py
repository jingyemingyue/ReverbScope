"""Decay view: Schroeder curves with the evaluation range, and T values by band."""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QSplitter, QVBoxLayout, QWidget

from reverbscope.i18n import _
from reverbscope.interpretation.profiles import band_text
from reverbscope.labels import validity_word
from reverbscope.models.result import BandDecay, DecayMetric, Validity
from reverbscope.ui.plotkit import (
    BAND_DASHES,
    DASHES,
    X_FREQUENCY,
    X_TIME_S,
    ChartPanel,
    follow_chart_visibility,
    pg,
)
from reverbscope.ui.theme import PLOT_SERIES, tokens
from reverbscope.ui.views.base import AnalysisView
from reverbscope.ui.workspace import (
    Entry,
    WorkspaceModel,
    curve_legend,
    curve_width,
    entry_label,
    hidden_selection_note,
)

METRICS = ("edt", "t20", "t30")
BROADBAND = "__broadband__"
#: Every band of the current measurement in one chart, as the 0.5 Decay tab.
ALL_BANDS = "__all__"
#: Band resolutions of the Resolution list: the octave bands every result has,
#: and the one-third-octave bands of a result analysed with them.
OCTAVE = "octave"
THIRD_OCTAVE = "third_octave"


def metric_of(band: BandDecay, name: str) -> DecayMetric:
    return {"edt": band.edt, "t20": band.t20, "t30": band.t30}[name]


def bands_of(entry: Entry, resolution: str) -> tuple[BandDecay, ...]:
    """The octave or one-third-octave bands of ``entry`` (none when it has none)."""
    if entry.result is None:
        return ()
    if resolution == THIRD_OCTAVE:
        return entry.result.decay.third_octave_bands or ()
    return entry.result.decay.bands


def _third_octave_note(bands: tuple[BandDecay, ...]) -> str:
    """How many one-third-octave bands have two slopes (valid fits only)."""
    fits = [
        b.multi_slope
        for b in bands
        if b.multi_slope is not None
        and b.multi_slope.validity is Validity.VALID
        and b.multi_slope.selected_slopes is not None
    ]
    two = sum(1 for fit in fits if fit.selected_slopes == 2)
    return _(
        "One-third-octave bands: two slopes in {two} of {fitted} bands with a valid fit."
    ).format(two=two, fitted=len(fits))


class DecayView(AnalysisView):
    view_id = "decay"

    def __init__(self, model: WorkspaceModel, parent: QWidget | None = None) -> None:
        super().__init__(model, parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)
        controls = QHBoxLayout()
        # Only shown for a measurement analysed in one-third-octave bands too.
        self.resolution_label = QLabel(_("Resolution"))
        controls.addWidget(self.resolution_label)
        self.resolution = QComboBox()
        self.resolution.addItem(_("Octave"), OCTAVE)
        self.resolution.addItem(_("One-third octave"), THIRD_OCTAVE)
        self.resolution.currentIndexChanged.connect(self._resolution_changed)
        controls.addWidget(self.resolution)
        controls.addWidget(QLabel(_("Band")))
        self.band = QComboBox()
        self.band.currentIndexChanged.connect(self.refresh)
        controls.addWidget(self.band)
        controls.addWidget(QLabel(_("Metric")))
        self.metric_combo = QComboBox()
        for name in METRICS:
            self.metric_combo.addItem(name.upper(), name)
        self.metric_combo.setCurrentIndex(2)
        self.metric_combo.currentIndexChanged.connect(self.refresh)
        controls.addWidget(self.metric_combo)
        controls.addStretch(1)
        layout.addLayout(controls)
        splitter = QSplitter(Qt.Orientation.Vertical)
        self.chart = ChartPanel(
            X_TIME_S,
            x_label=_("Time (s)"),
            y_label=_("Schroeder decay (dB)"),
            title=_("Energy decay curves"),
        )
        self.chart.export_name = "decay"
        self.bands_chart = ChartPanel(
            X_FREQUENCY,
            x_label=_("Band centre (Hz)"),
            y_label=_("Reverberation time (s)"),
            y_unit="s",
            title=_("Reverberation by band"),
        )
        self.bands_chart.export_name = "decay-bands"
        splitter.addWidget(self.chart)
        splitter.addWidget(self.bands_chart)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter, 1)
        self.notes = QLabel("")
        self.notes.setProperty("role", "hint")
        self.notes.setWordWrap(True)
        layout.addWidget(self.notes)
        self._bands_of = ""
        for signal in (
            model.current_changed,
            model.overlay_changed,
            model.entries_changed,
            model.entry_updated,
        ):
            signal.connect(self.refresh)
        follow_chart_visibility(self.chart, model)

    def title(self) -> str:
        return _("Decay")

    def resolution_value(self) -> str:
        """The band resolution shown: octave unless one-third octave is chosen
        and the current measurement has those bands."""
        current = self.model.current()
        if (
            self.resolution.currentData() == THIRD_OCTAVE
            and current is not None
            and current.result is not None
            and current.result.decay.third_octave_bands
        ):
            return THIRD_OCTAVE
        return OCTAVE

    def _resolution_changed(self) -> None:
        self._bands_of = ""
        self.refresh()

    def _fill_bands(self, entry: Entry | None) -> None:
        """The band list of the current entry, keeping the chosen band by label."""
        has_thirds = bool(
            entry is not None and entry.result is not None and entry.result.decay.third_octave_bands
        )
        self.resolution_label.setVisible(has_thirds)
        self.resolution.setVisible(has_thirds)
        resolution = self.resolution_value()
        key = f"{entry.key}#{resolution}" if entry is not None else ""
        if entry is None or entry.result is None or key == self._bands_of:
            return
        self._bands_of = key
        chosen = self.band.currentData()
        self.band.blockSignals(True)
        self.band.clear()
        self.band.addItem(_("Broadband"), BROADBAND)
        self.band.addItem(_("All bands of the current measurement"), ALL_BANDS)
        for band in bands_of(entry, resolution):
            self.band.addItem(band_text(band.band_label), band.band_label)
        row = self.band.findData(chosen)
        self.band.setCurrentIndex(max(row, 0))
        self.band.blockSignals(False)

    def _band_of(self, entry: Entry) -> BandDecay | None:
        assert entry.result is not None
        chosen = self.band.currentData() or BROADBAND
        if chosen in (BROADBAND, ALL_BANDS):
            return entry.result.decay.broadband
        return next(
            (b for b in bands_of(entry, self.resolution_value()) if b.band_label == chosen), None
        )

    def redraw(self) -> None:
        t = tokens()
        current = self.model.current()
        self._fill_bands(current)
        self.chart.clear()
        self.bands_chart.clear()
        metric_name = str(self.metric_combo.currentData())
        notes: list[str] = []
        longest = 0.0
        shown = (
            current
            if current is not None
            and current.result is not None
            and self.model.is_visible(current.key)
            else None
        )
        decay = shown.result.decay if shown is not None and shown.result is not None else None
        if decay is not None and not any(
            band.edc_db.size
            for band in (decay.broadband, *decay.bands, *(decay.third_octave_bands or ()))
        ):
            # A session saved without curves keeps the figures only; an empty
            # chart with a legend looked like a broken measurement.
            self.chart.set_message(_("No decay curves stored with this session"))
        if self.band.currentData() == ALL_BANDS and shown is not None:
            longest = self._draw_all_bands(shown, notes)
        for entry in [] if self.band.currentData() == ALL_BANDS else self.model.drawn():
            band = self._band_of(entry)
            is_current = current is not None and entry.key == current.key
            is_baseline = entry.key == self.model.baseline_key
            if band is None or band.edc_db.size == 0:
                notes.append(
                    _("{name}: no decay curve stored for this band").format(name=entry_label(entry))
                )
                continue
            longest = max(longest, float(band.edc_time_s[-1]))
            self.chart.add_curve(
                curve_legend(entry, baseline=is_baseline),
                band.edc_time_s,
                band.edc_db,
                color=entry.color,
                width=curve_width(current=is_current, baseline=is_baseline),
                style=DASHES[entry.color_index % len(DASHES)],
                key=entry.key,
                processing=_("Schroeder integral, Lundeby-truncated"),
                readout=is_current,
                z=10 if is_current else 0,
            )
            self._draw_band_values(entry, metric_name, is_current)
        if current is not None and current.result is not None:
            band = self._band_of(current)
            if band is not None:
                metric = metric_of(band, metric_name)
                top, bottom = metric.evaluation_range_db
                region_lo, region_hi = sorted((top, bottom))
                fill = t["accent"]
                shade = pg.LinearRegionItem(
                    values=(region_lo, region_hi),
                    orientation="horizontal",
                    movable=False,
                    brush=pg.mkBrush(fill + "26"),
                )
                for line in shade.lines:
                    line.setPen(pg.mkPen(None))
                shade.setZValue(-10)
                self.chart.add_item(shade)
                value = (
                    f"{metric.seconds:.2f} s"
                    if metric.seconds is not None and metric.validity is Validity.VALID
                    else validity_word(metric.validity)
                )
                notes.append(
                    _(
                        "Shaded: the {metric} evaluation range ({top:.0f} to {bottom:.0f} dB) "
                        "of the current measurement; {metric} = {value}."
                    ).format(metric=metric_name.upper(), top=top, bottom=bottom, value=value)
                )
                if band.noise_floor_db is not None:
                    notes.append(
                        _("Noise floor {floor:.0f} dB re peak.").format(floor=band.noise_floor_db)
                    )
                slope_note = self._draw_slope_fit(current, band)
                if slope_note:
                    notes.append(slope_note)
        if shown is not None and self.resolution_value() == THIRD_OCTAVE:
            notes.append(_third_octave_note(bands_of(shown, THIRD_OCTAVE)))
        self.chart.set_default_range((0.0, longest or 1.0), (-70.0, 5.0))
        self.bands_chart.set_default_range((50.0, 16_000.0), None)
        notes.append(
            _("Band chart: filled = VALID, hollow = not VALID (the value is shown, not trusted).")
        )
        hidden = hidden_selection_note(self.model)
        if hidden:
            notes.append(hidden)
            if not self.model.drawn():
                self.chart.set_message(hidden)
        self.notes.setText("  ".join(notes))

    def _draw_slope_fit(self, entry: Entry, band: BandDecay) -> str:
        """Overlay the two-slope model of the current band, when it has one.

        The curves are the fitted model (``core.multislope``) evaluated on the
        fitted range without its noise term, so they sit on the truncated
        Schroeder curve; each slope is also drawn alone. Returns the note.
        """
        fit = band.multi_slope
        if fit is None or fit.selected_slopes is None:
            return ""
        model = fit.selected
        if model is None:
            return ""
        if model.slope_count == 1:
            if fit.validity is not Validity.VALID:
                return ""
            return _("Slope fit: one slope ({seconds:.2f} s) describes this decay.").format(
                seconds=model.decay_times_s[0]
            )
        if (
            fit.fit_start_s is None
            or fit.fit_end_s is None
            or fit.integration_end_s is None
            or band.edc_time_s.size == 0
        ):
            return ""
        t = tokens()
        end = min(fit.fit_end_s, float(band.edc_time_s[-1]))
        times = np.linspace(fit.fit_start_s, end, 200)
        total = model.evaluate(times, fit.integration_end_s, include_noise=False)
        level = 10.0 * np.log10(np.maximum(total, 1e-30))
        processing = _("two-slope model fitted to the decay curve (noise term not drawn)")
        self.chart.add_curve(
            _("Two-slope fit"),
            times,
            level,
            color=t["warn"],
            width=1.6,
            dash=(4, 2),
            key=f"{entry.key}#slopes",
            processing=processing,
            z=12,
        )
        for index, name in enumerate((_("Fast slope T1"), _("Slow slope T2"))):
            self.chart.add_curve(
                name,
                times,
                model.component_db(index, times),
                color=t["muted"],
                width=1.0,
                dash=BAND_DASHES[(index + 1) % len(BAND_DASHES)],
                key=f"{entry.key}#slope{index + 1}",
                processing=processing,
                z=11,
            )
        if fit.knee_time_s is not None and fit.knee_level_db is not None:
            self.chart.add_markers(
                [fit.knee_time_s], [fit.knee_level_db], color=t["warn"], filled=True
            )
        t1, t2 = model.decay_times_s
        text = _(
            "Two-slope fit: T1 = {t1:.2f} s, T2 = {t2:.2f} s, slow slope {late:+.1f} dB "
            "re fast; turning point {knee}."
        ).format(
            t1=t1,
            t2=t2,
            late=model.amplitudes_db[1] - model.amplitudes_db[0],
            knee=(
                _("{time:.2f} s at {level:.0f} dB").format(
                    time=fit.knee_time_s, level=fit.knee_level_db
                )
                if fit.knee_time_s is not None and fit.knee_level_db is not None
                else "–"
            ),
        )
        if fit.validity is not Validity.VALID:
            text += " " + _("({validity}: shown, not trusted.)").format(
                validity=validity_word(fit.validity)
            )
        return text

    def _draw_all_bands(self, entry: Entry | None, notes: list[str]) -> float:
        """Broadband (solid) and every band (its own dash pattern) of ``entry``.

        A band without an RT60 says why in its legend name (outside the
        excitation range, unreliable, ...), as the decay table does.
        """
        if entry is None or entry.result is None:
            return 0.0
        decay = entry.result.decay
        longest = 0.0
        broadband = decay.broadband
        resolution = self.resolution_value()
        if broadband.edc_db.size:
            longest = float(broadband.edc_time_s[-1])
            self.chart.add_curve(
                _("Broadband"),
                broadband.edc_time_s,
                broadband.edc_db,
                color=entry.color,
                width=2.4,
                key=f"{entry.key}#broadband",
                processing=_("Schroeder integral, Lundeby-truncated"),
                readout=True,
                z=10,
            )
        missing: list[str] = []
        for index, band in enumerate(bands_of(entry, resolution)):
            if band.edc_db.size == 0:
                missing.append(f"{band_text(band.band_label)} ({validity_word(band.t30.validity)})")
                continue
            longest = max(longest, float(band.edc_time_s[-1]))
            rt = band.rt60_estimate_s
            name = band_text(band.band_label) + (
                f"  RT60≈{rt:.2f} s"
                if rt is not None
                else f"  ({validity_word(band.t30.validity)})"
            )
            self.chart.add_curve(
                name,
                band.edc_time_s,
                band.edc_db,
                color=PLOT_SERIES[index % len(PLOT_SERIES)],
                width=1.0,
                dash=BAND_DASHES[index % len(BAND_DASHES)],
                key=f"{entry.key}#{band.band_label}",
                processing=_("Schroeder integral, Lundeby-truncated"),
            )
        notes.append(
            _("All bands of {name}; overlays are not drawn in this mode.").format(
                name=entry_label(entry)
            )
        )
        if missing:
            notes.append(_("No curve: {bands}.").format(bands=", ".join(missing)))
        self._draw_band_values(entry, str(self.metric_combo.currentData()), True)
        return longest

    def _draw_band_values(self, entry: Entry, metric_name: str, is_current: bool) -> None:
        assert entry.result is not None
        centres: list[float] = []
        values: list[float] = []
        valid: list[bool] = []
        resolution = self.resolution_value()
        for band in bands_of(entry, resolution):
            metric = metric_of(band, metric_name)
            if band.center_hz is None or metric.seconds is None:
                continue
            centres.append(band.center_hz)
            values.append(metric.seconds)
            valid.append(metric.validity is Validity.VALID)
        if not centres:
            return
        x = np.array(centres)
        y = np.array(values)
        self.bands_chart.add_curve(
            entry_label(entry),
            x,
            y,
            color=entry.color,
            width=1.6 if is_current else 1.0,
            style=DASHES[entry.color_index % len(DASHES)],
            key=entry.key,
            processing=(
                _("{metric}, one-third-octave bands").format(metric=metric_name.upper())
                if resolution == THIRD_OCTAVE
                else metric_name.upper()
            ),
            readout=is_current,
        )
        mask = np.array(valid)
        if mask.any():
            self.bands_chart.add_markers(x[mask], y[mask], color=entry.color, filled=True)
        if (~mask).any():
            self.bands_chart.add_markers(x[~mask], y[~mask], color=entry.color, filled=False)

    def restyle(self) -> None:
        self.chart.restyle()
        self.bands_chart.restyle()
        self.refresh()
