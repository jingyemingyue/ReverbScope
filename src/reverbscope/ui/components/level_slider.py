"""Playback level control with a marked safe ceiling (SAFE-01)."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QDoubleSpinBox, QHBoxLayout, QSlider, QWidget

from reverbscope.audio.backend import SAFE_MAX_LEVEL_DBFS
from reverbscope.i18n import _


class LevelSlider(QWidget):
    """Slider −40…0 dBFS synced with a spin box; marks the safe ceiling."""

    value_changed = Signal(float)

    def __init__(
        self,
        spin: QDoubleSpinBox,
        parent: QWidget | None = None,
        *,
        minimum: float = -40.0,
        maximum: float = 0.0,
        safe_max: float = SAFE_MAX_LEVEL_DBFS,
    ) -> None:
        super().__init__(parent)
        self._minimum = minimum
        self._maximum = maximum
        self._safe_max = safe_max
        self._spin = spin
        self._slider = QSlider(Qt.Orientation.Horizontal)
        # Tenths of a dB keep the slider fine enough for 0.5 dB steps.
        self._slider.setRange(int(minimum * 10), int(maximum * 10))
        self._slider.setSingleStep(5)
        self._slider.setPageStep(10)
        self._slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self._slider.setTickInterval(max(1, int((safe_max - minimum) * 10)))
        self._slider.setToolTip(_("Safe ceiling {level:g} dBFS").format(level=safe_max))
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._slider, 1)
        layout.addWidget(spin)
        self._slider.valueChanged.connect(self._slider_moved)
        spin.valueChanged.connect(self._spin_moved)
        self.set_value(float(spin.value()))

    def value(self) -> float:
        return float(self._spin.value())

    def set_value(self, level: float) -> None:
        clamped = max(self._minimum, min(self._maximum, level))
        ticks = round(clamped * 10)
        self._slider.blockSignals(True)
        self._spin.blockSignals(True)
        self._slider.setValue(ticks)
        self._spin.setValue(clamped)
        self._slider.blockSignals(False)
        self._spin.blockSignals(False)
        self._apply_safe_property(clamped)

    def _apply_safe_property(self, level: float) -> None:
        self._slider.setProperty("above_safe", level > self._safe_max)
        style = self._slider.style()
        style.unpolish(self._slider)
        style.polish(self._slider)

    def _slider_moved(self, ticks: int) -> None:
        level = ticks / 10.0
        self._spin.blockSignals(True)
        self._spin.setValue(level)
        self._spin.blockSignals(False)
        self._apply_safe_property(level)
        self.value_changed.emit(level)

    def _spin_moved(self, level: float) -> None:
        ticks = round(float(level) * 10)
        self._slider.blockSignals(True)
        self._slider.setValue(ticks)
        self._slider.blockSignals(False)
        self._apply_safe_property(float(level))
        self.value_changed.emit(float(level))
