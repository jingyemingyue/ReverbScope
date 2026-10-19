# ruff: noqa
# Design-phase mockup renderer (docs only, not product code).
"""Render the light-sidebar baseline mockups.

QT_QPA_PLATFORM=offscreen python render.py [--only name1,name2] [--out DIR]
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtGui import QGuiApplication

app = QGuiApplication.instance() or QGuiApplication(sys.argv)
import lk  # noqa: E402

lk.load_fonts()
import lscreens as S  # noqa: E402

OUT = (
    Path(sys.argv[sys.argv.index("--out") + 1])
    if "--out" in sys.argv
    else lk.HERE.parent / "mockups"
)

JOBS = [
    ("01-home", S.home, ["zh-light", "en-light", "zh-dark"], (1280, 800)),
    ("02-measure-1-connect", S.measure_connect, ["zh-light"], (1280, 800)),
    ("03-measure-2-safe", S.measure_signal, ["zh-light", "en-light", "zh-dark"], (1280, 800)),
    ("04-measure-3-running", S.measure_running, ["zh-light", "zh-dark"], (1280, 800)),
    ("05-analysis-fr", S.analysis_fr, ["zh-light", "en-light", "zh-dark"], (1280, 800)),
    ("05b-analysis-fr-inspector", S.analysis_fr, ["zh-light"], (1440, 900)),
    ("06-analysis-decay", S.analysis_decay, ["zh-light"], (1280, 800)),
    ("07-analysis-waterfall", S.analysis_waterfall, ["zh-light"], (1280, 800)),
    ("08-compare", S.compare, ["zh-light"], (1280, 800)),
    ("09-settings", S.settings, ["zh-light"], (1280, 800)),
    ("10-narrow-fr", S.analysis_fr, ["zh-light"], (960, 640)),
    ("10b-narrow-measure-safe", S.measure_signal, ["zh-light"], (960, 640)),
    ("11-icon-spec", S.icon_sheet, ["zh-light"], (1280, 800)),
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
