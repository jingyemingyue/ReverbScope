# ruff: noqa: T201
# Design-phase mockup renderer (docs only, not product code).
"""Render the PR #71 review v2 mockups offscreen.

. env.sh && QT_QPA_PLATFORM=offscreen python render_v2.py [--only SUBSTR] [--out DIR]
"""

from __future__ import annotations

import sys
from pathlib import Path

import pk

JOBS = [
    ("v2-01-measure-level", "screen_measure_level", "zh", "dark", 1440, 900),
    ("v2-02-measuring", "screen_measuring_v2", "zh", "dark", 1440, 900),
    ("v2-03-frequency", "screen_fr", "zh", "dark", 1440, 900),
    ("v2-04-decay", "screen_decay", "zh", "light", 1440, 900),
    ("v2-05-waterfall", "screen_waterfall", "zh", "dark", 1440, 900),
    ("v2-06-compare", "screen_compare", "zh", "light", 1440, 900),
    ("v2-07-narrow-960", "screen_narrow", "zh", "dark", 960, 640),
    ("v2-08-frequency", "screen_fr", "en", "light", 1440, 900),
    ("v2-09-measure-level-960", "screen_measure_level", "en", "dark", 960, 640),
    ("v2-10-measure-level", "screen_measure_level", "zh", "light", 1440, 900),
]


def main() -> None:
    only = sys.argv[sys.argv.index("--only") + 1] if "--only" in sys.argv else ""
    out = Path(sys.argv[sys.argv.index("--out") + 1]) if "--out" in sys.argv else pk.OUT_DIR
    out.mkdir(parents=True, exist_ok=True)
    app = pk.app()
    import importlib

    import v2screens

    for name, fn, lang, theme, w, h in JOBS:
        tag = f"{name}.{lang}-{theme}.{w}"
        if only and only not in tag:
            continue
        pk.set_mode(lang, theme, w, h)
        importlib.reload(v2screens)
        v2screens.install()
        pk.set_mode(lang, theme, w, h)
        root = getattr(v2screens, fn)()
        root.show()
        for _ in range(4):
            app.processEvents()
        from PySide6.QtWidgets import QAbstractButton, QLabel

        clipped = []
        for wdg in root.findChildren(QLabel) + root.findChildren(QAbstractButton):
            if not wdg.isVisible() or (
                isinstance(wdg, QLabel) and (wdg.wordWrap() or (wdg.pixmap() and not wdg.text()))
            ):
                continue
            txt = wdg.text()
            if (
                txt
                and isinstance(wdg, QLabel)
                and max(wdg.fontMetrics().horizontalAdvance(t) for t in txt.split("\n"))
                > wdg.contentsRect().width() + 1
            ):
                clipped.append(txt[:40])
            if (
                isinstance(wdg, QAbstractButton)
                and txt
                and wdg.sizeHint().width() > wdg.width() + 2
            ):
                clipped.append("[btn] " + txt[:40])
        if clipped:
            print("  CLIPPED:", clipped)
        pm = root.grab()
        path = out / f"{tag}.png"
        pm.save(str(path))
        root.close()
        root.deleteLater()
        app.processEvents()
        print(path.name, pm.width(), pm.height())


if __name__ == "__main__":
    main()
