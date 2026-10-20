"""Screenshots of the light sidebar GUI, offscreen, for docs/design/light-sidebar.

    QT_QPA_PLATFORM=offscreen python scripts/render_gui_light_sidebar.py \
        [--out docs/images/gui-light-sidebar] [--lang zh_CN] [--scheme light] \
        [--size 1280x800] [--view start ...] [--optimize]

Writes ``<lang>_<scheme>_<width>x<height>_<view>.png``. The audio backend is
a stub that lists a laptop's speakers (the system default), its microphone
and a two-channel interface, so the Standalone page shows the real
no-output state: nothing preselected, Start off and the reason beside it.
``standalone-ready`` picks the interface output afterwards. The analysis
views open the synthetic demo's two positions as a project (A as baseline,
drawn under B, the first early reflection of B selected). No audio is
played or recorded; the data is a simulated room, not a measurement, and an
offscreen render is not a hardware test.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

#: (width, height, scheme, views): what the pull request and the docs show.
_ALL = (
    "start",
    "standalone",
    "standalone-ready",
    "daw",
    "overview",
    "fr",
    "etc",
    "decay",
    "spectrogram",
    "waterfall",
    "compare",
    "project",
)
_KEY = ("start", "standalone", "overview", "fr")
SHOTS: tuple[tuple[int, int, str, tuple[str, ...]], ...] = (
    (1280, 800, "light", _ALL),
    (960, 640, "light", _KEY),
    (1280, 800, "dark", _KEY),
    (960, 640, "dark", _KEY),
)
LANGUAGES = ("zh_CN", "en")


class _StubInterface:
    """A laptop with its speakers (the system default) and an interface."""

    name = "stub"

    def list_devices(self) -> list[Any]:
        from reverbscope.audio.backend import DeviceInfo

        return [
            DeviceInfo(0, "MacBook Pro Speakers", "Core Audio", 0, 2, 48000.0, False, True),
            DeviceInfo(1, "MacBook Pro Microphone", "Core Audio", 1, 0, 48000.0, True, False),
            DeviceInfo(2, "Studio Interface 2x2", "Core Audio", 2, 2, 48000.0, False, False),
        ]

    def check_sample_rate(self, *_args: object, **_kwargs: object) -> None:
        return None


def _install_stub() -> None:
    from reverbscope.audio import backend as backend_module
    from reverbscope.audio import inventory as inventory_module

    real_build = inventory_module.build_inventory
    backend_module.get_backend = lambda *_args, **_kwargs: _StubInterface()  # type: ignore[assignment]
    inventory_module.build_inventory = (  # type: ignore[assignment]
        lambda backend, **_kwargs: real_build(backend, probe_rates=False, platform="darwin")
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--out", type=Path, default=Path("docs/images/gui-light-sidebar"))
    parser.add_argument("--lang", action="append", default=[], help="zh_CN or en (repeatable)")
    parser.add_argument("--scheme", default="", help="render only light or dark")
    parser.add_argument("--size", default="", help="render only this size, e.g. 960x640")
    parser.add_argument("--view", action="append", default=[], help="render only these views")
    parser.add_argument("--optimize", action="store_true", help="run optipng on the output")
    args = parser.parse_args(argv)
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ.pop("REVERBSCOPE_AUDIO_BACKEND", None)
    os.environ["REVERBSCOPE_EDITION"] = "user"
    work = Path(tempfile.mkdtemp(prefix="reverbscope-light-"))
    os.environ["REVERBSCOPE_HOME"] = str(work / "home")
    out: Path = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    _install_stub()
    written: list[Path] = []
    try:
        for lang in args.lang or LANGUAGES:
            for width, height, scheme, views in SHOTS:
                if args.scheme and scheme != args.scheme:
                    continue
                if args.size and f"{width}x{height}" != args.size:
                    continue
                chosen = tuple(v for v in views if v in args.view) if args.view else views
                if chosen:
                    written += _render(work, out, lang, width, height, scheme, chosen)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    if args.optimize and written and shutil.which("optipng"):
        subprocess.run(["optipng", "-quiet", "-o2", *map(str, written)], check=True)
    return 0


def _render(
    work: Path,
    out: Path,
    lang: str,
    width: int,
    height: int,
    scheme: str,
    views: tuple[str, ...],
) -> list[Path]:
    os.environ["REVERBSCOPE_COLOR_SCHEME"] = scheme
    from PySide6.QtWidgets import QApplication

    from reverbscope.demo import DEMO_ROOM_NAME, run_demo
    from reverbscope.i18n import _, activate
    from reverbscope.io.project_store import add_session, save_project
    from reverbscope.io.recent import remember_session
    from reverbscope.models.project import Project
    from reverbscope.ui.main_window import MainWindow
    from reverbscope.ui.theme import apply_application_chrome

    activate(lang)
    app = QApplication.instance() or QApplication(sys.argv[:1])
    apply_application_chrome(app)  # type: ignore[arg-type]
    demo = work / f"demo-{lang}"
    if not demo.exists():
        run_demo(demo)
        save_project(demo, Project(name=_(DEMO_ROOM_NAME)))
        for label in ("A", "B"):  # named as the Project view suggests
            (demo / f"position-{label.lower()}").rename(demo / f"{label}-1")
            add_session(demo, demo / f"{label}-1", position=label)
            remember_session(demo / f"{label}-1")

    def pump(seconds: float) -> None:
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            app.processEvents()
            time.sleep(0.01)

    written: list[Path] = []

    def save(view: str) -> None:
        path = out / f"{lang}_{scheme}_{width}x{height}_{view}.png"
        window.grab().save(str(path))
        written.append(path)
        print(path)

    window = MainWindow()
    window.resize(width, height)
    window.show()
    pump(0.4)
    for view in ("start", "standalone", "standalone-ready", "daw"):
        if view not in views:
            continue
        if view == "start":
            window.show_home()
        elif view == "daw":
            window.show_mode("universal_daw")
        else:
            window.show_mode("standalone")
            page = window.standalone
            if view == "standalone-ready":
                page.output_device.setCurrentIndex(page.output_device.findData(2))
            else:
                page.output_device.setCurrentIndex(page.output_device.findData(None))
        pump(0.4)
        save(view)
    analysis = [v for v in views if v not in ("start", "standalone", "standalone-ready", "daw")]
    if analysis:
        window.show_project(demo)
        window.model.wait_until_loaded()
        keys = [entry.key for entry in window.model.entries() if entry.result is not None]
        window.model.set_baseline(keys[0])
        window.model.set_current(keys[-1])
        window.model.set_overlay(keys[0], True)
        window.model.set_overlay(keys[-1], True)
        current = window.model.current()
        if (
            current is not None
            and current.result is not None
            and current.result.reflections.reflections
        ):
            window.model.select_reflection(current.key, 0)
        for view in analysis:
            window.show_view(view)
            pump(2.5 if view in ("spectrogram", "waterfall") else 0.7)
            save(view)
    window.close()
    pump(0.2)
    return written


if __name__ == "__main__":
    raise SystemExit(main())
