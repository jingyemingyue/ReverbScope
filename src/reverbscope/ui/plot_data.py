"""Adapters from a measurement's result to the curves a chart draws.

Pure functions, no Qt: a :class:`~reverbscope.ui.document.Measurement`
in, :class:`Curve` objects out, each carrying the measurement's colour and
line style so the same measurement looks the same in every chart. Nothing
here computes a metric: the curves are read from the
:class:`~reverbscope.models.result.AnalysisResult` as they were stored, and
the RT60 in a decay label is the result's own estimate.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from reverbscope.i18n import _
from reverbscope.interpretation.profiles import band_text
from reverbscope.labels import validity_word
from reverbscope.models.result import FloatArray
from reverbscope.ui.document import Measurement
from reverbscope.ui.plots import _BAND_DASHES

#: A matplotlib line style: a named style (``"-"``, ``"--"``) or a dash
#: pattern ``(offset, (on, off, ...))`` such as :data:`_BAND_DASHES` holds.
LineStyle = str | tuple[float, tuple[float, ...]]

#: Axis keys. Panels whose kind shares an axis key may link their x limits;
#: a frequency axis is never linked to a time axis, and seconds never to
#: milliseconds (same quantity, another unit: the numbers would not match).
AXIS_FREQUENCY = "frequency_hz"
AXIS_TIME_S = "time_s"
AXIS_TIME_MS = "time_ms"
AXIS_NONE = "none"


@dataclass(frozen=True)
class Curve:
    """One line of a chart: ``x`` against ``y`` for one measurement.

    ``emphasis`` marks the curve the inspector asked to highlight (a decay
    band); ``secondary`` marks a supporting curve drawn thin and faint (the
    raw frequency response under the smoothed one). ``item`` names what a
    click on the curve selects, e.g. ``("band", 2)``.
    """

    x: FloatArray
    y: FloatArray
    label: str
    measurement_id: str
    colour: str
    style: LineStyle
    emphasis: bool = False
    secondary: bool = False
    item: tuple[str, int] | None = None


@dataclass(frozen=True)
class PlotKind:
    """A chart the panel can show.

    ``multi`` kinds overlay every visible measurement; the others draw the
    selected one only. ``log_x`` says the x axis is logarithmic (kept so when
    the user zooms). ``difference`` says the kind can draw candidate minus
    baseline.
    """

    key: str
    axis: str
    title: Callable[[], str]
    multi: bool
    log_x: bool = False
    difference: bool = False


PLOT_KINDS: tuple[PlotKind, ...] = (
    PlotKind(
        "frequency",
        AXIS_FREQUENCY,
        lambda: _("Frequency response"),
        multi=True,
        log_x=True,
        difference=True,
    ),
    PlotKind("decay", AXIS_TIME_S, lambda: _("Decay"), multi=True, difference=True),
    PlotKind("noise", AXIS_FREQUENCY, lambda: _("Noise"), multi=True, log_x=True),
    PlotKind("impulse", AXIS_NONE, lambda: _("Impulse response"), multi=False),
    PlotKind("reflections", AXIS_TIME_MS, lambda: _("Early reflections"), multi=False),
    PlotKind("placement", AXIS_NONE, lambda: _("Placement geometry"), multi=False),
)

_KINDS_BY_KEY = {kind.key: kind for kind in PLOT_KINDS}


def plot_kind(key: str) -> PlotKind:
    """The kind with ``key``; a ``KeyError`` names an unknown one."""
    return _KINDS_BY_KEY[key]


def _finite(values: FloatArray) -> bool:
    return bool(values.size) and bool(np.isfinite(values).any())


def frequency_curves(measurement: Measurement, *, raw: bool) -> list[Curve]:
    """The smoothed magnitude (the raw one when nothing was smoothed), and
    with ``raw`` the raw one under it. Empty for a session saved without
    curves."""
    fr = measurement.result.frequency_response
    if fr.frequencies_hz.size == 0:
        return []
    name = measurement.name()
    curves: list[Curve] = []
    smoothed = fr.magnitude_db_smoothed
    if smoothed is not None and _finite(smoothed):
        curves.append(
            Curve(
                x=fr.frequencies_hz,
                y=smoothed,
                label=name,
                measurement_id=measurement.id,
                colour=measurement.colour,
                style=measurement.style,
            )
        )
        if raw and _finite(fr.magnitude_db_raw):
            curves.append(
                Curve(
                    x=fr.frequencies_hz,
                    y=fr.magnitude_db_raw,
                    label=_("{name} (raw)").format(name=name),
                    measurement_id=measurement.id,
                    colour=measurement.colour,
                    style=":",
                    secondary=True,
                )
            )
    elif _finite(fr.magnitude_db_raw):
        curves.append(
            Curve(
                x=fr.frequencies_hz,
                y=fr.magnitude_db_raw,
                label=name,
                measurement_id=measurement.id,
                colour=measurement.colour,
                style=measurement.style,
            )
        )
    return curves


def decay_label(name: str, band_label: str, rt60_s: float | None, validity_word_: str) -> str:
    """``name`` with the band and its RT60 estimate, or why there is none."""
    band = band_text(band_label)
    if rt60_s is not None:
        return _("{name}, {band}, RT60~{rt60:.2f} s").format(name=name, band=band, rt60=rt60_s)
    return _("{name}, {band} ({validity})").format(name=name, band=band, validity=validity_word_)


def decay_curves(measurement: Measurement, *, bands: bool) -> list[Curve]:
    """The broadband Schroeder decay (item ``("band", 0)``) and, with
    ``bands``, each octave band dashed as :data:`_BAND_DASHES` does (item
    ``("band", i + 1)``). A band keeps its dash pattern even for a
    measurement drawn dashed: the colour says which measurement it is."""
    decay = measurement.result.decay
    name = measurement.name()
    curves: list[Curve] = []
    bb = decay.broadband
    if bb.edc_db.size:
        curves.append(
            Curve(
                x=bb.edc_time_s,
                y=bb.edc_db,
                label=name
                if bb.rt60_estimate_s is None
                else _("{name}, RT60~{rt60:.2f} s").format(name=name, rt60=bb.rt60_estimate_s),
                measurement_id=measurement.id,
                colour=measurement.colour,
                style=measurement.style,
                item=("band", 0),
            )
        )
    if not bands:
        return curves
    for index, band in enumerate(decay.bands):
        if band.edc_db.size == 0:
            continue
        curves.append(
            Curve(
                x=band.edc_time_s,
                y=band.edc_db,
                label=decay_label(
                    name, band.band_label, band.rt60_estimate_s, validity_word(band.t30.validity)
                ),
                measurement_id=measurement.id,
                colour=measurement.colour,
                style=_BAND_DASHES[index % len(_BAND_DASHES)],
                secondary=True,
                item=("band", index + 1),
            )
        )
    return curves


def noise_curve(measurement: Measurement) -> Curve | None:
    """The noise power spectral density, or ``None`` when no quiet segment
    was found or the spectrum was not stored."""
    noise = measurement.result.noise
    if noise.psd_frequencies_hz is None or noise.psd_db is None:
        return None
    mask = noise.psd_frequencies_hz > 0
    if not mask.any():
        return None
    name = measurement.name()
    label = (
        name
        if noise.rms_dbfs is None
        else _("{name}, {rms:.1f} dBFS RMS").format(name=name, rms=noise.rms_dbfs)
    )
    return Curve(
        x=noise.psd_frequencies_hz[mask],
        y=noise.psd_db[mask],
        label=label,
        measurement_id=measurement.id,
        colour=measurement.colour,
        style=measurement.style,
    )


__all__ = [
    "AXIS_FREQUENCY",
    "AXIS_NONE",
    "AXIS_TIME_MS",
    "AXIS_TIME_S",
    "PLOT_KINDS",
    "Curve",
    "LineStyle",
    "PlotKind",
    "decay_curves",
    "frequency_curves",
    "noise_curve",
    "plot_kind",
]
