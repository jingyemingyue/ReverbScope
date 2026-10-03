"""The environment report (``reverbscope doctor``): build, settings, privacy."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from reverbscope.diagnostics import (
    PRIVACY_NOTE,
    build_info,
    environment_report,
    format_environment_report,
    redact_home,
)


def test_home_folder_is_redacted_on_posix_and_windows() -> None:
    home = "/home/anna"  # strings, not Path: Path("/home/anna") is \home\anna on Windows
    assert redact_home("/home/anna/.reverbscope/reverbscope.log", home) == "~/.reverbscope/reverbscope.log"
    assert redact_home("/home/anna", home) == "~"
    # A sibling whose name starts with the account name is not the home folder.
    assert redact_home("/home/annabel/x", home) == "/home/annabel/x"
    assert redact_home("/opt/reverbscope", home) == "/opt/reverbscope"
    windows_home = "C:\\Users\\Anna"
    assert redact_home("c:\\users\\anna\\.reverbscope\\settings.json", windows_home) == (
        "~\\.reverbscope\\settings.json"
    )


def test_build_info_is_read_from_the_bundle_file(tmp_path: Path) -> None:
    path = tmp_path / "build_info.json"
    assert build_info(path) is None  # source and pip installs have none
    path.write_text(json.dumps({"commit": "abc123", "ci_run": "https://x/1"}), encoding="utf-8")
    assert build_info(path) == {"commit": "abc123", "ci_run": "https://x/1"}
    path.write_text("[1, 2]", encoding="utf-8")
    assert build_info(path) is None
    path.write_text("{not json", encoding="utf-8")
    assert build_info(path) is None


def test_report_keeps_output_folder_private(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("REVERBSCOPE_HOME", str(tmp_path))
    secret = tmp_path / "Clients" / "Private Project"
    (tmp_path / "settings.json").write_text(
        json.dumps({"schema_version": 1, "output_dir": str(secret), "theme": "dark"}),
        encoding="utf-8",
    )
    report = environment_report("fake")
    assert report["settings"]["output_dir_set"] is True
    assert report["settings"]["theme"] == "dark"
    text = format_environment_report(report)
    assert "Private Project" not in text and "Private Project" not in json.dumps(report)
    assert text.endswith(PRIVACY_NOTE)


def test_report_survives_a_broken_settings_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("REVERBSCOPE_HOME", str(tmp_path))
    (tmp_path / "settings.json").write_text("{", encoding="utf-8")
    report = environment_report("fake")
    assert "Settings:" in format_environment_report(report)


def test_report_lists_devices_and_probes_on_request() -> None:
    plain = format_environment_report(environment_report("fake"))
    assert "rates not probed" in plain and "[ 0]" in plain
    probed_report = environment_report("fake", probe_rates=True)
    assert probed_report["audio"]["rates_probed"]
    probed = format_environment_report(probed_report)
    assert "record 44100, 48000" in probed and "play 44100, 48000" in probed


def test_report_without_audio_backend_still_prints(monkeypatch: pytest.MonkeyPatch) -> None:
    from reverbscope.audio import backend

    def unavailable(name: str | None = None) -> None:
        raise OSError("PortAudio library not found")

    monkeypatch.setattr(backend, "get_backend", unavailable)
    text = format_environment_report(environment_report())
    assert "unavailable: PortAudio library not found" in text


def test_audio_callbacks_are_checked(monkeypatch: pytest.MonkeyPatch) -> None:
    from reverbscope import diagnostics

    assert diagnostics.audio_callback_check() == "ok"
    assert "Audio callbacks: ok" in format_environment_report(environment_report("fake"))

    class NoExecutableMemory:
        def callback(self, *args: object) -> None:
            raise MemoryError("Cannot allocate write+execute memory for ffi.callback()")

    import _cffi_backend

    monkeypatch.setattr(_cffi_backend, "FFI", NoExecutableMemory)
    assert diagnostics.audio_callback_check().startswith("failed: MemoryError")


def test_cli_doctor_probe(capsys: pytest.CaptureFixture[str]) -> None:
    from reverbscope.cli.main import main

    assert main(["--backend", "fake", "doctor", "--probe"]) == 0
    assert re.search(r"Record\s+44\.1 · 48 · 88\.2", capsys.readouterr().out)
    assert main(["--backend", "fake", "doctor", "--probe", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["audio"]["devices"][0]["input_rates"]


def test_package_versions_fall_back_to_the_module(monkeypatch: pytest.MonkeyPatch) -> None:
    """A PyInstaller bundle has no dist-info; __version__ still names the version."""
    import numpy

    from reverbscope import diagnostics

    def no_metadata(name: str) -> str:
        raise diagnostics.PackageNotFoundError(name)

    monkeypatch.setattr(diagnostics, "version", no_metadata)
    assert diagnostics._package_version("numpy", "numpy") == numpy.__version__
    assert diagnostics._package_version("nothing-here", "not_a_listed_module") is None
