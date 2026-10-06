"""Without PySide6 the GUI commands explain what to install instead of a traceback.

A wheel installed without the ``gui`` extra (or a Linux system without the Qt
system libraries) used to reach ``from PySide6...`` inside ``run_app`` and
print an ImportError traceback: the friendly message in ``cmd_gui`` only
guarded the import of ``roomscope.ui.app``, which does not import Qt.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from roomscope.cli.main import main
from roomscope.ui import app

MISSING = "No module named 'PySide6'"


def test_roomscope_gui_without_pyside6_prints_a_sentence(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with (
        patch.object(app, "pyside6_import_error", return_value=MISSING),
        patch.object(app, "run_app", side_effect=AssertionError("must not start")),
    ):
        assert main(["--lang", "en", "gui"]) == 2
    err = capsys.readouterr().err
    assert "Traceback" not in err
    assert MISSING in " ".join(err.split())  # the sentence is wrapped to the terminal
    assert 'pip install "PySide6_Essentials>=6.6"' in err
    # PyPI has no roomscope package yet: the advice must not send people there.
    assert "roomscope[gui]" not in err


def test_roomscope_gui_entry_point_without_pyside6(capsys: pytest.CaptureFixture[str]) -> None:
    with (
        patch.object(app, "pyside6_import_error", return_value=MISSING),
        patch.object(app, "run_app", side_effect=AssertionError("must not start")),
        patch.dict("os.environ", {"ROOMSCOPE_LANG": "en"}),
        pytest.raises(SystemExit) as stop,
    ):
        app.main()
    assert stop.value.code == 2
    err = capsys.readouterr().err
    assert MISSING in err
    assert "PySide6_Essentials" in err


def test_the_message_is_translated(capsys: pytest.CaptureFixture[str]) -> None:
    with (
        patch.object(app, "pyside6_import_error", return_value=MISSING),
        patch.object(app, "run_app", side_effect=AssertionError("must not start")),
    ):
        assert main(["--lang", "zh_CN", "gui"]) == 2
    err = capsys.readouterr().err
    assert "无法启动桌面界面" in "".join(err.split())  # wrapped between characters
    assert MISSING in " ".join(err.split())


def test_pyside6_import_error_is_none_when_qt_loads() -> None:
    pytest.importorskip("PySide6.QtWidgets")
    assert app.pyside6_import_error() is None


def test_a_session_without_a_screen_gets_a_sentence_not_an_abort(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Qt ends the whole process ("Could not load the Qt platform plugin xcb")
    when a Linux session has no display. The menu runs ``gui`` in its own
    process, so it would die with it; say so in words before Qt is started."""
    with (
        patch.object(app, "pyside6_import_error", return_value=None),
        patch.object(app, "display_missing", return_value=True),
        patch.object(app, "run_app", side_effect=AssertionError("must not start")),
    ):
        assert main(["--lang", "en", "gui"]) == 2
    err = " ".join(capsys.readouterr().err.replace("│", " ").split())
    assert "needs a graphical display" in err and "DISPLAY and WAYLAND_DISPLAY" in err
    assert "Traceback" not in err


def test_the_desktop_launcher_without_a_screen_says_so(capsys: pytest.CaptureFixture[str]) -> None:
    with (
        patch.object(app, "pyside6_import_error", return_value=None),
        patch.object(app, "display_missing", return_value=True),
        patch.object(app, "run_app", side_effect=AssertionError("must not start")),
        patch.dict("os.environ", {"ROOMSCOPE_LANG": "en"}),
        pytest.raises(SystemExit) as stop,
    ):
        app.main()
    assert stop.value.code == 2
    assert "graphical display" in capsys.readouterr().err


def test_the_smoke_test_does_not_need_a_screen(capsys: pytest.CaptureFixture[str]) -> None:
    """``roomscope gui --smoke`` runs Qt's offscreen platform by itself."""
    with (
        patch.object(app, "pyside6_import_error", return_value=None),
        patch.object(app, "display_missing", return_value=True),
        patch.object(app, "run_app", return_value=0) as run_app,
    ):
        assert main(["gui", "--smoke"]) == 0
    assert run_app.call_args.kwargs["smoke"] is True


@pytest.mark.parametrize(
    ("environ", "platform", "missing"),
    [
        ({}, "linux", True),
        ({"DISPLAY": ":0"}, "linux", False),
        ({"WAYLAND_DISPLAY": "wayland-0"}, "linux", False),
        ({"QT_QPA_PLATFORM": "offscreen"}, "linux", False),
        ({}, "win32", False),
        ({}, "darwin", False),
    ],
)
def test_a_screen_is_missing_only_on_linux_without_display_or_platform(
    environ: dict[str, str], platform: str, missing: bool
) -> None:
    assert app.display_missing(environ, platform) is missing
