"""Smoke-test a release bundle or an on-PATH ``reverbscope`` (ARCHITECTURE_V1.md §6.2).

Runs ``--version``, ``doctor --json`` (the report a bug reporter pastes: it
must name every library version, find that PortAudio's cffi callbacks can be
created, and, with ``--expect-commit``, name the commit the bundle was built
from; ``--expect-package`` and ``--expect-machine`` check which edition and
which CPU architecture it is), a fake-backend Standalone measurement, and the
command line a first-time user runs: ``reverbscope demo`` in English and in
Chinese, and ``--format json show`` with nothing but JSON on stdout.

Desktop Edition: then ``gui --smoke`` offscreen, ``gui --smoke`` through the
windowed ``reverbscope-gui`` launcher when the bundle has one (Windows, Linux),
and that launcher started without arguments, as a double-click does,
requiring the GUI to stay open.

Terminal Edition (``--terminal``): ``doctor`` must report no Qt, PySide6 or
matplotlib, and ``reverbscope gui`` must refuse with the Terminal Edition
sentence in English and Chinese (exit code 2) instead of a traceback.

Nothing is sent to a loudspeaker.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from pathlib import Path


def find_binary(root: Path | None, explicit: Path | None) -> Path:
    if explicit is not None:
        return explicit
    if root is not None:
        for name in ("reverbscope", "reverbscope.exe"):
            candidate = root / name
            if candidate.is_file():
                return candidate
        for app in (
            root / "ReverbScope.app" / "Contents" / "MacOS" / "reverbscope",
            root.parent / "ReverbScope.app" / "Contents" / "MacOS" / "reverbscope",
        ):
            if app.is_file():
                return app
    from shutil import which

    found = which("reverbscope")
    if found:
        return Path(found)
    raise SystemExit("reverbscope binary not found; pass --root or --reverbscope")


def smoke_gui_argv(binary: Path) -> list[str]:
    return [str(binary), "gui", "--smoke"]


def find_gui_launcher(binary: Path) -> Path | None:
    """The windowed ``reverbscope-gui`` next to the console binary of a bundle.

    Only a PyInstaller bundle (an ``_internal`` folder beside the binary) has
    one; the ``reverbscope-gui`` script of a pip install opens the GUI without
    reading its arguments, so ``gui --smoke`` would not end.
    """
    if not (binary.parent / "_internal").is_dir():
        return None
    for name in ("reverbscope-gui", "reverbscope-gui.exe"):
        candidate = binary.parent / name
        if candidate.is_file():
            return candidate
    return None


#: A desktop launch (no arguments) must still be running after this long:
#: the GUI's event loop, not a usage message that exits at once.
DESKTOP_LAUNCH_WAIT_S = 6.0


def check_stays_open(
    argv: list[str], env: dict[str, str], *, seconds: float = DESKTOP_LAUNCH_WAIT_S
) -> None:
    """Start ``argv`` like a double-click does and require it to keep running."""
    with subprocess.Popen(argv, env=env) as process:
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise SystemExit(
                    f"desktop launch of {argv[0]} exited at once (code {process.returncode}); "
                    "a launch without arguments must open the GUI"
                )
            time.sleep(0.2)
        process.terminate()
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


#: Libraries only the Desktop Edition ships (``doctor`` package names).
GUI_PACKAGES = frozenset({"matplotlib", "PySide6_Essentials", "shiboken6"})
#: The sentence ``reverbscope gui`` prints in the Terminal Edition.
TERMINAL_GUI_TEXT = {
    "en": "This is the Terminal Edition of ReverbScope. Install the Desktop Edition to use the GUI.",
    "zh_CN": "当前安装的是 ReverbScope 终端版。如需图形界面，请安装桌面版。",
}


def _cli_env(home: Path) -> dict[str, str]:
    """A clean environment: its own ReverbScope home, no colour, UTF-8 pipes."""
    env = os.environ.copy()
    env["REVERBSCOPE_HOME"] = str(home)
    env["NO_COLOR"] = "1"
    env.pop("FORCE_COLOR", None)
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def check_doctor(
    binary: Path,
    expect_commit: str | None = None,
    *,
    terminal: bool = False,
    expect_package: str | None = None,
    expect_machine: str | None = None,
) -> dict[str, object]:
    """``doctor --json`` runs, names NumPy's version and, if given, the build commit.

    In the Terminal Edition the GUI's libraries must be absent, not merely unused.
    """
    done = subprocess.run(
        [str(binary), "--backend", "fake", "doctor", "--json"],
        check=True,
        capture_output=True,
        text=True,
        timeout=120,
    )
    report = json.loads(done.stdout)
    packages = report.get("packages", {})
    if terminal:
        present = sorted(name for name in GUI_PACKAGES if packages.get(name))
        if present:
            raise SystemExit(f"Terminal Edition carries GUI libraries: {', '.join(present)}")
        packages = {k: v for k, v in packages.items() if k not in GUI_PACKAGES}
    missing = [name for name, found in packages.items() if not found]
    if missing or not report.get("packages"):
        # A bundle carries little package metadata; doctor must still name them.
        raise SystemExit(f"doctor reports no version for: {', '.join(missing) or 'any package'}")
    if report.get("audio_callbacks") != "ok":
        # PortAudio's cffi callback could not be created: no recording works.
        raise SystemExit(f"audio callbacks: {report.get('audio_callbacks')}")
    build = report.get("build") or {}
    commit = build.get("commit")
    if expect_commit and commit != expect_commit:
        raise SystemExit(f"doctor reports build commit {commit!r}, expected {expect_commit!r}")
    if expect_package and build.get("package") != expect_package:
        raise SystemExit(
            f"doctor reports package {build.get('package')!r}, expected {expect_package!r}"
        )
    machine = str(report.get("machine", "")).lower()
    if expect_machine and machine not in _MACHINES.get(expect_machine, {expect_machine}):
        raise SystemExit(f"bundle runs as {machine!r}, expected {expect_machine!r}")
    return report


#: ``platform.machine()`` spellings of each release architecture.
_MACHINES = {
    "arm64": {"arm64", "aarch64"},
    "x86_64": {"x86_64", "amd64", "x64"},
}


def check_first_run(binary: Path, work: Path) -> None:
    """What a first-time user runs: the demo in both languages and JSON output."""
    work.mkdir(parents=True, exist_ok=True)
    env = _cli_env(work / "home")
    for lang, marker in (("en", "Synthetic data"), ("zh_CN", "合成数据")):
        folder = work / f"demo-{lang}"
        done = subprocess.run(
            [str(binary), "--lang", lang, "demo", "--out", str(folder)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=env,
            timeout=300,
        )
        if done.returncode != 0 or marker not in done.stdout or "Traceback" in done.stderr:
            raise SystemExit(
                f"reverbscope --lang {lang} demo failed ({done.returncode}):\n"
                f"{done.stdout}\n{done.stderr}"
            )
    done = subprocess.run(
        [str(binary), "--format", "json", "show", str(work / "demo-en" / "position-a")],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        timeout=120,
    )
    if done.returncode != 0:
        raise SystemExit(f"--format json show failed ({done.returncode}): {done.stderr}")
    try:
        json.loads(done.stdout)
    except ValueError as exc:
        raise SystemExit(f"--format json show wrote more than JSON to stdout: {exc}") from exc
    if "\x1b[" in done.stdout:
        raise SystemExit("--format json show wrote escape sequences to stdout")


def check_terminal_gui_refusal(binary: Path, work: Path) -> None:
    """``reverbscope gui`` in the Terminal Edition: a sentence and exit code 2, no traceback."""
    env = _cli_env(work / "home")
    for lang, sentence in TERMINAL_GUI_TEXT.items():
        done = subprocess.run(
            [str(binary), "--lang", lang, "gui"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=env,
            timeout=120,
        )
        # The sentence is wrapped to the terminal width; compare it unwrapped.
        flat = "".join(done.stderr.split()) if lang == "zh_CN" else " ".join(done.stderr.split())
        wanted = "".join(sentence.split()) if lang == "zh_CN" else sentence
        if done.returncode != 2 or wanted not in flat or "Traceback" in done.stderr:
            raise SystemExit(
                f"reverbscope --lang {lang} gui in the Terminal Edition ({done.returncode}):\n"
                f"{done.stderr}"
            )


def smoke(
    binary: Path,
    out: Path,
    *,
    gui: bool = True,
    require_gui_launcher: bool = False,
    expect_commit: str | None = None,
    terminal: bool = False,
    expect_package: str | None = None,
    expect_machine: str | None = None,
    first_run: bool = True,
) -> None:
    version = subprocess.run([str(binary), "--version"], check=True, capture_output=True, text=True)
    if "reverbscope" not in version.stdout.lower() and "reverbscope" not in version.stderr.lower():
        raise SystemExit(f"--version did not name reverbscope: {version.stdout!r}")
    check_doctor(
        binary,
        expect_commit,
        terminal=terminal,
        expect_package=expect_package,
        expect_machine=expect_machine,
    )
    if first_run:
        check_first_run(binary, out.parent / f"{out.name}-first-run")
    if terminal:
        check_terminal_gui_refusal(binary, out.parent / f"{out.name}-first-run")
        gui = False
    subprocess.run(
        [
            str(binary),
            "--backend",
            "fake",
            "measure",
            "--out",
            str(out),
            "--duration",
            "2",
            "--post-silence",
            "1.5",
            "--level",
            "-20",
        ],
        check=True,
    )
    if not (out / "session.json").is_file() and not any(out.rglob("session.json")):
        raise SystemExit(f"fake measure did not write session.json under {out}")
    if gui:
        env = os.environ.copy()
        env.setdefault("QT_QPA_PLATFORM", "offscreen")
        subprocess.run(smoke_gui_argv(binary), check=True, env=env, timeout=120)
        launcher = find_gui_launcher(binary)
        if launcher is None and require_gui_launcher:
            raise SystemExit(f"no reverbscope-gui launcher next to {binary}")
        if launcher is not None:
            subprocess.run(smoke_gui_argv(launcher), check=True, env=env, timeout=120)
            # What Explorer, the Start menu, AppRun and the desktop file do.
            check_stays_open([str(launcher)], env)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, help="bundle directory (dist/reverbscope)")
    parser.add_argument("--reverbscope", type=Path, help="path to the reverbscope binary")
    parser.add_argument("--out", type=Path, help="session output directory")
    parser.add_argument(
        "--no-gui",
        action="store_true",
        help="skip the offscreen GUI smoke (CLI-only binaries)",
    )
    parser.add_argument(
        "--require-gui-launcher",
        action="store_true",
        help="fail when the windowed reverbscope-gui launcher is missing (Windows, Linux)",
    )
    parser.add_argument(
        "--expect-commit",
        help="fail unless reverbscope doctor reports this build commit (release builds)",
    )
    parser.add_argument(
        "--terminal",
        action="store_true",
        help="the Terminal Edition: no GUI libraries, and `gui` must refuse politely",
    )
    parser.add_argument(
        "--expect-package",
        choices=("desktop", "terminal"),
        help="fail unless the bundle's build_info names this edition",
    )
    parser.add_argument(
        "--expect-machine",
        choices=sorted(_MACHINES),
        help="fail unless the bundle runs as this CPU architecture",
    )
    parser.add_argument(
        "--skip-first-run",
        action="store_true",
        help="skip the demo and JSON checks (a second smoke of the same build)",
    )
    args = parser.parse_args(argv)
    binary = find_binary(args.root, args.reverbscope)
    out = args.out or Path("smoke-session")
    out.mkdir(parents=True, exist_ok=True)
    smoke(
        binary,
        out,
        gui=not args.no_gui,
        require_gui_launcher=args.require_gui_launcher,
        expect_commit=args.expect_commit,
        terminal=args.terminal,
        expect_package=args.expect_package,
        expect_machine=args.expect_machine,
        first_run=not args.skip_first_run,
    )
    print(f"smoke ok: {binary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
