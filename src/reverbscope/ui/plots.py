"""Matplotlib plots of an :class:`AnalysisResult`.

Every axis is labelled with its unit; nothing is normalised in a way that
hides the measurement scale. Functions draw into a :class:`~matplotlib.figure.Figure`
so they work in the Qt canvas and in scripts alike.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import mpl_toolkits.mplot3d  # noqa: F401  registers the 3d projection
import numpy as np
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle

from reverbscope.core.reflections import reflection_envelope_db
from reverbscope.i18n import _
from reverbscope.interpretation.profiles import band_text, confidence_text, noise_segment_text
from reverbscope.labels import validity_word
from reverbscope.models.comparison import FrequencyResponseDelta
from reverbscope.models.result import AnalysisResult, EnergyMetric, PlacementResult, Validity
from reverbscope.ui.theme import PLOT_SERIES, ensure_plot_fonts, plot_colors, style_figure, tokens

_EPS = 1e-300

# Dash patterns so a plot is readable when colour is not (ARCHITECTURE_V1 §5.8):
# one per octave band, none solid like Broadband. The palette has six colours,
# so with the eight default bands the dashes are what tells repeats apart.
_BAND_DASHES = (
    (0, (5, 2)),
    (0, (1, 1.5)),
    (0, (6, 2, 1.5, 2)),
    (0, (3, 1, 1, 1, 1, 1)),
    (0, (9, 3)),
    (0, (2, 3)),
    (0, (8, 2, 1.5, 2, 1.5, 2)),
    (0, (4, 4)),
    (0, (1, 3)),
    (0, (12, 2, 3, 2)),
)


def plot_impulse_response(fig: Figure, result: AnalysisResult) -> None:
    fig.clear()
    ensure_plot_fonts()
    ir = result.impulse_response
    sr = ir.sample_rate
    t_ms = (np.arange(ir.samples.shape[0]) - ir.direct_sound_index) * 1000.0 / sr
    ax1 = fig.add_subplot(2, 1, 1)
    n_zoom = min(ir.samples.shape[0], int(0.1 * sr) + ir.direct_sound_index)
    ax1.plot(t_ms[:n_zoom], ir.samples[:n_zoom], linewidth=0.8)
    ax1.set_xlabel(_("Time after direct sound (ms)"))
    ax1.set_ylabel(_("Amplitude (relative)"))
    ax1.set_title(_("Impulse response, first 100 ms"))
    ax1.grid(True, alpha=0.3)
    ax2 = fig.add_subplot(2, 1, 2)
    env = reflection_envelope_db(ir.samples, sr, hold_ms=0.5)
    env = env - float(np.max(env))
    ax2.plot(t_ms / 1000.0, env, linewidth=0.8)
    ax2.set_xlabel(_("Time after direct sound (s)"))
    ax2.set_ylabel(_("Envelope (dB re direct)"))
    ax2.set_ylim(-100.0, 5.0)
    ax2.set_title(_("Energy-time curve"))
    ax2.grid(True, alpha=0.3)
    fig.tight_layout()
    style_figure(fig)


def _not_stored(fig: Figure, ax: Any, text: str) -> None:
    """Say in the middle of an empty chart why there is nothing to draw."""
    ax.text(0.5, 0.5, text, ha="center", va="center", transform=ax.transAxes)
    ax.set_axis_off()
    fig.tight_layout()
    style_figure(fig)


def plot_frequency_response(
    fig: Figure, result: AnalysisResult, *, selected_resonance: int | None = None
) -> None:
    """The smoothed and raw response; the low-frequency resonance candidates
    are marked on the curve, the selected one (an index) filled in."""
    fig.clear()
    ensure_plot_fonts()
    fr = result.frequency_response
    ax = fig.add_subplot(1, 1, 1)
    if fr.frequencies_hz.size == 0:
        # A session saved without curves (--no-curves) keeps the figures only;
        # empty axes with a legend looked like a broken measurement.
        _not_stored(fig, ax, _("No frequency response stored with this session"))
        return
    _mark_resonances(ax, result, selected_resonance)
    ax.semilogx(
        fr.frequencies_hz,
        fr.magnitude_db_raw,
        linewidth=0.5,
        alpha=0.35,
        linestyle=":",
        color=plot_colors()["muted"],
        label=_("raw"),
    )
    if fr.magnitude_db_smoothed is not None:
        ax.semilogx(
            fr.frequencies_hz,
            fr.magnitude_db_smoothed,
            linewidth=1.6,
            linestyle="-",
            color=PLOT_SERIES[0],
            label=_("1/{fraction}-octave smoothed").format(fraction=fr.smoothing_fraction),
        )
    loopback = result.impulse_response.loopback
    if (
        loopback is not None
        and loopback.interface_response_hz is not None
        and loopback.interface_response_db is not None
    ):
        ax.semilogx(
            loopback.interface_response_hz,
            loopback.interface_response_db,
            linewidth=1.0,
            alpha=0.8,
            linestyle="--",
            label=_("interface (loopback)"),
        )
    ax.set_xlim(20.0, result.sample_rate / 2.0)
    finite = fr.magnitude_db_raw[np.isfinite(fr.magnitude_db_raw)]
    if finite.shape[0]:
        top = float(np.percentile(finite, 99.5))
        ax.set_ylim(top - 60.0, top + 10.0)
    ax.set_xlabel(_("Frequency (Hz)"))
    ax.set_ylabel(_("Magnitude (dB, relative)"))
    ax.set_title(_("Frequency response ({window:.2f} s window)").format(window=fr.window_s))
    ax.grid(True, which="both", alpha=0.3)
    ax.legend(loc="lower left")
    fig.tight_layout()
    style_figure(fig)


def _mark_resonances(ax: Any, result: AnalysisResult, selected: int | None) -> None:
    fr = result.frequency_response
    curve = (
        fr.magnitude_db_smoothed if fr.magnitude_db_smoothed is not None else fr.magnitude_db_raw
    )
    if curve is None or curve.size == 0:
        return
    colors = plot_colors()
    for index, candidate in enumerate(result.resonances.candidates):
        position = int(np.argmin(np.abs(fr.frequencies_hz - candidate.frequency_hz)))
        level = float(curve[position])
        if not np.isfinite(level):
            continue
        chosen = selected is not None and index == selected
        ax.plot(
            candidate.frequency_hz,
            level,
            "v" if candidate.decay_distinguishable else "^",
            markersize=9 if chosen else 7,
            markerfacecolor=PLOT_SERIES[1] if chosen else "none",
            markeredgecolor=PLOT_SERIES[1],
            label=_("resonance candidates") if index == 0 else None,
        )
        ax.annotate(
            f"{candidate.frequency_hz:.0f} Hz",
            (candidate.frequency_hz, level),
            xytext=(4, 6),
            textcoords="offset points",
            fontsize="x-small",
            color=colors["fg"],
        )


def plot_decay(fig: Figure, result: AnalysisResult, *, highlight: int | None = None) -> None:
    fig.clear()
    ensure_plot_fonts()
    ax = fig.add_subplot(1, 1, 1)
    bb = result.decay.broadband
    if all(curve.edc_db.size == 0 for curve in (bb, *result.decay.bands)):
        # As for the frequency response: the RT60s are in the decay table.
        _not_stored(fig, ax, _("No decay curves stored with this session"))
        return
    # ``highlight`` is a row of the decay table: 0 is broadband, then the bands.
    ax.plot(
        bb.edc_time_s,
        bb.edc_db,
        linewidth=3.2 if highlight == 0 else 2.4,
        linestyle="-",
        alpha=1.0 if highlight in (None, 0) else 0.45,
        label=_("Broadband"),
    )
    for index, band in enumerate(result.decay.bands):
        rt = band.rt60_estimate_s
        # Without an RT60 say why (outside the sweep, unreliable, ...), as the
        # table does, rather than always "insufficient range".
        label = band.band_label + (
            f"  RT60~{rt:.2f} s" if rt is not None else f"  ({validity_word(band.t30.validity)})"
        )
        chosen = highlight == index + 1
        ax.plot(
            band.edc_time_s,
            band.edc_db,
            linewidth=2.0 if chosen else 0.9,
            alpha=1.0 if chosen or highlight is None else 0.35,
            linestyle=_BAND_DASHES[index % len(_BAND_DASHES)],
            label=label,
        )
    ax.set_ylim(-70.0, 5.0)
    ax.set_xlabel(_("Time (s)"))
    ax.set_ylabel(_("Schroeder decay (dB)"))
    ax.set_title(_("Energy decay curves (Lundeby-truncated)"))
    ax.grid(True, alpha=0.3)
    ax.legend(loc="upper right", fontsize="small")
    fig.tight_layout()
    style_figure(fig)


def plot_noise(fig: Figure, result: AnalysisResult) -> None:
    fig.clear()
    ensure_plot_fonts()
    noise = result.noise
    ax = fig.add_subplot(1, 1, 1)
    if noise.psd_frequencies_hz is None or noise.psd_db is None:
        _not_stored(
            fig,
            ax,
            # A session saved without curves has a level but no spectrum.
            _("No quiet segment available")
            if noise.rms_dbfs is None
            else _("No noise spectrum stored with this session"),
        )
        return
    f = noise.psd_frequencies_hz
    mask = f > 0
    ax.semilogx(f[mask], noise.psd_db[mask], linewidth=0.7)
    for hum in noise.hum:
        if hum.detected:
            for freq, prominence in hum.harmonics:
                idx = int(np.argmin(np.abs(f - freq)))
                ax.plot(freq, noise.psd_db[idx], "v", markerfacecolor="none")
                ax.annotate(
                    f"{freq:.0f} Hz +{prominence:.0f} dB",
                    (freq, noise.psd_db[idx]),
                    fontsize="x-small",
                )
    ax.set_xlim(10.0, result.sample_rate / 2.0)
    ax.set_xlabel(_("Frequency (Hz)"))
    ax.set_ylabel(_("PSD (dB re FS^2/Hz)"))
    ax.set_title(
        _("Background noise: {rms:.1f} dBFS RMS ({segment}), uncalibrated").format(
            rms=noise.rms_dbfs, segment=noise_segment_text(noise.segment_source)
        )
    )
    ax.grid(True, which="both", alpha=0.3)
    fig.tight_layout()
    style_figure(fig)


def plot_reflections(fig: Figure, result: AnalysisResult) -> None:
    fig.clear()
    ensure_plot_fonts()
    ir = result.impulse_response
    sr = ir.sample_rate
    refl = result.reflections
    ax = fig.add_subplot(1, 1, 1)
    env = reflection_envelope_db(ir.samples, sr, hold_ms=0.1)
    half = max(1, round(0.5e-3 * sr))
    lo = max(0, ir.direct_sound_index - half)
    hi = min(env.shape[0], ir.direct_sound_index + half + 1)
    env = env - float(np.max(env[lo:hi]))
    start = max(0, ir.direct_sound_index - round(2e-3 * sr))
    stop = min(env.shape[0], ir.direct_sound_index + round(refl.window_ms[1] * sr / 1000.0) + 1)
    t_ms = (np.arange(start, stop) - ir.direct_sound_index) * 1000.0 / sr
    ax.plot(t_ms, env[start:stop], linewidth=0.8, label=_("envelope"))
    if refl.reflections:
        ax.plot(
            [r.delay_ms for r in refl.reflections],
            [r.relative_db for r in refl.reflections],
            "o",
            markerfacecolor="none",
            label=_("candidate reflections"),
        )
    ax.axhline(refl.threshold_db, color="gray", linestyle="--", linewidth=0.8, label=_("threshold"))
    ax.set_ylim(-60.0, 5.0)
    ax.set_xlabel(_("Time after direct sound (ms)"))
    ax.set_ylabel(_("Level re direct sound (dB)"))
    ax.set_title(
        _("Early reflections (direct-sound confidence: {confidence})").format(
            confidence=confidence_text(refl.direct_sound_confidence)
        )
    )
    ax.grid(True, alpha=0.3)
    ax.legend(loc="upper right")
    fig.tight_layout()
    style_figure(fig)


#: Shown when the user has not entered a tape measure. Not a result.
_EXAMPLE_DISTANCE_M = 2.0
_EXAMPLE_HEIGHT_M = 1.2

#: Line styles that say where a length comes from, so the picture reads in
#: greyscale: measured by the user (solid), derived by the model (dashed),
#: an example with no measurement behind it (dotted).
STYLE_MEASURED: dict[str, Any] = {"linestyle": "-", "linewidth": 2.0}
STYLE_DERIVED: dict[str, Any] = {"linestyle": "--", "linewidth": 1.6}
STYLE_EXAMPLE: dict[str, Any] = {"linestyle": ":", "linewidth": 1.4}


@dataclass(frozen=True)
class SideView:
    """What the side-view picture draws: each length with its provenance.

    ``None`` means not known; the picture then says so rather than drawing
    a number. ``example`` marks lengths that stand in for a missing input.
    """

    mic_height_m: float | None
    mic_height_example: bool
    distance_m: float | None
    distance_example: bool
    source_height_m: float | None
    source_height_sigma_m: float | None = None
    source_alternatives_m: tuple[float, ...] = ()
    horizontal_m: float | None = None
    horizontal_sigma_m: float | None = None
    ceiling_m: float | None = None
    ceiling_sigma_m: float | None = None
    ceiling_alternatives_m: tuple[float, ...] = ()
    #: The side is an example picture: nothing was solved.
    illustrative: bool = True


def side_view_from_inputs(distance_m: float | None, mic_height_m: float | None) -> SideView:
    """The picture for the inputs form: what was typed, examples for the rest."""
    return SideView(
        mic_height_m=mic_height_m if mic_height_m is not None else _EXAMPLE_HEIGHT_M,
        mic_height_example=mic_height_m is None,
        distance_m=distance_m if distance_m is not None else _EXAMPLE_DISTANCE_M,
        distance_example=distance_m is None,
        source_height_m=None,
        illustrative=True,
    )


def side_view_from_placement(placement: PlacementResult) -> SideView:
    """The picture for a result: the user's inputs as measured, the model's
    lengths as derived, with their input uncertainty and every alternative."""
    source = placement.source_height_m
    horizontal = placement.horizontal_separation_m
    ceiling = placement.ceiling_height_m
    solved = (
        placement.mic_height_m is not None
        and source.validity is Validity.VALID
        and source.metres is not None
        and horizontal.validity is Validity.VALID
        and horizontal.metres is not None
    )
    return SideView(
        mic_height_m=placement.mic_height_m
        if placement.mic_height_m is not None
        else _EXAMPLE_HEIGHT_M,
        mic_height_example=placement.mic_height_m is None,
        distance_m=placement.distance_m
        if placement.distance_m is not None
        else _EXAMPLE_DISTANCE_M,
        distance_example=placement.distance_m is None,
        source_height_m=source.metres if solved else None,
        source_height_sigma_m=source.input_uncertainty_m if solved else None,
        source_alternatives_m=tuple(source.alternatives_m) if solved else (),
        horizontal_m=horizontal.metres if solved else None,
        horizontal_sigma_m=horizontal.input_uncertainty_m if solved else None,
        ceiling_m=ceiling.metres if ceiling.validity is Validity.VALID else None,
        ceiling_sigma_m=ceiling.input_uncertainty_m if ceiling.validity is Validity.VALID else None,
        ceiling_alternatives_m=tuple(ceiling.alternatives_m)
        if ceiling.validity is Validity.VALID
        else (),
        illustrative=not solved,
    )


def plot_side_view(fig: Figure, view: SideView, *, ax: Any = None) -> str:
    """A two-dimensional side view of the microphone and the loudspeaker.

    Heights are drawn above the plane the user measured the microphone
    height from. Returns the sentence that says what is measured, what is
    derived and what is only an example; no wall is ever drawn. With ``ax``
    the picture goes into that axes and the caller lays the figure out.
    """
    own_figure = ax is None
    if own_figure:
        fig.clear()
        ensure_plot_fonts()
        ax = fig.add_subplot(1, 1, 1)
    colors = plot_colors()
    accent = tokens()["accent"]
    speaker = PLOT_SERIES[1]
    mic_z = view.mic_height_m if view.mic_height_m is not None else _EXAMPLE_HEIGHT_M
    distance = view.distance_m if view.distance_m is not None else _EXAMPLE_DISTANCE_M
    if view.source_height_m is not None and view.horizontal_m is not None:
        source_z = view.source_height_m
        horizontal = view.horizontal_m
    else:
        # Nothing solved: the loudspeaker is drawn at the microphone height
        # only so the distance tape is the straight line the user measures.
        source_z = mic_z
        horizontal = distance
    top = max(mic_z, source_z, view.ceiling_m or 0.0, *view.source_alternatives_m, 1.0)
    right = max(horizontal, 1.0) * 1.25
    # The reference plane.
    ax.axhline(0.0, color=colors["muted"], linewidth=1.2)
    ax.text(-0.05 * right, 0.03, _("reference plane"), fontsize=8, color=colors["muted"])
    # Microphone stand.
    mic_style = STYLE_EXAMPLE if view.mic_height_example else STYLE_MEASURED
    ax.plot([0.0, 0.0], [0.0, mic_z], color=accent, **mic_style)
    ax.plot(0.0, mic_z, "o", color=accent, markersize=7)
    ax.annotate(
        _("Microphone") + (f"\n{mic_z:.2f} m" if not view.mic_height_example else ""),
        (0.0, mic_z),
        xytext=(-8, 6),
        textcoords="offset points",
        ha="right",
        fontsize=8,
        color=colors["fg"],
    )
    # Loudspeaker: solved (derived) or illustrative.
    source_style = STYLE_EXAMPLE if view.illustrative else STYLE_DERIVED
    ax.plot([horizontal, horizontal], [0.0, source_z], color=speaker, **source_style)
    ax.add_patch(
        Rectangle(
            (horizontal - 0.12, source_z - 0.15),
            0.24,
            0.30,
            fill=not view.illustrative,
            facecolor=speaker if not view.illustrative else "none",
            edgecolor=speaker,
            alpha=0.85,
            linestyle=source_style["linestyle"],
        )
    )
    for alternative in view.source_alternatives_m:
        ax.add_patch(
            Rectangle(
                (horizontal - 0.12, alternative - 0.15),
                0.24,
                0.30,
                fill=False,
                edgecolor=speaker,
                linestyle=":",
                alpha=0.7,
            )
        )
    speaker_text = _("Loudspeaker")
    if not view.illustrative:
        speaker_text += f"\n{source_z:.2f} m"
        if view.source_height_sigma_m is not None:
            speaker_text += f" ±{view.source_height_sigma_m:.2f}"
        if view.source_alternatives_m:
            speaker_text += "\n" + _("or {values}").format(
                values=" / ".join(f"{alt:.2f} m" for alt in view.source_alternatives_m)
            )
    else:
        speaker_text += "\n" + _("(illustrative)")
    ax.annotate(
        speaker_text,
        (horizontal, source_z),
        xytext=(10, 6),
        textcoords="offset points",
        fontsize=8,
        color=colors["fg"],
    )
    # The straight-line distance (what the user measures).
    distance_style = STYLE_EXAMPLE if view.distance_example else STYLE_MEASURED
    ax.plot([0.0, horizontal], [mic_z, source_z], color=colors["fg"], **distance_style)
    mid_x, mid_z = horizontal * 0.5, (mic_z + source_z) * 0.5
    distance_text = (
        _("distance {metres:.2f} m").format(metres=distance)
        if not view.distance_example
        else _("distance (not measured)")
    )
    ax.annotate(
        distance_text,
        (mid_x, mid_z),
        xytext=(0, 8),
        textcoords="offset points",
        ha="center",
        fontsize=8,
        color=colors["fg"],
    )
    # Horizontal separation, derived.
    if not view.illustrative and view.horizontal_m is not None:
        y = -0.12 * top
        ax.annotate(
            "",
            xy=(horizontal, y),
            xytext=(0.0, y),
            arrowprops={"arrowstyle": "<->", "color": colors["muted"], "linestyle": "--"},
        )
        text = _("horizontal {metres:.2f} m").format(metres=horizontal)
        if view.horizontal_sigma_m is not None:
            text += f" ±{view.horizontal_sigma_m:.2f}"
        ax.text(
            horizontal * 0.5,
            y - 0.04 * top,
            text,
            ha="center",
            va="top",
            fontsize=8,
            color=colors["muted"],
        )
    # The plane above the devices, derived; never a wall.
    if view.ceiling_m is not None:
        ax.plot(
            [-0.1 * right, right],
            [view.ceiling_m, view.ceiling_m],
            color=colors["muted"],
            **STYLE_DERIVED,
        )
        text = _("plane above {metres:.2f} m").format(metres=view.ceiling_m)
        if view.ceiling_sigma_m is not None:
            text += f" ±{view.ceiling_sigma_m:.2f}"
        if view.ceiling_alternatives_m:
            text += " " + _("or {values}").format(
                values=" / ".join(f"{alt:.2f} m" for alt in view.ceiling_alternatives_m)
            )
        ax.text(
            right * 0.98,
            view.ceiling_m + 0.03 * top,
            text,
            ha="right",
            fontsize=8,
            color=colors["muted"],
        )
        for alternative in view.ceiling_alternatives_m:
            ax.plot(
                [-0.1 * right, right],
                [alternative, alternative],
                color=colors["muted"],
                linestyle=":",
                linewidth=1.0,
                alpha=0.7,
            )
        top = max(top, view.ceiling_m, *view.ceiling_alternatives_m)
    # One scale for both axes without a fixed aspect (which shrinks the axes
    # box and warns): the axes box is about twice as wide as high, so the
    # horizontal span is twice the vertical one.
    height = top * 1.5
    span = max(right * 1.35, 2.0 * height)
    ax.set_xlim(-0.35 * right, -0.35 * right + span)
    # A little headroom so the loudspeaker label clears the title and legend.
    ax.set_ylim(-0.25 * top, -0.25 * top + span / 2.0 + 0.3 * top)
    ax.set_xlabel(_("horizontal (m)"))
    ax.set_ylabel(_("height above the reference plane (m)"))
    ax.grid(True, alpha=0.25)
    legend_items = [
        Line2D([0], [0], color=colors["fg"], **STYLE_MEASURED, label=_("measured (tape)")),
        Line2D([0], [0], color=colors["fg"], **STYLE_DERIVED, label=_("derived (model)")),
        Line2D([0], [0], color=colors["fg"], **STYLE_EXAMPLE, label=_("example only")),
    ]
    ax.legend(handles=legend_items, loc="upper right", fontsize="x-small")
    ax.set_title(_("Side view: no wall or room shape is drawn"), fontsize=10)
    if own_figure:
        fig.tight_layout()
        style_figure(fig)
    return side_view_hint(view)


def side_view_hint(view: SideView) -> str:
    """The sentence under a side view: what is measured, derived, or an example."""
    if not view.illustrative:
        return _(
            "Solid lines are what you measured; dashed lines are what the reflections and "
            "your two tape measures allow. ± is the input uncertainty only, not the model "
            "error. Every alternative is drawn: ReverbScope does not pick one."
        )
    if not view.distance_example and not view.mic_height_example:
        return _(
            "The line is the loudspeaker distance you entered, and the stand is the "
            "microphone height you entered. The loudspeaker is drawn at that same height "
            "only so the tape can be seen; its real height comes from a measurement. "
            "No room and no wall are drawn."
        )
    if not view.distance_example:
        return _(
            "The line is the loudspeaker distance you entered. Both heights in this "
            "picture are an example. No room and no wall are drawn."
        )
    return _(
        "Nothing has been entered. This picture shows where the two tape measures go. "
        "It is not your room, and no wall is drawn."
    )


def plot_placement_illustration(
    fig: Figure, *, distance_m: float | None, mic_height_m: float | None
) -> str:
    """The inputs picture: a side view of the two tape measures. Not a result."""
    return plot_side_view(fig, side_view_from_inputs(distance_m, mic_height_m))


def plot_placement_result(fig: Figure, placement: PlacementResult | None) -> str:
    """The side view of a result, or the tape-measure picture when nothing was solved."""
    if placement is None:
        return plot_placement_illustration(fig, distance_m=None, mic_height_m=None)
    return plot_side_view(fig, side_view_from_placement(placement))


def plot_reflection_timeline(
    fig: Figure,
    result: AnalysisResult,
    *,
    selected: int | None = None,
    candidate_index: int | None = None,
    ax: Any = None,
) -> None:
    """Direct sound, every early-reflection candidate, the threshold and the
    analysed window on one time axis; the selected candidate is filled.

    ``selected`` is an index into ``result.reflections.reflections``;
    ``candidate_index`` one into ``result.placement.candidates`` (the same
    arrivals, re-expressed as geometry), whichever the caller has. With
    ``ax`` the timeline goes into that axes.
    """
    own_figure = ax is None
    if own_figure:
        fig.clear()
        ensure_plot_fonts()
        ax = fig.add_subplot(1, 1, 1)
    colors = plot_colors()
    refl = result.reflections
    placement = result.placement
    window = refl.analysed_window_ms or refl.window_ms
    ax.axvspan(window[0], window[1], color=colors["grid"], alpha=0.35, label=_("analysed window"))
    if refl.window_truncated and refl.analysed_window_ms is not None:
        ax.axvspan(
            refl.analysed_window_ms[1],
            refl.window_ms[1],
            color=colors["muted"],
            alpha=0.12,
            hatch="//",
            label=_("not searched (response ended)"),
        )
    ax.axhline(refl.threshold_db, color="gray", linestyle="--", linewidth=0.8, label=_("threshold"))
    ax.stem([0.0], [0.0], linefmt=colors["fg"], markerfmt="D", basefmt=" ", label=_("direct sound"))
    if selected is None and candidate_index is not None:
        selected = candidate_index
    for index, reflection in enumerate(refl.reflections):
        chosen = selected is not None and index == selected
        colour = PLOT_SERIES[0]
        marker = "o"
        if placement is not None and index < len(placement.candidates):
            candidate = placement.candidates[index]
            if candidate.interpretable_as_plane is False:
                colour = colors["muted"]
                marker = "x"
            elif candidate.surface is not None:
                colour = PLOT_SERIES[1] if candidate.surface == "upper_plane" else PLOT_SERIES[3]
        ax.plot(
            [reflection.delay_ms, reflection.delay_ms],
            [-80.0, reflection.relative_db],
            color=colour,
            linewidth=2.2 if chosen else 1.0,
            alpha=1.0 if chosen or selected is None else 0.5,
        )
        ax.plot(
            reflection.delay_ms,
            reflection.relative_db,
            marker,
            color=colour,
            markersize=9 if chosen else 6,
            markerfacecolor=colour if chosen else "none",
        )
        ax.annotate(
            f"{reflection.delay_ms:.1f} ms / {reflection.relative_db:.1f} dB",
            (reflection.delay_ms, reflection.relative_db),
            xytext=(4, 4),
            textcoords="offset points",
            fontsize="x-small",
            color=colors["fg"],
        )
    ax.set_ylim(-60.0, 5.0)
    ax.set_xlim(-1.0, window[1] * 1.05)
    ax.set_xlabel(_("Time after direct sound (ms)"))
    ax.set_ylabel(_("Level re direct sound (dB)"))
    ax.set_title(
        _("Reflection timeline (direct-sound confidence: {confidence})").format(
            confidence=confidence_text(refl.direct_sound_confidence)
        ),
        fontsize=10,
    )
    ax.grid(True, alpha=0.3)
    handles = [
        Line2D(
            [0],
            [0],
            color=PLOT_SERIES[0],
            marker="o",
            markerfacecolor="none",
            linestyle="",
            label=_("candidate"),
        ),
        Line2D(
            [0],
            [0],
            color=PLOT_SERIES[3],
            marker="o",
            markerfacecolor="none",
            linestyle="",
            label=_("attributed: reference plane"),
        ),
        Line2D(
            [0],
            [0],
            color=PLOT_SERIES[1],
            marker="o",
            markerfacecolor="none",
            linestyle="",
            label=_("attributed: plane above"),
        ),
        Line2D(
            [0],
            [0],
            color=colors["muted"],
            marker="x",
            linestyle="",
            label=_("not a plane reflection"),
        ),
    ]
    ax.legend(handles=handles, loc="lower right", fontsize="x-small", ncol=2)
    if own_figure:
        fig.tight_layout()
        style_figure(fig)


def plot_placement_overview(
    fig: Figure, result: AnalysisResult, *, candidate_index: int | None = None
) -> str:
    """The side view above the reflection timeline: the default placement
    picture. Returns the side view's sentence."""
    fig.clear()
    ensure_plot_fonts()
    side_ax, time_ax = fig.subplots(2, 1, gridspec_kw={"height_ratios": [0.85, 1.15]})
    placement = result.placement
    view = (
        side_view_from_placement(placement)
        if placement is not None
        else side_view_from_inputs(None, None)
    )
    hint = plot_side_view(fig, view, ax=side_ax)
    plot_reflection_timeline(fig, result, candidate_index=candidate_index, ax=time_ax)
    fig.tight_layout()
    style_figure(fig)
    return hint


def plot_placement_3d(fig: Figure, placement: PlacementResult | None) -> str:
    """The auxiliary three-dimensional view: only what the model solved.

    A single microphone does not decide which way the loudspeaker sits. When
    the horizontal separation and the loudspeaker height are both valid, every
    position on the ring is equally consistent with the measurement; one
    cabinet is drawn so the direct path can be seen, and said to be illustrative.
    """
    if placement is None or not _placement_axis_known(placement):
        _draw_placement(
            fig,
            mic_z=placement.mic_height_m
            if placement is not None and placement.mic_height_m is not None
            else _EXAMPLE_HEIGHT_M,
            source_z=placement.mic_height_m
            if placement is not None and placement.mic_height_m is not None
            else _EXAMPLE_HEIGHT_M,
            horizontal_m=placement.distance_m
            if placement is not None and placement.distance_m is not None
            else _EXAMPLE_DISTANCE_M,
            ceiling_z=None,
            ring=False,
            title=_("Placement picture (nothing solved). Drag to rotate."),
        )
        return _(
            "The vertical axis was not solved, so this is the tape-measure picture: "
            "the loudspeaker position is an example. No room and no wall are drawn."
        )
    source = placement.source_height_m.metres
    horizontal = placement.horizontal_separation_m.metres
    mic = placement.mic_height_m
    assert source is not None and horizontal is not None and mic is not None
    ceiling = placement.ceiling_height_m.metres
    if placement.ceiling_height_m.validity is not Validity.VALID:
        ceiling = None
    _draw_placement(
        fig,
        mic_z=mic,
        source_z=source,
        horizontal_m=horizontal,
        ceiling_z=ceiling,
        ring=True,
        title=_("Measured geometry. Drag to rotate."),
    )
    return _(
        "The ring is every loudspeaker position this measurement allows. The cabinet "
        "is one of them, drawn so the direct path can be seen. No wall is drawn."
    )


def plot_frequency_overlay(
    fig: Figure,
    baseline: AnalysisResult,
    candidate: AnalysisResult,
    delta: FrequencyResponseDelta | None,
    *,
    view: str = "both",
) -> None:
    """Baseline and candidate on one dB axis (no normalisation of either),
    and the difference under them; ``view`` is ``baseline``, ``candidate``,
    ``both`` or ``difference``."""
    fig.clear()
    ensure_plot_fonts()
    colors = plot_colors()
    curves = [
        (_("baseline"), baseline, PLOT_SERIES[0], "-"),
        (_("candidate"), candidate, PLOT_SERIES[1], "--"),
    ]
    if view == "baseline":
        curves = curves[:1]
    elif view == "candidate":
        curves = curves[1:]
    if view == "difference":
        ax_curves = None
        ax_diff = fig.add_subplot(1, 1, 1)
    else:
        ax_curves = fig.add_subplot(2, 1, 1)
        ax_diff = fig.add_subplot(2, 1, 2, sharex=ax_curves)
    finite: list[float] = []
    if ax_curves is not None:
        for name, result, colour, style in curves:
            fr = result.frequency_response
            if fr.frequencies_hz.size == 0:
                continue
            curve = (
                fr.magnitude_db_smoothed
                if fr.magnitude_db_smoothed is not None
                else fr.magnitude_db_raw
            )
            ax_curves.semilogx(
                fr.frequencies_hz, curve, color=colour, linestyle=style, linewidth=1.5, label=name
            )
            finite.extend(float(v) for v in curve[np.isfinite(curve)])
        if finite:
            top = float(np.percentile(finite, 99.5))
            ax_curves.set_ylim(top - 50.0, top + 8.0)
        ax_curves.set_ylabel(_("Magnitude (dB, relative)"))
        ax_curves.set_title(_("Frequency response: one scale for both takes"))
        ax_curves.grid(True, which="both", alpha=0.3)
        ax_curves.legend(loc="lower left")
        if not finite:
            ax_curves.text(
                0.5,
                0.5,
                _("No frequency response stored with this session"),
                ha="center",
                va="center",
                transform=ax_curves.transAxes,
            )
    if delta is not None and delta.frequencies_hz.size:
        ax_diff.semilogx(
            delta.frequencies_hz, delta.difference_db, color=PLOT_SERIES[2], linestyle="-"
        )
        ax_diff.axhline(0.0, color=colors["muted"], linewidth=0.8)
        ax_diff.set_ylabel("Δ dB")
        ax_diff.set_title(_("Frequency-response difference (candidate − baseline)"))
        ax_diff.grid(True, which="both", alpha=0.3)
    else:
        ax_diff.text(
            0.5,
            0.5,
            _("No difference curve"),
            ha="center",
            va="center",
            transform=ax_diff.transAxes,
        )
        ax_diff.set_axis_off()
    ax_diff.set_xlabel(_("Frequency (Hz)"))
    fig.tight_layout()
    style_figure(fig)


def plot_decay_overlay(fig: Figure, baseline: AnalysisResult, candidate: AnalysisResult) -> None:
    """The broadband decay curves of both takes on one time and dB axis."""
    fig.clear()
    ensure_plot_fonts()
    ax = fig.add_subplot(1, 1, 1)
    drawn = False
    for name, result, colour, style in (
        (_("baseline"), baseline, PLOT_SERIES[0], "-"),
        (_("candidate"), candidate, PLOT_SERIES[1], "--"),
    ):
        bb = result.decay.broadband
        if bb.edc_db.size == 0:
            continue
        drawn = True
        rt = bb.rt60_estimate_s
        label = name + (f"  RT60~{rt:.2f} s" if rt is not None else "")
        ax.plot(bb.edc_time_s, bb.edc_db, color=colour, linestyle=style, linewidth=1.8, label=label)
    if not drawn:
        _not_stored(fig, ax, _("No decay curves stored with this session"))
        return
    ax.set_ylim(-70.0, 5.0)
    ax.set_xlabel(_("Time (s)"))
    ax.set_ylabel(_("Schroeder decay (dB)"))
    ax.set_title(_("Broadband decay: baseline and candidate"))
    ax.grid(True, alpha=0.3)
    ax.legend(loc="upper right")
    fig.tight_layout()
    style_figure(fig)


def _placement_axis_known(placement: PlacementResult) -> bool:
    return (
        placement.mic_height_m is not None
        and placement.source_height_m.validity is Validity.VALID
        and placement.source_height_m.metres is not None
        and placement.horizontal_separation_m.validity is Validity.VALID
        and placement.horizontal_separation_m.metres is not None
        and placement.horizontal_separation_m.metres > 0.05
    )


def _draw_placement(
    fig: Figure,
    *,
    mic_z: float,
    source_z: float,
    horizontal_m: float,
    ceiling_z: float | None,
    ring: bool,
    title: str,
) -> None:
    fig.clear()
    ensure_plot_fonts()
    ax: Any = fig.add_subplot(111, projection="3d")
    colors = plot_colors()
    accent = tokens()["accent"]
    speaker = PLOT_SERIES[1]
    radius = max(horizontal_m, mic_z, source_z, 0.8) * 1.35
    _disc(ax, radius, 0.0, colors["muted"], 0.28)
    ax.plot(
        radius * np.cos(np.linspace(0, 2 * np.pi, 80)),
        radius * np.sin(np.linspace(0, 2 * np.pi, 80)),
        np.zeros(80),
        color=colors["muted"],
        linewidth=0.8,
    )
    ax.text(radius * 0.15, -radius * 0.62, 0.02, _("reference plane"), fontsize=8)
    top = max(mic_z, source_z, ceiling_z or 0.0, 1.0)
    if ceiling_z is not None and ceiling_z > top * 0.5:
        _disc(ax, radius, ceiling_z, colors["grid"], 0.18)
        ax.text(0.0, 0.0, ceiling_z, _("Plane above the devices"), fontsize=8)
        top = max(top, ceiling_z)
    angle = 0.6 if ring else 0.0
    sx = horizontal_m * float(np.cos(angle))
    sy = horizontal_m * float(np.sin(angle))
    if ring:
        theta = np.linspace(0, 2 * np.pi, 160)
        ax.plot(
            horizontal_m * np.cos(theta),
            horizontal_m * np.sin(theta),
            np.full_like(theta, source_z),
            color=accent,
            linestyle="--",
            linewidth=1.3,
        )
        ax.text(
            -horizontal_m * 0.95,
            horizontal_m * 0.2,
            source_z + 0.1,
            _("possible positions"),
            fontsize=8,
        )
    ax.plot([0.0, 0.0], [0.0, 0.0], [0.0, mic_z], color=accent, linewidth=2.2)
    ax.plot([0.0, 0.0], [0.0, 0.0], [mic_z, mic_z + 0.05], color=accent, linewidth=4.0)
    ax.text(-0.42, 0.02, mic_z, _("Microphone"), fontsize=8)
    ax.plot([sx, sx], [sy, sy], [0.0, source_z], color=speaker, linewidth=0.8, linestyle=":")
    _wire_box(ax, sx, sy, source_z, 0.28, 0.22, 0.36, speaker)
    ax.text(sx + 0.22, sy + 0.12, source_z + 0.24, _("Loudspeaker"), fontsize=8)
    ax.plot([0.0, sx], [0.0, sy], [mic_z, source_z], color=colors["fg"], linewidth=1.4)
    mid_z = (mic_z + source_z) * 0.5 + 0.16
    ax.text(sx * 0.42, sy * 0.42, mid_z, _("Direct sound"), fontsize=8)
    scale = 1.0 if radius >= 1.4 else 0.5
    edge = -radius * 0.72
    ax.plot([edge, edge + scale], [edge, edge], [0.0, 0.0], color=colors["fg"], linewidth=2.0)
    ax.text(edge + scale * 0.5, edge, 0.05, f"{scale:g} m", fontsize=8)
    zlim = top * 1.15
    ax.set_xlim(-radius, radius)
    ax.set_ylim(-radius, radius)
    ax.set_zlim(0.0, zlim)
    ax.set_box_aspect((radius * 2.0, radius * 2.0, zlim))
    ax.view_init(elev=24, azim=-58)
    ax.set_title(title)
    fig.subplots_adjust(left=0.0, right=1.0, bottom=0.0, top=0.9)
    style_figure(fig)
    ax.set_axis_off()


def _disc(ax: Any, radius: float, z: float, color: str, alpha: float) -> None:
    theta = np.linspace(0, 2 * np.pi, 36)
    rad = np.linspace(0, radius, 5)
    r, t = np.meshgrid(rad, theta)
    ax.plot_surface(
        r * np.cos(t),
        r * np.sin(t),
        np.full_like(r, z),
        color=color,
        alpha=alpha,
        linewidth=0,
        antialiased=False,
        shade=False,
    )


def _wire_box(
    ax: Any, cx: float, cy: float, cz: float, sx: float, sy: float, sz: float, color: str
) -> None:
    x0, x1 = cx - sx / 2.0, cx + sx / 2.0
    y0, y1 = cy - sy / 2.0, cy + sy / 2.0
    z0, z1 = cz - sz / 2.0, cz + sz / 2.0
    corners = [
        (x0, y0, z0),
        (x1, y0, z0),
        (x1, y1, z0),
        (x0, y1, z0),
        (x0, y0, z1),
        (x1, y0, z1),
        (x1, y1, z1),
        (x0, y1, z1),
    ]
    for i, j in (
        (0, 1),
        (1, 2),
        (2, 3),
        (3, 0),
        (4, 5),
        (5, 6),
        (6, 7),
        (7, 4),
        (0, 4),
        (1, 5),
        (2, 6),
        (3, 7),
    ):
        a, b = corners[i], corners[j]
        ax.plot([a[0], b[0]], [a[1], b[1]], [a[2], b[2]], color=color, linewidth=1.2)


def decay_table_rows(result: AnalysisResult) -> list[tuple[str, str, str, str, str]]:
    """Rows (band, EDT, T20, T30, RT60 estimate) for a table widget."""

    def fmt(metric_seconds: float | None, validity: Validity) -> str:
        if validity is Validity.VALID and metric_seconds is not None:
            return f"{metric_seconds:.2f} s"
        if validity is Validity.UNRELIABLE and metric_seconds is not None:
            return f"({metric_seconds:.2f} s)"
        if validity is Validity.INSUFFICIENT_RANGE:
            return _("insufficient range")
        return _("n/a")

    rows: list[tuple[str, str, str, str, str]] = []
    for band in (result.decay.broadband, *result.decay.bands):
        rt = (
            f"{band.rt60_estimate_s:.2f} s ({band.rt60_basis})"
            if band.rt60_estimate_s is not None
            else "-"
        )
        rows.append(
            (
                band_text(band.band_label),
                fmt(band.edt.seconds, band.edt.validity),
                fmt(band.t20.seconds, band.t20.validity),
                fmt(band.t30.seconds, band.t30.validity),
                rt,
            )
        )
    return rows


def energy_table_rows(result: AnalysisResult) -> list[tuple[str, str, str, str, str]]:
    """Rows (band, C50, C80, D50, centre time). Ratios, not a room score."""

    def fmt(metric: EnergyMetric) -> str:
        if metric.value is None:
            if metric.validity is Validity.INSUFFICIENT_RANGE:
                return _("insufficient range")
            return _("n/a")
        if metric.unit == "dB":
            text = f"{metric.value:+.1f} dB"
        elif metric.unit == "%":
            text = f"{metric.value:.0f} %"
        else:
            text = f"{metric.value * 1000:.0f} ms"
        if metric.validity is Validity.VALID:
            return text
        if metric.validity is Validity.UNRELIABLE:
            return f"({text})"
        if metric.validity is Validity.INSUFFICIENT_RANGE:
            return _("insufficient range")
        return _("n/a")

    rows: list[tuple[str, str, str, str, str]] = []
    for band in (result.decay.broadband, *result.decay.bands):
        rows.append(
            (
                band_text(band.band_label),
                fmt(band.c50),
                fmt(band.c80),
                fmt(band.d50),
                fmt(band.centre_time),
            )
        )
    return rows
