"""Package version, read from installed metadata.

``pyproject.toml`` is the single source; a test proves this string matches it.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("reverbscope")
except PackageNotFoundError:  # pragma: no cover - only when the package is not installed
    __version__ = "0.1.0.dev1"
