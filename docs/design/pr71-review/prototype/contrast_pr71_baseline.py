# ruff: noqa: E731, T201
"""WCAG 2.x contrast for PR #71 tokens (as-is) and the proposed v2 tokens."""


def lum(h):
    h = h.lstrip("#")
    r, g, b = [int(h[i : i + 2], 16) / 255 for i in (0, 2, 4)]
    f = lambda c: c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def cr(a, b):
    la, lb = sorted([lum(a), lum(b)], reverse=True)
    return (la + 0.05) / (lb + 0.05)


PR71_DARK = {
    "bg": "#242424",
    "surface": "#2c2c2c",
    "surface_alt": "#353535",
    "border": "#494949",
    "text": "#eeeeee",
    "muted": "#b7b7b7",
    "accent": "#82b4ff",
    "accent_text": "#152033",
    "good": "#91c9a1",
    "warn": "#efc17c",
    "bad": "#f3a09d",
    "info": "#a4c6f7",
    "grid": "#494949",
    "canvas": "#202020",
}
PR71_LIGHT = {
    "bg": "#ededed",
    "surface": "#f7f7f7",
    "surface_alt": "#e3e3e3",
    "border": "#c8c8c8",
    "text": "#262626",
    "muted": "#555555",
    "accent": "#245d9f",
    "accent_text": "#ffffff",
    "good": "#286b3a",
    "warn": "#804600",
    "bad": "#ab302e",
    "info": "#275b9b",
    "grid": "#d6d6d6",
    "canvas": "#fafafa",
}
ENTRY = ["#177e89", "#e07a2e", "#7a5cc7", "#3f9c4a", "#c2437a", "#3b73c4", "#a88a12", "#7d8590"]
if __name__ == "__main__":
    out = []
    for name, t in (("PR71 dark", PR71_DARK), ("PR71 light", PR71_LIGHT)):
        for fg in ("text", "muted", "accent", "good", "warn", "bad", "info"):
            for bg in ("bg", "surface", "surface_alt", "canvas"):
                out.append((name, fg, bg, round(cr(t[fg], t[bg]), 2)))
        out.append((name, "accent_text", "accent", round(cr(t["accent_text"], t["accent"]), 2)))
        out.append((name, "border", "surface", round(cr(t["border"], t["surface"]), 2)))
        out.append((name, "grid", "canvas", round(cr(t["grid"], t["canvas"]), 2)))
        for i, c in enumerate(ENTRY):
            out.append((name, f"ENTRY_COLORS[{i}] {c}", "canvas", round(cr(c, t["canvas"]), 2)))
    for r in out:
        print(*r, sep="\t")
