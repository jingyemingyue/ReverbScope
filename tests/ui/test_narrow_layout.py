"""Regression tests for narrow window layout (960x640) and responsive repair.

Verifies that in narrow windows with both Navigator and Inspector open,
action buttons and content widgets in ProjectPage and StartPanel are not
horizontally clipped, remain within the visible scroll viewport, and preserve
keyboard accessibility and interactivity across the full test matrix.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import cast

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QPushButton, QScrollArea, QWidget

from reverbscope.audio import backend as backend_module
from reverbscope.audio import inventory as inventory_module
from reverbscope.audio.backend import DeviceInfo
from reverbscope.core.pipeline import Reference, analyze, synthetic_recording
from reverbscope.i18n import activate
from reverbscope.io.project_store import add_session, save_project
from reverbscope.io.session_store import save_measurement
from reverbscope.models.configuration import SweepSettings
from reverbscope.models.project import Project
from reverbscope.models.result import AnalysisResult
from reverbscope.models.session import MeasurementSession
from reverbscope.ui import theme
from reverbscope.ui.main_window import MainWindow
from tests.conftest import make_rir

pytestmark = pytest.mark.gui


@pytest.fixture(scope="module")
def app() -> QApplication:
    instance = QApplication.instance()
    return cast(QApplication, instance if instance is not None else QApplication([]))


class _Interface:
    """Mock audio interface for GUI tests."""

    name = "test"

    def list_devices(self) -> list[DeviceInfo]:
        return [
            DeviceInfo(0, "MacBook Pro Speakers", "Core Audio", 0, 2, 48000.0, False, True),
            DeviceInfo(1, "MacBook Pro Microphone", "Core Audio", 1, 0, 48000.0, True, False),
            DeviceInfo(2, "Studio Interface 2x2", "Core Audio", 2, 2, 48000.0, False, False),
        ]

    def check_sample_rate(self, *_args: object, **_kwargs: object) -> None:
        return None


@pytest.fixture
def interface(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("REVERBSCOPE_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("REVERBSCOPE_AUDIO_BACKEND", raising=False)
    real_build = inventory_module.build_inventory
    monkeypatch.setattr(backend_module, "get_backend", lambda name=None: _Interface())
    monkeypatch.setattr(
        inventory_module,
        "build_inventory",
        lambda backend, **kw: real_build(backend, probe_rates=False, platform="darwin"),
    )


def _pump(app: QApplication, seconds: float = 0.05) -> None:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.005)
    app.processEvents()


def _result(sweep: SweepSettings, rt60_s: float, seed: int, strong: bool = False) -> AnalysisResult:
    ir = make_rir(
        sweep.sample_rate,
        rt60_s=rt60_s,
        reflections=[(0.010, 0.5)] if strong else [],
        diffuse_level=0.02,
        seed=seed,
    )
    return analyze(
        synthetic_recording(sweep, ir, noise_rms=1e-5, seed=seed), Reference.from_settings(sweep)
    )


def _make_test_project(root: Path, sweep: SweepSettings) -> Path:
    project = root / "booth"
    save_project(project, Project(name="Booth"))
    for name, position, result in (
        ("a-1", "A", _result(sweep, 0.35, 1)),
        ("b-1", "B", _result(sweep, 0.9, 2, strong=True)),
    ):
        session = MeasurementSession(
            room_name="Booth", measurement_position=position, recording_profile="vocal"
        )
        save_measurement(project / name, session, result, copy_recording=False)
        add_session(project, project / name, position=position)
    return project


@pytest.mark.parametrize("language", ["en", "zh_CN"])
def test_project_page_actions_not_clipped_in_narrow_window(
    app: QApplication, interface: None, language: str
) -> None:
    """At 960x640 with Navigator and Inspector both open, all Project page
    actions must fit horizontally within the scroll viewport without clipping."""
    activate(language)
    try:
        theme.apply_application_chrome(app)
        window = MainWindow()
        window.resize(960, 640)
        window.show()
        _pump(app, 0.05)
        # Force inspector open at 960px (PR #97 leftover condition)
        window.set_inspector_open(True)
        window.show_project()
        _pump(app, 0.1)

        pv = window.project
        scroll = pv.findChild(QScrollArea)
        assert scroll is not None, "ProjectPage must contain a scroll area"
        viewport = scroll.viewport()
        assert viewport.width() > 0, "Viewport width must be positive"

        actions = [
            pv.add_button,
            pv.compare_button,
            pv.measure_button,
            pv.copy_button,
        ]

        for button in actions:
            assert button.isVisible(), f"Button {button.text()!r} must be visible"
            assert button.focusPolicy() != Qt.FocusPolicy.NoFocus, (
                f"Button {button.text()!r} must be keyboard focusable"
            )

            # Check that button width is not squeezed smaller than its sizeHint
            assert button.width() + 1 >= button.sizeHint().width(), (
                f"Button {button.text()!r} text clipped: {button.width()} < {button.sizeHint().width()}"
            )

            # Check that button is within horizontal bounds of the scroll viewport
            top_left = button.mapTo(viewport, button.rect().topLeft())
            top_right = button.mapTo(viewport, button.rect().topRight())

            assert top_left.x() >= 0, (
                f"Button {button.text()!r} left edge ({top_left.x()}px) is off-screen to the left "
                f"in {language} at viewport width {viewport.width()}px"
            )
            assert top_right.x() <= viewport.width(), (
                f"Button {button.text()!r} right edge ({top_right.x()}px) overflows viewport "
                f"({viewport.width()}px) by {top_right.x() - viewport.width()}px in {language}"
            )

        window.close()
    finally:
        activate("en")


@pytest.mark.parametrize("language", ["en", "zh_CN"])
def test_project_page_actions_with_loaded_project_in_narrow_window(
    app: QApplication,
    interface: None,
    language: str,
    tmp_path: Path,
    short_sweep: SweepSettings,
) -> None:
    """When a project is open, its action buttons are enabled, clickable,
    and fully contained horizontally inside the 960x640 viewport with inspector open."""
    activate(language)
    try:
        theme.apply_application_chrome(app)
        project_dir = _make_test_project(tmp_path, short_sweep)
        window = MainWindow()
        window.resize(960, 640)
        window.show()
        _pump(app, 0.05)
        window.set_inspector_open(True)
        window.show_project(project_dir)
        assert window.model.wait_until_loaded()
        _pump(app, 0.1)

        pv = window.project
        scroll = pv.findChild(QScrollArea)
        assert scroll is not None
        viewport = scroll.viewport()

        # add_button, measure_button, copy_button must be enabled when a project is open
        assert pv.add_button.isEnabled()
        assert pv.measure_button.isEnabled()
        assert pv.copy_button.isEnabled()

        for button in [pv.add_button, pv.compare_button, pv.measure_button, pv.copy_button]:
            assert button.isVisible()
            top_left = button.mapTo(viewport, button.rect().topLeft())
            top_right = button.mapTo(viewport, button.rect().topRight())
            assert top_left.x() >= 0
            assert top_right.x() <= viewport.width(), (
                f"{button.text()!r} right {top_right.x()} overflows viewport {viewport.width()} in {language}"
            )

        # Select second take to enable compare_button and test interaction
        pv.table.selectRow(1)
        assert pv.compare_button.isEnabled()

        window.close()
    finally:
        activate("en")


@pytest.mark.parametrize("language", ["en", "zh_CN"])
def test_start_panel_shortcuts_not_overflowing_in_narrow_window(
    app: QApplication, interface: None, language: str
) -> None:
    """At 960x640 with Inspector open, StartPanel body must not exceed the viewport
    width, preventing horizontal clipping of shortcut key captions."""
    activate(language)
    try:
        theme.apply_application_chrome(app)
        window = MainWindow()
        window.resize(960, 640)
        window.show()
        _pump(app, 0.05)
        # Force inspector open at 960px (PR #97 leftover condition)
        window.set_inspector_open(True)
        window.show_home()
        _pump(app, 0.1)

        home = window.home
        scroll = home.scroll_area
        viewport = scroll.viewport()
        body = scroll.widget()
        assert body is not None

        assert body.width() <= viewport.width(), (
            f"StartPanel body width ({body.width()}px) overflows scroll viewport "
            f"({viewport.width()}px) by {body.width() - viewport.width()}px in {language}"
        )

        for child in body.findChildren(QWidget):
            if child.isVisible():
                pt_right = child.mapTo(viewport, child.rect().topRight())
                assert pt_right.x() <= viewport.width() + 1, (
                    f"StartPanel child {child.metaObject().className()} right edge "
                    f"({pt_right.x()}px) overflows viewport ({viewport.width()}px) in {language}"
                )

        window.close()
    finally:
        activate("en")


# Test Matrix covering:
# 960x640 (zh, en) x (light, dark)
# 1280x800 (zh, en) x (light, dark)
# 1440x900 (zh, en) x (light)
# 1920x1080 (zh, en) x (light)
MATRIX_CASES = [
    ((960, 640), "en", "light"),
    ((960, 640), "en", "dark"),
    ((960, 640), "zh_CN", "light"),
    ((960, 640), "zh_CN", "dark"),
    ((1280, 800), "en", "light"),
    ((1280, 800), "en", "dark"),
    ((1280, 800), "zh_CN", "light"),
    ((1280, 800), "zh_CN", "dark"),
    ((1440, 900), "en", "light"),
    ((1440, 900), "zh_CN", "light"),
    ((1920, 1080), "en", "light"),
    ((1920, 1080), "zh_CN", "light"),
]


@pytest.mark.parametrize("size,language,theme_name", MATRIX_CASES)
def test_matrix_layout_responsive_integrity(
    app: QApplication,
    interface: None,
    monkeypatch: pytest.MonkeyPatch,
    size: tuple[int, int],
    language: str,
    theme_name: str,
) -> None:
    """Verifies layout integrity across the full test matrix combinations."""
    monkeypatch.setenv(theme.ENV_COLOR_SCHEME, theme_name)
    activate(language)
    try:
        theme.apply_application_chrome(app)
        window = MainWindow()
        window.resize(*size)
        window.show()
        _pump(app, 0.05)
        window.set_inspector_open(True)

        # 1. Check Project View
        window.show_project()
        _pump(app, 0.05)
        pv = window.project
        p_scroll = pv.findChild(QScrollArea)
        assert p_scroll is not None
        p_viewport = p_scroll.viewport()

        for btn in (pv.add_button, pv.compare_button, pv.measure_button, pv.copy_button):
            assert btn.isVisible()
            assert btn.focusPolicy() != Qt.FocusPolicy.NoFocus
            tr = btn.mapTo(p_viewport, btn.rect().topRight())
            tl = btn.mapTo(p_viewport, btn.rect().topLeft())
            assert tl.x() >= 0
            assert tr.x() <= p_viewport.width() + 1

        # 2. Check Start Panel
        window.show_home()
        _pump(app, 0.05)
        home = window.home
        h_scroll = home.scroll_area
        h_viewport = h_scroll.viewport()
        h_body = h_scroll.widget()
        assert h_body is not None
        assert h_body.width() <= h_viewport.width() + 1

        window.close()
    finally:
        activate("en")


def test_simulated_wide_font_metrics_containment(app: QApplication, interface: None) -> None:
    """Verifies that under simulated wide font metrics (e.g. Windows Segoe UI
    or enlarged DPI settings), both StartPanel and ProjectPage adaptively stack
    their mode cards and action buttons, completely preventing viewport overflow."""
    from PySide6.QtGui import QFont

    orig_font = app.font()
    app.setFont(QFont("Arial", 12))
    activate("en")
    try:
        theme.apply_application_chrome(app)
        window = MainWindow()
        window.resize(960, 640)
        window.show()
        _pump(app, 0.05)
        window.set_inspector_open(True)

        # 1. StartPanel check
        window.show_home()
        _pump(app, 0.05)
        home = window.home
        h_vp = home.scroll_area.viewport()
        h_body = home.scroll_area.widget()
        assert h_body is not None
        assert h_body.width() <= h_vp.width() + 1
        for child in home.composer.findChildren(QPushButton):
            if child.isVisible():
                tr = child.mapTo(h_vp, child.rect().topRight())
                tl = child.mapTo(h_vp, child.rect().topLeft())
                assert tl.x() >= 0
                assert tr.x() <= h_vp.width() + 1

        # 2. ProjectPage check
        window.show_project()
        _pump(app, 0.05)
        pv = window.project
        p_scroll = pv.findChild(QScrollArea)
        assert p_scroll is not None
        p_vp = p_scroll.viewport()
        for btn in (pv.add_button, pv.compare_button, pv.measure_button, pv.copy_button):
            assert btn.isVisible()
            assert btn.focusPolicy() != Qt.FocusPolicy.NoFocus
            tr = btn.mapTo(p_vp, btn.rect().topRight())
            tl = btn.mapTo(p_vp, btn.rect().topLeft())
            assert tl.x() >= 0
            assert tr.x() <= p_vp.width() + 1, (
                f"Button {btn.text()!r} right edge {tr.x()} overflows viewport {p_vp.width()}"
            )

        window.close()
    finally:
        app.setFont(orig_font)
        activate("en")
