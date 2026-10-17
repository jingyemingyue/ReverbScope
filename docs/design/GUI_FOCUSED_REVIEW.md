# Focused desktop: draft review

The execution standard is [GUIDELINES.zh-CN.md](../GUIDELINES.zh-CN.md).
This is a maintainer-requested GUI redesign for review, not a release or a
hardware acceptance claim. The base is main `01291d8`, after PR #69.
Implementation and provenance are described in
[GUI_2_ARCHITECTURE.md](GUI_2_ARCHITECTURE.md) and
[GUI_REFERENCE_AUDIT.md](GUI_REFERENCE_AUDIT.md).

## Design

Photoshop's separation of document canvas, task options and optional
properties is the reference. ReverbScope now uses neutral charcoal chrome,
a large single canvas, four task destinations and a contextual view selector.
Measurements and Properties are closed by default and cover an edge without
resizing the chart. The interface and DAW workflows have distinct steps;
only an active take's transport stays visible across tasks.

The overview leads with four metrics and interpretation. Tables and
diagnostics expand on demand. Frequency response versus difference, and
decay curves versus band metrics, use full-canvas switches. Spectral
parameters expand when needed. Existing stored data, uncertainty, warnings,
validity and per-topic comparison verdicts remain available.

## Before and after

All images below use synthetic demo data and offscreen Qt. They do not show
hardware measurements. Before images use the main-branch GUI; after images
use this branch, with the same two-position demo. Chinese font fallbacks
were installed on the QA host; no font is bundled by this change.

| Main: permanent workstation columns | Draft: focused task canvas |
| --- | --- |
| ![Before: synthetic overview](../images/gui-focused/before-overview.zh-CN.png) | ![After: synthetic overview](../images/gui-focused/after-overview.zh-CN.png) |
| ![Before: synthetic decay](../images/gui-focused/before-decay.zh-CN.png) | ![After: synthetic decay](../images/gui-focused/after-decay.zh-CN.png) |

| Other task or state | Screenshot |
| --- | --- |
| Measurement review, Chinese, 1280×800 at 2× device pixels | ![Synthetic measurement setup](../images/gui-focused/measurement.zh-CN.png) |
| Frequency response, English, light preference, 960×640 | ![Synthetic frequency response](../images/gui-focused/frequency.en.png) |
| Room, Chinese, entered example geometry and measured constraints | ![Synthetic room](../images/gui-focused/room.zh-CN.png) |
| Comparison, English | ![Synthetic comparison](../images/gui-focused/compare.en.png) |
| Optional properties drawer | ![Synthetic measurement properties](../images/gui-focused/properties.zh-CN.png) |

## Feature coverage

| Capability | Implementation retained or reconstructed |
| --- | --- |
| Sweep → playback/recording → deconvolution → IR | `ui/pages.py`, existing measurement and analysis workers / preflight |
| Overview, RT / EDT / T20 / T30 / C50 / C80 | `ui/views/overview.py`, complete expandable metric tables |
| Schroeder decay and per-band reverberation | `ui/views/decay.py`, full-canvas chart switch |
| Frequency response, smoothing, overlays, alignment, baseline difference | `ui/views/frequency.py` |
| Impulse / ETC, early reflection selection | `ui/views/impulse.py`, linked room selection and expandable table |
| Noise spectrum and hum | `ui/views/noise.py` |
| Spectrogram and waterfall, transform controls, slice selection | `ui/views/timefreq.py`, original cancellation/cache/generation behavior |
| Full report and copy | `ui/views/report.py`, shared report renderer |
| 3D room, layers, camera/picking, placement, scan import | `ui/room/`, projected QPainter scene hosted in pyqtgraph |
| Comparison and project workflow | `ui/compare_view.py`, `ui/project_view.py`, original verdict and spatial-average data |
| Health diagnosis and chart routing | `ui/health_nav.py`, overview, optional inspector |
| Settings and bilingual UI | `ui/settings_dialog.py`, existing gettext `.po` catalog |

## Automated evidence

Commands run from the worktree with Python 3.12, the existing `dev,gui`
dependencies, and `PYTHONPATH=src`.

| Command | Result |
| --- | --- |
| `ruff check . && ruff format --check .` | Passed; 362 files already formatted |
| `mypy --platform linux` | Passed; 128 source files |
| `python scripts/check_doc_links.py` | Passed; docs and nine root documents |
| `python scripts/check_cli_docs.py` | Passed; 80 commands parsed for syntax, none executed |
| `python scripts/check_src_safety.py` | Passed |
| `QT_QPA_PLATFORM=offscreen pytest --cov=reverbscope.core --cov=reverbscope.models --cov-fail-under=85` | Passed; 3463 passed, one font-availability skip; 93.43% coverage against the 85% gate; clean process exit |
| `QT_QPA_PLATFORM=offscreen pytest tests/ui/test_gui_smoke.py::test_charts_draw_chinese_text_with_an_installed_cjk_font tests/ui/test_gui_zh.py` | Passed; five font/localization tests |

The full run's existing font-availability check skipped because Matplotlib's
loaded font cache had no CJK face. After a QA-host fallback was installed and
the cache refreshed, that exact test and the four Chinese-interface tests
passed in a fresh process. No skip was added and no font is bundled.

The screenshot runner covers 21 states × four sizes (960×640, 1280×800,
1366×768, 1920×1080) × two themes × two languages = 336 images.
Two additional 1280×800 dark runs at 2× device pixels include optional
measurement/properties drawers, spectral settings and four room cameras:
30 more images, 366 captures total. All four runner invocations exited
successfully. The following commands reproduce their flags with an example
output folder:

```bash
QT_QPA_PLATFORM=offscreen python scripts/render_gui2_screenshots.py --out /tmp/gui-review --lang en
QT_QPA_PLATFORM=offscreen python scripts/render_gui2_screenshots.py --out /tmp/gui-review --lang zh_CN
QT_QPA_PLATFORM=offscreen python scripts/render_gui2_screenshots.py --out /tmp/gui-review --lang en --width 1280 --scheme dark --scale 2 --view overview --view fr --view spectrogram --view room --view measure_connection --view measure_review --view settings --panels --cameras
QT_QPA_PLATFORM=offscreen python scripts/render_gui2_screenshots.py --out /tmp/gui-review --lang zh_CN --width 1280 --scheme dark --scale 2 --view overview --view fr --view spectrogram --view room --view measure_connection --view measure_review --view settings --panels --cameras
```

Each state was constructed and captured; selected before/after, narrow,
Chinese and 2× images were visually inspected. This is not a pixel-diff gate
or an assertion that every capture received a human review.

Behavior tests were migrated from splitter/mirrored-control assumptions to
persistent task pages and canonical controls. Their data, validity, safety,
range, export, unsaved-take and worker-lifetime checks remain. New tests
cover task switching without losing chart/document state, canvas tool modes,
saved-demo marking, and review values matching the selected settings.
Measurement controls now enter their final Qt layout directly, and the room
canvas detaches its custom scene item before closing the graphics view.
A new regression creates and closes eight windows, visits every measurement
step, checks the native table header type and confirms the windows are freed.
That regression passed; a separate 24-window lifecycle stress run also
completed without a crash.
A read-only AST comparison also confirmed that 18 existing preflight,
recording/analysis, cancellation and placement-argument methods are unchanged;
`core/`, `models/`, the audio backend, workers and dependency manifest have
no diff. All existing test functions remain. No skips, expected failures or
lower coverage gates were added.

## Remaining acceptance

Setup pages scroll vertically at short window heights. The top step buttons
also provide Previous/Continue navigation; the active take's Stop transport
stays outside the scrolling page. Review setup navigation on native screens.

Native macOS/Windows appearance, real audio-device names and channel lists,
a real sweep, immediate hardware mute, a DAW round trip and long-session
comfort still need maintainer testing. Offscreen screenshots and the fake
backend do not satisfy those checks. Keep the PR draft and require a
maintainer review before any merge. Public-release README images remain
on their current release design until the draft is accepted.
