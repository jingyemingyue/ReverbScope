"""Screenshots of the focused desktop, offscreen, from the synthetic demo.

    QT_QPA_PLATFORM=offscreen python scripts/render_gui2_screenshots.py [--out docs/images/gui2]

Writes ``<lang>_<width>x<height>_<scheme>_<view>.png`` for the views and
sizes below, in Simplified Chinese by default (``--lang en`` for English).
The demo's two positions are opened as a project, position A is the
baseline and drawn under position B, the first early reflection of B is
selected and the example room is entered, so every view has something to
show. ``--scale 2`` renders at a device pixel ratio of 2 (a high-DPI check;
it is not a Retina display). No audio hardware is used; the data is a
simulated room, not a measurement.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

#: (width, height, scheme, views): what the pull request and the docs show.
_VIEWS = (
    "empty",
    "start",
    "overview",
    "fr",
    "etc",
    "decay",
    "noise",
    "spectrogram",
    "waterfall",
    "room",
    "compare",
    "project",
    "report",
    "measure_connection",
    "measure_signal",
    "measure_review",
    "daw_signal",
    "daw_record",
    "daw_import",
    "daw_analyze",
    "settings",
)
SHOTS: tuple[tuple[int, int, str, tuple[str, ...]], ...] = tuple(
    (width, height, scheme, _VIEWS)
    for width, height in ((960, 640), (1280, 800), (1366, 768), (1920, 1080))
    for scheme in ("dark", "light")
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=Path("docs/images/gui2"))
    parser.add_argument("--lang", default="zh_CN")
    parser.add_argument("--scale", type=float, default=1.0, help="device pixel ratio")
    parser.add_argument("--width", type=int, default=0, help="render only this width")
    parser.add_argument("--height", type=int, default=0, help="render only this height")
    parser.add_argument("--scheme", default="", help="render only light or dark")
    parser.add_argument(
        "--view",
        action="append",
        default=[],
        help="render only these views (repeatable); default is every view",
    )
    parser.add_argument(
        "--cameras",
        action="store_true",
        help="also save the room view from the plan, front, side and default perspective",
    )
    parser.add_argument(
        "--panels", action="store_true", help="also capture optional drawers and display settings"
    )
    args = parser.parse_args(argv)
    if args.scale != 1.0:
        os.environ["QT_SCALE_FACTOR"] = str(args.scale)
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ["REVERBSCOPE_AUDIO_BACKEND"] = "fake"
    os.environ["REVERBSCOPE_EDITION"] = "user"
    work = Path(tempfile.mkdtemp(prefix="reverbscope-gui2-"))
    os.environ["REVERBSCOPE_HOME"] = str(work / "home")
    out: Path = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    try:
        for width, height, scheme, views in SHOTS:
            if args.width and width != args.width:
                continue
            if args.height and height != args.height:
                continue
            if args.scheme and scheme != args.scheme:
                continue
            chosen = tuple(view for view in views if view in args.view) if args.view else views
            _render(
                work,
                out,
                args.lang,
                width,
                height,
                scheme,
                chosen,
                args.scale,
                cameras=args.cameras,
                panels=args.panels,
            )
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return 0


def _room_cameras(
    window: Any,
    out: Path,
    lang: str,
    width: int,
    height: int,
    scheme: str,
    suffix: str,
    pump: Callable[[float], None],
) -> None:
    """Plan, front, side and the default perspective, after the default shot."""
    room = window.views["room"]
    canvas = room.canvas
    print(f"canvas {canvas.width()}x{canvas.height()}", flush=True)
    for label, preset in (
        ("perspective", ""),
        ("plan", "top"),
        ("front", "front"),
        ("side", "side"),
    ):
        if preset == "":
            room.reset_view()
            canvas.fit()
        elif preset == "top":
            room.plan_button.setChecked(True)
        else:
            room.look(preset)
        pump(0.15)
        path = out / f"{lang}_{width}x{height}_{scheme}_room_{label}{suffix}.png"
        window.grab().save(str(path))
        print(path, flush=True)
    room.reset_view()
    canvas.fit()


def _render(
    work: Path,
    out: Path,
    lang: str,
    width: int,
    height: int,
    scheme: str,
    views: tuple[str, ...],
    scale: float,
    *,
    cameras: bool = False,
    panels: bool = False,
) -> None:
    os.environ["REVERBSCOPE_COLOR_SCHEME"] = scheme
    from PySide6.QtWidgets import QApplication

    from reverbscope.demo import DEMO_ROOM_NAME, run_demo
    from reverbscope.i18n import _, activate
    from reverbscope.io.project_store import add_session, save_project
    from reverbscope.models.project import Project
    from reverbscope.ui.main_window import MainWindow
    from reverbscope.ui.settings_dialog import SettingsDialog
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

    def pump(seconds: float) -> None:
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            app.processEvents()
            time.sleep(0.01)

    window = MainWindow()
    window.resize(width, height)
    window.show()
    pump(0.3)
    # The first scheme saves the example room into the demo folder. The next
    # scheme would ask before replacing it, and an offscreen run cannot click
    # that dialog. Drop the file so every scheme starts from an empty room.
    saved_room = demo / "room-geometry.json"
    if saved_room.is_file():
        saved_room.unlink()
    suffix = "" if scale == 1.0 else f"@{scale:g}x"
    if "empty" in views:
        window.grab().save(str(out / f"{lang}_{width}x{height}_{scheme}_empty{suffix}.png"))
    window.show_project(demo)
    window.model.wait_until_loaded()
    keys = [entry.key for entry in window.model.entries() if entry.result is not None]
    window.model.set_baseline(keys[0])
    window.model.set_current(keys[-1])
    # Visibility is independent of selection: draw the baseline and the current one.
    window.model.set_overlay(keys[0], True)
    window.model.set_overlay(keys[-1], True)
    current = window.model.current()
    if (
        current is not None
        and current.result is not None
        and current.result.reflections.reflections
    ):
        window.model.select_reflection(current.key, 0)
    window.views["room"].use_example()
    for view in views:
        if view == "empty":
            continue
        if view == "start":
            window._show_start()
            pump(0.4)
        elif view.startswith("measure_"):
            window.show_mode("standalone")
            window.standalone.flow.set_step(
                ("measure_connection", "measure_signal", "measure_review").index(view)
            )
            pump(0.2)
        elif view.startswith("daw_"):
            window.show_mode("universal_daw")
            window.daw.flow.set_step(
                ("daw_signal", "daw_record", "daw_import", "daw_analyze").index(view)
            )
            pump(0.2)
        elif view != "settings":
            window.show_view(view)
            pump(2.5 if view in ("spectrogram", "waterfall") else 0.3)
            worker = getattr(window.views[view], "_worker", None)
            if worker is not None:
                if not worker.wait(15_000):
                    raise RuntimeError(f"{view} did not finish rendering")
                pump(0.2)
        name = f"{lang}_{width}x{height}_{scheme}_{view}{suffix}.png"
        if view == "settings":
            dialog = SettingsDialog(window)
            dialog.show()
            pump(0.2)
            saved = dialog.grab().save(str(out / name))
            dialog.close()
            dialog.deleteLater()
        else:
            saved = window.grab().save(str(out / name))
        if not saved:
            raise OSError(f"cannot save {out / name}")
        print(out / name, flush=True)
        if panels and view in ("fr", "room", "spectrogram"):
            if view == "fr":
                for panel_name, open_panel in (
                    ("measurements", window.set_navigator_open),
                    ("properties", window.set_inspector_open),
                ):
                    open_panel(True)
                    pump(0.1)
                    window.grab().save(str(out / name.replace(".png", f"_{panel_name}.png")))
                    open_panel(False)
            elif view == "room":
                window.views["room"].parameters_button.setChecked(True)
                pump(0.1)
                window.grab().save(str(out / name.replace(".png", "_parameters.png")))
                window.views["room"].parameters_button.setChecked(False)
            else:
                window.views["spectrogram"].display_settings.set_open(True)
                pump(0.1)
                window.grab().save(str(out / name.replace(".png", "_settings.png")))
                window.views["spectrogram"].display_settings.set_open(False)
        if view == "room" and cameras:
            _room_cameras(window, out, lang, width, height, scheme, suffix, pump)
    window.views["room"].load(None)  # leave the demo's folder as the demo wrote it
    window.close()
    pump(0.2)


if __name__ == "__main__":
    raise SystemExit(main())
