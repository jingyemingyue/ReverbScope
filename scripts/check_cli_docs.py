"""Parse complete RoomScope commands in Markdown shell fences against the current CLI.

This is a syntax check only: no command handler, backend or shell is run.
Inline prose, transcripts in text fences and non-RoomScope commands are not
checked. Shell fences may use bash, sh, shell or console; examples may have
comments, quoted arguments, a leading $ prompt and backslash continuations.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import re
import shlex
import sys
from collections.abc import Iterator
from pathlib import Path

SHELL_LANGUAGES = frozenset({"bash", "sh", "shell", "console"})
FENCE = re.compile(r"^\s*(`{3,}|~{3,})([^`~]*)$")


def commands(markdown: str) -> Iterator[tuple[int, str]]:
    """Yield a shell command and its first source line from each shell fence."""
    fence = ""
    shell = False
    pending = ""
    start = 0
    for number, line in enumerate(markdown.splitlines(), 1):
        match = FENCE.match(line)
        if match:
            marker, info = match.groups()
            if not fence:
                fence = marker
                shell = info.strip() in SHELL_LANGUAGES
                continue
            if marker[0] == fence[0] and len(marker) >= len(fence) and not info.strip():
                if pending:
                    yield start, pending  # An unfinished continuation must fail parsing.
                fence, pending = "", ""
                shell = False
                continue
        if not shell:
            continue
        stripped = line.strip()
        if not pending:
            if not stripped or stripped.startswith("#"):
                continue
            start = number
            command = stripped
        else:
            command = pending[:-1] + " " + stripped
        if command.endswith("\\"):
            pending = command
        else:
            yield start, command
            pending = ""
    if pending:
        yield start, pending


def _is_roomscope(program: str) -> bool:
    return program.replace("\\", "/").rsplit("/", 1)[-1].lower() in {"roomscope", "roomscope.exe"}


def check(root: Path) -> tuple[int, list[str]]:
    """Return the number of CLI examples checked and all source-located errors."""
    if not (root / "docs").is_dir():
        return 0, [
            f"{root / 'docs'}: documentation directory not found; run from the repository root or pass --root"
        ]
    from roomscope.cli.main import build_parser

    parser = build_parser()
    paths = [*sorted(root.glob("*.md")), *sorted((root / "docs").rglob("*.md"))]
    count = 0
    errors: list[str] = []
    for path in paths:
        try:
            markdown = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            errors.append(f"{path}: cannot read Markdown: {exc}")
            continue
        for line, command in commands(markdown):
            try:
                argv = shlex.split(command, comments=True)
            except ValueError as exc:
                # A broken quote in an unrelated shell command is outside this check.
                lexer = shlex.shlex(command, posix=True)
                lexer.whitespace_split = True
                try:
                    head = next(lexer, "")
                    if head == "$":
                        head = next(lexer, "")
                except ValueError:
                    head = ""
                if _is_roomscope(head):
                    errors.append(f"{path}:{line}: {command}\ninvalid shell quoting: {exc}")
                continue
            if argv and argv[0] == "$":
                argv = argv[1:]
            if not argv or not _is_roomscope(argv[0]):
                continue
            count += 1
            output = io.StringIO()
            with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
                try:
                    parser.parse_args(argv[1:])
                except SystemExit as exc:
                    if exc.code != 0:
                        errors.append(f"{path}:{line}: {command}\n{output.getvalue().strip()}")
    if count == 0 and not errors:
        errors.append(f"{root}: no RoomScope commands found in Markdown shell fences")
    return count, errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."), help="repository root")
    args = parser.parse_args(argv)
    count, errors = check(args.root)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print(f"CLI docs ok: {count} commands parsed (syntax only; none executed)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
