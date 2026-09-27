"""Terminal styling for the CLI: optional ANSI emphasis, rules and a progress line.

No third-party dependency. Colour is used sparingly (headings, severity tags,
validity) and only when the stream is an interactive terminal. It is off for
pipes, files and CI logs, when ``NO_COLOR`` is set (https://no-color.org) or
``TERM=dumb``, and when ``--no-color`` is given. ``FORCE_COLOR`` turns it on
for a non-terminal stream. The plain text is identical with and without colour,
so the GUI and tests can use the same report functions unstyled.
"""

from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass
from typing import TextIO

_CODES = {
    "bold": "1",
    "dim": "2",
    "red": "31",
    "green": "32",
    "yellow": "33",
    "cyan": "36",
}

#: Widest rule the reports draw; narrower terminals get a narrower rule.
MAX_WIDTH = 78
MIN_WIDTH = 40


def color_supported(stream: TextIO | None = None, *, requested: bool | None = None) -> bool:
    """Whether ANSI colour should be written to ``stream``.

    ``requested`` is ``False`` for ``--no-color``; ``None`` means decide from
    the environment and the stream.
    """
    if requested is False:
        return False
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FORCE_COLOR"):
        return True
    if os.environ.get("TERM") == "dumb":
        return False
    target = stream if stream is not None else sys.stdout
    isatty = getattr(target, "isatty", None)
    try:
        interactive = bool(isatty()) if callable(isatty) else False
    except (OSError, ValueError):
        return False
    if interactive and sys.platform == "win32":
        return _enable_windows_vt()
    return interactive


def _enable_windows_vt() -> bool:
    """Turn on ANSI escape processing in a Windows console; ``False`` if it cannot."""
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        enable_vt = 0x0004  # ENABLE_VIRTUAL_TERMINAL_PROCESSING
        ok = True
        for std_handle in (-11, -12):  # STD_OUTPUT_HANDLE, STD_ERROR_HANDLE
            handle = kernel32.GetStdHandle(std_handle)
            mode = ctypes.c_uint32()
            if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
                ok = False
                continue
            if not kernel32.SetConsoleMode(handle, mode.value | enable_vt):
                ok = False
        return ok
    except (AttributeError, OSError, ValueError):
        return False


def terminal_width() -> int:
    """Report width: the terminal's, clamped to [MIN_WIDTH, MAX_WIDTH]."""
    columns = shutil.get_terminal_size(fallback=(MAX_WIDTH, 24)).columns
    return max(MIN_WIDTH, min(MAX_WIDTH, columns))


@dataclass(frozen=True)
class Style:
    """ANSI emphasis that degrades to plain text when ``color`` is ``False``."""

    color: bool = False

    def _wrap(self, text: str, *codes: str) -> str:
        if not self.color or not text:
            return text
        sequence = ";".join(_CODES[c] for c in codes)
        return f"\x1b[{sequence}m{text}\x1b[0m"

    def heading(self, text: str) -> str:
        return self._wrap(text, "bold")

    def dim(self, text: str) -> str:
        return self._wrap(text, "dim")

    def good(self, text: str) -> str:
        return self._wrap(text, "green")

    def caution(self, text: str) -> str:
        return self._wrap(text, "yellow")

    def bad(self, text: str) -> str:
        return self._wrap(text, "red")

    def accent(self, text: str) -> str:
        return self._wrap(text, "cyan")

    def command(self, text: str) -> str:
        return self._wrap(text, "bold")

    def severity(self, severity: str) -> str:
        """``[warning]`` / ``[notice]`` / ``[info]`` tag, coloured by severity."""
        tag = f"[{severity}]"
        if severity == "warning":
            return self.caution(tag)
        if severity == "notice":
            return self.accent(tag)
        return self.dim(tag)

    def validity(self, value: str, text: str | None = None) -> str:
        """Colour ``text`` (default: ``value``) by a :class:`Validity` value."""
        shown = value if text is None else text
        if value == "valid":
            return self.good(shown)
        return self.caution(shown)


PLAIN = Style(color=False)


class ProgressLine:
    """Measurement progress on stderr.

    On a terminal: one line that is redrawn in place (``[#####-----]  50 %``).
    Elsewhere (pipes, CI logs): a line at 0, 25, 50, 75 and 100 % only, so a
    log file does not fill up with hundreds of percentages.
    """

    def __init__(self, label: str, stream: TextIO | None = None, *, width: int = 30) -> None:
        self.label = label
        self.stream = stream if stream is not None else sys.stderr
        isatty = getattr(self.stream, "isatty", None)
        try:
            self.interactive = bool(isatty()) if callable(isatty) else False
        except (OSError, ValueError):
            self.interactive = False
        self.width = width
        self._last_step = -1
        self._last_drawn = -1
        self._finished = False

    def __call__(self, fraction: float) -> None:
        fraction = min(1.0, max(0.0, float(fraction)))
        if self.interactive:
            percent = int(fraction * 100)
            if percent == self._last_drawn:
                return
            self._last_drawn = percent
            filled = round(fraction * self.width)
            bar = "#" * filled + "-" * (self.width - filled)
            self.stream.write(f"\r  {self.label} [{bar}] {percent:3d} %")
            self.stream.flush()
            if fraction >= 1.0:
                self.finish()
            return
        step = int(fraction * 4)
        if step > self._last_step:
            self._last_step = step
            self.stream.write(f"  {self.label} {step * 25:3d} %\n")
            self.stream.flush()

    def finish(self) -> None:
        """End the redrawn line (safe to call more than once)."""
        if self.interactive and not self._finished and self._last_drawn >= 0:
            self.stream.write("\n")
            self.stream.flush()
        self._finished = True
