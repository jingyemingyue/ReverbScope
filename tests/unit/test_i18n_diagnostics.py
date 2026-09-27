"""Stored diagnostics stay English in result files and are shown translated.

``diag()`` returns the English sentence that result.json keeps; ``localize()``
recognises it at display time through the ``"diagnostic"`` catalog entries.
Text that matches no template, as in a session written by another version,
is shown unchanged, so old files still open.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

import pytest

from roomscope.i18n import DIAGNOSTIC_CONTEXT, activate, diag, localize, parse_po

CATALOG = Path("src/roomscope/locale/zh_CN/LC_MESSAGES/roomscope.po")
PREFIX = f"{DIAGNOSTIC_CONTEXT}\x04"


@pytest.fixture
def zh() -> Iterator[None]:
    activate("zh_CN")
    try:
        yield
    finally:
        activate("en")


def _diagnostic_templates() -> dict[str, str]:
    return {k[len(PREFIX) :]: v for k, v in parse_po(CATALOG).items() if k.startswith(PREFIX)}


def test_diag_returns_the_english_sentence() -> None:
    assert diag("band {band} has {n:.1f} dB") == "band {band} has {n:.1f} dB"
    assert diag("band {band} has {n:.1f} dB", band="63 Hz", n=12.345) == "band 63 Hz has 12.3 dB"


def test_english_display_is_the_stored_text() -> None:
    activate("en")
    for template in list(_diagnostic_templates())[:20]:
        assert localize(template) == template


def test_every_catalogued_diagnostic_is_recognised(zh: None) -> None:
    """Each template, filled with plausible values, comes back in Chinese."""
    templates = _diagnostic_templates()
    assert templates, "no diagnostic templates in the catalog"
    for template in templates:
        fields = set(re.findall(r"\{(\w+)[^{}]*\}", template))
        values = {name: _sample(template, name) for name in fields}
        english = template.format(**values)
        shown = localize(english)
        assert shown != english or not re.search(r"[A-Za-z]{4,}", _strip(template)), (
            template,
            shown,
        )


def _sample(template: str, name: str) -> object:
    spec = re.search(r"\{" + name + r"(?::([^{}]*))?\}", template)
    fmt = spec.group(1) if spec and spec.group(1) else ""
    if fmt and fmt[-1] in "dn":
        return 7
    if fmt and fmt[-1] in "efg%":
        return 3.25
    if fmt:
        return 3.25
    return "7"


def _strip(template: str) -> str:
    return re.sub(r"\{[^{}]*\}", "", template)


def test_unknown_or_legacy_text_is_shown_unchanged(zh: None) -> None:
    legacy = "a note written by RoomScope 0.1 that no template matches"
    assert localize(legacy) == legacy
    assert localize("") == ""
    assert localize("/Users/someone/room.wav") == "/Users/someone/room.wav"


def test_translations_keep_percent_placeholders() -> None:
    """argparse's messages use %(name)s placeholders; they must survive."""
    for msgid, msgstr in parse_po(CATALOG).items():
        english = sorted(re.findall(r"%\(\w+\)[sdrf]|%[sdr]", msgid))
        if english:
            assert sorted(re.findall(r"%\(\w+\)[sdrf]|%[sdr]", msgstr)) == english, msgid


def test_diagnostic_contexts_are_consistent() -> None:
    """A diagnostic template is catalogued under its context only once, and
    never also as a plain msgid with a different translation."""
    catalog = parse_po(CATALOG)
    for template, translated in _diagnostic_templates().items():
        plain = catalog.get(template)
        assert plain is None or plain == translated, template
