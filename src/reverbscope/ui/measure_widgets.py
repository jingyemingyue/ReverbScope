"""Widgets the measurement dialogs share: the recording profile row, the
metadata form and the optional tape measurements with their side view.
"""

from __future__ import annotations

from typing import Any, cast

from reverbscope.ui.qt import ensure_pyside6

ensure_pyside6()

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from reverbscope.i18n import _
from reverbscope.interpretation import available_profiles
from reverbscope.interpretation.profiles import profile_title
from reverbscope.ui.widgets import label


def metadata_form(
    room: str = "", position: str = "", mic: str = ""
) -> tuple[QGroupBox, QLineEdit, QLineEdit, QLineEdit]:
    """Room, position and microphone: what a project lists a take under."""
    box = QGroupBox(_("Measurement metadata (optional)"))
    form = QFormLayout(box)
    room_edit = QLineEdit(room)
    room_edit.setPlaceholderText(_("Booth A, living room, studio B"))
    position_edit = QLineEdit(position)
    position_edit.setPlaceholderText(_("A, desk, corner"))
    mic_edit = QLineEdit(mic)
    form.addRow(_("Room"), room_edit)
    form.addRow(_("Position"), position_edit)
    form.addRow(_("Microphone"), mic_edit)
    return box, room_edit, position_edit, mic_edit


def profile_combo(profile: str) -> QComboBox:
    """The recording profiles, ``profile`` preselected, each with its description."""
    from reverbscope.interpretation.explain import profile_description

    combo = QComboBox()
    for index, name in enumerate(available_profiles()):
        combo.addItem(profile_title(name), name)
        combo.setItemData(index, profile_description(name), Qt.ItemDataRole.ToolTipRole)
    combo.setCurrentIndex(max(combo.findData(profile), 0))

    def describe(_index: int) -> None:
        combo.setToolTip(profile_description(str(combo.currentData() or "")))

    combo.currentIndexChanged.connect(describe)
    describe(combo.currentIndex())
    return combo


def profile_row(combo: QComboBox, page: QWidget) -> tuple[QHBoxLayout, QPushButton]:
    """The profile selector with the button that says what the profile wants."""
    from reverbscope.ui.profile_dialog import profile_of, show_profile_help

    row = QHBoxLayout()
    row.setSpacing(8)
    row.addWidget(combo, 1)
    button = QPushButton(_("Profile details"))
    button.setToolTip(_("What this profile watches for, and what it does not judge."))
    button.clicked.connect(lambda: show_profile_help(profile_of(combo), page))
    row.addWidget(button)
    return row, button


class PlacementInputs(QGroupBox):
    """Optional tape measurements that raise the placement tier (S5).

    The picture beside the fields is a side view of the two tape measures:
    what was typed is drawn as measured, everything else as an example.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setTitle(_("Tape measurements (optional)"))
        row = QHBoxLayout(self)
        form = QFormLayout()
        self.distance = QDoubleSpinBox()
        self.distance.setRange(0.0, 15.0)
        self.distance.setDecimals(2)
        self.distance.setSingleStep(0.01)
        self.distance.setSuffix(" m")
        self.distance.setSpecialValueText(_("not measured"))
        self.distance.setValue(0.0)
        self.distance.setToolTip(_("Straight line from the loudspeaker to the microphone capsule."))
        self.mic_height = QDoubleSpinBox()
        self.mic_height.setRange(0.0, 5.0)
        self.mic_height.setDecimals(2)
        self.mic_height.setSingleStep(0.01)
        self.mic_height.setSuffix(" m")
        self.mic_height.setSpecialValueText(_("not measured"))
        self.mic_height.setValue(0.0)
        self.mic_height.setEnabled(False)
        self.mic_height.setToolTip(
            _("Capsule above the first solid horizontal surface below it. Needs the distance.")
        )
        self.temperature = QDoubleSpinBox()
        self.temperature.setRange(-20.0, 50.0)
        self.temperature.setDecimals(1)
        self.temperature.setValue(20.0)
        self.temperature.setSuffix(" C")
        self.temperature.setEnabled(False)
        self.temperature_measured = QCheckBox(_("air temperature measured"))
        self.temperature_measured.toggled.connect(self.temperature.setEnabled)
        self.distance.valueChanged.connect(self._sync_height)
        self.distance.valueChanged.connect(self._redraw_scene)
        self.mic_height.valueChanged.connect(self._redraw_scene)
        form.addRow(_("Loudspeaker distance"), self.distance)
        form.addRow(_("Microphone height"), self.mic_height)
        form.addRow(self.temperature_measured, self.temperature)
        form.addRow(
            label(
                _(
                    "With the distance, every early reflection gets its path length in "
                    "metres; with the microphone height as well, the loudspeaker height, "
                    "the horizontal separation and the plane above can be solved."
                ),
                "hint",
                wrap=True,
            )
        )
        row.addLayout(form, 1)
        scene = QVBoxLayout()
        self.figure = Figure(figsize=(5.0, 2.8), dpi=100)
        self.canvas: Any = cast(Any, FigureCanvasQTAgg)(self.figure)
        self.canvas.setMinimumHeight(180)
        self.scene_hint = QLabel("")
        self.scene_hint.setWordWrap(True)
        self.scene_hint.setProperty("role", "hint")
        scene.addWidget(self.canvas, 1)
        scene.addWidget(self.scene_hint)
        row.addLayout(scene, 2)
        self._redraw_scene()

    def _sync_height(self, value: float) -> None:
        allowed = value >= 0.20
        self.mic_height.setEnabled(allowed)
        if not allowed:
            self.mic_height.setValue(0.0)

    def redraw(self) -> None:
        """Draw the picture again (in a new colour scheme)."""
        self._redraw_scene()

    def _redraw_scene(self, _value: float | None = None) -> None:
        from reverbscope.ui.plots import plot_placement_illustration

        distance = self.distance.value()
        height = self.mic_height.value()
        hint = plot_placement_illustration(
            self.figure,
            distance_m=distance if distance >= 0.20 else None,
            mic_height_m=height if self.mic_height.isEnabled() and height >= 0.02 else None,
        )
        self.scene_hint.setText(hint)
        self.canvas.draw_idle()

    def values(self) -> tuple[float | None, float | None, float | None]:
        """``(distance_m, mic_height_m, temperature_c)`` as the analysis takes them."""
        distance = self.distance.value()
        height = self.mic_height.value()
        distance_m = distance if distance >= 0.20 else None
        mic_height_m = height if distance_m is not None and height >= 0.02 else None
        temperature_c = self.temperature.value() if self.temperature_measured.isChecked() else None
        return distance_m, mic_height_m, temperature_c

    def analysis_kwargs(self) -> dict[str, float | None]:
        distance_m, mic_height_m, temperature_c = self.values()
        return {
            "placement_distance_m": distance_m,
            "placement_mic_height_m": mic_height_m,
            "placement_temperature_c": temperature_c,
        }

    def summary(self) -> str:
        """One line: what was entered."""
        distance_m, mic_height_m, temperature_c = self.values()
        parts: list[str] = []
        if distance_m is not None:
            parts.append(_("loudspeaker distance {metres:.2f} m").format(metres=distance_m))
        if mic_height_m is not None:
            parts.append(_("microphone height {metres:.2f} m").format(metres=mic_height_m))
        if temperature_c is not None:
            parts.append(_("air {celsius:.1f} °C").format(celsius=temperature_c))
        if not parts:
            return _("No tape measurement entered (the placement geometry stays at tier 0).")
        from reverbscope.i18n import list_join

        return list_join(parts)
