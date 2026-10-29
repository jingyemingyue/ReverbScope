"""GUI starts when PortAudio cannot initialise (Ubuntu without PulseAudio)."""

from __future__ import annotations

import builtins
import sys
from collections.abc import Iterator

import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtWidgets import QApplication

from reverbscope.ui.main_window import MainWindow


@pytest.fixture(scope="module")
def app() -> Iterator[QApplication]:
    existing = QApplication.instance()
    created = existing is None
    application = QApplication.instance() if existing is not None else QApplication([])
    assert isinstance(application, QApplication)
    yield application
    if created:
        application.quit()


def test_main_window_starts_when_portaudio_fails_at_import(
    app: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``MainWindow`` must open; Standalone Run stays off; DAW mode still exists."""

    class PortAudioError(Exception):
        pass

    PortAudioError.__module__ = "sounddevice"
    real_import = builtins.__import__

    def fake_import(
        name: str,
        globals: object = None,
        locals: object = None,
        fromlist: tuple[str, ...] = (),
        level: int = 0,
    ) -> object:
        if name == "sounddevice" or name.startswith("sounddevice."):
            raise PortAudioError(
                "Error initializing PortAudio: PulseAudio_Initialize: Can't connect to server"
            )
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.delitem(sys.modules, "sounddevice", raising=False)
    monkeypatch.setattr(builtins, "__import__", fake_import)

    window = MainWindow()
    try:
        window.show_mode("standalone")
        page = window.standalone
        assert not page.run_button.isEnabled()
        assert page.status.property("banner") == "warn"
        assert "unavailable" in page.status.text().lower() or "Audio backend" in page.status.text()
        # Universal DAW Mode does not need PortAudio.
        window.show_mode("daw")
        assert window.daw is not None
    finally:
        window.close()
