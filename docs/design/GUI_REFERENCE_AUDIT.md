# GUI 2.0: reference audit

What the workstation borrows from other programs, and under what terms.
[GUI_2_ARCHITECTURE.md](GUI_2_ARCHITECTURE.md) is the design; this file is
the record that keeps it clean.

## What was consulted

The original workstation did not copy third-party source or assets. For
the focused-desktop redesign on 2026-10-17, the maintainer requested
Photoshop's design language. Adobe's public
[workspace overview](https://helpx.adobe.com/photoshop/desktop/get-started/learn-the-basics/workspace-overview.html)
and [contextual task bar guide](https://helpx.adobe.com/photoshop/desktop/get-started/learn-the-basics/boost-workflows-with-the-contextual-task-bar.html)
were consulted for the separation of document, tools and contextual options.
Adobe's material remains copyrighted; no screenshots, prose, icons,
fonts, colour tables, style sheets or implementation were copied.

The neutral UI colours in `ui/design/tokens.py` and monochrome geometric
tool drawings in `ui/components/tool_rail.py` are original ReverbScope
implementation, covered by this repository's license. They introduce no
third-party asset, font, palette package or dependency. Existing curve
colours and audited pyqtgraph colour maps are retained. The C7 review
therefore adds no license payload or dependency entry. System fonts are
used; a QA host's installed CJK fallback is not shipped as an app asset.

The interaction conventions below are common to measurement software in
general. They are named here so a reviewer can see that only the idea, not
an implementation, was taken.

| Convention | Where it appears in ReverbScope | Taken |
| --- | --- | --- |
| Document canvas, narrow tools, contextual options and optional properties | `ui/analysis_workspace.py`, `ui/components/` | Interaction pattern only; original native implementation |
| Measurement list with per-measurement colour and overlay check box | `ui/navigator.py` | The idea only |
| Energy-time curve with reflection markers | `ui/views/impulse.py`, `display/etc.py` | The idea; the envelope is ReverbScope's own reflection detector |
| Cumulative spectral decay ("waterfall") | `display/timefreq.py`, `ui/views/timefreq.py` | The textbook method (windowed slices with a rise and a taper); parameters are ReverbScope's |
| Spectrogram of the impulse response | `display/timefreq.py` | The textbook short-time Fourier transform |
| Fractional-octave display smoothing | `display/curves.py` | The textbook power average over ±1/(2N) octave |
| Wheel zoom about the cursor, drag to pan, double-click to fit | `ui/plotkit.py`, `ui/room/canvas.py` | The idea only |
| First-order image sources in a rectangular room | `geometry/paths.py` | The textbook image-source construction |

## Libraries

The existing desktop libraries are listed with their licenses in
[DEPENDENCIES.md](../DEPENDENCIES.md). pyqtgraph 0.14.0 (MIT) and its
`viridis` and `inferno` colour maps (CC0) are already included; the desktop
bundle ships only those two tables. This redesign adds no library.

## Rule for later changes

Before code, assets or text from another program is used, its license is
checked and recorded in this table, together with what was taken. A
program whose license does not allow it is not used, and its screenshots
are not used as a template either.
