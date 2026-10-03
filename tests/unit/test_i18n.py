from __future__ import annotations

from reverbscope.core.pipeline import Reference, analyze, synthetic_recording
from reverbscope.i18n import (
    _,
    activate,
    available_locales,
    current_locale,
    format_message,
    normalize_lang,
    parse_po,
)
from reverbscope.interpretation import interpret
from reverbscope.models.configuration import SweepSettings
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
    assert _("ReverbScope analysis") == "ReverbScope analysis"
    ir = make_rir(short_sweep.sample_rate, rt60_s=0.35, reflections=[(0.018, 0.4)])
    rec = synthetic_recording(short_sweep, ir, noise_rms=2e-5)
    result = analyze(rec, Reference.from_settings(short_sweep))
    english = interpret(result, "generic")
    assert english
    assert all(item.locale == "en" for item in english)
    activate("zh_CN")
    assert current_locale() == "zh_CN"
    assert _("ReverbScope analysis") == "ReverbScope 分析"
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

    from reverbscope.i18n import write_mo

    po = tmp_path / "reverbscope.po"
    po.write_text('msgid "Hello"\nmsgstr "你好"\n', encoding="utf-8")
    catalog = parse_po(po)
    assert catalog["Hello"] == "你好"
    mo = tmp_path / "reverbscope.mo"
    write_mo(catalog, mo)
    with mo.open("rb") as handle:
        trans = gettext.GNUTranslations(handle)
    assert trans.gettext("Hello") == "你好"


def _copy_catalog(tmp_path) -> tuple[object, object]:
    import shutil
    from pathlib import Path

    from reverbscope.i18n import locale_dir

    base = Path(tmp_path) / "locale"
    messages = base / "zh_CN" / "LC_MESSAGES"
    messages.mkdir(parents=True)
    shutil.copy(Path(locale_dir()) / "zh_CN" / "LC_MESSAGES" / "reverbscope.po", messages)
    return base, messages


def test_loading_a_catalog_never_writes_to_the_package_tree(tmp_path, monkeypatch) -> None:
    """#14: an installed tree or a frozen bundle may be read-only; no .mo is written."""
    from reverbscope import i18n

    base, messages = _copy_catalog(tmp_path)
    monkeypatch.setattr(i18n, "_LOCALE_DIR", base)
    before = sorted(p.name for p in messages.iterdir())
    try:
        assert activate("zh_CN") == "zh_CN"
        assert _("Analyze") == "分析"
    finally:
        activate("en")
    assert sorted(p.name for p in messages.iterdir()) == before == ["reverbscope.po"]


def test_compiled_mo_is_used_only_while_it_matches_the_po(tmp_path, monkeypatch) -> None:
    import gettext

    from reverbscope import i18n

    base, messages = _copy_catalog(tmp_path)
    monkeypatch.setattr(i18n, "_LOCALE_DIR", base)
    written = i18n.compile_catalogs(base)
    assert written == [messages / "reverbscope.mo"]
    loaded = i18n._load_translation("zh_CN")
    assert isinstance(loaded, gettext.GNUTranslations)
    assert loaded.info()[i18n.SOURCE_HASH_HEADER.lower()] == i18n.source_hash(
        messages / "reverbscope.po"
    )
    # Edit the .po after compiling: the stale .mo must not win.
    po = messages / "reverbscope.po"
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
    i18n.write_mo({"Analyze": "旧"}, messages / "reverbscope.mo")
    assert i18n._load_translation("zh_CN").gettext("Analyze") == "分析"


def test_msgctxt_entries_round_trip_through_po_and_mo(tmp_path) -> None:
    import gettext

    from reverbscope.i18n import _PoTranslations, write_mo

    po = tmp_path / "reverbscope.po"
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
    mo = tmp_path / "reverbscope.mo"
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
    from reverbscope.i18n import SOURCE_HASH_HEADER, locale_dir, source_hash

    spec = importlib.util.spec_from_file_location("hatch_build", Path("hatch_build.py"))
    assert spec is not None and spec.loader is not None
    hook = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hook)
    src_messages = Path(locale_dir()) / "zh_CN" / "LC_MESSAGES"
    before = sorted(p.name for p in src_messages.iterdir())
    include = hook.compiled_catalogs(tmp_path)
    assert list(include.values()) == ["reverbscope/locale/zh_CN/LC_MESSAGES/reverbscope.mo"]
    mo = Path(next(iter(include)))
    assert mo == tmp_path / "zh_CN" / "LC_MESSAGES" / "reverbscope.mo"
    with mo.open("rb") as handle:
        compiled = gettext.GNUTranslations(handle)
    assert compiled.info()[SOURCE_HASH_HEADER.lower()] == source_hash(src_messages / "reverbscope.po")
    assert compiled.gettext("Analyze") == "分析"
    assert sorted(p.name for p in src_messages.iterdir()) == before
