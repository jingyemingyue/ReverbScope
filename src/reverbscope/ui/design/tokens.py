"""Original neutral desktop palette and logical-pixel measurements.

The reference is Photoshop's separation of canvas, options and properties,
not Adobe artwork or its implementation. See GUI_REFERENCE_AUDIT.md.
"""

SPACE = 8
PAGE_MARGIN = 28
SECTION_GAP = 24
CONTROL_HEIGHT = 30
CONTEXT_HEIGHT = 52
TOOL_RAIL_WIDTH = 48
DRAWER_WIDTH = 352
READING_WIDTH = 1080
FORM_WIDTH = 900
MIN_PLOT_HEIGHT = 260

DARK: dict[str, str] = {
    "bg": "#242424",
    "surface": "#2c2c2c",
    "surface_alt": "#353535",
    "border": "#494949",
    "text": "#eeeeee",
    "muted": "#b7b7b7",
    "accent": "#82b4ff",
    "accent_hover": "#a5caff",
    "accent_text": "#152033",
    "accent_soft": "#34435a",
    "good": "#91c9a1",
    "good_soft": "#283b2e",
    "warn": "#efc17c",
    "warn_soft": "#423725",
    "bad": "#f3a09d",
    "bad_soft": "#492e2e",
    "info": "#a4c6f7",
    "info_soft": "#2d3c52",
    "grid": "#494949",
    "canvas": "#202020",
}

LIGHT: dict[str, str] = {
    "bg": "#ededed",
    "surface": "#f7f7f7",
    "surface_alt": "#e3e3e3",
    "border": "#c8c8c8",
    "text": "#262626",
    "muted": "#555555",
    "accent": "#245d9f",
    "accent_hover": "#1c4b82",
    "accent_text": "#ffffff",
    "accent_soft": "#dce7f5",
    "good": "#286b3a",
    "good_soft": "#e2efe4",
    "warn": "#804600",
    "warn_soft": "#f8eddc",
    "bad": "#ab302e",
    "bad_soft": "#f8e4e4",
    "info": "#275b9b",
    "info_soft": "#e0eafa",
    "grid": "#d6d6d6",
    "canvas": "#fafafa",
}
