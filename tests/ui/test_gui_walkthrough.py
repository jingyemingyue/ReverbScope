"""The first-measurement card on Home, and the profile explanations."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from reverbscope.audio.fake import make_rir
from reverbscope.core.pipeline import Reference, analyze, synthetic_recording
from reverbscope.models.configuration import SweepSettings
from reverbscope.models.session import MeasurementSession
from reverbscope.settings import load_settings
from reverbscope.ui.main_window import MainWindow

pytestmark = pytest.mark.gui


@pytest.fixture(scope="module")
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_the_card_shows_on_a_first_start_and_stays_away_once_dismissed(
    app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("REVERBSCOPE_HOME", str(tmp_path / "home"))
    window = MainWindow()
    window.show()
    card = window.home.walkthrough
    assert card.isVisible()
    # Its buttons lead into the modes.
    card.buttons[0].click()
    assert window.stack.currentWidget() is window.standalone and window.standalone.demo_mode
    window.show_home()
    card.buttons[1].click()
    assert window.stack.currentWidget() is window.daw
    window.show_home()
    card.dismiss_button.click()
    assert card.isHidden()
    assert load_settings().walkthrough_dismissed is True
    window.show_home()
    assert card.isHidden()
    window.close()
    # The next start remembers; Help ▸ Getting started brings the card back.
    again = MainWindow()
    again.show()
    assert again.home.walkthrough.isHidden()
    again.getting_started_action.trigger()
    assert again.stack.currentWidget() is again.home
    assert again.home.walkthrough.isVisible()
    assert load_settings().walkthrough_dismissed is False
    again.close()


def test_the_profile_selector_explains_the_profile(
    app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, short_sweep: SweepSettings
) -> None:
    monkeypatch.setenv("REVERBSCOPE_HOME", str(tmp_path / "home"))
    result = analyze(
        synthetic_recording(short_sweep, make_rir(short_sweep.sample_rate, rt60_s=0.3)),
        Reference.from_settings(short_sweep),
    )
    window = MainWindow()
    window.show()
    window.show_mode("universal_daw")
    page = window.daw
    page.profile.setCurrentIndex(page.profile.findData("drums"))
    assert "Drums" in page.profile.toolTip()
    from reverbscope.ui.profile_dialog import ProfileDialog

    page.profile_help.click()
    dialogs = [w for w in app.topLevelWidgets() if isinstance(w, ProfileDialog) and w.isVisible()]
    assert dialogs and dialogs[0].item.name == "drums"
    assert "not judged" in " ".join(dialogs[0].item.skips)
    for dialog in dialogs:
        dialog.close()
    # The inspector explains the profile the result was interpreted with.
    window.model.add_take(
        MeasurementSession(), result, [], "", "vocal", unsaved=False, synthetic=True
    )
    assert window.inspector.profile_button.isVisibleTo(window.inspector)
    dialog = window.inspector.show_profile_help()
    assert dialog is not None
    assert dialog.item.name == "vocal" and "Vocals" in dialog.windowTitle()
    dialog.close()
    window.close()
