# ruff: noqa: T201
# Design-phase mockup renderer (docs only, not product code).
"""Render the pro-desktop mockups offscreen.

QT_QPA_PLATFORM=offscreen python render_pro.py [--only SUBSTR] [--out DIR]
"""

from __future__ import annotations

import sys
from pathlib import Path

import pk

OUT = pk.OUT_DIR

# name, function, lang, theme, w, h
JOBS = [
    ("01-fr-pro", "screen_fr_pro", "zh", "dark", 1440, 900),
    ("01-fr-pro", "screen_fr_pro", "zh", "light", 1440, 900),
    ("01-fr-pro", "screen_fr_pro", "en", "light", 1440, 900),
    ("02-etc-cursors", "screen_etc", "zh", "light", 1440, 900),
    ("03-rt60-bands", "screen_rt60", "zh", "light", 1440, 900),
    ("04-waterfall", "screen_waterfall", "zh", "dark", 1440, 900),
    ("05-compare-dual", "screen_compare", "zh", "light", 1440, 900),
    ("06-fr-guided", "screen_guided", "zh", "light", 1440, 900),
    ("07-measuring", "screen_measuring", "zh", "dark", 1440, 900),
    ("08-narrow", "screen_narrow", "zh", "light", 1100, 720),
    ("09-minimum", "screen_minimum", "zh", "light", 960, 640),
    ("10-states", "screen_states", "zh", "light", 1440, 900),
    ("10-states", "screen_states", "zh", "dark", 1440, 900),
]


def main() -> None:
    only = sys.argv[sys.argv.index("--only") + 1] if "--only" in sys.argv else ""
    out = Path(sys.argv[sys.argv.index("--out") + 1]) if "--out" in sys.argv else OUT
    out.mkdir(parents=True, exist_ok=True)
    app = pk.app()
    import importlib

    for name, fn, lang, theme, w, h in JOBS:
        tag = f"{name}.{lang}-{theme}.{w}"
        if only and only not in tag:
            continue
        pk.set_mode(lang, theme, w, h)
        import pscreens

        importlib.reload(pscreens)
        f = getattr(pscreens, fn, None)
        if f is None:
            print("skip", tag)
            continue
        root = f()
        root.show()
        for _ in range(4):
            app.processEvents()
        clipped = []
        from PySide6.QtWidgets import QAbstractButton, QLabel

        for wdg in root.findChildren(QLabel) + root.findChildren(QAbstractButton):
            if not wdg.isVisible() or (
                isinstance(wdg, QLabel) and (wdg.wordWrap() or (wdg.pixmap() and not wdg.text()))
            ):
                continue
            txt = wdg.text()
            if (
                txt
                and max(wdg.fontMetrics().horizontalAdvance(t) for t in txt.split("\n"))
                > wdg.contentsRect().width() + 1
                and not isinstance(wdg, QAbstractButton)
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
