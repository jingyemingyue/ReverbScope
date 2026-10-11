# Desktop workbench: design references

The desktop app (`reverbscope gui`) is a measurement workbench: a chart area,
a list of the open measurements, an inspector for the selected one, and a
status line for the take that runs. Its layout and interaction model were
designed after reading three open-source audio tools. **No source text,
identifier list, icon or other asset was copied from any of them**: they are
all under copyleft licences (GPL), ReverbScope is Apache-2.0, and everything
in `src/reverbscope/ui/` is an independent implementation in PySide6 Widgets
(QMainWindow, QDockWidget, QSplitter, Qt Model/View, matplotlib canvases).
What follows records what was read, at which revision, and which design
choices were taken over, changed or rejected.

## Open Sound Meter (chart area + source list + properties bar)

* Repository: <https://github.com/psmokotnin/osm>, branch `master`, commit
  `1e08de2322f5e8849e1ba39e1d3993187a7cc75c`. Licence GPL-3.0-or-later.
* Files read: `qml/main.qml`, `qml/Charts.qml`, `qml/SideBar.qml`,
  `qml/PropetiesBar.qml`, `src/sourcelist.h`, `src/model/sourcemodel.h`.

| Pattern seen | ReverbScope |
| --- | --- |
| The window is a chart stack with a fixed-width source column on the right and a properties strip under the charts; the app opens straight into it. | `WorkbenchWindow`: charts in the centre, the measurement list in a right dock, the inspector in a bottom dock. The window opens on the workbench with "No measurement loaded"; there is no start page. |
| One to three stacked chart slots, each keeping its own chart type and ranges; slots beyond the count are hidden, not destroyed; the count is persisted. | One or two `PlotPanel`s in a vertical `QSplitter` ("One chart" / "Two charts", Ctrl+1 / Ctrl+2); the hidden panel keeps its kind and zoom; kinds, split and count are saved with the layout. |
| Three independent per-source states: one selected source, a set of checked sources, and each source's own "active" flag; colour identity assigned once by the list from a rotating palette. | `WorkspaceDocument` keeps the selected measurement, the visible set and the baseline apart; each measurement gets a colour from a fixed palette when it is added and keeps it in every chart and in the list. |
| The source list is a plain container; a thin list model adapts it to views and forwards fine-grained change signals. | `WorkspaceDocument` (QObject with signals) and `MeasurementListModel` (`QAbstractItemModel`, position groups → measurements) that only maps the document. |
| The properties strip shows one editor at a time for whatever object is pushed into it, and is cleared before the object disappears. | The inspector shows the selected measurement only, folds when nothing is selected, and is cleared before a measurement is closed. Unlike OSM's always-visible strip, it is a dock that opens on demand. |
| Rejected: the signal generator, the live spectrum default, phase and coherence charts, the remote-access panel. | ReverbScope draws only what an `AnalysisResult` holds: frequency response, decay, noise, impulse, early reflections, placement geometry. |

## Friture (independent panels, state and layout restore)

* Repository: <https://github.com/tlecomte/friture>, branch `master`, commit
  `0c6a787a2cc02efd7b6656c74cd2b5e4a5b6e81a`. Licence GPL-3.0-only.
* Files read: `friture/dockmanager.py`, `friture/dock.py`,
  `friture/main_window_view_model.py`, `friture/analyzer.py`.

| Pattern seen | ReverbScope |
| --- | --- |
| A manager object (not the window) owns the ordered panels, creates them as children of the main window and persists them under QSettings groups; the window stores its own geometry and state separately. | `WorkbenchWindow` saves `saveGeometry()` / `saveState()` plus the panel kinds, the chart count and the split under `QSettings("ReverbScope", "ReverbScope")`, restores them on a real launch only (`restore_layout=True` from `run_app`; tests start from the default), and "Reset layout" restores the default arrangement. |
| A panel is a thin host with a swappable content type; switching the type stashes the old type's settings so they come back when the type is chosen again. | A `PlotPanel` switches its chart kind from its control bar and keeps per-kind zoom; the document is untouched by view changes. |
| A redraw tick that is skipped when the window is not visible; panels can be paused. | A panel marks itself dirty while hidden and draws when shown (`refresh()` / `showEvent`); a hidden second chart costs nothing. |
| A root view model that composes smaller ones and holds no logic. | `WorkspaceController` (open, save, project, compare), `MeasurementController` (jobs, Stop) and the document are separate from the window, which only wires signals. |
| Rejected: QML panel chrome, the real-time ring buffer and timers. | ReverbScope has no live stream; the status line shows the take's real progress and a busy bar for the analysis, never a level meter without a level source. |

## Sonic Visualiser (panes, layers, the active object, linked zoom)

* Repositories: <https://github.com/sonic-visualiser/sonic-visualiser>, branch
  `default`, commit `11310565d0478b601cde331ff3e037aace7b4bfa`, with the
  pinned `svapp` (`76783215a715f6fb773fbe058b1352effd0dc810`) and `svgui`
  (`d5dccf33e3431bbe48731cd168cf2fb25c8ace32`) revisions. Licence
  GPL-2.0-or-later. Reference manual 5.2.1:
  <https://www.sonicvisualiser.org/doc/reference/5.2.1/en/> (Panes and
  Layers, Display Properties, Zoom and Scrolling, keyboard reference).
* Files read: `main/MainWindow.cpp`, `svapp/framework/MainWindowBase.cpp`,
  `svgui/view/View.h`, `svgui/view/Pane.h`, `svgui/view/PaneStack.h`,
  `svgui/layer/Layer.h`, `svgui/view/ViewManager.h`.

| Pattern seen | ReverbScope |
| --- | --- |
| A pane draws several layers over one another; exactly one pane is active and its front layer is the active layer; single-object commands act on it. | A chart draws every visible measurement as a layer; the selected measurement is drawn last and thicker and is the one the inspector, Save, Close and "Set as baseline" act on; the last-clicked panel is the active one for Locate and PNG export. |
| A layer can be hidden ("dormant") without being removed from its pane. | Unchecking a measurement in the list hides its curves everywhere and keeps the measurement, its selection and its baseline role. |
| Panes follow global scroll and zoom only when their axes are compatible; a spectrum pane (frequency axis) is never linked to time panes. | `ZoomLink` propagates x-limits only between panels with the same axis kind (frequency in Hz, time in s, time in ms); "Linked zoom" in the View menu switches it off. dBFS and relative dB are named in every y label and never shared. |
| A tabbed property box per pane, with the pane itself as one tab and names surfaced through tooltips to save space. | The inspector's tabs: Measurement quality, Diagnostics, Properties, Tables, Comparison, Report, with compact tables and tooltips instead of long captions. |
| Rejected: time-aligned playback, the overview strip, undoable pane commands, the layer editing commands. | Measurements are not edited in the GUI; opening and closing are plain list operations guarded by the unsaved-take question. |

## Choices of our own

* Three measurement states, not one "current session": selecting a
  measurement never hides another, a new take joins the list instead of
  replacing the result on screen, and a running job keeps its own identity
  so its result is added as a new entry whatever is selected meanwhile.
* No demo mode in the product: synthetic data (`reverbscope demo`, the fake
  audio backend) remains an automated-test facility, and a synthetic session
  that is opened is marked "synthetic data" in the list, the inspector and
  the title.
* The measurement entry points are dialogs (Standalone: devices, channels,
  signal, optional dimensions; Universal DAW: test signal, recording,
  channels), so the workbench stays the only workplace; the status line
  carries the real progress and Stop.
