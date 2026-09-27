"""Simplified Chinese outside the application: the Windows installer, the
README and the user documents (each language links the other)."""

from __future__ import annotations

import re
from pathlib import Path

ISS = Path("packaging/windows/roomscope.iss")
ROOT = Path(".")


def _iss() -> str:
    raw = ISS.read_bytes()
    # Inno Setup reads a script with non-ASCII text as UTF-8 only with a BOM.
    assert raw.startswith(b"\xef\xbb\xbf")
    return raw.decode("utf-8-sig")


def test_installer_offers_english_and_simplified_chinese() -> None:
    iss = _iss()
    languages = re.findall(r'^Name: "(\w+)"; MessagesFile: "([^"]+)"', iss, re.MULTILINE)
    assert ("english", "compiler:Default.isl") in languages
    assert ("chinesesimplified", "compiler:Languages\\ChineseSimplified.isl") in languages
    # The Windows UI language picks the installer language; the dialog only
    # appears when it is neither.
    assert "LanguageDetectionMethod=uilanguage" in iss
    assert "ShowLanguageDialog=auto" in iss
    # Per-user install without administrator rights, unchanged.
    assert "PrivilegesRequired=lowest" in iss


def test_installer_texts_are_localized_messages() -> None:
    iss = _iss()
    names = {
        name for name, _file in re.findall(r'^Name: "(\w+)"; MessagesFile: "([^"]+)"', iss, re.M)
    }
    custom = re.findall(r"^(\w+)\.(\w+)=(.+)$", iss, re.MULTILINE)
    by_message: dict[str, set[str]] = {}
    for language, message, text in custom:
        assert text.strip()
        by_message.setdefault(message, set()).add(language)
    # Every custom message exists in every language.
    for message, languages in by_message.items():
        assert languages == names, message
    icons = iss.split("[Icons]", 1)[1].split("\n[", 1)[0]
    for line in icons.strip().splitlines():
        name = re.search(r'Name: "([^"]+)"', line)
        assert name is not None
        # Shortcut names are the app name, a {cm:...} message or a constant.
        visible = re.sub(r"\{[^{}]*(\{[^{}]*\})?[^{}]*\}", "", name.group(1)).strip("\\ ")
        assert visible in {"", "RoomScope"}, line


def test_release_workflow_requires_the_chinese_installer_messages() -> None:
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8")
    assert "Languages\\ChineseSimplified.isl" in workflow


def test_readmes_switch_language_at_the_top() -> None:
    english = (ROOT / "README.md").read_text(encoding="utf-8").splitlines()
    chinese = (ROOT / "README.zh-CN.md").read_text(encoding="utf-8").splitlines()
    assert "[简体中文](README.zh-CN.md)" in english[0]
    assert "[English](README.md)" in chinese[0]


def test_readme_zh_cn_keeps_the_limits() -> None:
    text = (ROOT / "README.zh-CN.md").read_text(encoding="utf-8")
    for fact in ("硬件验证", "预发布", "公证", "Authenticode"):
        assert fact in text, fact
    assert "评分" in text  # RoomScope gives no room score
    assert "DAW" in text


def _pairs() -> list[tuple[Path, Path]]:
    pairs = []
    found = [*ROOT.glob("*.zh-CN.md"), *Path("docs").rglob("*.zh-CN.md")]
    found.append(Path("docs/user-guide/zh-CN.md"))
    for chinese in sorted(set(found)):
        english = chinese.with_name(chinese.name.replace(".zh-CN.md", ".md"))
        if chinese.name == "zh-CN.md":
            english = chinese.with_name("en.md")
        if english.exists():
            pairs.append((english, chinese))
    return pairs


def test_every_chinese_document_and_its_english_original_link_each_other() -> None:
    pairs = _pairs()
    names = {c.as_posix() for _e, c in pairs}
    for expected in (
        "README.zh-CN.md",
        "SECURITY.zh-CN.md",
        "docs/HARDWARE_TESTS.zh-CN.md",
        "docs/user-guide/zh-CN.md",
        "docs/user-guide/daw-setup.zh-CN.md",
        "docs/COMPATIBILITY.zh-CN.md",
    ):
        assert expected in names, expected
    for english, chinese in pairs:
        en_text = english.read_text(encoding="utf-8")
        zh_text = chinese.read_text(encoding="utf-8")
        assert chinese.name in en_text, f"{english} does not link {chinese.name}"
        assert english.name in zh_text, f"{chinese} does not link {english.name}"


def test_docs_index_says_which_documents_are_in_chinese() -> None:
    index = Path("docs/index.md").read_text(encoding="utf-8")
    assert "简体中文" in index
    for _english, chinese in _pairs():
        if chinese.parent.as_posix().startswith("docs"):
            assert chinese.name in index, chinese
