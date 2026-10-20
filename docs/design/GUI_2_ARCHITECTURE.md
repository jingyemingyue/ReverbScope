# Focused desktop GUI: architecture

The execution standard is [GUIDELINES.zh-CN.md](../GUIDELINES.zh-CN.md).
This document describes the GUI implementation; it does not replace that
standard. The maintainer explicitly requested a complete GUI redesign,
Photoshop's design language, a dark default, all existing features including
the room view, and a draft for review. Those task decisions supersede the
older workstation's permanently visible columns. No DSP, audio backend,
measurement schema or dependency changes are part of this redesign.

[GUI_REFERENCE_AUDIT.md](GUI_REFERENCE_AUDIT.md) records the visual
references and the provenance of the implementation.

## 1. Goals and boundaries

One task occupies the content area. Neutral charcoal chrome, a large canvas,
quiet typography and optional properties follow the separation of tools,
document and contextual controls familiar from Photoshop. The task order
is Project, Measure, Analysis, Compare. This is a native PySide6 Widgets
application, with pyqtgraph for interactive plots and the room canvas.
There is no browser, external service or OpenGL requirement.

All measurements, validity words, health diagnoses and interpretations
continue to come from the existing analysis modules. Display controls
change the presentation of stored data. They never overwrite a result.
The reconstruction retains every analysis view, room geometry and scan
import, comparison, project action, settings field and bilingual string.

## 2. Shell and measurement flow

`ui/analysis_workspace.py`, `ui/main_window.py`, `ui/components/`,
`ui/design/`, `ui/pages.py`, `ui/measure_strip.py`.

| Area | Contents | Visibility |
| --- | --- | --- |
| Task bar | Project, Measure, Analysis, Compare; Save and Settings | Always |
| Context bar | Analysis view and current measurement, or measurement method and position | Current task only |
| Tools | Cursor, pan, box zoom, fit | Curve and time-frequency views |
| Canvas | One page in the existing persistent `QStackedWidget` | One active page |
| Measurements / Properties | Existing navigator and inspector inside edge drawers | Closed initially; one at a time |
| Transport | Phase, progress, status, return to measurement, Stop / Esc | While measuring or analyzing |

Drawers cover the canvas edge and can be closed from their header, context
button or View menu. They do not change chart geometry or axis limits.
The room has its own optional parameters drawer and camera controls.
Legacy splitter state cannot restore the old three-column layout.

The same `WorkspaceModel` and `MeasurementState` own selection, overlays,
baseline and live-take state. Task switches only change the current page;
they neither clear a measurement nor cancel a worker. Existing shortcuts
remain: Ctrl+1 through Ctrl+9, Ctrl+0 for Compare, Ctrl+Shift+1/2 for the
measurement methods, Ctrl+S for saving. Qt displays platform-native keys.

### 2.1 Measurement steps

| Method | Steps | Existing behavior retained |
| --- | --- | --- |
| Audio interface | Connection; Signal and level; Measure | Host API, input/output, channels, rate, loopback, sweep duration, level, profile, optional metadata and tape measurements |
| DAW recording | Test signal; Record in DAW; Import recording; Analyze | WAV and reference sidecar generation, recording instructions, microphone/loopback channel selection, external reference import, metadata, placement, profile |

Each step uses the original controls and preflight methods. Device settings
have one canonical copy on the measurement page; the previous strip's
mirrors are gone. The final interface step reads the actual chosen devices,
channels, rate, duration and level. Optional room and placement fields
expand on demand. Previous and Continue preserve entered values and never
start audio. Ctrl+Return invokes the existing measurement/analysis action.

During a take, device settings and step navigation are disabled. Stop and
Esc remain available in the global transport after changing tasks. The
original per-take playback confirmation, immediate mute, separate-clock
warning, cancellation and worker lifecycle are unchanged. The transport
is absent when idle. No product Demo mode was added; the fake backend
remains an automation tool, and saved synthetic sessions are marked using
the existing `DEMO_MODE` value.

### 2.2 Data protection

The original Save / Discard / Cancel protection remains on every action
that can drop an unsaved take. Opening a session adds it beside the current
take. Opening a project keeps that take. New Measurement, taking another
measurement, removing an unsaved entry and closing the window retain the
existing guards. A task button is navigation, not New Measurement.

## 3. Workspace model

`ui/workspace.py` (`WorkspaceModel`, `Entry`, `ProjectLoader`).

The model is the single owner of what is open. Views and panels read it and
send requests to it; they never hold a measurement of their own. The
navigator stays a `QTreeWidget` filled from this model. A
`QAbstractItemModel` would only mirror the same entries; a project is tens
of measurements, not a database, so the extra model would not make selection
or visibility any more reliable.

* **Entry**: one measurement. `key` (the resolved session folder, or
  `take:<n>` for a live take that has no folder yet), `label`, `position`,
  `directory`, `session`, `result` (`None` while it loads), `findings`,
  `findings_problem`, `profile`, `color`, `unsaved`, `error` (why it could
  not be read) and `synthetic` (a demo take).
* **Current entry**: the one the inspector and the single-measurement
  summaries describe. Selecting it does not change visibility.
* **Visible** (the overlay set): the entries drawn in the chart views.
  Hiding the current entry keeps it selected. The inspector still describes
  it; the charts do not draw it. A measurement is made visible when it is
  opened or when a take finishes, not when the user merely selects it.
* **Baseline**: the entry a comparison is made against (`set_baseline`).
  Setting it does not change visibility or selection. The compare view and
  the difference panes compare the current entry with it. A baseline curve
  is named in the legend.
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
  is dropped when it is reloaded or removed, and it moves with the entry
  when a take is saved under a folder key. The cache has an 8 MiB budget
  (`DISPLAY_CACHE_BUDGET`), not a hard memory cap. While more than one
  picture is stored, the oldest are dropped until the total fits. One
  picture larger than the budget is kept. A default spectrogram of a short
  sweep is about 1.9 MiB and a default waterfall about 115 KiB. The stored
  measurements are not in this cache.

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
  the placement table to the room view's parameters drawer (and, with a VALID
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
* The spectrogram and the waterfall also follow `overlay_changed`. Hiding
  the current measurement clears the picture at once. A worker that finishes
  afterwards may keep its result in the display cache when the impulse
  response it read is still that entry's result. It draws only when the
  generation, the measurement, the source result, the parameters and the
  visibility still match. "Cached" and "allowed to draw" are separate.
* A single decaying mode of known T60 is used as a physical check in the
  tests: the waterfall's level at the mode frequency falls at 60 / T60 dB/s.

## 6. Charts

`ui/pg.py`, `ui/plotkit.py`, `ui/views/frequency.py`, `ui/views/impulse.py`,
`ui/views/decay.py`, `ui/views/noise.py`, `ui/views/timefreq.py`.

### 6.1 Library

Charts use pyqtgraph 0.14.0 (MIT). It draws with `QPainter` on the Qt that
the app already ships, keeps interaction fast on 100k-point curves, and
needs no OpenGL. The tape-measure schematic is also a pyqtgraph plot,
explicitly labelled as entered dimensions rather than a measured room.
matplotlib stays for static helper/export and README rendering functions.

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
  button, double-click or `R` / the Frame button to fit;
* Axes opens exact lower and upper limits in the labelled units, with
  positive limits for logarithmic frequency axes and strictly increasing
  limits on both axes. A chosen range survives display processing and
  redraws until Frame; linked frequency and difference charts share x limits;
* a cursor readout with units (`1.23 kHz  −4.5 dB`, `12.4 ms  −18.0 dB`)
  that reads the curve under the cursor, the current entry's by default;
* a legend whose names and colours match the measurement list, with the
  current curve drawn thicker;
* sensible default ranges: 20 Hz to the Nyquist frequency (or the
  excitation band, when it is narrower) on frequency axes, 60 dB under the
  99.5th percentile on level axes, the stored length on time axes;
* Export ▸ chart PNG, chart SVG, curve CSV (with a header that says which
  display processing was applied).

The overview puts RT60, C50, noise and reflections before interpretation.
Diagnostics, complete metric tables and direct-sound details expand on demand.
Valid numbers retain a neutral validity label; warnings and invalid values
retain their status. The inspector's conditions also expand on demand.
Paths use an elided line with the full path available on hover. Body text is
14 logical pixels; hints are 12, chart and UI fonts share Chinese fallbacks.
Original neutral light/dark tokens and spacing live in `ui/design/`.
A new installation starts dark; explicit saved light or system choices remain
available in the tabbed Settings dialog.

Room parameters starts closed and reveals the existing inputs, scan import
and reflection selection in an overlay drawer. The room camera fits
after a hidden view's layout becomes visible, unless the user already moved
it. This does not change geometry, predictions or saved measurement data.

### 6.3 Frequency, impulse, decay and noise

* **Frequency response**: overlays in the entries' colours, display
  smoothing (none, 1/48 … 1/1 octave), level alignment, the stored curve on
  demand and shading outside the excitation band. A display selector switches
  the full canvas between response and current-minus-baseline difference.
  Both charts retain their linked x range and export controls.
* **Impulse response / ETC**: the ETC (or the waveform) of the current entry
  and the overlays; reflection markers are clickable and select the
  reflection in the model (§3), which the room view follows. The complete
  reflection table is available in an expandable details section.
* **Decay**: the Schroeder curves by band with the evaluation range of the
  chosen metric shaded, or a full-canvas band chart of T values, selected
  with the display control; a value that is not VALID is drawn hollow.
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

**What is on at first.** Entered geometry and the measured layer are on.
Predicted paths (the geometric assumption) are off until that layer is
ticked. **All constraints** is off: the selected reflection is a short
ellipsoid, and other predicted paths are not drawn. Turning it on draws the
direct-distance sphere, the full ellipsoid and every predicted path, still
dotted and labelled as an assumption. **Restore default view** puts the
layers and the camera back. The choice is saved in `ui.ini`.

**Rendering.** `ui/room/` puts the existing `QPainter` projected scene in a
pyqtgraph `GraphicsView`, without OpenGL: an orbit camera
(rotate, pan, zoom about the cursor, fit, reset), an axis triad labelled
length / width / up, a metre scale bar, the entered floor filled faintly,
and a mark on the front edge (the face at y = 0). Fit frames the entered
box, the loudspeaker, the current microphone, the dimension captions and
whatever measured constraint or highlighted assumption is actually drawn.
It then steps the camera back until those points sit inside a margin, so
the near corner and the captions are not cut off on the right or the
bottom. A resize refits until the user orbits, pans or zooms. The canvas names the
camera: plan (true to scale, front along the lower edge), front, side, or
a free perspective after the user orbits. Front and side are pitched enough
that the box reads as a volume; the near face is still the one the preset
names. Device names and the length, width and height captions are placed
in screen space so a loudspeaker and the current microphone, or two
dimension captions, do not cover each other. The plan view allows dragging
the loudspeaker and the microphone. It runs offscreen, so it is tested and
screenshotted in CI.

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
`window/geometry`, `shell/version`, `workspace/view`, a display alias per
measurement key, and per project
(`project/<sha1 of the folder>/…`) the current entry, the overlay set and
the baseline, restored when that project is opened again. Drawers always
start closed. Old splitter and panel-open keys are ignored. Missing or
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
are 对比-ed, never 比较-d. New task, step, control and accessibility strings
are translated in the existing `reverbscope.po`. The language restart hint
uses that catalog too; open windows keep their active language until restart.

## 11. Testing

* Offscreen (`QT_QPA_PLATFORM=offscreen`): the model, every view, the flow
  of §2.1, thread shutdown, unsaved-take prompts, old sessions and projects,
  the geometry file, the display transforms and the zh_CN interface.
* Ordinary desktop run, real Retina displays and measurements with a real
  audio interface and DAW are separate acceptance steps and are recorded as
  such in the pull request; offscreen tests do not stand in for them.

## 12. Screenshots and review

`render_gui2_screenshots.py` uses the synthetic two-position project,
marks it as synthetic, and opens all analysis pages including Noise and
Report, both measurement workflows, and Settings. It covers 960×640,
1280×800, 1366×768 and 1920×1080, in both dark and the saved light
preference. `--lang en` and `--lang zh_CN` select the catalog.
`--scale 2` checks device-pixel scaling; it is not a Retina hardware test.
The room's plan/front/side cameras remain available through `--cameras`;
`--panels` also captures optional measurement/properties drawers and settings.

    QT_QPA_PLATFORM=offscreen python scripts/render_gui2_screenshots.py --out /tmp/gui-review

Curated before/after images and the validation record are in
[GUI_FOCUSED_REVIEW.md](GUI_FOCUSED_REVIEW.md). The draft does not replace
the public-release README images. Hardware audio, a real DAW round trip,
and native macOS/Windows appearance still require maintainer acceptance.
