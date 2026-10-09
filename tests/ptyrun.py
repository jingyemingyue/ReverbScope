"""Run ``reverbscope`` on a real pseudo-terminal, as a person at a terminal does.

The menu is for a terminal: ``input()`` reads the tty's line, Ctrl+C is a
signal the terminal driver sends, and Qt can abort the process. None of that
happens with a scripted ``ask``; this starts the program in a pty (POSIX only)
and types at it. ``expect`` waits for text instead of sleeping, so a slow
machine only makes a test slower.
"""

from __future__ import annotations

import contextlib
import fcntl
import os
import pty
import select
import struct
import subprocess
import sys
import termios
import time
from collections.abc import Mapping, Sequence

CTRL_C = "\x03"
CTRL_D = "\x04"

#: Runs first in the child, which is a session leader of its own: the pty
#: becomes its controlling terminal (so that the terminal driver can send
#: Ctrl+C as SIGINT to it) and the program takes its place. A trampoline in
#: Python rather than ``preexec_fn`` or ``pty.fork``: forking from a process
#: with threads (numpy's, Qt's) is what Python 3.12 warns about.
_TRAMPOLINE = (
    "import fcntl, os, sys, termios; "
    "fcntl.ioctl(0, termios.TIOCSCTTY, 0); "
    "os.execv(sys.argv[1], sys.argv[1:])"
)


class Terminal:
    """A program running with a pty as its stdin, stdout and stderr."""

    def __init__(
        self,
        argv: Sequence[str],
        *,
        env: Mapping[str, str],
        cwd: str,
        columns: int = 88,
        rows: int = 40,
    ) -> None:
        self.output = ""
        self.status: int | None = None
        self._buffer = b""
        master, slave = pty.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", rows, columns, 0, 0))
        self.process = subprocess.Popen(
            [sys.executable, "-c", _TRAMPOLINE, *argv],
            stdin=slave,
            stdout=slave,
            stderr=slave,
            cwd=cwd,
            env=dict(env),
            start_new_session=True,
            close_fds=True,
        )
        os.close(slave)
        self.fd = master

    @classmethod
    def python(cls, *args: str, env: Mapping[str, str], cwd: str) -> Terminal:
        """``reverbscope`` with ``args``, from this interpreter and this source tree."""
        environment = {**env, "PYTHONPATH": os.pathsep.join(sys.path)}
        return cls([sys.executable, "-m", "reverbscope.cli.main", *args], env=environment, cwd=cwd)

    def _read(self, wait: float) -> bool:
        ready, _w, _x = select.select([self.fd], [], [], wait)
        if not ready:
            return True
        try:
            data = os.read(self.fd, 65536)
        except OSError:  # the child closed its side
            return False
        if not data:
            return False
        self._buffer += data
        self.output = self._buffer.decode("utf-8", "replace").replace("\r\n", "\n")
        return True

    def expect(self, text: str, *, after: int = 0, timeout: float = 60.0) -> int:
        """Wait until ``text`` appears in the output after offset ``after``;
        return the offset just past it."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            found = self.output.find(text, after)
            if found >= 0:
                return found + len(text)
            if not self._read(0.2):
                break
        found = self.output.find(text, after)
        if found >= 0:
            return found + len(text)
        raise AssertionError(f"{text!r} did not appear; the screen so far:\n{self.output}")

    def send(self, text: str) -> None:
        os.write(self.fd, text.encode("utf-8"))

    def type(self, text: str) -> None:
        """``text`` and Enter."""
        self.send(text + "\r")

    def finish(self, timeout: float = 60.0) -> int:
        """Wait for the program to end; its exit code (-N for signal N)."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            status = self.process.poll()
            if status is not None:
                self._read(0.1)
                self.status = status
                os.close(self.fd)
                return status
            self._read(0.1)
        self.process.kill()
        self.process.wait()
        os.close(self.fd)
        raise AssertionError(f"the program did not end; the screen so far:\n{self.output}")

    def close(self) -> None:
        """Make sure nothing is left running (after a failed assertion)."""
        if self.status is None:
            self.process.kill()
            self.process.wait()
            with contextlib.suppress(OSError):
                os.close(self.fd)
