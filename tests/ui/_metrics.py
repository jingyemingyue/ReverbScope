"""Font metrics a pixel-fit check needs before it means anything."""

from __future__ import annotations

import sys

from PySide6.QtGui import QFont, QFontMetrics, QGuiApplication

#: 13 px "ReverbScope" is about 80 px in Segoe UI, SF and DejaVu Sans; Qt's
#: offscreen platform on Windows draws it in a fallback face at about 154 px.
_WIDE_LATIN_PX = 120


def wide_offscreen_latin() -> bool:
    """True on Windows' offscreen platform when its Latin face is about twice
    as wide as any desktop font. A window that fits on the desktop cannot fit
    there (its own minimum is wider than the requested size), so a pixel fit
    says nothing; checks that are not about pixels still run."""
    if sys.platform != "win32" or QGuiApplication.platformName() != "offscreen":
        return False
    font = QFont(QGuiApplication.font())
    font.setPixelSize(13)
    return QFontMetrics(font).horizontalAdvance("ReverbScope") > _WIDE_LATIN_PX
