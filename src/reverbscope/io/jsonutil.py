"""JSON reads with size and depth caps (ARCHITECTURE_V1.md §8)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from reverbscope.errors import SessionError
from reverbscope.i18n import _
from reverbscope.models.loadutil import record_name

#: Refused before ``json.loads``. 32 MiB is well above a result with curves.
MAX_JSON_BYTES = 32 * 1024 * 1024
#: Nesting of ``{`` / ``[`` outside strings. ReverbScope schemas are shallow.
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


def read_json_object(path: Path, *, kind: str = "JSON") -> dict[str, Any]:
    """Read a JSON object, refusing oversized, over-deep or non-object files."""
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise SessionError(_("cannot read {path}: {error}").format(path=path, error=exc)) from exc
    if size > MAX_JSON_BYTES:
        raise SessionError(
            _("{name} is {size} bytes; {kind} files larger than {limit} bytes are refused").format(
                name=path.name, size=size, kind=record_name(kind), limit=MAX_JSON_BYTES
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
    except json.JSONDecodeError as exc:
        raise SessionError(_("cannot read {path}: {error}").format(path=path, error=exc)) from exc
    if not isinstance(data, dict):
        raise SessionError(_("{path} is not a JSON object").format(path=path))
    return data
