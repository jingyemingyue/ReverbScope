"""Write a GNU gettext ``.po`` catalog from ordered entries.

Used to keep the extra language files in the same shape as ``zh_CN``.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path


def _quote(text: str) -> str:
    escaped = (
        text.replace("\\", "\\\\").replace('"', '\\"').replace("\t", "\\t").replace("\n", "\\n")
    )
    return f'"{escaped}"'


def _block(kind: str, text: str) -> list[str]:
    if "\n" in text or len(text) > 72:
        lines = [f'{kind} ""']
        remaining = text
        while remaining:
            chunk, remaining = remaining[:72], remaining[72:]
            lines.append(_quote(chunk))
        return lines
    return [f"{kind} {_quote(text)}"]


def write_po(
    path: Path,
    *,
    language: str,
    language_name: str,
    entries: Sequence[dict[str, str]],
) -> None:
    """Write ``entries`` (``msgctxt``, ``msgid``, ``msgstr``) to ``path``."""
    lines = [
        f"# RoomScope {language_name} catalog.",
        "# English is the source language. Numbers stay ASCII; units are not translated.",
        "# License and legal sentences stay in English.",
        'msgid ""',
        'msgstr ""',
        '"Project-Id-Version: roomscope 0.5.0b1\\n"',
        f'"Language: {language}\\n"',
        '"MIME-Version: 1.0\\n"',
        '"Content-Type: text/plain; charset=UTF-8\\n"',
        '"Content-Transfer-Encoding: 8bit\\n"',
        "",
    ]
    for entry in entries:
        msgid = entry["msgid"]
        if not msgid:
            continue
        ctxt = entry.get("msgctxt") or ""
        if ctxt:
            lines.extend(_block("msgctxt", ctxt))
        lines.extend(_block("msgid", msgid))
        lines.extend(_block("msgstr", entry["msgstr"]))
        lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
