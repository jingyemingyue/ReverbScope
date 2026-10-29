"""English/Chinese documentation pairs: heading levels and table shapes.

Full translation pairs must match. Digests (ARCHITECTURE_V1, GUIDELINES) are
explicitly exempt from shape parity but must say they are digests and link
both ways. The documentation hubs (index) must keep the language table and a
Research notes section on both sides.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(".")
DOCS = ROOT / "docs"
HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")

#: Pairs that are digests / summaries, not line-by-line translations.
DIGEST_RELATIVE = {
    "docs/ARCHITECTURE_V1.md",
    "docs/GUIDELINES.md",
}

#: Hubs with intentionally different section titles; still require shared pieces.
HUB_RELATIVE = {
    "docs/index.md",
}


def _pairs() -> list[tuple[Path, Path]]:
    pairs: list[tuple[Path, Path]] = []
    found = [*ROOT.glob("*.zh-CN.md"), *DOCS.rglob("*.zh-CN.md")]
    found.append(DOCS / "user-guide" / "zh-CN.md")
    for chinese in sorted(set(found)):
        english = chinese.with_name(chinese.name.replace(".zh-CN.md", ".md"))
        if chinese.name == "zh-CN.md":
            english = chinese.with_name("en.md")
        if english.exists():
            pairs.append((english, chinese))
    return pairs


def _headings(text: str) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    in_fence = False
    for line in text.splitlines():
        if line.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        match = HEADING.match(line)
        if match:
            out.append((len(match.group(1)), match.group(2).strip()))
    return out


def _split_row(row: str) -> list[str]:
    """Split a GFM table row on ``|``, keeping ``\\|`` as a literal pipe."""
    body = row.strip().strip("|")
    cells: list[str] = []
    current: list[str] = []
    escaped = False
    for char in body:
        if escaped:
            current.append(char)
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == "|":
            cells.append("".join(current).strip())
            current = []
            continue
        current.append(char)
    cells.append("".join(current).strip())
    return cells


def _tables(text: str) -> list[tuple[int, int]]:
    """Return ``(row_count, column_count)`` for each GFM table outside fences."""
    lines = text.splitlines()
    out: list[tuple[int, int]] = []
    in_fence = False
    index = 0
    while index < len(lines):
        line = lines[index]
        if line.strip().startswith("```"):
            in_fence = not in_fence
            index += 1
            continue
        if in_fence or not line.startswith("|"):
            index += 1
            continue
        block: list[str] = []
        while index < len(lines) and lines[index].startswith("|"):
            block.append(lines[index])
            index += 1
        rows: list[list[str]] = []
        for row in block:
            cells = _split_row(row)
            if all(re.match(r"^:?-+:?$", cell or "-") for cell in cells):
                continue
            rows.append(cells)
        if rows:
            out.append((len(rows), max(len(row) for row in rows)))
    return out


def test_full_translation_pairs_match_heading_levels_and_tables() -> None:
    failures: list[str] = []
    for english, chinese in _pairs():
        rel = english.as_posix()
        if rel in DIGEST_RELATIVE or rel in HUB_RELATIVE:
            continue
        en_text = english.read_text(encoding="utf-8")
        zh_text = chinese.read_text(encoding="utf-8")
        en_levels = [level for level, _title in _headings(en_text)]
        zh_levels = [level for level, _title in _headings(zh_text)]
        if en_levels != zh_levels:
            failures.append(f"{rel}: heading levels {en_levels} != {zh_levels}")
        en_tables = _tables(en_text)
        zh_tables = _tables(zh_text)
        if en_tables != zh_tables:
            failures.append(f"{rel}: tables {en_tables} != {zh_tables}")
    assert failures == [], "EN/ZH structure:\n" + "\n".join(failures)


@pytest.mark.parametrize("english_rel", sorted(DIGEST_RELATIVE))
def test_digest_pairs_declare_themselves(english_rel: str) -> None:
    english = Path(english_rel)
    chinese = english.with_name(english.stem + ".zh-CN.md")
    assert chinese.is_file(), chinese
    zh = chinese.read_text(encoding="utf-8")
    en = english.read_text(encoding="utf-8")
    assert "摘要" in zh or "digest" in zh.lower(), f"{chinese} should say it is a digest"
    assert chinese.name in en, f"{english} should link {chinese.name}"
    assert english.name in zh, f"{chinese} should link {english.name}"


def test_index_hubs_share_language_table_and_research_notes() -> None:
    english = DOCS / "index.md"
    chinese = DOCS / "index.zh-CN.md"
    en = english.read_text(encoding="utf-8")
    zh = chinese.read_text(encoding="utf-8")
    assert _tables(en) and _tables(zh), "both hubs need the language pairing table"
    assert _tables(en)[0] == _tables(zh)[0], "language table shape must match"
    assert any(title.lower().startswith("research") for _lv, title in _headings(en))
    assert any("研究" in title for _lv, title in _headings(zh))
