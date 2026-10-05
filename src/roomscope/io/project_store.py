"""Project folders: ``project.json`` plus ordinary session directories (S3)."""

from __future__ import annotations

import json
from pathlib import Path

from roomscope.errors import SessionError
from roomscope.i18n import _
from roomscope.io.jsonutil import read_json_object, write_text_atomic
from roomscope.io.session_store import SESSION_FILE, list_sessions, load_session
from roomscope.models.project import PositionEntry, Project
from roomscope.version import __version__

PROJECT_FILE = "project.json"
SESSIONS_DIR = "sessions"


def project_file(path: str | Path) -> Path:
    p = Path(path)
    return p / PROJECT_FILE if p.is_dir() or p.suffix.lower() != ".json" else p


def is_project(path: str | Path) -> bool:
    return project_file(path).is_file()


def save_project(directory: str | Path, project: Project) -> Path:
    base = Path(directory)
    base.mkdir(parents=True, exist_ok=True)
    if not project.roomscope_version:
        project.roomscope_version = __version__
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
    base = Path(directory)
    project = load_project(base) if is_project(base) else Project(name=base.name)
    session = Path(session_dir)
    if session.name == SESSION_FILE:
        # One session, one entry: "dir" and "dir/session.json" are the same take.
        session = session.parent
    # A typo would be stored and then skipped by every listing without a word.
    load_session(session)
    stored = _relative(session, base)
    target = _resolve(base, stored).resolve()
    for entry in project.positions:
        if entry.label != position and any(
            _resolve(base, d).resolve() == target for d in entry.session_dirs
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
            known = {_resolve(base, d).resolve() for d in dirs}
            if target not in known:
                dirs.append(stored)
            positions[index] = PositionEntry(label=position, session_dirs=tuple(dirs))
            break
    else:
        positions.append(PositionEntry(label=position, session_dirs=(stored,)))
    project.positions = tuple(positions)
    save_project(base, project)
    return project


def list_project_sessions(path: str | Path) -> list[tuple[str, Path]]:
    """``(position_label, session_directory)`` in project order, then leftovers."""
    base = project_file(path).parent
    project = load_project(base)
    seen: set[Path] = set()
    items: list[tuple[str, Path]] = []
    for entry in project.positions:
        for stored in entry.session_dirs:
            candidate = _resolve(base, stored)
            if (candidate / SESSION_FILE).is_file() or (
                candidate.name == SESSION_FILE and candidate.is_file()
            ):
                folder = candidate if candidate.is_dir() else candidate.parent
                if folder.resolve() in seen:
                    # Listed twice (or under two positions): average it once.
                    continue
                items.append((entry.label, folder))
                seen.add(folder.resolve())
    for listing in list_sessions(base):
        if listing.path.resolve() not in seen:
            items.append(("", listing.path))
    return items


def _relative(path: Path, base: Path) -> str:
    """Store paths inside the project with ``/`` so a project moves between OSes."""
    try:
        return path.resolve().relative_to(base.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def _resolve(base: Path, stored: str) -> Path:
    candidate = Path(stored)
    if candidate.is_absolute():
        return candidate
    # A relative entry written on Windows uses "\"; it is never part of a
    # folder name RoomScope writes, so read it as a separator everywhere.
    return base.joinpath(*[part for part in stored.replace("\\", "/").split("/") if part])
