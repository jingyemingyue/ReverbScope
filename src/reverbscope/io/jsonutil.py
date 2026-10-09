"""JSON reads with size and depth caps (ARCHITECTURE_V1.md §8)."""

from __future__ import annotations

import contextlib
import json
import os
import re
import secrets
import shutil
import stat
from pathlib import Path
from typing import Any

from reverbscope.errors import SessionError
from reverbscope.i18n import _
from reverbscope.models.loadutil import record_name

#: Refused before ``json.loads``: sessions, projects, settings, comparisons.
MAX_JSON_BYTES = 32 * 1024 * 1024
#: ``result.json`` stores every frequency-response bin: at 192 kHz with a 6 s
#: impulse response (the default ``ir_max_length_s``) that is about 40 MB.
MAX_RESULT_JSON_BYTES = 128 * 1024 * 1024
#: Nesting of ``{`` / ``[`` outside strings. ReverbScope schemas are shallow.
MAX_JSON_DEPTH = 32


#: A JSON string (escapes kept whole), a string left open to the end of the
#: text (a lone backslash last included), or one bracket. Everything else
#: (numbers, whitespace, names) is skipped by the regex engine, which reads a
#: result.json of several megabytes in milliseconds where a Python loop over
#: its characters took longer than parsing it. The quantifiers are possessive
#: (Python 3.11 and later): with a backtracking alternation per character, one
#: 40 MB string in a file below the size limit took 34 s and 4.8 GiB to scan,
#: where the loop needs 2 s and 190 MiB and this pattern 0.3 s and 180 MiB.
_JSON_TOKENS = re.compile(r'"[^"\\]*+(?:\\.[^"\\]*+)*+(?:"|\\?\Z)|[{}\[\]]', re.DOTALL)


def json_nesting_depth(text: str) -> int:
    """Return the maximum ``{`` / ``[`` nesting, ignoring characters inside strings."""
    depth = 0
    deepest = 0
    for match in _JSON_TOKENS.finditer(text):
        token = match.group()
        if token == "{" or token == "[":
            depth += 1
            if depth > deepest:
                deepest = depth
        elif token == "}" or token == "]":
            depth = max(0, depth - 1)
        # A string: skipped whole, whatever brackets it holds.
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


def discard(path: Path) -> None:
    """Delete a temporary file, a read-only one too, without ever raising.

    Windows cannot delete a read-only file, and a temporary that took the
    permissions of a write-protected file it was to replace is one. A cleanup
    that raised would hide the error that made it necessary, and stop before
    the other temporaries were removed.
    """
    try:
        path.unlink(missing_ok=True)
    except OSError:
        with contextlib.suppress(OSError):
            os.chmod(path, stat.S_IREAD | stat.S_IWRITE)
            path.unlink(missing_ok=True)


def keep_beside(target: Path, suffix: str) -> Path:
    """A second name for the regular file ``target``, next to it and unique.

    A hard link where it costs nothing. A copy where the file system has no
    links (FAT and exFAT memory cards) and for a read-only file: on Windows
    the links of a file share its read-only flag, so the second name could
    not be deleted without unprotecting the file. Raises ``OSError``.
    """
    if os.stat(target).st_mode & stat.S_IWUSR:
        name = target.with_name(f".{target.stem}.{os.getpid()}-{secrets.token_hex(4)}{suffix}")
        try:
            os.link(target, name)  # fails, never follows, when the name exists
        except OSError:
            pass
        else:
            return name
    copy, descriptor = _create_beside(target, suffix)
    try:
        with os.fdopen(descriptor, "wb") as out, open(target, "rb") as source:
            shutil.copyfileobj(source, out)
        shutil.copystat(target, copy)
    except BaseException:
        discard(copy)
        raise
    return copy


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
        discard(temporary)


def make_folder(path: Path) -> None:
    """``mkdir -p`` for a folder ReverbScope writes into.

    A folder that cannot be made (a file of that name, a parent that is a
    file, a name the file system refuses, a Windows reserved name such as
    ``CON``, a disk that is full or read-only) is the user's to fix, not a
    bug: it is reported as :class:`SessionError` instead of a bare OSError.
    """
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise SessionError(
            _("cannot create folder {path}: {error}").format(path=path, error=exc)
        ) from exc


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
        # utf-8-sig: Notepad's "UTF-8 with BOM" and Windows PowerShell 5's
        # "-Encoding UTF8" start the file with a byte-order mark.
        text = path.read_text(encoding="utf-8-sig")
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
    except json.JSONDecodeError as exc:
        # The parser's own sentence is English whatever the interface language;
        # where the file is broken is what the user needs to fix it.
        where = _("invalid JSON at line {line}, column {column}").format(
            line=exc.lineno, column=exc.colno
        )
        raise SessionError(_("cannot read {path}: {error}").format(path=path, error=where)) from exc
    except ValueError as exc:  # an integer longer than 4300 digits
        raise SessionError(_("cannot read {path}: {error}").format(path=path, error=exc)) from exc
    if not isinstance(data, dict):
        raise SessionError(_("{path} is not a JSON object").format(path=path))
    return data
