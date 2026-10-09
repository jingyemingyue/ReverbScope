"""Project folders: ``project.json`` plus ordinary session directories (S3)."""

from __future__ import annotations

import json
from pathlib import Path

from reverbscope.errors import SessionError
from reverbscope.i18n import _
from reverbscope.io.jsonutil import make_folder, read_json_object, write_text_atomic
from reverbscope.io.session_store import SESSION_FILE, list_sessions, load_session
from reverbscope.models.project import PositionEntry, Project
from reverbscope.version import __version__

PROJECT_FILE = "project.json"
SESSIONS_DIR = "sessions"


def project_file(path: str | Path) -> Path:
    p = Path(path)
    return p / PROJECT_FILE if p.is_dir() or p.suffix.lower() != ".json" else p


def is_project(path: str | Path) -> bool:
    return project_file(path).is_file()


def save_project(directory: str | Path, project: Project) -> Path:
    base = Path(directory)
    make_folder(base)
    if not project.reverbscope_version:
        project.reverbscope_version = __version__
    target = base / PROJECT_FILE
    try:
        write_text_atomic(target, json.dumps(project.to_dict(), indent=2) + "\n")
    except (OSError, TypeError, ValueError) as exc:
        raise SessionError(
            _("cannot write {path}: {error}").format(path=target, error=exc)
        ) from exc
    return target


def load_project(path: str | Path) -> Project:
    return Project.from_dict(read_json_object(project_file(path), kind="project"))


def add_session(
    directory: str | Path,
    session_dir: str | Path,
    *,
    position: str,
) -> Project:
    """Append ``session_dir`` to the named position, creating the position if needed."""
    given = project_file(directory)
    # "room/project.json" names the same project as "room", as in
    # list_project_sessions (`project show` and `project average`).
    base = given.parent if given.is_file() else Path(directory)
    project = load_project(base) if is_project(base) else Project(name=base.name)
    session = Path(session_dir)
    # A typo would be stored and then skipped by every listing without a word.
    load_session(session)
    if not session.is_dir():
        # One session, one entry: "dir", "dir/session.json" and "dir/result.json"
        # are the same take.
        session = session.parent
    stored = _relative(session, base)
    target = _resolve(base, stored).resolve()
    for entry in project.positions:
        if entry.label != position and any(
            _resolved(base, d) == target for d in entry.session_dirs
        ):
            # One take is one position; the listing would keep the first label.
            raise SessionError(
                _("{session} is already listed under position '{label}'").format(
                    session=session, label=entry.label
                )
            )
    positions = list(project.positions)
    for index, entry in enumerate(positions):
        if entry.label == position:
            dirs = list(entry.session_dirs)
            known = {_resolved(base, d) for d in dirs}
            if target not in known:
                dirs.append(stored)
            positions[index] = PositionEntry(label=position, session_dirs=tuple(dirs))
            break
    else:
        positions.append(PositionEntry(label=position, session_dirs=(stored,)))
    project.positions = tuple(positions)
    save_project(base, project)
    return project


def _session_folder(candidate: Path) -> Path | None:
    """The session folder a stored entry names, or None when there is none to read."""
    if (candidate / SESSION_FILE).is_file() or (
        candidate.name == SESSION_FILE and candidate.is_file()
    ):
        return candidate if candidate.is_dir() else candidate.parent
    return None


def list_project_sessions(path: str | Path) -> list[tuple[str, Path]]:
    """``(position_label, session_directory)`` in project order, then leftovers.

    An entry whose folder is gone is left out; :func:`missing_project_sessions`
    names those, so a caller can say what the listing does not hold.
    """
    base = project_file(path).parent
    project = load_project(base)
    seen: set[Path] = set()
    items: list[tuple[str, Path]] = []
    for entry in project.positions:
        for stored in entry.session_dirs:
            folder = _session_folder(_resolve(base, stored))
            if folder is not None:
                if folder.resolve() in seen:
                    # Listed twice (or under two positions): average it once.
                    continue
                items.append((entry.label, folder))
                seen.add(folder.resolve())
    for listing in list_sessions(base):
        if listing.path.resolve() not in seen:
            items.append(("", listing.path))
    return items


def missing_project_sessions(path: str | Path) -> list[tuple[str, str]]:
    """``(position_label, stored_path)`` of every listed take that has no session to read.

    A session folder that was moved, renamed or deleted after ``project add``
    (or an absolute path whose project moved) is skipped by
    :func:`list_project_sessions`; ``project show`` and ``project average`` use
    this to say so, instead of quietly working with fewer positions.
    """
    base = project_file(path).parent
    project = load_project(base)
    return [
        (entry.label, stored)
        for entry in project.positions
        for stored in entry.session_dirs
        if _session_folder(_resolve(base, stored)) is None
    ]


def _relative(path: Path, base: Path) -> str:
    """Store paths inside the project with ``/`` so a project moves between OSes."""
    try:
        return path.resolve().relative_to(base.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def _resolved(base: Path, stored: str) -> Path | None:
    """A stored entry resolved, or None when it cannot be: a NUL byte or a
    link loop (a project.json from someone else) names no session, as in
    :func:`list_project_sessions`."""
    try:
        return _resolve(base, stored).resolve()
    except (OSError, RuntimeError, ValueError):
        return None


def _resolve(base: Path, stored: str) -> Path:
    candidate = Path(stored)
    if candidate.is_absolute():
        return candidate
    # A relative entry written on Windows uses "\"; it is never part of a
    # folder name ReverbScope writes, so read it as a separator everywhere.
    return base.joinpath(*[part for part in stored.replace("\\", "/").split("/") if part])
