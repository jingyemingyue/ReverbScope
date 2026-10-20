"""Line icons for the light sidebar workstation: one family, Lucide.

The shapes below are copied from lucide-static 1.59.0 (https://lucide.dev),
ISC License, Copyright (c) 2026 Lucide Icons and Contributors; the icons
Lucide derives from Feather are also under the MIT License, Copyright (c)
2013-present Cole Bemis. The full texts are in
``packaging/licenses/lucide-LICENSE.txt`` and the desktop bundle's
``THIRD_PARTY_LICENSES/_notices/lucide.txt`` (docs/DEPENDENCIES.md, C7 audit
in docs/design/GUI_REFERENCE_AUDIT.md). Only the icons the interface uses are
kept, as SVG elements in this module, so no data file has to be packaged.

Every icon names one real action of the GUI (docs/design/light-sidebar/
IMPLEMENTATION.md has the table). They are drawn with a 1.5 px stroke at the
size asked for and in the colour of the current theme; the disabled state
uses the theme's disabled colour so a locked control reads as locked.
"""

from __future__ import annotations

import functools

from PySide6.QtCore import QByteArray, QRectF, QSize, Qt
from PySide6.QtGui import QGuiApplication, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

#: Lucide element markup, by icon name (24 x 24 view box).
LUCIDE: dict[str, tuple[str, ...]] = {
    "activity": (
        '<path d="M22 12h-2.48a2 2 0 0 0-1.93 1.46l-2.35 8.36a.25.25 0 0 1-.48 0L9.24 2.18a.25.25 0 0 0-.48 0l-2.35 8.36A2 2 0 0 1 4.49 12H2" />',
    ),
    "arrow-left-right": (
        '<path d="M8 3 4 7l4 4" />',
        '<path d="M4 7h16" />',
        '<path d="m16 21 4-4-4-4" />',
        '<path d="M20 17H4" />',
    ),
    "arrow-right": (
        '<path d="M5 12h14" />',
        '<path d="m12 5 7 7-7 7" />',
    ),
    "audio-lines": (
        '<path d="M2 10v3" />',
        '<path d="M6 6v11" />',
        '<path d="M10 3v18" />',
        '<path d="M14 8v7" />',
        '<path d="M18 5v13" />',
        '<path d="M22 10v3" />',
    ),
    "audio-waveform": (
        '<path d="M2 13a2 2 0 0 0 2-2V7a2 2 0 0 1 4 0v13a2 2 0 0 0 4 0V4a2 2 0 0 1 4 0v13a2 2 0 0 0 4 0v-4a2 2 0 0 1 2-2" />',
    ),
    "cable": (
        '<path d="M17 19a1 1 0 0 1-1-1v-2a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v2a1 1 0 0 1-1 1z" />',
        '<path d="M17 21v-2" />',
        '<path d="M19 14V6.5a1 1 0 0 0-7 0v11a1 1 0 0 1-7 0V10" />',
        '<path d="M21 21v-2" />',
        '<path d="M3 5V3" />',
        '<path d="M4 10a2 2 0 0 1-2-2V6a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2a2 2 0 0 1-2 2z" />',
        '<path d="M7 5V3" />',
    ),
    "chart-spline": (
        '<path d="M3 3v16a2 2 0 0 0 2 2h16" />',
        '<path d="M7 16c.5-2 1.5-7 4-7 2 0 2 3 4 3 2.5 0 4.5-5 5-7" />',
    ),
    "check": ('<path d="M20 6 9 17l-5-5" />',),
    "chevron-down": ('<path d="m6 9 6 6 6-6" />',),
    "chevron-left": ('<path d="m15 18-6-6 6-6" />',),
    "chevron-right": ('<path d="m9 18 6-6-6-6" />',),
    "circle-check": (
        '<circle cx="12" cy="12" r="10" />',
        '<path d="m16 9-5.5 5.5L8 12" />',
    ),
    "circle-dashed": (
        '<path d="M10.1 2.182a10 10 0 0 1 3.8 0" />',
        '<path d="M13.9 21.818a10 10 0 0 1-3.8 0" />',
        '<path d="M17.609 3.721a10 10 0 0 1 2.69 2.7" />',
        '<path d="M2.182 13.9a10 10 0 0 1 0-3.8" />',
        '<path d="M20.279 17.609a10 10 0 0 1-2.7 2.69" />',
        '<path d="M21.818 10.1a10 10 0 0 1 0 3.8" />',
        '<path d="M3.721 6.391a10 10 0 0 1 2.7-2.69" />',
        '<path d="M6.391 20.279a10 10 0 0 1-2.69-2.7" />',
    ),
    "circle-help": (
        '<circle cx="12" cy="12" r="10" />',
        '<path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3" />',
        '<path d="M12 17h.01" />',
    ),
    "circle-x": (
        '<circle cx="12" cy="12" r="10" />',
        '<path d="m15 9-6 6" />',
        '<path d="m9 9 6 6" />',
    ),
    "copy": (
        '<rect width="14" height="14" x="8" y="8" rx="2" ry="2" />',
        '<path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2" />',
    ),
    "download": (
        '<path d="M12 15V3" />',
        '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />',
        '<path d="m7 10 5 5 5-5" />',
    ),
    "file-down": (
        '<path d="M6 22a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h8a2.4 2.4 0 0 1 1.704.706l3.588 3.588A2.4 2.4 0 0 1 20 8v12a2 2 0 0 1-2 2z" />',
        '<path d="M14 2v5a1 1 0 0 0 1 1h5" />',
        '<path d="M12 18v-6" />',
        '<path d="m9 15 3 3 3-3" />',
    ),
    "file-input": (
        '<path d="M4 11V4a2 2 0 0 1 2-2h8a2.4 2.4 0 0 1 1.706.706l3.588 3.588A2.4 2.4 0 0 1 20 8v12a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2v-1" />',
        '<path d="M14 2v5a1 1 0 0 0 1 1h5" />',
        '<path d="M2 15h10" />',
        '<path d="m9 18 3-3-3-3" />',
    ),
    "file-text": (
        '<path d="M6 22a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h8a2.4 2.4 0 0 1 1.704.706l3.588 3.588A2.4 2.4 0 0 1 20 8v12a2 2 0 0 1-2 2z" />',
        '<path d="M14 2v5a1 1 0 0 0 1 1h5" />',
        '<path d="M10 9H8" />',
        '<path d="M16 13H8" />',
        '<path d="M16 17H8" />',
    ),
    "flask-conical": (
        '<path d="M14 2v6a2 2 0 0 0 .245.96l5.51 10.08A2 2 0 0 1 18 22H6a2 2 0 0 1-1.755-2.96l5.51-10.08A2 2 0 0 0 10 8V2" />',
        '<path d="M6.453 15h11.094" />',
        '<path d="M8.5 2h7" />',
    ),
    "folder": (
        '<path d="M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z" />',
    ),
    "folder-open": (
        '<path d="m6 14 1.5-2.9A2 2 0 0 1 9.24 10H20a2 2 0 0 1 1.94 2.5l-1.54 6a2 2 0 0 1-1.95 1.5H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h3.9a2 2 0 0 1 1.69.9l.81 1.2a2 2 0 0 0 1.67.9H18a2 2 0 0 1 2 2v2" />',
    ),
    "git-compare": (
        '<circle cx="18" cy="18" r="3" />',
        '<circle cx="6" cy="6" r="3" />',
        '<path d="M13 6h3a2 2 0 0 1 2 2v7" />',
        '<path d="M11 18H8a2 2 0 0 1-2-2V9" />',
    ),
    "heart-pulse": (
        '<path d="M2 9.5a5.5 5.5 0 0 1 9.591-3.676.56.56 0 0 0 .818 0A5.49 5.49 0 0 1 22 9.5c0 2.29-1.5 4-3 5.5l-5.492 5.313a2 2 0 0 1-3 .019L5 15c-1.5-1.5-3-3.2-3-5.5" />',
        '<path d="M3.22 13H9.5l.5-1 2 4.5 2-7 1.5 3.5h5.27" />',
    ),
    "history": (
        '<path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" />',
        '<path d="M3 3v5h5" />',
        '<path d="M12 7v5l4 2" />',
    ),
    "info": (
        '<circle cx="12" cy="12" r="10" />',
        '<path d="M12 16v-4" />',
        '<path d="M12 8h.01" />',
    ),
    "layers": (
        '<path d="M12.83 2.18a2 2 0 0 0-1.66 0L2.6 6.08a1 1 0 0 0 0 1.83l8.58 3.91a2 2 0 0 0 1.66 0l8.58-3.9a1 1 0 0 0 0-1.83z" />',
        '<path d="M2 12a1 1 0 0 0 .58.91l8.6 3.91a2 2 0 0 0 1.65 0l8.58-3.9A1 1 0 0 0 22 12" />',
        '<path d="M2 17a1 1 0 0 0 .58.91l8.6 3.91a2 2 0 0 0 1.65 0l8.58-3.9A1 1 0 0 0 22 17" />',
    ),
    "lock": (
        '<rect width="18" height="11" x="3" y="11" rx="2" ry="2" />',
        '<path d="M7 11V7a5 5 0 0 1 10 0v4" />',
    ),
    "mic": (
        '<path d="M12 19v3" />',
        '<path d="M19 10v2a7 7 0 0 1-14 0v-2" />',
        '<rect x="9" y="2" width="6" height="13" rx="3" />',
    ),
    "music": (
        '<path d="M21 16V3a1 1 0 0 0-1.28-.96l-10 2.917a1 1 0 0 0-.72.96V19" />',
        '<circle cx="18" cy="16" r="3" />',
        '<circle cx="6" cy="19" r="3" />',
    ),
    "panel-left": (
        '<rect width="18" height="18" x="3" y="3" rx="2" />',
        '<path d="M9 3v18" />',
    ),
    "panel-right": (
        '<rect width="18" height="18" x="3" y="3" rx="2" />',
        '<path d="M15 3v18" />',
    ),
    "plus": (
        '<path d="M5 12h14" />',
        '<path d="M12 5v14" />',
    ),
    "rotate-ccw": (
        '<path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" />',
        '<path d="M3 3v5h5" />',
    ),
    "save": (
        '<path d="M15.2 3a2 2 0 0 1 1.4.6l3.8 3.8a2 2 0 0 1 .6 1.4V19a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z" />',
        '<path d="M17 21v-7a1 1 0 0 0-1-1H8a1 1 0 0 0-1 1v7" />',
        '<path d="M7 3v4a1 1 0 0 0 1 1h7" />',
    ),
    "settings": (
        '<path d="M9.671 4.136a2.34 2.34 0 0 1 4.659 0 2.34 2.34 0 0 0 3.319 1.915 2.34 2.34 0 0 1 2.33 4.033 2.34 2.34 0 0 0 0 3.831 2.34 2.34 0 0 1-2.33 4.033 2.34 2.34 0 0 0-3.319 1.915 2.34 2.34 0 0 1-4.659 0 2.34 2.34 0 0 0-3.32-1.915 2.34 2.34 0 0 1-2.33-4.033 2.34 2.34 0 0 0 0-3.831A2.34 2.34 0 0 1 6.35 6.051a2.34 2.34 0 0 0 3.319-1.915" />',
        '<circle cx="12" cy="12" r="3" />',
    ),
    "sliders-vertical": (
        '<path d="M10 8h4" />',
        '<path d="M12 21v-9" />',
        '<path d="M12 8V3" />',
        '<path d="M17 16h4" />',
        '<path d="M19 12V3" />',
        '<path d="M19 21v-5" />',
        '<path d="M3 14h4" />',
        '<path d="M5 10V3" />',
        '<path d="M5 21v-7" />',
    ),
    "square-stop": (
        '<circle cx="12" cy="12" r="10" />',
        '<rect x="9" y="9" width="6" height="6" rx="1" />',
    ),
    "stethoscope": (
        '<path d="M11 2v2" />',
        '<path d="M5 2v2" />',
        '<path d="M5 3H4a2 2 0 0 0-2 2v4a6 6 0 0 0 12 0V5a2 2 0 0 0-2-2h-1" />',
        '<path d="M8 15a6 6 0 0 0 12 0v-3" />',
        '<circle cx="20" cy="10" r="2" />',
    ),
    "triangle-alert": (
        '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3" />',
        '<path d="M12 9v4" />',
        '<path d="M12 17h.01" />',
    ),
    "x": (
        '<path d="M18 6 6 18" />',
        '<path d="m6 6 12 12" />',
    ),
    "ruler": (
        '<path d="M21.3 15.3a2.4 2.4 0 0 1 0 3.4l-2.6 2.6a2.4 2.4 0 0 1-3.4 0L2.7 8.7a2.41 2.41 0 0 1 0-3.4l2.6-2.6a2.41 2.41 0 0 1 3.4 0Z" />',
        '<path d="m14.5 12.5 2-2" />',
        '<path d="m11.5 9.5 2-2" />',
        '<path d="m8.5 6.5 2-2" />',
        '<path d="m17.5 15.5 2-2" />',
    ),
}

#: Stroke width in pixels at the drawn size (SPEC §16.1).
STROKE_PX = 1.5


def svg_markup(name: str, color: str, size: int = 16, stroke_px: float = STROKE_PX) -> str:
    """The SVG document of ``name`` in ``color``, stroked ``stroke_px`` wide at ``size``."""
    elements = LUCIDE[name]
    width = stroke_px * 24.0 / max(size, 1)
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" '
        f'fill="none" stroke="{color}" stroke-width="{width:.3f}" stroke-linecap="round" '
        f'stroke-linejoin="round">{"".join(elements)}</svg>'
    )


def pixmap(name: str, color: str, size: int = 16, ratio: float | None = None) -> QPixmap:
    """``name`` drawn at ``size`` logical pixels for the screen's pixel ratio."""
    if ratio is None:
        app = QGuiApplication.instance()
        screen = QGuiApplication.primaryScreen() if app is not None else None
        ratio = screen.devicePixelRatio() if screen is not None else 1.0
    return _pixmap(name, color, size, max(1.0, float(ratio)))


@functools.lru_cache(maxsize=512)
def _pixmap(name: str, color: str, size: int, ratio: float) -> QPixmap:
    device = max(1, round(size * ratio))
    image = QPixmap(device, device)
    image.fill(Qt.GlobalColor.transparent)
    renderer = QSvgRenderer(QByteArray(svg_markup(name, color, size).encode("utf-8")))
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter, QRectF(0, 0, device, device))
    painter.end()
    image.setDevicePixelRatio(ratio)
    return image


def icon(name: str, size: int = 16, *, color: str = "", tone: str = "") -> QIcon:
    """A theme-coloured :class:`QIcon` of ``name``.

    ``color`` wins; otherwise ``tone`` picks a token (``accent``, ``good``,
    ``warn``, ``bad``, ``info``, ``on_accent``) and the default is the
    secondary text colour. Normal, active, selected and disabled states are
    drawn so Qt never greys the icon out by itself.
    """
    from reverbscope.ui.theme import tokens

    t = tokens()
    base = color or {
        "accent": t["accent_ink"],
        "good": t["good"],
        "warn": t["warn"],
        "bad": t["bad"],
        "info": t["info"],
        "on_accent": t["accent_text"],
        "on_bad": t["on_bad"],
        "text": t["text"],
    }.get(tone, t["muted"])
    result = QIcon()
    result.addPixmap(pixmap(name, base, size), QIcon.Mode.Normal, QIcon.State.Off)
    result.addPixmap(pixmap(name, base, size), QIcon.Mode.Normal, QIcon.State.On)
    active = color or (t["text"] if not tone else base)
    result.addPixmap(pixmap(name, active, size), QIcon.Mode.Active, QIcon.State.Off)
    result.addPixmap(pixmap(name, t["accent_ink"], size), QIcon.Mode.Active, QIcon.State.On)
    result.addPixmap(pixmap(name, t["accent_ink"], size), QIcon.Mode.Selected, QIcon.State.On)
    result.addPixmap(pixmap(name, t["disabled"], size), QIcon.Mode.Disabled, QIcon.State.Off)
    result.addPixmap(pixmap(name, t["disabled"], size), QIcon.Mode.Disabled, QIcon.State.On)
    return result


def icon_size(size: int = 16) -> QSize:
    return QSize(size, size)
