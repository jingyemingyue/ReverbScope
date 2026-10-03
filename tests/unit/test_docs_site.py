from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load():
    path = Path("scripts") / "build_docs_site.py"
    spec = importlib.util.spec_from_file_location("build_docs_site", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_markdown_subset_renders_tables_links_and_code() -> None:
    site = _load()
    html = site.markdown_to_html(
        "# Title\n\nSee [Architecture](ARCHITECTURE_V1.md#scope).\n\n"
        "| A | B |\n| --- | --- |\n| 1 | `code` |\n\n"
        "- item **bold**\n\n```python\nprint(1)\n```\n"
    )
    assert "<h1>Title</h1>" in html
    assert 'href="ARCHITECTURE_V1.html#scope"' in html
    assert "<table>" in html and "<th>A</th>" in html
    assert "<code>code</code>" in html
    assert "<strong>bold</strong>" in html
    assert 'class="language-python"' in html
    assert "prefers-color-scheme" not in html


def test_build_site_writes_themed_pages(tmp_path: Path) -> None:
    site = _load()
    dest = tmp_path / "site"
    written = site.build_site(Path("docs"), dest)
    index = dest / "index.html"
    architecture = dest / "ARCHITECTURE_V1.html"
    css = dest / "assets" / "theme.css"
    assert index.is_file()
    assert architecture.is_file()
    assert css.is_file()
    assert any(path.name == "en.html" for path in written)
    index_html = index.read_text(encoding="utf-8")
    css_text = css.read_text(encoding="utf-8")
    assert "ReverbScope" in index_html
    assert "user-guide/en.html" in index_html
    assert "prefers-color-scheme: dark" in css_text
    assert 'class="sidebar"' in index_html
    assert "Generated from" in index_html
    assert (dest / "user-guide" / "en.html").is_file()
    nested = (dest / "user-guide" / "en.html").read_text(encoding="utf-8")
    assert 'href="../assets/theme.css"' in nested
