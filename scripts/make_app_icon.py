"""Draw ReverbScope's application icon and export it for every platform.

The icon is a scope: a lens with a graticule, a decaying trace with a sharp
attack (an impulse response), and two fading echoes of the trace for the
reverberation. It is original artwork for this repository (Apache-2.0, like
the rest of the tree); no third-party icon, font or image goes into it.

Two steps, because the glow needs SVG filters that Qt's SVG renderer and
Pillow do not draw:

1. ``python scripts/make_app_icon.py svg`` writes the two sources into
   ``packaging/icons``: ``reverbscope.svg`` (full detail) and
   ``reverbscope-small.svg`` (no graticule or echoes, heavier strokes; used at
   32 px and below so the small sizes stay crisp).
2. Rasterise each at 1024 x 1024 with a transparent background, for example
   with Chrome::

       chrome --headless=new --disable-gpu --hide-scrollbars \\
         --force-device-scale-factor=1 --default-background-color=00000000 \\
         --window-size=1024,1024 --screenshot=full.png file://$PWD/packaging/icons/reverbscope.svg

   then ``python scripts/make_app_icon.py export full.png small.png`` writes
   ``ReverbScope.iconset`` (turn it into ``ReverbScope.icns`` with macOS
   ``iconutil -c icns``), ``ReverbScope.ico``, ``reverbscope.png`` (512 px,
   for Linux desktop entries) and the window icons under
   ``src/reverbscope/ui/icons``.

The macOS artwork keeps Apple's margin (an 824 px tile on a 1024 px canvas);
Windows and Linux use the tile cropped to the full square, as their icons are.
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ICONS = ROOT / "packaging" / "icons"
WINDOW_ICONS = ROOT / "src" / "reverbscope" / "ui" / "icons"

# Window icons: the small artwork up to this size, the full artwork above.
SMALL_MAX = 32
WINDOW_SIZES = (16, 24, 32, 48, 64, 128, 256)
MACOS_WINDOW_SIZES = (128, 512)
ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)

_DEFS = """
  <linearGradient id="bg" x1="0.15" y1="0" x2="0.85" y2="1">
    <stop offset="0" stop-color="#1A6F7B"/>
    <stop offset="0.5" stop-color="#0D4450"/>
    <stop offset="1" stop-color="#062029"/>
  </linearGradient>
  <radialGradient id="glow" cx="0.5" cy="0.5" r="0.55">
    <stop offset="0" stop-color="#38C2CF" stop-opacity="0.35"/>
    <stop offset="1" stop-color="#38C2CF" stop-opacity="0"/>
  </radialGradient>
  <linearGradient id="sheen" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#FFFFFF" stop-opacity="0.10"/>
    <stop offset="1" stop-color="#FFFFFF" stop-opacity="0"/>
  </linearGradient>
  <linearGradient id="rim" x1="0.1" y1="0" x2="0.9" y2="1">
    <stop offset="0" stop-color="#FFFFFF"/>
    <stop offset="0.45" stop-color="#BDF4F8"/>
    <stop offset="1" stop-color="#2A9EAB"/>
  </linearGradient>
  <radialGradient id="lens" cx="0.5" cy="0.40" r="0.62">
    <stop offset="0" stop-color="#0E4B57"/>
    <stop offset="1" stop-color="#041419"/>
  </radialGradient>
  <linearGradient id="trace" x1="0" y1="0" x2="1" y2="0">
    <stop offset="0" stop-color="#FFFFFF"/>
    <stop offset="1" stop-color="#C9F6FA"/>
  </linearGradient>
  <linearGradient id="glass" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#FFFFFF" stop-opacity="0.13"/>
    <stop offset="1" stop-color="#FFFFFF" stop-opacity="0"/>
  </linearGradient>
  <filter id="shadow" x="-20%" y="-20%" width="140%" height="140%">
    <feDropShadow dx="0" dy="12" stdDeviation="14" flood-color="#000" flood-opacity="0.32"/>
  </filter>
  <filter id="soft" x="-30%" y="-30%" width="160%" height="160%">
    <feGaussianBlur stdDeviation="12"/>
  </filter>
  <clipPath id="clip"><rect x="100" y="100" width="824" height="824" rx="185"/></clipPath>
"""


def _trace(cx: float, cy: float, radius: float, shift: float = 0.0) -> str:
    """A decaying sine with a sharp attack, as polyline points."""
    left, right = cx - radius * 0.80, cx + radius * 0.80
    points = []
    for i in range(301):
        u = i / 300
        envelope = (1 - math.exp(-u * 60)) * math.exp(-3.2 * u)
        x = left + (right - left) * u + shift
        y = cy - math.sin(u * 6.5 * math.pi) * radius * 0.60 * envelope
        points.append(f"{x:.1f},{y:.1f}")
    return " ".join(points)


def _polyline(points: str, color: str, width: float, opacity: float, extra: str = "") -> str:
    return (
        f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width="{width:g}" '
        f'stroke-linecap="round" stroke-linejoin="round" opacity="{opacity:g}"{extra}/>'
    )


def icon_svg(*, small: bool = False) -> str:
    """The icon on a 1024 px canvas with the macOS margin."""
    cx = cy = 512.0
    radius = 318.0 if small else 300.0
    trace = _trace(cx, cy, radius)
    lens: list[str] = []
    if not small:
        for k in (-2, -1, 1, 2):
            offset = k * radius / 3
            for x1, y1, x2, y2 in (
                (cx - radius, cy + offset, cx + radius, cy + offset),
                (cx + offset, cy - radius, cx + offset, cy + radius),
            ):
                lens.append(
                    f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
                    'stroke="#A8EEF4" stroke-opacity="0.10" stroke-width="4"/>'
                )
        lens.append(
            f'<line x1="{cx - radius:.1f}" y1="{cy:.1f}" x2="{cx + radius:.1f}" y2="{cy:.1f}" '
            'stroke="#A8EEF4" stroke-opacity="0.24" stroke-width="5"/>'
        )
        # The reverberation: two later, fainter copies of the trace.
        lens.append(_polyline(_trace(cx, cy, radius, 84), "#3FC9D6", 12, 0.20))
        lens.append(_polyline(_trace(cx, cy, radius, 42), "#5FD9E5", 14, 0.40))
    stroke = 46.0 if small else 22.0
    lens.append(_polyline(trace, "#4FDCE9", round(stroke * 1.8), 0.85, ' filter="url(#soft)"'))
    lens.append(_polyline(trace, "url(#trace)", stroke, 1))
    if not small:
        lens.append(
            f'<rect x="{cx - radius:.1f}" y="{cy - radius:.1f}" width="{2 * radius:.1f}" '
            f'height="{radius * 0.75:.1f}" fill="url(#glass)"/>'
        )
    rim = 40 if small else 22
    inner_rim = (
        ""
        if small
        else f'<circle cx="{cx:g}" cy="{cy:g}" r="{radius - 13:g}" fill="none" '
        'stroke="#02151A" stroke-opacity="0.6" stroke-width="4"/>'
    )
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024" width="1024" height="1024">
<!-- ReverbScope application icon. Generated by scripts/make_app_icon.py; edit the script, not this file. -->
<defs>{_DEFS}
  <clipPath id="lensclip"><circle cx="{cx:g}" cy="{cy:g}" r="{radius - 2:g}"/></clipPath>
</defs>
<g filter="url(#shadow)"><rect x="100" y="100" width="824" height="824" rx="185" fill="url(#bg)"/></g>
<g clip-path="url(#clip)">
  <rect x="100" y="100" width="824" height="824" fill="url(#glow)"/>
  <circle cx="{cx:g}" cy="{cy + 10:g}" r="{radius + 18:g}" fill="#000" opacity="0.28" filter="url(#soft)"/>
  <circle cx="{cx:g}" cy="{cy:g}" r="{radius:g}" fill="url(#lens)"/>
  <g clip-path="url(#lensclip)">
  {"".join(lens)}
  </g>
  <circle cx="{cx:g}" cy="{cy:g}" r="{radius:g}" fill="none" stroke="url(#rim)" stroke-width="{rim}"/>
  {inner_rim}
  <rect x="100" y="100" width="824" height="412" fill="url(#sheen)"/>
</g>
<rect x="101.5" y="101.5" width="821" height="821" rx="183.5" fill="none" stroke="#FFFFFF" stroke-opacity="0.12" stroke-width="3"/>
</svg>
"""


def write_svgs() -> None:
    ICONS.mkdir(parents=True, exist_ok=True)
    (ICONS / "reverbscope.svg").write_text(icon_svg(), encoding="utf-8")
    (ICONS / "reverbscope-small.svg").write_text(icon_svg(small=True), encoding="utf-8")


def export(full_png: Path, small_png: Path) -> None:
    from PIL import Image  # matplotlib's dependency; only this tool needs it

    full = Image.open(full_png).convert("RGBA")
    small = Image.open(small_png).convert("RGBA")
    for image in (full, small):
        if image.size != (1024, 1024):
            raise SystemExit(f"expected 1024 x 1024 renders, got {image.size}")

    def scaled(image: Image.Image, size: int) -> Image.Image:
        return image.resize((size, size), Image.Resampling.LANCZOS)

    def mac(size: int) -> Image.Image:
        return scaled(small if size <= SMALL_MAX else full, size)

    # Windows and Linux: the tile without the macOS margin (and its shadow).
    full_bleed = {
        name: img.crop((100, 100, 924, 924)) for name, img in (("full", full), ("small", small))
    }

    def square(size: int) -> Image.Image:
        return scaled(full_bleed["small" if size <= SMALL_MAX else "full"], size)

    iconset = ICONS / "ReverbScope.iconset"
    iconset.mkdir(parents=True, exist_ok=True)
    for base in (16, 32, 128, 256, 512):
        mac(base).save(iconset / f"icon_{base}x{base}.png")
        mac(base * 2).save(iconset / f"icon_{base}x{base}@2x.png")
    ico = [square(size) for size in ICO_SIZES]
    ico[-1].save(
        ICONS / "ReverbScope.ico",
        sizes=[(size, size) for size in ICO_SIZES],
        append_images=ico[:-1],
    )
    square(512).save(ICONS / "reverbscope.png")
    WINDOW_ICONS.mkdir(parents=True, exist_ok=True)
    for size in WINDOW_SIZES:
        square(size).save(WINDOW_ICONS / f"app-{size}.png", optimize=True)
    for size in MACOS_WINDOW_SIZES:
        mac(size).save(WINDOW_ICONS / f"app-macos-{size}.png", optimize=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("svg", help="write packaging/icons/reverbscope*.svg")
    out = sub.add_parser("export", help="write the platform icons from two 1024 px renders")
    out.add_argument("full", type=Path, help="render of reverbscope.svg")
    out.add_argument("small", type=Path, help="render of reverbscope-small.svg")
    args = parser.parse_args(argv)
    if args.command == "svg":
        write_svgs()
    else:
        export(args.full, args.small)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
