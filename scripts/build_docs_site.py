"""Build a themed static HTML site from ``docs/`` (ARCHITECTURE_V1.md S7).

No extra runtime dependency: a small Markdown subset (headings, lists,
tables, fenced code, links, emphasis) is rendered with the standard library.
GitHub still renders the Markdown; this generator is for a browsable site.
"""

from __future__ import annotations

import argparse
import html
import posixpath
import re
import shutil
import unicodedata
from dataclasses import dataclass, replace
from pathlib import Path

HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
UL_ITEM = re.compile(r"^[-*]\s+(.*)$")
OL_ITEM = re.compile(r"^(\d+)\.\s+(.*)$")
TABLE_SEP = re.compile(r"^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$")
INLINE_CODE = re.compile(r"`([^`]+)`")
LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
BOLD = re.compile(r"\*\*([^*]+)\*\*")
ITALIC = re.compile(r"(?<!\*)\*([^*]+)\*(?!\*)")
#: Where a link that leaves docs/ (``../CONTRIBUTING.md``) is shown: the site
#: holds only the pages rendered from docs/.
REPO_BLOB = "https://github.com/jingyemingyue/ReverbScope/blob/main/"

THEME_CSS = """
:root {
  --bg: #f7f5f0;
  --fg: #1c1b18;
  --muted: #5c5850;
  --border: #d7d2c6;
  --accent: #0b5cab;
  --code-bg: #efece4;
  --sidebar: #efece4;
  --max: 52rem;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #161513;
    --fg: #ece8df;
    --muted: #b3ada0;
    --border: #3a372f;
    --accent: #7eb6ff;
    --code-bg: #24221c;
    --sidebar: #1d1b17;
  }
}
* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; }
body {
  font-family: "Iowan Old Style", "Palatino Linotype", Palatino, Georgia, serif;
  background: var(--bg);
  color: var(--fg);
  line-height: 1.55;
}
.layout { display: grid; grid-template-columns: 18rem 1fr; min-height: 100vh; }
nav.sidebar {
  background: var(--sidebar);
  border-right: 1px solid var(--border);
  padding: 1.4rem 1.1rem 2rem;
  position: sticky; top: 0; align-self: start; max-height: 100vh; overflow: auto;
}
nav.sidebar h1 { font-size: 1.1rem; margin: 0 0 0.4rem; }
nav.sidebar p.tag { color: var(--muted); font-size: 0.85rem; margin: 0 0 1rem; }
nav.sidebar h2 { font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.04em;
  color: var(--muted); margin: 1.1rem 0 0.35rem; }
nav.sidebar a { color: var(--accent); text-decoration: none; display: block;
  padding: 0.12rem 0; font-size: 0.95rem; }
nav.sidebar a:hover, nav.sidebar a[aria-current="page"] { text-decoration: underline; }
main { padding: 1.6rem 2rem 3rem; max-width: calc(var(--max) + 4rem); }
article { max-width: var(--max); }
h1, h2, h3, h4 { line-height: 1.25; }
h1 { font-size: 1.85rem; }
h2 { font-size: 1.35rem; margin-top: 1.6rem; border-bottom: 1px solid var(--border);
  padding-bottom: 0.2rem; }
h3 { font-size: 1.15rem; }
p, li { font-size: 1.02rem; }
a { color: var(--accent); }
code, pre { font-family: "Source Code Pro", "SFMono-Regular", Menlo, Consolas, monospace;
  font-size: 0.9em; }
code { background: var(--code-bg); padding: 0.08em 0.28em; border-radius: 3px; }
pre { background: var(--code-bg); padding: 0.85rem 1rem; overflow: auto;
  border: 1px solid var(--border); border-radius: 4px; }
pre code { background: none; padding: 0; }
table { border-collapse: collapse; width: 100%; margin: 1rem 0; font-size: 0.92rem; }
th, td { border: 1px solid var(--border); padding: 0.35rem 0.55rem; text-align: left;
  vertical-align: top; }
th { background: var(--code-bg); }
blockquote { margin: 1rem 0; padding: 0.1rem 0.9rem; border-left: 3px solid var(--accent);
  color: var(--muted); }
hr { border: 0; border-top: 1px solid var(--border); margin: 1.6rem 0; }
footer { margin-top: 2.5rem; color: var(--muted); font-size: 0.85rem; }
@media (max-width: 860px) {
  .layout { grid-template-columns: 1fr; }
  nav.sidebar { position: static; max-height: none; }
}
"""


@dataclass(frozen=True)
class NavItem:
    title: str
    href: str
    section: str


@dataclass(frozen=True)
class Chrome:
    """The text around a page's content, in the page's language."""

    lang: str  # the <html lang> value
    index: str  # the hub page, whose list items make the sidebar
    tag: str
    footer: str


CHROME = {
    "en": Chrome(
        lang="en",
        index="index.md",
        tag="Documentation",
        footer="Generated from <code>docs/</code> by <code>scripts/build_docs_site.py</code>. "
        "Markdown on GitHub remains authoritative.",
    ),
    "zh-CN": Chrome(
        lang="zh-CN",
        index="index.zh-CN.md",
        tag="文档",
        footer="本站由 <code>scripts/build_docs_site.py</code> 根据 <code>docs/</code> 生成，"
        "以 GitHub 上的 Markdown 为准。",
    ),
}


def page_language(relative: Path) -> str:
    """``zh-CN`` for ``*.zh-CN.md`` and ``user-guide/zh-CN.md``, else ``en``."""
    stem = relative.stem
    return "zh-CN" if stem == "zh-CN" or stem.endswith(".zh-CN") else "en"


def rewrite_md_href(href: str, page: str = "index.md") -> str:
    """Turn a same-tree ``.md`` link into the generated ``.html`` page.

    ``page`` is the linking file's path inside docs/. A link that leaves
    docs/ points to the file on GitHub, because the site has no copy of it.
    """
    if href.startswith(("http://", "https://", "mailto:", "ftp://", "#")):
        return href
    path, frag = href, ""
    if "#" in href:
        path, frag = href.split("#", 1)
        frag = "#" + frag
    in_repo = posixpath.normpath(posixpath.join("docs", posixpath.dirname(page), path))
    if in_repo != "docs" and not in_repo.startswith("docs/"):
        return REPO_BLOB + in_repo + frag
    if path.endswith(".md"):
        path = path[: -len(".md")] + ".html"
    return path + frag


def heading_anchor(markdown: str) -> str:
    """The anchor GitHub gives a heading, so ``#check-the-download`` links work.

    Markdown marks are dropped and the text lower-cased; letters (CJK too),
    digits, ``-`` and ``_`` are kept, each space becomes ``-`` and any other
    character (punctuation, full-width or not) is removed.
    """
    text = LINK.sub(r"\1", markdown)
    text = INLINE_CODE.sub(r"\1", text)
    text = ITALIC.sub(r"\1", BOLD.sub(r"\1", text))
    kept: list[str] = []
    for char in text.strip().lower():
        if char == " ":
            kept.append("-")
        elif char in "-_" or unicodedata.category(char)[0] in "LNM":
            kept.append(char)
    return "".join(kept)


def inline_html(text: str, page: str = "index.md") -> str:
    pieces: list[str] = []
    cursor = 0
    for match in LINK.finditer(text):
        pieces.append(_inline_plain(text[cursor : match.start()]))
        label = _inline_plain(match.group(1))
        href = html.escape(rewrite_md_href(match.group(2).split()[0], page), quote=True)
        pieces.append(f'<a href="{href}">{label}</a>')
        cursor = match.end()
    pieces.append(_inline_plain(text[cursor:]))
    return "".join(pieces)


def _inline_plain(text: str) -> str:
    chunks: list[str] = []
    cursor = 0
    for match in INLINE_CODE.finditer(text):
        chunks.append(_emph(text[cursor : match.start()]))
        chunks.append(f"<code>{html.escape(match.group(1))}</code>")
        cursor = match.end()
    chunks.append(_emph(text[cursor:]))
    return "".join(chunks)


def _emph(text: str) -> str:
    escaped = html.escape(text)
    escaped = BOLD.sub(r"<strong>\1</strong>", escaped)
    return ITALIC.sub(r"<em>\1</em>", escaped)


def _split_row(line: str) -> list[str]:
    body = line.strip()
    if body.startswith("|"):
        body = body[1:]
    if body.endswith("|"):
        body = body[:-1]
    return [cell.strip() for cell in body.split("|")]


def markdown_to_html(text: str, page: str = "index.md") -> str:
    """Render a documentation Markdown subset to an HTML fragment.

    ``page`` is the file's path inside docs/; relative links are resolved
    from it.
    """
    lines = text.replace("\r\n", "\n").split("\n")
    out: list[str] = []
    # GitHub numbers a repeated anchor: "linux", "linux-1", "linux-2", ...
    anchors: dict[str, int] = {}
    i = 0
    in_code = False
    code_lang = ""
    code_lines: list[str] = []
    para: list[str] = []
    list_kind: str | None = None

    def close_list() -> None:
        nonlocal list_kind
        if list_kind is not None:
            out.append(f"</{list_kind}>")
            list_kind = None

    def flush_para() -> None:
        if para:
            out.append(f"<p>{inline_html(' '.join(para), page)}</p>")
            para.clear()

    def anchor(heading: str) -> str:
        base = anchor_id = heading_anchor(heading)
        while anchor_id in anchors:
            anchors[base] += 1
            anchor_id = f"{base}-{anchors[base]}"
        anchors[anchor_id] = 0
        return anchor_id

    def open_list(kind: str) -> None:
        nonlocal list_kind
        if list_kind != kind:
            close_list()
            out.append(f"<{kind}>")
            list_kind = kind

    while i < len(lines):
        line = lines[i]
        if in_code:
            if line.startswith("```"):
                lang = html.escape(code_lang) if code_lang else ""
                cls = f' class="language-{lang}"' if lang else ""
                out.append(
                    f"<pre><code{cls}>{html.escape(chr(10).join(code_lines))}\n</code></pre>"
                )
                in_code = False
                code_lines = []
            else:
                code_lines.append(line)
            i += 1
            continue
        if line.startswith("```"):
            flush_para()
            close_list()
            in_code = True
            code_lang = line[3:].strip()
            i += 1
            continue
        stripped = line.strip()
        heading = HEADING.match(line)
        if heading:
            flush_para()
            close_list()
            level = len(heading.group(1))
            title = heading.group(2).strip()
            anchor_id = anchor(title)
            id_attr = f' id="{html.escape(anchor_id, quote=True)}"' if anchor_id else ""
            out.append(f"<h{level}{id_attr}>{inline_html(title, page)}</h{level}>")
            i += 1
            continue
        if stripped in {"---", "***", "___"}:
            flush_para()
            close_list()
            out.append("<hr>")
            i += 1
            continue
        if stripped.startswith(">"):
            flush_para()
            close_list()
            quote = [stripped[1:].strip()]
            i += 1
            while i < len(lines) and lines[i].strip().startswith(">"):
                quote.append(lines[i].strip()[1:].strip())
                i += 1
            out.append(f"<blockquote><p>{inline_html(' '.join(quote), page)}</p></blockquote>")
            continue
        if (
            stripped.startswith("|")
            and i + 1 < len(lines)
            and TABLE_SEP.match(lines[i + 1].strip())
        ):
            flush_para()
            close_list()
            headers = _split_row(stripped)
            i += 2
            rows: list[list[str]] = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append(_split_row(lines[i].strip()))
                i += 1
            cells = "".join(f"<th>{inline_html(h, page)}</th>" for h in headers)
            body = []
            for row in rows:
                tds = "".join(f"<td>{inline_html(c, page)}</td>" for c in row)
                body.append(f"<tr>{tds}</tr>")
            out.append(
                f"<table><thead><tr>{cells}</tr></thead><tbody>{''.join(body)}</tbody></table>"
            )
            continue
        ul = UL_ITEM.match(line)
        if ul:
            flush_para()
            open_list("ul")
            out.append(f"<li>{inline_html(ul.group(1), page)}</li>")
            i += 1
            continue
        ol = OL_ITEM.match(line)
        if ol:
            flush_para()
            open_list("ol")
            out.append(f"<li>{inline_html(ol.group(2), page)}</li>")
            i += 1
            continue
        if not stripped:
            flush_para()
            close_list()
            i += 1
            continue
        para.append(stripped)
        i += 1
    if in_code:
        lang = html.escape(code_lang) if code_lang else ""
        cls = f' class="language-{lang}"' if lang else ""
        out.append(f"<pre><code{cls}>{html.escape(chr(10).join(code_lines))}\n</code></pre>")
    flush_para()
    close_list()
    return "\n".join(out)


def nav_items(index_text: str) -> list[NavItem]:
    items: list[NavItem] = []
    section = "Docs"
    for line in index_text.splitlines():
        heading = HEADING.match(line)
        if heading and len(heading.group(1)) == 2:
            section = heading.group(2).strip()
            continue
        ul = UL_ITEM.match(line)
        if not ul:
            continue
        link = LINK.search(ul.group(1))
        if link is None:
            continue
        items.append(
            NavItem(title=link.group(1), href=rewrite_md_href(link.group(2)), section=section)
        )
    return items


def _sidebar(items: list[NavItem], current: str, css_prefix: str, chrome: Chrome) -> str:
    home = rewrite_md_href(chrome.index)
    blocks = [
        f'<h1><a href="{html.escape(css_prefix + home)}">ReverbScope</a></h1>',
        f'<p class="tag">{html.escape(chrome.tag)}</p>',
    ]
    last = ""
    for item in items:
        if item.section != last:
            blocks.append(f"<h2>{html.escape(item.section)}</h2>")
            last = item.section
        # The Chinese hub links README.zh-CN.md and the issue forms on GitHub.
        external = "://" in item.href or item.href.startswith("mailto:")
        href = html.escape(item.href if external else css_prefix + item.href)
        current_attr = ' aria-current="page"' if item.href == current else ""
        blocks.append(f'<a href="{href}"{current_attr}>{html.escape(item.title)}</a>')
    return "\n".join(blocks)


def _page(title: str, body: str, sidebar: str, css_href: str, chrome: Chrome) -> str:
    return (
        f'<!DOCTYPE html>\n<html lang="{chrome.lang}">\n<head>\n'
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{html.escape(title)} — ReverbScope</title>\n"
        f'<link rel="stylesheet" href="{html.escape(css_href)}">\n'
        '</head>\n<body>\n<div class="layout">\n'
        f'<nav class="sidebar">{sidebar}</nav>\n'
        f"<main><article>{body}</article>\n"
        f"<footer>{chrome.footer}</footer>\n</main>\n</div>\n</body>\n</html>\n"
    )


def _first_heading(markdown: str, fallback: str) -> str:
    for line in markdown.splitlines():
        match = HEADING.match(line)
        if match:
            return match.group(2).strip()
    return fallback


def rel_prefix(relative: Path) -> str:
    depth = len(relative.parent.parts)
    return "" if depth == 0 else "../" * depth


#: Files the desktop puts into a folder that was browsed (Finder, Explorer).
OS_LITTER = frozenset({".DS_Store", "Thumbs.db", "desktop.ini"})


def holds_only_litter(folder: Path) -> bool:
    """Whether ``folder`` is empty apart from what Finder or Explorer put there.

    A folder that was just made and opened in Finder already holds ``.DS_Store``,
    so it must count as empty. Only files count: a folder that carries one of
    these names may hold the user's own files.
    """
    return all(entry.name in OS_LITTER and not entry.is_dir() for entry in folder.iterdir())


def is_previous_site(folder: Path) -> bool:
    """Whether ``folder`` holds nothing but what :func:`build_site` writes."""
    if not (folder / "assets" / "theme.css").is_file():
        return False
    for path in folder.rglob("*"):
        if path.is_dir() or path.name in OS_LITTER:
            continue
        relative = path.relative_to(folder)
        if relative.as_posix() == "assets/theme.css":
            continue
        if path.is_symlink() or path.suffix != ".html" or relative.parts[0] == "assets":
            return False
    return True


def build_site(docs: Path, dest: Path) -> list[Path]:
    """Render every Markdown file under ``docs`` into ``dest``. Returns HTML paths."""
    resolved = dest.resolve()
    sources = docs.resolve()
    if resolved.is_relative_to(sources) or sources.is_relative_to(resolved):
        # dest is removed first: "--out docs", "--out ." or "--out docs/images"
        # would delete the sources.
        raise SystemExit(
            f"refusing to write the site into {dest}: it holds or is inside the documentation"
        )
    if dest.exists() or dest.is_symlink():
        # dest is deleted before it is written, so "--out src" or a folder of
        # the user's own files must be refused, not emptied.
        if dest.is_symlink() or not dest.is_dir():
            raise SystemExit(f"refusing to write the site into {dest}: it is not a folder")
        if not holds_only_litter(dest) and not is_previous_site(dest):
            raise SystemExit(
                f"refusing to write the site into {dest}: the folder is not empty and "
                "holds more than a site written by this script; choose a new folder"
            )
        shutil.rmtree(dest)
    (dest / "assets").mkdir(parents=True)
    (dest / "assets" / "theme.css").write_text(THEME_CSS.lstrip(), encoding="utf-8")
    navigation = {
        chrome.index: nav_items((docs / chrome.index).read_text(encoding="utf-8"))
        for chrome in CHROME.values()
        if (docs / chrome.index).is_file()
    }
    written: list[Path] = []
    for source in sorted(docs.rglob("*.md")):
        relative = source.relative_to(docs)
        chrome = CHROME[page_language(relative)]
        if chrome.index not in navigation:
            # No hub in this language: its pages use the English one.
            chrome = replace(chrome, index=CHROME["en"].index)
        target = dest / relative.with_suffix(".html")
        target.parent.mkdir(parents=True, exist_ok=True)
        markdown = source.read_text(encoding="utf-8")
        title = _first_heading(markdown, source.stem)
        prefix = rel_prefix(relative)
        current = relative.with_suffix(".html").as_posix()
        page = _page(
            title,
            markdown_to_html(markdown, relative.as_posix()),
            _sidebar(navigation.get(chrome.index, []), current, prefix, chrome),
            prefix + "assets/theme.css",
            chrome,
        )
        target.write_text(page, encoding="utf-8")
        written.append(target)
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--docs", type=Path, default=Path("docs"), help="Markdown source")
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("site"),
        help="HTML output folder: a new or empty one, or an earlier site, which is replaced",
    )
    args = parser.parse_args(argv)
    written = build_site(args.docs, args.out)
    print(f"wrote {len(written)} pages under {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
