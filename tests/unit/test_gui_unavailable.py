"""Without PySide6 the GUI commands explain what to install instead of a traceback.

A wheel installed without the ``gui`` extra (or a Linux system without the Qt
system libraries) used to reach ``from PySide6...`` inside ``run_app`` and
print an ImportError traceback: the friendly message in ``cmd_gui`` only
guarded the import of ``reverbscope.ui.app``, which does not import Qt.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from reverbscope.cli.main import main
from reverbscope.ui import app

MISSING = "No module named 'PySide6'"


def test_reverbscope_gui_without_pyside6_prints_a_sentence(
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
    assert 'pip install "PySide6_Essentials>=6.6,<6.12"' in err
    # PyPI has no reverbscope package yet: the advice must not send people there.
    assert "reverbscope[gui]" not in err


def test_reverbscope_gui_entry_point_without_pyside6(capsys: pytest.CaptureFixture[str]) -> None:
    with (
        patch.object(app, "pyside6_import_error", return_value=MISSING),
        patch.object(app, "run_app", side_effect=AssertionError("must not start")),
        patch.dict("os.environ", {"REVERBSCOPE_LANG": "en"}),
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


@pytest.mark.parametrize(
    ("environ", "platform", "expected"),
    [
        ({}, "linux", True),
        ({"DISPLAY": "", "WAYLAND_DISPLAY": "", "QT_QPA_PLATFORM": ""}, "linux", True),
        ({"DISPLAY": ":0"}, "linux", False),
        ({"WAYLAND_DISPLAY": "wayland-0"}, "linux", False),
        ({"QT_QPA_PLATFORM": "offscreen"}, "linux", False),
        ({"QT_QPA_PLATFORM": "minimal"}, "linux", False),
        ({"QT_QPA_PLATFORM": "xcb"}, "linux", False),
        ({}, "linux2", True),
        ({}, "darwin", False),
        ({}, "win32", False),
    ],
)
def test_display_missing_only_means_linux_without_a_display(
    environ: dict[str, str], platform: str, expected: bool
) -> None:
    assert app.display_missing(environ, platform) is expected


def test_both_launchers_refuse_a_linux_session_without_a_display(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with (
        patch.object(app, "pyside6_import_error", return_value=None),
        patch.object(app, "display_missing", return_value=True),
        patch.object(app, "run_app", side_effect=AssertionError("must not start")),
    ):
        assert main(["--lang", "en", "gui"]) == 2
        with pytest.raises(SystemExit) as stop:
            app.main()
    assert stop.value.code == 2
    err = capsys.readouterr().err
    assert "Traceback" not in err
    assert "graphical display" in " ".join(err.split())
    assert "WAYLAND_DISPLAY" in err


def test_the_missing_display_message_is_chinese(capsys: pytest.CaptureFixture[str]) -> None:
    with (
        patch.object(app, "pyside6_import_error", return_value=None),
        patch.object(app, "display_missing", return_value=True),
        patch.object(app, "run_app", side_effect=AssertionError("must not start")),
        patch.dict("os.environ", {"REVERBSCOPE_LANG": "zh_CN"}),
    ):
        assert main(["--lang", "zh_CN", "gui"]) == 2
        with pytest.raises(SystemExit) as stop:
            app.main()
    assert stop.value.code == 2
    err = "".join(capsys.readouterr().err.split())
    assert "Traceback" not in err
    assert "桌面应用需要图形显示环境" in err
    assert "WAYLAND_DISPLAY" in err


def test_gui_smoke_starts_when_the_display_is_missing() -> None:
    with (
        patch.object(app, "pyside6_import_error", return_value=None),
        patch.object(app, "display_missing", return_value=True),
        patch.object(app, "run_app", return_value=0) as started,
    ):
        assert main(["gui", "--smoke"]) == 0
    started.assert_called_once()
    assert started.call_args.kwargs["smoke"] is True


def test_a_present_display_keeps_the_app_return_code() -> None:
    with (
        patch.object(app, "pyside6_import_error", return_value=None),
        patch.object(app, "display_missing", return_value=False),
        patch.object(app, "run_app", return_value=7) as started,
    ):
        assert main(["--lang", "en", "gui"]) == 7
        with pytest.raises(SystemExit) as stop:
            app.main()
    assert stop.value.code == 7
    assert started.call_count == 2


def test_a_missing_pyside6_is_reported_before_a_missing_display(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with (
        patch.object(app, "pyside6_import_error", return_value=MISSING),
        patch.object(app, "display_missing", return_value=True),
        patch.object(app, "run_app", side_effect=AssertionError("must not start")),
    ):
        assert main(["--lang", "en", "gui"]) == 2
    err = capsys.readouterr().err
    assert MISSING in " ".join(err.split())
    assert "graphical display" not in err


def test_the_terminal_edition_is_reported_before_a_missing_display(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with (
        patch("reverbscope.edition.is_terminal_package", return_value=True),
        patch.object(app, "run_app", side_effect=AssertionError("must not start")),
    ):
        assert main(["gui"]) == 2
    assert "graphical display" not in capsys.readouterr().err
