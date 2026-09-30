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


def check_app(app: Path, version: str) -> Path:
    info = plistlib.loads((app / "Contents" / "Info.plist").read_bytes())
    assert info["CFBundleShortVersionString"] == version
    assert info["CFBundleVersion"] == version
    assert info["NSMicrophoneUsageDescription"]
    # The bundled NumPy / SciPy wheels are built for macOS 14 (macosx_14_0).
    assert info["LSMinimumSystemVersion"] == "14.0", info.get("LSMinimumSystemVersion")
    executable = app / "Contents" / "MacOS" / info["CFBundleExecutable"]
    assert executable.is_file(), executable
    # The app is built for the runner's architecture: arm64 on Apple silicon,
    # x86_64 on an Intel runner.
    archs = subprocess.check_output(["lipo", "-archs", str(executable)], text=True)
    assert platform.machine() in archs.split(), (platform.machine(), archs)
    subprocess.run(["codesign", "--verify", "--deep", "--strict", str(app)], check=True)
    return executable


def main() -> None:
    dmg = Path(sys.argv[1]).resolve()
    version = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))["project"][
        "version"
    ]
    subprocess.run(["hdiutil", "verify", str(dmg)], check=True)
    with tempfile.TemporaryDirectory(prefix="roomscope-dmg-") as directory:
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
            app = mount / "RoomScope.app"
            check_app(app, version)
            installed = root / "Applications" / "RoomScope.app"
            installed.parent.mkdir()
            subprocess.run(["ditto", str(app), str(installed)], check=True)
        finally:
            subprocess.run(["hdiutil", "detach", str(mount)], check=True)

        executable = check_app(installed, version)
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
