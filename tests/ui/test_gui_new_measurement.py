"""New Measurement: Universal DAW Mode and Standalone Mode are two routes of one
page. The steps, the action bar and the defaults belong to the page; only the
step that captures the sound changes with the route."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMessageBox, QScrollArea

from reverbscope.audio.playrec import DEFAULT_STANDALONE_LEVEL_DBFS
from reverbscope.models.configuration import SweepSettings
from reverbscope.ui.main_window import MainWindow
from reverbscope.ui.pages import ROUTE_DAW, ROUTE_STANDALONE

pytestmark = pytest.mark.gui


@pytest.fixture(scope="module")
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(
    app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[MainWindow]:
    monkeypatch.setenv("REVERBSCOPE_HOME", str(tmp_path / "home"))
    win = MainWindow()
    win.show()
    app.processEvents()
    yield win
    win.state.unsaved_take = False
    win.close()


def _answer(monkeypatch: pytest.MonkeyPatch, label: str) -> list[list[str]]:
    """Make the next message box click its button ``label``; return what it offered."""
    offered: list[list[str]] = []

    def exec_(box: QMessageBox) -> int:
        offered.append([button.text() for button in box.buttons()])
        next(button for button in box.buttons() if button.text() == label).click()
        return 0

    monkeypatch.setattr(QMessageBox, "exec", exec_)
    return offered


def test_both_routes_are_one_page_with_the_same_steps(window: MainWindow) -> None:
    page = window.measure
    window.show_mode("universal_daw")
    assert window.stack.currentWidget() is page
    assert page.route == ROUTE_DAW
    assert page.recording_panel.isVisibleTo(page)
    assert not page.devices_panel.isVisibleTo(page)
    assert not page.stop_button.isVisibleTo(page)
    assert page.run_button.text() == "Analyze"
    assert not page.playback_level.isVisibleTo(page)

    window.show_mode("standalone")
    assert window.stack.currentWidget() is page
    assert page.route == ROUTE_STANDALONE
    assert page.devices_panel.isVisibleTo(page)
    assert not page.recording_panel.isVisibleTo(page)
    assert page.stop_button.isVisibleTo(page)
    assert page.run_button.text() == "Run Measurement"
    assert page.playback_level.isVisibleTo(page) and not page.level.isVisibleTo(page)


def test_each_route_starts_at_its_own_level(window: MainWindow) -> None:
    """The DAW's peak level keeps its default; the interface starts low, as the
    safety rules of Standalone Mode say."""
    page = window.measure
    assert page.level.value() == pytest.approx(SweepSettings().level_dbfs)
    assert page.playback_level.value() == pytest.approx(DEFAULT_STANDALONE_LEVEL_DBFS)
    window.show_mode("standalone")
    assert page.current_sweep_settings().level_dbfs == pytest.approx(DEFAULT_STANDALONE_LEVEL_DBFS)
    window.show_mode("universal_daw")
    assert page.current_sweep_settings().level_dbfs == pytest.approx(SweepSettings().level_dbfs)


def test_the_action_bar_is_outside_the_scrolling_body(window: MainWindow) -> None:
    """The Run or Analyze button must stay in view on a short window."""
    page = window.measure
    for scroll in page.findChildren(QScrollArea):
        assert not scroll.isAncestorOf(page.run_button)
        assert not scroll.isAncestorOf(page.back_button)
    assert page.run_button.parentWidget() is not None


def test_a_busy_page_locks_the_route_switch(
    window: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    page = window.measure
    window.show_mode("standalone")
    monkeypatch.setattr(page, "is_busy", lambda: True)
    page.refresh_controls()
    assert not any(button.isEnabled() for button in page.route_buttons.values())
    assert not page.run_button.isEnabled()
    # A menu shortcut while busy shows the page as it is.
    window.show_mode("universal_daw")
    assert window.stack.currentWidget() is page
    assert page.route == ROUTE_STANDALONE
    monkeypatch.undo()
    page.refresh_controls()
    assert all(button.isEnabled() for button in page.route_buttons.values())


def test_leaving_the_demo_returns_to_the_interface(window: MainWindow) -> None:
    page = window.measure
    window.show_mode("demo")
    assert page.demo_mode and page.route == ROUTE_STANDALONE
    assert page.demo_bar.isVisibleTo(page)
    page.leave_demo_button.click()
    assert not page.demo_mode and page.route == ROUTE_STANDALONE
    assert not page.demo_bar.isVisibleTo(page)


def test_the_demo_does_not_outlive_its_route(window: MainWindow) -> None:
    page = window.measure
    window.show_mode("demo")
    window.show_mode("universal_daw")
    assert not page.demo_mode
    assert not page.demo_bar.isVisibleTo(page)


def test_the_daw_route_shows_no_interface_status(window: MainWindow) -> None:
    """The device line in the footer belongs to the interface route."""
    page = window.measure
    window.show_mode("standalone")
    window.show_mode("universal_daw")
    assert page.status.text() == ""


def test_the_walkthrough_points_at_the_demo_card_without_repeating_it(
    window: MainWindow,
) -> None:
    card = window.home.walkthrough
    assert not hasattr(card, "buttons") and not hasattr(card, "demo_button")
    assert card.guide_button.isVisibleTo(card)
    daw, standalone, demo = window.home.mode_cards
    assert daw.button.property("primary") is True
    assert standalone.button.property("primary") is True
    assert demo.button.property("primary") is not True
    demo.button.click()
    assert window.measure.demo_mode and window.stack.currentWidget() is window.measure


def test_a_new_take_asks_before_it_replaces_an_unsaved_take(
    window: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    page = window.measure
    window.show_mode("standalone")
    window.state.unsaved_take = True
    window.state.result = object()  # type: ignore[assignment]
    started: list[object] = []
    monkeypatch.setattr(page, "_preflight", lambda *args: started.append(args) or None)

    offered = _answer(monkeypatch, "Cancel")
    page.start_measurement()
    assert offered and "Discard" in offered[0] and "Cancel" in offered[0]
    assert started == [] and window.state.unsaved_take is True

    _answer(monkeypatch, "Discard")
    page.start_measurement()
    assert len(started) == 1
    window.state.result = None
    window.state.unsaved_take = False


def test_without_an_unsaved_take_nothing_is_asked(
    window: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    page = window.measure
    offered = _answer(monkeypatch, "Cancel")
    window.state.unsaved_take = False
    assert page._may_replace_unsaved_take() is True
    assert offered == []
