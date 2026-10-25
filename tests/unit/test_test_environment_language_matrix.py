"""Language selection stays deterministic under the test pin.

The product still switches with ``--lang`` / ``activate``. These tests lock
that a Chinese system preference cannot leak into a later English assertion
after ``monkeypatch.undo()``, and that explicit Chinese still works.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from reverbscope.i18n import _, activate, language_choice
from reverbscope.settings import UserSettings, save_settings
from tests.frames import invoke


def test_explicit_lang_zh_cn_still_translates(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("REVERBSCOPE_HOME", str(tmp_path / "home"))
    code, _out, err = invoke(
        ["--lang", "zh_CN", "--style", "boxed", "show", "somewhere", "--bogus"], capsys
    )
    assert code == 2
    assert err.startswith("╭─ ✗ 错误 ─"), err.splitlines()[0] if err else err


def test_explicit_lang_en_stays_english(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("REVERBSCOPE_HOME", str(tmp_path / "home"))
    code, _out, err = invoke(
        ["--lang", "en", "--style", "boxed", "show", "somewhere", "--bogus"], capsys
    )
    assert code == 2
    assert err.startswith("╭─ ✗ Error ─")


def test_lc_all_c_stays_english_under_the_pin() -> None:
    from reverbscope.i18n import current_locale

    assert os.environ.get("LANG") == "C.UTF-8"
    assert current_locale() == "en"
    assert _("cannot write {path}: {error}").startswith("cannot write")
    # language_choice() may still see a Windows getlocale() tag such as
    # "English_United States"; it must not resolve to zh_CN under the pin.
    assert language_choice().lang != "zh_CN", language_choice()


def test_activate_zh_then_en_does_not_leak() -> None:
    activate("zh_CN")
    assert "无法写入" in _("cannot write {path}: {error}")
    activate("en")
    assert _("cannot write {path}: {error}").startswith("cannot write")


def test_saved_language_zh_is_honoured_when_requested(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("REVERBSCOPE_HOME", str(tmp_path / "home"))
    save_settings(UserSettings(language="zh_CN", cli_style="boxed"))
    code, _out, err = invoke(["show", "somewhere", "--bogus"], capsys)
    assert code == 2
    assert err.startswith("╭─ ✗ 错误 ─"), err.splitlines()[0] if err else err


def test_undo_cannot_reopen_macos_preferences(monkeypatch: pytest.MonkeyPatch) -> None:
    from reverbscope import i18n
    from reverbscope.i18n import current_locale

    monkeypatch.undo()
    monkeypatch.setattr(sys, "platform", "darwin", raising=False)
    assert i18n.MACOS_PREFERENCES == ()
    assert i18n._macos_languages() == []
    for name in ("LANG", "LC_ALL", "LC_MESSAGES", "LANGUAGE", "REVERBSCOPE_LANG"):
        monkeypatch.delenv(name, raising=False)
    assert language_choice().lang != "zh_CN", language_choice()
    activate(None)
    assert current_locale() == "en"
    assert _("cannot write {path}: {error}").startswith("cannot write")
