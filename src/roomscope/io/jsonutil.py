"""JSON reads with size and depth caps (ARCHITECTURE_V1.md §8)."""

from __future__ import annotations

import json
import os
import secrets
import stat
from pathlib import Path
from typing import Any

from roomscope.errors import SessionError
from roomscope.i18n import _
from roomscope.models.loadutil import record_name

#: Refused before ``json.loads``: sessions, projects, settings, comparisons.
MAX_JSON_BYTES = 32 * 1024 * 1024
#: ``result.json`` stores every frequency-response bin: at 192 kHz with a 6 s
#: impulse response (the default ``ir_max_length_s``) that is about 40 MB.
MAX_RESULT_JSON_BYTES = 128 * 1024 * 1024
#: Nesting of ``{`` / ``[`` outside strings. RoomScope schemas are shallow.
MAX_JSON_DEPTH = 32


def json_nesting_depth(text: str) -> int:
    """Return the maximum ``{`` / ``[`` nesting, ignoring characters inside strings."""
    depth = 0
    deepest = 0
    in_string = False
    escape = False
    for char in text:
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
            continue
        if char in "{[":
            depth += 1
            if depth > deepest:
                deepest = depth
        elif char in "}]":
            depth = max(0, depth - 1)
    return deepest


def _create_beside(target: Path, suffix: str) -> tuple[Path, int]:
    temporary = target.with_name(f".{target.stem}.{os.getpid()}-{secrets.token_hex(4)}{suffix}")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    return temporary, os.open(temporary, flags, 0o666)


def temporary_beside(target: Path, suffix: str) -> Path:
    """Create an empty file next to ``target`` under a name no one else uses.

    The name is unique per writer, so two programs saving the same file never
    share (or delete) each other's temporary, and the file is created with
    ``O_EXCL``, so a link planted under a guessable name in a folder from
    someone else is never followed. ``suffix`` ends the name (soundfile reads
    the format from it). Raises ``OSError``.
    """
    temporary, descriptor = _create_beside(target, suffix)
    os.close(descriptor)
    return temporary


def keep_mode(temporary: Path, target: Path) -> None:
    """Give ``temporary`` the permissions of the regular file it will replace."""
    try:
        status = os.lstat(target)
    except OSError:
        return
    if stat.S_ISREG(status.st_mode):
        os.chmod(temporary, stat.S_IMODE(status.st_mode))


def write_text_atomic(path: Path, text: str, *, follow_symlinks: bool = False) -> None:
    """Replace ``path`` with ``text`` so that a failed write keeps the old file.

    ``Path.write_text`` truncates first: a full disk half-way through would
    leave a cut-off session, project or settings file in place of the old one.
    The file keeps its permissions. ``follow_symlinks`` writes through a link
    (the user's own settings kept in a dotfiles folder); without it a link is
    replaced, so that a link in a folder from someone else cannot redirect
    the write. Raises ``OSError`` like ``write_text``.
    """
    target = Path(os.path.realpath(path)) if follow_symlinks else path
    temporary, descriptor = _create_beside(target, f"{target.suffix}.tmp")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        keep_mode(temporary, target)
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def read_json_object(
    path: Path, *, kind: str = "JSON", max_bytes: int = MAX_JSON_BYTES
) -> dict[str, Any]:
    """Read a JSON object, refusing oversized, over-deep or non-object files."""
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise SessionError(_("cannot read {path}: {error}").format(path=path, error=exc)) from exc
    if size > max_bytes:
        raise SessionError(
            _("{name} is {size} bytes; {kind} files larger than {limit} bytes are refused").format(
                name=path.name, size=size, kind=record_name(kind), limit=max_bytes
            )
        )
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise SessionError(_("cannot read {path}: {error}").format(path=path, error=exc)) from exc
    depth = json_nesting_depth(text)
    if depth > MAX_JSON_DEPTH:
        raise SessionError(
            _("{name} nests {depth} levels; {kind} files deeper than {limit} are refused").format(
                name=path.name, depth=depth, kind=record_name(kind), limit=MAX_JSON_DEPTH
            )
        )
    try:
        data = json.loads(text)
    except ValueError as exc:  # JSONDecodeError, or an integer longer than 4300 digits
        raise SessionError(_("cannot read {path}: {error}").format(path=path, error=exc)) from exc
    if not isinstance(data, dict):
        raise SessionError(_("{path} is not a JSON object").format(path=path))
    return data
