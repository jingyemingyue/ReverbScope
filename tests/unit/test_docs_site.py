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
    assert '<h1 id="title">Title</h1>' in html
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


def test_the_site_is_never_written_over_the_documentation(tmp_path: Path) -> None:
    """``--out docs`` deleted the sources before reading them, and ``--out
    docs/user-guide`` still deleted that folder."""
    import pytest

    site = _load()
    docs = tmp_path / "docs"
    (docs / "user-guide").mkdir(parents=True)
    (docs / "index.md").write_text("# Index\n", encoding="utf-8")
    (docs / "user-guide" / "en.md").write_text("# Guide\n", encoding="utf-8")
    for dest in (docs, tmp_path, docs / "user-guide", docs / "new-folder"):
        with pytest.raises(SystemExit):
            site.build_site(docs, dest)
    assert (docs / "index.md").is_file()
    assert (docs / "user-guide" / "en.md").is_file()
    assert not (docs / "new-folder").exists()


def test_the_site_only_replaces_an_empty_folder_or_an_earlier_site(tmp_path: Path) -> None:
    """``--out src`` or ``--out ~/Desktop/ReverbScope`` deleted whatever that
    folder held before the site was written into it."""
    import pytest

    site = _load()
    victim = tmp_path / "victim"
    (victim / "notes").mkdir(parents=True)
    (victim / "notes" / "important.txt").write_text("notes", encoding="utf-8")
    (victim / "thesis.docx").write_bytes(b"keep")
    with pytest.raises(SystemExit, match="victim"):
        site.build_site(Path("docs"), victim)
    assert (victim / "notes" / "important.txt").read_text(encoding="utf-8") == "notes"
    assert (victim / "thesis.docx").read_bytes() == b"keep"
    assert not (victim / "assets").exists()

    a_file = tmp_path / "page.html"
    a_file.write_text("mine", encoding="utf-8")
    with pytest.raises(SystemExit):
        site.build_site(Path("docs"), a_file)
    assert a_file.read_text(encoding="utf-8") == "mine"

    empty = tmp_path / "empty"
    empty.mkdir()
    assert site.build_site(Path("docs"), empty)

    # An earlier site is replaced, and a page whose source is gone goes with it.
    (empty / "removed-page.html").write_text("<p>old</p>", encoding="utf-8")
    (empty / ".DS_Store").write_bytes(b"\0")
    assert site.build_site(Path("docs"), empty)
    assert not (empty / "removed-page.html").exists()
    assert (empty / "index.html").is_file()

    # A file the generator never writes means the folder is not only a site.
    (empty / "user-guide" / "my-notes.txt").write_text("mine", encoding="utf-8")
    with pytest.raises(SystemExit):
        site.build_site(Path("docs"), empty)
    assert (empty / "user-guide" / "my-notes.txt").is_file()


def test_a_folder_holding_only_desktop_litter_counts_as_empty(tmp_path: Path) -> None:
    """Finder writes ``.DS_Store`` as soon as a fresh folder is opened, so
    "mkdir out, open it, run the script" was refused as "not empty"."""
    import pytest

    site = _load()
    for name in sorted(site.OS_LITTER):
        folder = tmp_path / f"litter-{name}"
        folder.mkdir()
        (folder / name).write_bytes(b"\0")
        assert site.build_site(Path("docs"), folder)
        assert (folder / "index.html").is_file()

    # Litter beside a file of the user's own is still a folder to keep.
    mixed = tmp_path / "mixed"
    mixed.mkdir()
    (mixed / ".DS_Store").write_bytes(b"\0")
    (mixed / "thesis.docx").write_bytes(b"keep")
    with pytest.raises(SystemExit, match="mixed"):
        site.build_site(Path("docs"), mixed)
    assert (mixed / "thesis.docx").read_bytes() == b"keep"

    # Only a file counts as litter: a folder that happens to carry the name
    # and holds the user's files must not be deleted with it.
    disguised = tmp_path / "disguised"
    (disguised / ".DS_Store").mkdir(parents=True)
    (disguised / ".DS_Store" / "notes.txt").write_text("mine", encoding="utf-8")
    with pytest.raises(SystemExit, match="disguised"):
        site.build_site(Path("docs"), disguised)
    assert (disguised / ".DS_Store" / "notes.txt").read_text(encoding="utf-8") == "mine"


def test_headings_carry_the_anchors_github_gives_them() -> None:
    """Headings had no id, so every ``#section`` link opened the top of the page."""
    site = _load()
    html = site.markdown_to_html(
        "# Install ReverbScope\n\n## Check the download\n\n### First launch on macOS\n\n"
        "## Python wheel and source\n\n## `reverbscope config`: settings\n\n"
        "## 终端版\n\n### macOS 首次打开\n\n## Python wheel 和源码包\n\n"
        "## 我该下载哪个文件？\n\n## Linux\n\n## Linux\n\n## Linux-1\n\n"
        "See [the check](#check-the-download).\n"
    )
    for anchor in (
        "install-reverbscope",
        "check-the-download",
        "first-launch-on-macos",
        "python-wheel-and-source",
        "reverbscope-config-settings",
        "终端版",
        "macos-首次打开",
        "python-wheel-和源码包",
        "我该下载哪个文件",
        "linux",
        "linux-1",
        "linux-1-1",
    ):
        assert f' id="{anchor}"' in html, anchor
    assert '<h2 id="check-the-download">Check the download</h2>' in html
    assert 'href="#check-the-download"' in html


def test_links_that_leave_docs_point_to_the_repository() -> None:
    """``../CONTRIBUTING.md`` became ``../CONTRIBUTING.html``, which the site
    never has; ``../.github/workflows/release.yml`` was not in it either."""
    site = _load()
    blob = "https://github.com/jingyemingyue/ReverbScope/blob/main/"
    page = site.markdown_to_html(
        "[c](../CONTRIBUTING.md#tests) [w](../.github/workflows/release.yml) "
        "[i](INSTALLATION.md#macos)",
        page="EDITIONS.md",
    )
    assert f'href="{blob}CONTRIBUTING.md#tests"' in page
    assert f'href="{blob}.github/workflows/release.yml"' in page
    assert 'href="INSTALLATION.html#macos"' in page
    nested = site.markdown_to_html(
        "[h](../HARDWARE_TESTS.md) [r](../../README.md)", page="user-guide/en.md"
    )
    assert 'href="../HARDWARE_TESTS.html"' in nested
    assert f'href="{blob}README.md"' in nested


def test_every_link_of_the_generated_site_resolves(tmp_path: Path) -> None:
    import re
    from urllib.parse import unquote

    site = _load()
    dest = (tmp_path / "site").resolve()
    site.build_site(Path("docs"), dest)
    ids = {
        page: set(re.findall(r' id="([^"]+)"', page.read_text(encoding="utf-8")))
        for page in dest.rglob("*.html")
    }
    assert ids
    dead: list[str] = []
    for page in ids:
        for href in re.findall(r'href="([^"]+)"', page.read_text(encoding="utf-8")):
            if href.startswith(("http://", "https://", "mailto:")):
                continue
            path, _, fragment = href.partition("#")
            target = (page.parent / unquote(path)).resolve() if path else page
            if not target.exists() or (fragment and unquote(fragment) not in ids[target]):
                dead.append(f"{page.relative_to(dest)}: {href}")
    assert dead == []


def test_chinese_pages_are_marked_and_framed_in_chinese(tmp_path: Path) -> None:
    """The Chinese pages were ``lang="en"`` with the English sidebar, tag line
    and footer, and docs/index.zh-CN.md never served as their navigation."""
    site = _load()
    dest = tmp_path / "site"
    site.build_site(Path("docs"), dest)
    for name in ("index.zh-CN.html", "INSTALLATION.zh-CN.html", "user-guide/zh-CN.html"):
        page = (dest / name).read_text(encoding="utf-8")
        assert '<html lang="zh-CN">' in page, name
        assert '<p class="tag">文档</p>' in page, name
        assert "<h2>中文用户文档</h2>" in page, name
        assert "For developers" not in page and "Generated from" not in page, name
        assert "以 GitHub 上的 Markdown 为准" in page, name
    nested = (dest / "user-guide" / "zh-CN.html").read_text(encoding="utf-8")
    assert 'href="../index.zh-CN.html">ReverbScope</a>' in nested
    assert 'href="../INSTALLATION.zh-CN.html"' in nested
    # The Chinese hub links README.zh-CN.md on GitHub: no "../" in front of it.
    assert 'href="https://github.com/jingyemingyue/ReverbScope/blob/main/README.zh-CN.md"' in nested
    assert 'href="../https:' not in nested
    english = (dest / "INSTALLATION.html").read_text(encoding="utf-8")
    assert '<html lang="en">' in english
    assert '<p class="tag">Documentation</p>' in english and "<h2>For developers</h2>" in english
    assert "Generated from" in english
