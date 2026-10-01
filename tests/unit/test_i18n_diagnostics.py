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


def test_device_timing_reason_stays_chinese_when_joined_with_other_faults(zh: None) -> None:
    from roomscope.core.pipeline import _decay_unreliable_reasons

    reasons = _decay_unreliable_reasons("low", 2.0, True, device_timing_problems=True)
    shown = localize("; ".join(reasons))
    assert shown.startswith("音频设备报告本次录音")
    assert "直达声检测置信度低" in shown
    assert "录音削波" in shown
    assert _english_left(shown) == []


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


# --- Template matching: a wrong translation is worse than stable English ----

REFLECTION_NOTE = (
    "candidates are envelope peaks standing above the local diffuse level; in a "
    "dense early tail some candidates may be statistical rather than discrete reflections"
)


def _english_left(text: str) -> list[str]:
    return re.findall(r"[A-Za-z]{4,}", text)


def test_joined_reasons_keep_their_own_parts(zh: None) -> None:
    """Two compare reasons joined with "; ", each with a nested reason: every
    part keeps its own meaning (the second reason never ends up in the first)."""
    text = (
        "baseline unreliable (the response does not decay); "
        "candidate unreliable (Decay slope is not negative)"
    )
    assert localize(text) == "基线：不可靠（响应没有衰减）；候选：不可靠（衰减斜率不为负）"


def test_a_nested_diagnostic_with_its_own_semicolon_is_one_value(zh: None) -> None:
    shown = localize(f"inherited from the reflection search: {REFLECTION_NOTE}")
    assert shown.startswith("沿用自反射搜索：")
    assert _english_left(shown) == []


def test_number_fields_never_take_words(zh: None) -> None:
    assert localize("T20 1.20 s vs 1.35 s") != "T20 1.20 s vs 1.35 s"
    assert localize("T20 fast s vs slow s") == "T20 fast s vs slow s"


def test_names_and_unknown_text_stay_as_they_are(zh: None) -> None:
    for text in (
        "Studio One Output (Core Audio)",
        "MacBook Pro Microphone",
        "baseline",
        "failed",
        "a note that no template knows; and another one",
        "[Errno 2] No such file or directory: '/Users/me/room.wav'",
    ):
        assert localize(text) == text


def test_stored_words_inside_a_sentence_are_translated(zh: None) -> None:
    assert localize("baseline not_computed") == "基线：未计算"
    assert localize("candidate unreliable") == "候选：不可靠"


def test_deep_nesting_ends(zh: None) -> None:
    text = "decay analysis, broadband: " * 40 + "the response does not decay"
    shown = localize(text)
    assert isinstance(shown, str) and shown


def test_a_failed_loopback_stores_an_english_reason_in_chinese(
    zh: None, short_sweep: object
) -> None:
    """The loopback path stores the text of the exception it catches; under
    zh_CN it must still be the English diagnostic (shown translated later)."""
    import numpy as np

    from roomscope.core.pipeline import Reference, analyze, synthetic_recording
    from roomscope.models.audio import AudioSignal
    from tests.conftest import make_rir

    ir = make_rir(short_sweep.sample_rate, rt60_s=0.4)  # type: ignore[attr-defined]
    mic = synthetic_recording(short_sweep, ir, noise_rms=1e-5)  # type: ignore[arg-type]
    silent = AudioSignal(np.zeros_like(mic.samples), mic.sample_rate)
    result = analyze(mic, Reference.from_settings(short_sweep), loopback=silent)  # type: ignore[arg-type]
    loopback = result.impulse_response.loopback
    assert loopback is not None and not loopback.compensation_applied
    assert loopback.reason and loopback.reason.isascii(), loopback.reason
    assert all(text.isascii() for text in result.warnings)
    assert localize(loopback.reason) != loopback.reason
