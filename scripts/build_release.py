"""Build this platform's release files locally, without GitHub Actions.

Runs the steps of the ``bundle`` job of ``.github/workflows/release.yml`` on
the machine it is started on (except the ones that change that machine, see
below), and writes the same file names into
``dist/``, so a maintainer can build on a Mac (Apple silicon and/or Intel), a
Windows PC and a Linux PC and attach the results to the draft Release by
hand (``docs/RELEASE_PLAN.md`` §3a):

* Desktop Edition: license bundle -> PyInstaller -> ``--strip`` bundle gate
  -> smoke test (CLI, demo, fake-backend measurement, offscreen GUI, windowed
  launcher);
* Terminal Edition: its license bundle -> PyInstaller with
  ``REVERBSCOPE_PACKAGE=terminal`` -> the ``--terminal`` gate (no Qt, PySide6
  or matplotlib) -> smoke test (CLI, demo in English and Chinese, JSON on
  stdout, ``gui`` refused politely);
* Linux: ``ReverbScope-Desktop-Linux-x86_64.tar.gz`` and
  ``ReverbScope-Terminal-Linux-x86_64.tar.gz``;
* Windows: ``ReverbScope-Desktop-Windows-x64.zip``,
  ``ReverbScope-Terminal-Windows-x64.zip`` and, with Inno Setup installed,
  ``ReverbScope-Desktop-Windows-x64-Setup.exe``. The installer is compiled but
  not installed, smoke-tested and uninstalled as the workflow does, because
  that would change this PC; run it by hand (``/VERYSILENT /CURRENTUSER
  /DIR=<folder>``, ``smoke_bundle.py --root <folder>``, ``unins000.exe
  /VERYSILENT``) before publishing a locally built installer;
* macOS: ad-hoc signed ``ReverbScope.app`` in
  ``ReverbScope-Desktop-macOS-<arch>.dmg``, mounted and launched by
  ``check_macos_dmg.py``, and ``ReverbScope-Terminal-macOS-<arch>.tar.gz``;
* ``SHA256SUMS-<OS>-<ARCH>``; with ``--python-dist`` also the wheel and sdist.

Install the pinned runtime first (the script refuses a different one unless
``--allow-unlocked`` is given)::

    python -m pip install -r requirements/bundle.lock
    python -m pip install -e ".[dev,gui]" pyinstaller==6.22.3 build
    python scripts/build_release.py

Nothing is uploaded and nothing is tagged.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import tomllib
from collections.abc import Callable
from dataclasses import dataclass, field
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
#: The Windows Terminal Edition's "open a prompt here" launcher.
TERMINAL_CMD = "ReverbScope Terminal.cmd"
DIST = ROOT / "dist"
PYINSTALLER_VERSION = "6.22.3"
INNO_SETUP_DEFAULT = Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")) / (
    "Inno Setup 6/ISCC.exe"
)


@dataclass(frozen=True)
class Target:
    """The platform a bundle is built for, named as the release workflow names it."""

    system: str  # "Linux", "Windows" or "macOS" (GitHub's RUNNER_OS)
    arch: str  # "X64" or "ARM64" (GitHub's RUNNER_ARCH)
    machine: str  # platform.machine(): "x86_64", "AMD64", "arm64", ...

    @property
    def checksum_name(self) -> str:
        return f"SHA256SUMS-{self.system}-{self.arch}"

    @property
    def archives(self) -> tuple[str, ...]:
        """Desktop Edition file(s), then the Terminal Edition's (release_draft.CHECKSUM_FILES)."""
        if self.system == "Linux":
            return (
                "ReverbScope-Desktop-Linux-x86_64.tar.gz",
                "ReverbScope-Terminal-Linux-x86_64.tar.gz",
            )
        if self.system == "Windows":
            return (
                "ReverbScope-Desktop-Windows-x64-Setup.exe",
                "ReverbScope-Desktop-Windows-x64.zip",
                "ReverbScope-Terminal-Windows-x64.zip",
            )
        return (
            f"ReverbScope-Desktop-macOS-{self.cpu}.dmg",
            f"ReverbScope-Terminal-macOS-{self.cpu}.tar.gz",
        )

    @property
    def cpu(self) -> str:
        """``arm64`` or ``x86_64``: the CPU in the file names and in the smoke test."""
        return "arm64" if self.arch == "ARM64" else "x86_64"


def current_target() -> Target:
    machine = platform.machine()
    arch = "ARM64" if machine.lower() in {"arm64", "aarch64"} else "X64"
    if sys.platform == "darwin":
        return Target("macOS", arch, machine)
    if sys.platform == "win32":
        return Target("Windows", arch, machine)
    return Target("Linux", arch, machine)


@dataclass
class Step:
    name: str
    run: Callable[[], None]
    skipped: str | None = None
    notes: list[str] = field(default_factory=list)


def _run(*argv: str | Path, env: dict[str, str] | None = None) -> None:
    command = [str(part) for part in argv]
    print("  $", " ".join(command), flush=True)
    subprocess.run(command, check=True, cwd=ROOT, env=env)


def _python(*argv: str | Path, env: dict[str, str] | None = None) -> None:
    _run(sys.executable, *argv, env=env)


def project_version() -> str:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return str(data["project"]["version"])


def lock_mismatches(lock: Path) -> list[str]:
    """Installed versions that differ from ``requirements/bundle.lock``."""
    problems: list[str] = []
    for line in lock.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if not line or "==" not in line:
            continue
        name, pinned = (part.strip() for part in line.split("==", 1))
        try:
            installed = version(name)
        except PackageNotFoundError:
            problems.append(f"{name}: not installed (lock pins {pinned})")
            continue
        if installed != pinned:
            problems.append(f"{name}: {installed} installed, lock pins {pinned}")
    try:
        pyinstaller = version("pyinstaller")
    except PackageNotFoundError:
        problems.append(f"pyinstaller: not installed (workflow uses {PYINSTALLER_VERSION})")
    else:
        if pyinstaller != PYINSTALLER_VERSION:
            problems.append(
                f"pyinstaller: {pyinstaller} installed, workflow uses {PYINSTALLER_VERSION}"
            )
    return problems


def find_iscc() -> Path | None:
    found = shutil.which("iscc") or shutil.which("ISCC")
    if found:
        return Path(found)
    return INNO_SETUP_DEFAULT if INNO_SETUP_DEFAULT.is_file() else None


def checksum_lines(paths: list[Path]) -> str:
    return "".join(
        f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n" for path in paths
    )


def plan(target: Target, args: argparse.Namespace, work: Path) -> list[Step]:
    """The build steps for ``target``, in the release workflow's order."""
    licenses = work / "THIRD_PARTY_LICENSES"
    bundle = DIST / "reverbscope"
    app = DIST / "ReverbScope.app"
    offscreen = {**os.environ, "QT_QPA_PLATFORM": "offscreen"}
    steps: list[Step] = []

    def tests() -> None:
        _python("-m", "pytest", "-q", env=offscreen)

    steps.append(Step("Test suite", tests, skipped="--skip-tests" if args.skip_tests else None))

    def python_dist() -> None:
        for old in DIST.glob("reverbscope-*.whl"):
            old.unlink()
        for old in DIST.glob("reverbscope-*.tar.gz"):
            if not old.name.startswith("reverbscope-linux"):
                old.unlink()
        _python("-m", "build", "--outdir", DIST)

    steps.append(
        Step(
            "sdist and wheel",
            python_dist,
            skipped=None if args.python_dist else "pass --python-dist (build them on one machine)",
        )
    )

    def license_bundle() -> None:
        shutil.rmtree(licenses, ignore_errors=True)
        _python("scripts/build_license_bundle.py", "--out", licenses)

    steps.append(Step("License bundle", license_bundle))

    def pyinstaller() -> None:
        shutil.rmtree(bundle, ignore_errors=True)
        shutil.rmtree(app, ignore_errors=True)
        _python("-m", "PyInstaller", "--noconfirm", "--clean", "packaging/reverbscope.spec")

    steps.append(Step("PyInstaller", pyinstaller))

    def gate() -> None:
        shutil.copytree(licenses, bundle / "THIRD_PARTY_LICENSES", dirs_exist_ok=True)
        _python(
            "scripts/check_bundle_contents.py",
            "--root",
            bundle,
            "--strip",
            "--require-licenses",
        )

    steps.append(Step("Copy licenses and remove disallowed modules", gate))

    if target.system == "macOS":

        def mac_app() -> None:
            resources = app / "Contents" / "Resources"
            shutil.copytree(licenses, resources / "THIRD_PARTY_LICENSES", dirs_exist_ok=True)
            _python("scripts/check_bundle_contents.py", "--root", app, "--strip")
            _python("scripts/check_bundle_contents.py", "--root", resources, "--require-licenses")
            # Inside-out ad hoc signature and --deep verification, as in CI.
            _run("sh", "packaging/macos/sign_app.sh", app)

        steps.append(Step("Check macOS .app and its licenses", mac_app))

    def smoke() -> None:
        out = work / "bundle-smoke" / "session"
        extra = [] if target.system == "macOS" else ["--require-gui-launcher"]
        extra += ["--expect-package", "desktop", "--expect-machine", target.cpu]
        _python("scripts/smoke_bundle.py", "--root", bundle, "--out", out, *extra, env=offscreen)
        if target.system == "macOS":
            _run(app / "Contents" / "MacOS" / "ReverbScope", "gui", "--smoke", env=offscreen)

    steps.append(Step("Smoke frozen binary (Desktop Edition)", smoke))

    terminal = DIST / "reverbscope-terminal"
    terminal_licenses = work / "THIRD_PARTY_LICENSES-terminal"

    def terminal_build() -> None:
        shutil.rmtree(terminal, ignore_errors=True)
        shutil.rmtree(terminal_licenses, ignore_errors=True)
        _python("scripts/build_license_bundle.py", "--terminal", "--out", terminal_licenses)
        _python(
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            "--workpath",
            ROOT / "build" / "terminal",
            "packaging/reverbscope.spec",
            env={**os.environ, "REVERBSCOPE_PACKAGE": "terminal"},
        )
        shutil.copytree(terminal_licenses, terminal / "THIRD_PARTY_LICENSES", dirs_exist_ok=True)
        _python(
            "scripts/check_bundle_contents.py",
            "--root",
            terminal,
            "--strip",
            "--require-licenses",
            "--terminal",
        )
        if target.system == "Windows":
            shutil.copy2(ROOT / "packaging" / "windows" / "terminal" / TERMINAL_CMD, terminal)

    steps.append(Step("Terminal Edition (command line only, no Qt)", terminal_build))

    def terminal_smoke() -> None:
        _python(
            "scripts/smoke_bundle.py",
            "--root",
            terminal,
            "--out",
            work / "terminal-smoke" / "session",
            "--terminal",
            "--expect-package",
            "terminal",
            "--expect-machine",
            target.cpu,
        )

    steps.append(Step("Smoke Terminal Edition", terminal_smoke))
    desktop_name, *_rest = target.archives

    if target.system == "Linux":

        def linux_archive() -> None:
            _run("tar", "-C", DIST, "-czf", DIST / desktop_name, "reverbscope")

        steps.append(Step("Linux archive (Desktop Edition)", linux_archive))
    elif target.system == "Windows":

        def windows_zip() -> None:
            shutil.make_archive(str(DIST / "ReverbScope-Desktop-Windows-x64"), "zip", bundle)

        steps.append(Step("Windows zip (Desktop Edition)", windows_zip))
        iscc = find_iscc()

        def windows_installer() -> None:
            assert iscc is not None
            (DIST / "ReverbScope-Desktop-Windows-x64-Setup.exe").unlink(missing_ok=True)
            # Released Inno Setup keeps the Chinese messages unofficial (not installed).
            chinese = subprocess.run(
                [
                    sys.executable,
                    "scripts/inno_chinese_messages.py",
                    *("--iscc", str(iscc), "--out", str(work)),
                ],
                check=True,
                cwd=ROOT,
                capture_output=True,
                text=True,
            ).stdout.strip()
            _run(
                iscc,
                f"/DMyAppVersion={project_version()}",
                f"/DChineseMessages={chinese}",
                "packaging/windows/reverbscope.iss",
            )

        steps.append(
            Step(
                "Windows installer",
                windows_installer,
                skipped=None
                if iscc is not None
                else "Inno Setup 6 not found (https://jrsoftware.org/isinfo.php)",
            )
        )
    else:
        dmg = DIST / desktop_name

        def mac_dmg() -> None:
            _run("bash", "packaging/macos/make_dmg.sh", app, dmg)
            _python("scripts/check_macos_dmg.py", dmg, env=offscreen)

        steps.append(Step("macOS disk image", mac_dmg))

    terminal_archive_name = target.archives[-1]

    def terminal_archive() -> None:
        if target.system == "Windows":
            shutil.make_archive(
                str(DIST / terminal_archive_name.removesuffix(".zip")), "zip", terminal
            )
        else:
            _run("tar", "-C", DIST, "-czf", DIST / terminal_archive_name, "reverbscope-terminal")

    steps.append(Step("Terminal Edition archive", terminal_archive))

    def checksums() -> None:
        assets = [DIST / name for name in target.archives if (DIST / name).is_file()]
        if not assets:
            raise SystemExit("no distributable archive was produced")
        missing = [name for name in target.archives if not (DIST / name).is_file()]
        if missing and not (args.no_installer and missing == [target.archives[0]]):
            raise SystemExit(f"missing release files: {', '.join(missing)}")
        (DIST / target.checksum_name).write_text(checksum_lines(assets), encoding="utf-8")

    steps.append(Step("Checksums of distributable files", checksums))
    return steps


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--skip-tests", action="store_true", help="do not run pytest first")
    parser.add_argument(
        "--python-dist", action="store_true", help="also build the wheel and the sdist"
    )
    parser.add_argument(
        "--allow-unlocked",
        action="store_true",
        help="build with packages that differ from requirements/bundle.lock",
    )
    parser.add_argument(
        "--no-installer",
        action="store_true",
        help="Windows: ship only the zip when Inno Setup is missing (the workflow requires it)",
    )
    args = parser.parse_args(argv)

    target = current_target()
    if target.system != "macOS" and target.arch != "X64":
        # The release ships x86_64 Linux and x64 Windows only (README); an ARM
        # build would carry an x86_64 file name.
        print(f"{target.system} {target.arch} is not a release platform; nothing was built")
        return 2
    release_version = project_version()
    print(f"ReverbScope {release_version}: building for {target.system} {target.arch}")
    if "dev" in release_version:
        print("  note: a .dev version never gets a draft Release")

    problems = lock_mismatches(ROOT / "requirements" / "bundle.lock")
    if problems:
        print("installed packages differ from requirements/bundle.lock:")
        for problem in problems:
            print(f"  - {problem}")
        if not args.allow_unlocked:
            print("install the lock (see this script's docstring) or pass --allow-unlocked")
            return 2

    DIST.mkdir(exist_ok=True)
    # Files of an earlier build must not be checksummed or listed as this one.
    for name in (*target.archives, target.checksum_name):
        (DIST / name).unlink(missing_ok=True)
    with tempfile.TemporaryDirectory(prefix="reverbscope-release-") as directory:
        steps = plan(target, args, Path(directory))
        for index, step in enumerate(steps, 1):
            if step.skipped:
                print(f"[{index}/{len(steps)}] {step.name}: skipped ({step.skipped})")
                if step.name == "Windows installer" and not args.no_installer:
                    print("install Inno Setup 6 or pass --no-installer")
                    return 1
                continue
            print(f"[{index}/{len(steps)}] {step.name}", flush=True)
            step.run()

    produced = [DIST / name for name in (*target.archives, target.checksum_name)]
    if args.python_dist:
        produced += sorted(DIST.glob(f"reverbscope-{release_version}-*.whl"))
        produced.append(DIST / f"reverbscope-{release_version}.tar.gz")
    print("\nFiles for the draft Release (upload with the web page or `gh release upload`):")
    for path in produced:
        if path.is_file():
            print(f"  {path.relative_to(ROOT)}  ({path.stat().st_size / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
