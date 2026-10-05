"""Shipped JSON Schemas for ReverbScope file formats.

Hand-maintained. The dataclasses are the source of truth; tests prove each
``to_dict`` validates against the matching schema, and ``reverbscope schema``
prints these files byte-for-byte.
"""

from __future__ import annotations

import json
from importlib.resources import files
from typing import Any, cast

from reverbscope.errors import ConfigurationError

SCHEMA_FILES: dict[str, str] = {
    "result": "result.schema.json",
    "session": "session.schema.json",
    "comparison": "comparison.schema.json",
    "project": "project.schema.json",
    "sidecar": "sweep-sidecar.schema.json",
}


def schema_names() -> tuple[str, ...]:
    return tuple(SCHEMA_FILES)


def schema_text(name: str) -> str:
    """Return the shipped schema file as text (no re-serialisation)."""
    filename = SCHEMA_FILES.get(name)
    if filename is None:
        raise ConfigurationError(f"unknown schema '{name}'; available: {sorted(SCHEMA_FILES)}")
    return files("reverbscope.schemas").joinpath(filename).read_text(encoding="utf-8")


def load_schema(name: str) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(schema_text(name)))
