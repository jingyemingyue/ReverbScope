# ruff: noqa: N806, T201
# Design-phase mockup renderer (docs only, not product code).
"""WCAG 2.2 AA contrast check for the pro-desktop tokens (pk.LIGHT / pk.DARK).

    python contrast_pro.py [--md OUT.md]

Text pairs need >= 4.5:1, non-text (curves, cursors, control outlines, focus
ring, icons that carry meaning) need >= 3:1 (SC 1.4.3 / 1.4.11).
Exit status 1 when any required pair fails.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pk


def lum(h: str) -> float:
    h = h.lstrip("#")
    out = []
    for i in (0, 2, 4):
        c = int(h[i : i + 2], 16) / 255
        out.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
    return 0.2126 * out[0] + 0.7152 * out[1] + 0.0722 * out[2]


def ratio(a: str, b: str) -> float:
    la, lb = sorted((lum(a), lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


TEXT_FG = ["text", "muted", "faint"]
TEXT_BG = [
    "bg",
    "surface",
    "surface_alt",
    "toolbar",
    "sidebar",
    "panel",
    "hover",
    "selected",
    "readout_bg",
    "plot_bg",
]
PAIRS: list[tuple[str, str, float, str]] = []
for fg in TEXT_FG:
    for bg in TEXT_BG:
        PAIRS.append((fg, bg, 4.5, "text"))
PAIRS += [
    ("accent", "surface", 4.5, "text: link / active toggle"),
    ("accent_fg", "accent_soft", 4.5, "text: active tool label"),
    ("accent_fg", "panel", 4.5, "text: link in panel"),
    ("accent_fg", "selected", 4.5, "text: link in selected row"),
    ("accent_text", "accent", 4.5, "text: primary button"),
    ("accent_text", "accent_hover", 4.5, "text: primary hover"),
    ("accent_text", "accent_pressed", 4.5, "text: primary pressed"),
    ("plot_text", "plot_bg", 4.5, "text: axis ticks"),
    ("cursor_flag_text", "cursor", 4.5, "text: cursor flag"),
    ("planned", "planned_soft", 4.5, "text: planned badge"),
    ("planned", "surface", 4.5, "text: planned badge on surface"),
    ("info", "info_soft", 4.5, "text: synthetic badge"),
    ("good", "good_soft", 4.5, "text: status good"),
    ("warn", "warn_soft", 4.5, "text: status warning"),
    ("bad", "bad_soft", 4.5, "text: status critical"),
    ("info", "surface", 4.5, "text: info"),
    ("good", "panel", 4.5, "text: good in panel"),
    ("warn", "panel", 4.5, "text: warn in panel"),
    ("warn", "surface", 4.5, "text: warn in table"),
    ("bad", "surface", 4.5, "text: error"),
    ("border_strong", "surface", 3.0, "non-text: input outline"),
    ("border_strong", "panel", 3.0, "non-text: input outline in panel"),
    ("focus", "surface", 3.0, "non-text: focus ring"),
    ("focus", "toolbar", 3.0, "non-text: focus ring on toolbar"),
    ("accent", "toolbar", 3.0, "non-text: active icon on toolbar"),
    ("cursor", "plot_bg", 3.0, "non-text: cursor line"),
    ("plot_axis", "plot_bg", 3.0, "non-text: axis line"),
]
for i in range(1, 9):
    PAIRS.append((f"band_{i}", "plot_bg", 3.0, "non-text: band curve"))
    PAIRS.append((f"series_{i}", "plot_bg", 3.0, "non-text: curve"))
    PAIRS.append((f"series_{i}", "surface", 3.0, "non-text: legend swatch"))


def run(md: Path | None = None) -> int:
    fails = 0
    lines = [
        "| 主题 | 前景 | 背景 | 前景色 | 背景色 | 对比度 | 要求 | 用途 | 结果 |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for name, T in (("light", pk.LIGHT), ("dark", pk.DARK)):
        for fg, bg, need, use in PAIRS:
            r = ratio(T[fg], T[bg])
            ok = r >= need
            fails += not ok
            lines.append(
                f"| {name} | `{fg}` | `{bg}` | {T[fg]} | {T[bg]} | {r:.2f} | {need} | {use} | {'通过' if ok else '**未通过**'} |"
            )
            if not ok:
                print(f"FAIL {name}: {fg} {T[fg]} on {bg} {T[bg]} = {r:.2f} < {need} ({use})")
    print(f"{len(PAIRS) * 2} pairs, {fails} failures")
    if md:
        md.write_text(
            "# 专业桌面版 · 对比度检查（WCAG 2.2 AA）\n\n由 `contrast_pro.py` 生成。文字 ≥ 4.5:1，非文字（曲线、光标、控件边框、焦点环）≥ 3:1。\n\n"
            + "\n".join(lines)
            + f"\n\n共 {len(PAIRS) * 2} 对，未通过 {fails} 对。\n"
        )
    return 1 if fails else 0


if __name__ == "__main__":
    out = Path(sys.argv[sys.argv.index("--md") + 1]) if "--md" in sys.argv else None
    sys.exit(run(out))
