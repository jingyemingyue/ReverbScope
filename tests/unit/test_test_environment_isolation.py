"""Infrastructure owns REVERBSCOPE_HOME and the English language pin.

A test that calls ``monkeypatch.undo()`` used to undo the autouse fixtures
that keep writes out of ``~/.reverbscope`` and that keep the catalog English
on a Chinese Mac. Session Qt teardown then ran after the function fixture
had already restored the process environment, so leftover windows could
write ``ui.ini`` into the real home. These tests lock the ownership split:
infrastructure uses its own ``MonkeyPatch.context()``; a test undo cannot
take that away.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from reverbscope.i18n import activate, language_choice
from reverbscope.io.recent import reverbscope_home
from reverbscope.settings import UserSettings, load_settings, save_settings


def _real_home() -> Path:
    return Path.home() / ".reverbscope"


def _sha256(path: Path) -> str | None:
    import hashlib

    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_monkeypatch_undo_keeps_the_isolated_reverbscope_home(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """``undo()`` used to put ``REVERBSCOPE_HOME`` back to the process value."""
    before = os.environ.get("REVERBSCOPE_HOME")
    assert before is not None
    assert Path(before) != _real_home()
    isolated = Path(before)

    monkeypatch.setenv("WT_SESSION", "probe")
    monkeypatch.undo()

    after = os.environ.get("REVERBSCOPE_HOME")
    assert after is not None
    assert Path(after).resolve() == isolated.resolve()
    assert Path(after).resolve() != _real_home().resolve()
    assert "WT_SESSION" not in os.environ
    # A write after undo must still land under the isolated folder.
    save_settings(UserSettings(language="en"))
    written = load_settings()
    assert written.language == "en"
    assert (reverbscope_home() / "settings.json").is_file()
    assert not (_real_home() / "settings.json").is_file() or _real_home() != reverbscope_home()


def test_monkeypatch_undo_keeps_the_english_language_pin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """On a Chinese Mac, undoing the shared monkeypatch restored zh_CN."""
    from reverbscope import i18n

    assert i18n.MACOS_PREFERENCES == ()
    monkeypatch.setenv("WT_SESSION", "probe")
    monkeypatch.undo()
    # The pin owns its own MonkeyPatch: preferred languages stay empty.
    assert i18n.MACOS_PREFERENCES == ()
    assert os.environ.get("LANG") == "C.UTF-8"
    assert i18n._macos_languages() == []

    # Without the pin, Darwin + Chinese preferred languages select zh_CN.
    # With the pin still holding MACOS_PREFERENCES as (), that path is closed.
    monkeypatch.setattr(sys, "platform", "darwin", raising=False)
    for name in ("LANG", "LC_ALL", "LC_MESSAGES", "LANGUAGE", "REVERBSCOPE_LANG"):
        monkeypatch.delenv(name, raising=False)
    choice = language_choice()
    assert choice.lang.split("_", 1)[0] == "en", choice
    activate(None)
    from reverbscope.i18n import _

    assert _("cannot write {path}: {error}").startswith("cannot write")


def test_an_exception_in_the_test_body_leaves_isolation_in_place(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The fixture must not rely on the test finishing cleanly to keep the home."""
    home = Path(os.environ["REVERBSCOPE_HOME"]).resolve()
    monkeypatch.setenv("REVERBSCOPE_PROBE", "1")
    try:
        raise RuntimeError("boom")
    except RuntimeError:
        assert Path(os.environ["REVERBSCOPE_HOME"]).resolve() == home
        assert home != _real_home().resolve()


def test_subprocess_inherits_the_isolated_home(tmp_path: Path) -> None:
    """A child process must not fall back to the developer's real home."""
    expected = str(Path(os.environ["REVERBSCOPE_HOME"]).resolve())
    script = (
        "import os, pathlib, json\n"
        "home = pathlib.Path(os.environ['REVERBSCOPE_HOME']).resolve()\n"
        "real = pathlib.Path.home() / '.reverbscope'\n"
        "assert home != real.resolve()\n"
        "home.mkdir(parents=True, exist_ok=True)\n"
        "(home / 'subprocess-marker.txt').write_text('ok', encoding='utf-8')\n"
        "print(home)\n"
    )
    done = subprocess.run(
        [sys.executable, "-c", script],
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(Path("src").resolve())},
    )
    child_home = Path(done.stdout.strip()).resolve()
    assert str(child_home) == expected
    assert (child_home / "subprocess-marker.txt").read_text(encoding="utf-8") == "ok"
    assert not (_real_home() / "subprocess-marker.txt").exists()


def test_consecutive_tests_do_not_share_settings(tmp_path: Path) -> None:
    """Each test gets its own folder; a previous test's settings stay there."""
    save_settings(UserSettings(language="zh_CN", cli_style="plain"))
    first = Path(os.environ["REVERBSCOPE_HOME"]).resolve()
    assert load_settings().language == "zh_CN"
    assert (first / "settings.json").is_file()
    # The next assertion is checked by the following test in this module.


def test_consecutive_tests_start_from_a_clean_home() -> None:
    """The test above wrote zh_CN; this one must not see that file."""
    home = Path(os.environ["REVERBSCOPE_HOME"]).resolve()
    assert not (home / "settings.json").exists()
    assert load_settings().language == ""


def test_process_reverbscope_home_is_restored_to_session_isolation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """After a function overlay ends, the session temp must still be set.

    This test only checks that undoing the *test* monkeypatch leaves a
    non-real home. The session fixture is what Qt teardown falls back to.
    """
    monkeypatch.undo()
    home = Path(os.environ["REVERBSCOPE_HOME"]).resolve()
    assert home != _real_home().resolve()
    assert home.is_dir() or home.parent.is_dir()


def test_real_home_files_keep_their_digests_across_an_undo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Even when the real folder exists, an undo must not rewrite it."""
    real = _real_home()
    settings = real / "settings.json"
    ui = real / "ui.ini"
    before_settings = _sha256(settings)
    before_ui = _sha256(ui)

    monkeypatch.setenv("WT_SESSION", "1")
    monkeypatch.undo()
    save_settings(UserSettings(cli_style="boxed"))
    assert (reverbscope_home() / "settings.json").is_file()

    assert _sha256(settings) == before_settings
    assert _sha256(ui) == before_ui
