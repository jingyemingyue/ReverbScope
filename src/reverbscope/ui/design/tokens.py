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
#: Height of the analysis view tabs and the task bar.
TAB_HEIGHT = 36
TASKBAR_HEIGHT = 44
#: Numbers (key figures, readouts, tables) in a monospace face with even
#: digit widths. Only installed faces are used; ReverbScope bundles none.
MONO_FAMILIES = (
    "IBM Plex Mono",
    "SF Mono",
    "JetBrains Mono",
    "Menlo",
    "Consolas",
    "DejaVu Sans Mono",
    "Noto Sans Mono CJK SC",
    "Source Han Sans CN",
    "Microsoft YaHei",
    "PingFang SC",
)

DARK: dict[str, str] = {
    # Graphite chrome with a faint cool cast; the chart canvas is the darkest
    # surface so curves read first (chart-first, as REW / Smaart / RX).
    "bg": "#1d1f23",
    "surface": "#24272c",
    "surface_alt": "#2c3036",
    "border": "#3a3f47",
    "text": "#e7e9ec",
    "muted": "#a4abb6",
    "accent": "#74a9f7",
    "accent_hover": "#93bdfa",
    "accent_text": "#0f1a2b",
    "accent_soft": "#263750",
    "good": "#86cf9d",
    "good_soft": "#1f3127",
    "warn": "#e9bb6c",
    "warn_soft": "#382f1f",
    "bad": "#f2948f",
    "bad_soft": "#3d2526",
    "info": "#97bdf3",
    "info_soft": "#223147",
    "grid": "#34383f",
    "canvas": "#17191c",
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
