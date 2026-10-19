"""Peak / RMS input level meter, drawn with QPainter in the design tokens.

Vertical (beside the live spectrum) or compact horizontal. Each channel
shows the RMS bar, the peak bar behind it, the peak-hold marker, a clip
indicator that latches until it is clicked, and the numeric peak and RMS.
The ballistics live in :mod:`reverbscope.display.live`; this widget only draws.
"""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFontMetrics, QMouseEvent, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from reverbscope.audio.backend import SAFE_MAX_LEVEL_DBFS
from reverbscope.display.live import (
    METER_FLOOR_DBFS,
    METER_TICKS_DBFS,
    PEAK_HOLD_S,
    SILENCE_DBFS,
    MeterChannel,
    meter_fraction,
)
from reverbscope.health import HEADROOM_DB
from reverbscope.i18n import _
from reverbscope.ui.design.tokens import SPACE
from reverbscope.ui.theme import tokens

#: Bar thickness and the gap between channels (logical px).
BAR = 12
GAP = 6


def format_dbfs(value: float) -> str:
    """``-12.3`` with a real minus sign; ``-inf`` below the meter floor."""
    if value <= SILENCE_DBFS + 0.5 or value < METER_FLOOR_DBFS - 40.0:
        return "−∞"
    text = f"{value:.1f}"
    return text.replace("-", "−")


class LevelMeter(QWidget):
    """A multi-channel peak / RMS meter. Click it to clear the clip indicators."""

    clip_reset = Signal()

    def __init__(
        self,
        names: Sequence[str] = (),
        *,
        orientation: Qt.Orientation = Qt.Orientation.Vertical,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.orientation = orientation
        self.channels: list[MeterChannel] = []
        self.names: list[str] = []
        self.set_channels(names or [_("Input")])
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName(_("Input level meter"))
        self.setToolTip(
            _(
                "Peak (light bar, marker held {hold:g} s) and RMS (solid bar) in dBFS. "
                "The line at {safe:g} dBFS is the level from which a sweep needs your "
                "acknowledgement; the red box latches when the input reaches full scale. "
                "Click to clear it."
            ).format(hold=PEAK_HOLD_S, safe=SAFE_MAX_LEVEL_DBFS)
        )
        if orientation == Qt.Orientation.Vertical:
            self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        else:
            self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    # --- data -------------------------------------------------------------------

    def set_channels(self, names: Sequence[str]) -> None:
        names = list(names) or [_("Input")]
        if names != self.names:
            self.names = names
            self.channels = [MeterChannel() for _name in names]
            self.updateGeometry()
            self.update()

    def update_levels(
        self, peaks_dbfs: Sequence[float], rms_dbfs: Sequence[float], dt_s: float
    ) -> None:
        for channel, peak, rms in zip(self.channels, peaks_dbfs, rms_dbfs, strict=False):
            channel.update(peak, rms, dt_s)
        self.update()
        self.setAccessibleDescription(self.readout_text())

    def reset(self) -> None:
        for channel in self.channels:
            channel.reset()
        self.update()

    def reset_clip(self) -> None:
        for channel in self.channels:
            channel.reset_clip()
        self.clip_reset.emit()
        self.update()

    @property
    def clipped(self) -> bool:
        return any(channel.clipped for channel in self.channels)

    def readout_text(self) -> str:
        return "  ".join(
            _("{name}: peak {peak} dBFS, RMS {rms} dBFS").format(
                name=name,
                peak=format_dbfs(channel.peak.hold),
                rms=format_dbfs(channel.last_rms_dbfs),
            )
            for name, channel in zip(self.names, self.channels, strict=True)
        )

    # --- geometry ---------------------------------------------------------------

    def _scale_width(self) -> int:
        return QFontMetrics(self.font()).horizontalAdvance("−48") + 4

    def _readout_width(self) -> int:
        return QFontMetrics(self.font()).horizontalAdvance("−99.9") + 4

    def _column_width(self) -> int:
        """One vertical channel: its bar, its readout and its name side by side."""
        metrics = QFontMetrics(self.font())
        names = max((metrics.horizontalAdvance(n) for n in self.names), default=0) + 6
        return max(BAR + GAP, self._readout_width(), names)

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt override
        n = len(self.channels)
        line = QFontMetrics(self.font()).height()
        if self.orientation == Qt.Orientation.Vertical:
            per = self._column_width()
            return QSize(self._scale_width() + n * per + SPACE, 260)
        return QSize(360, n * (BAR + GAP) + line + 2 * SPACE)

    def minimumSizeHint(self) -> QSize:  # noqa: N802 - Qt override
        hint = self.sizeHint()
        if self.orientation == Qt.Orientation.Vertical:
            return QSize(hint.width(), 160)
        return QSize(200, hint.height())

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt override
        if event.button() == Qt.MouseButton.LeftButton:
            self.reset_clip()
            event.accept()
            return
        super().mousePressEvent(event)

    # --- painting ---------------------------------------------------------------

    def _colors(self) -> dict[str, QColor]:
        t = tokens()
        peak = QColor(t["accent"])
        peak.setAlpha(110)
        return {
            "track": QColor(t["surface_alt"]),
            "rms": QColor(t["accent"]),
            "peak": peak,
            "hot": QColor(t["bad"]),
            "hold": QColor(t["text"]),
            "text": QColor(t["text"]),
            "muted": QColor(t["muted"]),
            "grid": QColor(t["border"]),
            "safe": QColor(t["warn"]),
            "clip_off": QColor(t["border"]),
        }

    def paintEvent(self, _event: QPaintEvent) -> None:  # noqa: N802 - Qt override
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        colors = self._colors()
        if self.orientation == Qt.Orientation.Vertical:
            self._paint_vertical(painter, colors)
        else:
            self._paint_horizontal(painter, colors)
        painter.end()

    def _paint_vertical(self, painter: QPainter, c: dict[str, QColor]) -> None:
        metrics = QFontMetrics(self.font())
        line = metrics.height()
        scale_w = self._scale_width()
        per = self._column_width()
        top = line // 2 + BAR  # room for the clip box
        bottom = self.height() - 2 * line - SPACE
        span = max(1, bottom - top)

        def y_of(db: float) -> float:
            return bottom - meter_fraction(db) * span

        painter.setPen(c["muted"])
        labelled = -1e9
        for tick in METER_TICKS_DBFS:
            y = y_of(tick)
            # Every tick gets its mark on the bar; a label only where it fits.
            if y - labelled < line * 0.9:
                continue
            labelled = y
            text = f"{tick:g}".replace("-", "−")
            painter.drawText(
                QRectF(0, y - line / 2, scale_w - 4, line),
                int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
                text,
            )
        x = scale_w
        for name, channel in zip(self.names, self.channels, strict=True):
            bar_x = x + (per - BAR) / 2
            track = QRectF(bar_x, top, BAR, span)
            painter.fillRect(track, c["track"])
            for tick in METER_TICKS_DBFS:
                y = y_of(tick)
                painter.setPen(QPen(c["grid"], 1))
                painter.drawLine(int(bar_x - 3), int(y), int(bar_x), int(y))
            self._fill_level(painter, c, track, channel.peak.level, c["peak"], vertical=True)
            self._fill_level(painter, c, track, channel.rms.level, c["rms"], vertical=True)
            # The acknowledgement level and the peak-hold marker.
            safe_y = y_of(SAFE_MAX_LEVEL_DBFS)
            painter.setPen(QPen(c["safe"], 2))
            painter.drawLine(int(bar_x - 2), int(safe_y), int(bar_x + BAR + 2), int(safe_y))
            if channel.peak.hold > METER_FLOOR_DBFS:
                hold_y = y_of(channel.peak.hold)
                painter.setPen(QPen(c["hot"] if channel.peak.hold > -HEADROOM_DB else c["hold"], 2))
                painter.drawLine(int(bar_x), int(hold_y), int(bar_x + BAR), int(hold_y))
            clip = QRectF(bar_x, top - BAR + 1, BAR, BAR - 3)
            painter.fillRect(clip, c["hot"] if channel.clipped else c["clip_off"])
            painter.setPen(c["text"])
            readout = QRectF(x, bottom + 4, per, line)
            painter.drawText(
                readout, int(Qt.AlignmentFlag.AlignCenter), format_dbfs(channel.peak.hold)
            )
            painter.setPen(c["muted"])
            painter.drawText(
                QRectF(x, bottom + 4 + line, per, line),
                int(Qt.AlignmentFlag.AlignCenter),
                name,
            )
            x += per

    def _paint_horizontal(self, painter: QPainter, c: dict[str, QColor]) -> None:
        metrics = QFontMetrics(self.font())
        line = metrics.height()
        name_w = max((metrics.horizontalAdvance(n) for n in self.names), default=0) + SPACE
        readout_w = self._readout_width() * 2 + SPACE
        left = name_w
        right = self.width() - readout_w
        span = max(1, right - left)

        def x_of(db: float) -> float:
            return left + meter_fraction(db) * span

        y = SPACE // 2
        for name, channel in zip(self.names, self.channels, strict=True):
            track = QRectF(left, y, span, BAR)
            painter.setPen(c["muted"])
            painter.drawText(
                QRectF(0, y - 2, name_w - 4, BAR + 4),
                int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
                name,
            )
            painter.fillRect(track, c["track"])
            self._fill_level(painter, c, track, channel.peak.level, c["peak"], vertical=False)
            self._fill_level(painter, c, track, channel.rms.level, c["rms"], vertical=False)
            safe_x = x_of(SAFE_MAX_LEVEL_DBFS)
            painter.setPen(QPen(c["safe"], 2))
            painter.drawLine(int(safe_x), int(y - 2), int(safe_x), int(y + BAR + 2))
            if channel.peak.hold > METER_FLOOR_DBFS:
                hold_x = x_of(channel.peak.hold)
                painter.setPen(QPen(c["hot"] if channel.peak.hold > -HEADROOM_DB else c["hold"], 2))
                painter.drawLine(int(hold_x), int(y), int(hold_x), int(y + BAR))
            clip = QRectF(right + 2, y, BAR - 2, BAR)
            painter.fillRect(clip, c["hot"] if channel.clipped else c["clip_off"])
            painter.setPen(c["text"])
            painter.drawText(
                QRectF(right + BAR + 2, y - 2, readout_w - BAR - 2, BAR + 4),
                int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                f"{format_dbfs(channel.peak.hold)} / {format_dbfs(channel.last_rms_dbfs)}",
            )
            y += BAR + GAP
        painter.setPen(c["muted"])
        for tick in METER_TICKS_DBFS:
            if tick in (-3.0, -18.0):
                continue  # too close to their neighbours on a short scale
            tx = x_of(tick)
            painter.setPen(QPen(c["grid"], 1))
            painter.drawLine(int(tx), int(y - GAP + 1), int(tx), int(y))
            painter.setPen(c["muted"])
            painter.drawText(
                QRectF(tx - 20, y, 40, line),
                int(Qt.AlignmentFlag.AlignCenter),
                f"{tick:g}".replace("-", "−"),
            )

    def _fill_level(
        self,
        painter: QPainter,
        c: dict[str, QColor],
        track: QRectF,
        level: float,
        color: QColor,
        *,
        vertical: bool,
    ) -> None:
        fraction = meter_fraction(level)
        if fraction <= 0.0:
            return
        hot_from = meter_fraction(-HEADROOM_DB)
        if vertical:
            height = track.height() * fraction
            rect = QRectF(track.left(), track.bottom() - height, track.width(), height)
            painter.fillRect(rect, color)
            if fraction > hot_from:
                hot_top = track.bottom() - track.height() * hot_from
                hot = QRectF(track.left(), rect.top(), track.width(), hot_top - rect.top())
                painter.fillRect(hot, c["hot"])
        else:
            width = track.width() * fraction
            rect = QRectF(track.left(), track.top(), width, track.height())
            painter.fillRect(rect, color)
            if fraction > hot_from:
                hot_left = track.left() + track.width() * hot_from
                hot = QRectF(hot_left, track.top(), rect.right() - hot_left, track.height())
                painter.fillRect(hot, c["hot"])
