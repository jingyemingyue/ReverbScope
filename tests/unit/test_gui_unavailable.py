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
    assert MISSING in err
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
    assert "无法启动桌面界面" in err
    assert MISSING in err


def test_pyside6_import_error_is_none_when_qt_loads() -> None:
    pytest.importorskip("PySide6.QtWidgets")
    assert app.pyside6_import_error() is None
