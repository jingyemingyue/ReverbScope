"""Smoke-test a release bundle or an on-PATH ``roomscope`` (ARCHITECTURE_V1.md §6.2).

Runs ``--version``, ``doctor --json`` (the report a bug reporter pastes: it
must name every library version, find that PortAudio's cffi callbacks can be
created, and, with ``--expect-commit``, name the commit the bundle was built
from; ``--expect-package`` and ``--expect-machine`` check which edition and
which CPU architecture it is), a fake-backend Standalone measurement, and the
command line a first-time user runs: ``roomscope demo`` in English and in
Chinese, and ``--format json show`` with nothing but JSON on stdout.

Desktop Edition: then ``gui --smoke`` offscreen, ``gui --smoke`` through the
windowed ``roomscope-gui`` launcher when the bundle has one (Windows, Linux),
and that launcher started without arguments, as a double-click does,
requiring the GUI to stay open.

Terminal Edition (``--terminal``): ``doctor`` must report no Qt, PySide6 or
matplotlib, and ``roomscope gui`` must refuse with the Terminal Edition
sentence in English and Chinese (exit code 2) instead of a traceback.

Nothing is sent to a loudspeaker.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path
from typing import NoReturn


def find_binary(root: Path | None, explicit: Path | None) -> Path:
    if explicit is not None:
        return explicit
    if root is not None:
        for name in ("roomscope", "roomscope.exe"):
            candidate = root / name
            if candidate.is_file():
                return candidate
        for app in (
            root / "RoomScope.app" / "Contents" / "MacOS" / "roomscope",
            root.parent / "RoomScope.app" / "Contents" / "MacOS" / "roomscope",
        ):
            if app.is_file():
                return app
    from shutil import which

    found = which("roomscope")
    if found:
        return Path(found)
    raise SystemExit("roomscope binary not found; pass --root or --roomscope")


def smoke_gui_argv(binary: Path) -> list[str]:
    return [str(binary), "gui", "--smoke"]


def find_gui_launcher(binary: Path) -> Path | None:
    """The windowed ``roomscope-gui`` next to the console binary of a bundle.

    Only a PyInstaller bundle (an ``_internal`` folder beside the binary) has
    one; the ``roomscope-gui`` script of a pip install opens the GUI without
    reading its arguments, so ``gui --smoke`` would not end.
    """
    if not (binary.parent / "_internal").is_dir():
        return None
    for name in ("roomscope-gui", "roomscope-gui.exe"):
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
#: Optional Qt packages in a source/wheel CLI-only install; matplotlib is runtime.
OPTIONAL_QT_PACKAGES = GUI_PACKAGES - {"matplotlib"}
#: The sentence ``roomscope gui`` prints in the Terminal Edition.
TERMINAL_GUI_TEXT = {
    "en": "This is the Terminal Edition of RoomScope. Install the Desktop Edition to use the GUI.",
    "zh_CN": "当前安装的是 RoomScope 终端版。如需图形界面，请安装桌面版。",
}


def _cli_env(home: Path) -> dict[str, str]:
    """A clean environment: its own RoomScope home, no colour, UTF-8 pipes."""
    env = os.environ.copy()
    env["ROOMSCOPE_HOME"] = str(home)
    env["NO_COLOR"] = "1"
    env.pop("FORCE_COLOR", None)
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def _fail_command(
    argv: list[str],
    reason: str,
    stdout: str | bytes | None = None,
    stderr: str | bytes | None = None,
) -> NoReturn:
    """Keep the failed command and its captured output in the CI log."""
    lines = [reason, f"command: {shlex.join(argv)}"]
    for label, output in (("stdout", stdout), ("stderr", stderr)):
        if isinstance(output, bytes):
            output = output.decode("utf-8", errors="replace")
        if output:
            lines.append(f"{label}:\n{output.rstrip()}")
    raise SystemExit("\n".join(lines))


def _run_command(
    argv: list[str],
    *,
    env: dict[str, str] | None = None,
    timeout: float = 120,
    expected_code: int = 0,
) -> subprocess.CompletedProcess[str]:
    """Run a bounded smoke step; failures are actionable instead of tracebacks."""
    try:
        done = subprocess.run(
            argv, capture_output=True, text=True, encoding="utf-8", env=env, timeout=timeout
        )
    except subprocess.TimeoutExpired as exc:
        _fail_command(argv, f"command timed out after {timeout:g} s", exc.stdout, exc.stderr)
    except OSError as exc:
        _fail_command(argv, f"cannot start command: {exc}")
    if done.returncode != expected_code:
        _fail_command(
            argv,
            f"command failed (exit {done.returncode}, expected {expected_code})",
            done.stdout,
            done.stderr,
        )
    return done


def _json_object(done: subprocess.CompletedProcess[str], step: str) -> dict[str, object]:
    try:
        value = json.loads(done.stdout)
    except ValueError as exc:
        _fail_command(done.args, f"{step} wrote invalid JSON: {exc}", done.stdout, done.stderr)
    if not isinstance(value, dict):
        _fail_command(done.args, f"{step} must write a JSON object", done.stdout, done.stderr)
    return value


def check_doctor(
    binary: Path,
    expect_commit: str | None = None,
    *,
    terminal: bool = False,
    expect_package: str | None = None,
    expect_machine: str | None = None,
    env: dict[str, str] | None = None,
    require_gui: bool = True,
) -> dict[str, object]:
    """``doctor --json`` runs, names NumPy's version and, if given, the build commit.

    In the Terminal Edition the GUI's libraries must be absent, not merely unused.
    """
    done = _run_command(
        [str(binary), "--backend", "fake", "doctor", "--json"],
        env=env,
    )
    report = _json_object(done, "doctor")
    packages = report.get("packages", {})
    if not isinstance(packages, dict) or not packages:
        raise SystemExit(
            "doctor reports no version for any package: packages must be a non-empty object"
        )
    if terminal:
        present = sorted(name for name in GUI_PACKAGES if packages.get(name))
        if present:
            raise SystemExit(f"Terminal Edition carries GUI libraries: {', '.join(present)}")
        packages = {k: v for k, v in packages.items() if k not in GUI_PACKAGES}
    elif not require_gui:
        packages = {
            k: v for k, v in packages.items() if k not in OPTIONAL_QT_PACKAGES or v is not None
        }
    missing = [name for name, found in packages.items() if not isinstance(found, str) or not found]
    if missing:
        # A bundle carries little package metadata; doctor must still name them.
        raise SystemExit(f"doctor reports no version for: {', '.join(missing) or 'any package'}")
    if report.get("audio_callbacks") != "ok":
        # PortAudio's cffi callback could not be created: no recording works.
        raise SystemExit(f"audio callbacks: {report.get('audio_callbacks')}")
    build = report.get("build")
    if build is None:
        build = {}
    if not isinstance(build, dict):
        raise SystemExit("doctor reports invalid build metadata: expected a JSON object or null")
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
        done = _run_command(
            [str(binary), "--lang", lang, "demo", "--out", str(folder)],
            env=env,
            timeout=300,
        )
        if marker not in done.stdout or "Traceback" in done.stderr:
            raise SystemExit(
                f"roomscope --lang {lang} demo failed ({done.returncode}):\n"
                f"{done.stdout}\n{done.stderr}"
            )
    done = _run_command(
        [str(binary), "--format", "json", "show", str(work / "demo-en" / "position-a")],
        env=env,
    )
    _json_object(done, "--format json show")
    if "\x1b[" in done.stdout:
        raise SystemExit("--format json show wrote escape sequences to stdout")


def check_terminal_gui_refusal(binary: Path, work: Path) -> None:
    """``roomscope gui`` in the Terminal Edition: a sentence and exit code 2, no traceback."""
    env = _cli_env(work / "home")
    for lang, sentence in TERMINAL_GUI_TEXT.items():
        done = _run_command(
            [str(binary), "--lang", lang, "gui"],
            env=env,
            expected_code=2,
        )
        # The sentence is wrapped to the terminal width; compare it unwrapped.
        flat = "".join(done.stderr.split()) if lang == "zh_CN" else " ".join(done.stderr.split())
        wanted = "".join(sentence.split()) if lang == "zh_CN" else sentence
        if wanted not in flat or "Traceback" in done.stderr:
            raise SystemExit(
                f"roomscope --lang {lang} gui in the Terminal Edition ({done.returncode}):\n"
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
    env = _cli_env(out.parent / f"{out.name}-home")
    version = _run_command([str(binary), "--version"], env=env)
    if "roomscope" not in version.stdout.lower() and "roomscope" not in version.stderr.lower():
        raise SystemExit(f"--version did not name roomscope: {version.stdout!r}")
    check_doctor(
        binary,
        expect_commit,
        terminal=terminal,
        expect_package=expect_package,
        expect_machine=expect_machine,
        env=env,
        require_gui=gui,
    )
    if first_run:
        check_first_run(binary, out.parent / f"{out.name}-first-run")
    if terminal:
        check_terminal_gui_refusal(binary, out.parent / f"{out.name}-first-run")
        gui = False
    measured = _run_command(
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
        env=env,
    )
    print(measured.stdout, end="")
    if measured.stderr:
        print(measured.stderr, end="", file=sys.stderr)
    if not (out / "session.json").is_file() and not any(out.rglob("session.json")):
        raise SystemExit(f"fake measure did not write session.json under {out}")
    if gui:
        env.setdefault("QT_QPA_PLATFORM", "offscreen")
        _run_command(smoke_gui_argv(binary), env=env)
        launcher = find_gui_launcher(binary)
        if launcher is None and require_gui_launcher:
            raise SystemExit(f"no roomscope-gui launcher next to {binary}")
        if launcher is not None:
            _run_command(smoke_gui_argv(launcher), env=env)
            # What Explorer, the Start menu, AppRun and the desktop file do.
            check_stays_open([str(launcher)], env)


def main(argv: list[str] | None = None) -> int:
    # Child pipes are UTF-8; redirected Windows logs may otherwise use cp1252.
    # Configure both streams before argparse or a SystemExit can write a failure.
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="backslashreplace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, help="bundle directory (dist/roomscope)")
    parser.add_argument("--roomscope", type=Path, help="path to the roomscope binary")
    parser.add_argument("--out", type=Path, help="session output directory")
    parser.add_argument(
        "--no-gui",
        action="store_true",
        help="skip the offscreen GUI smoke (CLI-only binaries)",
    )
    parser.add_argument(
        "--require-gui-launcher",
        action="store_true",
        help="fail when the windowed roomscope-gui launcher is missing (Windows, Linux)",
    )
    parser.add_argument(
        "--expect-commit",
        help="fail unless roomscope doctor reports this build commit (release builds)",
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
    binary = find_binary(args.root, args.roomscope)
    out = args.out or Path("smoke-session")
    try:
        out.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise SystemExit(f"cannot create smoke output directory {out}: {exc}") from exc
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
