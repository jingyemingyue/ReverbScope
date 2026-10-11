"""The workspace document: every measurement open in the workbench, and the
three states the workbench keeps apart.

* the **selected** measurement: the one whose properties, diagnostics and
  tables are shown, and whose curve is drawn on top;
* the **visible** measurements: those whose curves are drawn (a checkbox
  in the measurement list; selecting one never hides another);
* the **baseline**: the measurement the selected one is compared against.

A measurement keeps its session, its result, its findings and its health
report together, plus what the workbench needs to save it again (a live
take's recording until it is on disk). Nothing here computes a metric or
judges a number: the result, :func:`reverbscope.health.assess` and the
recording profile do that; the document only holds them.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from reverbscope.core.pipeline import Reference
from reverbscope.demo import DEMO_MODE, localize_demo_name
from reverbscope.health import HealthReport, HealthStatus, assess
from reverbscope.i18n import _
from reverbscope.interpretation import Finding
from reverbscope.models.audio import AudioSignal
from reverbscope.models.result import AnalysisResult
from reverbscope.models.session import MeasurementSession
from reverbscope.ui.theme import PLOT_SERIES

#: Curve colours, one per measurement in the order they are opened; distinct
#: in both colour schemes. After the last one the palette starts again and
#: the line style tells the repeats apart (see :func:`line_style`).
MEASUREMENT_COLOURS: tuple[str, ...] = (
    *PLOT_SERIES[:5],
    "#1f5fa8",
    "#9c6b2f",
    "#2a9d8f",
    "#b5473d",
    "#5f6f8a",
)
_LINE_STYLES = ("-", "--", "-.", ":")


def line_style(colour_index: int) -> str:
    """Solid for the first pass through the palette, dashed for the next."""
    return _LINE_STYLES[(colour_index // len(MEASUREMENT_COLOURS)) % len(_LINE_STYLES)]


@dataclass
class Measurement:
    """One measurement open in the workbench.

    ``path`` is the session folder it was opened from or saved to, ``None``
    while it exists only in memory. ``recording`` is a live take's audio
    until the session is saved (``unsaved_take``); a recording imported from
    a file keeps its ``recording_path`` instead and needs no copy.
    """

    session: MeasurementSession
    result: AnalysisResult
    findings: list[Finding] = field(default_factory=list)
    #: Why there are no findings: the recording profile failed.
    findings_problem: str = ""
    profile: str = "generic"
    health: HealthReport | None = None
    path: Path | None = None
    recording: AudioSignal | None = None
    recording_path: Path | None = None
    reference: Reference | None = None
    unsaved_take: bool = False
    #: The project folder the measurement belongs to (opened from it, or to be
    #: listed in it when saved) and the position label it is listed under.
    project: Path | None = None
    position: str = ""
    colour_index: int = 0
    id: str = field(default_factory=lambda: uuid.uuid4().hex)

    def __post_init__(self) -> None:
        if self.health is None:
            self.health = assess(self.result)
        if not self.position:
            self.position = self.session.measurement_position.strip()

    @property
    def colour(self) -> str:
        return MEASUREMENT_COLOURS[self.colour_index % len(MEASUREMENT_COLOURS)]

    @property
    def style(self) -> str:
        return line_style(self.colour_index)

    @property
    def synthetic(self) -> bool:
        """Synthetic data (the fake backend or ``reverbscope demo``): never a room."""
        return self.session.mode == DEMO_MODE

    @property
    def status(self) -> HealthStatus:
        assert self.health is not None
        return self.health.overall

    @property
    def unsaved(self) -> bool:
        """Not on disk yet: a live take, or an analysed import never saved."""
        return self.path is None

    def name(self) -> str:
        """Room and position, or the folder name, or a stand-in."""
        session = self.session
        room = localize_demo_name(session.mode, session.room_name).strip()
        position = localize_demo_name(session.mode, self.position).strip()
        if room and position:
            return f"{room} / {position}"
        if room:
            return room
        if position:
            return position
        if self.path is not None:
            return self.path.name
        return _("Unnamed measurement")

    def group_label(self) -> str:
        """The row the measurement list groups it under."""
        position = localize_demo_name(self.session.mode, self.position).strip()
        return position or _("No position")


class WorkspaceDocument(QObject):
    """The open measurements with the selected, visible and baseline states.

    Signals carry measurement ids (``str``); ``None`` means no measurement
    where an id is optional. Every mutation goes through a method here so the
    list, the charts and the inspector see the same state.
    """

    measurement_added = Signal(str)
    measurement_removed = Signal(str)
    #: The measurement's contents changed (saved, renamed, listed in a project).
    measurement_changed = Signal(str)
    selection_changed = Signal(object)
    visibility_changed = Signal(str, bool)
    baseline_changed = Signal(object)
    project_changed = Signal(object)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._measurements: list[Measurement] = []
        self._selected: str | None = None
        self._visible: set[str] = set()
        self._baseline: str | None = None
        self._project: Path | None = None
        self._project_name: str = ""

    # --- the list -------------------------------------------------------------------

    @property
    def measurements(self) -> list[Measurement]:
        return list(self._measurements)

    def __len__(self) -> int:
        return len(self._measurements)

    def get(self, measurement_id: str | None) -> Measurement | None:
        if measurement_id is None:
            return None
        return next((m for m in self._measurements if m.id == measurement_id), None)

    def index_of(self, measurement_id: str) -> int:
        return next((i for i, m in enumerate(self._measurements) if m.id == measurement_id), -1)

    def find_by_path(self, path: Path) -> Measurement | None:
        """The measurement opened from ``path`` (a session folder), if any."""
        wanted = _canonical(path)
        return next(
            (m for m in self._measurements if m.path is not None and _canonical(m.path) == wanted),
            None,
        )

    def at_path(self, path: Path) -> list[Measurement]:
        """Every measurement opened from or saved to ``path``, in list order."""
        wanted = _canonical(path)
        return [
            m for m in self._measurements if m.path is not None and _canonical(m.path) == wanted
        ]

    def add(self, measurement: Measurement, *, select: bool = True, visible: bool = True) -> str:
        """Add ``measurement``; it gets the lowest colour no open measurement
        uses (a closed measurement's colour is free again) and, by default,
        becomes the selected one and is drawn. The others stay as they are."""
        used = {m.colour_index for m in self._measurements}
        colour_index = 0
        while colour_index in used:
            colour_index += 1
        measurement.colour_index = colour_index
        self._measurements.append(measurement)
        if visible:
            self._visible.add(measurement.id)
        self.measurement_added.emit(measurement.id)
        if visible:
            self.visibility_changed.emit(measurement.id, True)
        if select:
            self.set_selected(measurement.id)
        return measurement.id

    def remove(self, measurement_id: str) -> None:
        index = self.index_of(measurement_id)
        if index < 0:
            return
        del self._measurements[index]
        self._visible.discard(measurement_id)
        if self._baseline == measurement_id:
            self._baseline = None
            self.baseline_changed.emit(None)
        if self._selected == measurement_id:
            # The nearest neighbour takes the selection, as in a file list;
            # with nothing left the selection is announced as gone.
            neighbour = (
                self._measurements[min(index, len(self._measurements) - 1)].id
                if self._measurements
                else None
            )
            self._selected = None
            self.measurement_removed.emit(measurement_id)
            if neighbour is None:
                self.selection_changed.emit(None)
            else:
                self.set_selected(neighbour)
            return
        self.measurement_removed.emit(measurement_id)

    def clear(self) -> None:
        for measurement in list(self._measurements):
            self.remove(measurement.id)

    def touch(self, measurement_id: str) -> None:
        """Say that a measurement's contents changed (saved, listed)."""
        if self.get(measurement_id) is not None:
            self.measurement_changed.emit(measurement_id)

    # --- the three states ---------------------------------------------------------

    def selected(self) -> Measurement | None:
        return self.get(self._selected)

    def selected_id(self) -> str | None:
        return self._selected

    def set_selected(self, measurement_id: str | None) -> None:
        if measurement_id is not None and self.get(measurement_id) is None:
            measurement_id = None
        if measurement_id == self._selected:
            return
        self._selected = measurement_id
        self.selection_changed.emit(measurement_id)

    def is_visible(self, measurement_id: str) -> bool:
        return measurement_id in self._visible

    def set_visible(self, measurement_id: str, visible: bool) -> None:
        if self.get(measurement_id) is None or visible == (measurement_id in self._visible):
            return
        if visible:
            self._visible.add(measurement_id)
        else:
            self._visible.discard(measurement_id)
        self.visibility_changed.emit(measurement_id, visible)

    def visible(self) -> list[Measurement]:
        """The measurements whose curves are drawn, in list order."""
        return [m for m in self._measurements if m.id in self._visible]

    def baseline(self) -> Measurement | None:
        return self.get(self._baseline)

    def baseline_id(self) -> str | None:
        return self._baseline

    def set_baseline(self, measurement_id: str | None) -> None:
        if measurement_id is not None and self.get(measurement_id) is None:
            measurement_id = None
        if measurement_id == self._baseline:
            return
        self._baseline = measurement_id
        self.baseline_changed.emit(measurement_id)

    def candidate(self) -> Measurement | None:
        """The selected measurement when a baseline is set and it is another one."""
        selected = self.selected()
        if selected is None or self._baseline is None or selected.id == self._baseline:
            return None
        return selected

    # --- the project --------------------------------------------------------------

    @property
    def project(self) -> Path | None:
        return self._project

    @property
    def project_name(self) -> str:
        return self._project_name

    def set_project(self, path: Path | None, name: str = "") -> None:
        self._project = path
        self._project_name = name
        self.project_changed.emit(path)

    # --- saving -------------------------------------------------------------------

    def unsaved(self) -> list[Measurement]:
        """Measurements that exist only in memory (a live take among them)."""
        return [m for m in self._measurements if m.unsaved]

    def unsaved_takes(self) -> list[Measurement]:
        """Live takes whose only recording is in memory: closing loses them."""
        return [m for m in self._measurements if m.unsaved_take]

    def mark_saved(self, measurement_id: str, directory: Path) -> None:
        measurement = self.get(measurement_id)
        if measurement is None:
            return
        measurement.path = directory
        measurement.unsaved_take = False
        measurement.recording = None
        self.measurement_changed.emit(measurement_id)


def _canonical(path: Path) -> Path:
    try:
        return path.resolve()
    except OSError:
        return path
