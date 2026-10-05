"""Which language RoomScope picks, and why: ``--lang``, the stored setting,
``ROOMSCOPE_LANG``, then where each system keeps the user's language (the
Mac's preferred languages, the Windows display language, GNU ``LANGUAGE``
and the POSIX locale variables)."""

from __future__ import annotations

import plistlib
import sys
from pathlib import Path

import pytest

from roomscope import i18n
from roomscope.i18n import (
    ORIGIN_DESKTOP,
    ORIGIN_MACOS,
    ORIGIN_WINDOWS,
    SOURCE_ENVIRONMENT,
    SOURCE_OPTION,
    SOURCE_SETTINGS,
    SOURCE_SYSTEM,
    language_choice,
    resolve_language,
    supported_language,
)
from roomscope.settings import UserSettings, save_settings


@pytest.fixture
def system(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> pytest.MonkeyPatch:
    """No stored language, no override, no Mac preferences, no Windows
    display language, and no locale from Python: every test sets its own."""
    monkeypatch.delenv("ROOMSCOPE_LANG", raising=False)
    for name in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(i18n, "MACOS_PREFERENCES", (str(tmp_path / "missing.plist"),))
    monkeypatch.setattr(i18n, "_windows_ui_language", lambda: None)
    monkeypatch.setattr(i18n.py_locale, "getlocale", lambda *args: (None, None))
    return monkeypatch


def _plist(path: Path, languages: object, *, binary: bool = True) -> Path:
    fmt = plistlib.FMT_BINARY if binary else plistlib.FMT_XML
    path.write_bytes(plistlib.dumps({"AppleLanguages": languages, "AppleLocale": "en_CN"}, fmt=fmt))
    return path


def test_supported_languages_are_a_catalog_or_english() -> None:
    assert supported_language("zh-Hans-CN") == "zh_CN"
    assert supported_language("zh_CN.UTF-8") == "zh_CN"
    assert supported_language("zh") == "zh_CN"
    assert supported_language("en_US.UTF-8") == "en"
    assert supported_language("en-GB") == "en"
    for other in ("fr_FR", "zh_TW", "zh-Hant-TW", "C", "C.UTF-8", "POSIX", "", "  ", None):
        assert supported_language(other) is None, other


# --- macOS -------------------------------------------------------------------------------


def test_a_mac_follows_its_preferred_languages_not_lang(
    system: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Terminal and VS Code set LANG=en_US.UTF-8 on a Mac set to Chinese."""
    system.setattr(sys, "platform", "darwin")
    system.setenv("LANG", "en_US.UTF-8")
    system.setenv("LC_ALL", "en_US.UTF-8")
    user = _plist(tmp_path / "user.plist", ["zh-Hans-CN", "en-CN"])
    system.setattr(i18n, "MACOS_PREFERENCES", (str(user), str(tmp_path / "system.plist")))
    choice = language_choice()
    assert choice.lang == "zh_CN"
    assert (choice.source, choice.origin, choice.value) == (
        SOURCE_SYSTEM,
        ORIGIN_MACOS,
        "zh-Hans-CN, en-CN",
    )
    assert resolve_language() == "zh_CN"


def test_the_first_language_the_mac_lists_that_roomscope_has_wins(
    system: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    system.setattr(sys, "platform", "darwin")
    system.setenv("LANG", "zh_CN.UTF-8")
    plist = tmp_path / "user.plist"
    system.setattr(i18n, "MACOS_PREFERENCES", (str(plist),))
    _plist(plist, ["fr-FR", "en-GB", "zh-Hans-CN"])
    assert resolve_language() == "en"
    _plist(plist, ["de-DE", "zh-Hans-CN", "en-US"])
    assert resolve_language() == "zh_CN"
    # Nothing the Mac lists has a catalog: the locale variables decide.
    _plist(plist, ["fr-FR", "de-DE"])
    assert language_choice().origin == "LANG"
    assert resolve_language() == "zh_CN"


def test_the_computer_wide_preferences_and_an_xml_plist_are_read(
    system: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    system.setattr(sys, "platform", "darwin")
    system.setenv("LANG", "en_US.UTF-8")
    computer = _plist(tmp_path / "computer.plist", ["zh-Hans"], binary=False)
    system.setattr(i18n, "MACOS_PREFERENCES", (str(tmp_path / "none.plist"), str(computer)))
    assert resolve_language() == "zh_CN"


@pytest.mark.parametrize(
    "content",
    [
        b"not a plist at all",
        b"",
        plistlib.dumps(["zh-Hans-CN"]),  # not a dictionary
        plistlib.dumps({"AppleLanguages": "zh-Hans-CN"}),  # not a list
        plistlib.dumps({"AppleLanguages": [1, True, ""]}),
        plistlib.dumps({"AppleLocale": "zh_CN"}),
    ],
    ids=["garbage", "empty", "list", "string", "no-strings", "no-key"],
)
def test_unreadable_mac_preferences_fall_back_to_lang(
    system: pytest.MonkeyPatch, tmp_path: Path, content: bytes
) -> None:
    system.setattr(sys, "platform", "darwin")
    system.setenv("LANG", "zh_CN.UTF-8")
    plist = tmp_path / "user.plist"
    plist.write_bytes(content)
    system.setattr(i18n, "MACOS_PREFERENCES", (str(plist),))
    choice = language_choice()
    assert (choice.lang, choice.origin) == ("zh_CN", "LANG")


def test_a_mac_preference_folder_that_cannot_be_read_is_not_an_error(
    system: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    system.setattr(sys, "platform", "darwin")
    system.setattr(i18n, "MACOS_PREFERENCES", (str(tmp_path),))  # a folder, not a file
    assert resolve_language() == "en"


def test_the_gui_on_a_mac_follows_qts_ui_languages_first(
    system: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Opened from the Finder (no LANG) or from a terminal (LANG=en_US)."""
    system.setattr(sys, "platform", "darwin")
    english = _plist(tmp_path / "user.plist", ["en-US"])
    system.setattr(i18n, "MACOS_PREFERENCES", (str(english),))
    assert resolve_language(system_languages=["zh-Hans-CN", "en-US"]) == "zh_CN"
    system.setenv("LANG", "en_US.UTF-8")
    choice = language_choice(system_languages=["zh-Hans-CN", "en-US"])
    assert (choice.lang, choice.origin) == ("zh_CN", ORIGIN_DESKTOP)
    # Qt lists nothing RoomScope has: the Mac's own list is next.
    assert resolve_language(system_languages=["fr-FR"]) == "en"


# --- Windows -----------------------------------------------------------------------------


def test_windows_follows_the_display_language_before_lang(system: pytest.MonkeyPatch) -> None:
    """Git Bash and MSYS set LANG=en_US.UTF-8 on a Chinese Windows."""
    system.setattr(sys, "platform", "win32")
    system.setenv("LANG", "en_US.UTF-8")
    system.setattr(i18n, "_windows_ui_language", lambda: "zh_CN")
    choice = language_choice()
    assert (choice.lang, choice.source, choice.origin) == ("zh_CN", SOURCE_SYSTEM, ORIGIN_WINDOWS)
    system.setattr(i18n, "_windows_ui_language", lambda: None)
    assert resolve_language() == "en_US"  # activate() then falls back to English
    assert language_choice().origin == "LANG"


# --- Linux and other POSIX systems -------------------------------------------------------


@pytest.mark.parametrize(
    ("language", "lang", "expected", "origin"),
    [
        ("zh_CN:en", "en_US.UTF-8", "zh_CN", "LANGUAGE"),
        ("en:zh_CN", "zh_CN.UTF-8", "en", "LANGUAGE"),
        ("fr:zh_CN:en", "en_US.UTF-8", "zh_CN", "LANGUAGE"),
        ("fr_FR:de", "zh_CN.UTF-8", "zh_CN", "LANG"),  # nothing listed has a catalog
        ("zh_CN:en", "C.UTF-8", "en", ""),  # gettext ignores LANGUAGE in the C locale
        ("zh_CN:en", "POSIX", "en", ""),
        ("", "zh_CN.UTF-8", "zh_CN", "LANG"),
        (":zh_CN", "en_US.UTF-8", "zh_CN", "LANGUAGE"),
    ],
)
def test_gnu_language_is_honoured_as_gettext_does(
    system: pytest.MonkeyPatch, language: str, lang: str, expected: str, origin: str
) -> None:
    system.setattr(sys, "platform", "linux")
    system.setenv("LANGUAGE", language)
    system.setenv("LANG", lang)
    choice = language_choice()
    assert (choice.lang, choice.origin) == (expected, origin)


def test_language_needs_a_locale_to_be_set(system: pytest.MonkeyPatch) -> None:
    system.setattr(sys, "platform", "linux")
    system.setenv("LANGUAGE", "zh_CN")
    assert resolve_language() == "en"
    system.setenv("LC_MESSAGES", "en_US.UTF-8")
    assert resolve_language() == "zh_CN"


def test_the_posix_variables_keep_their_order(system: pytest.MonkeyPatch) -> None:
    system.setattr(sys, "platform", "linux")
    system.setenv("LANG", "en_US.UTF-8")
    system.setenv("LC_MESSAGES", "zh_CN.UTF-8")
    assert language_choice().origin == "LC_MESSAGES"
    assert resolve_language() == "zh_CN"
    system.setenv("LC_ALL", "en_GB.UTF-8")
    assert resolve_language() == "en_GB"
    assert language_choice().origin == "LC_ALL"
    # The GUI's UI languages count only when no variable is set.
    for name in ("LC_ALL", "LC_MESSAGES", "LANG"):
        system.delenv(name)
    assert resolve_language(system_languages=["zh-CN"]) == "zh_CN"


# --- The explicit choices ----------------------------------------------------------------


def test_the_explicit_choices_come_before_the_system(system: pytest.MonkeyPatch) -> None:
    system.setattr(sys, "platform", "linux")
    system.setenv("LANG", "en_US.UTF-8")
    system.setenv("ROOMSCOPE_LANG", "zh_CN")
    choice = language_choice()
    assert (choice.lang, choice.source, choice.value) == ("zh_CN", SOURCE_ENVIRONMENT, "zh_CN")
    save_settings(UserSettings(language="en"))
    assert (language_choice().lang, language_choice().source) == ("en", SOURCE_SETTINGS)
    choice = language_choice("zh-Hans")
    assert (choice.lang, choice.source, choice.value) == ("zh_CN", SOURCE_OPTION, "zh-Hans")


def test_a_python_without_plistlib_falls_back_to_lang(
    system: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    system.setattr(sys, "platform", "darwin")
    system.setenv("LANG", "zh_CN.UTF-8")
    plist = _plist(tmp_path / "user.plist", ["en-US"])
    system.setattr(i18n, "MACOS_PREFERENCES", (str(plist),))
    system.setitem(sys.modules, "plistlib", None)  # import plistlib raises ImportError
    assert language_choice().origin == "LANG"
