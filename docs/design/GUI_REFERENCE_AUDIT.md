# GUI 2.0: reference audit

What the workstation borrows from other programs, and under what terms.
[GUI_2_ARCHITECTURE.md](GUI_2_ARCHITECTURE.md) is the design; this file is
the record that keeps it clean.

## What was consulted

No source code, icons, images, colour maps, style sheets or documentation
text of another room-acoustics or audio-measurement program was read,
copied or adapted while building the workstation. Every module under
`src/reverbscope/ui/` and `src/reverbscope/display/` was written for
ReverbScope (as was the removed `src/reverbscope/geometry/`, kept under the
tag `archive/3d-room-before-removal`).

The interaction conventions below are common to measurement software in
general. They are named here so a reviewer can see that only the idea, not
an implementation, was taken.

| Convention | Where it appears in ReverbScope | Taken |
| --- | --- | --- |
| Measurement list with per-measurement colour and overlay check box | `ui/navigator.py` | The idea only |
| Energy-time curve with reflection markers | `ui/views/impulse.py`, `display/etc.py` | The idea; the envelope is ReverbScope's own reflection detector |
| Cumulative spectral decay ("waterfall") | `display/timefreq.py`, `ui/views/timefreq.py` | The textbook method (windowed slices with a rise and a taper); parameters are ReverbScope's |
| Spectrogram of the impulse response | `display/timefreq.py` | The textbook short-time Fourier transform |
| Fractional-octave display smoothing | `display/curves.py` | The textbook power average over ±1/(2N) octave |
| Wheel zoom about the cursor, drag to pan, double-click to fit | `ui/plotkit.py` | The idea only |

## Libraries

The libraries the workstation uses are listed with their licenses in
[DEPENDENCIES.md](../DEPENDENCIES.md). The one new library is pyqtgraph
0.14.0 (MIT). Its `viridis` and `inferno` colour maps are CC0; the desktop
bundle ships only those two tables.

## Rule for later changes

Before code, assets or text from another program is used, its license is
checked and recorded in this table, together with what was taken. A
program whose license does not allow it is not used, and its screenshots
are not used as a template either.
