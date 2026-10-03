"""zh_CN catalog completeness (#14).

Every literal handed to ``_()``, ``N_()``, ``pgettext()``, ``ngettext()``,
``format_message()`` or used as a ``finding()`` template anywhere under
``src/reverbscope`` must have a non-empty Simplified Chinese translation whose
placeholders match the English ones. Finding sentences must not carry English
words once the catalog is active.
"""

from __future__ import annotations

import ast
import re
import string
from pathlib import Path

import numpy as np
import pytest
from scipy.signal import fftconvolve

from reverbscope.i18n import DIAGNOSTIC_CONTEXT, activate, parse_po
from reverbscope.interpretation import available_profiles, get_profile
from reverbscope.interpretation.interpreter import Severity
from reverbscope.interpretation.profiles import (
    ProfileBase,
    change_direction_text,
    decay_length_text,
    noise_segment_text,
    profile_title,
)
from reverbscope.labels import topic_text
from reverbscope.models.comparison import MetricDelta
from reverbscope.models.result import Reflection, ResonanceCandidate, Validity
from tests.conftest import make_rir

SRC = Path("src/reverbscope")
CATALOG = SRC / "locale" / "zh_CN" / "LC_MESSAGES" / "reverbscope.po"
CONTEXT_SEPARATOR = "\x04"

#: ``_()`` calls whose argument is not a literal. Each one translates a value
#: that is itself extracted elsewhere (a ``N_()`` constant or a ``finding()``
#: template). A new entry here needs the same justification.
DYNAMIC_CALLS = {
    ("i18n.py", "_(template)"),
    ("interpretation/interpreter.py", "_(template)"),
    ("cli/main.py", "_(SAFETY_MESSAGE)"),
    # argparse's own texts, each extracted with N_() in ARGPARSE_MESSAGES.
    ("cli/main.py", "_(message)"),
    # Root-help command groups (COMMAND_GROUPS) and session modes
    # (SESSION_MODES), each extracted with N_().
    ("cli/main.py", "_(group)"),
    ("cli/main.py", "_(mode)"),
    # Device Inspector column headings, each extracted with N_() in COLUMNS.
    ("ui/dev_tools.py", "_(column)"),
    ("ui/pages.py", "_(SAFETY_MESSAGE)"),
    ("ui/pages.py", "_(DAW_INSTRUCTIONS)"),
    # The "GUI cannot start" sentence, extracted with N_() in ui/app.py.
    ("cli/main.py", "_(GUI_UNAVAILABLE)"),
    ("ui/app.py", "_(GUI_UNAVAILABLE)"),
}

#: ASCII tokens a Chinese finding may legitimately contain: units, metric
#: names and standard numbers are never translated.
ALLOWED_ASCII = {
    "RT60",
    "dB",
    "dBFS",
    "RMS",
    "SPL",
    "Hz",
    "ms",
    "s",
    "T20",
    "T30",
    "EDT",
    "ISO",
    "T",
    "C50",
    "C80",
}


def _literal(node: ast.expr) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _call_name(node: ast.Call) -> str | None:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


def extract_messages() -> tuple[dict[str, list[str]], set[tuple[str, str]]]:
    """Return ``{msgid: [where, ...]}`` and the set of dynamic ``_()`` call sites."""
    found: dict[str, list[str]] = {}
    dynamic: set[tuple[str, str]] = set()
    for path in sorted(SRC.rglob("*.py")):
        rel = path.relative_to(SRC).as_posix()
        source = path.read_text(encoding="utf-8")
        for node in ast.walk(ast.parse(source)):
            if not isinstance(node, ast.Call):
                continue
            name = _call_name(node)
            ids: list[str] = []
            if name in {"_", "N_", "format_message"} and node.args:
                text = _literal(node.args[0])
                if text is not None:
                    ids.append(text)
                elif name == "_":
                    dynamic.add((rel, ast.get_source_segment(source, node) or ""))
            elif name == "finding" and len(node.args) >= 4:
                text = _literal(node.args[3])
                if text is not None:
                    ids.append(text)
            elif name == "ngettext" and len(node.args) >= 2:
                ids.extend(t for t in (_literal(node.args[0]), _literal(node.args[1])) if t)
            elif name == "diag" and node.args:
                text = _literal(node.args[0])
                if text is not None:
                    ids.append(f"{DIAGNOSTIC_CONTEXT}{CONTEXT_SEPARATOR}{text}")
                else:
                    dynamic.add((rel, ast.get_source_segment(source, node) or ""))
            elif name == "pgettext" and len(node.args) >= 2:
                context, text = _literal(node.args[0]), _literal(node.args[1])
                if context and text:
                    ids.append(f"{context}{CONTEXT_SEPARATOR}{text}")
            for msgid in ids:
                found.setdefault(msgid, []).append(f"{rel}:{node.lineno}")
    return found, dynamic


def _placeholders(text: str) -> list[tuple[str, str]]:
    return sorted(
        (field, spec or "")
        for _, field, spec, _ in string.Formatter().parse(text)
        if field is not None
    )


def test_every_extracted_message_has_a_zh_cn_translation() -> None:
    messages, _dynamic = extract_messages()
    catalog = parse_po(CATALOG)
    # The extractor must see the modules the issue names.
    wheres = {where.split(":")[0] for places in messages.values() for where in places}
    assert {"interpretation/profiles.py", "audio/backend.py", "cli/main.py"} <= wheres
    missing = {
        msgid.replace(CONTEXT_SEPARATOR, " | "): places
        for msgid, places in messages.items()
        if not catalog.get(msgid, "").strip()
    }
    assert missing == {}


def test_dynamic_translation_calls_are_known() -> None:
    _messages, dynamic = extract_messages()
    assert dynamic <= DYNAMIC_CALLS, sorted(dynamic - DYNAMIC_CALLS)


def test_translations_keep_the_english_placeholders() -> None:
    catalog = parse_po(CATALOG)
    mismatched = {
        msgid: (msgstr, _placeholders(msgid), _placeholders(msgstr))
        for msgid, msgstr in catalog.items()
        if _placeholders(msgid.split(CONTEXT_SEPARATOR)[-1]) != _placeholders(msgstr)
    }
    assert mismatched == {}


def test_safety_warning_and_level_refusal_are_translated() -> None:
    from reverbscope.audio.backend import SAFETY_MESSAGE
    from reverbscope.i18n import _

    activate("zh_CN")
    try:
        assert _(SAFETY_MESSAGE).startswith("先把监听")
        refusal = _(
            "Level {level:g} dBFS is above {max_level:g} dBFS. "
            "Set the monitor level low first and pass --acknowledge-level to confirm."
        )
        assert "--acknowledge-level" in refusal and "监听" in refusal
    finally:
        activate("en")


def _english_words(text: str) -> list[str]:
    return [word for word in re.findall(r"[A-Za-z][A-Za-z0-9]*", text) if word not in ALLOWED_ASCII]


def _all_profile_sentences(profile: ProfileBase) -> list[str]:
    reflection = Reflection(delay_ms=12.0, relative_db=-4.0)
    resonances = [
        ResonanceCandidate(
            frequency_hz=frequency,
            level_above_baseline_db=8.0,
            narrowband_decay_20db_s=0.6,
            filter_ringing_20db_s=0.1,
            decay_distinguishable=True,
            surroundings_decay_20db_s=0.3,
        )
        for frequency in (48.0, 96.0)
    ]
    sentences = [
        profile.reflection_message(reflection),
        profile.low_imbalance_message(0.9, 0.4),
        profile.hum_message(50.0),
        profile.resonance_message(resonances),
    ]
    for severity, label in (
        (Severity.INFO, "short"),
        (Severity.NOTICE, "noticeable"),
        (Severity.WARNING, "long"),
    ):
        for basis in (None, "T30"):
            sentences.append(profile.decay_message(0.8, severity, decay_length_text(label), basis))
    for source in (None, "pre-sweep", "tail"):
        sentences.append(profile.noise_floor_message(-72.0, noise_segment_text(source)))
    sentences.append(profile.clarity_low_message(-1.5, profile.clarity_low_db or 0.0))
    sentences.append(profile.clarity_high_message(9.0, profile.clarity_high_db or 8.0))
    return sentences


@pytest.mark.parametrize("name", available_profiles())
def test_every_profile_sentence_is_chinese(name: str) -> None:
    profile = get_profile(name)
    assert isinstance(profile, ProfileBase)
    activate("zh_CN")
    try:
        for sentence in _all_profile_sentences(profile):
            assert any("一" <= ch <= "鿿" for ch in sentence), sentence
            assert _english_words(sentence) == [], sentence
    finally:
        activate("en")


def test_comparison_words_are_translated_but_params_stay_english() -> None:
    profile = get_profile("vocal")
    assert isinstance(profile, ProfileBase)
    rt = MetricDelta(
        name="broadband.rt60_estimate",
        baseline=0.45,
        candidate=0.9,
        validity=Validity.VALID,
        delta_s=0.45,
        delta_percent=100.0,
        delta=0.45,
        unit="s",
    )
    activate("zh_CN")
    try:
        crossing = profile._decay_threshold_crossing(rt)
        assert crossing is not None
        assert "“较短”" in crossing.message and "“很长”" in crossing.message
        assert crossing.params["before"] == "short" and crossing.params["after"] == "long"
        assert _english_words(crossing.message) == []
        assert change_direction_text("longer") == "变长"
    finally:
        activate("en")
    english = profile._decay_threshold_crossing(rt)
    assert english is not None and "'short'" in english.message and "'long'" in english.message


def test_findings_keep_english_labels_in_params(short_sweep) -> None:
    from reverbscope.core.pipeline import Reference, analyze, synthetic_recording
    from reverbscope.interpretation import interpret

    ir = make_rir(short_sweep.sample_rate, rt60_s=0.9, diffuse_level=0.05)
    result = analyze(
        synthetic_recording(short_sweep, ir, noise_rms=2e-5), Reference.from_settings(short_sweep)
    )
    activate("zh_CN")
    try:
        chinese = interpret(result, "choir")
    finally:
        activate("en")
    english = interpret(result, "choir")
    by_id = {item.message_id: item for item in english}
    for item in chinese:
        assert item.params == by_id[item.message_id].params
        if item.message_id == "reverberation.rt60":
            assert item.params["label"] in {"short", "noticeable", "long"}
        if item.message_id == "noise.floor":
            assert item.params["segment"] in {"pre-sweep", "tail", None}


@pytest.mark.parametrize("profile", ["drums", "room_mic", "acoustic_guitar", "choir"])
def test_cli_zh_cn_analyze_prints_no_english_finding_text(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], profile: str
) -> None:
    from reverbscope.cli.main import main
    from reverbscope.io.wav import read_wav, write_wav

    sweep = tmp_path / "sweep.wav"
    assert main(["sweep", "--out", str(sweep), "--duration", "2", "--post-silence", "2.0"]) == 0
    signal = read_wav(sweep)
    # A live room with a hard early slap and a little noise, so that the
    # reflection, decay and noise sections all speak.
    ir = make_rir(signal.sample_rate, rt60_s=1.3, reflections=[(0.011, 0.8)], diffuse_level=0.05)
    rec = fftconvolve(signal.samples, ir)[: signal.n_samples + ir.shape[0]]
    rec = rec + np.random.default_rng(3).normal(0.0, 3e-5, rec.shape[0])
    recording = write_wav(tmp_path / "recording.wav", rec, signal.sample_rate, subtype="FLOAT")
    capsys.readouterr()
    try:
        code = main(
            [
                "--lang",
                "zh_CN",
                "analyze",
                "--recording",
                str(recording),
                "--sweep",
                str(sweep),
                "--profile",
                profile,
            ]
        )
        title = profile_title(profile)
        reverberation = topic_text("reverberation")
    finally:
        activate("en")
    assert code == 0
    assert title != profile and reverberation == "混响"
    out = capsys.readouterr().out
    header = f"解读（{title}配置）"
    assert header in out
    section = out.split(header, 1)[1].splitlines()
    # Each finding: "  <symbol> <severity> · <topic>", then its message
    # indented by four spaces (wrapped over as many lines as it needs).
    findings: list[tuple[str, str]] = []
    for line in section:
        head = re.match(r"^  \S+ (.+?) · (.+)$", line)
        if head:
            findings.append((head.group(2), ""))
        elif line.startswith("    ") and findings:
            topic, message = findings[-1]
            findings[-1] = (topic, message + line.strip())
    assert findings, out
    assert reverberation in {topic for topic, _message in findings}
    for topic, message in findings:
        assert message, topic
        assert _english_words(message) == [], (topic, message)
