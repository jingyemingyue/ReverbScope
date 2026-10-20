"""Before/after screenshots of the dark desktop, offscreen, from the synthetic demo.

    QT_QPA_PLATFORM=offscreen python scripts/render_gui_polish_screenshots.py \
        --out docs/images/gui-polish-dark/after --lang zh_CN --size 1280x800

Writes ``<lang>_<width>x<height>_<view>.png`` in the dark scheme. The demo's
two positions are opened as a project, position A is the baseline and both
are drawn. No audio hardware is used and nothing is played: the measurement
pages run on the fake backend. The room view is not rendered (it is being
removed from main in a separate change).
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

VIEWS = (
    "start",
    "overview",
    "fr",
    "fr_properties",
    "fr_measurements",
    "etc",
    "decay",
    "noise",
    "spectrogram",
    "waterfall",
    "compare",
    "project",
    "report",
    "measure_connection",
    "measure_signal",
    "measure_review",
    "measure_review_no_output",
    "daw_import",
    "saved_notice",
    "settings",
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--lang", default="zh_CN")
    parser.add_argument("--size", default="1280x800")
    parser.add_argument("--view", action="append", default=[])
    args = parser.parse_args(argv)
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ["REVERBSCOPE_AUDIO_BACKEND"] = "fake"
    os.environ["REVERBSCOPE_EDITION"] = "user"
    os.environ["REVERBSCOPE_COLOR_SCHEME"] = "dark"
    work = Path(tempfile.mkdtemp(prefix="reverbscope-polish-"))
    os.environ["REVERBSCOPE_HOME"] = str(work / "home")
    out: Path = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    width, height = (int(part) for part in args.size.split("x"))
    views = tuple(view for view in VIEWS if not args.view or view in args.view)
    try:
        _render(work, out, args.lang, width, height, views)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return 0


def _render(
    work: Path, out: Path, lang: str, width: int, height: int, views: tuple[str, ...]
) -> None:
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
    apply_application_chrome(app)
    demo = work / f"demo-{lang}"
    run_demo(demo)
    save_project(demo, Project(name=_(DEMO_ROOM_NAME)))
    for position in ("A", "B"):
        (demo / f"position-{position.lower()}").rename(demo / f"{position}-1")
        add_session(demo, demo / f"{position}-1", position=position)

    def pump(seconds: float) -> None:
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            app.processEvents()
            time.sleep(0.01)

    window: Any = MainWindow()
    window.resize(width, height)
    window.show()
    pump(0.3)

    def save(name: str, widget: Any = None) -> None:
        path = out / f"{lang}_{width}x{height}_{name}.png"
        if not (widget or window).grab().save(str(path)):
            raise OSError(f"cannot save {path}")
        print(path, flush=True)

    if "start" in views:
        window._show_start()
        pump(0.4)
        save("start")
    window.show_project(demo)
    window.model.wait_until_loaded()
    keys = [entry.key for entry in window.model.entries() if entry.result is not None]
    window.model.set_baseline(keys[0])
    window.model.set_current(keys[-1])
    window.model.set_overlay(keys[0], True)
    window.model.set_overlay(keys[-1], True)
    for view in views:
        if view == "start":
            continue
        if view == "measure_review_no_output":
            # The Run gate as a real interface shows it before an output is
            # picked by hand. The fake backend itself plays nothing and is
            # never gated, so the page is told it lists a real backend.
            page = window.standalone
            if not hasattr(page, "run_block_reason"):
                continue
            window.show_mode("standalone")
            page.flow.set_step(2)
            page._inventory_backend = "portaudio"
            page._explicit_output = None
            page._sync_run_button()
            pump(0.3)
            save(view)
            page._inventory_backend = "fake"
            page._sync_run_button()
            continue
        if view.startswith("measure_"):
            window.show_mode("standalone")
            window.standalone.flow.set_step(
                ("measure_connection", "measure_signal", "measure_review").index(view)
            )
            pump(0.3)
            save(view)
            continue
        if view == "daw_import":
            window.show_mode("universal_daw")
            window.daw.flow.set_step(2)
            pump(0.3)
            save(view)
            continue
        if view == "settings":
            dialog = SettingsDialog(window)
            dialog.show()
            pump(0.3)
            save(view, dialog)
            dialog.close()
            dialog.deleteLater()
            continue
        if view == "saved_notice":
            window.show_view("fr")
            pump(0.3)
            text = _("Session saved to {path}").format(path=str(demo / "B-1"))
            notify = getattr(window, "notify", None)
            if notify is not None:
                notify(text)
            else:
                window.statusBar().showMessage(text)
            pump(0.3)
            save(view)
            continue
        base = view.split("_")[0]
        window.show_view(base)
        pump(2.5 if base in ("spectrogram", "waterfall") else 0.4)
        worker = getattr(window.views[base], "_worker", None)
        if worker is not None:
            if not worker.wait(15_000):
                raise RuntimeError(f"{base} did not finish rendering")
            pump(0.3)
        if view.endswith("_properties"):
            window.set_inspector_open(True)
            pump(0.2)
        elif view.endswith("_measurements"):
            window.set_navigator_open(True)
            pump(0.2)
        save(view)
        window.reset_layout()
    window.close()
    pump(0.2)


if __name__ == "__main__":
    raise SystemExit(main())
