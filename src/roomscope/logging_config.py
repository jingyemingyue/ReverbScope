"""Logging configuration.

Library code only ever calls ``logging.getLogger(__name__)``; front ends call
:func:`configure_logging` once. The library never configures the root logger on
import, so RoomScope can be embedded without side effects.
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from typing import IO

LOGGER_NAME = "roomscope"
_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"
LOG_FILENAME = "roomscope.log"
LOG_MAX_BYTES = 1_000_000
LOG_BACKUPS = 3


def get_logger(name: str | None = None) -> logging.Logger:
    """Return a logger below the ``roomscope`` namespace."""
    if name is None or name == LOGGER_NAME:
        return logging.getLogger(LOGGER_NAME)
    if name.startswith(LOGGER_NAME + "."):
        return logging.getLogger(name)
    return logging.getLogger(f"{LOGGER_NAME}.{name}")


class _SharedRotatingFileHandler(RotatingFileHandler):
    """Rotating log that keeps appending when another process holds the file.

    Windows refuses to rename an open file (WinError 32), so a second RoomScope
    process (the CLI next to the GUI) would make every later record fail. The
    rotation is skipped until the file can be renamed.
    """

    def doRollover(self) -> None:  # noqa: N802 - logging API
        try:
            super().doRollover()
        except PermissionError:
            if self.stream is None:
                self.stream = self._open()


def configure_logging(
    level: int | str = logging.INFO,
    stream: IO[str] | None = None,
    *,
    fmt: str = _FORMAT,
    log_file: bool = True,
) -> logging.Logger:
    """Configure the ``roomscope`` logger with a stream handler and a log file.

    The rotating file lives under ``$ROOMSCOPE_HOME/roomscope.log``. Calling
    this more than once replaces the previous RoomScope handlers instead of
    stacking them.
    """
    logger = logging.getLogger(LOGGER_NAME)
    for handler in list(logger.handlers):
        if getattr(handler, "_roomscope_handler", False):
            logger.removeHandler(handler)
    handler = logging.StreamHandler(stream or sys.stderr)
    handler.setFormatter(logging.Formatter(fmt))
    handler._roomscope_handler = True  # type: ignore[attr-defined]
    logger.addHandler(handler)
    if log_file:
        try:
            from roomscope.io.recent import roomscope_home

            path = roomscope_home() / LOG_FILENAME
            path.parent.mkdir(parents=True, exist_ok=True)
            file_handler = _SharedRotatingFileHandler(
                path, maxBytes=LOG_MAX_BYTES, backupCount=LOG_BACKUPS, encoding="utf-8"
            )
            file_handler.setFormatter(logging.Formatter(fmt))
            file_handler._roomscope_handler = True  # type: ignore[attr-defined]
            logger.addHandler(file_handler)
        except OSError:
            pass
    logger.setLevel(level)
    logger.propagate = False
    return logger
