# Screenshots and demo media

Every image in the README comes from `roomscope demo`, a simulated room. None
of them shows a real measurement, and each one says so: the GUI images carry
a "Synthetic demo data" stamp and the README captions say "synthetic demo".
Replace them with real-room images only when a real measurement (with the
tester's permission) is available, and label those as real.

## Regenerating

```bash
pip install -e ".[dev,gui]"
QT_QPA_PLATFORM=offscreen python scripts/render_readme_assets.py   # writes docs/assets/
```

The script runs the demo in a temporary folder (`ROOMSCOPE_HOME` is redirected,
so your recent-session list is untouched), captures the CLI output with
colour, and grabs the Qt window offscreen. On Linux it needs the Qt system
libraries listed in CONTRIBUTING.md. Rerun it after any change to the report
wording or the GUI layout, and commit the new images with that change.

## What exists

| File | Size | Command / view | Used in |
| --- | --- | --- | --- |
| `docs/assets/gui-results.png` | 1120×860 | `roomscope gui` → open `roomscope-demo/position-a` → Overview | README "See it in action" (first image), README.zh-CN, social preview |
| `docs/assets/cli-demo.svg` | ~80–95 columns | `roomscope demo` (colour on) | README, collapsible "CLI" |
| `docs/assets/gui-compare.png` | 1120×1000 | Compare page, A → B, "Input gain unchanged" ticked | README, collapsible "Compare" |
| `docs/assets/gui-frequency-response.png` | 1120×860 | Results → Frequency Response tab, position A | README, collapsible "Frequency response" |
| `docs/assets/social-preview.png` | 1280×640 | Composed from `gui-results.png` | GitHub Settings → Social preview |

## Still to make (needs a person at a real desktop)

The offscreen renders cannot show the operating system's window frame, menus
or high-DPI fonts. Worth adding once someone runs RoomScope on a Mac or a
Windows PC:

1. **Animated GIF of the CLI demo** (~15 s, 900 px wide, ≤ 3 MB). Record with
   [asciinema](https://asciinema.org/) + `agg`, or
   [vhs](https://github.com/charmbracelet/vhs):
   `roomscope demo` → scroll to "4. Comparison" → `roomscope show roomscope-demo/position-a | head -20`.
   Place it above the fold in the README, replacing the static SVG.
2. **Native-window screenshots** (macOS light and dark mode, Windows 11) of
   the Home page, a result and the Compare page, 1440×900 or 2× retina,
   cropped to the window. Keep the "synthetic demo data" caption.
3. **GIF of the DAW workflow** (~20 s): generate the sweep, drag it into a DAW
   track, record, export, `roomscope analyze`. Only with a real DAW session,
   and labelled with the DAW name. This is the clearest way to show "works
   with your DAW".
4. **Real-room example** (after the first hardware report): the same four
   images from a real measurement, with the room and hardware named in the
   caption and the tester's permission.

## Rules

* Never pass off a synthetic result as a real measurement, in an image, an
  alt text or a caption.
* Keep each PNG under ~300 KB and each GIF under 3 MB; the README should load
  fast on a phone.
* Alt text describes what the image shows, including "synthetic" where it is.
