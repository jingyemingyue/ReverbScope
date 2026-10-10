"""The tape-measure picture beside the placement inputs (matplotlib, 3D).

The only matplotlib drawing left in the desktop app: the charts of a result
are pyqtgraph views (``reverbscope.ui.views``) and the measured room is the
QPainter room view (``reverbscope.ui.room``). This picture is a schematic of
where the two tape measures go before a measurement; it is not a room and
not a result.
"""

from __future__ import annotations

from typing import Any

import mpl_toolkits.mplot3d  # noqa: F401  registers the 3d projection
import numpy as np
from matplotlib.figure import Figure

from reverbscope.i18n import _
from reverbscope.ui.theme import PLOT_SERIES, ensure_plot_fonts, plot_colors, style_figure, tokens

_EXAMPLE_DISTANCE_M = 2.0
_EXAMPLE_HEIGHT_M = 1.2


def plot_placement_illustration(
    fig: Figure, *, distance_m: float | None, mic_height_m: float | None
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
    )
    if distance_entered and height_entered:
        return _(
            "The line is the loudspeaker distance you entered, and the stand is the "
            "microphone height you entered. The loudspeaker is drawn at that same height "
            "only so the tape can be seen; its real height comes from a measurement. "
            "No room and no wall are drawn."
        )
    if distance_entered:
        return _(
            "The line is the loudspeaker distance you entered. Both heights in this "
            "picture are an example. No room and no wall are drawn."
        )
    return _(
        "Nothing has been entered. This picture shows where the two tape measures go. "
        "It is not your room, and no wall is drawn."
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
