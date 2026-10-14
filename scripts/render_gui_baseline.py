"""Archive Phase 0 GUI pages and timings from main or the #58 workstation.

Run once per language/theme/scale in a fresh process. Source imports are
selected explicitly, settings are temporary, and only fake audio is used.
This is source/offscreen evidence, not packaged cold-start or native acceptance.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import sys
import tempfile
import time
from pathlib import Path

SIZES = ((960, 640), (1280, 800), (1440, 900), (1920, 1080))


def main() -> int:
    started = time.perf_counter()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--demo", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--lang", choices=("en", "zh_CN"), required=True)
    parser.add_argument("--scheme", choices=("light", "dark"), required=True)
    parser.add_argument("--scale", choices=(1, 2), type=int, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(args.source.resolve() / "src"))
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    os.environ["QT_SCALE_FACTOR"] = str(args.scale)
    os.environ["REVERBSCOPE_AUDIO_BACKEND"] = "fake"
    os.environ["REVERBSCOPE_EDITION"] = "user"
    os.environ["REVERBSCOPE_COLOR_SCHEME"] = args.scheme
    args.out.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="reverbscope-baseline-") as home:
        os.environ["REVERBSCOPE_HOME"] = home
        os.environ.setdefault("MPLCONFIGDIR", str(args.out.resolve().parent / "mpl-cache"))
        from PySide6 import __version__ as qt_version
        from PySide6.QtCore import QPoint, QRect, Qt
        from PySide6.QtGui import QPainter, QPixmap
        from PySide6.QtWidgets import QApplication

        from reverbscope.i18n import activate
        from reverbscope.ui.app import install_qt_translations
        from reverbscope.ui.main_window import MainWindow
        from reverbscope.ui.settings_dialog import SettingsDialog
        from reverbscope.ui.theme import apply_application_chrome

        app = QApplication([])
        activate(args.lang)
        install_qt_translations(app)
        apply_application_chrome(app)
        window = MainWindow()
        window.resize(*SIZES[1])
        window.show()
        app.processEvents()
        startup_s = time.perf_counter() - started
        workstation = hasattr(window, "views")
        captures: list[dict[str, object]] = []
        switches: list[dict[str, object]] = []

        def settle() -> None:
            for _step in range(5):
                app.processEvents()

        def grab(name: str, widget: object = window) -> None:
            settle()
            pixmap = widget.grab()
            dpr = pixmap.devicePixelRatio()
            footer_h = window.fontMetrics().height() * 2
            stamped = QPixmap(pixmap.width(), pixmap.height() + round(footer_h * dpr))
            stamped.setDevicePixelRatio(dpr)
            stamped.fill(app.palette().window().color())
            painter = QPainter(stamped)
            painter.drawPixmap(QPoint(0, 0), pixmap)
            painter.setFont(app.font())
            painter.setPen(app.palette().windowText().color())
            painter.drawText(
                QRect(0, round(pixmap.height() / dpr), widget.width(), footer_h),
                Qt.AlignmentFlag.AlignCenter,
                (
                    "合成演示数据 · 离屏渲染"
                    if args.lang == "zh_CN"
                    else "Synthetic demo data · offscreen"
                )
                + " · "
                + args.revision[:7],
            )
            painter.end()
            filename = f"{args.lang}-{args.scheme}-{args.scale}x-{size[0]}x{size[1]}-{name}.png"
            if not stamped.save(str(args.out / filename)):
                raise RuntimeError(f"could not save {filename}")
            captures.append(
                {
                    "file": filename,
                    "page": name,
                    "requested_size": size,
                    "actual_size": [widget.width(), widget.height()],
                    "image_pixels": [stamped.width(), stamped.height()],
                    "device_pixel_ratio": dpr,
                    "synthetic": True,
                }
            )

        load_times = []
        try:
            for size in SIZES:
                window.resize(*size)
                window.show_home()
                grab("home")
                for mode in ("universal_daw", "standalone"):
                    window.show_mode(mode)
                    grab(mode)
                load_started = time.perf_counter()
                window.open_session_path(args.demo / "position-a")
                settle()
                load_times.append(time.perf_counter() - load_started)
                if workstation:
                    for view_id in window.views:
                        begin = time.perf_counter()
                        window.show_view(view_id)
                        settle()
                        switches.append(
                            {"size": size, "view": view_id, "s": time.perf_counter() - begin}
                        )
                        view = window.views[view_id]
                        if view_id in ("spectrogram", "waterfall"):
                            wait_started = time.perf_counter()
                            while view.result is None and time.perf_counter() - wait_started < 10:
                                app.processEvents()
                                time.sleep(0.01)
                            if view.result is None:
                                raise RuntimeError(f"{view_id} did not finish rendering")
                        grab(view_id)
                else:
                    for index in range(window.results.tabs.count()):
                        begin = time.perf_counter()
                        window.results.tabs.setCurrentIndex(index)
                        settle()
                        switches.append(
                            {
                                "size": size,
                                "view": f"result-{index}",
                                "s": time.perf_counter() - begin,
                            }
                        )
                        grab(f"result-{index}")
                window.show_compare()
                window.compare.set_paths(args.demo / "position-a", args.demo / "position-b")
                window.compare.same_gain.setChecked(True)
                window.compare.run_compare()
                grab("comparison-populated")
                window.show_project(args.demo)
                if workstation:
                    window.model.wait_until_loaded()
                grab("project-populated")
                settings = SettingsDialog(window)
                settings.show()
                grab("settings", settings)
                settings.close()
                settings.deleteLater()
        finally:
            window.close()
            settle()
        manifest = {
            "revision": args.revision,
            "language": args.lang,
            "theme": args.scheme,
            "scale": args.scale,
            "source": str(args.source.resolve()),
            "python": platform.python_version(),
            "platform": platform.platform(),
            "qt": qt_version,
            "evidence": "synthetic, offscreen; native and packaged acceptance unrun",
            "source_imports_to_first_window_s": startup_s,
            "measurement_open_s": load_times,
            "view_switches": switches,
            "captures": captures,
        }
        path = args.out / f"{args.lang}-{args.scheme}-{args.scale}x.json"
        path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"{path}: {len(captures)} synthetic screenshots")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
