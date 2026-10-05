"""The English and Simplified Chinese GitHub issue forms stay in sync.

Each ``<form>.yml`` in ``.github/ISSUE_TEMPLATE`` has a ``<form>-zh-CN.yml``
translation. Only the prose is translated: the fields, their ids, required
flags, dropdown option counts and defaults, text rendering and the GitHub
labels must be identical, so a report filed in either language carries the
same evidence and lands in the same triage queue.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

yaml = pytest.importorskip("yaml")

ROOT = Path(__file__).resolve().parents[2]
FORMS = ROOT / ".github" / "ISSUE_TEMPLATE"
ZH_SUFFIX = "-zh-CN"
REPO_BLOB = "https://github.com/jingyemingyue/ReverbScope/blob/main/"

pytestmark = pytest.mark.skipif(
    not FORMS.is_dir(), reason="issue forms are not part of this checkout (sdist)"
)


def _load(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict), f"{path.name}: not a mapping"
    return data


def _english_forms() -> list[str]:
    if not FORMS.is_dir():
        return []
    return sorted(
        p.stem
        for p in FORMS.glob("*.yml")
        if p.name != "config.yml" and not p.stem.endswith(ZH_SUFFIX)
    )


def _structure(form: dict[str, Any]) -> list[tuple[Any, ...]]:
    """Everything about the body that must not differ between languages."""
    items = []
    for item in form["body"]:
        attributes = item.get("attributes", {})
        options = attributes.get("options")
        items.append(
            (
                item["type"],
                item.get("id"),
                bool(item.get("validations", {}).get("required", False)),
                None if options is None else len(options),
                attributes.get("default"),
                attributes.get("multiple"),
                attributes.get("render"),
            )
        )
    return items


def _title_prefix(form: dict[str, Any]) -> str | None:
    match = re.match(r"\[[^\]]+\]", form.get("title", ""))
    return match.group(0) if match else None


def _doc_links(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    return re.findall(re.escape(REPO_BLOB) + r"([^\s)\"']+)", text)


def _zh_counterpart(doc: str) -> str:
    if doc == "docs/user-guide/en.md":
        return "docs/user-guide/zh-CN.md"
    stem, _, ext = doc.rpartition(".")
    return f"{stem}{ZH_SUFFIX}.{ext}"


def test_the_expected_forms_exist() -> None:
    assert {"bug", "measurement", "hardware", "daw", "feature"} <= set(_english_forms())


def test_every_form_file_has_a_partner() -> None:
    english = set(_english_forms())
    chinese = {p.stem.removesuffix(ZH_SUFFIX) for p in FORMS.glob(f"*{ZH_SUFFIX}.yml")}
    assert english == chinese


@pytest.mark.parametrize("stem", _english_forms())
def test_chinese_form_matches_english_form(stem: str) -> None:
    en_path = FORMS / f"{stem}.yml"
    zh_path = FORMS / f"{stem}{ZH_SUFFIX}.yml"
    en, zh = _load(en_path), _load(zh_path)

    assert en["name"].endswith("(English)"), en["name"]
    assert zh["name"].endswith("（简体中文）"), zh["name"]
    assert zh.get("labels") == en.get("labels")
    assert _title_prefix(zh) == _title_prefix(en)

    en_body, zh_body = _structure(en), _structure(zh)
    assert [i[:2] for i in zh_body] == [i[:2] for i in en_body], "item types / ids differ"
    assert zh_body == en_body

    ids = [item["id"] for item in en["body"] if "id" in item]
    assert len(ids) == len(set(ids)), f"{stem}: duplicate ids"


@pytest.mark.parametrize("stem", _english_forms())
def test_chinese_form_links_chinese_docs_where_they_exist(stem: str) -> None:
    for doc in _doc_links(FORMS / f"{stem}{ZH_SUFFIX}.yml"):
        if ZH_SUFFIX in doc or doc.endswith("zh-CN.md"):
            continue
        counterpart = _zh_counterpart(doc)
        assert not (ROOT / counterpart).is_file(), f"link {counterpart} instead of {doc}"
    for doc in _doc_links(FORMS / f"{stem}.yml"):
        assert "zh-CN" not in doc, f"English form {stem}.yml links {doc}"


def test_config_parses_and_offers_both_languages() -> None:
    config = _load(FORMS / "config.yml")
    assert config["blank_issues_enabled"] is True
    names = [link["name"] for link in config["contact_links"]]
    assert any(re.search(r"[一-鿿]", name) for name in names)
    assert any(re.search(r"[A-Za-z]{4,}", name) for name in names)
    for link in config["contact_links"]:
        assert link["url"].startswith("https://"), link
        assert link["about"], link


#: Evidence and privacy rules: when the English form says it, the Chinese
#: form must say it too (the Chinese words are those the forms use).
_RULES = (
    ("CI", "CI"),
    ("fake", "fake"),
    ("Demo", "演示"),
    ("personal", "个人"),
    ("reverbscope doctor", "reverbscope doctor"),
)


def _code_spans(text: str) -> set[str]:
    """Inline code: commands, flags, file names; the same in every language."""
    return {s for s in re.findall(r"`([^`\n]+)`", text) if re.match(r"[\w./\[-]", s)}


@pytest.mark.parametrize("stem", _english_forms())
def test_chinese_form_keeps_every_command_and_evidence_rule(stem: str) -> None:
    english = (FORMS / f"{stem}.yml").read_text(encoding="utf-8")
    chinese = (FORMS / f"{stem}{ZH_SUFFIX}.yml").read_text(encoding="utf-8")
    assert _code_spans(english) <= _code_spans(chinese), sorted(
        _code_spans(english) - _code_spans(chinese)
    )
    for english_word, chinese_word in _RULES:
        if english_word in english:
            assert chinese_word in chinese, f"{stem}: {chinese_word!r} missing"
