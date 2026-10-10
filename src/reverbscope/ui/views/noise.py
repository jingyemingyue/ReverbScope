"""Noise view: the noise spectrum with the detected hum harmonics marked."""

from __future__ import annotations

import numpy as np
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from reverbscope.i18n import _
from reverbscope.interpretation.profiles import noise_segment_text
from reverbscope.ui.plotkit import DASHES, X_FREQUENCY, ChartPanel
from reverbscope.ui.theme import tokens
from reverbscope.ui.views.base import AnalysisView
from reverbscope.ui.workspace import WorkspaceModel, entry_label


class NoiseView(AnalysisView):
    view_id = "noise"

    def __init__(self, model: WorkspaceModel, parent: QWidget | None = None) -> None:
        super().__init__(model, parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)
        self.chart = ChartPanel(
            X_FREQUENCY,
            x_label=_("Frequency (Hz)"),
            y_label=_("PSD (dB re FS^2/Hz)"),
            title=_("Background noise"),
        )
        self.chart.export_name = "noise"
        layout.addWidget(self.chart, 1)
        self.notes = QLabel("")
        self.notes.setProperty("role", "hint")
        self.notes.setWordWrap(True)
        layout.addWidget(self.notes)
        for signal in (model.current_changed, model.overlay_changed, model.entries_changed):
            signal.connect(self.refresh)

    def title(self) -> str:
        return _("Noise")

    def redraw(self) -> None:
        t = tokens()
        self.chart.clear()
        current = self.model.current()
        notes: list[str] = []
        tops: list[float] = []
        nyquist = 24_000.0
        for entry in self.model.drawn():
            assert entry.result is not None
            noise = entry.result.noise
            is_current = current is not None and entry.key == current.key
            if noise.psd_frequencies_hz is None or noise.psd_db is None:
                reason = (
                    _("no quiet segment available")
                    if noise.rms_dbfs is None
                    else _("no noise spectrum stored with this session")
                )
                notes.append(f"{entry_label(entry)}: {reason}")
                continue
            f = np.asarray(noise.psd_frequencies_hz, dtype=np.float64)
            db = np.asarray(noise.psd_db, dtype=np.float64)
            keep = f > 0
            if is_current:
                nyquist = entry.result.sample_rate / 2.0
            self.chart.add_curve(
                entry_label(entry),
                f[keep],
                db[keep],
                color=entry.color,
                width=1.5 if is_current else 1.0,
                style=DASHES[entry.color_index % len(DASHES)],
                key=entry.key,
                processing=_("Welch power spectral density of the quiet segment"),
                readout=is_current,
                z=10 if is_current else 0,
            )
            finite = db[keep][np.isfinite(db[keep])]
            if finite.size:
                tops.append(float(np.max(finite)))
            if is_current:
                for hum in noise.hum:
                    if not hum.detected:
                        continue
                    xs = [freq for freq, _p in hum.harmonics]
                    ys = [float(db[int(np.argmin(np.abs(f - freq)))]) for freq in xs]
                    tips = [
                        _("{freq:.0f} Hz, {prominence:.0f} dB above its surroundings").format(
                            freq=freq, prominence=prominence
                        )
                        for freq, prominence in hum.harmonics
                    ]
                    self.chart.add_markers(xs, ys, color=t["warn"], symbol="t", tips=tips)
                    notes.append(
                        _("Hum at {base:g} Hz: {count} harmonics marked.").format(
                            base=hum.base_hz, count=len(xs)
                        )
                    )
                if noise.rms_dbfs is not None:
                    self.chart.set_title(
                        _("Background noise: {rms:.1f} dBFS RMS ({segment}), uncalibrated").format(
                            rms=noise.rms_dbfs, segment=noise_segment_text(noise.segment_source)
                        )
                    )
        if not tops:
            self.chart.set_title(_("Background noise"))
        top = max(tops) if tops else 0.0
        self.chart.set_default_range((10.0, nyquist), (top - 80.0, top + 10.0))
        self.notes.setText("  ".join(notes))

    def restyle(self) -> None:
        self.chart.restyle()
        self.refresh()
