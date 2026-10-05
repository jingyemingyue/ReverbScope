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
    assert 'name="description"' in index_html
    assert 'rel="canonical"' in index_html
    assert 'property="og:title"' in index_html
    assert 'property="og:description"' in index_html
    assert site.PLACEHOLDER_BASE_URL in index_html
    assert (dest / "robots.txt").is_file()
    assert (dest / "sitemap.xml").is_file()


def test_site_seo_files_use_placeholder_and_allow_indexing(tmp_path: Path) -> None:
    site = _load()
    dest = tmp_path / "site"
    site.build_site(Path("docs"), dest, base_url=site.PLACEHOLDER_BASE_URL)
    robots = (dest / "robots.txt").read_text(encoding="utf-8")
    assert "User-agent: *" in robots
    assert "Allow: /" in robots
    assert "Disallow:" not in robots
    assert f"Sitemap: {site.PLACEHOLDER_BASE_URL}sitemap.xml" in robots
    assert (
        "submitted" in robots.lower()
        or "not submit" in robots.lower()
        or "nothing was submitted" in robots.lower()
    )

    sitemap = (dest / "sitemap.xml").read_text(encoding="utf-8")
    assert 'xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"' in sitemap
    assert f"{site.PLACEHOLDER_BASE_URL}index.html" in sitemap
    assert f"{site.PLACEHOLDER_BASE_URL}user-guide/en.html" in sitemap
    assert f"{site.PLACEHOLDER_BASE_URL}user-guide/zh-CN.html" in sitemap

    index_html = (dest / "index.html").read_text(encoding="utf-8")
    assert 'lang="en"' in index_html
    assert "<title>" in index_html and "ReverbScope" in index_html
    assert 'content="' in index_html
    index_desc = index_html.split('name="description" content="', 1)[1].split('"', 1)[0]
    assert "recording room" in index_desc
    install = (dest / "INSTALLATION.html").read_text(encoding="utf-8")
    install_desc = install.split('name="description" content="', 1)[1].split('"', 1)[0]
    assert "two betas" in install_desc
    assert "github.com" not in install_desc.casefold()
    zh = (dest / "index.zh-CN.html").read_text(encoding="utf-8")
    assert 'lang="zh-CN"' in zh
    assert 'rel="canonical"' in zh
    assert 'property="og:url"' in zh
    zh_desc = zh.split('name="description" content="', 1)[1].split('"', 1)[0]
    assert "录音房间" in zh_desc


def test_build_site_honours_custom_base_url(tmp_path: Path) -> None:
    site = _load()
    dest = tmp_path / "site"
    site.build_site(Path("docs"), dest, base_url="https://example.com/docs")
    html = (dest / "index.html").read_text(encoding="utf-8")
    assert 'href="https://example.com/docs/index.html"' in html
    robots = (dest / "robots.txt").read_text(encoding="utf-8")
    assert "Sitemap: https://example.com/docs/sitemap.xml" in robots


def test_page_description_skips_language_switcher() -> None:
    site = _load()
    text = (
        "# Title\n\n**English** | [简体中文](index.zh-CN.md)\n\n"
        "This is the documentation hub for measuring rooms with ReverbScope.\n"
    )
    desc = site.page_description(text, fallback="fallback")
    assert "documentation hub" in desc
    assert "English" not in desc


def test_page_description_skips_download_url_line() -> None:
    site = _load()
    text = (
        "# Installing ReverbScope\n\n"
        "**Download page (stable beta):** <https://github.com/jingyemingyue/ReverbScope/releases>\n\n"
        "ReverbScope is offered as two betas. Both are still beta.\n"
    )
    desc = site.page_description(text, fallback="fallback")
    assert "two betas" in desc
    assert "github.com" not in desc.casefold()


def test_build_site_refuses_to_overwrite_landing_page(tmp_path: Path) -> None:
    site = _load()
    landing = tmp_path / "site"
    landing.mkdir()
    (landing / "index.html").write_text(
        '<html><script src="https://utteranc.es/client.js"></script></html>',
        encoding="utf-8",
    )
    (landing / "robots.txt").write_text("User-agent: *\nAllow: /\n", encoding="utf-8")
    (landing / "sitemap.xml").write_text("<urlset></urlset>\n", encoding="utf-8")
    try:
        site.build_site(Path("docs"), landing)
    except site.LandingPageError:
        pass
    else:
        raise AssertionError("expected LandingPageError")
    assert (landing / "index.html").read_text(encoding="utf-8").count("utteranc.es") == 1
    assert (landing / "robots.txt").is_file()
    assert (landing / "sitemap.xml").is_file()


def test_committed_site_is_the_only_published_seo_root() -> None:
    landing = Path("site")
    robots = (landing / "robots.txt").read_text(encoding="utf-8")
    sitemap = (landing / "sitemap.xml").read_text(encoding="utf-8")
    index = (landing / "index.html").read_text(encoding="utf-8")
    assert "User-agent: *" in robots
    assert "Allow: /" in robots
    assert "jingyemingyue.github.io/ReverbScope/sitemap.xml" in robots
    assert sitemap.count("<urlset") == 1
    assert "jingyemingyue.github.io/ReverbScope/" in sitemap
    assert "utteranc.es" in index
    assert 'property="og:title"' in index
    assert index.count("<sitemap") == 0
