"""The workspace model: what is open, what is selected, what is drawn together.

One :class:`WorkspaceModel` per window owns every open measurement
(:class:`Entry`), the current one, the overlay set, the comparison
baseline, each entry's colour and the selected early reflection. The
navigator, the inspector and every view read it and send requests to it;
none of them holds a measurement of its own, so switching views keeps the
selection and the chart state. See docs/design/GUI_2_ARCHITECTURE.md §3.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QThread, Signal

from reverbscope.errors import ReverbScopeError
from reverbscope.i18n import _, localize
from reverbscope.interpretation import Finding, available_profiles, interpret
from reverbscope.models.project import Project
from reverbscope.models.result import AnalysisResult
from reverbscope.models.session import MeasurementSession

log = logging.getLogger(__name__)

#: One colour per entry, kept for the entry's life: Okabe–Ito-like hues that
#: stay apart for colour-blind readers and readable on light and dark charts.
ENTRY_COLORS = (
    "#177e89",
    "#e07a2e",
    "#7a5cc7",
    "#3f9c4a",
    "#c2437a",
    "#3b73c4",
    "#a88a12",
    "#7d8590",
)

#: Prefix of the key of a take that has no folder yet.
TAKE_PREFIX = "take:"


def safe_findings(result: AnalysisResult, profile: str) -> tuple[list[Finding], str]:
    """The findings for ``result``, or none and the reason why.

    A recording profile that fails (a third-party one from an entry point)
    must not stop the result from being shown: the page stayed busy for good
    and the measurement was never seen.
    """
    from reverbscope.ui.workers import unexpected_error_text

    try:
        return interpret(result, profile), ""
    except ReverbScopeError as exc:
        return [], localize(str(exc))
    except Exception:
        log.exception("recording profile %r failed to interpret the result", profile)
        return [], unexpected_error_text()


def usable_profile(session: MeasurementSession | None) -> str:
    """The session's recording profile, or ``generic`` when this install lacks it."""
    profile = (session.recording_profile if session is not None else "") or "generic"
    return profile if profile in available_profiles() else "generic"


@dataclass
class Entry:
    """One open measurement."""

    key: str
    directory: Path | None
    session: MeasurementSession | None
    result: AnalysisResult | None
    position: str = ""
    findings: list[Finding] = field(default_factory=list)
    findings_problem: str = ""
    profile: str = "generic"
    color: str = ENTRY_COLORS[0]
    #: Index of :attr:`color` in :data:`ENTRY_COLORS`; also picks a dash pattern.
    color_index: int = 0
    #: A live take whose recording exists only in memory until it is saved.
    unsaved: bool = False
    #: Why the folder could not be read (shown in the list, never drawn).
    error: str = ""
    #: A take on the fake backend (the demo): never a measurement of a room.
    synthetic: bool = False

    @property
    def loading(self) -> bool:
        return self.result is None and not self.error

    @property
    def is_take(self) -> bool:
        return self.key.startswith(TAKE_PREFIX)


def entry_label(entry: Entry) -> str:
    """The name the list, the legend and the inspector show for ``entry``.

    The only implementation: the navigator and every chart call it, so a
    curve's legend always reads like its row in the list.
    """
    from reverbscope.demo import localize_demo_name

    session = entry.session
    mode = session.mode if session is not None else ""
    folder = entry.directory.name if entry.directory is not None else ""
    if entry.is_take:
        named = (
            localize_demo_name(mode, session.measurement_position or session.room_name)
            if session is not None
            else ""
        )
        base = _("Unsaved take") if entry.unsaved else _("New take")
        text = f"{base} · {named}" if named else base
    elif entry.position and folder:
        text = f"{entry.position} · {folder}"
    elif folder:
        text = folder
    elif session is not None:
        text = localize_demo_name(mode, session.room_name) or _("(unnamed room)")
    else:
        text = entry.key
    return text


@dataclass(frozen=True)
class LoadedEntry:
    """What :class:`ProjectLoader` read for one folder, off the GUI thread."""

    position: str
    directory: Path
    session: MeasurementSession | None
    result: AnalysisResult | None
    findings: list[Finding]
    findings_problem: str
    profile: str
    error: str


class ProjectLoader(QThread):
    """Reads a project's session folders one at a time, off the GUI thread.

    ``listed`` carries the project and its positions as soon as the index is
    read, so the list shows every position before the first take is loaded;
    ``loaded`` then carries each take. Both carry the generation the load
    started under: the model drops what belongs to an older one.
    """

    listed = Signal(int, object, object)
    loaded = Signal(int, object)
    failed = Signal(int, str)

    def __init__(self, path: Path, generation: int) -> None:
        super().__init__()
        self.path = path
        self.generation = generation

    def run(self) -> None:
        from reverbscope.io.project_store import list_project_sessions, load_project
        from reverbscope.io.session_store import load_measurement

        try:
            project = load_project(self.path)
            items = list_project_sessions(self.path)
        except ReverbScopeError as exc:
            self.failed.emit(self.generation, localize(str(exc)))
            return
        except Exception:
            log.exception("reading project %s failed unexpectedly", self.path)
            from reverbscope.ui.workers import unexpected_error_text

            self.failed.emit(self.generation, unexpected_error_text())
            return
        self.listed.emit(self.generation, project, items)
        for position, folder in items:
            if self.isInterruptionRequested():
                return
            try:
                measurement = load_measurement(folder)
            except ReverbScopeError as exc:
                self.loaded.emit(
                    self.generation,
                    LoadedEntry(position, Path(folder), None, None, [], "", "generic", str(exc)),
                )
                continue
            except Exception:
                log.exception("reading session %s failed unexpectedly", folder)
                from reverbscope.ui.workers import unexpected_error_text

                self.loaded.emit(
                    self.generation,
                    LoadedEntry(
                        position,
                        Path(folder),
                        None,
                        None,
                        [],
                        "",
                        "generic",
                        unexpected_error_text(),
                    ),
                )
                continue
            profile = usable_profile(measurement.session)
            findings, problem = safe_findings(measurement.result, profile)
            self.loaded.emit(
                self.generation,
                LoadedEntry(
                    position,
                    measurement.directory,
                    measurement.session,
                    measurement.result,
                    findings,
                    problem,
                    profile,
                    "",
                ),
            )


def folder_key(directory: str | Path) -> str:
    """The key of a saved session: its resolved folder."""
    return str(Path(directory).resolve())


class WorkspaceModel(QObject):
    """Every open measurement, the selection, the overlays and the baseline."""

    entries_changed = Signal()
    entry_updated = Signal(str)
    current_changed = Signal(str)
    overlay_changed = Signal()
    baseline_changed = Signal()
    #: ``(key, index)``; index ``-1`` clears the selection.
    reflection_changed = Signal(str, int)
    project_changed = Signal()
    loading_changed = Signal(bool)
    #: Why a project could not be read (translated).
    project_failed = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._entries: dict[str, Entry] = {}
        self._current: str = ""
        self._overlay: set[str] = set()
        self._baseline: str = ""
        self._reflection: tuple[str, int] = ("", -1)
        self._cache: dict[str, dict[Any, Any]] = {}
        self._colors: dict[str, int] = {}
        self._takes = 0
        self.project_path: Path | None = None
        self.project: Project | None = None
        #: Position labels of the project, in its order, also those without a take.
        self.positions: list[str] = []
        self.generation = 0
        self._loader: ProjectLoader | None = None
        self._old_loaders: list[ProjectLoader] = []
        #: Selection to restore once the project's takes are loaded.
        self._pending_selection: dict[str, Any] | None = None

    # --- reading ---------------------------------------------------------------

    def __iter__(self) -> Iterator[Entry]:
        return iter(list(self._entries.values()))

    def __len__(self) -> int:
        return len(self._entries)

    def entries(self) -> list[Entry]:
        return list(self._entries.values())

    def entry(self, key: str) -> Entry | None:
        return self._entries.get(key)

    def current(self) -> Entry | None:
        return self._entries.get(self._current)

    @property
    def current_key(self) -> str:
        return self._current

    def baseline(self) -> Entry | None:
        return self._entries.get(self._baseline)

    @property
    def baseline_key(self) -> str:
        return self._baseline

    def is_overlaid(self, key: str) -> bool:
        return key in self._overlay

    def overlay_keys(self) -> list[str]:
        return [key for key in self._entries if key in self._overlay]

    def drawn(self) -> list[Entry]:
        """The entries a chart draws: the overlays in list order, then the current one.

        The current entry is always drawn and drawn last (on top). Entries
        still loading or that could not be read are skipped.
        """
        keys = [key for key in self._entries if key in self._overlay and key != self._current]
        if self._current:
            keys.append(self._current)
        return [
            self._entries[key]
            for key in keys
            if key in self._entries and self._entries[key].result is not None
        ]

    def selected_reflection(self) -> tuple[str, int]:
        return self._reflection

    def unsaved_entries(self) -> list[Entry]:
        return [entry for entry in self._entries.values() if entry.unsaved]

    @property
    def loading(self) -> bool:
        return self._loader is not None and self._loader.isRunning()

    # --- adding and removing ---------------------------------------------------

    def _next_color(self, key: str) -> int:
        if key in self._colors:
            return self._colors[key]
        # Reserved colours count too: a project being read again gets each
        # take's colour back as it arrives, so no newcomer may take it meanwhile.
        used = set(self._colors.values())
        index = next((i for i in range(len(ENTRY_COLORS)) if i not in used), None)
        if index is None:
            index = len(self._entries) % len(ENTRY_COLORS)
        self._colors[key] = index
        return index

    def _put(self, entry: Entry) -> Entry:
        index = self._next_color(entry.key)
        entry.color_index = index
        entry.color = ENTRY_COLORS[index]
        self._entries[entry.key] = entry
        self._cache.pop(entry.key, None)
        return entry

    def add_session(
        self,
        directory: Path,
        session: MeasurementSession,
        result: AnalysisResult,
        *,
        position: str = "",
        findings: list[Finding] | None = None,
        findings_problem: str = "",
        profile: str | None = None,
        make_current: bool = True,
    ) -> Entry:
        """A saved session; opening the same folder again replaces its entry."""
        key = folder_key(directory)
        chosen = profile or usable_profile(session)
        if findings is None:
            findings, findings_problem = safe_findings(result, chosen)
        entry = self._put(
            Entry(
                key=key,
                directory=Path(directory),
                session=session,
                result=result,
                position=position or self._position_of(key),
                findings=findings,
                findings_problem=findings_problem,
                profile=chosen,
                synthetic=session.mode == "demo",
            )
        )
        self.entries_changed.emit()
        if make_current:
            self.set_current(key)
        else:
            self.entry_updated.emit(key)
        return entry

    def add_take(
        self,
        session: MeasurementSession,
        result: AnalysisResult,
        findings: list[Finding],
        findings_problem: str,
        profile: str,
        *,
        unsaved: bool,
        synthetic: bool,
        position: str = "",
    ) -> Entry:
        """A take that has just been analysed; it becomes the current entry.

        Earlier takes that were saved or discarded are gone by now (the window
        asks before an unsaved one is replaced); a saved take was re-keyed to
        its folder by :meth:`mark_saved` and stays.
        """
        for old in [entry.key for entry in self._entries.values() if entry.is_take]:
            self._drop(old)
        self._takes += 1
        key = f"{TAKE_PREFIX}{self._takes}"
        self._put(
            Entry(
                key=key,
                directory=None,
                session=session,
                result=result,
                position=position,
                findings=findings,
                findings_problem=findings_problem,
                profile=profile,
                unsaved=unsaved,
                synthetic=synthetic,
            )
        )
        self.entries_changed.emit()
        self.set_current(key)
        return self._entries[key]

    def mark_saved(self, key: str, directory: Path, *, position: str = "") -> str:
        """The take ``key`` was saved into ``directory``: it keeps its colour,
        its place in the overlays and the baseline, under its folder's key."""
        entry = self._entries.get(key)
        if entry is None:
            return key
        new_key = folder_key(directory)
        if new_key != key and new_key in self._entries:
            # The take replaced a session that was open: one entry for the folder.
            self._drop(new_key, notify=False)
        self._colors[new_key] = self._colors.pop(key, entry.color_index)
        entry.key = new_key
        entry.directory = Path(directory)
        entry.unsaved = False
        if position:
            entry.position = position
        rebuilt: dict[str, Entry] = {}
        for k, value in self._entries.items():
            rebuilt[new_key if k == key else k] = value
        self._entries = rebuilt
        if key in self._overlay:
            self._overlay.discard(key)
            self._overlay.add(new_key)
        if self._baseline == key:
            self._baseline = new_key
        if self._current == key:
            self._current = new_key
        if self._reflection[0] == key:
            self._reflection = (new_key, self._reflection[1])
        if key in self._cache:
            self._cache[new_key] = self._cache.pop(key)
        self.entries_changed.emit()
        self.current_changed.emit(self._current)
        return new_key

    def remove(self, key: str) -> None:
        if key in self._entries:
            self._drop(key)
            self.entries_changed.emit()

    def _drop(self, key: str, *, notify: bool = True, keep_color: bool = False) -> None:
        self._entries.pop(key, None)
        self._cache.pop(key, None)
        if not keep_color:
            self._colors.pop(key, None)
        changed_overlay = key in self._overlay
        self._overlay.discard(key)
        if self._baseline == key:
            self._baseline = ""
            if notify:
                self.baseline_changed.emit()
        if self._reflection[0] == key:
            self._reflection = ("", -1)
            if notify:
                self.reflection_changed.emit("", -1)
        if changed_overlay and notify:
            self.overlay_changed.emit()
        if self._current == key:
            self._current = next(iter(self._entries), "") if self._entries else ""
            if notify:
                self.current_changed.emit(self._current)

    def clear(self) -> None:
        """Close everything: the project, its takes and loose sessions."""
        self._stop_loader()
        self.generation += 1
        self._entries.clear()
        self._cache.clear()
        self._colors.clear()
        self._overlay.clear()
        self._baseline = ""
        self._reflection = ("", -1)
        self._current = ""
        self.project_path = None
        self.project = None
        self.positions = []
        self._pending_selection = None
        self.entries_changed.emit()
        self.project_changed.emit()
        self.current_changed.emit("")
        self.overlay_changed.emit()
        self.baseline_changed.emit()

    # --- selection -------------------------------------------------------------

    def set_current(self, key: str) -> None:
        if key and key not in self._entries:
            return
        self._current = key
        if self._reflection[0] and self._reflection[0] != key:
            self._reflection = ("", -1)
            self.reflection_changed.emit("", -1)
        self.current_changed.emit(key)

    def set_overlay(self, key: str, on: bool) -> None:
        if key not in self._entries:
            return
        if on == (key in self._overlay):
            return
        if on:
            self._overlay.add(key)
        else:
            self._overlay.discard(key)
        self.overlay_changed.emit()

    def set_baseline(self, key: str) -> None:
        if key and key not in self._entries:
            return
        if key == self._baseline:
            return
        self._baseline = key
        self.baseline_changed.emit()

    def select_reflection(self, key: str, index: int) -> None:
        """Select reflection ``index`` of entry ``key`` (``-1`` clears)."""
        if (key, index) == self._reflection:
            return
        entry = self._entries.get(key)
        if index >= 0 and (
            entry is None
            or entry.result is None
            or index >= len(entry.result.reflections.reflections)
        ):
            return
        self._reflection = (key, index) if index >= 0 else ("", -1)
        self.reflection_changed.emit(*self._reflection)

    # --- cache -----------------------------------------------------------------

    def cache_get(self, key: str, name: Any) -> Any:
        return self._cache.get(key, {}).get(name)

    def cache_put(self, key: str, name: Any, value: Any) -> None:
        if key in self._entries:
            self._cache.setdefault(key, {})[name] = value

    # --- projects --------------------------------------------------------------

    def _position_of(self, key: str) -> str:
        entry = self._entries.get(key)
        return entry.position if entry is not None else ""

    def open_project(self, path: Path, *, selection: dict[str, Any] | None = None) -> None:
        """Read the project at ``path`` in the background.

        Saved sessions of the previous project and loose sessions are closed;
        an unsaved take stays (the window asked about it, and it may be saved
        into this project). ``selection`` (from ``ui.ini``) is restored once
        the takes it names are loaded.
        """
        self._stop_loader()
        self.generation += 1
        same = self.project_path is not None and path.resolve() == self.project_path.resolve()
        for key in [entry.key for entry in self._entries.values() if not entry.unsaved]:
            self._drop(key, notify=False, keep_color=same)
        if not same:
            self._colors = {k: v for k, v in self._colors.items() if k in self._entries}
        base = path if path.is_dir() else path.parent
        self.project_path = base
        self.project = None
        self.positions = []
        self._pending_selection = selection
        self.entries_changed.emit()
        self.overlay_changed.emit()
        self.baseline_changed.emit()
        self.current_changed.emit(self._current)
        self.project_changed.emit()
        loader = ProjectLoader(base, self.generation)
        loader.listed.connect(self._on_listed)
        loader.loaded.connect(self._on_loaded)
        loader.failed.connect(self._on_failed)
        loader.finished.connect(self._on_loader_finished)
        self._loader = loader
        self.loading_changed.emit(True)
        loader.start()

    def reload_project(self) -> None:
        """Read the open project again (a take was saved or added to it),
        keeping the current entry, the overlays and the baseline."""
        if self.project_path is not None:
            self.open_project(self.project_path, selection=self.selection_state())

    def close_project(self) -> None:
        self._stop_loader()
        self.generation += 1
        for key in [
            entry.key
            for entry in self._entries.values()
            if not entry.unsaved and self._in_project(entry)
        ]:
            self._drop(key, notify=False)
        self.project_path = None
        self.project = None
        self.positions = []
        self.entries_changed.emit()
        self.overlay_changed.emit()
        self.baseline_changed.emit()
        self.current_changed.emit(self._current)
        self.project_changed.emit()

    def _in_project(self, entry: Entry) -> bool:
        if self.project_path is None or entry.directory is None:
            return False
        try:
            entry.directory.resolve().relative_to(self.project_path.resolve())
        except ValueError:
            return bool(entry.position)
        return True

    def add_position(self, label: str) -> None:
        """A position named in the window before its first take is saved."""
        if label and label not in self.positions:
            self.positions.append(label)
            self.project_changed.emit()

    def _on_listed(self, generation: int, project: object, items: object) -> None:
        if generation != self.generation or not isinstance(project, Project):
            return
        self.project = project
        labels = [entry.label for entry in project.positions]
        for position, _folder in items if isinstance(items, list) else []:
            if position and position not in labels:
                labels.append(position)
        self.positions = labels
        self.project_changed.emit()

    def _on_loaded(self, generation: int, loaded: object) -> None:
        if generation != self.generation or not isinstance(loaded, LoadedEntry):
            return
        key = folder_key(loaded.directory)
        entry = self._put(
            Entry(
                key=key,
                directory=loaded.directory,
                session=loaded.session,
                result=loaded.result,
                position=loaded.position,
                findings=loaded.findings,
                findings_problem=loaded.findings_problem,
                profile=loaded.profile,
                error=localize(loaded.error) if loaded.error else "",
                synthetic=loaded.session is not None and loaded.session.mode == "demo",
            )
        )
        self.entries_changed.emit()
        pending = self._pending_selection or {}
        if key == pending.get("current") or (not self._current and entry.result is not None):
            self.set_current(key)
        if key in pending.get("overlay", ()):
            self.set_overlay(key, True)
        if key == pending.get("baseline"):
            self.set_baseline(key)

    def _on_failed(self, generation: int, message: str) -> None:
        if generation == self.generation:
            self.project_failed.emit(message)

    def _on_loader_finished(self) -> None:
        loader = self.sender()
        if loader is self._loader:
            self._loader = None
            self._pending_selection = None
            # Colours reserved for takes that did not come back are free again.
            self._colors = {k: v for k, v in self._colors.items() if k in self._entries}
            self.loading_changed.emit(False)
        if isinstance(loader, ProjectLoader) and loader in self._old_loaders:
            self._old_loaders.remove(loader)

    def _stop_loader(self) -> None:
        """Ask a running load to stop; its late signals are dropped by generation.

        The thread object is kept until it finishes: a ``QThread`` destroyed
        while it runs aborts the process.
        """
        if self._loader is not None and self._loader.isRunning():
            self._loader.requestInterruption()
            self._old_loaders.append(self._loader)
            self.loading_changed.emit(False)
        self._loader = None

    def wait_until_loaded(self, timeout_s: float = 30.0) -> bool:
        """Run the event loop until the project's takes are read (scripts and tests).

        Returns ``False`` when the load is still running after ``timeout_s``.
        """
        import time

        from PySide6.QtCore import QCoreApplication

        deadline = time.monotonic() + timeout_s
        while self._loader is not None:
            if time.monotonic() > deadline:
                return False
            self._loader.wait(10)
            QCoreApplication.processEvents()
        QCoreApplication.processEvents()
        return True

    def shutdown(self) -> None:
        """Stop every load and wait for it (the window is closing)."""
        loaders = [*self._old_loaders, *([self._loader] if self._loader is not None else [])]
        for loader in loaders:
            loader.requestInterruption()
        for loader in loaders:
            loader.wait()
        self._old_loaders.clear()
        self._loader = None

    # --- persistence of the selection -------------------------------------------

    def selection_state(self) -> dict[str, Any]:
        """The current entry, the overlays and the baseline, by folder key."""
        return {
            "current": "" if self._current.startswith(TAKE_PREFIX) else self._current,
            "overlay": [k for k in self.overlay_keys() if not k.startswith(TAKE_PREFIX)],
            "baseline": "" if self._baseline.startswith(TAKE_PREFIX) else self._baseline,
        }
