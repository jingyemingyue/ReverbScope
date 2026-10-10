"""Frequency response view: overlays, display smoothing, level alignment, difference pane."""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from reverbscope.display import DisplayDataError
from reverbscope.display.curves import (
    DEFAULT_ALIGN_BAND_HZ,
    difference,
    level_offset,
    smooth_fractional_octave,
)
from reverbscope.i18n import _
from reverbscope.ui.plotkit import DASHES, X_FREQUENCY, ChartPanel
from reverbscope.ui.theme import tokens
from reverbscope.ui.views.base import AnalysisView
from reverbscope.ui.workspace import Entry, WorkspaceModel, entry_label

#: The smoothing combo: ``-1`` = the analysis' own smoothed curve.
STORED_SMOOTHING = -1
SMOOTHING_CHOICES = (STORED_SMOOTHING, 0, 48, 24, 12, 6, 3, 1)


def smoothing_text(choice: int, stored_fraction: int | None = None) -> str:
    if choice == STORED_SMOOTHING:
        if stored_fraction:
            return _("analysis smoothing (1/{fraction} octave)").format(fraction=stored_fraction)
        return _("analysis smoothing")
    if choice == 0:
        return _("no smoothing (stored curve)")
    return _("display smoothing 1/{fraction} octave").format(fraction=choice)


class FrequencyView(AnalysisView):
    view_id = "fr"

    def __init__(self, model: WorkspaceModel, parent: QWidget | None = None) -> None:
        super().__init__(model, parent)
        self._x_default = (20.0, 24_000.0)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)
        controls = QHBoxLayout()
        controls.addWidget(QLabel(_("Smoothing")))
        self.smoothing = QComboBox()
        for choice in SMOOTHING_CHOICES:
            self.smoothing.addItem(smoothing_text(choice), choice)
        self.smoothing.setToolTip(
            _(
                "Display smoothing averages the stored curve in power over a fraction of an "
                "octave. It changes the picture only; exports say which was applied."
            )
        )
        self.smoothing.currentIndexChanged.connect(self.refresh)
        controls.addWidget(self.smoothing)
        self.align = QCheckBox(_("Align levels at 500 Hz to 2 kHz"))
        self.align.setToolTip(
            _(
                "Shift every curve so its mean level between 500 Hz and 2 kHz is 0 dB. The "
                "shift is shown in the legend."
            )
        )
        self.align.toggled.connect(self.refresh)
        controls.addWidget(self.align)
        self.show_raw = QCheckBox(_("Show the stored curve"))
        self.show_raw.setToolTip(_("Draw the unsmoothed stored curve of the current measurement."))
        self.show_raw.toggled.connect(self.refresh)
        controls.addWidget(self.show_raw)
        controls.addStretch(1)
        layout.addLayout(controls)

        self.splitter = QSplitter(Qt.Orientation.Vertical)
        self.chart = ChartPanel(
            X_FREQUENCY,
            x_label=_("Frequency (Hz)"),
            y_label=_("Magnitude (dB, relative)"),
            title=_("Frequency response"),
        )
        self.chart.export_name = "frequency-response"
        self.diff = ChartPanel(
            X_FREQUENCY,
            x_label=_("Frequency (Hz)"),
            y_label=_("Difference (dB)"),
            title=_("Difference (current − baseline)"),
        )
        self.diff.export_name = "frequency-difference"
        self.diff.plot_item.setXLink(self.chart.plot_item)
        self.splitter.addWidget(self.chart)
        self.splitter.addWidget(self.diff)
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 1)
        layout.addWidget(self.splitter, 1)
        self.notes = QLabel("")
        self.notes.setProperty("role", "hint")
        self.notes.setWordWrap(True)
        layout.addWidget(self.notes)
        for signal in (
            model.current_changed,
            model.overlay_changed,
            model.baseline_changed,
            model.entries_changed,
        ):
            signal.connect(self.refresh)

    def title(self) -> str:
        return _("Frequency response")

    # --- data -------------------------------------------------------------------

    def curve_for(self, entry: Entry) -> tuple[np.ndarray, np.ndarray, str] | None:
        """The curve drawn for ``entry`` and the processing applied, or None."""
        assert entry.result is not None
        fr = entry.result.frequency_response
        if fr.frequencies_hz.size == 0:
            return None
        choice = int(self.smoothing.currentData())
        cache_name = ("fr", choice)
        cached = self.model.cache_get(entry.key, cache_name)
        if cached is None:
            if choice == STORED_SMOOTHING and fr.magnitude_db_smoothed is not None:
                db = np.asarray(fr.magnitude_db_smoothed, dtype=np.float64)
                processing = smoothing_text(choice, fr.smoothing_fraction)
            elif choice > 0:
                db = smooth_fractional_octave(fr.frequencies_hz, fr.magnitude_db_raw, choice)
                processing = smoothing_text(choice)
            else:
                db = np.asarray(fr.magnitude_db_raw, dtype=np.float64)
                processing = smoothing_text(0)
            cached = (np.asarray(fr.frequencies_hz, dtype=np.float64), db, processing)
            self.model.cache_put(entry.key, cache_name, cached)
        f, db, processing = cached
        if self.align.isChecked():
            offset = level_offset(f, db, DEFAULT_ALIGN_BAND_HZ)
            if offset is not None:
                db = db - offset
                processing += "; " + _("aligned by {offset:+.1f} dB").format(offset=-offset)
        return f, db, processing

    # --- drawing ----------------------------------------------------------------

    def redraw(self) -> None:
        t = tokens()
        self.chart.clear()
        self.diff.clear()
        current = self.model.current()
        notes: list[str] = []
        tops: list[float] = []
        curves: dict[str, tuple[np.ndarray, np.ndarray]] = {}
        for entry in self.model.drawn():
            data = self.curve_for(entry)
            if data is None:
                notes.append(
                    _("{name}: no frequency response stored with this session").format(
                        name=entry_label(entry)
                    )
                )
                continue
            f, db, processing = data
            curves[entry.key] = (f, db)
            is_current = current is not None and entry.key == current.key
            self.chart.add_curve(
                entry_label(entry),
                f,
                db,
                color=entry.color,
                width=2.2 if is_current else 1.2,
                style=DASHES[entry.color_index % len(DASHES)],
                key=entry.key,
                processing=processing,
                readout=is_current,
                z=10 if is_current else 0,
            )
            finite = db[np.isfinite(db)]
            if finite.size:
                tops.append(float(np.percentile(finite, 99.5)))
        nyquist = 24_000.0
        low = 20.0
        if current is not None and current.result is not None:
            result = current.result
            nyquist = result.sample_rate / 2.0
            fr = result.frequency_response
            if fr.frequencies_hz.size == 0:
                # A session saved without curves (--no-curves) keeps the figures only.
                self.chart.set_message(_("No frequency response stored with this session"))
            if self.show_raw.isChecked() and fr.frequencies_hz.size:
                self.chart.add_curve(
                    _("{name} (stored)").format(name=entry_label(current)),
                    fr.frequencies_hz,
                    fr.magnitude_db_raw,
                    color=t["muted"],
                    width=0.8,
                    style=Qt.PenStyle.DotLine,
                    processing=smoothing_text(0),
                    z=-1,
                    alpha=150,
                )
            loopback = result.impulse_response.loopback
            if (
                loopback is not None
                and loopback.interface_response_hz is not None
                and loopback.interface_response_db is not None
            ):
                self.chart.add_curve(
                    _("audio interface (loopback)"),
                    loopback.interface_response_hz,
                    loopback.interface_response_db,
                    color=t["muted"],
                    width=1.0,
                    style=Qt.PenStyle.DashLine,
                )
            band = fr.excitation_band or result.impulse_response.excitation_band
            if band is not None:
                if band.low_hz > low:
                    self.chart.add_region(low / 2.0, band.low_hz, color=t["muted"], alpha=45)
                if band.high_hz < nyquist:
                    self.chart.add_region(band.high_hz, nyquist, color=t["muted"], alpha=45)
                notes.append(
                    _(
                        "Shaded: outside the sweep's range ({low:.0f} Hz to {high:.0f} Hz); "
                        "the curve there is not a measurement."
                    ).format(low=band.low_hz, high=band.high_hz)
                )
                low = max(low, min(band.low_hz, 20.0))
            notes.append(
                _("Window {window:.2f} s, resolution {resolution:.1f} Hz.").format(
                    window=fr.window_s, resolution=fr.resolution_hz
                )
                if np.isfinite(fr.resolution_hz)
                else _("Window {window:.2f} s.").format(window=fr.window_s)
            )
        top = max(tops) if tops else 0.0
        self._x_default = (low, nyquist)
        self.chart.set_default_range(self._x_default, (top - 60.0, top + 10.0))
        self._draw_difference(curves, notes)
        self.notes.setText("  ".join(notes))
        if not self.model.drawn():
            self.chart.set_title(_("Frequency response: no measurement selected"))
        else:
            self.chart.set_title(_("Frequency response"))

    def _draw_difference(
        self, curves: dict[str, tuple[np.ndarray, np.ndarray]], notes: list[str]
    ) -> None:
        baseline = self.model.baseline()
        current = self.model.current()
        show = (
            baseline is not None
            and current is not None
            and baseline.key != current.key
            and baseline.result is not None
        )
        self.diff.setVisible(show)
        if not show:
            return
        assert baseline is not None and current is not None
        base = curves.get(baseline.key)
        if base is None:
            data = self.curve_for(baseline)
            base = (data[0], data[1]) if data is not None else None
        cur = curves.get(current.key)
        if base is None or cur is None:
            notes.append(_("No difference: one of the two has no frequency response."))
            return
        try:
            grid, delta = difference(base[0], base[1], cur[0], cur[1])
        except DisplayDataError as exc:
            notes.append(exc.text())
            return
        self.diff.set_title(
            _("Difference: {current} − {baseline}").format(
                current=entry_label(current), baseline=entry_label(baseline)
            )
        )
        self.diff.add_curve(
            _("difference"),
            grid,
            delta,
            color=current.color,
            width=1.6,
            readout=True,
            processing=_("current minus baseline, both as drawn above"),
        )
        self.diff.add_hline(0.0, color=tokens()["muted"])
        finite = np.abs(delta[np.isfinite(delta)])
        span = max(6.0, float(np.percentile(finite, 99)) + 2.0) if finite.size else 12.0
        # The same x range as the chart above: the two panes are linked.
        self.diff.set_default_range(self._x_default, (-span, span))

    def restyle(self) -> None:
        self.chart.restyle()
        self.diff.restyle()
        self.refresh()
