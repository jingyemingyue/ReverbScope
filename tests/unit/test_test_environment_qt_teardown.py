"""Session Qt teardown must keep writing under the isolated home.

Function-scoped isolation ends before session teardown. Without a session
``REVERBSCOPE_HOME``, closing a leftover window could create ``ui.ini`` in
the real ``~/.reverbscope``. The session fixture owns that variable for the
whole process.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from reverbscope.io.recent import reverbscope_home

pytest.importorskip("PySide6.QtWidgets")


def test_session_home_survives_a_test_monkeypatch_undo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    function_home = Path(os.environ["REVERBSCOPE_HOME"]).resolve()
    monkeypatch.undo()
    after_undo = Path(os.environ["REVERBSCOPE_HOME"]).resolve()
    assert after_undo == function_home
    assert after_undo != (Path.home() / ".reverbscope").resolve()


def test_closing_a_window_targets_the_isolated_home(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from PySide6.QtWidgets import QApplication

    from reverbscope.ui import ui_state
    from reverbscope.ui.main_window import MainWindow

    isolated = tmp_path / "home"
    monkeypatch.setenv("REVERBSCOPE_HOME", str(isolated))
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.show()
    app.processEvents()
    window.close()
    app.processEvents()
    assert reverbscope_home().resolve() == isolated.resolve()
    assert (reverbscope_home() / ui_state.UI_FILE).parent.resolve() == isolated.resolve()
    assert isolated.resolve() != (Path.home() / ".reverbscope").resolve()
