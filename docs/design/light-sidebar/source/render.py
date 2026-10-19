# ruff: noqa
# Design-phase mockup renderer (docs only, not product code).
"""Render the light-sidebar baseline mockups.

PYTHONPATH=<repo>/src QT_QPA_PLATFORM=offscreen python render.py [--only name1,name2] [--out DIR]
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtGui import QGuiApplication

app = QGuiApplication.instance() or QGuiApplication(sys.argv)
import lk  # noqa: E402

lk.load_fonts()
import lscreens as S  # noqa: E402
import lscreens2 as S2  # noqa: E402

OUT = (
    Path(sys.argv[sys.argv.index("--out") + 1])
    if "--out" in sys.argv
    else lk.HERE.parent / "mockups"
)

JOBS = [
    ("01-home", S.home, ["zh-light", "en-light", "zh-dark"], (1280, 800)),
    ("02-measure-1-connect", S.measure_connect, ["zh-light"], (1280, 800)),
    ("02b-measure-no-output", S.measure_connect_no_output, ["zh-light", "en-light"], (1280, 800)),
    ("03-measure-2-safe", S.measure_signal, ["zh-light", "en-light", "zh-dark"], (1280, 800)),
    ("04-measure-3-running", S.measure_running, ["zh-light", "zh-dark"], (1280, 800)),
    ("05-analysis-fr", S2.frequency, ["zh-light", "en-light", "zh-dark"], (1280, 800)),
    ("05b-analysis-fr-inspector", S2.frequency, ["zh-light"], (1440, 900)),
    ("06-analysis-decay", S2.decay, ["zh-light"], (1280, 800)),
    ("07-analysis-waterfall", S2.waterfall, ["zh-light"], (1280, 800)),
    ("08-compare", S2.compare, ["zh-light"], (1280, 800)),
    ("09-settings", S2.settings, ["zh-light"], (1280, 800)),
    ("10-narrow-fr", S2.frequency, ["zh-light"], (960, 640)),
    ("10b-narrow-measure-safe", S.measure_signal, ["zh-light"], (960, 640)),
    ("11-icon-spec", S2.icon_sheet, ["zh-light"], (1280, 800)),
    ("12a-daw-1-signal", S2.daw_signal, ["zh-light"], (1280, 800)),
    ("12b-daw-2-record", S2.daw_record, ["zh-light"], (1280, 800)),
    ("12c-daw-3-import", S2.daw_import, ["zh-light", "en-light"], (1280, 800)),
    ("13-overview", S2.overview, ["zh-light", "en-light", "zh-dark"], (1280, 800)),
    ("13b-overview-inspector", S2.overview, ["zh-light"], (1440, 900)),
    ("14-time-etc", S2.time_etc, ["zh-light"], (1280, 800)),
    ("15-noise", S2.noise, ["zh-light"], (1280, 800)),
    ("16-spectrogram", S2.spectrogram_view, ["zh-light", "zh-dark"], (1280, 800)),
    ("17-room", S2.room, ["zh-light"], (1280, 800)),
    ("18-project", S2.project, ["zh-light"], (1280, 800)),
    ("19-report-export", S2.report_export, ["zh-light"], (1280, 800)),
    ("20-health", S2.health_sheet, ["zh-light"], (1280, 800)),
    ("20b-narrow-health", S2.health_sheet, ["zh-light"], (960, 640)),
]


def main():
    only = sys.argv[sys.argv.index("--only") + 1].split(",") if "--only" in sys.argv else None
    for name, fn, variants, (W, H) in JOBS:
        if only and not any(o in name for o in only):
            continue
        for v in variants:
            lang, theme = v.split("-")
            lk.set_mode(lang, theme, W, H)
            cv = lk.Canvas(name=name)
            fn(cv)
            lk.mock_label(cv)
            out = OUT / f"{name}.{v}.{W}.png"
            cv.save(out)
            print("ok", out.name, flush=True)
    if lk.OVERFLOWS:
        print("OVERFLOWS:")
        for o in lk.OVERFLOWS:
            print("  ", o)
    else:
        print("no text overflow")
    import json

    (lk.HERE / "icons_used.json").write_text(
        json.dumps({k: sorted(v) for k, v in sorted(lk.USED_ICONS.items())}, indent=1)
    )


if __name__ == "__main__":
    main()
