"""Importing a room scan (PLY or OBJ): a worker thread and its dialog.

The file is read off the GUI thread with a size limit, a vertex limit and
cancellation (``geometry.scan.read_scan``). Scans record neither their units
nor which axis is up, so the dialog asks, together with the yaw and how the
scan is placed in the room. The choice is stored with the file's SHA-256 in
``room-geometry.json``.
"""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from reverbscope.geometry.room import SCAN_UNITS, UP_AXES, Point, ScanReference
from reverbscope.geometry.scan import (
    MAX_SCAN_BYTES,
    MAX_SCAN_VERTICES,
    ScanCancelledError,
    ScanError,
    ScanMesh,
    align_to_floor_corner,
    place_scan,
    read_scan,
)
from reverbscope.i18n import _, localize
from reverbscope.ui.widgets import label, set_banner_text

log = logging.getLogger(__name__)


class ScanWorker(QThread):
    """Reads one scan; ``finished_reading`` carries the mesh or an error text."""

    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, path: Path) -> None:
        super().__init__()
        self.path = path

    def run(self) -> None:
        try:
            mesh = read_scan(self.path, cancelled=self.isInterruptionRequested)
        except ScanCancelledError:
            return
        except ScanError as exc:
            self.failed.emit(localize(str(exc)))
            return
        except Exception:
            log.exception("reading scan %s failed unexpectedly", self.path)
            from reverbscope.ui.workers import unexpected_error_text

            self.failed.emit(unexpected_error_text())
            return
        if not self.isInterruptionRequested():
            self.succeeded.emit(mesh)


class ScanImportDialog(QDialog):
    """Choose a file, read it in the background, then set units, axis, yaw, placement."""

    def __init__(self, start_dir: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(_("Import a room scan"))
        self.mesh: ScanMesh | None = None
        self._worker: ScanWorker | None = None
        layout = QVBoxLayout(self)
        layout.addWidget(
            label(
                _(
                    "PLY or OBJ, up to {megabytes} MB and {vertices:,} vertices. The scan is "
                    "drawn as entered geometry; nothing is measured from it."
                ).format(megabytes=MAX_SCAN_BYTES // (1024 * 1024), vertices=MAX_SCAN_VERTICES),
                "hint",
                wrap=True,
            )
        )
        row = QHBoxLayout()
        self.path = QLineEdit()
        self.path.setReadOnly(True)
        browse = QPushButton(_("Choose file..."))
        browse.clicked.connect(lambda: self._browse(start_dir))
        row.addWidget(self.path, 1)
        row.addWidget(browse)
        layout.addLayout(row)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.hide()
        layout.addWidget(self.progress)
        self.status = label("", "hint", wrap=True)
        layout.addWidget(self.status)
        form = QFormLayout()
        self.units = QComboBox()
        for unit in SCAN_UNITS:
            self.units.addItem(unit, unit)
        self.up_axis = QComboBox()
        for axis in UP_AXES:
            self.up_axis.addItem(axis, axis)
        self.yaw = QDoubleSpinBox()
        self.yaw.setRange(-180.0, 180.0)
        self.yaw.setSuffix(" °")
        self.align = QCheckBox(_("Put the scan's lowest corner on the room's floor corner"))
        self.align.setChecked(True)
        form.addRow(_("Units in the file"), self.units)
        form.addRow(_("Up axis in the file"), self.up_axis)
        form.addRow(_("Turn about the vertical"), self.yaw)
        form.addRow(self.align)
        layout.addLayout(form)
        self.buttons = QDialogButtonBox()
        self.ok_button = self.buttons.addButton(_("Import"), QDialogButtonBox.ButtonRole.AcceptRole)
        self.ok_button.setEnabled(False)
        cancel = self.buttons.addButton(_("Cancel"), QDialogButtonBox.ButtonRole.RejectRole)
        self.buttons.accepted.connect(self.accept)
        cancel.clicked.connect(self.reject)
        layout.addWidget(self.buttons)

    # --- reading --------------------------------------------------------------------------

    def _browse(self, start_dir: str) -> None:
        path, _filter = QFileDialog.getOpenFileName(
            self, _("Import a room scan"), start_dir, _("Room scans (*.ply *.obj)")
        )
        if path:
            self.read(Path(path))

    def read(self, path: Path) -> None:
        self.stop()
        self.mesh = None
        self.ok_button.setEnabled(False)
        self.path.setText(str(path))
        self.progress.show()
        set_banner_text(self.status, _("Reading {name}...").format(name=path.name))
        worker = ScanWorker(path)
        worker.succeeded.connect(self._read)
        worker.failed.connect(self._failed)
        worker.finished.connect(self.progress.hide)
        self._worker = worker
        worker.start()

    def _read(self, mesh: object) -> None:
        if self.sender() is not self._worker or not isinstance(mesh, ScanMesh):
            return
        self.mesh = mesh
        self.ok_button.setEnabled(True)
        faces = 0 if mesh.faces is None else len(mesh.faces)
        set_banner_text(
            self.status,
            _("{vertices:,} vertices, {faces:,} triangles. {note}").format(
                vertices=len(mesh.vertices), faces=faces, note=mesh.source_units_note
            ),
        )

    def _failed(self, message: str) -> None:
        if self.sender() is not self._worker:
            return
        set_banner_text(
            self.status, _("Cannot import the scan: {error}").format(error=message), "warn"
        )

    def stop(self) -> None:
        """Cancel a read and wait for the thread: one destroyed while it runs aborts."""
        if self._worker is not None:
            self._worker.requestInterruption()
            self._worker.wait()

    def done(self, result: int) -> None:
        self.stop()
        super().done(result)

    # --- result ---------------------------------------------------------------------------

    def placement(self) -> tuple[ScanReference, object] | None:
        """The reference to store and the placed vertices (room metres)."""
        if self.mesh is None:
            return None
        units = str(self.units.currentData())
        up = str(self.up_axis.currentData())
        yaw = float(self.yaw.value())
        placed = place_scan(
            self.mesh.vertices, units=units, up_axis=up, yaw_deg=yaw, offset=Point(0.0, 0.0, 0.0)
        )
        offset = align_to_floor_corner(placed) if self.align.isChecked() else Point(0.0, 0.0, 0.0)
        placed = place_scan(self.mesh.vertices, units=units, up_axis=up, yaw_deg=yaw, offset=offset)
        reference = ScanReference(
            file=Path(self.path.text()).name,
            units=units,
            up_axis=up,
            yaw_deg=yaw,
            offset=offset,
            sha256=self.mesh.sha256,
        )
        return reference, placed
