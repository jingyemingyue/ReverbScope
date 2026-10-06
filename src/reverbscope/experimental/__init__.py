"""Experimental features. Not part of the 0.5 stable or release-candidate set.

Nothing in this package is imported by the measurement core. Stable and
release-candidate builds must not treat these modules as a supported feature.
The guided acoustic assistant lives on ``experimental/guided-acoustic-assistant``.
"""

from __future__ import annotations

#: Marker read by tests and the guided report. Never flip this to ship the
#: assistant inside a stable or release-candidate feature set.
EXPERIMENTAL = True
TRACK = "experimental/guided-acoustic-assistant"

__all__ = ["EXPERIMENTAL", "TRACK"]
