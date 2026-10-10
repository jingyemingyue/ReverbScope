"""The room view (``room``): the entered room, what the measurement constrains,
and what follows only from an assumption.

The user enters the room box, the loudspeaker and the microphone of each
position; they are saved in ``room-geometry.json`` next to ``project.json``
(or in the session folder), never in a session. The current measurement adds
the measured layer: the excess path and ellipsoid of the selected
reflection, and the direct distance when a loopback measured it. First-order
paths of the entered box are the assumption layer. A single microphone
cannot locate a wall; the view says so and never draws one as found.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from pathlib import Path
from typing import Any

import numpy as np
from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from reverbscope.geometry.paths import (
    SINGLE_MICROPHONE_NOTE,
    PredictedPath,
    consistency_checks,
    constraint_for,
    direct_distance,
    match_reflection,
    overlay_refusal,
    predict_first_order,
    speed_for,
    tolerance_ms,
)
from reverbscope.geometry.room import (
    GeometryError,
    Point,
    RoomBox,
    RoomGeometry,
    example_room,
    load_geometry,
    save_geometry,
    with_microphone,
    without_microphone,
)
from reverbscope.geometry.scan import (
    ScanCancelledError,
    ScanError,
    place_scan,
    read_scan,
    voxel_thin,
)
from reverbscope.i18n import _, localize
from reverbscope.labels import surface_text, validity_word
from reverbscope.models.result import AnalysisResult, PlacementResult, Validity
from reverbscope.ui.room.canvas import (
    LAYER_ASSUMED,
    LAYER_ENTERED,
    LAYER_MEASURED,
    LAYER_NAMES,
    RoomCanvas,
    RoomScene,
)
from reverbscope.ui.views.base import AnalysisView
from reverbscope.ui.widgets import label, set_banner_text
from reverbscope.ui.workspace import Entry, WorkspaceModel

log = logging.getLogger(__name__)

#: Points of an imported scan that are drawn (voxel-thinned).
SCAN_DISPLAY_POINTS = 20_000
SCAN_VOXEL_M = 0.05
#: Position label used when the measurement names none.
DEFAULT_POSITION = "A"


def placement_ring(
    placement: PlacementResult | None, mic: Point | None
) -> tuple[Point, float] | None:
    """Where the placement result puts the loudspeaker, around the entered microphone.

    Only when the loudspeaker height and the horizontal separation are both
    VALID; a single microphone leaves the direction open, so it is a ring.
    """
    if placement is None or mic is None:
        return None
    height = placement.source_height_m
    separation = placement.horizontal_separation_m
    if (
        height.validity is not Validity.VALID
        or height.metres is None
        or separation.validity is not Validity.VALID
        or separation.metres is None
        or separation.metres <= 0.05
    ):
        return None
    return Point(mic.x, mic.y, height.metres), separation.metres


def position_of(entry: Entry | None) -> str:
    if entry is None:
        return DEFAULT_POSITION
    if entry.position:
        return entry.position
    if entry.session is not None and entry.session.measurement_position.strip():
        return entry.session.measurement_position.strip()
    return DEFAULT_POSITION


class ScanLoader(QThread):
    """Reads and places the scan named in the geometry file, off the GUI thread."""

    loaded = Signal(int, object)
    failed = Signal(int, str)

    def __init__(self, generation: int, path: Path, geometry: RoomGeometry) -> None:
        super().__init__()
        self.generation = generation
        self.path = path
        self.room_geometry = geometry

    def run(self) -> None:
        reference = self.room_geometry.scan
        assert reference is not None
        try:
            mesh = read_scan(self.path, cancelled=self.isInterruptionRequested)
            if mesh.sha256 != reference.sha256:
                self.failed.emit(
                    self.generation,
                    _(
                        "{name} changed since it was placed (its SHA-256 differs); import it "
                        "again to place it"
                    ).format(name=self.path.name),
                )
                return
            placed = place_scan(
                mesh.vertices,
                units=reference.units,
                up_axis=reference.up_axis,
                yaw_deg=reference.yaw_deg,
                offset=reference.offset,
            )
            points = voxel_thin(placed, SCAN_VOXEL_M, SCAN_DISPLAY_POINTS)
        except ScanCancelledError:
            return
        except ScanError as exc:
            self.failed.emit(self.generation, localize(str(exc)))
            return
        except Exception:
            log.exception("reading scan %s failed unexpectedly", self.path)
            from reverbscope.ui.workers import unexpected_error_text

            self.failed.emit(self.generation, unexpected_error_text())
            return
        self.loaded.emit(self.generation, points)


def _spin(maximum: float, special: str = "") -> QDoubleSpinBox:
    spin = QDoubleSpinBox()
    spin.setDecimals(2)
    spin.setSingleStep(0.05)
    spin.setRange(0.0 if special else -maximum, maximum)
    spin.setSuffix(" m")
    if special:
        spin.setSpecialValueText(special)
    spin.setKeyboardTracking(False)
    return spin


class _PointBox(QGroupBox):
    """A checkable group of x, y, z: unchecked means not entered."""

    def __init__(self, title: str) -> None:
        super().__init__(title)
        self.setCheckable(True)
        self.setChecked(False)
        form = QFormLayout(self)
        form.setContentsMargins(6, 4, 6, 4)
        self.x_spin = _spin(1000.0)
        self.y_spin = _spin(1000.0)
        self.z_spin = _spin(1000.0)
        for axis, spin in (("x", self.x_spin), ("y", self.y_spin), ("z", self.z_spin)):
            form.addRow(axis, spin)

    def point(self) -> Point | None:
        if not self.isChecked():
            return None
        return Point(self.x_spin.value(), self.y_spin.value(), self.z_spin.value())

    def set_point(self, point: Point | None) -> None:
        self.setChecked(point is not None)
        if point is not None:
            self.x_spin.setValue(point.x)
            self.y_spin.setValue(point.y)
            self.z_spin.setValue(point.z)

    def spins(self) -> tuple[QDoubleSpinBox, ...]:
        return (self.x_spin, self.y_spin, self.z_spin)


class RoomView(AnalysisView):
    view_id = "room"

    #: The consistency checks for the current measurement and a note (for the inspector).
    checks_changed = Signal(object, str)

    def __init__(self, model: WorkspaceModel, parent: QWidget | None = None) -> None:
        super().__init__(model, parent)
        self.room_geometry = RoomGeometry()
        #: Where the geometry is saved; ``None`` keeps it in memory only.
        self.directory: Path | None = None
        self._scan_points: np.ndarray | None = None
        self._scan_loader: ScanLoader | None = None
        self._old_loaders: list[ScanLoader] = []
        self._generation = 0
        self._filling = False
        # A room file this version cannot read is shown as empty and never
        # overwritten: a save would drop every position it holds.
        self._read_only = False
        self._predicted: list[PredictedPath] = []
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(400)
        self._save_timer.timeout.connect(self.save)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(6)
        tools = QHBoxLayout()
        self.plan_button = QToolButton()
        self.plan_button.setText(_("Plan view"))
        self.plan_button.setCheckable(True)
        self.plan_button.setToolTip(
            _("Look straight down, to scale; drag the loudspeaker or a microphone to move it.")
        )
        self.plan_button.toggled.connect(self._toggle_plan)
        fit = QToolButton()
        fit.setText(_("Fit"))
        fit.setToolTip(_("Frame the room (F or double-click)."))
        reset = QToolButton()
        reset.setText(_("Reset view"))
        reset.setToolTip(_("Back to the default angle (R)."))
        tools.addWidget(self.plan_button)
        tools.addWidget(fit)
        tools.addWidget(reset)
        tools.addSpacing(12)
        self.layer_boxes: dict[str, QCheckBox] = {}
        for layer in (LAYER_ENTERED, LAYER_MEASURED, LAYER_ASSUMED):
            box = QCheckBox(_(LAYER_NAMES[layer]))
            box.setChecked(True)
            box.toggled.connect(self._layers_changed)
            tools.addWidget(box)
            self.layer_boxes[layer] = box
        tools.addStretch(1)
        self.import_button = QPushButton(_("Import scan..."))
        self.import_button.clicked.connect(self.import_scan)
        self.example_button = QPushButton(_("Example room"))
        self.example_button.setToolTip(
            _(
                "Fill in a 5 x 4 x 2.7 m example to try the view; a room already entered "
                "is replaced only after you confirm."
            )
        )
        self.example_button.clicked.connect(self.use_example)
        tools.addWidget(self.import_button)
        tools.addWidget(self.example_button)
        layout.addLayout(tools)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.canvas = RoomCanvas()
        fit.clicked.connect(self.canvas.fit)
        reset.clicked.connect(self.canvas.reset)
        self.canvas.device_clicked.connect(self._device_clicked)
        self.canvas.device_moved.connect(self._device_moved)
        self.canvas.face_clicked.connect(self._face_clicked)
        splitter.addWidget(self.canvas)

        side = QWidget()
        side_layout = QVBoxLayout(side)
        side_layout.setContentsMargins(6, 0, 0, 0)
        side_layout.setSpacing(6)
        self.room_box = QGroupBox(_("Room box (inside, metres)"))
        self.room_box.setCheckable(True)
        self.room_box.setChecked(False)
        room_form = QFormLayout(self.room_box)
        room_form.setContentsMargins(6, 4, 6, 4)
        self.length_spin = _spin(200.0)
        self.width_spin = _spin(200.0)
        self.height_spin = _spin(200.0)
        room_form.addRow(_("Length (x)"), self.length_spin)
        room_form.addRow(_("Width (y)"), self.width_spin)
        room_form.addRow(_("Height (z)"), self.height_spin)
        side_layout.addWidget(self.room_box)
        self.source_box = _PointBox(_("Loudspeaker"))
        side_layout.addWidget(self.source_box)
        self.mic_box = _PointBox(_("Microphone"))
        side_layout.addWidget(self.mic_box)
        self.save_status = label("", "hint", wrap=True)
        side_layout.addWidget(self.save_status)
        side_layout.addWidget(label(_("Early reflections").upper(), "section"))
        self.reflections = QTableWidget(0, 3)
        self.reflections.setHorizontalHeaderLabels([_("Delay (ms)"), _("Level (dB)"), _("Match")])
        self.reflections.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.reflections.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.reflections.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.reflections.verticalHeader().setVisible(False)
        self.reflections.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.reflections.setMinimumHeight(110)
        self.reflections.itemSelectionChanged.connect(self._table_selected)
        side_layout.addWidget(self.reflections)
        self.notes = label("", "hint", wrap=True)
        side_layout.addWidget(self.notes)
        side_layout.addWidget(label(_("Placement").upper(), "section"))
        self.placement_summary = label("", "hint", wrap=True)
        side_layout.addWidget(self.placement_summary)
        self.placement_table = QTableWidget(0, 3)
        self.placement_table.setHorizontalHeaderLabels([_("Figure"), _("Value"), _("Validity")])
        self.placement_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.placement_table.verticalHeader().setVisible(False)
        self.placement_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        side_layout.addWidget(self.placement_table)
        self.candidates = QTableWidget(0, 4)
        self.candidates.setHorizontalHeaderLabels(
            [_("Delay (ms)"), _("Excess path (m)"), _("Surface"), _("Plane?")]
        )
        self.candidates.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.candidates.verticalHeader().setVisible(False)
        side_layout.addWidget(self.candidates)
        side_layout.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidget(side)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setMinimumWidth(250)
        splitter.addWidget(scroll)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter, 1)

        for spin in (self.length_spin, self.width_spin, self.height_spin):
            spin.valueChanged.connect(self._edited)
        self.room_box.toggled.connect(self._edited)
        for point_box in (self.source_box, self.mic_box):
            point_box.toggled.connect(self._edited)
            for spin in point_box.spins():
                spin.valueChanged.connect(self._edited)
        for signal in (model.current_changed, model.entries_changed, model.project_changed):
            signal.connect(self._follow_model)
        model.reflection_changed.connect(lambda *_a: self.refresh())
        self._follow_model()

    def title(self) -> str:
        return _("Room")

    # --- where the geometry lives -----------------------------------------------------

    def target_directory(self) -> Path | None:
        if self.model.project_path is not None:
            return self.model.project_path
        entry = self.model.current()
        return entry.directory if entry is not None else None

    def _follow_model(self, *_args: object) -> None:
        directory = self.target_directory()
        if directory != self.directory:
            if self._save_timer.isActive():
                self._save_timer.stop()
                self.save()
            self.load(directory)
        self.refresh()
        self._emit_checks()

    def load(self, directory: Path | None) -> None:
        self.directory = directory
        self._generation += 1
        self._scan_points = None
        self._stop_scan_loader()
        geometry = RoomGeometry()
        message = ""
        self._read_only = False
        if directory is not None:
            try:
                geometry = load_geometry(directory) or RoomGeometry()
            except GeometryError as exc:
                self._read_only = True
                message = _("Cannot read the room file: {error}").format(error=localize(str(exc)))
                message += " " + _("It is not overwritten; changes here are not saved.")
        self.room_geometry = geometry
        if geometry.scan is not None and directory is not None:
            path = directory / geometry.scan.file
            if path.is_file():
                loader = ScanLoader(self._generation, path, geometry)
                loader.loaded.connect(self._scan_loaded)
                loader.failed.connect(self._scan_failed)
                self._scan_loader = loader
                loader.start()
            else:
                message = _("The scan {name} is not in {folder}.").format(
                    name=geometry.scan.file, folder=directory
                )
        self._fill_inputs()
        self._set_save_status(message)
        self.canvas.set_scene(self._scene(), refit=True)

    def _set_save_status(self, message: str = "") -> None:
        if message:
            set_banner_text(self.save_status, message, "warn")
            return
        if self.directory is None:
            text = _("Not saved: open a project or a saved session to keep the room.")
        elif self.room_geometry.newer:
            text = _("Written by a newer ReverbScope: shown, but not overwritten.")
        else:
            text = _("Saved in {path}").format(path=self.directory / "room-geometry.json")
        set_banner_text(self.save_status, text)

    # --- inputs -----------------------------------------------------------------------

    def _fill_inputs(self) -> None:
        self._filling = True
        box = self.room_geometry.room
        self.room_box.setChecked(box is not None)
        if box is not None:
            self.length_spin.setValue(box.length_m)
            self.width_spin.setValue(box.width_m)
            self.height_spin.setValue(box.height_m)
        self.source_box.set_point(self.room_geometry.source)
        position = position_of(self.model.current())
        self.mic_box.setTitle(_("Microphone at {position}").format(position=position))
        self.mic_box.set_point(self.room_geometry.microphone(position))
        self._filling = False

    def _edited(self, *_args: object) -> None:
        if self._filling:
            return
        try:
            geometry = self._geometry_from_inputs()
        except GeometryError as exc:
            set_banner_text(self.save_status, localize(str(exc)), "warn")
            return
        self.room_geometry = geometry
        self.refresh()
        self._emit_checks()
        if self._writable():
            self._save_timer.start()

    def _geometry_from_inputs(self) -> RoomGeometry:
        room = None
        if (
            self.room_box.isChecked()
            and min(self.length_spin.value(), self.width_spin.value(), self.height_spin.value()) > 0
        ):
            room = RoomBox(
                self.length_spin.value(), self.width_spin.value(), self.height_spin.value()
            )
        geometry = replace(self.room_geometry, room=room, source=self.source_box.point())
        position = position_of(self.model.current())
        mic = self.mic_box.point()
        if mic is None:
            return without_microphone(geometry, position)
        return with_microphone(geometry, position, mic)

    def _writable(self) -> bool:
        return self.directory is not None and not self._read_only and not self.room_geometry.newer

    def save(self) -> bool:
        if self.directory is None or not self._writable():
            return False
        try:
            save_geometry(self.directory, self.room_geometry)
        except GeometryError as exc:
            set_banner_text(
                self.save_status,
                _("Cannot save the room: {error}").format(error=localize(str(exc))),
                "warn",
            )
            return False
        self._set_save_status()
        return True

    def use_example(self) -> None:
        entered = self.room_geometry.room is not None or self.room_geometry.source is not None
        if entered and self._writable() and not self._confirm_example():
            return
        example = example_room()
        position = position_of(self.model.current())
        mic = example.microphone("A")
        assert mic is not None
        self.room_geometry = replace(
            self.room_geometry,
            room=example.room,
            source=example.source,
            microphones={**dict(self.room_geometry.microphones), position: mic},
        )
        self._fill_inputs()
        self._edited()
        self.canvas.fit()

    def _confirm_example(self) -> bool:
        assert self.directory is not None
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle(_("Example room"))
        box.setText(_("Replace the room and loudspeaker entered here with the example?"))
        box.setInformativeText(
            _("The example is saved in {path}.").format(path=self.directory / "room-geometry.json")
        )
        replace_button = box.addButton(_("Replace"), QMessageBox.ButtonRole.AcceptRole)
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.exec()
        return box.clickedButton() is replace_button

    def import_scan(self) -> None:
        from reverbscope.ui.room.scan_import import ScanImportDialog

        dialog = ScanImportDialog(str(self.directory or ""), self)
        if not dialog.exec():
            return
        placed = dialog.placement()
        if placed is None:
            return
        reference, points = placed
        self.room_geometry = replace(self.room_geometry, scan=reference)
        self._scan_points = voxel_thin(np.asarray(points), SCAN_VOXEL_M, SCAN_DISPLAY_POINTS)
        source = Path(dialog.path.text())
        if self.directory is not None and source.parent.resolve() != self.directory.resolve():
            set_banner_text(
                self.save_status,
                _("Copy {name} into {folder} so the room opens with its scan next time.").format(
                    name=source.name, folder=self.directory
                ),
                "warn",
            )
        if self._writable():
            self._save_timer.start()
        self.canvas.set_scene(self._scene(), refit=True)

    def _scan_loaded(self, generation: int, points: object) -> None:
        if generation != self._generation:
            return
        self._scan_points = np.asarray(points)
        self.canvas.set_scene(self._scene(), refit=True)

    def _scan_failed(self, generation: int, message: str) -> None:
        if generation == self._generation:
            set_banner_text(self.save_status, message, "warn")

    # --- the scene --------------------------------------------------------------------

    def _layers(self) -> dict[str, bool]:
        return {layer: box.isChecked() for layer, box in self.layer_boxes.items()}

    def _layers_changed(self, _checked: bool) -> None:
        self.canvas.scene.layers = self._layers()
        self.canvas.update()

    def _toggle_plan(self, plan: bool) -> None:
        self.canvas.set_plan(plan)

    def _scene(self) -> RoomScene:
        entry = self.model.current()
        position = position_of(entry)
        scene = RoomScene(
            box=self.room_geometry.room,
            source=self.room_geometry.source,
            microphones=dict(self.room_geometry.microphones),
            current_microphone=position,
            scan_points=self._scan_points,
            layers=self._layers(),
        )
        result = entry.result if entry is not None else None
        self._predicted = []
        if result is None:
            return scene
        speed, _temperature, _assumed = speed_for(result)
        if self.room_geometry.room is not None:
            try:
                self._predicted = predict_first_order(self.room_geometry, position, speed)
            except GeometryError:
                self._predicted = []
        scene.predicted = self._predicted
        if overlay_refusal(result) is not None:
            return scene
        loopback = result.impulse_response.loopback
        if (
            self.room_geometry.source is not None
            and loopback is not None
            and loopback.path_delay_ms is not None
        ):
            scene.sphere = (self.room_geometry.source, loopback.path_delay_ms / 1000.0 * speed)
        key, index = self.model.selected_reflection()
        mic = self.room_geometry.microphone(position)
        scene.placement_ring = placement_ring(result.placement, mic)
        if (
            entry is not None
            and key == entry.key
            and 0 <= index < len(result.reflections.reflections)
        ):
            reflection = result.reflections.reflections[index]
            distance = direct_distance(self.room_geometry, position)
            constraint = constraint_for(reflection.delay_ms, distance, speed)
            if (
                constraint.semi_major_m is not None
                and self.room_geometry.source is not None
                and mic is not None
            ):
                scene.ellipsoid = (self.room_geometry.source, mic, constraint.semi_major_m)
            if self._predicted:
                match = match_reflection(
                    reflection.delay_ms,
                    self._predicted,
                    tolerance_ms(result.sample_rate, speed),
                )
                scene.highlighted_faces = {path.face for path, _r in match.candidates}
        return scene

    def redraw(self) -> None:
        entry = self.model.current()
        self._fill_inputs()
        scene = self._scene()
        self.canvas.empty_text = (
            ""
            if scene.box is not None or scene.source is not None or scene.microphones
            else _(
                "Enter the room box and the device positions on the right, import a scan, or "
                "try the example room."
            )
        )
        self.canvas.set_scene(scene)
        self._fill_reflections(entry)
        self._fill_notes(entry)
        self._fill_placement(entry.result.placement if entry and entry.result else None)

    def _fill_reflections(self, entry: Entry | None) -> None:
        result = entry.result if entry is not None else None
        table = self.reflections
        table.blockSignals(True)
        reflections = result.reflections.reflections if result is not None else ()
        table.setRowCount(len(reflections))
        speed = speed_for(result)[0] if result is not None else 343.0
        tolerance = tolerance_ms(result.sample_rate, speed) if result is not None else 0.0
        for row, reflection in enumerate(reflections):
            match_text = ""
            if self._predicted and self.room_geometry.room is not None:
                match = match_reflection(reflection.delay_ms, self._predicted, tolerance)
                match_text = match.text(self.room_geometry.room)
            for column, text in enumerate(
                (f"{reflection.delay_ms:.2f}", f"{reflection.relative_db:.1f}", match_text)
            ):
                item = QTableWidgetItem(text)
                item.setToolTip(text)
                table.setItem(row, column, item)
        key, index = self.model.selected_reflection()
        if entry is not None and key == entry.key and 0 <= index < len(reflections):
            table.selectRow(index)
        else:
            table.clearSelection()
        table.blockSignals(False)

    def _fill_notes(self, entry: Entry | None) -> None:
        notes = [_(SINGLE_MICROPHONE_NOTE)]
        result = entry.result if entry is not None else None
        if result is not None:
            refusal = overlay_refusal(result)
            if refusal is not None:
                notes.append(_("Measured layer withheld: {reason}.").format(reason=refusal))
            key, index = self.model.selected_reflection()
            if (
                entry is not None
                and key == entry.key
                and 0 <= index < len(result.reflections.reflections)
                and refusal is None
            ):
                reflection = result.reflections.reflections[index]
                speed, _t, _a = speed_for(result)
                constraint = constraint_for(
                    reflection.delay_ms,
                    direct_distance(self.room_geometry, position_of(entry)),
                    speed,
                )
                notes.append(constraint.text)
        elif entry is None:
            notes.append(_("Select a measurement to draw what it constrains."))
        self.notes.setText("\n".join(notes))

    def _fill_placement(self, placement: PlacementResult | None) -> None:
        if placement is None:
            self.placement_summary.setText(
                _("No placement result. Add a loudspeaker distance to raise the tier.")
            )
            self.placement_table.setRowCount(0)
            self.candidates.setRowCount(0)
            return
        assumed = _(" (assumed)") if placement.temperature_assumed else ""
        self.placement_summary.setText(
            _(
                "Placement tier {tier}. No coordinates, room length, room width or "
                "named wall are derived. Speed of sound {speed:.1f} m/s at "
                "{temp:.0f} °C{assumed}."
            ).format(
                tier=placement.tier,
                speed=placement.speed_of_sound_m_s,
                temp=placement.temperature_c,
                assumed=assumed,
            )
            + " "
            + self._ring_note(placement)
        )
        rows = [
            (_("Loudspeaker height"), placement.source_height_m),
            (_("Plane above the devices"), placement.ceiling_height_m),
            (_("Horizontal separation"), placement.horizontal_separation_m),
        ]
        self.placement_table.setRowCount(len(rows))
        for index, (caption, length) in enumerate(rows):
            if length.metres is None:
                value = _("not determined")
            else:
                value = f"{length.metres:.2f} m"
                if length.input_uncertainty_m is not None:
                    value += f" ±{length.input_uncertainty_m:.2f}"
            for column, text in enumerate((caption, value, validity_word(length.validity))):
                item = QTableWidgetItem(text)
                if column == 0 and length.reason:
                    item.setToolTip(localize(length.reason))
                self.placement_table.setItem(index, column, item)
        self.candidates.setRowCount(len(placement.candidates))
        for index, candidate in enumerate(placement.candidates):
            plane = _("yes") if candidate.interpretable_as_plane else _("no")
            if candidate.interpretable_as_plane is None:
                plane = _("untested")
            values = (
                f"{candidate.delay_ms:.2f}",
                f"{candidate.excess_path_m:.2f}",
                surface_text(candidate.surface),
                plane,
            )
            for column, text in enumerate(values):
                self.candidates.setItem(index, column, QTableWidgetItem(text))

    def _ring_note(self, placement: PlacementResult) -> str:
        far = Point(0.0, 0.0, 0.0)
        if placement_ring(placement, far) is None:
            return ""
        mic = self.room_geometry.microphone(position_of(self.model.current()))
        if mic is None:
            return _(
                "Enter this position's microphone to see the ring of loudspeaker "
                "positions the measurement allows."
            )
        return _(
            "The thick dashed ring is every loudspeaker position the measurement "
            "allows; one microphone cannot say where on it the loudspeaker is."
        )

    # --- linking ----------------------------------------------------------------------

    def _table_selected(self) -> None:
        entry = self.model.current()
        rows = {index.row() for index in self.reflections.selectedIndexes()}
        if entry is None or not rows:
            return
        self.model.select_reflection(entry.key, rows.pop())

    def _face_clicked(self, face: str) -> None:
        """A predicted point was clicked: select the measured reflection that matches it."""
        entry = self.model.current()
        if entry is None or entry.result is None:
            return
        speed, _t, _a = speed_for(entry.result)
        tolerance = tolerance_ms(entry.result.sample_rate, speed)
        for index, reflection in enumerate(entry.result.reflections.reflections):
            match = match_reflection(reflection.delay_ms, self._predicted, tolerance)
            if any(path.face == face for path, _r in match.candidates):
                self.model.select_reflection(entry.key, index)
                return
        set_banner_text(
            self.save_status,
            _("No detected reflection matches the predicted path off this face."),
        )

    def _device_clicked(self, name: str, point: object) -> None:
        assert isinstance(point, Point)
        who = (
            _("Loudspeaker")
            if name == "source"
            else _("Microphone {position}").format(position=name)
        )
        set_banner_text(
            self.save_status,
            _("{who}: x = {x:.2f} m, y = {y:.2f} m, z = {z:.2f} m").format(
                who=who, x=point.x, y=point.y, z=point.z
            ),
        )

    def _device_moved(self, name: str, point: object) -> None:
        assert isinstance(point, Point)
        if name == "source":
            self.room_geometry = replace(self.room_geometry, source=point)
        else:
            self.room_geometry = with_microphone(self.room_geometry, name, point)
        self._fill_inputs()
        self._edited()

    # --- inspector and lifetime -----------------------------------------------------------

    def checks(self) -> tuple[list[Any], str]:
        entry = self.model.current()
        if entry is None or entry.result is None:
            return [], ""
        result: AnalysisResult = entry.result
        if self.room_geometry.room is None and self.room_geometry.source is None:
            return [], ""
        note = _(SINGLE_MICROPHONE_NOTE)
        return consistency_checks(result, self.room_geometry, position_of(entry)), note

    def _emit_checks(self) -> None:
        checks, note = self.checks()
        self.checks_changed.emit(checks, note)

    def _stop_scan_loader(self) -> None:
        if self._scan_loader is not None and self._scan_loader.isRunning():
            self._scan_loader.requestInterruption()
            self._old_loaders.append(self._scan_loader)
        self._scan_loader = None
        self._old_loaders = [loader for loader in self._old_loaders if loader.isRunning()]

    def shutdown(self) -> None:
        if self._save_timer.isActive():
            self._save_timer.stop()
            self.save()
        loaders = [*self._old_loaders, *([self._scan_loader] if self._scan_loader else [])]
        for loader in loaders:
            loader.requestInterruption()
        for loader in loaders:
            loader.wait()
        self._old_loaders.clear()
        self._scan_loader = None
