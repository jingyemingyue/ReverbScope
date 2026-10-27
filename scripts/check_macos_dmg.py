"""Inspect and smoke-test the installed app from the finished macOS disk image."""

from __future__ import annotations

import json
import os
import platform
import plistlib
import subprocess
import sys
import tempfile
import time
import tomllib
from pathlib import Path


def check_localizations(app: Path, info: dict) -> None:
    """The bundle declares Simplified Chinese, so AppKit's own panels and menu
    items follow a Chinese Mac, and the microphone prompt explains itself in
    Chinese (packaging/macos/zh-Hans.lproj)."""
    declared = info.get("CFBundleLocalizations") or []
    assert {"en", "zh-Hans"} <= set(declared), declared
    for language in declared:
        if language == info.get("CFBundleDevelopmentRegion"):
            continue
        strings = app / "Contents" / "Resources" / f"{language}.lproj" / "InfoPlist.strings"
        assert strings.is_file(), strings
        purpose = plistlib.loads(strings.read_bytes())["NSMicrophoneUsageDescription"]
        assert purpose and purpose != info["NSMicrophoneUsageDescription"], (language, purpose)


def check_bundle_identity(info: dict, version: str) -> None:
    """Stable identity keys the Finder, TCC and updates rely on."""
    assert info["CFBundleShortVersionString"] == version
    assert info["CFBundleVersion"] == version
    assert info["CFBundleIdentifier"] == "org.reverbscope.ReverbScope", info.get(
        "CFBundleIdentifier"
    )
    assert info["CFBundleExecutable"] == "ReverbScope", info.get("CFBundleExecutable")
    assert info["CFBundleName"] == "ReverbScope", info.get("CFBundleName")
    assert info["CFBundlePackageType"] == "APPL", info.get("CFBundlePackageType")
    assert info.get("NSHighResolutionCapable") is True, info.get("NSHighResolutionCapable")
    assert info["NSMicrophoneUsageDescription"]
    # The bundled NumPy / SciPy wheels are built for macOS 14 (macosx_14_0).
    assert info["LSMinimumSystemVersion"] == "14.0", info.get("LSMinimumSystemVersion")


def check_dmg_arch_name(dmg: Path, archs: str) -> None:
    """Release DMG names carry the CPU (``…-macOS-arm64.dmg`` / ``…-x86_64.dmg``).

    A mismatch means an Apple Silicon build was labelled Intel (or the reverse)
    and would be offered to the wrong Macs on the Releases page.
    """
    name = dmg.name
    if "-macOS-" not in name:
        return
    listed = set(archs.split())
    if "arm64" in name and "arm64" not in listed:
        raise AssertionError(f"DMG name {name!r} says arm64 but lipo reports {archs!r}")
    if "x86_64" in name and "x86_64" not in listed:
        raise AssertionError(f"DMG name {name!r} says x86_64 but lipo reports {archs!r}")


def check_app(app: Path, version: str, *, dmg: Path | None = None) -> Path:
    info = plistlib.loads((app / "Contents" / "Info.plist").read_bytes())
    check_bundle_identity(info, version)
    check_localizations(app, info)
    executable = app / "Contents" / "MacOS" / info["CFBundleExecutable"]
    assert executable.is_file(), executable
    # The app is built for the runner's architecture: arm64 on Apple silicon,
    # x86_64 on an Intel runner.
    archs = subprocess.check_output(["lipo", "-archs", str(executable)], text=True).strip()
    assert platform.machine() in archs.split(), (platform.machine(), archs)
    if dmg is not None:
        check_dmg_arch_name(dmg, archs)
    subprocess.run(["codesign", "--verify", "--deep", "--strict", str(app)], check=True)
    return executable


def main() -> None:
    dmg = Path(sys.argv[1]).resolve()
    version = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))["project"][
        "version"
    ]
    subprocess.run(["hdiutil", "verify", str(dmg)], check=True)
    with tempfile.TemporaryDirectory(prefix="reverbscope-dmg-") as directory:
        root = Path(directory)
        mount = root / "mounted"
        mount.mkdir()
        subprocess.run(
            ["hdiutil", "attach", "-readonly", "-nobrowse", "-mountpoint", str(mount), str(dmg)],
            check=True,
        )
        try:
            assert (mount / "Applications").is_symlink()
            assert os.readlink(mount / "Applications") == "/Applications"
            app = mount / "ReverbScope.app"
            check_app(app, version, dmg=dmg)
            installed = root / "Applications" / "ReverbScope.app"
            installed.parent.mkdir()
            subprocess.run(["ditto", str(app), str(installed)], check=True)
        finally:
            subprocess.run(["hdiutil", "detach", str(mount)], check=True)

        executable = check_app(installed, version, dmg=dmg)
        env = os.environ.copy()
        env["QT_QPA_PLATFORM"] = "offscreen"
        # The report a bug reporter pastes, from the copied app: library
        # versions and (in CI) the commit the app was built from.
        doctor = subprocess.run(
            [str(executable), "--backend", "fake", "doctor", "--json"],
            check=True,
            capture_output=True,
            text=True,
            env=env,
            timeout=120,
        )
        report = json.loads(doctor.stdout)
        assert all(report["packages"].values()), report["packages"]
        assert report["audio_callbacks"] == "ok", report["audio_callbacks"]
        if os.environ.get("GITHUB_SHA"):
            assert (report["build"] or {}).get("commit") == os.environ["GITHUB_SHA"], report[
                "build"
            ]
        subprocess.run([str(executable), "gui", "--smoke"], check=True, env=env, timeout=120)
        with subprocess.Popen([str(executable)], env=env) as process:
            time.sleep(6)
            if process.poll() is not None:
                raise RuntimeError(f"Finder-style launch exited immediately: {process.returncode}")
            process.terminate()
            process.wait(timeout=15)
    print(f"mounted DMG, copied app, GUI startup and signature verified: {dmg}")


if __name__ == "__main__":
    main()
