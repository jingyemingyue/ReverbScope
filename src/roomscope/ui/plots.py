"""Matplotlib plots of an :class:`AnalysisResult`.

Every axis is labelled with its unit; nothing is normalised in a way that
hides the measurement scale. Functions draw into a :class:`~matplotlib.figure.Figure`
so they work in the Qt canvas and in scripts alike.
"""

from __future__ import annotations

from typing import Any

import mpl_toolkits.mplot3d  # noqa: F401  registers the 3d projection
import numpy as np
from matplotlib.figure import Figure

from roomscope.core.placement import horizontal_plane_image_path
from roomscope.core.reflections import reflection_envelope_db
from roomscope.i18n import _
from roomscope.interpretation.profiles import band_text, confidence_text, noise_segment_text
from roomscope.models.result import (
    AnalysisResult,
    EnergyMetric,
    PlacementResult,
    RoomScan,
    Validity,
)
from roomscope.ui.theme import PLOT_SERIES, ensure_plot_fonts, plot_colors, style_figure, tokens

_EPS = 1e-300

# Linestyles so a plot is readable when colour is not (ARCHITECTURE_V1 §5.8).
_LINESTYLES = ("-", "--", "-.", ":", (0, (3, 1, 1, 1)))


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


def plot_frequency_response(fig: Figure, result: AnalysisResult) -> None:
    fig.clear()
    ensure_plot_fonts()
    fr = result.frequency_response
    ax = fig.add_subplot(1, 1, 1)
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


def plot_decay(fig: Figure, result: AnalysisResult) -> None:
    fig.clear()
    ensure_plot_fonts()
    ax = fig.add_subplot(1, 1, 1)
    bb = result.decay.broadband
    ax.plot(bb.edc_time_s, bb.edc_db, linewidth=2.4, linestyle="-", label=_("Broadband"))
    for index, band in enumerate(result.decay.bands):
        rt = band.rt60_estimate_s
        label = band.band_label + (
            f"  RT60~{rt:.2f} s" if rt is not None else "  ({})".format(_("insufficient range"))
        )
        ax.plot(
            band.edc_time_s,
            band.edc_db,
            linewidth=0.9,
            alpha=0.8,
            linestyle=_LINESTYLES[(index + 1) % len(_LINESTYLES)],
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
        ax.text(
            0.5,
            0.5,
            _("No quiet segment available"),
            ha="center",
            va="center",
            transform=ax.transAxes,
        )
        ax.set_axis_off()
        fig.tight_layout()
        style_figure(fig)
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


def plot_spectrum(fig: Figure, result: AnalysisResult) -> None:
    fig.clear()
    ensure_plot_fonts()
    ax = fig.add_subplot(1, 1, 1)
    spectrum = result.spectrum
    if spectrum is None or spectrum.frequencies_hz.size == 0:
        ax.text(
            0.5,
            0.5,
            _("No spectrum available"),
            ha="center",
            va="center",
            transform=ax.transAxes,
        )
        ax.set_axis_off()
        fig.tight_layout()
        style_figure(fig)
        return
    mask = spectrum.frequencies_hz > 0
    ax.semilogx(spectrum.frequencies_hz[mask], spectrum.level_db[mask], linewidth=0.8)
    if spectrum.peak_hz is not None and spectrum.peak_db is not None:
        ax.plot(spectrum.peak_hz, spectrum.peak_db, "o", markerfacecolor="none")
        ax.annotate(
            f"{spectrum.peak_hz:.0f} Hz",
            (spectrum.peak_hz, spectrum.peak_db),
            fontsize="x-small",
        )
    ax.set_xlim(10.0, result.sample_rate / 2.0)
    ax.set_xlabel(_("Frequency (Hz)"))
    ax.set_ylabel(_("PSD (dB re FS^2/Hz)"))
    ax.set_title(_("Spectrum (impulse response)"))
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


def plot_placement_illustration(
    fig: Figure,
    *,
    distance_m: float | None,
    mic_height_m: float | None,
    scan: RoomScan | None = None,
) -> str:
    """A rotatable picture of the two tape measures. Not a room, and not a result.

    The loudspeaker is drawn at the microphone height so the distance tape is
    the straight line the user is asked to measure. That height is an example
    until a measurement solves the vertical axis.
    """
    distance_entered = distance_m is not None
    height_entered = mic_height_m is not None
    distance = distance_m if distance_m is not None else _EXAMPLE_DISTANCE_M
    height = mic_height_m if mic_height_m is not None else _EXAMPLE_HEIGHT_M
    _draw_placement(
        fig,
        mic_z=height,
        source_z=height,
        horizontal_m=distance,
        ceiling_z=None,
        ring=False,
        title=_("Placement picture. Drag to rotate."),
        scan=scan,
    )
    extra = _scan_hint(scan)
    if distance_entered and height_entered:
        return (
            _(
                "The line is the loudspeaker distance you entered, and the stand is the "
                "microphone height you entered. The loudspeaker is drawn at that same height "
                "only so the tape can be seen; its real height comes from a measurement. "
                "No room and no wall are drawn."
            )
            + extra
        )
    if distance_entered:
        return (
            _(
                "The line is the loudspeaker distance you entered. Both heights in this "
                "picture are an example. No room and no wall are drawn."
            )
            + extra
        )
    return (
        _(
            "Nothing has been entered. This picture shows where the two tape measures go. "
            "It is not your room, and no wall is drawn."
        )
        + extra
    )


def plot_placement_result(
    fig: Figure, placement: PlacementResult | None, scan: RoomScan | None = None
) -> str:
    """The measured vertical axis, or the tape-measure picture when it is not known.

    A single microphone does not decide which way the loudspeaker sits. When
    the horizontal separation and the loudspeaker height are both valid, every
    position on the ring is equally consistent with the measurement; one
    cabinet is drawn so the direct path can be seen.
    """
    if placement is None or not _placement_axis_known(placement):
        return plot_placement_illustration(
            fig,
            distance_m=None if placement is None else placement.distance_m,
            mic_height_m=None if placement is None else placement.mic_height_m,
            scan=scan,
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
        scan=scan,
    )
    hint = _(
        "The ring is every loudspeaker position this measurement allows. The cabinet "
        "is one of them, drawn so the direct path can be seen. No wall is drawn."
    )
    if ceiling is not None:
        hint += " " + _(
            "The hollow mark is the first-order image source of that loudspeaker; "
            "the dashed path is the specular bounce off the plane above."
        )
    return hint + _scan_hint(scan)


def _scan_hint(scan: RoomScan | None) -> str:
    if scan is None:
        return ""
    return " " + _(
        "The faint points are an imported scan ({name}), not a RoomScope measurement "
        "and not a lidar attached to this computer."
    ).format(name=scan.source_name)


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
    scan: RoomScan | None = None,
) -> None:
    fig.clear()
    ensure_plot_fonts()
    ax: Any = fig.add_subplot(111, projection="3d")
    colors = plot_colors()
    accent = tokens()["accent"]
    speaker = PLOT_SERIES[1]
    radius = max(horizontal_m, mic_z, source_z, 0.8) * 1.35
    if scan is not None and scan.points_m.size:
        extent = float(np.max(np.abs(scan.points_m)))
        radius = max(radius, extent * 1.05 if extent > 0 else radius)
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
    if scan is not None and scan.points_m.size:
        top = max(top, float(scan.points_m[:, 2].max()))
        ax.scatter(
            scan.points_m[:, 0],
            scan.points_m[:, 1],
            scan.points_m[:, 2],
            s=6,
            c=colors["muted"],
            alpha=0.35,
            depthshade=False,
        )
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
    image_z = None
    if ceiling_z is not None:
        image, bounce = horizontal_plane_image_path(
            (sx, sy, source_z), (0.0, 0.0, mic_z), ceiling_z
        )
        image_z = image[2]
        bounce_color = PLOT_SERIES[2]
        ax.plot(
            [sx, bounce[0], 0.0],
            [sy, bounce[1], 0.0],
            [source_z, bounce[2], mic_z],
            color=bounce_color,
            linestyle="--",
            linewidth=1.3,
        )
        ax.scatter(
            [image[0]],
            [image[1]],
            [image[2]],
            s=42,
            facecolors="none",
            edgecolors=speaker,
            linewidths=1.4,
        )
        ax.text(image[0] + 0.16, image[1] + 0.08, image[2], _("Image source"), fontsize=8)
        ax.text(
            bounce[0] + 0.12, bounce[1] + 0.08, bounce[2] + 0.06, _("Specular bounce"), fontsize=8
        )
    scale = 1.0 if radius >= 1.4 else 0.5
    edge = -radius * 0.72
    ax.plot([edge, edge + scale], [edge, edge], [0.0, 0.0], color=colors["fg"], linewidth=2.0)
    ax.text(edge + scale * 0.5, edge, 0.05, f"{scale:g} m", fontsize=8)
    zlim = max(top, image_z or 0.0) * 1.15
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
