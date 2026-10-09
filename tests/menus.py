"""Drive the interactive menu with scripted answers, as a person would type them.

``drive`` runs :func:`reverbscope.cli.interactive.run_menu` with the answers in
order (an exception in the list is raised at that question: ``KeyboardInterrupt()``
is Ctrl+C), records the command lines the menu runs instead of running them, and
returns what was written with its blanks collapsed (the console wraps
sentences). The end of the answers is the end of input.
"""

from __future__ import annotations

import io
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import TextIO

from reverbscope.cli.console import Console
from reverbscope.cli.interactive import run_menu
from reverbscope.i18n import activate

#: An answer that presses Ctrl+C instead of typing.
CTRL_C = KeyboardInterrupt()
#: An answer that presses Ctrl+D (the end of input).
CTRL_D = EOFError()


@dataclass
class Visit:
    """One run of the menu: how it ended, what it ran, said and asked."""

    code: int
    runs: list[list[str]] = field(default_factory=list)
    raw: str = ""
    prompts: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        """What the menu wrote, on one line."""
        return " ".join(self.raw.split())

    @property
    def lines(self) -> list[str]:
        return self.raw.splitlines()


def drive(
    answers: Sequence[object],
    *,
    width: int = 80,
    lang: str = "en",
    prefix: Sequence[str] = (),
    terminal_edition: bool = False,
    run: Callable[[list[str]], int] | None = None,
    console: Console | None = None,
    out: TextIO | None = None,
) -> Visit:
    """Run the menu on ``answers``. ``out`` is where it writes (default: a
    buffer, which ``Visit.raw`` returns); pass ``sys.stdout`` to read the menu
    and the commands it runs together."""
    pending = iter(answers)
    visit = Visit(code=-1)
    buffer = io.StringIO()
    out = out or buffer

    def ask(prompt: str) -> str:
        visit.prompts.append(prompt)
        try:
            answer = next(pending)
        except StopIteration:
            raise EOFError from None
        if isinstance(answer, BaseException):
            raise type(answer)(*answer.args)
        return str(answer)

    def record(argv: list[str]) -> int:
        visit.runs.append(list(argv))
        return run(argv) if run is not None else 0

    activate(lang)
    try:
        visit.code = run_menu(
            console or Console(width=width),
            ask=ask,
            run=record,
            out=out,
            terminal_edition=terminal_edition,
            prefix=prefix,
        )
    finally:
        activate("en")
    visit.raw = buffer.getvalue()
    return visit
