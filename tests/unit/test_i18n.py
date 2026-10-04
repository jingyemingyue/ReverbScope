from __future__ import annotations

from roomscope.core.pipeline import Reference, analyze, synthetic_recording
from roomscope.i18n import (
    _,
    activate,
    available_locales,
    current_locale,
    format_message,
    normalize_lang,
    parse_po,
)
from roomscope.interpretation import interpret
from roomscope.models.configuration import SweepSettings
from tests.conftest import make_rir


def test_normalize_and_available_locales() -> None:
    assert normalize_lang("zh-CN") == "zh_CN"
    assert normalize_lang("zh") == "zh_CN"
    assert "en" in available_locales()
    assert "zh_CN" in available_locales()


def test_english_is_source_and_chinese_translates_findings(
    short_sweep: SweepSettings,
) -> None:
    activate("en")
    assert current_locale() == "en"
    assert _("RoomScope analysis") == "RoomScope analysis"
    ir = make_rir(short_sweep.sample_rate, rt60_s=0.35, reflections=[(0.018, 0.4)])
    rec = synthetic_recording(short_sweep, ir, noise_rms=2e-5)
    result = analyze(rec, Reference.from_settings(short_sweep))
    english = interpret(result, "generic")
    assert english
    assert all(item.locale == "en" for item in english)
    activate("zh_CN")
    assert current_locale() == "zh_CN"
    assert _("RoomScope analysis") == "RoomScope 分析"
    chinese = interpret(result, "generic")
    assert chinese
    assert all(item.locale == "zh_CN" for item in chinese)
    assert any(any("\u4e00" <= ch <= "\u9fff" for ch in item.message) for item in chinese)
    activate("en")


def test_numbers_stay_ascii() -> None:
    activate("zh_CN")
    text = format_message("Sample rate: {rate} Hz    created: {created}", rate=48000, created="t")
    assert "48000" in text
    assert "." in format_message(
        "The broadband decay is short (estimated RT60 {rt:.2f} s). "
        "This is typical of a treated or small, well-damped room.",
        rt=0.45,
    )
    activate("en")


def test_daw_chrome_is_in_the_chinese_catalog() -> None:
    activate("zh_CN")
    assert _("Analyze") == "分析"
    assert _("Step 1 - Generate Test Signal").startswith("步骤")
    activate("en")


def test_cli_help_and_report_labels_are_in_the_chinese_catalog() -> None:
    activate("zh_CN")
    assert _("write the ESS test signal WAV (+ JSON sidecar)").startswith("写出")
    assert _("Reverberation") == "混响"
    assert _("At a glance") == "概览"
    assert _("show this help message and exit") == "显示此帮助信息并退出"
    assert _("Next steps") == "下一步"
    activate("en")


def test_parse_po_round_trip(tmp_path) -> None:
    import gettext

    from roomscope.i18n import write_mo

    po = tmp_path / "roomscope.po"
    po.write_text('msgid "Hello"\nmsgstr "你好"\n', encoding="utf-8")
    catalog = parse_po(po)
    assert catalog["Hello"] == "你好"
    mo = tmp_path / "roomscope.mo"
    write_mo(catalog, mo)
    with mo.open("rb") as handle:
        trans = gettext.GNUTranslations(handle)
    assert trans.gettext("Hello") == "你好"


def _copy_catalog(tmp_path) -> tuple[object, object]:
    import shutil
    from pathlib import Path

    from roomscope.i18n import locale_dir

    base = Path(tmp_path) / "locale"
    messages = base / "zh_CN" / "LC_MESSAGES"
    messages.mkdir(parents=True)
    shutil.copy(Path(locale_dir()) / "zh_CN" / "LC_MESSAGES" / "roomscope.po", messages)
    return base, messages


def test_loading_a_catalog_never_writes_to_the_package_tree(tmp_path, monkeypatch) -> None:
    """#14: an installed tree or a frozen bundle may be read-only; no .mo is written."""
    from roomscope import i18n

    base, messages = _copy_catalog(tmp_path)
    monkeypatch.setattr(i18n, "_LOCALE_DIR", base)
    before = sorted(p.name for p in messages.iterdir())
    try:
        assert activate("zh_CN") == "zh_CN"
        assert _("Analyze") == "分析"
    finally:
        activate("en")
    assert sorted(p.name for p in messages.iterdir()) == before == ["roomscope.po"]


def test_compiled_mo_is_used_only_while_it_matches_the_po(tmp_path, monkeypatch) -> None:
    import gettext

    from roomscope import i18n

    base, messages = _copy_catalog(tmp_path)
    monkeypatch.setattr(i18n, "_LOCALE_DIR", base)
    written = i18n.compile_catalogs(base)
    assert written == [messages / "roomscope.mo"]
    loaded = i18n._load_translation("zh_CN")
    assert isinstance(loaded, gettext.GNUTranslations)
    assert loaded.info()[i18n.SOURCE_HASH_HEADER.lower()] == i18n.source_hash(
        messages / "roomscope.po"
    )
    # Edit the .po after compiling: the stale .mo must not win.
    po = messages / "roomscope.po"
    po.write_text(
        po.read_text(encoding="utf-8").replace('msgstr "分析"', 'msgstr "分析（新）"', 1),
        encoding="utf-8",
    )
    reloaded = i18n._load_translation("zh_CN")
    assert not isinstance(reloaded, gettext.GNUTranslations)
    assert reloaded.gettext("Analyze") == "分析（新）"
    # A .mo without its .po (a packager that drops sources) is used as is.
    po.unlink()
    assert i18n._load_translation("zh_CN").gettext("Analyze") == "分析"
    # A .mo compiled before the hash header existed is ignored when a .po exists.
    po.write_text('msgid "Analyze"\nmsgstr "分析"\n', encoding="utf-8")
    i18n.write_mo({"Analyze": "旧"}, messages / "roomscope.mo")
    assert i18n._load_translation("zh_CN").gettext("Analyze") == "分析"


def test_msgctxt_entries_round_trip_through_po_and_mo(tmp_path) -> None:
    import gettext

    from roomscope.i18n import _PoTranslations, write_mo

    po = tmp_path / "roomscope.po"
    po.write_text(
        'msgctxt "decay length"\nmsgid "long"\nmsgstr "很长"\n\n'
        'msgid "long"\nmsgstr "长"\n\n'
        'msgctxt "noise segment"\n"\\n"\nmsgid "tail"\nmsgstr ""\n"录音末尾"\n',
        encoding="utf-8",
    )
    catalog = parse_po(po)
    assert catalog == {
        "decay length\x04long": "很长",
        "long": "长",
        "noise segment\n\x04tail": "录音末尾",
    }
    in_memory = _PoTranslations(catalog)
    assert in_memory.pgettext("decay length", "long") == "很长"
    assert in_memory.gettext("long") == "长"
    assert in_memory.pgettext("RT60 change", "long") == "long"
    mo = tmp_path / "roomscope.mo"
    write_mo(catalog, mo)
    with mo.open("rb") as handle:
        compiled = gettext.GNUTranslations(handle)
    assert compiled.pgettext("decay length", "long") == "很长"
    assert compiled.gettext("long") == "长"


def test_wheel_build_hook_compiles_into_a_temporary_directory(tmp_path) -> None:
    """The hook force-includes a hashed .mo and never writes into ``src/``."""
    import gettext
    import importlib.util
    from pathlib import Path

    import pytest

    pytest.importorskip("hatchling")
    from roomscope.i18n import SOURCE_HASH_HEADER, locale_dir, source_hash

    spec = importlib.util.spec_from_file_location("hatch_build", Path("hatch_build.py"))
    assert spec is not None and spec.loader is not None
    hook = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hook)
    src_messages = Path(locale_dir()) / "zh_CN" / "LC_MESSAGES"
    before = sorted(p.name for p in src_messages.iterdir())
    include = hook.compiled_catalogs(tmp_path)
    assert list(include.values()) == ["roomscope/locale/zh_CN/LC_MESSAGES/roomscope.mo"]
    mo = Path(next(iter(include)))
    assert mo == tmp_path / "zh_CN" / "LC_MESSAGES" / "roomscope.mo"
    with mo.open("rb") as handle:
        compiled = gettext.GNUTranslations(handle)
    assert compiled.info()[SOURCE_HASH_HEADER.lower()] == source_hash(src_messages / "roomscope.po")
    assert compiled.gettext("Analyze") == "分析"
    assert sorted(p.name for p in src_messages.iterdir()) == before


def test_parse_po_unescapes_in_one_pass_and_skips_fuzzy(tmp_path) -> None:
    """``\\\\n`` (a backslash, then n) became a newline; fuzzy entries were used."""
    from roomscope.i18n import parse_po

    po = tmp_path / "x.po"
    po.write_text(
        'msgid "path"\nmsgstr "C:\\\\new\\\\table"\n\n'
        '#, fuzzy\nmsgid "draft"\nmsgstr "not yet"\n\n'
        'msgid "after"\nmsgstr "kept"\n\n'
        '#, fuzzy\nmsgctxt "diagnostic"\nmsgid "ctx draft"\nmsgstr "no"\n\n'
        'msgctxt "diagnostic"\nmsgid "ctx"\nmsgstr "a \\"b\\"\\n"\n',
        encoding="utf-8",
    )
    assert parse_po(po) == {
        "path": "C:\\new\\table",
        "after": "kept",
        "diagnostic\x04ctx": 'a "b"\n',
    }


def _duplicate_po_entries(text: str) -> list[tuple[str, str]]:
    """``(msgctxt, msgid)`` keys that occur more than once in a ``.po`` text.

    Continuation lines are joined, so a msgid written as ``msgid ""`` followed
    by ``"..."`` lines counts too. The header (an empty msgid) and obsolete
    ``#~`` entries are left out.
    """
    from collections import Counter

    fields: list[list[str]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith('"') and fields:
            fields[-1][1] += line[1:-1]
        elif line.startswith("msg"):
            keyword, _sep, value = line.partition(" ")
            fields.append([keyword, value.strip()[1:-1]])
    keys: list[tuple[str, str]] = []
    context = ""
    for keyword, value in fields:
        if keyword == "msgctxt":
            context = value
        elif keyword == "msgid":
            if value or context:
                keys.append((context, value))
            context = ""
    return [key for key, count in Counter(keys).items() if count > 1]


def test_the_catalog_has_no_duplicate_entries() -> None:
    """GNU msgfmt refuses a catalog with a duplicate msgid. The check missed
    entries whose msgid spans several lines."""
    from pathlib import Path

    path = Path("src/roomscope/locale/zh_CN/LC_MESSAGES/roomscope.po")
    text = path.read_text(encoding="utf-8") + "\n"
    assert _duplicate_po_entries(text) == []
    long_entry = 'msgid ""\n"The first line, "\n"and the second."\nmsgstr "x"\n\n'
    other_ending = 'msgid ""\n"The first line, "\n"and another."\nmsgstr "y"\n\n'
    in_context = 'msgctxt "diagnostic"\nmsgid "Cancel"\nmsgstr "z"\n\n'
    assert _duplicate_po_entries(text + long_entry + other_ending) == []
    assert _duplicate_po_entries(text + long_entry + long_entry) == [
        ("", "The first line, and the second.")
    ]
    assert _duplicate_po_entries(text + in_context + in_context) == [("diagnostic", "Cancel")]


def test_metric_labels_split_from_the_right() -> None:
    from roomscope.labels import metric_label

    assert metric_label("band.31.5 Hz.t20") == "31.5 Hz T20"
    assert metric_label("band.2.5 kHz.edt", "s") == "2.5 kHz EDT (s)"
    assert metric_label("band.63 Hz") == "63 Hz"


# --- Diagnostics joined with "; " (localize) ---------------------------------

EDT_STEP = (
    "the decay curve drops 15.7 dB across the direct sound (it carries 97 % of the energy; "
    "limit 5 dB): EDT describes the direct sound rather than the room at this position"
)
FILTER_BT = (
    "B*T = 3.8 < 4: the band filter's own decay is comparable to the measured decay; "
    "values in this band are unreliable"
)
TRUNCATION = (
    "the noise truncation is not trustworthy ({problem}) and the result depends on it ({changes})"
)


def _english_left(text: str) -> list[str]:
    import re

    return re.findall(r"[A-Za-z]{4,}", text)


def _shown_in_chinese(text: str) -> str:
    from roomscope.i18n import localize

    activate("zh_CN")
    try:
        return localize(text)
    finally:
        activate("en")


def test_joined_diagnostics_with_their_own_semicolons() -> None:
    """A template whose literal text has a "; " (EDT step, B*T) was cut there."""
    edt, bt = _shown_in_chinese(EDT_STEP), _shown_in_chinese(FILTER_BT)
    assert _english_left(edt) == _english_left(bt) == []
    assert _shown_in_chinese(EDT_STEP + "; " + FILTER_BT) == edt + "；" + bt


def test_a_value_that_joins_several_diagnostics() -> None:
    """The truncation warning lists every changed metric, joined with "; "."""
    from roomscope.i18n import diag

    text = diag(
        TRUNCATION,
        problem="the late decay slope (-3.3 dB/s) is less than 0.5 times the early slope "
        "(-115.2 dB/s)",
        changes="T20 0.51 s vs 0.54 s; T30 0.53 s vs 9.81 s",
    )
    assert _english_left(_shown_in_chinese(text)) == []
    warning = diag("decay analysis, {band}: {warning}", band="500 Hz", warning=text)
    assert _english_left(_shown_in_chinese(warning)) == []


def test_upper_plane_rejections_joined_before_a_literal_semicolon() -> None:
    from roomscope.i18n import diag

    rejections = "; ".join(
        diag(
            "the {delay:.1f} ms candidate has no real solution for a plane above both devices",
            delay=delay,
        )
        for delay in (5.1, 6.3)
    )
    text = diag(
        "no detected reflection can be read as a plane above both devices: "
        "{rejections}; even the lowest plausible upper plane ({lowest:.1f} m) would "
        "arrive at about {delay:.1f} ms, beyond the {start:.1f}-{end:.1f} ms window "
        "that could be searched, so absence here is not evidence of absence",
        rejections=rejections,
        lowest=2.1,
        delay=9.0,
        start=0.8,
        end=8.0,
    )
    shown = _shown_in_chinese(text)
    assert _english_left(shown) == [], shown


def test_comparison_reasons_that_nest_joined_reasons() -> None:
    from roomscope.i18n import diag

    text = (
        diag("baseline {validity} ({reason})", validity="unreliable", reason=EDT_STEP)
        + "; "
        + diag(
            "candidate {validity} ({reason})",
            validity="unreliable",
            reason=EDT_STEP + "; " + FILTER_BT,
        )
    )
    shown = _shown_in_chinese(text)
    assert _english_left(shown) == [], shown
    # One inside each EDT sentence and inside B*T, one before B*T and one
    # between the two sides.
    assert shown.count("；") == 5, shown


def test_a_joined_metric_reason_inside_a_comparison_reason() -> None:
    """#43: low confidence and clipping, joined by with_all_unreliable()."""
    from roomscope.core.compare import _decay_metric_delta
    from roomscope.i18n import diag
    from roomscope.models.result import DecayMetric, Validity

    low_confidence = diag(
        "direct-sound detection confidence is low (pre-peak margin {margin_db:.1f} dB): "
        "the recording may not contain the reference sweep",
        margin_db=3.0,
    )
    clipping = diag(
        "the recording clips, so the measurement chain was not linear and the "
        "deconvolved response is not the room's impulse response"
    )
    bad = DecayMetric(
        "t30", 0.5, Validity.UNRELIABLE, 30.0, reason=low_confidence + "; " + clipping
    )
    good = DecayMetric("t30", 0.5, Validity.VALID, 30.0)
    reason = _decay_metric_delta("broadband.t30", bad, good).reason
    assert reason is not None
    shown = _shown_in_chinese(reason)
    assert _english_left(shown) == [], shown


def test_plain_joins_and_unknown_pieces_still_work() -> None:
    assert _shown_in_chinese("baseline not_computed; candidate unreliable") == (
        "基线：未计算；候选：不可靠"
    )
    # An unknown piece stays English next to a translated one.
    shown = _shown_in_chinese("a note that no template knows; candidate unreliable")
    assert shown == "a note that no template knows；候选：不可靠"
    # Nothing recognised: the text as stored, separators included.
    unknown = "a note that no template knows; and (another; one)"
    assert _shown_in_chinese(unknown) == unknown


def test_comparison_reasons_name_the_validity_in_words() -> None:
    """#66: "candidate outside_excitation_range" stayed an id, also in zh_CN."""
    from roomscope.core.compare import _decay_metric_delta
    from roomscope.models.result import DecayMetric, Validity

    reason = _decay_metric_delta(
        "band.4 kHz.t30",
        DecayMetric("t30", None, Validity.INSUFFICIENT_RANGE, None, reason="too little decay"),
        DecayMetric("t30", None, Validity.OUTSIDE_EXCITATION, None),
    ).reason
    assert reason == (
        "baseline insufficient range (too little decay); candidate outside the sweep's range"
    )
    assert _shown_in_chinese(reason) == "基线：衰减范围不足（too little decay）；候选：超出扫频范围"
    # A reason stored with the ids by an earlier version.
    stored = "baseline insufficient_decay_range; candidate outside_excitation_range"
    assert _shown_in_chinese(stored) == "基线：衰减范围不足；候选：超出扫频范围"


def test_noise_band_metric_labels() -> None:
    """#23: the GUI compare table showed "noise.band.1000Hz (dBFS)"."""
    from roomscope.labels import metric_label

    assert metric_label("noise.band.1000Hz", "dBFS") == "Background noise, 1 kHz (dBFS)"
    assert metric_label("noise.band.31.5Hz") == "Background noise, 31.5 Hz"
    assert metric_label("noise.rms_dbfs") == "Background noise, RMS"
    activate("zh_CN")
    try:
        assert metric_label("noise.band.63Hz", "dBFS") == "本底噪声，63 Hz (dBFS)"
    finally:
        activate("en")
