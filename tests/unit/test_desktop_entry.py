"""The macOS app opens the GUI when Finder passes no arguments."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from reverbscope.__main__ import desktop_args


def test_finder_launch_opens_gui() -> None:
    with (
        patch.object(sys, "platform", "darwin"),
        patch.object(sys, "executable", "/Applications/ReverbScope.app/Contents/MacOS/ReverbScope"),
        patch.object(sys, "argv", ["ReverbScope"]),
        patch.object(sys, "frozen", True, create=True),
    ):
        assert desktop_args() == ["gui"]


def test_mac_cli_keeps_cli_semantics() -> None:
    with (
        patch.object(sys, "platform", "darwin"),
        patch.object(sys, "executable", "/tmp/reverbscope/reverbscope"),
        patch.object(sys, "argv", ["reverbscope"]),
        patch.object(sys, "frozen", True, create=True),
    ):
        assert desktop_args() is None


def test_windows_gui_launcher_opens_gui() -> None:
    with (
        patch.object(sys, "platform", "win32"),
        patch.object(sys, "executable", r"C:\Program Files\ReverbScope\reverbscope-gui.exe"),
        patch.object(sys, "argv", [r"C:\Program Files\ReverbScope\reverbscope-gui.exe"]),
        patch.object(sys, "frozen", True, create=True),
    ):
        assert desktop_args() == ["gui"]


def test_linux_gui_launcher_opens_gui() -> None:
    with (
        patch.object(sys, "platform", "linux"),
        patch.object(sys, "executable", "/opt/reverbscope/reverbscope-gui"),
        patch.object(sys, "argv", ["reverbscope-gui"]),
        patch.object(sys, "frozen", True, create=True),
    ):
        assert desktop_args() == ["gui"]


def test_console_executable_keeps_cli_semantics() -> None:
    with (
        patch.object(sys, "platform", "win32"),
        patch.object(sys, "executable", r"C:\Program Files\ReverbScope\reverbscope.exe"),
        patch.object(sys, "argv", ["reverbscope.exe"]),
        patch.object(sys, "frozen", True, create=True),
    ):
        assert desktop_args() is None


@pytest.mark.parametrize(
    "extra",
    [[r"C:\Users\me\Desktop\take.wav"], ["/home/me/take.wav"], ["session-folder"]],
)
def test_file_dropped_on_gui_launcher_opens_gui(extra: list[str]) -> None:
    """The windowed launcher has no console for a usage error."""
    with (
        patch.object(sys, "platform", "win32"),
        patch.object(sys, "executable", r"C:\ReverbScope\reverbscope-gui.exe"),
        patch.object(sys, "argv", ["reverbscope-gui.exe", *extra]),
        patch.object(sys, "frozen", True, create=True),
    ):
        assert desktop_args() == ["gui"]


@pytest.mark.parametrize("extra", [["--version"], ["analyze", "--help"], ["-v", "devices"]])
def test_gui_launcher_keeps_real_commands(extra: list[str]) -> None:
    with (
        patch.object(sys, "platform", "linux"),
        patch.object(sys, "executable", "/opt/reverbscope/reverbscope-gui"),
        patch.object(sys, "argv", ["reverbscope-gui", *extra]),
        patch.object(sys, "frozen", True, create=True),
    ):
        assert desktop_args() is None


def test_mac_app_with_arguments_is_the_cli() -> None:
    with (
        patch.object(sys, "platform", "darwin"),
        patch.object(sys, "executable", "/Applications/ReverbScope.app/Contents/MacOS/ReverbScope"),
        patch.object(sys, "argv", ["ReverbScope", "--version"]),
        patch.object(sys, "frozen", True, create=True),
    ):
        assert desktop_args() is None


def test_gui_launcher_passes_explicit_arguments_through() -> None:
    with (
        patch.object(sys, "platform", "win32"),
        patch.object(sys, "executable", r"C:\ReverbScope\reverbscope-gui.exe"),
        patch.object(sys, "argv", ["reverbscope-gui.exe", "gui", "--smoke"]),
        patch.object(sys, "frozen", True, create=True),
    ):
        assert desktop_args() is None


def test_unfrozen_python_is_never_redirected() -> None:
    with (
        patch.object(sys, "executable", "/usr/bin/reverbscope-gui"),
        patch.object(sys, "argv", ["reverbscope-gui"]),
        patch.object(sys, "frozen", False, create=True),
    ):
        assert desktop_args() is None


def test_bundle_keeps_the_matplotlib_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """PyInstaller's runtime hook sets a new temporary MPLCONFIGDIR per start;
    a bundle replaces it with a folder that survives, a source install does not."""
    from reverbscope import __version__
    from reverbscope.__main__ import keep_matplotlib_cache

    monkeypatch.setenv("REVERBSCOPE_HOME", str(tmp_path))
    monkeypatch.setenv("MPLCONFIGDIR", "temporary-per-start")
    monkeypatch.delattr(sys, "frozen", raising=False)
    keep_matplotlib_cache()
    assert os.environ["MPLCONFIGDIR"] == "temporary-per-start"
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    keep_matplotlib_cache()
    folder = tmp_path / "cache" / f"matplotlib-{__version__}"
    assert folder.is_dir()
    assert os.environ["MPLCONFIGDIR"] == str(folder)
