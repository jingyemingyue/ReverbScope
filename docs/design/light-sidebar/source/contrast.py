# ruff: noqa
"""WCAG 2.x contrast for the light-sidebar tokens. Writes contrast.md."""

import lk


def lum(h):
    h = h.lstrip("#")
    r, g, b = [int(h[i : i + 2], 16) / 255 for i in (0, 2, 4)]
    f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def cr(a, b):
    la, lb = sorted([lum(a), lum(b)], reverse=True)
    return (la + 0.05) / (lb + 0.05)


TEXT = [
    ("text1", "window"),
    ("text1", "sidebar.bot"),
    ("text1", "surface"),
    ("text2", "window"),
    ("text2", "sidebar.bot"),
    ("text2", "surface"),
    ("text3", "window"),
    ("text3", "sidebar.bot"),
    ("text3", "sidebar.top"),
    ("text3", "surface"),
    ("text3", "sunken"),
    ("text1", "sel.sidebar"),
    ("accent.text", "window"),
    ("accent.text", "surface"),
    ("accent.text", "accent.soft"),
    ("on.accent", "accent"),
    ("on.crit", "crit"),
    ("warn", "warn.soft"),
    ("warn", "window"),
    ("warn", "surface"),
    ("good", "window"),
    ("crit", "crit.soft"),
    ("info", "surface"),
    ("planned", "planned.soft"),
    ("plot.text", "plot.bg"),
    ("plot.text", "window"),
    ("text1", "readout"),
    ("text3", "readout"),
]
NONTEXT = [
    ("cur", "plot.bg"),
    ("base", "plot.bg"),
    ("delta", "plot.bg"),
    ("d2", "plot.bg"),
    ("d7", "plot.bg"),
    ("axis", "plot.bg"),
    ("cursor", "plot.bg"),
    ("control", "surface"),
    ("control", "window"),
    ("accent", "window"),
    ("focus", "surface"),
    ("crit", "window"),
    ("warn", "plot.bg"),
    ("grid.major", "plot.bg"),
    ("grid.minor", "plot.bg"),
]
out = [
    "# Contrast (WCAG 2.x) — light-sidebar tokens",
    "",
    "Text: AA ≥ 4.5 (body) · Non-text / chart lines: ≥ 3.0 (WCAG 1.4.11). Grid lines are intentionally < 3 (decorative, not information).",
    "",
]
fails = []
for kind, pairs, th in (("文字 Text", TEXT, 4.5), ("非文字 Non-text", NONTEXT, 3.0)):
    out += [f"## {kind}", "", "| fg | bg | light | dark | 结果 |", "|---|---|---|---|---|"]
    for fg, bg in pairs:
        l = cr(lk.LIGHT[fg], lk.LIGHT[bg])
        d = cr(lk.DARK[fg], lk.DARK[bg])
        deco = fg.startswith("grid")
        ok = deco or (l >= th and d >= th)
        if not ok:
            fails.append((fg, bg, l, d))
        out.append(
            f"| `{fg}` | `{bg}` | {l:.2f} | {d:.2f} | {'装饰（豁免）' if deco else ('✓' if ok else '✗')} |"
        )
    out.append("")
import lcharts

out += [
    "## 瀑布时间色阶 Waterfall ramp (vs plot.bg)",
    "",
    "| theme | stops | min ratio |",
    "|---|---|---|",
]
for th, stops, bg in (
    ("light", lcharts.RAMP_LIGHT, lk.LIGHT["plot.bg"]),
    ("dark", lcharts.RAMP_DARK, lk.DARK["plot.bg"]),
):
    rs = [cr(s, bg) for s in stops]
    out.append(f"| {th} | {' '.join(stops)} | {min(rs):.2f} |")
    if min(rs) < 3:
        fails.append((th, "ramp", min(rs), 0))
out.append("")
open("contrast.md", "w").write("\n".join(out))
print("fails:", fails)
