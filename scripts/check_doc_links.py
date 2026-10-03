"""Check relative Markdown links under docs/ and in the repository root's own
Markdown files (README, README.zh-CN, SECURITY, ...) (ARCHITECTURE_V1.md §7.1)."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")


def _targets(markdown: str) -> list[str]:
    found: list[str] = []
    for match in LINK.finditer(markdown):
        raw = match.group(1).strip()
        if raw.startswith("<") and raw.endswith(">"):
            raw = raw[1:-1]
        href = raw.split()[0] if raw else ""
        href = href.split("#", 1)[0]
        if not href:
            continue
        if href.startswith(("http://", "https://", "mailto:", "ftp://")):
            continue
        found.append(href)
    return found


def check(root: Path, extra: list[Path] | None = None) -> list[str]:
    """Links of every ``*.md`` under ``root`` and of the ``extra`` files.

    A link may point anywhere inside the repository, which is ``root``'s
    parent (the default ``root`` is ``docs``).
    """
    if not root.is_dir():
        return [
            f"{root}: documentation directory not found; run from the repository root or pass --root"
        ]
    paths = [*sorted(root.rglob("*.md")), *(extra or [])]
    if not paths:
        return [f"{root}: no Markdown documents found"]
    errors: list[str] = []
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            errors.append(f"{path}: cannot read Markdown: {exc}")
            continue
        for href in _targets(text):
            target = (path.parent / href).resolve()
            try:
                target.relative_to(root.resolve().parent)
            except ValueError:
                errors.append(f"{path}: link escapes the repository: {href}")
                continue
            if not target.exists():
                errors.append(f"{path}: broken link {href}")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("docs"), help="docs directory")
    args = parser.parse_args(argv)
    # The repository root's own documents (README, README.zh-CN, SECURITY...).
    extra = sorted(args.root.resolve().parent.glob("*.md"))
    errors = check(args.root, extra)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print(f"doc links ok under {args.root} and in {len(extra)} root documents")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
