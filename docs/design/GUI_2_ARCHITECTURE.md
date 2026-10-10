# GUI 2.0 desktop workstation: architecture

Status: implemented on the `claude/project-thread-fykasp` branch (draft pull
request). This document is the contract the workstation code follows. Each
section names the modules that implement it; a change to the behaviour
described here changes this file in the same commit.

The workstation rebuilds the desktop app around one window that keeps the
project, the measurement list, the chart and the measurement controls on
screen together. It reuses the analysis as it is: nothing in `core/`,
`models/`, `health.py` or `interpretation/` changes behaviour, and every
number the window shows is a number those modules computed. What is new is
display code (how stored data is drawn) and the room geometry the user
enters, which is stored apart from the measurements.

[GUI_REFERENCE_AUDIT.md](GUI_REFERENCE_AUDIT.md) records which other
programs were looked at, under which licenses, and what was and was not
taken from them.

## 1. Goals and non-goals

Goals, in the order resources go to them:

1. A workspace that keeps a measurement list, a large chart area, an
   inspector and a compact measurement strip on screen at once, with
   resizable regions and a layout that is restored at the next start.
2. Professional chart interaction: overlays in the list's colours, show and
   hide, a highlighted current curve, zoom, pan and reset, a cursor readout
   with units, a difference pane for comparisons, labelled display
   processing, and export of what is on screen.
3. A three-dimensional room view that is useful rather than decorative: it
   separates what the user entered, what a measurement constrains and what
   follows only from a geometric assumption.

Non-goals: new acoustic metrics, a room score, a new file format for
measurements, OpenGL rendering, or any change to the command line.

## 2. Window layout

`ui/main_window.py`, `ui/analysis_workspace.py`, `ui/navigator.py`,
`ui/inspector.py`, `ui/measure_strip.py`, `ui/start_panel.py`.

```
┌──────────────────────────────────────────────────────────────────────┐
│ menu bar                                                             │
├─────────────┬─────────────────────────────────────────┬──────────────┤
│ Navigator   │ view bar: Overview · Frequency · Impulse │ Inspector    │
│  project    │  · Decay · Noise · Spectrogram ·         │  health      │
│  positions  │  Waterfall · Room · Project · Compare    │  key figures │
│  takes      │ ─────────────────────────────────────── │  validity    │
│  (overlay,  │ current view (stack)                     │  conditions  │
│  colour,    │                                          │  properties  │
│  baseline)  │                                          │              │
├─────────────┴─────────────────────────────────────────┴──────────────┤
│ measure strip: mode · device · rate · channels · loopback · Start/Stop │
└──────────────────────────────────────────────────────────────────────┘
```

* The three columns are one horizontal `QSplitter`; the measure strip sits
  under it. Splitter sizes, the current view and the window geometry are
  saved in `ui.ini` (§8).
* `MainWindow.stack` is the workspace's `QStackedWidget`. It holds the start
  panel, the two measurement set-up pages (Universal DAW Mode, Standalone
  Mode, which Demo shares), every analysis view, the project view and the
  compare view.
* The start panel replaces the old home page. The marketing pills and the
  large mode cards are gone; the first-measurement card stays, can be
  dismissed, and comes back from Help ▸ Getting started.
* Shortcuts: `Ctrl+1` … `Ctrl+9` select the analysis views in the order of
  `default_views()`; `Ctrl+0` opens Compare. The measurement set-up pages
  moved to `Ctrl+Shift+1` (Universal DAW Mode), `Ctrl+Shift+2` (Standalone
  Mode) and `Ctrl+Shift+3` (Demo).
* Switching views never stops a take. The Standalone page used to stop the
  take when it was hidden; the measure strip now carries Stop (and `Esc`),
  so the take keeps running while the user looks at another view.

### 2.1 The continuous flow

Open a project → choose a position → measure or import → read the health →
analyse the curves → overlay another position → read the comparison verdict
→ save or export → measure the next position. Every step keeps the project,
the selection and the chart state: the workspace model (§3) owns them, not
the views.

The unsaved-take protection of 0.5 is kept and widened: every action that
would drop an unsaved take (New Measurement, a new take, closing the window,
removing the take from the list) asks first, with Save, Discard and Cancel.
Open Session and opening a project no longer replace anything: the session
is added to the list beside the take, and a project keeps the unsaved take
(it may be saved into that project). The take is the only live entry; a new
take replaces the previous one once the previous one is saved or
discarded.

The measure strip mirrors the active set-up page: its device, rate and
channel controls share the page's models, so a choice in either place is
the same choice. **Set up...** opens the page for what the strip does not
carry (sweep length, level, tape measurements, the DAW files). In DAW mode
Start reads "Import recording..." and analyses the chosen files. Choosing a
position in the navigator's menu ("Measure at …") or in the project view
fills the strip's position and the pages' position and room fields.

## 3. Workspace model

`ui/workspace.py` (`WorkspaceModel`, `Entry`, `ProjectLoader`).

The model is the single owner of what is open. Views and panels read it and
send requests to it; they never hold a measurement of their own.

* **Entry**: one measurement. `key` (the resolved session folder, or
  `take:<n>` for a live take that has no folder yet), `label`, `position`,
  `directory`, `session`, `result` (`None` while it loads), `findings`,
  `findings_problem`, `profile`, `color`, `unsaved`, `error` (why it could
  not be read) and `synthetic` (a demo take).
* **Current entry**: the one the inspector and the single-curve views
  describe.
* **Overlay**: the entries drawn together in the chart views. The current
  entry is always drawn; the others are drawn when their list check box is
  on.
* **Baseline**: the entry a comparison is made against (`set_baseline`).
  The compare view and the difference panes compare the current entry with
  it.
* **Colours**: each entry keeps one colour for its whole life, chosen when
  it is added from an eight-colour palette safe for colour-blind readers
  (Okabe–Ito order). Reloading a project keeps the colour of every entry
  that is still there, by key. The list swatch, the curves and the legend
  use the same colour.
* **Selected reflection**: `(key, index)` of the early reflection selected
  in the impulse view or the room view; `reflection_changed` tells both.
* **Background loading**: `ProjectLoader` (a `QThread`) reads the session
  folders of a project and emits one entry at a time; the window stays
  responsive while a large project opens. Every load carries a generation
  token; a result that arrives for an older generation is dropped.
* **Cache**: `cache_get(key, name)` / `cache_put(key, name, value)` keep
  display data per entry (decimated curves, spectrograms). An entry's cache
  is dropped when it is reloaded or removed.

Signals: `entries_changed`, `entry_updated(key)`, `current_changed(key)`,
`overlay_changed`, `baseline_changed`, `reflection_changed(key, index)`,
`project_changed`, `loading_changed(bool)`.

The 0.5 `MeasurementState` stays as the record of the live take and its
recording (the mode pages write it, Save reads it). When a take or an
analysis finishes, the window adds it to the model as an unsaved entry and
makes it current.

## 4. Views

`ui/views/base.py` (`AnalysisView`), `ui/views/*.py`,
`ui/analysis_workspace.py` (`default_views()`).

* An `AnalysisView` has a `view_id`, a translated `title()`, and a
  `refresh()` that draws from the model. A view redraws only while it is
  visible: a model signal that arrives while it is hidden marks it dirty,
  and `showEvent` draws it then. Ten hidden charts no longer redraw at every
  selection change.
* `default_views()` returns, in shortcut order: Overview (`overview`),
  Frequency response (`fr`), Impulse response / ETC (`etc`), Decay (`decay`),
  Noise (`noise`), Spectrogram (`spectrogram`), Waterfall (`waterfall`),
  Room (`room`), Project (`project`). Compare (`compare`) and the full text
  report (`report`) follow without a number.
* The 0.5 Results tabs are gone. Their content moved: the key figures,
  health and findings to Overview and the inspector; each chart to its view;
  the placement table to the room view's side panel (and, with a VALID
  height and separation, the ring of loudspeaker positions in the room's
  measured layer); the text report to the report view. "About this
  profile..." is in the inspector's Conditions section; Save Session is in
  the File menu and the navigator's menu.
* The compare view compares the model's baseline with the current entry.
  Its session picker (two saved sessions, as on the 0.5 Compare page) opens
  both into the list, makes the first the baseline and the second current,
  and folds away once a pair is shown.
* The inspector (`ui/inspector.py`) shows, for the current entry: the
  subtitle (room, position, microphone, profile, sample rate, folder),
  measurement health, key figures with validity, conditions, the comparison
  with the baseline (verdict per topic, "Input gain unchanged", "Open the
  comparison"), the selected reflection, and the room view's consistency
  checks.

## 5. Display data

`display/` holds the code that turns stored results into what is drawn. It
imports no Qt and never changes a result: every function takes arrays and
returns new arrays, and tests check that `result.to_dict()` is unchanged
afterwards.

### 5.1 Curves (`display/curves.py`)

* `peak_subset(x, y, max_points, *, log_x)`: a display subset that keeps the
  minimum and the maximum of each of `max_points / 2` buckets (equal width
  in `log10(x)` when `log_x`). Every point drawn is a stored point, so a
  notch keeps its depth and a peak its height. pyqtgraph's own
  `autoDownsample` (subsample or mean) is not used: it makes notches
  shallower.
* `smooth_fractional_octave(f, db, fraction)`: display smoothing over
  ±1/(2·fraction) octave, averaged in power. Labelled in the legend as
  display smoothing; the stored curve stays reachable (the raw curve can be
  shown, and CSV export writes which processing was applied).
* `level_offset(f, db, band=(500, 2000))`: the mean level in a band, used for
  level alignment of overlays. The offset is shown in the legend.
* `difference(f_a, a, f_b, b)`: `b − a` on `a`'s grid over the common range,
  interpolated in `log10(f)`.

### 5.2 Energy-time curve (`display/etc.py`)

The ETC uses the same envelope as the reflection detector
(`core.reflections.reflection_envelope_db`, hold 0.1 ms) and the same 0 dB
reference (the envelope maximum within ±0.5 ms of the direct sound). A
reflection marker is placed on the curve sample at its delay, so it lies
exactly on the curve and its level equals the stored `relative_db`.

### 5.3 Spectrogram and waterfall (`display/timefreq.py`)

Both are computed from the stored impulse response, never from the
recording, on a frequency grid anchored at 1 kHz (`1000 · 2^(k/n)` for
`n` points per octave).

* **Spectrogram** (`spectrogram(samples, sample_rate, direct_index, params)`):
  short-time Fourier transform with a Hann window of `window_ms`, advanced
  by `hop_ms`, over `time_range_ms` relative to the direct sound and
  `freq_range_hz`. Values are power spectral levels in dB; normalisation is
  `"peak"` (0 dB = the largest value shown), `"direct"` (0 dB = the frame
  that holds the direct sound) or `"none"` (dB re full scale²). Levels below
  `floor_db` are clipped to it for display only.
* **Waterfall / cumulative spectral decay**
  (`cumulative_spectral_decay(samples, sample_rate, direct_index, params)`):
  one spectrum per slice, the slice `k` starting `k · step_ms` after
  `start_ms` (relative to the direct sound) and lasting `window_ms`, with a
  half-Hann rise of `rise_ms` at its start and a half-Hann fall over the last
  `taper_percent` of the window. Levels are in dB relative to the peak of
  the first slice; optional `smoothing` (1/N octave, display only).
* Parameters are frozen dataclasses that validate themselves
  (`TimeFrequencyParamError`). Empty, too short or non-finite input raises
  `DisplayDataError`, whose message is an `N_` template with parameters, so
  the view shows it translated.
* Results carry `notes`: `(template, params)` tuples saying what was done
  (window, step, ranges, unit, normalisation, how many frames were dropped
  for lack of data). The views list them under the chart.
* A `cancelled` callable is polled between frames; when it returns true the
  transform raises `TransformCancelledError`. The views run the transforms
  in a `QThread` with a generation token and pass
  `cancelled=thread.isInterruptionRequested`.
* A single decaying mode of known T60 is used as a physical check in the
  tests: the waterfall's level at the mode frequency falls at 60 / T60 dB/s.

## 6. Charts

`ui/pg.py`, `ui/plotkit.py`, `ui/views/frequency.py`, `ui/views/impulse.py`,
`ui/views/decay.py`, `ui/views/noise.py`, `ui/views/timefreq.py`.

### 6.1 Library

Charts use pyqtgraph 0.14.0 (MIT). It draws with `QPainter` on the Qt that
the app already ships, keeps interaction fast on 100k-point curves, and
needs no OpenGL. matplotlib stays for the command line's scripts and the
README image renderer.

* pyqtgraph is imported in one place only: `ui/pg.py` (`pyqtgraph()`,
  `colormap(name)`, `svg_export(widget, path)`, `png_export(widget, path,
  scale=2.0)`). A test rejects `import pyqtgraph` anywhere else.
* pyqtgraph's own SVG exporter is broken on Qt 6.11; `svg_export` paints the
  scene into a `QSvgGenerator` instead.
* pyqtgraph's context menus and export dialog are English only; they are
  switched off on every plot. Export is in our own menu.
* `setLogMode` converts only `PlotDataItem`s, so frequency charts draw
  everything (curves, shading, markers, cursor) in `log10(Hz)` coordinates
  and label the axis in Hz themselves (`plotkit.LogFrequencyAxis`).
* `mkPen` styles are given as `Qt.PenStyle` members.

### 6.2 Interaction

Every chart (`plotkit.ChartPanel`) offers:

* wheel zoom about the cursor, drag to pan, a box zoom with the right
  button, double-click or `R` / the Reset button to fit;
* a cursor readout with units (`1.23 kHz  −4.5 dB`, `12.4 ms  −18.0 dB`)
  that reads the curve under the cursor, the current entry's by default;
* a legend whose names and colours match the measurement list, with the
  current curve drawn thicker;
* sensible default ranges: 20 Hz to the Nyquist frequency (or the
  excitation band, when it is narrower) on frequency axes, 60 dB under the
  99.5th percentile on level axes, the stored length on time axes;
* Export ▸ chart PNG, chart SVG, curve CSV (with a header that says which
  display processing was applied).

### 6.3 Frequency, impulse, decay and noise

* **Frequency response**: overlays in the entries' colours, display
  smoothing (none, 1/48 … 1/1 octave), level alignment, the stored curve on
  demand, shading outside the excitation band, and a difference pane under
  the chart when a baseline is set (current − baseline).
* **Impulse response / ETC**: the ETC (or the waveform) of the current entry
  and the overlays; reflection markers are clickable and select the
  reflection in the model (§3), which the room view follows.
* **Decay**: the Schroeder curves by band with the evaluation range of the
  chosen metric shaded, and a band chart of T values under it; a value that
  is not VALID is drawn hollow.
* **Noise**: the noise spectrum with the detected hum harmonics marked.

### 6.4 Room geometry and the room view

`geometry/room.py`, `geometry/paths.py`, `geometry/scan.py`,
`schemas/room-geometry.schema.json`, `ui/room/`.

**Three layers, never mixed.** Everything in the room view belongs to one
of three layers, each with its own line style, colour and label:

1. *Entered* (solid): the room box the user typed (length, width, height),
   the loudspeaker and the microphone positions, and an imported scan.
2. *Measured constraint* (dashed): what a measurement supports on its own:
   the direct distance (a sphere of that radius around the loudspeaker), and
   for a selected reflection the excess path and the ellipsoid of every
   point that could have reflected it, with its distance interval.
3. *Geometric assumption* (dotted): first-order specular paths computed
   from the entered box. They are an assumption about the room, not a
   measurement, and are labelled so.

**The geometry file.** `room-geometry.json` sits next to `project.json`
(or in the session folder when no project is open). It holds only what the
user entered: the box, the loudspeaker, the microphone of each position, an
optional scan reference (file name, units, up axis, yaw, offset, SHA-256),
and free notes. Measurements never write to it, and it never writes to a
session. Writes are atomic (temporary file, then rename); unknown keys are
kept; a file with a newer `schema_version` is read but not overwritten.
Renaming a position renames its microphone entry.

**What can be said.** A single microphone cannot locate a wall: one
reflection fixes an ellipsoid, not a point. The room view says so. When the
direct sound's confidence is low the overlays are withheld and
`overlay_refusal` says why. A selected reflection is matched against the
predicted first-order arrivals within a tolerance derived from the sample
period and the entered positions' uncertainty: *no match*, *one match*
(with the face named by its coordinates, e.g. "the face at x = 0 m") or
*ambiguous* (all candidates listed), always with the residual in ms.
`consistency_checks` compares the entered direct distance with the measured
one and reports each check in the inspector.

**Scans.** PLY (ASCII, binary little and big endian) and OBJ are read on a
worker thread with a size limit, a vertex limit, cancellation and voxel
thinning for display. The import dialog asks for the units, the up axis,
the yaw and the alignment; the choice is stored with the file's SHA-256.

**Rendering.** `ui/room/` draws with `QPainter` only: an orbit camera
(rotate, pan, zoom about the cursor, fit, reset), an axis triad and a metre
scale bar. The plan view allows dragging the loudspeaker and the
microphone. It runs offscreen, so it is tested and screenshotted in CI.

## 7. Threads and lifetimes

* Every `QThread` belongs to an object with a `shutdown()` that requests
  interruption (or stops the take) and waits for it. `MainWindow.closeEvent`
  calls every one of them before the window closes; a `QThread` destroyed
  while it runs aborts the process.
* Every background job carries a generation token. A result for an older
  generation (the selection changed, the project was closed, the window
  closed) is dropped without touching the model.
* No analysis is re-run for display. Zooming, panning, moving the cursor and
  changing display smoothing work on cached display data.
* pyqtgraph builds its context menus and plot-settings panel as parentless
  widgets that only its Python objects hold. `ui.pg.plot_widget` parents
  them to the plot (marked internal), and `ChartPanel.dispose` tears the plot
  down in pyqtgraph's order (`ui.pg.close_plot_widget`) when the window
  closes for good; left to the destructors, the scene deleted its items in
  whatever order the collector left them and crashed now and then.

## 8. Saved interface state

`ui.ini` in the ReverbScope home folder (`QSettings`, INI format):
`window/geometry`, `window/splitter`, `workspace/view`, and per project
(`project/<sha1 of the folder>/…`) the current entry, the overlay set and
the baseline, restored when that project is opened again. Missing or
unreadable keys fall back to defaults; nothing in `ui.ini` is needed to
open a session or a project.

## 9. Dependencies and packaging

* `pyqtgraph==0.14.0` joins the `gui` extra and the desktop bundle lock.
  License: MIT, read from the upstream repository; the license bundle
  carries it.
* PyInstaller excludes `pyqtgraph.opengl`, `pyqtgraph.examples`,
  `pyqtgraph.jupyter` and `PySide6.QtTest`, and the colour-map files the app
  does not use. The Terminal Edition excludes pyqtgraph altogether.
* `reverbscope doctor` lists the pyqtgraph version next to PySide6.

## 10. Words

New interface text goes through `_()` (module constants through `N_()`)
with its zh_CN entry in the same commit, using the established terms:
基准 / 对比项, 对比, 回采, 话筒, 扬声器, 音频接口, 频带, 延迟, 本底噪声, 余量,
脉冲响应, 频率响应, 测量健康, 能量时间曲线, 时频谱, 瀑布图. Two measurements
are 对比-ed, never 比较-d. Strings that already exist on main are not
reworded here.

## 11. Testing

* Offscreen (`QT_QPA_PLATFORM=offscreen`): the model, every view, the flow
  of §2.1, thread shutdown, unsaved-take prompts, old sessions and projects,
  the geometry file, the display transforms and the zh_CN interface.
* Ordinary desktop run, real Retina displays and measurements with a real
  audio interface and DAW are separate acceptance steps and are recorded as
  such in the pull request; offscreen tests do not stand in for them.
